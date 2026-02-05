"""
美团商家爬虫

搜索与自动售货机相关的商家和商品

作者: UVM Research Team
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List
from urllib.parse import quote

from playwright.async_api import async_playwright, Page


CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "meituan_pois.csv",
    "headless": False,
    # 搜索关键词 - 涵盖可能的自动售货机商家类型
    "keywords": [
        "自动售货",
        "无人售货",
        "成人用品",
        "情趣用品",
        "自动售卖",
        "24小时售货",
        "自助售货",
    ],
}

CSV_HEADERS = ["uid", "name", "address", "category", "rating", "review_count", "city", "crawl_time"]


class MeituanSaver:
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
        if not name:
            return False
        invalid = ['class=', 'data-', 'transform', 'none;', '<', '>', '备案', '举报', 'ICP', 'cookies']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_poi(self, poi: Dict[str, Any]) -> bool:
        name = poi.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        key = f"{name}_{poi.get('address', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "uid": poi.get("id", name),
                "name": name,
                "address": poi.get("address", ""),
                "category": poi.get("category", ""),
                "rating": poi.get("rating", ""),
                "review_count": poi.get("review_count", ""),
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  [{poi.get('category', 'N/A')}] {name}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


class MeituanScraper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.saver = MeituanSaver(config["output_dir"], config["output_file"])

    async def run(self):
        print(f"\n{'='*60}")
        print(f"美团商家爬虫 - 自动售货相关")
        print(f"{'='*60}\n")

        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/meituan_scraper",
                headless=self.config["headless"],
                executable_path=chrome_path,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                # 方法1: 直接搜索关键词
                await self.keyword_search(page)

                # 方法2: 浏览成人用品分类
                await self.browse_category(page)

            finally:
                await asyncio.sleep(5)
                await browser.close()

        print(f"\n共获取 {self.saver.get_count()} 条 POI\n")

    async def keyword_search(self, page: Page):
        """关键词搜索"""
        print(f"[方法1] 关键词搜索")

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")
            try:
                # 美团搜索URL
                search_url = f"https://www.meituan.com/s/{quote(keyword)}/"

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)

                pois = await self.extract_pois(page)
                for poi in pois:
                    poi["category"] = keyword
                    self.saver.save_poi(poi)

                # 滚动加载更多
                for _ in range(2):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    pois = await self.extract_pois(page)
                    for poi in pois:
                        poi["category"] = keyword
                        self.saver.save_poi(poi)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def browse_category(self, page: Page):
        """浏览相关分类"""
        print(f"\n[方法2] 浏览分类页面")

        # 尝试访问成人用品/情趣用品分类
        category_urls = [
            "https://www.meituan.com/category/1/",  # 美食
            "https://www.meituan.com/category/5/",  # 休闲娱乐
        ]

        for url in category_urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 查找可能相关的链接
                related = await page.evaluate('''() => {
                    const results = [];
                    document.querySelectorAll('a').forEach(a => {
                        const text = a.textContent ? a.textContent.trim() : '';
                        if (text.includes('成人') || text.includes('情趣') ||
                            text.includes('24小时') || text.includes('自助')) {
                            results.push({
                                name: text,
                                href: a.href
                            });
                        }
                    });
                    return results.slice(0, 10);
                }''')

                if related:
                    print(f"    找到 {len(related)} 个相关链接")
                    for r in related:
                        print(f"      - {r['name'][:50]}")

                await asyncio.sleep(2)

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def extract_pois(self, page: Page) -> List[Dict[str, Any]]:
        """提取POI信息"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 查找商家卡片/列表项
                const selectors = [
                    'a[href*="/shop/"]',
                    'a[href*="/store/"]',
                    '.poi-item',
                    '.shop-item',
                    '[data-poibox]',
                    'a[href*="/meishi/"]'
                ];

                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            let text = '';
                            let href = '';

                            if (el.tagName === 'A') {
                                text = el.textContent ? el.textContent.trim() : '';
                                href = el.href;
                            } else {
                                const link = el.querySelector('a');
                                if (link) {
                                    text = link.textContent ? link.textContent.trim() : '';
                                    href = link.href;
                                } else {
                                    text = el.textContent ? el.textContent.trim() : '';
                                }
                            }

                            if (text.length >= 3 && text.length <= 100) {
                                // 过滤无关内容
                                if (!text.includes('百度') && !text.includes('美团') &&
                                    !text.includes('更多') && !text.includes('查看') &&
                                    !text.includes('transform') && !text.includes('data-') &&
                                    !seen.has(text)) {

                                    seen.add(text);

                                    // 提取ID
                                    let id = text;
                                    const match = href.match(/\/(\d+)\//);
                                    if (match) id = match[1];

                                    results.push({
                                        id: id,
                                        name: text,
                                        address: '',
                                        category: '',
                                        rating: '',
                                        review_count: ''
                                    });
                                }
                            }
                        } catch(e) {}
                    });
                });

                return results.slice(0, 50);
            }"""

            return await page.evaluate(js)
        except Exception as e:
            print(f"    提取失败: {e}")
            return []


async def main():
    scraper = MeituanScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
