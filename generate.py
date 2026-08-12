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

# ===== PREMIUM: 513100市价/净值（天天基金+yfinance） =====
premium = None; prem_fresh = False
try:
    req_p = urllib.request.Request("https://api.fund.eastmoney.com/f10/lsjz?fundCode=513100&pageIndex=1&pageSize=1")
    req_p.add_header("Referer","https://fundf10.eastmoney.com/")
    with urllib.request.urlopen(req_p,timeout=10) as resp:
        nav_d = json.loads(resp.read())
        nav_val = float(nav_d["Data"]["LSJZList"][0]["DWJZ"])
    etf_p = yf.Ticker("513100.SS").info.get("regularMarketPrice")
    if not etf_p: etf_p = yf.Ticker("513100.SS").info.get("previousClose")
    if nav_val and etf_p:
        premium = round((etf_p / nav_val - 1) * 100, 1)
        prem_fresh = True
except Exception as e:
    print(f"[WARN] Premium: {e}",file=sys.stderr)
if premium is None: premium = "?"

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
    "score": sc, "daily": daily_amount, "premium": premium if isinstance(premium, (int,float)) else None,
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
bj_tz = timezone(timedelta(hours=8))
ts = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M")

def h(t,c): return ' class="hi"' if t==tier and c==col else ""
def z(v): return ' class="z"' if v==0 else ""
def hm(m): return ' style="background:#fef3c7"' if abs(m-dd_mult)<0.01 else ""

prem_switch = isinstance(premium, (int,float)) and premium < 5
prem_sell = isinstance(premium, (int,float)) and premium > 8
prem_display = f"{premium:.1f}%" if isinstance(premium, (int,float)) else "N/A"

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
if not isinstance(premium, (int,float)):
    prem_html = f'<div class="ca"><h3>💱 溢价切换</h3><p style="font-size:12px;color:#6b7280">溢价率数据暂不可用，请手动查看雪球</p></div>'
elif prem_switch:
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
.nav{{position:fixed;bottom:0;left:0;right:0;background:rgba(255,255,255,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-top:0.5px solid rgba(0,0,0,0.08);display:flex;justify-content:space-around;padding:0;z-index:100;max-width:660px;margin:0 auto}}
.nav a{{text-decoration:none;color:#8e8e93;font-size:10px;font-weight:500;text-align:center;display:flex;flex-direction:column;align-items:center;gap:1px;padding:5px 0 8px;flex:1;transition:color .2s}}
.nav a.active{{color:#007aff;font-weight:600}}
.nav a .ic{{font-size:20px;line-height:1;margin-bottom:1px}}</style></head><body><div class="c">
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
<div class="cd"><div class="va">{prem_display}</div><div class="lb">溢价率 513100</div></div>
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

<nav class="nav">
<a href="index.html" class="active"><span class="ic">▤</span>纳指</a>
<a href="btc.html"><span class="ic">◇</span>比特币</a>
<a href="history.html"><span class="ic">☰</span>历史</a>
</nav>
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

# ==========================================
# BTC AHR999 定投页面
# ==========================================
btc_err = False
try:
    btc_t = yf.Ticker("BTC-USD")
    btc_info = btc_t.info
    btc_price = int(btc_info.get("regularMarketPrice", 63500))
    btc_52h = int(btc_info.get("fiftyTwoWeekHigh", 126000))
    btc_dd = round((btc_price - btc_52h) / btc_52h * 100, 1)

    ibit_t = yf.Ticker("IBIT")
    ibit_price = round(ibit_t.info.get("regularMarketPrice", 36.8), 2)

    # MSTR
    mstr_t = yf.Ticker("MSTR")
    mstr_info = mstr_t.info
    mstr_price = round(mstr_info.get("regularMarketPrice", 96), 2)
    mstr_52h = int(mstr_info.get("fiftyTwoWeekHigh", 399))
    mstr_dd = round((mstr_price - mstr_52h) / mstr_52h * 100, 1)
    mstr_mcap = mstr_info.get("marketCap", 37e9)
    btc_held = 578000
    mnav = round(mstr_mcap / (btc_held * btc_price), 2) if btc_price else 1.0

    # AHR999: 200MA + index growth
    btc_hist = btc_t.history(period="250d")
    btc_prices = btc_hist["Close"].tolist()
    if len(btc_prices) >= 200:
        btc_ma200 = sum(btc_prices[-200:]) / 200
    else:
        btc_ma200 = btc_price * 0.95
    genesis = date(2009, 1, 3)
    days_b = (date.today() - genesis).days
    growth_val = 10 ** (5.84 * __import__("math").log10(days_b) - 17.01)
    ahr999 = round((btc_price / btc_ma200) * (btc_price / growth_val), 4)
    ahr999_raw = ahr999
except Exception as e:
    btc_err = True
    btc_price = 63500; btc_52h = 126000; btc_dd = -49.6
    ibit_price = 36.8
    mstr_price = 96; mstr_52h = 399; mstr_dd = -75.9; mnav = 1.0
    btc_ma200 = 69000; ahr999 = 0.34

# DCA rules
btc_below_50k = btc_price < 50000
if btc_below_50k:
    btc_weekly = 12000; btc_shares = round(12000 / 7.25 / ibit_price)
    btc_active = "应急加速"
elif ahr999 < 0.45:
    btc_weekly = 6000; btc_shares = round(6000 / 7.25 / ibit_price)
    btc_active = "抄底"
elif ahr999 <= 1.2:
    btc_weekly = 3000; btc_shares = round(3000 / 7.25 / ibit_price)
    btc_active = "定投"
else:
    btc_weekly = 0; btc_shares = 0
    btc_active = "暂停"

btc_ts = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M")
btc_status = "⚠ 数据获取异常" if btc_err else "数据正常"

# Save BTC state
BTC_STATE = os.path.join(BASE_DIR, "btc_state.json")
btc_history = load_json(BTC_STATE, {"history": []}).get("history", [])
btc_history = [h for h in btc_history if h.get("date") != today_str]
btc_history.append({
    "date": today_str,
    "btc": btc_price, "ibtc": ibit_price, "ahr999": ahr999_raw if not btc_err else None,
    "mstr": mstr_price, "mnav": mnav, "weekly": btc_weekly
})
if len(btc_history) > 365: btc_history = btc_history[-365:]
save_json(BTC_STATE, {"history": btc_history})

ahr_tier = "🔴 < 0.45" if ahr999 < 0.45 else "🟢 0.45-1.2" if ahr999 <= 1.2 else "🟡 > 1.2"

btc_html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>比特币 AHR999 定投决策</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a1a2e;line-height:1.6}}
.c{{max-width:660px;margin:0 auto;padding:20px 16px 40px}}
.h{{text-align:center;padding:20px 0 8px}}.h h1{{font-size:20px;font-weight:700}}
.h .d{{font-size:12px;color:#6b7280;margin-top:4px}}
.r{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}}
.cd{{background:#fff;border-radius:12px;padding:12px 8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.va{{font-size:20px;font-weight:700;line-height:1.2}}.lb{{font-size:10px;color:#6b7280;margin-top:2px}}
.dc{{background:linear-gradient(135deg,#d97706,#ea580c);color:#fff;border-radius:14px;padding:18px;text-align:center;margin:14px 0}}
.dc .bg{{font-size:30px;font-weight:800;line-height:1}}.dc .sb{{font-size:13px;opacity:.9;margin-top:4px}}
.ca{{background:#fff;border-radius:12px;padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.ca h3{{font-size:13px;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#1e293b;color:#fff;padding:5px 6px;text-align:center;font-weight:600;font-size:10px}}
td{{padding:5px 6px;border-bottom:1px solid #e5e7eb;text-align:center;font-size:11px}}
td.lb{{background:#f8fafc;text-align:left;font-weight:600;font-size:10px}}
td.deep{{background:#fef2f2;color:#dc2626;font-weight:700}}
td.normal{{background:#f0fdf4;color:#16a34a;font-weight:700}}
td.high{{background:#fff7ed;color:#d97706;font-weight:700}}
.fo{{font-size:10px;color:#6b7280;text-align:center;border-top:1px solid #e5e7eb;padding-top:12px;margin-top:16px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.chart-box{{height:220px}}
</style>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
</head><body><div class="c">
<div class="h"><h1>比特币 AHR999 定投决策</h1>
<div class="d">更新: {btc_ts} · 数据源: yfinance · AHR999 自算</div></div>

<div class="r">
<div class="cd"><div class="va">${btc_price:,}</div><div class="lb">BTC 价格</div></div>
<div class="cd"><div class="va">${ibit_price:.2f}</div><div class="lb">IBIT 每股</div></div>
<div class="cd"><div class="va" style="color:#dc2626">{btc_dd:+.1f}%</div><div class="lb">回撤 52周高 ${btc_52h:,}</div></div>
</div>
<div class="r">
<div class="cd"><div class="va">${btc_ma200:,.0f}</div><div class="lb">200日定投均线</div></div>
<div class="cd"><div class="va" style="color:#dc2626">${mstr_price:.2f} ({mstr_dd:+.1f}%)</div><div class="lb">MSTR · 52周高 ${mstr_52h}</div></div>
<div class="cd"><div class="va" style="color:{'#16a34a' if mnav>=1 else '#dc2626'}">{mnav:.2f}x {'溢价' if mnav>=1 else '折价'}</div><div class="lb">MSTR mNAV · 持有578K BTC</div></div>
</div>

<div class="dc">
<div class="sb">今日定投 · {ahr_tier}</div>
<div class="bg">¥{btc_weekly:,} / 周</div>
<div class="sb">AHR999={ahr999:.4f} · 价格/200MA={btc_price/btc_ma200:.2f} {'· BTC<$50K 应急加速' if btc_below_50k else ''}</div>
</div>

<div class="ca"><h3>定投规则</h3>
<table>
<tr><th>条件</th><th>区间</th><th>周投金额</th><th>IBIT 股数</th><th>状态</th></tr>
<tr><td style="color:#dc2626"><b>BTC < $50,000</b></td><td style="color:#dc2626">应急加速</td><td style="color:#dc2626"><b>¥12,000</b></td><td>~{round(12000/7.25/ibit_price)} 股</td><td>{'← 现在' if btc_below_50k else '未触发'}</td></tr>
<tr><td class="deep"><b>{ahr999:.4f}</b></td><td class="deep">< 0.45 抄底</td><td class="deep">¥6,000</td><td>~{round(6000/7.25/ibit_price)} 股</td><td>{'← 现在' if not btc_below_50k and ahr999<0.45 else ''}</td></tr>
<tr><td class="normal">0.45 ~ 1.2</td><td class="normal">定投区间</td><td class="normal">¥3,000</td><td>~{round(3000/7.25/ibit_price)} 股</td><td>{'← 现在' if 0.45<=ahr999<=1.2 else ''}</td></tr>
<tr><td class="high">> 1.2</td><td class="high">高估暂停</td><td class="high">¥0</td><td>0</td><td>{'← 现在' if ahr999>1.2 else ''}</td></tr>
</table>
</div>

<div class="ca"><h3>四年减半周期 · 底部预判</h3>
<div class="chart-box" id="cycle-chart"></div>
<table>
<tr><th>周期</th><th>减半</th><th>牛市顶</th><th>顶→底</th><th>熊市底</th><th>回撤</th><th>减半→底</th></tr>
<tr style="background:#fef2f2"><td><b>2024（本轮）</b></td><td><b>24.04</b></td><td><b>$126,000</b><br>25.10</td><td>已过 10 月<br>剩 ~2 月</td><td><b>$45-65K</b><br>预测 26.09-10</td><td>~-50%</td><td><b>28/30 月</b><br>剩 1-2 月</td></tr>
<tr><td>2020</td><td>20.05</td><td>$69,000 · 21.11</td><td>12 个月</td><td>$15,500 · 22.11</td><td class="deep">-77%</td><td>30 个月</td></tr>
<tr><td>2016</td><td>16.07</td><td>$19,700 · 17.12</td><td>12 个月</td><td>$3,150 · 18.12</td><td class="deep">-84%</td><td>29 个月</td></tr>
<tr><td>2012</td><td>12.11</td><td>$1,150 · 13.12</td><td>13 个月</td><td>$150 · 15.01</td><td class="deep">-87%</td><td>25 个月</td></tr>
</table>
<p style="font-size:10px;color:#6b7280;margin-top:6px">
两条独立线索同时指向 2026 年 9-10 月：<br>
① <b>顶→底</b>：历次牛市见顶后 12-13 个月触底，本轮顶在 25.10，+12 个月 = <b>26.10</b><br>
② <b>减半→底</b>：历次减半后 25-30 个月触底，当前第 28 个月，历史最长 30 个月 = <b>26.10</b>
</p></div>

<div class="grid2">
<div class="ca"><h3>本周操作</h3>
<p style="font-size:20px;font-weight:800;color:#dc2626">¥{btc_weekly:,} / 周</p>
<p style="font-size:12px">IBIT ${ibit_price:.2f} × {btc_shares} 股</p>
<p style="font-size:11px;color:#6b7280;margin-top:4px">{"BTC < $50K 应急加速" if btc_below_50k else "AHR999 " + str(ahr999) + " < 0.45" if ahr999 < 0.45 else "正常定投"}</p>
</div>
<div class="ca"><h3>退出条件</h3>
<p style="font-size:12px"><b>AHR999 > 2.0</b>：分4周清仓</p>
<p style="font-size:12px;margin-top:4px">止盈资金暂存，等 AHR999 < 1.2 时重新启动</p>
<p style="font-size:11px;color:#6b7280;margin-top:4px">投完即止</p>
</div>
</div>

<div class="fo">AHR999 自算 · yfinance 数据 · ¥200,000 · 仅供参考不构成投资建议</div>

<nav class="nav">
<a href="index.html"><span class="ic">▤</span>纳指</a>
<a href="btc.html" class="active"><span class="ic">◇</span>比特币</a>
<a href="history.html"><span class="ic">☰</span>历史</a>
</nav>
</div>

<script>
var c=echarts.init(document.getElementById('cycle-chart'));
c.setOption({{
title:{{text:'BTC 减半周期 · 价格走势（对数）',left:'center',textStyle:{{fontSize:11}}}},
tooltip:{{trigger:'axis',formatter:function(p){{return p[0].name+'<br>BTC: $'+p[0].data.toLocaleString()}}}},
grid:{{left:50,right:20,top:35,bottom:30}},
xAxis:{{type:'category',data:['2011','2012','2013','2014','2015','2016','2017','2018','2019','2020','2021','2022','2023','2024','2025','2026(预测)'],axisLabel:{{fontSize:9,interval:1}}}},
yAxis:{{type:'log',min:100,axisLabel:{{fontSize:9,formatter:'${{value}}'}},splitLine:{{lineStyle:{{color:'#e5e7eb'}}}}}},
series:[{{
type:'line',data:[5,13,1150,200,450,750,19700,3150,11000,29000,69000,15500,44000,70000,126000,{btc_price}],
smooth:true,lineStyle:{{color:'#d97706',width:2}},itemStyle:{{color:'#d97706'}},
markLine:{{silent:true,symbol:'none',label:{{fontSize:9,position:'start'}},
data:[
{{name:'减半🔽',xAxis:'2012',lineStyle:{{color:'#dc2626',type:'dashed'}}}},
{{name:'减半🔽',xAxis:'2016',lineStyle:{{color:'#dc2626',type:'dashed'}}}},
{{name:'减半🔽',xAxis:'2020',lineStyle:{{color:'#dc2626',type:'dashed'}}}},
{{name:'减半🔽(24.04)',xAxis:'2024',lineStyle:{{color:'#dc2626',type:'dashed'}}}}
]}}, markArea:{{silent:true,label:{{fontSize:9}},data:[[
{{xAxis:'2026(预测)',itemStyle:{{color:'rgba(220,38,38,0.08)'}}}},{{itemStyle:{{color:'rgba(220,38,38,0.01)'}}}}
]]}}
}},{{
type:'line',data:[null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,52000],
lineStyle:{{color:'#dc2626',type:'dotted',width:1}},itemStyle:{{color:'#dc2626'}},showSymbol:false
}}]
}});
</script>
</body></html>'''

with open(os.path.join(BASE_DIR, "btc.html"), "w", encoding="utf-8") as f:
    f.write(btc_html)

print(f"v5.1 DONE: PE={pe:.2f}({tn}) VIX={vix:.1f} DD={dd_pct}% phase={phase} daily=¥{daily_amount} score={sc} | BTC=${btc_price} AHR={ahr999:.4f} wk=¥{btc_weekly}")
