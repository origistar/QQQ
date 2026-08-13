#!/usr/bin/env python3
"""v5.1 push.py - 每日早间微信推送（Server酱）"""
import json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

SENDKEY = "SCT396112T9n16DUSsF8qCu65elrkq3UIu"
BASE = "https://origistar.github.io/QQQ"

bj = timezone(timedelta(hours=8))
now = datetime.now(bj)
wd = ["一", "二", "三", "四", "五", "六", "日"]
date_str = f"{now.month}月{now.day}日 周{wd[now.weekday()]}"

# ---- 纳指 ----
try:
    with open("state.json", encoding="utf-8") as f:
        nd = json.load(f)
    h = nd.get("history", [])
    last = h[-1] if h else {}
    pe = last.get("pe", "?"); vix = last.get("vix", "?")
    score = last.get("score", "?"); daily = last.get("daily", 0)
    prem = last.get("premium", "?")
    pe_f = float(pe) if isinstance(pe, (int, float)) else 99
    tn = "低估" if pe_f < 28 else "合理偏低" if pe_f <= 33 else "合理" if pe_f <= 36 else "偏高" if pe_f <= 38 else "高估/止盈"
    prem_s = f"{prem:.1f}%" if isinstance(prem, (int, float)) else "?"
    prem_icon = "⚠️" if isinstance(prem, (int, float)) and prem > 8 else ""
    ndx_txt = f"PE {pe} · {tn}\nVIX {vix} · 性价比 {score} 分\n今日定投 ¥{daily:,}/日\n溢价率 {prem_s}{prem_icon}"
except Exception as e:
    ndx_txt = f"纳指数据异常: {e}"

# ---- BTC ----
try:
    with open("btc_state.json", encoding="utf-8") as f:
        bd = json.load(f)
    bh = bd.get("history", [])
    bl = bh[-1] if bh else {}
    btc = bl.get("btc", "?"); ahr = bl.get("ahr999", "?"); wk = bl.get("weekly", 0)
    ibit = bl.get("ibtc", "?")
    ahr_f = float(ahr) if isinstance(ahr, (int, float)) else None
    if ahr_f is None:
        ahr_t = "数据待更新"
    elif ahr_f < 0.45:
        ahr_t = "🔴抄底区"
    elif ahr_f <= 1.2:
        ahr_t = "🟢定投区"
    else:
        ahr_t = "🟡高估暂停"
    btc_txt = f"BTC ${btc:,}\nAHR999 {ahr} {ahr_t}\nIBIT ${ibit} · 本周 ¥{wk:,}/周"
except Exception as e:
    btc_txt = f"BTC 数据异常: {e}"

title = f"🎯 定投早报 · {date_str}"
desp = (
    f"**📈 纳指100**\n{ndx_txt}\n\n"
    f"**₿ 比特币**\n{btc_txt}\n\n"
    f"[纳指页面]({BASE}/) · [BTC页面]({BASE}/btc.html)"
)

# Send via Server酱
url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
req = urllib.request.Request(url, data=data)
req.add_header("User-Agent", "Mozilla/5.0")
try:
    r = urllib.request.urlopen(req, timeout=10)
    res = json.loads(r.read())
    print(f"PUSH OK: code={res.get('code')} msg={res.get('message')}")
except Exception as e:
    print(f"PUSH FAIL: {e}")
