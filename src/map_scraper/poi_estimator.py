"""
北京售货机数�� POI 推估脚本

核心思路：
1. 通过地图API获取各类场所POI数量（写字楼、地铁站、工厂等）
2. 根据合理的比例假设，推算这些场所可能放置的售货机数量
3. 输出推估结果和空间分布

作者: UVM Research Team
"""

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote

import aiohttp


# ==================== 配置 ====================
AMAP_API_KEY = "6dc3b2f659ec16fefe5016f0ad69ad25"
CITY = "北京"
OUTPUT_DIR = Path("data/estimation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==================== 场所类型定义 ====================
# 每类场所的搜索关键词和假设的售货机配置比例
VENUE_TYPES = {
    "写字楼": {
        "keywords": ["写字楼", "商务楼", "办公楼", "SOHO", "科技园", "产业园"],
        "machines_per_venue": 2.0,  # 每栋写字楼平均2台（大堂+茶水间）
        "confidence": "中",  # 置信度
        "notes": "大型写字楼可能更多，小型可能没有"
    },
    "地铁站": {
        "keywords": ["地铁站", "地铁口"],
        "machines_per_venue": 3.0,  # 每个地铁站平均3台（各个出口）
        "confidence": "高",
        "notes": "每个站厅和通道都有"
    },
    "住宅小区": {
        "keywords": ["小区", "家园", "公寓", "社区"],
        "machines_per_venue": 0.3,  # 每个小区30%概率有售货机
        "confidence": "中",
        "notes": "大型小区可能有，小型没有"
    },
    "工厂园区": {
        "keywords": ["工厂", "工业园", "制造", "加工厂", "车间"],
        "machines_per_venue": 2.5,  # 每个工厂平均2.5台
        "confidence": "中",
        "notes": "工厂通常有多���"
    },
    "高校": {
        "keywords": ["大学", "学院", "高校", "学校"],
        "machines_per_venue": 5.0,  # 每所大学平均5台
        "confidence": "高",
        "notes": "宿舍楼、教学楼、图书馆都有"
    },
    "医院": {
        "keywords": ["医院", "诊所", "卫生院"],
        "machines_per_venue": 2.0,  # 每个医院平均2台
        "confidence": "中",
        "notes": "门诊大厅、住院部"
    },
    "商场": {
        "keywords": ["商场", "购物中心", "百货", "奥特莱斯"],
        "machines_per_venue": 3.0,  # 每个商场平均3台
        "confidence": "高",
        "notes": "各楼层、电影院旁"
    },
    "酒店": {
        "keywords": ["酒店", "宾馆", "旅馆"],
        "machines_per_venue": 1.0,  # 每个酒店平均1台
        "confidence": "中",
        "notes": "大堂或楼层"
    },
    "交通枢纽": {
        "keywords": ["机场", "火车站", "客运站", "公交枢纽"],
        "machines_per_venue": 10.0,  # 大型交通枢纽平均10台
        "confidence": "高",
        "notes": "值机区、候车区、到达区"
    },
}

# 北京各区列表
DISTRICTS = [
    "朝阳区", "海淀区", "东城区", "西城区",
    "丰台区", "石景山区", "通州区", "昌平区",
    "大兴区", "顺义区", "房山区", "门头沟区",
    "平谷区", "怀柔区", "密云区", "延庆区"
]


# ==================== 高德地图API ====================
class AmapAPI:
    """高德地图API封装"""

    BASE_URL = "https://restapi.amap.com/v3/place/text"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def search(self, keywords: str, region: str = "北京") -> Dict:
        """
        搜索POI，返回总数

        注意：高德API返回的count是估算总数，可能大于实际可获取的数量
        """
        params = {
            "key": self.api_key,
            "keywords": keywords,
            "city": region,
            "offset": 1,  # 每页数量，最少1
            "page": 1,  # 第一页
        }

        try:
            async with self.session.get(
                self.BASE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

                if data.get("status") == "1":
                    count = int(data.get("count", 0))
                    return {
                        "keywords": keywords,
                        "region": region,
                        "count": count,
                        "success": True
                    }
                else:
                    return {
                        "keywords": keywords,
                        "region": region,
                        "count": 0,
                        "success": False,
                        "error": data.get("info", "Unknown")
                    }
        except Exception as e:
            return {
                "keywords": keywords,
                "region": region,
                "count": 0,
                "success": False,
                "error": str(e)
            }


# ==================== 推估计算器 ====================
class VendingMachineEstimator:
    """售货机数量推估计算器"""

    def __init__(self):
        self.results = {}
        self.district_data = {d: {} for d in DISTRICTS}

    async def collect_poi_counts(self, api: AmapAPI):
        """收集所有场所类型的POI数量"""
        print("\n" + "=" * 60)
        print("开始收集POI数据...")
        print("=" * 60)

        for venue_type, config in VENUE_TYPES.items():
            print(f"\n[{venue_type}]")

            total_count = 0
            keyword_counts = []

            # 先全市搜索
            for keyword in config["keywords"]:
                result = await api.search(keyword, CITY)
                if result["success"]:
                    count = result["count"]
                    total_count += count
                    keyword_counts.append((keyword, count))
                    print(f"  {keyword}: {count:,} 个")

                    # 延迟避免限流
                    await asyncio.sleep(0.3)

            # 去重处理：同一类型的关键词可能有重叠
            # 保守估计，取最大的那个作为基数
            if keyword_counts:
                max_count = max(c for _, c in keyword_counts)
                # 其他关键词补充20%（考虑覆盖不全的情况）
                estimated_total = int(max_count * 1.2)
            else:
                estimated_total = 0

            self.results[venue_type] = {
                "poi_count": estimated_total,
                "machines_per_venue": config["machines_per_venue"],
                "estimated_machines": int(estimated_total * config["machines_per_venue"]),
                "confidence": config["confidence"],
                "notes": config["notes"],
                "keyword_details": keyword_counts
            }

            print(f"  → 估算场所数: {estimated_total:,}")
            print(f"  → 估算售货机: {int(estimated_total * config['machines_per_venue']):,} 台")

    async def collect_district_data(self, api: AmapAPI):
        """收集各区数据，用于空间分布分析"""
        print("\n" + "=" * 60)
        print("收集各区POI数据（空间分布分析）...")
        print("=" * 60)

        # 只选择几个关键类型做区域分析
        key_types = ["写字楼", "地铁站", "住宅小区", "商场"]

        for district in DISTRICTS:
            print(f"\n[{district}]", end="", flush=True)

            for venue_type in key_types:
                keywords = VENUE_TYPES[venue_type]["keywords"][0]  # 取第一个关键词
                result = await api.search(keywords, district)

                if result["success"]:
                    self.district_data[district][venue_type] = result["count"]
                    print(f" {venue_type}:{result['count']}", end="", flush=True)

                await asyncio.sleep(0.2)

    def calculate_estimation(self):
        """计算最终推估结果"""
        print("\n" + "=" * 60)
        print("推估结果汇总")
        print("=" * 60)

        total_machines = 0
        total_venues = 0

        print(f"\n{'场所类型':<12} {'场所数':>10} {'台/场所':>8} {'推估售货机':>12} {'置信度':<6}")
        print("-" * 60)

        for venue_type, data in self.results.items():
            venues = data["poi_count"]
            ratio = data["machines_per_venue"]
            machines = data["estimated_machines"]
            confidence = data["confidence"]

            print(f"{venue_type:<12} {venues:>10,} {ratio:>8.1f} {machines:>12,} {confidence:<6}")

            total_venues += venues
            total_machines += machines

        print("-" * 60)
        print(f"{'合计':<12} {total_venues:>10,} {'':>8} {total_machines:>12,}")
        print("\n" + "=" * 60)

        # 考虑重复计算后的调整
        print("\n推估说明:")
        print("  1. 上述结果可能存在重复计算（如商场内的写字楼）")
        print("  2. 实际数量建议按 70-80% 折扣率计算")

        discount = 0.75  # 75%折扣率
        adjusted_total = int(total_machines * discount)

        print(f"\n  原始推估: {total_machines:,} 台")
        print(f"  折扣率: {discount*100}%")
        print(f"  调整后推估: {adjusted_total:,} 台")

        return {
            "raw_total": total_machines,
            "adjusted_total": adjusted_total,
            "discount_rate": discount
        }

    def save_results(self, estimation: Dict):
        """保存推估结果到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. 保存详细JSON
        json_data = {
            "timestamp": timestamp,
            "city": CITY,
            "estimation": estimation,
            "venue_details": self.results,
            "district_data": self.district_data
        }

        json_file = OUTPUT_DIR / f"estimation_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # 2. 保存各区分布CSV
        csv_file = OUTPUT_DIR / f"distribution_{timestamp}.csv"
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["区域", "写字楼", "地铁站", "住宅小区", "商场", "推估售货机数"])

            for district, data in self.district_data.items():
                if data:
                    offices = data.get("写字楼", 0)
                    subways = data.get("地铁站", 0)
                    residential = data.get("住宅小区", 0)
                    malls = data.get("商场", 0)

                    # 简单推估公式
                    district_machines = int(
                        offices * 2.0 +
                        subways * 3.0 +
                        residential * 0.3 +
                        malls * 3.0
                    )

                    writer.writerow([district, offices, subways, residential, malls, district_machines])

        # 3. 保存汇总报告
        report_file = OUTPUT_DIR / f"report_{timestamp}.txt"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("北京自动售货机数量 POI 推估报告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"数据来源: 高德地图API\n\n")

            f.write("推估方法说明:\n")
            f.write("-" * 40 + "\n")
            f.write("通过各类场所POI数量，结合合理的配置比例假设，\n")
            f.write("推算北京地区可能的自动售货机总量。\n\n")

            f.write("各类场所推估:\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'场所类型':<12} {'场所数':>10} {'台/场所':>8} {'推估售货机':>12}\n")
            f.write("-" * 40 + "\n")
            for venue_type, data in self.results.items():
                f.write(f"{venue_type:<12} {data['poi_count']:>10,} "
                       f"{data['machines_per_venue']:>8.1f} {data['estimated_machines']:>12,}\n")

            f.write("-" * 40 + "\n")
            f.write(f"{'合计':<12} {sum(v['poi_count'] for v in self.results.values()):>10,} "
                   f"{'':>8} {estimation['raw_total']:>12,}\n\n")

            f.write("推估结论:\n")
            f.write("-" * 40 + "\n")
            f.write(f"  原始推估总量: {estimation['raw_total']:,} 台\n")
            f.write(f"  考虑重复等因素，按 {estimation['discount_rate']*100:.0f}% 折扣率调整\n")
            f.write(f"  最终推估数量: {estimation['adjusted_total']:,} 台\n\n")

            f.write("数据说明:\n")
            f.write("-" * 40 + "\n")
            f.write("1. 此数据为基于POI的推估值，非真实统计数据\n")
            f.write("2. 实际数量受多种因素影响，可能与推估值有差异\n")
            f.write("3. 置信度\"高\"表示假设相对可靠，\"中\"表示存在较大不确定性\n")
            f.write("4. 如需更准确数据，建议进行实地抽样验证\n\n")

            f.write("=" * 60 + "\n")

        print(f"\n结果已保存:")
        print(f"  - 详细数据: {json_file}")
        print(f"  - 区域分布: {csv_file}")
        print(f"  - 推估报告: {report_file}")


# ==================== 主程序 ====================
async def main():
    print("=" * 60)
    print("北京自动售货机数量 POI 推估工具")
    print("=" * 60)

    estimator = VendingMachineEstimator()

    async with AmapAPI(AMAP_API_KEY) as api:
        # 收集全市各类场所POI数量
        await estimator.collect_poi_counts(api)

        # 收集各区数据（用于空间分布）
        await estimator.collect_district_data(api)

        # 计算推估结果
        estimation = estimator.calculate_estimation()

        # 保存结果
        estimator.save_results(estimation)

    print("\n" + "=" * 60)
    print("推估完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
