"""
高德地图网格搜索爬虫
使用矩形区域搜索，覆盖更广的范围

作者: UVM Research Team
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, List

import aiohttp


# ==================== 配置 ====================
CONFIG = {
    "city": "北京",
    "city_code": "110000",  # 北京市城市代码
    "output_dir": "data/raw",
    "output_file": "vending_grid.csv",
    "api_key": "6dc3b2f659ec16fefe5016f0ad69ad25",

    # 搜索关键词
    "keywords": [
        "友宝", "售货机", "无人售货", "饮料机", "咖啡机",
        "自动售货", "自动贩卖", "成人用品售货"
    ],

    # 北京市的矩形边界（用于网格搜索）
    "bounds": {
        "min_lat": 39.4,   # 南边界
        "max_lat": 41.1,   # 北边界
        "min_lng": 115.4,  # 西边界
        "max_lng": 117.5,  # 东边界
    },

    # 网格大小（度数），约等于5km x 5km
    "grid_size": 0.05,
}

CSV_HEADERS = [
    "id", "name", "address", "category", "brand", "lat", "lng",
    "city", "district", "source", "crawl_time"
]


# ==================== 数据保存类 ====================
class VendingSaver:
    """售货机数据保存器"""

    CONVENIENCE_STORES = {
        "便利店", "7-11", "711", "全家", "familymart", "罗森", "lawson",
        "物美", "便利蜂", "喜士多", "ok便利店", "快客", "十足", "京客隆",
        "超市发", "好邻居", "顺天府", "超市", "卖��", "购物中心", "百货",
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

    def is_vending_machine(self, name: str) -> bool:
        """判断是否为自动售货机"""
        if not name or len(name) < 3 or len(name) > 100:
            return False

        name_lower = name.lower()

        # 过滤便利店
        for store in self.CONVENIENCE_STORES:
            if store in name_lower:
                return False

        # 必须包含售货机相关词
        vending_keywords = [
            '售货机', '贩卖机', '无人售货', '友宝', 'ubox', 'u-box',
            '丰e足食', '丰翼', '成人用品', '情趣', '饮料机', '咖啡机'
        ]

        return any(kw in name or kw in name_lower for kw in vending_keywords)

    def extract_brand(self, name: str) -> str:
        """从名称中提取品牌"""
        if not name:
            return "其他"

        name_lower = name.lower()

        if "友宝" in name or "ubox" in name_lower or "u-box" in name_lower:
            return "友宝"
        elif "丰e足食" in name or "丰翼" in name:
            return "丰e足食"
        elif "成人用品" in name or "情趣" in name:
            return "成人用品"
        elif "泡泡玛特" in name or "pop mart" in name_lower:
            return "泡泡玛特"
        elif "咖啡" in name:
            return "咖啡机"
        elif "饮料" in name or "可乐" in name or "农夫山泉" in name:
            return "饮料机"
        else:
            return "其他"

    def save_poi(self, poi: Dict[str, Any], source: str = "") -> bool:
        """保存POI数据"""
        name = poi.get("name", "")
        if not self.is_vending_machine(name):
            return False

        poi_id = poi.get("id", "")
        key = f"{poi_id}_{name}"

        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.file_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                "id": poi_id,
                "name": name,
                "address": poi.get("address", ""),
                "category": poi.get("category", ""),
                "brand": self.extract_brand(name),
                "lat": poi.get("lat", ""),
                "lng": poi.get("lng", ""),
                "city": CONFIG["city"],
                "district": poi.get("district", ""),
                "source": source,
                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        return True

    def get_count(self) -> int:
        return len(self.seen)


# ==================== 网格搜索爬虫 ====================
class GridScraper:
    """网格搜索爬虫 - 使用矩形区域搜索"""

    BASE_URL = "https://restapi.amap.com/v5/place/text"

    def __init__(self, api_key: str, config: Dict[str, Any]):
        self.api_key = api_key
        self.config = config
        self.saver = VendingSaver(config["output_dir"], config["output_file"])

    def generate_grid_rectangles(self) -> List[Dict[str, float]]:
        """生成覆盖整个城市的网格矩形"""
        bounds = self.config["bounds"]
        grid_size = self.config["grid_size"]

        rectangles = []
        lat = bounds["min_lat"]
        while lat < bounds["max_lat"]:
            lng = bounds["min_lng"]
            while lng < bounds["max_lng"]:
                rectangles.append({
                    "min_lat": lat,
                    "max_lat": min(lat + grid_size, bounds["max_lat"]),
                    "min_lng": lng,
                    "max_lng": min(lng + grid_size, bounds["max_lng"]),
                })
                lng += grid_size
            lat += grid_size

        return rectangles

    async def search_rectangle(self, session: aiohttp.ClientSession,
                               rect: Dict[str, float], keyword: str) -> int:
        """在指定矩形区域内搜索"""
        count = 0

        # 构建矩形区域字符串
        rectangle = f"{rect['min_lng']},{rect['min_lat']},{rect['max_lng']},{rect['max_lat']}"

        for page in range(1, 6):  # 每个区域最多5页
            params = {
                "keywords": keyword,
                "rectangle": rectangle,
                "page_size": 20,
                "page_num": page,
                "key": self.api_key,
            }

            pois = await self._request(session, params)
            if not pois:
                break

            for poi in pois:
                formatted_poi = {
                    "id": poi.get("id", ""),
                    "name": poi.get("name", ""),
                    "address": poi.get("address", ""),
                    "category": poi.get("type", ""),
                    "lat": poi.get("location", "").split(",")[1] if poi.get("location") else "",
                    "lng": poi.get("location", "").split(",")[0] if poi.get("location") else "",
                    "district": poi.get("adname", "")
                }
                if self.saver.save_poi(formatted_poi, "高德网格"):
                    count += 1

            if len(pois) < 20:
                break

            await asyncio.sleep(0.5)

        return count

    async def _request(self, session: aiohttp.ClientSession, params: Dict, retry: int = 2) -> List[Dict]:
        """执行API请求"""
        for attempt in range(retry):
            try:
                async with session.get(self.BASE_URL, params=params,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("status") == "1":
                        return data.get("pois", [])
                    else:
                        if attempt == retry - 1:
                            return []
            except Exception:
                if attempt < retry - 1:
                    await asyncio.sleep(1)
                    continue
        return []

    async def run(self):
        """执行网格搜索"""
        print("\n[网格搜索] 开始...")

        rectangles = self.generate_grid_rectangles()
        print(f"  生成 {len(rectangles)} 个搜索网格")

        async with aiohttp.ClientSession() as session:
            total_count = 0
            processed = 0

            for rect in rectangles:
                processed += 1
                rect_count = 0

                for keyword in self.config["keywords"]:
                    count = await self.search_rectangle(session, rect, keyword)
                    rect_count += count
                    total_count += count

                if processed % 10 == 0:
                    print(f"  进度: {processed}/{len(rectangles)} | 累计: {total_count} 条")

                await asyncio.sleep(0.3)  # 网格之间延迟

        print(f"\n[网格搜索] 完成! 共获取 {total_count} 条数据")
        return total_count


# ==================== 主程序 ====================
async def main():
    print("=" * 60)
    print("自动售货机网格搜索爬虫")
    print("=" * 60)

    scraper = GridScraper(CONFIG["api_key"], CONFIG)
    await scraper.run()

    print(f"\n数据保存在: {scraper.saver.file_path}")
    print(f"唯一记录数: {scraper.saver.get_count()} 条")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
