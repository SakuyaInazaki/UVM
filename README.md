# UVM Location & Product Analysis
# 无人售货机选址与商品配置研究

## 项目概述

本项目采用**双轨爬虫策略**，为无人售货机的选址决策与商品配置提供数据支持。

- **Task A (地图数据爬虫)**: 基于百度地图/高德地图，爬取目标区域的POI数据、人流量热力图等信息。
- **Task B (商品与销量爬虫)**: 基于美团/饿了么平台，爬取区域内竞品的商品目录、价格、销量等数据。

## 目录结构

```
UVM_sakimi/
├── src/
│   ├── map_scraper/      # 地图数据爬虫 (百度/高德)
│   └── product_scraper/  # 商品与销量爬虫 (美团/饿了么)
├── data/
│   ├── raw/              # 原始爬取数据
│   └── processed/        # 清洗后的分析数据
├── notebooks/            # Jupyter 分析笔记本
├── config/               # 配置文件
├── logs/                 # 运行日志
├── requirements.txt      # Python 依赖
└── README.md            # 项目说明
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
playwright install
```

### 配置

在 `config/` 目录下配置必要参数（注意：`cookies.json` 不会上传到 Git）。

## 许可证

MIT License
