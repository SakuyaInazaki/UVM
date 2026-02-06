"""
美团KTV数据采集器 - Playwright方案

使用Playwright模拟真实浏览器行为，尝试采集美团KTV数据

注意：美团反爬极强，此方案仅供参考学习

作者: UVM Research Team
"""

import asyncio
import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from playwright.async_api import async_playwright, Page, Browser


CONFIG = {
    # 美团不同的URL模式（逐一尝试）
    "base_urls": [
        "https://i.meituan.com",  # 移动版
        "https://bj.meituan.com",  # 北京站
    ],
    "city": "北京",
    "city_pinyin": "beijing",
    "keywords": ["KTV"],
    "output_dir": "data/raw",
    "output_file": "ktv_meituan.csv",
    "headless": False,  # 设为False更容易通过检测
    "delay_range": (2, 5),  # 随机延迟范围(秒)
}


class MeituanKTVScraper:
    """美团KTV爬虫 - Playwright实现"""

    def __init__(self, config: Dict):
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
                    "shop_id", "name", "address", "district", "rating",
                    "review_count", "avg_price", "score", "source", "crawl_time"
                ])
            print(f"创建文件: {self.output_path}")

    def random_delay(self):
        """随机延迟"""
        delay = random.uniform(*self.config["delay_range"])
        time.sleep(delay)

    async def simulate_human_behavior(self, page: Page):
        """模拟人类行为"""
        # 随机滚动
        await page.evaluate(f"window.scrollTo(0, {random.randint(100, 500)})")
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # 模拟鼠标移动
        await page.mouse.move(
            random.randint(100, 800),
            random.randint(100, 600)
        )

    async def extract_shop_list(self, page: Page) -> List[Dict]:
        """提取店铺列表"""
        # 尝试多种选择器
        selectors = [
            '.poi-item',
            '[class*="poi"]',
            '[class*="shop"]',
            '[class*="business"]',
            '.item',
        ]

        shops = []

        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    print(f"  找到 {len(elements)} 个元素 (选择器: {selector})")

                    for el in elements[:20]:  # 限制数量
                        try:
                            text = await el.inner_text()
                            if text and len(text) > 5:
                                shops.append({"raw_text": text, "element": el})
                        except:
                            continue
                    break
            except:
                continue

        return shops

    async def parse_shop_info(self, shop_data: Dict) -> Dict:
        """解析店铺信息"""
        text = shop_data.get("raw_text", "")

        # 简单的正则解析
        import re

        # 尝试提取名称
        name_match = re.search(r'^(.{2,20}?)(?=地址|$)', text)
        name = name_match.group(1) if name_match else ""

        # 尝试提取评分
        rating_match = re.search(r'(\d+\.?\d*)分?', text)
        rating = rating_match.group(1) if rating_match else ""

        # 尝试提取价格
        price_match = re.search(r'¥?(\d+)元?', text)
        price = price_match.group(1) if price_match else ""

        return {
            "shop_id": "",
            "name": name.strip(),
            "address": "",
            "district": "",
            "rating": rating,
            "review_count": "",
            "avg_price": price,
            "score": "",
            "source": "美团",
            "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def save_shop(self, shop: Dict) -> bool:
        """保存店铺信息"""
        name = shop.get("name", "")
        if not name or len(name) < 3:
            return False

        key = f"{shop['shop_id']}_{name}"
        if key in self.seen:
            return False

        self.seen.add(key)

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                shop.get("shop_id", ""),
                shop.get("name", ""),
                shop.get("address", ""),
                shop.get("district", ""),
                shop.get("rating", ""),
                shop.get("review_count", ""),
                shop.get("avg_price", ""),
                shop.get("score", ""),
                shop.get("source", ""),
                shop.get("crawl_time", "")
            ])

        return True

    async def scrape(self):
        """执行爬取"""
        print("=" * 70)
        print("美团KTV数据采集 - Playwright方案")
        print("=" * 70)

        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(
                headless=self.config["headless"],
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )

            # 创建上下文
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )

            # 注入反检测脚本
            await context.add_init_script("""
                // 覆盖navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });

                // 覆盖chrome对象
                window.chrome = {
                    runtime: {}
                };

                // 覆盖permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            # 设置响应拦截来捕获API调用
            api_data = []

            def log_response(response):
                """捕获API响应"""
                url = response.url
                if 'api' in url or 'search' in url or 'poi' in url.lower():
                    print(f"  API响应: {url[:80]}")

            page = await context.new_page()

            # 注册响应处理
            page.on('response', log_response)
            print("\n" + "=" * 70)
            print("请手动登录美团账号")
            print("=" * 70)
            await page.goto(self.config["base_urls"][0], wait_until="domcontentloaded", timeout=30000)

            # 检查是否已登录
            await asyncio.sleep(2)
            content = await page.content()
            if "登录" in content or "login" in content.lower():
                print("\n等待登录...")
                print("请在浏览器窗口中完成登录（最多等待120秒）...")
                # 等待最多120秒，每2秒检查一次是否登录成功
                for i in range(60):
                    await asyncio.sleep(2)
                    content = await page.content()
                    # 检查是否还有登录按钮或登录相关内容
                    has_login = "登录" in content and "注册" in content
                    if not has_login or "我的" in content or "消息" in content:
                        print("✓ 登录成功！")
                        break
                    if i % 10 == 0:  # 每20秒提示一次
                        print(f"  等待中... ({i*2}秒)")
                else:
                    print("⚠️ 超时，将继续尝试爬取...")
            else:
                print("✓ 已经登录状态")

            total_count = 0

            # 先尝试找到可用的URL模式
            working_url = None
            for base_url in self.config["base_urls"]:
                print(f"\n尝试URL: {base_url}")
                try:
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
                    content = await page.content()
                    if "验证" in content:
                        print(f"  ⚠️ 显示验证中心，需要人工处理")
                    elif len(content) > 10000:
                        print(f"  ✓ 页面加载成功 ({len(content)} 字符)")
                        working_url = base_url
                        break
                    else:
                        print(f"  页面太小: {len(content)} 字符")
                except Exception as e:
                    print(f"  错误: {e}")

            if not working_url:
                print("\n⚠️ 所有URL都无法访问，尝试使用默认URL")
                working_url = "https://i.meituan.com"

            print(f"\n使用URL: {working_url}")

            for keyword in self.config["keywords"]:
                print(f"\n[搜索关键词: {keyword}]")

                try:
                    # 方式1: 在首页搜索框输入
                    print(f"  尝试在首页搜索...")
                    await page.goto(working_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(2)

                    # 尝试找到搜索框并输入
                    search_selectors = [
                        'input[placeholder*="搜索"]',
                        'input[type="search"]',
                        '.search-input',
                        '#search-input',
                        'input[name="keyword"]',
                    ]

                    search_found = False
                    for selector in search_selectors:
                        try:
                            search_box = await page.query_selector(selector)
                            if search_box:
                                await search_box.fill(keyword)
                                await asyncio.sleep(1)
                                # 按回车或点击搜索按钮
                                await page.press(selector, 'Enter')
                                await asyncio.sleep(3)
                                search_found = True
                                print(f"    ✓ 搜索框操作成功")
                                break
                        except:
                            continue

                    if not search_found:
                        print(f"    未找到搜索框，尝试直接URL...")

                    # 检查结果页
                    content = await page.content()
                    print(f"    当前页面: {page.url}")
                    print(f"    页面长度: {len(content)} 字符")

                    # 查找所有可能相关的链接
                    links_js = """() => {
                        const links = Array.from(document.querySelectorAll('a'));
                        return links
                            .filter(a => a.href && (
                                a.textContent.includes('KTV') ||
                                a.textContent.includes('娱乐') ||
                                a.textContent.includes('休闲') ||
                                a.href.includes('ktv') ||
                                a.href.includes('entertainment') ||
                                a.href.includes('i.meituan.com')
                            ))
                            .map(a => ({
                                text: a.textContent.trim().substring(0, 50),
                                href: a.href
                            }))
                            .slice(0, 20);
                    }"""
                    links = await page.evaluate(links_js)
                    print(f"    找到相关链接: {len(links)}个")
                    for link in links[:5]:
                        print(f"      - {link['text']}: {link['href'][:80]}")

                    # 尝试访问找到的分类链接
                    if links:
                        for link in links:
                            href = link.get('href', '')
                            if 'i.meituan.com/c/' in href:
                                print(f"    尝试分类链接: {href}")
                                await page.goto(href, wait_until="networkidle", timeout=30000)
                                await asyncio.sleep(3)
                                content = await page.content()
                                print(f"      页面长度: {len(content)} 字符")
                                if len(content) > 50000:
                                    print(f"      ✓ 找到数据页面！")
                                    working_url = page.url
                                    break

                    # 尝试访问i.meituan.com的KTV页面
                    test_urls = [
                        "https://i.meituan.com/beijing/ktv",
                        "https://i.meituan.com/beijing/category/ktv",
                        "https://i.meituan.com/category/ktv",
                        "https://www.meituan.com/beijing/ktv/",
                    ]

                    for test_url in test_urls:
                        print(f"    尝试: {test_url}")
                        try:
                            await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(2)
                            content = await page.content()
                            print(f"      页面���度: {len(content)} 字符")
                            if len(content) > 30000 and "KTV" in content:
                                print(f"      ✓ 找到KTV页面！")
                                break
                        except Exception as e:
                            print(f"      错误: {e}")

                    # 最终检查当前页面
                    content = await page.content()
                    print(f"    最终页面: {page.url}")
                    print(f"    页面长度: {len(content)} 字符")

                    # 尝试更多选择器提取数据
                    print(f"    尝试提取店铺数据...")

                    # 尝试多种选择器
                    selectors_to_try = [
                        '.poi-item', '.shop-item', '.deal-item', '.list-item',
                        '[class*="shop"]', '[class*="poi"]', '[class*="item"]',
                        'article', '.card', '.item-content',
                    ]

                    for selector in selectors_to_try:
                        try:
                            count = await page.locator(selector).count()
                            if count > 0:
                                print(f"      {selector}: {count}个")
                        except:
                            pass

                    # 打印页面结构示例
                    structure_js = """() => {
                        const main = document.querySelector('main') || document.body;
                        const children = Array.from(main.children).slice(0, 10);
                        return children.map(el => ({
                            tag: el.tagName,
                            class: el.className,
                            id: el.id,
                            textContent: el.textContent?.substring(0, 50)
                        }));
                    }"""
                    structure = await page.evaluate(structure_js)
                    print(f"    页面结构: {structure[:3]}")

                    # 提取Next.js数据
                    next_data_js = """() => {
                        const script = document.getElementById('__NEXT_DATA__');
                        if (script) {
                            try {
                                return JSON.parse(script.textContent);
                            } catch(e) {
                                return {error: e.message};
                            }
                        }
                        return null;
                    }"""
                    next_data = await page.evaluate(next_data_js)

                    if next_data:
                        import json
                        # 保存原始数据用于分析
                        with open('/tmp/next_data.json', 'w', encoding='utf-8') as f:
                            json.dump(next_data, f, ensure_ascii=False, indent=2)
                        print(f"    ✓ 找到__NEXT_DATA__! 已保存到 /tmp/next_data.json")

                        # 尝试解析KTV数据
                        try:
                            props = next_data.get('props', {})
                            page_props = props.get('pageProps', {})
                            print(f"    pageProps keys: {list(page_props.keys())[:10]}")

                            # 查找可能的POI数据
                            for key, value in page_props.items():
                                if isinstance(value, list) and len(value) > 0:
                                    print(f"      {key}: list with {len(value)} items")
                                elif isinstance(value, dict):
                                    print(f"      {key}: dict with keys {list(value.keys())[:5]}")
                        except Exception as e:
                            print(f"    解析错误: {e}")

                    # 等待API调用完成
                    print(f"    等待API数据...")
                    await asyncio.sleep(5)

                    # 检查捕获的API数据
                    if api_data:
                        print(f"    ✓ 捕获到{len(api_data)}个API响应")
                        with open('/tmp/api_data.json', 'w', encoding='utf-8') as f:
                            json.dump(api_data, f, ensure_ascii=False, indent=2)
                        print(f"    已保存到 /tmp/api_data.json")

                        # 尝试从API数据中提取KTV信息
                        for item in api_data:
                            data = item.get('data', {})
                            if isinstance(data, dict):
                                if 'data' in data:
                                    inner = data['data']
                                    if isinstance(inner, list) and len(inner) > 0:
                                        print(f"      找到数据列表: {len(inner)}项")
                                        # 检查是否是POI数据
                                        if isinstance(inner[0], dict):
                                            keys = list(inner[0].keys())
                                            print(f"      字段: {keys[:10]}")

                    # 尝试提取数据
                    shops = await self.extract_shop_list(page)

                    if not shops:
                        print(f"  未找到数据，可能被拦截或需要登录")
                        # 尝试获取页面内容用于调试
                        content = await page.content()
                        if "登录" in content or "login" in content.lower():
                            print(f"  检测到登录页面")
                        if "验证" in content or "verify" in content.lower():
                            print(f"  检测到验证码页面")
                        continue

                    # 解析并保存数据
                    keyword_count = 0
                    for shop_data in shops:
                        shop = await self.parse_shop_info(shop_data)
                        if self.save_shop(shop):
                            keyword_count += 1
                            total_count += 1
                            print(f"    采集: {shop['name']}")

                    print(f"  本关键词采集: {keyword_count}条")

                    self.random_delay()

                except Exception as e:
                    print(f"  错误: {e}")
                    continue

            await browser.close()

        print(f"\n{'=' * 70}")
        print(f"采集完成！")
        print(f"  总计: {total_count} 条")
        print(f"  数据保存在: {self.output_path}")
        print(f"\n提示: 如果数据量为0，可能需要:")
        print(f"  1. 登录美团账号")
        print(f"  2. 使用住宅代理IP")
        print(f"  3. 手动处理验证码")
        print(f"  4. 降低请求频率")


async def main():
    scraper = MeituanKTVScraper(CONFIG)
    await scraper.scrape()


if __name__ == "__main__":
    asyncio.run(main())
