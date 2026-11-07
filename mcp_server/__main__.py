"""
Run the MCP server:

    python -m mcp_server                                  # stdio, for a local client (uses VIDEODL_API_KEY)
    python -m mcp_server --transport streamable-http      # remote clients connect to http://HOST:PORT/mcp
"""
import argparse
import logging

from . import config
from .server import build_server, transport_security


def main():
    parser = argparse.ArgumentParser(prog='mcp_server')
    parser.add_argument('--transport', choices=['stdio', 'streamable-http'], default='stdio')
    parser.add_argument('--host', default=config.HOST)
    parser.add_argument('--port', type=int, default=config.PORT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)  # its INFO lines repeat every API URL

    # A server-wide fallback key is only safe when one person runs the server for themselves (stdio).
    # Over HTTP every caller must bring their own key.
    server = build_server(default_key=config.DEFAULT_API_KEY if args.transport == 'stdio' else '')
    if args.transport == 'stdio':
        server.run('stdio')
    else:
        server.run('streamable-http', host=args.host, port=args.port, transport_security=transport_security())


if __name__ == '__main__':
    main()
