"""
Persuadir Sinais V2 - Configuração
--------------------------------------
"""

SYMBOLS = [
    "BTC/USDT",
    "SOL/USDT",
    "LINK/USDT",
]

EXCHANGE_ID = "binance"

# Múltiplos intervalos de tempo analisados juntos. O sinal só dispara
# quando pelo menos MIN_TIMEFRAMES_AGREE concordam na direção - isso é
# o que filtra ruído e prioriza eficácia sobre quantidade de sinais.
TIMEFRAMES = {
    "1m": {"weight": 0.5, "limit": 120},
    "15m": {"weight": 0.3, "limit": 96},   # 24h de histórico em candles de 15min
    "1h": {"weight": 0.2, "limit": 72},    # 3 dias de histórico em candles de 1h
}
MIN_TIMEFRAMES_AGREE = 2  # de 3

# Sensibilidade do limiar adaptativo (em desvios-padrão do score
# histórico do PRÓPRIO ativo no timeframe de 1m)
SIGNAL_SENSITIVITY = 1.5

# Depois de quantos candles de 1m um sinal é considerado "resolvido"
# para fins de aprendizado (comparar se a direção prevista se confirmou)
RESOLUTION_HORIZON_CANDLES = 5

MODE = "AVISO"
NOTIFY_CHANNEL = "CONSOLE"
