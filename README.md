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

## 状态(2026-08-28)
- **Phase 0**: 4/6 完成(初始议题库 + 自动化抽取 + 议题关系图 + FastAPI 骨架,见 `data/issues.yaml` + `data/issue_relations.yaml` + `app/`)
- **Phase 1**: 0/6 待启动(Web App 骨架未搭建)

## API 骨架(Phase 0 #5)
- 入口:`app/main.py` · 启动 `uvicorn app.main:app --port 8000` → <http://localhost:8000/docs>
- 路由:`/health` `/graph` `/pulse`,详见 [app/README.md](./app/README.md)

## 关联文档
- 产品立项与技术方案: [项目开发计划.md](./项目开发计划.md)
- 议题库字段规范: [data/issues.schema.md](./data/issues.schema.md)
- 议题关系图规范: [data/issue_relations.schema.md](./data/issue_relations.schema.md)
- 巡检报告: [.Log/巡检-社会-20260827.md](./.Log/巡检-社会-20260827.md)
