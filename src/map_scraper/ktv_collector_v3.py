"""
KTV数据采集器 v3 - 按北京各区采集
"""

import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests

CONFIG = {
    "keywords": ["KTV", "量贩KTV", "量贩式KTV", "卡拉OK", "歌舞厅"],
    "output_dir": "data/raw",
    "output_file": "ktv_pois.csv",
    "max_pages": 5,
    "amap_key": "",
}


class KTVCollectorV3:
    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self._init_csv()
        self.config["amap_key"] = self._get_amap_key()

    def _get_amap_key(self) -> str:
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
                    "type", "tel", "source", "crawl_time"
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
                "高德地图",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def search_amap(self, keyword: str, city_code: str, page: int = 1) -> Dict:
        url = "https://restapi.amap.com/v5/place/text"

        params = {
            "key": self.config["amap_key"],
            "keywords": keyword,
            "region": city_code,
            "city_limit": "true",
            "page_size": "50",
            "page_num": str(page - 1),
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            return response.json()
        except Exception as e:
            return {}

    def parse_pois(self, data: Dict) -> List[Dict]:
        pois = []

        try:
            for item in data.get("pois", []):
                name = item.get("name", "")
                if not self.is_valid_name(name):
                    continue

                location = item.get("location", "")
                lng, lat = "", ""
                if location:
                    parts = location.split(",")
                    if len(parts) == 2:
                        lng, lat = parts

                pois.append({
                    "id": item.get("id", ""),
                    "name": name,
                    "address": item.get("address", ""),
                    "district": item.get("adname", ""),
                    "lng": lng,
                    "lat": lat,
                    "type": item.get("type", ""),
                    "tel": item.get("tel", "")
                })

        except Exception:
            pass

        return pois

    def run(self):
        print("=" * 70)
        print("KTV数据采集器 v3 - 按区采集")
        print("=" * 70)

        if not self.config["amap_key"]:
            print("\n错误: 未找到高德API key")
            return

        total_count = 0

        # 先用全市搜索
        print("\n[全市搜索]")
        city_code = "110100"
        for keyword in self.config["keywords"]:
            for page in range(1, self.config["max_pages"] + 1):
                data = self.search_amap(keyword, city_code, page)

                if not data or int(data.get("count", 0)) == 0:
                    break

                pois = self.parse_pois(data)
                for poi in pois:
                    if self.save_poi(poi):
                        total_count += 1

                print(f"  {keyword} 第{page}页: {len(pois)}条")

                if int(data.get("count", 0)) <= page * 50:
                    break

                time.sleep(0.2)

        # 然后按主要城区搜索
        main_districts = {
            "朝阳区": "110105",
            "海淀区": "110108",
            "丰台区": "110106",
            "东城区": "110101",
            "西城区": "110102",
            "通州区": "110112",
            "昌平区": "110114",
            "大兴区": "110115",
        }

        print("\n[各区搜索]")
        for district_name, district_code in main_districts.items():
            print(f"\n{district_name}")
            for keyword in ["KTV", "量贩KTV", "歌舞厅"]:
                for page in range(1, 4):
                    data = self.search_amap(keyword, district_code, page)

                    if not data or int(data.get("count", 0)) == 0:
                        break

                    pois = self.parse_pois(data)
                    page_count = 0
                    for poi in pois:
                        if self.save_poi(poi):
                            total_count += 1
                            page_count += 1

                    if page_count > 0:
                        print(f"  {keyword} 第{page}页: +{page_count}条")

                    if int(data.get("count", 0)) <= page * 50:
                        break

                    time.sleep(0.2)

        print(f"\n{'=' * 70}")
        print(f"采集完成！共获取 {total_count} 条数据")
        print(f"数据保存在: {self.output_path}")


def main():
    collector = KTVCollectorV3(CONFIG)
    collector.run()


if __name__ == "__main__":
    main()
