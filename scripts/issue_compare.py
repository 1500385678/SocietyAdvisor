#!/usr/bin/env python3
"""
issue_compare.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链再扩展(9/16 T5 周期)

多议题横向对比 CLI。聚合 data/issues.yaml × data/pulse_snapshots.yaml × data/issue_relations.yaml,
对 2+ 议题输出"同框对比表",为 Phase 1 `/pulse/compare` 接口 + 多议题拉表场景提供 CLI 端预演。

对比维度(每议题 8 字段):
  1. 基础    issue_id / name / category / heat_score
  2. 热度    snapshot_count(快照条数)/ total_volume(总声量)/ avg_volume(日均声量)
  3. 情感    avg_pos / avg_neu / avg_neg(按快照均值)
  4. 关系    out_degree / in_degree / total_degree(从 issue_relations.yaml)
  5. 趋势    delta_pct(首末日声量变化率)/ delta_neg(负向情感变化)

跨议题衍生(3 段):
  1. 同 category 分组:经济/教育/科技/...
  2. 极值定位:热度最高 / 声量最大 / 负向情感最深
  3. 排名快照:按 heat_score / total_volume / avg_neg / total_degree 四档排序

字段规范:见 data/pulse_snapshots.schema.md v1.0 + data/issues.schema.md v1.0 + data/issue_relations.schema.md v1.0

用法:
  python3 scripts/issue_compare.py issue-001 issue-002 issue-005           # 默认 3 议题对比
  python3 scripts/issue_compare.py issue-001 issue-002 issue-005 --top 5   # 极值 Top K(默认 3)
  python3 scripts/issue_compare.py issue-001 issue-009 --source hybrid     # 按 source 过滤
  python3 scripts/issue_compare.py issue-001 issue-002 --json              # 机器可读 JSON
  python3 scripts/issue_compare.py issue-001 issue-002 --strict             # 任何字段缺失 → exit 1
  python3 scripts/issue_compare.py issue-001 issue-002 --issues data/issues.yaml --pulse data/pulse_snapshots.yaml --relations data/issue_relations.yaml

依赖:PyYAML (pip3 install pyyaml)

退出码:
  0  成功 / JSON 输出 / 人读报告(无问题)
  1  参数错 / 输入文件缺失 / 议题数 < 2 / ID 不存在 / --strict 失败
  2  缺少依赖 PyYAML

设计决策:
  - 单议题不能对比,≥ 2 议题才能形成"对比";argparse 控制 + run-time 校验
  - 议题 ID 不存在 → 立即 exit 1(避免静默跳过,确保对比对象真实存在)
  - 快照为空(议题无 pulse 数据)→ 仍输出基础段 + 热度/关系段,标记 N/A,不全 fail
  - 关系图空(无 relations.yaml 或无对应边)→ 标记 degree=0,不 fail(允许孤议题对比)
  - --strict 才把"快照为空 / 关系为空"算 fail(默认宽松,便于早期数据不全阶段也能跑)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ISSUES_DEFAULT_PATH = "data/issues.yaml"
PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
RELATIONS_DEFAULT_PATH = "data/issue_relations.yaml"
TOP_DEFAULT = 3
ALLOWED_SOURCES = {"news", "weibo", "zhihu", "wechat", "hybrid"}


# ============== IO ==============

def load_yaml(path: Path) -> dict:
    """读取 yaml;缺失依赖给出明确指引。"""
    try:
        import yaml
    except ImportError:
        print("❌ 缺少依赖 PyYAML\n   安装: pip3 install pyyaml", file=sys.stderr)
        sys.exit(2)
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


def load_relations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = load_yaml(path)
    rels = data.get("relations", [])
    return rels if isinstance(rels, list) else []


def _date_str(v) -> str:
    """yaml 解析 2026-08-25 会成 date 对象,统一转 str。"""
    if v is None or v == "":
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


# ============== 字段聚合 ==============

def _snapshot_stats(snaps: list[dict]) -> dict:
    """单议题的 pulse 聚合:总声量 / 日均 / 情感均值 / 趋势 delta。"""
    if not snaps:
        return {
            "snapshot_count": 0,
            "total_volume": None,
            "avg_volume": None,
            "max_date": None,
            "min_date": None,
            "avg_pos": None,
            "avg_neu": None,
            "avg_neg": None,
            "delta_pct": None,
            "delta_neg": None,
            "has_pulse": False,
        }

    volumes = [s.get("volume", 0) or 0 for s in snaps]
    pos = [s.get("sentiment_pos", 0) or 0 for s in snaps]
    neu = [s.get("sentiment_neu", 0) or 0 for s in snaps]
    neg = [s.get("sentiment_neg", 0) or 0 for s in snaps]

    ordered = sorted(snaps, key=lambda s: _date_str(s.get("snapshot_date", "")))
    first_vol = ordered[0].get("volume", 0) or 0
    last_vol = ordered[-1].get("volume", 0) or 0
    delta_pct = round((last_vol - first_vol) / first_vol * 100, 1) if first_vol > 0 else None
    delta_neg = round(neg[-1] - neg[0], 3)

    return {
        "snapshot_count": len(snaps),
        "total_volume": sum(volumes),
        "avg_volume": round(sum(volumes) / len(volumes), 1),
        "max_date": _date_str(ordered[-1].get("snapshot_date")),
        "min_date": _date_str(ordered[0].get("snapshot_date")),
        "avg_pos": round(sum(pos) / len(pos), 3),
        "avg_neu": round(sum(neu) / len(neu), 3),
        "avg_neg": round(sum(neg) / len(neg), 3),
        "delta_pct": delta_pct,
        "delta_neg": delta_neg,
        "has_pulse": True,
    }


def _relation_stats(issue_id: str, relations: list[dict]) -> dict:
    """单议题的关系聚合:出度 / 入度 / 总度。"""
    out_d = 0
    in_d = 0
    for r in relations:
        src = r.get("source", "")
        tgt = r.get("target", "")
        if src == issue_id:
            out_d += 1
        if tgt == issue_id:
            in_d += 1
    return {
        "out_degree": out_d,
        "in_degree": in_d,
        "total_degree": out_d + in_d,
        "has_relations": (out_d + in_d) > 0,
    }


def build_compare_rows(
    issue_ids: list[str],
    issues: list[dict],
    snapshots: list[dict],
    relations: list[dict],
    source_filter: Optional[str],
) -> tuple[list[dict], list[str]]:
    """对每个 issue_id 构建 1 行对比数据 + 返回缺失 ID 列表。"""
    issues_by_id = {it.get("id", ""): it for it in issues}

    if source_filter:
        if source_filter not in ALLOWED_SOURCES:
            print(f"❌ --source 必须在 {sorted(ALLOWED_SOURCES)} 内,收到 {source_filter!r}", file=sys.stderr)
            sys.exit(1)
        snapshots = [s for s in snapshots if s.get("source") == source_filter]

    by_issue_snaps: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        by_issue_snaps[s.get("issue_id", "")].append(s)

    rows: list[dict] = []
    missing: list[str] = []
    for iid in issue_ids:
        issue = issues_by_id.get(iid)
        if issue is None:
            missing.append(iid)
            continue
        stats = _snapshot_stats(by_issue_snaps.get(iid, []))
        rel = _relation_stats(iid, relations)
        rows.append({
            "issue_id": iid,
            "name": issue.get("name", iid),
            "category": issue.get("category", ""),
            "heat_score": issue.get("heat_score", 0) or 0,
            "tags": issue.get("tags", []) or [],
            **stats,
            **rel,
        })

    return rows, missing


# ============== 衍生分析 ==============

def category_breakdown(rows: list[dict]) -> dict[str, int]:
    by_cat: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("category"):
            by_cat[r["category"]] += 1
    return dict(sorted(by_cat.items(), key=lambda kv: -kv[1]))


def extremes(rows: list[dict]) -> dict[str, Optional[dict]]:
    """4 档极值定位(已 _attach_name 的 rows)。"""

    def pick(field: str, mode: str) -> Optional[dict]:
        candidates = [r for r in rows if r.get(field) is not None]
        if not candidates:
            return None
        if mode == "max":
            return max(candidates, key=lambda r: r[field])
        return min(candidates, key=lambda r: r[field])

    return {
        "heat_top": pick("heat_score", "max"),
        "volume_top": pick("total_volume", "max"),
        "neg_deepest": pick("avg_neg", "max"),
        "degree_top": pick("total_degree", "max"),
    }


def rankings(rows: list[dict], top_k: int) -> dict[str, list[dict]]:
    """4 档排名(已 _attach_name 的 rows)。"""

    def take(field: str, mode: str) -> list[dict]:
        candidates = [r for r in rows if r.get(field) is not None]
        candidates.sort(key=lambda r: r[field], reverse=(mode == "max"))
        return candidates[:top_k]

    return {
        "by_heat_score": take("heat_score", "max"),
        "by_total_volume": take("total_volume", "max"),
        "by_avg_neg": take("avg_neg", "max"),
        "by_total_degree": take("total_degree", "max"),
    }


# ============== 报告渲染 ==============

def _row_attach_source(rows: list[dict], source_filter: Optional[str]) -> list[dict]:
    return [{**r, "source_filter": source_filter or "(all sources)"} for r in rows]


def print_human_report(
    issue_ids: list[str],
    rows: list[dict],
    missing: list[str],
    issues_path: Path,
    pulse_path: Path,
    relations_path: Path,
    top_k: int,
    source_filter: Optional[str],
) -> None:
    print(f"🔀 多议题横向对比报告 · SocietyAdvisor Phase 0 #4 工具链")
    print(f"   issues:     {issues_path}")
    print(f"   pulse:      {pulse_path}")
    print(f"   relations:  {relations_path}")
    if source_filter:
        print(f"   source:     {source_filter}(过滤后)")
    print(f"   对比对象:   {len(issue_ids)} 个(实际匹配 {len(rows)} 个)")
    if missing:
        print(f"   ⚠️  缺失议题 ID: {missing}(已跳过)")
    print()

    if not rows:
        print(f"   ⚠️  无可对比议题,exit")
        return

    # ── 1. 基础段(每议题 1 行)──
    print(f"━━━ 1. 议题基础信息({len(rows)} 议题) ━━━")
    for r in rows:
        tags = ", ".join(r.get("tags", [])[:4]) or "—"
        print(f"   · {r['issue_id']} {r['name']}")
        print(f"       category:  {r['category']}")
        print(f"       heat:      {r['heat_score']}")
        print(f"       tags:      {tags}")
    print()

    # ── 2. 热度段(pulse 聚合)──
    print(f"━━━ 2. 热度对比(pulse 聚合) ━━━")
    for r in rows:
        if r["has_pulse"]:
            print(f"   · {r['issue_id']} {r['name']} · 快照 {r['snapshot_count']} 条 "
                  f"· 总声量 {r['total_volume']} · 日均 {r['avg_volume']}")
            print(f"       日期范围:  {r['min_date']} → {r['max_date']}")
            if r["delta_pct"] is not None:
                arrow = "📈 上升" if r["delta_pct"] > 0 else ("📉 下降" if r["delta_pct"] < 0 else "—")
                print(f"       趋势 Δ%:   {r['delta_pct']:+.1f}% {arrow}")
        else:
            print(f"   · {r['issue_id']} {r['name']} · ⚠️  无 pulse 数据")
    print()

    # ── 3. 情感段 ──
    print(f"━━━ 3. 情感对比(快照均值) ━━━")
    for r in rows:
        if r["has_pulse"]:
            print(f"   · {r['issue_id']} {r['name']} · pos {r['avg_pos']:.3f} · "
                  f"neu {r['avg_neu']:.3f} · neg {r['avg_neg']:.3f}")
            if r["delta_neg"] is not None:
                arrow = "⚠️  恶化" if r["delta_neg"] > 0 else ("✅ 缓和" if r["delta_neg"] < 0 else "—")
                print(f"       Δneg:      {r['delta_neg']:+.3f} {arrow}")
        else:
            print(f"   · {r['issue_id']} {r['name']} · ⚠️  无情感数据")
    print()

    # ── 4. 关系段 ──
    print(f"━━━ 4. 关系对比(关系边出入度) ━━━")
    for r in rows:
        if r["has_relations"]:
            print(f"   · {r['issue_id']} {r['name']} · 出度 {r['out_degree']} · "
                  f"入度 {r['in_degree']} · 总度 {r['total_degree']}")
        else:
            print(f"   · {r['issue_id']} {r['name']} · 0 边(孤立节点)")
    print()

    # ── 5. category 分组 ──
    cat_map = category_breakdown(rows)
    if cat_map:
        print(f"━━━ 5. category 分组({len(cat_map)} 类) ━━━")
        for cat, n in cat_map.items():
            ids_in_cat = [r["issue_id"] for r in rows if r["category"] == cat]
            print(f"   · {cat}: {n} 个({', '.join(ids_in_cat)})")
        print()

    # ── 6. 极值定位 ──
    ext = extremes(rows)
    print(f"━━━ 6. 极值定位(单项冠军) ━━━")
    if ext["heat_top"]:
        r = ext["heat_top"]
        print(f"   · 热度最高:    {r['issue_id']} {r['name']} · heat {r['heat_score']}")
    if ext["volume_top"]:
        r = ext["volume_top"]
        print(f"   · 声量最大:    {r['issue_id']} {r['name']} · 总声量 {r['total_volume']}")
    if ext["neg_deepest"]:
        r = ext["neg_deepest"]
        print(f"   · 负向最深:    {r['issue_id']} {r['name']} · neg {r['avg_neg']:.3f}")
    if ext["degree_top"]:
        r = ext["degree_top"]
        print(f"   · 关系最密:    {r['issue_id']} {r['name']} · 总度 {r['total_degree']}")
    print()

    # ── 7. 排名 Top K ──
    rk = rankings(rows, top_k)
    print(f"━━━ 7. 排名 Top {top_k} ━━━")
    for label, key in [
        ("按 heat_score 倒序", "by_heat_score"),
        ("按 total_volume 倒序", "by_total_volume"),
        ("按 avg_neg 倒序(负向最深)", "by_avg_neg"),
        ("按 total_degree 倒序(关系最密)", "by_total_degree"),
    ]:
        items = rk[key]
        print(f"   · {label}:")
        if items:
            for i, r in enumerate(items, 1):
                if key == "by_heat_score":
                    val = f"heat {r['heat_score']}"
                elif key == "by_total_volume":
                    val = f"vol {r['total_volume']}"
                elif key == "by_avg_neg":
                    val = f"neg {r['avg_neg']:.3f}"
                else:
                    val = f"deg {r['total_degree']}"
                print(f"       {i}. {r['issue_id']} {r['name']} · {val}")
        else:
            print(f"       _(无数据)_")
    print()

    # ── 8. 缺失议题 ID 列表 ──
    if missing:
        print(f"━━━ 8. 缺失议题 ID(未在 issues.yaml 命中) ━━━")
        for iid in missing:
            print(f"   · {iid}")
        print()


# ============== 主流程 ==============

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 多议题横向对比 CLI(议题库 × pulse × 关系图 同框对比)",
        usage="python3 scripts/issue_compare.py ISSUE_ID [ISSUE_ID ...] [选项]",
    )
    parser.add_argument("issue_ids", nargs="+", metavar="ISSUE_ID", help="对比的议题 ID(≥ 2 个,如 issue-001 issue-002)")
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, metavar="PATH", help=f"议题库路径(默认: {ISSUES_DEFAULT_PATH})")
    parser.add_argument("--pulse", default=PULSE_DEFAULT_PATH, metavar="PATH", help=f"pulse 快照路径(默认: {PULSE_DEFAULT_PATH})")
    parser.add_argument("--relations", default=RELATIONS_DEFAULT_PATH, metavar="PATH", help=f"关系图路径(默认: {RELATIONS_DEFAULT_PATH})")
    parser.add_argument("--source", choices=sorted(ALLOWED_SOURCES), help="按 source 过滤(5 选 1)")
    parser.add_argument("--top", type=int, default=TOP_DEFAULT, metavar="K", help=f"排名 Top K(默认: {TOP_DEFAULT})")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式(机器可读)")
    parser.add_argument("--strict", action="store_true", help="严格模式:发现议题无 pulse 数据 / 无关系边 → exit 1")
    args = parser.parse_args()

    if len(args.issue_ids) < 2:
        print(f"❌ 至少需要 2 个议题 ID 才能对比,收到 {len(args.issue_ids)} 个({args.issue_ids})", file=sys.stderr)
        return 1

    issues_path = Path(args.issues)
    pulse_path = Path(args.pulse)
    relations_path = Path(args.relations)

    if not issues_path.exists():
        print(f"❌ 输入文件不存在: {issues_path}", file=sys.stderr)
        return 1

    issues = load_issues(issues_path)
    snapshots = load_snapshots(pulse_path)
    relations = load_relations(relations_path)

    rows, missing = build_compare_rows(args.issue_ids, issues, snapshots, relations, args.source)

    if missing:
        print(f"❌ 以下议题 ID 在 issues.yaml 中不存在:{missing}", file=sys.stderr)
        return 1

    if args.json:
        out = {
            "issues_path": str(issues_path),
            "pulse_path": str(pulse_path),
            "relations_path": str(relations_path),
            "source_filter": args.source,
            "issue_ids": args.issue_ids,
            "rows": _row_attach_source(rows, args.source),
            "category_breakdown": category_breakdown(rows),
            "extremes": extremes(rows),
            "rankings": rankings(rows, args.top),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_human_report(
            args.issue_ids, rows, missing,
            issues_path, pulse_path, relations_path,
            args.top, args.source,
        )

    # ── 退出码 ──
    if args.strict:
        problems = []
        no_pulse = [r["issue_id"] for r in rows if not r["has_pulse"]]
        no_rels = [r["issue_id"] for r in rows if not r["has_relations"]]
        if no_pulse:
            problems.append(f"无 pulse 数据: {no_pulse}")
        if no_rels:
            problems.append(f"无关系边: {no_rels}")
        if problems:
            print(f"\n❌ 严格模式:{' / '.join(problems)},exit 1", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())