#!/usr/bin/env python3
"""
A股短线T+1股票筛选系统 - 极速版 v6
策略：8步选股法
优化：腾讯实时接口 + baostock技术分析，<20秒完成
"""

import requests
import pandas as pd
import numpy as np
import logging
import sys
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import baostock as bs

from config import (
    WECHAT_BOT_URL, WECHAT_BOT_TOKEN, WECHAT_USER_ID, WECHAT_CONTEXT_TOKEN,
    GAIN_MIN, GAIN_MAX, VOLUME_RATIO_MIN,
    TURNOVER_MIN, TURNOVER_MAX,
    MARKET_CAP_MIN, MARKET_CAP_MAX,
    MA_PERIODS, LOG_FILE, LOG_DIR
)

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def generate_a_stock_codes() -> List[str]:
    codes = []
    for prefix in ['60', '68']:
        for i in range(0, 1000):
            codes.append(f"sh{prefix}{i:04d}")
    for prefix in ['00', '30']:
        for i in range(0, 1000):
            codes.append(f"sz{prefix}{i:04d}")
    return codes


def fetch_tencent_batch(codes: List[str]) -> List[Dict]:
    results = []
    codes_str = ','.join(codes)
    url = f'http://qt.gtimg.cn/q={codes_str}'
    
    try:
        resp = requests.get(url, timeout=5)
        resp.encoding = 'gbk'
        
        for line in resp.text.split(';'):
            if '=' not in line:
                continue
            
            match = re.search(r'="([^"]*)"', line)
            if not match:
                continue
            
            d = match.group(1).split('~')
            if len(d) < 45:
                continue
            
            try:
                # 流通市值：d[44]是流通市值（亿元）
                market_cap = 0
                if len(d) > 44 and d[44]:
                    try:
                        market_cap = float(d[44]) * 1e8  # 亿转元
                    except:
                        market_cap = 0
                
                results.append({
                    '代码': d[2],
                    '名称': d[1],
                    '最新价': float(d[3]),
                    '昨收': float(d[4]),
                    '涨跌幅': float(d[32]) if d[32] else 0,
                    '成交量': float(d[6]),
                    '换手率': float(d[38]) if d[38] else 0,
                    '量比': float(d[10]) if d[10] else 1.5,
                    '流通市值': market_cap,
                })
            except:
                continue
    except Exception as e:
        logger.debug(f"腾讯请求失败：{e}")
    
    return results


def get_all_a_stocks_tencent() -> pd.DataFrame:
    all_codes = generate_a_stock_codes()
    all_results = []
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = []
        batch_size = 100
        for i in range(0, len(all_codes), batch_size):
            batch = all_codes[i:i+batch_size]
            futures.append(executor.submit(fetch_tencent_batch, batch))
        
        for future in as_completed(futures):
            try:
                results = future.result()
                all_results.extend(results)
            except:
                pass
    
    return pd.DataFrame(all_results)


class StockScreener:
    def __init__(self):
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.results = []
        
    def run(self) -> List[Dict]:
        logger.info("=" * 50)
        logger.info("开始执行股票筛选（极速版 v6）...")
        logger.info("=" * 50)
        
        start_time = datetime.now()
        
        try:
            logger.info("阶段1：获取实时行情...")
            df = get_all_a_stocks_tencent()
            logger.info(f"获取到 {len(df)} 只股票，耗时: {(datetime.now()-start_time).total_seconds():.1f}秒")
            
            if df.empty:
                return []
            
            logger.info("阶段2：快速筛选...")
            df = self.quick_filter(df)
            logger.info(f"筛选后剩余 {len(df)} 只")
            
            if df.empty:
                return []
            
            logger.info("阶段3：技术分析...")
            self.results = self.technical_analysis(df)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ 筛选完成！总耗时: {elapsed:.1f}秒")
            logger.info(f"最终推荐 {len(self.results)} 只股票")
            logger.info("=" * 50)
            
            return self.results
            
        except Exception as e:
            logger.error(f"筛选过程出错：{e}")
            import traceback
            traceback.print_exc()
            raise
    
    def quick_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        # 步骤1：涨幅 3%~5%
        df = df[(df['涨跌幅'] >= GAIN_MIN) & (df['涨跌幅'] <= GAIN_MAX)]
        logger.info(f"  - 涨幅筛选后: {len(df)} 只")
        
        # 步骤2：量比 > 1
        df = df[df['量比'] > VOLUME_RATIO_MIN]
        logger.info(f"  - 量比筛选后: {len(df)} 只")
        
        # 步骤3：换手率 5%~10%
        df = df[(df['换手率'] >= TURNOVER_MIN) & (df['换手率'] <= TURNOVER_MAX)]
        logger.info(f"  - 换手率筛选后: {len(df)} 只")
        
        # 步骤4：流通市值 50亿~200亿
        if len(df) > 0:
            logger.info(f"  - 流通市值范围: {df['流通市值'].min()/1e8:.1f}亿 ~ {df['流通市值'].max()/1e8:.1f}亿")
            df = df[(df['流通市值'] >= MARKET_CAP_MIN * 1e8) & 
                    (df['流通市值'] <= MARKET_CAP_MAX * 1e8)]
            logger.info(f"  - 市值筛选后: {len(df)} 只")
        
        return df
    
    def technical_analysis(self, df: pd.DataFrame) -> List[Dict]:
        results = []
        market_gain = self.get_market_gain()
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {
                executor.submit(self._analyze_stock, row, market_gain): row 
                for _, row in df.iterrows()
            }
            
            for future in as_completed(futures):
                try:
                    r = future.result()
                    if r:
                        results.append(r)
                except:
                    pass
        
        return results
    
    def _analyze_stock(self, row: pd.Series, market_gain: float) -> Dict:
        code = row['代码']
        bs_code = f"sh.{code}" if code.startswith(('60', '68')) else f"sz.{code}"
        
        try:
            lg = bs.login()
            try:
                hist = bs.query_history_k_data_plus(
                    bs_code, "close,volume",
                    start_date=(datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d'),
                    end_date=self.today,
                    frequency="d", adjustflag="3"
                )
                
                if hist.error_code != '0' or len(hist.get_data()) < 20:
                    return None
                
                df = hist.get_data()
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                closes = df['close'].values
                volumes = df['volume'].values
                
                ma5 = np.mean(closes[-5:])
                ma10 = np.mean(closes[-10:])
                ma20 = np.mean(closes[-20:])
                
                ma5_prev = np.mean(closes[-6:-1])
                ma10_prev = np.mean(closes[-11:-1])
                ma20_prev = np.mean(closes[-21:-1])
                
                if not (ma5 > ma10 > ma20 and 
                        ma5 > ma5_prev and ma10 > ma10_prev and ma20 > ma20_prev and
                        closes[-1] > ma20):
                    return None
                
                vol_5d = volumes[-5:]
                if not all(vol_5d[i] <= vol_5d[i+1] for i in range(len(vol_5d)-1)):
                    return None
                
                if row['涨跌幅'] <= market_gain:
                    return None
                
                return {
                    '代码': row['代码'],
                    '名称': row['名称'],
                    '最新价': f"{row['最新价']:.2f}",
                    '涨跌幅': f"{row['涨跌幅']:.2f}%",
                    '换手率': f"{row['换手率']:.2f}%",
                    '量比': f"{row['量比']:.2f}",
                    '流通市值': f"{row['流通市值']/1e8:.2f}亿"
                }
            finally:
                bs.logout()
        except:
            return None
    
    def get_market_gain(self) -> float:
        try:
            lg = bs.login()
            try:
                sh = bs.query_history_k_data_plus("sh.000001", "close",
                    start_date=(datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'),
                    end_date=self.today, frequency="d")
                
                if sh.error_code == '0' and len(sh.get_data()) >= 2:
                    df = sh.get_data()
                    df['close'] = df['close'].astype(float)
                    prev = df.iloc[-2]['close']
                    curr = df.iloc[-1]['close']
                    return (curr - prev) / prev * 100 if prev > 0 else 0
            finally:
                bs.logout()
        except:
            pass
        return 0.0


def send_wechat_notification(results: List[Dict]):
    if not results:
        logger.info("无推荐股票")
        print("\n无推荐股票")
        return
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    content = f"📈 A股短线推荐 ({now})\n\n"
    content += f"共筛选出 {len(results)} 只股票：\n\n"
    
    for i, stock in enumerate(results, 1):
        content += f"{i}. {stock['名称']}({stock['代码']})\n"
        content += f"   价格：{stock['最新价']}  涨幅：{stock['涨跌幅']}\n"
        content += f"   换手率：{stock['换手率']}  量比：{stock['量比']}\n"
        content += f"   流通市值：{stock['流通市值']}\n\n"
    
    content += "⚠️ 以上仅为系统筛选结果，不构成投资建议！"
    
    try:
        url = f"{WECHAT_BOT_URL}/cgi-bin/message/send"
        headers = {"Authorization": f"Bearer {WECHAT_BOT_TOKEN}", "Content-Type": "application/json"}
        payload = {"touser": WECHAT_USER_ID, "msgtype": "text", "text": {"content": content}, "context_token": WECHAT_CONTEXT_TOKEN}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"微信推送：{resp.status_code}")
    except Exception as e:
        logger.error(f"微信推送异常：{e}")
    
    print("\n" + "=" * 50)
    print(content)
    print("=" * 50)


def main():
    screener = StockScreener()
    results = screener.run()
    send_wechat_notification(results)


if __name__ == '__main__':
    main()
