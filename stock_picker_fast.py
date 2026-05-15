#!/usr/bin/env python3
"""
A股短线T+1股票筛选系统 - 极速Web版 v4
优化：全市场覆盖 + 本地行业映射 + 双重筛选策略
速度：< 5秒
"""

import requests
import pandas as pd
import numpy as np
import logging
import sys
import os
import re
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

session = requests.Session()

# 加载本地行业映射
INDUSTRY_MAP = {}
try:
    with open(os.path.join(os.path.dirname(__file__), 'industry_map.json'), 'r', encoding='utf-8') as f:
        INDUSTRY_MAP = json.load(f)
    logger.info(f"加载行业映射: {len(INDUSTRY_MAP)} 条")
except:
    pass

# 行业分类简化映射（证监会代码 -> 简化板块名称）
INDUSTRY_SHORT_MAP = {
    # 金融
    'J66': '金融', 'J67': '金融', 'J68': '金融', 'J69': '金融',
    # 科技/电子
    'C39': '电子/半导体', 'C38': '电子设备', 'C40': '仪器仪表',
    # 医药
    'C27': '医药', 'C35': '医药器械',
    # 制造业
    'C30': '建材', 'C31': '钢铁', 'C32': '有色金属', 'C33': '金属制品',
    'C34': '机械', 'C36': '汽车', 'C37': '船舶', 'C41': '其他制造',
    # 能源/资源
    'B06': '煤炭', 'B07': '石油', 'B08': '黑色金属矿', 'B09': '有色金属矿',
    'D44': '电力', 'D45': '燃气', 'D46': '水务',
    # 建筑/地产
    'E47': '建筑', 'E48': '建筑', 'E49': '建筑', 'K70': '地产',
    # 交通运输
    'G53': '铁路', 'G54': '公路', 'G55': '水运', 'G56': '航空', 'G59': '物流',
    # 信息技术
    'I63': '电信', 'I64': '互联网', 'I65': '软件服务',
    # 商业/消费
    'F51': '批发', 'F52': '零售', 'H61': '酒店', 'H62': '餐饮',
    'R85': '新闻', 'R86': '出版', 'R87': '影视', 'R88': '艺术',
    # 农业
    'A01': '农业', 'A02': '林业', 'A03': '畜牧业', 'A04': '渔业', 'A05': '农服',
    # 其他
    'C13': '农副食品', 'C14': '食品', 'C15': '饮料', 'C16': '烟草',
    'C17': '纺织', 'C18': '服装', 'C19': '皮革', 'C20': '木材', 'C21': '家具',
    'C22': '造纸', 'C23': '印刷', 'C24': '文教用品', 'C25': '石油加工',
    'C26': '化学', 'C28': '化学纤维', 'C29': '橡胶塑料',
    'C42': '废弃资源', 'M73': '研发', 'M74': '专业服务', 'M75': '科技服务',
    'N77': '水利', 'N78': '环保', 'O79': '公共设施', 'P80': '教育',
    'Q81': '卫生', 'Q83': '体育', 'S90': '综合',
}

def get_industry_name(code: str) -> str:
    """根据股票代码获取行业名称（修复格式匹配）"""
    # 转换代码格式：纯数字 -> 市场前缀格式
    if code.startswith(('60', '68')):
        map_key = f"sh.{code}"
    elif code.startswith(('00', '30')):
        map_key = f"sz.{code}"
    else:
        map_key = code
    
    industry_code = INDUSTRY_MAP.get(map_key, '')
    if not industry_code:
        return '未知'
    
    # 简化行业名称
    prefix = industry_code.split(' ')[0] if ' ' in industry_code else industry_code[:3]
    return INDUSTRY_SHORT_MAP.get(prefix, industry_code)

def generate_all_a_stock_codes() -> List[str]:
    """生成全市场A股代码列表（排除科创板688/689）"""
    codes = []
    # 上海主板 (600-605) - 排除科创板688/689
    prefixes_sh = ['600', '601', '603', '605']
    for p in prefixes_sh:
        for i in range(1000): codes.append(f"sh{p}{i:03d}")
            
    # 深圳 (000-003, 300-301创业板)
    prefixes_sz = ['000', '001', '002', '003', '300', '301']
    for p in prefixes_sz:
        for i in range(1000): codes.append(f"sz{p}{i:03d}")
        
    return list(set(codes))

def fetch_tencent_details_batch(codes: List[str]) -> List[Dict]:
    """通过腾讯接口批量获取详单数据"""
    results = []
    codes_str = ','.join(codes)
    url = f'http://qt.gtimg.cn/q={codes_str}'
    
    try:
        resp = session.get(url, timeout=5)
        resp.encoding = 'gbk'
        
        for line in resp.text.split(';'):
            if '=' not in line: continue
            
            match = re.search(r'=\"([^\"]*)\"', line)
            if not match: continue
            
            d = match.group(1).split('~')
            if len(d) < 50: continue
            
            try:
                code = d[2]
                industry = get_industry_name(code)  # 使用修复后的行业获取
                
                results.append({
                    '代码': code,
                    '名称': d[1],
                    '最新价': float(d[3]),
                    '昨收': float(d[4]),
                    '涨跌幅': float(d[32]) if d[32] else 0,
                    '成交量': float(d[6]),
                    '换手率': float(d[38]) if d[38] else 0,
                    '量比': float(d[10]) if d[10] else 0,
                    '流通市值': float(d[44]) * 1e8 if len(d) > 44 and d[44] else 0,
                    '行业': industry,
                    '板块': industry
                })
            except: continue
    except Exception as e:
        logger.debug(f"请求失败: {e}")
    
    return results

def get_all_market_data() -> pd.DataFrame:
    """获取全市场数据"""
    all_codes = generate_all_a_stock_codes()
    logger.info(f"生成全市场代码: {len(all_codes)} 只")
    
    batch_size = 80
    all_results = []
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        batches = [all_codes[i:i+batch_size] for i in range(0, len(all_codes), batch_size)]
        logger.info(f"共 {len(batches)} 批数据，开始请求...")
        
        futures = [executor.submit(fetch_tencent_details_batch, batch) for batch in batches]
        
        for i, future in enumerate(as_completed(futures)):
            try:
                res = future.result()
                all_results.extend(res)
                if (i+1) % 20 == 0:
                    logger.info(f"已获取 {(i+1)*batch_size}/{len(all_codes)} 只...")
            except: pass
                
    df = pd.DataFrame(all_results)
    if '代码' in df.columns:
        df = df[df['代码'].str.match(r'^\d{6}$')]
    return df

def analyze_ma_strict(code: str) -> Tuple[bool, bool]:
    """严格技术分析：返回(严格通过, 放宽通过)"""
    try:
        symbol = f"sh{code}" if code.startswith(('60', '68')) else f"sz{code}"
        url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=30"
        resp = requests.get(url, timeout=2)
        data = resp.json()
        
        if len(data) < 21: return (False, False)
        
        closes = [float(d['close']) for d in data]
        volumes = [float(d['volume']) for d in data]
        
        # 计算均线
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        
        ma5_prev = np.mean(closes[-6:-1])
        ma10_prev = np.mean(closes[-11:-1])
        ma20_prev = np.mean(closes[-21:-1])
        
        # 基础条件（放宽版）
        ma_aligned = ma5 > ma10 > ma20
        ma5_10_upward = ma5 > ma5_prev and ma10 > ma10_prev
        price_above = closes[-1] > ma20
        
        relaxed_pass = ma_aligned and ma5_10_upward and price_above
        
        # 严格条件：增加成交量递增 + MA20向上
        vol_5d = volumes[-5:]
        vol_increasing = all(vol_5d[i] <= vol_5d[i+1] for i in range(len(vol_5d)-1))
        ma20_upward = ma20 > ma20_prev
        
        strict_pass = relaxed_pass and vol_increasing and ma20_upward
        
        return (strict_pass, relaxed_pass)
    except: 
        return (False, False)

def print_formatted_results(results, strategy_type=""):
    """打印格式化结果供Web解析"""
    if not results:
        print("\n无推荐股票")
        return
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    strategy_label = f"【{strategy_type}】" if strategy_type else ""
    print(f"\n📈 A股短线推荐 ({now}) {strategy_label}\n")
    print(f"共筛选出 {len(results)} 只股票：\n")
    for r in results:
        print(f"{r['序号']}. {r['名称']}({r['代码']})")
        print(f"   价格：{r['最新价']}  涨幅：{r['涨跌幅']}")
        print(f"   换手率：{r['换手率']}  量比：{r['量比']}")
        print(f"   流通市值：{r['流通市值']}")
        print(f"   所属板块：{r['板块']}")
        print()
    print("⚠️ 以上仅为系统筛选结果，不构成投资建议！")
    print("=" * 50)

def run_screening():
    """双重筛选策略：先严格，再放宽"""
    logger.info("=" * 50)
    logger.info("开始执行股票筛选（极速Web版 v4 - 双重筛选）...")
    logger.info("=" * 50)
    
    start_time = datetime.now()
    
    try:
        logger.info("步骤1：获取全市场实时数据...")
        df = get_all_market_data()
        logger.info(f"获取到 {len(df)} 只股票有效数据，耗时: {(datetime.now()-start_time).total_seconds():.1f}秒")
        
        if df.empty: return [], "无数据"
        
        logger.info("步骤2：基础筛选...")
        df = df[(df['涨跌幅'] >= GAIN_MIN) & (df['涨跌幅'] <= GAIN_MAX)]
        logger.info(f"  - 涨幅筛选后: {len(df)} 只")
        df = df[df['量比'] > VOLUME_RATIO_MIN]
        logger.info(f"  - 量比筛选后: {len(df)} 只")
        df = df[(df['换手率'] >= TURNOVER_MIN) & (df['换手率'] <= TURNOVER_MAX)]
        logger.info(f"  - 换手率筛选后: {len(df)} 只")
        df = df[(df['流通市值'] >= MARKET_CAP_MIN * 1e8) & (df['流通市值'] <= MARKET_CAP_MAX * 1e8)]
        logger.info(f"  - 市值筛选后: {len(df)} 只")
        
        if df.empty: return [], "基础筛选无候选"
        
        candidates = df.to_dict(orient='records')
        
        # 第一轮：严格条件筛选
        logger.info("步骤3a：严格技术分析（均线多头+向上+成交量递增）...")
        strict_results = []
        relaxed_candidates = []  # 放宽版通过的候选
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(analyze_ma_strict, row['代码']): row for row in candidates}
            for future in as_completed(futures):
                try:
                    strict_pass, relaxed_pass = future.result()
                    row = futures[future]
                    if strict_pass:
                        strict_results.append(row)
                    elif relaxed_pass:
                        relaxed_candidates.append(row)
                except: pass
        
        logger.info(f"严格筛选通过: {len(strict_results)} 只")
        
        # 如果严格筛选有结果，直接返回
        if strict_results:
            final_results = strict_results
            strategy_type = "严格筛选"
        else:
            # 第二轮：使用放宽条件的结果
            logger.info("步骤3b：严格筛选无结果，启用放宽条件...")
            final_results = relaxed_candidates
            strategy_type = "放宽筛选"
            logger.info(f"放宽筛选通过: {len(final_results)} 只")
        
        # 格式化输出（按代码去重）
        seen_codes = set()
        unique_results = []
        for row in final_results:
            if row['代码'] not in seen_codes:
                seen_codes.add(row['代码'])
                unique_results.append(row)
        
        output = []
        for i, row in enumerate(unique_results, 1):
            output.append({
                '序号': i,
                '代码': row['代码'],
                '名称': row['名称'],
                '最新价': f"{row['最新价']:.2f}",
                '涨跌幅': f"{row['涨跌幅']:.2f}%",
                '换手率': f"{row['换手率']:.2f}%",
                '量比': f"{row['量比']:.2f}",
                '流通市值': f"{row['流通市值']/1e8:.2f}亿",
                '板块': row['板块'],
                '行业': row['行业']
            })
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ 筛选完成！总耗时: {elapsed:.1f}秒")
        logger.info(f"策略: {strategy_type}，最终推荐 {len(output)} 只股票")
        logger.info("=" * 50)
        
        return output, strategy_type
        
    except Exception as e:
        logger.error(f"筛选过程出错：{e}")
        import traceback
        traceback.print_exc()
        return [], "异常"

def send_wechat_notification(results, strategy_type):
    """发送微信推送 - 即使结果为空也通知"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    if not results:
        content = f"📊 A股短线筛选 ({now})\n\n"
        content += "筛选条件：涨幅3-5% / 量比>1 / 换手率5-10% / 市值50-200亿\n\n"
        content += "❌ 两轮筛选均无符合技术条件的股票\n\n"
        content += "说明：\n"
        content += "- 第一轮严格筛选（均线多头+向上+成交量递增）：0只\n"
        content += "- 第二轮放宽筛选（均线多头+MA5/MA10向上）：0只\n\n"
        content += "💡 建议：今日无符合条件股票，关注市场变化"
    else:
        strategy_label = f"【{strategy_type}】"
        content = f"📈 A股短线推荐 ({now}) {strategy_label}\n\n"
        content += f"筛选条件：涨幅3-5% / 量比>1 / 换手率5-10% / 市值50-200亿\n\n"
        content += f"✅ 共筛选出 {len(results)} 只股票：\n\n"
        
        for stock in results:
            content += f"{stock['序号']}. {stock['名称']}({stock['代码']})\n"
            content += f"   价格：{stock['最新价']}  涨幅：{stock['涨跌幅']}\n"
            content += f"   换手率：{stock['换手率']}  量比：{stock['量比']}\n"
            content += f"   流通市值：{stock['流通市值']}\n"
            content += f"   所属板块：{stock['板块']}\n\n"
        
        content += "⚠️ 以上仅为系统筛选结果，不构成投资建议！"
    
    try:
        url = f"{WECHAT_BOT_URL}/cgi-bin/message/send"
        headers = {"Authorization": f"Bearer {WECHAT_BOT_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "touser": WECHAT_USER_ID,
            "msgtype": "text",
            "text": {"content": content},
            "context_token": WECHAT_CONTEXT_TOKEN
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"微信推送状态：{resp.status_code}")
        if resp.status_code == 200:
            logger.info("✅ 推送成功")
        else:
            logger.warning(f"推送响应：{resp.text[:100] if resp.text else 'empty'}")
    except Exception as e:
        logger.error(f"微信推送异常：{e}")
    
    print("\n" + "=" * 50)
    print(content)
    print("=" * 50)

def main():
    results, strategy_type = run_screening()
    print_formatted_results(results, strategy_type)
    send_wechat_notification(results, strategy_type)

if __name__ == '__main__':
    main()