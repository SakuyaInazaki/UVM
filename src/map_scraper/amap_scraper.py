"""
高德地图 POI 爬取模块

尝试使用高德地图网页版获取数据

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
    "keywords": [
        "自动售货机", "无人售货", "便利店", "超市",
        "全家", "罗森", "7-11", "物美", "便利蜂",
    ],
    "output_dir": "data/raw",
    "output_file": "amap_pois.csv",
    "headless": False,
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

    def is_valid_name(self, name: str) -> bool:
        invalid = ['class=', 'data-', 'transform', 'none;', '<', '>']
        for p in invalid:
            if p in name:
                return False
        if not re.search(r'[\u4e00-\u9fff]', name):
            return False
        if len(name) < 5 or len(name) > 100:
            return False
        if '地图' in name or '百度' in name:
            return False
        return True

    def save_poi(self, name: str, keyword: str = "") -> bool:
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        if name in self.seen:
            return False
        self.seen.add(name)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "uid": name,
                "name": name,
                "address": "",
                "keyword": keyword,
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  [{keyword}] {name}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


class AMapScraper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.saver = POISaver(config["output_dir"], config["output_file"])

    async def run(self):
        print(f"\n{'='*60}")
        print(f"高德地图 POI 爬虫")
        print(f"{'='*60}\n")

        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/amap_scraper",
                headless=self.config["headless"],
                executable_path=chrome_path,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                await self.search_all(page)
            finally:
                await browser.close()

        print(f"\n共获取 {self.saver.get_count()} 条 POI\n")

    async def search_all(self, page: Page):
        """搜索所有关键词"""
        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")

            # 高德地图搜索 URL
            url = f"https://www.amap.com/search?query={quote(keyword)}"

            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # 提取数据
            pois = await self.extract_pois(page)
            for poi in pois:
                self.saver.save_poi(poi["name"], keyword)

            # 滚动
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                pois = await self.extract_pois(page)
                for poi in pois:
                    self.saver.save_poi(poi["name"], keyword)

    async def extract_pois(self, page: Page) -> List[Dict[str, Any]]:
        """提取POI"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 查找搜索结果
                const selectors = [
                    '[class*="poi-name"]',
                    '[class*="search-item"]',
                    '[class*="place-item"]',
                    'a[href*="detail"]',
                ];

                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        const text = el.textContent ? el.textContent.trim() : '';
                        if (text.length >= 5 && text.length <= 100 && !seen.has(text)) {
                            if (/[\\u4e00-\\u9fff]/.test(text)) {
                                seen.add(text);
                                results.push({name: text});
                            }
                        }
                    });
                });

                // 查找所有链接
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent ? a.textContent.trim() : '';
                    if (text.length >= 5 && text.length <= 100 && !seen.has(text)) {
                        if (/[\\u4e00-\\u9fff]/.test(text)) {
                            seen.add(text);
                            results.push({name: text});
                        }
                    }
                });

                return results.slice(0, 30);
            }"""

            return await page.evaluate(js)
        except Exception as e:
            print(f"  ! 异常: {e}")
            return []


async def main():
    scraper = AMapScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
