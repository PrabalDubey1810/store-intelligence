# ── Dashboard: lightweight static file server ─────────────────────────────────
# Uses Python's built-in http.server (no Node.js, no extra deps).
# All static assets (index.html, style.css, app.js) are baked into the image.
FROM python:3.11-slim

WORKDIR /app

# Copy static web assets
COPY index.html style.css app.js server.py ./

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000')" || exit 1

CMD ["python", "server.py"]
