# 09:00 飞书日报 cron 注册流程

> 闭环 9/9 commit `fda4d88` 留待后续 T5 周期那段(commit message 明确:"真飞书 webhook 推送(`FEISHU_WEBHOOK_URL` env 配置 + 注册 09:00 `mavis cron`)留待后续")
> 9/11 T5 周期补完:`scripts/register_feishu_daily.sh` 一键脚本 + 本文档 3 段流程
> 关联:`scripts/run_daily_report.sh`(9/8 cron 入口 + 9/9 真推送补完) / `scripts/feishu_publish.py`(9/9 真飞书 webhook 推送模块)

---

## 1. 设计目标

让 SocietyAdvisor 项目**每日 09:00(CST)自动跑昨日飞书日报**:
1. 生成 `.Log/日报-YYYYMMDD.md`(基于 `data/issues.yaml` + `data/issue_relations.yaml` + `data/pulse_snapshots.yaml` 4 段结构)
2. 真推飞书自定义机器人 webhook(标题前缀 `【SocietyAdvisor 日报 YYYYMMDD】`)
3. git add + commit + push(Gitee + GitHub)

**当前状态(9/11 03:20)**:
- ✅ `scripts/run_daily_report.sh` 已就绪(--push 真推 / --push-dry-run 预览 / --webhook-url 显式传)
- ✅ `scripts/feishu_publish.py` 已就绪(stdlib urllib 真投递,6 档退出码)
- ❌ `FEISHU_WEBHOOK_URL` env 未配置
- ❌ 09:00 `mavis cron` 未注册
- ❌ `.Log/日报-20260909.md` + `.Log/日报-20260910.md` 缺失(9/9+9/10 09:00 cron 窗口未跑)

---

## 2. 3 段流程

### 阶段 1:`FEISHU_WEBHOOK_URL` env 配置

#### 1.1 获取飞书自定义机器人 webhook URL

1. 打开飞书,进入要接收 SocietyAdvisor 日报的群
2. 群设置 → 群机器人 → 添加机器人 → 自定义机器人
3. 名称:`SocietyAdvisor 日报`
4. 描述:`每日 09:00 推送社会议题热度日报`
5. 复制 webhook URL(形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

#### 1.2 写入 `~/.zshrc`

```bash
echo 'export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/你的真实webhook"' >> ~/.zshrc
source ~/.zshrc
```

#### 1.3 验证

```bash
echo "${FEISHU_WEBHOOK_URL}"   # 应输出完整 URL,非空
```

#### 1.4 备选:session 级临时注入(不推荐)

```bash
FEISHU_WEBHOOK_URL="https://..." bash scripts/run_daily_report.sh --push-dry-run --date 2026-09-10
```

---

### 阶段 2:`mavis cron` 09:00 注册

#### 2.1 dry-run 预览(不改系统)

```bash
cd /Users/aaron/Mac/Consultant/09-社会-Society/_SocietyLib/SocietyWeb/
bash scripts/register_feishu_daily.sh --dry-run
```

输出应为 mavis cron create 命令预览 + 设计说明 + 前置条件 checklist。

#### 2.2 list 查已注册(避免重复)

```bash
# 9/11 周期简化设计下,需张勇手动调 mavis 工具的 cron list 命令
mavis cron list --agent-name me
```

预期 9/10 巡检时点 4 个 cron:
| cron_name | schedule | CST | 用途 |
|---|---|---|---|
| `daily-社会` | `20 0 * * *` | 00:20 | 写行业日报(Daily/09-社会-Society-日报-YYYYMMDD.md)|
| `log-社会-日报` | `20 1 * * *` | 01:20 | 写工程师日志(09-社会-Society/.Log/)|
| `巡检-社会` | `20 2 * * *` | 02:20 | 巡检项目(.Log/巡检-社会-YYYYMMDD.md)|
| `dev-社会-日报` | `20 3 * * *` | 03:20 | 当日开发(本 cron,SocietyWeb/)|
| `feishu-社会-日报` | `0 9 * * *` | 09:00 | **飞书日报(待注册,.Log/日报-YYYYMMDD.md)** |

#### 2.3 apply 真注册

**9/11 周期简化设计下,需张勇手动调 mavis 工具的 cron create 命令**(本脚本不擅自改系统状态):

```bash
# 在 mavis tool 环境调:
mavis({
  command: "cron create",
  args: {
    cron_name: "feishu-社会-日报",
    schedule: "0 9 * * *",
    timezone: "Asia/Shanghai",
    agent_name: "me",
    prompt: '你是 09-社会-Society 行业顾问。每日 09:00 自动跑飞书日报:1. cd /Users/aaron/Mac/Consultant/09-社会-Society/_SocietyLib/SocietyWeb/;2. 读 $FEISHU_WEBHOOK_URL env(若为空,跳过推送,只生成 .Log/日报-昨日.md);3. 跑 bash scripts/run_daily_report.sh --push --webhook-url "$FEISHU_WEBHOOK_URL"(默认 report_date=昨日 CST);4. git add -A + commit -m "feishu-daily: 推送日报 $(date +%Y%m%d)";5. source /Users/aaron/Mac/Consultant/_ConsultantLib/.github-sync/env.sh(若未注入 git 凭证);6. git push -q -f gitee main;7. git push -q -f github main(慢,允许 30s 超时,失败不阻塞);8. 完成后报告:日报文件路径 + 飞书 message_id + Gitee push 状态 + GitHub push 状态 + commit hash。',
    session: { mode: "new" },
    enabled: true
  }
})
```

#### 2.4 验证注册成功

```bash
# 应在 list 中看到 feishu-社会-日报
mavis cron list --agent-name me --search feishu
```

---

### 阶段 3:端到端验证

#### 3.1 等 9/12 09:00 cron 自动触发

不需要任何操作,mavis 会按 schedule 自动触发 `feishu-社会-日报` cron。

#### 3.2 验证 3 项产物

```bash
# 1. .Log/日报-20260911.md 应自动生成(1454 字节左右)
ls -la .Log/日报-20260911.md

# 2. 飞书群应收到推送(标题前缀 "【SocietyAdvisor 日报 20260911】")
# 登录飞书 → SocietyAdvisor 日报 群 → 查看 9/12 09:00 消息

# 3. git 应有 feishu-daily commit + Gitee/GitHub push
git log --oneline -3
git log --all --oneline --grep "feishu-daily" -5
```

#### 3.3 失败排查

| 现象 | 可能原因 | 排查 |
|---|---|---|
| `.Log/日报-20260911.md` 未生成 | cron 未注册 / 09:00 cron 窗口未到 | `mavis cron list --search feishu` |
| 飞书群无消息 | `FEISHU_WEBHOOK_URL` 未注入 / webhook 失效 | `echo $FEISHU_WEBHOOK_URL` |
| 飞书推送失败 4xx | webhook URL 拼错 / 群机器人删除 | `bash scripts/run_daily_report.sh --push-dry-run --date 2026-09-11` |
| git push 失败 | 凭证未注入 / 远程断连 | `source /Users/aaron/Mac/Consultant/_ConsultantLib/.github-sync/env.sh` |
| cron 重复触发 2 次 | 同名 cron 重复注册 | `mavis cron delete --cron-id <旧cronId>` |

---

## 3. 注销流程(如需)

```bash
# 1. 查 cronId
mavis cron list --agent-name me --search feishu

# 2. 注销
mavis cron delete --cron-id <cronId>

# 3. 验证
mavis cron list --agent-name me --search feishu   # 应为空
```

或用本项目脚本:

```bash
bash scripts/register_feishu_daily.sh --unregister   # 9/11 简化设计下,只打印流程提示
```

---

## 4. 风险与边界

| 风险 | 影响 | 应对 |
|---|---|---|
| `FEISHU_WEBHOOK_URL` 写入 `~/.zshrc` 但 mavis cron 用独立 env | cron 触发时 env 无 webhook,推送失败 | mavis cron 9-社会-Society 已有 4 cron,默认继承父 env;若不行,在 prompt 里加 `source ~/.zshrc` |
| 09:00 cron 重复注册 2 次 | 同一日生成 2 份日报 + 飞书群 2 条消息 | cron_name 唯一 + `--list` 检查;若重复,mavis cron delete 旧 cronId |
| 真实 cron 触发后 daily_report.py 缺数据 | 13 条快照 + 15 议题 + 18 边 是当前 baseline;若 Phase 1 接入真实舆情,数据源切换时需保持兼容 | 9/11 周期不切换数据源,沿用 baseline |
| 跨日触发(09:00 cron 跨日) | 昨日 CST 已是今日,生成昨日日报 | `run_daily_report.sh` 默认 report_date=昨日 CST,语义正确 |

---

## 5. 变更记录

| 日期 | 变更 | commit |
|---|---|---|
| 2026-09-11 | 首版:register_feishu_daily.sh + feishu-cron-setup.md(本轮 T5 应急补建) | TBD |
| 2026-09-09 | 上游:`scripts/feishu_publish.py` 真飞书 webhook 推送模块(本流程前置) | `fda4d88` |
| 2026-09-08 | 上游:`scripts/run_daily_report.sh` cron 入口 + --push-stub | `fa57304` |
| 2026-09-04 | 上游:`scripts/daily_report.py` 飞书日报生成器 4 段结构 | `c0d7125` |
