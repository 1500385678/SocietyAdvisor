#!/usr/bin/env bash
# run_daily_report.sh · SocietyAdvisor Phase 0 #6 飞书日报 cron 入口
#
# 9/8 T5 周期首版:提供 --dry-run + --push-stub,真飞书推送留待后续周期
# 9/9 T5 周期升级:--push-stub → --push,真调 scripts/feishu_publish.py
#                 走 stdlib urllib 投递,无第三方 HTTP 依赖
#
# 行为:
#   1. 默认 report_date = 昨日(CST),符合"09:00 推昨日 Top 10"语义
#   2. 默认输出 .Log/日报-YYYYMMDD.md,文件名与 T1 巡检文件同前缀体系
#   3. --strict 开启,缺议题库 / 缺 pulse 快照 → exit 1(cron 会通过 mavis 通知)
#   4. --push 开启后:feishu_publish.py 真投 webhook,失败透传 exit code
#   5. 成功 → 打印"✅ 路径 + 字节数",失败 → stderr 输出原因
#
# 用法:
#   bash scripts/run_daily_report.sh                          # 默认昨日 + .Log/日报-昨日.md
#   bash scripts/run_daily_report.sh --date 2026-09-04        # 指定日期
#   bash scripts/run_daily_report.sh --dry-run                # dry-run: 不写盘,stdout 预览
#   bash scripts/run_daily_report.sh --push                    # 真推飞书 webhook(默认走 env FEISHU_WEBHOOK_URL)
#   bash scripts/run_daily_report.sh --push --webhook-url URL  # 显式传 webhook
#   bash scripts/run_daily_report.sh --push --push-dry-run     # 只看 payload,不发
#   bash scripts/run_daily_report.sh --push-stub               # 兼容 9/8 旧名,等价于 --push --push-dry-run
#
# 依赖:python3 + PyYAML(daily_report.py);feishu_publish.py 走 stdlib
#       真飞书 webhook 推送由 scripts/feishu_publish.py 提供(9/9 T5 周期补完)
# 环境变量:
#   FEISHU_WEBHOOK_URL - 默认 webhook URL(可在 ~/.zshrc / mavis cron env 注入)
#   PYTHON_BIN          - Python 解释器(默认 python3)

set -euo pipefail

# ============== 路径定位 ==============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DAILY_REPORT="${SCRIPT_DIR}/daily_report.py"
FEISHU_PUBLISH="${SCRIPT_DIR}/feishu_publish.py"

CST_OFFSET_HOURS=8
NOW_CST_EPOCH=$(( $(date +%s) + CST_OFFSET_HOURS * 3600 ))
YESTERDAY_CST=$(date -u -r $(( NOW_CST_EPOCH - 86400 )) +%Y-%m-%d 2>/dev/null \
                || date -u -d "@$(( NOW_CST_EPOCH - 86400 ))" +%Y-%m-%d)
YESTERDAY_COMPACT=$(echo "${YESTERDAY_CST}" | tr -d '-')

# ============== 参数 ==============
REPORT_DATE="${YESTERDAY_CST}"
DRY_RUN=0
PUSH=0
PUSH_DRY_RUN=0
WEBHOOK_URL="${FEISHU_WEBHOOK_URL:-}"
TOP=10
DEGREE_TOP=3
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)             REPORT_DATE="$2"; shift 2 ;;
    --top)              TOP="$2"; shift 2 ;;
    --degree-top)       DEGREE_TOP="$2"; shift 2 ;;
    --dry-run)          DRY_RUN=1; shift ;;
    --push)             PUSH=1; shift ;;
    --push-dry-run)     PUSH=1; PUSH_DRY_RUN=1; shift ;;  # 9/9 新增:隐式开 push
    --push-stub)        PUSH=1; PUSH_DRY_RUN=1; shift ;;  # 9/8 旧名兼容
    --webhook-url)      WEBHOOK_URL="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,40p' "$0"
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

if [[ ${PUSH} -eq 1 && ! -f "${FEISHU_PUBLISH}" ]]; then
  echo "❌ --push 需要 ${FEISHU_PUBLISH} 但找不到" >&2
  exit 2
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "❌ 找不到 ${PYTHON_BIN},请先安装 Python 3" >&2
  exit 2
fi

# ============== 执行日报生成 ==============
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

# ============== 飞书推送(9/9 T5 周期补完) ==============
# --push 真调 feishu_publish.py;失败透传 exit code(1/2/3/4/5/6)
# --push-dry-run 仅看 payload,不发(9/8 旧 --push-stub 行为)
if [[ ${PUSH} -eq 1 ]]; then
  PUSH_CMD=(
    "${PYTHON_BIN}" "${FEISHU_PUBLISH}"
    --from-file "${DEFAULT_OUTPUT}"
    --title "SocietyAdvisor 日报 ${REPORT_DATE_COMPACT}"
  )
  if [[ -n "${WEBHOOK_URL}" ]]; then
    PUSH_CMD+=(--webhook-url "${WEBHOOK_URL}")
  fi
  if [[ ${PUSH_DRY_RUN} -eq 1 ]]; then
    PUSH_CMD+=(--dry-run)
    echo "▶ 飞书推送 --push-dry-run(只预览):"
    "${PUSH_CMD[@]}"
  else
    echo "▶ 飞书真推送:"
    "${PUSH_CMD[@]}"
  fi
fi

echo "🎉 run_daily_report.sh 完成 · ${REPORT_DATE}"
