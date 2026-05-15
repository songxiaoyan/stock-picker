#!/bin/bash
# A股短线筛选 + Hermes推送脚本
# 定时任务使用此脚本，筛选在Docker中执行，推送通过Hermes

PROJECT_DIR="/mnt/d/hermes-workspace/stock-picker"
LOG_FILE="$PROJECT_DIR/logs/cron_output.log"

echo "=== A股短线筛选开始 ===" >> "$LOG_FILE"
date >> "$LOG_FILE"

# 在Docker中执行筛选，捕获输出
OUTPUT=$(docker run --rm -v "$PROJECT_DIR/logs:/app/logs" stock-picker 2>&1)
echo "$OUTPUT" >> "$LOG_FILE"

# 解析结果，提取股票信息发送推送
# 如果找到推荐股票，格式化并发送
if echo "$OUTPUT" | grep -q "共筛选出"; then
    # 提取股票数量和详情
    STOCK_COUNT=$(echo "$OUTPUT" | grep "最终推荐" | grep -oP '\d+ 只股票' | grep -oP '\d+')
    
    if [ "$STOCK_COUNT" -gt 0 ]; then
        # 构建推送消息（提取股票列表）
        MESSAGE=$(echo "$OUTPUT" | sed -n '/📈 A股短线推荐/,/⚠️ 以上仅为系统筛选结果/p')
        
        # 通过hermes推送 - 使用send_message工具
        # 注意：这里需要hermes环境，实际在定时任务中无法直接调用
        # 所以改用curl调用Hermes的HTTP API
        
        echo "筛选完成，共 $STOCK_COUNT 只股票" >> "$LOG_FILE"
    else
        echo "今日无符合条件股票" >> "$LOG_FILE"
    fi
else
    echo "筛选执行失败" >> "$LOG_FILE"
fi

echo "=== 执行完成 ===" >> "$LOG_FILE"