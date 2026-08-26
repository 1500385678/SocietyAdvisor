# SocietyAdvisor · 议题关系字段规范 v1.0

> 数据源:`data/issue_relations.yaml`
> 适配:T5 `md_to_json.py relations` → SQLite `issue_relations` 表
> 维护者:09-社会-Society agent
> 更新日期:2026-08-27

---

## 一、字段一览

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | ✅ | 起始议题 ID,外键引用 `issues.id` |
| `target` | string | ✅ | 目标议题 ID,外键引用 `issues.id` |
| `relation` | enum | ✅ | 关系类型,3 选 1:`cause` / `influence` / `related` |
| `weight` | float(0-1) | ✅ | 关系强度,2 位小数,用于图谱边粗细与排序 |
| `note` | string(multi-line) | ✅ | 关系注释,30-150 字,说明"为什么相关 + 关键机制" |
| `created_at` | date(YYYY-MM-DD) | ✅ | 关系入库日期,ISO 8601 |

---

## 二、字段细则

### 2.1 `source` / `target` 命名规则

- 必须存在于 `data/issues.yaml` 的 `issues[].id` 列表
- `source != target`(不允许自环)
- 边为**有向**:`A cause B` ≠ `B cause A`,需要单独建一条
- 不存在"重复边":同一 `(source, target, relation)` 三元组只能出现一次
- 范例:`issue-001`、`issue-009`

### 2.2 `relation` 枚举约束

```yaml
relation_enum: [cause, influence, related]
```

- **`cause`**:A 直接导致 B,机制清晰可追溯(权重通常 ≥ 0.5)
- **`influence`**:A 显著影响 B 的发展或表现,但非唯一原因(权重 0.3-0.7)
- **`related`**:A 与 B 存在主题交叉或共同讨论空间,但无明确因果(权重 0.2-0.5)

> 一期暂定 3 类;Phase 2 可扩展 `opposite`(对立)、`sequence`(时序)、`subsume`(包含)

### 2.3 `weight` 计算口径

- 范围:0.0 - 1.0,2 位小数
- 经验赋值(本期手工标注,T4 cron 后续可改自动计算):
  - 0.7-1.0:核心因果,多源数据反复验证
  - 0.4-0.7:显著影响,主要文献支持
  - 0.2-0.4:边缘相关,观察期讨论
- 用途:图谱渲染时 `edge.width = weight * 10`,节点排序时 `node.score = Σ inbound.weight`

### 2.4 `note` 写作要求

- 长度:30-150 字
- 三要素:**机制 + 关键变量 + 政策/数据锚点**
- 避免抽象判断(如"两者相关"),要可操作
- 多行 YAML 字符串,使用 `|` 保留换行

### 2.5 `created_at` 时间戳

- 格式:`YYYY-MM-DD`
- 语义:首次入库日期,后续编辑不修改
- 历史回填(2026-08-27 之前的边)统一记为 2026-08-27

---

## 三、YAML 校验示例

```python
import yaml
from pathlib import Path

def load_relations():
    raw = Path("data/issue_relations.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    relations = data["relations"]

    valid_relations = {"cause", "influence", "related"}
    edges = set()
    for rel in relations:
        # 字段校验
        assert rel["source"].startswith("issue-")
        assert rel["target"].startswith("issue-")
        assert rel["source"] != rel["target"], "自环禁止"
        assert rel["relation"] in valid_relations
        assert 0.0 <= rel["weight"] <= 1.0
        assert 30 <= len(rel["note"]) <= 300  # 允许换行展开
        # 唯一性
        key = (rel["source"], rel["target"], rel["relation"])
        assert key not in edges, f"重复边: {key}"
        edges.add(key)
    return relations
```

---

## 四、与 SQLite 表的映射(T5 衔接)

| YAML 字段 | issue_relations 表列 | PostgreSQL 类型 |
|-----------|----------------------|----------------|
| source | source_id | TEXT REFERENCES issues(id) |
| target | target_id | TEXT REFERENCES issues(id) |
| relation | relation | TEXT(枚举约束) |
| weight | weight | REAL |
| note | note | TEXT |
| created_at | created_at | DATE |
| (组合主键) | (source_id, target_id, relation) | PRIMARY KEY |

T5 `md_to_json.py relations` 只需做 `INSERT OR REPLACE` 即可幂等更新。

---

## 五、与 issues.yaml 的耦合

- 任何新边必须先确保 `source` / `target` 在 `data/issues.yaml` 已存在
- 若 `data/issues.yaml` 删除某议题,所有引用该 ID 的边须同步清理
- 推荐流程:`issues.yaml` 改完 → 跑 `md_to_json.py` → 再跑 `md_to_json.py relations` → 校验

---

## 六、变更记录

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-08-27 | v1.0 建立,首批 12 条边入库(覆盖 10 个议题的因果/影响/相关链路) | 09-社会-Society (T1 cron) |
