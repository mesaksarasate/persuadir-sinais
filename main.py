"""
Persuadir Sinais V3 - Ponto de entrada (GitHub Actions)
------------------------------------------------------------
Rodado pelo workflow do GitHub Actions, acionado por um evento
repository_dispatch (disparado pelo cron-job.org a cada 1 minuto) -
não pelo agendador `schedule:` do próprio GitHub, para não cair nas
limitações de frequência e no desligamento automático por inatividade.

Também pode ser rodado localmente, chamando `python main.py` direto -
útil para testar sem precisar do GitHub Actions.
"""

import config
import data_feed
import indicators
import signal_engine
import notifier
import state_store


def processar_simbolo(exchange, store, symbol: str):
    ind_by_tf = {}
    for tf, params in config.TIMEFRAMES.items():
        df = data_feed.fetch_candles(exchange, symbol, tf, params["limit"])
        if len(df) < 20:
            print(f"[main] Dados insuficientes em {tf} para {symbol}, pulando ciclo.")
            return
        ind_by_tf[tf] = indicators.compute_indicators(df)

    sig = signal_engine.evaluate(store, symbol, ind_by_tf)
    notifier.notify(sig)


def executar_ciclo():
    exchange = data_feed.get_exchange(config.EXCHANGE_ID)
    store = state_store.get_store()

    for symbol in config.SYMBOLS:
        try:
            processar_simbolo(exchange, store, symbol)
        except Exception as exc:
            print(f"[main] Erro processando {symbol}: {exc}")


if __name__ == "__main__":
    executar_ciclo()
