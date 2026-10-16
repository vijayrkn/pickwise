"""The investable universe: liquid US large caps spread across all 11 GICS sectors."""

UNIVERSE: dict[str, list[str]] = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "CSCO", "ACN",
        "INTC", "QCOM", "TXN", "IBM", "NOW", "INTU", "AMAT", "MU", "PANW", "ANET",
    ],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "VZ", "T", "CMCSA"],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "CMG",
    ],
    "Consumer Staples": ["WMT", "PG", "COST", "KO", "PEP", "PM", "MDLZ", "CL"],
    "Financials": [
        "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP", "SPGI", "SCHW", "C",
    ],
    "Health Care": [
        "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN", "ISRG", "VRTX",
    ],
    "Industrials": ["GE", "CAT", "RTX", "HON", "UNP", "BA", "DE", "LMT", "UPS", "ETN"],
    "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "PSX"],
    "Utilities": ["NEE", "SO", "DUK", "CEG"],
    "Real Estate": ["PLD", "AMT", "EQIX", "SPG"],
    "Materials": ["LIN", "SHW", "APD", "FCX"],
}

BENCHMARK = "SPY"


def all_tickers() -> list[str]:
    return [t for tickers in UNIVERSE.values() for t in tickers]


def sector_of(ticker: str) -> str:
    for sector, tickers in UNIVERSE.items():
        if ticker in tickers:
            return sector
    return "Unknown"
