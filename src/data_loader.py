"""数据加载与数据库初始化

从 CSV 文件加载 Olist 数据集，建立 SQLite 数据库并做基础清洗。

数据来源：Brazilian E-Commerce Public Dataset by Olist (Kaggle)
下载地址：https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

用法：
    python src/data_loader.py
"""

# cd C:\Users\86139\ecommerce-analysis

import os
import sys
#用于输出规范的运行日志
import logging
# Python 自带的数据库接口
import sqlite3
import pandas as pd
from pathlib import Path

# 强行把项目根目录加入 Python 的搜索范围，从而让你能顺利导入位于根目录下的 config.py 文件
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── CSV → 数据库表 映射 ─────────────────────────────────────
# 遍历这个字典，每个 CSV 对应一张表。

TABLE_MAP = {
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_orders_dataset.csv": "orders",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "product_category_translation",
}


def check_raw_data() -> bool:
    """检查 raw 目录下是否存在所有需要的 CSV 文件"""
    missing = []
    for f in config.DATASET_FILES:
        if not os.path.exists(os.path.join(config.RAW_DIR, f)):
            missing.append(f)
    if missing:
        logger.error("缺少以下数据文件，请从 Kaggle 下载后放入 %s：", config.RAW_DIR)
        logger.error("下载地址：%s", config.DATASET_URL)
        for f in missing:
            logger.error("  ✗ %s", f)
        return False
    logger.info("✓ 所有数据文件已就绪 (%d 个)", len(config.DATASET_FILES))
    return True


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
     """清洗客户表"""
     # 按customer_unique_id去重
     df = df.drop_duplicates(subset="customer_unique_id")
     return df


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """清洗订单表：解析日期、处理缺失"""
    date_cols = [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            # 文本内容先统一转换成小写，并去除首尾的空格
    df["order_status"] = df["order_status"].str.lower().str.strip()
    return df


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    """清洗订单商品表"""
    # 转换为时间类型
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    return df


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """清洗评论表"""
    if "review_comment_title" in df.columns:
        df["review_comment_title"] = df["review_comment_title"].fillna("")
    if "review_comment_message" in df.columns:
        df["review_comment_message"] = df["review_comment_message"].fillna("")
    return df


def clean_geolocation(df: pd.DataFrame) -> pd.DataFrame:
    """清洗地理信息表：去重"""
    return df.drop_duplicates(subset=["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"])


CLEANERS = {
    "customers": clean_customers,
    "orders": clean_orders,
    "order_items": clean_order_items,
    "order_reviews": clean_reviews,
    "geolocation": clean_geolocation,
}


def build_database() -> None:
    """主流程：读取 CSV → 清洗 → 写入 SQLite"""
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
        logger.info("已删除旧数据库")

    conn = sqlite3.connect(config.DB_PATH)

    for csv_file, table_name in TABLE_MAP.items():
        csv_path = os.path.join(config.RAW_DIR, csv_file)    # data/raw/xxx.csv
        logger.info("加载 %s → %s", csv_file, table_name)

        df = pd.read_csv(csv_path)

        cleaner = CLEANERS.get(table_name)
        if cleaner:
            df = cleaner(df)
            logger.info("  清洗完成: %d 行 %d 列", len(df), len(df.columns))
            # 直接把DataFrame写入SQLite，表名就是TABLE_MAP里的名字
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        logger.info("  写入完成: %d 行", len(df))

    conn.close()
    logger.info("✓ 数据库构建完成: %s", config.DB_PATH)


def run_quality_check() -> None:
    """数据质量报告"""
    conn = sqlite3.connect(config.DB_PATH)
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn)

    print("\n" + "=" * 60)
    print("  数据质量报告")
    print("=" * 60)

    for t in tables["name"]:
        row_count = pd.read_sql(f"SELECT COUNT(*) AS n FROM [{t}]", conn)["n"][0]
        col_info = pd.read_sql(f"PRAGMA table_info([{t}])", conn)
        nulls = []
        for col in col_info["name"]:
            n_null = row_count - pd.read_sql(
                f'SELECT COUNT([{col}]) AS n FROM [{t}]', conn
            )["n"][0]
            if n_null > 0:
                nulls.append(f"{col}({n_null})")
        null_str = ", ".join(nulls) if nulls else "无缺失"
        print(f"  [{t:35s}] {row_count:>8,d} 行 | 缺失: {null_str}")

    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    if not check_raw_data():
        sys.exit(1)
    build_database()
    run_quality_check()
