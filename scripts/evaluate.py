"""Reproducible targeted benchmark. Original end-to-end baseline is left unmeasured."""
import argparse
from datetime import date
import importlib.util
import json
import math
from pathlib import Path
from time import perf_counter

from finsight.financials import normalize, calculate
from finsight.rag import Hybrid
from finsight.schema import Draft, Evidence, Numeric, Reference
from finsight.verification import verify

ROOT = Path(__file__).resolve().parents[1]


def apple_fixture():
    doc = json.loads((ROOT/"tests/evaluation/apple_fy2024.json").read_text(encoding="utf-8"))
    facts = {}
    for tag, amount in doc["facts_millions"].items():
        row = {"val":amount*doc["source_scale"],"accn":doc["accession"],"form":"10-K",
               "start":doc["fy_start"],"end":doc["fy_end"],"filed":doc["filed"]}
        facts[tag] = {"units":{"USD":[row]}}
        if tag.startswith("Revenue"):
            facts[tag]["units"]["USD"].append(row | {"start":doc["prior_start"],"end":doc["prior_end"],
                "val":doc["prior_revenue_millions"]*doc["source_scale"]})
    return doc, {"cik":doc["cik"],"facts":{"us-gaap":facts}}


def evaluate(v1_path=None):
    start = perf_counter()
    doc, payload = apple_fixture()
    end,cutoff = date.fromisoformat(doc["fy_end"]),date.fromisoformat(doc["cutoff"])
    facts, _ = normalize(payload,cutoff,3)
    ratios = calculate(facts)
    same_period = {x.key:x.value for x in [*facts,*ratios] if x.end==end}
    rows = []

    def row(metric, input, expected, actual):
        if type(expected) is float and isinstance(actual,(float,int)):
            passed = math.isclose(expected,actual,rel_tol=1e-6,abs_tol=1e-7)
        else:
            passed = actual==expected
        rows.append({"metric":metric,"input":input,"expected":expected,"actual":actual,"pass":passed})

    for key, expected in doc["expected"].items():
        row("Financial data accuracy" if key=="revenue" else "Calculation accuracy",
            f"AAPL FY2024 · {key}",expected,same_period[key])
    row("Missing data handling","ROIC không đủ đầu vào",None,same_period["roic"])
    quote = "Verified industrial components distribute through resellers."
    e = Evidence(id="S1",document_id="S",company_cik=320193,title="Fixture mô phỏng",
                 url=doc["source"],locator="Đoạn mô phỏng",published=date(2024,11,1),text=quote,
                 quality="primary",content_hash="synthetic",kind="fixture")
    draft = Draft(dimension="growth",text="Doanh thu tăng 18%.",
                  numeric=Numeric(key="revenue_growth",value=18,unit="%",end=end),
                  references=[Reference(evidence_id="S1",quote=quote)])
    def status(claim, sources):
        return verify(claim,"C1","financial",cik=320193,as_of=cutoff,provided=sources,numbers=ratios).status

    row("Contradiction detection","Giả lập AAPL tăng 18% có ID nguồn tồn tại","CONTRADICTED",status(draft,[e]))
    qualitative = draft.model_copy(update={"numeric":None})
    row("Evidence support","ID hợp lệ nhưng mệnh đề không được đối chiếu nội dung","UNVERIFIED",status(qualitative,[e]))
    row("Citation validity","ID không tồn tại","UNVERIFIED",status(qualitative,[]))
    future = e.model_copy(update={"published":date(2024,11,20),"id":"S2"})
    query = "industrial components"
    found = [x.id for x in Hybrid([e,future],cutoff,320193,None).retrieve(query,2)]
    row("Temporal correctness","S2 công bố sau mốc",["S1"],found)
    row("Retrieval quality","Truy vấn có một đoạn gắn nhãn S1",1,int("S1" in found))
    baseline = {"original_full_run":"not_run","v1_full_run":"not_run"}
    if v1_path:
        spec = importlib.util.spec_from_file_location("baseline_v1_citations",Path(v1_path)/"core/rag_engine.py")
        v1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v1)
        _, supported_ids = v1.validate_citations("Doanh thu tăng 18%. [S1]",["S1"])
        baseline["v1_citation_id_rule"] = {"input":"Doanh thu tăng 18%. [S1]",
                                          "actual_accepted_ids":supported_ids,
                                          "same_input_v2_status":status(draft,[e])}
    return {"source":doc["source"],"cases":rows,"passed":sum(x["pass"] for x in rows),
            "count":len(rows),"offline_latency_ms":round((perf_counter()-start)*1000,2),
            "live_api_calls":0,"baseline":baseline}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--v1",help="Thư mục V1 tùy chọn để kiểm tra luật ID trích dẫn.")
    parser.add_argument("--output",type=Path,help="Ghi kết quả JSON.")
    args=parser.parse_args()
    results=evaluate(args.v1)
    body=json.dumps(results,indent=2,ensure_ascii=False)
    if args.output:
        args.output.write_text(body+"\n",encoding="utf-8")
    print(body)
    return int(results["passed"]!=results["count"])


if __name__=="__main__":
    raise SystemExit(main())
