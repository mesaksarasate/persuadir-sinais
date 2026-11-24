"""
Persuadir Sinais V4 - Memória persistente (sem cartão)
-----------------------------------------------------------
Mesma interface da V3 (StateStore), três backends possíveis:

  - LocalJSONStore: arquivo local, para teste/backtest
  - FirestoreStore: mantido para quem optar pelo Google Cloud depois
  - CloudflareKVStore: produção na stack sem cartão (GitHub Actions +
    Cloudflare Workers KV). Não roda nenhuma lógica na Cloudflare -
    usa só a API REST dela como um "banco de dados" simples de
    chave/valor, acessado por chamadas HTTP comuns.

NOVIDADE NESTA VERSÃO (V4): o backend de produção (CloudflareKVStore)
deixou de gravar um registro por ativo a cada chamada (score, sinais
pendentes e acurácia eram 3 gravações separadas, por ativo, por
ciclo - podendo passar de 2.000 gravações/dia e estourar o limite
gratuito da Cloudflare, que é de 1.000/dia). Agora ele mantém tudo em
memória durante o ciclo e grava **um único registro, com todos os
ativos juntos, uma única vez por ciclo** - load_all() no início,
flush_all() no fim. Isso derruba o consumo para ~240 gravações/dia
(a cada 6 minutos), deixando folga de sobra para notícias e outras
funcionalidades futuras, sem custar nada a mais.

A escolha do backend é automática por variável de ambiente - o resto
do sistema (signal_engine.py) não muda nadinha entre as três.
"""

import json
import os
from abc import ABC, abstractmethod

import requests

# Chave única na KV onde TODOS os ativos ficam guardados juntos.
COMBINED_KEY = "sinais_estado"
# Chave única onde as notícias ficam guardadas.
NEWS_KEY = "noticias"

EMPTY_SYMBOL_RECORD = {"score_history": [], "pending_signals": [], "accuracy": {"acertos": 0, "total": 0}}


class StateStore(ABC):
    @abstractmethod
    def get_score_history(self, symbol: str) -> list: ...

    @abstractmethod
    def append_score(self, symbol: str, score: float, max_len: int = 200): ...

    @abstractmethod
    def save_pending_signal(self, symbol: str, signal_dict: dict): ...

    @abstractmethod
    def get_pending_signals(self, symbol: str) -> list: ...

    @abstractmethod
    def resolve_signal(self, symbol: str, signal_id: str, correct: bool): ...

    @abstractmethod
    def get_accuracy(self, symbol: str) -> dict: ...

    def load_all(self):
        """Carrega o estado de todos os ativos de uma vez, antes do ciclo.
        Backends que não precisam (ex.: arquivo local) deixam como no-op."""
        pass

    def flush_all(self):
        """Grava o estado de todos os ativos de uma vez, ao fim do ciclo.
        Backends que não precisam (ex.: arquivo local) deixam como no-op."""
        pass

    def save_news(self, items: list):
        """Guarda a lista de notícias mais recentes. Default: no-op —
        só o CloudflareKVStore implementa de fato (é o backend de produção)."""
        pass

    def get_news(self) -> list:
        return []


class LocalJSONStore(StateStore):
    """Backend em arquivo, para teste e backtest local - sem rede."""

    def __init__(self, path: str = "persuadir_sinais_state.json"):
        self.path = path
        if not os.path.exists(path):
            self._write({"score_history": {}, "pending_signals": {}, "accuracy": {}, "noticias": []})

    def _read(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data: dict):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def get_score_history(self, symbol: str) -> list:
        return self._read()["score_history"].get(symbol, [])

    def append_score(self, symbol: str, score: float, max_len: int = 200):
        data = self._read()
        hist = data["score_history"].setdefault(symbol, [])
        hist.append(score)
        data["score_history"][symbol] = hist[-max_len:]
        self._write(data)

    def save_pending_signal(self, symbol: str, signal_dict: dict):
        data = self._read()
        pending = data["pending_signals"].setdefault(symbol, [])
        pending.append(signal_dict)
        data["pending_signals"][symbol] = pending
        self._write(data)

    def get_pending_signals(self, symbol: str) -> list:
        return self._read()["pending_signals"].get(symbol, [])

    def resolve_signal(self, symbol: str, signal_id: str, correct: bool):
        data = self._read()
        pending = data["pending_signals"].get(symbol, [])
        data["pending_signals"][symbol] = [s for s in pending if s["id"] != signal_id]
        acc = data["accuracy"].setdefault(symbol, {"acertos": 0, "total": 0})
        acc["total"] += 1
        if correct:
            acc["acertos"] += 1
        self._write(data)

    def get_accuracy(self, symbol: str) -> dict:
        acc = self._read()["accuracy"].get(symbol, {"acertos": 0, "total": 0})
        taxa = (acc["acertos"] / acc["total"]) if acc["total"] > 0 else None
        return {**acc, "taxa": taxa}

    def save_news(self, items: list):
        data = self._read()
        data["noticias"] = items
        self._write(data)

    def get_news(self) -> list:
        return self._read().get("noticias", [])


class CloudflareKVStore(StateStore):
    """
    Backend de produção na stack sem cartão. Guarda TODOS os ativos num
    único registro (chave COMBINED_KEY) na Cloudflare KV, carregado uma
    vez no início do ciclo (load_all) e regravado uma única vez no fim
    (flush_all) - assim o ciclo inteiro custa 1 gravação, não uma por
    ativo nem uma por operação.

    Precisa de três variáveis de ambiente (vêm dos Secrets do GitHub
    Actions, nunca hardcoded):
      CF_ACCOUNT_ID   - ID da conta Cloudflare
      CF_KV_NAMESPACE_ID - ID do namespace do KV criado para o projeto
      CF_API_TOKEN    - token com permissão de leitura/escrita nesse KV
    """

    def __init__(self):
        self.account_id = os.environ["CF_ACCOUNT_ID"]
        self.namespace_id = os.environ["CF_KV_NAMESPACE_ID"]
        self.token = os.environ["CF_API_TOKEN"]
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/storage/kv/namespaces/{self.namespace_id}/values"
        )
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self._cache = None          # dict completo, carregado por load_all()
        self._dirty = False         # True se algo mudou e precisa gravar no flush_all()
        self._news_dirty = None     # lista de notícias pendente de gravação, ou None

    # ---------- Infraestrutura interna (KV bruta) ----------

    def _get(self, key: str):
        resp = requests.get(f"{self.base_url}/{key}", headers=self.headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def _put(self, key: str, value):
        resp = requests.put(
            f"{self.base_url}/{key}",
            headers=self.headers,
            data=json.dumps(value),
            timeout=10,
        )
        resp.raise_for_status()

    def _ensure_loaded(self):
        if self._cache is None:
            self.load_all()

    def _record(self, symbol: str) -> dict:
        self._ensure_loaded()
        key = symbol.replace("/", "_")
        if key not in self._cache:
            self._cache[key] = {
                "score_history": [],
                "pending_signals": [],
                "accuracy": {"acertos": 0, "total": 0},
            }
        return self._cache[key]

    # ---------- Ciclo de vida (1 leitura e 1 gravação por ciclo) ----------

    def load_all(self):
        data = self._get(COMBINED_KEY)
        self._cache = data if isinstance(data, dict) else {}
        self._dirty = False

    def flush_all(self):
        if self._cache is not None and self._dirty:
            self._put(COMBINED_KEY, self._cache)
            self._dirty = False
        if self._news_dirty is not None:
            self._put(NEWS_KEY, self._news_dirty)
            self._news_dirty = None

    # ---------- Interface StateStore ----------

    def get_score_history(self, symbol: str) -> list:
        return self._record(symbol)["score_history"]

    def append_score(self, symbol: str, score: float, max_len: int = 200):
        record = self._record(symbol)
        record["score_history"].append(score)
        record["score_history"] = record["score_history"][-max_len:]
        self._dirty = True

    def save_pending_signal(self, symbol: str, signal_dict: dict):
        record = self._record(symbol)
        record["pending_signals"].append(signal_dict)
        self._dirty = True

    def get_pending_signals(self, symbol: str) -> list:
        return self._record(symbol)["pending_signals"]

    def resolve_signal(self, symbol: str, signal_id: str, correct: bool):
        record = self._record(symbol)
        record["pending_signals"] = [s for s in record["pending_signals"] if s["id"] != signal_id]
        record["accuracy"]["total"] += 1
        if correct:
            record["accuracy"]["acertos"] += 1
        self._dirty = True

    def get_accuracy(self, symbol: str) -> dict:
        acc = self._record(symbol)["accuracy"]
        taxa = (acc["acertos"] / acc["total"]) if acc.get("total", 0) > 0 else None
        return {**acc, "taxa": taxa}

    def save_news(self, items: list):
        self._news_dirty = items

    def get_news(self) -> list:
        data = self._get(NEWS_KEY)
        return data if isinstance(data, list) else []


def get_store() -> StateStore:
    """
    Produção (GitHub Actions): usa Cloudflare KV se as variáveis de
    ambiente estiverem presentes. Caso contrário (teste/backtest
    local): arquivo local - sem precisar mudar nada no resto do código.
    """
    if os.environ.get("CF_ACCOUNT_ID"):
        return CloudflareKVStore()
    return LocalJSONStore()
