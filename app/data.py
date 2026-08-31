"""数据加载层 · 复用 md_to_json.py 的 YAML 源,启动期加载 + 简单缓存。

Phase 0 阶段数据量小(issues ≤ 30,relations ≤ 100, snapshots ≤ 200),直接全量载入内存,
后续 SQLite 灌库完成切换为 SQLAlchemy 即可,接口签名保持稳定。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

# 项目根目录 = data/ 的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ISSUES_PATH = PROJECT_ROOT / "data" / "issues.yaml"
RELATIONS_PATH = PROJECT_ROOT / "data" / "issue_relations.yaml"
PULSE_SNAPSHOTS_PATH = PROJECT_ROOT / "data" / "pulse_snapshots.yaml"


def _coerce_pulse_snapshot(s: dict) -> dict:
    """YAML 把 YYYY-MM-DD 解析为 datetime.date,统一转回 ISO 字符串以匹配 schema。"""
    out = dict(s)
    d = out.get("snapshot_date")
    if hasattr(d, "isoformat"):
        out["snapshot_date"] = d.isoformat()
    return out


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_issues() -> list[dict]:
    """加载议题列表,首次调用后缓存。"""
    data = _load_yaml(ISSUES_PATH)
    return data.get("issues", []) if data else []


@lru_cache(maxsize=1)
def load_relations() -> list[dict]:
    """加载议题关系列表,首次调用后缓存。"""
    data = _load_yaml(RELATIONS_PATH)
    return data.get("relations", []) if data else []


@lru_cache(maxsize=1)
def load_pulse_snapshots() -> list[dict]:
    """加载舆情快照列表,首次调用后缓存。

    字段对齐 `data/pulse_snapshots.schema.md` v1.0:
    issue_id / source / volume / sentiment_pos / sentiment_neu / sentiment_neg / snapshot_date / source_url / note
    """
    data = _load_yaml(PULSE_SNAPSHOTS_PATH)
    raw = data.get("snapshots", []) if data else []
    return [_coerce_pulse_snapshot(s) for s in raw]


def filter_pulse_snapshots(
    issue_id: str,
    source: Optional[str] = None,
) -> list[dict]:
    """按 issue_id(必填) + source(可选) 过滤舆情快照。

    返回按 snapshot_date 升序排列(便于前端画时间序列)。
    """
    items = [s for s in load_pulse_snapshots() if s.get("issue_id") == issue_id]
    if source:
        items = [s for s in items if s.get("source") == source]
    return sorted(items, key=lambda s: s.get("snapshot_date", ""))


def issue_index() -> dict[str, dict]:
    """id → issue 索引,供 /graph /pulse 反查。"""
    return {i["id"]: i for i in load_issues()}


def filter_issues(category: Optional[str] = None, min_heat: Optional[int] = None) -> list[dict]:
    """按 category / heat_score 过滤议题(对齐 scripts/md_to_json.py 的过滤语义)。"""
    items = load_issues()
    if category:
        items = [i for i in items if i.get("category") == category]
    if min_heat is not None:
        items = [i for i in items if (i.get("heat_score") or 0) >= min_heat]
    return items
