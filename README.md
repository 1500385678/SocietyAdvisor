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

## 状态(2026-09-08)
- **Phase 0**: 7/6 严格计数 ✅(超额 1 项 = 飞书日报生成器脚本骨架,9/4 T5 周期叠加,9/6 README 状态段与项目开发计划.md 严格计数同步;原 6/6 主体任务 9/1 T5 周期收尾)
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
- 飞书日报 cron 入口:`bash scripts/run_daily_report.sh`(默认昨日 CST,输出 `.Log/日报-YYYYMMDD.md`;`--dry-run` 预览 / `--strict` 严格模式 / `--push-stub` 飞书推送占位)

## 关联文档
- 产品立项与技术方案: [项目开发计划.md](./项目开发计划.md)
- 议题库字段规范: [data/issues.schema.md](./data/issues.schema.md)
- 议题关系图规范: [data/issue_relations.schema.md](./data/issue_relations.schema.md)
- 舆情快照字段规范: [data/pulse_snapshots.schema.md](./data/pulse_snapshots.schema.md)
- 巡检报告: [.Log/巡检-社会-20260901.md](./.Log/巡检-社会-20260901.md)
