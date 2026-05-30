"""KnowledgeAgent：RAG 检索 + 引用答案。

调用链：query_rewriter → hybrid_retrieve → rerank → answer。
W1 落地点：流式答案 + 引用块通过 SSE 透传给前端。
W4 增强：语义缓存命中时直接返回，跳过 RAG 全链路。
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from rag import answer_generator, query_rewriter, reranker, retriever
from agents.state import AgentState
from llm.semantic_cache import get_cache
from tracing.observe import observe

logger = logging.getLogger(__name__)


@observe(name="knowledge_agent.retrieve", capture_input=False)
async def _retrieve_for_state(state: AgentState) -> list[retriever.Chunk]:
    """多 query 召回 + 合并 + 重排。"""
    msgs = state.get("messages") or []
    query = ""
    for m in reversed(msgs):
        if m.get("role") == "user":
            query = str(m.get("content", ""))
            break
    if not query:
        return []

    queries = await query_rewriter.rewrite(query, n=2)
    pool: dict[str, retriever.Chunk] = {}
    for q in queries:
        for chunk in retriever.hybrid_retrieve(
            query=q, tenant_id=state.get("tenant_id")
        ):
            pool.setdefault(chunk.chunk_id or f"{chunk.doc_id}-{hash(chunk.chunk_text)}", chunk)
    candidates = list(pool.values())
    return reranker.rerank(query=query, chunks=candidates)


@observe(name="knowledge_agent.run", capture_input=False)
async def run_knowledge_agent(state: AgentState) -> AgentState:
    """非流式节点：把答案与引用写回 state，便于评测调用。"""
    msgs = state.get("messages") or []
    query = next(
        (m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), ""
    )
    query = str(query)

    cache = get_cache()
    cached = await cache.get(query)
    if cached is not None:
        logger.debug("knowledge_agent cache HIT for query=%s", query[:40])
        return AgentState(answer=cached, citations=[], retrieved_chunks=[])

    chunks = await _retrieve_for_state(state)
    result = await answer_generator.answer_oneshot(query=query, chunks=chunks)

    await cache.set(query, result["answer"])

    return AgentState(
        answer=result["answer"],
        citations=result["citations"],
        retrieved_chunks=[c.model_dump() for c in chunks],
    )


async def stream_knowledge(
    state: AgentState,
) -> AsyncIterator[answer_generator.AnswerEvent]:
    """流式入口：用于 /api/v1/chat SSE。每个事件转 SSE event。"""
    msgs = state.get("messages") or []
    query = str(
        next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")
    )

    cache = get_cache()
    cached = await cache.get(query)
    if cached is not None:
        logger.debug("stream_knowledge cache HIT")
        yield answer_generator.AnswerEvent(
            type="agent_step",
            data={"agent": "knowledge", "cache_hit": True, "retrieval_count": 0},
        )
        yield answer_generator.AnswerEvent(type="token", data={"text": cached})
        yield answer_generator.AnswerEvent(
            type="done", data={"citations": 0, "cache_hit": True},
        )
        return

    chunks = await _retrieve_for_state(state)
    yield answer_generator.AnswerEvent(
        type="agent_step",
        data={
            "agent": "knowledge",
            "cache_hit": False,
            "retrieval_count": len(chunks),
        },
    )

    full_answer: list[str] = []
    async for ev in answer_generator.stream_answer(query=query, chunks=chunks):
        if ev.type == "token":
            full_answer.append(str(ev.data.get("text", "")))
        yield ev

    if full_answer and query.strip():
        await cache.set(query, "".join(full_answer))


__all__ = ["run_knowledge_agent", "stream_knowledge"]
