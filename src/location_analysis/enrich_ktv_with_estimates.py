"""
KTV数据增强 - 添加估算的评分和价格信息

基于以下行业规则估算:
- 人均消费根据区县和品牌档次估算
- 评分根据品牌和区域估算
- 套餐根据人均消费生成参考套餐

注意: 这是估算数据，仅用于研究参考，非真实商业数据

作者: UVM Research Team
"""

import csv
import json
import random
from pathlib import Path
from collections import defaultdict


# 品牌档次分类 (根据市场定位)
BRAND_TIERS = {
    # 高端品牌
    "温莎": {"tier": "高端", "base_price": 150, "base_rating": 4.5},
    "钱柜": {"tier": "高端", "base_price": 180, "base_rating": 4.6},
    "麦乐迪": {"tier": "高端", "base_price": 160, "base_rating": 4.4},

    # 中高端
    "魅KTV": {"tier": "中高端", "base_price": 120, "base_rating": 4.2},
    "纯K": {"tier": "中高端", "base_price": 110, "base_rating": 4.3},
    "星聚会": {"tier": "中高端", "base_price": 100, "base_rating": 4.2},

    # 中端
    "唱吧麦颂": {"tier": "中端", "base_price": 80, "base_rating": 4.0},
    "酷秀": {"tier": "中端", "base_price": 70, "base_rating": 3.9},
    "乐巢": {"tier": "中端", "base_price": 75, "base_rating": 3.8},
    "39度": {"tier": "中端", "base_price": 70, "base_rating": 3.8},

    # 其他
    "蓝调": {"tier": "中端", "base_price": 65, "base_rating": 3.7},
}

# 区县消费系数
DISTRICT_MULTIPLIERS = {
    "朝阳区": 1.3,
    "海淀区": 1.25,
    "东城区": 1.35,
    "西城区": 1.3,
    "丰台区": 1.0,
    "石景山区": 0.95,
    "通州区": 0.9,
    "昌平区": 0.85,
    "大兴区": 0.9,
    "顺义区": 0.95,
    "房山区": 0.8,
    "门头沟区": 0.8,
    "怀柔区": 0.75,
    "平谷区": 0.75,
    "密云区": 0.75,
    "延庆区": 0.75,
}

# 套餐模板
PACKAGE_TEMPLATES = {
    "高端": [
        {"name": "欢唱套餐", "hours": 4, "people": 2, "discount": 0.85},
        {"name": "商务套餐", "hours": 3, "people": 4, "discount": 0.8},
        {"name": "豪华包厢套餐", "hours": 5, "people": 6, "discount": 0.75},
        {"name": "下午茶欢唱", "hours": 4, "people": 2, "discount": 0.6},
        {"name": "午夜场套餐", "hours": 4, "people": 4, "discount": 0.7},
    ],
    "中高端": [
        {"name": "标准欢唱", "hours": 4, "people": 2, "discount": 0.8},
        {"name": "聚会套餐", "hours": 4, "people": 6, "discount": 0.75},
        {"name": "周末特惠", "hours": 5, "people": 4, "discount": 0.7},
        {"name": "日场优惠", "hours": 4, "people": 2, "discount": 0.6},
    ],
    "中端": [
        {"name": "超值欢唱", "hours": 4, "people": 2, "discount": 0.75},
        {"name": "学生优惠", "hours": 3, "people": 2, "discount": 0.6},
        {"name": "团购特惠", "hours": 4, "people": 4, "discount": 0.7},
        {"name": "白天场", "hours": 4, "people": 2, "discount": 0.55},
    ]
}


def detect_brand(name: str) -> str:
    """检测KTV品牌"""
    for brand in BRAND_TIERS:
        if brand in name:
            return brand
    return "其他"


def generate_packages(tier: str, avg_price: float, count: int = 3) -> list:
    """生成套餐信息"""
    templates = PACKAGE_TEMPLATES.get(tier, PACKAGE_TEMPLATES["中端"])
    packages = []

    for template in templates[:count]:
        base_price = avg_price * template["hours"] * template["people"]
        price = int(base_price * template["discount"])

        packages.append({
            "name": template["name"],
            "hours": template["hours"],
            "people": template["people"],
            "price": price,
            "original_price": int(base_price),
            "per_person": int(price / template["people"])
        })

    return packages


def enrich_ktv_data(input_file: Path, output_file: Path):
    """增强KTV数据"""

    enriched_data = []
    stats = defaultdict(int)

    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row.get('name', '')
            district = row.get('district', '')

            # 检测品牌
            brand = detect_brand(name)
            brand_info = BRAND_TIERS.get(brand, {"tier": "中端", "base_price": 60, "base_rating": 3.6})

            # 计算人均消费
            district_mult = DISTRICT_MULTIPLIERS.get(district, 1.0)
            base_price = brand_info["base_price"]
            avg_price = int(base_price * district_mult * random.uniform(0.9, 1.1))

            # 计算评分
            base_rating = brand_info["base_rating"]
            rating = round(base_rating + random.uniform(-0.3, 0.2), 1)
            rating = max(3.0, min(5.0, rating))

            # 生成评论数
            review_count = random.randint(50, 2000)

            # 生成套餐
            tier = brand_info["tier"]
            packages = generate_packages(tier, avg_price)

            # 价格等级
            if avg_price >= 120:
                price_level = "高"
            elif avg_price >= 80:
                price_level = "中"
            else:
                price_level = "低"

            enriched_row = {
                **row,
                "brand": brand,
                "tier": tier,
                "rating": rating,
                "review_count": review_count,
                "avg_price": avg_price,
                "price_level": price_level,
                "packages": json.dumps(packages, ensure_ascii=False),
                "package_count": len(packages),
                "estimated": "TRUE"
            }

            enriched_data.append(enriched_row)
            stats[district] += 1
            stats[tier] += 1

    # 写入增强数据
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "name", "address", "district", "lng", "lat",
            "type", "tel", "source", "crawl_time",
            "brand", "tier", "rating", "review_count", "avg_price",
            "price_level", "packages", "package_count", "estimated"
        ])
        writer.writeheader()
        writer.writerows(enriched_data)

    return enriched_data, stats


def main():
    input_file = Path("data/raw/ktv_pois_merged.csv")
    output_file = Path("data/raw/ktv_with_estimates.csv")

    if not input_file.exists():
        print(f"错误: 找不到输入文件 {input_file}")
        return

    print("=" * 70)
    print("KTV数据增强 - 添加估算评分和套餐")
    print("=" * 70)

    enriched_data, stats = enrich_ktv_data(input_file, output_file)

    # 统计
    tier_stats = {k: v for k, v in stats.items() if k in BRAND_TIERS.values() or k == "中端"}

    print(f"\n处理完成!")
    print(f"  输入: {input_file}")
    print(f"  输出: {output_file}")
    print(f"  记录数: {len(enriched_data)}")

    print(f"\n档次分布:")
    for tier, count in tier_stats.items():
        print(f"  {tier}: {count}家")

    # 示例数据
    print(f"\n示例数据 (前3条):")
    for i, row in enumerate(enriched_data[:3]):
        print(f"\n  [{i+1}] {row['name']}")
        print(f"      品牌: {row['brand']} | 档次: {row['tier']}")
        print(f"      评分: {row['rating']} | 评论: {row['review_count']} | 人均: ¥{row['avg_price']}")
        packages = json.loads(row['packages'])
        print(f"      套餐: {len(packages)}个")
        for pkg in packages[:2]:
            print(f"        - {pkg['name']}: ¥{pkg['price']} ({pkg['hours']}小时/{pkg['people']}人)")

    print("\n" + "=" * 70)
    print("⚠️  注意: 价格和评分数据为估算值，仅用于研究参考")
    print("=" * 70)


if __name__ == "__main__":
    main()
