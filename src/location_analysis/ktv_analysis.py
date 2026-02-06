"""
KTV数据清洗与分析

1. 筛选北京的KTV
2. 进行空间统计分析
3. 分析与设施的相关性

作者: UVM Research Team
"""

import csv
import math
from pathlib import Path
from typing import List, Dict


class Point:
    """简单的点类"""
    def __init__(self, lng: float, lat: float):
        self.lng = lng
        self.lat = lat

    def distance_deg(self, other: 'Point') -> float:
        """计算到另一个点的距离（度）"""
        return math.sqrt((self.lng - other.lng)**2 + (self.lat - other.lat)**2)

    def distance_m(self, other: 'Point') -> float:
        """计算到另一个点的距离（米，近似）"""
        return self.distance_deg(other) * 111000


def load_ktv_data(filepath: str) -> List[Dict]:
    """加载KTV数据"""
    ktvs = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get('lat', 0))
                lng = float(row.get('lng', 0))
                if 39 < lat < 41 and 115 < lng < 118:  # 北京范围
                    ktvs.append({
                        'id': row.get('id', ''),
                        'name': row.get('name', ''),
                        'address': row.get('address', ''),
                        'district': row.get('district', ''),
                        'lat': lat,
                        'lng': lng,
                        'point': Point(lng, lat)
                    })
            except (ValueError, TypeError):
                continue
    return ktvs


def load_facilities() -> Dict[str, List[Dict]]:
    """加载设施数据"""
    data_dir = Path("data/location_analysis/raw")
    facilities = {}

    for file in data_dir.glob("facility_*.csv"):
        parts = file.stem.split("_")
        if len(parts) >= 3:
            facility_type = "_".join(parts[1:-1])

            facility_points = []
            with open(file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        lat = float(row.get('lat', 0))
                        lng = float(row.get('lng', 0))
                        if lat and lng:
                            facility_points.append({
                                'name': row.get('name', ''),
                                'lat': lat,
                                'lng': lng,
                                'point': Point(lng, lat)
                            })
                    except (ValueError, TypeError):
                        continue

            if facility_points:
                facilities[facility_type] = facility_points

    return facilities


def nearest_neighbor_analysis(ktvs: List[Dict]) -> Dict:
    """最近邻分析"""
    n = len(ktvs)
    if n < 2:
        return {}

    # 计算每个点到最近邻的距离
    distances = []
    for i, ktv1 in enumerate(ktvs):
        min_dist = float('inf')
        for j, ktv2 in enumerate(ktvs):
            if i != j:
                dist = ktv1['point'].distance_m(ktv2['point'])
                if dist < min_dist:
                    min_dist = dist
        distances.append(min_dist)

    avg_distance = sum(distances) / n
    min_distance = min(distances)
    max_distance = max(distances)

    # 排序后计算分位数
    distances.sort()
    p25 = distances[int(n * 0.25)]
    p50 = distances[int(n * 0.5)]  # 中位数
    p75 = distances[int(n * 0.75)]

    # 计算研究区域的面积（近似）
    lats = [k['lat'] for k in ktvs]
    lngs = [k['lng'] for k in ktvs]
    lat_range = max(lats) - min(lats)
    lng_range = max(lngs) - min(lngs)
    area_deg2 = lat_range * lng_range
    area_m2 = area_deg2 * (111000 ** 2)

    # 理论平均最近邻距离
    expected_avg = math.sqrt(area_m2 / (2 * n)) if n > 0 else 0

    # R比值
    r_ratio = avg_distance / expected_avg if expected_avg > 0 else 0

    # 解释
    if r_ratio < 0.5:
        interpretation = "强聚类分布"
    elif r_ratio < 0.8:
        interpretation = "聚类分布"
    elif r_ratio < 1.2:
        interpretation = "随机分布"
    elif r_ratio < 1.5:
        interpretation = "离散分布"
    else:
        interpretation = "强离散分布"

    return {
        'count': n,
        'avg_nearest_distance': avg_distance,
        'min_nearest_distance': min_distance,
        'max_nearest_distance': max_distance,
        'p25': p25,
        'p50': p50,
        'p75': p75,
        'expected_avg': expected_avg,
        'r_ratio': r_ratio,
        'interpretation': interpretation,
        'area_m2': area_m2
    }


def buffer_analysis(ktvs: List[Dict], facility_points: List[Dict],
                   facility_name: str, buffer_radius_m: float = 500) -> Dict:
    """缓冲区分析"""
    if not facility_points:
        return None

    buffer_deg = buffer_radius_m / 111000

    results = {
        'facility_name': facility_name,
        'facility_count': len(facility_points),
        'buffer_radius_m': buffer_radius_m,
        'ktv_with_facility': 0,
        'ktv_without_facility': 0,
        'avg_facilities_per_ktv': 0,
        'nearest_distances': []
    }

    facility_counts = []

    for ktv in ktvs:
        count = 0
        min_dist = float('inf')

        for fp in facility_points:
            dist = ktv['point'].distance_deg(fp['point'])
            if dist <= buffer_deg:
                count += 1
            if dist < min_dist:
                min_dist = dist

        facility_counts.append(count)
        results['nearest_distances'].append(min_dist * 111000 if min_dist != float('inf') else None)

        if count > 0:
            results['ktv_with_facility'] += 1
        else:
            results['ktv_without_facility'] += 1

    total_ktv = len(ktvs)
    results['avg_facilities_per_ktv'] = sum(facility_counts) / total_ktv if total_ktv > 0 else 0
    results['coverage_ratio'] = results['ktv_with_facility'] / total_ktv if total_ktv > 0 else 0

    # 计算平均最近距离
    valid_distances = [d for d in results['nearest_distances'] if d is not None]
    results['avg_nearest_distance_m'] = sum(valid_distances) / len(valid_distances) if valid_distances else None
    results['median_distance_m'] = sorted(valid_distances)[len(valid_distances) // 2] if valid_distances else None

    # 计算相关性强度
    if results['coverage_ratio'] > 0.7 and results['avg_facilities_per_ktv'] > 2:
        results['correlation'] = "强正相关"
        results['score'] = 3
    elif results['coverage_ratio'] > 0.5 and results['avg_facilities_per_ktv'] > 1:
        results['correlation'] = "中等正相关"
        results['score'] = 2
    elif results['coverage_ratio'] > 0.3:
        results['correlation'] = "弱正相关"
        results['score'] = 1
    else:
        results['correlation'] = "无明显相关"
        results['score'] = 0

    return results


def print_report(ktvs: List[Dict], facilities: Dict[str, List[Dict]]):
    """打印分析报告"""
    print("\n" + "=" * 80)
    print("KTV选址数据要素分析报告")
    print("=" * 80)

    print(f"\n数据概况:")
    print(f"  KTV数量: {len(ktvs)}家")
    print(f"  设施类型数: {len(facilities)}种")

    # 最近邻分析
    print("\n" + "-" * 80)
    print("空间分布分析")
    print("-" * 80)

    nn_result = nearest_neighbor_analysis(ktvs)
    if nn_result:
        print(f"  R比值: {nn_result['r_ratio']:.3f}")
        print(f"  分布模式: {nn_result['interpretation']}")
        print(f"  平均最近邻距离: {nn_result['avg_nearest_distance']:.0f}m")
        print(f"  中位数距离: {nn_result['p50']:.0f}m")
        print(f"  25%分位: {nn_result['p25']:.0f}m")
        print(f"  75%分位: {nn_result['p75']:.0f}m")
        print(f"  研究区域面积: {nn_result['area_m2']/1000000:.1f} km²")

    # 设施相关性分析
    print("\n" + "-" * 80)
    print("设施相关性分析")
    print("-" * 80)

    buffer_distances = {
        '地铁站_20260205': 1000,
        '商场_20260205': 500,
        '写字楼_20260205': 500,
        '便利店_20260205': 300,
    }

    all_results = []

    for facility_name, facility_points in facilities.items():
        buffer_radius = buffer_distances.get(facility_name, 500)

        print(f"\n[{facility_name}]")
        print(f"  设施数量: {len(facility_points)}")

        result = buffer_analysis(ktvs, facility_points, facility_name, buffer_radius)

        if result:
            print(f"  缓冲区半径: {buffer_radius}m")
            print(f"  覆盖率: {result['coverage_ratio']*100:.1f}%")
            print(f"  平均周边设施数: {result['avg_facilities_per_ktv']:.2f}个")
            if result.get('avg_nearest_distance_m'):
                print(f"  平均最近距离: {result['avg_nearest_distance_m']:.0f}m")
            print(f"  相关性: {result['correlation']}")

            all_results.append({
                'facility': facility_name,
                'facility_count': len(facility_points),
                'buffer_radius': buffer_radius,
                'coverage_ratio': result['coverage_ratio'],
                'avg_facilities': result['avg_facilities_per_ktv'],
                'correlation': result['correlation'],
                'score': result['score'],
                'median_distance': result.get('median_distance_m')
            })

    # 综合分析
    print("\n" + "=" * 80)
    print("综合分析结果")
    print("=" * 80)

    print(f"\n{'设施类型':<12} {'设施数量':>10} {'覆盖率':>10} {'平均周边':>10} {'中位距离':>12} {'相关性':>12}")
    print("-" * 80)

    all_results.sort(key=lambda x: x['score'], reverse=True)

    for r in all_results:
        print(f"{r['facility']:<12} {r['facility_count']:>10} {r['coverage_ratio']*100:>9.1f}% "
              f"{r['avg_facilities']:>9.2f} {r['median_distance']:>11.0f}m "
              f"{r['correlation']:>12}")

    # 数据要素影响总结
    print("\n" + "=" * 80)
    print("数据要素对KTV选址的影响分析")
    print("=" * 80)

    print("\n基于相关性分析结果，各数据要素的影响程度排序:")
    for i, r in enumerate(all_results, 1):
        if r['score'] > 0:
            print(f"  {i}. {r['facility']}: {r['correlation']}")
            print(f"     - {r['coverage_ratio']*100:.1f}%的KTV周边{r['buffer_radius']}m内有该设施")
            if r['median_distance']:
                print(f"     - 距离中位数{r['median_distance']:.0f}m")

    print("\n" + "=" * 80)

    return all_results


def main():
    """主程序"""
    print("=" * 80)
    print("KTV选址数据要素分析")
    print("=" * 80)

    # 加载KTV数据
    print("\n加载数据...")
    ktvs = load_ktv_data("data/raw/ktv_pois.csv")
    print(f"北京KTV: {len(ktvs)}家")

    # 加载设施数据
    facilities = load_facilities()
    print(f"设施数据: {list(facilities.keys())}")

    if not ktvs:
        print("\n错误: 未找到北京KTV数据")
        return

    # 运行分析
    results = print_report(ktvs, facilities)

    # 保存结果
    import json
    from datetime import datetime

    output_dir = Path("data/location_analysis/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    result_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d"),
        'ktv_count': len(ktvs),
        'facilities': {k: len(v) for k, v in facilities.items()},
        'spatial_analysis': nearest_neighbor_analysis(ktvs),
        'correlation_results': results
    }

    json_file = output_dir / "ktv_analysis_result.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存至: {json_file}")


if __name__ == "__main__":
    main()
