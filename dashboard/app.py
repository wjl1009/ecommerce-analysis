"""
电商用户行为与营收分析 — 交互看板
═══════════════════════════════════════════
启动方式：
    streamlit run dashboard/app.py

部署到 Streamlit Cloud 后可直接用浏览器演示。
───────────────────────────────────────────
页面结构（4 个 Tab）：
  1. 营收趋势 & 漏斗  → 月度营收柱+线图 + 漏斗转化率 + 预警
  2. RFM 用户分群     → 树图 + 柱图 + 详情表
  3. 品类分析         → 品类收入排名 + 价格vs评分气泡图 + 帕累托图
  4. 卖家同期群留存   → 留存热力图 + 留存曲线

数据来源：src/analysis.py 里的函数 → 4 个 SQL 文件 → data/olist.db
刷新机制：侧边栏"刷新数据"按钮清除缓存 / 1 小时自动过期
"""

import sys
import os

# 把项目根目录加入 Python 搜索路径，确保能 import src.analysis
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 导入所有分析函数（一个函数对应一类分析）
from src.analysis import (
    run_rfm_analysis,           # SQL: 01_rfm_segmentation.sql
    run_funnel_analysis,        # SQL: 02_funnel_analysis.sql
    run_category_analysis,      # SQL: 04_product_category_analysis.sql
    run_cohort_retention,       # SQL: 03_cohort_retention.sql
    monthly_summary,            # 内嵌 SQL
    cohort_retention_pivot,     # 调用 run_cohort_retention 后透视
    rfm_kmeans_clustering,      # Python K-Means（和 SQL RFM 互为补充）
    ab_test_summary,            # Python 统计检验
)


# ═══════════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="电商用户行为与营收分析",
    page_icon="🛒",
    layout="wide",                # 宽屏布局，充分利用横向空间
    initial_sidebar_state="expanded",  # 默认展开侧边栏
)

st.title("🛒 电商用户行为与营收分析")
st.caption("Brazilian E-Commerce (Olist) | 数据分析师项目作品")


# ═══════════════════════════════════════════════════════════
# 侧边栏 — 数据加载 & 项目说明
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 控制面板")

    # 点击后清除所有缓存，下次加载数据时重新查数据库
    if st.button("🔄 刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("""
    **技术栈**
    - SQLite + SQL 窗口函数
    - Python (pandas/scikit-learn)
    - Plotly 交互图表
    - Streamlit 看板

    **数据集**
    - Brazilian E-Commerce
    - 10 万+ 订单 | 9.6 万客户 | 3,095 卖家
    - Kaggle Public Dataset
    """)


# ═══════════════════════════════════════════════════════════
# 数据加载（带缓存）
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)   # ttl=3600：1 小时后缓存自动过期
def load_all_data():
    """一次性加载所有分析数据。
    ────────────────────────
    为什么用 @st.cache_data 缓存？
      每次切换 Tab 或交互，Streamlit 会重新运行整个脚本。
      如果不缓存，每次都要重新执行 5 个 SQL 查询——慢且浪费。
      ttl=3600 保证数据每 1 小时刷新一次（也可以手动点刷新按钮）。

    返回的字典里 6 个 key：
      monthly       → Tab 1 营收趋势
      rfm           → Tab 2 RFM 分群树图 + 详情
      funnel        → Tab 1 漏斗 + 预警
      category      → Tab 3 品类分析
      cohort_pivot  → Tab 4 留存矩阵
      clusters      → Tab 2 K-Means 聚类（备用）
    """
    return {
        "monthly": monthly_summary(),
        "rfm": run_rfm_analysis(),
        "funnel": run_funnel_analysis(),
        "category": run_category_analysis(),
        "cohort_pivot": cohort_retention_pivot(),
        "clusters": rfm_kmeans_clustering(),
    }


# 执行数据加载（首次运行或缓存过期后）
data = load_all_data()


# ═══════════════════════════════════════════════════════════
# 顶部 KPI 卡片
# ═══════════════════════════════════════════════════════════
# 4 个数字卡片，一屏看完平台的核心指标
# 数据来自 monthly_summary()（按月的聚合数据，这里再 SUM 求总计）

monthly = data["monthly"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    total_rev = monthly["revenue"].sum()
    st.metric("累计营收", f"R$ {total_rev:,.0f}")
with col2:
    total_orders = monthly["orders"].sum()
    st.metric("总订单数", f"{total_orders:,}")
with col3:
    total_buyers = monthly["buyers"].sum()
    st.metric("总买家数", f"{total_buyers:,}")
with col4:
    avg_aov = (monthly["revenue"].sum() / monthly["orders"].sum()) if total_orders > 0 else 0
    st.metric("客单价", f"R$ {avg_aov:,.2f}")


# ═══════════════════════════════════════════════════════════
# 4 个 Tab 页签
# ═══════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 营收趋势 & 漏斗",
    "👤 RFM 用户分群",
    "📦 品类分析",
    "🔄 卖家同期群留存",
])


# ──────────────────────────────────────────────────────────
# Tab 1: 营收趋势 & 漏斗
# ──────────────────────────────────────────────────────────
with tab1:
    st.subheader("月度营收与订单趋势")

    col_left, col_right = st.columns([2, 1])   # 左 2/3 宽，右 1/3 窄

    # ── 左侧：营收（柱）+ 订单数（线）双轴图 ──
    with col_left:
        fig = make_subplots(specs=[[{"secondary_y": True}]])  # 声明双 Y 轴

        # 柱状图：营收（左 Y 轴）
        fig.add_trace(
            go.Bar(
                x=monthly["month"], y=monthly["revenue"],
                name="营收 (R$)", marker_color="#636EFA",
            ),
            secondary_y=False,
        )

        # 折线图：订单数（右 Y 轴）
        fig.add_trace(
            go.Scatter(
                x=monthly["month"], y=monthly["orders"],
                name="订单数", mode="lines+markers",
                marker_color="#EF553B", line=dict(width=2),
            ),
            secondary_y=True,
        )

        fig.update_layout(height=400, hovermode="x unified", title="营收（柱）& 订单数（线）")
        fig.update_xaxes(title_text="")
        fig.update_yaxes(title_text="营收 (R$)", secondary_y=False)
        fig.update_yaxes(title_text="订单数", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

    # ── 右侧：最新一个月的漏斗转化 ──
    with col_right:
        funnel = data["funnel"]
        latest_funnel = funnel.tail(1).iloc[0]   # 取最后一行（最新月）

        st.markdown("**最新月漏斗转化**")
        # 5 个步骤，每步显示人数 + 相对于第 1 步的整体转化率
        funnel_steps = [
            ("下单",   int(latest_funnel["下单用户数"])),
            ("有商品", int(latest_funnel["有商品用户数"])),
            ("已支付", int(latest_funnel["已支付用户数"])),
            ("已交付", int(latest_funnel["已交付用户数"])),
            ("好评",   int(latest_funnel["好评用户数"])),
        ]
        for name, val in funnel_steps:
            pct = f"{val / funnel_steps[0][1] * 100:.1f}%" if funnel_steps[0][1] > 0 else "N/A"
            st.metric(name, f"{val:,}", pct)

    st.divider()

    # ── 预警列表 ──
    # 从 funnel 表里筛选出"预警"列不等于"正常"的行
    st.subheader("月度预警")
    alerts = funnel[funnel["预警"] != "正常"][["月份", "下单环比变化", "预警"]]
    if not alerts.empty:
        st.dataframe(alerts, use_container_width=True, hide_index=True)
    else:
        st.success("最近月份无异常预警")


# ──────────────────────────────────────────────────────────
# Tab 2: RFM 用户分群
# ──────────────────────────────────────────────────────────
with tab2:
    st.subheader("RFM 用户价值分群")

    rfm = data["rfm"]

    col_a, col_b = st.columns(2)

    # ── 左侧：树图（Treemap）──
    # 面积 = 用户数，颜色深度 = 收入贡献
    with col_a:
        fig = px.treemap(
            rfm,
            path=["用户群体"],            # 按用户群体分组
            values="用户数",              # 面积代表该群体的人数
            color="群体总收入",           # 颜色代表该群体的收入贡献
            color_continuous_scale="Blues",
            title="用户分群树图（面积=用户数，颜色=收入贡献）",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # ── 右侧：柱状图 — 各群体平均消费金额 ──
    with col_b:
        fig = px.bar(
            rfm,
            x="用户群体", y="人均消费",
            color="用户群体",
            title="各群组平均消费金额",
            text_auto=".0f",               # 柱上显示数值，保留 0 位小数
        )
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── 详情表格 ──
    st.subheader("RFM 分群详情")
    st.dataframe(
        rfm.style.format({
            "平均距今天数": "{:.0f}",          # 天数显示整数
            "平均购买次数": "{:.1f}",          # 次数保留 1 位小数
            "人均消费": "R$ {:.2f}",           # 金额加 R$ 前缀
            "群体总收入": "R$ {:.2f}",
            "人数占比": "{:.1f}%",             # 百分比保留 1 位小数
        }),
        use_container_width=True,
        hide_index=True,                      # 隐藏 DataFrame 自带的行号
    )

    st.info(
        "面试讲解要点：高价值用户占比虽小但贡献了大部分收入；"
        "流失风险用户需要推送优惠券召回；SQL 中使用了 NTILE 窗口函数 + 多层 CTE。"
    )


# ──────────────────────────────────────────────────────────
# Tab 3: 品类分析（帕累托）
# ──────────────────────────────────────────────────────────
with tab3:
    st.subheader("品类贡献度分析（帕累托）")

    category = data["category"]

    # 滑块：让用户自己选择显示多少个品类（5~30，默认 15）
    top_n = st.slider("显示 Top N 品类", 5, 30, 15)
    cat_top = category.head(top_n)

    col_c, col_d = st.columns(2)

    # ── 左侧：品类收入排名柱图 ──
    with col_c:
        fig = px.bar(
            cat_top,
            x="品类名", y="总收入",
            color="品类分层",           # 不同分层不同颜色（核心/重要/长尾）
            text_auto=".0f",
            title="品类收入排名",
        )
        fig.update_layout(height=500, xaxis_tickangle=-45)  # 标签倾斜 45 度，避免重叠
        st.plotly_chart(fig, use_container_width=True)

    # ── 右侧：价格 vs 评分 气泡图 ──
    # X=平均单价, Y=平均评分, 气泡大小=订单数, 颜色=品类分层
    with col_d:
        fig = px.scatter(
            cat_top,
            x="平均单价", y="平均评分",
            size="订单数", color="品类分层",
            hover_name="品类名",         # 悬停时显示品类名
            title="品类价格 vs 评分（气泡=订单量）",
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── 帕累托图 ──
    # 柱图 = 每个品类的收入（左 Y 轴），折线 = 累计占比（右 Y 轴）
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 收入柱图
    fig.add_trace(
        go.Bar(
            x=category["品类名"], y=category["总收入"],
            name="收入", marker_color="#636EFA",
        ),
        secondary_y=False,
    )

    # 累计占比折线
    fig.add_trace(
        go.Scatter(
            x=category["品类名"], y=category["累计收入占比"],
            name="累计占比 %", mode="lines+markers",
            line=dict(color="#EF553B", width=2),
        ),
        secondary_y=True,
    )

    # 添加 80% 参考线（帕累托原则的分界线）
    fig.add_hline(
        y=80, line_dash="dash", line_color="gray",
        secondary_y=True, annotation_text="80% 线",
    )
    fig.update_layout(height=400, title="帕累托分析（80% 收入来自哪些品类？）")
    fig.update_xaxes(tickangle=-45, showticklabels=False)  # 品类太多，隐藏 X 轴标签
    fig.update_yaxes(title_text="收入 (R$)", secondary_y=False)
    fig.update_yaxes(title_text="累计占比 %", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────
# Tab 4: 卖家同期群留存
# ──────────────────────────────────────────────────────────
with tab4:
    st.subheader("卖家同期群留存矩阵")
    st.caption(
        "数据说明：Olist 数据集客户无复购（每客户仅1单），"
        "因此留存分析改用卖家维度。卖家持续接单是 marketplace 健康度的核心指标。"
    )

    pivot = data["cohort_pivot"]   # 透视表：行=同期群月份, 列=第N月, 值=留存率

    if not pivot.empty:
        # ── 留存热力图 ──
        # px.imshow 直接渲染矩阵：颜色越绿→留存越高，颜色越红→留存越低
        fig = px.imshow(
            pivot.values,                           # 二维数组
            x=pivot.columns, y=pivot.index,         # X 和 Y 轴标签
            color_continuous_scale="RdYlGn",        # 红黄绿配色
            text_auto=".0f",                        # 格子上显示数值
            aspect="auto",
            title="卖家月度同期群留存率（%）",
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

        # ── 留存曲线 ──
        # 每个同期群画一条线，X=第N月，Y=留存率
        st.subheader("卖家留存曲线对比")
        fig = go.Figure()
        for idx, row in pivot.iterrows():
            fig.add_trace(go.Scatter(
                x=row.index, y=row.values,
                mode="lines+markers", name=idx,
                hovertemplate=f"Cohort: {idx}<br>Month %{{x}}: %{{y:.0f}}%<extra></extra>",
            ))
        fig.update_layout(
            height=400,
            xaxis_title="第 N 月",
            yaxis_title="留存率 (%)",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("留存数据不足，请先运行数据加载。")

    st.info(
        "面试讲解要点：同期群分析使用 SQL 自 JOIN + GROUP BY 生成留存矩阵；"
        "卖家第 1 月留存 55-71%，远好于用户留存；"
        "2017-06 同期群异常（第 1 月仅 43%）需排查；"
        "留存曲线呈渐进衰减而非断崖式，说明卖家有持续经营动力。"
    )


# ═══════════════════════════════════════════════════════════
# 底部
# ═══════════════════════════════════════════════════════════
st.divider()
st.caption("Built with Streamlit + Plotly | 数据来源：Olist Brazilian E-Commerce (Kaggle)")
