"""SocietyAdvisor FastAPI 入口。

Phase 0 骨架(6/6 已收尾,9/1 T5 周期 #4 第二步完成 /pulse 真实读取):
  GET /graph   议题图谱(节点 + 边)        - working
  GET /pulse   舆情切片(单议题多源聚合)   - working(读 pulse_snapshots.yaml)
  GET /health  健康检查

启动:uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.routers import graph, pulse

app = FastAPI(
    title="SocietyAdvisor API",
    version=__version__,
    description="09-社会-Society 行业顾问 API · Phase 0 收尾(6/6)",
)
app.include_router(graph.router)
app.include_router(pulse.router)


@app.get("/health", tags=["meta"], summary="健康检查")
def health() -> dict:
    return {"status": "ok", "version": __version__}
