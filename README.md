# 电商用户行为与营收分析

> **Brazilian E-Commerce (Olist) 数据分析项目**
>
> 从 10 万条订单数据中识别用户价值、诊断转化瓶颈、量化实验效果。

---

## 项目概览

| 维度 | 说明 |
|------|------|
| 数据来源 | Brazilian E-Commerce Public Dataset (Kaggle)，9.6 万客户，10 万+ 订单 |
| 分析工具 | SQLite + SQL 窗口函数 + Python (pandas/scikit-learn) |
| 可视化 | Plotly + Streamlit 交互看板 |
| 分析方法 | RFM 分群、K-Means 聚类、漏斗分析、同期群留存、A/B 测试 |

---

## 分析模块

### 1. RFM 用户分群 `sql/01_rfm_segmentation.sql`
- SQL `NTILE` 窗口函数对用户进行 Recency / Frequency / Monetary 打分
- 5 层用户分层：高价值用户 → 流失用户
- 交叉验证：Python K-Means 聚类

### 2. 漏斗分析 & 归因 `sql/02_funnel_analysis.sql`
- 5 步转化漏斗：下单 → 商品 → 支付 → 交付 → 好评
- 月度环比预警，自动标注转化率异常月份
- 归因拆解：销量下降 = 流量少了还是转化低了？

### 3. 同期群留存 `sql/03_cohort_retention.sql`
- SQL 自 JOIN 生成 cohort 留存矩阵
- 识别留存拐点（第 1 个月是黄金窗口期）
- 对比不同批次用户的留存质量，评估产品迭代效果

### 4. 品类贡献度分析 `sql/04_product_category_analysis.sql`
- 帕累托分析：多少品类贡献了 80% 收入
- 品类 × 评分矩阵，发现"高收入低评分"的问题品类

### 5. A/B 测试框架
- Welch's t-test（不假设方差相等，更稳健）
- 样本量估算：给定基线率和最小检测效应，反推所需样本量
- 效应量评估：p 值 + 业务意义双重判断

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载数据集
# 访问 https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
# 下载所有 CSV 文件放入 data/raw/

# 3. 加载数据 & 建库
python run.py load

# 4. 运行分析
python run.py

# 5. 启动交互看板
python run.py dashboard

# 6. 打开 Jupyter Notebook
python run.py notebook
```

---

## 项目结构

```
ecommerce-analysis/
├── data/
│   ├── raw/                  # Kaggle 原始 CSV
│   └── processed/            # 清洗后数据
├── sql/                      # SQL 分析查询
│   ├── 01_rfm_segmentation.sql
│   ├── 02_funnel_analysis.sql
│   ├── 03_cohort_retention.sql
│   └── 04_product_category_analysis.sql
├── notebooks/                # Jupyter 分析笔记
│   ├── 01_eda.ipynb
│   ├── 02_rfm_clustering.ipynb
│   ├── 03_funnel_retention.ipynb
│   └── 04_ab_test.ipynb
├── src/
│   ├── data_loader.py        # 数据加载 & 清洗
│   └── analysis.py           # 核心分析模块
├── dashboard/
│   └── app.py                # Streamlit 交互看板
├── reports/                  # 生成的报告
├── config.py                 # 项目配置
├── run.py                    # 主入口
├── requirements.txt
└── README.md
```

---

## 技术亮点

| 技术点 | 体现在哪里 |
|--------|-----------|
| **SQL 窗口函数** | RFM 分群的 `NTILE`、漏斗的 `LAG`、品类的 `RANK` + 累计 `SUM OVER` |
| **多表 JOIN** | 漏斗分析连接 5 张表（customers → orders → items → payments → reviews） |
| **CTE** | 所有 SQL 查询均使用 `WITH` 递归 CTE，结构清晰可读 |
| **统计推断** | Welch's t-test + 置信区间 + 样本量计算 |
| **机器学习** | K-Means 聚类 + 肘部法则选择 K 值 |
| **交互可视化** | Plotly 双轴图、热力图、树图、帕累托图 |
| **工程化** | 一键运行、模块化结构、缓存机制 |

---

