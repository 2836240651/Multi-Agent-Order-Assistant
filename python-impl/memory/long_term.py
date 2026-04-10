"""
长期记忆 — 基于向量数据库的持久化记忆
存储用户画像、历史工单、知识库文档等需要持久化的信息。
支持语义相似度检索，用于RAG知识检索Agent。
"""

from __future__ import annotations

import hashlib
import json
import jieba
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

_SentenceTransformer = None

RFF_K = 60

_STOP_WORDS = {
    # 标点符号
    "，", "。", "！", "？", "、", "；", "：", "「", "」", "『", "』",
    "【", "】", "〔", "〕", "《", "》", "〈", "〉", "〖", "〗", "～",
    "'", '"', "'", '"', "'", "'''", "'''", "…", "—", "～", "·",
    ",", ".", "!", "?", ";", ":", "'", '"', "(", ")", "[", "]", "{", "}",
    "-", "–", "—", "~", "|", "/", "\\", "@", "#", "$", "%", "^", "&", "*",
    "+", "=", "<", ">", "®", "©", "™",

    # 常用助词
    "的", "了", "着", "过", "呢", "吗", "吧", "啊", "呀", "嘛",
    "哦", "呢", "哈", "呐", "呃", "嗯", "噢", "哼", "喔", "嗨",
    "之", "乎", "者", "所", "为", "而", "于", "则", "且", "或",

    # 常用虚词
    "是", "有", "在", "和", "与", "或", "但", "而", "却", "则",
    "对", "把", "被", "让", "给", "向", "从", "到", "由", "按",
    "因", "为", "由", "于", "通过", "经过", "根据", "依据", "按照",

    # 常见动词/形容词（检索意义弱）
    "会", "能", "可以", "请", "让", "要", "想", "得", "该", "应",
    "能够", "应该", "必须", "需要", "希望", "认为", "觉得", "知道",
    "没有", "不是", "没有", "不", "没", "莫", "别", "勿", "未",
    "很", "都", "也", "还", "又", "再", "已", "已经", "曾", "曾经",
    "将", "将要", "会", "将", "正", "正在", "在", "着", "了",

    # 数词和量词（单独出现时意义弱）
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "百", "千", "万", "亿", "个", "件", "次", "位", "元", "期",
    "第一", "第二", "第三", "首先", "然后", "接着", "最后",

    # 指示代词
    "这", "那", "这", "这些", "那些", "此", "其", "该", "各",
    "某", "本", "自己", "本人", "自己", "咱们", "我们", "你们",

    # 疑问词
    "什么", "怎么", "如何", "为什么", "为何", "哪", "哪个", "哪些",
    "哪里", "哪儿", "谁", "多少", "几", "怎样", "怎么样",

    # 时间词
    "现在", "目前", "当前", "今天", "明天", "昨天", "今年", "明年",
    "去年", "这时", "那时", "随时", "经常", "有时", "偶尔",

    # 常见名词（泛化词）
    "情况", "问题", "事情", "事物", "东西", "事儿", "问题", "事项",
    "方面", "部分", "相关", "有关", "一种", "一些",

    # 语气词
    "吧", "吗", "呢", "啊", "呀", "哦", "噢", "呢", "呐", "呃",

    # 方位词
    "上", "下", "左", "右", "前", "后", "里", "外", "中", "内",

    # 连接词
    "而且", "并且", "以及", "还有", "以及", "或者", "或者说",

    # 常用副词
    "非常", "特别", "十分", "极其", "相当", "比较", "稍微", "略微",
    "完全", "绝对", "一定", "必须", "应当", "本来", "原来", "果然",

    # 常用介词
    "关于", "对于", "至于", "由于", "鉴于", "根据", "按照", "依据",
}




def _get_sentence_transformer():
    global _SentenceTransformer
    if _SentenceTransformer is None:
        try:
            from sentence_transformers import SentenceTransformer
            _SentenceTransformer = SentenceTransformer
        except ImportError:
            _SentenceTransformer = False
    return _SentenceTransformer


class LongTermMemory:
    """
    长期记忆：基于FAISS向量检索 + BM25关键词检索的混合搜索。

    特点：
    - 混合搜索：向量语义检索 + BM25关键词检索 + RRF合并
    - 持久化到磁盘，跨会话保持
    - 支持增量更新和批量导入
    - 生产环境可切换为Milvus/Pinecone

    搜索流程：
    1. 向量搜索 (top_k retrieval)
    2. BM25搜索 (top_k retrieval)
    3. RRF合并两个排序结果
    """

    def __init__(
        self,
        index_path: str = "./vector_store/faiss_index",
        embedding_dim: int = 384,
    ):
        self.index_path = Path(index_path)
        self.embedding_dim = embedding_dim
        self._documents: list[dict[str, Any]] = []
        self._index = None
        self._model = None
        self._bm25: BM25Okapi | None = None
        self._bm25_corpus: list[list[str]] = []

        st_cls = _get_sentence_transformer()
        if st_cls:
            self._model = st_cls("paraphrase-multilingual-MiniLM-L12-v2")
        self._init_index()

    def _init_index(self):
        """初始化FAISS索引"""
        if faiss is None:
            self._index = None
            return

        metadata_path = self.index_path.with_suffix(".meta.json")
        if self.index_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
                if metadata_path.exists():
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        self._documents = json.load(f)
                self._rebuild_bm25()
            except Exception:
                self._index = faiss.IndexFlatIP(self.embedding_dim)
        else:
            self._index = faiss.IndexFlatIP(self.embedding_dim)

    def _tokenize(self, text: str) -> list[str]:
        """中文分词（过滤停用词和单字）"""
        tokens = jieba.cut(text)
        return [
            t for t in tokens
            if t not in _STOP_WORDS and len(t) > 1
        ]

    def _rebuild_bm25(self):
        """重建BM25索引"""
        if not _BM25_AVAILABLE or not self._documents:
            return
        corpus = [doc["content"] for doc in self._documents]
        tokenized_corpus = [self._tokenize(doc) for doc in corpus]
        self._bm25 = BM25Okapi(tokenized_corpus)
        self._bm25_corpus = tokenized_corpus

    def _get_embedding(self, text: str) -> np.ndarray:
        """
        使用 sentence-transformers 获取文本向量。
        生产环境可替换为 OpenAI Embedding API 或本地模型。
        """
        if self._model is not None:
            vec = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return vec.astype(np.float32)
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        np.random.seed(int(text_hash[:8], 16) % (2**32))
        vec = np.random.randn(self.embedding_dim).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec

    def add_document(self, content: str, source: str = "", metadata: dict | None = None) -> str:
        """添加文档到向量库"""
        doc_id = hashlib.md5(content.encode()).hexdigest()[:12]

        doc = {
            "id": doc_id,
            "content": content,
            "source": source,
            "metadata": metadata or {},
        }
        self._documents.append(doc)

        if self._index is not None:
            embedding = self._get_embedding(content)
            self._index.add(embedding.reshape(1, -1))

        if _BM25_AVAILABLE:
            if self._bm25 is None:
                self._bm25_corpus = [self._tokenize(d["content"]) for d in self._documents]
                self._bm25 = BM25Okapi(self._bm25_corpus)
            else:
                self._bm25_corpus.append(self._tokenize(content))
                self._bm25 = BM25Okapi(self._bm25_corpus)

        return doc_id

    def add_documents_batch(self, documents: list[dict]) -> list[str]:
        """批量添加文档"""
        doc_ids = []
        for doc in documents:
            doc_id = self.add_document(
                content=doc.get("content", ""),
                source=doc.get("source", ""),
                metadata=doc.get("metadata", {}),
            )
            doc_ids.append(doc_id)
        return doc_ids

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义相似度检索（仅向量）"""
        if self._index is None or not self._documents:
            return self._fallback_search(query, top_k)

        query_vec = self._get_embedding(query).reshape(1, -1)
        scores, indices = self._index.search(query_vec, min(top_k, len(self._documents)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._documents):
                continue
            doc = self._documents[idx].copy()
            doc["score"] = float(score)
            results.append(doc)

        return results

    def search_bm25(self, query: str, top_k: int = 20) -> list[dict]:
        """BM25关键词检索"""
        if self._bm25 is None or not self._documents:
            return self._fallback_search(query, top_k)

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        doc_scores = [(i, float(score)) for i, score in enumerate(scores) if score > 0]
        doc_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in doc_scores[:top_k]:
            if idx < len(self._documents):
                doc = self._documents[idx].copy()
                doc["score"] = score
                results.append(doc)

        return results

    def search_hybrid(self, query: str, top_k: int = 5, vector_weight: float = 0.5) -> list[dict]:
        """
        混合搜索：向量检索 + BM25 + RRF合并

        Args:
            query: 查询文本
            top_k: 最终返回的文档数
            vector_weight: 向量搜索权重 (0-1)，BM25权重为 1 - vector_weight

        Returns:
            合并后的文档列表，按RRF分数排序
        """
        retrieval_k = max(top_k * 2, 20)

        vector_results = self.search(query, top_k=retrieval_k)
        bm25_results = self.search_bm25(query, top_k=retrieval_k)

        if not vector_results and not bm25_results:
            return self._fallback_search(query, top_k)

        rrf_scores: dict[int, float] = {}

        for rank, doc in enumerate(vector_results):
            doc_id = doc.get("id")
            if doc_id is None:
                continue
            key = self._get_doc_key(doc_id)
            if key not in rrf_scores:
                rrf_scores[key] = 0.0
            rrf_scores[key] += vector_weight * (1.0 / (RFF_K + rank + 1))

        for rank, doc in enumerate(bm25_results):
            doc_id = doc.get("id")
            if doc_id is None:
                continue
            key = self._get_doc_key(doc_id)
            if key not in rrf_scores:
                rrf_scores[key] = 0.0
            rrf_scores[key] += (1 - vector_weight) * (1.0 / (RFF_K + rank + 1))

        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        results = []
        for key in sorted_keys[:top_k]:
            doc = self._documents[key].copy()
            doc["score"] = rrf_scores[key]
            doc["vector_score"] = next(
                (d["score"] for d in vector_results if self._get_doc_key(d.get("id")) == key),
                None
            )
            doc["bm25_score"] = next(
                (d["score"] for d in bm25_results if self._get_doc_key(d.get("id")) == key),
                None
            )
            results.append(doc)

        return results

    def _get_doc_key(self, doc_id: str | None) -> int:
        """根据doc_id获取文档索引"""
        if doc_id is None:
            return -1
        for i, doc in enumerate(self._documents):
            if doc.get("id") == doc_id:
                return i
        return -1

    def _fallback_search(self, query: str, top_k: int) -> list[dict]:
        """当FAISS不可用时的关键词回退搜索"""
        scored = []
        query_terms = set(query.lower().split())

        for doc in self._documents:
            content_lower = doc["content"].lower()
            score = sum(1 for term in query_terms if term in content_lower)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def save(self):
        """持久化索引到磁盘"""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        if self._index is not None:
            faiss.write_index(self._index, str(self.index_path))

        metadata_path = self.index_path.with_suffix(".meta.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self._documents, f, ensure_ascii=False, indent=2)

    def load_knowledge_base(self, kb_dir: str) -> int:
        """从目录批量加载知识库文档"""
        kb_path = Path(kb_dir)
        if not kb_path.exists():
            return 0

        count = 0
        for file_path in kb_path.glob("**/*.txt"):
            content = file_path.read_text(encoding="utf-8")
            chunks = self._chunk_text(content)
            for chunk in chunks:
                self.add_document(
                    content=chunk,
                    source=str(file_path.name),
                    metadata={"file": str(file_path)},
                )
                count += 1

        return count

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 128) -> list[str]:
        """
        文本分块：固定长度 + 重叠窗口。
        优先按段落分割，段落过长则按句子分割。
        """
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    current_chunk = overlap_text + para + "\n\n"
                else:
                    sentences = para.replace("。", "。\n").replace(".", ".\n").split("\n")
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        if len(current_chunk) + len(sentence) <= chunk_size:
                            current_chunk += sentence
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:chunk_size]]
