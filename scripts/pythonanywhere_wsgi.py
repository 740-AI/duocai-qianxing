"""
PythonAnywhere WSGI 配置模板
==============================
使用方法：把本文件内容**整体替换**到 PythonAnywhere 的
  Web → WSGI configuration file（路径形如 /var/www/你的用户名_pythonanywhere_com_wsgi.py）
中的内容，然后按注释改两处：USERNAME 与项目路径。
"""

import sys
import os

# ========== 需要确认的一处 ==========
USERNAME = "YOUR_USERNAME"          # ← 改成你的 PythonAnywhere 用户名（小写）
PROJECT = f"/home/{USERNAME}/duocai-qianxing"
# =====================================

if PROJECT not in sys.path:
    sys.path.insert(0, os.path.join(PROJECT, "app"))
    sys.path.insert(0, PROJECT)

# 数据库放到项目 data 目录（PythonAnywhere 免费版磁盘持久，重启不丢）
os.environ.setdefault("QX_DB", os.path.join(PROJECT, "data", "app.db"))

os.environ["FLASK_ENV"] = "production"

from server import app as _flask_app, init_db  # noqa: E402

init_db()  # 确保表结构存在（首次访问时执行，幂等）

# PythonAnywhere 需要一个名为 application 的 WSGI 可调用对象
application = _flask_app
