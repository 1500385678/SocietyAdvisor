#!/usr/bin/env python3
"""
scheduler_health.py · SocietyAdvisor Phase 0 #6 调度层健康检查(9/17 T5 周期)

聚合项目调度层 4 维健康检查:T1 巡检连续性 + T4 plan 生成连续性 + 09:00 飞书日报连续性
+ cron 注册脚本完整性。专注"调度层健康",与 phase_status.py(数据/代码/工具链完整性)互补。

4 段检查维度:
  1. .Log/巡检-社会-YYYYMMDD.md     → T1 巡检(02:20 窗口)连续性
  2. .plan/YYYYMMDD.md              → T4 plan 生成(02:00~03:00 窗口)连续性
  3. .Log/日报-YYYYMMDD.md          → 09:00 飞书日报连续性(数据日期维度)
  4. scripts/register_feishu_daily.sh → 09:00 飞书 cron 注册链路完整性

每段输出:应到天数 / 实到天数 / 连续缺失天数 / 最近一份日期 / 状态(✅/⚠️/❌)

退出码:
  0  全部健康 / 仅历史性单次静默(< 2 日)允许 ✅
  1  任一段连续缺失 ≥ 2 日 ❌(需要排查)
  2  缺 Python 依赖(本脚本仅 stdlib,无依赖)
  3  参数错

用法:
  python3 scripts/scheduler_health.py                          # 默认人读报告(看过去 14 日)
  python3 scripts/scheduler_health.py --days 30                # 看过去 30 日
  python3 scripts/scheduler_health.py --json                   # 机器可读 JSON
  python3 scripts/scheduler_health.py --strict                # 任何缺口 ≥ 2 日 → exit 1
  python3 scripts/scheduler_health.py --date 2026-09-17        # 自定义"今天"日期(测试用)

设计决策:
  - 仅 stdlib 依赖,无 PyYAML 要求(纯文件系统扫描 + 日期计算)
  - "今天"默认取系统本地日期,可用 --date 覆盖(便于单测 + 历史回放)
  - "应到天数"窗口回看 days 日(默认 14 日),不只看昨日一天
  - 巡检连续缺失 ≥ 2 日 → ❌ 标红;单日缺失保留为历史性静默(8/30 + 9/13 模式)
  - cron 注册脚本只看文件存在 + 大小 > 0(避免误读 stale 内容);具体 cron 是否真注册
    留给 scripts/register_feishu_daily.sh --list 调 mavis 自行验证(本脚本不依赖 mavis CLI)

依赖:无(仅 Python 3.8+ stdlib)
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 默认路径(相对项目根,与 phase_status.py 风格一致)
LOG_DIR = Path(".Log")
PLAN_DIR = Path(".plan")
INSPECT_PREFIX = "巡检-社会-"
DAILY_PREFIX = "日报-"
PLAN_PREFIX_LEN = 8  # YYYYMMDD.md → YYYYMMDD
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_TODAY = date.today()

# 单次静默允许(不计入连续缺失)
ALLOW_SINGLE_DAY_GAP = 1
# 连续缺失阈值(>= 2 日触发 ❌)
GAP_FAIL_THRESHOLD = 2


# ============== 路径与日期工具 ==============

def parse_yyyymmdd(s: str) -> Optional[date]:
    """'20260917' / '2026-09-17' / '2026_09_17' → date,失败返回 None。"""
    s = s.replace("-", "").replace("_", "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def list_dates_in_window(directory: Path, prefix: str, suffix: str,
                         today: date, days: int) -> List[date]:
    """扫 directory,挑出文件名匹配 prefix + YYYYMMDD + suffix 的日期,
    过滤落在 [today - days + 1, today] 窗口内,返回排序日期列表。
    """
    if not directory.is_dir():
        return []
    window_start = today - timedelta(days=days - 1)
    out: List[date] = []
    for f in directory.iterdir():
        if not f.is_file():
            continue
        name = f.name
        if not name.startswith(prefix):
            continue
        # prefix 后跟 8 位日期 + suffix
        rest = name[len(prefix):]
        if not rest.endswith(suffix):
            continue
        ymd = rest[:-len(suffix)] if suffix else rest
        d = parse_yyyymmdd(ymd)
        if d is None:
            continue
        if window_start <= d <= today:
            out.append(d)
    return sorted(set(out))


def date_str(d: date, sep: str = "-") -> str:
    """date → 'YYYY-MM-DD' 或 'YYYYMMDD'(sep='')。"""
    return d.strftime("%Y%m%d") if not sep else d.strftime(f"%Y{sep}%m{sep}%d")


def expected_dates(today: date, days: int) -> List[date]:
    """[today - days + 1, today] 闭区间,返回排序日期列表。"""
    return [today - timedelta(days=i) for i in range(days - 1, -1, -1)]


def missing_dates(have: List[date], expected: List[date]) -> List[date]:
    """应到但没有的日期,排序返回。"""
    s = set(have)
    return [d for d in expected if d not in s]


def consecutive_run_end(have: List[date], today: date) -> Tuple[int, Optional[date]]:
    """从 today 往前数,连续有日报的天数 + 最后一份日期(<= today)。
    注意:只看 < today 的历史日(今天可能还没到 09:00,不算缺口)。
    """
    s = set(have)
    streak = 0
    cursor = today - timedelta(days=1)
    while cursor in s:
        streak += 1
        cursor -= timedelta(days=1)
    last_date = max(have) if have else None
    return streak, last_date


# ============== 4 段检查 ==============

def check_inspect(log_dir: Path, today: date, days: int) -> Dict:
    """段 1:.Log/巡检-社会-YYYYMMDD.md 连续性。"""
    have = list_dates_in_window(log_dir, INSPECT_PREFIX, ".md", today, days)
    expected = expected_dates(today, days)
    miss = missing_dates(have, expected)
    streak, last = consecutive_run_end(have, today)
    # 巡检单日静默允许(8/30 + 9/13 历史性模式);连续 ≥ 2 日才算 ❌
    is_fail = len(miss) >= GAP_FAIL_THRESHOLD
    return {
        "section": "T1 巡检连续性(02:20 窗口)",
        "lookback_days": days,
        "expected": len(expected),
        "have": len(have),
        "missing_count": len(miss),
        "missing_dates": [date_str(d) for d in miss],
        "consecutive_run_days": streak,
        "last_date": date_str(last) if last else None,
        "status": "❌" if is_fail else ("⚠️" if miss else "✅"),
    }


def check_plan(plan_dir: Path, today: date, days: int) -> Dict:
    """段 2:.plan/YYYYMMDD.md 连续性。"""
    if not plan_dir.is_dir():
        # .plan/ 已被 .gitignore 排除,目录存在但无文件也视为"无 plan"
        have: List[date] = []
    else:
        have = list_dates_in_window(plan_dir, "", ".md", today, days)
    expected = expected_dates(today, days)
    miss = missing_dates(have, expected)
    streak, last = consecutive_run_end(have, today)
    is_fail = len(miss) >= GAP_FAIL_THRESHOLD
    # mtime 信息(便于排查 T4 是否真在跑)
    plan_mtime = None
    if plan_dir.is_dir():
        try:
            latest_mtime = max(
                (f.stat().st_mtime for f in plan_dir.iterdir() if f.is_file()),
                default=None,
            )
            if latest_mtime is not None:
                plan_mtime = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            plan_mtime = None
    return {
        "section": "T4 plan 生成连续性(02:00~03:00 窗口)",
        "lookback_days": days,
        "expected": len(expected),
        "have": len(have),
        "missing_count": len(miss),
        "missing_dates": [date_str(d) for d in miss],
        "consecutive_run_days": streak,
        "last_date": date_str(last) if last else None,
        "plan_dir_mtime": plan_mtime,
        "status": "❌" if is_fail else ("⚠️" if miss else "✅"),
    }


def check_daily(log_dir: Path, today: date, days: int) -> Dict:
    """段 3:.Log/日报-YYYYMMDD.md 连续性(09:00 飞书日报)。
    注意:日报"数据日期"是昨日,文件名 = 昨日的 YYYYMMDD。
    即 9/17 09:00 跑出 .Log/日报-20260916.md(数据日期 9/16)。
    所以"应到日期"窗口需要回看 [today - days, today - 1],不含今天。
    """
    # 直接扫描 .Log/日报-* 文件,不依赖 list_dates_in_window(后者默认 today 在窗口内)
    have: List[date] = []
    if log_dir.is_dir():
        window_start = today - timedelta(days=days)
        window_end = today - timedelta(days=1)  # 不含 today(今日 09:00 还未到)
        for f in log_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name
            if not name.startswith(DAILY_PREFIX):
                continue
            ymd = name[len(DAILY_PREFIX):]
            if not ymd.endswith(".md"):
                continue
            ymd = ymd[:-3]
            d = parse_yyyymmdd(ymd)
            if d is None:
                continue
            if window_start <= d <= window_end:
                have.append(d)
    have = sorted(set(have))
    expected_window = [today - timedelta(days=i) for i in range(1, days + 1)]
    miss = missing_dates(have, expected_window)
    streak, last = consecutive_run_end(have, today)
    is_fail = len(miss) >= GAP_FAIL_THRESHOLD
    return {
        "section": "09:00 飞书日报连续性(数据日期=昨日)",
        "lookback_days": days,
        "expected": len(expected_window),
        "have": len(have),
        "missing_count": len(miss),
        "missing_dates": [date_str(d) for d in miss],
        "consecutive_run_days": streak,
        "last_date": date_str(last) if last else None,
        "note": "日报数据日期 = 昨日,文件名 = 昨日 YYYYMMDD",
        "status": "❌" if is_fail else ("⚠️" if miss else "✅"),
    }


def check_cron_script(scripts_dir: Path) -> Dict:
    """段 4:scripts/register_feishu_daily.sh 文件完整性。"""
    target = scripts_dir / "register_feishu_daily.sh"
    exists = target.is_file()
    size = target.stat().st_size if exists else 0
    # 简单健全性:文件 > 100 字节 + 含 "feishu-社会-日报" 字符串 + 含 "schedule"
    content_ok = False
    if exists:
        content = target.read_text(encoding="utf-8", errors="replace")
        content_ok = (
            "feishu-社会-日报" in content
            and "0 9 * * *" in content
            and "Asia/Shanghai" in content
        )
    # 本脚本不调 mavis CLI(避免依赖外部命令);只检查文件存在 + 内容完整
    # 真 cron 注册状态留给 `bash scripts/register_feishu_daily.sh --list` 自行验证
    is_fail = not exists or not content_ok
    return {
        "section": "09:00 飞书 cron 注册脚本完整性",
        "path": str(target),
        "exists": exists,
        "size_bytes": size,
        "content_ok": content_ok,
        "note": "本脚本仅检查文件存在 + 内容完整;真 cron 是否注册留给 register_feishu_daily.sh --list(需 mavis CLI)",
        "status": "✅" if (exists and content_ok) else "❌",
    }


# ============== 渲染 ==============

def render_markdown(report: Dict) -> str:
    """人读 4 段报告 + 顶部总览。"""
    lines: List[str] = []
    today = report["today"]
    days = report["lookback_days"]
    overall = report["overall_status"]
    lines.append(f"# SocietyAdvisor · 调度层健康报告")
    lines.append(f"> 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 参照日期 {today} · 回看 {days} 日")
    lines.append(f"> 整体状态:{overall}")
    lines.append("")
    lines.append("## 4 段检查摘要")
    lines.append("")
    lines.append("| # | 维度 | 应到 | 实到 | 连续缺失 | 状态 |")
    lines.append("|---|---|---|---|---|---|")
    for i, sec in enumerate(report["sections"], 1):
        # 段 4(脚本完整性)没有 expected/have/missing_dates 字段
        if "expected" in sec:
            lines.append(
                f"| {i} | {sec['section']} | {sec['expected']} | {sec['have']} | "
                f"{sec['missing_count']} | {sec['status']} |"
            )
        else:
            lines.append(
                f"| {i} | {sec['section']} | - | {'OK' if sec.get('content_ok') else '缺失'} | "
                f"- | {sec['status']} |"
            )
    lines.append("")
    lines.append("## 详细输出")
    lines.append("")
    for i, sec in enumerate(report["sections"], 1):
        lines.append(f"### 段 {i}:{sec['section']}  {sec['status']}")
        if "expected" in sec:
            lines.append(f"- 回看窗口:{sec['lookback_days']} 日")
            lines.append(f"- 应到 / 实到:{sec['expected']} / {sec['have']}")
            lines.append(f"- 缺失日期数:{sec['missing_count']}")
            if sec["missing_dates"]:
                lines.append(f"  - 缺失清单:`{', '.join(sec['missing_dates'])}`")
            lines.append(f"- 连续有日报天数(从昨日往前):{sec['consecutive_run_days']}")
            lines.append(f"- 最近一份日期:`{sec['last_date'] or '(无)'}`")
        # 段特定字段
        if "plan_dir_mtime" in sec:
            lines.append(f"- .plan/ 目录最近 mtime:`{sec['plan_dir_mtime'] or '(空)'}`")
        if "note" in sec and "path" not in sec:
            lines.append(f"- 注:{sec['note']}")
        if "path" in sec:
            lines.append(f"- 路径:`{sec['path']}`")
            lines.append(f"- 文件存在:`{sec['exists']}` · 大小:{sec['size_bytes']} bytes · 内容完整:`{sec['content_ok']}`")
            lines.append(f"- 注:{sec['note']}")
        lines.append("")
    return "\n".join(lines)


def overall_status(sections: List[Dict]) -> str:
    """4 段中任一 ❌ → 整体 ❌;否则 → ✅。"""
    has_fail = any(s["status"] == "❌" for s in sections)
    if has_fail:
        return "❌"
    has_warn = any(s["status"] == "⚠️" for s in sections)
    return "⚠️" if has_warn else "✅"


# ============== main ==============

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 调度层健康检查(T1 巡检 / T4 plan / 09:00 飞书日报 / cron 注册脚本)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"回看天数(默认 {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="指定'今天'日期 YYYY-MM-DD(默认系统本地日期,便于测试)",
    )
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="任何缺口 >= 2 日 → exit 1(默认只看 ❌)",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=LOG_DIR,
        help=f".Log 目录路径(默认 {LOG_DIR})",
    )
    parser.add_argument(
        "--plan-dir", type=Path, default=PLAN_DIR,
        help=f".plan 目录路径(默认 {PLAN_DIR})",
    )
    parser.add_argument(
        "--scripts-dir", type=Path, default=Path("scripts"),
        help="scripts 目录路径(默认 scripts)",
    )
    args = parser.parse_args()

    # 校验 --date
    if args.date:
        try:
            today = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"[scheduler_health] --date 格式错:需 YYYY-MM-DD,得到 {args.date}", file=sys.stderr)
            return 3
    else:
        today = DEFAULT_TODAY
    if args.days < 1:
        print(f"[scheduler_health] --days 必须 >= 1,得到 {args.days}", file=sys.stderr)
        return 3

    # 跑 4 段
    s1 = check_inspect(args.log_dir, today, args.days)
    s2 = check_plan(args.plan_dir, today, args.days)
    s3 = check_daily(args.log_dir, today, args.days)
    s4 = check_cron_script(args.scripts_dir)
    sections = [s1, s2, s3, s4]

    report = {
        "today": date_str(today),
        "lookback_days": args.days,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": sections,
        "overall_status": overall_status(sections),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))

    # 退出码
    has_fail = any(s["status"] == "❌" for s in sections)
    if has_fail:
        return 1
    if args.strict:
        # strict 下任何缺口 >= 2 日 → fail
        any_gap_fail = any(s["missing_count"] >= GAP_FAIL_THRESHOLD for s in sections)
        if any_gap_fail:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())