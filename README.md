# SaveDock MCP: free video downloader MCP server for AI agents

**SaveDock MCP** lets AI agents and MCP clients (Claude, Cursor, VS Code, Windsurf and any client with remote MCP support) download videos and audio by calling tools. Give your agent a link from **YouTube, Instagram, TikTok, Facebook, X (Twitter) or Pinterest** and it can read the video's details, then save it as **MP4 video** or **MP3 audio**.

It is the MCP server behind [SaveDock](https://savedock.pro), a free online video downloader. No account, no API key, no sign-up.

- Website: https://savedock.pro
- MCP docs: https://savedock.pro/mcp-server/
- Hosted endpoint (Streamable HTTP): `https://mcp.savedock.pro/mcp`

## Quick start: connect to the hosted server

You do not need to install or run anything. Add the URL to your MCP client.

Claude Code:

```bash
claude mcp add --transport http savedock https://mcp.savedock.pro/mcp
```

Any client that reads a JSON config:

```json
{
  "mcpServers": {
    "savedock": { "url": "https://mcp.savedock.pro/mcp" }
  }
}
```

Exact syntax differs between clients, so check your client's remote MCP documentation. After connecting, just ask: *"Download this YouTube video as MP3: https://..."*

Free use is limited per IP address (10 downloads per hour). Downloaded files are temporary and are deleted automatically after a few hours.

## Tools

| Tool | What it does |
|---|---|
| `get_video_info(url)` | Returns title, uploader, duration and the qualities available. Read-only. |
| `download_video(url, quality="best", audio_only=false, wait_seconds=...)` | Starts a download and waits for it. Returns a temporary `download_url`, or a job id if it is still running. Use `audio_only=true` for MP3. |
| `get_download_status(job_id, wait_seconds=...)` | Checks a running job. |
| `cancel_download(job_id)` | Stops a queued or running job. |

Resources: `videodl://platforms` (supported sites and limits) and `videodl://quality-options` (what `quality` accepts).

Results include readable text plus structured content. Errors come back with `isError: true` and a machine-readable `code`, `message`, `retryable` and `retry_after`, so an agent can decide whether to retry. The server returns a download link; file bytes are never placed into the conversation.

## Supported platforms

YouTube, Instagram, TikTok, Facebook, X (Twitter) and Pinterest. Availability depends on what each site allows, and some videos (private, age-restricted or region-locked) cannot be downloaded.

## Install and run it yourself

This package is a thin Model Context Protocol adapter over the SaveDock REST API. It has no yt-dlp, no database and no business logic of its own, so it needs an API to talk to (`VIDEODL_API_URL`).

```bash
git clone https://github.com/QamarAftab575/savedock-mcp.git
cd savedock-mcp
pip install .            # or: pip install -r requirements.txt

# Local, one user (stdio):
VIDEODL_API_URL=https://your-api.example.com python -m mcp_server

# Remote, many callers (Streamable HTTP, endpoint /mcp):
VIDEODL_API_URL=https://your-api.example.com \
MCP_ALLOWED_HOSTS=mcp.example.com \
python -m mcp_server --transport streamable-http --host 0.0.0.0 --port 8001
```

Or with Docker:

```bash
docker build -t savedock-mcp .
docker run -p 8001:8001 -e VIDEODL_API_URL=https://your-api.example.com savedock-mcp
```

### Settings

| Variable | Meaning |
|---|---|
| `VIDEODL_API_URL` | Where `/api/v1/` lives (default `http://127.0.0.1:8000`). |
| `VIDEODL_API_KEY` | Optional key for higher limits, used on stdio only and ignored over HTTP. |
| `MCP_TRUST_PROXY` | Set `true` only when a reverse proxy you control sits in front, so per-user limits use the forwarded address. |
| `MCP_HOST`, `MCP_PORT` | Bind address (default `127.0.0.1:8001`). |
| `MCP_ALLOWED_HOSTS` | Comma list of public host names; turns on DNS-rebinding protection. Set it in production. |
| `MCP_ALLOWED_ORIGINS` | Browser origins allowed to call the server. |
| `MCP_WAIT_SECONDS`, `MCP_MAX_WAIT_SECONDS`, `MCP_POLL_SECONDS` | Wait defaults, cap and poll interval. |

## Tests

```bash
python -m unittest discover -s mcp_server/tests -t .
```

The tests use a mocked REST service and a real in-memory MCP client.

## Responsible use

Only download content you own, that is in the public domain, or that you have permission to save. You are responsible for following the terms of the platforms you use and the copyright law that applies to you.

## License

MIT. See [LICENSE](LICENSE).
