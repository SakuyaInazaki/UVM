"""
通过高德地图API采集丰e足食售货机位置

丰e足食是顺丰孵化的无人零售品牌，在高德地图上有大量POI数据

作者: UVM Research Team
"""

import asyncio
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests


CONFIG = {
    "keywords": [
        "丰e足食",
        "丰e足食智能柜",
        "顺丰售货机",
        "自动售货机",
        "无人售货",
        "智能售货",
    ],
    "city": "北京",
    "output_dir": "data/raw",
    "output_file": "fenge_zushi_amap.csv",
    "max_pages": 10,  # 每个关键词最多翻页数
}


class AmapFengEScraper:
    """高德地图丰e足食爬虫"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self._init_csv()

        # 使用现有的高德API key（从之前的代码中读取）
        self.amap_key = self._get_amap_key()

    def _get_amap_key(self) -> str:
        """获取高德API key"""
        # 从 vending_scraper.py 读取已有的key
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
                    "type", "distance", "tel", "source", "crawl_time"
                ])
            print(f"✓ 创建文件: {self.output_path}")

    def is_valid_name(self, name: str) -> bool:
        """验证名称有效性"""
        if not name:
            return False
        invalid = ['undefined', 'null', 'object', '<', '>']
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
        if "丰巢" in name:
            return False

        # 对于非"丰"相关的名称，检查是否是售货机相关的
        if not any(k in name for k in ["丰", "feng", "Feng"]):
            # 检查类型是否是售货机相关
            poi_type = poi.get("type", "").lower()
            if "售货" not in poi_type and "vending" not in poi_type.lower():
                # 如果类型也不匹配，检查地址是否有售货机相关关键词
                address = poi.get("address", "")
                if not any(k in address for k in ["售货", "vending", "自动", "无人", "智能柜"]):
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
                poi.get("distance", ""),
                poi.get("tel", ""),
                "高德地图",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        return True

    def search_keyword(self, keyword: str, page: int = 1) -> Dict:
        """搜索关键词"""
        if not self.amap_key:
            print("  ! 未找到高德API key")
            return {}

        url = "https://restapi.amap.com/v5/place/text"

        params = {
            "key": self.amap_key,
            "keywords": keyword,
            "city": self.config["city"],
            "city_limit": "true",
            "page_size": "50",
            "page_num": str(page - 1),  # 高德从0开始
            "show_fields": "business,photos,children"
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            return response.json()
        except Exception as e:
            print(f"  ! 请求失败: {e}")
            return {}

    def parse_pois(self, data: Dict) -> List[Dict]:
        """解析POI数据"""
        pois = []

        try:
            for item in data.get("pois", []):
                # 解析基本信息
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
                pcode = item.get("pcode", "")  # 省代码
                cityname = item.get("cityname", "")  # 市
                adname = item.get("adname", "")  # 区

                district = ""
                if cityname:
                    district = cityname
                if adname:
                    district += adname if district else adname

                # 获取详细信息
                poi_id = item.get("id", "")

                # 评分和距离
                distance = item.get("distance", "")

                # 电话
                tel = item.get("tel", "")

                # 类型
                type_name = item.get("type", "")

                pois.append({
                    "id": poi_id,
                    "name": name,
                    "address": address,
                    "district": district,
                    "lng": lng,
                    "lat": lat,
                    "distance": distance,
                    "tel": tel,
                    "type": type_name
                })

        except Exception as e:
            print(f"    解析失败: {e}")

        return pois

    def run(self):
        """运行爬虫"""
        print("=" * 70)
        print("高德地图 - 丰e足食售货机数据采集")
        print("=" * 70)

        if not self.amap_key:
            print("\n错误: 未找到高德API key")
            print("请先配置 src/map_scraper/config.py 中的 AMAP_KEY")
            return

        print(f"\n城市: {self.config['city']}")
        print(f"关键词: {', '.join(self.config['keywords'])}\n")

        total_count = 0

        for keyword in self.config["keywords"]:
            print(f"\n[{keyword}]")

            for page in range(1, self.config["max_pages"] + 1):
                print(f"  第{page}页...", end=" ")

                data = self.search_keyword(keyword, page)

                if not data:
                    print("无结果")
                    break

                count = int(data.get("count", 0))
                pois = self.parse_pois(data)

                if not pois:
                    print("无更多数据")
                    break

                page_count = 0
                for poi in pois:
                    if self.save_poi(poi):
                        page_count += 1
                        print(f"\n    ✓ {poi['name'][:40]}")

                total_count += page_count
                print(f"  (本页{page_count}条)")

                # 检查是否还有更多
                if count <= page * 50:
                    break

                time.sleep(0.5)  # 避免请求过快

        print(f"\n{'=' * 70}")
        print(f"采集完成！共获取 {total_count} 条数据")
        print(f"数据保存在: {self.output_path}")


def main():
    scraper = AmapFengEScraper(CONFIG)
    scraper.run()


if __name__ == "__main__":
    main()
