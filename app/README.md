# SocietyAdvisor API · Phase 0 骨架

> FastAPI 入口,服务于 Phase 0 #5"搭建 FastAPI 骨架 + /graph /pulse 接口"
> 启动时间:2026-08-28
> 关联任务:项目开发计划.md Phase 0 #5

## 启动

```bash
# 项目根目录
cd /Users/aaron/Mac/Consultant/09-社会-Society/_SocietyLib/SocietyWeb/

# 启动(已装 fastapi / uvicorn / pyyaml / pydantic 即可)
uvicorn app.main:app --reload --port 8000
```

打开 <http://localhost:8000/docs> 看 Swagger UI。

## 接口

| Method | Path | 状态 | 说明 |
|--------|------|------|------|
| GET | `/health` | ✅ | 健康检查,返回 `{"status": "ok", "version": "0.1.0"}` |
| GET | `/graph` | ✅ | 议题图谱(节点 + 边),支持 `?category=经济&min_heat=80` 过滤 |
| GET | `/pulse` | 🟡 桩 | 舆情切片,Phase 0 暂返回 `not_implemented`,等待 #4 历史舆情快照灌库 |

## 数据流

```
data/issues.yaml ──┐
                   ├─→ app.data (lru_cache) ─→ /graph (节点)
data/issue_relations.yaml ─┘                  ─→ /graph (边)
                                              ─→ /pulse (反查议题名)
```

## 后续(Phase 0 剩余 + Phase 1)

- Phase 0 #4:历史舆情快照灌库 → `/pulse` 返回真实声量 + 情感分布
- Phase 1:加 `/stakeholder` `/timeline` 路由 + SQLite 切数据源
