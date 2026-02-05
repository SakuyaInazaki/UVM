"""
腾讯地图POI爬虫

使用腾讯地图WebService API搜索POI

API文档: https://lbs.qq.com/webservice_v1/guide-search.html

注意: 需要申请腾讯地图开发者密钥(Key)
申请地址: https://lbs.qq.com/dev/console/application/mine

作者: UVM Research Team
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List, Optional
from urllib.parse import quote

import aiohttp


CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "tencent_pois.csv",
    # 腾讯地图API密钥 (需要申请)
    "api_key": "",  # 请填入你的腾讯地图API Key
    # 搜索关键词
    "keywords": [
        "自动售货机",
        "无人售货",
        "自助售货",
        "成人用品自动售货",
        "友宝",
        "饮料自动售货机",
    ],
    # 北京各区域的边界 (用于矩形搜索)
    "regions": [
        # 朝阳区
        {"name": "朝阳", "bounds": "39.84,116.44,39.96,116.58"},
        # 海淀区
        {"name": "海淀", "bounds": "39.86,116.22,39.98,116.38"},
        # 东城区
        {"name": "东城", "bounds": "39.88,116.38,39.95,116.44"},
        # 西城区
        {"name": "西城", "bounds": "39.88,116.34,39.95,116.42"},
        # 丰台区
        {"name": "丰台", "bounds": "39.78,116.22,39.88,116.35"},
    ],
}

CSV_HEADERS = ["id", "name", "address", "category", "lat", "lng", "adcode", "city", "crawl_time"]


class TencentSaver:
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
        invalid = ['备案', '举报', 'ICP', 'cookies', 'http', 'www']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_poi(self, poi: Dict[str, Any]) -> bool:
        name = poi.get("title", "").strip()
        poi_id = poi.get("id", "")

        if not self.is_valid_name(name):
            return False

        if poi_id in self.seen:
            return False
        self.seen.add(poi_id)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "id": poi_id,
                "name": name,
                "address": poi.get("address", ""),
                "category": poi.get("category", ""),
                "lat": poi.get("location", {}).get("lat", ""),
                "lng": poi.get("location", {}).get("lng", ""),
                "adcode": poi.get("ad_info", {}).get("adcode", ""),
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        print(f"  [{poi.get('category', 'N/A')}] {name} - {poi.get('address', 'N/A')[:30]}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


class TencentScraper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.saver = TencentSaver(config["output_dir"], config["output_file"])
        self.session: Optional[aiohttp.ClientSession] = None

        # 检查API Key
        if not self.config.get("api_key"):
            print("! 警告: 未设置腾讯地图API密钥")
            print("! 请访问 https://lbs.qq.com/dev/console/application/mine 申请密钥")
            print("! 将密钥填入 CONFIG['api_key']")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session:
            await self.session.close()

    async def run(self):
        print(f"\n{'='*60}")
        print(f"腾讯地图POI爬虫")
        print(f"{'='*60}\n")

        if not self.config.get("api_key"):
            print("请先设置腾讯地图API密钥!")
            return

        try:
            # 方法1: 城市级搜索
            await self.search_by_city()

            # 方法2: 矩形区域搜索
            await self.search_by_regions()

        finally:
            await self.close()

        print(f"\n共获取 {self.saver.get_count()} 条 POI\n")

    async def search_by_city(self):
        """按城市搜索"""
        print(f"[方法1] 城市级搜索")

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")
            count = 0

            for page_index in range(1, 11):  # 最多10页
                pois = await self.search_api(
                    keyword=keyword,
                    boundary=f"region({self.config['city']},0)",
                    page_index=page_index,
                    page_size=20
                )

                if not pois:
                    break

                for poi in pois:
                    if self.saver.save_poi(poi):
                        count += 1

                print(f"    第{page_index}页: 获取 {len(pois)} 条")

                if len(pois) < 20:
                    break

                await asyncio.sleep(0.5)

            print(f"    总计: {count} 条")

    async def search_by_regions(self):
        """按矩形区域搜索"""
        print(f"\n[方法2] 矩形区域搜索")

        for region in self.config["regions"]:
            region_name = region["name"]
            bounds = region["bounds"]

            print(f"\n  区域: {region_name}")

            for keyword in self.config["keywords"][:3]:  # 只用前3个关键词
                print(f"    搜索: {keyword}")

                for page_index in range(1, 6):  # 最多5页
                    pois = await self.search_api(
                        keyword=keyword,
                        boundary=f"rectangle({bounds})",
                        page_index=page_index,
                        page_size=20
                    )

                    if not pois:
                        break

                    for poi in pois:
                        self.saver.save_poi(poi)

                    if len(pois) < 20:
                        break

                    await asyncio.sleep(0.5)

    async def search_api(
        self,
        keyword: str,
        boundary: str,
        page_index: int = 1,
        page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """调用腾讯地图搜索API"""
        url = "https://apis.map.qq.com/ws/place/v1/search"

        params = {
            "keyword": keyword,
            "boundary": boundary,
            "page_size": page_size,
            "page_index": page_index,
            "key": self.config["api_key"],
            "output": "json"
        }

        try:
            session = await self._get_session()
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

                if data.get("status") == 0:
                    return data.get("data", [])
                else:
                    error = data.get("message", "Unknown error")
                    print(f"    API错误: {error}")
                    return []

        except asyncio.TimeoutError:
            print(f"    请求超时")
            return []
        except Exception as e:
            print(f"    请求失败: {e}")
            return []


async def main():
    scraper = TencentScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
