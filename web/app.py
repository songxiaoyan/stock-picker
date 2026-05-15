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

PROJECT_DIR = "/mnt/d/hermes-workspace/stock-picker"
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

if __name__ == '__main__':
    os.makedirs(os.path.join(PROJECT_DIR, "logs"), exist_ok=True)
    print("启动Web服务: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
