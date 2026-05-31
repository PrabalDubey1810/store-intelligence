"""
FastAPI entrypoint — Store Intelligence API
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog
import logging
import uuid
import time
import os

from database import SessionLocal, check_db_health
from pos_loader import load_pos_csv

# Routers
from ingestion import router as ingestion_router
from metrics   import router as metrics_router
from funnel    import router as funnel_router
from heatmap   import router as heatmap_router
from anomalies import router as anomalies_router
from health    import router as health_router

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()  # logging requires uppercase
logging.basicConfig(level=LOG_LEVEL)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger(__name__)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Store Intelligence API",
    description="Purplle Tech Challenge 2026 — Retail Store Analytics API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: load POS data ────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        csv_path = os.getenv("POS_CSV_PATH", "/app/data/pos_transactions.csv")
        rows = load_pos_csv(db, csv_path)
        log.info("startup_complete", pos_rows_loaded=rows)
    except Exception as e:
        log.error("startup_error", error=str(e))
    finally:
        db.close()


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    request.state.event_count = None
    start = time.perf_counter()

    try:
        response = await call_next(request)
        latency = round((time.perf_counter() - start) * 1000, 2)

        log.info(
            "http_request",
            trace_id=trace_id,
            store_id=request.path_params.get("store_id", "N/A"),
            endpoint=str(request.url.path),
            method=request.method,
            latency_ms=latency,
            event_count=getattr(request.state, "event_count", None),
            status_code=response.status_code,
        )
        response.headers["X-Trace-Id"] = trace_id
        return response

    except Exception as exc:
        latency = round((time.perf_counter() - start) * 1000, 2)
        log.error("http_error", trace_id=trace_id, error=str(exc), latency_ms=latency)
        raise


# ── Global error handler — no raw stack traces ────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    log.error("unhandled_exception", trace_id=trace_id, error=str(exc), exc_info=True)

    from sqlalchemy.exc import OperationalError
    if isinstance(exc, OperationalError):
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "detail": "Database connection failed. Please retry shortly.",
                "trace_id": trace_id,
            }
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
            "trace_id": trace_id,
        }
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingestion_router, tags=["Ingestion"])
app.include_router(metrics_router,   tags=["Metrics"])
app.include_router(funnel_router,    tags=["Funnel"])
app.include_router(heatmap_router,   tags=["Heatmap"])
app.include_router(anomalies_router, tags=["Anomalies"])
app.include_router(health_router,    tags=["Health"])


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "Store Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
