"""
选址分析工具（简化版）
数据要素对无人售货机选址影响研究
不依赖pandas/geopandas等外部库
"""

import csv
import json
import math
from pathlib import Path
from typing import List, Tuple, Dict, Optional


class Point:
    """简单的点类"""
    def __init__(self, lng: float, lat: float):
        self.lng = lng
        self.lat = lat

    def distance_to(self, other: 'Point') -> float:
        """计算到另一个点的距离（度）"""
        return math.sqrt((self.lng - other.lng)**2 + (self.lat - other.lat)**2)

    def distance_meters(self, other: 'Point') -> float:
        """计算到另一个点的距离（米，近似）"""
        # 粗略转换：1度约111km
        return self.distance_to(other) * 111000


def load_vending_machines(filepath: str = "data/raw/vending_comprehensive.csv") -> List[Dict]:
    """加载售货机POI数据"""
    machines = []

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get('lat', 0))
                lng = float(row.get('lng', 0))
                if 39 < lat < 41 and 115 < lng < 118:  # 北京范围
                    machines.append({
                        'id': row.get('id', ''),
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


def print_data_summary(machines: List[Dict]):
    """打印数据摘要"""
    print("\n" + "=" * 70)
    print("售货机POI数据概览")
    print("=" * 70)

    print(f"\n总记录数: {len(machines)}")

    # 按类别统计
    categories = {}
    for m in machines:
        cat = m['category']
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\n按类别统计:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # 按区域统计
    districts = {}
    for m in machines:
        dist = m['district']
        districts[dist] = districts.get(dist, 0) + 1

    print(f"\n按区域统计:")
    for dist, count in sorted(districts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {dist}: {count}")


def calculate_bounds(machines: List[Dict]) -> Tuple[float, float, float, float]:
    """计算数据边界框"""
    if not machines:
        return (0, 0, 0, 0)

    min_lat = min(m['lat'] for m in machines)
    max_lat = max(m['lat'] for m in machines)
    min_lng = min(m['lng'] for m in machines)
    max_lng = max(m['lng'] for m in machines)

    return (min_lng, min_lat, max_lng, max_lat)


def nearest_neighbor_analysis(machines: List[Dict]) -> Dict:
    """最近邻分析"""
    n = len(machines)
    if n < 2:
        return {}

    # 计算每个点到最近邻的距离
    distances = []
    for i, m1 in enumerate(machines):
        min_dist = float('inf')
        for j, m2 in enumerate(machines):
            if i != j:
                dist = m1['point'].distance_to(m2['point'])
                if dist < min_dist:
                    min_dist = dist
        distances.append(min_dist)

    avg_distance = sum(distances) / len(distances)

    # 计算边界和面积
    min_lng, min_lat, max_lng, max_lat = calculate_bounds(machines)
    area_sq_deg = (max_lng - min_lng) * (max_lat - min_lat)

    # 理论平均距离（随机分布）
    expected_avg = 0.5 * math.sqrt(area_sq_deg / n)

    # R比值
    r_ratio = avg_distance / expected_avg if expected_avg > 0 else 0

    return {
        'avg_neighbor_distance_deg': avg_distance,
        'avg_neighbor_distance_m': avg_distance * 111000,
        'expected_avg_distance_deg': expected_avg,
        'r_ratio': r_ratio,
        'interpretation': interpret_r_ratio(r_ratio)
    }


def interpret_r_ratio(r: float) -> str:
    """解释R比值"""
    if r < 0.8:
        return f"聚集分布 (R={r:.3f}<0.8)"
    elif r > 1.2:
        return f"均匀分布 (R={r:.3f}>1.2)"
    else:
        return f"随机分布 (R={r:.3f}~1.0)"


def calculate_centroid(machines: List[Dict]) -> Point:
    """计算分布中心"""
    avg_lat = sum(m['lat'] for m in machines) / len(machines)
    avg_lng = sum(m['lng'] for m in machines) / len(machines)
    return Point(avg_lng, avg_lat)


def calculate_std_ellipse(machines: List[Dict]) -> Dict:
    """计算标准差椭圆"""
    # 计算协方差
    mean_lng = sum(m['lng'] for m in machines) / len(machines)
    mean_lat = sum(m['lat'] for m in machines) / len(machines)

    # 计算方差和协方差
    var_lng = sum((m['lng'] - mean_lng)**2 for m in machines) / len(machines)
    var_lat = sum((m['lat'] - mean_lat)**2 for m in machines) / len(machines)
    cov = sum((m['lng'] - mean_lng) * (m['lat'] - mean_lat) for m in machines) / len(machines)

    # 特征值分解
    trace = var_lng + var_lat
    diff = var_lng - var_lat
    det = var_lng * var_lat - cov * cov

    # 主轴方向（度）
    if abs(diff) < 1e-10:
        angle = 45 if cov > 0 else -45
    else:
        angle = 0.5 * math.atan2(2 * cov, diff) * 180 / math.pi

    # 标准差
    std_lng = math.sqrt(var_lng)
    std_lat = math.sqrt(var_lat)

    return {
        'center': (mean_lng, mean_lat),
        'std_lng_deg': std_lng,
        'std_lat_deg': std_lat,
        'std_lng_m': std_lng * 111000,
        'std_lat_m': std_lat * 111000,
        'angle_deg': angle
    }


def quadrant_analysis(machines: List[Dict]) -> Dict:
    """象限分析 - 以中心为原点"""
    centroid = calculate_centroid(machines)

    quadrants = {'NE': 0, 'NW': 0, 'SE': 0, 'SW': 0}

    for m in machines:
        if m['lat'] >= centroid.lat and m['lng'] >= centroid.lng:
            quadrants['NE'] += 1
        elif m['lat'] >= centroid.lat and m['lng'] < centroid.lng:
            quadrants['NW'] += 1
        elif m['lat'] < centroid.lat and m['lng'] >= centroid.lng:
            quadrants['SE'] += 1
        else:
            quadrants['SW'] += 1

    return quadrants


def buffer_analysis(machines: List[Dict], buffer_radius_m: float = 500) -> Dict:
    """缓冲区分析 - 计算每个点位周边的点数"""
    buffer_deg = buffer_radius_m / 111000

    results = []
    for m in machines:
        count = 0
        for other in machines:
            if m['id'] != other['id']:
                if m['point'].distance_to(other['point']) <= buffer_deg:
                    count += 1
        results.append(count)

    # 统计
    avg_neighbors = sum(results) / len(results) if results else 0
    max_neighbors = max(results) if results else 0

    # 找出密集点
    density_sorted = sorted(
        [(m, r) for m, r in zip(machines, results)],
        key=lambda x: x[1],
        reverse=True
    )

    return {
        'buffer_radius_m': buffer_radius_m,
        'avg_neighbors': avg_neighbors,
        'max_neighbors': max_neighbors,
        'densest_locations': [
            {'name': m['name'], 'neighbors': n, 'district': m['district']}
            for m, n in density_sorted[:5]
        ]
    }


def facility_correlation_sample(
    machines: List[Dict],
    facility_points: List[Point],
    facility_name: str,
    buffer_radius_m: float = 300
) -> Dict:
    """
    计算售货机与某类设施的相关性（示例）

    Args:
        machines: 售货机列表
        facility_points: 设施坐标列表
        facility_name: 设施名称
        buffer_radius_m: 缓冲区半径（米）
    """
    if not facility_points:
        return None

    buffer_deg = buffer_radius_m / 111000

    # 统计每个售货机周边的设施数量
    facility_counts = []
    for m in machines:
        count = sum(
            1 for f in facility_points
            if m['point'].distance_to(f) <= buffer_deg
        )
        facility_counts.append(count)

    avg_facilities = sum(facility_counts) / len(facility_counts) if facility_counts else 0

    # 统计有设施覆盖的售货机比例
    covered_ratio = sum(1 for c in facility_counts if c > 0) / len(facility_counts)

    return {
        'facility_name': facility_name,
        'facility_count': len(facility_points),
        'buffer_radius_m': buffer_radius_m,
        'avg_facilities_near_vending': avg_facilities,
        'vending_with_facility_ratio': covered_ratio,
        'interpretation': f"{covered_ratio*100:.1f}%的售货机周边{buffer_radius_m}m内有{facility_name}"
    }


def print_spatial_analysis_report(machines: List[Dict]):
    """打印完整的空间分析报告"""
    print("\n" + "=" * 70)
    print("北京无人售货机空间分布分析报告")
    print("=" * 70)

    # 1. 数据摘要
    print_data_summary(machines)

    # 2. 边界范围
    min_lng, min_lat, max_lng, max_lat = calculate_bounds(machines)
    print(f"\n空间范围:")
    print(f"  经度: {min_lng:.4f} ~ {max_lng:.4f}")
    print(f"  纬度: {min_lat:.4f} ~ {max_lat:.4f}")
    print(f"  跨度: {(max_lng-min_lng)*111:.1f}km × {(max_lat-min_lat)*111:.1f}km")

    # 3. 分布中心
    centroid = calculate_centroid(machines)
    print(f"\n分布中心:")
    print(f"  坐标: ({centroid.lng:.4f}, {centroid.lat:.4f})")

    # 4. 最近邻分析
    nna = nearest_neighbor_analysis(machines)
    print(f"\n最近邻分析:")
    print(f"  平均最近邻距离: {nna['avg_neighbor_distance_m']:.1f}米")
    print(f"  R比值: {nna['r_ratio']:.3f}")
    print(f"  分布模式: {nna['interpretation']}")

    # 5. 标准差椭圆
    ellipse = calculate_std_ellipse(machines)
    print(f"\n标准差椭圆:")
    print(f"  主轴标准差: {ellipse['std_lng_m']:.1f}米")
    print(f"  次轴标准差: {ellipse['std_lat_m']:.1f}米")
    print(f"  方向角度: {ellipse['angle_deg']:.1f}度")

    # 6. 象限分析
    quads = quadrant_analysis(machines)
    print(f"\n象限分布 (以中心为原点):")
    for q, count in quads.items():
        print(f"  {q}: {count}台")

    # 7. 缓冲区分析
    buff = buffer_analysis(machines, 500)
    print(f"\n缓冲区分析 (500米半径):")
    print(f"  平均周边点数: {buff['avg_neighbors']:.1f}")
    print(f"  最密集点位周边点数: {buff['max_neighbors']}")
    print(f"  最密集区域:")
    for loc in buff['densest_locations'][:3]:
        print(f"    - {loc['name']} ({loc['district']}): {loc['neighbors']}台")

    # 8. 选址要素分析总结
    print("\n" + "=" * 70)
    print("数据要素对选址的影响分析")
    print("=" * 70)

    print("\n基于现有数据分析，售货机选址呈现以下特征:")
    print(f"\n1. 空间分布模式:")
    print(f"   - {nna['interpretation']}")
    print(f"   - 分布呈现{'沿主轴方向' if abs(ellipse['angle_deg']) > 20 else '较为均匀'}的空间格局")

    print(f"\n2. 高密度区域特征:")
    top_districts = sorted(
        [(d, sum(1 for m in machines if m['district'] == d)) for d in set(m['district'] for m in machines)],
        key=lambda x: -x[1]
    )[:3]
    for dist, count in top_districts:
        print(f"   - {dist}: {count}台")

    print(f"\n3. 聚集特征:")
    print(f"   - 平均每台售货机500米范围内有{buff['avg_neighbors']:.1f}台其他售货机")
    print(f"   - 最密集区域可达{buff['max_neighbors']}台，显示明显的空间聚集效应")

    print("\n" + "=" * 70)


def save_results(machines: List[Dict], output_dir: str = "data/location_analysis/output"):
    """保存分析结果"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 保存为JSON
    result = {
        'timestamp': '2026-02-05',
        'total_machines': len(machines),
        'bounds': calculate_bounds(machines),
        'centroid': [calculate_centroid(machines).lng, calculate_centroid(machines).lat],
        'nearest_neighbor_analysis': nearest_neighbor_analysis(machines),
        'std_ellipse': calculate_std_ellipse(machines),
        'quadrant_distribution': quadrant_analysis(machines),
        'buffer_analysis_500m': buffer_analysis(machines, 500)
    }

    json_file = output_path / "spatial_analysis_result.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存至: {json_file}")

    return result


def main():
    """主程序"""
    print("=" * 70)
    print("数据要素对无人售货机选址影响研究")
    print("空间统计分析工具")
    print("=" * 70)

    # 加载数据
    print("\n正在加载数据...")
    machines = load_vending_machines()
    print(f"成功加载 {len(machines)} 条售货机POI记录")

    # 运行分析
    print("\n正在运行空间统计分析...")
    print_spatial_analysis_report(machines)

    # 保存结果
    save_results(machines)

    print("\n分析完成！")


if __name__ == "__main__":
    main()
