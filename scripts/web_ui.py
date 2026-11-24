"""Serve the built research workspace and relay its local API requests."""
from contextlib import asynccontextmanager
from pathlib import Path
import re
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from finsight.config import settings

DIST = Path(__file__).resolve().parents[1] / "frontend" / "web" / "dist"
RUN = r"[0-9a-f-]{36}"
READ_ROUTES = re.compile(
    rf"(?:health|system/status|dashboard|companies/search|reports|reports/{RUN}(?:/export|/signals|/investment|/context/(?:news|social))?|"
    rf"analysis/{RUN}/(?:progress|evidence/[\w:.-]+/(?:location|pdf)))"
)
WRITE_ROUTES = re.compile(rf"(?:analysis|valuation/dcf|reports/{RUN}/(?:rerun|feedback)|analysis/{RUN}/evidence/[\w:.-]+/check)")
DELETE_ROUTES = re.compile(rf"reports/{RUN}")


@asynccontextmanager
async def lifespan(app):
    cfg = settings()
    token = cfg.api_token.get_secret_value()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=str(httpx.URL(scheme="http", host="127.0.0.1" if cfg.backend_host in {"0.0.0.0", "::"} else cfg.backend_host, port=cfg.backend_port)), headers=headers, timeout=28, trust_env=False
    ) as client:
        app.state.backend = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.middleware("http")
async def browser_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
    )
    return response


@app.get("/api/v1/ui/config")
def ui_config():
    return {"search_budget": settings().max_search_requests_per_run}


@app.api_route("/api/v1/{route:path}", methods=["GET", "POST", "DELETE"])
async def relay(route: str, request: Request):
    allowed = {"GET": READ_ROUTES, "POST": WRITE_ROUTES, "DELETE": DELETE_ROUTES}[request.method]
    if not allowed.fullmatch(route):
        raise HTTPException(404, "Không tìm thấy chức năng này.")
    if request.method != "GET":
        if request.headers.get("origin") != f"http://{request.headers.get('host')}":
            raise HTTPException(403, "Yêu cầu phải được gửi từ giao diện FinSight.")
        if request.method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "Yêu cầu phải sử dụng JSON.")
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 32_768:
            raise HTTPException(413, "Dữ liệu gửi lên quá lớn.")
        payload.extend(chunk)
    try:
        result = await request.app.state.backend.request(
            request.method, "/api/v1/" + quote(route, safe="/:"), params=request.query_params.multi_items(),
            content=bytes(payload), headers={"Content-Type": "application/json"} if payload else None,
        )
    except httpx.RequestError:
        raise HTTPException(503, "Chưa kết nối được máy chủ FinSight. Hãy kiểm tra cửa sổ khởi động.") from None
    headers = {"Cache-Control": "no-store"}
    for key in ("content-type", "content-disposition"):
        if key in result.headers:
            headers[key] = result.headers[key]
    return Response(result.content, result.status_code, headers)


app.mount("/assets", StaticFiles(directory=DIST / "assets", check_dir=False), name="assets")


@app.get("/{path:path}")
def workspace(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Không tìm thấy API.")
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Chưa có bản dựng giao diện. Hãy chạy BUILD_WEB_WINDOWS.bat.")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
