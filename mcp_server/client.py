"""Async client for the /api/v1/ REST service. This is the only thing the MCP server talks to."""
from typing import Optional

import httpx


class ApiError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, retry_after: int = 0, status: int = 0):
        super().__init__(message)
        self.code, self.message, self.retryable, self.retry_after, self.status = code, message, retryable, retry_after, status

    def as_dict(self) -> dict:
        body = {'code': self.code, 'message': self.message, 'retryable': self.retryable}
        if self.retry_after:
            body['retry_after'] = self.retry_after
        return body


class VideoDLClient:
    def __init__(self, base_url: str, api_key: str = '', timeout: float = 60, transport: Optional[httpx.AsyncBaseTransport] = None,
                 extra_headers: Optional[dict] = None):
        headers = {'User-Agent': 'videodl-mcp/1.0', **(extra_headers or {})}  # the API recognises this prefix as 'came through MCP'
        url = httpx.URL(base_url)
        if url.scheme == 'http' and url.host in ('127.0.0.1', 'localhost', '::1'):
            # Same-machine hop behind the TLS proxy: production Django redirects plain HTTP to HTTPS unless told the
            # outside connection was already secure (SECURE_PROXY_SSL_HEADER).
            headers.setdefault('X-Forwarded-Proto', 'https')
        if api_key:  # optional: without a key the API treats the caller as anonymous (free, limited per IP)
            headers['Authorization'] = f'Bearer {api_key}'
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport, headers=headers)

    async def aclose(self):
        await self._http.aclose()

    async def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError('upstream_unavailable', "The download service could not be reached. Try again shortly.", True, 30) from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400:
            err = body.get('error') if isinstance(body.get('error'), dict) else {}
            raise ApiError(err.get('code', 'upstream_error'), err.get('message', f"The service answered HTTP {response.status_code}."),
                           bool(err.get('retryable')), int(err.get('retry_after') or 0), response.status_code)
        return body

    async def platforms(self) -> dict:
        return await self._call('GET', '/api/v1/')

    async def info(self, url: str) -> dict:
        return await self._call('POST', '/api/v1/info', json={'url': url})

    async def create(self, url: str, quality: str, audio_only: bool) -> dict:
        return await self._call('POST', '/api/v1/downloads', json={'url': url, 'quality': quality, 'audio_only': audio_only})

    async def get(self, job_id: str) -> dict:
        return await self._call('GET', f'/api/v1/downloads/{job_id}')

    async def cancel(self, job_id: str) -> dict:
        return await self._call('DELETE', f'/api/v1/downloads/{job_id}')
