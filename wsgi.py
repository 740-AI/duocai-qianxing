"""WSGI 入口（生产环境用 gunicorn 加载）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

from server import app, init_db  # noqa: E402

init_db()  # 启动时确保表结构存在

application = app
