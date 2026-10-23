# 集团级附注披露模板下推 — 技术方案

## §1 架构总览

```
合并项目 ConsolNoteTab / 明细映射弹窗
  │
  ├── 「📝 编辑集团模板」→ 明细模板编辑器（复用 ConsolNoteDetailTemplate）
  │     每行加 category 字段：required / optional / dynamic_zone
  │
  ├── 「📤 下推模板」→ POST /consolidation/notes/{pid}/{year}/push-template
  │     遍历企业树数据叶子 → 逐家写 disclosure_notes + 激活结构锁
  │
  └── 「🔄 重新汇总」→ reaggregate_subtree（现有链路）
        固定行按 row_id 精确匹配，动态行走七级匹配
```

## §2 数据模型扩展

### 2.1 明细模板行扩展

在 `ConsolNoteDetailTemplateVersion.rows` JSONB 的每行中新增字段：

```json
{
  "target_row_id": "uuid-xxx",
  "canonical_name": "库存现金",
  "row_type": "data",
  "category": "required",      // NEW: required / optional / dynamic_zone
  "sort_order": 10,
  "aliases": ["现金"],
  "recommended_account_codes": ["1001"]
}
```

`category` 默认 `"required"`（向后兼容现有模板）。`dynamic_zone` 类型的行只有一个占位标记，`canonical_name` 为空或 `"[动态行区]"`。

### 2.2 子企业附注行扩展

在 `disclosure_notes.table_data._tables[].rows[]` 的每行中可选字段：

```json
{
  "label": "库存现金",
  "values": [100.5, 200.3],
  "row_type": "data",
  "_pushed_row_id": "uuid-xxx",    // NEW: 来自集团下推的行 ID（有此字段 = 被锁的行）
  "_pushed_category": "required",   // NEW: required / optional
  "_pushed_optional_active": true   // NEW: optional 行是否被子企业勾选（required 行无此字段）
}
```

### 2.3 下推记录表（新建）

```sql
-- V2xx
CREATE TABLE IF NOT EXISTS consol_note_template_push_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consol_project_id UUID NOT NULL REFERENCES projects(id),
    section_id TEXT NOT NULL,
    template_version_id UUID NOT NULL,
    pushed_by UUID,
    pushed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    entity_count INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    failures JSONB DEFAULT '[]'
);
```

## §3 下推服务 `consol_note_template_push_service.py`

### 3.1 主流程

```python
async def push_template_to_subsidiaries(
    db, consol_project_id, section_id, year, template_version_id, pushed_by,
) -> PushResult:
    # 1. 加载模板版本
    version = load_version(template_version_id)
    template_rows = version.rows
    
    # 2. 遍历企业树数据叶子
    tree = build_tree(db, consol_project_id)
    leaves = data_leaves(tree)
    
    # 3. 逐家下推
    results = []
    for leaf in leaves:
        if leaf.project_id is None:
            results.append(skip(leaf, "无关联项目"))
            continue
        try:
            await _push_to_one(db, leaf.project_id, section_id, year, template_rows)
            results.append(success(leaf))
        except Exception as e:
            results.append(failure(leaf, str(e)))
    
    # 4. 激活结构锁（只锁固定行）
    await activate_structure_lock(db, consol_project_id, section_id, template_version_id, leaves)
    
    # 5. 记录日志
    log = PushLog(...)
    db.add(log)
    await db.flush()
    
    return PushResult(...)
```

### 3.2 单企业下推 `_push_to_one`

```python
async def _push_to_one(db, project_id, section_id, year, template_rows):
    # 读现有附注章节
    note = await load_disclosure_note(db, project_id, section_id, year)
    
    if note is None:
        # 新建骨架
        rows = _build_skeleton(template_rows)
        await create_disclosure_note(db, project_id, section_id, year, rows)
    else:
        # 增量合并——不覆盖已有金额
        existing_rows = note.table_data.get("_tables", [{}])[0].get("rows", [])
        merged = _merge_rows(template_rows, existing_rows)
        note.table_data["_tables"][0]["rows"] = merged
        note.updated_at = now()
        await db.flush()
```

### 3.3 骨架构建 `_build_skeleton`

```python
def _build_skeleton(template_rows):
    rows = []
    for tr in template_rows:
        if tr["category"] == "dynamic_zone":
            rows.append({"label": "", "row_type": "dynamic_zone_marker", 
                         "_pushed_row_id": tr["target_row_id"]})
            continue
        rows.append({
            "label": tr["canonical_name"],
            "values": [],  # 金额为空
            "row_type": tr["row_type"],
            "_pushed_row_id": tr["target_row_id"],
            "_pushed_category": tr["category"],
            **({"_pushed_optional_active": True} if tr["category"] == "optional" else {}),
        })
    return rows
```

### 3.4 增量合并 `_merge_rows`

```python
def _merge_rows(template_rows, existing_rows):
    # 按 _pushed_row_id 索引现有行
    existing_by_id = {r["_pushed_row_id"]: r for r in existing_rows if "_pushed_row_id" in r}
    # 用户新增的行（没有 _pushed_row_id 的）
    user_added = [r for r in existing_rows if "_pushed_row_id" not in r]
    
    merged = []
    for tr in template_rows:
        rid = tr["target_row_id"]
        if tr["category"] == "dynamic_zone":
            # 动态行区：插入用户新增的行 + 占位标记
            merged.extend(user_added)
            user_added = []  # 只插一次
            merged.append({"label": "", "row_type": "dynamic_zone_marker", "_pushed_row_id": rid})
            continue
        existing = existing_by_id.get(rid)
        if existing:
            # 保留已有金额，更新行名（如果模板改了名）
            existing["label"] = tr["canonical_name"]
            existing["_pushed_category"] = tr["category"]
            merged.append(existing)
        else:
            # 新增行
            merged.append({
                "label": tr["canonical_name"],
                "values": [],
                "row_type": tr["row_type"],
                "_pushed_row_id": rid,
                "_pushed_category": tr["category"],
                **({"_pushed_optional_active": True} if tr["category"] == "optional" else {}),
            })
    # 剩余用户新增行追加在末尾（如果动态行区位置之前没有消化完）
    merged.extend(user_added)
    return merged
```

## §4 拉数时按 row_id 精确匹配

在 `consol_note_detail_suggest.py` 的 `suggest_template_rows` 七级匹配**之前**，加第 0 级：

```python
# 0. row_id 精确匹配（集团下推的行带 _pushed_row_id）
if "_pushed_row_id" in source_row_attrs:
    rid = source_row_attrs["_pushed_row_id"]
    if rid in target_row_id_index:
        → exact_id 匹配, confidence=1.0
        continue
```

这样集团下推的行（固定行 + 可选行）100% 按 `row_id` 匹配，完全绕开名字匹配。

## §5 前端改动

### 5.1 模板编辑器

- 每行增加 `category` 下拉选择（必填/可选/动态行区）
- 动态行区只能有一个，位于合计行之前

### 5.2 下推按钮与结果弹窗

- 合并附注工具栏增加「📤 下推模板」按钮
- 点击后调 `POST /consolidation/notes/{pid}/{year}/push-template`
- 结果弹窗显示：成功 N 家 / 失败 M 家（逐家列出失败原因）

### 5.3 子企业附注编辑器

- 带 `_pushed_row_id` + `_pushed_category=required` 的行显示🔒，不允许删除/改名
- 带 `_pushed_category=optional` 的行显示☐/☑ 切换
- `dynamic_zone_marker` 行渲染为「➕ 添加行」按钮

## §6 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/migrations/V2xx__consol_note_template_push_log.sql` | 新 | 下推日志表 |
| `backend/app/services/consol_note_template_push_service.py` | 新 | 下推服务 |
| `backend/app/routers/consol_notes.py` | 改 | 新增 push-template 端点 |
| `backend/app/services/consol_note_detail_template_service.py` | 改 | 模板行 category 校验 |
| `backend/app/services/consol_note_detail_suggest.py` | 改 | 第 0 级 row_id 匹配 |
| `backend/app/services/consol_note_detail_apply_service.py` | 改 | apply 时传递 row_id |
| `frontend/.../ConsolNoteTab.vue` | 改 | 下推按钮 + 结果弹窗 |
| `frontend/.../NoteTableEditor.vue` | 改 | 🔒行 + ☐可选行 + 动态行区 |
| `backend/tests/services/test_consol_note_template_push.py` | 新 | 下推服务测试 |

## §7 与现有机制的关系

| 现有机制 | 关系 |
|----------|------|
| 明细映射（V186） | 拉数链路不变，只是匹配时多了第 0 级 row_id |
| 结构锁（V200） | 下推后自动激活，复用现有 `consol_note_structure_lock` 表 |
| 映射规则模板 | 模板里的 `row_id` 通过下推传递到子企业，规则匹配时优先用 row_id |
| 公式推送种子 | 子企业的公式推送照旧——推送的是金额，不是行结构 |
| 标题行库 | 不受影响——标题行库识别表级结构，行级匹配在 suggest 层 |

## §8 风险

- 下推写入子企业 `disclosure_notes` 是跨项目写操作，需要校验权限（合并项目的 edit 级 + 子企业项目的写权限）
- 增量合并可能产生冲突（模板删了一行但子企业已填数据）→ 标冲突让合并负责人决策，不自动删
- `dynamic_zone_marker` 是特殊行类型，附注编辑器、Word 导出、就绪判定都需要识别它
