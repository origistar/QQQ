#!/usr/bin/env python
# 动量ETF前十跟踪 —— 每日任务入口
# 1) 抓取最新官方前十 (yfinance funds_data) -> 追加 momentum_snapshots.json
# 2) 渲染 momentum_changes.html (重建列静态 + 最新列动态)
# 注意：重建列依赖 reconstruct_top10.json（历史静态，无需每日重算）。
import subprocess, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))

def run(script):
    p = subprocess.run([sys.executable, os.path.join(BASE, script)],
                       capture_output=True, text=True)
    print(p.stdout.strip())
    if p.returncode != 0:
        print("!! 失败:", script, p.stderr.strip())
        sys.exit(1)

if __name__ == "__main__":
    run("momentum_tracker_fetch.py")   # 追加最新官方快照
    run("render_changes.py")           # 重新生成页面
    print("✅ 每日更新完成")
