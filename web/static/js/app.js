const API = window.location.origin;
let currentTab = 'realtime';
let pollInterval = null;
let currentSector = '商业航天';
let sectorDataCache = {};
const SECTORS = ["商业航天", "机器人", "半导体", "芯片", "AI应用", "新能源", "锂电", "电池", "电力"];

function el(id) { return document.getElementById(id); }

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