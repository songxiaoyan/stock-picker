FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs

# 默认命令（使用极速版脚本）
CMD ["python3", "stock_picker_fast.py"]
