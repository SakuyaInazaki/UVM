"""
KTV数据清洗和去重
"""

import csv
from pathlib import Path
from collections import defaultdict


def clean_ktv_data():
    """清洗和去重KTV数据"""
    input_file = Path("data/raw/ktv_pois.csv")
    output_file = Path("data/raw/ktv_pois_clean.csv")

    # 读取所有数据
    all_data = []
    seen = {}  # (name, lat, lng) -> record

    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get('lat', 0))
                lng = float(row.get('lng', 0))
                name = row.get('name', '').strip()

                # 筛选北京范围内的数据
                if 39 < lat < 41 and 115 < lng < 118 and name:
                    key = (name, round(lng, 6), round(lat, 6))
                    if key not in seen:
                        seen[key] = row
                        all_data.append(row)
                    else:
                        # 如果重复，保留信息更完整的
                        existing = seen[key]
                        if not existing.get('tel') and row.get('tel'):
                            seen[key] = row
            except:
                pass

    # 按名称去重（保留第一条记录）
    final_data = []
    seen_names = set()
    for row in all_data:
        name = row.get('name', '').strip()
        if name and name not in seen_names:
            seen_names.add(name)
            final_data.append(row)

    # 写入清洗后的数据
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "name", "address", "district", "lng", "lat",
            "type", "tel", "source", "crawl_time"
        ])
        for row in final_data:
            writer.writerow([
                row.get('id', ''),
                row.get('name', ''),
                row.get('address', ''),
                row.get('district', ''),
                row.get('lng', ''),
                row.get('lat', ''),
                row.get('type', ''),
                row.get('tel', ''),
                row.get('source', ''),
                row.get('crawl_time', '')
            ])

    # 统计
    from collections import Counter
    districts = Counter(r.get('district', '未知') for r in final_data)

    print("=" * 70)
    print("KTV数据清洗结果")
    print("=" * 70)
    print(f"\n原始数据: {len(all_data)} 条")
    print(f"去重后: {len(final_data)} 家")
    print(f"\n按区县分布:")
    for d, c in districts.most_common():
        print(f"  {d}: {c}家")

    print(f"\n数据已保存至: {output_file}")
    print("=" * 70)

    return final_data


if __name__ == "__main__":
    clean_ktv_data()
