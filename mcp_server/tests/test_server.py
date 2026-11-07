"""
MCP server tests. The REST service is replaced by httpx.MockTransport, and a real MCP client talks to the
server in memory, so the full tool-call path (schemas, structured output, isError) is exercised.
Run from the project root:  python -m unittest discover -s mcp_server/tests -t .
"""
import asyncio
import json
import unittest

try:
    import httpx
    from mcp.client import Client
except ImportError:  # the website does not need the MCP packages (see mcp_server/requirements.txt)
    raise unittest.SkipTest('mcp / httpx are not installed')

from mcp_server import config, server as srv
from mcp_server.client import ApiError, VideoDLClient

DONE = {'id': 'job-1', 'status': 'done', 'progress': 100, 'url': 'https://youtu.be/x', 'title': 'Clip', 'quality': '720p MP4',
        'result': {'download_url': 'https://files.example/d/tok', 'expires_at': '2026-01-01T00:00:00+00:00', 'filename': 'Clip.mp4',
                   'mime_type': 'video/mp4', 'size_bytes': 2 * 1024 * 1024}}


def run(coro):
    return asyncio.run(coro)


class Fake:
    """Scripted REST service. `routes` maps (method, path) to a list of (status, body) answered in turn (last one repeats)."""

    def __init__(self, routes):
        self.routes, self.requests = routes, []

    def handler(self, request: httpx.Request):
        self.requests.append(request)
        queue = self.routes[(request.method, request.url.path)]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, json=body)

    def factory(self, key, headers=None):
        return VideoDLClient('http://api.test', key, transport=httpx.MockTransport(self.handler), extra_headers=headers)


class McpServerTests(unittest.TestCase):
    def setUp(self):
        config.POLL_SECONDS = 0.01

    def call(self, fake, tool, args, key='vd_test'):
        server = srv.build_server(default_key=key, client_factory=fake.factory)

        async def go():
            async with Client(server) as client:
                return await client.call_tool(tool, args)
        return run(go())

    def test_lists_four_tools_with_annotations(self):
        server = srv.build_server(client_factory=Fake({}).factory)

        async def go():
            async with Client(server) as client:
                return (await client.list_tools()).tools
        tools = {t.name: t for t in run(go())}
        self.assertEqual(set(tools), {'get_video_info', 'download_video', 'get_download_status', 'cancel_download'})
        self.assertTrue(tools['get_video_info'].annotations.read_only_hint)
        self.assertFalse(tools['download_video'].annotations.read_only_hint)
        self.assertIn('url', tools['download_video'].input_schema['properties'])

    def test_download_waits_then_returns_the_link(self):
        fake = Fake({('POST', '/api/v1/downloads'): [(202, {**DONE, 'status': 'queued', 'progress': 0, 'result': None})],
                     ('GET', '/api/v1/downloads/job-1'): [(200, {**DONE, 'status': 'downloading', 'progress': 40}), (200, DONE)]})
        result = self.call(fake, 'download_video', {'url': 'https://youtu.be/x', 'quality': '720'})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content['result']['download_url'], 'https://files.example/d/tok')
        self.assertIn('https://files.example/d/tok', result.content[0].text)
        self.assertEqual(json.loads(fake.requests[0].content), {'url': 'https://youtu.be/x', 'quality': '720', 'audio_only': False})

    def test_slow_download_returns_a_job_id_to_poll(self):
        busy = {**DONE, 'status': 'downloading', 'progress': 10, 'result': None}
        fake = Fake({('POST', '/api/v1/downloads'): [(202, busy)], ('GET', '/api/v1/downloads/job-1'): [(200, busy)]})
        result = self.call(fake, 'download_video', {'url': 'https://youtu.be/x', 'wait_seconds': 0})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content['status'], 'downloading')
        self.assertIn('get_download_status', result.content[0].text)
        self.assertIn('job-1', result.content[0].text)

    def test_api_errors_become_tool_errors_with_codes(self):
        err = {'error': {'code': 'quota_exceeded', 'message': 'Daily quota reached.', 'retryable': True, 'retry_after': 3600}}
        fake = Fake({('POST', '/api/v1/downloads'): [(429, err)]})
        result = self.call(fake, 'download_video', {'url': 'https://youtu.be/x'})
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content['error']['code'], 'quota_exceeded')
        self.assertTrue(result.structured_content['error']['retryable'])
        self.assertIn('quota_exceeded', result.content[0].text)

    def test_failed_job_is_a_tool_error(self):
        failed = {**DONE, 'status': 'failed', 'result': None, 'error': {'code': 'private', 'message': 'Private video.', 'retryable': False}}
        fake = Fake({('GET', '/api/v1/downloads/job-1'): [(200, failed)]})
        result = self.call(fake, 'get_download_status', {'job_id': 'job-1', 'wait_seconds': 0})
        self.assertTrue(result.is_error)
        self.assertIn('private', result.content[0].text)

    def test_service_down(self):
        def boom(request):
            raise httpx.ConnectError('refused')
        server = srv.build_server(client_factory=lambda key, headers=None: VideoDLClient('http://api.test', key, transport=httpx.MockTransport(boom)))

        async def go():
            async with Client(server) as client:
                return await client.call_tool('get_video_info', {'url': 'https://youtu.be/x'})
        result = run(go())
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content['error']['code'], 'upstream_unavailable')

    def test_the_default_key_is_forwarded_as_bearer(self):
        info = {'title': 'T', 'uploader': '', 'platform': 'YouTube', 'duration_seconds': 5,
                'qualities': [{'id': '720', 'label': '720p', 'size_bytes': 3 * 1024 * 1024}], 'downloadable': True}
        fake = Fake({('POST', '/api/v1/info'): [(200, info)]})
        result = self.call(fake, 'get_video_info', {'url': 'https://youtu.be/x'}, key='vd_mine')
        self.assertFalse(result.is_error)
        self.assertEqual(fake.requests[0].headers['authorization'], 'Bearer vd_mine')
        self.assertIn('720: 720p (~3.0 MB)', result.content[0].text)

    def test_the_api_can_tell_the_call_came_through_mcp_and_each_call_is_logged(self):
        fake = Fake({('GET', '/api/v1/downloads/job-1'): [(200, DONE)]})
        with self.assertLogs('videodl.mcp', 'INFO') as logs:
            self.call(fake, 'get_download_status', {'job_id': 'job-1', 'wait_seconds': 0}, key='vd_x')
        self.assertTrue(fake.requests[0].headers['user-agent'].startswith('videodl-mcp'))
        self.assertIn('x-mcp-client', fake.requests[0].headers)
        line = logs.output[0]
        self.assertIn('tool=get_download_status', line)
        self.assertIn('outcome=ok', line)
        self.assertIn('keyed=yes', line)
        self.assertNotIn('vd_x', line)  # secrets and URLs never go into the log

    def test_failed_calls_are_logged_with_the_error_code(self):
        err = {'error': {'code': 'quota_exceeded', 'message': 'x', 'retryable': True}}
        fake = Fake({('POST', '/api/v1/downloads'): [(429, err)]})
        with self.assertLogs('videodl.mcp', 'INFO') as logs:
            self.call(fake, 'download_video', {'url': 'https://youtu.be/secret-video'}, key='')
        self.assertIn('outcome=error:quota_exceeded', logs.output[0])
        self.assertIn('keyed=no', logs.output[0])
        self.assertNotIn('secret-video', logs.output[0])

    def test_cancel(self):
        fake = Fake({('DELETE', '/api/v1/downloads/job-1'): [(200, {**DONE, 'status': 'cancelled', 'cancelled': True, 'result': None})]})
        result = self.call(fake, 'cancel_download', {'job_id': 'job-1'})
        self.assertFalse(result.is_error)
        self.assertIn('cancelled', result.content[0].text)

    def test_resources(self):
        fake = Fake({('GET', '/api/v1/'): [(200, {'platforms': ['YouTube'], 'limits': {'max_duration_seconds': 3600}})]})
        server = srv.build_server(client_factory=fake.factory)

        async def go():
            async with Client(server) as client:
                listed = {str(r.uri) for r in (await client.list_resources()).resources}
                plat = await client.read_resource('videodl://platforms')
                qual = await client.read_resource('videodl://quality-options')
                return listed, plat, qual
        listed, plat, qual = run(go())
        self.assertEqual(listed, {'videodl://platforms', 'videodl://quality-options'})
        self.assertIn('YouTube', plat.contents[0].text)
        self.assertIn('audio:mp3:192', qual.contents[0].text)

    def test_no_key_means_an_anonymous_call_with_no_auth_header(self):
        fake = Fake({('GET', '/api/v1/downloads/job-1'): [(200, DONE)]})
        result = self.call(fake, 'get_download_status', {'job_id': 'job-1', 'wait_seconds': 0}, key='')
        self.assertFalse(result.is_error)
        self.assertNotIn('authorization', fake.requests[0].headers)

    def test_client_address_headers(self):
        from types import SimpleNamespace as NS

        def ctx(headers, host=None):
            return NS(headers=headers, request_context=NS(request=NS(client=NS(host=host) if host else None)))
        trusted = {'x-forwarded-for': '203.0.113.5', 'cf-connecting-ip': '203.0.113.5'}
        # behind a proxy we run: believe what it set
        self.assertEqual(srv._client_address_headers(ctx(trusted, '10.0.0.2'), True),
                         {'X-Forwarded-For': '203.0.113.5', 'CF-Connecting-IP': '203.0.113.5'})
        # directly exposed: ignore claimed headers (spoofable) and use the real peer address
        self.assertEqual(srv._client_address_headers(ctx(trusted, '198.51.100.8'), False), {'X-Forwarded-For': '198.51.100.8'})
        # trusted proxy but no headers: fall back to the peer
        self.assertEqual(srv._client_address_headers(ctx({}, '198.51.100.8'), True), {'X-Forwarded-For': '198.51.100.8'})
        # stdio / in-memory: nothing to forward
        self.assertEqual(srv._client_address_headers(ctx(None), True), {})

    def test_transport_security_turns_on_with_hosts(self):
        self.assertFalse(srv.transport_security([], []).enable_dns_rebinding_protection)
        self.assertTrue(srv.transport_security(['mcp.example.com'], []).enable_dns_rebinding_protection)


class ClientTests(unittest.TestCase):
    def sent_headers(self, base_url):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json={})
        run(VideoDLClient(base_url, '', transport=httpx.MockTransport(handler)).platforms())
        return seen

    def test_loopback_hop_declares_the_outside_connection_secure(self):
        self.assertEqual(self.sent_headers('http://127.0.0.1:8000')['x-forwarded-proto'], 'https')
        self.assertEqual(self.sent_headers('http://localhost:8000')['x-forwarded-proto'], 'https')

    def test_other_targets_are_left_alone(self):
        self.assertNotIn('x-forwarded-proto', self.sent_headers('https://api.example.com'))
        self.assertNotIn('x-forwarded-proto', self.sent_headers('http://api.internal:8000'))

    def test_non_json_error_page_is_handled(self):
        client = VideoDLClient('http://api.test', 'k', transport=httpx.MockTransport(lambda r: httpx.Response(502, text='<html>bad gateway')))
        with self.assertRaises(ApiError) as ctx:
            run(client.info('https://youtu.be/x'))
        self.assertEqual((ctx.exception.code, ctx.exception.status), ('upstream_error', 502))


if __name__ == '__main__':
    unittest.main()
