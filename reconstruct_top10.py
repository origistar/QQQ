#!/usr/bin/env python
# 方法重建：用「标普500时点成分 + 12个月动量」重建 SPMO / MTUM 各调仓节点的前十。
# SPMO 宇宙=标普500，重建前十与官方持仓高度接近（权重不同，头部名字趋同），标注清楚。
# MTUM 宇宙应为 MSCI USA（含中盘），此处用标普500近似，标注「近似」。
# 这不是基金官方申报持仓，仅供趋势参考。
import csv, datetime as dt, json
import yfinance as yf
import numpy as np
import pandas as pd

NODES = {
    "SPMO": ["2025-06-30", "2025-12-31", "2026-06-30", "2026-08-13"],
    "MTUM": ["2025-02-28", "2025-05-31", "2025-08-31", "2025-11-30",
             "2026-02-28", "2026-05-31", "2026-08-12"],
}

pit = {}
with open("sp500_pit.csv", newline="") as f:
    r = csv.reader(f)
    next(r)
    for row in r:
        pit[row[0]] = [t for t in row[1].split(",") if t]

def universe_as_of(date_str):
    d = dt.date.fromisoformat(date_str)
    best = None
    for k in pit:
        kd = dt.date.fromisoformat(k)
        if kd <= d and (best is None or kd > best[0]):
            best = (kd, pit[k])
    return best[1]

def momentum_top10(tickers, node_date, prices):
    nd = dt.date.fromisoformat(node_date)
    py = nd - dt.timedelta(days=365)
    nd_s, py_s = nd.isoformat(), py.isoformat()
    res = {}
    for t in tickers:
        s = prices.get(t)
        if s is None:
            continue
        try:
            sub = s.loc[:nd_s].dropna()
            if len(sub) == 0:
                continue
            p_now = float(sub.iloc[-1])
            sub2 = s.loc[:py_s].dropna()
            if len(sub2) == 0:
                continue
            p_prev = float(sub2.iloc[-1])
        except Exception:
            continue
        if p_prev == 0 or np.isnan(p_prev):
            continue
        mom = p_now / p_prev - 1
        if np.isnan(mom):
            continue
        res[t] = mom
    ranked = sorted(res.items(), key=lambda x: -x[1])[:10]
    return [(t, round(m * 100, 1)) for t, m in ranked]

all_tk = set()
for fund, nodes in NODES.items():
    for n in nodes:
        all_tk.update(universe_as_of(n))
all_tk = sorted(all_tk)
print("总 tickers:", len(all_tk))

print("下载价格中...")
px = yf.download(all_tk, start="2023-12-01", end="2026-08-20",
                 auto_adjust=False, progress=False, threads=True, group_by="ticker")
prices = {}
if isinstance(px.columns, pd.MultiIndex):
    for t in all_tk:
        try:
            prices[t] = px[t]["Close"]
        except Exception:
            prices[t] = None
else:
    prices[all_tk[0]] = px["Close"]

out = {}
for fund, nodes in NODES.items():
    out[fund] = {}
    for n in nodes:
        uni = universe_as_of(n)
        top = momentum_top10(uni, n, prices)
        out[fund][n] = top
        print(fund, n, "->", [t for t, _ in top])

with open("reconstruct_top10.json", "w") as f:
    json.dump(out, f, indent=1)
print("saved reconstruct_top10.json")
