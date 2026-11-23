"""
Persuadir Sinais - Indicadores adaptativos
---------------------------------------------
Princípio seguido aqui (igual ao resto da família Persuadir): nada de
regra fixa tipo "RSI > 70 é sempre venda". Cada indicador é medido
relativo ao PRÓPRIO comportamento recente do ativo (z-score), então o
mesmo evento é interpretado de forma diferente para um ativo calmo e
para um ativo agitado - o sistema se adapta em tempo real a cada
mercado, em vez de usar uma régua única para todos.
"""

import numpy as np
import pandas as pd


def zscore(series: pd.Series) -> pd.Series:
    """
    Transforma uma série em 'quantos desvios-padrão acima/abaixo da
    própria média recente' cada ponto está. É isso que torna o
    sistema adaptativo: o que é 'anormal' é recalculado a cada ciclo,
    a partir dos próprios dados, não de um número fixo no código.
    """
    mean = series.mean()
    std = series.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - mean) / std


def compute_momentum_score(df: pd.DataFrame, short: int = 5, long: int = 20) -> float:
    """
    Momentum: direção e força do movimento recente, medida pelo
    cruzamento de duas médias móveis (curta vs longa), normalizada
    pela volatilidade recente do próprio ativo (ATR simplificado).
    """
    close = df["close"]
    ema_short = close.ewm(span=short, adjust=False).mean()
    ema_long = close.ewm(span=long, adjust=False).mean()

    diff = (ema_short - ema_long)
    volatility = close.diff().abs().rolling(long).mean()
    volatility = volatility.replace(0, np.nan).bfill().ffill()

    normalized = diff / volatility
    return float(normalized.iloc[-1])


def compute_volume_score(df: pd.DataFrame) -> float:
    """
    Detecta volume anormal: compara o volume do candle mais recente
    com a distribuição de volume da janela (z-score). Volume alto
    costuma preceder/acompanhar movimentos mais confiáveis.
    """
    vol_z = zscore(df["volume"])
    return float(vol_z.iloc[-1])


def compute_rsi_like_score(df: pd.DataFrame, period: int = 14) -> float:
    """
    Versão do RSI (índice de força relativa) cujo resultado já sai
    centrado e normalizado (em vez de 0-100 com limiares fixos de
    30/70), para entrar direto no score combinado do signal_engine.
    """
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.bfill().ffill()
    # Centraliza em 0 (50 = neutro) e normaliza para a mesma escala
    # aproximada dos outros scores (-3 a +3 tipicamente).
    centered = (rsi - 50) / 15
    return float(centered.iloc[-1])


def compute_indicators(df: pd.DataFrame) -> dict:
    """Calcula todos os indicadores para o candle mais recente de um ativo."""
    return {
        "momentum": compute_momentum_score(df),
        "volume": compute_volume_score(df),
        "rsi": compute_rsi_like_score(df),
        "last_price": float(df["close"].iloc[-1]),
    }
