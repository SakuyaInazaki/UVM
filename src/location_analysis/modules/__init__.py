"""
选址分析模块
数据要素对无人售货机选址影响研究
"""

from .data_loader import LocationDataLoader
from .spatial_stats import SpatialAnalyzer
from .correlation import LocationCorrelationAnalyzer
from .evaluation import SiteEvaluationModel

__all__ = [
    'LocationDataLoader',
    'SpatialAnalyzer',
    'LocationCorrelationAnalyzer',
    'SiteEvaluationModel'
]

__version__ = '1.0.0'
__author__ = 'UVM Research Team'
