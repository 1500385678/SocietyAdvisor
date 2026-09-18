#!/usr/bin/env python3
"""
issue_diff.py · SocietyAdvisor Phase 0 #4 质量层 · 工具链再扩展(9/19 T5 周期)

单议题跨时间点对比 CLI。聚合 data/issues.yaml × data/pulse_snapshots.yaml,
对 1 个议题的"两个时间点快照"输出 diff 报告,为 Phase 1 时间线 +
"政策事件前后 / 突发新闻前后"事件影响分析提供 CLI 端预演。

对比维度(每议题 5 段):
  1. 议题基础    issue_id / name / category / heat_score
  2. A 点详细    snapshot_date / volume / sentiment_pos / neu / neg / source / note
  3. B 点详细    同上
  4. 差异        volume_diff / volume_pct / pos_diff / neu_diff / neg_diff
                + 情感标签(恶化/缓和/稳定,基于 |Δneg| ≥ 0.02 阈值)
                + 声量标签(显著上升/下降/平稳,基于 |Δpct| ≥ 10% 阈值)
  5. 衍生        两点之间的快照条数 + 中间日期范围(A→B 之间所有快照的 vol/neg 列表)

字段规范:见 data/pulse_snapshots.schema.md v1.0 + data/issues.schema.md v1.0

用法:
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25                       # B = 该议题下 date-a 之后最近一条
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25 --date-b 2026-08-29   # 显式指定两点
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25 --source hybrid       # 按 source 过滤(默认 hybrid)
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25 --json                # 机器可读 JSON
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25 --strict              # 任何缺失/无对比点 → exit 1
  python3 scripts/issue_diff.py issue-001 --date-a 2026-08-25 --issues data/issues.yaml --pulse data/pulse_snapshots.yaml

依赖:PyYAML (pip3 install pyyaml)

退出码:
  0  成功 / JSON 输出 / 人读报告(无问题)
  1  参数错 / 输入文件缺失 / 议题不存在 / 快照缺失(--strict 时才 fail)
  2  缺少依赖 PyYAML

设计决策:
  - 默认 source=hybrid,与 phase_status.py / issue_compare.py 对齐;真实多源接入 Phase 1
  - B 点默认 = 该议题下 date-a 之后最近一条(避免用户手动算日期);--date-b 显式覆盖
  - date-a 必须存在该议题快照,否则 --strict 模式 exit 1,默认宽松给提示
  - 情感标签阈值 |Δneg| ≥ 0.02 = 显著(对齐 issue_trend.py 的"情感预警"判定);
    声量标签阈值 |Δpct| ≥ 10% = 显著(与日常波动区分)
  - 衍生段输出 A→B 之间所有快照(若有),便于人工核对"中间经过几次波动"
  - 与 issue_trend.py(N 日连续趋势)+ issue_compare.py(多议题同框对比)互补,
    本脚本专注"单议题 2 点 diff"(事件影响分析的核心诉求)

T4 调度连续 18 日停摆(9/2→9/19),.plan/20260919.md 未生成,本轮按 9/14~9/18 同款
"应急补建"通道直接落地变更,不擅自建 plan 文件。
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ISSUES_DEFAULT_PATH = "data/issues.yaml"
PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
DEFAULT_SOURCE = "hybrid"
NEG_DELTA_THRESHOLD = 0.02   # |Δneg| ≥ 此值触发"恶化/缓和"标签
VOL_DELTA_PCT_THRESHOLD = 10  # |Δpct%| ≥ 此值触发"显著上升/下降"标签
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
        print(f"❌ 快照文件不存在: {path}", file=sys.stderr)
        sys.exit(1)
    data = load_yaml(path)
    snaps = data.get("snapshots", [])
    return snaps if isinstance(snaps, list) else []


def _date_str(v) -> str:
    """yaml 解析 2026-08-25 会成 date 对象,统一转 str。"""
    if v is None or v == "":
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _find_issue(issues: list[dict], issue_id: str) -> Optional[dict]:
    for it in issues:
        if it.get("id") == issue_id:
            return it
    return None


def _filter_snaps(snaps: list[dict], issue_id: str, source: str) -> list[dict]:
    """按 issue_id + source 过滤,按 snapshot_date 排序。"""
    out = [
        s for s in snaps
        if s.get("issue_id") == issue_id and s.get("source") == source
    ]
    out.sort(key=lambda s: _date_str(s.get("snapshot_date", "")))
    return out


def _pick_point(snaps: list[dict], date: str, mode: str) -> Optional[dict]:
    """
    从已排序快照列表里挑点。
    mode="exact":严格匹配 date(否则 None)
    mode="on_or_after":date 或之后的最近一条
    mode="before":date 之前的最近一条(A 点 backup)
    """
    if mode == "exact":
        for s in snaps:
            if _date_str(s.get("snapshot_date")) == date:
                return s
        return None
    if mode == "on_or_after":
        for s in snaps:
            if _date_str(s.get("snapshot_date")) >= date:
                return s
        return None
    if mode == "before":
        cand = None
        for s in snaps:
            if _date_str(s.get("snapshot_date")) < date:
                cand = s
            else:
                break
        return cand
    raise ValueError(f"unknown mode: {mode}")


# ============== 字段计算 ==============

def _round(v, n=3) -> Optional[float]:
    if v is None:
        return None
    return round(v, n)


def _volume_pct(a_vol: float, b_vol: float) -> Optional[float]:
    if a_vol is None or a_vol <= 0:
        return None
    return round((b_vol - a_vol) / a_vol * 100, 1)


def _sentiment_label(neg_diff: Optional[float]) -> str:
    if neg_diff is None:
        return "N/A"
    if neg_diff >= NEG_DELTA_THRESHOLD:
        return "恶化 ⬆️"
    if neg_diff <= -NEG_DELTA_THRESHOLD:
        return "缓和 ⬇️"
    return "稳定 ➡️"


def _volume_label(pct: Optional[float]) -> str:
    if pct is None:
        return "N/A"
    if pct >= VOL_DELTA_PCT_THRESHOLD:
        return "显著上升 ⬆️"
    if pct <= -VOL_DELTA_PCT_THRESHOLD:
        return "显著下降 ⬇️"
    return "平稳 ➡️"


def _between_snaps(snaps: list[dict], a_date: str, b_date: str) -> list[dict]:
    """A→B 之间(含 A 不含 B)的快照列表。"""
    return [
        s for s in snaps
        if a_date <= _date_str(s.get("snapshot_date")) < b_date
    ]


# ============== 报告渲染 ==============

def _render_md(report: dict) -> str:
    """人读 Markdown 报告。"""
    lines = []
    lines.append(f"# 议题跨时间点 diff 报告")
    lines.append("")
    lines.append(f"> 生成时间: {report['generated_at']} · source={report['source']}")
    lines.append("")

    # ① 议题基础
    base = report["issue"]
    lines.append("## ① 议题基础")
    lines.append(f"- **issue_id**: `{base['id']}`")
    lines.append(f"- **name**: {base['name']}")
    lines.append(f"- **category**: {base['category']}")
    lines.append(f"- **heat_score**: {base['heat_score']}")
    lines.append("")

    # ② A 点
    a = report["point_a"]
    lines.append("## ② A 点(baseline)")
    if a is None:
        lines.append("_(无)_")
    else:
        lines.append(f"- **snapshot_date**: {a['snapshot_date']}")
        lines.append(f"- **volume**: {a['volume']}")
        lines.append(f"- **sentiment**: pos={a['sentiment_pos']} / neu={a['sentiment_neu']} / neg={a['sentiment_neg']}")
        if a.get("note"):
            lines.append(f"- **note**: {a['note']}")
    lines.append("")

    # ③ B 点
    b = report["point_b"]
    lines.append("## ③ B 点(对比)")
    if b is None:
        lines.append("_(无)_")
    else:
        lines.append(f"- **snapshot_date**: {b['snapshot_date']}")
        lines.append(f"- **volume**: {b['volume']}")
        lines.append(f"- **sentiment**: pos={b['sentiment_pos']} / neu={b['sentiment_neu']} / neg={b['sentiment_neg']}")
        if b.get("note"):
            lines.append(f"- **note**: {b['note']}")
    lines.append("")

    # ④ 差异
    d = report["diff"]
    lines.append("## ④ 差异(delta)")
    if d.get("volume_diff") is None:
        lines.append("_(两点缺失,无 diff)_")
    else:
        lines.append(f"- **volume_diff**: {d['volume_diff']:+d} ({d['volume_pct']:+.1f}%)")
        lines.append(f"- **声量标签**: {d['volume_label']}")
        lines.append(f"- **pos_diff**: {d['pos_diff']:+.3f}")
        lines.append(f"- **neu_diff**: {d['neu_diff']:+.3f}")
        lines.append(f"- **neg_diff**: {d['neg_diff']:+.3f}")
        lines.append(f"- **情感标签**: {d['sentiment_label']}")
    lines.append("")

    # ⑤ 衍生
    lines.append("## ⑤ A→B 之间快照")
    between = report["between"]
    if not between:
        lines.append("_(两点之间无其他快照)_")
    else:
        lines.append(f"共 {len(between)} 条:")
        lines.append("")
        lines.append("| snapshot_date | volume | neg |")
        lines.append("|---|---|---|")
        for s in between:
            lines.append(
                f"| {s['snapshot_date']} | {s['volume']} | {s['sentiment_neg']:.3f} |"
            )
    lines.append("")

    # 总结
    if d.get("volume_diff") is not None:
        lines.append("---")
        lines.append(f"**总结**: A→B 声量{d['volume_label']},情感{d['sentiment_label']}。")
        lines.append("")
    return "\n".join(lines)


# ============== 主流程 ==============

def run_diff(
    issue_id: str,
    date_a: str,
    date_b: Optional[str],
    source: str,
    issues: list[dict],
    snaps_all: list[dict],
    strict: bool,
) -> dict:
    issue = _find_issue(issues, issue_id)
    if issue is None:
        print(f"❌ 议题不存在: {issue_id}", file=sys.stderr)
        sys.exit(1)

    snaps = _filter_snaps(snaps_all, issue_id, source)
    if not snaps:
        msg = f"❌ 议题 {issue_id} 在 source={source} 下无快照"
        print(msg, file=sys.stderr)
        sys.exit(1)

    # A 点
    point_a = _pick_point(snaps, date_a, mode="exact")
    if point_a is None:
        if strict:
            print(f"❌ A 点(date-a={date_a})在 source={source} 下不存在", file=sys.stderr)
            sys.exit(1)
        print(f"⚠️ A 点(date-a={date_a})在 source={source} 下不存在,自动回退到 date-a 之前最近一条")
        point_a = _pick_point(snaps, date_a, mode="before")
        if point_a is None:
            print(f"❌ 无任何 date-a 之前的快照可回退", file=sys.stderr)
            sys.exit(1)

    # B 点
    if date_b:
        point_b = _pick_point(snaps, date_b, mode="exact")
        if point_b is None and strict:
            print(f"❌ B 点(date-b={date_b})在 source={source} 下不存在", file=sys.stderr)
            sys.exit(1)
    else:
        point_b = _pick_point(snaps, _date_str(point_a.get("snapshot_date")), mode="on_or_after")
        # _pick_point "on_or_after" 会返回 ≥ A 点的那条;A 点本身就被算进去,所以跳过 A
        if point_b is not None and _date_str(point_b.get("snapshot_date")) == _date_str(point_a.get("snapshot_date")):
            # 取下一条
            idx = snaps.index(point_a)
            point_b = snaps[idx + 1] if idx + 1 < len(snaps) else None
        if point_b is None:
            print(f"⚠️ B 点(date-a={date_a} 之后)无快照可对比")

    # diff
    diff = {}
    if point_a is not None and point_b is not None:
        a_vol = point_a.get("volume", 0) or 0
        b_vol = point_b.get("volume", 0) or 0
        a_pos = point_a.get("sentiment_pos", 0) or 0
        b_pos = point_b.get("sentiment_pos", 0) or 0
        a_neu = point_a.get("sentiment_neu", 0) or 0
        b_neu = point_b.get("sentiment_neu", 0) or 0
        a_neg = point_a.get("sentiment_neg", 0) or 0
        b_neg = point_b.get("sentiment_neg", 0) or 0

        vol_pct = _volume_pct(a_vol, b_vol)
        neg_diff = round(b_neg - a_neg, 3)
        diff = {
            "volume_diff": b_vol - a_vol,
            "volume_pct": vol_pct if vol_pct is not None else 0.0,
            "pos_diff": round(b_pos - a_pos, 3),
            "neu_diff": round(b_neu - a_neu, 3),
            "neg_diff": neg_diff,
            "volume_label": _volume_label(vol_pct),
            "sentiment_label": _sentiment_label(neg_diff),
        }

    # between
    between_raw = (
        _between_snaps(snaps, _date_str(point_a.get("snapshot_date")), _date_str(point_b.get("snapshot_date")))
        if point_b is not None else []
    )
    between = [
        {
            "snapshot_date": _date_str(s.get("snapshot_date")),
            "volume": s.get("volume", 0) or 0,
            "sentiment_neg": s.get("sentiment_neg", 0) or 0,
        }
        for s in between_raw
    ]

    from datetime import datetime
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "issue": {
            "id": issue["id"],
            "name": issue.get("name", ""),
            "category": issue.get("category", ""),
            "heat_score": issue.get("heat_score", ""),
        },
        "source": source,
        "date_a": date_a,
        "date_b": date_b,
        "point_a": (
            {
                "snapshot_date": _date_str(point_a.get("snapshot_date")),
                "volume": point_a.get("volume", 0) or 0,
                "sentiment_pos": point_a.get("sentiment_pos", 0) or 0,
                "sentiment_neu": point_a.get("sentiment_neu", 0) or 0,
                "sentiment_neg": point_a.get("sentiment_neg", 0) or 0,
                "note": point_a.get("note", ""),
            }
            if point_a else None
        ),
        "point_b": (
            {
                "snapshot_date": _date_str(point_b.get("snapshot_date")),
                "volume": point_b.get("volume", 0) or 0,
                "sentiment_pos": point_b.get("sentiment_pos", 0) or 0,
                "sentiment_neu": point_b.get("sentiment_neu", 0) or 0,
                "sentiment_neg": point_b.get("sentiment_neg", 0) or 0,
                "note": point_b.get("note", ""),
            }
            if point_b else None
        ),
        "diff": diff,
        "between": between,
    }


def main():
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor · 议题跨时间点 diff CLI (Phase 0 #4 工具链扩展)"
    )
    parser.add_argument("issue_id", help="议题 ID,如 issue-001")
    parser.add_argument(
        "--date-a",
        required=True,
        help="A 点(基准)日期,格式 YYYY-MM-DD;该议题在该日必须有快照(或回退到之前最近一条)",
    )
    parser.add_argument(
        "--date-b",
        default=None,
        help="B 点(对比)日期,格式 YYYY-MM-DD;省略 = A 点之后最近一条快照",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"快照 source 过滤,默认 {DEFAULT_SOURCE};可选:{sorted(ALLOWED_SOURCES)}",
    )
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    parser.add_argument("--strict", action="store_true", help="任何缺失 → exit 1(默认宽松给提示)")
    parser.add_argument("--issues", default=ISSUES_DEFAULT_PATH, help="议题库 yaml 路径")
    parser.add_argument("--pulse", default=PULSE_DEFAULT_PATH, help="声量快照 yaml 路径")
    args = parser.parse_args()

    if args.source not in ALLOWED_SOURCES:
        print(
            f"❌ --source 必须是 {sorted(ALLOWED_SOURCES)} 之一,实参={args.source}",
            file=sys.stderr,
        )
        sys.exit(1)

    issues = load_issues(Path(args.issues))
    snaps = load_snapshots(Path(args.pulse))

    report = run_diff(
        issue_id=args.issue_id,
        date_a=args.date_a,
        date_b=args.date_b,
        source=args.source,
        issues=issues,
        snaps_all=snaps,
        strict=args.strict,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_md(report))


if __name__ == "__main__":
    main()