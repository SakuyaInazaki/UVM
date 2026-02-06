# UVM KTV选址研究 - 工作进度报告

**日期**: 2026-02-06
**项目**: 数据要素在KTV选址中的影响研究

---

## 一、项目目标

研究**数据要素**对KTV选址的影响，需要获取：
1. KTV的地理位置数据（POI）
2. KTV的评分数据
3. KTV的套餐/价格数据
4. 周边设施数据（学校、商场等）

---

## 二、已完成工作

### 2.1 数据采集 ✅

| 数据源 | 数据量 | 状态 | 文件路径 |
|--------|--------|------|----------|
| 高德地图API | 469家北京KTV | ✅ 完成 | `data/raw/ktv_pois_merged.csv` |
| 估算评分/套餐 | 469家 | ✅ 完成 | `data/raw/ktv_with_estimates.csv` |
| 周边设施POI | 若干 | ✅ 完成 | `data/location_analysis/raw/` |

**数据字段** (`ktv_with_estimates.csv`):
```
id, name, address, district, lng, lat, type, tel, source, crawl_time,
brand, tier, rating, review_count, avg_price, price_level,
packages, package_count, estimated
```

### 2.2 数据文件清单

```
data/
├── raw/
│   ├── ktv_pois_merged.csv          # 469家KTV基础数据（高德）
│   ├── ktv_with_estimates.csv       # 469家KTV+估算评分套餐
│   ├── ktv_data_validation_report.md # 数据验证报告
│   └── fenge_zushi_machines.csv      # 分装大师设备数据
├── location_analysis/
│   └── raw/                          # 周边设施数据
└── estimation/                       # 估算模型数据
```

### 2.3 代码脚本

```
src/
├── map_scraper/
│   ├── meituan_ktv_scraper.py       # 美团爬虫（Playwright）
│   ├── dianping_ktv_enhanced.py     # 大众点评爬虫
│   └── ktv_collector*.py            # 高德POI采集工具
└── location_analysis/
    ├── enrich_ktv_with_estimates.py # 数据增强（评分/套餐估算）
    └── ktv_analysis.py              # KTV分析脚本
```

---

## 三、关键问题记录

### 3.1 美团/大众点评爬取失败 ⚠️

**问题**: 无法获取真实的KTV评分和套餐数据

| 平台 | 问题 | 原因 |
|------|------|------|
| 美团 | 显示"验证中心" | 风控拦截，需要住宅IP |
| 大众点评 | 返回404 | URL格式变化，需要登录 |

**已尝试的方案**:
1. ✅ Playwright浏览器自动化
2. ✅ 手动登录验证
3. ✅ 多种URL格式测试
4. ✅ API响应拦截
5. ❌ 所有方案都失败

**结论**: 美团/大众点评的反爬极强，需要：
- 住宅代理IP池
- 破解WASM加密token
- 或使用商业数据服务

### 3.2 当前数据方案

使用**估算数据**作为替代：
- 评分：基于品牌档次估算（3.5-4.5分）
- 人均价格：基于区域×品牌档次估算
- 套餐：基于档次生成模板套餐

数据标记为 `estimated: TRUE`，仅用于研究参考。

---

## 四、数据质量评估

### 4.1 北京KTV分布 (469家)

| 区县 | 数量 | 占比 |
|------|------|------|
| 朝阳区 | 101 | 21.5% |
| 海淀区 | 64 | 13.6% |
| 丰台区 | 52 | 11.1% |
| 昌平区 | 39 | 8.3% |
| 通州区 | 38 | 8.1% |
| 其他区县 | 175 | 37.4% |

### 4.2 品牌分布

| 品牌 | 门店数 | 档次 |
|------|--------|------|
| 唱吧麦颂 | 80 | 中端 |
| 酷秀 | 32 | 中端 |
| 魅KTV | 28 | 中高端 |
| 星聚会 | 18 | 中高端 |
| 温莎 | 4 | 高端 |

---

## 五、Git提交记录

```bash
# 最新提交
180b9fe - chore: ignore local claude settings
9f9375d - feat: add KTV and location data (38个data文件)
fca27b0 - feat: add KTV data collection and scraping tools (18个脚本)
```

**仓库**: https://github.com/SakuyaInazaki/UVM.git

---

## 六、下一步建议

### 6.1 数据获取方向

| 方案 | 可行性 | 成本 | 建议优先级 |
|------|--------|------|-----------|
| 使用现有估算数据 | ✅ 可用 | 无 | ⭐⭐⭐ |
| 爬取KTV品牌官网 | ✅ 可行 | 低 | ⭐⭐ |
| 实地抽样调查 | ✅ 准确 | 中 | ⭐⭐ |
| 购买商业数据 | ✅ 可靠 | 高 | ⭐ |
| 继续攻克美团反爬 | ❌ 极难 | 极高 | ⚠️ 不推荐 |

### 6.2 推荐工作流程

1. **接受当前估算数据**用于初步分析
2. **编写分析脚本**，研究选址因素相关性
3. **抽样验证**部分KTV的真实数据
4. 如需高精度数据，考虑购买或实地调研

### 6.3 可直接使用的脚本

```bash
# 查看KTV数据
python3 -c "
import csv
import json
with open('data/raw/ktv_with_estimates.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    print(f'总计: {len(rows)}家KTV')
    for row in rows[:5]:
        print(f\"{row['name']} - {row['district']} - ¥{row['avg_price']}\")
"
```

---

## 七、技术栈记录

- **Python**: 3.9.6
- **爬虫**: Playwright (异步)
- **地图API**: 高德地图 Amap Place API
- **数据格式**: CSV, JSON
- **Git**: 已提交所有重要文件到GitHub

---

## 八、重要提示

1. **data目录已提交**，包含469家KTV数据
2. **所有脚本已提交**，可直接运行
3. **新对话开始时**，先读取此文件了解进度
4. **如需继续爬取美团**，需要准备住宅代理IP

---

**报告生成时间**: 2026-02-06 21:30
**状态**: 数据采集阶段基本完成，可进入分析阶段
