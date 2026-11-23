"""
Persuadir Sinais V2 - Motor de decisão (eficácia > eficiência)
-------------------------------------------------------------------
Duas camadas de proteção contra ruído, em cima do que já existia na V1:

1. CONFIRMAÇÃO MULTI-TIMEFRAME: o sinal só dispara quando a maioria
   dos intervalos de tempo observados (1m, 15m, 1h) concorda na
   direção. Um pico de 1 minuto que não é confirmado pelos intervalos
   maiores é tratado como ruído, não como sinal.

2. AUTOCALIBRAÇÃO: o sistema guarda se os sinais que emitiu no
   passado acertaram ou não a direção, e usa essa taxa de acerto REAL
   (por ativo) para ajustar a confiança informada. Se um ativo vem
   historicamente com taxa de acerto perto do acaso, o sistema passa
   a comunicar isso com confiança mais baixa, mesmo que o score bruto
   pareça forte - é o "aprender com os dados" aplicado aqui.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import numpy as np

import config
import indicators


@dataclass
class Signal:
    symbol: str
    action: str
    confidence: float
    price: float
    explanation: str
    raw_score: float
    timeframes_agree: int
    historical_accuracy: float | None


def _combined_score(ind: dict) -> float:
    return 0.5 * ind["momentum"] + 0.25 * ind["volume"] + 0.25 * ind["rsi"]


def _adaptive_threshold(score_history: list) -> float:
    if len(score_history) < 20:
        return 1.0
    std = float(np.std(score_history))
    return max(0.5, std * config.SIGNAL_SENSITIVITY)


def _multi_timeframe_score(ind_by_tf: dict) -> tuple[float, int, dict]:
    """
    Combina o score de cada timeframe com seu peso, e conta quantos
    timeframes concordam em direção com o resultado final.
    Retorna (score_ponderado, quantidade_que_concorda, scores_por_tf).
    """
    scores = {tf: _combined_score(ind) for tf, ind in ind_by_tf.items()}
    weighted = sum(scores[tf] * config.TIMEFRAMES[tf]["weight"] for tf in scores)

    if weighted == 0:
        agree = 0
    else:
        agree = sum(1 for tf, s in scores.items() if s * weighted > 0)

    return weighted, agree, scores


def _explain(ind_1m: dict, scores_by_tf: dict, agree: int, action: str, acc: dict) -> str:
    direction = "alta" if action == "COMPRA" else "baixa"
    parts = [
        f"Sinal de {action.lower()} - {agree} de {len(scores_by_tf)} intervalos de tempo "
        f"(1min, 15min, 1h) confirmam movimento de {direction}."
    ]
    if abs(ind_1m["volume"]) > 1.0:
        parts.append("Volume de negociação acima do normal reforça o sinal.")
    if acc["total"] >= 10 and acc["taxa"] is not None:
        parts.append(
            f"Nos últimos {acc['total']} sinais deste ativo, o sistema acertou a direção "
            f"em {acc['taxa']*100:.0f}% das vezes."
        )
    elif acc["total"] > 0:
        parts.append(
            f"Ainda coletando histórico de desempenho deste ativo ({acc['total']} sinais até agora)."
        )
    return " ".join(parts)


def _calibrate_confidence(raw_confidence: float, acc: dict) -> float:
    """
    Sem histórico suficiente (menos de 10 sinais resolvidos): usa a
    confiança bruta, mas limitada a 70% - o sistema ainda não provou
    nada sobre si mesmo nesse ativo.

    Com histórico: pondera a confiança bruta pela taxa de acerto real.
    Taxa de acerto de 50% (= acaso) derruba a confiança pela metade;
    taxa de 70%+ preserva ou reforça levemente.
    """
    if acc["total"] < 10 or acc["taxa"] is None:
        return min(raw_confidence, 70.0)

    fator = max(0.2, min(1.2, acc["taxa"] / 0.5 * 0.6))
    return round(min(95.0, raw_confidence * fator), 1)


def _resolve_pending(store, symbol: str, current_price: float, current_index_time):
    """
    Verifica sinais pendentes desse ativo que já passaram do horizonte
    de resolução e registra se a direção prevista se confirmou.
    """
    pending = store.get_pending_signals(symbol)
    for sig in pending:
        candles_passed = current_index_time - sig["emitted_at"]
        if candles_passed < config.RESOLUTION_HORIZON_CANDLES * 60:  # em segundos, 1m=60s
            continue
        subiu = current_price > sig["price_at_signal"]
        correct = (sig["action"] == "COMPRA" and subiu) or (sig["action"] == "VENDA" and not subiu)
        store.resolve_signal(symbol, sig["id"], correct)


def evaluate(store, symbol: str, ind_by_tf: dict, now_ts: float | None = None) -> Signal:
    now_ts = now_ts if now_ts is not None else time.time()
    ind_1m = ind_by_tf["1m"]

    # Resolve sinais antigos antes de emitir um novo (aprendizado contínuo)
    _resolve_pending(store, symbol, ind_1m["last_price"], now_ts)

    weighted_score, agree, scores_by_tf = _multi_timeframe_score(ind_by_tf)

    store.append_score(symbol, weighted_score)
    history = store.get_score_history(symbol)
    threshold = _adaptive_threshold(history)

    if weighted_score > threshold and agree >= config.MIN_TIMEFRAMES_AGREE:
        action = "COMPRA"
    elif weighted_score < -threshold and agree >= config.MIN_TIMEFRAMES_AGREE:
        action = "VENDA"
    else:
        action = "NEUTRO"

    acc = store.get_accuracy(symbol)

    if threshold > 0:
        raw_confidence = min(95.0, (abs(weighted_score) / threshold) * 50)
    else:
        raw_confidence = 0.0

    if action == "NEUTRO":
        explanation = (
            f"Sem confirmação suficiente agora "
            f"({agree} de {len(scores_by_tf)} intervalos concordam - precisa de {config.MIN_TIMEFRAMES_AGREE})."
        )
        confidence = 0.0
    else:
        confidence = _calibrate_confidence(raw_confidence, acc)
        explanation = _explain(ind_1m, scores_by_tf, agree, action, acc)
        store.save_pending_signal(symbol, {
            "id": str(uuid.uuid4()),
            "action": action,
            "price_at_signal": ind_1m["last_price"],
            "emitted_at": now_ts,
        })

    return Signal(
        symbol=symbol,
        action=action,
        confidence=confidence,
        price=ind_1m["last_price"],
        explanation=explanation,
        raw_score=round(weighted_score, 3),
        timeframes_agree=agree,
        historical_accuracy=acc["taxa"],
    )
