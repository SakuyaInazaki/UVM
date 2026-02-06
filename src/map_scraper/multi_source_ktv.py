"""
多源KTV数据采集器 - 交叉验证

从高德、百度等多个平台采集数据，确保数据准确性

作者: UVM Research Team
"""

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict

import requests


CONFIG = {
    "city": "北京",
    "city_code": "110100",
    "output_dir": "data/raw",
    "output_file": "ktv_pois_multi_source.csv",
    "max_pages": 10,
}


class MultiSourceKTVCollector:
    """多源KTV数据采集器"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # 按来源分类存储
        self.sources = {
            "amap": set(),  # 高德
            "baidu": set(),  # 百度
        }
        self.all_pois = {}  # name -> poi_data

        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "type", "tel", "sources", "source_count", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def get_amap_key(self) -> str:
        """获取高德API key"""
        config_file = Path("src/map_scraper/vending_scraper.py")
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    content = f.read()
                    match = re.search(r'"amap_api_key":\s*"([^"]+)"', content)
                    if match:
                        return match.group(1)
            except:
                pass
        return ""

    def get_baidu_key(self) -> str:
        """获取百度API key"""
        config_file = Path("src/map_scraper/vending_scraper.py")
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    content = f.read()
                    match = re.search(r'"tencent_api_key":\s*"([^"]+)"', content)
                    if match:
                        return match.group(1)
            except:
                pass
        return ""

    def is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        invalid = ['undefined', 'null', '<', '>', 'function', 'class=']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def is_beijing(self, lng: str, lat: str) -> bool:
        """判断坐标是否在北京"""
        try:
            lat_f = float(lat)
            lng_f = float(lng)
            return 39 < lat_f < 41 and 115 < lng_f < 118
        except:
            return False

    def add_poi(self, poi: Dict, source: str):
        """添加POI，支持多源合并"""
        name = poi.get("name", "").strip()
        if not self.is_valid_name(name):
            return

        # 创建唯一键（基于坐标）
        lng = poi.get("lng", "")
        lat = poi.get("lat", "")
        key = f"{name}_{lng}_{lat}"

        if not self.is_beijing(lng, lat):
            return

        if key in self.all_pois:
            # 已存在，合并源信息
            self.all_pois[key]["sources"].add(source)
            self.all_pois[key]["source_count"] += 1
        else:
            # 新POI
            self.all_pois[key] = {
                "id": poi.get("id", ""),
                "name": name,
                "address": poi.get("address", ""),
                "district": poi.get("district", ""),
                "lng": lng,
                "lat": lat,
                "type": poi.get("type", ""),
                "tel": poi.get("tel", ""),
                "sources": {source},
                "source_count": 1
            }

    def search_amap(self, keywords: List[str]) -> int:
        """高德地图搜索"""
        api_key = self.get_amap_key()
        if not api_key:
            print("  ! 未找到高德API key")
            return 0

        url = "https://restapi.amap.com/v5/place/text"
        count = 0

        for keyword in keywords:
            for page in range(1, self.config["max_pages"] + 1):
                params = {
                    "key": api_key,
                    "keywords": keyword,
                    "city": self.config["city_code"],
                    "city_limit": "true",
                    "page_size": "50",
                    "page_num": str(page - 1),
                    "show_fields": "business"
                }

                try:
                    response = requests.get(url, params=params, timeout=30)
                    data = response.json()

                    if not data or int(data.get("count", 0)) == 0:
                        break

                    for item in data.get("pois", []):
                        name = item.get("name", "")
                        if not name:
                            continue

                        location = item.get("location", "")
                        lng, lat = "", ""
                        if location:
                            parts = location.split(",")
                            if len(parts) == 2:
                                lng, lat = parts

                        self.add_poi({
                            "id": item.get("id", ""),
                            "name": name,
                            "address": item.get("address", ""),
                            "district": item.get("adname", ""),
                            "lng": lng,
                            "lat": lat,
                            "type": item.get("type", ""),
                            "tel": item.get("tel", "")
                        }, "amap")

                    if int(data.get("count", 0)) <= page * 50:
                        break

                    time.sleep(0.2)
                except Exception as e:
                    print(f"  ! 高德搜索错误: {e}")
                    break

        return len([p for p in self.all_pois.values() if "amap" in p["sources"]])

    def search_baidu(self, keywords: List[str]) -> int:
        """百度地图搜索"""
        api_key = self.get_baidu_key()
        if not api_key:
            print("  ! 未找到百度API key（或使用腾讯地图key）")
            return 0

        # 百度地图Place API
        url = "https://api.map.baidu.com/place/v2/search"
        count = 0

        for keyword in keywords:
            params = {
                "query": keyword,
                "region": self.config["city"],
                "city_limit": "true",
                "page_size": 20,
                "page_num": 0,
                "output": "json",
                "ak": api_key
            }

            try:
                response = requests.get(url, params=params, timeout=30)
                data = response.json()

                if data.get("status") == 0:
                    for item in data.get("results", []):
                        name = item.get("name", "")
                        if not name:
                            continue

                        location = item.get("location", {})
                        lng = location.get("lng", "")
                        lat = location.get("lat", "")

                        self.add_poi({
                            "id": item.get("uid", ""),
                            "name": name,
                            "address": item.get("address", ""),
                            "district": item.get("area", ""),
                            "lng": lng,
                            "lat": lat,
                            "type": item.get("detail_info", {}).get("tag", ""),
                            "tel": item.get("telephone", "")
                        }, "baidu")

                time.sleep(0.2)
            except Exception as e:
                print(f"  ! 百度搜索错误: {e}")

        return len([p for p in self.all_pois.values() if "baidu" in p["sources"]])

    def save_results(self):
        """保存结果"""
        count = 0
        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            for poi in self.all_pois.values():
                if self.is_beijing(poi["lng"], poi["lat"]):
                    sources_str = ",".join(poi["sources"])
                    writer.writerow([
                        poi["id"],
                        poi["name"],
                        poi["address"],
                        poi["district"],
                        poi["lng"],
                        poi["lat"],
                        poi["type"],
                        poi["tel"],
                        sources_str,
                        poi["source_count"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ])
                    count += 1
        return count

    def run(self):
        """运行采集器"""
        print("=" * 70)
        print("多源KTV数据采集器 - 交叉验证")
        print("=" * 70)

        # 关键词列表
        keywords = [
            "KTV", "量贩KTV", "量贩式KTV", "卡拉OK",
            "歌舞厅", "音乐厅", "娱乐城"
        ]

        # 高德地图采集
        print("\n[高德地图]")
        amap_count = self.search_amap(keywords)
        print(f"  采集到: {amap_count} 条")

        # 百度地图采集
        print("\n[百度地图]")
        baidu_count = self.search_baidu(keywords)
        print(f"  采集到: {baidu_count} 条")

        # 按区县补充采集
        print("\n[按区县补充采集]")
        districts = {
            "朝阳区": "110105",
            "海淀区": "110108",
            "丰台区": "110106",
            "东城区": "110101",
            "西城区": "110102",
            "通州区": "110112",
            "昌平区": "110114",
            "大兴区": "110115",
            "房山区": "110111",
            "顺义区": "110113",
        }

        for district_name, district_code in districts.items():
            for keyword in ["KTV", "量贩KTV"]:
                params = {
                    "key": self.get_amap_key(),
                    "keywords": keyword,
                    "region": district_code,
                    "city_limit": "true",
                    "page_size": "50",
                    "page_num": "0",
                }
                try:
                    response = requests.get(
                        "https://restapi.amap.com/v5/place/text",
                        params=params, timeout=20
                    )
                    data = response.json()
                    for item in data.get("pois", []):
                        location = item.get("location", "")
                        if location:
                            parts = location.split(",")
                            lng, lat = parts[0], parts[1] if len(parts) > 1 else ""
                            self.add_poi({
                                "id": item.get("id", ""),
                                "name": item.get("name", ""),
                                "address": item.get("address", ""),
                                "district": district_name,
                                "lng": lng,
                                "lat": lat,
                                "type": item.get("type", ""),
                                "tel": item.get("tel", "")
                            }, "amap")
                except:
                    pass
            time.sleep(0.1)

        # 保存结果
        total_count = self.save_results()

        # 统计
        single_source = len([p for p in self.all_pois.values() if p["source_count"] == 1])
        multi_source = len([p for p in self.all_pois.values() if p["source_count"] > 1])

        print(f"\n{'=' * 70}")
        print(f"采集完成！")
        print(f"  总计: {total_count} 家KTV")
        print(f"  单源验证: {single_source} 家")
        print(f"  多源验证: {multi_source} 家")
        print(f"数据保存在: {self.output_path}")


def main():
    collector = MultiSourceKTVCollector(CONFIG)
    collector.run()


if __name__ == "__main__":
    main()
