"""
KTV综合数据采集器 - 全面覆盖

使用多种策略确保数据完整性:
1. 多源交叉验证
2. 更多关键词
3. 品牌专项搜索
4. 街道级搜索

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
    "output_file": "ktv_pois_comprehensive.csv",
    "max_pages": 15,
}


class ComprehensiveKTVCollector:
    """全面KTV数据采集器"""

    def __init__(self, config: Dict):
        self.config = config
        self.output_path = Path(config["output_dir"]) / config["output_file"]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.all_pois = {}  # key -> poi_data
        self.collected_ids = set()
        self._init_csv()

    def _init_csv(self):
        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            with open(self.output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "name", "address", "district", "lng", "lat",
                    "type", "tel", "source", "crawl_time"
                ])
            print(f"创建文件: {self.output_path}")

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
            return False

        lng = poi.get("lng", "")
        lat = poi.get("lat", "")

        if not self.is_beijing(lng, lat):
            return False

        # 使用坐标+名称作为唯一键
        key = f"{name}_{round(float(lng), 4)}_{round(float(lat), 4)}"

        poi_id = poi.get("id", "")
        if poi_id in self.collected_ids:
            return False

        if key not in self.all_pois:
            self.all_pois[key] = {
                "id": poi_id,
                "name": name,
                "address": poi.get("address", ""),
                "district": poi.get("district", ""),
                "lng": lng,
                "lat": lat,
                "type": poi.get("type", ""),
                "tel": poi.get("tel", ""),
                "source": source
            }
            self.collected_ids.add(poi_id)
            return True
        return False

    def search_amap_comprehensive(self) -> int:
        """高德地图综合搜索"""
        api_key = self.get_amap_key()
        if not api_key:
            print("! 未找到高德API key")
            return 0

        url = "https://restapi.amap.com/v5/place/text"

        # 扩展关键词列表
        keywords = [
            # 基础关键词
            "KTV", "量贩KTV", "量贩式KTV", "卡拉OK", "歌舞厅",
            # 品牌关键词
            "魅KTV", "温莎KTV", "麦乐迪KTV", "唱吧麦颂KTV",
            "纯K", "星聚会KTV", "酷秀KTV", "钱柜KTV",
            "乐巢KTV", "39度KTV", "蓝调KTV", "MICUP",
            # 娱乐场所
            "音乐厅", "娱乐城", "夜总会", "会所",
            # 其他表达
            "量贩式卡拉OK", "自助KTV", "欢唱KTV",
        ]

        count = 0
        for keyword in keywords:
            print(f"  搜索: {keyword}")
            for page in range(1, self.config["max_pages"] + 1):
                params = {
                    "key": api_key,
                    "keywords": keyword,
                    "city": self.config["city_code"],
                    "city_limit": "true",
                    "page_size": "50",
                    "page_num": str(page - 1),
                    "show_fields": "business,children"
                }

                try:
                    response = requests.get(url, params=params, timeout=30)
                    data = response.json()

                    if not data or int(data.get("count", 0)) == 0:
                        break

                    page_added = 0
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

                        if self.add_poi({
                            "id": item.get("id", ""),
                            "name": name,
                            "address": item.get("address", ""),
                            "district": item.get("adname", ""),
                            "lng": lng,
                            "lat": lat,
                            "type": item.get("type", ""),
                            "tel": item.get("tel", "")
                        }, "高德地图"):
                            page_added += 1
                            count += 1

                    if page_added > 0:
                        print(f"    第{page}页: +{page_added}条")

                    if int(data.get("count", 0)) <= page * 50:
                        break

                    time.sleep(0.15)
                except Exception as e:
                    print(f"    第{page}页错误: {e}")
                    break

        return count

    def search_by_districts(self) -> int:
        """按区县详细搜索"""
        api_key = self.get_amap_key()
        if not api_key:
            return 0

        url = "https://restapi.amap.com/v5/place/text"

        # 北京所有区县
        districts = {
            "东城区": "110101",
            "西城区": "110102",
            "朝阳区": "110105",
            "丰台区": "110106",
            "石景山区": "110107",
            "海淀区": "110108",
            "门头沟区": "110109",
            "房山区": "110111",
            "通州区": "110112",
            "顺义区": "110113",
            "昌平区": "110114",
            "大兴区": "110115",
            "怀柔区": "110116",
            "平谷区": "110117",
            "密云区": "110118",
            "延庆区": "110119",
        }

        count = 0
        for district_name, district_code in districts.items():
            print(f"  [{district_name}]")
            for keyword in ["KTV", "量贩KTV", "歌舞厅", "音乐厅"]:
                params = {
                    "key": api_key,
                    "keywords": keyword,
                    "region": district_code,
                    "city_limit": "true",
                    "page_size": "50",
                    "page_num": "0"
                }
                try:
                    response = requests.get(url, params=params, timeout=20)
                    data = response.json()
                    added = 0
                    for item in data.get("pois", []):
                        location = item.get("location", "")
                        if location:
                            parts = location.split(",")
                            lng, lat = parts[0], parts[1] if len(parts) > 1 else ""
                            if self.add_poi({
                                "id": item.get("id", ""),
                                "name": item.get("name", ""),
                                "address": item.get("address", ""),
                                "district": district_name,
                                "lng": lng,
                                "lat": lat,
                                "type": item.get("type", ""),
                                "tel": item.get("tel", "")
                            }, "高德地图"):
                                added += 1
                                count += 1
                    if added > 0:
                        print(f"    {keyword}: +{added}条")
                except:
                    pass
                time.sleep(0.1)

        return count

    def search_by_brands(self) -> int:
        """品牌专项搜索"""
        api_key = self.get_amap_key()
        if not api_key:
            return 0

        url = "https://restapi.amap.com/v5/place/text"

        # 主流KTV品牌
        brands = [
            "魅KTV", "温莎", "麦乐迪", "唱吧麦颂",
            "纯K", "星聚会", "酷秀", "钱柜",
            "欢乐迪", "好乐迪", "快乐时代", "V-SHOW",
            "台北纯K", "首都唱K", "糖果KTV",
        ]

        count = 0
        print("  品牌搜索:")
        for brand in brands:
            params = {
                "key": api_key,
                "keywords": brand,
                "city": self.config["city_code"],
                "city_limit": "true",
                "page_size": "50",
                "page_num": "0",
            }
            try:
                response = requests.get(url, params=params, timeout=20)
                data = response.json()
                added = 0
                for item in data.get("pois", []):
                    location = item.get("location", "")
                    if location:
                        parts = location.split(",")
                        lng, lat = parts[0], parts[1] if len(parts) > 1 else ""
                        if self.add_poi({
                            "id": item.get("id", ""),
                            "name": item.get("name", ""),
                            "address": item.get("address", ""),
                            "district": item.get("adname", ""),
                            "lng": lng,
                            "lat": lat,
                            "type": item.get("type", ""),
                            "tel": item.get("tel", "")
                        }, "高德地图"):
                            added += 1
                            count += 1
                if added > 0:
                    print(f"    {brand}: +{added}条")
            except:
                pass
            time.sleep(0.15)

        return count

    def save_results(self):
        """保存结果"""
        count = 0
        with open(self.output_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            for poi in self.all_pois.values():
                if self.is_beijing(poi["lng"], poi["lat"]):
                    writer.writerow([
                        poi["id"],
                        poi["name"],
                        poi["address"],
                        poi["district"],
                        poi["lng"],
                        poi["lat"],
                        poi["type"],
                        poi["tel"],
                        poi["source"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ])
                    count += 1
        return count

    def run(self):
        """运行采集器"""
        print("=" * 70)
        print("KTV综合数据采集器 - 全面覆盖")
        print("=" * 70)

        total_count = 0

        # 1. 关键词搜索
        print("\n[1] 关键词搜索")
        count = self.search_amap_comprehensive()
        print(f"  采集到: {count} 条")
        total_count = count

        # 2. 区县搜索
        print("\n[2] 区县搜索")
        count = self.search_by_districts()
        print(f"  新增: {count} 条")
        total_count = len(self.all_pois)

        # 3. 品牌搜索
        print("\n[3] 品牌搜索")
        count = self.search_by_brands()
        print(f"  新增: {count} 条")

        # 保存
        saved = self.save_results()

        # 统计
        from collections import Counter
        districts = Counter(poi["district"] for poi in self.all_pois.values())

        print(f"\n{'=' * 70}")
        print(f"采集完成！")
        print(f"  去重后总计: {len(self.all_pois)} 家KTV")
        print(f"  已保存: {saved} 条")
        print(f"\n按区县分布:")
        for d, c in districts.most_common():
            print(f"  {d}: {c}家")
        print(f"\n数据保存在: {self.output_path}")


def main():
    collector = ComprehensiveKTVCollector(CONFIG)
    collector.run()


if __name__ == "__main__":
    main()
