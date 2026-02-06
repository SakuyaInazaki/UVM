"""
大众点评KTV数据采集

使用Playwright采集大众点评KTV数据

作者: UVM Research Team
"""

import asyncio
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from urllib.parse import quote

from playwright.async_api import async_playwright


CONFIG = {
    "city": "北京",
    "keywords": ["KTV", "量贩式KTV", "量贩KTV", "卡拉OK"],
    "output_dir": "data/raw",
    "output_file": "ktv_pois_dianping.csv",
    "headless": True,
    "max_pages": 5,
}


class DianpingKTVScraper:
    """大众点评KTV爬虫"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen: Set[str] = set()
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "rating", "review_count", "price", "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        invalid = ['undefined', 'null', '<', '>', 'function', 'class=',
                   '更多', '加载', '查看', '到底了', '没有']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_poi(self, poi: Dict) -> bool:
        name = poi.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        key = f"{name}_{poi.get('lng', '')}_{poi.get('lat', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                poi.get("id", ""),
                name,
                poi.get("address", ""),
                poi.get("district", ""),
                poi.get("lng", ""),
                poi.get("lat", ""),
                poi.get("rating", ""),
                poi.get("review_count", ""),
                poi.get("price", ""),
                "大众点评",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    async def scrape(self):
        """执行爬取"""
        print("=" * 70)
        print("大众点评KTV数据采集")
        print("=" * 70)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config["headless"],
                args=['--disable-blink-features=AutomationControlled']
            )

            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 900})

            total_count = 0

            for keyword in self.config["keywords"]:
                print(f"\n[{keyword}]")

                for page_num in range(1, self.config["max_pages"] + 1):
                    try:
                        # 大众点评搜索URL
                        url = f"https://www.dianping.com/search/keyword/{self.config['city']}/{quote(keyword)}/"

                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(2)

                        # 提取POI数据
                        js = """() => {
                            const results = [];
                            const seen = new Set();

                            // 查找商户列表项
                            const items = document.querySelectorAll('.list-item, .shop-item, [class*="poi"], [class*="shop"]');

                            items.forEach(item => {
                                try {
                                    const nameEl = item.querySelector('[class*="name"], [class*="title"], h1, h2, h3, h4, .tit');
                                    const addrEl = item.querySelector('[class*="addr"], [class*="address"]');
                                    const linkEl = item.querySelector('a[href*="/shop/"]');

                                    if (nameEl) {
                                        const name = nameEl.textContent?.trim() || '';
                                        const address = addrEl?.textContent?.trim() || '';
                                        const href = linkEl?.href || '';

                                        if (name && name.length >= 3 && name.length < 100) {
                                            if (!seen.has(name)) {
                                                seen.add(name);

                                                // 提取ID
                                                let id = name;
                                                if (href) {
                                                    const match = href.match(/\\/shop\\/(\\d+)/);
                                                    if (match) id = match[1];
                                                }

                                                results.push({
                                                    id: id,
                                                    name: name,
                                                    address: address,
                                                    url: href
                                                });
                                            }
                                        }
                                    }
                                } catch(e) {}
                            });

                            return results.slice(0, 50);
                        }"""

                        pois = await page.evaluate(js)

                        if not pois:
                            print(f"  第{page_num}页: 无数据")
                            break

                        page_count = 0
                        for poi in pois:
                            if self.save_poi(poi):
                                page_count += 1
                                total_count += 1

                        print(f"  第{page_num}页: {page_count}条")

                        # 检查是否还有更多
                        has_more = await page.evaluate("""() => {
                            const nextBtn = document.querySelector('.next-page, .next, [class*="next"]');
                            if (nextBtn && !nextBtn.classList.contains('disabled')) {
                                return true;
                            }
                            return false;
                        }""")

                        if not has_more:
                            break

                        # 点击下一页
                        try:
                            await page.click('.next-page, .next, [class*="next"]')
                            await asyncio.sleep(2)
                        except:
                            break

                    except Exception as e:
                        print(f"  第{page_num}页错误: {e}")
                        break

            await browser.close()

        print(f"\n{'=' * 70}")
        print(f"采集完成！共获取 {total_count} 条数据")
        print(f"数据保存在: {self.output_path}")


async def main():
    scraper = DianpingKTVScraper(CONFIG)
    await scraper.scrape()


if __name__ == "__main__":
    asyncio.run(main())
