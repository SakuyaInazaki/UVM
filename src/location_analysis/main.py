"""
选址分析主程序
数据要素对无人售货机选址影响研究

用法:
    python main.py --mode stats      # 空间统计分析
    python main.py --mode correlation # 相关性分析
    python main.py --mode evaluate    # 选址评价
    python main.py --mode all         # 完整分析
"""

import argparse
import sys
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent / "modules"))

from data_loader import LocationDataLoader
from spatial_stats import SpatialAnalyzer
from correlation import LocationCorrelationAnalyzer
from evaluation import SiteEvaluationModel


def run_spatial_analysis(data_dir: str = "../../data/raw"):
    """运行空间统计分析"""
    print("\n" + "=" * 70)
    print("步骤1: 空间统计分析")
    print("=" * 70)

    # 加载数据
    loader = LocationDataLoader(data_dir)
    vending_gdf = loader.load_vending_machines()

    # 创建分析器
    analyzer = SpatialAnalyzer(vending_gdf)

    # 打印摘要
    analyzer.print_summary()

    return vending_gdf


def run_correlation_analysis(vending_gdf, data_dir: str = "../../data/raw"):
    """运行相关性分析"""
    print("\n" + "=" * 70)
    print("步骤2: 相关性分析")
    print("=" * 70)

    # 创建分析器
    analyzer = LocationCorrelationAnalyzer(vending_gdf)

    # 加载设施数据（如果有）
    facilities = {}

    # 尝试加载各类设施数据
    facility_files = {
        'metro': 'amap_pois.csv',
        'mall': 'amap_pois.csv',
        'office': 'amap_pois.csv'
    }

    for name, filename in facility_files.items():
        try:
            gdf = loader.load_facility_poi(filename)
            if gdf is not None:
                facilities[name] = gdf
        except:
            pass

    if facilities:
        analyzer.print_correlation_summary(facilities)
    else:
        print("\n暂无设施数据，跳过相关性分析")
        print("提示: 请补充各类设施POI数据以进行相关性分析")

    return analyzer


def run_evaluation(vending_gdf):
    """运行选址评价"""
    print("\n" + "=" * 70)
    print("步骤3: 选址评价模型")
    print("=" * 70)

    # 创建评价模型
    model = SiteEvaluationModel(vending_gdf)
    model.use_default_weights()

    # 获取数据边界
    bounds = vending_gdf.total_bounds
    print(f"\n数据范围: {bounds}")

    # 示例：评价现有售货机点位
    print("\n分析现有售货机点位得分分布...")
    scores = []
    for idx, row in vending_gdf.iterrows():
        location = (row.geometry.x, row.geometry.y)
        result = model.evaluate_site(location)
        scores.append(result['score'])

    print(f"\n得分统计:")
    print(f"  平均分: {sum(scores)/len(scores):.3f}")
    print(f"  最高分: {max(scores):.3f}")
    print(f"  最低分: {min(scores):.3f}")

    # 找出最优和最差点位
    vending_gdf = vending_gdf.copy()
    vending_gdf['score'] = scores
    print(f"\n得分最高的5个点位:")
    top = vending_gdf.nlargest(5, 'score')
    for idx, row in top.iterrows():
        print(f"  {row.get('name', 'Unknown')}: {row['score']:.3f}")

    return model


def main():
    parser = argparse.ArgumentParser(description='选址分析工具')
    parser.add_argument(
        '--mode',
        choices=['stats', 'correlation', 'evaluate', 'all'],
        default='all',
        help='分析模式'
    )
    parser.add_argument(
        '--data-dir',
        default='../../data/raw',
        help='数据目录'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("数据要素对无人售货机选址影响研究")
    print("=" * 70)

    vending_gdf = None
    model = None

    if args.mode in ['stats', 'all']:
        vending_gdf = run_spatial_analysis(args.data_dir)

    if args.mode in ['correlation', 'all'] and vending_gdf is not None:
        run_correlation_analysis(vending_gdf, args.data_dir)

    if args.mode in ['evaluate', 'all'] and vending_gdf is not None:
        model = run_evaluation(vending_gdf)

    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
