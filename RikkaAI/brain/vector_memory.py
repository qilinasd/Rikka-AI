"""
RikkaAI - 向量记忆检索（ChromaDB + 本地 n-gram 哈希向量，零下载离线可用）

ChromaDB 默认 embedding 要下载 79MB ONNX 模型，国内网络不可行。
这里用本地字符 n-gram 哈希向量做轻量语义 embedding（256 维），
ChromaDB 只承担向量存储与相似度检索，完全离线。

设计：
- 自己在外面算好向量，经 embeddings= 参数直接传给 ChromaDB（绕开其
  EmbeddingFunction 接口的版本兼容问题）
- 碎片入库时同步写入向量库（id = 碎片 id）
- 检索时 query 向量 → 返回相近碎片 id 列表
- 与 memory_vault.search 的 FTS/关键词结果做 RRF 融合（第三路召回）
"""

import hashlib
import os
import threading

import config

_DIM = 256
_COLLECTION = "rikka_memories"
_lock = threading.Lock()


def _ngram_embed(text: str, dim: int = _DIM):
    """字符 n-gram 哈希向量：对 1/2/3-gram 做确定性哈希投影到 dim 维，L2 归一化。
    中文按字符切分，英文按单词切分，兼顾语义相似与离线零下载。"""
    import re as _re
    vec = [0.0] * dim
    t = str(text or "")
    tokens = _re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", t)
    ngrams = []
    ngrams.extend(tokens)
    ngrams.extend(tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1))
    ngrams.extend(tokens[i] + tokens[i + 1] + tokens[i + 2] for i in range(len(tokens) - 2))
    for g in ngrams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _get_collection():
    import chromadb
    db_dir = os.path.join(config.USER_CONFIG_DIR, "chroma")
    os.makedirs(db_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=db_dir)
    return client.get_or_create_collection(
        _COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def add_fragment(fragment_id, text, entity=""):
    """碎片入库 → 同步写入向量库。失败静默（向量检索是增强，不能阻断主流程）。"""
    try:
        doc = f"{entity} {text}".strip()
        vec = _ngram_embed(doc)
        with _lock:
            col = _get_collection()
            col.upsert(ids=[str(fragment_id)], embeddings=[vec], documents=[doc])
    except Exception:
        pass


def add_fragments_batch(items):
    """批量写入：items = [(id, text, entity), ...]"""
    try:
        if not items:
            return
        ids = [str(i) for i, _, _ in items]
        docs = [f"{e} {t}".strip() for _, t, e in items]
        vecs = [_ngram_embed(d) for d in docs]
        with _lock:
            col = _get_collection()
            col.upsert(ids=ids, embeddings=vecs, documents=docs)
    except Exception:
        pass


def delete_fragment(fragment_id):
    try:
        with _lock:
            col = _get_collection()
            col.delete(ids=[str(fragment_id)])
    except Exception:
        pass


def search(query: str, top_k: int = 5) -> list:
    """向量检索：返回 [{fragment_id, distance, text}]，无结果返回 []。"""
    try:
        qvec = _ngram_embed(str(query))
        with _lock:
            col = _get_collection()
            res = col.query(query_embeddings=[qvec], n_results=top_k)
            ids = res.get("ids", [[]])[0]
            docs = res.get("documents", [[]])[0]
            dists = res.get("distances", [[]])[0] if res.get("distances") else [None] * len(ids)
            out = []
            for i, fid in enumerate(ids):
                if fid is None:
                    continue
                out.append({
                    "fragment_id": int(fid),
                    "distance": dists[i] if i < len(dists) else None,
                    "text": docs[i] if i < len(docs) else "",
                })
            return out
    except Exception:
        return []


def health() -> dict:
    """向量库健康状态（供调试）。"""
    try:
        with _lock:
            col = _get_collection()
            return {"ok": True, "count": col.count(), "collection": _COLLECTION}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
