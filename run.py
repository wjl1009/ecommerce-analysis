"""项目主入口

用法:
    python run.py              # 运行全部分析并打印结果
    python run.py load         # 仅加载数据到数据库
    python run.py dashboard    # 启动 Streamlit 看板
    python run.py notebook     # 启动 Jupyter
"""

import sys
import os
import subprocess


def cmd_load():
    """加载数据"""
    print(">> 加载数据并构建数据库...")
    from src.data_loader import check_raw_data, build_database, run_quality_check
    if not check_raw_data():
        print("\n请先从 Kaggle 下载数据集：")
        print("  https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        print(f"\n将下载的 CSV 文件放入: {os.path.join(os.path.dirname(__file__), 'data', 'raw')}")
        sys.exit(1)
    build_database()
    run_quality_check()


def cmd_analyze():
    """运行分析"""
    print(">> 运行核心分析...")
    from src.analysis import run_all
    run_all(output_format="print")


def cmd_dashboard():
    """启动看板"""
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    subprocess.run(["streamlit", "run", dashboard_path])


def cmd_notebook():
    """启动 Jupyter"""
    notebook_dir = os.path.join(os.path.dirname(__file__), "notebooks")
    subprocess.run(["jupyter", "notebook", "--notebook-dir", notebook_dir])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        cmd_analyze()
    elif sys.argv[1] == "load":
        cmd_load()
    elif sys.argv[1] == "dashboard":
        cmd_dashboard()
    elif sys.argv[1] == "notebook":
        cmd_notebook()
    else:
        print(f"未知命令: {sys.argv[1]}")
        print("用法: python run.py [load|dashboard|notebook]")
