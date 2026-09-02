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

## 状态(2026-09-03)
- **Phase 0**: 6/6 完成 ✅(初始议题库 + 自动化抽取 + 议题关系图 + FastAPI 骨架 + 历史舆情快照灌库 + /pulse 真实读取,9/1 T5 周期收尾)
  - 2026-08-29 续:议题库 10 → 15(新增 issue-011 人口政策 / 012 教育改革 / 013 数字鸿沟 / 014 医疗资源 / 015 乡村振兴),关系图 12 → 18 条边
  - 2026-08-31 续:Phase 0 #4 起步 — `pulse_snapshots.schema.md` v1.0 + 首批 13 条模拟快照(6 议题 × 5 天)
  - 2026-09-01 续:Phase 0 #4 第二步 — `PulseSnapshot` / `PulseSeries` schema + `/pulse` 路由读真实数据,Phase 0 收尾 6/6
  - 2026-09-02 续(质量层):新增 `scripts/validate_pulse.py` 校验脚本(13/13 通过 + 外键 100% 命中 + 唯一性 0 冲突),Phase 0 计数仍 6/6,质量层叠加
  - 2026-09-03 续(质量层 · 工具链):新增 `scripts/issue_summary.py` 数据汇总 CLI(15 议题 / 18 边 / 5 category,跨表校验 0 孤儿边,`--json` / `--strict` / `--top K` 三档开关),Phase 0 计数仍 6/6,工具链补完
- **Phase 1**: 0/7 待启动(Web App 骨架未搭建)

## API 骨架(Phase 0 收尾)
- 入口:`app/main.py` · 启动 `uvicorn app.main:app --port 8000` → <http://localhost:8000/docs>
- 路由:`/health` `/graph` `/pulse`,详见 [app/README.md](./app/README.md)
- /pulse 用法:`GET /pulse?issue_id=issue-001` → 单议题多源时间序列;`&source=hybrid` 按来源过滤
- 数据校验:`python3 scripts/validate_pulse.py --strict --check-issues data/issues.yaml`
- 数据汇总:`python3 scripts/issue_summary.py`(议题数 / category 分组 / Top 5 热度 / 关系图出入度 / 跨表孤儿边校验)

## 关联文档
- 产品立项与技术方案: [项目开发计划.md](./项目开发计划.md)
- 议题库字段规范: [data/issues.schema.md](./data/issues.schema.md)
- 议题关系图规范: [data/issue_relations.schema.md](./data/issue_relations.schema.md)
- 舆情快照字段规范: [data/pulse_snapshots.schema.md](./data/pulse_snapshots.schema.md)
- 巡检报告: [.Log/巡检-社会-20260901.md](./.Log/巡检-社会-20260901.md)
