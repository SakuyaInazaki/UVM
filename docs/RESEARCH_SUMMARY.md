# 自动售货机数据采集研究总结

## 项目背景
为UVM（Unmanned Vending Machine）研究项目采集自动售货机POI数据。

## 研究发现

### 1. 主要运营商

| 运营商 | 市场规模 | 覆盖城市 | API可用性 |
|--------|----------|----------|-----------|
| **友宝 (Ubox)** | 10万+ 台 | 300+ 城市 | ❌ 无公开API |
| **丰e足食** | 16万+ 台 | 72 城市 | ❌ 无公开API |
| **其他品牌** | 未知 | 未知 | ❌ 无公开API |

### 2. 运营商官网调研

#### 友宝在线 (Ubox)
- 官网: https://www.uboxol.com/
- 移动端: https://m.ubox.cn/
- 特点: 阿里巴巴战略合作伙伴
- **结论**: 官网无门店/设备位置查询功能

#### 丰e足食
- 官网: https://www.feng1.com/
- 母公司: 顺丰集团 (SF Express)
- 客服: 400-103-2121
- **结论**: 官网专注B2B安装申请，无位置查询

### 3. 为什么没有公开位置数据？

自动售货机公司不公开设备位置的原因:
1. **位置动态变化**: 设备频繁移动、增减
2. **隐私保护**: 很多设备位于私人空间（办公室、工厂内部）
3. **商业机密**: 位置数据是核心商业资产

### 4. 当前数据采集状态

#### 已有数据质量分析
```
原始数据: 139 条
├── 有效售货机: 7 条 (5%)
└── 无效数据: 132 条 (95%)
    ├── 便利店: 87 条
    ├── 超市/卖场: 26 条
    ├── 网页元素: 14 条
    └── 其他: 5 条
```

**主要问题**: 之前的爬取方法获取了大量便利店数据，而非真正的自动售货机。

## 解决方案

### 方案A: 使用地图API（推荐）

需要申请API Key，然后使用专用爬虫:

```python
# 配置API Key
CONFIG = {
    "tencent_api_key": "你的腾讯地图Key",  # https://lbs.qq.com/dev/console/application/mine
    "amap_api_key": "你的高德地图Key",     # https://console.amap.com/dev/key/app
}
```

运行爬虫:
```bash
python src/map_scraper/vending_scraper.py
```

### 方案B: 手动数据收集

1. **实地调研**: 在目标区域实地记录售货机位置
2. **电话咨询**: 联系运营商客服
   - 友宝: 4001-528-528
   - 丰e足食: 400-103-2121

### 方案C: 替代数据源

考虑使用相关替代数据:
- 写字楼/办公楼位置列表
- 地铁站位置列表
- 机场/火车站位置列表

## 关键文件说明

| 文件 | 说明 |
|------|------|
| `src/map_scraper/vending_scraper.py` | 改进的专用爬虫（需API Key） |
| `src/utils/clean_poi_data.py` | 数据清洗工具 |
| `data/raw/vending_machines_cleaned.csv` | 清洗后的有效数据 |

## 下一步建议

1. **申请地图API Key**
   - 腾讯地图: https://lbs.qq.com/dev/console/application/mine
   - 高德地图: https://console.amap.com/dev/key/app

2. **运行专用爬虫**
   - 使用严格过滤逻辑
   - 只收集真正的自动售货机POI

3. **考虑替代方案**
   - 如果POI数据难以获取，可转向研究售货机分布规律
   - 基于写字楼、交通枢纽等位置进行推算

## 参考资料

- [腾讯位置服务 - WebService API](https://lbs.qq.com/webservice_v1/guide-search.html)
- [高德开放平台 - POI搜索](https://lbs.amap.com/api/webservice/guide/api/search)
- 友宝在线: https://www.uboxol.com/
- 丰e足食: https://www.feng1.com/

---
*生成时间: 2026-02-04*
*作者: UVM Research Team*
