"""Diagnostics are opt-in for live API calls."""
import argparse
from datetime import date
import importlib
import sys

import httpx

from finsight.agents import Gemini
from finsight.config import settings
from finsight.pipeline import Pipeline
from finsight.research import Brave
from finsight.schema import Selection
from finsight.storage import Repository, mysql_engine
from finsight.transport import Budget, Http, ProviderError, Rate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true",help="Kiểm tra SEC và các API có khóa. Có thể phát sinh chi phí.")
    args = parser.parse_args()
    cfg = settings()
    failed = False
    checks = {name:(lambda n=name:importlib.import_module(n)) for name in
              ("fastapi","sqlalchemy","pymysql","faiss","sentence_transformers","pymupdf","google.genai","streamlit")}
    checks["MySQL"] = Repository(mysql_engine(cfg),60).health
    if args.live:
        budget = Budget(120,6,1)
        def sec_check():
            with httpx.Client() as c:
                service = Pipeline(cfg).sec(c,budget)
                company,_ = service.company("AAPL",date.today())
                assert service.facts(company.cik)["cik"] == company.cik

        checks["SEC"] = sec_check
        if cfg.brave_search_api_key.get_secret_value():
            def brave_check():
                with httpx.Client() as c:
                    service = Brave(Http(c,budget,Rate(cfg.brave_requests_per_second),"Brave",10),cfg)
                    if cfg.brave_web_search_enabled:
                        service.search("Apple AAPL SEC Form 10-K","official","web")
                    if cfg.brave_llm_context_enabled:
                        service.search("Apple AAPL SEC Form 10-K","official","context")

            checks["Brave"] = brave_check
        else:
            print("Brave: bỏ qua do chưa cấu hình khóa.")
        if cfg.gemini_api_key.get_secret_value() and cfg.gemini_model:
            def gemini_check():
                model = Gemini(cfg,budget)
                try:
                    model.ask("Trả claim_ids rỗng.",{},Selection)
                finally:
                    model.close()

            checks["Gemini"] = gemini_check
        else:
            print("Gemini: bỏ qua do thiếu khóa hoặc tên model.")
    for name,check in checks.items():
        try:
            check()
            print(f"{name}: OK")
        except Exception as exc:
            print(f"{name}: LỖI · {str(exc) if isinstance(exc,ProviderError) else type(exc).__name__}")
            failed = True
    return int(failed)


if __name__=="__main__":
    sys.exit(main())
