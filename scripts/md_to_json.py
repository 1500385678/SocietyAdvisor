#!/usr/bin/env python3
"""
md_to_json.py · SocietyAdvisor Phase 0 #1

将 data/issues.yaml(结构化议题库)转换为 JSON,服务于:
  1. 后续 SQLite 灌库(issues 表,见 4.3 节数据架构)
  2. Web App 议题列表 API 渲染数据源
  3. 飞书日报"监控议题"引用

字段规范遵循 data/issues.schema.md v1.0:
  id / name / category / description / tags / heat_score / created_at

用法:
  python3 scripts/md_to_json.py                       # 默认: data/issues.yaml → data/issues.json
  python3 scripts/md_to_json.py input.yaml out.json   # 自定义输入输出
  python3 scripts/md_to_json.py --pretty              # 美化输出
  python3 scripts/md_to_json.py --category 经济        # 按 category 过滤输出
  python3 scripts/md_to_json.py --min-heat 70          # 按 heat_score 阈值过滤

依赖:PyYAML (pip3 install pyyaml)
"""

import sys
import json
import argparse
import datetime
from pathlib import Path

DEFAULT_INPUT = "data/issues.yaml"
DEFAULT_OUTPUT = "data/issues.json"
SCHEMA_VERSION = "1.0"

# 字段规范见 data/issues.schema.md v1.0
ALLOWED_CATEGORIES = {"经济", "教育", "科技", "环境", "社会"}


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
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT, help="输入 yaml 路径")
    parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT, help="输出 json 路径")
    parser.add_argument("--pretty", action="store_true", help="美化输出(缩进 2)")
    parser.add_argument("--category", help="按 category 过滤(如:经济)")
    parser.add_argument("--min-heat", type=int, help="按 heat_score 阈值过滤")
    parser.add_argument("--strict", action="store_true", help="严格模式:schema 校验失败则 exit 1")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

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
            "schema_version": SCHEMA_VERSION,
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


if __name__ == "__main__":
    main()
