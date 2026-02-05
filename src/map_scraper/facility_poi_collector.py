"""
设施POI��集工具
用于获取地铁站、商场、写字楼等选址因素POI数据
"""

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import aiohttp


# ==================== 配置 ====================
AMAP_API_KEY = "6dc3b2f659ec16fefe5016f0ad69ad25"
CITY = "北京"
OUTPUT_DIR = Path("data/location_analysis/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==================== 设施类型定义 ====================
# 选址分析需要获取的设施类型
FACILITY_TYPES = {
    "地铁站": {
        "keywords": ["地铁站", "地铁口"],
        "priority": "high",
        "description": "用于分析交通可达性"
    },
    "写字楼": {
        "keywords": ["写字楼", "办公楼", "商务楼"],
        "priority": "high",
        "description": "用于分析办公需求"
    },
    "商场": {
        "keywords": ["商场", "购物中心", "购物广场"],
        "priority": "high",
        "description": "用于分析商业环境"
    },
    "高校": {
        "keywords": ["大学", "学院", "高校"],
        "priority": "medium",
        "description": "用于分析学生需求"
    },
    "医院": {
        "keywords": ["医院", "诊所"],
        "priority": "medium",
        "description": "用于分析医疗场所需求"
    },
    "小区": {
        "keywords": ["小区", "家园", "公寓", "住宅"],
        "priority": "medium",
        "description": "用于分析居民需求"
    },
    "便利店": {
        "keywords": ["便利店", "7-11", "全家", "罗森"],
        "priority": "high",
        "description": "用于分析竞争环境"
    },
    "酒店": {
        "keywords": ["酒店", "宾馆"],
        "priority": "low",
        "description": "用于分析流动需求"
    },
    "KTV": {
        "keywords": ["KTV", "量贩KTV"],
        "priority": "low",
        "description": "用于分析娱乐需求"
    },
    "网吧": {
        "keywords": ["网吧", "电竞馆", "网咖"],
        "priority": "low",
        "description": "用于分析娱乐需求"
    }
}


class AmapPOICollector:
    """高德地图POI采集器"""

    BASE_URL = "https://restapi.amap.com/v3/place/text"
    SEARCH_URL = "https://restapi.amap.com/v3/place/around"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None
        self.results = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def search_pois(
        self,
        keyword: str,
        region: str = CITY,
        max_count: int = 1000
    ) -> List[Dict]:
        """
        搜索POI，返回详细列表

        Args:
            keyword: 搜索关键词
            region: 搜索区域
            max_count: 最大获取数量

        Returns:
            POI列表，每个包含name, address, lon, lat等
        """
        all_pois = []
        page = 1
        page_size = 50  # 高德API每页最多50条

        while len(all_pois) < max_count:
            params = {
                "key": self.api_key,
                "keywords": keyword,
                "city": region,
                "offset": page_size,
                "page": page,
                "extensions": "base"  # 返回基本信息
            }

            try:
                async with self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

                    if data.get("status") == "1":
                        pois = data.get("pois", [])
                        if not pois:
                            break

                        for poi in pois:
                            # 提取关键信息
                            name = poi.get("name", "")
                            address = poi.get("address", "")
                            pname = poi.get("pname", "")  # 省
                            cityname = poi.get("cityname", "")  # 市
                            adname = poi.get("adname", "")  # 区
                            location = poi.get("location", "")  # "lng,lat"

                            if location:
                                lon, lat = location.split(",") if "," in location else (None, None)
                            else:
                                lon, lat = None, None

                            all_pois.append({
                                "id": poi.get("id", ""),
                                "name": name,
                                "address": address,
                                "province": pname,
                                "city": cityname,
                                "district": adname,
                                "lng": lon,
                                "lat": lat,
                                "type": poi.get("type", ""),
                                "keyword": keyword
                            })

                        print(f"  {keyword} 第{page}页: 获取{len(pois)}条，累计{len(all_pois)}条")

                        # 检查是否还有更多
                        count = int(data.get("count", 0))
                        if len(all_pois) >= count:
                            break

                        page += 1
                        await asyncio.sleep(0.3)  # 避免请求过快
                    else:
                        print(f"  {keyword} 搜索失败: {data.get('info', 'Unknown')}")
                        break

            except Exception as e:
                print(f"  {keyword} 请求异常: {e}")
                break

        return all_pois[:max_count]

    async def collect_all_facilities(
        self,
        facility_types: Dict = None,
        max_per_type: int = 500
    ):
        """
        采集所有类型的设施数据

        Args:
            facility_types: 设施类型定义
            max_per_type: 每种设施最大采集数量
        """
        if facility_types is None:
            facility_types = FACILITY_TYPES

        print("\n" + "=" * 70)
        print("开始采集设施数据...")
        print("=" * 70)

        for facility_name, config in facility_types.items():
            print(f"\n[{facility_name}] {config.get('description', '')}")

            all_pois = []
            keyword_counts = {}

            # 对每个关键词进行搜索
            for keyword in config["keywords"]:
                print(f"  搜索关键词: {keyword}", end="", flush=True)
                pois = await self.search_pois(keyword, max_count=max_per_type)

                keyword_counts[keyword] = len(pois)
                all_pois.extend(pois)

                await asyncio.sleep(0.5)

            # 去重（按名称和位置）
            unique_pois = self._deduplicate_pois(all_pois)

            self.results[facility_name] = {
                "pois": unique_pois,
                "count": len(unique_pois),
                "keyword_counts": keyword_counts,
                "config": config
            }

            print(f"  → 去重后: {len(unique_pois)}条")

    def _deduplicate_pois(self, pois: List[Dict]) -> List[Dict]:
        """去重POI数据"""
        seen = set()
        unique = []

        for poi in pois:
            # 使用名称+坐标作为唯一标识
            key = (poi["name"], poi["lng"], poi["lat"])
            if key not in seen and poi["lng"] and poi["lat"]:
                seen.add(key)
                unique.append(poi)

        return unique

    def save_results(self):
        """保存采集结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print("\n" + "=" * 70)
        print("保存数据...")
        print("=" * 70)

        # 1. 保存各类设施为单独CSV
        for facility_name, data in self.results.items():
            if not data["pois"]:
                continue

            filename = OUTPUT_DIR / f"facility_{facility_name}_{timestamp}.csv"
            with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                fieldnames = ["id", "name", "address", "district", "lng", "lat", "type", "keyword"]
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(data["pois"])

            print(f"  {facility_name}: {filename} ({data['count']}条)")

        # 2. 保存合并数据
        all_pois = []
        for facility_name, data in self.results.items():
            for poi in data["pois"]:
                poi["facility_type"] = facility_name
                all_pois.append(poi)

        merged_file = OUTPUT_DIR / f"all_facilities_{timestamp}.csv"
        with open(merged_file, "w", newline="", encoding="utf-8-sig") as f:
            if all_pois:
                fieldnames = ["id", "name", "address", "district", "lng", "lat", "type", "facility_type", "keyword"]
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(all_pois)

        print(f"\n合并数据: {merged_file} ({len(all_pois)}条)")

        # 3. 保存统计摘要
        summary = {
            "timestamp": timestamp,
            "city": CITY,
            "facilities": {
                name: {
                    "count": data["count"],
                    "keyword_counts": data["keyword_counts"]
                }
                for name, data in self.results.items()
            },
            "total_pois": len(all_pois)
        }

        summary_file = OUTPUT_DIR / f"collection_summary_{timestamp}.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"统计摘要: {summary_file}")

    def print_summary(self):
        """打印采集摘要"""
        print("\n" + "=" * 70)
        print("设施采集摘要")
        print("=" * 70)

        total = 0
        for name, data in self.results.items():
            print(f"\n{name}:")
            print(f"  数量: {data['count']}")
            print(f"  关键词统计: {data['keyword_counts']}")
            total += data['count']

        print(f"\n总计: {total}条POI")
        print("=" * 70)


async def main():
    """主程序"""
    print("=" * 70)
    print("设施POI采集工具")
    print("=" * 70)

    # 只采集高优先级的设施
    high_priority = {
        k: v for k, v in FACILITY_TYPES.items()
        if v.get("priority") == "high"
    }

    print(f"\n将采集以下高优先级设施:")
    for name, config in high_priority.items():
        print(f"  - {name}: {', '.join(config['keywords'])}")

    async with AmapPOICollector(AMAP_API_KEY) as collector:
        await collector.collect_all_facilities(
            facility_types=high_priority,
            max_per_type=500  # 每种设施最多500条
        )

        collector.print_summary()
        collector.save_results()

    print("\n采集完成!")


if __name__ == "__main__":
    asyncio.run(main())
