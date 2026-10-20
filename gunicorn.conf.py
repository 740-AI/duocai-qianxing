"""gunicorn 生产配置"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = 2
worker_class = "gthread"
timeout = 60
graceful_timeout = 20
max_requests = 2000          # 防内存泄漏
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
loglevel = "info"
