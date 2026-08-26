#!/usr/bin/env python3
"""
md_to_json.py · SocietyAdvisor Phase 0 #1 + #3

将 YAML 转换为 JSON,服务于:
  1. 后续 SQLite 灌库(issues / issue_relations 表,见 4.3 节数据架构)
  2. Web App 议题列表 / 图谱 API 渲染数据源
  3. 飞书日报"监控议题"引用

字段规范:
  issues 模式: data/issues.schema.md v1.0
  relations 模式: data/issue_relations.schema.md v1.0

用法:
  python3 scripts/md_to_json.py                       # issues 模式: data/issues.yaml → data/issues.json
  python3 scripts/md_to_json.py --mode relations      # relations 模式: data/issue_relations.yaml → data/issue_relations.json
  python3 scripts/md_to_json.py input.yaml out.json   # 自定义输入输出
  python3 scripts/md_to_json.py --pretty              # 美化输出
  python3 scripts/md_to_json.py --category 经济        # 按 category 过滤输出(仅 issues)
  python3 scripts/md_to_json.py --min-heat 70          # 按 heat_score 阈值过滤(仅 issues)
  python3 scripts/md_to_json.py --check-issues path   # relations 模式:校验 source/target 必须在 issues.yaml 存在

依赖:PyYAML (pip3 install pyyaml)
"""

import sys
import json
import argparse
import datetime
from pathlib import Path

# issues 模式
ISSUES_DEFAULT_INPUT = "data/issues.yaml"
ISSUES_DEFAULT_OUTPUT = "data/issues.json"
ISSUES_SCHEMA_VERSION = "1.0"
ALLOWED_CATEGORIES = {"经济", "教育", "科技", "环境", "社会"}

# relations 模式
RELATIONS_DEFAULT_INPUT = "data/issue_relations.yaml"
RELATIONS_DEFAULT_OUTPUT = "data/issue_relations.json"
RELATIONS_SCHEMA_VERSION = "1.0"
ALLOWED_RELATIONS = {"cause", "influence", "related"}


def load_yaml(path: Path) -> dict:
    """读取 yaml;缺失依赖给出明确指引。"""
    try:
        import yaml
    except ImportError:
        print("❌ 缺少依赖 PyYAML\n   安装: pip3 install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_issue(raw: dict) -> dict:
    """对齐 schema:字段补齐 + 类型规范化。"""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "category": raw.get("category"),
        "description": (raw.get("description") or "").strip(),
        "tags": list(raw.get("tags", [])),
        "heat_score": int(raw.get("heat_score", 0)),
        "created_at": str(raw.get("created_at", "")),
    }


def validate(issue: dict) -> list[str]:
    """单条议题 schema 校验,返回错误列表(空 = 通过)。"""
    errs = []
    if not issue["id"] or not str(issue["id"]).startswith("issue-"):
        errs.append(f"id 格式异常: {issue['id']!r}")
    if not issue["name"]:
        errs.append("name 缺失")
    if issue["category"] not in ALLOWED_CATEGORIES:
        errs.append(f"category 不在白名单: {issue['category']!r}")
    if not (50 <= len(issue["description"]) <= 400):
        errs.append(f"description 长度越界(50-400): {len(issue['description'])}")
    if not (3 <= len(issue["tags"]) <= 5):
        errs.append(f"tags 数量越界(3-5): {len(issue['tags'])}")
    if not (0 <= issue["heat_score"] <= 100):
        errs.append(f"heat_score 越界(0-100): {issue['heat_score']}")
    return errs


def main():
    parser = argparse.ArgumentParser(description="SocietyAdvisor · yaml → json 转换")
    parser.add_argument(
        "--mode",
        choices=["issues", "relations"],
        default="issues",
        help="转换模式:issues(默认)/ relations",
    )
    parser.add_argument("input", nargs="?", default=None, help="输入 yaml 路径(默认按 mode 选)")
    parser.add_argument("output", nargs="?", default=None, help="输出 json 路径(默认按 mode 选)")
    parser.add_argument("--pretty", action="store_true", help="美化输出(缩进 2)")
    parser.add_argument("--category", help="按 category 过滤(如:经济,仅 issues)")
    parser.add_argument("--min-heat", type=int, help="按 heat_score 阈值过滤(仅 issues)")
    parser.add_argument("--strict", action="store_true", help="严格模式:schema 校验失败则 exit 1")
    parser.add_argument(
        "--check-issues",
        metavar="ISSUES_PATH",
        help="relations 模式:校验 source/target 必须存在于指定的 issues.yaml",
    )
    args = parser.parse_args()

    if args.mode == "relations":
        run_relations(args)
    else:
        run_issues(args)


def run_issues(args):
    in_path = Path(args.input or ISSUES_DEFAULT_INPUT)
    out_path = Path(args.output or ISSUES_DEFAULT_OUTPUT)

    if not in_path.exists():
        print(f"❌ 输入文件不存在: {in_path}", file=sys.stderr)
        sys.exit(1)

    data = load_yaml(in_path)
    raw_issues = data.get("issues", [])
    normalized = [normalize_issue(it) for it in raw_issues]

    # schema 校验
    all_errs = []
    for it in normalized:
        errs = validate(it)
        if errs:
            all_errs.append((it["id"], errs))
    if all_errs:
        print(f"⚠️  schema 校验发现 {len(all_errs)} 条异常:", file=sys.stderr)
        for iid, errs in all_errs:
            print(f"   - {iid}: {'; '.join(errs)}", file=sys.stderr)
        if args.strict:
            sys.exit(1)

    # 过滤
    before = len(normalized)
    if args.category:
        normalized = [it for it in normalized if it["category"] == args.category]
    if args.min_heat is not None:
        normalized = [it for it in normalized if it["heat_score"] >= args.min_heat]

    # 排序:heat_score 降序
    normalized.sort(key=lambda x: (-x["heat_score"], x["id"]))

    result = {
        "meta": {
            "source": str(in_path),
            "count": len(normalized),
            "total_before_filter": before,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "schema_version": ISSUES_SCHEMA_VERSION,
            "filters": {
                "category": args.category,
                "min_heat": args.min_heat,
            },
        },
        "issues": normalized,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    # 简明报告
    print(f"✅ {len(normalized)} 条议题 → {out_path}")
    if before != len(normalized):
        print(f"   过滤: {before} → {len(normalized)} (category={args.category}, min_heat={args.min_heat})")
    cats = {}
    for it in normalized:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        bar = "█" * n
        print(f"   {cat}: {n:>2}  {bar}")
    avg_heat = sum(it["heat_score"] for it in normalized) / max(len(normalized), 1)
    print(f"   平均热度: {avg_heat:.1f}")


# ─────────────────────────────────────────────────────────
# relations 模式(Phase 0 #3)
# ─────────────────────────────────────────────────────────

def normalize_relation(raw: dict) -> dict:
    """对齐 issue_relations schema:字段补齐 + 类型规范化。"""
    return {
        "source": raw.get("source"),
        "target": raw.get("target"),
        "relation": raw.get("relation"),
        "weight": round(float(raw.get("weight", 0.0)), 2),
        "note": (raw.get("note") or "").strip(),
        "created_at": str(raw.get("created_at", "")),
    }


def validate_relation(rel: dict) -> list[str]:
    """单条关系 schema 校验,返回错误列表(空 = 通过)。"""
    errs = []
    if not rel["source"] or not str(rel["source"]).startswith("issue-"):
        errs.append(f"source 格式异常: {rel['source']!r}")
    if not rel["target"] or not str(rel["target"]).startswith("issue-"):
        errs.append(f"target 格式异常: {rel['target']!r}")
    if rel["source"] == rel["target"]:
        errs.append("自环禁止:source == target")
    if rel["relation"] not in ALLOWED_RELATIONS:
        errs.append(f"relation 不在白名单({sorted(ALLOWED_RELATIONS)}): {rel['relation']!r}")
    if not (0.0 <= rel["weight"] <= 1.0):
        errs.append(f"weight 越界(0.0-1.0): {rel['weight']}")
    if not (30 <= len(rel["note"]) <= 300):
        errs.append(f"note 长度越界(30-300): {len(rel['note'])}")
    if not rel["created_at"]:
        errs.append("created_at 缺失")
    return errs


def load_issue_ids(path: Path) -> set[str]:
    """读取 issues.yaml,返回所有合法议题 ID 集合。"""
    data = load_yaml(path)
    return {it["id"] for it in data.get("issues", []) if it.get("id")}


def run_relations(args):
    in_path = Path(args.input or RELATIONS_DEFAULT_INPUT)
    out_path = Path(args.output or RELATIONS_DEFAULT_OUTPUT)
    check_issues_path = Path(args.check_issues) if args.check_issues else None

    if not in_path.exists():
        print(f"❌ 输入文件不存在: {in_path}", file=sys.stderr)
        sys.exit(1)

    data = load_yaml(in_path)
    raw_relations = data.get("relations", [])
    normalized = [normalize_relation(r) for r in raw_relations]

    # schema 校验
    all_errs = []
    for rel in normalized:
        errs = validate_relation(rel)
        if errs:
            all_errs.append((rel["source"], rel["target"], errs))
    if all_errs:
        print(f"⚠️  schema 校验发现 {len(all_errs)} 条异常:", file=sys.stderr)
        for s, t, errs in all_errs:
            print(f"   - {s} → {t}: {'; '.join(errs)}", file=sys.stderr)

    # 唯一性校验(source, target, relation) 三元组
    seen = set()
    dup_errs = []
    for rel in normalized:
        key = (rel["source"], rel["target"], rel["relation"])
        if key in seen:
            dup_errs.append(key)
        seen.add(key)
    if dup_errs:
        print(f"⚠️  重复边 {len(dup_errs)} 条:", file=sys.stderr)
        for s, t, r in dup_errs:
            print(f"   - {s} -[{r}]-> {t}", file=sys.stderr)

    # 可选:外部 issues 引用一致性
    external_check_errs = []
    if check_issues_path:
        if not check_issues_path.exists():
            print(f"❌ --check-issues 文件不存在: {check_issues_path}", file=sys.stderr)
            sys.exit(1)
        valid_ids = load_issue_ids(check_issues_path)
        for rel in normalized:
            for field in ("source", "target"):
                if rel[field] not in valid_ids:
                    external_check_errs.append((field, rel[field]))
        if external_check_errs:
            print(f"⚠️  引用一致性校验失败 {len(external_check_errs)} 处:", file=sys.stderr)
            for field, iid in external_check_errs:
                print(f"   - {field}={iid} 不在 {check_issues_path}", file=sys.stderr)

    fatal = bool(all_errs) or bool(dup_errs) or bool(external_check_errs)
    if args.strict and fatal:
        sys.exit(1)

    # 排序:weight 降序 → source asc → target asc
    normalized.sort(key=lambda x: (-x["weight"], x["source"], x["target"]))

    # 关系类型分布
    rel_dist = {}
    for rel in normalized:
        rel_dist[rel["relation"]] = rel_dist.get(rel["relation"], 0) + 1

    # 入度/出度统计(节点维度)
    out_degree = {}
    in_degree = {}
    for rel in normalized:
        out_degree[rel["source"]] = out_degree.get(rel["source"], 0) + 1
        in_degree[rel["target"]] = in_degree.get(rel["target"], 0) + 1

    result = {
        "meta": {
            "source": str(in_path),
            "count": len(normalized),
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "schema_version": RELATIONS_SCHEMA_VERSION,
            "relation_distribution": rel_dist,
            "check_issues": str(check_issues_path) if check_issues_path else None,
            "node_stats": {
                "out_degree": out_degree,
                "in_degree": in_degree,
            },
        },
        "relations": normalized,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    # 简明报告
    print(f"✅ {len(normalized)} 条关系边 → {out_path}")
    avg_w = sum(r["weight"] for r in normalized) / max(len(normalized), 1)
    print(f"   平均权重: {avg_w:.2f}")
    for rt, n in sorted(rel_dist.items(), key=lambda x: -x[1]):
        bar = "█" * n
        print(f"   {rt:>10}: {n:>2}  {bar}")
    # Top 节点(出度)
    top_out = sorted(out_degree.items(), key=lambda x: -x[1])[:5]
    if top_out:
        print("   最高出度节点(影响他人最多):")
        for nid, n in top_out:
            print(f"     - {nid}: {n}")
    top_in = sorted(in_degree.items(), key=lambda x: -x[1])[:5]
    if top_in:
        print("   最高入度节点(被影响最多):")
        for nid, n in top_in:
            print(f"     - {nid}: {n}")


if __name__ == "__main__":
    main()
