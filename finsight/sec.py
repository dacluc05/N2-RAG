from datetime import date
import json
import re

from finsight.schema import Company, Filing
from finsight.transport import Http, ProviderError


class SEC:
    def __init__(self, http: Http, user_agent: str, directory_loader=None):
        self.http = http
        self.attempts = 3
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._directory = None
        self.directory_loader = directory_loader

    def get(self, url: str, operation: str):
        if not re.search(r"[^\s]+@[^\s]+\.[^\s]+", self.headers["User-Agent"]):
            raise ProviderError("SEC", "cần SEC_USER_AGENT gồm tên ứng dụng và email liên hệ")
        raw, _ = self.http.get(url, operation, headers=self.headers, attempts=self.attempts)
        return json.loads(raw)

    def search(self, query: str):
        if self._directory is None:
            def load():
                return self.get("https://www.sec.gov/files/company_tickers_exchange.json", "tickers")

            self._directory = self.directory_loader(load) if self.directory_loader else load()
        fields = self._directory["fields"]
        matches = []
        for row in self._directory["data"]:
            item = dict(zip(fields, row))
            ticker, name = item["ticker"], item["name"]
            if query.casefold() in f"{ticker} {name}".casefold():
                matches.append(Company(ticker=ticker, cik=item["cik"], name=name,
                                       exchange=item.get("exchange") or ""))
        return sorted(matches, key=lambda x: (x.ticker.upper() != query.upper(), x.ticker))[:20]

    def company(self, ticker: str, as_of: date):
        base = next((x for x in self.search(ticker) if x.ticker.upper() == ticker), None)
        if base is None:
            raise ProviderError("SEC", "ticker không có trong danh mục hiện tại")
        url = f"https://data.sec.gov/submissions/CIK{base.cik:010}.json"
        profile = self.get(url, "submissions")
        records = profile["filings"]["recent"]
        filings = self._filings(base.cik, records, as_of)
        if not filings or as_of < min(f.filed for f in filings):
            for archive in profile["filings"].get("files", [])[:12]:
                name = archive["name"]
                if re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name) and archive["filingFrom"] <= str(as_of):
                    filings += self._filings(base.cik, self.get("https://data.sec.gov/submissions/" + name, "archive"), as_of)
                    if filings:
                        break
        company = base.model_copy(update={"sic": str(profile.get("sic", "")),
                                          "industry": profile.get("sicDescription", "")})
        return company, sorted(filings, key=lambda f: f.filed, reverse=True)

    @staticmethod
    def _filings(cik: int, records: dict, as_of: date):
        result = []
        for form, filed, end, acc, name in zip(*(records[key] for key in
                ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument"))):
            if not end and form in {"DEF 14A","8-K"}:
                end = filed
            if (form in {"10-K", "10-Q", "10-K/A", "10-Q/A", "8-K", "DEF 14A", "20-F", "20-F/A", "40-F", "40-F/A"}
                    and end and filed <= str(as_of) and end <= str(as_of)
                    and re.fullmatch(r"\d{10}-\d{2}-\d{6}", acc)
                    and re.fullmatch(r"[\w.-]+", name)):
                result.append(Filing(accession=acc, form=form, filed=filed, end=end,
                    url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{name}"))
        return result

    def facts(self, cik: int):
        return self.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010}.json", "companyfacts")
