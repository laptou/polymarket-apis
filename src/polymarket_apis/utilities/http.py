"""
dual-mode http client wrapper for sync and async operations.
enables easy parallelization of api calls via asyncio.gather().
"""

from typing import Any, TypeVar

import httpx

T = TypeVar("T")


class DualHttpClient:
    """
    wrapper around httpx that provides both sync and async http methods.
    use sync methods for simple scripts, async methods for concurrent requests.
    """

    def __init__(self, timeout: float = 30.0):
        self._sync = httpx.Client(http2=True, timeout=timeout)
        self._async = httpx.AsyncClient(http2=True, timeout=timeout)

    # sync methods
    def get(self, url: str, **kwargs) -> httpx.Response:
        return self._sync.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self._sync.post(url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        return self._sync.delete(url, **kwargs)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        return self._sync.request(method, url, **kwargs)

    def stream(self, method: str, url: str, **kwargs):
        return self._sync.stream(method, url, **kwargs)

    # async methods
    async def aget(self, url: str, **kwargs) -> httpx.Response:
        return await self._async.get(url, **kwargs)

    async def apost(self, url: str, **kwargs) -> httpx.Response:
        return await self._async.post(url, **kwargs)

    async def adelete(self, url: str, **kwargs) -> httpx.Response:
        return await self._async.delete(url, **kwargs)

    async def arequest(self, method: str, url: str, **kwargs) -> httpx.Response:
        return await self._async.request(method, url, **kwargs)

    def close(self):
        self._sync.close()

    async def aclose(self):
        await self._async.aclose()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()
        await self.aclose()
