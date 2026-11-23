"""
Persuadir Sinais V3 - Memória persistente (sem cartão)
-----------------------------------------------------------
Mesma interface da V2 (StateStore), três backends possíveis:

  - LocalJSONStore: arquivo local, para teste/backtest
  - FirestoreStore: mantido para quem optar pelo Google Cloud depois
  - CloudflareKVStore: produção na stack sem cartão (GitHub Actions +
    Cloudflare Workers KV). Não roda nenhuma lógica na Cloudflare -
    usa só a API REST dela como um "banco de dados" simples de
    chave/valor, acessado por chamadas HTTP comuns.

A escolha do backend é automática por variável de ambiente - o resto
do sistema (signal_engine.py) não muda nadinha entre as três.
"""

import json
import os
import time
from abc import ABC, abstractmethod

import requests


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


class LocalJSONStore(StateStore):
    """Backend em arquivo, para teste e backtest local - sem rede."""

    def __init__(self, path: str = "persuadir_sinais_state.json"):
        self.path = path
        if not os.path.exists(path):
            self._write({"score_history": {}, "pending_signals": {}, "accuracy": {}})

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


class CloudflareKVStore(StateStore):
    """
    Backend de produção na stack sem cartão. Guarda TUDO (histórico de
    score, sinais pendentes, acurácia) em UM único registro por
    símbolo no Cloudflare KV, lido e regravado a cada chamada - o
    volume de dados é pequeno o bastante para isso ser suficiente
    (nunca mais que algumas centenas de números por ativo).

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

    def _key(self, symbol: str) -> str:
        return symbol.replace("/", "_")

    def _read_record(self, symbol: str) -> dict:
        resp = requests.get(f"{self.base_url}/{self._key(symbol)}", headers=self.headers, timeout=10)
        if resp.status_code == 404:
            return {"score_history": [], "pending_signals": [], "accuracy": {"acertos": 0, "total": 0}}
        resp.raise_for_status()
        return resp.json()

    def _write_record(self, symbol: str, record: dict):
        resp = requests.put(
            f"{self.base_url}/{self._key(symbol)}",
            headers=self.headers,
            data=json.dumps(record),
            timeout=10,
        )
        resp.raise_for_status()

    def get_score_history(self, symbol: str) -> list:
        return self._read_record(symbol)["score_history"]

    def append_score(self, symbol: str, score: float, max_len: int = 200):
        record = self._read_record(symbol)
        record["score_history"].append(score)
        record["score_history"] = record["score_history"][-max_len:]
        self._write_record(symbol, record)

    def save_pending_signal(self, symbol: str, signal_dict: dict):
        record = self._read_record(symbol)
        record["pending_signals"].append(signal_dict)
        self._write_record(symbol, record)

    def get_pending_signals(self, symbol: str) -> list:
        return self._read_record(symbol)["pending_signals"]

    def resolve_signal(self, symbol: str, signal_id: str, correct: bool):
        record = self._read_record(symbol)
        record["pending_signals"] = [s for s in record["pending_signals"] if s["id"] != signal_id]
        record["accuracy"]["total"] += 1
        if correct:
            record["accuracy"]["acertos"] += 1
        self._write_record(symbol, record)

    def get_accuracy(self, symbol: str) -> dict:
        acc = self._read_record(symbol)["accuracy"]
        taxa = (acc["acertos"] / acc["total"]) if acc.get("total", 0) > 0 else None
        return {**acc, "taxa": taxa}


def get_store() -> StateStore:
    """
    Produção (GitHub Actions): usa Cloudflare KV se as variáveis de
    ambiente estiverem presentes. Caso contrário (teste/backtest
    local): arquivo local - sem precisar mudar nada no resto do código.
    """
    if os.environ.get("CF_ACCOUNT_ID"):
        return CloudflareKVStore()
    return LocalJSONStore()
