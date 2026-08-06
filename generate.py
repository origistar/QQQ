#!/usr/bin/env python3
"""Generate index.html with live market data for v3.2 DCA strategy."""

import urllib.request, json, sys
from datetime import datetime, timezone

# ========== 数据获取 ==========

# 1. 蛋卷基金 PE
pe, pe_pct, roe = 31.66, 53.4, 29.98
try:
    req = urllib.request.Request("https://danjuanfunds.com/djapi/index_eva/dj")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=15) as resp:
        items = json.loads(resp.read())["data"]["items"]
    for item in items:
        if item.get("index_code") == "NDX":
            pe = round(item["pe"], 2)
            pe_pct = round(item["pe_percentile"] * 100, 1)
            roe = round(item["roe"] * 100, 1)
except Exception as e:
    print(f"[WARN] PE fetch failed: {e}", file=sys.stderr)

# 2. yfinance (VIX / NDX / QQQ)
vix, ndx, ndx52, qqq = 16.50, 29733, 30762, 723.85
try:
    import yfinance as yf
    vi = yf.Ticker("^VIX").info
    vix = round(vi.get("regularMarketPrice", 16.50), 2)
    ni = yf.Ticker("^NDX").info
    ndx = int(ni.get("regularMarketPrice", 29733))
    ndx52 = int(ni.get("fiftyTwoWeekHigh", 30762))
    qi = yf.Ticker("QQQ").info
    qqq = round(qi.get("regularMarketPrice", 723.85), 2)
except Exception as e:
    print(f"[WARN] yfinance fetch failed: {e}", file=sys.stderr)

# ========== 策略计算 ==========
dd_ratio = (ndx - ndx52) / ndx52
dd_pct = round(dd_ratio * 100, 2)
dd_abs = abs(dd_ratio)

# PE 分档
if pe < 25:
    tier, tier_name = "low", "低估"
elif pe <= 30:
    tier, tier_name = "mid", "合理"
else:
    tier, tier_name = "high", "偏贵"

# VIX 分档
if vix < 13:
    col, col_name = "greed", "贪婪"
elif vix <= 18:
    col, col_name = "calm", "平稳"
elif vix <= 30:
    col, col_name = "fear", "恐慌"
else:
    col, col_name = "extreme", "极恐"

# 基准矩阵
bm = {
    ("low", "greed"): 1.0, ("low", "calm"): 2.0, ("low", "fear"): 3.0, ("low", "extreme"): 4.0,
    ("mid", "greed"): 0.5, ("mid", "calm"): 1.5, ("mid", "fear"): 2.0, ("mid", "extreme"): 3.0,
    ("high", "greed"): 0.0, ("high", "calm"): 1.0, ("high", "fear"): 1.5, ("high", "extreme"): 2.0,
}
base = bm[(tier, col)]

# 回撤乘数
if dd_abs < 0.06:
    mult = 1.0
elif dd_abs < 0.10:
    mult = 1.5
elif dd_abs < 0.15:
    mult = 2.0
elif dd_abs < 0.20:
    mult = 3.0
elif dd_abs < 0.25:
    mult = 5.0
elif dd_abs < 0.30:
    mult = 8.0
else:
    mult = 10.0

units = base * mult
if pe > 35:
    units = 0
amount = int(units * 300)
sell = pe > 35
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ========== 辅助函数 ==========
def h(t, c):
    """Highlight current cell in matrix"""
    return ' class="hi"' if t == tier and c == col else ""

def z(v):
    """Zero cell style"""
    return ' class="z"' if v == 0 else ""

def h_mult(m):
    """Highlight current drawdown multiplier"""
    return ' style="background:#fef3c7"' if m == mult else ""

# ========== HTML 生成 ==========
sell_block = ""
if sell:
    sell_block = f'''<div class="ca sell"><strong style="color:#dc2626">\u26a0 止盈信号触发</strong>
<p style="font-size:12px;margin-top:4px">PE={pe:.2f}>35, VIX={vix:.1f} | 买入暂停，启动周度定抛止损程序</p></div>'''

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>纳指100 QQQ 定投决策 · v3.2</title>
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
</style>
</head>
<body>
<div class="c">
<div class="h"><h1>纳指100 QQQ 定投决策</h1><div class="d">更新: {ts} &nbsp;|&nbsp; 数据: 蛋卷+CBOE+yfinance</div></div>

<div class="r">
<div class="cd"><div class="va">{pe:.2f}</div><div class="lb">PE-TTM</div></div>
<div class="cd"><div class="va">{vix:.2f}</div><div class="lb">VIX 情绪</div></div>
<div class="cd"><div class="va" style="color:{'#dc2626' if dd_pct<0 else '#16a34a'}">{dd_pct:+.2f}%</div><div class="lb">回撤 (52周高)</div></div>
</div>

<div class="r">
<div class="cd"><div class="va">{ndx:,}</div><div class="lb">NDX 纳指100</div></div>
<div class="cd"><div class="va">${qqq:.2f}</div><div class="lb">QQQ 价格</div></div>
<div class="cd"><div class="va">{roe:.1f}%</div><div class="lb">ROE</div></div>
</div>

<div class="dc">
<div class="sb">今日定投</div>
<div class="bg">{'暂停' if units == 0 else f'¥{amount:,} / 日'}</div>
<div class="sb">PE={pe:.1f}({tier_name}) · VIX={vix:.1f}({col_name}) · 回撤{dd_pct:.1f}% → 基准{base}份 × 回撤乘数{mult}x = {units:.1f}份</div>
</div>

{sell_block}

<div class="ca"><h3>买入基准矩阵（PE × VIX）</h3>
<div style="overflow-x:auto"><table class="tb">
<tr><th>PE 分档</th><th>贪婪 &lt;13</th><th>平稳 13-18</th><th>恐慌 18-30</th><th>极恐 &gt;30</th></tr>
<tr><td class="lb">PE &lt; 25（低估）</td><td{h("low","greed")}>1.0</td><td{h("low","calm")}>2.0</td><td{h("low","fear")}>3.0</td><td{h("low","extreme")}>4.0</td></tr>
<tr><td class="lb">PE 25-30（合理）</td><td{h("mid","greed")}>0.5</td><td{h("mid","calm")}>1.5</td><td{h("mid","fear")}>2.0</td><td{h("mid","extreme")}>3.0</td></tr>
<tr><td class="lb">PE &gt; 30（偏贵/高估）</td><td{z(bm[("high","greed")])}{h("high","greed")}>0.0</td><td{h("high","calm")}>1.0</td><td{h("high","fear")}>1.5</td><td{h("high","extreme")}>2.0</td></tr>
</table></div>
<p style="font-size:10px;color:#6b7280;margin-top:4px">黄色=当前。PE>35 止盈窗口打开，份数强制为0</p></div>

<div class="ca"><h3>回撤折扣乘数</h3>
<table class="ft">
<tr><th>回撤</th><th>&lt;6%</th><th>6-10%</th><th>10-15%</th><th>15-20%</th><th>20-25%</th><th>25-30%</th><th>&gt;30%</th></tr>
<tr><td style="font-weight:600">乘数</td>
<td{h_mult(1.0)}>×1.0</td>
<td{h_mult(1.5)}>×1.5</td>
<td{h_mult(2.0)}>×2.0</td>
<td{h_mult(3.0)}>×3.0</td>
<td{h_mult(5.0)}>×5.0</td>
<td{h_mult(8.0)}>×8.0</td>
<td{h_mult(10.0)}>×10.0</td></tr>
</table></div>

<div class="ca"><h3>止盈规则</h3>
<p style="font-size:12px">PE>35 且 VIX<18 → 周度定抛 10 周卖出 30%<br>PE>38 或 PE>35 且 VIX<13 → 加速 4-5 周卖完<br>PE回落至<35 立即停止止盈</p></div>

<div class="ca"><h3>资金池</h3>
<p style="font-size:12px">¥100万 正常定投(日上限¥6,000) + ¥50万 备用金(分10份,每份¥5万,回撤>20%启用)</p></div>

<div class="fo">v3.2 金字塔定投 · 数据: 蛋卷基金/CBOE/yfinance · 每日自动更新 · 仅供参考不构成投资建议</div>
</div>
</body>
</html>'''

with open("D:/workbuddy/纳指/qqq-site/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"DONE: PE={pe:.2f} VIX={vix:.2f} NDX={ndx} DD={dd_pct}% tier={tier}({tier_name}) col={col}({col_name})")
print(f"  base={base} mult={mult}x units={units:.1f} amount=¥{amount}")
