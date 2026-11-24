"""
Persuadir Sinais V4 - Ponto de entrada (GitHub Actions)
------------------------------------------------------------
Rodado pelo workflow do GitHub Actions, acionado por um evento
repository_dispatch (disparado pelo cron-job.org a cada 6 minutos) -
não pelo agendador `schedule:` do próprio GitHub, para não cair nas
limitações de frequência e no desligamento automático por inatividade.

Também pode ser rodado localmente, chamando `python main.py` direto -
útil para testar sem precisar do GitHub Actions.

NOVIDADE NESTA VERSÃO (V4):
- store.load_all() / store.flush_all(): o estado de todos os ativos é
  carregado uma vez no início do ciclo e gravado uma única vez no
  fim - uma gravação na KV por ciclo, em vez de várias por ativo.
- Busca de notícias (a cada NEWS_REFRESH_MINUTES, não a cada ciclo),
  guardada à parte, para exibição informativa no app.
"""

import time

import config
import data_feed
import indicators
import news_feed
import notifier
import signal_engine
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


def deve_atualizar_noticias() -> bool:
    """
    Notícias mudam bem mais devagar que preço - não precisa buscar a
    cada ciclo de 6 minutos. Busca só na primeira "janela" de cada
    bloco de NEWS_REFRESH_MINUTES, sem precisar guardar nenhum estado
    extra pra isso.
    """
    minuto_do_dia = int(time.time() // 60)
    return (minuto_do_dia % config.NEWS_REFRESH_MINUTES) < 6


def atualizar_noticias(store):
    try:
        itens = news_feed.fetch_latest_news(limit=config.NEWS_ITEMS_LIMIT)
        if itens is not None:
            store.save_news(itens)
    except Exception as exc:
        print(f"[main] Erro ao atualizar notícias: {exc}")


def executar_ciclo():
    exchange = data_feed.get_exchange(config.EXCHANGE_ID)
    store = state_store.get_store()
    store.load_all()

    try:
        for symbol in config.SYMBOLS:
            try:
                processar_simbolo(exchange, store, symbol)
            except Exception as exc:
                print(f"[main] Erro processando {symbol}: {exc}")

        if deve_atualizar_noticias():
            atualizar_noticias(store)
    finally:
        # Sempre grava o que foi acumulado até aqui, mesmo se algum
        # símbolo específico tiver falhado no meio do caminho.
        store.flush_all()


if __name__ == "__main__":
    executar_ciclo()
