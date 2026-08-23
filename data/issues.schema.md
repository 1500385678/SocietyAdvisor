# SocietyAdvisor · 议题库字段规范 v1.0

> 数据源:`data/issues.yaml`
> 适配:T5 即将启动的 `md_to_json.py` → SQLite `issues` 表
> 维护者:09-社会-Society agent
> 更新日期:2026-08-24

---

## 一、字段一览

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 议题唯一 ID,格式 `issue-NNN`(3 位补零) |
| `name` | string | ✅ | 议题中文名(2-10 字),用于展示与搜索 |
| `category` | enum | ✅ | 所属大类,5 选 1:经济 / 教育 / 科技 / 环境 / 社会 |
| `description` | string(multi-line) | ✅ | 议题核心内涵,50-200 字,说明"讨论什么" |
| `tags` | string[] | ✅ | 3-5 个标签,中文短词,用于二级筛选与全文检索 |
| `heat_score` | int(0-100) | ✅ | 议题热度评分(由 T4 每日 cron 计算并回填) |
| `created_at` | date(YYYY-MM-DD) | ✅ | 议题入库日期,ISO 8601 |

---

## 二、字段细则

### 2.1 `id` 命名规则

- 格式:`issue-` + 3 位数字补零
- 分配:按入库顺序递增,**永不重用**
- 废弃议题 ID 不删除,只把对应记录标记为 `archived: true`(扩展字段,本期未启用)
- 范例:`issue-001`、`issue-002`、...、`issue-042`

### 2.2 `category` 枚举约束

```yaml
category_enum: [经济, 教育, 科技, 环境, 社会]
```

- 一期暂定 5 大类,Phase 2 可扩展「文化」「国际」「健康」等
- 一条议题**只能归属一个 category**,跨领域议题拆为多条

### 2.3 `description` 写作要求

- 长度:50-200 字
- 内容三要素:**现象 + 关键变量 + 关注点**
- 避免抽象口号(如"促进社会发展"),要可操作
- 多行 YAML 字符串,使用 `|` 保留换行

### 2.4 `tags` 标签规则

- 数量:3-5 个
- 形式:中文 2-6 字短词,不用空格、不用英文逗号
- 用途:二级筛选、相似度计算、舆情抓取关键词扩展
- 与 `name` 语义不重复

### 2.5 `heat_score` 计算口径

- 范围:0-100
- 计算维度(T4 cron 实现):
  1. 近 7 日新闻提及量(40%)
  2. 微博/知乎热搜出现频次(30%)
  3. 政策文件发布密度(15%)
  4. 学术研究新增(15%)
- 初始入库默认 50,首次跑 T4 后回填
- 每周日 23:50 写入 `.plan/heatmap.json` 备份

### 2.6 `created_at` 时间戳

- 格式:`YYYY-MM-DD`
- 语义:首次入库日期,后续编辑不修改
- 历史回填(2026-08-24 之前的议题)统一记为 2026-08-24

---

## 三、YAML 校验示例

```python
import yaml
from pathlib import Path

def load_issues():
    raw = Path("data/issues.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    issues = data["issues"]
    assert len(issues) == 10, f"首期 10 条,实际 {len(issues)}"

    valid_categories = {"经济", "教育", "科技", "环境", "社会"}
    for it in issues:
        assert it["id"].startswith("issue-")
        assert it["category"] in valid_categories
        assert 0 <= it["heat_score"] <= 100
        assert 3 <= len(it["tags"]) <= 5
        assert 50 <= len(it["description"]) <= 400  # 允许换行展开
    return issues
```

---

## 四、与 SQLite 表的映射(T5 衔接)

| YAML 字段 | issues 表列 | PostgreSQL 类型 |
|-----------|------------|----------------|
| id | id | TEXT PRIMARY KEY |
| name | name | TEXT NOT NULL |
| category | category | TEXT(枚举约束) |
| description | description | TEXT |
| tags | tags | TEXT[] |
| heat_score | heat_score | SMALLINT |
| created_at | created_at | DATE |

T5 `md_to_json.py` 只需做 `INSERT OR REPLACE` 即可幂等更新。

---

## 五、变更记录

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-08-24 | v1.0 建立,首批 10 条议题入库 | 09-社会-Society (T4 cron) |
