"""
动量ETF持仓跟踪 —— 抓取脚本
抓取 SPMO / MTUM 的「前十持仓 + 板块权重」，按日期追加到 momentum_snapshots.json。
数据源：yfinance.funds_data（与现有 GitHub Actions 基建同一库，无需额外密钥）。
用法：python momentum_tracker_fetch.py   （建议开 VPN）
"""
import yfinance as yf
import json
import datetime
import os

FUNDS = {
    'SPMO': 'Invesco S&P 500 Momentum ETF（半年度调仓）',
    'MTUM': 'iShares MSCI USA Momentum Factor ETF（季度调仓）',
}
SNAP = os.path.join(os.path.dirname(__file__), 'momentum_snapshots.json')


def fetch_one(tkr):
    tk = yf.Ticker(tkr)
    fd = tk.funds_data
    th = fd.top_holdings.head(10)
    col = 'Holding Percent' if 'Holding Percent' in th.columns else th.columns[-1]
    top = [{'symbol': str(i), 'name': str(r['Name']),
            'pct': round(float(r[col]) * 100, 2)} for i, r in th.iterrows()]
    sw = fd.sector_weightings or {}
    sectors = {k: round(float(v) * 100, 2) for k, v in sw.items()}
    return {'top': top, 'sectors': sectors}


def main():
    today = datetime.date.today().isoformat()
    snap = {today: {}}
    for tkr, desc in FUNDS.items():
        snap[today][tkr] = fetch_one(tkr)
        snap[today][tkr]['desc'] = desc
        print(f'  {tkr}: 前十 {len(snap[today][tkr]["top"])} 只, 板块 {len(snap[today][tkr]["sectors"])} 类')
    data = {}
    if os.path.exists(SNAP):
        with open(SNAP, encoding='utf-8') as f:
            data = json.load(f)
    data[today] = snap[today]   # 同日覆盖，不重复
    with open(SNAP, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'✅ 已写入快照 {today}（共 {len(data)} 个快照）')


if __name__ == '__main__':
    main()
