"""Pydantic 响应模型 · 与 data/*.schema.md v1.0 字段保持一致。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RelationType = Literal["cause", "influence", "related"]


class Issue(BaseModel):
    id: str
    name: str
    category: str
    description: str
    tags: list[str] = Field(default_factory=list)
    heat_score: int = 0
    created_at: str


class IssueRelation(BaseModel):
    source: str
    target: str
    relation: RelationType
    weight: float
    note: str = ""
    created_at: str = ""


class GraphNode(BaseModel):
    id: str
    name: str
    category: str
    heat_score: int = 0


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: RelationType
    weight: float


class GraphResponse(BaseModel):
    """议题图谱节点 + 边,前端 D3.js / ECharts 直接渲染。"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: dict


class PulseStub(BaseModel):
    """Phase 0 阶段 /pulse 桩,等待 Phase 1 接入真实舆情源(微博/知乎/新闻 API)。"""

    issue_id: str
    issue_name: str
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "舆情快照灌库尚未启动,见 项目开发计划.md Phase 0 #4(历史舆情快照灌库)"
