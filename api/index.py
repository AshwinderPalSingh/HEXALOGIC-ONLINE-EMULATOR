import os
import time

from flask import Flask, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from api.sandbox_api import sandbox_api
from sim8051.observability import MetricsRegistry
from sim8051.session import build_session_store_from_env
from sim8051.uart_network import UARTNetwork

CLEAR_TOKEN = "batman"
app = Flask(__name__, static_folder="static")
# Deployed behind a single-hop reverse proxy (Railway) that terminates TLS and
# forwards plain HTTP internally. Without this, request.is_secure always
# reads False in production, so the session cookie's Secure flag could never
# be set even when the client connection really is HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)
app.config.setdefault("MAX_CONTENT_LENGTH", int(os.environ.get("HEXLOGIC_MAX_CONTENT_LENGTH", 262_144)))
app.config.setdefault("HEXLOGIC_MAX_SOURCE_CHARS", int(os.environ.get("HEXLOGIC_MAX_SOURCE_CHARS", 200_000)))
app.config.setdefault("HEXLOGIC_MAX_RUN_STEPS", int(os.environ.get("HEXLOGIC_MAX_RUN_STEPS", 100_000)))
app.config.setdefault("HEXLOGIC_ENABLE_DEBUG_TRACE", os.environ.get("HEXLOGIC_ENABLE_DEBUG_TRACE", "0").strip() == "1")
_session_store = build_session_store_from_env()
_metrics = MetricsRegistry()
_uart_network = UARTNetwork()
app.extensions["hexalogic_session_store"] = _session_store
app.extensions["hexlogic_session_store"] = _session_store
app.extensions["hexalogic_metrics"] = _metrics
app.extensions["hexlogic_metrics"] = _metrics
app.extensions["hexalogic_uart_network"] = _uart_network
app.register_blueprint(sandbox_api)

app.jinja_env.globals.update(zip=zip)


def _cors_allowed_origins():
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw or raw == "*":
        return "*"
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _origin_allowed(origin):
    allowed = _cors_allowed_origins()
    if allowed == "*":
        return True
    return bool(origin and origin in allowed)


@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get("Origin")
    if _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Hexlogic-Session"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "X-Hexlogic-Session"
    return response


@app.before_request
def _log_request_start():
    request.environ["_hexlogic_started_at"] = time.perf_counter()


@app.after_request
def _log_request_end(response):
    metrics = app.extensions.get("hexalogic_metrics") or app.extensions.get("hexlogic_metrics")
    if metrics is not None:
        metrics.record_api_request(error=response.status_code >= 400)
    if request.path.startswith("/api/"):
        elapsed_ms = 0.0
        started = request.environ.get("_hexlogic_started_at")
        if started is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        app.logger.info("%s %s %s %.3fms", request.method, request.path, response.status_code, elapsed_ms)
    return response


@app.errorhandler(RequestEntityTooLarge)
def _payload_too_large(_exc):
    return {"error": {"type": "validation", "message": "Request payload too large", "context": {}}}, 413


@app.route("/", methods=["GET"])
def main():
    return render_template(
        "index.html",
        api_base=(os.environ.get("HEXLOGIC_API_BASE", "") or "").rstrip("/"),
    )


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "target": "AT89C51"}
