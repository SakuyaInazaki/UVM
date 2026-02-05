"""
UVM 地图位置爬虫 - 多策略 POI 爬取模块

改进版：更精确的数据提取和清洗

作者: UVM Research Team
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List, Tuple

from playwright.async_api import async_playwright, Page


CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "clean_pois.csv",
    "headless": False,
    "keywords": [
        "自动售货机", "便利店", "无人售货", "物美便利店",
        "罗森便利店", "全家便利店", "7-11", "便利蜂",
    ],
}

CSV_HEADERS = ["uid", "name", "address", "keyword", "city", "crawl_time"]


class POISaver:
    def __init__(self, output_dir: str, output_file: str):
        self.output_path = Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_path / output_file
        self.seen: Set[str] = set()
        self._init_csv()

    def _init_csv(self):
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            with open(self.file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()
            print(f"✓ 文件: {self.file_path}")

    def is_valid_name(self, name: str) -> bool:
        """验证POI名称是否有效"""
        # 过滤包含HTML/CSS的无效数据
        invalid_patterns = [
            'transform:', 'user-select', 'data-index=', 'data-stat-',
            'class="', 'title="', '<', '>', 'css', ';', '=',
            'px;', 'none;', '10px', '33px',
        ]
        for pattern in invalid_patterns:
            if pattern in name:
                return False
        # 过滤纯数字或特殊字符
        if not re.search(r'[\u4e00-\u9fff]', name):  # 没有中文字符
            return False
        if len(name) < 5 or len(name) > 100:
            return False
        return True

    def clean_name(self, name: str) -> str:
        """清洗名称"""
        # 移除title属性后的内容
        name = re.sub(r'".*$', '', name)
        # 移除CSS样式
        name = re.sub(r'"?\s*transform:.*', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def save_poi(self, name: str, address: str = "", keyword: str = "") -> bool:
        name = name.strip()
        name = self.clean_name(name)

        if not self.is_valid_name(name):
            return False

        uid = name
        if uid in self.seen:
            return False
        self.seen.add(uid)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "uid": uid,
                "name": name,
                "address": address[:100],
                "keyword": keyword,
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  [{keyword}] {name}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


class MultiStrategyScraper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.saver = POISaver(config["output_dir"], config["output_file"])

    async def run(self):
        print(f"\n{'='*60}")
        print(f"多策略地图POI爬虫 (改进版)")
        print(f"{'='*60}")
        print(f"城市: {self.config['city']}")
        print(f"关键词: {self.config['keywords']}")
        print(f"{'='*60}\n")

        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/clean_scraper",
                headless=self.config["headless"],
                executable_path=chrome_path,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                await self.search_all_keywords(page)
                await self.extract_store_chains(page)
            except Exception as e:
                print(f"\n[ERROR] {e}")
            finally:
                await browser.close()

        print(f"\n{'='*60}")
        print(f"爬虫完成！共获取 {self.saver.get_count()} 条 POI")
        print(f"数据已保存至: {self.saver.file_path}")
        print(f"{'='*60}\n")

    async def search_all_keywords(self, page: Page):
        """搜索所有关键词"""
        print(f"[策略] 关键词搜索")

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")
            try:
                await page.goto("https://map.baidu.com/", wait_until="domcontentloaded")
                await asyncio.sleep(2)

                search_box = await page.wait_for_selector("#sole-input", timeout=10000)
                await search_box.click()
                await page.keyboard.press("Control+A")
                await search_box.fill(f"{self.config['city']}{keyword}")
                await asyncio.sleep(1)
                await page.keyboard.press("Enter")
                await asyncio.sleep(8)

                # 提取数据
                pois = await self.extract_pois_clean(page)
                for poi in pois:
                    self.saver.save_poi(poi["name"], poi.get("address", ""), keyword)

                # 滚动加载更多
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    pois = await self.extract_pois_clean(page)
                    for poi in pois:
                        self.saver.save_poi(poi["name"], poi.get("address", ""), keyword)

            except Exception as e:
                print(f"  ! 失败: {e}")

    async def extract_store_chains(self, page: Page):
        """提取连锁便利店"""
        print(f"\n[策略] 连锁品牌搜索")

        # 直链搜索特定品牌
        brands = ["全家便利店", "罗森", "7-11便利店", "物美便利店", "便利蜂"]

        for brand in brands:
            print(f"\n  搜索: {brand}")
            try:
                url = f"https://map.baidu.com/search/{brand}/{self.config['city']}"
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(5)

                pois = await self.extract_pois_clean(page)
                for poi in pois:
                    self.saver.save_poi(poi["name"], poi.get("address", ""), brand)

                # 滚动
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  ! 失败: {e}")

    async def extract_pois_clean(self, page: Page) -> List[Dict[str, Any]]:
        """精确提取POI数据"""
        try:
            # 使用 JavaScript 精确提取 POI 名称
            js_code = """() => {
                const results = [];
                const seenNames = new Set();

                // 方法1: 从搜索结果列表提取
                // 百度地图的搜索结果通常在特定的DOM结构中
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const text = el.textContent ? el.textContent.trim() : '';

                    // 跳过明显不是POI的元素
                    if (text.length < 5 || text.length > 150) return;

                    // 检查是否包含关键词
                    if (!text.includes('便利店') && !text.includes('超市') &&
                        !text.includes('售货机') && !text.includes('商场') &&
                        !text.includes('7-11') && !text.includes('全家') &&
                        !text.includes('罗森') && !text.includes('物美')) {
                        return;
                    }

                    // 跳过包含HTML属性的文本
                    if (text.includes('transform') || text.includes('data-index') ||
                        text.includes('class=') || text.includes('px;')) {
                        return;
                    }

                    // 尝试获取href或title属性
                    const title = el.getAttribute('title') || '';
                    const href = el.getAttribute('href') || '';

                    // 优先使用title属性（通常包含完整名称）
                    let name = title || text;

                    // 如果text包含了更多完整信息，使用text
                    if (text.length > name.length && text.split('\\n').length < 3) {
                        name = text;
                    }

                    // 清理名称
                    name = name.replace(/\\s+/g, ' ').trim();

                    if (name.length >= 5 && name.length <= 100 && !seenNames.has(name)) {
                        // 检查是否是有效名称（包含中文和数字/字母）
                        if (/[\\u4e00-\\u9fff]/.test(name)) {
                            seenNames.add(name);
                            results.push({name: name, address: ''});
                        }
                    }
                });

                // 方法2: 查找链接元素
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent ? a.textContent.trim() : '';
                    if (text.length >= 5 && text.length <= 100) {
                        // 检查是否包含目标关键词
                        const keywords = ['便利店', '超市', '售货机', '商场', '7-11', '全家', '罗森'];
                        if (keywords.some(k => text.includes(k))) {
                            if (!seenNames.has(text) && !text.includes('transform')) {
                                seenNames.add(text);
                                results.push({name: text, address: ''});
                            }
                        }
                    }
                });

                return results.slice(0, 50);
            }"""

            pois = await page.evaluate(js_code)

            # 去重
            unique = []
            seen = set()
            for p in pois:
                name = p["name"]
                if name not in seen:
                    seen.add(name)
                    unique.append(p)

            return unique

        except Exception as e:
            print(f"  ! 提取异常: {e}")
            return []


async def main():
    scraper = MultiStrategyScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
