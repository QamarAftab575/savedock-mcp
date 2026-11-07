# docker build -t savedock-mcp .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_server/ mcp_server/
RUN useradd --system --uid 10001 mcp
USER mcp
EXPOSE 8001
ENV MCP_HOST=0.0.0.0 MCP_PORT=8001
CMD ["python", "-m", "mcp_server", "--transport", "streamable-http"]
