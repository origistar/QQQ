#!/usr/bin/env python3
"""v4.2 generate.py - 性价比评分 + 溢价切换 + ROE监控 + PE滞回"""
import urllib.request, json, sys, os
from datetime import datetime, timezone, date, timedelta

STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "state.json")
HYST_FILE = os.path.join(os.path.dirname(__file__) or ".", "pe_hyst.json")

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"sell_active": False, "sell_tier": None, "sell_started": None, "sell_week": 0, "has_sold": False}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(s, f, ensure_ascii=False, indent=2)

# PE滞回: 新PE需连续5天在同一档才切换
def load_hyst():
    try:
        with open(HYST_FILE,"r",encoding="utf-8") as f: return json.load(f)
    except: return {"tier":"mid_low","days_in_tier":1}

def update_hyst(new_tier):
    h=load_hyst()
    if new_tier==h["tier"]: h["days_in_tier"]+=1
    else: h={"tier":new_tier,"days_in_tier":1}
    with open(HYST_FILE,"w",encoding="utf-8") as f: json.dump(h,f,ensure_ascii=False)
    return h["tier"] if h["days_in_tier"]>=5 else h["tier"] if h["tier"]==load_state().get("last_effective_tier","mid_low") else load_state().get("last_effective_tier","mid_low")

state = load_state()

# Data
pe, pe_pct, roe = 31.66, 53.4, 29.98
try:
    req = urllib.request.Request("https://danjuanfunds.com/djapi/index_eva/dj")
    req.add_header("User-Agent","Mozilla/5.0")
    with urllib.request.urlopen(req,timeout=15) as resp:
        for item in json.loads(resp.read())["data"]["items"]:
            if item.get("index_code")=="NDX": pe=round(item["pe"],2); pe_pct=round(item["pe_percentile"]*100,1); roe=round(item["roe"]*100,1)
except Exception as e: print(f"[WARN] PE: {e}",file=sys.stderr)

vix, ndx, ndx52, qqq = 16.50, 29733, 30762, 723.85
try:
    import yfinance as yf
    vix=round(yf.Ticker("^VIX").info.get("regularMarketPrice",16.50),2)
    ni=yf.Ticker("^NDX").info; ndx=int(ni.get("regularMarketPrice",29733)); ndx52=int(ni.get("fiftyTwoWeekHigh",30762))
    qqq=round(yf.Ticker("QQQ").info.get("regularMarketPrice",723.85),2)
except Exception as e: print(f"[WARN] yfinance: {e}",file=sys.stderr)

dd_pct=round((ndx-ndx52)/ndx52*100,2); dd_abs=abs((ndx-ndx52)/ndx52)

# ---- 溢价率 (从集思录爬取, 暂时用缓存) ----
premium = None
try:
    req = urllib.request.Request("https://www.jisilu.cn/data/qdii/detail/513100")
    req.add_header("User-Agent","Mozilla/5.0")
    with urllib.request.urlopen(req,timeout=10) as resp:
        body = resp.read().decode()
        # 简单正则提取最新溢价率
        import re
        m = re.search(r'(\d+\.\d+)%', body)
        if m: premium = float(m.group(1))
except: pass
# 如果爬不到, 用默认值
if premium is None: premium = 13.0

prem_switch = premium < 5  # 溢价<5%切场内
prem_sell = premium > 8    # 溢价>8%卖回场外

# ---- 性价比评分 (五因子加权) ----
# PE分位越高越贵→分数越低
pe_score = max(0, 100 - pe_pct) * 0.35
# 回撤越深→分数越高
dd_score = min(100, dd_abs * 400) * 0.25
# VIX越高(恐慌)→分数越高
vix_score = min(100, max(0, (vix - 10) * 5)) * 0.20
# ROE越高→分数越高
roe_score = min(100, (roe - 10) * 5) * 0.10
# 均线偏离 (用60日线近似, 偏离越大越贵)
ma_dev = abs((ndx - ndx52) / ndx52) # 简化为52周高偏离
ma_score = max(0, 100 - ma_dev * 500) * 0.10
sc = round(pe_score + dd_score + vix_score + roe_score + ma_score)
sc_label = "极高" if sc >= 71 else "中等" if sc >= 41 else "偏低"

# PE分档 (带滞回)
raw_tier="low" if pe<28 else "mid_low" if pe<=33 else "mid" if pe<=36 else "high" if pe<=38 else "sell"
tier = update_hyst(raw_tier)
# save effective tier for state
state["last_effective_tier"]=tier; save_state(state)

tn={"low":"低估","mid_low":"合理偏低","mid":"合理","high":"偏高","sell":"高估/止盈"}[tier]

if vix<13: col,cn="greed","贪婪"
elif vix<=18: col,cn="calm","平稳"
elif vix<=30: col,cn="fear","恐慌"
else: col,cn="extreme","极恐"

bm={("low","greed"):1,("low","calm"):2,("low","fear"):3,("low","extreme"):4,
    ("mid_low","greed"):0.5,("mid_low","calm"):1.5,("mid_low","fear"):2,("mid_low","extreme"):3,
    ("mid","greed"):0.5,("mid","calm"):1,("mid","fear"):1.5,("mid","extreme"):2,
    ("high","greed"):0,("high","calm"):0.5,("high","fear"):1,("high","extreme"):1.5,
    ("sell","greed"):0,("sell","calm"):0,("sell","fear"):0,("sell","extreme"):0}

base=bm.get((tier,col),0)
if dd_abs<0.06: mult=1.0
elif dd_abs<0.10: mult=1.5
elif dd_abs<0.15: mult=2.0
elif dd_abs<0.20: mult=3.0
elif dd_abs<0.25: mult=3.0
elif dd_abs<0.30: mult=4.0
else: mult=5.0

units=0.0 if tier=="sell" else base*mult; amount=int(units*1000)

# Sell/buyback state machine (unchanged)
today_str=date.today().isoformat()
t1=pe>38 and vix<18; t2=pe>40 or (pe>38 and vix<13)
if t2:
    if not state["sell_active"] or state["sell_tier"]!=2: state={"sell_active":True,"sell_tier":2,"sell_started":today_str,"sell_week":1,"has_sold":True,"last_effective_tier":tier}
    else: w=(date.today()-date.fromisoformat(state["sell_started"])).days//7+1; state["sell_week"]=min(w,5)
elif t1:
    if not state["sell_active"]: state={"sell_active":True,"sell_tier":1,"sell_started":today_str,"sell_week":1,"has_sold":True,"last_effective_tier":tier}
    elif state.get("sell_tier")!=2: w=(date.today()-date.fromisoformat(state["sell_started"])).days//7+1; state["sell_week"]=min(w,10)
elif pe<38 and state["sell_active"]: state["sell_active"]=False; state["sell_tier"]=None; state["sell_week"]=0

buyback=False; bb_reason=""
if state.get("has_sold") and not state["sell_active"]:
    if pe<28: buyback=True; bb_reason=f"PE={pe:.1f}<28"
    elif dd_abs>0.15: buyback=True; bb_reason=f"DD>{15}%"
    elif pe<32: buyback=True; bb_reason=f"PE={pe:.1f}<32"
if buyback: state["has_sold"]=False; state["last_effective_tier"]=tier
save_state(state)

# ROE alert
roe_warn=roe<18
profit_warn=pe*roe/100>50  # PEG-style: PE*ROE rough check

ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# HTML helpers
def h(t,c): return ' class="hi"' if t==tier and c==col else ""
def z(v): return ' class="z"' if v==0 else ""
def hm(m): return ' style="background:#fef3c7"' if m==mult else ""

sel=state["sell_active"]; st=state.get("sell_tier"); sw=state.get("sell_week",0)
sell_html=""
if sel:
    mw=5 if st==2 else 10; wp=round(30/mw,1); sp="加速" if st==2 else ""
    sell_html=f'<div class="ca sell"><strong style="color:#dc2626">\u26a0 止盈进行中（第{sw}/{mw}周）</strong><p style="font-size:12px;margin-top:4px">PE={pe:.1f}>38 | {sp} | 每周卖<b>{wp}%</b> | 累计建议卖出约<b>{sw*wp}%</b></p><p style="font-size:11px;color:#6b7280;margin-top:2px">PE回落<38自动停止 | 手工在富途执行</p></div>'

bb_html=""
if buyback: bb_html=f'<div class="ca" style="border-color:#16a34a;background:#f0fdf4"><strong style="color:#16a34a">\u2705 买回信号</strong><p style="font-size:12px;margin-top:4px">{bb_reason} | 建议将止盈卖出的资金买回QQQ</p></div>'

roe_html=""
if roe_warn: roe_html=f'<div class="ca sell"><strong style="color:#dc2626">\u26a0 ROE警告</strong><p style="font-size:12px;margin-top:4px">ROE={roe:.1f}%<18% 警戒线 | 连续2季触发则卖出30%</p></div>'

profit_html=""
# floating profit >50% discretionary warning
profit_html=f'<div class="ca" style="border-color:#d97706;background:#fff7ed;font-size:11px"><strong style="color:#d97706">\U0001f7e0 浮盈提醒</strong>：定期检查持仓浮盈，若<strong>>50%</strong>，可考虑手动减仓10-20%，分2-3次执行（每次间隔≥1周）。</div>'

h_note=""
hyst=load_hyst()
if hyst["days_in_tier"]<5: hyst_note=f'<span style="font-size:10px;color:#d97706">[滞回: {hyst["days_in_tier"]}/5天]</span>'

html=f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>纳指100 QQQ 定投决策 v4.1</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a1a2e;line-height:1.6}}
.c{{max-width:720px;margin:0 auto;padding:20px 16px 40px}}
.h{{text-align:center;padding:20px 0 8px}}.h h1{{font-size:22px;font-weight:700}}
.h .d{{font-size:13px;color:#6b7280;margin-top:4px}}
.r{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}}
.cd{{background:#fff;border-radius:12px;padding:14px 10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.va{{font-size:22px;font-weight:700;line-height:1.2}}.lb{{font-size:11px;color:#6b7280;margin-top:2px}}
.dc{{background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;border-radius:14px;padding:20px;text-align:center;margin:16px 0}}
.dc .bg{{font-size:34px;font-weight:800;line-height:1}}.dc .sb{{font-size:14px;opacity:.9;margin-top:6px}}
.ca{{background:#fff;border-radius:12px;padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.04);border:1px solid #e5e7eb}}
.ca h3{{font-size:13px;margin-bottom:8px}}
.tb{{width:100%;border-collapse:collapse;font-size:12px}}
.tb th{{background:#1e293b;color:#fff;padding:5px 4px;text-align:center;font-weight:600;font-size:10px}}
.tb td{{text-align:center;padding:5px 4px;border:1px solid #e5e7eb;font-weight:600;font-size:12px}}
.tb td.lb{{background:#f1f5f9;text-align:left;padding-left:6px;font-size:10px}}
.tb td.hi{{background:#fef3c7}}.tb td.z{{color:#cbd5e1}}
.ft{{width:100%;border-collapse:collapse;font-size:12px}}
.ft th{{background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;font-size:11px;border-bottom:2px solid #e5e7eb}}
.ft td{{padding:5px 8px;border-bottom:1px solid #e5e7eb;font-size:12px}}
.fo{{font-size:10px;color:#6b7280;text-align:center;border-top:1px solid #e5e7eb;padding-top:12px;margin-top:16px}}
.sell{{border-color:#dc2626!important;background:#fef2f2!important}}
</style></head><body><div class="c">
<div class="h"><h1>纳指100 定投决策 v4.2</h1><div class="d">更新: {ts} | 性价比{sc}分({sc_label}) | PE滞回5天</div></div>

<div class="r">
<div class="cd"><div class="va">{pe:.2f}</div><div class="lb">PE-TTM {hyst_note}</div></div>
<div class="cd"><div class="va">{vix:.2f}</div><div class="lb">VIX 情绪</div></div>
<div class="cd"><div class="va" style="color:{'#dc2626' if dd_pct<0 else '#16a34a'}">{dd_pct:+.2f}%</div><div class="lb">回撤 (52周高)</div></div>
</div>

<div class="r">
<div class="cd"><div class="va">{ndx:,}</div><div class="lb">NDX 纳指100</div></div>
<div class="cd"><div class="va">${qqq:.2f}</div><div class="lb">QQQ 价格</div></div>
<div class="cd"><div class="va">{roe:.1f}%</div><div class="lb">ROE {'⚠' if roe_warn else ''}</div></div>
</div>

<div class="dc">
<div class="sb">今日定投</div>
<div class="bg">{'止盈暂停' if sel else '暂停' if units==0 else f'¥{amount:,} / 日'}</div>
<div class="sb">PE={pe:.1f}({tn}) · VIX={vix:.1f}({cn}) · 回撤{dd_pct:.1f}% · 基准{base}份x乘数{mult}x={units:.1f}份</div>
</div>

{sell_html}{bb_html}{roe_html}{profit_html}

<div class="ca"><h3>\U0001f4ca 定投性价比评分 {sc} 分（{sc_label}）</h3>
<p style="font-size:11px;color:#6b7280">
PE分位({pe_pct:.0f}%) · 回撤({dd_pct:+.1f}%) · VIX({vix:.1f}) · ROE({roe:.0f}%) · 均线偏离<br>
71-100 性价比极高 · 41-70 中等 · 10-40 偏低
</p></div>

<div class="ca"><h3>\U0001f4b1 溢价率场内外切换 <span style="font-size:10px;background:#fef3c7;padding:1px 4px;border-radius:3px">NEW</span></h3>
<p style="font-size:12px">当前溢价率 <b>{premium:.1f}%</b> {'→ <span style=\"color:#16a34a\">切换场内ETF定投</span>' if prem_switch else '→ 正常场外基金定投' if not prem_sell else '→ <span style=\"color:#dc2626\">溢价偏高，可卖出场内持仓</span>'}</p>
<p style="font-size:10px;color:#6b7280;margin-top:2px">规则：溢价<5%切场内买入 · 溢价>8%卖回场外 · 其余时间场外基金定投</p></div>

<div class="ca"><h3>买入基准矩阵（PE x VIX）</h3>
<div style="overflow-x:auto"><table class="tb">
<tr><th>PE 分档</th><th>贪婪 &lt;13</th><th>平稳 13-18</th><th>恐慌 18-30</th><th>极恐 &gt;30</th></tr>
<tr><td class="lb">PE &lt; 28（低估）</td><td{h("low","greed")}>1.0</td><td{h("low","calm")}>2.0</td><td{h("low","fear")}>3.0</td><td{h("low","extreme")}>4.0</td></tr>
<tr><td class="lb">PE 28-33（合理偏低）</td><td{h("mid_low","greed")}>0.5</td><td{h("mid_low","calm")}>1.5</td><td{h("mid_low","fear")}>2.0</td><td{h("mid_low","extreme")}>3.0</td></tr>
<tr><td class="lb">PE 33-36（合理）</td><td{h("mid","greed")}>0.5</td><td{h("mid","calm")}>1.0</td><td{h("mid","fear")}>1.5</td><td{h("mid","extreme")}>2.0</td></tr>
<tr><td class="lb">PE 36-38（偏高）</td><td{z(bm[("high","greed")])}{h("high","greed")}>0.0</td><td{h("high","calm")}>0.5</td><td{h("high","fear")}>1.0</td><td{h("high","extreme")}>1.5</td></tr>
<tr><td class="lb">PE > 38（高估/止盈）</td><td>0.0</td><td>0.0</td><td>0.0</td><td>0.0</td></tr>
</table></div></div>

<div class="ca"><h3>回撤折扣乘数</h3>
<table class="ft">
<tr><th>回撤</th><th>&lt;6%</th><th>6-10%</th><th>10-15%</th><th>15-20%</th><th>20-25%</th><th>25-30%</th><th>&gt;30%</th></tr>
<tr><td style="font-weight:600">乘数</td>
<td{hm(1.0)}>x1.0</td><td{hm(1.5)}>x1.5</td><td{hm(2.0)}>x2.0</td><td{hm(3.0)}>x3.0</td><td{hm(3.0)}>x3.0</td><td{hm(4.0)}>x4.0</td><td{hm(5.0)}>x5.0</td></tr>
</table></div>

<div class="ca"><h3>止盈与买回规则</h3>
<p style="font-size:12px"><b>卖出：</b>PE>38且VIX<18 → 一档，每周卖3%，10周卖完30%<br>PE>40或PE>38且VIX<13 → 二档，每周卖6-8%，4-5周卖完</p>
<p style="font-size:12px;margin-top:4px"><b>买回:</b>PE<32或PE<28或DD>15% → 买回QQQ</p>
<p style="font-size:12px;margin-top:4px"><b>浮盈减仓:</b>持仓浮盈>50%时可手动减10-20%仓位，分2-3次，间隔≥1周</p>
<p style="font-size:10px;color:#6b7280;margin-top:2px">PE回落至<38 立即停止止盈</p></div>

<div class="fo">v4.2 金字塔定投 · 性价比评分 · 溢价切换 · PE滞回 · 每日更新 · 仅供参考不构成投资建议</div>
</div></body></html>'''

with open(os.path.join(os.path.dirname(__file__) or ".","index.html"),"w",encoding="utf-8") as f: f.write(html)

print(f"DONE: PE={pe:.2f} tier={tier}({tn}) VIX={vix:.1f} DD={dd_pct}% units={units:.1f}=¥{amount} score={sc} prem={premium:.1f}%")
