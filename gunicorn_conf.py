import multiprocessing, os

bind = os.getenv("WEB_CONCURRENCY_BIND", "0.0.0.0:8000")
workers = int(os.getenv("WEB_CONCURRENCY", (multiprocessing.cpu_count() * 2) + 1))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("WEB_TIMEOUT", 30))
graceful_timeout = int(os.getenv("WEB_GRACEFUL_TIMEOUT", 30))
keepalive = 5
accesslog = "-"
errorlog = "-"
