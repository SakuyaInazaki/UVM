"""
相关性分析模块
分析售货机分布与各类选址因素的相关性
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from typing import List, Dict, Tuple
from scipy.stats import pearsonr, spearmanr
import warnings
warnings.filterwarnings('ignore')


class LocationCorrelationAnalyzer:
    """选址相关性分析器"""

    def __init__(self, vending_gdf: gpd.GeoDataFrame):
        """
        Args:
            vending_gdf: 售货机GeoDataFrame
        """
        self.vending_gdf = vending_gdf
        self.results = {}

    def calculate_facility_density(
        self,
        facility_gdf: gpd.GeoDataFrame,
        grid_size: float = 0.01  # 约1km
    ) -> gpd.GeoDataFrame:
        """
        计算网格单元内设施密度

        Args:
            facility_gdf: 设施POI数据
            grid_size: 网格大小（度）

        Returns:
            带密度列的GeoDataFrame
        """
        # 获取边界
        minx, miny, maxx, maxy = self.vending_gdf.total_bounds

        # 创建网格
        x_coords = np.arange(minx, maxx + grid_size, grid_size)
        y_coords = np.arange(miny, maxy + grid_size, grid_size)

        grid_cells = []
        for x in x_coords[:-1]:
            for y in y_coords[:-1]:
                from shapely.geometry import box
                cell = box(x, y, x + grid_size, y + grid_size)
                grid_cells.append({'geometry': cell, 'grid_id': f"{x:.2f}_{y:.2f}"})

        grid_gdf = gpd.GeoDataFrame(grid_cells, crs="EPSG:4326")

        # 计算每个网格内的设施数量
        for idx, row in grid_gdf.iterrows():
            cell = row.geometry
            count = len(facility_gdf[facility_gdf.geometry.intersects(cell)])
            grid_gdf.loc[idx, 'facility_count'] = count
            grid_gdf.loc[idx, 'facility_density'] = count / (grid_size * 111000) ** 2 * 1000000  # 每平方公里

        return grid_gdf

    def proximity_analysis(
        self,
        facility_gdf: gpd.GeoDataFrame,
        facility_name: str,
        distances: List[float] = [100, 200, 500, 1000]
    ) -> pd.DataFrame:
        """
        邻近度分析 - 统计售货机周边不同距离内的设施数量

        Args:
            facility_gdf: 设施POI数据
            facility_name: 设施名称（用于输出）
            distances: 距离列表（米）

        Returns:
            统计结果DataFrame
        """
        results = []

        for _, vm in self.vending_gdf.iterrows():
            vm_point = vm.geometry
            row_result = {
                'vending_id': vm.get('id', vm.name),
                'vending_name': vm.get('name', ''),
                'lat': vm_point.y,
                'lng': vm_point.x
            }

            for dist in distances:
                # 转换距离为度（粗略）
                buffer_deg = dist / 111000
                buffer = vm_point.buffer(buffer_deg)

                # 统计设施数量
                nearby = facility_gdf[facility_gdf.geometry.intersects(buffer)]
                row_result[f'{facility_name}_{dist}m'] = len(nearby)

                # 最近设施距离
                if len(nearby) > 0:
                    nearest_dist = nearby.geometry.distance(vm_point).min() * 111000
                    row_result[f'{facility_name}_nearest'] = nearest_dist
                else:
                    row_result[f'{facility_name}_nearest'] = np.nan

            results.append(row_result)

        df = pd.DataFrame(results)
        self.results[f'proximity_{facility_name}'] = df
        return df

    def spatial_correlation(
        self,
        facility_gdf: gpd.GeoDataFrame,
        facility_name: str
    ) -> Dict:
        """
        分析售货机密度与设施密度的空间相关性

        Args:
            facility_gdf: 设施POI数据
            facility_name: 设施名称

        Returns:
            相关性统计字典
        """
        # 计算网格密度
        grid_gdf = self.calculate_facility_density(facility_gdf)

        # 计算每个网格内售货机数量
        for idx, row in grid_gdf.iterrows():
            cell = row.geometry
            count = len(self.vending_gdf[self.vending_gdf.geometry.intersects(cell)])
            grid_gdf.loc[idx, 'vending_count'] = count
            grid_gdf.loc[idx, 'vending_density'] = count / (0.01 * 111000) ** 2 * 1000000

        # 只分析有售货机的网格
        active_grids = grid_gdf[grid_gdf['vending_count'] > 0]

        if len(active_grids) < 3:
            return {'error': '有效网格数量不足'}

        # 计算相关性
        pearson_r, pearson_p = pearsonr(
            active_grids['vending_density'],
            active_grids['facility_density']
        )
        spearman_r, spearman_p = spearmanr(
            active_grids['vending_density'],
            active_grids['facility_density']
        )

        result = {
            'facility_name': facility_name,
            'n_grids': len(active_grids),
            'pearson_r': pearson_r,
            'pearson_p': pearson_p,
            'spearman_r': spearman_r,
            'spearman_p': spearman_p,
            'interpretation': self._interpret_correlation(pearson_r, pearson_p)
        }

        self.results[f'correlation_{facility_name}'] = result
        return result

    def _interpret_correlation(self, r: float, p: float) -> str:
        """解释相关性结果"""
        if p > 0.05:
            return "不显著"
        elif abs(r) < 0.3:
            return "弱相关"
        elif abs(r) < 0.7:
            return "中等相关"
        else:
            return "强相关"

    def hotspot_analysis(
        self,
        facility_gdf: gpd.GeoDataFrame,
        facility_name: str
    ) -> Dict:
        """
        热点区重叠分析 - 识别售货机热点与设施热点的重叠程度

        Args:
            facility_gdf: 设施POI数据
            facility_name: 设施名称

        Returns:
            热点重叠统计
        """
        # 计算密度
        grid_gdf = self.calculate_facility_density(facility_gdf)

        for idx, row in grid_gdf.iterrows():
            cell = row.geometry
            count = len(self.vending_gdf[self.vending_gdf.geometry.intersects(cell)])
            grid_gdf.loc[idx, 'vending_count'] = count

        # 定义热点阈值（前25%）
        vending_threshold = grid_gdf['vending_count'].quantile(0.75)
        facility_threshold = grid_gdf['facility_count'].quantile(0.75)

        # 分类
        grid_gdf['vending_hotspot'] = grid_gdf['vending_count'] >= vending_threshold
        grid_gdf['facility_hotspot'] = grid_gdf['facility_count'] >= facility_threshold

        # 重叠分析
        n_vending_hot = grid_gdf['vending_hotspot'].sum()
        n_facility_hot = grid_gdf['facility_hotspot'].sum()
        n_both_hot = (grid_gdf['vending_hotspot'] & grid_gdf['facility_hotspot']).sum()

        # Jaccard相似度
        jaccard = n_both_hot / (n_vending_hot + n_facility_hot - n_both_hot) if (n_vending_hot + n_facility_hot - n_both_hot) > 0 else 0

        result = {
            'facility_name': facility_name,
            'n_vending_hotspots': n_vending_hot,
            'n_facility_hotspots': n_facility_hot,
            'n_overlap': n_both_hot,
            'overlap_ratio': n_both_hot / n_vending_hot if n_vending_hot > 0 else 0,
            'jaccard_index': jaccard,
            'interpretation': self._interpret_hotspot(jaccard)
        }

        self.results[f'hotspot_{facility_name}'] = result
        return result

    def _interpret_hotspot(self, jaccard: float) -> str:
        """解释热点重叠"""
        if jaccard < 0.2:
            return "热点重叠度低"
        elif jaccard < 0.5:
            return "热点重叠度中等"
        else:
            return "热点重叠度高"

    def comprehensive_analysis(
        self,
        facilities: Dict[str, gpd.GeoDataFrame]
    ) -> pd.DataFrame:
        """
        综合分析 - 对所有设施类型进行相关性分析

        Args:
            facilities: {设施名称: GeoDataFrame} 字典

        Returns:
            综合分析结果DataFrame
        """
        all_results = []

        for name, gdf in facilities.items():
            if gdf is None or len(gdf) == 0:
                continue

            # 相关性分析
            corr = self.spatial_correlation(gdf, name)
            if 'error' not in corr:
                all_results.append({
                    '设施类型': name,
                    '设施数量': len(gdf),
                    'Pearson相关系数': f"{corr['pearson_r']:.3f}",
                    '显著性': f"p={corr['pearson_p']:.4f}",
                    '解释': corr['interpretation']
                })

            # 热点分析
            hotspot = self.hotspot_analysis(gdf, name)
            all_results.append({
                '设施类型': f"{name}(热点)",
                '设施数量': len(gdf),
                'Jaccard指数': f"{hotspot['jaccard_index']:.3f}",
                '重叠度': hotspot['interpretation'],
                '解释': '-'
            })

        return pd.DataFrame(all_results)

    def print_correlation_summary(self, facilities: Dict[str, gpd.GeoDataFrame]):
        """打印相关性分析摘要"""
        print("\n" + "=" * 70)
        print("售货机与选址因素相关性分析")
        print("=" * 70)

        df = self.comprehensive_analysis(facilities)

        if not df.empty:
            print("\n" + df.to_string(index=False))

        print("=" * 70)


def main():
    """测试相关性分析"""
    import sys
    sys.path.insert(0, '../modules')
    from data_loader import LocationDataLoader

    # 加载售货机数据
    loader = LocationDataLoader()
    vending_gdf = loader.load_vending_machines()

    # 创建分析器
    analyzer = LocationCorrelationAnalyzer(vending_gdf)

    # 示例：如果没有其他设施数据，可以测试
    print("\n分析器已初始化")
    print(f"售货机数据: {len(vending_gdf)} 条")
    print("\n提示: 请加载设施POI数据进行相关性分析")


if __name__ == "__main__":
    main()
