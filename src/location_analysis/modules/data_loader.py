"""
数据��载与预处理模块
用于加载和处理售货机POI数据及各类选址因素数据
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path
from typing import Optional, Tuple, List
import warnings
warnings.filterwarnings('ignore')


class LocationDataLoader:
    """��址数据加载器"""

    def __init__(self, data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)
        self.vending_df: Optional[pd.DataFrame] = None
        self.vending_gdf: Optional[gdf.GeoDataFrame] = None

    def load_vending_machines(self, filepath: str = "vending_comprehensive.csv") -> gpd.GeoDataFrame:
        """
        加载售货机POI数据

        Returns:
            GeoDataFrame with geometry column
        """
        path = self.data_dir / filepath

        # 读取CSV
        df = pd.read_csv(path, encoding='utf-8-sig')

        # 基本信息
        print(f"\n售货机POI数据概览:")
        print(f"  总记录数: {len(df)}")
        print(f"  有坐标的: {df[['lat', 'lng']].notna().all(axis=1).sum()}")

        # 转换为GeoDataFrame
        geometry = gpd.points_from_xy(df['lng'], df['lat'])
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

        # 清洗数据
        gdf = self._clean_data(gdf)

        self.vending_df = df
        self.vending_gdf = gdf

        self._print_summary(gdf)

        return gdf

    def _clean_data(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """清洗数据"""
        # 移除无效坐标
        valid_mask = (
            (gdf['lat'].between(39.4, 41.0)) &  # 北京纬度范围
            (gdf['lng'].between(115.4, 117.5))  # 北京经度范围
        )
        gdf = gdf[valid_mask].copy()

        # 标准化类别
        if 'category' in gdf.columns:
            gdf['category_main'] = gdf['category'].apply(
                lambda x: x.split(';')[0] if pd.notna(x) else '未知'
            )

        return gdf

    def _print_summary(self, gdf: gpd.GeoDataFrame):
        """打印数据摘要"""
        print(f"\n按类别统计:")
        if 'category_main' in gdf.columns:
            for cat, count in gdf['category_main'].value_counts().items():
                print(f"  {cat}: {count}")

        print(f"\n按区域统计:")
        if 'district' in gdf.columns:
            for dist, count in gdf['district'].value_counts().head(10).items():
                print(f"  {dist}: {count}")

    def load_facility_poi(self, filepath: str) -> gpd.GeoDataFrame:
        """
        加载设施POI数据（地铁站、商场等）

        Args:
            filepath: CSV文件路径

        Returns:
            GeoDataFrame with geometry column
        """
        path = self.data_dir / filepath

        # 尝试读取
        try:
            df = pd.read_csv(path, encoding='utf-8-sig')
        except:
            df = pd.read_csv(path, encoding='gbk')

        # 检查坐标列
        lon_cols = ['lng', 'lon', 'longitude', '经度']
        lat_cols = ['lat', 'latitude', '纬度']

        lon_col = next((c for c in lon_cols if c in df.columns), None)
        lat_col = next((c for c in lat_cols if c in df.columns), None)

        if lon_col and lat_col:
            geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
            gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
            print(f"加载 {filepath}: {len(gdf)} 条记录")
            return gdf
        else:
            print(f"警告: {filepath} 缺少坐标列")
            return None

    def get_bounding_box(self, gdf: gpd.GeoDataFrame) -> Tuple[float, float, float, float]:
        """获取数据边界框"""
        bounds = gdf.total_bounds  # minx, miny, maxx, maxy
        return bounds

    def filter_by_district(self, gdf: gpd.GeoDataFrame, districts: List[str]) -> gpd.GeoDataFrame:
        """按区域筛选"""
        if 'district' not in gdf.columns:
            print("警告: 数据中没有district列")
            return gdf
        return gdf[gdf['district'].isin(districts)].copy()

    def save_processed(self, gdf: gpd.GeoDataFrame, output_path: str):
        """保存处理后的数据"""
        gdf.to_file(output_path, driver='GeoJSON')
        print(f"数据已保存至: {output_path}")


def main():
    """测试数据加载"""
    loader = LocationDataLoader()

    # 加载售货机数据
    vending_gdf = loader.load_vending_machines()

    # 保存为GeoJSON
    output_dir = Path("data/location_analysis/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    loader.save_processed(
        vending_gdf,
        output_dir / "vending_machines.geojson"
    )


if __name__ == "__main__":
    main()
