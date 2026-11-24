from datetime import date, datetime, timezone
from html import escape

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

from finsight.agents import DIMENSIONS, ROLES
from finsight.config import settings
from finsight.financials import fact_id
from finsight.insights import investment, money, signals, vi_number
from finsight.provenance import evidence_link, fact_evidence_id, marked_excerpt
from finsight.schema import Fact
from frontend.presentation import PERIODS, fact_title, formula_text, metric_name, value_text, vi_date, vi_unit

cfg = settings()
st.set_page_config(page_title="FinSight Intelligence V2",page_icon="◈",layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1240px; padding: 2.3rem 2.8rem 4rem;}
[data-testid="stSidebar"] {border-right: 1px solid #dce5ec;}
[data-testid="stSidebar"] h1 {font-size: 1.32rem; letter-spacing: -.025em;}
[data-testid="stHeadingWithActionElements"] h1,
[data-testid="stHeadingWithActionElements"] h2 {letter-spacing: -.034em;}
[data-testid="stMetric"] {min-height: 98px; background: #fff; border: 1px solid #dce5ec;
    border-radius: 12px; padding: 12px 16px;}
[data-testid="stMetricLabel"] {color: #4b6072;}
[data-testid="stMetricValue"] {font-size: clamp(1.18rem, 2.1vw, 1.7rem); font-weight: 650;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 12px; background: #fff;}
[data-testid="stExpander"] details {border-radius: 10px;}
[data-testid="stTabs"] [role="tablist"] {gap: 1.35rem; overflow-x: auto;}
[data-testid="stTabs"] [role="tab"] {white-space: nowrap; font-weight: 600;}
.fs-report {margin-bottom: .45rem; padding: 1.6rem 1.85rem; border-radius: 16px; color: #fff;
    background: linear-gradient(112deg, #132842, #163a51 75%, #18564f);}
.fs-report h2 {font-size: clamp(1.55rem, 3.5vw, 2.25rem); margin: .28rem 0 .18rem;
    padding: 0; letter-spacing: -.032em; color: #fff;}
.fs-report .fs-ticker {display: inline-block; font-size: .79rem; font-weight: 700;
    letter-spacing: .04em; background: #d9f3eb; color: #164640; padding: .22rem .54rem; border-radius: 5px;}
.fs-report p {margin: .55rem 0 0; color: #dceaf3;}
.fs-excerpt {white-space: pre-wrap; overflow-wrap: anywhere; max-height: 19rem; overflow: auto;
    margin: .35rem 0; padding: .85rem 1rem; border-left: 3px solid #7ab5aa;
    border-radius: 5px; background: #f0f7f7; color: #24394a; line-height: 1.55;}
.fs-excerpt mark {background: #ffeb9c; color: #17283a; padding: .03em .08em;}
@media(max-width: 700px) {
    .block-container {padding: 1.3rem 1rem 3rem;}
    .fs-report {padding: 1.15rem;}
    [data-testid="stTabs"] [role="tablist"] {gap: .85rem;}
}
</style>
""", unsafe_allow_html=True)
base = f"http://127.0.0.1:{cfg.backend_port}/api/v1"
secret = cfg.api_token.get_secret_value()
headers = {"Authorization":"Bearer "+secret} if secret else {}
states = {
    "pending":"Đang chờ","collecting":"Thu thập","validating":"Chuẩn hóa","retrieving":"Truy xuất",
    "analyzing":"Phân tích","verifying":"Kiểm chứng","generating":"Tạo báo cáo",
    "completed":"Hoàn tất","partial":"Có giới hạn","failed":"Thất bại",
}
verification = {
    "SUPPORTED":"Có bằng chứng","PARTIALLY_SUPPORTED":"Có bằng chứng một phần","CONTRADICTED":"Bị phản bác",
    "UNVERIFIED":"Chưa xác minh","NOT_APPLICABLE":"Không áp dụng",
}
agent_names = {k:v[0] for k,v in ROLES.items()} | {
    "computed":"Phép tính Python","lead":"Tổng hợp","verification":"Kiểm chứng","cross_examination":"Phản biện"}
agent_status = {"ready":"Đã xử lý","insufficient":"Thiếu bằng chứng","failed":"Lỗi"}


def api(method, route, *, binary=False, show_error=True, **kwargs):
    try:
        result = httpx.request(method,base+route,headers=headers,timeout=28,**kwargs)
        result.raise_for_status()
        return result.content if binary else result.json() if result.content else True
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail")
        except ValueError:
            detail = None
        if show_error:
            st.error(detail if isinstance(detail,str) else f"Yêu cầu không hợp lệ hoặc dịch vụ gặp lỗi ({exc.response.status_code}).")
    except httpx.HTTPError:
        if show_error:
            st.error("Không kết nối được FastAPI. Kiểm tra máy chủ API và cổng trong tệp .env.")
    return None


def status_name(key):
    return states.get(key,key)


def claim_text(claim):
    draft = claim["claim"]
    text = draft["text"]
    if claim["role"] == "computed" and (number := draft.get("numeric")):
        rendered = money(number["value"]) if number["unit"] == "USD" else value_text(number["value"], number["unit"])
        return f"{metric_name(number['key'])} kỳ kết thúc {vi_date(number['end'])} là {rendered}."
    return text


def claim_line(claim):
    st.write(claim_text(claim))
    st.caption(f"{claim['id']} · {verification.get(claim['status'], 'Chưa xác minh')}")


def fact_source(report, fact):
    st.markdown(f"**{fact_title(fact)}**")
    value = value_text(fact["value"], fact["unit"])
    st.markdown(f'<p class="fs-excerpt"><mark>{escape(value)}</mark></p>', unsafe_allow_html=True)
    st.caption(f"{PERIODS.get(fact['period'], 'Kỳ báo cáo')} · Công bố {vi_date(fact['filed'])} · Hồ sơ {fact['form'] or 'SEC'}")
    identifier = fact_evidence_id(Fact.model_validate(fact))
    cache_key = ("fact_location", report["id"], identifier)
    if cache_key not in st.session_state:
        location = api("GET", f"/analysis/{report['id']}/evidence/{identifier}/location", show_error=False)
        if location and location["located"]:
            st.session_state[cache_key] = location["url"]
    if target := st.session_state.get(cache_key):
        st.link_button("Mở đúng số liệu trong hồ sơ SEC", target)
    else:
        st.caption("Chưa định vị được số liệu trong hồ sơ này.")
        st.link_button("Mở hồ sơ SEC", fact["url"])


def claim_sources(report, claim, source_index, scope):
    evidence_rows, fact_rows = source_index
    refs = {ref["evidence_id"]: ref["quote"] for ref in claim["claim"].get("references", [])}
    sources_found = False
    for title, key in (("Nguồn hỗ trợ", "evidence_ids"), ("Nguồn trái chiều", "counter_ids")):
        ids = [identifier for identifier in claim.get(key, []) if identifier in evidence_rows]
        if not ids:
            continue
        sources_found = True
        st.markdown(f"**{title}**")
        for identifier in ids:
            row = evidence_rows[identifier]
            with st.container(border=True):
                if identifier in fact_rows:
                    fact_source(report, fact_rows[identifier])
                else:
                    st.write(row["title"])
                    st.caption(f"Công bố {vi_date(row['published'])} · Kỳ kết thúc {vi_date(row.get('report_end'))}")
                    quote = refs.get(identifier, "")
                    excerpt = marked_excerpt(row["text"], quote)
                    # Only offer a text fragment when the quote was found in the stored source.
                    target, mode = evidence_link(row["url"], quote if "<mark>" in excerpt else "",
                                                 kind=row["kind"], locator=row["locator"])
                    st.markdown(f'<div class="fs-excerpt">{excerpt}</div>', unsafe_allow_html=True)
                    if target:
                        label = {"text": "Mở và tô sáng đoạn gốc", "page": "Mở đúng trang PDF",
                                 "document": "Mở tài liệu gốc"}[mode]
                        st.link_button(label, target)
                    if mode in {"page", "document"} and quote:
                        st.caption("Đoạn trích được đối chiếu trong khung trên. Tài liệu gốc mở ở vị trí nguồn cho phép.")
                if scope == "evidence" and st.button("Kiểm tra truy cập nguồn", key=f"check_{report['id']}_{claim['id']}_{key}_{identifier}"):
                    result = api("POST", f"/analysis/{report['id']}/evidence/{identifier}/check")
                    if result:
                        (st.success if result["reachable"] else st.warning)(result["message"])
    if not sources_found:
        st.caption("Phiên này chưa lưu nguồn cho nhận định này.")
    if claim["reason"]:
        st.caption(claim["reason"])


def claim_card(report, claim, source_index, scope):
    with st.container(border=True):
        claim_line(claim)
        count = len(set(claim.get("evidence_ids", []) + claim.get("counter_ids", [])) & source_index[0].keys())
        label = f"Xem bằng chứng ({count})" if count else "Xem tình trạng bằng chứng"
        panel = st.expander(label, key=f"proof_{report['id']}_{scope}_{claim['id']}", on_change="rerun")
        if panel.open:
            with panel:
                claim_sources(report, claim, source_index, scope)


def charts(report):
    st.subheader("Diễn biến tài chính")
    rows = [fact for fact in report["facts"] if fact["period"] == "FY" and fact["key"] in
            {"revenue", "net_income", "ocf", "capex"}]
    if not rows:
        st.info("Thiếu số liệu tài chính theo năm.")
    else:
        frame = pd.DataFrame(rows).sort_values("end")
        frame["Chỉ tiêu"] = frame["key"].map(metric_name)
        frame["Số liệu"] = [
            value_text(value, unit) for value, unit in zip(frame["value"], frame["unit"])]
        for unit, subset in frame.groupby("unit"):
            fig = px.line(subset, x="end", y="value", color="Chỉ tiêu", markers=True,
                          color_discrete_sequence=["#087E75", "#3765A3", "#9A5C2A", "#7773AC"],
                          labels={"end": "Kết thúc kỳ", "value": vi_unit(unit)}, custom_data=["Chỉ tiêu", "Số liệu"])
            fig.update_traces(hovertemplate="%{customdata[0]}<br>%{x|%d/%m/%Y}<br>%{customdata[1]}<extra></extra>")
            fig.update_layout(margin=dict(t=12, b=10, l=15, r=15), legend=dict(orientation="h", title_text=""), height=360)
            st.plotly_chart(fig, width="stretch")
        st.caption("Nguồn biểu đồ · SEC EDGAR. Hồ sơ công bố nằm trong bảng số liệu.")
    market = report.get("market", {})
    if market.get("observations"):
        st.subheader("Giá đóng cửa")
        fig = px.line(pd.DataFrame(market["observations"]), x="date", y="close",
                      labels={"date": "Phiên", "close": market.get("currency") or "Giá đóng cửa"})
        st.plotly_chart(fig, width="stretch")
        st.link_button("Lịch sử giá trên Yahoo Finance", market["url"])

    if report["ratios"]:
        st.subheader("Chỉ số tài chính")
        ends = list(dict.fromkeys(row["end"] for row in report["ratios"]))
        end = st.selectbox("Kỳ kết thúc", ends, format_func=vi_date, key=f"ratio_end_{report['id']}")
        ratios = [row for row in report["ratios"] if row["end"] == end]
        st.dataframe([{"Chỉ tiêu": metric_name(row["key"]),
                       "Giá trị": value_text(row["value"], row["unit"], include_unit=False),
                       "Đơn vị": vi_unit(row["unit"]), "Công bố đầu vào": vi_date(row["filed"]),
                       "Ghi chú": row["reason"] or "—"} for row in ratios], hide_index=True)
        with st.expander("Công thức và số liệu đầu vào"):
            by_key = {row["key"]: row for row in ratios}
            key = st.selectbox("Chọn chỉ tiêu", list(by_key), format_func=metric_name, key=f"ratio_key_{report['id']}_{end}")
            row = by_key[key]
            st.write(formula_text(row["formula"]))
            fact_map = {fact_id(Fact.model_validate(fact)): fact for fact in report["facts"]}
            inputs = [fact_map[identifier] for identifier in row["inputs"] if identifier in fact_map]
            if inputs:
                fact_table(inputs)
            for identifier in row["inputs"]:
                if identifier.startswith("https://") and identifier not in fact_map:
                    st.link_button("Mở nguồn giá thị trường", identifier)
    if report["facts"]:
        with st.expander("Số liệu chuẩn hóa và hồ sơ công bố"):
            fact_table(report["facts"])
    if report.get("peers"):
        st.subheader("Doanh nghiệp đối chiếu")
        st.caption("So sánh doanh thu USD theo năm. Ngày kết thúc kỳ có thể chênh lệch tối đa 92 ngày.")
        st.dataframe([{"Mã chứng khoán": row["ticker"], "Doanh nghiệp": row["name"],
                       "Kỳ kết thúc": vi_date(row["end"]), "Doanh thu": value_text(row["revenue"], row["unit"]),
                       **{metric_name(key): value_text(row["ratios"].get(key), "%")
                          for key in ("revenue_growth", "gross_margin", "net_margin")},
                       "Hồ sơ SEC": row["url"]} for row in report["peers"]], hide_index=True,
                     column_config={"Hồ sơ SEC": st.column_config.LinkColumn(display_text="Mở hồ sơ")})
    if report["changes"]:
        with st.expander("Số liệu thay đổi giữa các lần công bố"):
            for change in report["changes"]:
                st.markdown(f"**{fact_title(change)}**")
                before = value_text(change["prior"]["value"], change["unit"])
                after = value_text(change["current"]["value"], change["unit"])
                st.write(f"{before} → {after}")
                st.link_button("Hồ sơ trước", change["prior"]["url"])
                st.link_button("Hồ sơ sau", change["current"]["url"])


def fact_table(facts):
    st.dataframe([{"Chỉ tiêu": metric_name(row["key"]), "Loại kỳ": PERIODS.get(row["period"], "—"),
                   "Kết thúc kỳ": vi_date(row["end"]), "Giá trị": value_text(row["value"], row["unit"], include_unit=False),
                   "Đơn vị": vi_unit(row["unit"]), "Ngày công bố": vi_date(row["filed"]),
                   "Loại hồ sơ": row["form"], "Hồ sơ SEC": row["url"]} for row in facts], hide_index=True,
                 column_config={"Hồ sơ SEC": st.column_config.LinkColumn(display_text="Mở hồ sơ")})


def evidence_tab(report, source_index):
    claims = {claim["id"]: claim for claim in report["claims"]}
    if not claims:
        st.info("Chưa có nhận định để kiểm tra.")
        return
    cid = st.selectbox("Nhận định", list(claims), index=None, placeholder="Chọn nhận định cần xác minh",
                       key="claim_" + report["id"], format_func=lambda key: f"{key} · {claim_text(claims[key])[:90]}")
    if cid is None:
        return
    chosen = claims[cid]
    claim_line(chosen)
    if numeric := chosen["claim"].get("numeric"):
        ratio = next((row for row in report["ratios"] if (row["key"], row["end"], row["unit"]) ==
                      (numeric["key"], numeric["end"], numeric["unit"])), None)
        if ratio:
            st.caption("Công thức · " + formula_text(ratio["formula"]))
    claim_sources(report, chosen, source_index, "evidence")


def show_report(run_id):
    report = api("GET","/reports/"+run_id)
    if not report:
        return
    company = report["company"]
    st.markdown(
        f'<section class="fs-report"><span class="fs-ticker">{escape(company["ticker"])}</span>'
        f'<h2>{escape(company["name"])}</h2>'
        f'<p>Chốt dữ liệu {vi_date(report["request"]["as_of"])} · Mã định danh SEC {company["cik"]}</p></section>',
        unsafe_allow_html=True,
    )
    source_index = (
        {row["id"]: row for row in report["evidence"]},
        {fact_evidence_id(Fact.model_validate(fact)): fact for fact in report["facts"]},
    )
    scores = report["scores"]
    columns = st.columns(4)
    columns[0].metric("Trạng thái", status_name(report["status"]))
    columns[1].metric("Có bằng chứng", f"{scores['supported']}/{scores['total_claims']}")
    columns[2].metric("Khía cạnh có bằng chứng", f"{len(scores['covered_dimensions'])}/{scores['total_dimensions']}")
    columns[3].metric("Nhận định bị phản bác", scores["contradicted_claims"])
    overview, finance, evidence, agents, export = st.tabs(
        ["Tổng quan", "Tài chính", "Bằng chứng", "Nhóm phân tích", "Xuất báo cáo"])
    with overview:
        accepted = {claim["id"]: claim for claim in report["claims"] if claim["status"] == "SUPPORTED"}
        if report.get("lead_assessment") and any(c["role"] != "computed" for c in accepted.values()):
            st.subheader("Đánh giá tổng hợp của Lead")
            for point in report["lead_assessment"]:
                st.write(point["text"])
                for cid in point["claim_ids"]:
                    if cid in accepted:
                        claim_card(report, accepted[cid], source_index, "lead-" + point["topic"])
        thesis = investment(report)
        with st.expander("Luận điểm đầu tư và định giá"):
            for key, title in (("driver_ids", "Động lực"), ("risk_ids", "Rủi ro cần theo dõi")):
                st.markdown(f"**{title}**")
                for cid in thesis[key]:
                    claim_card(report, accepted[cid], source_index, "investment")
                if not thesis[key]:
                    st.caption("Chưa có nhận định đủ bằng chứng cho mục này.")
            price, eps = thesis["price"], thesis["eps"]
            if price:
                st.write(f"Giá đóng cửa {vi_date(price['date'])}: {vi_number(price['close'])} {price['currency']}")
                if price["url"]:
                    st.link_button("Nguồn thị trường", price["url"])
            if eps:
                fact_source(report, eps)
            if not price or not eps:
                st.info("Chưa đủ dữ liệu để đánh giá mức giá tại mốc báo cáo.")
        st.subheader("Tóm tắt điều hành")
        for signal in signals(report):
            with st.container(border=True):
                st.markdown(f"**{signal['title']} · {vi_date(signal['end'])}**")
                st.write(signal["text"])
                panel = st.expander(
                    f"Xem bằng chứng ({len(signal['inputs'])})",
                    key=f"signal_{report['id']}_{signal['period']}", on_change="rerun",
                )
                if panel.open:
                    with panel:
                        for fact in signal["inputs"]:
                            with st.container(border=True):
                                fact_source(report, fact)
        summary = [accepted[cid] for cid in report["summary_ids"] if cid in accepted]
        editorial = [claim for claim in summary if claim["role"] != "computed"]
        if editorial and not report.get("lead_assessment"):
            st.subheader("Kết luận chính")
            for claim in editorial[:6]:
                claim_card(report, claim, source_index, "summary")
        missing = [label for key, label in DIMENSIONS.items() if key not in scores["covered_dimensions"]]
        if missing:
            st.caption("Cần thêm bằng chứng · " + ", ".join(missing))
        if not accepted:
            st.info("Chưa đủ bằng chứng để đánh giá.")
        st.subheader("Phân tích theo khía cạnh")
        for key, label in DIMENSIONS.items():
            with st.expander(label):
                found = [claim for claim in accepted.values() if claim["claim"]["dimension"] == key]
                for claim in found:
                    claim_card(report, claim, source_index, "dimension")
                if not found:
                    st.caption("Chưa đủ bằng chứng để đánh giá.")
        if report["warnings"]:
            with st.expander("Giới hạn phiên phân tích"):
                for warning in report["warnings"]:
                    st.write(warning)
        st.caption("Báo cáo phục vụ nghiên cứu và mang tính tham khảo khi đầu tư.")
    with finance:
        charts(report)
    with evidence:
        evidence_tab(report, source_index)
    with agents:
        for role, meta in report["agents"].items():
            with st.expander(f"{agent_names.get(role, 'Phân tích')} · {agent_status[meta['status']]}"):
                matches = [claim for claim in report["claims"] if claim["role"] == role]
                st.caption(f"{meta['count']} mục xử lý")
                for claim in matches:
                    claim_card(report, claim, source_index, "agents")
    with export:
        fmt = st.selectbox("Định dạng",["json","md","pdf"])
        if st.button("Tạo tệp tải xuống"):
            payload = api("GET",f"/reports/{run_id}/export",params={"format":fmt},binary=True)
            if payload:
                st.download_button("Tải báo cáo",payload,file_name=f"{company['ticker']}-V2.{fmt}")
        st.write("Mức sử dụng API")
        cost = report.get("estimated_cost_usd")
        elapsed = report.get("elapsed_seconds")
        if elapsed is not None:
            st.caption(f"Thời gian xử lý {elapsed:.2f} giây")
        if cost is not None:
            st.caption(f"Chi phí theo đơn giá cấu hình {cost:.4f} USD")
        usage = report["usage"]
        if usage:
            usage_labels = {
                "model": "Lượt gọi mô hình", "search": "Lượt tìm kiếm",
                "Brave:web": "Tìm kiếm web qua Brave", "SEC:tickers": "Tra cứu danh mục mã SEC",
                "Yahoo:history": "Tra cứu lịch sử giá Yahoo Finance", "Gemini:generate": "Lượt tạo nội dung Gemini",
                "SEC:submissions": "Tra cứu hồ sơ SEC", "SEC:companyfacts": "Tra cứu số liệu SEC",
                "gemini_input_tokens": "Token đầu vào Gemini", "gemini_output_tokens": "Token đầu ra Gemini",
                "Tài liệu:document": "Lượt tải tài liệu",
            }
            with st.expander("Chi tiết sử dụng"):
                st.dataframe([{"Hạng mục": usage_labels.get(key, key), "Số lượng": value}
                              for key, value in usage.items()], hide_index=True)
        with st.form("feedback"):
            score = st.slider("Mức độ hữu ích",1,5,5)
            note = st.text_area("Ghi chú",max_chars=2000)
            if st.form_submit_button("Lưu phản hồi") and api("POST",f"/reports/{run_id}/feedback",
                                                             json={"score":score,"note":note}):
                st.success("Đã lưu phản hồi.")


@st.fragment(run_every=3)
def progress():
    run_id = st.session_state.get("run_id")
    if not run_id:
        return
    state = api("GET",f"/analysis/{run_id}/progress")
    if not state:
        return
    status = state["run"]["status"]
    st.write(f"**{status_name(status)}** · {state['run']['ticker']}")
    for event in state["events"][-5:]:
        st.caption(event["message"])
    if status in {"completed","partial","failed"} and st.session_state.get("terminal")!=run_id:
        st.session_state["terminal"] = run_id
        st.rerun()


today = datetime.now(timezone.utc).date()
st.sidebar.title("FinSight Intelligence")
page = st.sidebar.radio("Điều hướng",["Tổng quan","Phân tích doanh nghiệp","Lịch sử báo cáo","Định giá DCF"])
if page=="Tổng quan":
    st.title("Tổng quan nghiên cứu")
    state = api("GET","/system/status")
    history = api("GET","/reports",params={"limit":100})
    totals = api("GET","/dashboard")
    if state:
        columns = st.columns(4)
        columns[0].metric("MySQL","Đã kết nối")
        for col,key,label in zip(columns[1:],("sec_configured","brave_configured","gemini_configured"),("SEC","Brave","Gemini")):
            col.metric(label,"Đã cấu hình" if state[key] else "Thiếu cấu hình")
    if totals and "companies" in totals:
        cols = st.columns(4)
        cols[0].metric("Doanh nghiệp",totals["companies"])
        cols[1].metric("Báo cáo đã lưu",totals["reports"])
        recent = totals["latest_scores"]
        cols[2].metric("Có bằng chứng · phiên gần nhất",f"{recent['supported']}/{recent['total_claims']}" if recent else "—")
        cost = totals["latest_cost_usd"]
        cols[3].metric("Chi phí ước tính · phiên gần nhất",f"{cost:.4f} USD" if cost is not None else "—")
    if history is not None:
        st.subheader("Phiên nghiên cứu gần đây")
        st.caption(f"{len({r['ticker'] for r in history})} doanh nghiệp · {len(history)} phiên gần nhất")
        if history:
            st.dataframe([{"Mã chứng khoán":r["ticker"],"Mốc chốt":vi_date(r["as_of"]),"Trạng thái":status_name(r["status"]),
                           "Tạo lúc (UTC)":r["created_at"]} for r in history],hide_index=True)
elif page=="Phân tích doanh nghiệp":
    st.title("Phân tích doanh nghiệp")
    lookup = st.text_input("Tìm mã chứng khoán hoặc tên doanh nghiệp",max_chars=100)
    if st.button("Tra cứu SEC") and lookup.strip():
        st.session_state["matches"] = api("GET","/companies/search",params={"q":lookup.strip()}) or []
    matches = st.session_state.get("matches",[])
    choice = st.selectbox("Doanh nghiệp",matches,format_func=lambda r:f"{r['ticker']} · {r['name']} · CIK {r['cik']}") if matches else None
    with st.form("analysis"):
        ticker = st.text_input("Mã chứng khoán",value=choice["ticker"] if choice else "",max_chars=12)
        columns = st.columns(3)
        as_of = columns[0].date_input("Mốc chốt dữ liệu (UTC)",today,max_value=today,min_value=date(1995,1,1),format="DD/MM/YYYY")
        years = columns[1].number_input("Số năm tài chính",2,10,10)
        mode = columns[2].selectbox("Chế độ",["standard","deep"],format_func=lambda x:{"standard":"Tiêu chuẩn","deep":"Chuyên sâu"}[x])
        peer_input = st.text_input("Mã chứng khoán doanh nghiệp đối chiếu",max_chars=45,placeholder="MSFT, GOOGL")
        searches = st.slider("Số yêu cầu tìm kiếm tối đa",0,cfg.max_search_requests_per_run,cfg.max_search_requests_per_run)
        if st.form_submit_button("Bắt đầu phân tích",type="primary"):
            data = api("POST","/analysis",json={"ticker":ticker,"as_of":str(as_of),"years":years,
                                               "mode":mode,"search_budget":searches,
                                               "peers":[x.strip() for x in peer_input.split(",") if x.strip()]})
            if data:
                st.session_state["run_id"] = data["id"]
    if run_id := st.session_state.get("run_id"):
        if st.session_state.get("terminal")==run_id:
            state = api("GET",f"/analysis/{run_id}/progress")
            if state and state["run"]["status"]=="failed":
                st.error(state["events"][-1]["message"] if state["events"] else "Phiên hết thời gian xử lý.")
            else:
                show_report(run_id)
        else:
            progress()
elif page=="Lịch sử báo cáo":
    st.title("Lịch sử báo cáo")
    ticker = st.text_input("Lọc theo mã chứng khoán",max_chars=12)
    after = st.date_input("Mốc dữ liệu từ ngày",value=None,max_value=today,format="DD/MM/YYYY")
    filters = ({"ticker":ticker.strip()} if ticker.strip() else {}) | ({"after":str(after)} if after else {})
    history = api("GET","/reports",params=filters)
    if history:
        reports = {r["id"]:r for r in history}
        label = lambda k:f"{reports[k]['ticker']} · {vi_date(reports[k]['as_of'])} · {reports[k]['created_at']} · {status_name(reports[k]['status'])}"
        run_id = st.selectbox("Chọn phiên",list(reports),format_func=label)
        if reports[run_id]["status"] in {"completed","partial"}:
            show_report(run_id)
        others = [i for i in reports if i!=run_id and reports[i]["status"] in {"completed","partial"}]
        if others and reports[run_id]["status"] in {"completed","partial"}:
            other = st.selectbox("So sánh với phiên",["",*others],format_func=lambda x:label(x) if x else "Chọn phiên khác")
            if other:
                a,b = (api("GET","/reports/"+i) for i in (run_id,other))
                if a and b:
                    st.dataframe([{"Phiên":x["id"],"Mã chứng khoán":x["company"]["ticker"],"Có bằng chứng":x["scores"]["supported"],
                                   "Tổng nhận định":x["scores"]["total_claims"],"Mốc chốt":vi_date(x["request"]["as_of"])}
                                  for x in (a,b)],hide_index=True)
        with st.expander("Thao tác với phiên"):
            if st.button("Chạy lại với cùng mốc dữ liệu"):
                job = api("POST",f"/reports/{run_id}/rerun")
                if job:
                    st.session_state["run_id"] = job["id"]
                    st.success("Đã gửi yêu cầu. Xem tiến trình ở mục Phân tích doanh nghiệp.")
            agree = st.checkbox("Xác nhận xóa phiên này")
            if st.button("Xóa phiên",disabled=not agree) and api("DELETE",f"/reports/{run_id}"):
                st.rerun()
    elif history == []:
        st.info("Chưa có phiên phù hợp với bộ lọc.")
else:
    st.title("Định giá DCF theo giả định")
    st.caption("Nhập dòng tiền tự do cho doanh nghiệp (FCFF), nợ ròng và số cổ phiếu theo đơn vị gốc. Tỷ lệ nhập theo phần trăm.")
    with st.form("dcf"):
        fcff = st.number_input("Dòng tiền tự do năm cơ sở (FCFF)",min_value=0.0)
        shares = st.number_input("Số cổ phiếu",min_value=0.0)
        debt = st.number_input("Nợ ròng")
        growth = st.number_input("Tăng trưởng FCFF (%)",value=5.0)
        wacc = st.number_input("Chi phí vốn bình quân (WACC, %)",value=10.0)
        terminal = st.number_input("Tăng trưởng dài hạn (%)",value=2.0)
        years = st.number_input("Số năm dự phóng",1,15,5)
        if st.form_submit_button("Tính theo giả định"):
            result = api("POST","/valuation/dcf",json={"fcff":fcff,"growth":growth/100,"discount":wacc/100,
                         "terminal_growth":terminal/100,"net_debt":debt,"shares":shares,"years":years})
            if result:
                st.metric("Giá trị mỗi cổ phiếu",vi_number(result['base']['per_share']))
                st.dataframe([{"WACC (%)":x["discount"]*100,"Tăng trưởng dài hạn (%)":x["terminal_growth"]*100,
                               "Giá trị mỗi cổ phiếu":x["valuation"]["per_share"] if x["valuation"] else None}
                              for x in result["sensitivity"]],hide_index=True)
