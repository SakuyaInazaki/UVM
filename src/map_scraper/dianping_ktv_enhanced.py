"""
大众点评KTV数据增强采集器
采集评分、评论数、人均消费、套餐等信息

注意：大众点评有反爬机制，本工具仅供学习研究使用

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional
from urllib.parse import quote, urlencode

import requests
from playwright.async_api import async_playwright


CONFIG = {
    "city": "北京",
    "city_id": "2",  # 大众点评城市ID: 北京=2
    "keywords": ["KTV", "量贩KTV", "唱吧麦颂", "温莎", "魅KTV", "纯K"],
    "output_dir": "data/raw",
    "output_file": "ktv_dianping_with_packages.csv",
    "max_pages": 3,
    "delay": 2,  # 页面延迟(秒)
}


class DianpingKTVEnhanced:
    """大众点评KTV增强采集器"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen: Set[str] = set()
        self.session = requests.Session()
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "shop_id", "name", "address", "district", "lng", "lat",
                    "rating", "review_count", "avg_price", "price_level",
                    "packages", "package_count", "opening_hours", "phone",
                    "tags", "source", "crawl_time"
                ])
            print(f"创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        invalid = ['undefined', 'null', '<', '>', 'function', 'class=',
                   '更多', '加载', '查看', '到底了', '没有', '推广']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_shop(self, shop: Dict) -> bool:
        """保存店铺信息"""
        name = shop.get("name", "").strip()
        if not self.is_valid_name(name):
            return False

        shop_id = shop.get("shop_id", "")
        key = f"{shop_id}_{name}"
        if key in self.seen:
            return False
        self.seen.add(key)

        # 格式化套餐信息
        packages = shop.get("packages", [])
        package_str = json.dumps(packages, ensure_ascii=False) if packages else ""

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                shop_id,
                name,
                shop.get("address", ""),
                shop.get("district", ""),
                shop.get("lng", ""),
                shop.get("lat", ""),
                shop.get("rating", ""),
                shop.get("review_count", ""),
                shop.get("avg_price", ""),
                shop.get("price_level", ""),
                package_str,
                len(packages),
                shop.get("opening_hours", ""),
                shop.get("phone", ""),
                shop.get("tags", ""),
                "大众点评",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    async def fetch_shop_detail(self, page, shop_id: str, shop_name: str) -> Optional[Dict]:
        """获取店铺详情页，包含套餐信息"""
        try:
            detail_url = f"https://www.dianping.com/shop/{shop_id}"

            await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(self.config["delay"])

            # 提取详情页数据
            detail_js = """() => {
                const result = {
                    rating: '',
                    review_count: '',
                    avg_price: '',
                    price_level: '',
                    opening_hours: '',
                    phone: '',
                    tags: '',
                    packages: []
                };

                try {
                    // 评分
                    const ratingEl = document.querySelector('.mid-score, .score, [class*="rating"], [class*="score"]');
                    if (ratingEl) result.rating = ratingEl.textContent?.trim() || '';

                    // 评论数
                    const reviewEl = document.querySelector('[class*="review"], [class*="comment"]');
                    if (reviewEl) {
                        const match = reviewEl.textContent.match(/(\\d+)/);
                        if (match) result.review_count = match[1];
                    }

                    // 人均消费
                    const priceEl = document.querySelector('[class*="price"], .avg-price, .price-num');
                    if (priceEl) {
                        const priceText = priceEl.textContent?.trim() || '';
                        const match = priceText.match(/(\\d+)/);
                        if (match) result.avg_price = match[1];
                    }

                    // 营业时间
                    const hoursEl = document.querySelector('[class*="open"], [class*="hour"], .business-hours');
                    if (hoursEl) result.opening_hours = hoursEl.textContent?.trim() || '';

                    // 电话
                    const phoneEl = document.querySelector('[class*="phone"], [class*="tel"]');
                    if (phoneEl) result.phone = phoneEl.textContent?.trim() || '';

                    // 标签
                    const tagsEls = document.querySelectorAll('[class*="tag"]');
                    result.tags = Array.from(tagsEls).map(el => el.textContent?.trim()).filter(t => t).join(',');

                    // 套餐信息
                    const packageItems = document.querySelectorAll('.deal-item, .package-item, [class*="deal"], [class*="package"]');
                    packageItems.forEach(item => {
                        const title = item.querySelector('[class*="title"], h3, h4');
                        const price = item.querySelector('[class*="price"], .deal-price');
                        const originalPrice = item.querySelector('[class*="original"], .original-price');

                        if (title && price) {
                            result.packages.push({
                                title: title.textContent?.trim() || '',
                                price: price.textContent?.trim() || '',
                                original_price: originalPrice?.textContent?.trim() || ''
                            });
                        }
                    });
                } catch(e) {
                    console.log('Detail extraction error:', e);
                }

                return result;
            }"""

            detail_data = await page.evaluate(detail_js)

            # 限制套餐数量
            if len(detail_data.get("packages", [])) > 10:
                detail_data["packages"] = detail_data["packages"][:10]

            return detail_data

        except Exception as e:
            print(f"    获取详情失败 {shop_name}: {e}")
            return None

    async def scrape(self):
        """执行爬取"""
        print("=" * 70)
        print("大众点评KTV数据增强采集")
        print("=" * 70)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )

            # 设置用户代理
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
            )

            page = await context.new_page()

            # 首先访问大众点评首页，等待用户手动登录
            print("\n" + "=" * 70)
            print("请手动登录大众点评账号")
            print("=" * 70)
            await page.goto("https://www.dianping.com", wait_until="domcontentloaded", timeout=30000)

            # 检查是否需要登录
            await asyncio.sleep(2)
            content = await page.content()
            if "登录" in content:
                print("\n等待登录...")
                print("请在浏览器窗口中完成登录（最多等待180秒）...")
                for i in range(90):
                    await asyncio.sleep(2)
                    content = await page.content()
                    has_login = "登录" in content and "注册" in content
                    if not has_login or "我的" in content or "消息" in content:
                        print("✓ 登录成功！")
                        break
                    if i % 15 == 0:
                        print(f"  等待中... ({i*2}秒)")
                else:
                    print("⚠️ 超时，将继续尝试爬取...")
            else:
                print("✓ 已经登录状态或无需登录")

            total_count = 0
            detail_count = 0

            for keyword in self.config["keywords"]:
                print(f"\n[{keyword}]")

                try:
                    # 大众点评搜索URL
                    search_url = f"https://www.dianping.com/search/keyword/{self.config['city']}/{quote(keyword)}/"

                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(self.config["delay"] + 2)  # 多等2秒

                    # 调试：检查页面内容
                    content = await page.content()
                    print(f"  页面长度: {len(content)} 字符")
                    if len(content) < 10000:
                        print(f"  页面太短，可能被拦截。内容: {content[:800]}")
                    if "验证" in content or "滑块" in content:
                        print(f"  ⚠️ 检测到验证码/滑块，需要手动处理")
                        print(f"  请在浏览器中完成验证，等待30秒...")
                        await asyncio.sleep(30)

                    # 提取搜索结果
                    search_js = """() => {
                        const results = [];
                        const items = document.querySelectorAll('.shop-item, .list-item, [class*="shop-list"] > div, .content-item');

                        items.forEach((item, index) => {
                            try {
                                // 店铺名称
                                const nameEl = item.querySelector('[class*="shopname"], [class*="title"], h4, a[class*="name"]');
                                const name = nameEl?.textContent?.trim() || '';

                                // 链接和ID
                                const linkEl = item.querySelector('a[href*="/shop/"]');
                                const href = linkEl?.href || '';
                                let shopId = '';
                                if (href) {
                                    const match = href.match(/\\/shop\\/(\\d+)/);
                                    if (match) shopId = match[1];
                                }

                                // 地址
                                const addrEl = item.querySelector('[class*="addr"], [class*="address"]');
                                const address = addrEl?.textContent?.trim() || '';

                                // 评分
                                const ratingEl = item.querySelector('[class*="score"], [class*="rating"]');
                                const rating = ratingEl?.textContent?.trim() || '';

                                // 评论数
                                const reviewEl = item.querySelector('[class*="review"], [class*="comment"]');
                                let reviewCount = '';
                                if (reviewEl) {
                                    const match = reviewEl.textContent.match(/(\\d+)/);
                                    if (match) reviewCount = match[1];
                                }

                                // 人均
                                const priceEl = item.querySelector('[class*="price"], .price-num');
                                let avgPrice = '';
                                if (priceEl) {
                                    const match = priceEl.textContent.match(/(\\d+)/);
                                    if (match) avgPrice = match[1];
                                }

                                // 区县
                                const regionEl = item.querySelector('[class*="region"], [class*="area"]');
                                const region = regionEl?.textContent?.trim() || '';

                                if (name && name.length >= 3 && shopId) {
                                    results.push({
                                        shop_id: shopId,
                                        name: name,
                                        address: address,
                                        district: region,
                                        rating: rating,
                                        review_count: reviewCount,
                                        avg_price: avgPrice,
                                        url: href
                                    });
                                }
                            } catch(e) {}
                        });

                        return results.slice(0, 30);
                    }"""

                    shops = await page.evaluate(search_js)

                    if not shops:
                        print(f"  无搜索结果")
                        continue

                    print(f"  搜索到 {len(shops)} 家店铺")

                    # 处理每家店铺
                    for shop in shops:
                        shop_id = shop.get("shop_id", "")
                        shop_name = shop.get("name", "")

                        print(f"  处理: {shop_name}")

                        # 获取详情
                        detail_data = await self.fetch_shop_detail(page, shop_id, shop_name)

                        # 合并数据
                        merged_data = {
                            "shop_id": shop_id,
                            "name": shop_name,
                            "address": shop.get("address", ""),
                            "district": shop.get("district", ""),
                            "lng": "",
                            "lat": "",
                            "rating": detail_data.get("rating") or shop.get("rating", ""),
                            "review_count": detail_data.get("review_count") or shop.get("review_count", ""),
                            "avg_price": detail_data.get("avg_price") or shop.get("avg_price", ""),
                            "price_level": "",
                            "packages": detail_data.get("packages", []),
                            "opening_hours": detail_data.get("opening_hours", ""),
                            "phone": detail_data.get("phone", ""),
                            "tags": detail_data.get("tags", "")
                        }

                        if self.save_shop(merged_data):
                            total_count += 1
                            if detail_data.get("packages"):
                                detail_count += 1
                                print(f"    套餐: {len(detail_data['packages'])}个")

                        # 避免请求过快
                        await asyncio.sleep(1)

                except Exception as e:
                    print(f"  搜索错误: {e}")
                    continue

            await browser.close()

        print(f"\n{'=' * 70}")
        print(f"采集完成！")
        print(f"  总计: {total_count} 家")
        print(f"  有套餐信息: {detail_count} 家")
        print(f"数据保存在: {self.output_path}")


async def main():
    scraper = DianpingKTVEnhanced(CONFIG)
    await scraper.scrape()


if __name__ == "__main__":
    asyncio.run(main())
