"""
POI数据清洗工具

清洗爬取的POI数据，过滤掉便利店等无关数据，保留真正的自动售货机数据

作者: UVM Research Team
"""

import csv
import re
from pathlib import Path
from typing import List, Set, Tuple


# 便利店/超市关键词 - 这些将被过滤掉
CONVENIENCE_STORE_KEYWORDS = {
    # 便利店品牌
    "便利店", "7-11", "711", "全家", "familymart", "罗森", "lawson",
    "物美", "便利蜂", "喜士多", "ok便利店", "快客", "十足", "京客隆",
    "超市发", "好邻居", "顺天府",

    # 超市/卖场
    "超市", "卖场", "购物中心", "百货", "大悦城", "万达", "凯德",
    "永辉", "华润", "家乐福", "沃尔玛", "盒马", "山姆",

    # 通用
    "便利", "超市", "商场"
}

# 自动售货机相关关键词 - 这些将被保留
VENDING_MACHINE_KEYWORDS = {
    "售货机", "贩卖机", "无人售货", "自动售货",
    "友宝", "ubox", "u-box", "u-box", "丰e足食", "丰翼",
    "成人用品", "情趣用品"
}

# 无关数据关键词
INVALID_KEYWORDS = {
    "京ICP", "备案", "举报", "协议", "声明", "隐私", "服务条款",
    "账号", "密码", "help", "www", "http", "https", "://",
    "class=", "data-", "transform", "none;", "<script"
}


def is_vending_machine(name: str, address: str = "", category: str = "") -> Tuple[bool, str]:
    """
    判断是否为自动售货机

    Returns:
        (is_vending, reason): 是否为售货机及原因
    """
    if not name:
        return False, "空名称"

    name_lower = name.lower().strip()

    # 检查无效数据
    for invalid in INVALID_KEYWORDS:
        if invalid in name_lower:
            return False, f"无效关键词: {invalid}"

    # 检查是否包含便利店关键词
    for store in CONVENIENCE_STORE_KEYWORDS:
        if store.lower() in name_lower:
            return False, f"便利店: {store}"

    # 检查是否包含售货机关键词
    for kw in VENDING_MACHINE_KEYWORDS:
        if kw.lower() in name_lower:
            return True, "售货机关键词"

    # 额外检查: 如果地址或分类包含相关信息
    combined = f"{name} {address} {category}".lower()
    for kw in VENDING_MACHINE_KEYWORDS:
        if kw.lower() in combined:
            return True, "地址/分类包含售货机"

    return False, "无售货机特征"


def clean_csv_file(input_file: Path, output_file: Path) -> dict:
    """
    清洗CSV文件

    Returns:
        统计信息
    """
    kept_rows = []
    removed_rows = []
    removal_reasons: dict = {}

    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        for row in reader:
            name = row.get('name', '') or row.get('title', '')
            address = row.get('address', '')
            category = row.get('category', '') or row.get('keyword', '')

            is_vending, reason = is_vending_machine(name, address, category)

            if is_vending:
                kept_rows.append(row)
            else:
                removed_rows.append(row)
                removal_reasons[reason] = removal_reasons.get(reason, 0) + 1

    # 写入清洗后的数据
    if output_file.exists():
        output_file.unlink()

    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(kept_rows)

    return {
        "total": len(kept_rows) + len(removed_rows),
        "kept": len(kept_rows),
        "removed": len(removed_rows),
        "reasons": removal_reasons
    }


def main():
    """主函数"""
    base_path = Path("data/raw")

    # 输入文件
    input_files = [
        base_path / "merged_pois.csv",
        base_path / "amap_pois.csv",
        base_path / "grid_pois.csv",
    ]

    # 输出文件
    output_file = base_path / "vending_machines_cleaned.csv"

    print("=" * 60)
    print("POI数据清洗工具")
    print("=" * 60)

    all_data = []
    headers = ["uid", "name", "address", "keyword", "city", "crawl_time"]

    # 读取所有文件
    for file_path in input_files:
        if not file_path.exists():
            print(f"⚠️ 文件不存在: {file_path}")
            continue

        print(f"\n📂 读取: {file_path.name}")
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or headers
                for row in reader:
                    all_data.append(row)
                print(f"   读取 {len(list(reader))} 条")
        except Exception as e:
            print(f"   ❌ 错误: {e}")

    if not all_data:
        print("\n⚠️ 没有数据可处理")
        return

    print(f"\n📊 总共读取 {len(all_data)} 条数据")

    # 过滤数据
    kept = []
    removal_reasons: dict = {}

    for row in all_data:
        name = row.get('name', '') or row.get('title', '')
        address = row.get('address', '')
        category = row.get('category', '') or row.get('keyword', '')

        is_vending, reason = is_vending_machine(name, address, category)

        if is_vending:
            kept.append(row)
        else:
            removal_reasons[reason] = removal_reasons.get(reason, 0) + 1

    # 写入结果
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(kept)

    # 输出统计
    print("\n" + "=" * 60)
    print("清洗结果:")
    print(f"  原始数据: {len(all_data)} 条")
    print(f"  保留数据: {len(kept)} 条")
    print(f"  过滤数据: {len(all_data) - len(kept)} 条")
    print(f"\n过滤原因统计:")
    for reason, count in sorted(removal_reasons.items(), key=lambda x: -x[1]):
        print(f"  - {reason}: {count} 条")
    print(f"\n✓ 清洗后数据保存在: {output_file}")
    print("=" * 60)

    # 显示一些保留的样本
    if kept:
        print("\n保留的样本数据:")
        for i, row in enumerate(kept[:10]):
            name = row.get('name', '') or row.get('title', '')
            print(f"  {i+1}. {name}")


if __name__ == "__main__":
    main()
