#!/usr/bin/env python3
"""
issue_trend.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链扩展(9/11 T5 周期)

聚合 data/pulse_snapshots.yaml × data/issues.yaml,生成"议题热度时间趋势"汇总报告。
与 issue_summary.py(库/关系图静态盘点)、daily_report.py(每日多议题快照)互补,本脚本专注:
  1. 单议题跨日声量变化(delta / delta_pct / 日均 / 极值日)
  2. 单议题情感负向变化(预警价值:neg 上升 = 舆情恶化)
  3. 跨议题排名:涨幅 Top K / 跌幅 Top K / 持续高热 / 负向预警 Top K

字段规范:见 data/pulse_snapshots.schema.md v1.0 + data/issues.schema.md v1.0

用法:
  python3 scripts/issue_trend.py                          # 默认 + 人读报告
  python3 scripts/issue_trend.py --top 5                  # 各 Top K 取 5(默认 3)
  python3 scripts/issue_trend.py --source weibo           # 按 source 过滤
  python3 scripts/issue_trend.py --json                   # 机器可读 JSON
  python3 scripts/issue_trend.py --strict                 # 快照 < 2 条的议题 → exit 1
  python3 scripts/issue_trend.py --issues data/issues.yaml --pulse data/pulse_snapshots.yaml

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ISSUES_DEFAULT_PATH = "data/issues.yaml"
PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
TOP_DEFAULT = 3
ALLOWED_SOURCES = {"news", "weibo", "zhihu", "wechat", "hybrid"}


# ============== IO ==============

def load_yaml(path: Path) -> dict:
    """读取 yaml;缺失依赖给出明确指引。"""
    try:
        import yaml
    except ImportError:
        print("❌ 缺少依赖 PyYAML\n   安装: pip3 install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_issues(path: Path) -> list[dict]:
    data = load_yaml(path)
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        print(f"❌ {path}: 顶层 issues 字段不是列表", file=sys.stderr)
        sys.exit(1)
    return issues


def load_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = load_yaml(path)
    snaps = data.get("snapshots", [])
    return snaps if isinstance(snaps, list) else []


def _date_str(v) -> str:
    """yaml 解析 2026-08-25 会成 date 对象,统一转 str。"""
    if v is None or v == "":
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


# ============== 趋势计算 ==============

def compute_issue_trend(issue_id: str, snaps: list[dict]) -> Optional[dict]:
    """对单个议题按 snapshot_date 排序后计算趋势指标。

    返回 None 表示该议题快照数 < 2(无法计算 delta,跳过)。
    """
    if len(snaps) < 2:
        return None

    ordered = sorted(snaps, key=lambda s: _date_str(s.get("snapshot_date", "")))
    first = ordered[0]
    last = ordered[-1]

    first_vol = first.get("volume", 0) or 0
    last_vol = last.get("volume", 0) or 0
    delta_vol = last_vol - first_vol
    delta_pct = round((delta_vol / first_vol) * 100, 1) if first_vol > 0 else None

    volumes = [s.get("volume", 0) or 0 for s in ordered]
    avg_vol = round(sum(volumes) / len(volumes), 1)
    max_snap = max(ordered, key=lambda s: s.get("volume", 0) or 0)

    first_neg = first.get("sentiment_neg", 0) or 0
    last_neg = last.get("sentiment_neg", 0) or 0
    delta_neg = round(last_neg - first_neg, 3)

    return {
        "issue_id": issue_id,
        "snapshot_count": len(ordered),
        "first_date": _date_str(first.get("snapshot_date")),
        "last_date": _date_str(last.get("snapshot_date")),
        "first_volume": first_vol,
        "last_volume": last_vol,
        "delta_volume": delta_vol,
        "delta_pct": delta_pct,
        "avg_volume": avg_vol,
        "max_date": _date_str(max_snap.get("snapshot_date")),
        "max_volume": max_snap.get("volume", 0) or 0,
        "first_neg": first_neg,
        "last_neg": last_neg,
        "delta_neg": delta_neg,
    }


def compute_trends(snapshots: list[dict], source_filter: Optional[str]) -> dict:
    """对所有议题计算趋势 + 跨议题排名。

    返回:
      {
        "trends": [每议题 trend dict],
        "insufficient": [快照 < 2 条的议题 id],
        "ranking": {
          "top_risers": ...,
          "top_fallers": ...,
          "top_persistent_heat": ...,
          "top_neg_warn": ...,
        }
      }
    """
    if source_filter:
        if source_filter not in ALLOWED_SOURCES:
            print(f"❌ --source 必须在 {sorted(ALLOWED_SOURCES)} 内,收到 {source_filter!r}", file=sys.stderr)
            sys.exit(1)
        snapshots = [s for s in snapshots if s.get("source") == source_filter]

    by_issue: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        by_issue[s.get("issue_id", "")].append(s)

    trends: list[dict] = []
    insufficient: list[dict] = []
    for issue_id, snaps in by_issue.items():
        t = compute_issue_trend(issue_id, snaps)
        if t is None:
            insufficient.append({"issue_id": issue_id, "snapshot_count": len(snaps)})
        else:
            trends.append(t)

    # 跨议题排名
    def by_desc(field: str) -> list[dict]:
        return sorted([t for t in trends if t.get(field) is not None],
                      key=lambda t: t[field], reverse=True)

    def by_asc(field: str) -> list[dict]:
        return sorted([t for t in trends if t.get(field) is not None],
                      key=lambda t: t[field])

    ranking = {
        "top_risers": by_desc("delta_pct"),                  # 涨幅最大(正向 delta_pct)
        "top_fallers": by_asc("delta_pct"),                  # 跌幅最大(负向 delta_pct,绝对值最大)
        "top_persistent_heat": by_desc("avg_volume"),         # 日均声量 Top
        "top_neg_warn": by_desc("delta_neg"),                 # 负向情感上升最大(预警)
    }

    return {
        "trends": trends,
        "insufficient": insufficient,
        "ranking": ranking,
    }


# ============== 报告渲染 ==============

def print_human_report(issues_path: Path, pulse_path: Path, top_k: int, source_filter: Optional[str], result: dict) -> None:
    """输出人读报告。"""
    print(f"📈 议题热度趋势报告 · SocietyAdvisor Phase 0 #4 工具链")
    print(f"   issues:     {issues_path}")
    print(f"   pulse:      {pulse_path}")
    if source_filter:
        print(f"   source:     {source_filter}(过滤后)")
    print()

    trends = result["trends"]
    insufficient = result["insufficient"]
    ranking = result["ranking"]

    # ── 1. 概览 ──
    print(f"━━━ 1. 概览 ━━━")
    print(f"   可计算趋势的议题:{len(trends)} 个(快照 ≥ 2 条)")
    print(f"   快照不足的议题:  {len(insufficient)} 个(快照 < 2 条,跳过)")
    if trends:
        all_dates = sorted({t["first_date"] for t in trends} | {t["last_date"] for t in trends})
        print(f"   数据日期范围:    {all_dates[0]} ~ {all_dates[-1]}(共 {len(all_dates)} 天)")
        snapshot_total = sum(t["snapshot_count"] for t in trends)
        print(f"   趋势样本快照:    {snapshot_total} 条")
    print()

    if not trends:
        print(f"   ⚠️  无可计算趋势的议题(每议题需 ≥ 2 条快照),exit")
        return

    def attach_name(t: dict, issues_by_id: dict) -> dict:
        return {
            **t,
            "name": issues_by_id.get(t["issue_id"], {}).get("name", t["issue_id"]),
        }

    issues_by_id = _load_issues_by_id_for_print(issues_path)

    # ── 2. 涨幅 Top K ──
    print(f"━━━ 2. 涨幅 Top {top_k}(首日 → 末日声量上升最猛) ━━━")
    risers = ranking["top_risers"][:top_k]
    if risers:
        for i, t in enumerate(risers, 1):
            r = attach_name(t, issues_by_id)
            print(f"   {i}. {r['issue_id']} {r['name']} · {r['delta_pct']:+.1f}% "
                  f"({r['first_volume']} → {r['last_volume']}, {r['first_date']} → {r['last_date']})")
    else:
        print(f"   _(无数据)_")
    print()

    # ── 3. 跌幅 Top K ──
    print(f"━━━ 3. 跌幅 Top {top_k}(首日 → 末日声量下降最猛) ━━━")
    fallers = ranking["top_fallers"][:top_k]
    if fallers:
        for i, t in enumerate(fallers, 1):
            r = attach_name(t, issues_by_id)
            print(f"   {i}. {r['issue_id']} {r['name']} · {r['delta_pct']:+.1f}% "
                  f"({r['first_volume']} → {r['last_volume']}, {r['first_date']} → {r['last_date']})")
    else:
        print(f"   _(无数据)_")
    print()

    # ── 4. 持续高热 Top K ──
    print(f"━━━ 4. 持续高热 Top {top_k}(日均声量最大) ━━━")
    persistent = ranking["top_persistent_heat"][:top_k]
    if persistent:
        for i, t in enumerate(persistent, 1):
            r = attach_name(t, issues_by_id)
            print(f"   {i}. {r['issue_id']} {r['name']} · 日均 {r['avg_volume']} · "
                  f"峰值 {r['max_volume']}({r['max_date']})")
    else:
        print(f"   _(无数据)_")
    print()

    # ── 5. 负向情感预警 Top K ──
    print(f"━━━ 5. 负向情感预警 Top {top_k}(neg 情感上升最猛) ━━━")
    neg_warn = ranking["top_neg_warn"][:top_k]
    if neg_warn:
        for i, t in enumerate(neg_warn, 1):
            r = attach_name(t, issues_by_id)
            arrow = "📈 恶化" if r["delta_neg"] > 0 else ("📉 缓和" if r["delta_neg"] < 0 else "—")
            print(f"   {i}. {r['issue_id']} {r['name']} · Δneg {r['delta_neg']:+.3f} "
                  f"({r['first_neg']:.2f} → {r['last_neg']:.2f}) {arrow}")
    else:
        print(f"   _(无数据)_")
    print()

    # ── 6. 快照不足的议题 ──
    if insufficient:
        print(f"━━━ 6. 快照不足议题(需 ≥ 2 条才能算趋势) ━━━")
        for ins in insufficient:
            name = issues_by_id.get(ins["issue_id"], {}).get("name", ins["issue_id"])
            print(f"   · {ins['issue_id']} {name} · 快照 {ins['snapshot_count']} 条")
        print()


def _load_issues_by_id_for_print(issues_path: Path) -> dict:
    """内部小工具:人读报告渲染时取议题 name。"""
    try:
        issues = load_issues(issues_path)
        return {it.get("id", ""): it for it in issues}
    except SystemExit:
        return {}


# ============== 主流程 ==============

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 议题热度趋势汇总(声量 + 情感,跨日)",
    )
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, metavar="PATH", help=f"议题库路径(默认: {ISSUES_DEFAULT_PATH})")
    parser.add_argument("--pulse", default=PULSE_DEFAULT_PATH, metavar="PATH", help=f"pulse 快照路径(默认: {PULSE_DEFAULT_PATH})")
    parser.add_argument("--source", choices=sorted(ALLOWED_SOURCES), help="按 source 过滤(5 选 1)")
    parser.add_argument("--top", type=int, default=TOP_DEFAULT, metavar="K", help=f"各 Top K 取值(默认: {TOP_DEFAULT})")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式(机器可读)")
    parser.add_argument("--strict", action="store_true", help="严格模式:发现快照 < 2 条的议题 → exit 1")
    args = parser.parse_args()

    issues_path = Path(args.issues)
    pulse_path = Path(args.pulse)

    if not issues_path.exists():
        print(f"❌ 输入文件不存在: {issues_path}", file=sys.stderr)
        return 1
    if not pulse_path.exists():
        print(f"❌ 输入文件不存在: {pulse_path}", file=sys.stderr)
        return 1

    snapshots = load_snapshots(pulse_path)
    result = compute_trends(snapshots, args.source)

    if args.json:
        out = {
            "issues_path": str(issues_path),
            "pulse_path": str(pulse_path),
            "source_filter": args.source,
            "trend_count": len(result["trends"]),
            "insufficient_count": len(result["insufficient"]),
            "trends": result["trends"],
            "insufficient": result["insufficient"],
            "ranking": {
                k: v[:args.top] for k, v in result["ranking"].items()
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_human_report(issues_path, pulse_path, args.top, args.source, result)

    # ── 退出码 ──
    if args.strict and result["insufficient"]:
        print(f"\n❌ 严格模式:发现 {len(result['insufficient'])} 个议题快照 < 2 条,exit 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
