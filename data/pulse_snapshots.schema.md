# SocietyAdvisor · 舆情快照字段规范 v1.0

> 数据源:`data/pulse_snapshots.yaml`
> 适配:`/pulse` 路由 + 飞书日报"近 7 日声量趋势"段落
> 维护者:09-社会-Society agent
> 创建日期:2026-08-31(Phase 0 #4 灌库起步)
> 状态:**v1.0 首版,字段最小集,Phase 1 接入真实数据源后扩展**

---

## 一、字段一览

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `issue_id` | string | ✅ | 关联 `issues.yaml` 中的 `id`,如 `issue-001`;**外键,必须已存在** |
| `source` | enum | ✅ | 数据来源平台,见 1.1 |
| `volume` | int(≥0) | ✅ | 当日声量(条/篇),0 = 无新增 |
| `sentiment_pos` | float(0.0-1.0) | ✅ | 正面情感占比,0.0-1.0,三段加和 = 1.0(允许 ±0.01 浮点误差) |
| `sentiment_neu` | float(0.0-1.0) | ✅ | 中性情感占比 |
| `sentiment_neg` | float(0.0-1.0) | ✅ | 负面情感占比 |
| `snapshot_date` | date(YYYY-MM-DD) | ✅ | 快照日期(数据所属日,非入库日) |
| `source_url` | string | ❌ | 该日代表性内容 URL(可选,Phase 1 接入时填) |
| `note` | string | ❌ | 人工备注(数据合成说明 / 异常说明),≤120 字 |

### 1.1 `source` 枚举约束

```yaml
source_enum: [news, weibo, zhihu, wechat, hybrid]
```

| 值 | 含义 | Phase 0 状态 |
|----|------|--------------|
| `news` | 主流新闻媒体(新华/澎湃/财新等) | 模拟 |
| `weibo` | 微博平台声量 | 模拟 |
| `zhihu` | 知乎热榜/回答 | 模拟 |
| `wechat` | 微信公众号文章 | 模拟 |
| `hybrid` | 多源聚合(日报合并时使用) | 模拟 |

**Phase 0 全部为 `hybrid` 模拟值**(手工合成,不代表真实声量),仅作为 `/pulse` 接口契约测试用。Phase 1 接入真实 API 后改为各平台单值。

---

## 二、唯一性约束

`(issue_id, source, snapshot_date)` 三元组必须唯一:

- 同一议题同一来源同一日只能有 1 条快照
- 重复录入视为数据错误,Phase 0 灌库脚本需在校验阶段报 `duplicate_key`
- 多源数据合并:每源 1 条,不合并为 1 条(便于后续按 source 过滤)

---

## 三、情感分布约束

```
sentiment_pos + sentiment_neu + sentiment_neg = 1.0 (±0.01)
```

- 全部 0 或全部 1 均合法(极端情况:当日全正/全负)
- 缺失任一段视为数据不完整,灌库脚本报 `incomplete_sentiment`
- 范围外值(如 -0.1 / 1.5)报 `sentiment_out_of_range`

---

## 四、典型样例

```yaml
- issue_id: issue-001       # 就业形势
  source: hybrid
  volume: 1240
  sentiment_pos: 0.18
  sentiment_neu: 0.41
  sentiment_neg: 0.41
  snapshot_date: 2026-08-25
  note: "Phase 0 模拟值,代表 8/25 当日全网声量与情感分布"
```

---

## 五、与开发计划 / 数据架构的对应

- **数据架构**:对应 `项目开发计划.md` 4.3 节 `pulse_snapshots` 表字段(volume / sentiment_pos / sentiment_neu / sentiment_neg / snapshot_date / source / issue_id)
- **Phase 0 进度**:对应 `项目开发计划.md` 第 217 行 Phase 0 #4「历史舆情快照灌库」checkbox
- **API 契约**:对应 `app/schemas.py` 中 `PulseStub` 模型,Phase 0 #4 完成后扩展为 `PulseSnapshot` + `PulseSeries`
- **采集层**:Phase 1 接入 scrapy + 官方 API,见 `项目开发计划.md` 4.2 节技术栈选型

---

## 六、版本与变更

| 版本 | 日期 | 变更 | 触发 |
|------|------|------|------|
| v1.0 | 2026-08-31 | 首版字段最小集,6 字段必填 + 2 字段可选 | Phase 0 #4 起步 |
