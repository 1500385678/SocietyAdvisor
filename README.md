# SocietyAdvisor

> 09-社会-Society 行业 Web 项目 · 内部代号 SocietyAdvisor

## 项目说明
基于张勇的 36 行业架构,SocietyAdvisor 是 社会-Society 行业的 Web 端顾问产品。
聚焦**议题图谱 + 舆情切片 + 利益方分析 + 时间线复盘**四大模块,
服务于媒体记者、政策研究、企业公共事务、学术研究者等需要快速理解社会动态的场景。

## 同步
- GitHub: https://github.com/1500385678/SocietyAdvisor
- Gitee: https://gitee.com/architectzy/SocietyAdvisor

## 自动化
- T1 每日 01:00 巡检 + 写日报(.Log/巡检-社会-YYYYMMDD.md)
- T4 每日 02:00 检查项目并更新 .plan/YYYYMMDD.md
- T5 每日 03:00 完成小步开发并 commit + push

## 状态(2026-09-11)
- **Phase 0**: 7/6 严格计数 ✅(超额 1 项 = 飞书日报生成器脚本骨架,9/4 T5 周期叠加,9/6 README 状态段与项目开发计划.md 严格计数同步;原 6/6 主体任务 9/1 T5 周期收尾)
- **Phase 0 #6 真飞书 cron 调度层补完(9/11)**:新增 `scripts/register_feishu_daily.sh` 一键注册脚本(4 档开关:`--dry-run` 默认预览 mavis cron create 命令 / `--apply` 提示手动调 mavis 工具 cron create / `--list` 查已注册 / `--unregister` 注销;cron_name=`feishu-社会-日报` / schedule=`0 9 * * *` / timezone=`Asia/Shanghai` / agent_name=`me` / session.mode=`new`)+ `docs/feishu-cron-setup.md` 完整 3 段流程文档(`FEISHU_WEBHOOK_URL` env 配置 → 09:00 mavis cron 注册 → 端到端验证 .Log/日报-YYYYMMDD.md + 飞书推送 + git commit/push);闭环 9/9 commit `fda4d88` 明确"留待后续 T5 周期"那段(真飞书 webhook 推送 `FEISHU_WEBHOOK_URL` env 配置 + 注册 09:00 `mavis cron`);9/10 巡检项 4 揭示"9/9 日报缺失 + 9/10 日报未生成"问题,本轮提供完整解决路径,张勇手动 `--apply` 触发后,9/12 02:20 巡检应能验证 .Log/日报-20260911.md 自动生成;手测 4 档开关全部正常(--dry-run 打印完整 mavis cron create 命令预览 + 设计说明 + 前置条件 checklist / --list 显示 5 个 09-社会-Society cron 预期表 / --apply 打印 mavis tool cron create API 调用 / --unregister 打印 3 步注销流程 / --foo 退出码 1);**Phase 0 严格计数仍 7/6**(本轮属 #6 飞书日报"调度层"最终段,非新主任务;`FEISHU_WEBHOOK_URL` env 配置 + 09:00 cron 真注册需张勇手动触发,本轮不擅自改系统状态)
- **Phase 0 #6 飞书真推送补完(9/9)**:新增 `scripts/feishu_publish.py` 真飞书 webhook 推送模块(stdlib urllib 投递,无第三方 HTTP 依赖;`msg_type=text` 协议;`--webhook-url` / `--text` / `--from-file` / `--title` / `--transport` 5 档开关;退出码 0 成功 / 1 参数错 / 2 缺依赖 / 3 网络 / 4 4xx / 5 5xx / 6 其他;--dry-run 降级预览);`scripts/run_daily_report.sh` 9/8 预留的 `--push-stub` 升级为 `--push`(真调 `feishu_publish.py --from-file`),新增 `--push-dry-run`(隐式打开 PUSH,只预览 payload)/ `--webhook-url`(显式传,env 兜底)/ `--push-stub` 旧名兼容;手测 `bash scripts/run_daily_report.sh --push-dry-run` 输出 9/8 推送 payload 预览(标题前缀 `【SocietyAdvisor 日报 20260908】` + 1454 字符全文),`--push --webhook-url https://httpbin.org/status/200` 走通 stdlib urllib 真投递 HTTP 200 / 4xx → exit 4 / 5xx → exit 5 / DNS 失败 → exit 3 全档退出码映射正确;**Phase 0 严格计数仍 7/6**(真推送属于 #6 飞书日报"调度层"最终补完,非新主任务;巡检项 4 "9/8 日报缺失"也借此周期手测补建,见 `.Log/日报-20260908.md`)
- **Phase 0 #6 cron 入口补完(9/8)**:新增 `scripts/run_daily_report.sh` 飞书日报 cron 入口包装(默认 report_date=昨日 CST,输出 `.Log/日报-YYYYMMDD.md`,`--strict` 模式 + `--dry-run` 预览 + `--push-stub` 飞书推送占位),把 `daily_report.py` 脚本骨架升到"可定时调起"形态,真飞书 webhook 推送留给后续周期;手测 `bash scripts/run_daily_report.sh --dry-run` 输出 2026-09-07 Top 10 完整预览,默认模式写入 `.Log/日报-20260907.md`(1454 字节,15 议题 / 13 快照)
  - 2026-08-29 续:议题库 10 → 15(新增 issue-011 人口政策 / 012 教育改革 / 013 数字鸿沟 / 014 医疗资源 / 015 乡村振兴),关系图 12 → 18 条边
  - 2026-08-31 续:Phase 0 #4 起步 — `pulse_snapshots.schema.md` v1.0 + 首批 13 条模拟快照(6 议题 × 5 天)
  - 2026-09-01 续:Phase 0 #4 第二步 — `PulseSnapshot` / `PulseSeries` schema + `/pulse` 路由读真实数据,Phase 0 主体 6/6 收尾
  - 2026-09-02 续(质量层):新增 `scripts/validate_pulse.py` 校验脚本(13/13 通过 + 外键 100% 命中 + 唯一性 0 冲突),Phase 0 主体 6/6 + 质量层叠加
  - 2026-09-03 续(质量层 · 工具链):新增 `scripts/issue_summary.py` 数据汇总 CLI(15 议题 / 18 边 / 5 category,跨表校验 0 孤儿边,`--json` / `--strict` / `--top K` 三档开关),Phase 0 主体 6/6 + 工具链补完
  - 2026-09-04 续(Phase 0 #6 起步 · 飞书日报):新增 `scripts/daily_report.py` 飞书日报生成器(4 段结构:Top 10 热度 + 声量监控汇总 + 关系图出入度 + 报告元信息,`--json` / `--strict` / `--output` / `--date` / `--top K` 五档开关,Markdown + JSON 双输出),Phase 0 严格计数 7/6(原 6/6 + 飞书日报生成器脚本骨架层,真实 cron 调度留待后续周期)
  - 2026-09-05 续(.plan/ 模式根因修复):`.gitignore` 末行加入 `.plan/   # 本地临时 plan 草稿,不入库` 排除规则,根除 9/2→9/3→9/4→9/5 4 周期 T1 报"uncommitted deletion"模式,9/6 02:20 巡检时点 working tree 完全 clean
  - 2026-09-08 续(Phase 0 #6 cron 入口补完):新增 `scripts/run_daily_report.sh` 飞书日报 cron 入口包装(默认 report_date=昨日 CST,输出 `.Log/日报-YYYYMMDD.md`,`--strict` / `--dry-run` / `--push-stub` 三档开关),把 `daily_report.py` 脚本骨架升到"可定时调起"形态,真飞书 webhook 推送留给后续周期;**Phase 0 严格计数仍 7/6**(cron 入口属于 #6 飞书日报"调度层"补完,非新主任务)
- **Phase 1**: 0/7 待启动(Web App 骨架未搭建)

## API 骨架(Phase 0 收尾)
- 入口:`app/main.py` · 启动 `uvicorn app.main:app --port 8000` → <http://localhost:8000/docs>
- 路由:`/health` `/graph` `/pulse`,详见 [app/README.md](./app/README.md)
- /pulse 用法:`GET /pulse?issue_id=issue-001` → 单议题多源时间序列;`&source=hybrid` 按来源过滤
- 数据校验:`python3 scripts/validate_pulse.py --strict --check-issues data/issues.yaml`
- 数据汇总:`python3 scripts/issue_summary.py`(议题数 / category 分组 / Top 5 热度 / 关系图出入度 / 跨表孤儿边校验)
- 飞书日报生成:`python3 scripts/daily_report.py`(4 段 Markdown 日报:Top 10 热度 / 声量监控 / 关系图亮点 / 元信息)
- 飞书日报 cron 入口:`bash scripts/run_daily_report.sh`(默认昨日 CST,输出 `.Log/日报-YYYYMMDD.md`;`--dry-run` 预览 / `--strict` 严格模式 / `--push` 真推飞书 webhook(走 env `FEISHU_WEBHOOK_URL` 或 `--webhook-url`)/ `--push-dry-run` 推送预览)
- 飞书日报 cron 注册:`bash scripts/register_feishu_daily.sh`(`--dry-run` 预览 mavis cron create 命令 / `--apply` 提示手动调 mavis tool / `--list` 查 09-社会-Society 已注册 cron / `--unregister` 注销;详见 [docs/feishu-cron-setup.md](./docs/feishu-cron-setup.md))
- 飞书日报 cron 注册流程:`docs/feishu-cron-setup.md` 3 段流程(`FEISHU_WEBHOOK_URL` env 配置 → 09:00 `mavis cron` 注册 → 端到端验证)
- 飞书真推送模块:`python3 scripts/feishu_publish.py`(`--text` / `--from-file` / `--webhook-url` / `--title` / `--transport urllib|curl` / `--dry-run` 6 档;退出码 0 成功 / 1 参数 / 2 依赖 / 3 网络 / 4 4xx / 5 5xx)

## 关联文档
- 产品立项与技术方案: [项目开发计划.md](./项目开发计划.md)
- 议题库字段规范: [data/issues.schema.md](./data/issues.schema.md)
- 议题关系图规范: [data/issue_relations.schema.md](./data/issue_relations.schema.md)
- 舆情快照字段规范: [data/pulse_snapshots.schema.md](./data/pulse_snapshots.schema.md)
- 巡检报告: [.Log/巡检-社会-20260901.md](./.Log/巡检-社会-20260901.md)
