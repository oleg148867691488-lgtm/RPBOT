"""NETCLIENT.PY — один общий httpx-клиент на весь бот (переиспользует соединения)."""

import httpx

_client = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"User-Agent": "RPBOT/2.0"},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
