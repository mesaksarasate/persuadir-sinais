"""
Persuadir Sinais — notificações push (Web Push)
------------------------------------------------
Dispara uma notificação real do navegador (com som do aparelho) sempre que
um novo sinal de COMPRA/VENDA é emitido, mesmo com o app fechado ou em
segundo plano. Usa o protocolo Web Push padrão (VAPID), sem nenhum serviço
pago: o próprio navegador/SO entrega a notificação.

As inscrições (PushSubscription) ficam guardadas na mesma Cloudflare KV que
já armazena os sinais, sob a chave "push:<usuario>:<hash>". Este módulo só
lê essas inscrições — quem as grava é o Worker (endpoint /subscribe).

Variáveis de ambiente necessárias (GitHub Actions Secrets):
  CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID, CF_API_TOKEN  -> já usadas por state_store.py
  VAPID_PRIVATE_KEY                                 -> chave privada VAPID (base64url)
  VAPID_CLAIMS_EMAIL                                -> ex.: "mailto:contato@persuadir.app"

Qualquer falha aqui é silenciosa (best-effort): nunca deve derrubar o
pipeline principal de cálculo de sinais.
"""

import os
import json
import requests

try:
    from pywebpush import webpush, WebPushException
except ImportError:  # biblioteca ausente não deve quebrar o pipeline
    webpush = None
    WebPushException = Exception


def _kv_base_url():
    account_id = os.environ["CF_ACCOUNT_ID"]
    namespace_id = os.environ["CF_KV_NAMESPACE_ID"]
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}"


def _kv_headers():
    return {"Authorization": "Bearer " + os.environ["CF_API_TOKEN"]}


def _list_push_keys():
    url = _kv_base_url() + "/keys"
    resp = requests.get(url, headers=_kv_headers(), params={"prefix": "push:"}, timeout=10)
    resp.raise_for_status()
    return [item["name"] for item in resp.json().get("result", [])]


def _get_kv_value(key):
    url = _kv_base_url() + "/values/" + key
    resp = requests.get(url, headers=_kv_headers(), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _delete_kv_key(key):
    url = _kv_base_url() + "/values/" + key
    requests.delete(url, headers=_kv_headers(), timeout=10)


def _format_push_message(signal):
    emoji = "🟢" if signal.action == "COMPRA" else "🔴"
    title = f"{emoji} {signal.action} · {signal.symbol.replace('_', '/')}"
    body = f"Preço: ${signal.price:,.2f} · confiança {signal.confidence:.0%}"
    return title, body


def send_push(signal):
    """Envia a notificação para todas as inscrições guardadas. Melhor-esforço:
    nunca lança exceção para fora — qualquer problema só é logado no console."""
    if webpush is None:
        print("Persuadir Sinais — pywebpush não instalado; pulando notificação push.")
        return
    if signal.action not in ("COMPRA", "VENDA"):
        return

    try:
        private_key = os.environ["VAPID_PRIVATE_KEY"]
        claims_email = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:contato@persuadir.app")
    except KeyError:
        print("Persuadir Sinais — VAPID_PRIVATE_KEY não configurada; pulando notificação push.")
        return

    try:
        keys = _list_push_keys()
    except Exception as e:
        print(f"Persuadir Sinais — falha ao listar inscrições push: {e}")
        return

    title, body = _format_push_message(signal)
    payload = json.dumps({
        "title": title,
        "body": body,
        "tag": "persuadir-sinais-" + signal.symbol,
        "url": "./",
    })

    for key in keys:
        try:
            record = _get_kv_value(key)
            if not record:
                continue
            subscription_info = record.get("subscription")
            if not subscription_info:
                continue

            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": claims_email},
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # Inscrição morta (usuário desinstalou/revogou) — limpamos.
                _delete_kv_key(key)
            else:
                print(f"Persuadir Sinais — falha ao enviar push ({key}): {e}")
        except Exception as e:
            print(f"Persuadir Sinais — erro inesperado ao enviar push ({key}): {e}")
