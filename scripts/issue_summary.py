#!/usr/bin/env python3
"""
issue_summary.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链补完(9/3 T5 周期)

汇总 data/issues.yaml + data/issue_relations.yaml,生成"开发者一眼看全"的中文报告。
为 Phase 1 / Web App 提供 CLI 维度的快速 sanity check,与 validate_pulse.py 同列工具链。

汇总维度:
  1. 议题库总量 + 按 category 分组(议题数 + 平均热度 + 最高热度议题)
  2. Top N 热度议题(id / name / heat_score / category)
  3. 关系图汇总(总边数 + 平均权重 + Top 出度 / Top 入度议题)
  4. 跨表校验:关系图 source/target 必须在议题库中,孤儿边告警
  5. 平均热度 + 最高 / 最低热度数值

用法:
  python3 scripts/issue_summary.py                          # 默认 + 人读报告
  python3 scripts/issue_summary.py --top 10                 # Top 10 议题(默认 5)
  python3 scripts/issue_summary.py --json                   # 机器可读 JSON
  python3 scripts/issue_summary.py --strict                 # 孤儿边 → exit 1
  python3 scripts/issue_summary.py --issues data/issues.yaml --relations data/issue_relations.yaml

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ISSUES_DEFAULT_PATH = "data/issues.yaml"
RELATIONS_DEFAULT_PATH = "data/issue_relations.yaml"
TOP_DEFAULT = 5
TOP_DEGREE_DEFAULT = 3


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
    """读取 issues.yaml,返回议题字典列表。"""
    data = load_yaml(path)
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        print(f"❌ {path}: 顶层 issues 字段不是列表", file=sys.stderr)
        sys.exit(1)
    return issues


def load_relations(path: Path) -> list[dict]:
    """读取 issue_relations.yaml,返回关系字典列表(可选,文件缺失时返回空)。"""
    if not path.exists():
        return []
    data = load_yaml(path)
    rels = data.get("relations", [])
    if not isinstance(rels, list):
        return []
    return rels


def summarize_issues(issues: list[dict]) -> dict:
    """汇总议题库:总数 / category 分组 / 热度统计 / Top N。"""
    n = len(issues)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for it in issues:
        cat = it.get("category", "未分类")
        by_category[cat].append(it)

    cat_stats = {}
    for cat, items in sorted(by_category.items()):
        heats = [it.get("heat_score", 0) for it in items if isinstance(it.get("heat_score"), (int, float))]
        avg_heat = round(sum(heats) / len(heats), 1) if heats else 0.0
        top_in_cat = max(items, key=lambda it: it.get("heat_score", 0)) if items else None
        cat_stats[cat] = {
            "count": len(items),
            "avg_heat": avg_heat,
            "top_issue": {
                "id": top_in_cat.get("id"),
                "name": top_in_cat.get("name"),
                "heat_score": top_in_cat.get("heat_score"),
            } if top_in_cat else None,
        }

    all_heats = [it.get("heat_score", 0) for it in issues if isinstance(it.get("heat_score"), (int, float))]
    avg_heat_total = round(sum(all_heats) / len(all_heats), 1) if all_heats else 0.0
    max_heat = max(all_heats) if all_heats else 0
    min_heat = min(all_heats) if all_heats else 0

    return {
        "total": n,
        "category_count": len(by_category),
        "avg_heat": avg_heat_total,
        "max_heat": max_heat,
        "min_heat": min_heat,
        "by_category": cat_stats,
    }


def top_issues(issues: list[dict], k: int) -> list[dict]:
    """按 heat_score 倒序取 Top K。"""
    sorted_issues = sorted(issues, key=lambda it: it.get("heat_score", 0), reverse=True)
    return [
        {
            "id": it.get("id"),
            "name": it.get("name"),
            "category": it.get("category"),
            "heat_score": it.get("heat_score"),
        }
        for it in sorted_issues[:k]
    ]


def summarize_relations(rels: list[dict], valid_issue_ids: set[str]) -> dict:
    """汇总关系图:边数 / 平均权重 / 出入度 Top K / 孤儿边告警。"""
    n = len(rels)
    weights = [r.get("weight", 0) for r in rels if isinstance(r.get("weight"), (int, float))]
    avg_weight = round(sum(weights) / len(weights), 3) if weights else 0.0

    out_degree: dict[str, int] = defaultdict(int)
    in_degree: dict[str, int] = defaultdict(int)
    orphans: list[dict] = []
    rel_types: dict[str, int] = defaultdict(int)

    for r in rels:
        src = r.get("source")
        tgt = r.get("target")
        rel_type = r.get("relation", "unknown")
        rel_types[rel_type] += 1
        if src:
            out_degree[src] += 1
        if tgt:
            in_degree[tgt] += 1
        # 孤儿边检测
        if src and src not in valid_issue_ids:
            orphans.append({"edge_index": rels.index(r), "field": "source", "value": src})
        if tgt and tgt not in valid_issue_ids:
            orphans.append({"edge_index": rels.index(r), "field": "target", "value": tgt})

    def top_k_by_degree(deg: dict[str, int], k: int) -> list[dict]:
        sorted_items = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)
        return [{"issue_id": iid, "degree": d} for iid, d in sorted_items[:k]]

    return {
        "total": n,
        "avg_weight": avg_weight,
        "relation_types": dict(rel_types),
        "top_out_degree": top_k_by_degree(out_degree, TOP_DEGREE_DEFAULT),
        "top_in_degree": top_k_by_degree(in_degree, TOP_DEGREE_DEFAULT),
        "orphans": orphans,
    }


def print_human_report(issues_path: Path, rels_path: Path, top_k: int, stats: dict) -> None:
    """输出人读报告。"""
    print(f"📋 议题汇总报告 · SocietyAdvisor Phase 0 #4 工具链")
    print(f"   issues:     {issues_path}")
    print(f"   relations:  {rels_path}")
    print()

    # ── 1. 议题库汇总 ──
    iss_sum = stats["issues"]
    print(f"━━━ 1. 议题库汇总 ━━━")
    print(f"   总数: {iss_sum['total']} 个议题,跨 {iss_sum['category_count']} 个 category")
    print(f"   热度: 平均 {iss_sum['avg_heat']} · 最高 {iss_sum['max_heat']} · 最低 {iss_sum['min_heat']}")
    print(f"   按 category 分组:")
    for cat, cs in iss_sum["by_category"].items():
        top = cs["top_issue"]
        top_str = f"{top['id']}({top['name']}, heat={top['heat_score']})" if top else "-"
        print(f"     · {cat}: {cs['count']} 个,均热 {cs['avg_heat']},最高 {top_str}")
    print()

    # ── 2. Top K 热度议题 ──
    print(f"━━━ 2. Top {top_k} 热度议题 ━━━")
    for i, it in enumerate(stats["top_issues"], 1):
        print(f"   {i}. {it['id']} {it['name']} · {it['category']} · heat={it['heat_score']}")
    print()

    # ── 3. 关系图汇总 ──
    rel_sum = stats["relations"]
    print(f"━━━ 3. 关系图汇总 ━━━")
    print(f"   总边数: {rel_sum['total']} 条,平均权重 {rel_sum['avg_weight']}")
    if rel_sum["relation_types"]:
        type_str = " / ".join(f"{k}={v}" for k, v in sorted(rel_sum["relation_types"].items()))
        print(f"   关系类型: {type_str}")
    print(f"   Top {TOP_DEGREE_DEFAULT} 出度议题(影响他人最多):")
    for i, item in enumerate(rel_sum["top_out_degree"], 1):
        print(f"     {i}. {item['issue_id']} · 出度={item['degree']}")
    print(f"   Top {TOP_DEGREE_DEFAULT} 入度议题(被影响最多):")
    for i, item in enumerate(rel_sum["top_in_degree"], 1):
        print(f"     {i}. {item['issue_id']} · 入度={item['degree']}")
    print()

    # ── 4. 跨表校验 ──
    orphans = rel_sum["orphans"]
    print(f"━━━ 4. 跨表校验 ━━━")
    if orphans:
        print(f"   ⚠️  发现 {len(orphans)} 处孤儿引用(关系图引用了 issues.yaml 中不存在的 id):")
        for o in orphans:
            print(f"     · relations[{o['edge_index']}].{o['field']} = {o['value']!r}")
    else:
        print(f"   ✅ 关系图 source/target 全部命中 issues.yaml(0 孤儿边)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="汇总 data/issues.yaml + data/issue_relations.yaml,生成议题库总览报告"
    )
    parser.add_argument(
        "--issues",
        default=ISSUES_DEFAULT_PATH,
        metavar="ISSUES_PATH",
        help=f"议题库路径(默认: {ISSUES_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--relations",
        default=RELATIONS_DEFAULT_PATH,
        metavar="RELATIONS_PATH",
        help=f"关系图路径(默认: {RELATIONS_DEFAULT_PATH},文件不存在则跳过)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=TOP_DEFAULT,
        metavar="K",
        help=f"Top K 热度议题(默认: {TOP_DEFAULT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式(机器可读)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式:发现孤儿边则 exit 1",
    )
    args = parser.parse_args()

    issues_path = Path(args.issues)
    rels_path = Path(args.relations)

    if not issues_path.exists():
        print(f"❌ 输入文件不存在: {issues_path}", file=sys.stderr)
        sys.exit(1)

    issues = load_issues(issues_path)
    rels = load_relations(rels_path)
    valid_issue_ids = {it.get("id") for it in issues if it.get("id")}

    iss_summary = summarize_issues(issues)
    top = top_issues(issues, args.top)
    rel_summary = summarize_relations(rels, valid_issue_ids)

    if args.json:
        # JSON 模式
        out = {
            "issues": iss_summary,
            "top_issues": top,
            "relations": rel_summary,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_human_report(issues_path, rels_path, args.top, {
            "issues": iss_summary,
            "top_issues": top,
            "relations": rel_summary,
        })

    # ── 退出码 ──
    if args.strict and rel_summary["orphans"]:
        print(f"\n❌ 严格模式:发现 {len(rel_summary['orphans'])} 处孤儿引用,exit 1", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
