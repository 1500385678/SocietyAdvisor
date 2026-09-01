# SocietyAdvisor API · Phase 0 骨架

> FastAPI 入口,服务于 Phase 0 #5"搭建 FastAPI 骨架 + /graph /pulse 接口"
> 启动时间:2026-08-28
> 关联任务:项目开发计划.md Phase 0 #5
> 最近更新:2026-09-02(/pulse 状态从 🟡 桩 → ✅,同步 9/1 T5 周期 #4 第二步落盘)

## 启动

```bash
# 项目根目录
cd /Users/aaron/Mac/Consultant/09-社会-Society/_SocietyLib/SocietyWeb/

# 启动(已装 fastapi / uvicorn / pyyaml / pydantic 即可)
uvicorn app.main:app --reload --port 8000
```

打开 <http://localhost:8000/docs> 看 Swagger UI。

## 数据校验

```bash
# 校验 pulse_snapshots.yaml(13 条全部通过 + 外键 100% 命中)
python3 scripts/validate_pulse.py --strict --check-issues data/issues.yaml
```

对齐 `data/pulse_snapshots.schema.md` v1.0,Phase 1 接入真实舆情源前的人工录入阶段防错。

## 接口

| Method | Path | 状态 | 说明 |
|--------|------|------|------|
| GET | `/health` | ✅ | 健康检查,返回 `{"status": "ok", "version": "0.1.0"}` |
| GET | `/graph` | ✅ | 议题图谱(节点 + 边),支持 `?category=经济&min_heat=80` 过滤 |
| GET | `/pulse` | ✅ | 舆情切片(单议题多源聚合),`?issue_id=issue-001[&source=hybrid]`(9/1 T5 收尾,读 pulse_snapshots.yaml) |

## 数据流

```
data/issues.yaml ──┐
                   ├─→ app.data (lru_cache) ─→ /graph (节点)
data/issue_relations.yaml ─┘                  ─→ /graph (边)
                                              ─→ /pulse (反查议题名)
```

## 后续(Phase 0 剩余 + Phase 1)

- Phase 0 #6:飞书日报 cron 接入(每日 09:00 推"昨日 Top 10")— 唯一 Phase 0 `[ ]`
- Phase 1:加 `/stakeholder` `/timeline` 路由 + SQLite 切数据源 + Web App 骨架(React + Ant Design)
