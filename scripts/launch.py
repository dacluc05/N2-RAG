import argparse
from pathlib import Path
import socket
import subprocess
import sys

from finsight.config import settings
from finsight.storage import Repository, mysql_engine


def check_port(host, port):
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, port))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", action="store_true", help="Mở giao diện Streamlit.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.legacy and not (root / "frontend" / "web" / "dist" / "index.html").is_file():
        print("Chưa có bản dựng giao diện. Chạy BUILD_WEB_WINDOWS.bat hoặc START_WINDOWS.bat --legacy.")
        return 1
    cfg = settings()
    repo = Repository(mysql_engine(cfg), 60)
    try:
        repo.health()
    except Exception as exc:
        print(f"MySQL chưa sẵn sàng ({type(exc).__name__}). Kiểm tra .env và chạy python -m alembic upgrade head.")
        return 1
    finally:
        repo.engine.dispose()
    try:
        check_port(cfg.backend_host, cfg.backend_port)
        check_port("127.0.0.1", cfg.frontend_port)
    except OSError:
        print("Cổng backend hoặc frontend đang được sử dụng. Dừng phiên cũ và chạy lại.")
        return 1
    backend = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "finsight.api:app", "--host", cfg.backend_host, "--port", str(cfg.backend_port)
    ], cwd=root)
    frontend = (
        [sys.executable, "-m", "streamlit", "run", "frontend/Home.py", "--server.port", str(cfg.frontend_port)]
        if args.legacy else
        [sys.executable, "-m", "uvicorn", "scripts.web_ui:app", "--host", "127.0.0.1", "--port", str(cfg.frontend_port)]
    )
    print(f"FinSight · http://127.0.0.1:{cfg.frontend_port}", flush=True)
    try:
        return subprocess.call(frontend, cwd=root)
    except KeyboardInterrupt:
        return 0
    finally:
        if backend.poll() is None:
            backend.terminate()
            backend.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
