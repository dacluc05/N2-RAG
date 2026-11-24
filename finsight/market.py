from datetime import date, timedelta
from math import isfinite
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from urllib.parse import quote


def number(value):
    try:
        x = float(value)
        return x if not isinstance(value, bool) and isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def yahoo_market(ticker: str, as_of: date, historical: bool, timeout: float) -> dict:
    import yfinance as yf

    if historical:
        # Vendor history may apply later split adjustments. Omit it for point-in-time reports.
        return {}
    symbol = ticker.replace(".", "-")
    import certifi
    bundle = certifi.where()
    if bundle.isascii():
        return read_market(yf.Ticker(symbol),symbol,as_of,timeout)

    # Some Windows libcurl builds cannot open a CA bundle in a non-ASCII path.
    from curl_cffi.requests import Session
    with TemporaryDirectory(prefix="finsight-ca-") as temp:
        copy = Path(temp)/"cacert.pem"
        if not str(copy).isascii():
            raise ValueError("Yahoo cần đường dẫn thư mục tạm Windows không chứa ký tự ngoài ASCII.")
        copyfile(bundle,copy)
        with Session(impersonate="chrome",verify=str(copy)) as session:
            return read_market(yf.Ticker(symbol,session=session),symbol,as_of,timeout)


def read_market(stock, ticker: str, as_of: date, timeout: float) -> dict:
    history = stock.history(start=as_of-timedelta(days=50), end=as_of+timedelta(days=1),
                            auto_adjust=False, timeout=min(timeout,10), raise_errors=True)
    if history.empty:
        return {}
    rows = [{"date": str(i.date()), "close": number(row.get("Close")), "volume": number(row.get("Volume"))}
            for i,row in history.iterrows() if i.date() < as_of and number(row.get("Close")) is not None]
    metadata = stock.history_metadata
    return {"url":f"https://finance.yahoo.com/quote/{quote(ticker.replace('.', '-'))}/history/",
            "currency":metadata.get("currency"), "observations":rows,"snapshot_date":str(as_of),
            "source":"yahoo", "scope":"Giá đóng cửa các phiên trước mốc chốt."}
