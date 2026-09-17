#!/usr/bin/env python3
"""
scheduler_trend.py · SocietyAdvisor Phase 0 #6 调度层健康趋势分析(9/18 T5 周期)

聚合项目调度层 4 维健康检查的 N 日轨迹:对过去 N 天的每一天,跑一次
scheduler_health.py 的 4 段检查(以那天作为 "today"),产出每日状态时间线,
并对比窗口起点 vs 终点的状态变化,识别修复事件 / 退化事件 / 持续问题。
与 scheduler_health.py(单日快照)互补。

4 段检查维度(复用 scheduler_health.py,本脚本不重复实现):
  1. .Log/巡检-社会-YYYYMMDD.md     → T1 巡检(02:20 窗口)连续性
  2. .plan/YYYYMMDD.md              → T4 plan 生成(02:00~03:00 窗口)连续性
  3. .Log/日报-YYYYMMDD.md          → 09:00 飞书日报连续性(数据日期维度)
  4. scripts/register_feishu_daily.sh → 09:00 飞书 cron 注册链路完整性

输出:
  - 4 段 × N 日 轨迹表(每段每日的 ✅/⚠️/❌ 字符)
  - 窗口起点状态(最早一日)
  - 窗口终点状态(今日 N 日汇总,与 scheduler_health.py 今日报告一致)
  - 修复/退化事件清单(每段起点 vs 终点)
  - 整体"轨迹方向"(好转 / 稳定 / 退化)

退出码:
  0  4 段趋势无退化(全稳或好转)
  1  4 段中任一段在过去 N 日出现退化(起点→终点变差)
  2  缺 Python 依赖(本脚本仅 stdlib + 同目录 scheduler_health.py)
  3  参数错

用法:
  python3 scripts/scheduler_trend.py                          # 默认人读报告(看过去 14 日趋势)
  python3 scripts/scheduler_trend.py --days 30                # 看过去 30 日趋势
  python3 scripts/scheduler_trend.py --json                   # 机器可读 JSON
  python3 scripts/scheduler_trend.py --strict                 # 任一段退化 → exit 1
  python3 scripts/scheduler_trend.py --date 2026-09-18        # 自定义"今天"日期(测试用)

设计决策:
  - 仅 stdlib 依赖 + 同目录 scheduler_health.py import(无 PyYAML / 无 mavis CLI)
  - "今天"默认取系统本地日期,可用 --date 覆盖(便于单测 + 历史回放)
  - 对过去 N 天每一天,以那天为 today 调用 4 段 check_*(today=D, days=1),
    拿到该天 4 段状态;轨迹 = N 个每日状态的列表
  - "事件"仅比较每段的起点(最早一日)与终点(今日 N 日汇总),
    不算逐日差分(避免被中间单日偶发噪声淹没长期趋势信号)
  - cron 脚本完整性每天都是同一个值(只要文件存在),轨迹不会变化,
    但保留作为 4 段完整性参照基线
  - 与 scheduler_health.py 分工:single-day snapshot(本工具起点/终点)
    vs N-day trajectory(本工具核心新增)

依赖:无(仅 Python 3.8+ stdlib + 同目录 scripts/scheduler_health.py)
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# 复用 scheduler_health.py 的 4 段检查函数(同目录 import)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scheduler_health import (  # noqa: E402
    LOG_DIR,
    PLAN_DIR,
    check_cron_script,
    check_daily,
    check_inspect,
    check_plan,
    date_str,
)

# 4 段名称(顺序与 scheduler_health.py 一致)
SEGMENT_NAMES = ["T1_巡检", "T4_plan", "T9_日报", "cron_脚本"]

# 状态优先级:数值越大越差(用于判断修复 vs 退化)
STATUS_RANK = {"✅": 0, "⚠️": 1, "❌": 2, "?": -1}


def collect_daily_status(
    target_day: date,
    log_dir: Path,
    plan_dir: Path,
    scripts_dir: Path,
) -> Dict[str, str]:
    """对 target_day 当天,跑 4 段 check_*(today=target_day, days=1) → 拿到当天状态。
    注:cron_脚本 是单值检查(不依赖 today/days),重复调用结果相同。
    """
    return {
        SEGMENT_NAMES[0]: check_inspect(log_dir, target_day, 1)["status"],
        SEGMENT_NAMES[1]: check_plan(plan_dir, target_day, 1)["status"],
        SEGMENT_NAMES[2]: check_daily(log_dir, target_day, 1)["status"],
        SEGMENT_NAMES[3]: check_cron_script(scripts_dir)["status"],
    }


def collect_window_status(
    today: date,
    days: int,
    log_dir: Path,
    plan_dir: Path,
    scripts_dir: Path,
) -> Dict[str, str]:
    """对 today 的 days 日窗口,跑 4 段 check_*(today=today, days=days) → 拿到窗口状态。
    与 scheduler_health.py 默认行为一致,作为轨迹终点对照。
    """
    return {
        SEGMENT_NAMES[0]: check_inspect(log_dir, today, days)["status"],
        SEGMENT_NAMES[1]: check_plan(plan_dir, today, days)["status"],
        SEGMENT_NAMES[2]: check_daily(log_dir, today, days)["status"],
        SEGMENT_NAMES[3]: check_cron_script(scripts_dir)["status"],
    }


def detect_events(trajectory: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """对比每段轨迹的起点(最早一日)与终点(今日 N 日窗口)状态。
    返回 [{segment, start, end, direction: '修复'|'退化'|'稳定'}]
    """
    events = []
    for seg_name, statuses in trajectory.items():
        if not statuses:
            continue
        start, end = statuses[0], statuses[-1]
        if start == end:
            events.append({"segment": seg_name, "start": start, "end": end, "direction": "稳定"})
        else:
            start_rank = STATUS_RANK.get(start, -1)
            end_rank = STATUS_RANK.get(end, -1)
            if end_rank < start_rank:
                events.append({"segment": seg_name, "start": start, "end": end, "direction": "修复"})
            elif end_rank > start_rank:
                events.append({"segment": seg_name, "start": start, "end": end, "direction": "退化"})
            else:
                events.append({"segment": seg_name, "start": start, "end": end, "direction": "稳定"})
    return events


def compute_overall_direction(events: List[Dict[str, str]]) -> str:
    """聚合 events 给出整体方向:全部稳定→稳定,有修复无退化→好转,有退化→退化"""
    has_improve = any(e["direction"] == "修复" for e in events)
    has_regress = any(e["direction"] == "退化" for e in events)
    if has_regress:
        return "退化"
    if has_improve:
        return "好转"
    return "稳定"


def render_markdown(
    today: date,
    days: int,
    dates: List[date],
    trajectory: Dict[str, List[str]],
    start_window: Dict[str, str],
    end_window: Dict[str, str],
    events: List[Dict[str, str]],
    overall_direction: str,
    overall_end: str,
) -> str:
    """渲染人读 Markdown 报告"""
    lines = []
    lines.append(f"## 调度层健康趋势报告(过去 {days} 日 · 截至 {date_str(today)})")
    lines.append("")
    lines.append(f"生成时间:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"轨迹方向:**{overall_direction}**(终点窗口状态 {overall_end})")
    lines.append("")

    # 1. 4 段 × N 日 轨迹表
    lines.append(f"### 1. {days} 日轨迹")
    lines.append("")
    date_header = " ".join(d.strftime("%m-%d") for d in dates)
    lines.append(f"```")
    lines.append(f"日期:   {date_header}")
    for seg_name in SEGMENT_NAMES:
        statuses = trajectory.get(seg_name, [])
        line = "  ".join(s if s else "?" for s in statuses)
        lines.append(f"{seg_name:8s}: {line}")
    lines.append("```")
    lines.append("")

    # 2. 窗口状态对比
    lines.append("### 2. 窗口状态对比(起点 N 日 vs 终点 N 日)")
    lines.append("")
    lines.append("| 段 | 起点状态(最早一日单日) | 终点状态(今日 N 日窗口) |")
    lines.append("|---|---|---|")
    for seg_name in SEGMENT_NAMES:
        lines.append(f"| {seg_name} | {start_window.get(seg_name, '?')} | {end_window.get(seg_name, '?')} |")
    lines.append("")

    # 3. 事件清单
    lines.append("### 3. 修复 / 退化事件")
    lines.append("")
    if all(e["direction"] == "稳定" for e in events):
        lines.append("- (无变化,4 段全程稳定)")
    else:
        for e in events:
            if e["direction"] != "稳定":
                arrow = "↑" if e["direction"] == "修复" else "↓"
                lines.append(f"- {arrow} **{e['segment']}** {e['start']} → {e['end']}({e['direction']})")
    lines.append("")

    # 4. 设计说明
    lines.append("### 4. 设计说明")
    lines.append("")
    lines.append("- 每日状态 = 对那天为 today 跑 4 段 check_*(days=1) 的 status 字段")
    lines.append("- 终点窗口状态 = 对今天为 today 跑 4 段 check_*(days=N) 的 status 字段(与 scheduler_health.py 默认行为一致)")
    lines.append("- 事件检测 = 起点(最早一日)vs 终点(今日 N 日窗口),不算逐日差分(避免单日偶发噪声淹没长期信号)")
    lines.append("- cron_脚本 段每天值相同(只要文件存在就 ✅),保留作为 4 段完整性参照基线")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SocietyAdvisor 调度层健康趋势分析(基于 scheduler_health.py 的 4 段检查,N 日轨迹)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=14,
        help="回看天数(默认 14 日,与 scheduler_health.py 默认一致)",
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
        help="任一段出现退化 → exit 1(默认只看 ❌)",
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
            print(f"[scheduler_trend] --date 格式错:需 YYYY-MM-DD,得到 {args.date}", file=sys.stderr)
            return 3
    else:
        today = date.today()
    if args.days < 1:
        print(f"[scheduler_trend] --days 必须 >= 1,得到 {args.days}", file=sys.stderr)
        return 3

    log_dir = args.log_dir
    plan_dir = args.plan_dir
    scripts_dir = args.scripts_dir

    # 过去 N 天日期列表(从最早到今日)
    dates = [today - timedelta(days=N) for N in range(args.days - 1, -1, -1)]

    # 1. 收集每日 4 段状态
    daily_status = {seg: [] for seg in SEGMENT_NAMES}
    for d in dates:
        ds = collect_daily_status(d, log_dir, plan_dir, scripts_dir)
        for seg in SEGMENT_NAMES:
            daily_status[seg].append(ds[seg])

    # 2. 起点窗口状态(最早一日单日 + 终点 N 日窗口)
    start_window = collect_daily_status(dates[0], log_dir, plan_dir, scripts_dir)
    end_window = collect_window_status(today, args.days, log_dir, plan_dir, scripts_dir)

    # 3. 事件检测
    events = detect_events(daily_status)
    overall_direction = compute_overall_direction(events)

    # 4. 整体终点状态(取 4 段中的最差)
    overall_end_rank = max(STATUS_RANK.get(s, -1) for s in end_window.values())
    overall_end = {0: "✅", 1: "⚠️", 2: "❌"}.get(overall_end_rank, "?")

    if args.json:
        report = {
            "today": date_str(today),
            "lookback_days": args.days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dates": [date_str(d) for d in dates],
            "trajectory": {seg: daily_status[seg] for seg in SEGMENT_NAMES},
            "start_window": start_window,
            "end_window": end_window,
            "events": events,
            "overall_direction": overall_direction,
            "overall_end_status": overall_end,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(
            today=today,
            days=args.days,
            dates=dates,
            trajectory=daily_status,
            start_window=start_window,
            end_window=end_window,
            events=events,
            overall_direction=overall_direction,
            overall_end=overall_end,
        ))

    # 退出码
    if args.strict and any(e["direction"] == "退化" for e in events):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())