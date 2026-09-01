#!/usr/bin/env python3
"""
validate_pulse.py · SocietyAdvisor Phase 0 #4 质量基础设施(9/2 T5 周期)

校验 data/pulse_snapshots.yaml 是否符合 data/pulse_snapshots.schema.md v1.0
用于 Phase 1 接入真实舆情源之前的"人工录入 + 灌库"阶段防错。

校验项(对齐 schema):
  1. 必填字段非空:issue_id / source / volume / sentiment_pos / sentiment_neu / sentiment_neg / snapshot_date
  2. 字段类型:volume 为 int ≥ 0,三段 sentiment 为 float ∈ [0.0, 1.0]
  3. source 在 5 选 1 enum 内:[news, weibo, zhihu, wechat, hybrid]
  4. 情感加和:sentiment_pos + sentiment_neu + sentiment_neg = 1.0 ± 0.01
  5. snapshot_date 格式:YYYY-MM-DD
  6. issue_id 外键:必须存在于 --check-issues 指定的 issues.yaml(可选,默认关闭)
  7. 唯一性:(issue_id, source, snapshot_date) 三元组全局唯一

用法:
  python3 scripts/validate_pulse.py                          # 默认 + 报告
  python3 scripts/validate_pulse.py --strict                 # 校验失败 exit 1
  python3 scripts/validate_pulse.py --check-issues data/issues.yaml  # 开外键
  python3 scripts/validate_pulse.py --pulse data/pulse_snapshots.yaml  # 自定义

依赖:PyYAML (pip3 install pyyaml)
"""
import argparse
import datetime
import sys
from pathlib import Path

PULSE_DEFAULT_PATH = "data/pulse_snapshots.yaml"
SCHEMA_VERSION = "1.0"
ALLOWED_SOURCES = {"news", "weibo", "zhihu", "wechat", "hybrid"}
REQUIRED_FIELDS = (
    "issue_id",
    "source",
    "volume",
    "sentiment_pos",
    "sentiment_neu",
    "sentiment_neg",
    "snapshot_date",
)
OPTIONAL_FIELDS = ("source_url", "note")
SENTIMENT_SUM_TOLERANCE = 0.01


def load_yaml(path: Path) -> dict:
    """读取 yaml;缺失依赖给出明确指引。"""
    try:
        import yaml
    except ImportError:
        print("❌ 缺少依赖 PyYAML\n   安装: pip3 install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_issue_ids(path: Path) -> set[str]:
    """读取 issues.yaml,返回所有合法议题 ID 集合。"""
    data = load_yaml(path)
    return {it["id"] for it in data.get("issues", []) if it.get("id")}


def validate_snapshot(snap: dict, idx: int) -> list[str]:
    """单条快照 schema 校验,返回错误列表(空 = 通过)。"""
    errs = []
    prefix = f"snapshots[{idx}]"

    # 必填字段检查
    for field in REQUIRED_FIELDS:
        if field not in snap or snap[field] is None:
            errs.append(f"{prefix}: 必填字段缺失或为 None: {field}")

    # 字段类型 + 范围
    if "issue_id" in snap and not (isinstance(snap["issue_id"], str) and snap["issue_id"]):
        errs.append(f"{prefix}: issue_id 必须是非空字符串")

    if "source" in snap:
        if snap["source"] not in ALLOWED_SOURCES:
            errs.append(
                f"{prefix}: source 不在白名单 {sorted(ALLOWED_SOURCES)}: {snap['source']!r}"
            )

    if "volume" in snap:
        if not isinstance(snap["volume"], int) or isinstance(snap["volume"], bool):
            errs.append(f"{prefix}: volume 必须是 int(实测 {type(snap['volume']).__name__})")
        elif snap["volume"] < 0:
            errs.append(f"{prefix}: volume 必须 ≥ 0(实测 {snap['volume']})")

    # 情感三段:float + 范围
    for field in ("sentiment_pos", "sentiment_neu", "sentiment_neg"):
        if field in snap:
            val = snap[field]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                errs.append(
                    f"{prefix}: {field} 必须是 float(实测 {type(val).__name__})"
                )
            elif not (0.0 <= val <= 1.0):
                errs.append(f"{prefix}: {field} 越界 [0.0, 1.0](实测 {val})")

    # 情感加和
    if all(f in snap for f in ("sentiment_pos", "sentiment_neu", "sentiment_neg")):
        s = (
            float(snap["sentiment_pos"])
            + float(snap["sentiment_neu"])
            + float(snap["sentiment_neg"])
        )
        if abs(s - 1.0) > SENTIMENT_SUM_TOLERANCE:
            errs.append(f"{prefix}: 情感加和 ≠ 1.0(实测 {s:.4f},容差 ±{SENTIMENT_SUM_TOLERANCE})")

    # snapshot_date 格式
    if "snapshot_date" in snap and isinstance(snap["snapshot_date"], str):
        try:
            datetime.date.fromisoformat(snap["snapshot_date"])
        except ValueError:
            errs.append(
                f"{prefix}: snapshot_date 格式异常(需 YYYY-MM-DD): {snap['snapshot_date']!r}"
            )

    return errs


def main():
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor · 舆情快照数据校验(pulse_snapshots.yaml → schema v1.0)"
    )
    parser.add_argument(
        "--pulse",
        default=PULSE_DEFAULT_PATH,
        help=f"输入 yaml 路径(默认 {PULSE_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--check-issues",
        metavar="ISSUES_PATH",
        help="开启 issue_id 外键校验(指定 issues.yaml 路径)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式:schema 校验失败则 exit 1",
    )
    args = parser.parse_args()

    pulse_path = Path(args.pulse)
    if not pulse_path.exists():
        print(f"❌ 输入文件不存在: {pulse_path}", file=sys.stderr)
        sys.exit(1)

    data = load_yaml(pulse_path)
    snaps = data.get("snapshots", [])

    # ── 1. 单条 schema 校验 ──
    all_errs: list[tuple[int, list[str]]] = []
    for i, snap in enumerate(snaps):
        errs = validate_snapshot(snap, i)
        if errs:
            all_errs.append((i, errs))

    # ── 2. 唯一性校验(issue_id, source, snapshot_date) ──
    dup_keys: list[tuple] = []
    seen: set = set()
    for i, snap in enumerate(snaps):
        key = (
            snap.get("issue_id"),
            snap.get("source"),
            str(snap.get("snapshot_date", "")),
        )
        if key in seen:
            dup_keys.append((i, key))
        seen.add(key)

    # ── 3. 外键校验(可选) ──
    fk_errs: list[tuple[int, str]] = []
    valid_issue_ids: set[str] = set()
    if args.check_issues:
        issues_path = Path(args.check_issues)
        if not issues_path.exists():
            print(f"❌ --check-issues 文件不存在: {issues_path}", file=sys.stderr)
            sys.exit(1)
        valid_issue_ids = load_issue_ids(issues_path)
        for i, snap in enumerate(snaps):
            iid = snap.get("issue_id")
            if iid and iid not in valid_issue_ids:
                fk_errs.append((i, iid))

    # ── 输出报告 ──
    n = len(snaps)
    print(f"📋 舆情快照校验报告 · {pulse_path}")
    print(f"   schema_version: v{SCHEMA_VERSION}")
    print(f"   总条数: {n}")
    print()

    fatal = bool(all_errs) or bool(dup_keys) or bool(fk_errs)

    if all_errs:
        print(f"❌ schema 校验失败 {len(all_errs)} 条:")
        for i, errs in all_errs:
            for e in errs:
                print(f"   - {e}")
        print()
    else:
        print(f"✅ schema 校验: {n}/{n} 通过")
        print()

    if dup_keys:
        print(f"❌ 唯一键冲突 {len(dup_keys)} 处:")
        for i, key in dup_keys:
            print(f"   - snapshots[{i}]: {key[0]} / {key[1]} / {key[2]} 已存在")
        print()
    else:
        print(f"✅ 唯一性: (issue_id, source, snapshot_date) 0 冲突")
        print()

    if args.check_issues:
        if fk_errs:
            print(f"❌ 外键校验失败 {len(fk_errs)} 处:")
            for i, iid in fk_errs:
                print(f"   - snapshots[{i}]: issue_id={iid} 不在 {issues_path}")
            print()
        else:
            print(f"✅ 外键: {n}/{n} 全部命中 issues.yaml({len(valid_issue_ids)} 个 ID)")
            print()
    else:
        print("ℹ️  外键校验未启用(--check-issues 关闭)")

    # 元数据交叉对账
    meta = data.get("meta", {})
    if meta:
        meta_total = meta.get("total")
        if meta_total is not None and meta_total != n:
            print(
                f"⚠️  meta.total={meta_total} 与 snapshots 实际条数 {n} 不一致",
                file=sys.stderr,
            )
            fatal = True
        else:
            print(f"✅ meta.total={meta_total} 一致")

        meta_issues = meta.get("issues_covered")
        if meta_issues is not None:
            actual_issues = len({s.get("issue_id") for s in snaps if s.get("issue_id")})
            if meta_issues != actual_issues:
                print(
                    f"⚠️  meta.issues_covered={meta_issues} 与实际 {actual_issues} 个议题不一致",
                    file=sys.stderr,
                )
                fatal = True
            else:
                print(f"✅ meta.issues_covered={meta_issues} 一致")

    if args.strict and fatal:
        sys.exit(1)
    elif fatal:
        sys.exit(2)

    print()
    print("🎉 校验完成,所有项目通过")


if __name__ == "__main__":
    main()
