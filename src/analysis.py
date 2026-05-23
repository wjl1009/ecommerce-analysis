"""
核心分析模块 — 所有数据分析的入口
──────────────────────────────
数据流：
  1. 本模块从 SQL 文件读取查询逻辑
  2. 连接 data/olist.db 执行查询
  3. 返回 pandas DataFrame 给 notebook 和看板使用

包含的分析模块：
  - RFM 分群（SQL + K-Means）
  - 漏斗分析 + 归因
  - 卖家同期群留存
  - 品类贡献度（帕累托）
  - A/B 测试（纯 Python 统计）
  - 月度概览
"""

import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from typing import Tuple, Dict
from datetime import datetime

# 强行把项目根目录加入 Python 的搜索范围，从而让你能顺利导入位于根目录下的 config.py 文件
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_connection():
    """创建数据库连接。
    每次调用返回新连接，用完记得 close()。
    为什么不复用连接？因为 SQLite 单写锁，多函数共用容易阻塞。"""
    return sqlite3.connect(config.DB_PATH)


# ═══════════════════════════════════════════════════════════
# 1. RFM 用户分群
# ═══════════════════════════════════════════════════════════
# 原理：用 R(最近购买距今天数)、F(购买次数)、M(消费金额) 三个维度给用户打分
# SQL 做 NTILE 分档打分 → CASE WHEN 贴标签
# Python K-Means 做无监督聚类 → 自动发现群体
# 两者互相验证：SQL 规则分群 vs 算法分群

def run_rfm_analysis() -> pd.DataFrame:
    """读取 sql/01_rfm_segmentation.sql 并执行，返回用户分群结果。
    5 行数据（5 个群体），列：用户群体、用户数、人均消费、群体总收入 等"""
    sql_path = os.path.join(config.SQL_DIR, "01_rfm_segmentation.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def rfm_kmeans_clustering(n_clusters: int = 4) -> pd.DataFrame:
    """用 K-Means 算法从 R/F/M 三个维度自动聚类用户。
    ────────────────────────────────────────────
    流程：
      1. 从数据库查每个用户的 R、F、M 原始值
      2. StandardScaler 标准化（把天数、次数、金额统一到同一尺度）
      3. KMeans 聚类（k=4，分成 4 组）
      4. 根据每组的 R/F/M 均值，给聚类贴上中文标签

    为什么做聚类？SQL 的分群规则是人定的（"R分≤2且F分≤2=高价值"），
    K-Means 让数据自己说话——两种方法互相验证。

    Parameters:
        n_clusters: 分几群，默认 4
    Returns:
        93,263 行 DataFrame，每行一个用户，带 cluster 和 cluster_name 列
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans

    conn = get_connection()

    # 查每个用户的 RFM 原始值（和 SQL 版用的同一套数据）
    query = """
        SELECT
            c.customer_unique_id,
            julianday('2018-09-01') - julianday(MAX(o.order_purchase_timestamp)) AS recency,
            COUNT(DISTINCT o.order_id) AS frequency,
            SUM(oi.price + oi.freight_value) AS monetary
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'delivered'
        GROUP BY c.customer_unique_id
    """
    df = pd.read_sql(query, conn)
    conn.close()

    # ── 标准化 ──
    # 为什么要标准化？recency 是几百天、monetary 是几百元、frequency 是 1-2 次
    # 如果不标准化，K-Means 会被 monetary 主导（数值大），frequency 几乎不起作用
    features = df[["recency", "frequency", "monetary"]]
    scaler = StandardScaler()                          # 把每个特征变成均值=0、标准差=1
    scaled = scaler.fit_transform(features)            # 返回 numpy 数组

    # ── 聚类 ──
    # random_state=42：固定随机种子，每次跑结果一致（可复现）
    # n_init=10：跑 10 次取最好的一次（K-Means 对初始点敏感）
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(scaled)
    df["cluster"] = kmeans.labels_                     # 0, 1, 2, 3

    # ── 贴标签 ──
    # 根据每群的中心点（均值）判断属于哪类
    # 规则：R 小=活跃（中位数以下为"近"），M 大=花钱多（中位数以上为"高"）
    cluster_stats = df.groupby("cluster")[["recency", "frequency", "monetary"]].mean()
    cluster_names = {}
    for c in cluster_stats.index:
        r, f, m = cluster_stats.loc[c]
        if r < cluster_stats["recency"].median() and m > cluster_stats["monetary"].median():
            cluster_names[c] = "高价值"
        elif r < cluster_stats["recency"].median() and m <= cluster_stats["monetary"].median():
            cluster_names[c] = "新用户"
        elif r >= cluster_stats["recency"].median() and m > cluster_stats["monetary"].median():
            cluster_names[c] = "流失中-高价值"
        else:
            cluster_names[c] = "已流失"
    df["cluster_name"] = df["cluster"].map(cluster_names)

    return df


# ═══════════════════════════════════════════════════════════
# 2. 卖家同期群留存
# ═══════════════════════════════════════════════════════════
# 数据背景：Olist 每个客户只买一次，所以不能用"用户复购率"做留存。
# 改用卖家维度——卖家持续在平台接单，才是 marketplace 健康度的核心指标。

def run_cohort_retention() -> pd.DataFrame:
    """读取 sql/03_cohort_retention.sql 并执行，返回卖家留存明细。
    每行 = 一个同期群在某个月的留存数据。
    约 231 行，列：同期群月份、第N月、留存卖家数、留存率百分比、预警"""
    sql_path = os.path.join(config.SQL_DIR, "03_cohort_retention.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def cohort_retention_pivot() -> pd.DataFrame:
    """把留存明细透视成矩阵表。
    ────────────────────────────
    输入（run_cohort_retention 的结果）：
      同期群月份 | 第N月 | 留存率百分比
      2017-01   | 0     | 100
      2017-01   | 1     | 71
      ...

    输出（透视表）：
                第0月  第1月  第2月  ...
      2017-01   100    71    60    ...
      2017-02   100    63    56    ...

    用途：热力图和留存曲线的数据源，笔记本和看板都用它。
    """
    df = run_cohort_retention()
    # aggfunc='first'：如果同一个 (同期群月份, 第N月) 有两条记录，取第一条。
    # 正常情况下每个组合只有一条，这里只是防御性写法。
    pivot = df.pivot_table(
        index="同期群月份",      # 透视表的行
        columns="第N月",         # 透视表的列
        values="留存率百分比",    # 透视表的值
        aggfunc="first",
    )
    return pivot


# ═══════════════════════════════════════════════════════════
# 3. A/B 测试框架
# ═══════════════════════════════════════════════════════════
# 回答"这个改动到底有没有效果"——不是看两组均值大小，而是做统计检验

def ab_test_summary(
    group_a: pd.Series, group_b: pd.Series, metric_name: str = "metric"
) -> Dict:
    """对两组数据执行 Welch's t 检验，返回中文版 A/B 测试报告。
    ──────────────────────────────────────────────────────────
    为什么要用 Welch's t-test（equal_var=False）？
      Student's t-test 假设两组方差相等——这在真实业务中几乎不成立。
      实验组可能让部分用户反应特别大（方差变大），Welch's 不假设等方差，更稳健。

    置信区间怎么算？
      diff ± 1.96 × SE
      1.96 是标准正态分布 95% 置信水平对应的 z 值。
      如果 n < 30，应该改用 t 分布分位数（但电商实验 n 通常很大，z 值足够）。

    Parameters:
        group_a: 对照组数据（pandas Series，如客单价）
        group_b: 实验组数据
        metric_name: 指标名称，用于报告标题

    Returns:
        字典，包含：指标、对照组均值、实验组均值、绝对差异、
                   相对提升、95%置信区间、t统计量、p值、是否显著、样本量
    """
    from scipy import stats

    n_a, n_b = len(group_a), len(group_b)       # 两组的样本量
    mean_a, mean_b = group_a.mean(), group_b.mean()  # 两组的均值
    std_a, std_b = group_a.std(), group_b.std()       # 两组的标准差

    # Welch's t-test：equal_var=False 是不假设等方差的关键参数
    t_stat, p_value = stats.ttest_ind(group_a, group_b, equal_var=False)

    # ── 差异的 95% 置信区间 ──
    # SE = sqrt(s1²/n1 + s2²/n2)，Welch's 标准误公式
    diff = mean_b - mean_a                          # 实验组减对照组
    se = np.sqrt(std_a**2 / n_a + std_b**2 / n_b)   # 差异的标准误
    ci_low = diff - 1.96 * se                       # 置信下限
    ci_high = diff + 1.96 * se                      # 置信上限
    relative_lift = diff / mean_a * 100 if mean_a != 0 else 0  # 相对提升百分比

    # 判断是否显著：p 值小于配置的显著性水平（默认 0.05）
    significant = p_value < config.SIGNIFICANCE_LEVEL

    return {
        "指标": metric_name,
        "对照组均值": round(mean_a, 4),
        "实验组均值": round(mean_b, 4),
        "绝对差异": round(diff, 4),
        "相对提升": f"{relative_lift:.2f}%",
        "95%_CI": f"[{ci_low:.4f}, {ci_high:.4f}]",
        "t统计量": round(t_stat, 4),
        "p值": round(p_value, 4),
        "是否显著": "显著" if significant else "不显著",
        "样本量_对照": n_a,
        "样本量_实验": n_b,
    }


def required_sample_size(
    baseline_rate: float, min_detectable_effect: float, power: float = 0.80
) -> int:
    """计算 A/B 测试每组最少需要多少样本——实验开始前最重要的一步。
    ──────────────────────────────────────────────────────────
    三个输入参数之间的关系：
      - baseline_rate（基线转化率）越大，所需样本越少（更容易检测到变化）
      - min_detectable_effect（MDE）越小，所需样本越多（检测微小变化需要大样本）
      - power（统计功效）越大，所需样本越多（更大概率检测到效应）

    典型调用：
      required_sample_size(baseline=0.05, mde=0.005, power=0.80)
      → 如果基线 5%，想检测 0.5% 的提升，80% 功效，需要每组约 3.1 万人

    公式来源：比例检验的样本量公式（正态近似法）
      n = (z_α√(2p̄(1-p̄)) + z_β√(p₁(1-p₁)+p₂(1-p₂)))² / (p₂-p₁)²
      其中 p̄ = (p₁+p₂)/2

    Parameters:
        baseline_rate: 对照组的基线转化率，如 0.05 表示 5%
        min_detectable_effect: 最小可检测效应（MDE），如 0.005 表示 0.5个百分点的提升
        power: 统计功效（1-β），默认 0.80。含义：如果真有提升，有 80% 概率检测出来

    Returns:
        每组所需的最小样本量（整数）
    """
    from scipy import stats

    alpha = config.SIGNIFICANCE_LEVEL          # 显著性水平，默认 0.05
    z_alpha = stats.norm.ppf(1 - alpha / 2)    # 双侧检验的 z 值 ≈ 1.96
    z_beta = stats.norm.ppf(power)             # 功效对应的 z 值，power=0.8 时 ≈ 0.84

    p1 = baseline_rate                         # 对照组比例
    p2 = baseline_rate + min_detectable_effect  # 实验组预期比例
    p_pool = (p1 + p2) / 2                     # 合并比例

    # 样本量公式（比例差异检验的标准公式）
    n = (
        (z_alpha * np.sqrt(2 * p_pool * (1 - p_pool))
         + z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
        / (min_detectable_effect) ** 2
    )
    return int(np.ceil(n))                     # 向上取整，宁可多不能少


# ═══════════════════════════════════════════════════════════
# 4. 漏斗分析
# ═══════════════════════════════════════════════════════════
# 五步漏斗：下单→有商品→已支付→已交付→好评
# 每一步的转化率 + 环比变化 + 自动预警

def run_funnel_analysis() -> pd.DataFrame:
    """读取 sql/02_funnel_analysis.sql 并执行，返回逐月漏斗数据。
    18 行（18 个月），列：月份、下单用户数、各步转化率、环比变化、预警"""
    sql_path = os.path.join(config.SQL_DIR, "02_funnel_analysis.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def run_category_analysis() -> pd.DataFrame:
    """读取 sql/04_product_category_analysis.sql 并执行，返回品类贡献度数据。
    71 行（71 个品类），列：品类名、收入排名、总收入、收入占比、累计收入占比、品类分层"""
    sql_path = os.path.join(config.SQL_DIR, "04_product_category_analysis.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


# ═══════════════════════════════════════════════════════════
# 5. 月度业务概览
# ═══════════════════════════════════════════════════════════
# 看板顶部 KPI 卡片的数据来源（累计营收、总订单数、总买家数、客单价）

def monthly_summary() -> pd.DataFrame:
    """从数据库直接查询月度核心指标。
    ──────────────────────────
    不读 SQL 文件，因为逻辑简单（一个 SELECT + GROUP BY），内嵌即可。

    LEFT JOIN reviews 的原因：部分订单没有评论，如果 INNER JOIN 会丢掉这些订单。
    和漏斗 SQL 里的设计一致。

    返回 20 行（20 个月），列：month、orders、buyers、revenue、aov、avg_rating
    """
    conn = get_connection()
    query = """
        SELECT
            strftime('%Y-%m', o.order_purchase_timestamp) AS month,
            COUNT(DISTINCT o.order_id)                     AS orders,
            COUNT(DISTINCT o.customer_id)                  AS buyers,
            ROUND(SUM(oi.price + oi.freight_value), 2)     AS revenue,
            ROUND(AVG(oi.price + oi.freight_value), 2)     AS aov,
            ROUND(AVG(orv.review_score), 2)                AS avg_rating
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN order_reviews orv ON o.order_id = orv.order_id
        WHERE o.order_status = 'delivered'
            AND o.order_purchase_timestamp >= '2017-01-01'
        GROUP BY month
        ORDER BY month
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


# ═══════════════════════════════════════════════════════════
# 6. 一键运行所有分析
# ═══════════════════════════════════════════════════════════
# 命令行运行 python src/analysis.py 时自动调用
# 也可以在 notebook 里手动调用 run_all()

def run_all(output_format: str = "print") -> Dict[str, pd.DataFrame]:
    """运行全部 4 个分析模块 + 月度概览，打印摘要或返回数据字典。
    ──────────────────────────────────────────────
    调用顺序：
      1. RFM 分群（SQL）
      2. 月度概览
      3. 漏斗分析
      4. 品类分析

    注意：不包含 K-Means 聚类（因为需要 sklearn，且耗时较长）

    Parameters:
        output_format: "print" 打印摘要到控制台 / "dict" 静默返回数据
    Returns:
        字典：{"rfm": DataFrame, "monthly": DataFrame, "funnel": DataFrame, "category": DataFrame}
    """
    results = {}

    if output_format == "print":
        print("=" * 60)
        print("  电商用户行为与营收分析")
        print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

    # ── RFM ──
    results["rfm"] = run_rfm_analysis()
    if output_format == "print":
        print("\n── RFM 用户分群 ──")
        print(results["rfm"].to_string(index=False))

    # ── 月度概览 ──
    results["monthly"] = monthly_summary()
    if output_format == "print":
        print("\n── 月度核心指标 ──")
        print(results["monthly"].to_string(index=False))

    # ── 漏斗 ──
    results["funnel"] = run_funnel_analysis()
    if output_format == "print":
        print("\n── 最近 3 个月漏斗 ──")
        print(results["funnel"].tail(3).to_string(index=False))

    # ── 品类 ──
    results["category"] = run_category_analysis()
    if output_format == "print":
        print("\n── Top 10 品类 ──")
        print(results["category"].head(10).to_string(index=False))

    if output_format == "print":
        print("\n" + "=" * 60)
        print("  分析完成，所有结果已返回")

    return results


# 如果直接运行 python src/analysis.py，就执行全部分析
if __name__ == "__main__":
    run_all()
