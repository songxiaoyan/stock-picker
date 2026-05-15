#!/bin/bash
# 启动cron服务
cron

# 保持容器运行
tail -f /app/logs/stock_picker.log
