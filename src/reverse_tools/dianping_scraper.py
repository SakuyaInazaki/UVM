"""
大众点评/美团售货机数据逆向爬虫

使用Playwright模拟浏览器，可以处理登录和验���码

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page

CONFIG = {
    "keywords": ["自助售货", "友宝", "自动售货机", "无人售货", "泡泡玛特"],
    "output_dir": "data/raw",
    "output_file": "dianping_vending.csv",
    "headless": False,  # 设为False便于处理验证码
}


class DianpingScraper:
    """大众点评爬虫"""

    def __init__(self, config):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "name", "address", "rating", "review_count",
                    "price", "category", "url", "crawl_time"
                ])

    def save_result(self, data):
        """保存结果"""
        key = data.get('name', '')
        if not key or key in self.seen:
            return False
        self.seen.add(key)

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                data.get('name', ''),
                data.get('address', ''),
                data.get('rating', ''),
                data.get('review_count', ''),
                data.get('price', ''),
                data.get('category', ''),
                data.get('url', ''),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        return True

    async def intercept_api(self, page):
        """拦截API请求"""
        captured_data = []

        def handle_response(response):
            try:
                url = response.url
                # 捕获API响应
                if any(x in url for x in ['api', 'search', 'ajax']):
                    if 'json' in response.headers.get('content-type', ''):
                        captured_data.append({
                            'url': url,
                            'status': response.status,
                        })
            except:
                pass

        page.on('response', handle_response)
        return captured_data

    async def search_keyword(self, page, keyword):
        """搜索单个关键词"""
        print(f"\n  搜索: {keyword}")
        count = 0

        try:
            # 构建搜索URL
            url = f"https://www.dianping.com/search/keyword/1/0_{keyword}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 检查是否有验证码
            if "验证" in await page.title() or "安全" in await page.title():
                print(f"    需要验证码，等待30秒手动处理...")
                await asyncio.sleep(30)

            # 尝试多种解析方式
            results = await self.parse_results(page, keyword)
            for r in results:
                if self.save_result(r):
                    count += 1
                    print(f"    ✓ {r.get('name', '')[:40]}")

            # 尝试滚动加载更多
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                results = await self.parse_results(page, keyword)
                for r in results:
                    if self.save_result(r):
                        count += 1

        except Exception as e:
            print(f"    错误: {e}")

        return count

    async def parse_results(self, page, keyword):
        """解析搜索结果"""
        results = []

        # 方法1: 尝试解析HTML结构
        js = """() => {
            const items = [];

            // 大众点评的商家列表结构
            const selectors = [
                '.shop-item', '.list-item', '.tit', 'a[href*="/shop/"]'
            ];

            // 查找所有包含店铺链接的元素
            const links = document.querySelectorAll('a[href*="/shop/"], a[href*="/shop_"]');

            links.forEach(link => {
                try {
                    const name = link.textContent?.trim() || link.title || '';
                    const href = link.href || '';

                    if (name && name.length >= 2 && name.length <= 50) {
                        // 查找父元素获取更多信息
                        let parent = link.closest('.shop-item, .list-item, .content');
                        let address = '';
                        let rating = '';

                        if (parent) {
                            const addrEl = parent.querySelector('.addr, .address, [class*="addr"]');
                            if (addrEl) address = addrEl.textContent?.trim() || '';

                            const ratingEl = parent.querySelector('.star, [class*="rating"], [class*="score"]');
                            if (ratingEl) rating = ratingEl.textContent?.trim() || '';
                        }

                        items.push({
                            name: name,
                            address: address,
                            rating: rating,
                            url: href,
                            category: keyword
                        });
                    }
                } catch(e) {}
            });

            return items.slice(0, 50);
        }"""

        try:
            items = await page.evaluate(js)
            results.extend(items)
        except Exception as e:
            print(f"    解析错误: {e}")

        return results

    async def run(self):
        """运行爬虫"""
        print("=" * 60)
        print("大众点评售货机数据逆向爬虫")
        print("=" * 60)
        print("\n注意：")
        print("1. 首次运行可能需要处理验证码")
        print("2. 如有需要，请在浏览器中手动完成登录")
        print()

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="/tmp/dianping_scraper",
                headless=self.config["headless"],
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                ]
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            total_count = 0
            for keyword in self.config["keywords"]:
                count = await self.search_keyword(page, keyword)
                total_count += count
                await asyncio.sleep(2)

            await browser.close()

        print(f"\n{'=' * 60}")
        print(f"完成! 共获取 {total_count} 条数据")
        print(f"数据保存在: {self.output_path}")
        print(f"{'=' * 60}")


async def main():
    scraper = DianpingScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
