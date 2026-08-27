"""/pulse 路由 · 舆情切片(Phase 0 桩,待 Phase 0 #4 完成灌库后实现)。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import data
from app.schemas import PulseStub

router = APIRouter(prefix="/pulse", tags=["pulse"])


@router.get("", response_model=PulseStub, summary="舆情切片(Phase 0 桩)")
def get_pulse(issue_id: str = Query(..., description="议题 id,如 issue-005")) -> PulseStub:
    """Phase 0 阶段返回 not_implemented;Phase 0 #4 历史舆情快照灌库完成后切换为真实声量/情感数据。"""
    idx = data.issue_index()
    issue = idx.get(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"议题不存在: {issue_id}")
    return PulseStub(issue_id=issue_id, issue_name=issue["name"])
