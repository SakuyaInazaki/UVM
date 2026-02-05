"""
高级地图POI爬虫 - 网络请求拦截版

通过Playwright拦截浏览器网络请求，直接获取地图API返回的JSON数据
无需解析DOM，数据更准确

作者: UVM Research Team
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List
from urllib.parse import quote

from playwright.async_api import async_playwright, Page, Request, Response


# ==================== 配置 ====================
CONFIG = {
    "city": "北京",
    "city_code": "131",  # 高德城市代码
    "output_dir": "data/raw",
    "output_file": "advanced_pois.csv",

    # 自动售货机关键词
    "keywords": [
        "友宝",
        "自动售货机",
        "无人售货",
        "自动贩卖机",
        "饮料售货",
        "成人用品售货",
        "ubox",
    ],

    # 过滤词
    "filter_keywords": [
        "便利店", "7-11", "711", "全家", "罗森", "物美", "便利蜂",
        "超市", "卖场", "购物中心"
    ],

    # 浏览器配置
    "headless": False,
}

CSV_HEADERS = [
    "id", "name", "address", "category", "lat", "lng",
    "tel", "district", "source", "keyword", "city", "crawl_time"
]


# ==================== 数据保存类 ====================
class AdvancedPOISaver:
    """高级POI数据保存器"""

    CONVENIENCE_STORES = {
        "便利店", "7-11", "711", "全家", "familymart", "罗森", "lawson",
        "物美", "便利蜂", "喜士多", "ok便利店", "快客", "十足", "京客隆",
        "超市发", "好邻居", "顺天府", "超市", "卖场", "购物中心", "百货",
        "永辉", "华润", "家乐福", "沃尔玛", "盒马", "山姆", "大悦城"
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

    def is_vending_machine(self, name: str) -> bool:
        """判断是否为自动售货机"""
        if not name or len(name) < 3 or len(name) > 100:
            return False

        name_lower = name.lower()

        # 过滤无效数据
        invalid_patterns = [
            'class=', 'data-', 'transform', 'none;', '<', '>',
            '备案', '举报', 'icp', 'cookies', 'http://', 'https://',
            'www.', '.cn', '.com'
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
            '售货机', '贩卖机', '无人售货', '友宝', 'ubox', 'u-box',
            '丰e', '成人用品', '情趣', '饮料机', '咖啡机'
        ]
        has_vending = any(kw in name or kw in name_lower for kw in vending_keywords)

        return has_vending

    def save_poi(self, poi: Dict[str, Any], source: str = "", keyword: str = "") -> bool:
        """保存POI数据"""
        name = poi.get("name", "")
        if not self.is_vending_machine(name):
            return False

        key = f"{source}_{poi.get('id', '')}_{name}"
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
                "tel": poi.get("tel", ""),
                "district": poi.get("district", ""),
                "source": source,
                "keyword": keyword,
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  ✓ [{poi.get('district', '')}] {name[:35]}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


# ==================== 高德地图爬虫（拦截API） ====================
class AmapAPIInterceptor:
    """高德地图API拦截器"""

    API_URLS = [
        "lbs.amap.com",
        "restapi.amap.com",
        "amap.com"
    ]

    def __init__(self, saver: AdvancedPOISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config
        self.captured_data: List[Dict] = []
        self.current_keyword = ""

    async def setup_interception(self, page: Page):
        """设置请求拦截"""

        async def handle_response(response: Response):
            """处理响应"""
            url = response.url
            try:
                # 只处理API响应
                if any(api in url for api in self.API_URLS):
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type or "json" in url:
                        try:
                            data = await response.json()
                            await self.process_api_data(data, url)
                        except:
                            pass
            except:
                pass

        page.on("response", handle_response)

    async def process_api_data(self, data: Any, url: str):
        """处理API数据"""
        if not isinstance(data, dict):
            return

        # 处理高德POI搜索响应
        if "pois" in data:
            pois = data["pois"]
            for poi in pois:
                # 解析高德POI格式
                name = poi.get("name", "")
                if not self.saver.is_vending_machine(name):
                    continue

                location = poi.get("location", "")
                if "," in location:
                    lng, lat = location.split(",")
                else:
                    lng, lat = "", ""

                formatted_poi = {
                    "id": poi.get("id", ""),
                    "name": name,
                    "address": poi.get("address", ""),
                    "category": poi.get("type", ""),
                    "lat": lat,
                    "lng": lng,
                    "tel": poi.get("tel", ""),
                    "district": poi.get("adname", "")
                }

                self.saver.save_poi(formatted_poi, "高德API", self.current_keyword)

    async def search(self, page: Page, keyword: str):
        """执行搜索"""
        self.current_keyword = keyword
        print(f"\n  [高德API] 搜索: {keyword}")

        # 使用高德地图Web版
        search_url = f"https://ditu.amap.com/search?query={quote(keyword)}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)  # 等待API调用

            # 尝试滚动触发更多数据加载
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

        except Exception as e:
            print(f"    ! 失败: {e}")


# ==================== 百度地图爬虫（拦截API） ====================
class BaiduAPIInterceptor:
    """百度地图API拦截器"""

    API_URLS = [
        "map.baidu.com",
        "api.map.baidu.com"
    ]

    def __init__(self, saver: AdvancedPOISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config
        self.current_keyword = ""

    async def setup_interception(self, page: Page):
        """设置请求拦截"""

        async def handle_response(response: Response):
            """处理响应"""
            url = response.url
            try:
                if any(api in url for api in self.API_URLS):
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            data = await response.json()
                            await self.process_api_data(data, url)
                        except:
                            pass
            except:
                pass

        page.on("response", handle_response)

    async def process_api_data(self, data: Any, url: str):
        """处理API数据"""
        if not isinstance(data, dict):
            return

        # 处理百度POI响应
        if "results" in data or "data" in data:
            results = data.get("results", data.get("data", []))

            for poi in results:
                if isinstance(poi, dict):
                    name = poi.get("name", "")
                    if not self.saver.is_vending_machine(name):
                        continue

                    location = poi.get("location", {}) or poi.get("latlng", {})
                    if isinstance(location, dict):
                        lat = location.get("lat", "")
                        lng = location.get("lng", "")
                    else:
                        lat, lng = "", ""

                    formatted_poi = {
                        "id": poi.get("id", poi.get("uid", "")),
                        "name": name,
                        "address": poi.get("address", ""),
                        "category": poi.get("detail_info", {}).get("tag", ""),
                        "lat": str(lat) if lat else "",
                        "lng": str(lng) if lng else "",
                        "tel": poi.get("telephone", ""),
                        "district": ""
                    }

                    self.saver.save_poi(formatted_poi, "百度API", self.current_keyword)

    async def search(self, page: Page, keyword: str):
        """执行搜索"""
        self.current_keyword = keyword
        print(f"\n  [百度API] 搜索: {keyword}")

        search_url = f"https://map.baidu.com/search/{quote(keyword)}/@11584496,3585536,13z"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            # 尝试滚动触发更多数据加载
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

        except Exception as e:
            print(f"    ! 失败: {e}")


# ==================== DOM解析爬虫（备用方案） ====================
class DOMParser:
    """DOM解析爬虫 - 当API拦截失败时使用"""

    def __init__(self, saver: AdvancedPOISaver, config: Dict[str, Any]):
        self.saver = saver
        self.config = config

    async def parse_page(self, page: Page, source: str):
        """解析页面DOM"""
        try:
            js = """() => {
                const results = [];

                // 查找所有可能包含POI信息的元素
                const elements = document.querySelectorAll('[class*="poi"], [class*="item"], [class*="name"], [data-poi]');

                elements.forEach(el => {
                    const name = el.textContent?.trim();
                    if (name && name.length >= 3 && name.length <= 100) {
                        results.push({
                            id: name,
                            name: name,
                            address: '',
                            category: '',
                            lat: '',
                            lng: ''
                        });
                    }
                });

                return results.slice(0, 50);
            }"""

            pois = await page.evaluate(js)
            return pois
        except Exception as e:
            print(f"    DOM解析失败: {e}")
            return []

    async def search_and_parse(self, page: Page, keyword: str, url: str, source: str):
        """搜索并解析"""
        print(f"\n  [DOM解析] {source}: {keyword}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            pois = await self.parse_page(page, source)
            for poi in pois:
                self.saver.save_poi(poi, source, keyword)

            # 滚动加载更多
            for _ in range(2):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                pois = await self.parse_page(page, source)
                for poi in pois:
                    self.saver.save_poi(poi, source, keyword)

        except Exception as e:
            print(f"    ! 失败: {e}")


# ==================== 主程序 ====================
async def main():
    print("=" * 60)
    print("高级地图POI爬虫 - API拦截版")
    print("=" * 60)

    saver = AdvancedPOISaver(CONFIG["output_dir"], CONFIG["output_file"])

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/advanced_map_scraper",
            headless=CONFIG["headless"],
            executable_path=chrome_path if Path(chrome_path).exists() else None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
            ]
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        # 创建拦截器
        amap_interceptor = AmapAPIInterceptor(saver, CONFIG)
        baidu_interceptor = BaiduAPIInterceptor(saver, CONFIG)
        dom_parser = DOMParser(saver, CONFIG)

        # 设置拦截
        await amap_interceptor.setup_interception(page)
        await baidu_interceptor.setup_interception(page)

        try:
            # 方法1: 高德地图API拦截
            print("\n[方法1] 高德地图API拦截")
            for keyword in CONFIG["keywords"][:3]:
                await amap_interceptor.search(page, keyword)
                await asyncio.sleep(2)

            # 方法2: 百度地图API拦截
            print("\n[方法2] 百度地图API拦截")
            for keyword in CONFIG["keywords"][:3]:
                await baidu_interceptor.search(page, keyword)
                await asyncio.sleep(2)

            # 方法3: DOM解析（备用）
            print("\n[方法3] DOM解析备用方案")

            # 腾讯地图
            for keyword in CONFIG["keywords"][:2]:
                url = f"https://apis.map.qq.com/uri/v1/search?keyword={quote(keyword)}&city={quote(CONFIG['city'])}"
                await dom_parser.search_and_parse(page, keyword, url, "腾讯地图")
                await asyncio.sleep(1)

        finally:
            await asyncio.sleep(5)
            await browser.close()

    print(f"\n{'=' * 60}")
    print(f"✓ 完成! 共获取 {saver.get_count()} 条POI数据")
    print(f"✓ 数据保存在: {saver.file_path}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
