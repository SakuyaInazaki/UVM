"""
选址评价模型模块
基于空间多准则决策分析(SMCDA)的选址评价方法
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from typing import Dict, List, Tuple, Optional
from shapely.geometry import Point
import warnings
warnings.filterwarnings('ignore')


class SiteEvaluationModel:
    """
    选址评价模型
    结合多准则决策分析(MCDA)与GIS空间分析
    """

    def __init__(
        self,
        vending_gdf: gpd.GeoDataFrame,
        facility_gdfs: Optional[Dict[str, gpd.GeoDataFrame]] = None
    ):
        """
        Args:
            vending_gdf: 现有售货机GeoDataFrame
            facility_gdfs: 各类设施POI数据字典 {设施类型: GeoDataFrame}
        """
        self.vending_gdf = vending_gdf
        self.facility_gdfs = facility_gdfs or {}
        self.weights = {}
        self.indicators = {}

        # 设置默认指标体系
        self._setup_default_indicators()

    def _setup_default_indicators(self):
        """设置默认指标体系"""
        self.indicators = {
            # 需求潜力指标
            'demand_residential': {
                'name': '居民区需求',
                'type': 'benefit',  # 正向指标（越大越好）
                'buffer': 500,  # 米
                'default_weight': 0.2
            },
            'demand_office': {
                'name': '办公需求',
                'type': 'benefit',
                'buffer': 300,
                'default_weight': 0.15
            },
            'demand_commercial': {
                'name': '商业需求',
                'type': 'benefit',
                'buffer': 200,
                'default_weight': 0.15
            },

            # 交通可达性指标
            'access_metro': {
                'name': '地铁可达性',
                'type': 'benefit',
                'buffer': 500,
                'default_weight': 0.15
            },
            'access_bus': {
                'name': '公交可达性',
                'type': 'benefit',
                'buffer': 200,
                'default_weight': 0.05
            },

            # 竞争环境指标
            'competition_vending': {
                'name': '现有售货机竞争',
                'type': 'cost',  # 负向指标（越小越好）
                'buffer': 300,
                'default_weight': 0.15
            },
            'competition_convenience': {
                'name': '便利店竞争',
                'type': 'cost',
                'buffer': 200,
                'default_weight': 0.10
            },

            # 场地适宜性指标
            'site_footfall': {
                'name': '预估人流量',
                'type': 'benefit',
                'buffer': 0,
                'default_weight': 0.05
            }
        }

    def set_weights(self, weights: Dict[str, float]):
        """
        设置指标权重

        Args:
            weights: {指标代码: 权重值}，权重总和应为1
        """
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            print(f"警告: 权重总和为{total:.3f}，将自动归一化")
            weights = {k: v/total for k, v in weights.items()}

        self.weights = weights
        print(f"权重已设置: {self.weights}")

    def use_default_weights(self):
        """使用默认权重（AHP层次分析法结果）"""
        self.weights = {
            k: v['default_weight']
            for k, v in self.indicators.items()
        }
        print(f"使用默认权重: {self.weights}")

    def calculate_indicator_value(
        self,
        location: Tuple[float, float],
        indicator_key: str
    ) -> float:
        """
        计算单个点位在某个指标上的得分

        Args:
            location: (lng, lat) 坐标
            indicator_key: 指标代码

        Returns:
            原始指标值
        """
        if indicator_key not in self.indicators:
            raise ValueError(f"未知指标: {indicator_key}")

        indicator = self.indicators[indicator_key]
        point = Point(location)
        buffer_m = indicator['buffer']

        # 转换为度
        buffer_deg = buffer_m / 111000 if buffer_m > 0 else 0
        buffer_geom = point.buffer(buffer_deg) if buffer_deg > 0 else point

        # 根据指标类型计算值
        value = 0.0

        if 'residential' in indicator_key:
            # 居民区数量
            if 'residential' in self.facility_gdfs:
                nearby = self.facility_gdfs['residential'][
                    self.facility_gdfs['residential'].geometry.intersects(buffer_geom)
                ]
                value = len(nearby)

        elif 'office' in indicator_key:
            # 写字楼数量
            if 'office' in self.facility_gdfs:
                nearby = self.facility_gdfs['office'][
                    self.facility_gdfs['office'].geometry.intersects(buffer_geom)
                ]
                value = len(nearby)

        elif 'commercial' in indicator_key:
            # 商场/商业设施数量
            if 'mall' in self.facility_gdfs:
                nearby = self.facility_gdfs['mall'][
                    self.facility_gdfs['mall'].geometry.intersects(buffer_geom)
                ]
                value = len(nearby)

        elif 'metro' in indicator_key:
            # 最近地铁站距离（转换为得分）
            if 'metro' in self.facility_gdfs:
                distances = self.facility_gdfs['metro'].geometry.distance(point) * 111000
                if len(distances) > 0:
                    nearest = distances.min()
                    # 距离越近得分越高：使用衰减函数
                    value = max(0, 1 - nearest / buffer_m) if buffer_m > 0 else 0

        elif 'bus' in indicator_key:
            # 公交站点数量
            if 'bus' in self.facility_gdfs:
                nearby = self.facility_gdfs['bus'][
                    self.facility_gdfs['bus'].geometry.intersects(buffer_geom)
                ]
                value = len(nearby)

        elif 'competition_vending' in indicator_key:
            # 现有售货机数量（负向）
            nearby = self.vending_gdf[
                self.vending_gdf.geometry.intersects(buffer_geom)
            ]
            value = len(nearby)

        elif 'competition_convenience' in indicator_key:
            # 便利店数量（负向）
            if 'convenience' in self.facility_gdfs:
                nearby = self.facility_gdfs['convenience'][
                    self.facility_gdfs['convenience'].geometry.intersects(buffer_geom)
                ]
                value = len(nearby)

        return value

    def normalize_indicator(
        self,
        values: np.ndarray,
        indicator_type: str
    ) -> np.ndarray:
        """
        标准化指标值

        Args:
            values: 原始指标值数组
            indicator_type: 'benefit'（正向）或 'cost'（负向）

        Returns:
            标准化后的值 [0, 1]
        """
        if indicator_type == 'benefit':
            # 正向指标：Min-Max标准化
            min_val, max_val = values.min(), values.max()
            if max_val - min_val > 0:
                return (values - min_val) / (max_val - min_val)
            else:
                return np.ones_like(values) * 0.5
        else:
            # 负向指标：值越小越好
            min_val, max_val = values.min(), values.max()
            if max_val - min_val > 0:
                return (max_val - values) / (max_val - min_val)
            else:
                return np.ones_like(values) * 0.5

    def evaluate_site(
        self,
        location: Tuple[float, float],
        weights: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        评价单个候选点位

        Args:
            location: (lng, lat) 坐标
            weights: 可选的自定义权重

        Returns:
            评价结果字典
        """
        if weights is None:
            weights = self.weights if self.weights else {k: v['default_weight'] for k, v in self.indicators.items()}

        # 计算各指标值
        indicator_values = {}
        normalized_values = {}

        for key in self.indicators:
            value = self.calculate_indicator_value(location, key)
            indicator_values[key] = value

        # 标准化（需要批量计算所有点位后才能标准化，这里先简化处理）
        # 对于单点评价，使用预设的标准化规则

        # 计算综合得分
        score = 0.0
        for key, weight in weights.items():
            if key in self.indicators:
                indicator = self.indicators[key]
                raw_value = indicator_values.get(key, 0)

                # 简化标准化（基于经验阈值）
                if indicator['type'] == 'benefit':
                    if 'metro' in key:
                        norm_value = min(1.0, raw_value)  # 已经是0-1范围
                    else:
                        norm_value = min(1.0, raw_value / 10)  # 假设10个为满分
                else:  # cost
                    norm_value = max(0, 1 - raw_value / 5)  # 假设5个竞争对手为最低分

                normalized_values[key] = norm_value
                score += norm_value * weight

        return {
            'location': location,
            'score': score,
            'indicator_values': indicator_values,
            'normalized_values': normalized_values
        }

    def evaluate_candidates(
        self,
        candidates: List[Tuple[float, float]],
        weights: Optional[Dict[str, float]] = None
    ) -> pd.DataFrame:
        """
        评价多个候选点位

        Args:
            candidates: [(lng, lat), ...] 候选点位列表
            weights: 可选的自定义权重

        Returns:
            评价结果DataFrame
        """
        results = []

        # 先计算所有点位的原始指标值
        all_raw_values = {key: [] for key in self.indicators}

        for location in candidates:
            for key in self.indicators:
                value = self.calculate_indicator_value(location, key)
                all_raw_values[key].append(value)

        # 批量标准化
        normalized_values = {}
        for key in self.indicators:
            arr = np.array(all_raw_values[key])
            indicator_type = self.indicators[key]['type']
            normalized_values[key] = self.normalize_indicator(arr, indicator_type)

        # 计算综合得分
        if weights is None:
            weights = self.weights if self.weights else {k: v['default_weight'] for k, v in self.indicators.items()}

        for i, location in enumerate(candidates):
            score = 0.0
            indicator_scores = {}

            for key, weight in weights.items():
                if key in self.indicators:
                    norm_val = normalized_values[key][i]
                    indicator_scores[key] = norm_val
                    score += norm_val * weight

            results.append({
                'lng': location[0],
                'lat': location[1],
                'total_score': score,
                **indicator_scores,
                **{f'{k}_raw': all_raw_values[k][i] for k in self.indicators}
            })

        df = pd.DataFrame(results)
        df = df.sort_values('total_score', ascending=False)

        return df

    def find_optimal_locations(
        self,
        region_bounds: Tuple[float, float, float, float],
        n_candidates: int = 100,
        n_select: int = 10,
        min_distance: float = 200
    ) -> gpd.GeoDataFrame:
        """
        在指定区域内寻找最优选址

        Args:
            region_bounds: (min_lng, min_lat, max_lng, max_lat)
            n_candidates: 候选点数量
            n_select: 选择最优的点数
            min_distance: 最小间距（米）

        Returns:
            最优点位GeoDataFrame
        """
        min_lng, min_lat, max_lng, max_lat = region_bounds

        # 生成随机候选点
        candidates = []
        for _ in range(n_candidates):
            lng = np.random.uniform(min_lng, max_lng)
            lat = np.random.uniform(min_lat, max_lat)
            candidates.append((lng, lat))

        # 评价所有候选点
        results_df = self.evaluate_candidates(candidates)

        # 选择前n_select个点，并确保最小间距
        selected = []
        for _, row in results_df.head(n_select * 2).iterrows():
            point = Point(row['lng'], row['lat'])

            # 检查与已选点的距离
            too_close = False
            for selected_point in selected:
                dist = point.distance(selected_point) * 111000  # 米
                if dist < min_distance:
                    too_close = True
                    break

            if not too_close:
                selected.append(point)
                if len(selected) >= n_select:
                    break

        # 创建结果GeoDataFrame
        result_gdf = gpd.GeoDataFrame(
            [{'geometry': p, 'rank': i+1} for i, p in enumerate(selected)],
            crs="EPSG:4326"
        )

        return result_gdf

    def generate suitability_map(
        self,
        region_bounds: Tuple[float, float, float, float],
        grid_size: float = 0.005
    ) -> gpd.GeoDataFrame:
        """
        生成选址适宜性地图（网格评分）

        Args:
            region_bounds: (min_lng, min_lat, max_lng, max_lat)
            grid_size: 网格大小（度）

        Returns:
            带适宜性评分的GeoDataFrame
        """
        min_lng, min_lat, max_lng, max_lat = region_bounds

        # 生成网格
        lngs = np.arange(min_lng, max_lng, grid_size)
        lats = np.arange(min_lat, max_lat, grid_size)

        grid_cells = []
        scores = []

        print(f"生成适宜性地图: {len(lngs)} x {len(lats)} = {len(lngs)*len(lats)} 个网格")

        for lng in lngs:
            for lat in lats:
                from shapely.geometry import box
                cell = box(lng, lat, lng + grid_size, lat + grid_size)
                center = (lng + grid_size/2, lat + grid_size/2)

                result = self.evaluate_site(center)
                grid_cells.append({'geometry': cell})
                scores.append(result['score'])

        # 创建GeoDataFrame
        gdf = gpd.GeoDataFrame(grid_cells, crs="EPSG:4326")
        gdf['suitability_score'] = scores

        # 分类适宜性等级
        gdf['suitability_class'] = pd.cut(
            gdf['suitability_score'],
            bins=[0, 0.3, 0.5, 0.7, 1.0],
            labels=['低', '中', '高', '极高']
        )

        return gdf


def main():
    """测试选址评价模型"""
    import sys
    sys.path.insert(0, '../modules')
    from data_loader import LocationDataLoader

    # 加载数据
    loader = LocationDataLoader()
    vending_gdf = loader.load_vending_machines()

    # 创建评价模型
    model = SiteEvaluationModel(vending_gdf)
    model.use_default_weights()

    # 示例：评价单个点位
    # 使用第一个售货机位置作为示例
    first_vm = vending_gdf.iloc[0]
    location = (first_vm.geometry.x, first_vm.geometry.y)

    result = model.evaluate_site(location)
    print(f"\n示例点位评价:")
    print(f"  位置: {location}")
    print(f"  综合得分: {result['score']:.3f}")
    print(f"  各指标得分: {result['normalized_values']}")


if __name__ == "__main__":
    main()
