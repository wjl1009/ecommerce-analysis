-- ════════════════════════════════════════════════════════
-- 品类贡献度分析（帕累托分析）
-- ════════════════════════════════════════════════════════
-- 目的：回答"钱从哪来"——哪些品类贡献了大部分收入？
-- 原理：按收入排名 → 算占比 → 算累计占比 → 分三层（核心/重要/长尾）
-- 输出：71 个品类的收入排名 + 累计占比 + 分层标签
-- ════════════════════════════════════════════════════════

WITH
-- ████████████████████████████████████████████████████████
-- 步骤1：统计每个品类的核心指标
-- ████████████████████████████████████████████████████████
-- 品类名字需要翻译（葡萄牙语→英语），所以 JOIN 了翻译表
-- ████████████████████████████████████████████████████████
品类基础指标 AS (
    SELECT
        t.product_category_name_english   AS 品类名,
        COUNT(DISTINCT o.order_id)        AS 订单数,
        COUNT(DISTINCT o.customer_id)     AS 购买人数,
        SUM(oi.price)                     AS 总收入,
        AVG(oi.price)                     AS 平均单价,
        ROUND(AVG(orv.review_score), 2)   AS 平均评分
    FROM products                       p
    JOIN product_category_translation   t  ON p.product_category_name = t.product_category_name
    JOIN order_items                    oi ON p.product_id = oi.product_id
    JOIN orders                         o  ON oi.order_id = o.order_id
    LEFT JOIN order_reviews             orv ON o.order_id = orv.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY t.product_category_name_english
),

-- ████████████████████████████████████████████████████████
-- 步骤2：排名 + 算占比 + 算累计占比
-- ████████████████████████████████████████████████████████
-- RANK()：按收入排名（同收入同名次）
-- SUM(收入) OVER()：所有品类的总收入（不加ORDER BY就是对全表求和）
-- SUM(收入) OVER(ORDER BY 收入 DESC ...)：按排名累加
--   第1名累计 = 第1名自己的收入
--   第2名累计 = 第1名 + 第2名的收入
--   第3名累计 = 第1名 + 第2名 + 第3名的收入 ...以此类推
-- ████████████████████████████████████████████████████████
品类排名 AS (
    SELECT
        *,
        -- 收入排名，按收入从高到低对品类排序
        RANK() OVER (ORDER BY 总收入 DESC) AS 收入排名,
        -- 单个品类占总收入的百分比
        ROUND(100.0 * 总收入 / SUM(总收入) OVER(), 2) AS 收入占比,
        -- 从第1名累加到当前行的累计占比
        ROUND(100.0 * SUM(总收入) OVER (
            ORDER BY 总收入 DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) / SUM(总收入) OVER(), 1) AS 累计收入占比
    FROM 品类基础指标
)
--  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW 的意思是"从第一行累加到当前行"，这是滚动求和的标准写法



-- ████████████████████████████████████████████████████████
-- 步骤3：输出 + 帕累托分层
-- ████████████████████████████████████████████████████████
-- 帕累托原则（二八法则）：
--   前50%收入 → 核心品类（重点投入，保供货保体验）
--   50-80%    → 重要品类（正常维护）
--   后20%     → 长尾品类（评估是否值得继续运营）
-- ████████████████████████████████████████████████████████
SELECT
    品类名,
    收入排名,
    订单数,
    购买人数,
    ROUND(总收入, 2)   AS 总收入,
    收入占比,
    累计收入占比,
    平均单价,
    平均评分,
    CASE
        WHEN 累计收入占比 <= 50 THEN '核心品类（贡献前50%收入）'
        WHEN 累计收入占比 <= 80 THEN '重要品类（贡献50-80%收入）'
        ELSE                         '长尾品类'
    END AS 品类分层
FROM 品类排名
ORDER BY 总收入 DESC;
