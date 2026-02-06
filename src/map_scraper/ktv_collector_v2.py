"""
KTV数据采集器 v2

使用更多搜索策略采集北京KTV数据

作者: UVM Research Team
"""

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests


CONFIG = {
    "city": "北京",
    "city_code": "110100",
    # 使用更多搜索词，包括具体区域
    "keywords": [
        # 通用词
        "KTV",
        "量贩KTV",
        "量贩式KTV",
        "卡拉OK",
        "歌舞厅",

        # 具体区域 + KTV
        "朝阳KTV",
        "海淀KTV",
        "西城KTV",
        "东城KTV",
        "丰台KTV",
        "通州KTV",
        "昌平KTV",
        "大兴KTV",

        # 品牌词
        "温莎KTV",
        "麦乐迪KTV",
        "纯K KTV",
        "魅KTV",
        "欢乐迪KTV",
        "好乐迪KTV",
        "唱吧麦颂",
        "糖果KTV",
        "快乐迪KTV",
        "首都KTV",
    ],
    "output_dir": "data/raw",
    "output_file": "ktv_pois.csv",
    "max_pages": 10,
}


class KTVCollectorV2:
    """KTV数据采集器 v2"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self._init_csv()

        # 获取高德API key
        self.amap_key = self._get_amap_key()

    def _get_amap_key(self) -> str:
        """从已有代码中获取高德API key"""
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

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "type", "tel", "rating", "cost", "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

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

    def save_poi(self, poi: Dict) -> bool:
        name = poi.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        key = f"{name}_{poi.get('lng', '')}_{poi.get('lat', '')}"
        if key in self.seen:
            return False
        self.seen.add(key)

        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                poi.get("id", ""),
                name,
                poi.get("address", ""),
                poi.get("district", ""),
                poi.get("lng", ""),
                poi.get("lat", ""),
                poi.get("type", ""),
                poi.get("tel", ""),
                poi.get("rating", ""),
                poi.get("cost", ""),
                "高德地图",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def search_amap(self, keyword: str, page: int = 1) -> Dict:
        """搜索高德地图"""
        if not self.amap_key:
            return {}

        url = "https://restapi.amap.com/v5/place/text"

        params = {
            "key": self.amap_key,
            "keywords": keyword,
            "city": self.config["city_code"],
            "city_limit": "true",
            "page_size": "50",
            "page_num": str(page - 1),
            "show_fields": "business,photos"
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            return response.json()
        except Exception as e:
            return {}

    def parse_pois(self, data: Dict) -> List[Dict]:
        """解析POI数据"""
        pois = []

        try:
            for item in data.get("pois", []):
                name = item.get("name", "")
                if not self.is_valid_name(name):
                    continue

                # 位置
                location = item.get("location", "")
                lng, lat = "", ""
                if location:
                    parts = location.split(",")
                    if len(parts) == 2:
                        lng, lat = parts

                # 地址
                address = item.get("address", "")

                # 区域
                cityname = item.get("cityname", "")
                adname = item.get("adname", "")
                district = f"{cityname}{adname}" if cityname or adname else ""

                # 电话
                tel = item.get("tel", "")

                # 类型
                type_name = item.get("type", "")

                # ID
                poi_id = item.get("id", "")

                pois.append({
                    "id": poi_id,
                    "name": name,
                    "address": address,
                    "district": district,
                    "lng": lng,
                    "lat": lat,
                    "type": type_name,
                    "tel": tel
                })

        except Exception as e:
            pass

        return pois

    def run(self):
        """运行采集器"""
        print("=" * 70)
        print("KTV数据采集器 v2")
        print("=" * 70)

        if not self.amap_key:
            print("\n错误: 未找到高德API key")
            return

        print(f"\n城市: {self.config['city']}")
        print(f"关键词数: {len(self.config['keywords'])}\n")

        total_count = 0
        beijing_count = 0

        for keyword in self.config["keywords"]:
            print(f"[{keyword}]")

            for page in range(1, self.config["max_pages"] + 1):
                print(f"  第{page}页...", end=" ")

                data = self.search_amap(keyword, page)

                if not data:
                    print("无结果")
                    break

                count = int(data.get("count", 0))
                pois = self.parse_pois(data)

                if not pois:
                    print("无更多")
                    break

                page_beijing = 0
                for poi in pois:
                    if self.save_poi(poi):
                        total_count += 1
                        # 检查是否是北京
                        lat = float(poi.get("lat", 0))
                        lng = float(poi.get("lng", 0))
                        if 39 < lat < 41 and 115 < lng < 118:
                            beijing_count += 1
                            page_beijing += 1

                print(f"共{len(pois)}条, 北京{page_beijing}条")

                if count <= page * 50:
                    break

                time.sleep(0.2)

        print(f"\n{'=' * 70}")
        print(f"采集完成！")
        print(f"  总共保存: {total_count} 条")
        print(f"  其中北京: {beijing_count} 条")
        print(f"数据保存在: {self.output_path}")


def main():
    collector = KTVCollectorV2(CONFIG)
    collector.run()


if __name__ == "__main__":
    main()
