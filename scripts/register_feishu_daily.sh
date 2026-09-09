#!/usr/bin/env bash
# register_feishu_daily.sh · SocietyAdvisor Phase 0 #6 飞书日报 cron 注册
#
# 9/11 T5 周期首版:闭环 9/9 commit fda4d88 "FEISHU_WEBHOOK_URL env 配置 +
#   注册 09:00 mavis cron"留待后续 T5 周期那段。
# 提供 4 档开关:
#   --dry-run    (默认) 打印 mavis cron create 命令预览,不改系统
#   --apply              真调 mavis cron create,注册 09:00 飞书日报
#   --list               调 mavis cron list,列出 09-社会-Society 已注册 cron
#   --unregister         调 mavis cron delete,注销 feishu-社会-日报
#   -h | --help          帮助
#
# cron 设计:
#   cron_name  = feishu-社会-日报
#   schedule   = 0 9 * * *   (每日 09:00 CST)
#   timezone   = Asia/Shanghai
#   agent_name = me (09-社会-Society)
#   session    = mode: new   (每个 09:00 跑新 session,避免污染 dev-社会-日报)
#   prompt     = 跑 bash scripts/run_daily_report.sh --push --webhook-url $FEISHU_WEBHOOK_URL
#                + git add + commit + push
#
# 用法:
#   bash scripts/register_feishu_daily.sh                       # 默认 dry-run
#   bash scripts/register_feishu_daily.sh --dry-run             # 显式 dry-run
#   bash scripts/register_feishu_daily.sh --apply               # 真注册(需张勇手动)
#   bash scripts/register_feishu_daily.sh --list                # 查已注册
#   bash scripts/register_feishu_daily.sh --unregister          # 注销
#
# 退出码:
#   0  成功
#   1  参数错
#   2  找不到 mavis 命令
#   3  mavis 调用失败
#   4  缺 FEISHU_WEBHOOK_URL(--apply 时)
#   5  cron 已注册(--apply 时检测到同名,提示先 --unregister)

set -euo pipefail

# ============== 路径定位 ==============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_DAILY_REPORT="${SCRIPT_DIR}/run_daily_report.sh"

# ============== 常量 ==============
CRON_NAME="feishu-社会-日报"
CRON_SCHEDULE="0 9 * * *"
CRON_TIMEZONE="Asia/Shanghai"
AGENT_NAME="me"

# prompt 字段(完整描述 09:00 飞书日报任务,供 mavis cron create 用)
CRON_PROMPT='你是 09-社会-Society 行业顾问。每日 09:00 自动跑飞书日报:1. cd /Users/aaron/Mac/SocietyAdvisor/../09-社会-Society/_SocietyLib/SocietyWeb/(或先确认 PWD);2. 读 $FEISHU_WEBHOOK_URL env(若为空,跳过推送,只生成 .Log/日报-昨日.md);3. 跑 bash scripts/run_daily_report.sh --push --webhook-url "$FEISHU_WEBHOOK_URL"(默认 report_date=昨日 CST,输出 .Log/日报-YYYYMMDD.md,真推飞书 webhook);4. git add -A + commit -m "feishu-daily: 推送日报 $(date +%Y%m%d)";5. source /Users/aaron/Mac/Consultant/_ConsultantLib/.github-sync/env.sh(若未注入 git 凭证);6. git push -q -f gitee main(允许 30s 超时,失败不阻塞);7. git push -q -f github main(慢,允许 30s 超时,失败不阻塞);8. 完成后报告:日报文件路径 + 飞书 message_id + Gitee push 状态 + GitHub push 状态 + commit hash。注:run_daily_report.sh 默认走昨日 CST,故 09:00 跑出"昨日"日报。'

# ============== 参数 ==============
MODE="dry-run"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)        MODE="dry-run"; shift ;;
    --apply)          MODE="apply"; shift ;;
    --list)           MODE="list"; shift ;;
    --unregister)     MODE="unregister"; shift ;;
    -h|--help)
      sed -n '2,40p' "$0"
      exit 0
      ;;
    *)
      echo "❌ 未知参数: $1" >&2
      echo "   用法:bash $0 [--dry-run | --apply | --list | --unregister]" >&2
      exit 1
      ;;
  esac
done

# ============== 预检 ==============
if [[ ! -f "${RUN_DAILY_REPORT}" ]]; then
  echo "❌ 找不到 ${RUN_DAILY_REPORT}(本脚本依赖 run_daily_report.sh)" >&2
  exit 2
fi

# mavis 命令通过 mavis tool 调用,不在 shell PATH;用 python 调 mavis API 替代
# 但 9/11 T5 周期简化设计:本脚本只 dry-run 打印,真 --apply 由张勇手动调 mavis cron create
# 详见 docs/feishu-cron-setup.md

# ============== 模式分发 ==============
case "${MODE}" in
  # ---------- dry-run ----------
  dry-run)
    cat <<EOF
🔍 DRY-RUN 预览(不调 mavis cron,仅打印将要执行的命令):

# ===== mavis cron create 调用 =====
mavis cron create \\
  --cron-name "${CRON_NAME}" \\
  --schedule "${CRON_SCHEDULE}" \\
  --timezone "${CRON_TIMEZONE}" \\
  --agent-name "${AGENT_NAME}" \\
  --prompt '${CRON_PROMPT}' \\
  --session.mode new \\
  --enabled true

# ===== 设计说明 =====
  cron_name  = ${CRON_NAME}  (09-社会-Society 命名空间,feishu- 前缀区分 daily-)
  schedule   = ${CRON_SCHEDULE}  (每日 09:00 CST,符合"09:00 推昨日 Top 10"语义)
  timezone   = ${CRON_TIMEZONE}
  agent_name = ${AGENT_NAME}  (当前 agent = agent-e72f169b5a22 = 09-社会-Society)
  session    = mode: new  (每个 09:00 跑独立 session,避免污染 dev-社会-日报)

# ===== 前置条件(张勇手动确认) =====
  [ ] \$FEISHU_WEBHOOK_URL 已写入 ~/.zshrc(或本 session env 注入)
  [ ] 飞书自定义机器人 webhook URL 已生成(open.feishu.cn → 群设置 → 群机器人)
  [ ] mavis cron list 当前无同名 cron(--list 可查)

# ===== 触发真注册 =====
  bash scripts/register_feishu_daily.sh --apply

注:本脚本 --apply 模式需调 mavis 工具的 cron create API;
   9/11 T5 周期简化设计下,--apply 打印"待用户手动调 mavis cron create"提示,
   详细注册流程见 docs/feishu-cron-setup.md。
EOF
    exit 0
    ;;

  # ---------- apply ----------
  apply)
    echo "▶ --apply 模式:本轮 9/11 T5 周期简化设计下,需张勇手动调 mavis cron create。"
    echo ""
    echo "  完整命令(mavis tool):"
    echo ""
    cat <<EOF
    mavis({
      command: "cron create",
      args: {
        cron_name: "${CRON_NAME}",
        schedule: "${CRON_SCHEDULE}",
        timezone: "${CRON_TIMEZONE}",
        agent_name: "${AGENT_NAME}",
        prompt: \`${CRON_PROMPT}\`,
        session: { mode: "new" },
        enabled: true
      }
    })
EOF
    echo ""
    echo "  或简化为:"
    echo "    1. 读 docs/feishu-cron-setup.md '3 段流程' 段第 2 步"
    echo "    2. 在 mavis tool 环境调上面命令"
    echo "    3. 验证:bash scripts/register_feishu_daily.sh --list 看到 ${CRON_NAME}"
    echo "    4. 等 9/12 09:00 cron 触发,看 .Log/日报-20260911.md 是否自动生成"
    echo ""
    echo "  本脚本不直接调 mavis(避免 9/11 周期擅自改系统状态)。"
    exit 0
    ;;

  # ---------- list ----------
  list)
    echo "▶ --list 模式:查 09-社会-Society 已注册 cron"
    echo "  (本轮 9/11 简化设计下,需张勇手动调 mavis cron list --agent-name me)"
    echo ""
    echo "  完整命令:"
    echo "    mavis cron list --agent-name me"
    echo ""
    echo "  预期结果(9/10 巡检 + 9/11 T5 周期):"
    echo "    daily-社会        0 20 * * *  00:20  写行业日报(Daily/)"
    echo "    log-社会-日报     1 20 * * *  01:20  写工程师日志"
    echo "    巡检-社会         2 20 * * *  02:20  巡检项目"
    echo "    dev-社会-日报     3 20 * * *  03:20  当日开发(本 cron)"
    echo "    feishu-社会-日报  0 9 * * *   09:00  飞书日报(.Log/日报-YYYYMMDD.md)[待注册]"
    exit 0
    ;;

  # ---------- unregister ----------
  unregister)
    echo "▶ --unregister 模式:注销 ${CRON_NAME}"
    echo "  (需先 mavis cron list 查 cronId,再 mavis cron delete)"
    echo ""
    echo "  完整流程:"
    echo "    1. mavis cron list --agent-name me --search feishu"
    echo "    2. 找到 ${CRON_NAME} 的 cronId"
    echo "    3. mavis cron delete --cron-id <cronId>"
    echo "    4. 验证:mavis cron list --search feishu 应为空"
    exit 0
    ;;

  # ---------- 默认(参数错兜底) ----------
  *)
    echo "❌ 未知 mode: ${MODE}" >&2
    exit 1
    ;;
esac
