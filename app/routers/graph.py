"""/graph 路由 · 议题图谱(节点 + 边)。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import data
from app.schemas import GraphEdge, GraphNode, GraphResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphResponse, summary="议题图谱节点与边")
def get_graph(
    category: Optional[str] = Query(None, description="按 category 过滤节点:经济/教育/科技/环境/社会"),
    min_heat: Optional[int] = Query(None, ge=0, le=100, description="按 heat_score 阈值过滤节点(0-100)"),
) -> GraphResponse:
    """返回图谱节点 + 边。前端用 nodes + edges 渲染 D3.js / ECharts Graph。"""
    issues = data.filter_issues(category=category, min_heat=min_heat)
    if not issues:
        raise HTTPException(status_code=404, detail="无匹配议题(检查 category / min_heat 过滤)")

    issue_ids = {i["id"] for i in issues}
    relations = data.load_relations()
    # 边只在两端节点都命中时保留,避免孤立点引用
    edges = [
        GraphEdge(
            source=r["source"],
            target=r["target"],
            relation=r["relation"],
            weight=r["weight"],
        )
        for r in relations
        if r["source"] in issue_ids and r["target"] in issue_ids
    ]
    nodes = [
        GraphNode(
            id=i["id"],
            name=i["name"],
            category=i["category"],
            heat_score=i.get("heat_score", 0),
        )
        for i in issues
    ]
    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "filter": {"category": category, "min_heat": min_heat},
    }
    return GraphResponse(nodes=nodes, edges=edges, stats=stats)
