import polars as pl

class DataHandler:
    """Data loading and preprocessing module for trading strategy system.

    Handles data ingestion from CSV and Parquet files and prepares
    the data for strategy analysis.

    Attributes:
        raw_data: Raw market data in DataFrame format
        dates: Numpy array of datetime objects
        open: Numpy array of opening prices
        close: Numpy array of closing prices  
        high: Numpy array of high prices
        low: Numpy array of low prices
        volume: Numpy array of trading volumes
    """
    def __init__(self, data_path, file_type='csv'):
        """
        :param data_path: 文件路径
        :param file_type: 文件类型 ('csv' 或 'parquet')
        """
        self.file_type = file_type
        if file_type == 'csv':
            self.raw_data = pl.read_csv(data_path)
        elif file_type == 'parquet':
            self.raw_data = pl.read_parquet(data_path)
        else:
            raise ValueError("不支持的file_type类型，请使用'csv'或'parquet'")
            
        # 初始化数据字段
        self.dates = None
        self.open = None
        self.high = None
        self.low = None
        self.close = None 
        self.settle = None
        self.volume = None

    def preprocess_data(self, start_date=None, end_date=None):
        """预处理数据
        Args:
            start_date (datetime.date): 起始日期(可选)
            end_date (datetime.date): 结束日期(可选)
        """
        # 检查并处理缺失值和NaN
        for col in self.raw_data.columns:
            if col == 'date':
                # 日期列不允许有缺失值
                if self.raw_data[col].is_null().any():
                    raise ValueError(f"日期列{col}包含缺失值")
            else:
                # 只对数值列处理NaN
                if self.raw_data[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
                    self.raw_data = self.raw_data.with_columns(
                        pl.col(col).fill_nan(None) # 将NaN转换为None
                                  .fill_null(strategy='forward') # 前向填充
                                  .fill_null(strategy='backward') # 后向填充
                                  .fill_null(0) # 最后将剩余的NaN填充为0
                    )

        # 转换日期列为datetime类型
        self.raw_data = self.raw_data.with_columns(
            pl.col('date').str.to_datetime()
        )

        # 获取数据中的实际日期范围
        min_date = self.raw_data['date'].min()
        max_date = self.raw_data['date'].max()

        # 自动调整超出范围的日期
        if start_date and start_date < min_date:
            start_date = None
        if end_date and end_date > max_date:
            end_date = None

        # 日期范围筛选
        if start_date or end_date:
            if start_date:
                self.raw_data = self.raw_data.filter(pl.col('date') >= start_date)
            if end_date:
                self.raw_data = self.raw_data.filter(pl.col('date') <= end_date)

        # 转换数据为numpy格式            
        self.dates = self.raw_data['date'].to_numpy()  # 直接使用已转换的日期列
        self.open = self.raw_data['open'].to_numpy()
        self.high = self.raw_data['high'].to_numpy()
        self.low = self.raw_data['low'].to_numpy()
        self.close = self.raw_data['close'].to_numpy()
        self.settle = self.raw_data['settle'].to_numpy()
        self.volume = self.raw_data['volume'].to_numpy()
        return self  # 添加返回自身以支持链式调用
