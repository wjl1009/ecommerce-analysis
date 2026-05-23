"""Streamlit Cloud 入口 — 指向 dashboard/app.py"""
import runpy
runpy.run_path("dashboard/app.py", run_name="__main__")
