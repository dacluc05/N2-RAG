from datetime import date
import pytest
from conftest import CUT, END, QUOTE, evidence
from finsight.schema import Draft, Numeric, Reference, Fact, Review
from finsight.verification import verify


def evaluate(text, value=120000000, key="revenue", period="FY"):
    source = evidence()
    draft = Draft(dimension="financial", text=text,
        numeric=Numeric(key=key, unit="USD", value=value, end=END, period=period),
        references=[Reference(evidence_id=source.id, quote=QUOTE)])
    fact = Fact(key=key, unit="USD", value=120000000, end=END, filed=CUT,
        period=period, concept=key, accession="fixture", url="https://example.org")
    return verify(draft, "C1", "financial", cik=123, as_of=CUT,
        provided=[source], numbers=[fact],
        review=lambda *_: Review(status="UNVERIFIED", reason="Đoạn trích không xác nhận số liệu."))


@pytest.mark.parametrize("text,value,code", [
    ("Doanh thu iPhone đạt 100 triệu USD.", 100000000, "NUMERIC_SCOPE"),
    ("Doanh thu dự kiến đạt 100 triệu USD.", 100000000, "NUMERIC_SCOPE"),
    ("Doanh thu điều chỉnh đạt 100 triệu USD.", 100000000, "NUMERIC_SCOPE"),
    ("Doanh thu đạt 120 triệu USD.", 100000000, "NUMERIC_TEXT_MISMATCH"),
    ("Doanh thu đạt 120 triệu USD.", 120, "NUMERIC_SCALE"),
    ("Doanh thu ngày 27/09/2024 đạt 100 triệu USD.", 100000000, "NUMERIC_PERIOD"),
    ("Doanh thu quý đạt 100 triệu USD.", 100000000, "NUMERIC_PERIOD"),
    ("Doanh thu đạt 120 triệu USD và lợi nhuận đạt 10 triệu USD.", 120000000, "INCOMPLETE_COMPARISON"),
])
def test_contract_errors_are_not_factual_contradictions(text, value, code):
    result = evaluate(text, value)
    assert result.status == "UNVERIFIED"
    assert result.reason_code == code


def test_wrong_metric_mapping_is_not_a_contradiction():
    result = evaluate("Lợi nhuận ròng đạt 100 triệu USD.", 100000000)
    assert result.reason_code == "NUMERIC_SCOPE"


def test_real_same_scope_error_still_contradicted():
    assert evaluate("Doanh thu đạt 100 triệu USD.", 100000000).status == "CONTRADICTED"


def test_matching_number_does_not_prove_irrelevant_quote():
    assert evaluate("Doanh thu đạt 120 triệu USD.").status == "UNVERIFIED"


def test_scoped_numbers_do_not_validate_added_interpretation():
    table = "| Compute & Networking | Graphics | Total\n| (In millions)\nYear Ended Sep 28, 2024\nRevenue | $ | 193,479 | $ | 22,459 | $ | 215,938"
    source = evidence(text=table).model_copy(update={"report_end": END})
    draft = Draft(dimension="financial",
        text="Năm kết thúc 28/09/2024, doanh thu mảng Graphics đạt 22.459 triệu USD, chứng minh triển vọng bền vững.",
        numeric=Numeric(key="revenue", value=22459000000, unit="USD", end=END, period="FY"),
        references=[Reference(evidence_id=source.id, quote=table.splitlines()[-1])])
    result = verify(draft, "C1", "financial", cik=123, as_of=CUT, provided=[source], numbers=[])
    assert result.status == "PARTIALLY_SUPPORTED"
    assert result.reason_code == "PARTIAL_NUMERIC_CHECK"
