"""Settings come from the environment so the same image runs anywhere (no Django needed in this process)."""
import os


def _csv(name: str) -> list:
    return [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]


API_URL = os.environ.get('VIDEODL_API_URL', 'http://127.0.0.1:8000').rstrip('/')
DEFAULT_API_KEY = os.environ.get('VIDEODL_API_KEY', '')  # only used on stdio, where the user runs the server for themselves

HOST = os.environ.get('MCP_HOST', '127.0.0.1')
PORT = int(os.environ.get('MCP_PORT', '8001'))
ALLOWED_HOSTS = _csv('MCP_ALLOWED_HOSTS')      # e.g. mcp.example.com ; enables DNS-rebinding protection
ALLOWED_ORIGINS = _csv('MCP_ALLOWED_ORIGINS')  # browser origins allowed to call the server (agents send none)

# The API limits anonymous callers per IP, and from its point of view every MCP call comes from this server.
# So this server passes the end user's address along. Headers from the caller are only believed when a proxy
# you control sits in front (it overwrites them); otherwise anyone could claim any address and dodge the limit.
TRUST_PROXY = os.environ.get('MCP_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')

WAIT_SECONDS = int(os.environ.get('MCP_WAIT_SECONDS', '60'))        # how long download_video waits before returning a job id
MAX_WAIT_SECONDS = int(os.environ.get('MCP_MAX_WAIT_SECONDS', '120'))  # most a caller may ask for; HD merges with ffmpeg can take 60-90s
POLL_SECONDS = float(os.environ.get('MCP_POLL_SECONDS', '2'))
HTTP_TIMEOUT = float(os.environ.get('MCP_HTTP_TIMEOUT', '120'))        # info extraction can take a while
