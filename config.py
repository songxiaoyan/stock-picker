# 股票筛选系统配置

# 微信ClawBot配置（从Hermes配置获取）
import os
WECHAT_BOT_URL = "https://ilinkai.weixin.qq.com"
WECHAT_BOT_TOKEN = os.environ.get("WEIXIN_TOKEN", "")
WECHAT_USER_ID = os.environ.get("WEIXIN_HOME_CHANNEL", "o9cq80yP9ApAsQJjehlbQRR8WlRw@im.wechat")
WECHAT_CONTEXT_TOKEN = os.environ.get("WEIXIN_TOKEN", "")

# 筛选参数
GAIN_MIN = 3.0      # 涨幅下限 %
GAIN_MAX = 5.0      # 涨幅上限 %
VOLUME_RATIO_MIN = 1.0  # 量比下限
TURNOVER_MIN = 5.0  # 换手率下限 %
TURNOVER_MAX = 10.0 # 换手率上限 %
MARKET_CAP_MIN = 50  # 流通市值下限 亿
MARKET_CAP_MAX = 200 # 流通市值上限 亿

# 均线周期
MA_PERIODS = [5, 10, 20]

# 日志
import os
LOG_DIR = "/app/logs" if os.path.exists("/app") else "logs"
LOG_FILE = os.path.join(LOG_DIR, "stock_picker.log")
