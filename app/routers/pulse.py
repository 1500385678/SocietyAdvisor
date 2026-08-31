"""/pulse 路由 · 舆情切片(Phase 0 #4 第二步:真实读取 pulse_snapshots.yaml)。

接口契约:
  GET /pulse?issue_id=issue-001                 返回该议题全部快照
  GET /pulse?issue_id=issue-001&source=hybrid   按 source 过滤
  GET /pulse?issue_id=issue-999                 404 议题不存在

数据源:data/pulse_snapshots.yaml(Phase 0 全部为 hybrid 模拟值)
字段规范:data/pulse_snapshots.schema.md v1.0
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import data
from app.schemas import PulseAggregate, PulseSeries, PulseSnapshot

router = APIRouter(prefix="/pulse", tags=["pulse"])


@router.get("", response_model=PulseSeries, summary="舆情切片(单议题多源聚合)")
def get_pulse(
    issue_id: str = Query(..., description="议题 id,如 issue-005"),
    source: Optional[str] = Query(None, description="按 source 过滤:news/weibo/zhihu/wechat/hybrid"),
) -> PulseSeries:
    """返回单议题的舆情时间序列 + 聚合(总声量 / 平均情感)。"""
    idx = data.issue_index()
    issue = idx.get(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"议题不存在: {issue_id}")

    raw = data.filter_pulse_snapshots(issue_id=issue_id, source=source)
    snapshots = [PulseSnapshot(**s) for s in raw]

    # 聚合:总声量 + 简单算术平均(各源等权)
    if snapshots:
        total_volume = sum(s.volume for s in snapshots)
        n = len(snapshots)
        avg_pos = round(sum(s.sentiment_pos for s in snapshots) / n, 4)
        avg_neu = round(sum(s.sentiment_neu for s in snapshots) / n, 4)
        avg_neg = round(sum(s.sentiment_neg for s in snapshots) / n, 4)
        date_range = {
            "start": snapshots[0].snapshot_date,
            "end": snapshots[-1].snapshot_date,
        }
    else:
        total_volume = 0
        avg_pos = avg_neu = avg_neg = 0.0
        date_range = {"start": None, "end": None}

    aggregate = PulseAggregate(
        snapshot_count=len(snapshots),
        total_volume=total_volume,
        avg_sentiment_pos=avg_pos,
        avg_sentiment_neu=avg_neu,
        avg_sentiment_neg=avg_neg,
        date_range=date_range,
    )

    return PulseSeries(
        issue_id=issue_id,
        issue_name=issue["name"],
        snapshots=snapshots,
        aggregate=aggregate,
        filter={"source": source},
    )
