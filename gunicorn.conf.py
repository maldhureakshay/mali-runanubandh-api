"""
Gunicorn configuration for Matrimony API production deployment.
Uses Uvicorn workers for async ASGI support.
"""
import multiprocessing

# Bind to localhost — Nginx will proxy to this
bind = "127.0.0.1:8000"

# Worker configuration
# For small instances (t3.micro/small): use 2 workers
# For larger instances: use (2 × CPU cores) + 1
# workers = multiprocessing.cpu_count() * 2 + 1
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout (seconds) — increase for slow geospatial queries
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "/var/log/matrimony-api/access.log"
errorlog = "/var/log/matrimony-api/error.log"
loglevel = "info"

# Process naming
proc_name = "matrimony-api"

# Security
limit_request_line = 8190
limit_request_fields = 100
