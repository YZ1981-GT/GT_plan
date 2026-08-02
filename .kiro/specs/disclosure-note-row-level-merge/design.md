# Design: 附注同步行级合并

## Overview

在 `wp_disclosure_sync_service` 的表级浅合并之上**加一层可选的行级合并**，
由载荷内的 `sub_table_data._row_scope` 触发；不声明就走原路径（零回归）。

段边界不新造标识 —— 直接读 `note_template_{listed,soe}.json` 里**已经存在**的
`rows[].report_row_code`（实测 listed 95 行 / soe 26 行带该字段，恰好落在多段共享表的段首）。
写入时给行打 `_seg` 戳，使下一轮同步能从落库数据自身定位段窗口，不必反查模板对齐标签
（标签在多个段里重复出现，全局按标签匹配必然串段）。

同一根因的第二个受害面 `_note_texts` / `text_content` 整替换，用同款「按键浅合并 +
显式删除语义」修掉。

首个消费者是 E1 外币章节（`五、73` / `八、92`），它是本 spec 的验收场景；
共享表清单里另外 28 张表由后续 per-cycle spec 逐个接入。

**明确不做**：
- 不改 `SyncFromWorkpaperRequest` schema（元数据键随 `sub_table_data` 走，同 `_note_texts` 范式）
- 不加迁移（`_row_scope` / `_seg` 都在 `table_data` JSONB 内）
- 不做「行级冲突检测 / 乐观锁」—— 段归属单一，同段并发写属 owner 内部问题
- 不动读时投影器的渲染语义，只要求它忽略未声明的行键

## Architecture

```
底稿披露 Tab
  buildXSyncPayload()
    sub_table_data = {
      "外币货币性项目": [ {label:"货币资金", ...}, {label:"其中：美元", ...}, ... ],
      "_row_scope":  { "外币货币性项目": { "owner_row_code": "BS-002" } },
      "_note_texts": [ { section:"e1-fx", title:"外币折算说明", text:"..." } ],
    }
        │  POST /workpapers/{id}/disclosure-notes/sync-from-workpaper
        ▼
wp_disclosure_sync_service.sync_from_workpaper
  ① _extract_note_texts            （既有）
  ② _extract_removed_table_keys    （既有）
  ③ _extract_row_scope             ★新增 → (data, {表名: RowScope})
  ④ normalize_sub_table_data       （既有）
  ⑤ 表级浅合并循环 —— 对每个推送表：
       has_scope ? _merge_rows_by_scope(...)   ★新增分支
                 : merged_sub[key] = rows      （既有，逐字节不变）
  ⑥ _drop_removed_tables           （既有）
  ⑦ _merge_note_texts              ★新增（替换原「整列表替换 + 无则置 None」）
        │
        ▼
disclosure_notes.table_data / text_content
        │  读时
        ▼
note_sub_table_projector.project_sub_tables → _tables[]（忽略 `_seg`）
```

段边界解析的数据流：

```
note_template_{variant}.json
   sections[].tables[].rows[].report_row_code
        │  生成器（构建期，产出可 diff 的清单 + drift 守卫）
        ▼
backend/data/note_shared_table_segments.json
   { "五、73": { "table": "外币货币性项目",
                "segments": [ {row_code:"BS-002", label:"货币资金", start:0, end:5}, ... ] } }
        │  运行期（服务端只读模板，清单供守卫/前端消费）
        ▼
note_shared_table_segments.resolve_segment_window(variant, section, table, owner_row_code)
        → (start, end) | None
```

## Components and Interfaces

### 1) `backend/app/services/note_shared_table_segments.py`（新建，纯函数 + 模板缓存）

```python
@dataclass(frozen=True)
class Segment:
    row_code: str          # 段首行 report_row_code，如 "BS-002"
    label: str             # 段首行标签，如 "货币资金"（溯源展示 / 守卫可读性）
    start: int             # 段首行在 rows[] 的下标（含）
    end: int               # 段止下标（不含）

def split_segments(rows: Sequence[Mapping]) -> list[Segment]:
    """按 report_row_code 切段。纯函数，无 DB/IO（Requirement 2.5）。

    段 = 从带 report_row_code 的行起，到下一个带 report_row_code 的行前；末段到表尾。
    首个带 report_row_code 的行之前若有行（表头说明行等），不属于任何段。
    """

def template_rows(variant: str, section_number: str, table_name: str) -> list[dict] | None:
    """模板行集（lru_cache；查不到返 None → 调用方 fail closed）。"""

def resolve_segment_window(
    variant: str, section_number: str, table_name: str, owner_row_code: str
) -> Segment | None:
    """段窗口。查不到表 / 查不到 owner_row_code → None（Requirement 2.2）。"""

def is_shared_table(variant: str, section_number: str, table_name: str) -> bool:
    """是否多段共享表（≥2 段）—— 供守卫判定「该不该带 _row_scope」。"""

def stamp_baseline_rows(rows: Sequence[Mapping]) -> list[dict]:
    """模板骨架 → 带 `_seg` 戳的基线行（数值置空，标签保留）。Requirement 4.1/4.4。

    `_seg` 由段首行的 report_row_code 向下传播到下一个段首之前。
    """
```

### 1b) 变体解析（`resolve_template_variant`，**易错点**）

```python
def resolve_template_variant(
    current_standard: str | None, source_template: SourceTemplate | None
) -> str | None:
    """决定查哪份 note_template。返回 'listed' / 'soe' / None（None → fail closed）。

    🔴 **禁止按章节号推导**：实测 20 个章节号同时存在于两份模板、其中 13 个标题不同
    （`八、1` listed = 政府补助 / soe = 货币资金；`五、42` listed = 其他应付款）。
    查错模板 → 算出错误段边界 → 覆盖错误的行区间。

    优先级：`current_standard` 前缀（`listed*` / `soe*`）> `note.source_template` > None。
    `source_template` 只作兜底 —— memory 已实证它有错配
    （项目 `2aa00f57` 的 `五、1` 记的是 `soe`，而 `五、1` 是上市编号）。
    """
```

### 2) `wp_disclosure_sync_service` 新增私有件

```python
SEG_KEY = "_seg"

@dataclass(frozen=True)
class RowScope:
    table_name: str
    owner_row_code: str

def _extract_row_scope(
    sub_table_data: dict | None,
) -> tuple[dict, dict[str, RowScope]]:
    """剥离 `_row_scope`（对称 `_extract_removed_table_keys`）。

    非法形态（非 dict / 缺 owner_row_code / 表名以 `_` 开头）一律丢弃并记 warning。
    """

def _merge_rows_by_scope(
    existing_rows: list[dict] | None,
    incoming_rows: list[dict],
    *,
    scope: RowScope,
    variant: str,
    section_number: str,
) -> tuple[list[dict], str | None]:
    """段内整段替换、段外原样保留。

    Returns:
        ``(merged_rows, error)``；``error`` 非空表示段边界解析失败 →
        调用方**跳过该表**（Requirement 2.2 fail closed），不得回退整表覆盖。

    基线选择（Requirement 4）：
      - existing_rows 非空 → 用它（不回退模板，否则抹掉他人已录数据）
      - existing_rows 为空 → 用 `stamp_baseline_rows(template_rows(...))`

    段窗口定位：
      - 基线里存在 `_seg == owner_row_code` 的**连续段** → 取该区间
      - 否则（首次 / 历史数据无戳）→ 用 `resolve_segment_window(...)` 的模板下标，
        并对基线长度做边界裁剪（Requirement 4.3：行数不一致以落库数据为准）

    incoming_rows 为空 → 段恢复为模板骨架行（Requirement 3.6），不是删段。
    写入行统一补 `_seg = owner_row_code`（Requirement 3.4）。
    """

def _merge_note_texts(
    existing: list[dict] | None,
    incoming: list[dict] | None,
    removed_sections: Sequence[str] = (),
) -> list[dict]:
    """按 `section` 键浅合并（Requirement 5.1/5.3）。

    - 同 `section` → incoming **原位**覆盖
    - 未推送的 `section` → 保留
    - `removed_sections` 里的 `section` → 删除（推送优先：本次推了就不删）
    - 段序稳定：既有顺序在前，新 section 追加在后（`text_content` 重排不跳动）
    - 合并键 `section` 优先、退 `title`；**两者皆空则用位置化占位键**
      （存量有循环推 `[{"text": "…"}]`，若「保留 + 追加」则每同步一次多攒一条）
    """
```

调用点改动（两个写入口，Requirement 6.3）：

| 位置 | 现状 | 改后 |
|------|------|------|
| `sync_from_workpaper` 第 ⑤ 步 | `merged_sub[key] = rows` | `key in row_scopes ? _merge_rows_by_scope(...) : merged_sub[key] = rows` |
| `sync_from_workpaper` `note_texts` 分支 | `note.text_content = formatted_texts or None` | 先 `_merge_note_texts` 再 `_format_note_texts`，**无推送时保留既有** |
| `sync_from_html`（实际方法名，非 `sync_from_html_disclosure`） | `existing_table_data["sub_table_data"] = incoming_sub` | 同款加行级合并分支（**新建**分支除外，那里拿不到变体且无他人数据） |

🔴 **基线不能取表级合并结果**：调用方已把 incoming 写进 `merged_sub` 了，
故行级合并必须显式传 `baselines=existing_sub`（落库既有子表），
否则「基线」就是 incoming 本身 → 段外行全丢。落地时已按此加了 `baselines` 形参。

### 3) `note_sub_table_projector`（只加断言，不改逻辑）

`project_sub_tables` 按 `columns[].key` 取值，未声明的行键天然被丢弃。
本 spec 只**要求并守卫**这一点（Requirement 3.5），若实测发现 `_seg` 会漏进输出则改投影器显式过滤 `_` 前缀行键。

### 4) 生成器与守卫

```
backend/scripts/gen/gen_note_shared_table_segments.py   # --write / --check（drift）
backend/data/note_shared_table_segments.json            # 29 张表 + 段清单
backend/tests/test_note_shared_table_segments.py        # 切段纯函数 + drift + 反向自检
backend/tests/test_disclosure_row_level_merge.py        # 合并语义 + fail closed + 零回归
audit-platform/frontend/src/components/workpaper/__tests__/
    disclosureSharedTableRowScope.spec.ts               # 推共享表必带 _row_scope
```

### 5) E1 首个消费者

```
audit-platform/frontend/src/components/workpaper/composables/e1FxNoteSectionMap.ts
    E1_FX_NOTE_SECTION = { listed: '五、73', soe: '八、92' }
    E1_FX_TABLE = '外币货币性项目'
    E1_FX_OWNER_ROW_CODE = 'BS-002'
    buildE1FxColumns(): Record<string, ColumnDef[]>        // 4 列 flat，零入参
    buildE1FxSyncPayload(variant, wpId, applicableStandards, snapshot)
```

## Data Models

### 载荷侧（`sub_table_data` 内的元数据键）

```jsonc
{
  "外币货币性项目": [
    { "label": "货币资金",     "fc_amount": null,   "rate": null,   "rmb_amount": null },
    { "label": "其中：美元",   "fc_amount": 14000,  "rate": 7.1884, "rmb_amount": 100637.6 },
    { "label": "欧元",         "fc_amount": 2000,   "rate": 7.8592, "rmb_amount": 15718.4 }
  ],
  "_row_scope": { "外币货币性项目": { "owner_row_code": "BS-002" } },
  "_note_texts": [{ "section": "e1-fx", "title": "外币折算说明", "text": "…" }],
  "_removed_text_sections": []
}
```

### 落库侧（`disclosure_notes.table_data.sub_table_data`）

```jsonc
{
  "外币货币性项目": [
    { "label": "货币资金",   "_seg": "BS-002", "fc_amount": null, "rate": null, "rmb_amount": null },
    { "label": "其中：美元", "_seg": "BS-002", "fc_amount": 14000, "rate": 7.1884, "rmb_amount": 100637.6 },
    { "label": "欧元",       "_seg": "BS-002", "fc_amount": 2000,  "rate": 7.8592, "rmb_amount": 15718.4 },
    { "label": "应收账款",   "_seg": "BS-006", "fc_amount": null, "rate": null, "rmb_amount": null },
    { "label": "其中：美元", "_seg": "BS-006", "fc_amount": null, "rate": null, "rmb_amount": null },
    { "label": "短期借款",   "_seg": "BS-031", "fc_amount": null, "rate": null, "rmb_amount": null }
  ]
}
```

`_seg` 是**行内元数据键**（不是表键），故：
- 不进 `_sub_table_columns`（未声明列 → 投影器丢弃）
- 不影响 `_count_rows_synced`（它只跳过 `_` 前缀的**表**键）
- 不影响 `normalize_sub_table_data`（业务键行形态保持 `{key: list[dict]}`）

### 段清单（生成产物）

```jsonc
{
  "_source": "note_template_{listed,soe}.json",
  "generated_at": "…",
  "tables": [
    {
      "variant": "soe",
      "section_number": "八、92",
      "section_title": "外币货币性项目",
      "table_name": "外币货币性项目",
      "row_count": 25,
      "segments": [
        { "row_code": "BS-002", "label": "货币资金",   "start": 0,  "end": 5 },
        { "row_code": "BS-006", "label": "应收账款",   "start": 5,  "end": 10 },
        { "row_code": "BS-031", "label": "短期借款",   "start": 10, "end": 15 },
        { "row_code": "BS-061", "label": "长期借款",   "start": 15, "end": 20 },
        { "row_code": "BS-062", "label": "应付债券",   "start": 20, "end": 25 }
      ]
    }
  ]
}
```

## Correctness Properties

### Property 1: 无 `_row_scope` 时逐字节等价

对任意载荷，若 `sub_table_data` 不含 `_row_scope`，则合并后的 `table_data`
与改动前实现的输出**逐字节相同**（characterization 测试用 `json.dumps` 比对）。

**Validates: Requirements 1.2, 6.1**

### Property 2: 段外行不可变

行级合并后，落库行里所有 `_seg != owner_row_code` 的行**逐字段等于**合并前的对应行
（含顺序、含 `null` 与 `0` 的区别）。

**Validates: Requirements 3.1, 7.4**

### Property 3: 段内整段替换

段内结果 == 本次推送行（顺序保持），且段内行数允许 ≠ 模板段行数。
`result == baseline[:start] + incoming + baseline[end:]` 恒成立。

**Validates: Requirements 3.1, 3.2**

### Property 4: 段边界只由模板 `report_row_code` 决定

`split_segments` 对任意行集：段数 == 带 `report_row_code` 的行数；
段区间两两不重叠且并集覆盖「首个段首行到表尾」；每段 `start` 处的行带 `report_row_code`。

**Validates: Requirements 2.1, 2.5**

### Property 5: 解析失败 fail closed

当模板查不到表或查不到 `owner_row_code` 时，该表**不写入**、返回 `row_scope_unresolved`，
且既有落库数据**完全未变**。反向自检：把 fail closed 改成回退整表覆盖，Property 2 必须失败。

**Validates: Requirements 2.2**

### Property 6: 标签重复不串段

对「其中：美元 / 欧元 / 港币」在多段重复出现的真实模板行集，
行级合并**只改 owner 段内**的同名行；其他段的同名行值不变。

**Validates: Requirements 3.3**

### Property 7: `_seg` 戳完整且不泄漏

写入后每一行都带 `_seg`；`project_sub_tables` 的输出行**不含** `_seg`；
`_sub_table_columns` 不含 `_seg` 列；Word 导出表头不含 `_seg`。

**Validates: Requirements 3.4, 3.5**

### Property 8: 首次同步保留他段骨架

首次同步（落库无该表）后，表内行数 == 模板行数（除 owner 段行数变化外），
且他段标签**全部存在**、数值为空。

**Validates: Requirements 4.1, 4.4**

### Property 9: 已有数据不回退模板

当落库已有数据且他段已录值时，本次同步后他段的值**不被模板空值覆盖**。

**Validates: Requirements 4.2, 4.3**

### Property 10: 空推送恢复骨架而非删段

owner 推送 `[]` 时，段内行标签**保留**（回到模板骨架）、数值置空，段不消失；
表的总行数不减少（除 owner 段行数曾被扩展外）。

**Validates: Requirements 3.6**

### Property 11: `_note_texts` 按 section 合并

合并结果的 section 键集 == 既有键集 ∪ 推送键集 − `_removed_text_sections`；
同名 section 取推送值；未推送 section 值不变；段序稳定（既有序在前）。

**Validates: Requirements 5.1, 5.3, 5.5**

### Property 12: 无 `_note_texts` 推送不清空文本

载荷不含 `_note_texts` 时 `text_content` 保持不变（现状是置 `None`，属本 spec 修掉的缺陷）。
单 owner 场景（既有键集 ⊆ 推送键集）下合并 ≡ 整替换。

**Validates: Requirements 5.2, 5.4**

### Property 13: 两个写入口行为一致

`sync_from_workpaper` 与 `sync_from_html`（实际方法名）对同一载荷产出**相同**的
`sub_table_data` 与 `row_scoped_tables` / `row_scope_unresolved`。

⚠️ 比对范围**不含** `text_content` / `_sub_table_columns` 的全等：实测 `sync_from_html`
入口本就不调 `_extract_note_texts`（`_note_texts` 留在 `sub_table_data` 里当元数据键），
且表级是整替换而非浅合并 —— 两处均为**预存在分叉**，本 spec 只接行级分支，不动它们。

**Validates: Requirements 6.3**

### Property 14: 共享表清单与模板无漂移

`gen_note_shared_table_segments.py --check` 为 0 欠账；
清单表数 == 扫模板得到的多段表数（listed 23 / soe 6，共 29）；
反向自检：手改清单一处段区间必须被 `--check` 抓出。

**Validates: Requirements 8.1, 8.4**

### Property 15: 推共享表必带 `_row_scope`

前端扫全部 `build*SyncPayload`：凡推送表名落在共享表清单内的，
其载荷必须带 `_row_scope` 且 `owner_row_code` ∈ 该表段集合；未带即红。
反向自检：临时去掉 E1 的 `_row_scope` 声明，该守卫必须失败。

**Validates: Requirements 8.2, 8.3**

### Property 16: E1 外币段投影正确

E1 推送后，附注「外币货币性项目」的 `_column_groups == []`（4 列 flat）、
货币资金段各币种行值与底稿一致、他四段行未被改动、`_last_sync_sheet` 为半角括号 sheet 名。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 17: 写库不用 `type_coerce`

涉及 JSONB 写入的语句必须是 `CAST(:td AS jsonb)` + `json.dumps(..., ensure_ascii=False)`；
源码级断言 `type_coerce` 不出现（配 `stripComments()` 反向自检 —— 说明注释里会写这个反例）。

**Validates: Requirements 6.5**

### Property 18: 变体解析不按章节号推导

`resolve_template_variant` 只看 `current_standard` 前缀与 `source_template`；
对 20 个跨模板撞号章节（含 13 个标题不同的，如 `八、1` listed = 政府补助 / soe = 货币资金）
分别给 listed / soe 两种 `current_standard`，必须取到**各自**模板的行集。
反向自检：改成按章节号在两份模板里「谁有取谁」，则 `八、1` 必取错模板 → 本 Property 失败。

**Validates: Requirements 2.6, 2.7**

## Error Handling

**总原则：宁可不同步，绝不覆盖他人数据。** 附注是交付物，静默污染的代价远高于「这次没推上」。

| 情形 | 处理 | 理由 |
|------|------|------|
| `_row_scope` 形态非法（非 dict / 缺 `owner_row_code` / 表名以 `_` 开头） | 丢弃该条声明 + warning；该表**退回表级覆盖** | 声明本身无效 ≠ 共享表；退回原语义是既有行为，不引入新风险 |
| `_row_scope` 声明的表不在本次推送键里 | 忽略该条 + warning（R1.4） | 声明与数据必须配对，孤立声明无意义 |
| 模板查不到该表 / 查不到 `owner_row_code` | **跳过该表写入**，返回 `row_scope_unresolved: [表名]`，其余表照常写 | fail closed（R2.2 / Property 5）。回退整表覆盖会静默清掉他段 |
| 落库行有 `_seg` 但 owner 段**不连续**（历史脏数据） | 取**首个连续段**，并 warning 记录被忽略的离散行下标 | 不做全局重排（会改他段顺序）；脏数据由后续 data-hygiene 脚本收 |
| 落库行数 < 模板段 `end` | 段窗口按落库长度裁剪（R4.3） | 落库数据为准，避免 IndexError 与凭空补行 |
| 两个 `owner_row_code` 声明重叠区间 | 服务端按载荷执行 + warning；前端守卫在测试期拦（R2.4） | 服务端无法判断谁对；唯一性属 registry 级约束 |
| `_removed_text_sections` 与本次推送的 section 冲突 | **推送优先**，不删 | 同 `_drop_removed_tables` 的既有语义（Property 7 of 旧 spec） |
| DB 写入异常 | 事务回滚，异常上抛由既有 422/409 兜底 | 不新增错误码；`StandardMismatchError` 等既有守卫在写入前 |

**返回值扩展**（向后兼容，只加字段）。现状返回键实测恰好 8 个：
`success` / `section_id` / `synced_at` / `rows_synced` / `created` / `revived` /
`blocked_by_manual_override` / `texts_synced`
—— **`dropped_tables` 不在返回值里**（`_drop_removed_tables` 返回它但调用方只 `logger.info`）。

```python
{
  # … 现有 8 个键不变 …
  "row_scoped_tables": list[str],    # ★ 本次走行级合并的表
  "row_scope_unresolved": list[str], # ★ 段边界解析失败被跳过的表
}
```

`row_scope_unresolved` 必须进**返回值**而不只是日志 —— fail closed 是静默跳过，
调用方（前端自动同步）需要据此提示审计师「这张表没同步成功」，否则又是一个 dead path。
`dropped_tables` 是否顺带补进返回值由 Task 5 决定；补了要同步更新 characterization 的键集断言。

**可观测性**：行级合并每次写入记一条 `logger.info`，含
`section / table / owner_row_code / window=(start,end) / baseline_source=existing|template / rows_in / rows_out`
—— 这是排查「他段被动了」的唯一线索，不能省。

## Testing Strategy

**分层**：纯函数（切段 / 合并 / 文本合并）用密集单测 + PBT；服务层用 fake session 的
characterization 测试锁零回归；跨前后端用真实 DB 直跑 + 浏览器实测收口。

### 1. 纯函数单测（`test_note_shared_table_segments.py`）
- `split_segments`：真实模板行集（`五、73` 16 行 / `八、92` 25 行）逐段区间钉死
- **PBT**：随机行集（随机位置插 `report_row_code`）→ 段区间两两不重叠、并集连续、每段首带 code（Property 4）
- `stamp_baseline_rows`：`_seg` 向下传播正确、数值置空、标签保留（Property 8）
- **反向自检**：把切段改成「按标签分组」，Property 6（标签重复不串段）必须失败

### 2. 合并语义单测（`test_disclosure_row_level_merge.py`）
- Property 2/3/6/9/10 用真实模板行集构造，逐行断言
- Property 5 fail closed：构造不存在的 `owner_row_code`，断言既有数据 md5 不变
  + 反向自检（改成回退覆盖则 Property 2 红）
- Property 11/12 文本合并：多 owner 场景（G2/G3/K1 共用 `五、8` 的真实 section 键）
- **PBT**：随机 owner 段 + 随机推送行数 → Property 3 恒等式 + 段外不变

### 3. 零回归 characterization（`test_disclosure_sync_characterization.py`）
- 取现存 5~8 个真实载荷形态（D1 / D2 / H2 / K1 / N1），无 `_row_scope` 跑新旧两条路径，
  `json.dumps(table_data, sort_keys=True)` **逐字节比对**（Property 1）
- 既有 `test_wp_disclosure_sync*.py` 全套不改断言跑绿（R6.2 允许诚实改的仅 `text_content`
  保留语义 1~2 条，须在测试里写明「原断言锁的是本 spec 要修掉的缺陷」）

### 4. 两入口一致性（Property 13）
同一载荷分别经 `sync_from_workpaper` 与 `sync_from_html_disclosure`，
断言 `sub_table_data` / `_sub_table_columns` / `text_content` 三者相同

### 5. 投影与导出（Property 7）
- `project_sub_tables` 输出行不含 `_seg`；`_column_groups == []`（4 列 flat）
- `note_word_exporter` 表头不含 `_seg`

### 6. 生成器 drift（Property 14）
`gen_note_shared_table_segments.py --check` 0 欠账 + 表数 == 29（listed 23 / soe 6）
+ 反向自检（手改一处段区间必被抓）

### 7. 前端守卫（Property 15）
扫全部 `build*SyncPayload` 的推送表名 ∩ 共享表清单 → 必须带 `_row_scope`；
含反向自检（临时去掉 E1 声明必红）。守卫读源码前 `stripComments()`。

### 8. 真实 DB + 浏览器实测（Property 16）
- 真实 DB 直跑：E1 推送前后 SQL 逐行比对他四段（应收账款 / 短期借款 / 长期借款 / 应付债券）**逐字未变**
- chrome-devtools 实测：底稿录外币 → 不点按钮自动同步 → 附注 `八、92` 货币资金段出现数据、
  他段骨架完好、`_column_groups == []`
- **先快照后改、按 md5 逐字节复原**；若某字段无版本快照不可复原，如实记录（E1 spec 已有先例）

### 9. CI
新增 `disclosure-row-level-merge`（后端 + 生成器 drift）与
`disclosure-row-level-merge-frontend`（守卫 + E1 契约）两个 job
