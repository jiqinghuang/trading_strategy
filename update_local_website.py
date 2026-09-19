"""
一键更新：运行策略 → 更新网站（仅本地同步，不推送）
用法：python update_local_website.py
"""

from pathlib import Path
import re
import shutil
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

try:
    from PIL import Image
except ImportError:  # Pillow 缺失时跳过 webp 转换与尺寸更新，PNG 同步不受影响
    Image = None

from run_all_strategies import STRATEGIES, StrategyRunner

# 路径配置
TRADING_DIR = Path(__file__).resolve().parent
WEBSITE_DIR = TRADING_DIR.parent / "jiqinghuang.github.io"
PLOTS_SRC = TRADING_DIR / "results" / "plots"
PLOTS_DST = WEBSITE_DIR / "assets" / "plots"
HTML_PATH = WEBSITE_DIR / "project-quant-trading.html"

# 策略图命名约定：大写字母开头（EWMA_30、BOLLINGER_20_1.5 等）。
# 孤儿清理只碰这一类文件；margin_model_*、手工放置的图等不受影响。
STRATEGY_PLOT_STEM_RE = re.compile(r"^[A-Z][A-Z0-9_.]*$")


def run_strategies():
    """运行所有策略并生成结果（网站发布口径：已扣单边 3bps 交易成本的净值）"""
    plt.rcParams["font.sans-serif"] = ["SimHei"]
    plt.rcParams["axes.unicode_minus"] = False

    runner = StrategyRunner(data_path=str(TRADING_DIR / "data" / "AUFI_WI.parquet"),
                            output_dir=str(TRADING_DIR / "results"), fee_bps=3)
    results = runner.run_all_strategies()
    runner.save_to_excel()

    # 统计卡元数据：策略数与实际回测年限（日历天/365.25）
    dates = next(iter(runner.strategy_data.values()))["processed_data"]["Date"]
    days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
    meta = {"n_strategies": len(results), "years": days / 365.25}
    return results, meta


def _png_size(path):
    """读取 PNG 实际像素尺寸；Pillow 不可用或读取失败返回 None。"""
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            return img.size  # (width, height)
    except OSError:
        return None


def copy_plots():
    """将图表复制到网站目录，并同步生成 webp（网站 <picture> 优先加载 webp，
    只复制 PNG 会导致访客看到的仍是旧图）。"""
    PLOTS_DST.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for f in PLOTS_SRC.glob("*.png"):
        shutil.copy2(f, PLOTS_DST / f.name)
        sizes[f.stem] = _png_size(PLOTS_DST / f.name)
        if Image is None:
            continue
        webp_path = PLOTS_DST / (f.stem + ".webp")
        try:
            with Image.open(f) as img:
                img.save(webp_path, "WEBP", quality=80)
        except (OSError, ValueError) as exc:
            print(f"警告: webp 转换失败 {f.name}: {exc}")
    if Image is None:
        print("警告: 未安装 Pillow，已跳过 webp 转换——网站 webp 图表不会更新！")
    else:
        print(f"已复制图表（含 webp）到 {PLOTS_DST}")
    return sizes


def cleanup_stale_plots():
    """删除网站 plots 目录中已不在当前策略清单里的旧策略图（png+webp 一并删）。

    只按 STRATEGY_PLOT_STEM_RE 识别同步生成的策略图；margin_model_* 等
    其他来源的图表不在清理范围，避免误删。返回删除的文件名列表。"""
    keep = {name for _, name, _, _ in STRATEGIES}
    removed = []
    for f in sorted(PLOTS_DST.glob("*")):
        if f.suffix.lower() not in (".png", ".webp"):
            continue
        if f.stem in keep or not STRATEGY_PLOT_STEM_RE.match(f.stem):
            continue
        f.unlink()
        removed.append(f.name)
    if removed:
        print(f"已清理不再引用的旧图表 {len(removed)} 个: {', '.join(removed)}")
    else:
        print("plots 目录无孤儿图表")
    return removed


def update_img_dimensions(sizes):
    """按实际 PNG 尺寸更新网站 <img> 的 width/height，避免图变形或预留错位。
    最佳努力：找不到对应图或 Pillow 不可用时警告并跳过，不阻断同步。"""
    if Image is None or not sizes:
        return
    html = HTML_PATH.read_text(encoding="utf-8")
    patched = 0
    for name, (width, height) in sizes.items():
        if width is None:
            continue
        pattern = (
            r'(<img src="assets/plots/' + re.escape(name) + r'\.png"[^>]*'
            r'width=")\d+(" height=")\d+(")'
        )
        html, n = re.subn(
            pattern, rf"\g<1>{width}\g<2>{height}\g<3>", html, count=1
        )
        if n:
            patched += n
    if patched != len(sizes):
        print(f"提示: 图表尺寸更新 {patched}/{len(sizes)} 张（其余为页面暂无或尺寸未变化）")
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"图片尺寸已核对: {HTML_PATH.name}")


def _fmt_pct(v):
    """比率列 → "12.33%"；NaN（如无交易策略的年化收益）→ 空串。"""
    return f"{v:.2%}" if pd.notna(v) else ""


def update_html(results, meta):
    """用原始回测结果（runner.results 的数值 dict）更新页面数据"""
    # 数值排序，最高收益排第一（Excel 里已是格式化字符串，这里直接用原始数值）
    results = sorted(results, key=lambda r: r["cumulative_return"], reverse=True)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 更新最高累积收益统计（先按展示口径保留两位小数，再取整，与表格显示一致）
    best_return = round(round((results[0]["cumulative_return"] - 1) * 100, 2))
    html, n_stat = re.subn(
        r'(<div class="stat-number">)-?\d+(<span style="font-size:1\.2rem">%</span>)',
        rf"\g<1>{best_return}\g<2>",
        html,
        count=1,
    )
    if n_stat != 1:
        raise ValueError(
            f"未找到网站顶部统计数字（匹配到 {n_stat} 处），页面结构可能已变化"
        )

    # 1.5 更新统计卡（策略数 / 品种数 / 回测年限），消除手写数字漂移
    def set_card(html, label_cn, value):
        """按卡片标签锚定更新 stat-number；预期恰好匹配 1 处。"""
        pattern = (
            r'(<div class="stat-number">)[^<]+'
            r'(</div>\s*<div class="stat-label"><span data-lang="cn">' + re.escape(label_cn) + r'</span>)'
        )
        html, n = re.subn(pattern, rf"\g<1>{value}\g<2>", html)
        if n != 1:
            raise ValueError(f"统计卡「{label_cn}」预期匹配 1 处，实际 {n} 处")
        return html

    n_symbols = len(list((TRADING_DIR / "data").glob("*.parquet")))
    html = set_card(html, "策略算法", meta["n_strategies"])
    html = set_card(html, "商品品种", n_symbols)
    html, n_year = re.subn(
        r'(<div class="stat-number">)[\d.]+(<span style="font-size:1\.2rem">yr</span>)',
        rf"\g<1>{meta['years']:.1f}\g<2>",
        html,
    )
    if n_year != 1:
        raise ValueError(f"回测周期卡预期匹配 1 处，实际 {n_year} 处")

    # 2. 更新性能表（原始数值在出口处一次性格式化，不再经过 Excel 字符串往返）
    def cell_class(v):
        """正收益用 highlight，负收益用 negative，零/NaN 无样式。"""
        if pd.isna(v) or v == 0:
            return ""
        return "highlight" if v > 0 else "negative"

    def td(v, text):
        cls = cell_class(v)
        return f'<td class="{cls}">{text}</td>' if cls else f"<td>{text}</td>"

    rows_html = ""
    for row in results:
        name = row.get("display_name", row["strategy_name"])
        sharpe = row["sharpe_ratio"]
        sharpe_text = f"{sharpe:.2f}" if pd.notna(sharpe) else ""

        rows_html += f"""            <tr>
              <td><strong>{name}</strong></td>
              {td(row["cumulative_return"] - 1, _fmt_pct(row["cumulative_return"] - 1))}
              {td(row["annualized_return"], _fmt_pct(row["annualized_return"]))}
              {td(row["annualized_volatility"], _fmt_pct(row["annualized_volatility"]))}
              {td(sharpe, sharpe_text)}
              {td(row["max_drawdown"], _fmt_pct(row["max_drawdown"]))}
              <td>{int(row["total_trades"])}</td>
              {td(row["win_rate"], _fmt_pct(row["win_rate"]))}
              {td(row["avg_trade_return"], _fmt_pct(row["avg_trade_return"]))}
            </tr>
"""

    # 替换 tbody 内容（锚定到 id="perf-table"，页面新增其他表格也不会误伤）
    html, n_tbody = re.subn(
        r'(<table[^>]*id="perf-table"[^>]*>[\s\S]*?<tbody>)\s*\n(.*?)\s*(</tbody>)',
        f"\\1\n{rows_html}          \\3",
        html,
        flags=re.DOTALL,
    )
    if n_tbody != 1:
        raise ValueError(
            f"未找到唯一的绩效表 tbody（匹配到 {n_tbody} 处），页面结构可能已变化"
        )

    # 3. 更新图片说明中的累积收益；无旧收益文本时也要补上
    for row in results:
        name = row["strategy_name"]
        cum = f"{row['cumulative_return'] - 1:.2%}"
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
    results, meta = run_strategies()

    # 2. 复制图表（含 webp），并清理已不在策略清单里的旧图
    print("\n[2/3] 复制图表到网站...")
    sizes = copy_plots()
    cleanup_stale_plots()

    # 3. 更新网站数据
    print("\n[3/3] 更新网站数据...")
    update_html(results, meta)
    update_img_dimensions(sizes)

    print("\n" + "=" * 60)
    print("全部完成! 两个文件夹已同步更新。")
    print("=" * 60)


if __name__ == "__main__":
    main()
