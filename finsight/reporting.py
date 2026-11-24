from html import escape
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit

from finsight.agents import DIMENSIONS
from finsight.insights import investment, vi_number


def selected(report):
    return {c["id"]:c for c in report["claims"] if c["status"]=="SUPPORTED"}


def lines(report):
    c, r = report["company"], report["request"]
    accepted = selected(report)
    yield "heading", f"{c['name']} ({c['ticker']})"
    yield "text", f"Mốc dữ liệu {r['as_of']} · Tạo lúc {report['created_at']} · FinSight V{report['version']}"
    yield "section", "Tóm tắt"
    for cid in report["summary_ids"]:
        if cid in accepted:
            yield "text", f"{accepted[cid]['claim']['text']} [{cid}]"
    if not report["summary_ids"]:
        yield "text", "Chưa đủ bằng chứng để đánh giá."
    if report.get("lead_assessment"):
        yield "section", "Đánh giá tổng hợp của Lead"
        for point in report["lead_assessment"]:
            refs = ", ".join(point["claim_ids"])
            yield "text", f"{point['text']} [{refs}]"
            yield "text", point.get("basis", "")
    thesis = investment(report)
    yield "section", "Luận điểm đầu tư và định giá"
    for signal in thesis["signals"][:1]:
        yield "text", f"{signal['title']} · {signal['end']} · {signal['text']}"
        for url in dict.fromkeys(f["url"] for f in signal["inputs"]):
            yield "link", ("Nguồn đối chứng số liệu", url)
    for key, label in (("driver_ids", "Động lực"), ("risk_ids", "Rủi ro")):
        for cid in thesis[key]:
            yield "text", f"{label} · {accepted[cid]['claim']['text']} [{cid}]"
    price, eps = thesis["price"], thesis["eps"]
    if price:
        yield "text", f"Giá đóng cửa {price['date']} · {vi_number(price['close'])} {price['currency']}"
        if price["url"]:
            yield "link", ("Nguồn giá thị trường", price["url"])
    if eps:
        yield "text", f"EPS pha loãng năm kết thúc {eps['end']} · {vi_number(eps['value'])} {eps['unit']}"
        yield "link", ("Nguồn đối chứng EPS", eps["url"])
    if not price or not eps:
        yield "text", "Chưa đủ dữ liệu để đánh giá mức giá tại mốc báo cáo."
    for dimension,label in DIMENSIONS.items():
        yield "section", label
        matching = [a for a in report["claims"] if a["claim"]["dimension"]==dimension]
        if not matching:
            yield "text", "Chưa đủ bằng chứng để đánh giá."
        for item in matching:
            yield "text", f"{item['claim']['text']} [{item['id']}]"
            yield "text", item["reason"]
    yield "section", "Số liệu tài chính theo năm"
    key_labels = {"revenue":"Doanh thu","net_income":"Lợi nhuận ròng","ocf":"Dòng tiền hoạt động"}
    for f in report["facts"]:
        if f["period"] == "FY" and f["key"] in key_labels:
            yield "text",f"{key_labels[f['key']]} · {f['end']} · {f['value']:,.0f} {f['unit']}"
    yield "section", "Chỉ tiêu và công thức"
    for ratio in report["ratios"]:
        val = f"{ratio['value']:,.6g} {ratio['unit']}" if ratio["value"] is not None else ratio["reason"]
        period = "Quý" if ratio.get("period") == "Q" else "Năm"
        yield "text", f"{ratio['key']} · {period} · {ratio['end']} · {val} · {ratio['formula']}"
    if report.get("peers"):
        yield "section","Doanh nghiệp đối chiếu"
        for peer in report["peers"]:
            yield "text", f"{peer['ticker']} · doanh thu {peer['revenue']:,.0f} {peer['unit']} · kết thúc {peer['end']}"
            labels = {"revenue_growth":"Tăng trưởng", "operating_margin":"Biên hoạt động",
                      "fcf_margin":"Biên dòng tiền tự do", "roic":"ROIC", "pe":"P/E"}
            comparisons = [f"{label} {vi_number(value)}{' lần' if key == 'pe' else '%'}"
                           for key, label in labels.items() if (value := peer["ratios"].get(key)) is not None]
            if comparisons:
                yield "text", " · ".join(comparisons)
            yield "link",(f"{peer['name']} · hồ sơ SEC",peer["url"])
            if peer.get("market_url") and peer.get("price_date"):
                yield "link", (f"Nguồn giá ngày {peer['price_date']}", peer["market_url"])
    yield "section", "Kiểm chứng và nguồn"
    evidence = {e["id"]:e for e in report["evidence"]}
    for claim in report["claims"]:
        yield "text", f"{claim['id']} · {claim['status']} · {claim['reason']}"
        for eid in [*claim["evidence_ids"],*claim["counter_ids"]]:
            if e := evidence.get(eid):
                if urlsplit(e["url"]).scheme=="https":
                    yield "link", (f"{e['title']} · {e['locator']}",e["url"])
    if report.get("external_context"):
        yield "section", "Bối cảnh báo chí và mạng xã hội"
        for group, label in (("news","Báo chí"),("social","Mạng xã hội · Ý kiến chưa kiểm chứng")):
            context = report["external_context"][group]
            yield "text", f"{label} · Đọc được {context['read']}/{context['found']} nguồn · {len(context['observations'])} nhận xét."
            for item in context["observations"]:
                if item.get("source_type") == "search_excerpt":
                    yield "text", "Trích đoạn tìm kiếm; chưa đọc bài gốc, cần kiểm chứng."
                yield "text", f"{item['published']} · {item['observation']}"
                yield "link", (item["title"], item["url"])
    yield "section", "Giới hạn nghiên cứu"
    for warning in report["warnings"]:
        yield "text", warning
    yield "text", "Báo cáo phục vụ nghiên cứu. Không phải khuyến nghị đầu tư."


def markdown(report) -> bytes:
    body = []
    for kind,value in lines(report):
        if kind=="link":
            label,url=value
            body.append(f"- {label} — <{url}>")
        else:
            safe = value.replace("<","&lt;").replace(">","&gt;")
            body.append(("# " if kind=="heading" else "## " if kind=="section" else "")+safe)
    return "\n\n".join(body).encode("utf-8")


def pdf(report, font_path: str) -> bytes:
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    options = [Path(font_path)] if font_path else [Path("C:/Windows/Fonts/arial.ttf"),
                                                     Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    font = next((x for x in options if x.is_file()),None)
    if not font:
        raise ValueError("Đặt PDF_FONT_PATH trỏ tới font TrueType hỗ trợ tiếng Việt.")
    pdfmetrics.registerFont(TTFont("FinSightUnicode",str(font)))
    buf = BytesIO()
    doc = SimpleDocTemplate(buf,title="FinSight Intelligence V2",author="FinSight Intelligence")
    styles = {k:ParagraphStyle(k,fontName="FinSightUnicode",fontSize=s,leading=s*1.4,
                              textColor="#112340" if k!="link" else "#00756E",
                              spaceBefore=8 if k in ("heading","section") else 0,
                              keepWithNext=k in ("heading","section"))
              for k,s in {"heading":22,"section":14,"text":10,"link":9}.items()}
    story = []
    for kind,value in lines(report):
        content = (f'<link href="{escape(value[1],quote=True)}">{escape(value[0])}</link>'
                   if kind=="link" else escape(value))
        story.extend((Paragraph(content,styles[kind]),Spacer(1,4)))
        if kind == "section" and value == "Số liệu tài chính theo năm":
            revenues = sorted((f for f in report["facts"] if f["period"]=="FY" and f["key"]=="revenue"
                               and f["unit"]=="USD"),key=lambda f:f["end"])
            if len(revenues)>1:
                drawing = Drawing(445,162)
                chart = HorizontalLineChart()
                chart.x,chart.y,chart.width,chart.height = 55,40,345,90
                chart.data = [[f["value"]/1e9 for f in revenues]]
                chart.categoryAxis.categoryNames = [f["end"] for f in revenues]
                chart.categoryAxis.labels.fontName = "FinSightUnicode"
                chart.categoryAxis.labels.fontSize = 8
                chart.valueAxis.labels.fontName = "FinSightUnicode"
                chart.valueAxis.labels.fontSize = 8
                chart.lines[0].strokeColor = HexColor("#00756E")
                chart.lines[0].strokeWidth = 2
                drawing.add(chart)
                drawing.add(String(55,143,"Doanh thu theo năm tài chính (tỷ USD)",fontName="FinSightUnicode",fontSize=10))
                drawing.add(String(55,13,"Nguồn: SEC EDGAR Company Facts",fontName="FinSightUnicode",fontSize=8))
                story.append(drawing)
    doc.build(story)
    return buf.getvalue()


def export(report, format, font_path=""):
    if format=="md":
        return markdown(report),"text/markdown; charset=utf-8"
    if format=="pdf":
        return pdf(report,font_path),"application/pdf"
    return json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode(),"application/json"
