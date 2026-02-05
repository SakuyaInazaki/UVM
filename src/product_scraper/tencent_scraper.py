"""
腾讯地图API爬虫

使用腾讯地图WebService API搜索POI数据

文档: https://lbs.qq.com/webservice_v1/guide-search.html

作者: UVM Research Team
"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List
from urllib.parse import quote

import aiohttp


CONFIG = {
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "tencent_pois.csv",
    # 腾讯地图API Key - 需要在腾讯位置服务控制台申请
    # 控制台: https://lbs.qq.com/dev/console/application/mine
    "api_key": "",  # 请填入你的API Key
    # 搜索关键词 - 涵盖可能的自动售货机相关类型
    "keywords": [
        "自动售货机",
        "自动售卖机",
        "无人售货",
        "友宝",
        "丰e足食",
        "自动售货",
        "饮料机",
        "成人用品",
        "情趣用品",
        "24小时售货",
    ],
}

CSV_HEADERS = ["id", "title", "address", "category", "lat", "lng", "tel", "city", "crawl_time"]


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

    def is_valid_poi(self, poi: Dict[str, Any]) -> bool:
        title = poi.get("title", "")

        # 过滤无效数据
        invalid = ['class=', 'data-', 'transform', 'none;', '<', '>', '备案', '举报', 'ICP']
        for p in invalid:
            if p in title:
                return False

        if not re.search(r'[\u4e00-\u9fff]', title):
            return False

        if len(title) < 3 or len(title) > 100:
            return False

        return True

    def save_poi(self, poi: Dict[str, Any], keyword: str = "") -> bool:
        if not self.is_valid_poi(poi):
            return False

        poi_id = poi.get("id", "")
        key = f"{poi_id}_{poi.get('title', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        location = poi.get("location", {})
        lat = location.get("lat", "") if isinstance(location, dict) else ""
        lng = location.get("lng", "") if isinstance(location, dict) else ""

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "id": poi_id,
                "title": poi.get("title", ""),
                "address": poi.get("address", ""),
                "category": poi.get("category", ""),
                "lat": lat,
                "lng": lng,
                "tel": poi.get("tel", ""),
                "city": CONFIG["city"],
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        category = poi.get("category", "N/A")
        print(f"  [{category}] {poi.get('title', '')}")
        return True

    def get_count(self) -> int:
        return len(self.seen)


class TencentMapScraper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.saver = TencentSaver(config["output_dir"], config["output_file"])
        self.base_url = "https://apis.map.qq.com/ws/place/v1/search"

    def has_api_key(self) -> bool:
        return bool(self.config.get("api_key", ""))

    async def run(self):
        print(f"\n{'='*60}")
        print(f"腾讯地图API爬虫")
        print(f"{'='*60}\n")

        if not self.has_api_key():
            print("⚠️ 未配置API Key!")
            print(f"\n请按以下步骤申请腾讯地图API Key:")
            print(f"1. 访问: https://lbs.qq.com/dev/console/application/mine")
            print(f"2. 登录/注册腾讯账号")
            print(f"3. 创建应用并获取Key")
            print(f"4. 将Key填入 CONFIG['api_key']")
            print(f"\n已创建文件: {self.config['output_dir']}/{self.config['output_file']}")
            return

        async with aiohttp.ClientSession() as session:
            # 方法1: 关键词搜索
            await self.keyword_search(session)

            # 方法2: 周边搜索 (需要指定中心点)
            await self.nearby_search(session)

        print(f"\n共获取 {self.saver.get_count()} 条 POI\n")

    async def keyword_search(self, session: aiohttp.ClientSession):
        """关键词搜索"""
        print(f"[方法1] 城市关键词搜索")

        city = self.config["city"]
        api_key = self.config["api_key"]

        for keyword in self.config["keywords"]:
            print(f"\n  搜索: {keyword}")

            # 构建请求URL - 指定城市搜索
            params = {
                "keyword": keyword,
                "boundary": f"region({city},0)",  # 仅在指定城市搜索，不自动扩大范围
                "page_size": 20,
                "page_index": 1,
                "key": api_key,
                "output": "json"
            }

            try:
                # 第一页
                result = await self._search_request(session, params)
                if result:
                    pois = result.get("data", [])
                    for poi in pois:
                        self.saver.save_poi(poi, keyword)

                    count = result.get("count", 0)
                    print(f"    总共 {count} 条结果")

                    # 翻页 (最多10页，每页20条=200条限制)
                    max_pages = min(10, (count + 19) // 20)
                    for page in range(2, max_pages + 1):
                        params["page_index"] = page
                        result = await self._search_request(session, params)
                        if result:
                            pois = result.get("data", [])
                            for poi in pois:
                                self.saver.save_poi(poi, keyword)

                await asyncio.sleep(0.5)  # 避免请求过快

            except Exception as e:
                print(f"    ! 失败: {e}")

    async def nearby_search(self, session: aiohttp.ClientSession):
        """周边搜索 - 以市中心为圆心"""
        print(f"\n[方法2] 周边搜索")

        # 北京市中心坐标
        centers = [
            (39.908491, 116.374328, "天安门"),
            (39.918938, 116.397427, "东城区"),
            (39.9072, 116.3689, "西城区"),
        ]

        api_key = self.config["api_key"]

        for lat, lng, name in centers:
            print(f"\n  中心点: {name}")

            for keyword in ["自动售货机", "友宝"]:
                params = {
                    "keyword": keyword,
                    "boundary": f"nearby({lat},{lng},1000)",  # 周边1000米
                    "page_size": 20,
                    "page_index": 1,
                    "key": api_key,
                    "output": "json"
                }

                try:
                    result = await self._search_request(session, params)
                    if result:
                        pois = result.get("data", [])
                        if pois:
                            print(f"    找到 {len(pois)} 条")
                            for poi in pois:
                                self.saver.save_poi(poi, keyword)

                except Exception as e:
                    print(f"    ! 失败: {e}")

                await asyncio.sleep(0.5)

    async def _search_request(self, session: aiohttp.ClientSession, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行搜索请求"""
        url = f"{self.base_url}?{self._build_query(params)}"

        async with session.get(url, timeout=30) as response:
            data = await response.json()

            status = data.get("status", -1)
            if status != 0:
                message = data.get("message", "未知错误")
                print(f"    API错误: {message} (status={status})")
                return {}

            return data

    def _build_query(self, params: Dict[str, Any]) -> str:
        """构建查询字符串"""
        return "&".join(f"{k}={quote(str(v))}" for k, v in params.items())


async def main():
    scraper = TencentMapScraper(CONFIG)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
