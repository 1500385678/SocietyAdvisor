#!/usr/bin/env python3
"""
phase_status.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链再扩展(9/15 T5 周期)

聚合项目全景的"阶段状态"CLI 报告:数据文件清单 + 议题库/关系图/声量快照 quick stats
+ 工具链索引(从脚本头注释抓用途)+ Phase 0/1 进度(基于 项目开发计划.md grep)
+ 健康检查(议题 id 唯一 / 关系图 0 孤儿边 / 声量快照外键命中)。

与现有工具链的定位:
  - issue_summary.py        → 议题库 + 关系图静态盘点(本脚本的子集)
  - issue_trend.py          → 时序趋势(声量快照侧)
  - issue_relations_analysis.py → 关系图图论深度
  - validate_pulse.py       → 声量快照数据校验(本脚本的健康检查更轻量)
  - daily_report.py         → 业务侧日报生成(对外)
  - phase_status.py(本脚本) → 工程侧"开发者 dashboard"快照(对内),把上面 5 个脚本 + Phase 0/1
                              进度 + 数据文件清单 + 工具链索引拼到一个 CLI 输出里,作
                              为 T5 周期写代码前的 sanity check 与 T1 巡检后的人工
                              快速核对入口

用法:
  python3 scripts/phase_status.py                          # 默认人读报告
  python3 scripts/phase_status.py --json                   # 机器可读 JSON
  python3 scripts/phase_status.py --strict                 # 有健康问题 → exit 1
  python3 scripts/phase_status.py --plan 项目开发计划.md   # 自定义计划文件路径
  python3 scripts/phase_status.py --scripts scripts/       # 自定义 scripts 目录

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union

ISSUES_DEFAULT_PATH = "data/issues.yaml"
RELATIONS_DEFAULT_PATH = "data/issue_relations.yaml"
PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
PLAN_DEFAULT_PATH = "项目开发计划.md"
SCRIPTS_DEFAULT_DIR = "scripts/"

# Phase 0 / Phase 1 章节标题(grep 锚点)
PHASE0_HEADING = "## 五、Phase 0 资产盘点"
PHASE1_HEADING = "## 六、Phase 1 MVP"

# 健康检查阈值
PULSE_EMOTION_SUM_TOLERANCE = 0.01


# ============== 通用工具 ==============

def load_yaml(path: Path) -> Union[dict, list]:
    """读取 yaml;缺失依赖给出明确指引。"""
    try:
        import yaml
    except ImportError:
        print("❌ 缺少依赖 PyYAML\n   安装: pip3 install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """避免除零;分母为 0 返回 default。"""
    return numerator / denominator if denominator else default


def _file_meta(path: Path) -> dict:
    """单个文件的元信息(存在/缺失/大小/行数/mtime)。"""
    if not path.exists():
        return {"path": str(path), "exists": False}
    text = path.read_text(encoding="utf-8")
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "mtime_iso": stat.st_mtime,  # 浮点时间戳;人读报告里再格式化为 YYYY-MM-DD
    }


def _format_mdate(mtime: float) -> str:
    """浮点时间戳 → YYYY-MM-DD(本地时区)。"""
    import datetime as dt
    return dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


# ============== 数据加载 ==============

def load_issues(path: Path) -> list[dict]:
    """读取 issues.yaml,返回议题字典列表。"""
    data = load_yaml(path)
    issues = data.get("issues", []) if isinstance(data, dict) else []
    if not isinstance(issues, list):
        print(f"❌ {path}: 顶层 issues 字段不是列表", file=sys.stderr)
        sys.exit(1)
    return issues


def load_relations(path: Path) -> list[dict]:
    """读取 issue_relations.yaml;文件缺失返回空(关系图是可选的)。"""
    if not path.exists():
        return []
    data = load_yaml(path)
    rels = data.get("relations", []) if isinstance(data, dict) else []
    return rels if isinstance(rels, list) else []


def load_pulse_snapshots(path: Path) -> list[dict]:
    """读取 pulse_snapshots.yaml;文件缺失返回空。"""
    if not path.exists():
        return []
    data = load_yaml(path)
    snaps = data.get("snapshots", []) if isinstance(data, dict) else data
    return snaps if isinstance(snaps, list) else []


# ============== 各维度计算 ==============

def compute_data_files(meta_paths: list[Path]) -> list[dict]:
    """数据文件清单 + 元信息。"""
    return [_file_meta(p) for p in meta_paths]


def compute_issues_stats(issues: list[dict]) -> dict:
    """议题库 quick stats。"""
    by_category: dict[str, list[dict]] = {}
    heat_scores = []
    for it in issues:
        cat = it.get("category", "(未分类)")
        by_category.setdefault(cat, []).append(it)
        heat = it.get("heat_score")
        if isinstance(heat, (int, float)):
            heat_scores.append(float(heat))
    return {
        "count": len(issues),
        "by_category": {
            cat: {
                "count": len(items),
                "avg_heat": round(safe_div(
                    sum(float(i.get("heat_score", 0)) for i in items if isinstance(i.get("heat_score"), (int, float))),
                    sum(1 for i in items if isinstance(i.get("heat_score"), (int, float)))
                ), 1),
            }
            for cat, items in sorted(by_category.items())
        },
        "heat": {
            "min": min(heat_scores) if heat_scores else 0,
            "max": max(heat_scores) if heat_scores else 0,
            "avg": round(safe_div(sum(heat_scores), len(heat_scores)), 1),
        },
    }


def compute_relations_stats(rels: list[dict]) -> dict:
    """关系图 quick stats。"""
    by_type: dict[str, int] = {}
    weights = []
    for r in rels:
        by_type[r.get("relation", "(无)")] = by_type.get(r.get("relation", "(无)"), 0) + 1
        w = r.get("weight")
        if isinstance(w, (int, float)):
            weights.append(float(w))
    return {
        "count": len(rels),
        "by_type": by_type,
        "weight_avg": round(safe_div(sum(weights), len(weights)), 3),
    }


def compute_pulse_stats(snaps: list[dict]) -> dict:
    """声量快照 quick stats。"""
    by_issue: dict[str, int] = {}
    by_source: dict[str, int] = {}
    dates = []
    for s in snaps:
        by_issue[s.get("issue_id", "(无)")] = by_issue.get(s.get("issue_id", "(无)"), 0) + 1
        by_source[s.get("source", "(无)")] = by_source.get(s.get("source", "(无)"), 0) + 1
        d = s.get("snapshot_date")
        if d:
            dates.append(d)
    return {
        "count": len(snaps),
        "by_issue": dict(sorted(by_issue.items())),
        "by_source": by_source,
        "date_range": [min(dates), max(dates)] if dates else None,
    }


def compute_phase_progress(plan_path: Path) -> dict:
    """从 项目开发计划.md 读 Phase 0 / Phase 1 章节,grep -[x] / -[ ] 计数。"""
    if not plan_path.exists():
        return {"phase0": None, "phase1": None, "error": f"{plan_path} 不存在"}
    text = plan_path.read_text(encoding="utf-8")

    def _slice_section(heading: str) -> Optional[str]:
        """从 heading 起到下一个 ## 章节标题(行首)之前。

        关键修复:heading 必须出现在**行首**(用 re.MULTILINE 锚定 ^),
        否则正文中提到 `## 六、Phase 1 MVP` 这种字符串时(例如本脚本 9/15 续
        条目里就引用了这两个锚点),`text.find` 会命中非章节标题位置,导致
        切到错误的段落。
        """
        m_head = re.search(r"^" + re.escape(heading), text, flags=re.MULTILINE)
        if m_head is None:
            return None
        head_start = m_head.start()
        rest = text[head_start + len(heading):]
        # 找下一个 **行首** 的章节标题(`^## <编号>、`)。re.MULTILINE 让 ^ 匹配每行行首。
        nxt = re.search(r"^## \S+、", rest, flags=re.MULTILINE)
        return rest[: nxt.start()] if nxt else rest

    def _count(section: Optional[str]) -> Optional[dict]:
        if section is None:
            return None
        done = len(re.findall(r"^- \[x\]", section, flags=re.MULTILINE))
        todo = len(re.findall(r"^- \[ \]", section, flags=re.MULTILINE))
        return {"done": done, "todo": todo, "total_section_lines": section.count("\n")}

    return {
        "phase0": _count(_slice_section(PHASE0_HEADING)),
        "phase1": _count(_slice_section(PHASE1_HEADING)),
    }


def compute_toolchain(scripts_dir: Path) -> list[dict]:
    """工具链索引:列 scripts/ 下所有 .py / .sh,每个文件的用途来自头注释首段。"""
    if not scripts_dir.exists():
        return []
    out = []
    for p in sorted(scripts_dir.iterdir()):
        if p.suffix not in (".py", ".sh"):
            continue
        if p.name.startswith("__"):
            continue
        # 抓头注释(只取 # 开头的连续行)
        purpose = _extract_purpose(p)
        out.append({
            "name": p.name,
            "kind": "python" if p.suffix == ".py" else "shell",
            "purpose": purpose,
            "size_bytes": p.stat().st_size,
            "mtime_iso": p.stat().st_mtime,
        })
    return out


def _extract_purpose(path: Path) -> str:
    """从脚本头提取"用途"。

    支持两种风格:
      A. Shell / pyhacker 风格:连续 # 注释块(无三引号)
      B. Python 风格:三引号 docstring(即使前面有 #! shebang 也算 docstring)

    取第一段非空、非"用法:" / "依赖:" 起始的描述行。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""

    # 先尝试三引号 docstring(只取第一个)
    if path.suffix == ".py":
        m = re.search(r'"""(.*?)"""', text, flags=re.DOTALL)
        if m:
            return _pick_purpose_line(m.group(1))

    # 否则:看前 40 行 # 注释
    lines = text.splitlines()[:40]
    block = []
    in_block = False
    for line in lines:
        s = line.rstrip()
        if not in_block:
            if s.startswith("#!") or s == "":
                continue
            if s.startswith("#"):
                in_block = True
                block.append(s)
        else:
            if s.startswith("#"):
                block.append(s)
            else:
                break
    if not block:
        return ""
    return _pick_purpose_line("\n".join(block))


def _pick_purpose_line(text: str) -> str:
    """从一段文本中挑出第一行"有用"的描述:去掉 # 装饰 + 跳过 用法: / 依赖: / 空行。"""
    for line in text.splitlines():
        stripped = re.sub(r"^#+\s*", "", line).strip()
        if not stripped:
            continue
        if stripped.startswith("用法") or stripped.startswith("依赖"):
            continue
        return stripped
    return ""


def compute_health(issues: list[dict], rels: list[dict], snaps: list[dict]) -> dict:
    """健康检查:议题 id 唯一 / 关系图 0 孤儿边 / 声量快照外键命中。"""
    issues_by_id = {it.get("id"): it for it in issues}

    # 1) 议题 id 唯一
    id_counts: dict[str, int] = {}
    for it in issues:
        iid = it.get("id")
        if iid:
            id_counts[iid] = id_counts.get(iid, 0) + 1
    duplicate_ids = [iid for iid, c in id_counts.items() if c > 1]

    # 2) 关系图孤儿边
    orphan_edges = []
    for r in rels:
        src = r.get("source")
        tgt = r.get("target")
        if src not in issues_by_id or tgt not in issues_by_id:
            orphan_edges.append({
                "source": src,
                "target": tgt,
                "reason": (
                    "source 不在议题库" if src not in issues_by_id else "target 不在议题库"
                ),
            })

    # 3) 声量快照外键 + 情感加和 1.0±0.01
    pulse_issues_missing = []
    pulse_emotion_errors = []
    for s in snaps:
        iid = s.get("issue_id")
        if iid not in issues_by_id:
            pulse_issues_missing.append(iid)
        emo = s.get("sentiment")
        if isinstance(emo, dict):
            total = sum(float(v) for v in emo.values() if isinstance(v, (int, float)))
            if abs(total - 1.0) > PULSE_EMOTION_SUM_TOLERANCE:
                pulse_emotion_errors.append({
                    "issue_id": iid,
                    "snapshot_date": s.get("snapshot_date"),
                    "sentiment_sum": round(total, 3),
                })

    # 4) 议题热度合理性(0-100 范围)
    heat_out_of_range = []
    for it in issues:
        h = it.get("heat_score")
        if isinstance(h, (int, float)) and not (0 <= h <= 100):
            heat_out_of_range.append({"id": it.get("id"), "heat_score": h})

    problems = []
    if duplicate_ids:
        problems.append(f"议题 id 重复: {duplicate_ids}")
    if orphan_edges:
        problems.append(f"关系图孤儿边: {len(orphan_edges)} 条")
    if pulse_issues_missing:
        problems.append(f"声量快照外键缺失: {len(set(pulse_issues_missing))} 个 issue_id")
    if pulse_emotion_errors:
        problems.append(f"声量情感加和异常: {len(pulse_emotion_errors)} 条")
    if heat_out_of_range:
        problems.append(f"议题热度超 0-100 范围: {len(heat_out_of_range)} 条")

    return {
        "duplicate_ids": duplicate_ids,
        "orphan_edges_count": len(orphan_edges),
        "orphan_edges_sample": orphan_edges[:3],
        "pulse_issues_missing_count": len(set(pulse_issues_missing)),
        "pulse_emotion_errors_count": len(pulse_emotion_errors),
        "heat_out_of_range_count": len(heat_out_of_range),
        "problems": problems,
        "is_healthy": len(problems) == 0,
    }


# ============== 报告渲染 ==============

def render_human(stats: dict, scripts_dir_name: str) -> str:
    """渲染人读报告。"""
    lines = []
    files = stats["data_files"]
    issues_s = stats["issues"]
    rels_s = stats["relations"]
    pulse_s = stats["pulse"]
    phase = stats["phase_progress"]
    toolchain = stats["toolchain"]
    health = stats["health"]

    lines.append("━━━ 0. 数据文件清单 ━━━")
    for f in files:
        if not f["exists"]:
            lines.append(f"   · {f['path']}  ❌ 缺失")
            continue
        mdate = _format_mdate(f["mtime_iso"])
        lines.append(f"   · {f['path']}  ✅  {f['size_bytes']:>5} 字节 / {f['lines']:>3} 行  ({mdate})")
    lines.append("")

    lines.append("━━━ 1. 议题库 quick stats ━━━")
    lines.append(f"   总数: {issues_s['count']} 条")
    if issues_s["count"]:
        lines.append(f"   热度范围: min={issues_s['heat']['min']} / max={issues_s['heat']['max']} / avg={issues_s['heat']['avg']}")
        lines.append(f"   按 category 分组({len(issues_s['by_category'])} 类):")
        for cat, info in issues_s["by_category"].items():
            lines.append(f"     - {cat}: {info['count']} 条 / 均热 {info['avg_heat']}")
    lines.append("")

    lines.append("━━━ 2. 关系图 quick stats ━━━")
    lines.append(f"   边数: {rels_s['count']} 条")
    if rels_s["count"]:
        types_str = " / ".join(f"{k}={v}" for k, v in sorted(rels_s["by_type"].items()))
        lines.append(f"   类型分布: {types_str}")
        lines.append(f"   平均权重: {rels_s['weight_avg']}")
    else:
        lines.append("   _(关系图为空)_")
    lines.append("")

    lines.append("━━━ 3. 声量快照 quick stats ━━━")
    lines.append(f"   总数: {pulse_s['count']} 条")
    if pulse_s["count"]:
        issues_top = sorted(pulse_s["by_issue"].items(), key=lambda kv: -kv[1])[:5]
        lines.append(f"   覆盖议题数: {len(pulse_s['by_issue'])} 个")
        lines.append(f"   来源分布: {pulse_s['by_source']}")
        lines.append(f"   Top 5 议题(按快照数): " + " / ".join(f"{iid}={n}" for iid, n in issues_top))
        if pulse_s["date_range"]:
            lines.append(f"   数据日期范围: {pulse_s['date_range'][0]} ~ {pulse_s['date_range'][1]}")
    else:
        lines.append("   _(声量快照为空)_")
    lines.append("")

    lines.append("━━━ 4. Phase 进度(基于 项目开发计划.md grep) ━━━")
    if phase.get("error"):
        lines.append(f"   ❌ {phase['error']}")
    else:
        p0 = phase["phase0"]
        p1 = phase["phase1"]
        if p0 is None:
            lines.append(f"   · Phase 0 章节: 未找到({PHASE0_HEADING})")
        else:
            lines.append(f"   · Phase 0 资产盘点: done={p0['done']} / todo={p0['todo']}({p0['done']}/{p0['done'] + p0['todo']})")
        if p1 is None:
            lines.append(f"   · Phase 1 MVP 章节: 未找到({PHASE1_HEADING})")
        else:
            lines.append(f"   · Phase 1 MVP:      done={p1['done']} / todo={p1['todo']}({p1['done']}/{p1['done'] + p1['todo']})")
    lines.append("")

    lines.append(f"━━━ 5. 工具链({scripts_dir_name}*.py / *.sh) ━━━")
    if not toolchain:
        lines.append(f"   _({scripts_dir_name} 目录为空或不存在)_")
    else:
        lines.append(f"   共 {len(toolchain)} 个脚本:")
        for t in toolchain:
            mdate = _format_mdate(t["mtime_iso"])
            purpose = t["purpose"] or "(无头注释)"
            lines.append(f"     - {t['name']:<32} [{t['kind']:<6}] {mdate}  {purpose[:80]}")
    lines.append("")

    lines.append("━━━ 6. 健康检查 ━━━")
    if health["is_healthy"]:
        lines.append("   ✅ 全部健康(议题 id 唯一 / 关系图 0 孤儿边 / 声量外键命中 / 情感加和 1.0±0.01 / 热度 0-100 范围)")
    else:
        lines.append("   ❌ 发现问题:")
        for prob in health["problems"]:
            lines.append(f"     - {prob}")
        if health["orphan_edges_sample"]:
            lines.append(f"     - 孤儿边样例(前 3): {health['orphan_edges_sample']}")
    lines.append("")

    return "\n".join(lines)


# ============== 主流程 ==============

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 工程侧阶段状态报告(数据文件 + 议题库/关系图/声量快照 + Phase 0/1 进度 + 工具链索引 + 健康检查)",
    )
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, metavar="PATH", help=f"议题库路径(默认: {ISSUES_DEFAULT_PATH})")
    parser.add_argument("--relations", default=RELATIONS_DEFAULT_PATH, metavar="PATH", help=f"关系图路径(默认: {RELATIONS_DEFAULT_PATH})")
    parser.add_argument("--pulse", default=PULSE_DEFAULT_PATH, metavar="PATH", help=f"声量快照路径(默认: {PULSE_DEFAULT_PATH})")
    parser.add_argument("--plan", default=PLAN_DEFAULT_PATH, metavar="PATH", help=f"项目开发计划路径(默认: {PLAN_DEFAULT_PATH})")
    parser.add_argument("--scripts", default=SCRIPTS_DEFAULT_DIR, metavar="DIR", help=f"scripts/ 目录(默认: {SCRIPTS_DEFAULT_DIR})")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式(机器可读)")
    parser.add_argument("--strict", action="store_true", help="严格模式:有任何健康问题 → exit 1")
    args = parser.parse_args()

    issues_path = Path(args.issues)
    rels_path = Path(args.relations)
    pulse_path = Path(args.pulse)
    plan_path = Path(args.plan)
    scripts_dir = Path(args.scripts)

    # ── 关键文件:议题库缺失 → 直接退出 ──
    if not issues_path.exists():
        print(f"❌ 议题库不存在: {issues_path}", file=sys.stderr)
        return 1

    issues = load_issues(issues_path)
    rels = load_relations(rels_path)
    snaps = load_pulse_snapshots(pulse_path)

    # 数据文件清单:固定 6 个核心文件
    meta_paths = [
        Path("data/issues.yaml"),
        Path("data/issue_relations.yaml"),
        Path("data/pulse_snapshots.yaml"),
        Path(args.plan),
        Path("README.md"),
        Path("社会顾问开发架构与计划.md"),
    ]
    data_files = compute_data_files(meta_paths)

    stats = {
        "data_files": data_files,
        "issues": compute_issues_stats(issues),
        "relations": compute_relations_stats(rels),
        "pulse": compute_pulse_stats(snaps),
        "phase_progress": compute_phase_progress(plan_path),
        "toolchain": compute_toolchain(scripts_dir),
        "health": compute_health(issues, rels, snaps),
    }

    if args.json:
        # JSON 输出:1) mtime_iso 浮点不方便看,转 ISO 字符串;2) pulse date → str
        for f in stats["data_files"]:
            if f.get("exists"):
                f["mtime_date"] = _format_mdate(f["mtime_iso"])
        for t in stats["toolchain"]:
            t["mtime_date"] = _format_mdate(t["mtime_iso"])
        # pulse.date_range 里的 date 对象转 ISO 字符串
        dr = stats["pulse"].get("date_range")
        if dr and not isinstance(dr[0], str):
            stats["pulse"]["date_range"] = [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in dr]
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(render_human(stats, args.scripts))

    # 健康检查退出码
    if args.strict and not stats["health"]["is_healthy"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())