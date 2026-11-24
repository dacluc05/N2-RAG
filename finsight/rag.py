from collections import defaultdict
from datetime import date
from functools import lru_cache
import re
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from rank_bm25 import BM25Okapi


def tokens(text):
    return re.findall(r"[^\W_]+",text.casefold())


@lru_cache(maxsize=2)
def embedding(name):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, trust_remote_code=False)


class Hybrid:
    def __init__(self, chunks, as_of: date, cik: int, model: str | None, encoder=None, cache_dir=None):
        unique = {}
        for chunk in chunks:
            if chunk.company_cik == cik and chunk.published and chunk.published <= as_of:
                key = (chunk.content_hash, chunk.report_end or chunk.published)
                prior = unique.get(key)
                if prior is None or (chunk.quality == "primary", chunk.published) > (prior.quality == "primary", prior.published):
                    unique[key] = chunk
        self.chunks = list(unique.values())
        self.sparse = BM25Okapi([tokens(c.text) for c in self.chunks]) if self.chunks else None
        self.dense = None
        self.encode = None
        self.warning = ""
        self.vectors_reused = 0
        self.vectors_created = 0
        if model and self.chunks:
            try:
                import faiss
                self.encode = encoder or embedding(model).encode
                import numpy as np
                cached, missing = {}, []
                folder = Path(cache_dir) / hashlib.sha256(model.encode()).hexdigest()[:24] if cache_dir else None
                if folder: folder.mkdir(parents=True,exist_ok=True)
                for index, chunk in enumerate(self.chunks):
                    key = hashlib.sha256(("v1|"+model+"|"+chunk.text).encode()).hexdigest()
                    target = folder / (key+".npy") if folder else None
                    try:
                        vector = np.load(target,allow_pickle=False) if target and target.is_file() else None
                        if vector is not None and (vector.ndim != 1 or not np.isfinite(vector).all()):
                            vector = None
                    except (OSError,ValueError):
                        vector = None
                    if vector is None: missing.append((index,target))
                    else: cached[index] = vector
                self.vectors_reused = len(cached)
                if missing:
                    fresh = self.encode([self.chunks[i].text for i,_ in missing],normalize_embeddings=True)
                    for (index,target), vector in zip(missing,fresh):
                        cached[index] = vector
                        if target:
                            temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
                            try:
                                with temporary.open("wb") as handle: np.save(handle,vector,allow_pickle=False)
                                os.replace(temporary,target)
                            finally:
                                temporary.unlink(missing_ok=True)
                    self.vectors_created = len(missing)
                vectors = np.asarray([cached[i] for i in range(len(self.chunks))],dtype="float32")
                self.dense = faiss.IndexFlatIP(vectors.shape[1])
                self.dense.add(vectors)
            except Exception as exc:
                self.warning = "FAISS/embedding chưa sẵn sàng. Truy xuất BM25 tiếp tục (" + type(exc).__name__ + ")."
                self.dense = None

    def retrieve(self, query: str, k: int, *, since: date | None = None, kinds=None,
                 quality=None, distinct_periods=False):
        if self.sparse is None:
            return []
        valid = {i for i,c in enumerate(self.chunks) if (since is None or c.published >= since)
                 and (kinds is None or c.kind in kinds) and (quality is None or c.quality == quality)}
        sparse = self.sparse.get_scores(tokens(query))
        ranked_sparse = sorted((i for i in valid if sparse[i] != 0),key=lambda i:(-sparse[i],i))
        ranks = [ranked_sparse]
        if self.dense is not None:
            q = self.encode([query],normalize_embeddings=True)
            _, dense = self.dense.search(q,len(self.chunks))
            ranks.append([int(i) for i in dense[0] if i in valid])
        score = defaultdict(float)
        for ranking in ranks:
            for position,i in enumerate(ranking[:max(k*5,25)],1):
                score[i] += 1/(40+position)
        ordered = sorted(score,key=lambda i:(-score[i]*(1.10 if self.chunks[i].quality=="primary" else 1),i))
        selected, seen = [], set()
        positions = defaultdict(list)
        for i in ordered:
            c = self.chunks[i]
            identity = c.report_end if distinct_periods else c.content_hash
            neighbors = positions[c.document_id]
            words = set(tokens(c.text))
            if identity not in seen and len(neighbors) < 2 and not any(
                abs(c.index - previous.index) <= 1 and len(words & prior_words) >= 0.75 * max(len(words), len(prior_words))
                for previous, prior_words in neighbors
            ):
                selected.append(c)
                seen.add(identity)
                neighbors.append((c, words))
            if len(selected) == k:
                break
        return selected
