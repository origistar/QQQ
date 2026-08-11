#!/usr/bin/env python3
"""v5.1 generate.py - 三阶段DD · DD乘数4/5/6 · 反转窗口 · 溢价切换 · 性价比评分 · 历史数据"""
import urllib.request, json, sys, os, time
from datetime import datetime, timezone, date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")

def load_json(path, default={}):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

state = load_json(STATE_FILE, {"sell_active":False,"sell_tier":None,"sell_started":None,
    "sell_week":0,"has_sold":False,"history":[],"bear_start_date":None,"last_data_hash":""})

# ===== 1. DATA FETCH (with freshness check) =====
pe, pe_pct, roe = 31.66, 53.4, 29.98
pe_err = False; pe_fresh = False
try:
    req = urllib.request.Request("https://danjuanfunds.com/djapi/index_eva/dj")
    req.add_header("User-Agent","Mozilla/5.0")
    with urllib.request.urlopen(req,timeout=15) as resp:
        for item in json.loads(resp.read())["data"]["items"]:
            if item.get("index_code")=="NDX": pe=round(item["pe"],2); pe_pct=round(item["pe_percentile"]*100,1); roe=round(item["roe"]*100,1); pe_fresh=True
    with urllib.request.urlopen(req,timeout=15) as resp:
        for item in json.loads(resp.read())["data"]["items"]:
            if item.get("index_code")=="NDX": pe=round(item["pe"],2); pe_pct=round(item["pe_percentile"]*100,1); roe=round(item["roe"]*100,1)
except Exception as e: pe_err = True; print(f"[WARN] PE fetch: {e}",file=sys.stderr)

vix, ndx, ndx52 = 16.50, 29733, 30762
yf_err = False; yf_fresh = False
try:
    import yfinance as yf
    vix_d = yf.Ticker("^VIX").info; ndx_d = yf.Ticker("^NDX").info
    vix = round(vix_d.get("regularMarketPrice", 16.50), 2)
    ndx = int(ndx_d.get("regularMarketPrice", 29733))
    ndx52 = int(ndx_d.get("fiftyTwoWeekHigh", 30762))
    yf_fresh = True
except Exception as e: yf_err = True; print(f"[WARN] yfinance: {e}",file=sys.stderr)

dd_pct = round((ndx - ndx52) / ndx52 * 100, 2)
dd_abs = abs((ndx - ndx52) / ndx52)

# Premium (jisilu)
premium = 13.0
try:
    req = urllib.request.Request("https://www.jisilu.cn/data/qdii/detail/513100")
    req.add_header("User-Agent","Mozilla/5.0")
    with urllib.request.urlopen(req,timeout=10) as resp:
        import re
        m = re.search(r'(\d+\.\d+)%', resp.read().decode())
        if m: premium = float(m.group(1))
except: pass

# ===== 2. TIER CALC (no hysteresis in v5.1) =====
raw_tier = "low" if pe<28 else "mid_low" if pe<=33 else "mid" if pe<=36 else "high" if pe<=38 else "sell"
tier = raw_tier
tn = {"low":"低估","mid_low":"合理偏低","mid":"合理","high":"偏高","sell":"高估/止盈"}[tier]

if vix<13: col, cn = "greed", "贪婪"
elif vix<=18: col, cn = "calm", "平稳"
elif vix<=30: col, cn = "fear", "恐慌"
else: col, cn = "extreme", "极恐"

# ===== 3. MATRIX =====
bm = {("low","greed"):1,("low","calm"):2,("low","fear"):3,("low","extreme"):4,
      ("mid_low","greed"):0.5,("mid_low","calm"):1.5,("mid_low","fear"):2,("mid_low","extreme"):3,
      ("mid","greed"):0.5,("mid","calm"):1,("mid","fear"):1.5,("mid","extreme"):2,
      ("high","greed"):0,("high","calm"):0.5,("high","fear"):1,("high","extreme"):1.5,
      ("sell","greed"):0,("sell","calm"):0,("sell","fear"):0,("sell","extreme"):0}
base = bm.get((tier,col), 0)

# ===== 4. DD MULTIPLIER (v5.1: bear 4/5/6) =====
dd_mult = 1.0
if dd_abs < 0.06: dd_mult = 1.0
elif dd_abs < 0.10: dd_mult = 1.5
elif dd_abs < 0.15: dd_mult = 2.0
elif dd_abs < 0.20: dd_mult = 3.0
elif dd_abs < 0.25: dd_mult = 4.0  # bear zone (v5.1)
elif dd_abs < 0.30: dd_mult = 5.0
else: dd_mult = 6.0

units = 0.0 if tier=="sell" else base * dd_mult
D = 1000 if dd_abs < 0.20 else 500  # daily pool ¥1000, bear ¥500
daily_amount = int(units * D) if units > 0 else 0

# ===== 5. PHASE DETECTION =====
# Track bear streak via state
is_bear = dd_abs >= 0.20
today_str = date.today().isoformat()

if is_bear:
    last_bear = state.get("bear_start_date")
    if not last_bear:
        state["bear_start_date"] = today_str
        bear_months = 0
    else:
        delta = (date.today() - date.fromisoformat(last_bear)).days
        bear_months = delta // 30
    
    if bear_months == 0:
        phase = "⚡反转窗口"
        phase_label = "②"
        daily_label = f"双池齐发（日常锁定×3 + 熊市×{dd_mult:.0f}）"
    else:
        phase = "🐻长熊期"
        phase_label = "③"
        daily_label = f"熊市池独立运作 ×{dd_mult:.0f} + 周追"
else:
    state["bear_start_date"] = None
    bear_months = 0
    phase = "日常期"
    phase_label = "①"
    daily_label = f"日常池 ×{dd_mult:.1f}"

save_json(STATE_FILE, state)

# ===== 6. SCORE =====
pe_score_s = max(0, 100 - pe_pct) * 0.35
dd_score_s = min(100, dd_abs * 400) * 0.25
vix_score_s = min(100, max(0, (vix - 10) * 5)) * 0.20
roe_score_s = min(100, (roe - 10) * 5) * 0.10
ma_dev = abs((ndx - ndx52) / ndx52)
ma_score_s = max(0, 100 - ma_dev * 500) * 0.10
sc = round(pe_score_s + dd_score_s + vix_score_s + roe_score_s + ma_score_s)
sc_label = "极高" if sc >= 71 else "中等" if sc >= 41 else "偏低"

# ===== 7. STOP PROFIT =====
sell_active = state.get("sell_active", False)
sell_tier = state.get("sell_tier")
t1 = pe > 38 and vix < 18
t2 = pe > 40 or (pe > 38 and vix < 13)

if t2:
    state["sell_active"] = True; state["sell_tier"] = 2
    state["sell_started"] = state.get("sell_started") or today_str
    w = (date.today() - date.fromisoformat(state["sell_started"])).days // 7 + 1
    state["sell_week"] = min(w, 5)
elif t1:
    state["sell_active"] = True; state["sell_tier"] = 1
    state["sell_started"] = state.get("sell_started") or today_str
    w = (date.today() - date.fromisoformat(state["sell_started"])).days // 7 + 1
    state["sell_week"] = min(w, 10)
elif pe < 38 and state.get("sell_active"):
    state["sell_active"] = False; state["sell_tier"] = None; state["sell_week"] = 0

# ===== 8. HISTORY =====
history = state.get("history", [])
# Deduplicate: remove existing entry for today if any
history = [h for h in history if h.get("date") != today_str]
history.append({
    "date": today_str,
    "pe": pe, "pe_pct": pe_pct, "vix": vix, "ndx": ndx,
    "dd_pct": round(dd_pct, 2), "tier": tier, "phase": phase_label,
    "score": sc, "daily": daily_amount, "premium": round(premium, 1)
})
# Keep last 365 days
if len(history) > 365: history = history[-365:]
state["history"] = history
save_json(STATE_FILE, state)

# ===== 9. DATA FRESHNESS CHECK =====
data_hash = f"{pe:.2f}|{vix:.2f}|{ndx}"
data_status = []
if not pe_fresh: data_status.append("⚠ PE数据获取失败，可能被防火墙拦截")
if not yf_fresh: data_status.append("⚠ VIX/NDX获取失败")
# Check if data is stale (same hash as last run + data fetch failed)
if not pe_fresh and not yf_fresh:
    sys.exit(1)  # Hard fail - don't push stale data
status_note = " · ".join(data_status) if data_status else "数据正常"
state["last_data_hash"] = data_hash
save_json(STATE_FILE, state)

# ===== 10. HTML =====
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def h(t,c): return ' class="hi"' if t==tier and c==col else ""
def z(v): return ' class="z"' if v==0 else ""
def hm(m): return ' style="background:#fef3c7"' if abs(m-dd_mult)<0.01 else ""

prem_switch = premium < 5
prem_sell = premium > 8

# History chart data (last 90 days)
hist_ndx = [h["ndx"] for h in history[-90:]]
hist_score = [h["score"] for h in history[-90:]]
hist_dates = [h["date"][5:] for h in history[-90:]]  # MM-DD

sell_html = ""
if state["sell_active"]:
    st = state["sell_tier"]; sw = state["sell_week"]
    mw = 5 if st == 2 else 10; wp = round(30/mw, 1)
    sell_html = f'<div class="ca sell"><strong style="color:#dc2626">⚠ 止盈进行中（第{sw}/{mw}周）</strong><p style="font-size:12px;margin-top:4px">PE={pe:.1f}>38 · 每周卖<b>{wp}%</b> · 累计约<b>{sw*wp}%</b></p></div>'

prem_html = ""
if prem_switch:
    prem_html = f'<div class="ca"><h3>💱 溢价切换</h3><p style="font-size:12px">溢价率 <b>{premium:.1f}% < 5%</b> → <span style="color:#16a34a">切换场内ETF买入 · 分批次转存量场外到场内</span></p></div>'
elif prem_sell:
    prem_html = f'<div class="ca"><h3>💱 溢价切换</h3><p style="font-size:12px">溢价率 <b>{premium:.1f}% > 8%</b> → <span style="color:#dc2626">分批次卖出场内持仓，切换回场外（需有场外额度）</span></p></div>'

float_warn = ""
if pe > 33:
    float_warn = '<p style="font-size:11px;color:#d97706;margin-top:4px">🟠 PE>33，请检查持仓浮盈，若>50%可减仓20%</p>'

html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>纳指100 定投决策 v5.1</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a1a2e;line-height:1.6}}
.c{{max-width:720px;margin:0 auto;padding:20px 16px 40px}}
.h{{text-align:center;padding:20px 0 8px}}.h h1{{font-size:20px;font-weight:700}}
.h .d{{font-size:12px;color:#6b7280;margin-top:4px}}
.r{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}}
.r4{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px}}
.cd{{background:#fff;border-radius:12px;padding:12px 8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.va{{font-size:20px;font-weight:700;line-height:1.2}}.lb{{font-size:10px;color:#6b7280;margin-top:2px}}
.dc{{background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;border-radius:14px;padding:18px;text-align:center;margin:14px 0}}
.dc .bg{{font-size:30px;font-weight:800;line-height:1}}.dc .sb{{font-size:13px;opacity:.9;margin-top:4px}}
.ca{{background:#fff;border-radius:12px;padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.ca h3{{font-size:13px;margin-bottom:8px}}
.tb{{width:100%;border-collapse:collapse;font-size:11px}}
.tb th{{background:#1e293b;color:#fff;padding:5px 4px;text-align:center;font-weight:600;font-size:10px}}
.tb td{{text-align:center;padding:5px 4px;border:1px solid #e5e7eb;font-weight:600;font-size:11px}}
.tb td.lb{{background:#f1f5f9;text-align:left;padding-left:6px;font-size:10px}}
.tb td.hi{{background:#fef3c7}}.tb td.z{{color:#cbd5e1}}
.ft{{width:100%;border-collapse:collapse;font-size:11px}}
.ft th{{background:#f1f5f9;padding:5px 6px;text-align:left;font-weight:600;font-size:10px;border-bottom:2px solid #e5e7eb}}
.ft td{{padding:4px 6px;border-bottom:1px solid #e5e7eb;font-size:11px}}
.fo{{font-size:10px;color:#6b7280;text-align:center;border-top:1px solid #e5e7eb;padding-top:12px;margin-top:16px}}
.sell{{border-color:#dc2626!important;background:#fef2f2!important}}
.ph{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}}
.ph1{{background:#f0fdf4;color:#16a34a}}.ph2{{background:#fefce8;color:#d97706}}.ph3{{background:#fef2f2;color:#dc2626}}
</style></head><body><div class="c">
<div class="h"><h1>纳指100 定投决策 v5.1</h1>
<div class="d">更新: {ts} · {status_note} · 性价比{sc}分({sc_label})</div></div>

<div class="r">
<div class="cd"><div class="va">{pe:.2f}</div><div class="lb">PE-TTM · {tn}</div></div>
<div class="cd"><div class="va">{vix:.2f}</div><div class="lb">VIX · {cn}</div></div>
<div class="cd"><div class="va" style="color:{'#dc2626' if dd_pct<0 else '#16a34a'}">{dd_pct:+.2f}%</div><div class="lb">回撤 距52周高</div></div>
</div>
<div class="r">
<div class="cd"><div class="va">{ndx:,}</div><div class="lb">NDX</div></div>
<div class="cd"><div class="va">{roe:.1f}%</div><div class="lb">ROE</div></div>
<div class="cd"><div class="va">{premium:.1f}%</div><div class="lb">溢价率 513100</div></div>
</div>

<div class="dc">
<div class="sb">今日定投 · <span class="ph ph{phase_label}">{phase}</span></div>
<div class="bg">{'止盈暂停' if state["sell_active"] else '¥'+f'{daily_amount:,}'+' / 日' if daily_amount>0 else '暂停'}</div>
<div class="sb">PE×VIX={base}份 × DD×{dd_mult:.1f} × ¥{D} = ¥{daily_amount:,}  {float_warn}</div>
</div>

{sell_html}

<div class="ca"><h3>📊 近90天趋势</h3>
<div style="height:200px"><canvas id="chart"></canvas></div></div>

{prem_html}

<div class="ca"><h3>PE × VIX 基准矩阵</h3>
<div style="overflow-x:auto"><table class="tb">
<tr><th>PE</th><th>贪婪&lt;13</th><th>平稳13-18</th><th>恐慌18-30</th><th>极恐>30</th></tr>
<tr><td class="lb">PE<28</td><td{h("low","greed")}>1.0</td><td{h("low","calm")}>2.0</td><td{h("low","fear")}>3.0</td><td{h("low","extreme")}>4.0</td></tr>
<tr><td class="lb">28~33</td><td{h("mid_low","greed")}>0.5</td><td{h("mid_low","calm")}>1.5</td><td{h("mid_low","fear")}>2.0</td><td{h("mid_low","extreme")}>3.0</td></tr>
<tr><td class="lb">33~36</td><td{h("mid","greed")}>0.5</td><td{h("mid","calm")}>1.0</td><td{h("mid","fear")}>1.5</td><td{h("mid","extreme")}>2.0</td></tr>
<tr><td class="lb">36~38</td><td{z(bm[("high","greed")])}{h("high","greed")}>0.0</td><td{h("high","calm")}>0.5</td><td{h("high","fear")}>1.0</td><td{h("high","extreme")}>1.5</td></tr>
<tr><td class="lb">>38</td><td>0</td><td>0</td><td>0</td><td>0</td></tr></table></div></div>

<div class="ca"><h3>DD 回撤乘数 · 三阶段</h3>
<table class="ft">
<tr><th>DD</th><th>&lt;6%</th><th>6-10%</th><th>10-15%</th><th>15-20%</th><th>20-25%</th><th>25-30%</th><th>>30%</th></tr>
<tr><td style="font-weight:600">日常</td><td{hm(1.0)}>×1.0</td><td{hm(1.5)}>×1.5</td><td{hm(2.0)}>×2.0</td><td{hm(3.0)}>×3.0</td><td>暂停</td><td>暂停</td><td>暂停</td></tr>
<tr><td style="font-weight:600">熊市</td><td>—</td><td>—</td><td>—</td><td>—</td><td{hm(4.0)}>×4.0</td><td{hm(5.0)}>×5.0</td><td{hm(6.0)}>×6.0</td></tr>
</table>
<p style="font-size:10px;color:#6b7280;margin-top:4px">DD<20%：日常池 · DD≥20%≤1月：反转窗口双池齐发 · DD≥20%>1月：长熊期熊市池独立运作</p></div>

<div class="ca"><h3>🎯 性价比评分 {sc}分（{sc_label}）</h3>
<p style="font-size:11px;color:#6b7280">PE分位({pe_pct:.0f}%)×35% · DD({dd_pct:+.1f}%)×25% · VIX({vix:.1f})×20% · ROE({roe:.0f}%)×10% · 均线×10%<br>71-100 极高 · 41-70 中等 · 10-40 偏低</p></div>

<div class="ca"><h3>止盈规则</h3>
<p style="font-size:11px"><b>PE>38</b> 且 VIX<18 → 每周卖3%，10周30%<br><b>PE>38</b> 且 VIX<13 → 每周卖6-8%，4-5周<br><b>PE>33 且浮盈>50%</b> → 卖出20%，分2-3次<br>PE回落<38 立即停止 | 买回: PE<32 或 DD>15%</p></div>

<div class="fo">v5.1 金字塔定投 · 三阶段DD · 溢价切换 · 每日更新 · 仅供参考不构成投资建议</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
const ctx=document.getElementById('chart').getContext('2d');
new Chart(ctx,{{
type:'line',
data:{{
labels:{json.dumps(hist_dates)},
datasets:[
{{label:'NDX',data:{json.dumps(hist_ndx)},borderColor:'#2563eb',yAxisID:'y',tension:0.2,pointRadius:0}},
{{label:'评分',data:{json.dumps(hist_score)},borderColor:'#f59e0b',yAxisID:'y1',tension:0.2,pointRadius:0,borderDash:[3,3]}}
]}},
options:{{
responsive:true,maintainAspectRatio:false,
plugins:{{legend:{{position:'top',labels:{{font:{{size:10}}}}}}}},
scales:{{
y:{{type:'linear',position:'left',grid:{{display:false}},ticks:{{font:{{size:9}}}}}},
y1:{{type:'linear',position:'right',min:0,max:100,grid:{{display:false}},ticks:{{font:{{size:9}}}}}}
}}
}}
}});
</script>
</body></html>'''

with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print(f"v5.1 DONE: PE={pe:.2f}({tn}) VIX={vix:.1f} DD={dd_pct}% phase={phase} daily=¥{daily_amount} score={sc}")
