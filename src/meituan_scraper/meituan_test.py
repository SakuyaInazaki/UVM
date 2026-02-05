"""
美团/大众点评售货机数据测试爬虫

注意：
1. 需要登录账号
2. 有反爬机制
3. 建议使用个人账号测试

作者: UVM Research Team
"""

import asyncio
import json
import csv
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

CONFIG = {
    "keywords": ["自助售货机", "友宝", "自动售货", "无人售货"],
    "output_dir": "data/raw",
    "output_file": "meituan_vending.csv",
    "headless": False,  # 美团需要登录，设为False便于手动登录
}


class MeituanScraper:
    """美团爬虫"""

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
                    "price", "category", "source", "crawl_time"
                ])

    def save_result(self, data):
        """保存结果"""
        key = f"{data.get('name', '')}_{data.get('address', '')}"
        if key in self.seen:
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
                '美团',
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        return True

    async def run(self):
        """运行爬虫"""
        print("=" * 60)
        print("美团售货机数据爬虫")
        print("=" * 60)
        print("\n注意：首次运行需要手动登录美团账号")
        print("启动后会自动打开浏览器，请在浏览器中完成登录\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config["headless"],
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            
            page = await context.new_page()

            try:
                # 方案1: 尝试访问大众点评搜索
                print("\n[方案1] 尝试大众点评搜索...")
                await page.goto("https://www.dianping.com/search/keyword/1/0_自助售货机", 
                               timeout=30000)
                await asyncio.sleep(5)
                
                # 检查是否需要验证码
                title = await page.title()
                print(f"  页面标题: {title}")
                
                # 尝试解析结果
                results = await self.parse_dianping(page)
                for r in results:
                    if self.save_result(r):
                        print(f"  ✓ {r.get('name', '')[:40]}")
                
                if not results:
                    print("  ! 未能解析到结果，可能需要手动处理验证码")
                    print("  浏览器将保持打开30秒，请手动操作...")
                    await asyncio.sleep(30)
                    results = await self.parse_dianping(page)
                    for r in results:
                        if self.save_result(r):
                            print(f"  ✓ {r.get('name', '')[:40]}")

            except Exception as e:
                print(f"  错误: {e}")
            
            finally:
                await browser.close()

        print(f"\n共获取 {len(self.seen)} 条数据")
        print(f"数据保存在: {self.output_path}")

    async def parse_dianping(self, page):
        """解析大众点评搜索结果"""
        results = []
        
        try:
            # 大众点评的搜索结果结构
            js = """() => {
                const items = [];
                
                // 查找商户列表项
                const elements = document.querySelectorAll('.shop-item, .list-item, [class*="shop"]');
                
                elements.forEach(el => {
                    try {
                        const nameEl = el.querySelector('.tit, .shop-name, [class*="name"]');
                        const addrEl = el.querySelector('.addr, .shop-address, [class*="address"]');
                        const ratingEl = el.querySelector('.comment-star, [class*="star"], [class*="rating"]');
                        const reviewEl = el.querySelector('.review-count, [class*="comment"]');
                        
                        if (nameEl) {
                            items.push({
                                name: nameEl.textContent?.trim() || '',
                                address: addrEl?.textContent?.trim() || '',
                                rating: ratingEl?.textContent?.trim() || '',
                                review_count: reviewEl?.textContent?.trim() || '',
                            });
                        }
                    } catch(e) {}
                });
                
                return items;
            }"""
            
            items = await page.evaluate(js)
            
            for item in items:
                if item.get('name') and len(item.get('name', '')) > 2:
                    results.append(item)
                    
        except Exception as e:
            print(f"    解析错误: {e}")
        
        return results


async def main():
    scraper = MeituanScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
