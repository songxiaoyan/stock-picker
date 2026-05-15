#!/bin/bash
# 股票筛选系统定时任务设置脚本

# 获取当前crontab内容
CURRENT_CRON=$(crontab -l 2>/dev/null)

# 新的定时任务
NEW_TASK="30 14 * * 1-5 cd /mnt/d/hermes-workspace/stock-picker && docker run --rm -v /mnt/d/hermes-workspace/stock-picker/logs:/app/logs stock-picker >> /mnt/d/hermes-workspace/stock-picker/logs/cron_output.log 2>&1"

# 检查是否已存在
if echo "$CURRENT_CRON" | grep -q "stock-picker"; then
    echo "定时任务已存在，跳过添加"
else
    # 添加新任务
    (echo "$CURRENT_CRON"; echo "$NEW_TASK") | crontab -
    echo "定时任务添加成功！"
    echo "运行时间：每周一至周五 14:30"
    echo "查看任务：crontab -l"
fi
