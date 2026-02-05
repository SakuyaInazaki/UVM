"""
售货机与设施相关性分析
使用采集到的设施数据分析对选址的影响
"""

import csv
import json
import math
from pathlib import Path
from typing import List, Dict, Tuple


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


def load_csv(filepath: str) -> List[Dict]:
    """加载CSV文件"""
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_vending_machines() -> List[Dict]:
    """加载售货机数据"""
    machines = []
    data = load_csv("data/raw/vending_comprehensive.csv")

    for row in data:
        try:
            lat = float(row.get('lat', 0))
            lng = float(row.get('lng', 0))
            if 39 < lat < 41 and 115 < lng < 118:
                machines.append({
                    'name': row.get('name', ''),
                    'category': row.get('category', '').split(';')[0],
                    'district': row.get('district', ''),
                    'lat': lat,
                    'lng': lng,
                    'point': Point(lng, lat)
                })
        except (ValueError, TypeError):
            continue

    return machines


def load_facilities() -> Dict[str, List[Dict]]:
    """加载所有设施数据"""
    data_dir = Path("data/location_analysis/raw")
    facilities = {}

    # 查找设施文件
    for file in data_dir.glob("facility_*.csv"):
        # 从文件名提取设施类型
        parts = file.stem.split("_")
        if len(parts) >= 3:
            facility_type = "_".join(parts[1:-1])  # 去掉facility_和时间戳

            data = load_csv(file)
            facility_points = []

            for row in data:
                try:
                    lat = float(row.get('lat', 0))
                    lng = float(row.get('lng', 0))
                    if lat and lng:
                        facility_points.append({
                            'name': row.get('name', ''),
                            'address': row.get('address', ''),
                            'district': row.get('district', ''),
                            'lat': lat,
                            'lng': lng,
                            'point': Point(lng, lat)
                        })
                except (ValueError, TypeError):
                    continue

            if facility_points:
                facilities[facility_type] = facility_points
                print(f"加载 {facility_type}: {len(facility_points)}条")

    return facilities


def buffer_correlation_analysis(
    vending_machines: List[Dict],
    facility_points: List[Dict],
    facility_name: str,
    buffer_radius_m: float = 300
) -> Dict:
    """
    缓冲区相关性分析
    统计售货机周边设施与售货机分布的关系

    Args:
        vending_machines: 售货机列表
        facility_points: 设施点列表
        facility_name: 设施名称
        buffer_radius_m: 缓冲区半径（米）
    """
    if not facility_points:
        return None

    buffer_deg = buffer_radius_m / 111000

    results = {
        'facility_name': facility_name,
        'facility_count': len(facility_points),
        'buffer_radius_m': buffer_radius_m,
        'vending_with_facility': 0,
        'vending_without_facility': 0,
        'avg_facilities_per_vending': 0,
        'nearest_distances': []
    }

    # 统计每个售货机周边的设施数量
    facility_counts = []

    for vm in vending_machines:
        count = 0
        min_dist = float('inf')

        for fp in facility_points:
            dist = vm['point'].distance_deg(fp['point'])
            if dist <= buffer_deg:
                count += 1
            if dist < min_dist:
                min_dist = dist

        facility_counts.append(count)
        results['nearest_distances'].append(min_dist * 111000 if min_dist != float('inf') else None)

        if count > 0:
            results['vending_with_facility'] += 1
        else:
            results['vending_without_facility'] += 1

    total_vending = len(vending_machines)
    results['avg_facilities_per_vending'] = sum(facility_counts) / total_vending if total_vending > 0 else 0
    results['coverage_ratio'] = results['vending_with_facility'] / total_vending if total_vending > 0 else 0

    # 计算平均最近距离
    valid_distances = [d for d in results['nearest_distances'] if d is not None]
    results['avg_nearest_distance_m'] = sum(valid_distances) / len(valid_distances) if valid_distances else None

    # 分析高密度区
    high_density_count = sum(1 for c in facility_counts if c >= 3)
    results['high_density_ratio'] = high_density_count / total_vending if total_vending > 0 else 0

    # 计算相关性强度（简化版）
    # 如果覆盖率高且平均设施数多，说明正相关
    if results['coverage_ratio'] > 0.7 and results['avg_facilities_per_vending'] > 2:
        results['correlation'] = "强正相关"
        results['score'] = 3
    elif results['coverage_ratio'] > 0.5 and results['avg_facilities_per_vending'] > 1:
        results['correlation'] = "中等正相关"
        results['score'] = 2
    elif results['coverage_ratio'] > 0.3:
        results['correlation'] = "弱正相关"
        results['score'] = 1
    else:
        results['correlation'] = "无明显相关"
        results['score'] = 0

    return results


def distance_decay_analysis(
    vending_machines: List[Dict],
    facility_points: List[Dict],
    facility_name: str
) -> Dict:
    """
    距离衰减分析
    分析售货机与设施的距离分布

    Returns:
        距离分位点和衰减曲线数据
    """
    if not facility_points:
        return None

    all_distances = []

    for vm in vending_machines:
        min_dist = float('inf')
        for fp in facility_points:
            dist = vm['point'].distance_m(fp['point'])
            if dist < min_dist:
                min_dist = dist
        if min_dist != float('inf'):
            all_distances.append(min_dist)

    if not all_distances:
        return None

    all_distances.sort()

    # 计算分位数
    n = len(all_distances)
    percentiles = {
        'min': all_distances[0],
        'p25': all_distances[int(n * 0.25)],
        'p50': all_distances[int(n * 0.5)],
        'p75': all_distances[int(n * 0.75)],
        'p90': all_distances[int(n * 0.9)],
        'max': all_distances[-1],
        'avg': sum(all_distances) / n
    }

    # 距离区间分布
    ranges = [
        (0, 100, '0-100m'),
        (100, 200, '100-200m'),
        (200, 500, '200-500m'),
        (500, 1000, '500-1000m'),
        (1000, float('inf'), '1000m+')
    ]

    range_counts = {}
    for min_r, max_r, label in ranges:
        count = sum(1 for d in all_distances if min_r <= d < max_r)
        range_counts[label] = {
            'count': count,
            'ratio': count / n
        }

    return {
        'facility_name': facility_name,
        'percentiles': percentiles,
        'range_distribution': range_counts
    }


def hotspot_overlap_analysis(
    vending_machines: List[Dict],
    facility_points: List[Dict],
    facility_name: str,
    grid_size_deg: float = 0.01
) -> Dict:
    """
    热点重叠分析
    分析售货机热点与设施热点的重叠程度

    Args:
        grid_size_deg: 网格大小（度）
    """
    if not facility_points:
        return None

    # 计算数据边界
    all_lats = [vm['lat'] for vm in vending_machines] + [fp['lat'] for fp in facility_points]
    all_lngs = [vm['lng'] for vm in vending_machines] + [fp['lng'] for fp in facility_points]

    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lng, max_lng = min(all_lngs), max(all_lngs)

    # 创建网格统计
    vending_grid = {}
    facility_grid = {}

    for vm in vending_machines:
        grid_x = int((vm['lng'] - min_lng) / grid_size_deg)
        grid_y = int((vm['lat'] - min_lat) / grid_size_deg)
        key = (grid_x, grid_y)
        vending_grid[key] = vending_grid.get(key, 0) + 1

    for fp in facility_points:
        grid_x = int((fp['lng'] - min_lng) / grid_size_deg)
        grid_y = int((fp['lat'] - min_lat) / grid_size_deg)
        key = (grid_x, grid_y)
        facility_grid[key] = facility_grid.get(key, 0) + 1

    # 定义热点阈值（前25%）
    if vending_grid:
        vending_threshold = sorted(vending_grid.values())[len(vending_grid) * 3 // 4] if len(vending_grid) > 4 else 1
        vending_hotspots = {k for k, v in vending_grid.items() if v >= vending_threshold}
    else:
        vending_hotspots = set()

    if facility_grid:
        facility_threshold = sorted(facility_grid.values())[len(facility_grid) * 3 // 4] if len(facility_grid) > 4 else 1
        facility_hotspots = {k for k, v in facility_grid.items() if v >= facility_threshold}
    else:
        facility_hotspots = set()

    # 重叠分析
    overlap = vending_hotspots & facility_hotspots

    # Jaccard指数
    union = vending_hotspots | facility_hotspots
    jaccard = len(overlap) / len(union) if union else 0

    return {
        'facility_name': facility_name,
        'vending_hotspots': len(vending_hotspots),
        'facility_hotspots': len(facility_hotspots),
        'overlap_grids': len(overlap),
        'jaccard_index': jaccard,
        'interpretation': '高重叠' if jaccard > 0.3 else '中重叠' if jaccar > 0.15 else '低重叠'
    }


def print_correlation_report(vending_machines: List[Dict], facilities: Dict[str, List[Dict]]):
    """打印相关性分析报告"""

    print("\n" + "=" * 80)
    print("售货机与选址因素相关性分析报告")
    print("=" * 80)

    print(f"\n数据概况:")
    print(f"  售货机数量: {len(vending_machines)}台")
    print(f"  设施类型数: {len(facilities)}种")

    # 缓冲区半径设置（扩大以更好捕捉相关性）
    # 键名匹配实际的设施类型名称
    buffer_distances = {}
    for facility_name in facilities.keys():
        if '地铁站' in facility_name:
            buffer_distances[facility_name] = 1000  # 地铁站影响范围更大
        elif '写字楼' in facility_name:
            buffer_distances[facility_name] = 500
        elif '商场' in facility_name:
            buffer_distances[facility_name] = 500
        elif '便利店' in facility_name:
            buffer_distances[facility_name] = 300
        else:
            buffer_distances[facility_name] = 300

    all_results = []

    for facility_name, facility_points in facilities.items():
        buffer_radius = buffer_distances.get(facility_name, 300)

        print(f"\n" + "-" * 80)
        print(f"[{facility_name}]")
        print(f"设施数量: {len(facility_points)}")

        # 1. 缓冲区相关性分析
        buffer_result = buffer_correlation_analysis(
            vending_machines, facility_points, facility_name, buffer_radius
        )

        if buffer_result:
            print(f"\n缓冲区分析 (半径{buffer_radius}m):")
            print(f"  覆盖率: {buffer_result['coverage_ratio']*100:.1f}% ({buffer_result['vending_with_facility']}/{len(vending_machines)})")
            print(f"  平均周边设施数: {buffer_result['avg_facilities_per_vending']:.2f}个")
            if buffer_result.get('avg_nearest_distance_m'):
                print(f"  平均最近距离: {buffer_result['avg_nearest_distance_m']:.1f}m")
            print(f"  相关性: {buffer_result['correlation']}")

        # 2. 距离衰减分析
        distance_result = distance_decay_analysis(vending_machines, facility_points, facility_name)

        if distance_result:
            print(f"\n距离分布:")
            p = distance_result['percentiles']
            print(f"  中位数: {p['p50']:.1f}m")
            print(f"  75%: {p['p75']:.1f}m")
            print(f"  平均: {p['avg']:.1f}m")

        all_results.append({
            'facility': facility_name,
            'facility_count': len(facility_points),
            'buffer_radius': buffer_radius,
            'coverage_ratio': buffer_result['coverage_ratio'] if buffer_result else 0,
            'avg_facilities': buffer_result['avg_facilities_per_vending'] if buffer_result else 0,
            'correlation': buffer_result['correlation'] if buffer_result else '',
            'score': buffer_result['score'] if buffer_result else 0,
            'median_distance': distance_result['percentiles']['p50'] if distance_result else None
        })

    # 综合分析
    print("\n" + "=" * 80)
    print("综合分析结果")
    print("=" * 80)

    print(f"\n{'设施类型':<12} {'设施数量':>10} {'覆盖率':>10} {'平均周边':>10} {'中位距离':>12} {'相关性':>12}")
    print("-" * 80)

    # 按相关性得分排序
    all_results.sort(key=lambda x: x['score'], reverse=True)

    for r in all_results:
        print(f"{r['facility']:<12} {r['facility_count']:>10} {r['coverage_ratio']*100:>9.1f}% "
              f"{r['avg_facilities']:>9.2f} {r['median_distance']:>11.0f}m "
              f"{r['correlation']:>12}")

    # 数据要素影响总结
    print("\n" + "=" * 80)
    print("数据要素对选址的影响分析")
    print("=" * 80)

    print("\n基于相关性分析结果，各数据要素的影响程度排序:")
    for i, r in enumerate(all_results, 1):
        if r['score'] > 0:
            print(f"  {i}. {r['facility']}: {r['correlation']}")
            print(f"     - {r['coverage_ratio']*100:.1f}%的售货机周边{r['buffer_radius']}m内有该设施")
            if r['median_distance']:
                print(f"     - 距离中位数{r['median_distance']:.0f}m")

    print("\n" + "=" * 80)

    return all_results


def save_results(vending_machines: List[Dict], facilities: Dict, results: List[Dict]):
    """保存分析结果"""
    output_dir = Path("data/location_analysis/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    result_data = {
        'timestamp': '2026-02-05',
        'vending_count': len(vending_machines),
        'facilities': {k: len(v) for k, v in facilities.items()},
        'correlation_results': results
    }

    json_file = output_dir / "correlation_analysis_result.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存至: {json_file}")


def main():
    """主程序"""
    print("=" * 80)
    print("售货机与设施相关性分析")
    print("=" * 80)

    # 加载数据
    print("\n加载数据...")

    vending_machines = load_vending_machines()
    print(f"售货机: {len(vending_machines)}台")

    facilities = load_facilities()

    if not facilities:
        print("\n错误: 未找到设施数据")
        print("请先运行: python3 src/map_scraper/facility_poi_collector.py")
        return

    # 运行分析
    results = print_correlation_report(vending_machines, facilities)

    # 保存结果
    save_results(vending_machines, facilities, results)


if __name__ == "__main__":
    main()
