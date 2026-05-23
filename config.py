"""项目配置文件"""

import os

# ── 路径 ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
SQL_DIR = os.path.join(BASE_DIR, "sql")
NOTEBOOK_DIR = os.path.join(BASE_DIR, "notebooks")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
DB_PATH = os.path.join(DATA_DIR, "olist.db")

# ── 数据集下载地址 ───────────────────────────────────
DATASET_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
DATASET_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

# ── 分析参数 ──────────────────────────────────────────
RFM_DATE_REFERENCE = "2018-09-01"  # RFM 分析的参考日期
HIGH_VALUE_THRESHOLD = 150  # 高价值用户消费阈值（巴西雷亚尔）
SIGNIFICANCE_LEVEL = 0.05   # A/B 测试显著性水平
