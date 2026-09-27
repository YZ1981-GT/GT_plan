# Task 19 — canary 真库前置实证 + 身份 backfill 方案

**日期**：2026-09-27　**真库**：audit-postgres (Docker, healthy)

## 真库 I 循环全貌

```sql
SELECT item_id, length(remark) as remark_len, length(conclusion) as concl_len
FROM checklist_responses WHERE item_id LIKE 'I%' ORDER BY item_id;
```

| item_id | remark_len | concl_len | 类型 |
|---|---|---|---|
| I1-review-session-20260725075117 | 261 | NULL | 非主表键 |
| I2-tb-data | 60 | NULL | 非主表键 |
| **I5-2-rows** | **745** | NULL | 主表键（非空） |
| **I6-2-detail-rows** | **194** | NULL | 🔴 **canary 主表键（非空）** |
| I6-adj-audited-total | 6 | NULL | derived_total_key |
| I6-adj-capitalized-i2 | 6 | NULL | 联动键 |
| I6-adj-expected-total | 7 | NULL | derived_total_key |

- 总计 **7 个 item_id**
- 主表键非空：**2 条**（I5-2-rows 745B / I6-2-detail-rows 194B）
- I1/I2/I3/I4 主表键 + I6-2-rows(legacy)：**0 行**（完全无数据）

## canary I6-2-detail-rows 载荷实证

```json
[
  {"category": "智能平台研发", "months": [500000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "aje": 0, "rje": 0},
  {"category": "新品临床试验", "months": [300000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "aje": 0, "rje": 0}
]
```

### 🔴 身份字段缺失确认

- **2 行都没有 `id` 字段**
- **2 行都没有 `rowId` 字段**
- `useI6Detail.ts#L303` 的兜底逻辑 `raw.id ?? raw.rowId ?? \`row-${Date.now()}-...\`` 会每次读都生成新 id
- ⇒ roundtrip 会判成「全删全增」

### 身份 backfill 方案决定

采 **方案 A：一次性 backfill**（给真库那 2 行加 `id` 字段）。理由：
1. `category` 不是全局唯一的（不同项目可能有同名分类），不适合作主键
2. 一次性 backfill 后 id 稳定，后续所有 roundtrip 都能正常比对
3. 成本极低（一条 SQL UPDATE）

🔴 **backfill 在 Task 20 provider 注册前执行**，在同一事务内完成。
backfill 方式：读出 JSON → 给每个对象加 `id: "i6-detail-{uuid4}"` → 写回。

### 反向自检

- 若不做 backfill，连跑两次 `useI6Detail` 读取，两次的 id 集合必然不同
- backfill 后，连跑两次读取，id 集合必须相同

## 非空断言

- `I6-2-detail-rows` 非空：✅（194B / 2 行）
- 若此断言失败（真库被清空），canary 选型失效，须回 Task 4 重选

## Backfill 执行记录

**时间**：2026-09-27　**方法**：`_i6_backfill_id.py` 脚本（已删）

```sql
UPDATE checklist_responses SET remark = '[
  {"id": "i6-detail-bf01-zhptyd", "category": "智能平台研发", "months": [500000,0,...], "aje": 0, "rje": 0},
  {"id": "i6-detail-bf02-xplcsy", "category": "新品临床试验", "months": [300000,0,...], "aje": 0, "rje": 0}
]' WHERE item_id = 'I6-2-detail-rows';
```

**结果**：`UPDATE 1`

**验证**：
- 2 行都有 `id` 字段 ✅
- `i6-detail-bf01-zhptyd` → 智能平台研发
- `i6-detail-bf02-xplcsy` → 新品临床试验
- category / months / aje / rje 值未变 ✅

**id 命名规则**：`i6-detail-bf{seq}-{pinyin缩写}`，bf=backfill，确保与 `useI6Detail.ts#L303` 的
`row-${Date.now()}-...` 兜底格式不同，可区分 backfill 行与新增行。

🔴 **backfill 后身份稳定**：连跑两次读取，id 集合应相同（不再每次兜底生成新 id）。
