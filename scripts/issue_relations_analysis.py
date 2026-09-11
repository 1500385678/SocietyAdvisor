#!/usr/bin/env python3
"""
issue_relations_analysis.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链再扩展(9/12 T5 周期)

聚合 data/issues.yaml × data/issue_relations.yaml,生成"议题关系图图论维度"汇总报告。
与 issue_summary.py(库/关系图静态盘点)、issue_trend.py(时序趋势)互补,本脚本专注图论深度:
  1. 概览:节点 / 边 / 平均度 / 密度 / 类型分布
  2. 按关系类型分组的统计(cause / influence / related × 边数 / 平均权重 / Top 节点)
  3. 节点度排序(总度 = 出度 + 入度,Top K)
  4. 孤立节点(没有任何边的议题)
  5. 异常检测:双向边(A→B 与 B→A 同时存在) / 自环边(A→A)
  6. 2 跳扩散:从某节点出发 2 跳内可达的节点数(影响力扩散范围)

字段规范:见 data/issues.schema.md v1.0 + data/issue_relations.schema.md v1.0
(relation 字段 3 选 1 enum:cause / influence / related;weight ∈ [0, 1])

用法:
  python3 scripts/issue_relations_analysis.py                          # 默认 + 人读报告
  python3 scripts/issue_relations_analysis.py --top 5                  # 各 Top K 取 5(默认 3)
  python3 scripts/issue_relations_analysis.py --json                   # 机器可读 JSON
  python3 scripts/issue_relations_analysis.py --strict                 # 有孤立节点 / 双向边 / 自环 → exit 1
  python3 scripts/issue_relations_analysis.py --source issue-005       # 2 跳扩散示例:从 issue-005 出发
  python3 scripts/issue_relations_analysis.py --issues data/issues.yaml --relations data/issue_relations.yaml

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ISSUES_DEFAULT_PATH = "data/issues.yaml"
RELATIONS_DEFAULT_PATH = "data/issue_relations.yaml"
TOP_DEFAULT = 3

# 关系类型 3 选 1(对齐 issue_relations.schema.md v1.0)
ALLOWED_RELATIONS = {"cause", "influence", "related"}


# ============== 数据加载 ==============

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
    """读取 issue_relations.yaml,返回关系字典列表(文件缺失返回空)。"""
    if not path.exists():
        return []
    data = load_yaml(path)
    rels = data.get("relations", [])
    if not isinstance(rels, list):
        return []
    return rels


# ============== 图论计算 ==============

def build_graph(rels: list[dict]) -> dict[str, list[str]]:
    """构建邻接表(无向视角,用于 2 跳扩散)。自环不参与 2 跳扩散。"""
    adj: dict[str, set[str]] = defaultdict(set)
    for r in rels:
        src = r.get("source")
        tgt = r.get("target")
        if src and tgt and src != tgt:
            adj[src].add(tgt)
            adj[tgt].add(src)  # 视为无向边计算扩散
    return {k: sorted(v) for k, v in adj.items()}


def compute_degree(rels: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """计算每个节点的出度 / 入度(自环计入出度+入度各一次)。"""
    out_deg: dict[str, int] = defaultdict(int)
    in_deg: dict[str, int] = defaultdict(int)
    for r in rels:
        src = r.get("source")
        tgt = r.get("target")
        if src:
            out_deg[src] += 1
        if tgt:
            in_deg[tgt] += 1
    return dict(out_deg), dict(in_deg)


def find_orphans(issues: list[dict], rels: list[dict]) -> list[str]:
    """孤立节点:在议题库中存在,但关系图中没有任何出/入边。"""
    involved: set[str] = set()
    for r in rels:
        if r.get("source"):
            involved.add(r["source"])
        if r.get("target"):
            involved.add(r["target"])
    return sorted([it.get("id") for it in issues if it.get("id") and it["id"] not in involved])


def find_bidirectional_edges(rels: list[dict]) -> list[dict]:
    """双向边:A→B 与 B→A 同时存在(异常:关系应单向)。"""
    pair: set[tuple[str, str]] = set()
    dupes: list[dict] = []
    seen_bidir: set[tuple[str, str]] = set()
    for r in rels:
        src = r.get("source")
        tgt = r.get("target")
        if not src or not tgt or src == tgt:
            continue
        key = (src, tgt)
        rev = (tgt, src)
        if rev in pair and key not in seen_bidir:
            dupes.append({"a": src, "b": tgt})
            seen_bidir.add(key)
        pair.add(key)
    return dupes


def find_self_loops(rels: list[dict]) -> list[str]:
    """自环边:source == target(异常:议题不应影响自身)。"""
    return sorted({r["source"] for r in rels if r.get("source") and r["source"] == r.get("target")})


def two_hop_reach(adj: dict[str, list[str]], source: str) -> dict:
    """从 source 出发,2 跳内可达的节点(不含 source 自身)。"""
    if source not in adj:
        return {"source": source, "reachable": [], "count": 0}
    # 1 跳
    hop1 = set(adj[source])
    # 2 跳 = 1 跳的邻居的邻居,排除 source 自身和 1 跳
    hop2: set[str] = set()
    for n in hop1:
        for m in adj.get(n, []):
            if m != source and m not in hop1:
                hop2.add(m)
    reachable = sorted(hop1 | hop2)
    return {
        "source": source,
        "hop1": sorted(hop1),
        "hop2": sorted(hop2 - hop1),
        "reachable": reachable,
        "count": len(reachable),
    }


def compute_overview(issues: list[dict], rels: list[dict]) -> dict:
    """概览:节点 / 边 / 平均度 / 密度 / 类型分布。"""
    n_nodes = len(issues)
    n_edges = len(rels)
    # 简单有向图(不计自环)最大可能边数 V*(V-1)
    max_edges_dir = n_nodes * (n_nodes - 1) if n_nodes >= 2 else 1
    # 密度按有向图口径
    density = round(n_edges / max_edges_dir, 4) if max_edges_dir > 0 else 0.0

    # 平均度(有向):出度入度总和 / 节点数
    out_deg, in_deg = compute_degree(rels)
    total_degree = sum(out_deg.values()) + sum(in_deg.values())
    avg_degree = round(total_degree / n_nodes, 2) if n_nodes else 0.0

    # 关系类型分布
    rel_types: dict[str, int] = defaultdict(int)
    for r in rels:
        rel_types[r.get("relation", "unknown")] += 1

    return {
        "nodes": n_nodes,
        "edges": n_edges,
        "max_edges_directed": max_edges_dir,
        "density": density,
        "avg_degree_directed": avg_degree,
        "relation_types": dict(sorted(rel_types.items())),
    }


def compute_by_relation_type(rels: list[dict], top_k: int) -> dict[str, dict]:
    """按关系类型分组:边数 / 平均权重 / Top 出源节点 / Top 入汇节点。"""
    out_by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    in_by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    weights_by_type: dict[str, list[float]] = defaultdict(list)
    edges_by_type: dict[str, int] = defaultdict(int)

    for r in rels:
        rt = r.get("relation", "unknown")
        edges_by_type[rt] += 1
        w = r.get("weight")
        if isinstance(w, (int, float)):
            weights_by_type[rt].append(float(w))
        src = r.get("source")
        tgt = r.get("target")
        if src:
            out_by_type[rt][src] += 1
        if tgt:
            in_by_type[rt][tgt] += 1

    def top_k_of(d: dict[str, int], k: int) -> list[dict]:
        return [{"issue_id": iid, "count": c} for iid, c in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:k]]

    result: dict[str, dict] = {}
    all_types = set(out_by_type.keys()) | set(in_by_type.keys())
    for rt in sorted(all_types):
        ws = weights_by_type.get(rt, [])
        avg_w = round(sum(ws) / len(ws), 3) if ws else 0.0
        result[rt] = {
            "edges": edges_by_type.get(rt, 0),
            "avg_weight": avg_w,
            "top_out_source": top_k_of(out_by_type.get(rt, {}), top_k),
            "top_in_target": top_k_of(in_by_type.get(rt, {}), top_k),
        }
    return result


def compute_degree_ranking(out_deg: dict[str, int], in_deg: dict[str, int], top_k: int) -> dict:
    """节点度排序:总度 = 出度 + 入度。"""
    all_ids = set(out_deg.keys()) | set(in_deg.keys())
    rows = []
    for iid in all_ids:
        o = out_deg.get(iid, 0)
        i = in_deg.get(iid, 0)
        rows.append({"issue_id": iid, "out": o, "in": i, "total": o + i})
    rows.sort(key=lambda r: r["total"], reverse=True)
    return {
        "top_total_degree": rows[:top_k],
        "bottom_total_degree": [r for r in rows if r["total"] > 0][-top_k:] if any(r["total"] > 0 for r in rows) else [],
    }


# ============== 报告输出 ==============

def print_human_report(issues_path: Path, rels_path: Path, top_k: int, source: str, stats: dict) -> None:
    """输出人读报告。"""
    print(f"🔗 议题关系图分析报告 · SocietyAdvisor Phase 0 #4 工具链")
    print(f"   issues:     {issues_path}")
    print(f"   relations:  {rels_path}")
    print()

    issues_by_id = _load_issues_by_id_for_print(issues_path)

    # ── 1. 概览 ──
    ov = stats["overview"]
    print(f"━━━ 1. 概览 ━━━")
    print(f"   节点: {ov['nodes']} 个议题")
    print(f"   边:   {ov['edges']} 条(有向图最大可能 {ov['max_edges_directed']} 条)")
    print(f"   密度: {ov['density']}(有向图口径,边数/最大可能边数)")
    print(f"   平均度: {ov['avg_degree_directed']}(出度+入度总和/节点数)")
    if ov["relation_types"]:
        type_str = " / ".join(f"{k}={v}" for k, v in ov["relation_types"].items())
        print(f"   关系类型分布: {type_str}")
    print()

    # ── 2. 按关系类型分组 ──
    by_type = stats["by_relation_type"]
    print(f"━━━ 2. 按关系类型分组 ━━━")
    for rt, ts in by_type.items():
        print(f"   · {rt}: {ts['edges']} 条,均权 {ts['avg_weight']}")
        if ts["top_out_source"]:
            top = ", ".join(f"{n['issue_id']}({n['count']})" for n in ts["top_out_source"])
            print(f"     Top 出源: {top}")
        if ts["top_in_target"]:
            top = ", ".join(f"{n['issue_id']}({n['count']})" for n in ts["top_in_target"])
            print(f"     Top 入汇: {top}")
    print()

    # ── 3. 节点度 Top K ──
    deg = stats["degree_ranking"]
    print(f"━━━ 3. 节点度排序 Top {top_k}(总度 = 出度 + 入度) ━━━")
    if deg["top_total_degree"]:
        for i, r in enumerate(deg["top_total_degree"], 1):
            name = issues_by_id.get(r["issue_id"], {}).get("name", "")
            print(f"   {i}. {r['issue_id']} {name} · 总度={r['total']}(出{r['out']} 入{r['in']})")
    else:
        print(f"   _(无数据)_")
    print()

    # ── 4. 孤立节点 ──
    orphans = stats["orphans"]
    print(f"━━━ 4. 孤立节点(无任何边的议题) ━━━")
    if orphans:
        for oid in orphans:
            name = issues_by_id.get(oid, {}).get("name", "")
            print(f"   · {oid} {name}")
    else:
        print(f"   _(无孤立节点)_")
    print()

    # ── 5. 异常检测 ──
    anomalies = stats["anomalies"]
    print(f"━━━ 5. 异常检测 ━━━")
    if anomalies["self_loops"]:
        print(f"   · 自环边({len(anomalies['self_loops'])} 个): " + ", ".join(anomalies["self_loops"]))
    else:
        print(f"   · 自环边: 0")
    if anomalies["bidirectional"]:
        print(f"   · 双向边({len(anomalies['bidirectional'])} 对):")
        for d in anomalies["bidirectional"]:
            print(f"     - {d['a']} ⇄ {d['b']}")
    else:
        print(f"   · 双向边: 0 对")
    print()

    # ── 6. 2 跳扩散 ──
    if source:
        reach = stats["two_hop_reach"]
        print(f"━━━ 6. 2 跳扩散(以 {source} 为源) ━━━")
        if reach["count"] == 0:
            print(f"   · {source} 在图中无任何邻居,2 跳内无可达节点")
        else:
            name = issues_by_id.get(source, {}).get("name", "")
            print(f"   源: {source} {name}")
            print(f"   1 跳({len(reach['hop1'])} 个): {', '.join(reach['hop1']) if reach['hop1'] else '(无)'}")
            print(f"   2 跳新增({len(reach['hop2'])} 个): {', '.join(reach['hop2']) if reach['hop2'] else '(无)'}")
            print(f"   2 跳内总可达: {reach['count']} 个节点")


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
        description="SocietyAdvisor 议题关系图图论维度分析(密度 / 类型×权重 / 度 / 孤立 / 异常 / 2 跳扩散)",
    )
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, metavar="PATH", help=f"议题库路径(默认: {ISSUES_DEFAULT_PATH})")
    parser.add_argument("--relations", default=RELATIONS_DEFAULT_PATH, metavar="PATH", help=f"关系图路径(默认: {RELATIONS_DEFAULT_PATH})")
    parser.add_argument("--top", type=int, default=TOP_DEFAULT, metavar="K", help=f"各 Top K 取值(默认: {TOP_DEFAULT})")
    parser.add_argument("--source", metavar="ISSUE_ID", help="2 跳扩散示例源节点(如 issue-005)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式(机器可读)")
    parser.add_argument("--strict", action="store_true", help="严格模式:有孤立节点 / 双向边 / 自环 → exit 1")
    args = parser.parse_args()

    issues_path = Path(args.issues)
    rels_path = Path(args.relations)

    if not issues_path.exists():
        print(f"❌ 输入文件不存在: {issues_path}", file=sys.stderr)
        return 1
    if not rels_path.exists():
        print(f"❌ 输入文件不存在: {rels_path}", file=sys.stderr)
        return 1

    issues = load_issues(issues_path)
    rels = load_relations(rels_path)

    # 计算所有维度
    overview = compute_overview(issues, rels)
    by_type = compute_by_relation_type(rels, args.top)
    out_deg, in_deg = compute_degree(rels)
    degree_ranking = compute_degree_ranking(out_deg, in_deg, args.top)
    orphans = find_orphans(issues, rels)
    bidir = find_bidirectional_edges(rels)
    self_loops = find_self_loops(rels)
    anomalies = {"self_loops": self_loops, "bidirectional": bidir}

    # 2 跳扩散(可选)
    two_hop = None
    if args.source:
        adj = build_graph(rels)
        two_hop = two_hop_reach(adj, args.source)

    stats = {
        "overview": overview,
        "by_relation_type": by_type,
        "degree_ranking": degree_ranking,
        "orphans": orphans,
        "anomalies": anomalies,
        "two_hop_reach": two_hop,
    }

    if args.json:
        out = {
            "issues_path": str(issues_path),
            "relations_path": str(rels_path),
            "source_filter": args.source,
            "overview": overview,
            "by_relation_type": by_type,
            "degree_ranking": {
                "top_total_degree": degree_ranking["top_total_degree"][:args.top],
                "bottom_total_degree": degree_ranking["bottom_total_degree"][-args.top:] if degree_ranking["bottom_total_degree"] else [],
            },
            "orphans": orphans,
            "anomalies": anomalies,
            "two_hop_reach": two_hop,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_human_report(issues_path, rels_path, args.top, args.source, stats)

    # ── 退出码 ──
    if args.strict:
        n_issues = 0
        if orphans:
            n_issues += len(orphans)
        if bidir:
            n_issues += len(bidir)
        if self_loops:
            n_issues += len(self_loops)
        if n_issues > 0:
            print(f"\n❌ 严格模式:发现 {len(orphans)} 个孤立节点 / {len(bidir)} 对双向边 / {len(self_loops)} 个自环,exit 1", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
