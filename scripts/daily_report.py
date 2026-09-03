#!/usr/bin/env python3
"""
daily_report.py · SocietyAdvisor Phase 0 #6 飞书日报生成器(9/4 T5 周期)

输入 data/issues.yaml + data/issue_relations.yaml + data/pulse_snapshots.yaml,
生成飞书 Bot 消费的 Markdown 日报骨架。结构 4 段:
  1. Top N 热度议题(按 heat_score 倒序)
  2. 近 7 日声量监控(按 issue_id 聚合 pulse_snapshots,总声量 + 平均情感)
  3. 议题关系亮点(出度 Top K / 入度 Top K)
  4. 报告元信息(生成时间 / 数据规模 / 数据日期范围)

用法:
  python3 scripts/daily_report.py                          # 默认 Markdown 到 stdout
  python3 scripts/daily_report.py --top 10                 # Top 10 议题(默认 10)
  python3 scripts/daily_report.py --json                   # 机器可读 JSON
  python3 scripts/daily_report.py --strict                 # 关键数据缺失 → exit 1
  python3 scripts/daily_report.py --date 2026-09-04        # 报告日期(默认今日 UTC+8)
  python3 scripts/daily_report.py --output .Log/日报-20260904.md
  python3 scripts/daily_report.py --issues data/issues.yaml --relations data/issue_relations.yaml --pulse data/pulse_snapshots.yaml

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ISSUES_DEFAULT_PATH = "data/issues.yaml"
RELATIONS_DEFAULT_PATH = "data/issue_relations.yaml"
PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
TOP_DEFAULT = 10
DEGREE_DEFAULT = 3
CST = timezone(timedelta(hours=8))


# ============== IO ==============

def load_yaml(path: Path) -> dict:
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


def load_relations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = load_yaml(path)
    rels = data.get("relations", [])
    return rels if isinstance(rels, list) else []


def load_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = load_yaml(path)
    snaps = data.get("snapshots", [])
    return snaps if isinstance(snaps, list) else []


# ============== 维度计算 ==============

def top_heat_issues(issues: list[dict], top: int) -> list[dict]:
    """Top N 热度议题(按 heat_score 倒序)。"""
    return sorted(
        issues,
        key=lambda it: it.get("heat_score", 0),
        reverse=True,
    )[:top]


def pulse_lookback(snapshots: list[dict], issues_by_id: dict) -> list[dict]:
    """声量监控:按 issue_id 聚合,返回 [{issue_id, name, total_volume, avg_pos, avg_neu, avg_neg, snapshot_count, latest_date}]。Phase 0 数据稀疏(13 条 / 6 议题 / 5 天),不按报告日期硬过滤窗口——把全量纳入,标签用"声量监控"而非"近 N 日",避免误导。"""
    by_issue: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        by_issue[s.get("issue_id", "")].append(s)

    rows = []
    for issue_id, snaps in by_issue.items():
        snaps_sorted = sorted(snaps, key=lambda s: s.get("snapshot_date", ""))
        total_volume = sum(s.get("volume", 0) for s in snaps_sorted)
        n = len(snaps_sorted)
        avg_pos = round(sum(s.get("sentiment_pos", 0) for s in snaps_sorted) / n, 3) if n else 0
        avg_neu = round(sum(s.get("sentiment_neu", 0) for s in snaps_sorted) / n, 3) if n else 0
        avg_neg = round(sum(s.get("sentiment_neg", 0) for s in snaps_sorted) / n, 3) if n else 0
        latest = snaps_sorted[-1].get("snapshot_date", "") if snaps_sorted else ""
        if hasattr(latest, "isoformat"):
            latest = latest.isoformat()
        rows.append({
            "issue_id": issue_id,
            "name": issues_by_id.get(issue_id, {}).get("name", issue_id),
            "total_volume": total_volume,
            "avg_pos": avg_pos,
            "avg_neu": avg_neu,
            "avg_neg": avg_neg,
            "snapshot_count": n,
            "latest_date": latest,
        })
    return sorted(rows, key=lambda r: r["total_volume"], reverse=True)


def degree_highlights(relations: list[dict], issues_by_id: dict, top: int) -> tuple[list[dict], list[dict]]:
    """出度 / 入度 Top K 议题。"""
    out_deg: dict[str, int] = defaultdict(int)
    in_deg: dict[str, int] = defaultdict(int)
    for r in relations:
        out_deg[r.get("source", "")] += 1
        in_deg[r.get("target", "")] += 1

    def rows(deg: dict[str, int]) -> list[dict]:
        ranked = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)[:top]
        return [
            {"issue_id": k, "name": issues_by_id.get(k, {}).get("name", k), "degree": v}
            for k, v in ranked if v > 0
        ]

    return rows(out_deg), rows(in_deg)


# ============== 报告渲染 ==============

def render_markdown(report: dict) -> str:
    """渲染为 Markdown(飞书 Bot 友好,无嵌套表格)。"""
    md = []
    md.append(f"# 社会顾问 · 飞书日报")
    md.append(f"> 生成时间 {report['meta']['generated_at']} · 数据日期 {report['meta']['date']}")
    md.append("")

    # Top 热度
    md.append(f"## 1. Top {len(report['top_issues'])} 热度议题")
    md.append("")
    md.append("| 排名 | ID | 议题 | 分类 | 热度 |")
    md.append("|---|---|---|---|---|")
    for i, it in enumerate(report["top_issues"], 1):
        md.append(f"| {i} | {it.get('id', '')} | {it.get('name', '')} | {it.get('category', '')} | {it.get('heat_score', 0)} |")
    md.append("")

    # 声量监控
    pulse = report["pulse"]
    md.append(f"## 2. 声量监控汇总({pulse['snapshot_total']} 条快照 · {pulse['issue_count']} 个议题)")
    md.append("")
    if pulse["rows"]:
        md.append("| 议题 | 总声量 | 平均正/中/负 | 快照数 | 最新日期 |")
        md.append("|---|---|---|---|---|")
        for r in pulse["rows"]:
            md.append(
                f"| {r['name']} ({r['issue_id']}) | {r['total_volume']} | "
                f"{r['avg_pos']} / {r['avg_neu']} / {r['avg_neg']} | "
                f"{r['snapshot_count']} | {r['latest_date']} |"
            )
    else:
        md.append("_(暂无 pulse 快照数据)_")
    md.append("")

    # 关系亮点
    rel = report["relations"]
    md.append(f"## 3. 议题关系亮点(总边数 {rel['total_edges']})")
    md.append("")
    if rel["top_out_degree"]:
        md.append(f"**出度 Top {len(rel['top_out_degree'])}** (该议题主动影响/导致其他议题):")
        for r in rel["top_out_degree"]:
            md.append(f"- {r['name']} ({r['issue_id']}) · 出度 {r['degree']}")
        md.append("")
    if rel["top_in_degree"]:
        md.append(f"**入度 Top {len(rel['top_in_degree'])}** (该议题被多议题影响/关联):")
        for r in rel["top_in_degree"]:
            md.append(f"- {r['name']} ({r['issue_id']}) · 入度 {r['degree']}")
        md.append("")
    if not rel["top_out_degree"] and not rel["top_in_degree"]:
        md.append("_(暂无关系数据)_")
        md.append("")

    # 元信息
    md.append("## 4. 报告元信息")
    md.append("")
    md.append(f"- 议题库总数:{report['meta']['issue_total']}")
    md.append(f"- 关系图总边数:{report['meta']['relation_total']}")
    md.append(f"- 声量快照总数:{report['meta']['pulse_total']}")
    if report["meta"].get("pulse_date_range"):
        md.append(f"- 声量数据日期范围:{report['meta']['pulse_date_range']}")
    md.append(f"- 数据源:`data/issues.yaml` + `data/issue_relations.yaml` + `data/pulse_snapshots.yaml`")
    md.append("")
    md.append("---")
    md.append("_本报告由 `scripts/daily_report.py` 自动生成 · Phase 0 #6 起步(9/4 T5 周期)_")

    return "\n".join(md)


# ============== 主流程 ==============

def build_report(
    issues: list[dict],
    relations: list[dict],
    snapshots: list[dict],
    top: int,
    degree_top: int,
    report_date: str,
) -> dict:
    issues_by_id = {it.get("id", ""): it for it in issues}
    top_issues = [
        {
            "id": it.get("id", ""),
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "heat_score": it.get("heat_score", 0),
        }
        for it in top_heat_issues(issues, top)
    ]
    pulse_rows = pulse_lookback(snapshots, issues_by_id)
    out_deg, in_deg = degree_highlights(relations, issues_by_id, degree_top)

    def _date_str(v) -> str:
        """yaml 解析 2026-08-25 会成 date 对象,统一转 str 给 JSON 序列化。"""
        if v is None or v == "":
            return ""
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    pulse_dates = sorted({_date_str(s.get("snapshot_date", "")) for s in snapshots if s.get("snapshot_date")})
    date_range = f"{pulse_dates[0]} ~ {pulse_dates[-1]}" if pulse_dates else ""

    return {
        "meta": {
            "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "date": report_date,
            "issue_total": len(issues),
            "relation_total": len(relations),
            "pulse_total": len(snapshots),
            "pulse_date_range": date_range,
        },
        "top_issues": top_issues,
        "pulse": {
            "snapshot_total": len(snapshots),
            "issue_count": len({s.get("issue_id") for s in snapshots}),
            "rows": pulse_rows,
        },
        "relations": {
            "total_edges": len(relations),
            "top_out_degree": out_deg,
            "top_in_degree": in_deg,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 飞书日报生成器",
    )
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, help="issues.yaml 路径")
    parser.add_argument("--relations", default=RELATIONS_DEFAULT_PATH, help="issue_relations.yaml 路径")
    parser.add_argument("--pulse", default=PULSE_DEFAULT_PATH, help="pulse_snapshots.yaml 路径")
    parser.add_argument("--top", type=int, default=TOP_DEFAULT, help="Top 热度议题数(默认 10)")
    parser.add_argument("--degree-top", type=int, default=DEGREE_DEFAULT, help="出入度 Top 数(默认 3)")
    parser.add_argument("--date", default=datetime.now(CST).strftime("%Y-%m-%d"), help="报告日期 YYYY-MM-DD(默认今日 CST)")
    parser.add_argument("--output", help="写入文件路径(默认 stdout)")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    parser.add_argument("--strict", action="store_true", help="关键数据缺失 → exit 1")
    args = parser.parse_args()

    issues = load_issues(Path(args.issues))
    relations = load_relations(Path(args.relations))
    snapshots = load_snapshots(Path(args.pulse))

    if args.strict and not issues:
        print(f"❌ --strict: 议题库为空,中止", file=sys.stderr)
        return 1
    if args.strict and not snapshots:
        print(f"❌ --strict: pulse_snapshots 为空,中止(日报无监控数据)", file=sys.stderr)
        return 1

    report = build_report(issues, relations, snapshots, args.top, args.degree_top, args.date)

    if args.json:
        body = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        body = render_markdown(report)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"✅ 日报已写入 {out} ({len(body)} 字节, {report['meta']['issue_total']} 议题 / {report['meta']['pulse_total']} 快照)")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
