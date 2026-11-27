"""Local multilingual encoder for the existing repository and its derived indexes.

Model assets are selected on the host. No network fallback or model code execution.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path


class LocalEncoder:
    def __init__(self, model: Path, tokenizer: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(
            max_length=128
        )  # MiniLM sentence-transformers profile
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>") or 0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(
            os.environ.get("KURO_MEMORY_ENCODER_THREADS", "1")
        )
        self.session = ort.InferenceSession(
            str(model), sess_options=options, providers=["CPUExecutionProvider"]
        )
        digest = hashlib.sha256(b"masked-mean-v1")
        for path in (model, tokenizer):
            with path.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)
        self.revision = digest.hexdigest()

    def encode(self, texts):
        import numpy as np

        tokens = self.tokenizer.encode_batch(texts)
        inputs = {
            "input_ids": [t.ids for t in tokens],
            "attention_mask": [t.attention_mask for t in tokens],
            "token_type_ids": [t.type_ids for t in tokens],
        }
        feeds = {
            i.name: np.asarray(inputs[i.name], dtype=np.int64)
            for i in self.session.get_inputs()
        }
        hidden = self.session.run(None, feeds)[0]
        mask = feeds["attention_mask"][:, :, None]
        pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
        return (
            pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
        ).astype("<f4")


@lru_cache(maxsize=1)
def _load(model, tokenizer, stamps):
    return LocalEncoder(model, tokenizer)


def local_encoder():
    configured = os.getenv("KURO_MEMORY_ENCODER_DIR")
    if not configured:
        return None
    root = Path(configured).resolve()
    model, tokenizer = root / "model_quint8_avx2.onnx", root / "tokenizer.json"
    try:
        return _load(
            model,
            tokenizer,
            (
                model.stat().st_mtime_ns,
                tokenizer.stat().st_mtime_ns,
                os.getenv("KURO_MEMORY_ENCODER_THREADS"),
            ),
        )
    except Exception as exc:
        from loguru import logger

        logger.warning(
            "Local semantic encoder unavailable ({}); lexical retrieval active",
            type(exc).__name__,
        )
        return None


def vector_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS semantic_vectors(
            owner TEXT, id TEXT, revision TEXT, vector BLOB,
            PRIMARY KEY(owner,id));
        CREATE TABLE IF NOT EXISTS semantic_terms(
            owner TEXT, term INTEGER, id TEXT, PRIMARY KEY(owner,term,id));
        CREATE INDEX IF NOT EXISTS semantic_terms_id ON semantic_terms(owner,id);
    """)


def _terms(vector):
    import numpy as np

    # Signed largest coordinates form an inverted candidate index. Exact cosine reranks candidates.
    axes = np.argsort(-np.abs(vector), kind="stable")[:24]
    return [int(axis + 1) * (1 if vector[axis] >= 0 else -1) for axis in axes]


def remove_vector(conn, owner, identity):
    conn.execute("DELETE FROM semantic_terms WHERE owner=? AND id=?", (owner, identity))
    conn.execute(
        "DELETE FROM semantic_vectors WHERE owner=? AND id=?", (owner, identity)
    )


def put_vector(conn, owner, identity, encoder, vector):
    remove_vector(conn, owner, identity)
    conn.execute(
        "INSERT INTO semantic_vectors VALUES(?,?,?,?)",
        (owner, identity, encoder.revision, vector.tobytes()),
    )
    conn.executemany(
        "INSERT INTO semantic_terms VALUES(?,?,?)",
        ((owner, term, identity) for term in _terms(vector)),
    )


def vector_hits(
    conn, owner, encoder, query, threshold, limit, *, eligible_sql="", eligible_args=()
):
    import numpy as np

    vector = encoder.encode([query])[0]
    terms = _terms(vector)
    placeholders = ",".join("?" for _ in terms)
    # Weight rare coordinates: repetitive day-to-day exchanges may share most
    # high-amplitude dimensions. Read only posting keys until scope and ranking
    # yield a candidate list; each float vector is fetched once per finalist.
    frequencies = conn.execute(
        f"SELECT term,count(*) FROM semantic_terms WHERE owner=? AND term IN ({placeholders}) GROUP BY term",
        (owner, *terms),
    )
    weighted = [(term, 1.0 / count**0.5) for term, count in frequencies]
    if not weighted:
        return {}
    values = ",".join("(?,?)" for _ in weighted)
    rows = conn.execute(
        f"""
        WITH weights(term,weight) AS (VALUES {values}),
        overlap AS MATERIALIZED (
            SELECT s.id,sum(w.weight) AS strength FROM weights w
            CROSS JOIN semantic_terms s ON s.owner=? AND s.term=w.term GROUP BY s.id
        ), eligible AS MATERIALIZED (
            SELECT s.id FROM overlap s WHERE 1=1 {eligible_sql}
            ORDER BY s.strength DESC,s.id LIMIT ?
        )
        SELECT v.id,v.vector FROM eligible e CROSS JOIN semantic_vectors v
          ON v.owner=? AND v.id=e.id AND v.revision=?
        """,
        (
            *[value for pair in weighted for value in pair],
            owner,
            *eligible_args,
            limit,
            owner,
            encoder.revision,
        ),
    )
    scores = [
        (identity, float(np.frombuffer(blob, dtype="<f4") @ vector))
        for identity, blob in rows
    ]
    return {identity: score for identity, score in scores if score >= threshold}
