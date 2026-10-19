"""Symbols scanned. Yahoo Finance tickers → (display name, class).
Futures = the CME / COMEX / NYMEX / CBOT contracts the big prop firms allow (Topstep, Apex, TPT, MFFU…).
Micro and full-size contracts share one chart, so NQ=F stands for both NQ and MNQ."""

FUTURES = {
    "NQ=F": "NQ · MNQ", "ES=F": "ES · MES", "YM=F": "YM · MYM", "RTY=F": "RTY · M2K",
    "GC=F": "GC · MGC", "SI=F": "SI · SIL", "HG=F": "HG · MHG", "PL=F": "PL",
    "CL=F": "CL · MCL", "NG=F": "NG · QG", "RB=F": "RB", "HO=F": "HO",
    "ZB=F": "ZB", "ZN=F": "ZN", "ZF=F": "ZF", "ZT=F": "ZT",
    "6E=F": "6E · M6E", "6B=F": "6B · M6B", "6J=F": "6J", "6A=F": "6A · M6A", "6C=F": "6C", "6S=F": "6S",
    "ZC=F": "ZC", "ZS=F": "ZS", "ZW=F": "ZW", "ZL=F": "ZL", "ZM=F": "ZM", "LE=F": "LE", "HE=F": "HE",
    "BTC=F": "BTC · MBT", "ETH=F": "ETH · MET",
}

CRYPTO = {t + "-USD": t for t in [
    "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "AVAX", "LINK",
    "TON11419", "SUI20947", "DOT", "LTC", "BCH", "NEAR", "XLM", "HBAR", "UNI7083", "PEPE24478",
]}
# clean display names for the Yahoo tickers that carry an id suffix
CRYPTO.update({"TON11419-USD": "TON", "SUI20947-USD": "SUI", "UNI7083-USD": "UNI", "PEPE24478-USD": "PEPE"})

FOREX = {p + "=X": p[:3] + "/" + p[3:] for p in [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "EURAUD", "GBPAUD", "CADJPY", "CHFJPY", "XAUUSD",
]}

STOCKS = {t: t for t in [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK-B", "JPM",
    "LLY", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "NFLX", "AMD",
    "CRM", "ORCL", "ADBE", "PLTR", "COIN", "MSTR", "INTC", "MU", "SMCI", "ARM",
    "BA", "DIS", "NKE", "WMT", "KO", "PEP", "BAC", "GS", "UBER", "SHOP",
]}

ETFS = {t: t for t in ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "USO", "XLE", "XLF", "SMH", "ARKK"]}

INDICES = {"^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow 30", "^RUT": "Russell 2000",
           "^VIX": "VIX", "^GDAXI": "DAX", "^FTSE": "FTSE 100", "^N225": "Nikkei 225"}

UNIVERSE = {}
for cls, group in (("futures", FUTURES), ("crypto", CRYPTO), ("forex", FOREX),
                   ("stocks", STOCKS), ("etfs", ETFS), ("indices", INDICES)):
    for tkr, name in group.items():
        UNIVERSE[tkr] = (name, cls)
