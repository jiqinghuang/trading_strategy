"""
一键更新：运行策略 → 更新网站（仅本地同步，不推送）
用法：python update_local_website.py
"""

from pathlib import Path
import os
import re
import shutil
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

from run_all_strategies import StrategyRunner

# 路径配置
TRADING_DIR = Path(__file__).resolve().parent
WEBSITE_DIR = TRADING_DIR.parent / "jiqinghuang.github.io"
PLOTS_SRC = TRADING_DIR / "results" / "plots"
PLOTS_DST = WEBSITE_DIR / "assets" / "plots"
EXCEL_PATH = TRADING_DIR / "results" / "strategy_results.xlsx"
HTML_PATH = WEBSITE_DIR / "project-quant-trading.html"


def run_strategies():
    """运行所有策略并生成结果"""
    plt.rcParams["font.sans-serif"] = ["SimHei"]
    plt.rcParams["axes.unicode_minus"] = False

    runner = StrategyRunner(data_path=str(TRADING_DIR / "data" / "AUFI_WI.parquet"), output_dir=str(TRADING_DIR / "results"))
    results = runner.run_all_strategies()
    if results:
        runner.save_to_excel()
    return results


def copy_plots():
    """将图表复制到网站目录"""
    PLOTS_DST.mkdir(parents=True, exist_ok=True)
    for f in PLOTS_SRC.glob("*.png"):
        shutil.copy2(f, PLOTS_DST / f.name)
    print(f"已复制图表到 {PLOTS_DST}")


def update_html():
    """读取 Excel 结果，更新 projects.html 中的数据"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="Summary")
    # 将百分比字符串转为数字再排序，避免字符串排序错误（如 "99%" 排在 "150%" 前面）
    df["_return_num"] = df["cumulative_return"].str.strip("%").astype(float)
    df = df.sort_values("_return_num", ascending=False).reset_index(drop=True)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 更新最高累积收益统计
    best_return = round(float(df.iloc[0]["cumulative_return"].strip("%")))
    html = re.sub(
        r'(<div class="stat-number">)-?\d+(<span style="font-size:1\.2rem">%</span>)',
        rf"\g<1>{best_return}\g<2>",
        html,
        count=1,
    )

    # 2. 更新性能表
    # 类型判断：正收益用 highlight，负收益用 negative
    def cell_class(val):
        v = float(val.strip("%"))
        return "highlight" if v > 0 else ("negative" if v < 0 else "")

    rows_html = ""
    for _, row in df.iterrows():
        name = row.get("display_name", row["strategy_name"])
        cum = row["cumulative_return"]
        ann = row["annualized_return"]
        dd = row["max_drawdown"]
        trades = int(row["total_trades"])
        wr = row["win_rate"]
        avg = row["avg_trade_return"]

        cum_cls = cell_class(cum)
        ann_cls = cell_class(ann)
        dd_cls = cell_class(dd)

        cum_td = f'<td class="{cum_cls}">{cum}</td>' if cum_cls else f"<td>{cum}</td>"
        ann_td = f'<td class="{ann_cls}">{ann}</td>' if ann_cls else f"<td>{ann}</td>"
        dd_td = f'<td class="{dd_cls}">{dd}</td>' if dd_cls else f"<td>{dd}</td>"

        rows_html += f"""            <tr>
              <td><strong>{name}</strong></td>
              {cum_td}
              {ann_td}
              {dd_td}
              <td>{trades}</td>
              <td>{wr}</td>
              <td>{avg}</td>
            </tr>
"""

    # 替换 tbody 内容
    html = re.sub(
        r"(<tbody>)\s*\n(.*?)\s*(</tbody>)",
        f"\\1\n{rows_html}          \\3",
        html,
        flags=re.DOTALL,
    )

    # 3. 更新图片说明中的累积收益；无旧收益文本时也要补上
    for _, row in df.iterrows():
        name = row["strategy_name"]
        cum = row["cumulative_return"]
        display = row.get("display_name", name)
        pattern = (
            r'(<div class="gallery-caption">)'
            + re.escape(display)
            + r'(?P<before>\s*\([^<]*\))?'
            + r'(?:\s+—\s+<span data-lang="cn">累积收益 -?[\d.]+%</span>'
              r'<span data-lang="en">Cumulative Return -?[\d.]+%</span>)?'
            + r'(?P<after>\s*\([^<]*\))?'
            + r'(?P<closing></div>)'
        )

        def replace_caption(match):
            suffix = match.group("before") or match.group("after") or ""
            return (
                f'{match.group(1)}{display}{suffix} — '
                f'<span data-lang="cn">累积收益 {cum}</span>'
                f'<span data-lang="en">Cumulative Return {cum}</span>'
                f'{match.group("closing")}'
            )

        html, replacements = re.subn(pattern, replace_caption, html, count=1)
        if replacements != 1:
            raise ValueError(f"未找到网站图表说明: {display}")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已更新 {HTML_PATH}")


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"一键更新 {today}")
    print("=" * 60)

    # 1. 运行策略
    print("\n[1/3] 运行策略...")
    results = run_strategies()
    if not results:
        print("没有成功运行的策略，退出")
        return

    # 2. 复制图表
    print("\n[2/3] 复制图表到网站...")
    copy_plots()

    # 3. 更新 HTML
    print("\n[3/3] 更新网站数据...")
    update_html()

    print("\n" + "=" * 60)
    print("全部完成! 两个文件夹已同步更新。")
    print("=" * 60)


if __name__ == "__main__":
    main()
