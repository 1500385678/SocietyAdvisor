#!/usr/bin/env bash
# run_daily_report.sh · SocietyAdvisor Phase 0 #6 飞书日报 cron 入口(9/8 T5 周期)
#
# 用途:把 scripts/daily_report.py 脚本骨架升到"可定时调起"形态,
#       供 mavis cron 09:00 调度 / 本地手测两种使用。
#
# 行为:
#   1. 默认 report_date = 昨日(CST),符合"09:00 推昨日 Top 10"语义
#   2. 默认输出 .Log/日报-YYYYMMDD.md,文件名与 T1 巡检文件同前缀体系
#   3. --strict 开启,缺议题库 / 缺 pulse 快照 → exit 1(cron 会通过 mavis 通知)
#   4. 成功 → 打印"✅ 路径 + 字节数",失败 → stderr 输出原因
#
# 用法:
#   bash scripts/run_daily_report.sh                  # 默认昨日 + .Log/日报-昨日.md
#   bash scripts/run_daily_report.sh --date 2026-09-04  # 指定日期
#   bash scripts/run_daily_report.sh --dry-run         # dry-run: 不真写盘,stdout 预览
#   bash scripts/run_daily_report.sh --push-stub       # 触发飞书推送 stub(目前只 echo)
#
# 依赖:python3 + PyYAML;与 daily_report.py 共用同一套环境。
# 真飞书 webhook 推送在 scripts/feishu_publish.py 中预留,本期仅 echo 占位。

set -euo pipefail

# ============== 路径定位 ==============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DAILY_REPORT="${SCRIPT_DIR}/daily_report.py"

CST_OFFSET_HOURS=8
NOW_CST_EPOCH=$(( $(date +%s) + CST_OFFSET_HOURS * 3600 ))
YESTERDAY_CST=$(date -u -r $(( NOW_CST_EPOCH - 86400 )) +%Y-%m-%d 2>/dev/null \
                || date -u -d "@$(( NOW_CST_EPOCH - 86400 ))" +%Y-%m-%d)
YESTERDAY_COMPACT=$(echo "${YESTERDAY_CST}" | tr -d '-')

# ============== 参数 ==============
REPORT_DATE="${YESTERDAY_CST}"
DRY_RUN=0
PUSH_STUB=0
TOP=10
DEGREE_TOP=3
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)        REPORT_DATE="$2"; shift 2 ;;
    --top)         TOP="$2"; shift 2 ;;
    --degree-top)  DEGREE_TOP="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=1; shift ;;
    --push-stub)   PUSH_STUB=1; shift ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1"); shift ;;
  esac
done

REPORT_DATE_COMPACT=$(echo "${REPORT_DATE}" | tr -d '-')
DEFAULT_OUTPUT="${PROJECT_ROOT}/.Log/日报-${REPORT_DATE_COMPACT}.md"

# ============== 预检 ==============
if [[ ! -f "${DAILY_REPORT}" ]]; then
  echo "❌ 找不到 ${DAILY_REPORT}" >&2
  exit 2
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "❌ 找不到 ${PYTHON_BIN},请先安装 Python 3" >&2
  exit 2
fi

# ============== 执行 ==============
CMD=(
  "${PYTHON_BIN}" "${DAILY_REPORT}"
  --date "${REPORT_DATE}"
  --top "${TOP}"
  --degree-top "${DEGREE_TOP}"
  --strict
)

if [[ ${DRY_RUN} -eq 1 ]]; then
  echo "🔍 DRY-RUN 预览(不写盘):${CMD[*]}"
  "${CMD[@]}"
  exit 0
fi

CMD+=(--output "${DEFAULT_OUTPUT}")

echo "▶ 飞书日报生成:日期=${REPORT_DATE} → ${DEFAULT_OUTPUT}"
"${CMD[@]}"

# ============== 飞书推送 stub ==============
# 真实 webhook 推送留给 scripts/feishu_publish.py(本期未实现,先 echo 占位)
if [[ ${PUSH_STUB} -eq 1 ]]; then
  echo "📨 [feishu-stub] 推 ${DEFAULT_OUTPUT} → 待 feishu_publish.py 接入"
fi

echo "🎉 run_daily_report.sh 完成 · ${REPORT_DATE}"
