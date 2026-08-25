import numpy as np
import polars as pl
from datetime import date as date_type, datetime


class DataHandler:
    """Data loading and preprocessing module for trading strategy system.

    Handles data ingestion from CSV and Parquet files and prepares
    the data for strategy analysis.
    """

    REQUIRED_COLUMNS = frozenset({
        "date", "open", "high", "low", "close", "settle", "volume",
    })
    REQUIRED_NUMERIC_COLUMNS = frozenset({
        "open", "high", "low", "close", "settle", "volume",
    })
    PRICE_COLUMNS = frozenset({"open", "high", "low", "close", "settle"})

    def __init__(self, data_path, file_type="csv"):
        """
        :param data_path: 文件路径
        :param file_type: 文件类型 ('csv' 或 'parquet')
        """
        self.file_type = file_type
        if file_type == "csv":
            self.raw_data = pl.read_csv(data_path)
        elif file_type == "parquet":
            self.raw_data = pl.read_parquet(data_path)
        else:
            raise ValueError("不支持的file_type类型，请使用'csv'或'parquet'")

        missing = self.REQUIRED_COLUMNS - set(self.raw_data.columns)
        if missing:
            raise ValueError(f"数据缺少必需列: {sorted(missing)}")

        self.dates = None
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.settle = None
        self.volume = None

    @staticmethod
    def _normalize_boundary(value, label):
        """将 date/datetime 边界统一为 datetime。"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date_type):
            return datetime.combine(value, datetime.min.time())
        raise TypeError(f"{label} 必须是 datetime/date/None，收到 {type(value).__name__}")

    def preprocess_data(self, start_date=None, end_date=None):
        """预处理数据。

        价格列不做前向/后向填充；存在缺失价格时直接报错，避免把未来价格
        带入历史回测。非价格数值列的缺失值填充为 0。
        """
        if self.raw_data.is_empty():
            raise ValueError("行情数据为空，无法进行回测")

        missing = self.REQUIRED_COLUMNS - set(self.raw_data.columns)
        if missing:
            raise ValueError(f"数据缺少必需列: {sorted(missing)}")
        if self.raw_data["date"].is_null().any():
            raise ValueError("日期列 date 包含缺失值")

        date_dtype = self.raw_data.schema["date"]
        try:
            if date_dtype == pl.String:
                self.raw_data = self.raw_data.with_columns(
                    pl.col("date").str.to_datetime(
                        format="%Y-%m-%d", strict=True
                    )
                )
            elif date_dtype == pl.Date:
                self.raw_data = self.raw_data.with_columns(
                    pl.col("date").cast(pl.Datetime)
                )
            elif isinstance(date_dtype, pl.Datetime):
                pass
            else:
                raise ValueError(
                    f"日期列 date 类型不支持: {date_dtype}，"
                    "请使用 YYYY-MM-DD 字符串、Date 或 Datetime"
                )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"日期列 date 无法解析: {exc}") from exc

        if self.raw_data["date"].is_null().any():
            raise ValueError("日期列 date 包含无法解析的值")

        # 策略计算要求时间顺序稳定；重复日期会造成重复收益区间。
        self.raw_data = self.raw_data.sort("date")
        if self.raw_data["date"].n_unique() != self.raw_data.height:
            raise ValueError("日期列 date 包含重复日期，无法安全回测")

        min_date = self.raw_data["date"].min()
        max_date = self.raw_data["date"].max()
        start_date = self._normalize_boundary(start_date, "start_date")
        end_date = self._normalize_boundary(end_date, "end_date")

        if start_date is not None:
            if start_date < min_date:
                start_date = None
            elif start_date > max_date:
                raise ValueError(
                    f"起始日期 {start_date} 超出数据范围 (最晚 {max_date})"
                )
        if end_date is not None:
            if end_date > max_date:
                end_date = None
            elif end_date < min_date:
                raise ValueError(
                    f"截止日期 {end_date} 早于数据范围 (最早 {min_date})"
                )
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError(f"起始日期 {start_date} 晚于截止日期 {end_date}")

        if start_date is not None or end_date is not None:
            filters = []
            if start_date is not None:
                filters.append(pl.col("date") >= start_date)
            if end_date is not None:
                filters.append(pl.col("date") <= end_date)
            self.raw_data = self.raw_data.filter(*filters)

        if self.raw_data.is_empty():
            raise ValueError("日期筛选后没有可用于回测的数据")

        for col in sorted(self.REQUIRED_NUMERIC_COLUMNS):
            dtype = self.raw_data.schema[col]
            if not dtype.is_numeric():
                raise ValueError(
                    f"必需数值列 {col} 不是数值类型（dtype={dtype}）"
                )

        # 数值列统一为 Float64，避免整数价格导致指标截断或无法写入 NaN。
        for col in self.raw_data.columns:
            if col == "date" or not self.raw_data.schema[col].is_numeric():
                continue
            expr = pl.col(col).cast(pl.Float64).fill_nan(None)
            if col in self.PRICE_COLUMNS:
                # 价格缺失直接报错，不使用 backward fill 引入未来数据。
                self.raw_data = self.raw_data.with_columns(expr)
            else:
                self.raw_data = self.raw_data.with_columns(expr.fill_null(0))

        for col in sorted(self.REQUIRED_NUMERIC_COLUMNS):
            if self.raw_data[col].is_null().any():
                raise ValueError(
                    f"必需数值列 {col} 包含缺失值，请清理数据后再回测"
                )

        for col in self.raw_data.columns:
            if col == "date" or not self.raw_data.schema[col].is_numeric():
                continue
            values = self.raw_data[col].to_numpy()
            if not np.isfinite(values).all():
                raise ValueError(f"数值列 {col} 包含 NaN 或无穷值")
            if col in self.PRICE_COLUMNS and (values <= 0).any():
                n_bad = int((values <= 0).sum())
                raise ValueError(
                    f"价格列 {col} 存在 {n_bad} 个 ≤ 0 的值，无法安全用于回测"
                )

        self.dates = self.raw_data["date"].to_numpy()
        self.open = self.raw_data["open"].to_numpy()
        self.high = self.raw_data["high"].to_numpy()
        self.low = self.raw_data["low"].to_numpy()
        self.close = self.raw_data["close"].to_numpy()
        self.settle = self.raw_data["settle"].to_numpy()
        self.volume = self.raw_data["volume"].to_numpy()
        return self
