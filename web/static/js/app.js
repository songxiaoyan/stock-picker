const API = window.location.origin;
let currentTab = 'realtime';
let pollInterval = null;
let currentSector = '商业航天';
let sectorDataCache = {};
const SECTORS = ["商业航天", "机器人", "半导体", "芯片", "AI应用", "新能源", "锂电", "电池", "电力"];

// 搜索相关变量
let searchDebounceTimer = null;
let lastSearchQuery = '';

function el(id) { return document.getElementById(id); }

// 搜索功能：处理输入（带防抖）
function handleSearchInput() {
    var input = el('search-input');
    var query = input ? input.value.trim() : '';
    
    // 清除之前的防抖定时器
    if (searchDebounceTimer) {
        clearTimeout(searchDebounceTimer);
    }
    
    // 输入为空时隐藏建议
    if (!query) {
        hideSearchSuggest();
        return;
    }
    
    // 防抖：300ms后执行搜索
    searchDebounceTimer = setTimeout(function() {
        if (query.length >= 1) {  // 输入至少1个字符才开始搜索
            fetchSearchSuggestions(query);
        }
    }, 300);
}

// 获取搜索建议
function fetchSearchSuggestions(query) {
    if (query === lastSearchQuery) return;  // 避免重复请求
    lastSearchQuery = query;
    
    fetch(API + '/api/search?q=' + encodeURIComponent(query))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.results && data.results.length > 0) {
                renderSearchSuggest(data.results);
            } else {
                hideSearchSuggest();
            }
        })
        .catch(function(e) {
            console.log('搜索失败:', e);
            hideSearchSuggest();
        });
}

// 渲染搜索建议下拉
function renderSearchSuggest(results) {
    var suggestBox = el('search-suggest');
    if (!suggestBox) return;
    
    var html = '';
    for (var i = 0; i < results.length; i++) {
        var stock = results[i];
        var changeColor = stock.change > 0 ? 'text-red-400' : (stock.change < 0 ? 'text-green-400' : 'text-slate-400');
        var changeText = stock.change > 0 ? '+' + stock.change.toFixed(2) + '%' : stock.change.toFixed(2) + '%';
        
        html += '<div class="px-3 py-2 hover:bg-slate-700 cursor-pointer flex items-center justify-between" onclick="selectSearchStock(\'' + stock.code + '\')">';
        html += '<div class="flex items-center gap-2">';
        html += '<span class="text-violet-400 font-mono text-sm">' + stock.code + '</span>';
        html += '<span class="text-white text-sm">' + stock.name + '</span>';
        html += '<span class="text-slate-500 text-xs">' + (stock.industry || '--') + '</span>';
        html += '</div>';
        html += '<div class="flex items-center gap-3 text-xs">';
        html += '<span class="text-slate-300">' + stock.price.toFixed(2) + '</span>';
        html += '<span class="' + changeColor + ' font-medium">' + changeText + '</span>';
        html += '<button onclick="analyzeStock(\'' + stock.code + '\'); event.stopPropagation();" class="bg-violet-600 hover:bg-violet-500 text-white px-2 py-1 rounded text-xs ml-2">';
        html += '<i class="fas fa-chart-bar"></i> 分析';
        html += '</button>';
        html += '</div>';
        html += '</div>';
    }
    
    suggestBox.innerHTML = html;
    suggestBox.classList.remove('hidden');
}

// 隐藏搜索建议
function hideSearchSuggest() {
    var suggestBox = el('search-suggest');
    if (suggestBox) {
        suggestBox.classList.add('hidden');
    }
}

// 选择搜索结果中的股票（跳转到分析页面）
function selectSearchStock(code) {
    hideSearchSuggest();
    var input = el('search-input');
    if (input) input.value = '';
    
    // 直接跳转到分析页面
    analyzeStock(code);
}

// 执行搜索（Enter键触发）
function performSearch() {
    var input = el('search-input');
    var query = input ? input.value.trim() : '';
    if (!query) return;
    
    fetch(API + '/api/search?q=' + encodeURIComponent(query))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.results && data.results.length > 0) {
                // 如果只有一个结果，直接跳转分析
                if (data.results.length === 1) {
                    analyzeStock(data.results[0].code);
                } else {
                    // 多个结果时显示建议
                    renderSearchSuggest(data.results);
                }
            } else {
                showToast('未找到匹配的股票', 'error');
            }
        })
        .catch(function(e) {
            showToast('搜索失败', 'error');
        });
}

// 点击页面其他区域隐藏搜索建议
document.addEventListener('click', function(e) {
    var searchInput = el('search-input');
    var searchSuggest = el('search-suggest');
    if (searchSuggest && searchInput) {
        if (!searchInput.contains(e.target) && !searchSuggest.contains(e.target)) {
            hideSearchSuggest();
        }
    }
});

document.addEventListener('DOMContentLoaded', function() {
    setInterval(function() {
        var clock = el('sys-time');
        if (clock) clock.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    }, 1000);
    loadStatus();
    loadHotSectors();
    setInterval(loadHotSectors, 15000);
});

function switchTab(tab) {
    currentTab = tab;
    var rBtn = el('btn-tab-realtime');
    var lBtn = el('btn-tab-limitup');
    var rView = el('view-realtime');
    var lView = el('view-limitup');
    
    if (rBtn) {
        if (tab === 'realtime') {
            rBtn.className = 'px-5 h-full text-sm font-medium border-b-2 border-violet-500 text-white flex items-center gap-2 transition-all hover:bg-slate-700/50';
        } else {
            rBtn.className = 'px-5 h-full text-sm font-medium border-b-2 border-transparent text-slate-400 flex items-center gap-2 hover:text-violet-400 transition-all hover:bg-slate-700/50';
        }
    }
    
    if (lBtn) {
        if (tab === 'limitup') {
            lBtn.className = 'px-5 h-full text-sm font-medium border-b-2 border-violet-500 text-white flex items-center gap-2 transition-all hover:bg-slate-700/50';
        } else {
            lBtn.className = 'px-5 h-full text-sm font-medium border-b-2 border-transparent text-slate-400 flex items-center gap-2 hover:text-violet-400 transition-all hover:bg-slate-700/50';
        }
    }
    
    if (rView) {
        if (tab === 'realtime') {
            rView.className = 'flex-1 overflow-auto p-0';
        } else {
            rView.className = 'hidden flex-1 overflow-auto p-0';
        }
    }
    
    if (lView) {
        if (tab === 'limitup') {
            lView.className = 'flex-1 overflow-auto p-0';
        } else {
            lView.className = 'hidden flex-1 overflow-auto p-0';
        }
    }
}

function loadStatus() {
    fetch(API + '/api/status')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            updateRealtimeUI(data.realtime);
            updateLimitUpUI(data.limitup);
            if ((data.realtime && data.realtime.running) || (data.limitup && data.limitup.running)) {
                if (!pollInterval) startPolling();
            }
        })
        .catch(function(e) { console.log('Status error:', e); });
}

function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(function() {
        fetch(API + '/api/status')
            .then(function(res) { return res.json(); })
            .then(function(data) {
                updateRealtimeUI(data.realtime);
                updateLimitUpUI(data.limitup);
                var isRunning = (data.realtime && data.realtime.running) || (data.limitup && data.limitup.running);
                var active = (data.realtime && data.realtime.running) ? data.realtime : (data.limitup || {});
                
                if (isRunning) {
                    var overlay = el('loading-overlay');
                    var text = el('loading-text');
                    var bar = el('loading-bar');
                    var statusText = el('status-text');
                    var mainBar = el('main-progress-bar');
                    
                    if (overlay) overlay.classList.remove('hidden');
                    if (text) text.textContent = active.message || '执行中...';
                    if (bar) bar.style.width = (active.progress || 0) + '%';
                    if (statusText) statusText.textContent = active.message || '执行中...';
                    if (mainBar) mainBar.style.width = (active.progress || 0) + '%';
                } else {
                    stopPolling();
                    var overlay = el('loading-overlay');
                    if (overlay) overlay.classList.add('hidden');
                    var statusText = el('status-text');
                    if (statusText) statusText.textContent = '就绪';
                    var mainBar = el('main-progress-bar');
                    if (mainBar) mainBar.style.width = '0%';
                }
            })
            .catch(function(e) { console.log('Poll error:', e); });
    }, 1000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

function updateRealtimeUI(state) {
    if (!state) return;
    var btn = el('btn-run-action');
    if (btn) {
        btn.disabled = state.running;
        if (state.running) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>运行中...';
        } else {
            btn.innerHTML = '<i class="fas fa-play"></i> 开始执行';
        }
    }

    if (state.log) {
        var log = el('log-console');
        if (log) log.textContent = state.log;
    }

    if (state.results && state.results.length > 0) {
        var count = el('count-realtime');
        var tbody = el('tbody-realtime');
        if (count) count.textContent = state.results.length + ' 只';
        if (tbody) {
            var html = '';
            for (var i = 0; i < state.results.length; i++) {
                var r = state.results[i];
                html += '<tr class="stock-row border-b border-slate-800/50 transition-colors">';
                html += '<td class="py-2 px-4 font-mono text-violet-400">' + r['代码'] + '</td>';
                html += '<td class="py-2 px-4 font-bold">' + r['名称'] + '</td>';
                html += '<td class="py-2 px-4 text-right">' + r['最新价'] + '</td>';
                // 实时筛选涨幅 - A股习惯：涨红跌绿
                var changeVal = parseFloat(r['涨跌幅']) || 0;
                var changeColor = changeVal > 0 ? 'text-red-400' : (changeVal < 0 ? 'text-green-400' : 'text-slate-300');
                html += '<td class="py-2 px-4 text-right ' + changeColor + ' font-bold">' + r['涨跌幅'] + '</td>';
                html += '<td class="py-2 px-4 text-right">' + r['量比'] + '</td>';
                html += '<td class="py-2 px-4 text-right">' + r['换手率'] + '</td>';
                html += '<td class="py-2 px-4 text-yellow-400 text-xs">' + r['板块'] + '</td>';
                html += '<td class="py-2 px-4 text-center"><button data-analysis-code="' + r['代码'] + '" onclick="event.stopPropagation(); analyzeStock(\'' + r['代码'] + '\', \'' + r['名称'].replace(/'/g, "\\'") + '\')" class="bg-violet-600 hover:bg-violet-500 text-white text-xs px-2 py-1 rounded transition-colors"><i class="fas fa-chart-bar mr-1"></i>分析</button></td>';
                html += '</tr>';
            }
            tbody.innerHTML = html;
            // Update button states for completed analysis
            setTimeout(updateExistingButtons, 100);
        }
        
        // 筛选完成后保存历史记录
        if (!state.running && state.results.length > 0) {
            saveScreenHistoryEntry('realtime', state.results);
        }
    }
}

function updateLimitUpUI(state) {
    if (!state) return;
    if (state.log) {
        var log = el('log-console');
        if (log) log.textContent = state.log;
    }

    if (state.results && state.results.length > 0) {
        var count = el('count-limitup');
        var tbody = el('tbody-limitup');
        if (count) count.textContent = state.results.length + ' 只';
        if (tbody) {
            var html = '';
            for (var i = 0; i < state.results.length; i++) {
                var r = state.results[i];
                var score = r['综合评分'] || 0;
                var colorClass = '';
                if (score > 100) colorClass = 'text-yellow-400 font-bold';
                else if (score > 80) colorClass = 'text-orange-400';
                else colorClass = 'text-slate-400';
                
                html += '<tr class="stock-row border-b border-slate-800/50 transition-colors">';
                html += '<td class="py-2 px-4 text-lg ' + colorClass + '">' + score + '</td>';
                html += '<td class="py-2 px-4 font-mono text-violet-400">' + r['代码'] + '</td>';
                html += '<td class="py-2 px-4 font-bold">' + r['名称'] + '</td>';
                html += '<td class="py-2 px-4 text-right">' + r['最新价'] + '</td>';
                html += '<td class="py-2 px-4 text-center"><span class="bg-red-600 text-white px-2 py-0.5 rounded text-xs">' + (r['涨停次数(近20日)'] || 0) + '次</span></td>';
                html += '<td class="py-2 px-4 text-right text-xs">' + (r['流通市值(亿)'] || '') + '亿</td>';
                html += '<td class="py-2 px-4 text-xs text-blue-300">' + (r['所属行业'] || '') + '</td>';
                html += '<td class="py-2 px-4 text-center"><button data-analysis-code="' + r['代码'] + '" onclick="event.stopPropagation(); analyzeStock(\'' + r['代码'] + '\', \'' + (r['名称'] || '').replace(/'/g, "\\'") + '\')" class="bg-violet-600 hover:bg-violet-500 text-white text-xs px-2 py-1 rounded transition-colors"><i class="fas fa-chart-bar mr-1"></i>分析</button></td>';
                html += '</tr>';
            }
            tbody.innerHTML = html;
            // Update button states for completed analysis
            setTimeout(updateExistingButtons, 100);
        }
        
        // 筛选完成后保存历史记录
        if (!state.running && state.results.length > 0) {
            saveScreenHistoryEntry('limitup', state.results);
        }
    }
}

function runActiveStrategy() {
    var url = currentTab === 'realtime' ? '/api/run' : '/api/run_limit_up';
    fetch(API + url, { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            startPolling();
            var statusText = el('status-text');
            if (statusText) statusText.textContent = '启动中...';
        })
        .catch(function(e) { 
            alert('启动失败: ' + e.message); 
        });
}

function loadHotSectors() {
    fetch(API + '/api/hot_sectors')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.sectors && Object.keys(data.sectors).length > 0) {
                sectorDataCache = data.sectors;
                renderSectorTabs();
                renderHotSector(currentSector);
            }
        })
        .catch(function(e) { console.log('Hot sectors error:', e); });
}

function renderSectorTabs() {
    var container = el('sector-nav');
    if (!container) return;
    
    var html = '';
    for (var i = 0; i < SECTORS.length; i++) {
        var s = SECTORS[i];
        if (sectorDataCache[s] && sectorDataCache[s].length > 0) {
            var activeClass = currentSector === s ? 'active' : 'text-slate-400';
            html += '<button onclick="switchSector(\'' + s + '\')" class="sector-tab px-3 py-1 text-xs rounded border border-transparent whitespace-nowrap ' + activeClass + '">' + s + '</button>';
        }
    }
    container.innerHTML = html;
}

function switchSector(sector) {
    currentSector = sector;
    renderSectorTabs();
    renderHotSector(sector);
}

function renderHotSector(sector) {
    var list = sectorDataCache[sector] || [];
    var tbody = el('tbody-hot-sector');
    if (!tbody) return;

    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-slate-500">暂无数据</td></tr>';
        return;
    }

    var html = '';
    for (var i = 0; i < list.length; i++) {
        var s = list[i];
        var score = (s['成交额'] || 0) * 0.4 + (s['量比'] || 0) * 1e7 * 0.3 + (s['换手率'] || 0) * 1e7 * 0.2;
        var scoreStr = (score / 1e8).toFixed(2);
        var rankColor = i < 3 ? 'text-yellow-400 font-bold' : 'text-slate-400';
        // 热门板块涨幅 - A股习惯：涨红跌绿
        var changeColor = (s['涨跌幅'] || 0) > 0 ? 'text-red-400' : 'text-green-400';
        
        html += '<tr class="stock-row border-b border-slate-800/50 transition-colors cursor-pointer">';
        html += '<td class="py-2 px-4 text-center ' + rankColor + '">' + (i + 1) + '</td>';
        html += '<td class="py-2 px-4 font-mono text-violet-400">' + s['代码'] + '</td>';
        html += '<td class="py-2 px-4 font-bold">' + s['名称'] + '</td>';
        html += '<td class="py-2 px-4 text-right">' + s['最新价'] + '</td>';
        html += '<td class="py-2 px-4 text-right ' + changeColor + '">' + (s['涨跌幅'] || 0).toFixed(2) + '%</td>';
        html += '<td class="py-2 px-4 text-right">' + s['量比'] + '</td>';
        html += '<td class="py-2 px-4 text-right text-yellow-400">' + scoreStr + '</td>';
        html += '<td class="py-2 px-4 text-center"><button data-analysis-code="' + s['代码'] + '" onclick="event.stopPropagation(); analyzeStock(\'' + s['代码'] + '\', \'' + (s['名称'] || '').replace(/'/g, "\\'") + '\')" class="bg-violet-600 hover:bg-violet-500 text-white text-xs px-2 py-1 rounded transition-colors"><i class="fas fa-chart-bar mr-1"></i>分析</button></td>';
        html += '</tr>';
    }
    tbody.innerHTML = html;
    // Update button states for completed analysis
    setTimeout(updateExistingButtons, 100);
}

function saveSchedule() {
    var hour = el('sch-hour');
    var min = el('sch-min');
    var toggle = el('schedule-toggle');
    
    var data = {
        hour: hour ? hour.value : '14',
        minute: min ? min.value : '30',
        enabled: toggle ? toggle.checked : true
    };
    
    fetch(API + '/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                alert('定时任务设置成功！');
            } else {
                alert('设置失败: ' + data.message);
            }
        })
        .catch(function(e) {
            alert('请求失败');
        });
}

// --- Stock Analysis Functions ---
var analysisTasks = {};  // code -> {task_id, status, name}
var completedAnalysis = {};  // code -> {name, time} from history

// Load analysis history on page load
function loadAnalysisHistory() {
    fetch(API + '/api/analysis/list')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.list) {
                for (var i = 0; i < data.list.length; i++) {
                    var h = data.list[i];
                    completedAnalysis[h.code] = {
                        name: h.name,
                        time: h.time
                    };
                }
                // Update buttons for already analyzed stocks
                updateExistingButtons();
                // Render history list in sidebar
                renderAnalysisHistory(data.list);
            }
        })
        .catch(function(e) { console.log('History load error:', e); });
}

// Call on page load
document.addEventListener('DOMContentLoaded', function() {
    loadAnalysisHistory();
});

function updateExistingButtons() {
    // Find all analysis buttons and check if they have completed analysis
    var buttons = document.querySelectorAll('[data-analysis-code]');
    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        var code = btn.getAttribute('data-analysis-code');
        if (completedAnalysis[code]) {
            // Already analyzed - show "查看报告"
            btn.className = 'bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-2 py-1 rounded transition-colors';
            btn.innerHTML = '<i class="fas fa-file-alt mr-1"></i>查看报告';
            btn.disabled = false;
            // Fix closure issue - use data attribute
            btn.onclick = function(e) {
                e.stopPropagation();
                var thisCode = this.getAttribute('data-analysis-code');
                window.location.href = '/analysis/' + thisCode;
            };
        }
    }
}

function renderAnalysisHistory(list) {
    var container = document.getElementById('analysis-history-list');
    if (!container) return;
    
    if (!list || list.length === 0) {
        container.innerHTML = '<p class="text-slate-500 text-xs text-center py-2">暂无分析记录</p>';
        return;
    }
    
    var html = '';
    for (var i = 0; i < Math.min(list.length, 5); i++) {
        var h = list[i];
        html += '<div class="flex items-center justify-between py-1 border-b border-slate-700/50">';
        html += '<div class="text-xs">';
        html += '<span class="text-violet-400 font-mono">' + h.code + '</span> ';
        html += '<span class="text-slate-300">' + h.name + '</span>';
        html += '</div>';
        html += '<button onclick="window.location.href=\'/analysis/' + h.code + '\'" class="text-xs text-emerald-400 hover:text-emerald-300">';
        html += '<i class="fas fa-external-link-alt"></i>';
        html += '</button>';
        html += '</div>';
    }
    container.innerHTML = html;
}

function analyzeStock(code, name) {
    // Show toast notification
    showToast('已启动后台分析：' + name + '(' + code + ')', 'info');
    
    // Update button to "分析中..." state immediately
    updateAnalysisButton(code, 'running', name);
    
    // Start analysis
    fetch(API + '/api/analyze/' + code, { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                analysisTasks[code] = {
                    task_id: data.task_id,
                    status: 'running',
                    name: name
                };
                startBackgroundPoll(data.task_id, code, name);
            } else {
                showToast('启动分析失败: ' + data.message, 'error');
                updateAnalysisButton(code, 'error', name);
            }
        })
        .catch(function(e) {
            showToast('请求失败: ' + e.message, 'error');
            updateAnalysisButton(code, 'error', name);
        });
}

function startBackgroundPoll(taskId, code, name) {
    var pollInterval = setInterval(function() {
        fetch(API + '/api/analysis/status/' + taskId)
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success && data.task) {
                    var task = data.task;
                    
                    if (task.status === 'completed') {
                        clearInterval(pollInterval);
                        analysisTasks[code] = {
                            task_id: taskId,
                            status: 'completed',
                            name: name
                        };
                        completedAnalysis[code] = { name: name, time: new Date().toISOString() };
                        // Show completion toast
                        showToast(name + '(' + code + ') 分析完成', 'success');
                        // Update button to "查看报告"
                        updateAnalysisButton(code, 'completed', name);
                        // Refresh history list in sidebar
                        loadAnalysisHistory();
                    } else if (task.status === 'failed') {
                        clearInterval(pollInterval);
                        analysisTasks[code] = {
                            task_id: taskId,
                            status: 'failed',
                            name: name
                        };
                        showToast('分析失败: ' + task.message, 'error');
                        updateAnalysisButton(code, 'error', name);
                    }
                }
            })
            .catch(function(e) { 
                console.log('Poll error:', e);
            });
    }, 3000);
    
    // Store interval for cleanup
    analysisTasks[code].pollInterval = pollInterval;
}

function updateAnalysisButton(code, status, name) {
    // Find all buttons for this stock code and update them
    var buttons = document.querySelectorAll('[data-analysis-code="' + code + '"]');
    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        if (status === 'running') {
            btn.className = 'bg-slate-600 text-white text-xs px-2 py-1 rounded transition-colors cursor-not-allowed';
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>分析中...';
            btn.disabled = true;
            btn.onclick = null;
        } else if (status === 'completed') {
            btn.className = 'bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-2 py-1 rounded transition-colors';
            btn.innerHTML = '<i class="fas fa-file-alt mr-1"></i>查看报告';
            btn.disabled = false;
            btn.onclick = function(e) {
                e.stopPropagation();
                var thisCode = this.getAttribute('data-analysis-code');
                window.location.href = '/analysis/' + thisCode;
            };
        } else if (status === 'error') {
            btn.className = 'bg-violet-600 hover:bg-violet-500 text-white text-xs px-2 py-1 rounded transition-colors';
            btn.innerHTML = '<i class="fas fa-chart-bar mr-1"></i>分析';
            btn.disabled = false;
        }
    }
}

function showToast(message, type) {
    var container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
        document.body.appendChild(container);
    }
    
    var toast = document.createElement('div');
    var bgColor = type === 'success' ? 'bg-emerald-600' : (type === 'error' ? 'bg-red-600' : 'bg-slate-600');
    toast.className = bgColor + ' text-white px-4 py-2 rounded shadow-lg text-sm flex items-center gap-2 animate-slide-in';
    
    var icon = type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle');
    toast.innerHTML = '<i class="fas ' + icon + '"></i>' + message;
    
    container.appendChild(toast);
    
    // Auto remove after 3 seconds
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(function() {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }, 3000);
}

function viewAnalysisResult(code) {
    window.location.href = '/analysis/' + code;
}

// ========== 持仓管理功能 ==========
var currentSellCode = '';

function loadPositions() {
    fetch(API + '/api/positions')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderPositions(data.positions);
            }
        })
        .catch(function(e) {
            console.log('加载持仓失败:', e);
        });
}

function renderPositions(positions) {
    var container = document.getElementById('positions-list');
    var summary = document.getElementById('positions-summary');
    
    if (!positions || positions.length === 0) {
        container.innerHTML = '<p class="text-slate-500 text-xs text-center py-2">暂无持仓记录</p>';
        if (summary) summary.classList.add('hidden');
        return;
    }
    
    var html = '';
    var totalValue = 0;
    var totalProfit = 0;
    
    for (var i = 0; i < positions.length; i++) {
        var pos = positions[i];
        totalValue += pos.current_value || 0;
        totalProfit += pos.profit || 0;
        
        var profitColor = pos.profit > 0 ? 'text-red-400' : (pos.profit < 0 ? 'text-green-400' : 'text-slate-400');
        var profitRateColor = pos.profit_rate > 0 ? 'text-red-400' : (pos.profit_rate < 0 ? 'text-green-400' : 'text-slate-400');
        
        html += '<div class="flex items-center justify-between py-1 border-b border-slate-700/50">';
        html += '<div class="text-xs">';
        html += '<span class="text-violet-400 font-mono">' + pos.code + '</span> ';
        html += '<span class="text-slate-300">' + pos.name + '</span>';
        html += '</div>';
        html += '<div class="flex items-center gap-2">';
        html += '<span class="' + profitColor + ' font-bold">' + (pos.profit > 0 ? '+' : '') + pos.profit.toFixed(0) + '</span>';
        html += '<button onclick="showSellPositionModal(\'' + pos.code + '\',\'' + pos.name + '\',' + pos.quantity + ',' + pos.current_price + ')" class="text-xs text-red-400 hover:text-red-300"><i class="fas fa-minus"></i></button>';
        html += '</div>';
        html += '</div>';
    }
    
    container.innerHTML = html;
    
    if (summary) {
        summary.classList.remove('hidden');
        document.getElementById('total-value').textContent = totalValue.toFixed(0) + '元';
        var totalProfitEl = document.getElementById('total-profit');
        totalProfitEl.textContent = (totalProfit > 0 ? '+' : '') + totalProfit.toFixed(0) + '元';
        totalProfitEl.className = 'font-bold ' + (totalProfit > 0 ? 'text-red-400' : (totalProfit < 0 ? 'text-green-400' : 'text-slate-400'));
    }
}

function showAddPositionModal() {
    document.getElementById('add-position-modal').classList.remove('hidden');
    // 清空输入框
    document.getElementById('pos-code').value = '';
    document.getElementById('pos-name').value = '';
    document.getElementById('pos-price').value = '';
    document.getElementById('pos-qty').value = '';
    document.getElementById('pos-stop-loss').value = '';
    document.getElementById('pos-stop-profit').value = '';
}

function hideAddPositionModal() {
    document.getElementById('add-position-modal').classList.add('hidden');
}

function addPosition() {
    var code = document.getElementById('pos-code').value.trim();
    var name = document.getElementById('pos-name').value.trim();
    var price = parseFloat(document.getElementById('pos-price').value) || 0;
    var qty = parseInt(document.getElementById('pos-qty').value) || 0;
    var stopLoss = parseFloat(document.getElementById('pos-stop-loss').value) || 0;
    var stopProfit = parseFloat(document.getElementById('pos-stop-profit').value) || 0;
    
    if (!code || price <= 0 || qty <= 0) {
        showToast('请填写完整信息', 'error');
        return;
    }
    
    fetch(API + '/api/positions/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            code: code,
            name: name,
            buy_price: price,
            quantity: qty,
            stop_loss: stopLoss,
            stop_profit: stopProfit
        })
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                showToast(data.message, 'success');
                hideAddPositionModal();
                loadPositions();
            } else {
                showToast(data.message, 'error');
            }
        })
        .catch(function(e) {
            showToast('添加失败', 'error');
        });
}

function showSellPositionModal(code, name, quantity, currentPrice) {
    currentSellCode = code;
    document.getElementById('sell-pos-info').textContent = name + '(' + code + ') 持有' + quantity + '股 当前价' + currentPrice;
    document.getElementById('sell-qty').value = quantity;  // 默认全部卖出
    document.getElementById('sell-price').value = currentPrice;  // 默认当前价卖出
    document.getElementById('sell-position-modal').classList.remove('hidden');
}

function hideSellPositionModal() {
    document.getElementById('sell-position-modal').classList.add('hidden');
    currentSellCode = '';
}

function sellPosition() {
    var qty = parseInt(document.getElementById('sell-qty').value) || 0;
    var price = parseFloat(document.getElementById('sell-price').value) || 0;
    
    if (!currentSellCode || qty <= 0) {
        showToast('请填写完整信息', 'error');
        return;
    }
    
    fetch(API + '/api/positions/sell', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            code: currentSellCode,
            quantity: qty,
            sell_price: price
        })
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                showToast(data.message, 'success');
                hideSellPositionModal();
                loadPositions();
            } else {
                showToast(data.message, 'error');
            }
        })
        .catch(function(e) {
            showToast('卖出失败', 'error');
        });
}

// ========== 关注股池功能 ==========
function loadWatchlist() {
    fetch(API + '/api/watchlist')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderWatchlist(data.watchlist);
            }
        })
        .catch(function(e) {
            console.log('加载关注列表失败:', e);
        });
}

function renderWatchlist(watchlist) {
    var container = document.getElementById('watchlist');
    var countEl = document.getElementById('watchlist-count');
    
    if (!watchlist || watchlist.length === 0) {
        container.innerHTML = '<p class="text-slate-500 text-xs text-center py-2">点击股票行的☆添加关注</p>';
        if (countEl) countEl.textContent = '0 只';
        return;
    }
    
    if (countEl) countEl.textContent = watchlist.length + ' 只';
    
    var html = '';
    for (var i = 0; i < watchlist.length; i++) {
        var item = watchlist[i];
        var changeColor = item.change > 0 ? 'text-red-400' : (item.change < 0 ? 'text-green-400' : 'text-slate-400');
        
        html += '<div class="flex items-center justify-between py-1 border-b border-slate-700/50">';
        html += '<div class="text-xs">';
        html += '<span class="text-violet-400 font-mono">' + item.code + '</span> ';
        html += '<span class="text-slate-300">' + item.name + '</span>';
        html += '</div>';
        html += '<div class="flex items-center gap-2">';
        html += '<span class="' + changeColor + '">' + item.current_price.toFixed(2) + '</span>';
        html += '<button onclick="removeFromWatchlist(\'' + item.code + '\')" class="text-xs text-pink-400 hover:text-pink-300"><i class="fas fa-times"></i></button>';
        html += '</div>';
        html += '</div>';
    }
    
    container.innerHTML = html;
}

function addToWatchlist(code, name) {
    fetch(API + '/api/watchlist/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code, name: name})
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                showToast('已关注 ' + name, 'success');
                loadWatchlist();
            } else {
                showToast(data.message, 'error');
            }
        })
        .catch(function(e) {
            showToast('关注失败', 'error');
        });
}

function removeFromWatchlist(code) {
    fetch(API + '/api/watchlist/remove', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code})
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                showToast('已取消关注', 'success');
                loadWatchlist();
            }
        })
        .catch(function(e) {
            showToast('取消关注失败', 'error');
        });
}

// ========== 大盘数据功能 ==========
function loadMarketIndex() {
    fetch(API + '/api/market/index')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                renderMarketIndex(data.data);
            }
        })
        .catch(function(e) {
            console.log('加载大盘指数失败:', e);
        });
}

function renderMarketIndex(data) {
    // 上证指数
    if (data.sh) {
        document.getElementById('index-sh').textContent = data.sh.price.toFixed(2);
        var shChange = data.sh.change;
        var shChangeEl = document.getElementById('index-sh-change');
        shChangeEl.textContent = (shChange >= 0 ? '+' : '') + shChange.toFixed(2) + '%';
        shChangeEl.className = 'text-xs ' + (shChange >= 0 ? 'text-red-400' : 'text-green-400');
    }
    
    // 深证成指
    if (data.sz) {
        document.getElementById('index-sz').textContent = data.sz.price.toFixed(2);
        var szChange = data.sz.change;
        var szChangeEl = document.getElementById('index-sz-change');
        szChangeEl.textContent = (szChange >= 0 ? '+' : '') + szChange.toFixed(2) + '%';
        szChangeEl.className = 'text-xs ' + (szChange >= 0 ? 'text-red-400' : 'text-green-400');
    }
    
    // 创业板
    if (data.cyb) {
        document.getElementById('index-cyb').textContent = data.cyb.price.toFixed(2);
        var cybChange = data.cyb.change;
        var cybChangeEl = document.getElementById('index-cyb-change');
        cybChangeEl.textContent = (cybChange >= 0 ? '+' : '') + cybChange.toFixed(2) + '%';
        cybChangeEl.className = 'text-xs ' + (cybChange >= 0 ? 'text-red-400' : 'text-green-400');
    }
}

function loadMarketNorth() {
    fetch(API + '/api/market/north')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                var northEl = document.getElementById('north-fund');
                var netFlow = data.data.net_flow || 0;
                northEl.textContent = (netFlow >= 0 ? '+' : '') + netFlow.toFixed(0) + '亿';
                northEl.className = 'text-sm font-bold ' + (netFlow >= 0 ? 'text-red-400' : 'text-green-400');
            }
        })
        .catch(function(e) {
            console.log('加载北向资金失败:', e);
        });
}

function loadMarketLimitStat() {
    fetch(API + '/api/market/limit_stat')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                document.getElementById('limit-up').textContent = data.data.limit_up || '--';
                document.getElementById('limit-down').textContent = data.data.limit_down || '--';
            }
        })
        .catch(function(e) {
            console.log('加载涨跌停统计失败:', e);
        });
}

function loadAllMarketData() {
    loadMarketIndex();
    loadMarketNorth();
    loadMarketLimitStat();
    loadMarketSentiment();
}

// ========== 市场情绪看板功能 ==========
function loadMarketSentiment() {
    fetch(API + '/api/market/sentiment')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                renderMarketSentiment(data.data);
            }
        })
        .catch(function(e) {
            console.log('加载市场情绪失败:', e);
        });
}

function renderMarketSentiment(data) {
    // 市场强度
    var strength = data.market_strength || 0;
    var strengthEl = document.getElementById('market-strength');
    var strengthBar = document.getElementById('market-strength-bar');
    
    if (strengthEl) {
        strengthEl.textContent = strength > 0 ? '+' + strength : strength;
        strengthEl.className = 'text-xs font-bold ' + (strength > 0 ? 'text-red-400' : (strength < 0 ? 'text-green-400' : 'text-slate-300'));
    }
    if (strengthBar) {
        strengthBar.style.width = Math.max(0, Math.min(100, Math.abs(strength))) + '%';
        strengthBar.className = 'h-1 rounded-full transition-all ' + (strength > 0 ? 'bg-red-500' : (strength < 0 ? 'bg-green-500' : 'bg-slate-500'));
    }
    
    // 领涨板块
    var leadingEl = document.getElementById('leading-sectors');
    if (leadingEl && data.leading_sectors && data.leading_sectors.length > 0) {
        var html = '';
        for (var i = 0; i < Math.min(3, data.leading_sectors.length); i++) {
            var s = data.leading_sectors[i];
            html += '<p class="text-slate-300">' + s.name + ' <span class="text-red-400">' + (s.change > 0 ? '+' : '') + s.change.toFixed(2) + '%</span></p>';
        }
        leadingEl.innerHTML = html;
    }
    
    // 领跌板块
    var laggingEl = document.getElementById('lagging-sectors');
    if (laggingEl && data.lagging_sectors && data.lagging_sectors.length > 0) {
        var html = '';
        for (var i = 0; i < Math.min(3, data.lagging_sectors.length); i++) {
            var s = data.lagging_sectors[i];
            html += '<p class="text-slate-300">' + s.name + ' <span class="text-green-400">' + s.change.toFixed(2) + '%</span></p>';
        }
        laggingEl.innerHTML = html;
    }
}

// ========== AI智能建议功能 ==========
function loadAiSuggestion(code, callback) {
    fetch(API + '/api/ai_suggestion/' + code)
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                if (callback) callback(data.data);
            }
        })
        .catch(function(e) {
            console.log('加载AI建议失败:', e);
        });
}

function renderAiSuggestion(suggestion) {
    var score = suggestion.overall_score || 0;
    var scoreColor = score >= 80 ? 'text-red-400' : (score >= 60 ? 'text-yellow-400' : (score >= 40 ? 'text-orange-400' : 'text-green-400'));
    
    var html = '<div class="bg-slate-700/50 rounded p-3">';
    html += '<div class="flex justify-between items-center mb-2">';
    html += '<span class="text-xs text-slate-400">综合评分</span>';
    html += '<span class="text-lg font-bold ' + scoreColor + '">' + score + '</span>';
    html += '</div>';
    html += '<div class="w-full bg-slate-700 rounded-full h-1 mb-2">';
    html += '<div class="h-1 rounded-full ' + (score >= 80 ? 'bg-red-500' : (score >= 60 ? 'bg-yellow-500' : (score >= 40 ? 'bg-orange-500' : 'bg-green-500'))) + '" style="width:' + score + '%"></div>';
    html += '</div>';
    html += '<p class="text-xs text-white mb-2">' + suggestion.suggestion + '</p>';
    if (suggestion.key_factors && suggestion.key_factors.length > 0) {
        html += '<div class="text-xs text-slate-300">';
        html += '<span class="text-slate-400">关键因素:</span> ';
        for (var i = 0; i < suggestion.key_factors.length; i++) {
            html += suggestion.key_factors[i];
            if (i < suggestion.key_factors.length - 1) html += ', ';
        }
        html += '</div>';
    }
    html += '<div class="mt-2 text-xs">';
    html += '<span class="text-slate-400">风险等级:</span> ';
    var riskColor = suggestion.risk_level === '低' ? 'text-emerald-400' : (suggestion.risk_level === '中' ? 'text-yellow-400' : (suggestion.risk_level === '中高' ? 'text-orange-400' : 'text-red-400'));
    html += '<span class="' + riskColor + '">' + suggestion.risk_level + '</span>';
    html += '</div>';
    html += '</div>';
    
    return html;
}

// ========== 报告导出功能 ==========
function exportReport(code) {
    fetch(API + '/api/export_report/' + code)
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                // 生成下载链接
                var blob = new Blob([JSON.stringify(data.data, null, 2)], {type: 'application/json'});
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'stock_report_' + code + '_' + new Date().toISOString().slice(0,10) + '.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('报告已导出', 'success');
            } else {
                showToast('导出失败: ' + data.message, 'error');
            }
        })
        .catch(function(e) {
            showToast('导出失败', 'error');
        });
}

// ========== 多时间推送功能 ==========
function saveSchedule() {
    var toggle = document.getElementById('schedule-toggle');
    var push930 = document.getElementById('push-930');
    var push1030 = document.getElementById('push-1030');
    var push1400 = document.getElementById('push-1400');
    var push1430 = document.getElementById('push-1430');
    
    var pushTimes = [];
    if (push930 && push930.checked) pushTimes.push('9:30');
    if (push1030 && push1030.checked) pushTimes.push('10:30');
    if (push1400 && push1400.checked) pushTimes.push('14:00');
    if (push1430 && push1430.checked) pushTimes.push('14:30');
    
    showToast('推送设置已保存: ' + pushTimes.join(', '), 'success');
    // TODO: 保存到后端
}

// ========== 页面初始化 ==========
document.addEventListener('DOMContentLoaded', function() {
    // 原有初始化
    setInterval(function() {
        var clock = document.getElementById('sys-time');
        if (clock) clock.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    }, 1000);
    loadStatus();
    loadHotSectors();
    setInterval(loadHotSectors, 15000);
    
    // 新增功能初始化
    loadPositions();
    loadWatchlist();
    loadAllMarketData();
    loadScreenParams();
    
    // 定时刷新持仓和关注股池价格
    setInterval(function() {
        loadPositions();
        loadWatchlist();
        loadAllMarketData();
    }, 30000);  // 每30秒刷新一次
});

// ========== 筛选参数自定义功能 ==========
var screenParams = {};

function loadScreenParams() {
    fetch(API + '/api/screen_params')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.params) {
                screenParams = data.params;
            }
        })
        .catch(function(e) {
            console.log('加载筛选参数失败:', e);
        });
}

function showScreenParamsModal() {
    document.getElementById('screen-params-modal').classList.remove('hidden');
    
    // 加载当前参数到输入框
    document.getElementById('param-change-min').value = screenParams.change_min || 3;
    document.getElementById('param-change-max').value = screenParams.change_max || 5;
    document.getElementById('param-volume-ratio').value = screenParams.volume_ratio_min || 1;
    document.getElementById('param-turnover-min').value = screenParams.turnover_min || 5;
    document.getElementById('param-turnover-max').value = screenParams.turnover_max || 10;
    document.getElementById('param-cap-min').value = screenParams.market_cap_min || 50;
    document.getElementById('param-cap-max').value = screenParams.market_cap_max || 200;
}

function hideScreenParamsModal() {
    document.getElementById('screen-params-modal').classList.add('hidden');
}

function saveScreenParams() {
    var params = {
        change_min: parseFloat(document.getElementById('param-change-min').value) || 3,
        change_max: parseFloat(document.getElementById('param-change-max').value) || 5,
        volume_ratio_min: parseFloat(document.getElementById('param-volume-ratio').value) || 1,
        turnover_min: parseFloat(document.getElementById('param-turnover-min').value) || 5,
        turnover_max: parseFloat(document.getElementById('param-turnover-max').value) || 10,
        market_cap_min: parseFloat(document.getElementById('param-cap-min').value) || 50,
        market_cap_max: parseFloat(document.getElementById('param-cap-max').value) || 200
    };
    
    fetch(API + '/api/screen_params/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(params)
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                screenParams = params;
                showToast('筛选参数已保存', 'success');
                hideScreenParamsModal();
            } else {
                showToast('保存失败', 'error');
            }
        })
        .catch(function(e) {
            showToast('保存失败', 'error');
        });
}

// ========== 筛选历史记录功能 ==========
function showScreenHistoryModal() {
    document.getElementById('screen-history-modal').classList.remove('hidden');
    loadScreenHistory();
}

function hideScreenHistoryModal() {
    document.getElementById('screen-history-modal').classList.add('hidden');
}

function loadScreenHistory() {
    fetch(API + '/api/screen_history')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderScreenHistory(data.history);
            }
        })
        .catch(function(e) {
            console.log('加载筛选历史失败:', e);
        });
}

// 自动保存筛选历史记录（带防重复机制）
var lastSavedHistoryTime = {};
function saveScreenHistoryEntry(type, results) {
    if (!results || results.length === 0) return;
    
    // 防止重复保存（同一类型5分钟内不重复）
    var now = Date.now();
    if (lastSavedHistoryTime[type] && (now - lastSavedHistoryTime[type]) < 300000) {
        return;
    }
    lastSavedHistoryTime[type] = now;
    
    var entry = {
        time: new Date().toLocaleString('zh-CN'),
        type: type,
        count: results.length,
        stocks: results.slice(0, 10).map(function(r) {
            return {
                code: r['代码'],
                name: r['名称'],
                change: r['涨跌幅'] || r['涨幅'] || ''
            };
        })
    };
    
    fetch(API + '/api/screen_history/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entry)
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.success) {
            console.log('筛选历史已保存');
            loadScreenHistory();
        }
    })
    .catch(function(e) {
        console.log('保存筛选历史失败:', e);
    });
}

function renderScreenHistory(history) {
    var container = document.getElementById('screen-history-list');
    
    if (!history || history.length === 0) {
        container.innerHTML = '<p class="text-slate-500 text-xs text-center py-4">暂无历史记录</p>';
        return;
    }
    
    var html = '';
    for (var i = 0; i < history.length; i++) {
        var h = history[i];
        html += '<div class="bg-slate-700/50 rounded p-3 border border-slate-600">';
        html += '<div class="flex justify-between items-center mb-2">';
        html += '<span class="text-xs text-slate-400">' + h.time + '</span>';
        html += '<span class="text-xs text-violet-400">' + (h.type === 'realtime' ? '实时筛选' : '涨停复盘') + '</span>';
        html += '</div>';
        html += '<div class="text-xs text-white">筛选结果: <span class="text-emerald-400">' + h.count + '只</span></div>';
        if (h.results && h.results.length > 0) {
            html += '<div class="mt-2 text-xs text-slate-300">';
            for (var j = 0; j < Math.min(h.results.length, 5); j++) {
                html += h.results[j].code + ' ' + h.results[j].name + ', ';
            }
            if (h.results.length > 5) {
                html += '...';
            }
            html += '</div>';
        }
        html += '</div>';
    }
    
    container.innerHTML = html;
}

// ========== 价格预警功能 ==========
var currentAlertCode = '';
var currentAlertName = '';
var currentAlertPrice = 0;

function showPriceAlertModal(code, name, price) {
    currentAlertCode = code;
    currentAlertName = name;
    currentAlertPrice = price;
    
    document.getElementById('alert-stock-info').textContent = name + '(' + code + ') 当前价: ' + price;
    document.getElementById('alert-target-up').value = '';
    document.getElementById('alert-target-down').value = '';
    document.getElementById('price-alert-modal').classList.remove('hidden');
}

function hidePriceAlertModal() {
    document.getElementById('price-alert-modal').classList.add('hidden');
    currentAlertCode = '';
}

function setPriceAlert() {
    var targetUp = parseFloat(document.getElementById('alert-target-up').value) || 0;
    var targetDown = parseFloat(document.getElementById('alert-target-down').value) || 0;
    
    if (targetUp <= 0 && targetDown <= 0) {
        showToast('请设置至少一个目标价', 'error');
        return;
    }
    
    // 添加到持仓作为止损止盈
    fetch(API + '/api/positions/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            code: currentAlertCode,
            name: currentAlertName,
            buy_price: currentAlertPrice,
            quantity: 1,  // 预警不需要数量，设置1
            stop_loss: targetDown > 0 ? targetDown : 0,
            stop_profit: targetUp > 0 ? targetUp : 0
        })
    })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                showToast('价格预警已设置', 'success');
                hidePriceAlertModal();
            } else {
                showToast('设置失败: ' + data.message, 'error');
            }
        })
        .catch(function(e) {
            showToast('设置失败', 'error');
        });
}

// ========== 板块对比分析功能 ==========
function showSectorCompareModal() {
    document.getElementById('sector-compare-modal').classList.remove('hidden');
    loadSectorCompareOptions();
}

function hideSectorCompareModal() {
    document.getElementById('sector-compare-modal').classList.add('hidden');
}

function loadSectorCompareOptions() {
    var select = document.getElementById('compare-sector-select');
    var sectors = ['商业航天', '机器人', '半导体', '芯片', 'AI应用', '新能源', '锂电', '电池', '电力'];
    
    var html = '<option value="">选择板块...</option>';
    for (var i = 0; i < sectors.length; i++) {
        html += '<option value="' + sectors[i] + '">' + sectors[i] + '</option>';
    }
    select.innerHTML = html;
    
    select.onchange = function() {
        if (select.value) {
            loadSectorCompareData(select.value);
        }
    };
}

function loadSectorCompareData(sector) {
    var container = document.getElementById('sector-compare-content');
    container.innerHTML = '<p class="text-slate-500 text-xs text-center py-4">加载中...</p>';
    
    // 使用热门板块数据
    fetch(API + '/api/hot_sectors')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success && data.data && data.data[sector]) {
                renderSectorCompare(sector, data.data[sector]);
            } else {
                container.innerHTML = '<p class="text-slate-500 text-xs text-center py-4">暂无数据</p>';
            }
        })
        .catch(function(e) {
            container.innerHTML = '<p class="text-slate-500 text-xs text-center py-4">加载失败</p>';
        });
}

function renderSectorCompare(sector, stocks) {
    var container = document.getElementById('sector-compare-content');
    
    if (!stocks || stocks.length === 0) {
        container.innerHTML = '<p class="text-slate-500 text-xs text-center py-4">该板块暂无数据</p>';
        return;
    }
    
    var html = '<div class="text-xs text-slate-300 mb-3">' + sector + '板块共 ' + stocks.length + ' 只股票</div>';
    html += '<table class="w-full text-xs">';
    html += '<thead class="text-slate-400"><tr><th class="py-1 px-2">排名</th><th class="py-1 px-2">代码</th><th class="py-1 px-2">名称</th><th class="py-1 px-2">价格</th><th class="py-1 px-2">涨幅</th><th class="py-1 px-2">量比</th></tr></thead>';
    html += '<tbody class="text-white">';
    
    for (var i = 0; i < stocks.length; i++) {
        var s = stocks[i];
        var changeColor = s.change > 0 ? 'text-red-400' : (s.change < 0 ? 'text-green-400' : 'text-slate-400');
        html += '<tr class="border-b border-slate-700">';
        html += '<td class="py-1 px-2 text-center">' + (i + 1) + '</td>';
        html += '<td class="py-1 px-2 font-mono">' + s.code + '</td>';
        html += '<td class="py-1 px-2">' + s.name + '</td>';
        html += '<td class="py-1 px-2">' + s.price + '</td>';
        html += '<td class="py-1 px-2 ' + changeColor + '">' + s.change + '%</td>';
        html += '<td class="py-1 px-2">' + s.volume_ratio + '</td>';
        html += '</tr>';
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

// ========== 股票表格行添加关注和预警按钮 ==========
function addWatchlistButtonToRow(code, name) {
    return '<button onclick="addToWatchlist(\'' + code + '\',\'' + name + '\')" class="text-xs text-pink-400 hover:text-pink-300 mr-2"><i class="far fa-star"></i></button>';
}

function addAlertButtonToRow(code, name, price) {
    return '<button onclick="showPriceAlertModal(\'' + code + '\',\'' + name + '\',' + price + ')" class="text-xs text-yellow-400 hover:text-yellow-300"><i class="fas fa-bell"></i></button>';
}