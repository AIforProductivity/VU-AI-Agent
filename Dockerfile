# VU Handbook MCP - production image (Streamable HTTP)
# Build:  docker build -t vu-handbook-mcp .
# Run:    docker run -p 8000:8000 vu-handbook-mcp --allow-host vumcp.example.com
#         (entrypoint is mcp_server.py, extra args are appended)
FROM python:3.12-slim

WORKDIR /app

# Runtime dependency only - the crawler toolchain (requests/bs4/pypdf) runs
# outside the image via tools/refresh.py.
RUN pip install --no-cache-dir "mcp>=1.13,<2"

COPY mcp_server.py README.md ./
COPY data/ ./data/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"

ENTRYPOINT ["python", "mcp_server.py"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8000"]
