"""
一键更新：运行策略 → 更新网站（仅本地同步，不推送）
用法：python update_local_website.py
"""

import os
import re
import shutil
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

from run_all_strategies import StrategyRunner

# 路径配置
TRADING_DIR = os.path.dirname(os.path.abspath(__file__))
WEBSITE_DIR = os.path.join(os.path.dirname(TRADING_DIR), "jiqinghuang.github.io")
PLOTS_SRC = os.path.join(TRADING_DIR, "results", "plots")
PLOTS_DST = os.path.join(WEBSITE_DIR, "assets", "plots")
EXCEL_PATH = os.path.join(TRADING_DIR, "results", "strategy_results.xlsx")
HTML_PATH = os.path.join(WEBSITE_DIR, "projects.html")


def run_strategies():
    """运行所有策略并生成结果"""
    plt.rcParams["font.sans-serif"] = ["SimHei"]
    plt.rcParams["axes.unicode_minus"] = False

    runner = StrategyRunner(data_path="data/AUFI_WI.parquet", output_dir="results")
    results = runner.run_all_strategies(years=5)
    if results:
        runner.save_to_excel()
    return results


def copy_plots():
    """将图表复制到网站目录"""
    os.makedirs(PLOTS_DST, exist_ok=True)
    for f in os.listdir(PLOTS_SRC):
        if f.endswith(".png"):
            shutil.copy2(os.path.join(PLOTS_SRC, f), os.path.join(PLOTS_DST, f))
    print(f"已复制图表到 {PLOTS_DST}")


def update_html(results):
    """读取 Excel 结果，更新 projects.html 中的数据"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="Summary")
    # 将百分比字符串转为数字再排序，避免字符串排序错误（如 "99%" 排在 "150%" 前面）
    df["_return_num"] = df["cumulative_return"].str.strip("%").astype(float)
    df = df.sort_values("_return_num", ascending=False).reset_index(drop=True)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 更新最高累积收益统计
    best_return = int(float(df.iloc[0]["cumulative_return"].strip("%")))
    html = re.sub(
        r'(<div class="stat-number">)\d+(<span style="font-size:1\.2rem">%</span>)',
        rf"\g<1>{best_return}\g<2>",
        html,
        count=1,
    )

    # 2. 更新性能表
    # 策略名映射：文件名 → 显示名
    name_map = {
        "TMA_5_20_60": "TMA (5/20/60)",
        "TMA_10_30_90": "TMA (10/30/90)",
        "EWMA_LONG_ONLY_30": "EWMA Long-Only",
        "EWMA_30": "EWMA Long-Short",
        "DONCHIAN_20": "Donchian (20)",
        "DONCHIAN_50": "Donchian (50)",
        "MACD_12_26_9": "MACD",
        "RSI_14_30_70": "RSI",
        "BOLLINGER_20_2": "Bollinger (20, 2.0)",
        "BOLLINGER_20_1.5": "Bollinger (20, 1.5)",
    }

    # 类型判断：正收益用 highlight，负收益用 negative
    def cell_class(val):
        v = float(val.strip("%"))
        return "highlight" if v > 0 else ("negative" if v < 0 else "")

    rows_html = ""
    for _, row in df.iterrows():
        name = name_map.get(row["strategy_name"], row["strategy_name"])
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

    # 3. 更新图片说明中的累积收益
    for _, row in df.iterrows():
        name = row["strategy_name"]
        cum = row["cumulative_return"]
        display = name_map.get(name, name)
        # 匹配 gallery-caption 中的收益数字
        pattern = (
            re.escape(display)
            + r""" — <span data-lang="cn">累积收益 [\d.]+%</span><span data-lang="en">Cumulative Return [\d.]+%</span>"""
        )
        replacement = f'{display} — <span data-lang="cn">累积收益 {cum}</span><span data-lang="en">Cumulative Return {cum}</span>'
        html = re.sub(pattern, replacement, html)

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
    update_html(results)

    print("\n" + "=" * 60)
    print("全部完成! 两个文件夹已同步更新。")
    print("=" * 60)


if __name__ == "__main__":
    main()
