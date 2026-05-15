# A股短线T+1股票筛选系统

## 系统概述
基于"8步选股法"的A股短线交易系统，适合T+1交易（当天买入，次日卖出）。

## 筛选策略

| 步骤 | 条件 | 说明 |
|------|------|------|
| 1 | 涨幅 3%~5% | 走势强劲但不过高 |
| 2 | 量比 > 1 | 成交活跃，有资金关注 |
| 3 | 换手率 5%~10% | 关注度适中 |
| 4 | 流通市值 50亿~200亿 | 盘子适中，易拉升 |
| 5 | 成交量阶梯放量 | 近5日持续放大 |
| 6 | 均线多头排列 | 5/10/20日均线向上 |
| 7 | 强于大盘 | 涨幅超过上证指数 |
| 8 | 尾盘买入时机 | 14:30后表现强势 |

## 快速开始

### 方式1：Web界面（推荐）

```bash
cd /mnt/d/hermes-workspace/stock-picker/web

# 安装依赖
pip install flask flask-cors --break-system-packages

# 启动Web服务
python app.py

# 访问：http://localhost:5000
```

### 方式2：Docker运行

```bash
cd /mnt/d/hermes-workspace/stock-picker

# 构建镜像
docker build -t stock-picker .

# 运行筛选
docker run --rm -v $(pwd)/logs:/app/logs stock-picker
```

### 方式3：命令行直接运行

```bash
cd /mnt/d/hermes-workspace/stock-picker

# 运行
python3 stock_picker.py
```

## Web界面功能

访问 `http://localhost:5000` 可使用Web管理界面：

1. **实时筛选** - 点击"立即筛选"按钮执行选股
2. **结果展示** - 表格形式展示符合条件的股票
3. **定时设置** - 设置自动运行时间和频率
4. **日志查看** - 实时查看运行日志
5. **状态监控** - 显示系统运行状态

## 微信通知配置

已配置通过Hermes微信ClawBot推送通知：
- **Bot地址**: https://ilinkai.weixin.qq.com
- **用户ID**: o9cq80yP9ApAsQJjehlbQRR8WlRw@im.wechat

配置信息已保存在 `config.py` 中，无需额外设置。

## 定时任务

### Linux/Mac (crontab)
```bash
# 每个交易日14:30运行
30 14 * * 1-5 cd /mnt/d/hermes-workspace/stock-picker && docker run --rm -v $(pwd)/logs:/app/logs stock-picker
```

### Windows 任务计划程序
1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：每周一至周五 14:30
4. 操作：启动程序 `docker run --rm -v D:\hermes-workspace\stock-picker\logs:/app/logs stock-picker`

## 目录结构
```
stock-picker/
├── config.py              # 配置文件
├── stock_picker.py        # 主程序
├── Dockerfile             # Docker镜像
├── requirements.txt       # Python依赖
├── web/                   # Web管理界面
│   ├── app.py             # Flask后端
│   ├── templates/         # HTML模板
│   └── static/            # 静态文件
├── logs/                  # 运行日志
└── README.md              # 说明文档
```

## 运行日志
- 日志文件：`logs/stock_picker.log`
- 查看日志：`tail -f logs/stock_picker.log`

## 测试结果
系统已成功测试运行，示例输出：
```
📈 A股短线推荐 (2026-05-09 11:29)

共筛选出 2 只股票：

1. sz.002676
   价格：8.15  涨幅：4.35%
   换手率：8.72%  量比：1.63
   流通市值：58.68亿

2. sz.300397
   价格：13.88  涨幅：3.50%
   换手率：9.78%  量比：1.71
   流通市值：56.65亿
```

## 注意事项
- 数据源：baostock（免费、稳定）
- 自动识别交易日（跳过周末和节假日）
- 全市场扫描约需5分钟
- 筛选结果仅供参考

## 免责声明
本系统仅为技术实现演示，不构成任何投资建议。股市有风险，投资需谨慎！
