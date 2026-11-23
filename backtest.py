"""
Persuadir Sinais V2 - Backtest
----------------------------------
Mesma lógica de produção (signal_engine + confirmação multi-timeframe
+ autocalibração), rodada sobre histórico real, candle a candle, sem
olhar o futuro. Usa o LocalJSONStore (apagado a cada execução) para
não misturar dados de teste com produção.
"""

import os
import pandas as pd

import config
import indicators
import signal_engine
import state_store


def run_backtest(dfs_by_tf: dict, symbol: str, store) -> pd.DataFrame:
    """
    dfs_by_tf: {"1m": df_1m, "15m": df_15m, "1h": df_1h} com histórico
    completo de cada timeframe. Percorre o timeframe de 1m candle a
    candle, usando a janela de dados correspondente de cada timeframe
    disponível até aquele instante.
    """
    df_1m = dfs_by_tf["1m"]
    window = config.TIMEFRAMES["1m"]["limit"]
    results = []

    for i in range(window, len(df_1m)):
        ts = df_1m["timestamp"].iloc[i]

        ind_by_tf = {}
        for tf, df_tf in dfs_by_tf.items():
            slice_tf = df_tf[df_tf["timestamp"] <= ts].tail(config.TIMEFRAMES[tf]["limit"])
            if len(slice_tf) < 20:
                ind_by_tf = None
                break
            ind_by_tf[tf] = indicators.compute_indicators(slice_tf.reset_index(drop=True))

        if ind_by_tf is None:
            continue

        sig = signal_engine.evaluate(store, symbol, ind_by_tf, now_ts=ts.timestamp())
        results.append({
            "timestamp": ts,
            "price": sig.price,
            "action": sig.action,
            "confidence": sig.confidence,
            "agree": sig.timeframes_agree,
        })

    return pd.DataFrame(results)


def summarize(results: pd.DataFrame) -> dict:
    sinais = results[results["action"] != "NEUTRO"].copy()
    if sinais.empty:
        return {"total_sinais": 0}

    precos = results["price"].values
    acertos = 0
    avaliados = 0
    for idx in sinais.index:
        if idx + config.RESOLUTION_HORIZON_CANDLES >= len(precos):
            continue
        avaliados += 1
        preco_no_sinal = precos[idx]
        preco_depois = precos[idx + config.RESOLUTION_HORIZON_CANDLES]
        subiu = preco_depois > preco_no_sinal
        if (sinais.loc[idx, "action"] == "COMPRA" and subiu) or \
           (sinais.loc[idx, "action"] == "VENDA" and not subiu):
            acertos += 1

    return {
        "total_sinais": len(sinais),
        "sinais_compra": int((sinais["action"] == "COMPRA").sum()),
        "sinais_venda": int((sinais["action"] == "VENDA").sum()),
        "avaliados_5_candles_depois": avaliados,
        "acertos_direcao": acertos,
        "taxa_acerto_direcao_%": round(100 * acertos / avaliados, 1) if avaliados else None,
    }


if __name__ == "__main__":
    import data_feed

    state_path = "backtest_state.json"
    if os.path.exists(state_path):
        os.remove(state_path)
    store = state_store.LocalJSONStore(state_path)

    exchange = data_feed.get_exchange(config.EXCHANGE_ID)
    for symbol in config.SYMBOLS:
        print(f"\n=== Backtest V2: {symbol} ===")
        try:
            dfs_by_tf = {
                tf: data_feed.fetch_candles(exchange, symbol, tf, params["limit"] * 4)
                for tf, params in config.TIMEFRAMES.items()
            }
        except Exception as exc:
            print(f"Não foi possível buscar histórico de {symbol}: {exc}")
            continue

        results = run_backtest(dfs_by_tf, symbol, store)
        resumo = summarize(results)
        for k, v in resumo.items():
            print(f"{k}: {v}")
