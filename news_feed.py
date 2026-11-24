"""
Persuadir Sinais - Notícias
---------------------------------
Busca manchetes recentes do mercado cripto numa fonte pública e
gratuita (feed RSS do CoinDesk), sem precisar de conta nem chave de
API. Usado só para exibir uma lista informativa ao usuário - não
decide nada sozinho no sinal (essa parte, de ajustar a confiança com
base no contexto, é uma camada separada, a ser somada depois).
"""

import xml.etree.ElementTree as ET

import requests

RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"


def fetch_latest_news(limit: int = 6) -> list | None:
    """
    Retorna uma lista de até `limit` notícias, cada uma como
    {"title": ..., "url": ..., "published": ...}, ou None se a busca
    falhar (nunca derruba o ciclo principal por causa disso).
    """
    try:
        resp = requests.get(RSS_URL, timeout=10, headers={"User-Agent": "PersuadirSinais/1.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            items.append({"title": title, "url": link, "published": pub_date})

        return items or None
    except Exception as exc:
        print(f"[news_feed] Erro ao buscar notícias: {exc}")
        return None
