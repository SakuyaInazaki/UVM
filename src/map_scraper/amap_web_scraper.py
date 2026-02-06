"""
通过高德地图网页版采集丰e足食售货机位置

直接访问高��地图网站搜索页面，解析返回的POI数据

作者: UVM Research Team
"""

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote

import requests


CONFIG = {
    "keywords": [
        "丰e足食",
        "自动售货机",
        "无人售货",
        "智能货柜",
        "自助售货",
    ],
    "city": "北京",  # 城市代码
    "city_code": "110100",  # 北京市
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_amap_web.csv",
}


class AmapWebScraper:
    """高德地图网页爬虫"""

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
                    "id", "name", "address", "district", "lng", "lat",
                    "type", "tel", "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        """验证名称有效性"""
        if not name:
            return False
        invalid = ['undefined', 'null', 'object', '<', '>', 'function']
        for p in invalid:
            if p in name:
                return False
        if len(name) < 3 or len(name) > 100:
            return False
        return True

    def save_poi(self, poi: Dict) -> bool:
        """保存POI数据"""
        name = poi.get("name", "").strip()
        name = re.sub(r'\s+', ' ', name)

        if not self.is_valid_name(name):
            return False

        # 排除丰巢快递柜
        if "丰巢" in name or "快递柜" in name:
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

    def search_web(self, keyword: str, page: int = 1) -> List[Dict]:
        """通过网页API搜索"""
        url = "https://www.amap.com/service/poisInfo"

        params = {
            "query": keyword,
            "qid": "",  # 不指定区域，使用query参数中的城市
            "s": "search_wb",  # 搜索来源
            "addr_poi_merge": "true",
            "is_search_by_shape": "false",
            "city": self.config["city_code"],
            "page": str(page),
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.amap.com/",
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            data = response.json()

            # 解析返回的POI列表
            pois = []
            if data.get("status") == "1" and "data" in data:
                for item in data["data"].get("poiList", []):
                    # 获取基本信息
                    poi_id = item.get("id", "")
                    name = item.get("name", "")

                    if not self.is_valid_name(name):
                        continue

                    # 解析位置
                    location = item.get("location", "")
                    lng, lat = "", ""
                    if location:
                        parts = location.split(",")
                        if len(parts) == 2:
                            lng, lat = parts

                    # 解析地址
                    address = item.get("address", "")

                    # 区域信息
                    district = item.get("districtname", "")

                    # 类型
                    type_name = item.get("type", "")

                    # 电话
                    tel = item.get("tel", "")

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

            return pois

        except Exception as e:
            print(f"  ! 请求失败: {e}")
            return []

    def run(self):
        """运行爬虫"""
        print("=" * 70)
        print("高德地图网页版 - 丰e足食售货机数据采集")
        print("=" * 70)

        print(f"\n城市: {self.config['city']}")
        print(f"关键词: {', '.join(self.config['keywords'])}\n")

        total_count = 0

        for keyword in self.config["keywords"]:
            print(f"\n[{keyword}]")

            # 翻页搜索
            for page in range(1, 11):  # 最多10页
                print(f"  第{page}页...", end=" ")

                pois = self.search_web(keyword, page)

                if not pois:
                    print("无更多数据")
                    break

                page_count = 0
                for poi in pois:
                    if self.save_poi(poi):
                        page_count += 1
                        if page_count <= 3:  # 只显示前3个
                            print(f"\n    ✓ {poi['name'][:40]}")

                total_count += page_count
                print(f"  (本页{page_count}条)")

                if page_count < 10:  # 如果一页少于10条，可能没有更多了
                    break

                time.sleep(0.5)

        print(f"\n{'=' * 70}")
        print(f"采集完成！共获取 {total_count} 条数据")
        print(f"数据保存在: {self.output_path}")


def main():
    scraper = AmapWebScraper(CONFIG)
    scraper.run()


if __name__ == "__main__":
    main()
