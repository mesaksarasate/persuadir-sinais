"""
Persuadir Sinais - Ingestão de dados
-------------------------------------
Busca candles (velas) de preço reais via ccxt, numa exchange pública,
sem precisar de chave de API (só leitura de mercado).
"""

import ccxt
import pandas as pd


def get_exchange(exchange_id: str):
    """Cria a conexão (somente leitura) com a exchange escolhida."""
    exchange_class = getattr(ccxt, exchange_id)
    return exchange_class({"enableRateLimit": True})


def fetch_candles(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Busca os últimos `limit` candles de `symbol` no `timeframe` pedido.
    Retorna um DataFrame com colunas: timestamp, open, high, low, close, volume.
    """
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_all(exchange, symbols: list, timeframe: str, limit: int) -> dict:
    """Busca candles para uma lista de símbolos. Retorna {symbol: DataFrame}."""
    data = {}
    for symbol in symbols:
        try:
            data[symbol] = fetch_candles(exchange, symbol, timeframe, limit)
        except Exception as exc:
            # Um símbolo com erro (rede, símbolo inválido etc.) não deve
            # derrubar a análise dos outros - só registra e segue.
            print(f"[data_feed] Falha ao buscar {symbol}: {exc}")
    return data
