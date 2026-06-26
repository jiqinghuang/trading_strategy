# -*- coding: utf-8 -*-
"""
Excel → Parquet 数据管道

每个品种从零创建 Excel workbook → Wind 生成数据 → 读取 → 丢弃。
无模板文件、无残留、无跨品种串写。

使用方法：
    python excel_to_parquet.py --end 20260508
    python excel_to_parquet.py --end 20260508 --full
    python excel_to_parquet.py --end 20260508 -s AU(T+D).SGE
"""

import argparse
import msvcrt
import os
import re
import sys
from datetime import datetime, timedelta

import polars as pl
import win32com.client

# ---------- 配置 ----------

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_START_DATE = datetime(1990, 1, 1).date()

SYMBOLS = [
    "AFI.WI",
    "AGFI.WI",
    "ALFI.WI",
    "AOFI.WI",
    "APLFI.WI",
    "AUFI.WI",
    "BCFI.WI",
    "BFI.WI",
    "BRFI.WI",
    "BUFI.WI",
    "CFFI.WI",
    "CFI.WI",
    "CJFI.WI",
    "CSFI.WI",
    "CUFI.WI",
    "CYFI.WI",
    "EBFI.WI",
    "ECFI.WI",
    "EGFI.WI",
    "FBFI.WI",
    "FGFI.WI",
    "FUFI.WI",
    "HCFI.WI",
    "IFI.WI",
    "JDFI.WI",
    "JFI.WI",
    "JMFI.WI",
    "LCFI.WI",
    "LFI.WI",
    "LGFI.WI",
    "LHFI.WI",
    "LUFI.WI",
    "MAFI.WI",
    "MFI.WI",
    "NIFI.WI",
    "NRFI.WI",
    "OIFI.WI",
    "PBFI.WI",
    "PFFI.WI",
    "PFI.WI",
    "PGFI.WI",
    "PKFI.WI",
    "PPFI.WI",
    "PRFI.WI",
    "PSFI.WI",
    "PXFI.WI",
    "RBFI.WI",
    "RMFI.WI",
    "RRFI.WI",
    "RSFI.WI",
    "RUFI.WI",
    "SAFI.WI",
    "SCFI.WI",
    "SFFI.WI",
    "SHFI.WI",
    "SIFI.WI",
    "SMFI.WI",
    "SNFI.WI",
    "SPFI.WI",
    "SRFI.WI",
    "SSFI.WI",
    "TAFI.WI",
    "URFI.WI",
    "VFI.WI",
    "WRFI.WI",
    "YFI.WI",
    "ZNFI.WI",
    "AU(T+D).SGE",
    "AG(T+D).SGE",
]

FIELD_NAMES = ["open", "high", "low", "close", "settle", "volume", "oi", "amt"]
FIELD_STR = ",".join(FIELD_NAMES)
DATE_FORMAT = "%Y-%m-%d"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# WSD 公式模板，写入时替换 {symbol} {start} {end}
WSD_FORMULA = (
    '=WSD("{symbol}","{fields}","{start}","{end}",'
    '"unit=1","TradingCalendar=SHFE","PriceAdj=",'
    '"rptType=1","Version=1","ShowParams=Y","UnitMask=32",'
    '"cols=8;rows=10000")'
)

# ---------- 路径工具 ----------


def get_parquet_path(symbol):
    clean = re.sub(r"[^\w]", "_", symbol)
    return os.path.join(DATA_DIR, f"{clean}.parquet")


def get_last_date(symbol):
    path = get_parquet_path(symbol)
    try:
        max_date = (
            pl.scan_parquet(path)
            .filter(pl.col("date").str.contains(DATE_RE.pattern))
            .select(pl.col("date").max())
            .collect()
            .item()
        )
        return datetime.strptime(max_date, DATE_FORMAT).date() if max_date else None
    except FileNotFoundError:
        return None


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


# ---------- 日期解析 ----------


def parse_end_date(date_str):
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法解析日期 '{date_str}'，支持格式: YYYYMMDD 或 YYYY-MM-DD")


# ---------- Excel 操作 ----------


def build_workbook(excel, symbol, start_date, end_date):
    """从零创建一个 workbook，写入品种/日期/公式，返回 worksheet"""
    wb = excel.Workbooks.Add()
    ws = wb.Worksheets(1)

    start = start_date.strftime(DATE_FORMAT)
    end = end_date.strftime(DATE_FORMAT)

    sheet_name = (
        f"{symbol} {start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    )
    ws.Name = sheet_name[:31]

    formula = WSD_FORMULA.format(symbol=symbol, fields=FIELD_STR, start=start, end=end)
    ws.Range("B7").Formula2 = formula

    return wb, ws


def read_data_range(ws):
    """从 A7:I{last_row} 读取 WSD 溢出数据，跳过非日期行"""
    last_row = ws.Cells(ws.Rows.Count, 1).End(-4162).Row
    if last_row <= 6:
        return None

    raw = ws.Range(f"A7:I{last_row}").Value
    if raw is None:
        return None

    rows = []
    for row in raw:
        if row[0] is None or len(row) < 9:
            continue
        date_str = (
            row[0].strftime(DATE_FORMAT)
            if isinstance(row[0], datetime)
            else str(row[0])[:10]
        )
        if not DATE_RE.match(date_str):
            continue
        vals = {}
        for i, name in enumerate(FIELD_NAMES):
            v = row[i + 1]
            if v is None:
                vals[name] = None
            else:
                try:
                    vals[name] = float(v)
                except (ValueError, TypeError):
                    # Wind WSD 可能返回 '#N/A'、'#ERROR'、'Err'、'NA' 等错误字符串
                    # （停牌、非交易日、数据缺口）；视为缺失而非让整个品种失败
                    vals[name] = None
        rows.append({"date": date_str, **vals})

    if not rows:
        return None

    df = pl.DataFrame(rows)
    df = df.filter(~pl.all_horizontal([pl.col(c).is_null() for c in FIELD_NAMES]))
    return df


def print_verification(symbol, new_df, existing=None):
    """打印已有数据末尾 + 新数据，方便终端核对"""
    print()
    if existing is None:
        print("--- 新品种，无已有数据 ---")
    else:
        tail = existing.tail(22)
        print(f"--- 已有末尾 ({tail.height}行, 截止 {existing['date'][-1]}) ---")
        print(tail)
    print(
        f"\n--- 新获取 ({len(new_df)}行  {new_df['date'][0]} ~ {new_df['date'][-1]}) ---"
    )
    print(new_df)
    print()


def merge_and_save(symbol, new_df, existing=None):
    path = get_parquet_path(symbol)
    if existing is None:
        new_df.sort("date").write_parquet(path)
    else:
        pl.concat([existing, new_df]).unique("date", keep="last").sort(
            "date"
        ).write_parquet(path)


# ---------- 交互 ----------


class QuitPipeline(Exception):
    pass


def wait_key():
    """阻塞等待按键，回车='read' ESC='skip' Q='quit'"""
    while True:
        k = msvcrt.getch()
        if k == b"\r":
            return "read"
        if k == b"\x1b":
            return "skip"
        if k in (b"q", b"Q"):
            raise QuitPipeline


# ---------- 主流程 ----------


def main():
    pl.Config().set_tbl_cols(-1).set_tbl_width_chars(200)
    parser = argparse.ArgumentParser(description="Excel → Parquet 数据管道")
    parser.add_argument(
        "--end", type=str, required=True, help="截止日期，格式 YYYYMMDD 或 YYYY-MM-DD"
    )
    parser.add_argument(
        "--full", action="store_true", help="全量重新获取（忽略已有 parquet）"
    )
    parser.add_argument("-s", "--symbol", type=str, help="只更新指定品种")
    args = parser.parse_args()

    try:
        end_date = parse_end_date(args.end)
    except ValueError as e:
        print(f"日期错误: {e}")
        sys.exit(1)

    ensure_data_dir()
    targets = [args.symbol] if args.symbol else SYMBOLS

    print("正在启动 Excel...")
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.ScreenUpdating = False

    success = 0
    up_to_date = 0
    skipped = []
    failed = []

    try:
        for i, symbol in enumerate(targets):
            print(f"[{i + 1:2d}/{len(targets)}] {symbol:<18s}", end=" ", flush=True)

            last_date = None if args.full else get_last_date(symbol)
            if last_date and last_date >= end_date:
                print(f"已是最新 (parquet 截止 {last_date})")
                up_to_date += 1
                continue

            start_date = (
                (last_date + timedelta(days=1)) if last_date else DEFAULT_START_DATE
            )

            try:
                wb, ws = build_workbook(excel, symbol, start_date, end_date)
                excel.CalculateUntilAsyncQueriesDone()

                # 第一步：按键读取
                print("回车=读取  ESC=跳过  Q=退出", end=" ", flush=True)
                action = wait_key()
                if action == "skip":
                    print("→ 跳过")
                    wb.Close(SaveChanges=False)
                    skipped.append(symbol)
                    continue

                df = read_data_range(ws)
                wb.Close(SaveChanges=False)

                if df is None or df.is_empty():
                    print("→ 无数据")
                    failed.append(symbol)
                    continue

                try:
                    existing_df = pl.read_parquet(get_parquet_path(symbol))
                except FileNotFoundError:
                    existing_df = None

                print_verification(symbol, df, existing_df)

                # 第二步：按键确认保存
                print("回车=保存  ESC=跳过  Q=退出", end=" ", flush=True)
                action = wait_key()
                if action == "skip":
                    print("→ 跳过")
                    skipped.append(symbol)
                    continue

                merge_and_save(symbol, df, existing_df)
                print(f"→ OK  {len(df):4d} 行  {df['date'][0]} ~ {df['date'][-1]}")
                success += 1

            except QuitPipeline:
                print("→ 退出")
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
                break

            except Exception as e:
                print(f"→ 失败: {e}")
                failed.append(symbol)

    finally:
        excel.Quit()

    total = len(targets)
    print(f"\n{'=' * 50}")
    print(
        f"截止日期: {end_date}  |  成功: {success}  已最新: {up_to_date}  跳过: {len(skipped)}  失败: {len(failed)}  /  共 {total}"
    )
    if skipped:
        print("跳过品种:", ", ".join(skipped))
    if failed:
        print("失败品种:", ", ".join(failed))


if __name__ == "__main__":
    main()
