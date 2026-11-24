import random
import time
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock

import httpx


class ProviderError(Exception):
    def __init__(self, provider: str, category: str):
        self.category = category
        super().__init__(f"{provider}: {category}")


class DocumentRedirect(ProviderError):
    def __init__(self, provider: str, code: int, location: str):
        super().__init__(provider, f"HTTP {code}")
        self.location = location


class Budget:
    def __init__(self, seconds: int, searches: int, model_calls: int):
        self.deadline = time.monotonic() + seconds
        self.searches = searches
        self.model_calls = model_calls
        self.counts = Counter()

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("Phiên phân tích", "hết thời gian")
        return remaining

    def charge(self, provider: str, operation: str):
        self.remaining()
        bucket = "search" if provider in ("Brave", "DDGS") else "model" if provider == "Gemini" else None
        maximum = {"search": self.searches, "model": self.model_calls}.get(bucket)
        if bucket and self.counts[bucket] >= maximum:
            raise ProviderError(provider, "hết ngân sách")
        if bucket:
            self.counts[bucket] += 1
        self.counts[f"{provider}:{operation}"] += 1


class Rate:
    def __init__(self, requests_per_second: float):
        self.interval = 1 / requests_per_second
        self.next = 0.
        self.lock = Lock()

    def wait(self, budget: Budget):
        with self.lock:
            delay = max(0., self.next - time.monotonic())
            if delay >= budget.remaining():
                raise ProviderError("HTTP", "hết thời gian")
            time.sleep(delay)
            self.next = time.monotonic() + self.interval


class Http:
    def __init__(self, client: httpx.Client, budget: Budget, rate: Rate, provider: str, timeout: int):
        self.client = client
        self.budget = budget
        self.rate = rate
        self.provider = provider
        self.timeout = timeout

    def get(self, url: str, operation: str, *, params=None, headers=None, max_bytes=45_000_000, attempts=3, report_redirect=False):
        category = "không kết nối được"
        for attempt in range(attempts):
            self.rate.wait(self.budget)
            self.budget.charge(self.provider, operation)
            retry_after = 0.
            try:
                with self.client.stream("GET", url, params=params, headers=headers,
                                        timeout=min(self.timeout, self.budget.remaining()),
                                        follow_redirects=False) as response:
                    code = response.status_code
                    if code == 200:
                        buffer = bytearray()
                        for block in response.iter_bytes(chunk_size=32768):
                            self.budget.remaining()
                            buffer.extend(block)
                            if len(buffer) > max_bytes:
                                raise ProviderError(self.provider, "phản hồi vượt giới hạn")
                        return bytes(buffer), response.headers
                    if report_redirect and code in (301, 302, 303, 307, 308):
                        raise DocumentRedirect(self.provider, code, response.headers.get("location", ""))
                    if code in (401, 403):
                        raise ProviderError(self.provider, f"quyền truy cập hoặc xác thực ({code})")
                    if code != 429 and code not in (500, 502, 503, 504):
                        raise ProviderError(self.provider, f"HTTP {code}")
                    category = f"giới hạn tốc độ ({code})" if code == 429 else f"lỗi máy chủ ({code})"
                    raw = response.headers.get("retry-after", "")
                    try:
                        retry_after = max(0., float(raw))
                    except ValueError:
                        try:
                            retry_after = max(0., (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            retry_after = 0.
            except httpx.HTTPError:
                category = "lỗi kết nối hoặc timeout"
            if attempt + 1 < attempts:
                delay = max(retry_after, .4 * 2 ** attempt + random.uniform(0, .15))
                if delay >= self.budget.remaining():
                    break
                time.sleep(delay)
        raise ProviderError(self.provider, category)
