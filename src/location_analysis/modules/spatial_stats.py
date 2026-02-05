"""
空间统计分析模块
实现核密度分析、空间自相关、标准差椭圆等
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.stats import gaussian_kde
from shapely.geometry import Point
from typing import Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# 尝试导入空间统计库
try:
    from libpysal.weights import Kernel, DistanceBand
    from esda.moran import Moran
    import libpysal
    HAS_PYSAL = True
except ImportError:
    HAS_PYSAL = False
    print("提示: 安装 PySAL 可获得更多空间分析功能")
    print("  pip install libpysal esda")


class SpatialAnalyzer:
    """空间统计分析器"""

    def __init__(self, gdf: gpd.GeoDataFrame):
        """
        Args:
            gdf: 包含geometry列的GeoDataFrame
        """
        self.gdf = gdf
        self.bounds = gdf.total_bounds  # minx, miny, maxx, maxy

    def kernel_density_estimation(
        self,
        bandwidth: float = 500,
        cell_size: float = 100,
        output_type: str = 'grid'
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        核密度估计 (2D Kernel Density Estimation)

        Args:
            bandwidth: 带宽（米），影响平滑程度
            cell_size: 网格单元大小（米）
            output_type: 'grid' 返回网格, 'points' 返回原始点密度

        Returns:
            (X, Y, Z) 网格坐标和密度值
        """
        # 获取坐标
        coords = np.array([[p.x, p.y] for p in self.gdf.geometry])

        # 计算边界（扩展bandwidth）
        minx, miny, maxx, maxy = self.bounds
        padding = bandwidth * 2
        minx -= padding / 111000  # 粗略转换为度
        maxx += padding / 111000
        miny -= padding / 111000
        maxy += padding / 111000

        # 创建网格
        x = np.linspace(minx, maxx, int((maxx - minx) * 111000 / cell_size))
        y = np.linspace(miny, maxy, int((maxy - miny) * 111000 / cell_size))
        X, Y = np.meshgrid(x, y)

        # 计算核密度（简化版：使用标准高斯核）
        # 注意：这里使用简化的计算，实际应考虑投影变换
        try:
            kde = gaussian_kde(coords.T, bw_method=bandwidth / 100000)
            Z = np.array([[kde([xi, yi])[0] for xi in x] for yi in y])
        except Exception as e:
            print(f"KDE计算失败: {e}")
            # 使用简单的直方图作为替代
            from scipy.stats import binned_statistic_2d
            stat = binned_statistic_2d(
                coords[:, 0], coords[:, 1], None,
                statistic='count', bins=[len(x), len(y)],
                range=[[minx, maxx], [miny, maxy]]
            )
            Z = stat.statistic.T

        return X, Y, Z

    def morans_i(self, w_type: str = 'distance', k: int = 5) -> dict:
        """
        计算Moran's I 空间自相关系数

        Args:
            w_type: 空间权重矩阵类型 ('distance' 或 'kernel')
            k: k近邻数量

        Returns:
            包含I值、p值、z值的字典
        """
        if not HAS_PYSAL:
            print("需要安装 PySAL: pip install libpysal esda")
            return None

        # 创建点坐标
        coords = np.array([[p.x, p.y] for p in self.gdf.geometry])

        # 计算密度（每个点周围一定范围内的点数）
        densities = self._calculate_point_densities(coords, radius=500)

        # 创建空间权重矩阵
        if w_type == 'distance':
            w = DistanceBand.from_array(coords, threshold=0.005, binary=True)
        else:
            w = Kernel.from_array(coords, k=k)

        # 标准化
        w.transform = 'r'

        # 计算Moran's I
        mi = Moran(densities, w)

        return {
            'I': mi.I,
            'p_norm': mi.p_norm,
            'z_norm': mi.z_norm,
            'sim': mi.sim if hasattr(mi, 'sim') else None,
            'interpretation': self._interpret_moran(mi.I, mi.p_norm)
        }

    def _calculate_point_densities(self, coords: np.ndarray, radius: float = 0.005) -> np.ndarray:
        """计算每个点周围半径内的点数"""
        from scipy.spatial import cKDTree
        tree = cKDTree(coords)
        densities = tree.query_ball_point(coords, r=radius)
        return np.array([len(d) for d in densities])

    def _interpret_moran(self, i: float, p: float) -> str:
        """解释Moran's I结果"""
        if p > 0.05:
            return "不显著（随机分布）"
        elif i > 0:
            return "正空间自相关（聚集分布）"
        else:
            return "负空间自相关（离散分布）"

    def standard_deviational_ellipse(self) -> dict:
        """
        计算标准差椭圆 (Standard Deviational Ellipse)

        Returns:
            包含中心、长短轴、旋转角度的字典
        """
        coords = np.array([[p.x, p.y] for p in self.gdf.geometry])

        # 计算中心
        center = coords.mean(axis=0)

        # 计算协方差矩阵
        cov = np.cov(coords.T)

        # 特征值分解
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # 标准差（椭圆轴长）
        stds = np.sqrt(eigenvalues)

        # 旋转角度
        angle = np.arctan2(eigenvectors[1, 1], eigenvectors[1, 0])

        return {
            'center': center,
            'std_x': stds[1],  # 主轴
            'std_y': stds[0],  # 次轴
            'angle_deg': np.degrees(angle),
            'angle_rad': angle
        }

    def nearest_neighbor_analysis(self) -> dict:
        """
        最近邻分析 (Nearest Neighbor Analysis)

        Returns:
            包含平均距离、R比值、z值的字典
        """
        coords = np.array([[p.x, p.y] for p in self.gdf.geometry])
        n = len(coords)

        from scipy.spatial import cKDTree
        tree = cKDTree(coords)
        distances, _ = tree.query(coords, k=2)  # k=2因为第一个是自身
        observed_avg_distance = distances[:, 1].mean()

        # 理论平均距离（随机分布期望）
        minx, miny, maxx, maxy = self.bounds
        area = (maxx - minx) * (maxy - miny) * 111000 * 111000  # 粗略转换为平方米
        expected_avg_distance = 0.5 * np.sqrt(area / n)

        # R比值
        r_ratio = observed_avg_distance / expected_avg_distance

        # Z检验
        se = 0.26136 / np.sqrt(n * n / area)
        z_score = (observed_avg_distance - expected_avg_distance) / se

        return {
            'observed_avg_distance': observed_avg_distance,
            'expected_avg_distance': expected_avg_distance,
            'r_ratio': r_ratio,
            'z_score': z_score,
            'interpretation': self._interpret_nna(r_ratio, z_score)
        }

    def _interpret_nna(self, r: float, z: float) -> str:
        """解释最近邻分析结果"""
        if abs(z) < 1.96:
            return "随机分布"
        elif r < 1:
            return f"聚集分布 (R={r:.3f})"
        else:
            return f"均匀分布 (R={r:.3f})"

    def buffer_analysis(
        self,
        center_gdf: gpd.GeoDataFrame,
        buffer_dists: list = [100, 200, 500]
    ) -> pd.DataFrame:
        """
        缓冲区分析 - 统计中心点周边设施数量

        Args:
            center_gdf: 中心点GeoDataFrame（如售货机）
            buffer_dists: 缓冲区距离列表（米）

        Returns:
            统计结果DataFrame
        """
        results = []

        for _, center_row in center_gdf.iterrows():
            center_point = center_row.geometry
            row_result = {'id': center_row.get('id', center_row.name)}

            for dist in buffer_dists:
                # 创建缓冲区（粗略转换：1度约111km）
                buffer_deg = dist / 111000
                buffer = center_point.buffer(buffer_deg)

                # 统计设施数量
                count = len(self.gdf[self.gdf.geometry.intersects(buffer)])
                row_result[f'buffer_{dist}m'] = count

            results.append(row_result)

        return pd.DataFrame(results)

    def print_summary(self):
        """打印空间分析摘要"""
        print("\n" + "=" * 60)
        print("空间统计分析摘要")
        print("=" * 60)

        print(f"\n数据范围:")
        minx, miny, maxx, maxy = self.bounds
        print(f"  经度: {minx:.4f} ~ {maxx:.4f}")
        print(f"  纬度: {miny:.4f} ~ {maxy:.4f}")
        print(f"  点数: {len(self.gdf)}")

        # 最近邻分析
        nna = self.nearest_neighbor_analysis()
        print(f"\n最近邻分析:")
        print(f"  平均最近邻距离: {nna['observed_avg_distance']:.6f}度")
        print(f"  R比值: {nna['r_ratio']:.3f}")
        print(f"  分布模式: {nna['interpretation']}")

        # 标准差椭圆
        ellipse = self.standard_deviational_ellipse()
        print(f"\n标准差椭圆:")
        print(f"  中心: ({ellipse['center'][0]:.4f}, {ellipse['center'][1]:.4f})")
        print(f"  主轴标准差: {ellipse['std_x']*111000:.1f}米")
        print(f"  次轴标准差: {ellipse['std_y']*111000:.1f}米")
        print(f"  旋转角度: {ellipse['angle_deg']:.1f}度")

        # 空间自相关
        if HAS_PYSAL:
            moran = self.morans_i()
            print(f"\nMoran's I 空间自相关:")
            print(f"  I值: {moran['I']:.4f}")
            print(f"  p值: {moran['p_norm']:.4f}")
            print(f"  解释: {moran['interpretation']}")

        print("=" * 60)


def main():
    """测试空间分析"""
    import sys
    sys.path.insert(0, '../modules')
    from data_loader import LocationDataLoader

    # 加载数据
    loader = LocationDataLoader()
    vending_gdf = loader.load_vending_machines()

    # 创建分析器
    analyzer = SpatialAnalyzer(vending_gdf)

    # 打印摘要
    analyzer.print_summary()


if __name__ == "__main__":
    main()
