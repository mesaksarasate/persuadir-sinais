"""
Persuadir Sinais - Notificador
---------------------------------
Na V1, só imprime no console (CONSOLE). Quando quiser ligar ao
WhatsApp via BotConversa/Persuadir, implemente send_whatsapp() e
troque NOTIFY_CHANNEL="WHATSAPP" no config.py - o resto do sistema
não precisa mudar.
"""

import config
from signal_engine import Signal


def format_message(signal: Signal) -> str:
    emoji = {"COMPRA": "🟢", "VENDA": "🔴", "NEUTRO": "⚪"}[signal.action]
    linhas = [
        f"{emoji} *{signal.symbol}* — {signal.action}",
        f"Preço atual: {signal.price:.4f}",
        f"Confiança: {signal.confidence}%",
        f"Motivo: {signal.explanation}",
        "",
        "⚠️ Sinal informativo, não é execução automática nem recomendação de investimento.",
    ]
    return "\n".join(linhas)


def send_console(signal: Signal):
    print(format_message(signal))
    print("-" * 40)


def send_whatsapp(signal: Signal):
    """
    Placeholder para a integração futura com o BotConversa/Persuadir.
    Quando for implementar: reaproveitar a mesma rota/webhook que o
    Zac (agente de atendimento) já usa para disparar mensagens.
    """
    raise NotImplementedError(
        "Integração com WhatsApp ainda não implementada nesta V1. "
        "Use NOTIFY_CHANNEL='CONSOLE' por enquanto."
    )


def notify(signal: Signal):
    if signal.action == "NEUTRO":
        return  # Não precisa poluir o canal com "nada aconteceu"

    if config.NOTIFY_CHANNEL == "CONSOLE":
        send_console(signal)
    elif config.NOTIFY_CHANNEL == "WHATSAPP":
        send_whatsapp(signal)
    else:
        raise ValueError(f"Canal de notificação desconhecido: {config.NOTIFY_CHANNEL}")
