"""
基于Playwright的地图POI爬虫

直接通过浏览器访问地图网站，模拟真实用户行为获取POI数据
无需API Key，通过网页抓取实现

支持平台:
- 高德地图 (PC/移动版)
- 百度地图 (PC/移动版)
- 腾讯地图 (PC/移动版)

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List
from urllib.parse import quote, urlencode

from playwright.async_api import async_playwright, Page, Browser


# ==================== 配置 ====================
CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "playwright_pois.csv",

    # 自动售货机关键词
    "keywords": [
        "友宝",
        "自动售货机",
        "无人售货",
        "自动贩卖机",
        "饮料自动售货",
        "成人用品售货",
    ],

    # 过滤词
    "filter_keywords": [
        "便利店", "7-11", "711", "全家", "罗森", "物美", "便利蜂",
        "超市", "卖场", "购物中心"
    ],

    # 浏览器配置
    "headless": False,  # 设为True可无头运行
    "slow_mo": 500,     # 操作延迟，避免被检测
}

CSV_HEADERS = [
    "id", "name", "address", "category", "lat", "lng",
    "source", "keyword", "city", "crawl_time"
]


# ==================== 数据保存类 ====================
class POISaver:
    """POI数据保存器"""

    CONVENIENCE_STORES = {
        "便利店", "7-11", "711", "全家", "familymart", "罗森", "lawson",
        "物美", "便利蜂", "喜士多", "ok便利店", "快客", "十足", "京客隆",
        "超市发", "好邻居", "顺天府", "超市", "卖场", "购物中心", "百货"
    }

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
            print(f"✓ 创建文件: {self.file_path}")

    def is_valid_poi(self, name: str) -> bool:
        """验证是否为有效POI"""
        if not name or len(name) < 3 or len(name) > 100:
            return False

        name_lower = name.lower()

        # 过滤无效数据
        invalid_patterns = [
            'class=', 'data-', 'transform', 'none;', '<', '>',
            '备案', '举报', 'icp', 'cookies', 'http', 'www', '://',
            '京东', '淘宝', '美团', '饿了么'
        ]
        for pattern in invalid_patterns:
            if pattern in name_lower:
                return False

        # 过滤便利店
        for store in self.CONVENIENCE_STORES:
            if store in name_lower:
                return False

        # 必须包含售货机相关词
        vending_keywords = [
            '售货机', '贩卖机', '无人售货', '友宝', 'ubox',
            '丰e', '成人用品', '情趣'
        ]
        has_vending = any(kw in name or kw in name_lower for kw in vending_keywords)

        return has_vending

    def save_poi(self, poi: Dict[str, Any], source: str = "", keyword: str = "") -> bool:
        """保存POI数据"""
        name = poi.get("name", "")
        if not self.is_valid_poi(name):
            return False

        key = f"{source}_{poi.get('id', '')}_{name}_{poi.get('address', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "id": poi.get("id", ""),
                "name": name,
                "address": poi.get("address", ""),
                "category": poi.get("category", ""),
                "lat": poi.get("lat", ""),
                "lng": poi.get("lng", ""),
                "source": source,
                "keyword": keyword,
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  ✓ {name[:40]}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


# ==================== 高德地图爬虫 ====================
class AmapScraper:
    """高德地图爬虫 - 使用移动端页面"""

    def __init__(self, saver: POISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config
        self.base_url = "https://m.amap.com"

    async def run(self, page: Page):
        """执行爬取"""
        print("\n[高德地图] 开始爬取...")

        city = self.config["city"]

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")

            try:
                # 构建搜索URL
                search_url = f"{self.base_url}/search?query={quote(keyword)}&city={quote(city)}"
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 等待搜索结果加载
                await page.wait_for_selector('.poi-item, .search-item, [class*="poi"]', timeout=10000)

                # 提取第一页结果
                pois = await self.extract_pois(page)
                for poi in pois:
                    self.saver.save_poi(poi, "高德地图", keyword)

                # 尝试滚动加载更多
                for i in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    pois = await self.extract_pois(page)
                    for poi in pois:
                        self.saver.save_poi(poi, "高德地图", keyword)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def extract_pois(self, page: Page) -> List[Dict[str, Any]]:
        """提取POI数据"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 多种选择器
                const selectors = [
                    '.poi-item',
                    '.search-item',
                    '[class*="poi"]',
                    '[class*="item"]',
                    'a[href*="detail"]'
                ];

                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        try {
                            const link = el.tagName === 'A' ? el : el.querySelector('a');
                            const name = el.textContent?.trim() || link?.textContent?.trim() || '';

                            if (name && name.length >= 3 && name.length <= 100 && !seen.has(name)) {
                                seen.add(name);

                                const href = link?.href || el.href || '';
                                const match = href.match(/id=([A-Z0-9]+)/i);

                                results.push({
                                    id: match ? match[1] : name,
                                    name: name,
                                    address: '',
                                    category: '',
                                    lat: '',
                                    lng: ''
                                });
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


# ==================== 百度地图爬虫 ====================
class BaiduMapScraper:
    """百度地图爬虫 - 使用移动端页面"""

    def __init__(self, saver: POISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config
        self.base_url = "https://map.baidu.com"

    async def run(self, page: Page):
        """执行爬取"""
        print("\n[百度地图] 开始爬取...")

        city = self.config["city"]

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")

            try:
                # 构建搜索URL - 使用移动端
                search_url = f"{self.base_url}/mobile/webapp/search/search?s=con&wd={quote(keyword)}&c={quote(city)}"

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)

                # 提取结果
                pois = await self.extract_pois(page)
                for poi in pois:
                    self.saver.save_poi(poi, "百度地图", keyword)

                # 滚动加载更多
                for i in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    pois = await self.extract_pois(page)
                    for poi in pois:
                        self.saver.save_poi(poi, "百度地图", keyword)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def extract_pois(self, page: Page) -> List[Dict[str, Any]]:
        """提取POI数据"""
        try:
            js = """() => {
                const results = [];
                const seen = new Set();

                // 查找POI元素
                const elements = document.querySelectorAll('[class*="poi"], [class*="item"], [class*="name"], a');

                elements.forEach(el => {
                    try {
                        const text = el.textContent?.trim() || '';

                        if (text && text.length >= 3 && text.length <= 100) {
                            // 过滤无关内容
                            if (!text.includes('更多') && !text.includes('查看') &&
                                !text.includes('百度') && !text.includes('地图') &&
                                !seen.has(text)) {

                                seen.add(text);

                                results.push({
                                    id: text,
                                    name: text,
                                    address: '',
                                    category: '',
                                    lat: '',
                                    lng: ''
                                });
                            }
                        }
                    } catch(e) {}
                });

                return results.slice(0, 30);
            }"""

            return await page.evaluate(js)
        except Exception as e:
            print(f"    提取失败: {e}")
            return []


# ==================== 腾讯地图爬虫 ====================
class TencentMapScraper:
    """腾讯地图爬虫 - 使用移动端页面"""

    def __init__(self, saver: POISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config
        self.base_url = "https://apis.map.qq.com"

    async def run(self, page: Page):
        """执行爬取"""
        print("\n[腾讯地图] 开始爬取...")

        city = self.config["city"]

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")

            try:
                # 使用腾讯地图移动端网页版
                search_url = f"https://apis.map.qq.com/uri/v1/marker?marker=coord:0,0;title:{quote(keyword)}&referer=myapp"

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 腾讯可能会跳转，提取当前页面内容
                pois = await self.extract_pois(page)
                for poi in pois:
                    self.saver.save_poi(poi, "腾讯地图", keyword)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def extract_pois(self, page: Page) -> List[Dict[str, Any]]:
        """提取POI数据"""
        try:
            js = """() => {
                const results = [];

                // 查找所有文本内容
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null
                );

                let node;
                const seen = new Set();

                while (node = walker.nextNode()) {
                    const text = node.textContent?.trim();

                    if (text && text.length >= 3 && text.length <= 100 &&
                        !text.includes('腾讯') && !text.includes('地图') &&
                        !seen.has(text)) {

                        // 检查是否包含售货机关键词
                        if (text.includes('售货') || text.includes('友宝') ||
                            text.includes('无人') || text.includes('自动')) {

                            seen.add(text);
                            results.push({
                                id: text,
                                name: text,
                                address: '',
                                category: '',
                                lat: '',
                                lng: ''
                            });
                        }
                    }
                }

                return results.slice(0, 20);
            }"""

            return await page.evaluate(js)
        except Exception as e:
            print(f"    提取失败: {e}")
            return []


# ==================== 主程序 ====================
async def main():
    print("=" * 60)
    print("基于Playwright的地图POI爬虫")
    print("=" * 60)

    saver = POISaver(CONFIG["output_dir"], CONFIG["output_file"])

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/map_scraper_v2",
            headless=CONFIG["headless"],
            executable_path=chrome_path if Path(chrome_path).exists() else None,
            user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 375, "height": 812},
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            # 高德地图
            amap = AmapScraper(saver, CONFIG)
            await amap.run(page)

            # 百度地图
            baidu = BaiduMapScraper(saver, CONFIG)
            await baidu.run(page)

            # 腾讯地图
            tencent = TencentMapScraper(saver, CONFIG)
            await tencent.run(page)

        finally:
            await asyncio.sleep(5)
            await browser.close()

    print(f"\n{'=' * 60}")
    print(f"✓ 完成! 共获取 {saver.get_count()} 条POI数据")
    print(f"✓ 数据保存在: {saver.file_path}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
