from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import subprocess
import json
import os
import re
import threading
import time
import pandas as pd
import numpy as np
import requests
import concurrent.futures
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 动态获取PROJECT_DIR（适配Docker容器内/外部路径）
if os.path.exists('/app/stock_picker_fast.py'):
    PROJECT_DIR = '/app'
else:
    PROJECT_DIR = '/mnt/d/hermes-workspace/stock-picker'
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "stock_picker.log")
SECTORS_FILE = os.path.join(PROJECT_DIR, "hot_sectors.json")
SKILL_SCRIPT = "/home/xiaoyansong/.hermes/skills/research/short-term-stock-picker/scripts/pick_stocks.py"

# --- Load Sector Map ---
SECTOR_MAP = {}
try:
    with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
        SECTOR_MAP = json.load(f)
except:
    pass

# --- Global States ---
state_realtime = {
    'running': False,
    'progress': 0,
    'message': '就绪',
    'results': [],
    'log': ''
}

state_limitup = {
    'running': False,
    'progress': 0,
    'message': '就绪',
    'results': [],
    'log': '',
    'csv_path': ''
}

# 股票搜索缓存（避免频繁请求）
STOCK_LIST_CACHE = None
STOCK_LIST_CACHE_TIME = 0
CACHE_EXPIRE_SECONDS = 3600  # 1小时过期

def get_all_stocks():
    """获取全市场股票列表（使用腾讯接口，带缓存）"""
    global STOCK_LIST_CACHE, STOCK_LIST_CACHE_TIME
    now = time.time()
    
    if STOCK_LIST_CACHE and (now - STOCK_LIST_CACHE_TIME) < CACHE_EXPIRE_SECONDS:
        return STOCK_LIST_CACHE
    
    try:
        # 使用腾讯实时接口（与stock_picker_fast.py一致）
        url = "http://qt.gtimg.cn/q=" + "sh000001"  # 先测试连接
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            raise Exception("腾讯接口不可用")
        
        # 获取全市场A股代码列表
        # 使用akshare获取代码列表（轻量级）
        import akshare as ak
        try:
            stock_list = ak.stock_info_a_code_name()  # 只获取代码和名称，不请求实时行情
            codes = []
            for _, row in stock_list.iterrows():
                code = str(row['code'])
                # 过滤科创板（688/689开头）
                if code.startswith('688') or code.startswith('689'):
                    continue
                codes.append(code)
        except:
            # akshare失败时使用本地代码列表（从industry_map.json）
            codes = []
            for key in SECTOR_MAP.keys():
                if '.' in key:
                    c = key.split('.')[1]
                    if not c.startswith('688') and not c.startswith('689'):
                        codes.append(c)
        
        # 批量获取实时行情（腾讯接口，每批500个）
        stocks = []
        market_map = {'6': 'sh', '0': 'sz', '3': 'sz'}
        
        for i in range(0, len(codes), 500):
            batch_codes = codes[i:i+500]
            qt_codes = []
            for c in batch_codes:
                market = 'sh' if c.startswith('6') else 'sz'
                qt_codes.append(f"{market}{c}")
            
            url = "http://qt.gtimg.cn/q=" + ','.join(qt_codes)
            resp = requests.get(url, timeout=15)
            lines = resp.text.strip().split('\n')
            
            for line in lines:
                if not line.startswith('v_'):
                    continue
                try:
                    # 解析腾讯数据格式: v_sh600519="51~贵州茅台~..."
                    parts = line.split('="')
                    if len(parts) < 2:
                        continue
                    raw_code = parts[0].replace('v_', '').replace('sh', '').replace('sz', '')
                    data = parts[1].replace('"', '').split('~')
                    
                    if len(data) < 45:
                        continue
                    
                    name = data[1]
                    price = float(data[3]) if data[3] else 0
                    change = float(data[32]) if data[32] else 0  # 涨跌幅
                    
                    # 查找行业
                    industry = '--'
                    market_key = f"{'sh' if raw_code.startswith('6') else 'sz'}.{raw_code}"
                    if market_key in SECTOR_MAP:
                        industry_code = SECTOR_MAP[market_key]
                        # 简化行业名称
                        industry_map_simple = {
                            'C': '制造业', 'J': '金融', 'K': '房地产', 'F': '批发零售',
                            'G': '交通运输', 'D': '电力', 'E': '建筑', 'I': '信息技术',
                            'M': '科研服务', 'N': '水利环境', 'O': '居民服务', 'P': '教育',
                            'Q': '卫生', 'R': '文化娱乐', 'S': '公共管理', 'A': '农业',
                            'B': '采矿', 'H': '住宿餐饮', 'L': '租赁商务', 'T': '国际组织'
                        }
                        if industry_code in industry_map_simple:
                            industry = industry_map_simple[industry_code]
                        else:
                            industry = industry_code
                    
                    stocks.append({
                        'code': raw_code,
                        'name': name,
                        'price': price,
                        'change': change,
                        'volume_ratio': 0,  # 腾讯接口不直接提供量比
                        'turnover': 0,
                        'market_cap': 0,
                        'industry': industry
                    })
                except Exception as e:
                    continue
        
        STOCK_LIST_CACHE = stocks
        STOCK_LIST_CACHE_TIME = now
        print(f"股票列表缓存更新: {len(stocks)} 条")
        return stocks
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return STOCK_LIST_CACHE or []

@app.route('/api/search', methods=['GET'])
def api_search():
    """搜索股票（代码或名称模糊匹配）"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'message': '请输入搜索关键词', 'results': []})
    
    stocks = get_all_stocks()
    if not stocks:
        return jsonify({'success': False, 'message': '获取股票列表失败', 'results': []})
    
    # 模糊匹配（代码前缀或名称包含）
    results = []
    query_lower = query.lower()
    for stock in stocks:
        code_match = stock['code'].startswith(query)
        name_match = query_lower in stock['name'].lower()
        
        if code_match or name_match:
            results.append(stock)
    
    # 按匹配度排序：代码精确匹配优先，名称匹配其次
    def sort_key(s):
        if s['code'] == query:
            return (0, 0)  # 精确代码匹配
        elif s['code'].startswith(query):
            return (1, len(s['code']) - len(query))  # 代码前缀匹配
        else:
            return (2, len(s['name']))  # 名称匹配
    
    results.sort(key=sort_key)
    
    # 限制返回数量
    return jsonify({
        'success': True,
        'query': query,
        'total': len(results),
        'results': results[:50]  # 最多返回50条
    })

@app.route('/api/stock/info/<code>', methods=['GET'])
def api_stock_info(code):
    """获取单只股票基本信息（用于分析入口）"""
    try:
        import akshare as ak
        stock_info = ak.stock_zh_a_spot_em()
        stock_row = stock_info[stock_info['代码'] == code]
        
        if stock_row.empty:
            return jsonify({'success': False, 'message': '股票代码不存在'})
        
        row = stock_row.iloc[0]
        return jsonify({
            'success': True,
            'data': {
                'code': code,
                'name': row['名称'],
                'price': float(row['最新价']) if row['最新价'] else 0,
                'change': float(row['涨跌幅']) if row['涨跌幅'] else 0,
                'volume_ratio': float(row['量比']) if row['量比'] else 0,
                'turnover': float(row['换手率']) if row['换手率'] else 0,
                'market_cap': float(row['总市值']) / 100000000 if row['总市值'] else 0,
                'industry': row.get('所属行业', '--') or '--'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({
        'realtime': state_realtime,
        'limitup': state_limitup
    })

@app.route('/api/run', methods=['POST'])
def api_run():
    # Handles "Real-time" screening
    if state_realtime['running']: return jsonify({'success': False, 'message': '进行中'})
    
    def task():
        global state_realtime
        state_realtime['running'] = True
        state_realtime['progress'] = 0
        state_realtime['log'] = ''
        state_realtime['message'] = '启动中...'
        try:
            proc = subprocess.Popen(
                ['python3', 'stock_picker_fast.py'],
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            log_buf = ""
            for line in proc.stdout:
                log_buf += line
                state_realtime['log'] = log_buf[-3000:]
                if "获取到" in line:
                    state_realtime['progress'] = 30
                    state_realtime['message'] = "获取行情..."
                elif "筛选完成" in line:
                    state_realtime['progress'] = 90
                    state_realtime['message'] = "解析结果..."
            
# Parse log for results
            results = []
            seen_codes = set()
            pattern = r'(\d+)\.\s*(.*?)\n\s+价格：([\d.]+)\s+涨幅：([\d.]+)%\s*\n\s+换手率：([\d.]+)%\s+量比：([\d.]+)\s*\n\s+流通市值：([\d.]+)亿\s*\n\s+所属板块：([^\n]+)'
            for m in re.finditer(pattern, log_buf):
                code = m.group(2).split('(')[1].replace(')','')
                if code not in seen_codes:
                    seen_codes.add(code)
                    results.append({
                        '序号': m.group(1),
                        '代码': code,
                        '名称': m.group(2).split('(')[0],
                        '最新价': m.group(3),
                        '涨跌幅': m.group(4) + '%',
                        '换手率': m.group(5) + '%',
                        '量比': m.group(6),
                        '流通市值': m.group(7) + '亿',
                        '板块': m.group(8)
                    })
            
            state_realtime['results'] = results
            state_realtime['progress'] = 100
            state_realtime['message'] = f"完成！找到 {len(results)} 只"
        except Exception as e:
            state_realtime['message'] = f"Error: {str(e)}"
        finally:
            state_realtime['running'] = False

    threading.Thread(target=task, daemon=True).start()
    return jsonify({'success': True, 'message': '任务已启动'})

@app.route('/api/run_limit_up', methods=['POST'])
def api_run_limit_up():
    if state_limitup['running']: return jsonify({'success': False, 'message': '进行中'})
    
    def task():
        global state_limitup
        state_limitup['running'] = True
        state_limitup['progress'] = 0
        state_limitup['message'] = '正在初始化...'
        state_limitup['log'] = ''
        state_limitup['results'] = []
        state_limitup['csv_path'] = ''
        
        try:
            process = subprocess.Popen(
                ['python3', SKILL_SCRIPT],
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            full_log = ""
            for line in process.stdout:
                full_log += line
                state_limitup['log'] = full_log[-2000:]
                
                if "已检查" in line and "个交易日" in line:
                    state_limitup['message'] = line.strip()
                    match = re.search(r'(\d+)/20', line)
                    if match:
                        state_limitup['progress'] = int(int(match.group(1)) / 20 * 100)
                elif "已分析" in line and "只" in line:
                    state_limitup['message'] = line.strip()
                    match = re.search(r'(\d+)/(\d+)', line)
                    if match:
                        curr = int(match.group(1))
                        total = int(match.group(2))
                        if total > 0:
                            state_limitup['progress'] = 50 + int((curr / total) * 50)
                elif "筛选完成" in line:
                    state_limitup['progress'] = 100
                    state_limitup['message'] = '解析结果中...'
                    
                if "📁 结果已保存到:" in line:
                    path_match = re.search(r'保存到:\s*(.+)', line)
                    if path_match:
                        state_limitup['csv_path'] = path_match.group(1).strip()

            process.wait()
            
            csv_file = os.path.join(PROJECT_DIR, 'short_term_results.csv')
            if os.path.exists(csv_file):
                try:
                    df = pd.read_csv(csv_file)
                    df = df.head(50)
                    state_limitup['results'] = df.to_dict(orient='records')
                    state_limitup['message'] = f"完成！共筛选 {len(df)} 只"
                except Exception as e:
                    state_limitup['message'] = "运行完成，但结果解析失败"
            else:
                state_limitup['message'] = "运行完成，但未找到结果文件"

        except Exception as e:
            state_limitup['message'] = f"错误：{str(e)}"
        finally:
            state_limitup['running'] = False

    threading.Thread(target=task, daemon=True).start()
    return jsonify({'success': True, 'message': '任务已启动'})

@app.route('/api/hot_sectors', methods=['GET'])
def api_hot_sectors():
    all_codes = []
    for codes in SECTOR_MAP.values():
        all_codes.extend(codes)
    all_codes = list(set(all_codes))
    
    if not all_codes:
        return jsonify({'sectors': {}})

    batch_size = 80
    results = []
    code_objs = [f"sz{c}" if c.startswith(('00','30')) else f"sh{c}" for c in all_codes]
    
    def _fetch_batch(url):
        try:
            resp = requests.get(url, timeout=3)
            resp.encoding = 'gbk'
            data = []
            for line in resp.text.split(';'):
                if '=' in line:
                    match = re.search(r'="([^"]*)"', line)
                    if match:
                        d = match.group(1).split('~')
                        if len(d) > 45:
                            try:
                                data.append({
                                    '代码': d[2], '名称': d[1],
                                    '最新价': float(d[3]), '涨跌幅': float(d[32]) if d[32] else 0,
                                    '成交额': float(d[39]) * 10000 if d[39] else 0,
                                    '换手率': float(d[38]) if d[38] else 0,
                                    '量比': float(d[10]) if d[10] else 0,
                                })
                            except: pass
            return data
        except: return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for i in range(0, len(code_objs), batch_size):
            batch = code_objs[i:i+batch_size]
            url = f"http://qt.gtimg.cn/q={','.join(batch)}"
            futures.append(executor.submit(_fetch_batch, url))
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    df = pd.DataFrame(results)
    if df.empty: return jsonify({'sectors': {}})

    df['score'] = df['成交额'] * 0.4 + df['量比'] * 1e7 * 0.3 + df['换手率'] * 1e7 * 0.2
    
    result_data = {}
    for sector_name in SECTOR_MAP.keys():
        sector_codes = SECTOR_MAP[sector_name]
        sector_df = df[df['代码'].isin(sector_codes)].sort_values('score', ascending=False).head(10)
        if not sector_df.empty:
            result_data[sector_name] = sector_df.to_dict(orient='records')
            
    return jsonify({'sectors': result_data})

@app.route('/api/schedule', methods=['POST'])
def api_set_schedule():
    data = request.json
    minute = data.get('minute', '30')
    hour = data.get('hour', '14')
    enabled = data.get('enabled', True)
    
    if enabled:
        cron_line = f"{minute} {hour} * * 1-5 cd {PROJECT_DIR} && docker run --rm -v {PROJECT_DIR}/logs:/app/logs stock-picker >> {PROJECT_DIR}/logs/cron_output.log 2>&1"
        try:
            subprocess.run(f'(crontab -l 2>/dev/null | grep -v "stock-picker"; echo "{cron_line}") | crontab -', 
                         shell=True, capture_output=True)
            return jsonify({'success': True, 'message': '设置成功'})
        except:
            return jsonify({'success': False, 'message': '设置失败'})
    else:
        try:
            subprocess.run('(crontab -l 2>/dev/null | grep -v "stock-picker") | crontab -', 
                         shell=True, capture_output=True)
            return jsonify({'success': True, 'message': '已关闭'})
        except:
            return jsonify({'success': False, 'message': '关闭失败'})

# --- Single Stock Analysis ---
ANALYSIS_DIR = "/mnt/d/hermes-workspace/stock-analysis"
ANALYSIS_SCRIPT = os.path.join(ANALYSIS_DIR, "stock_full_report.py")
ANALYSIS_OUTPUT_DIR = os.path.join(ANALYSIS_DIR, "output")
ANALYSIS_HISTORY_FILE = os.path.join(PROJECT_DIR, "analysis_history.json")

analysis_tasks = {}  # task_id -> {code, status, message, result_path}

# Load analysis history on startup
analysis_history = []
try:
    if os.path.exists(ANALYSIS_HISTORY_FILE):
        with open(ANALYSIS_HISTORY_FILE, 'r', encoding='utf-8') as f:
            analysis_history = json.load(f)
except:
    analysis_history = []

def save_analysis_history():
    """Save analysis history to file"""
    try:
        with open(ANALYSIS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(analysis_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save history error: {e}")

@app.route('/analysis/<code>')
def analysis_page(code):
    """Render single stock analysis page"""
    return render_template('analysis.html', code=code)

@app.route('/api/analysis/list', methods=['GET'])
def api_analysis_list():
    """Get list of completed analyses"""
    return jsonify({'success': True, 'list': analysis_history})

@app.route('/api/analyze/<code>', methods=['POST'])
def api_analyze(code):
    """Start async analysis for a single stock"""
    import uuid
    task_id = str(uuid.uuid4())[:8]
    
    def run_analysis():
        global analysis_tasks, analysis_history
        analysis_tasks[task_id] = {
            'code': code,
            'status': 'running',
            'message': '正在启动分析...',
            'progress': 0,
            'result_path': None
        }
        
        try:
            # Get stock name from realtime results if available
            stock_name = code
            for r in state_realtime.get('results', []):
                if r['代码'] == code:
                    stock_name = r['名称']
                    break
            
            # Run stock_full_report.py
            proc = subprocess.Popen(
                ['python3', ANALYSIS_SCRIPT, code],
                cwd=ANALYSIS_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            full_log = ""
            for line in proc.stdout:
                full_log += line
                if "正在获取" in line or "Fetching" in line:
                    analysis_tasks[task_id]['message'] = line.strip()
                    analysis_tasks[task_id]['progress'] = 20
                elif "分析完成" in line or "Analysis complete" in line:
                    analysis_tasks[task_id]['progress'] = 90
                    analysis_tasks[task_id]['message'] = '分析完成，保存结果...'
                elif "保存到" in line or "Saved to" in line:
                    analysis_tasks[task_id]['progress'] = 95
            
            proc.wait()
            
            # Check for output file
            result_file = os.path.join(ANALYSIS_OUTPUT_DIR, f"data_{code}.json")
            if os.path.exists(result_file):
                analysis_tasks[task_id]['status'] = 'completed'
                analysis_tasks[task_id]['progress'] = 100
                analysis_tasks[task_id]['message'] = '分析完成'
                analysis_tasks[task_id]['result_path'] = result_file
                
                # Save to history
                history_record = {
                    'code': code,
                    'name': stock_name,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'result_file': result_file
                }
                # Remove old record for same code
                analysis_history = [h for h in analysis_history if h['code'] != code]
                analysis_history.insert(0, history_record)
                # Keep only last 20
                analysis_history = analysis_history[:20]
                save_analysis_history()
            else:
                analysis_tasks[task_id]['status'] = 'failed'
                analysis_tasks[task_id]['message'] = '分析完成但未生成报告'
                
        except Exception as e:
            analysis_tasks[task_id]['status'] = 'failed'
            analysis_tasks[task_id]['message'] = f'分析失败: {str(e)}'
    
    threading.Thread(target=run_analysis, daemon=True).start()
    return jsonify({'success': True, 'task_id': task_id, 'code': code})

@app.route('/api/analysis/status/<task_id>', methods=['GET'])
def api_analysis_status(task_id):
    """Get analysis task status"""
    if task_id not in analysis_tasks:
        return jsonify({'success': False, 'message': 'Task not found'})
    return jsonify({'success': True, 'task': analysis_tasks[task_id]})

@app.route('/api/analysis/result/<code>', methods=['GET'])
def api_analysis_result(code):
    """Get analysis result for a stock"""
    result_file = os.path.join(ANALYSIS_OUTPUT_DIR, f"data_{code}.json")
    if not os.path.exists(result_file):
        return jsonify({'success': False, 'message': 'Result not found'})
    
    try:
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== 持仓管理模块 ==========
POSITIONS_FILE = os.path.join(PROJECT_DIR, "positions.json")

def load_positions():
    """加载持仓数据"""
    try:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_positions(positions):
    """保存持仓数据"""
    try:
        with open(POSITIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存持仓失败: {e}")
        return False

def get_stock_realtime_price(code):
    """获取股票实时价格"""
    try:
        market = 'sh' if code.startswith('6') else 'sz'
        url = f"http://qt.gtimg.cn/q={market}{code}"
        resp = requests.get(url, timeout=5)
        lines = resp.text.strip().split('\n')
        for line in lines:
            if line.startswith('v_'):
                parts = line.split('="')
                if len(parts) >= 2:
                    data = parts[1].replace('"', '').split('~')
                    if len(data) >= 4:
                        return float(data[3]) if data[3] else 0
        return 0
    except:
        return 0

@app.route('/api/positions', methods=['GET'])
def api_get_positions():
    """获取持仓列表（带实时价格和盈亏计算）"""
    positions = load_positions()
    
    # 刷新实时价格和盈亏
    for pos in positions:
        current_price = get_stock_realtime_price(pos['code'])
        pos['current_price'] = current_price
        pos['current_value'] = current_price * pos['quantity']
        pos['profit'] = (current_price - pos['buy_price']) * pos['quantity']
        pos['profit_rate'] = ((current_price - pos['buy_price']) / pos['buy_price'] * 100) if pos['buy_price'] > 0 else 0
    
    return jsonify({'success': True, 'positions': positions})

@app.route('/api/positions/add', methods=['POST'])
def api_add_position():
    """添加持仓"""
    data = request.json
    code = data.get('code', '').strip()
    name = data.get('name', '').strip()
    buy_price = float(data.get('buy_price', 0))
    quantity = int(data.get('quantity', 0))
    buy_date = data.get('buy_date', datetime.now().strftime('%Y-%m-%d'))
    stop_loss = float(data.get('stop_loss', 0))  # 止损价
    stop_profit = float(data.get('stop_profit', 0))  # 止盈价
    
    if not code or buy_price <= 0 or quantity <= 0:
        return jsonify({'success': False, 'message': '参数不完整或无效'})
    
    positions = load_positions()
    
    # 检查是否已持有
    for pos in positions:
        if pos['code'] == code:
            # 已持有，更新数量和均价
            total_cost = pos['buy_price'] * pos['quantity'] + buy_price * quantity
            total_quantity = pos['quantity'] + quantity
            pos['buy_price'] = total_cost / total_quantity
            pos['quantity'] = total_quantity
            pos['buy_date'] = buy_date
            save_positions(positions)
            return jsonify({'success': True, 'message': '持仓已更新（加仓）', 'position': pos})
    
    # 新持仓
    new_pos = {
        'code': code,
        'name': name,
        'buy_price': buy_price,
        'quantity': quantity,
        'buy_date': buy_date,
        'stop_loss': stop_loss,
        'stop_profit': stop_profit,
        'current_price': buy_price,  # 初始为买入价
        'current_value': buy_price * quantity,
        'profit': 0,
        'profit_rate': 0
    }
    positions.append(new_pos)
    save_positions(positions)
    
    return jsonify({'success': True, 'message': '持仓添加成功', 'position': new_pos})

@app.route('/api/positions/sell', methods=['POST'])
def api_sell_position():
    """卖出持仓（部分或全部）"""
    data = request.json
    code = data.get('code', '').strip()
    sell_quantity = int(data.get('quantity', 0))
    sell_price = float(data.get('sell_price', 0))
    
    if not code or sell_quantity <= 0:
        return jsonify({'success': False, 'message': '参数无效'})
    
    positions = load_positions()
    
    for i, pos in enumerate(positions):
        if pos['code'] == code:
            if sell_quantity > pos['quantity']:
                return jsonify({'success': False, 'message': '卖出数量超过持有数量'})
            
            # 计算本次卖出盈亏
            sell_profit = (sell_price - pos['buy_price']) * sell_quantity
            
            if sell_quantity == pos['quantity']:
                # 全部卖出，删除持仓
                positions.pop(i)
                save_positions(positions)
                return jsonify({
                    'success': True,
                    'message': f'已全部卖出，盈亏: {sell_profit:.2f}元',
                    'sell_profit': sell_profit
                })
            else:
                # 部分卖出
                pos['quantity'] -= sell_quantity
                pos['current_value'] = pos['current_price'] * pos['quantity']
                save_positions(positions)
                return jsonify({
                    'success': True,
                    'message': f'已卖出{sell_quantity}股，本次盈亏: {sell_profit:.2f}元',
                    'sell_profit': sell_profit,
                    'position': pos
                })
    
    return jsonify({'success': False, 'message': '未找到该持仓'})

@app.route('/api/positions/delete', methods=['POST'])
def api_delete_position():
    """删除持仓记录"""
    data = request.json
    code = data.get('code', '').strip()
    
    if not code:
        return jsonify({'success': False, 'message': '股票代码无效'})
    
    positions = load_positions()
    positions = [p for p in positions if p['code'] != code]
    save_positions(positions)
    
    return jsonify({'success': True, 'message': '持仓已删除'})

@app.route('/api/positions/update', methods=['POST'])
def api_update_position():
    """更新持仓止损止盈"""
    data = request.json
    code = data.get('code', '').strip()
    stop_loss = float(data.get('stop_loss', 0))
    stop_profit = float(data.get('stop_profit', 0))
    
    if not code:
        return jsonify({'success': False, 'message': '股票代码无效'})
    
    positions = load_positions()
    
    for pos in positions:
        if pos['code'] == code:
            pos['stop_loss'] = stop_loss
            pos['stop_profit'] = stop_profit
            save_positions(positions)
            return jsonify({'success': True, 'message': '止损止盈已更新', 'position': pos})
    
    return jsonify({'success': False, 'message': '未找到该持仓'})

@app.route('/api/positions/check_alerts', methods=['GET'])
def api_check_position_alerts():
    """检查持仓预警（止损止盈触发）"""
    positions = load_positions()
    alerts = []
    
    for pos in positions:
        current_price = get_stock_realtime_price(pos['code'])
        
        # 止损检查
        if pos['stop_loss'] > 0 and current_price <= pos['stop_loss']:
            alerts.append({
                'type': 'stop_loss',
                'code': pos['code'],
                'name': pos['name'],
                'message': f'{pos["name"]}({pos["code"]})触发止损！当前价{current_price}，止损价{pos["stop_loss"]}',
                'current_price': current_price,
                'target_price': pos['stop_loss']
            })
        
        # 止盈检查
        if pos['stop_profit'] > 0 and current_price >= pos['stop_profit']:
            alerts.append({
                'type': 'stop_profit',
                'code': pos['code'],
                'name': pos['name'],
                'message': f'{pos["name"]}({pos["code"]})触发止盈！当前价{current_price}，止盈价{pos["stop_profit"]}',
                'current_price': current_price,
                'target_price': pos['stop_profit']
            })
    
    return jsonify({'success': True, 'alerts': alerts})

# ========== 关注股池模块 ==========
WATCHLIST_FILE = os.path.join(PROJECT_DIR, "watchlist.json")

def load_watchlist():
    """加载关注列表"""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_watchlist(watchlist):
    """保存关注列表"""
    try:
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(watchlist, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存关注列表失败: {e}")
        return False

@app.route('/api/watchlist', methods=['GET'])
def api_get_watchlist():
    """获取关注列表（带实时价格）"""
    watchlist = load_watchlist()
    
    # 刷新实时价格
    for item in watchlist:
        current_price = get_stock_realtime_price(item['code'])
        item['current_price'] = current_price
        item['change'] = ((current_price - item.get('last_price', current_price)) / item.get('last_price', current_price) * 100) if item.get('last_price', 0) > 0 else 0
    
    return jsonify({'success': True, 'watchlist': watchlist})

@app.route('/api/watchlist/add', methods=['POST'])
def api_add_watchlist():
    """添加关注"""
    data = request.json
    code = data.get('code', '').strip()
    name = data.get('name', '').strip()
    
    if not code:
        return jsonify({'success': False, 'message': '股票代码无效'})
    
    watchlist = load_watchlist()
    
    # 检查是否已关注
    for item in watchlist:
        if item['code'] == code:
            return jsonify({'success': False, 'message': '已关注该股票'})
    
    # 获取当前价格
    current_price = get_stock_realtime_price(code)
    
    watchlist.append({
        'code': code,
        'name': name,
        'add_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'last_price': current_price,
        'current_price': current_price,
        'change': 0
    })
    save_watchlist(watchlist)
    
    return jsonify({'success': True, 'message': '关注成功', 'item': watchlist[-1]})

@app.route('/api/watchlist/remove', methods=['POST'])
def api_remove_watchlist():
    """取消关注"""
    data = request.json
    code = data.get('code', '').strip()
    
    if not code:
        return jsonify({'success': False, 'message': '股票代码无效'})
    
    watchlist = load_watchlist()
    watchlist = [w for w in watchlist if w['code'] != code]
    save_watchlist(watchlist)
    
    return jsonify({'success': True, 'message': '已取消关注'})

# ========== 大盘数据模块 ==========
@app.route('/api/market/index', methods=['GET'])
def api_market_index():
    """获取三大指数实时数据"""
    try:
        # 上证指数 sh000001, 深证成指 sz399001, 创业板 sz399006
        codes = ['sh000001', 'sz399001', 'sz399006']
        url = "http://qt.gtimg.cn/q=" + ','.join(codes)
        resp = requests.get(url, timeout=10)
        lines = resp.text.strip().split('\n')
        
        result = {}
        for line in lines:
            if not line.startswith('v_'):
                continue
            try:
                parts = line.split('="')
                if len(parts) < 2:
                    continue
                raw_code = parts[0].replace('v_', '')
                data = parts[1].replace('"', '').split('~')
                
                if len(data) < 45:
                    continue
                
                price = float(data[3]) if data[3] else 0
                change = float(data[32]) if data[32] else 0
                
                if raw_code == 'sh000001':
                    result['sh'] = {'price': price, 'change': change, 'name': '上证指数'}
                elif raw_code == 'sz399001':
                    result['sz'] = {'price': price, 'change': change, 'name': '深证成指'}
                elif raw_code == 'sz399006':
                    result['cyb'] = {'price': price, 'change': change, 'name': '创业板'}
            except:
                continue
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/market/north', methods=['GET'])
def api_market_north():
    """获取北向资金"""
    try:
        import akshare as ak
        # 尝试获取北向资金数据
        try:
            north_data = ak.stock_em_hsgt_north_net_flow_in(indicator="北向资金")
            if north_data and len(north_data) > 0:
                latest = north_data.iloc[-1]
                net_flow = float(latest['北向资金']) if '北向资金' in north_data.columns else 0
                return jsonify({'success': True, 'data': {'net_flow': net_flow, 'date': str(latest['日期']) if '日期' in north_data.columns else ''}})
        except:
            pass
        
        # 如果akshare失败，返回模拟数据
        return jsonify({'success': True, 'data': {'net_flow': 0, 'date': datetime.now().strftime('%Y-%m-%d'), 'note': '数据获取失败，显示为0'}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/market/limit_stat', methods=['GET'])
def api_market_limit_stat():
    """获取涨跌停统计"""
    try:
        import akshare as ak
        # 尝试获取涨跌停统计
        try:
            limit_up_data = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
            limit_up_count = len(limit_up_data) if limit_up_data else 0
            
            # 获取跌停数据（近似）
            limit_down_count = 0  # akshare没有直接的跌停统计接口
            
            return jsonify({'success': True, 'data': {'limit_up': limit_up_count, 'limit_down': limit_down_count}})
        except:
            pass
        
        return jsonify({'success': True, 'data': {'limit_up': 0, 'limit_down': 0, 'note': '数据获取失败'}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== 筛选参数自定义模块 ==========
SCREEN_PARAMS_FILE = os.path.join(PROJECT_DIR, "screen_params.json")

def load_screen_params():
    """加载筛选参数"""
    try:
        if os.path.exists(SCREEN_PARAMS_FILE):
            with open(SCREEN_PARAMS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'change_min': 3, 'change_max': 5,
            'volume_ratio_min': 1,
            'turnover_min': 5, 'turnover_max': 10,
            'market_cap_min': 50, 'market_cap_max': 200
        }
    except:
        return {}

def save_screen_params(params):
    """保存筛选参数"""
    try:
        with open(SCREEN_PARAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

@app.route('/api/screen_params', methods=['GET'])
def api_get_screen_params():
    """获取筛选参数"""
    params = load_screen_params()
    return jsonify({'success': True, 'params': params})

@app.route('/api/screen_params/save', methods=['POST'])
def api_save_screen_params():
    """保存筛选参数"""
    params = request.json
    if save_screen_params(params):
        return jsonify({'success': True, 'message': '参数已保存'})
    return jsonify({'success': False, 'message': '保存失败'})

# ========== 筛选历史记录模块 ==========
SCREEN_HISTORY_FILE = os.path.join(PROJECT_DIR, "screen_history.json")

def load_screen_history():
    """加载筛选历史"""
    try:
        if os.path.exists(SCREEN_HISTORY_FILE):
            with open(SCREEN_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_screen_history(history):
    """保存筛选历史"""
    try:
        with open(SCREEN_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

@app.route('/api/screen_history', methods=['GET'])
def api_get_screen_history():
    """获取筛选历史"""
    history = load_screen_history()
    return jsonify({'success': True, 'history': history})

@app.route('/api/screen_history/save', methods=['POST'])
def api_save_screen_history_entry():
    """保存筛选结果"""
    data = request.json
    entry = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': data.get('type', 'realtime'),  # realtime or limitup
        'results': data.get('results', []),
        'count': len(data.get('results', []))
    }
    
    history = load_screen_history()
    history.insert(0, entry)
    # 只保留最近30条
    history = history[:30]
    save_screen_history(history)
    
    return jsonify({'success': True, 'message': '历史已保存'})

# ========== 市场情绪看板模块 ==========
@app.route('/api/market/sentiment', methods=['GET'])
def api_market_sentiment():
    """获取市场情绪（领涨领跌板块、热门题材排行）"""
    try:
        import akshare as ak
        
        result = {
            'leading_sectors': [],  # 领涨板块
            'lagging_sectors': [],  # 领跌板块
            'hot_topics': [],       # 热门题材
            'market_strength': 0    # 市场强度评分
        }
        
        # 尝试获取板块涨跌数据
        try:
            # 获取行业板块涨跌排行
            sector_data = ak.stock_board_industry_index_em()
            if sector_data and len(sector_data) > 0:
                # 按涨跌幅排序
                sector_data = sector_data.sort_values(by='涨跌幅', ascending=False)
                
                # 领涨板块（前5）
                for i in range(min(5, len(sector_data))):
                    row = sector_data.iloc[i]
                    result['leading_sectors'].append({
                        'name': str(row.get('板块名称', '')),
                        'change': float(row.get('涨跌幅', 0)),
                        'leading_stock': str(row.get('领涨股票', ''))
                    })
                
                # 领跌板块（后5）
                for i in range(max(0, len(sector_data) - 5), len(sector_data)):
                    row = sector_data.iloc[i]
                    result['lagging_sectors'].append({
                        'name': str(row.get('板块名称', '')),
                        'change': float(row.get('涨跌幅', 0)),
                        'leading_stock': str(row.get('领涨股票', ''))
                    })
        except Exception as e:
            print(f"获取板块数据失败: {e}")
        
        # 热门题材（使用预设题材+涨幅计算）
        hot_topics_map = {
            '商业航天': ['航天', '卫星', '军工'],
            '机器人': ['机器人', '自动化', '智能制造'],
            '半导体': ['半导体', '芯片', '集成电路'],
            'AI应用': ['AI', '人工智能', '大模型'],
            '新能源': ['新能源', '光伏', '风电'],
            '锂电': ['锂电池', '锂电', '动力电池'],
            '电池': ['电池', '储能', '钠离子'],
            '电力': ['电力', '电网', '电力设备']
        }
        
        try:
            # 根据板块涨跌幅计算题材热度
            if sector_data and len(sector_data) > 0:
                for topic, keywords in hot_topics_map.items():
                    # 查找相关板块的平均涨幅
                    related_changes = []
                    for kw in keywords:
                        matches = sector_data[sector_data['板块名称'].str.contains(kw, na=False)]
                        if len(matches) > 0:
                            related_changes.extend(matches['涨跌幅'].tolist())
                    
                    avg_change = sum(related_changes) / len(related_changes) if related_changes else 0
                    result['hot_topics'].append({
                        'name': topic,
                        'avg_change': avg_change,
                        'hot_score': max(0, avg_change) * 10  # 热门分
                    })
                
                # 按热门分排序
                result['hot_topics'] = sorted(result['hot_topics'], key=lambda x: x['hot_score'], reverse=True)
        except Exception as e:
            print(f"计算题材热度失败: {e}")
        
        # 计算市场强度评分（基于领涨/领跌板块涨幅）
        leading_avg = sum([s['change'] for s in result['leading_sectors']]) / len(result['leading_sectors']) if result['leading_sectors'] else 0
        lagging_avg = sum([s['change'] for s in result['lagging_sectors']]) / len(result['lagging_sectors']) if result['lagging_sectors'] else 0
        result['market_strength'] = int((leading_avg - lagging_avg) * 10)  # 简化评分
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== AI智能建议模块 ==========
@app.route('/api/ai_suggestion/<code>', methods=['GET'])
def api_ai_suggestion(code):
    """获取AI智能投资建议"""
    try:
        # 获取股票分析数据
        result_file = os.path.join(ANALYSIS_OUTPUT_DIR, f"data_{code}.json")
        
        suggestion = {
            'code': code,
            'overall_score': 0,
            'suggestion': '',
            'key_factors': [],
            'risk_level': '中'
        }
        
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 基于分析数据计算综合评分和建议
            # 评分因素：资金流向、技术面、基本面、市场情绪
            
            score = 50  # 基础分
            
            # 资金流向评分
            fund_flow = data.get('fund_flow', {})
            if fund_flow.get('main_inflow_rate', 0) > 0:
                score += 15
                suggestion['key_factors'].append('主力资金流入')
            elif fund_flow.get('main_outflow_rate', 0) > 0:
                score -= 10
                suggestion['key_factors'].append('主力资金流出')
            
            # 技术面评分
            kline_data = data.get('kline_data', {})
            if kline_data.get('trend', '') == 'up':
                score += 10
                suggestion['key_factors'].append('K线趋势向上')
            elif kline_data.get('trend', '') == 'down':
                score -= 10
                suggestion['key_factors'].append('K线趋势向下')
            
            # 基本面评分
            financial = data.get('financial_summary', {})
            pe = financial.get('pe_ratio', 0)
            if pe > 0 and pe < 30:
                score += 10
                suggestion['key_factors'].append('估值合理')
            elif pe > 50:
                score -= 5
                suggestion['key_factors'].append('估值偏高')
            
            # 市场情绪评分（基于板块热度）
            sector = data.get('sector', '未知')
            # 检查是否在热门题材
            hot_topics = ['商业航天', '机器人', '半导体', '芯片', 'AI应用', '新能源', '锂电', '电池', '电力']
            if any(topic in sector for topic in hot_topics):
                score += 15
                suggestion['key_factors'].append('热门题材概念')
            
            suggestion['overall_score'] = max(0, min(100, score))
            
            # 根据评分生成建议
            if score >= 80:
                suggestion['suggestion'] = '综合评分较高，建议重点关注。多个积极因素叠加，可考虑逢低介入。'
                suggestion['risk_level'] = '低'
            elif score >= 60:
                suggestion['suggestion'] = '综合评分中等，建议观望。部分因素积极但存在不确定性，需等待更多信号。'
                suggestion['risk_level'] = '中'
            elif score >= 40:
                suggestion['suggestion'] = '综合评分偏低，建议谨慎。存在较多不利因素，不宜急于介入。'
                suggestion['risk_level'] = '中高'
            else:
                suggestion['suggestion'] = '综合评分较低，建议回避。多个消极因素叠加，风险较高。'
                suggestion['risk_level'] = '高'
        else:
            suggestion['suggestion'] = '暂无分析数据，请先进行个股深度分析。'
            suggestion['risk_level'] = '未知'
        
        return jsonify({'success': True, 'data': suggestion})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== 报告导出模块 ==========
@app.route('/api/export_report/<code>', methods=['GET'])
def api_export_report(code):
    """导出分析报告为JSON格式（前端可转为PDF或图片）"""
    try:
        result_file = os.path.join(ANALYSIS_OUTPUT_DIR, f"data_{code}.json")
        
        if not os.path.exists(result_file):
            return jsonify({'success': False, 'message': '报告不存在'})
        
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 添加导出格式信息
        export_data = {
            'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'code': code,
            'name': data.get('name', ''),
            'analysis_data': data,
            'export_format': 'json'
        }
        
        return jsonify({'success': True, 'data': export_data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== 价格预警模块 ==========
ALERTS_FILE = os.path.join(PROJECT_DIR, "alerts.json")

def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_alerts(alerts):
    with open(ALERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

@app.route('/api/alerts', methods=['GET'])
def api_get_alerts():
    """获取所有价格预警"""
    alerts = load_alerts()
    return jsonify({'success': True, 'alerts': alerts})

@app.route('/api/alerts/add', methods=['POST'])
def api_add_alert():
    """添加价格预警"""
    try:
        data = request.json
        code = data.get('code')
        name = data.get('name')
        target_price = data.get('target_price')
        alert_type = data.get('alert_type', 'above')  # above/below
        
        if not code or not target_price:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        alerts = load_alerts()
        new_alert = {
            'id': datetime.now().strftime('%Y%m%d%H%M%S') + '_' + code,
            'code': code,
            'name': name or '',
            'target_price': float(target_price),
            'alert_type': alert_type,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'active'
        }
        alerts.append(new_alert)
        save_alerts(alerts)
        
        return jsonify({'success': True, 'message': '预警已添加', 'alert': new_alert})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/alerts/remove/<alert_id>', methods=['DELETE'])
def api_remove_alert(alert_id):
    """删除价格预警"""
    try:
        alerts = load_alerts()
        alerts = [a for a in alerts if a['id'] != alert_id]
        save_alerts(alerts)
        return jsonify({'success': True, 'message': '预警已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ========== 板块对比分析模块 ==========
@app.route('/api/sector_compare', methods=['GET'])
def api_sector_compare():
    """同板块多股票横向对比"""
    try:
        codes = request.args.get('codes', '')
        if not codes:
            return jsonify({'success': False, 'message': '请提供股票代码'})
        
        code_list = codes.split(',')
        if len(code_list) < 2:
            return jsonify({'success': False, 'message': '请提供至少2个股票代码'})
        
        compare_data = []
        for code in code_list[:5]:  # 最多5个
            result_file = os.path.join(ANALYSIS_OUTPUT_DIR, f"data_{code}.json")
            if os.path.exists(result_file):
                with open(result_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                compare_data.append({
                    'code': code,
                    'name': data.get('name', ''),
                    'price': data.get('price', 0),
                    'change': data.get('change', 0),
                    'market_cap': data.get('market_cap', 0),
                    'turnover': data.get('turnover', 0),
                    'volume_ratio': data.get('volume_ratio', 0),
                    'score': data.get('score', 0),
                    'trend': data.get('trend', '未知')
                })
        
        if len(compare_data) < 2:
            return jsonify({'success': False, 'message': '请先分析对比的股票'})
        
        # 按评分排序
        compare_data.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return jsonify({'success': True, 'data': compare_data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    os.makedirs(os.path.join(PROJECT_DIR, "logs"), exist_ok=True)
    print("启动Web服务: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
