"""Pydantic 响应模型 · 与 data/*.schema.md v1.0 字段保持一致。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RelationType = Literal["cause", "influence", "related"]
PulseSource = Literal["news", "weibo", "zhihu", "wechat", "hybrid"]


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


class PulseSnapshot(BaseModel):
    """单条舆情快照 · 字段对齐 `data/pulse_snapshots.schema.md` v1.0。"""

    issue_id: str
    source: PulseSource
    volume: int = Field(ge=0, description="当日声量(条/篇),0 = 无新增")
    sentiment_pos: float = Field(ge=0.0, le=1.0)
    sentiment_neu: float = Field(ge=0.0, le=1.0)
    sentiment_neg: float = Field(ge=0.0, le=1.0)
    snapshot_date: str = Field(description="YYYY-MM-DD")
    source_url: Optional[str] = None
    note: Optional[str] = None


class PulseAggregate(BaseModel):
    """多快照聚合:总声量 + 平均情感(三段)。"""

    snapshot_count: int
    total_volume: int
    avg_sentiment_pos: float
    avg_sentiment_neu: float
    avg_sentiment_neg: float
    date_range: dict  # {start, end}


class PulseSeries(BaseModel):
    """单议题舆情时间序列 · /pulse 路由主返回。"""

    issue_id: str
    issue_name: str
    snapshots: list[PulseSnapshot]
    aggregate: PulseAggregate
    filter: dict  # {source} 回显,便于前端调试


class PulseStub(BaseModel):
    """Phase 0 阶段 /pulse 桩,等待 Phase 1 接入真实舆情源(微博/知乎/新闻 API)。

    Phase 0 #4 收尾后已切换为 PulseSeries;此模型仅保留作为兜底契约文档。
    """

    issue_id: str
    issue_name: str
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "舆情快照灌库尚未启动,见 项目开发计划.md Phase 0 #4(历史舆情快照灌库)"
