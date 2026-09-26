"""资源路径：兼容源码运行与 PyInstaller 打包"""

import os
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(app_dir(), name)


def user_data_dir() -> str:
    """可写目录：备份、导出默认位置"""
    d = os.path.join(os.environ.get("APPDATA", app_dir()), "OpenIME")
    os.makedirs(d, exist_ok=True)
    return d
