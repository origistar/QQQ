#!/usr/bin/env python
# 渲染「前十进出」跟踪表：
#  - 重建列 = 2025 各调仓节点（方法重建，趋势参考）
#  - 最右列 = 最新官方实际持仓（yfinance funds_data，真实公布数据）
# 新进/退出相对上一节点标记。
import json, datetime as dt, os

R = json.load(open("reconstruct_top10.json"))
REAL = json.load(open("momentum_snapshots.json"))
LATEST_DATE = max(REAL.keys())

# 候选重建节点（2025 起各调仓节点）
CANDIDATE = {
    "SPMO": ["2025-06-30", "2025-12-31", "2026-06-30"],
    "MTUM": ["2025-02-28", "2025-05-31", "2025-08-31", "2025-11-30", "2026-02-28", "2026-05-31"],
}
MAX_COLS = 5  # 含「最新官方」列，最多 5 列：最新 + 往前最近 4 期重建

def pick_cols(fund):
    # 取时间最新的 (MAX_COLS-1) 个重建节点（与最新列合计 ≤5 列），按时间正序（左旧→右新）
    nodes = [n for n in CANDIDATE[fund] if n in R.get(fund, {})]
    recent = sorted(nodes, reverse=True)[: MAX_COLS - 1]
    return sorted(recent)
META = {
    "SPMO": "Invesco S&P 500 Momentum ETF · 半年度调仓 · 宇宙=标普500",
    "MTUM": "iShares MSCI USA Momentum Factor ETF · 季度调仓 · 宇宙=标普500(近似MSCI USA)",
}

def latest_of(fund):
    top = REAL[LATEST_DATE][fund]["top"]  # [{symbol,pct,...}]
    return [x["symbol"] for x in top], {x["symbol"]: x["pct"] for x in top}

def section(fund):
    cols = []
    for n in pick_cols(fund):
        cur = [t for t, _ in R[fund][n]]
        cols.append((n, cur, {t: m for t, m in R[fund][n]}, "mom"))
    syms, pctmap = latest_of(fund)
    cols.append((f"最新·{LATEST_DATE}", syms, pctmap, "pct"))

    prev = set()
    transitions = []
    for name, csyms, _, _ in cols:
        curset = set(csyms)
        newp = [t for t in csyms if t not in prev]
        exits = [t for t in prev if t not in curset]
        transitions.append((name, newp, exits))
        prev = curset

    head = "".join(f'<th>{name}</th>' for name, _, _, _ in cols)
    rows = ""
    for i in range(10):
        cells = ""
        for idx, (name, csyms, valmap, kind) in enumerate(cols):
            if i < len(csyms):
                tk = csyms[i]
                val = valmap[tk]
                sub = f'<span class="mom">{val:+}%</span>' if kind == "mom" else f'<span class="mom">{val}%</span>'
                prevset = set(cols[idx - 1][1]) if idx > 0 else set()
                tag = ' <span class="new">新进</span>' if (idx > 0 and tk not in prevset) else ""
                cells += f"<td>{tk}{sub}{tag}</td>"
            else:
                cells += '<td class="na">—</td>'
        rows += f'<tr><td class="rk">{i+1}</td>{cells}</tr>'

    trans_html = ""
    for name, newp, exits in transitions[1:]:
        trans_html += (f'<div class="trans"><b>{name}</b> '
                       f'<span class="in">▲新进: {", ".join(newp) if newp else "无"}</span> '
                       f'<span class="out">▼退出: {", ".join(exits) if exits else "无"}</span></div>')
    return f'''
    <div class="fund">
      <h2>{fund} <span class="meta">{META[fund]}</span></h2>
      <div class="tablewrap">
      <table>
        <thead><tr><th class="rk">#</th>{head}</tr></thead>
        <tbody>{rows}</tbody>
      </table>
      </div>
      <div class="transbox">{trans_html}</div>
    </div>'''

html = f'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>动量ETF前十进出跟踪</title>
<style>
 * {{ box-sizing:border-box; }}
 body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6f8; color:#10151a; margin:0; padding:14px; }}
 h1 {{ font-size:20px; margin:0 0 2px; }}
 .sub {{ color:#5b6b75; font-size:12px; margin-bottom:14px; }}
 .fund {{ background:#fff; border-radius:14px; padding:14px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
 h2 {{ font-size:16px; margin:0 0 10px; }}
 .meta {{ font-weight:400; font-size:11px; color:#7a8794; display:block; margin-top:3px; }}
 .tablewrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
 table {{ border-collapse:collapse; width:100%; min-width:620px; font-size:13px; }}
 th,td {{ border:1px solid #eef1f4; padding:6px 7px; text-align:left; white-space:nowrap; }}
 thead th {{ background:#eef3f8; font-size:11px; color:#3c4950; position:sticky; top:0; }}
 thead th:last-child {{ background:#fff3e0; color:#8a5a00; }}
 td.rk, th.rk {{ background:#fafbfc; color:#9aa6b0; width:26px; text-align:center; }}
 td .mom {{ color:#9aa6b0; font-size:10px; margin-left:4px; }}
 .new {{ color:#fff; background:#15803d; font-size:9px; border-radius:4px; padding:1px 4px; margin-left:3px; vertical-align:middle; }}
 .na {{ color:#cdd5db; }}
 .transbox {{ margin-top:10px; font-size:12px; }}
 .trans {{ margin:3px 0; }}
 .in {{ color:#15803d; }} .out {{ color:#b91c1c; margin-left:8px; }}
 .disc {{ background:#fff8ec; border:1px solid #f3e2bf; border-radius:12px; padding:12px; font-size:12px; color:#7a5b1a; line-height:1.6; }}
 .disc b {{ color:#5b4310; }}
 .leg {{ font-size:11px; color:#7a8794; margin:-8px 0 14px; }}
 .leg b {{ color:#8a5a00; }}
</style></head><body>
<h1>动量 ETF 前十进出跟踪</h1>
<div class="sub">SPMO（半年度调仓）· MTUM（季度调仓）· 近期 5 期（含最新官方持仓）· 生成 {dt.date.today().isoformat()}</div>
<div class="leg">左列=各调仓节点<b>方法重建</b>（标普500时点成分+12个月动量，仅看轮动趋势）；<b>最右列=最新官方实际持仓</b>（yfinance·{LATEST_DATE}抓取，基金公布数据）。每日自动刷新最右列。</div>
{section("SPMO")}
{section("MTUM")}
<div class="disc"><b>口径说明：</b>最右「最新」列为基金<b>官方公布</b>的前十（动量加权持仓，NVDA/AVGO 等高权重股自然在内），是真实数据。左侧重建列用「12个月纯收益」排序，与官方存在权重口径差，仅用于观察<b>个股/板块轮动</b>。MTUM 重建宇宙用标普500近似 MSCI USA（含中盘）。若要各历史节点也用<b>官方精确持仓</b>，需抓 SEC N-PORT 申报（较重，可后续做）。</div>
</body></html>'''
open("momentum_changes.html", "w", encoding="utf-8").write(html)
print("saved momentum_changes.html", len(html), "bytes; latest=", LATEST_DATE)
