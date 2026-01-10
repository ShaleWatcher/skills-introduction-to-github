from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def _ts_ms() -> str:
    return str(int(time.time() * 1000))


def load_private_key_pem(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())


def sign_request(*, private_key, timestamp_ms: str, method: str, path: str) -> str:
    """
    Per Kalshi docs:
      message = timestamp + METHOD + path_without_query
      signature = RSA-PSS(SHA256), base64-encoded
    """

    path_wo_query = path.split("?", 1)[0]
    msg = f"{timestamp_ms}{method.upper()}{path_wo_query}".encode("utf-8")
    sig = private_key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("utf-8")


@dataclass(frozen=True, slots=True)
class KalshiAuth:
    key_id: str
    private_key_path: str
    base_url: str  # e.g. https://api.kalshi.com or https://demo-api.kalshi.co

    @staticmethod
    def from_env() -> Optional["KalshiAuth"]:
        key_id = os.environ.get("KALSHI_ACCESS_KEY", "").strip()
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
        base_url = os.environ.get("KALSHI_TRADE_BASE_URL", "https://api.kalshi.com").strip()
        if not key_id or not key_path:
            return None
        return KalshiAuth(key_id=key_id, private_key_path=key_path, base_url=base_url.rstrip("/"))


class KalshiClient:
    def __init__(self, auth: KalshiAuth):
        self._auth = auth
        self._pk = load_private_key_pem(auth.private_key_path)

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        ts = _ts_ms()
        signature = sign_request(private_key=self._pk, timestamp_ms=ts, method=method, path=path)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self._auth.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self._auth.base_url}{path}",
            method=method.upper(),
            headers=headers,
            data=data,
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    def batch_create_orders(self, orders: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", "/trade-api/v2/portfolio/orders/batched", body={"orders": orders})

