# Design Document

## Overview

把国企↔上市附注转换从「改个 `template_type` + 全链重算」修到「章节映射真正落地 + 结果如实上报 + 可预览可回滚」。

三条主线：

1. **差异数据可信**：重生成 `note_soe_listed_diff.json` 去 mock，落盘与实时计算不一致时以实时为准并 WARNING；补 `format_diff` 的定位键。
2. **映射真正执行**：`execute_conversion` 的章节步骤改为真实改写 `section_id`/**`note_section`**，映射逻辑直接实现在生产路径（`_map_disclosure_notes`）；返回值区分 mapped/archived/created/skipped/failed。

🔴 **Task 10 裁决（2026-08-07 实测落地）= 删除 v2，不接线**。`convert_disclosure_notes_v2` / `preview_conversion_v2` 已从 `note_conversion_service.py` 删除（code-level hits=0）。裁决依据见下文「核心设计取舍」与 tasks.md 的 Task 10 实录。本文档下文凡提到「收编 v2 逻辑」的表述，均指**生产路径 `_map_disclosure_notes` 自身已实现该语义**，不是要去接那两个已删方法。

🔴 **列名事实（2026-08-07 实证，立项三处写错）**：`disclosure_notes` **无 `section_number` 列**（章节号是 **`note_section`**）、**无 `legacy_aliases` 列**（源侧 sid 落 `template_lineage.legacy_section_ids`）、`status` 枚举**无 `archived`**（归档靠 `is_deleted=true` + `template_lineage.archived_sections`）。本文档下文一律按真实列名书写。
3. **匹配安全**：措辞差异用**穷举配对清单**而非相似度算法，并显式登记禁止匹配对（合并 ↔ 母公司）。

核心设计取舍：

- **不引入相似度匹配**。实证「财务报表主要项目注释」↔「母公司财务报表主要项目注释」相似度 0.87，任何阈值都无法既救回 5 对措辞差异又拦住这一对 ⇒ 只能穷举。
- **不做整体事务回滚**。逐章节 savepoint + `failed` 桶，与平台既有 legacy 迁移脚本同款（一个章节失败不该让整次转换白做）。
- **v2 删除而非接线（🔴 2026-08-07 实测裁决，推翻立项时写的「优先接线」）**。立项时判断「v2 是唯一已实现的正确骨架」，实测**不成立** —— Task 8/9 落地后，生产路径 `_map_disclosure_notes` 已完整实现章节映射且**严格强于 v2**（别名桥接 / binding_id 前缀重写 / sid NULL 回填 / 章节号占用检查 / 逐章 savepoint，v2 五项全无），而 v2 自身另有 3 个缺陷（`format_diff` 无 `section_id` 键 ⇒ 计数恒 0；`field_mapping` 全 null ⇒ adapt 空转；**共有章节只计数、根本不改 `section_id`**）。此时接线只会造出**第二份真源**（同一语义两处实现，改一处另一处不动）。⇒ 删除 + 把它 21 条测试断言迁移到生产路径测试（Requirement 6.3 明令不得直接删测试）。

## Architecture

```
触发源
  ├─ POST /note-conversion/execute  (手工)
  └─ STANDARD_CHANGED 事件 → _on_standard_changed_notes  (自动)
                    │
                    ▼
        NoteConversionService.execute_conversion()
                    │
   ┌────────────────┼─────────────────────────────────────┐
   │ Step1 快照     │ Step2 template_type                  │
   │ ✅ 保持        │ ✅ 保持                              │
   ├────────────────┴─────────────────────────────────────┤
   │ Step3 报表行映射   → 按 §需求3 二选一：                 │
   │   有差异 → 按 CROSS_VARIANT_ROW_CODE_MAP 改写          │
   │   无差异 → 保留 return 0 但补实证依据 + 原因码           │
   ├──────────────────────────────────────────────────────┤
   │ Step4 章节映射（本 spec 核心）                          │
   │   → 生产路径自有实现（v2 已删，见 Overview 取舍）：      │
   │     common   → 改写 section_id + note_section          │
   │                + template_lineage.legacy_section_ids   │
   │                + binding_id 前缀处置（446 条带 binding）│
   │     src_only → 软删 + template_lineage.archived        │
   │     tgt_only → 建空章节                                │
   │     sid IS NULL → 回填或进 skipped（禁静默跳过）         │
   │     format_diff → adapt_table_data（修 section_id 键）  │
   │   逐章节 savepoint，失败进 failed 桶                    │
   ├──────────────────────────────────────────────────────┤
   │ Step5 公式引用映射 → ROW('X') 按同族清单改写             │
   ├──────────────────────────────────────────────────────┤
   │ Step6 全链刷新 ✅ 保持（fail-open）                     │
   └──────────────────────────────────────────────────────┘
                    │
                    ▼
   返回 {mapped, archived, created, skipped, failed, snapshot_id, reasons}
```

匹配层：

```
note_section_matcher.py（新建，穷举配对真源）
  SECTION_TITLE_ALIASES : tuple[AliasPair, ...]   显式配对（5 对已实证）
  FORBIDDEN_MATCH_PAIRS : tuple[Pair, ...]        禁止匹配（含合并↔母公司）
  normalize_for_match(title) -> str               仅去空白 + 登记虚词
  match_section(soe_title, listed_title) -> bool  精确 → 别名 → 否则 False
```

差异数据层：

```
note_template_diff.py（改造）
  load_diff_data()  → 读落盘 + 与 compute_diff_from_templates() 比对
                      不一致 → WARNING + 返回实时结果
  compute_diff_from_templates() → 补 section_id 键
  adapt_table_data() → field_mapping 非空时真正改结构（现状为空操作）
```

## Components and Interfaces

### 1. `note_section_matcher.py`（新建）

```python
@dataclass(frozen=True)
class AliasPair:
    soe_title: str
    listed_title: str
    evidence: str          # 源 docx 依据（两侧标题原文）

SECTION_TITLE_ALIASES: tuple[AliasPair, ...]      # 穷举，5 对起
FORBIDDEN_MATCH_PAIRS: tuple[tuple[str, str], ...]  # 必含 合并↔母公司

def normalize_for_match(title: str) -> str:
    """仅去空白；虚词差异由 ALIASES 显式配对承载，不在此做泛化替换。"""

def match_section(soe_title: str, listed_title: str) -> bool:
    """精确相等 → 别名配对 → False。命中 FORBIDDEN 直接 False。"""
```

设计要点：**不提供相似度接口**，避免后续会话「顺手」放宽阈值。守卫用反向自检钉死：把禁止对加入 ALIASES 必须打红。

### 2. `execute_conversion` 章节步骤改造

```python
async def _map_disclosure_notes(self, project_id, year, current_type, target_type) -> dict:
    """真正改写章节标识；返回分类计数而非存量行数。

    返回 {mapped, archived, created, format_adapted, user_edits_preserved,
          skipped, failed: list[dict]}
    """
```

- 逐章节 `async with self.db.begin_nested()`，异常进 `failed` 并继续
- 共有章节：改 `section_id` + **`note_section`**，源 sid 进 **`template_lineage.legacy_section_ids`**
- **改写前检查目标 sid 是否已存在**（防产生重复行，需求 2.6）
- **`binding_id` 前缀处置**（需求 2.7）：`table_data` 内 446 条绑定的 id 形态是「章节号.行标签.列键」，改 `note_section` 会让它们失联 ⇒ 同步改前缀，旧章节号记入 `template_lineage.legacy_note_sections`
- **`section_id IS NULL` 的存量行**（需求 2.8）：按 `note_section` + `section_title` 回填后参与映射，回填不出则进 `skipped` 并附原因码，禁静默跳过

### 3. 跨变体 row_code 映射清单 + 禁止改写清单

```python
# backend/app/services/note_conversion_row_codes.py（新建）

# 「同义两码」：同一 row_name 在 soe / listed 下挂不同 row_code ⇒ 需要改写
# 12 条实证结果（report_config 全表对账，soe -> listed；反向由反转生成）
CROSS_VARIANT_ROW_CODE_MAP: dict[str, str] = {
    "BS-111": "BS-077",   # 其中：优先股
    "BS-112": "BS-078",   # 永续债
    "CFS-038": "CFS-016", # 处置子公司及其他营业单位收到的现金净额
    "IS-055": "IS-033",   # （一）不能重分类进损益的其他综合收益
    "IS-056": "IS-034",   # 1. 重新计量设定受益计划变动额
    "IS-057": "IS-035",   # 2. 权益法下不能转损益的其他综合收益
    "IS-058": "IS-036",   # 3. 其他权益工具投资公允价值变动
    "IS-059": "IS-037",   # 4. 企业自身信用风险公允价值变动
    "IS-062": "IS-039",   # （二）将重分类进损益的其他综合收益
    "IS-066": "IS-043",   # 4. 其他债权投资信用减值准备
    "IS-068": "IS-045",   # 6. 外币财务报表折算差额
    "IS-071": "IS-048",   # 9. 其他
}

# 「一码两义」：同一 row_code 在 soe / listed 下是不同科目 ⇒ 禁止改写
# 值为 (listed 侧 row_name, soe 侧 row_name)，作为禁止理由的实测依据
ONE_CODE_TWO_MEANINGS_FORBIDDEN: dict[str, tuple[str, str]] = {
    "BS-016": ("一年内到期的非流动资产", "其中：应收股利"),
    "BS-058": ("其他流动负债", "交易性金融负债"),
    "BS-059": ("流动负债合计", "衍生金融负债"),
}

_EVIDENCE: dict[str, str]   # 每条附 report_config 对账依据（含 applicable_standard 四值实测）
```

**判据口径**：按 `report_config` 的 `applicable_standard` 四值（`soe_standalone` / `soe_consolidated` / `listed_standalone` / `listed_consolidated`）逐一比对，取「同 `row_name` 在两侧各只有 1 个 row_code 且不相等」者。全表 339 个 row_name / 201 个两侧都有 / 78 个存在跨变体差异 / 12 条是干净 1↔1。

**禁止清单的必要性**：`BS-013`↔`BS-016` 等三组曾被立项误判为同义两码，实测 `BS-016` 在 soe 侧是「其中：应收股利」、`BS-059` 在 listed 侧是「流动负债合计」——按误判改写会把明细行指向另一科目甚至合计行。守卫必须断言两清单互斥（键值集合无交集）+ 反向自检（把误判组加入映射表必红）。

### 4. 预览端点

```
GET /note-conversion/{project_id}/{year}/preview?target_type=listed
→ {mapped: int, archived: int, created: int, user_edits_preserved: int,
   forbidden_hits: list[str], details: [...]}
```

复用同一映射函数，`dry_run=True` 时不写入（实现上走 savepoint + 显式 rollback，保证与真实执行同路径，避免「预览与实际不一致」）。

## Data Models

### 无 DB schema 变更

本 spec 无迁移。所有改动落在既有列：`disclosure_notes.section_id` / **`note_section`** / `is_deleted` / `is_empty` / `status` / `template_lineage`。

### `disclosure_notes` 字段用法（2026-08-07 逐列实证）

| 字段 | 存在性 | 转换中的作用 |
|---|---|---|
| `section_id` | ✅ varchar，**大面积为 NULL** | 主定位键，共有章节需改写到目标变体 sid；NULL 行须回填或进 `skipped`（需求 2.8） |
| **`note_section`** | ✅ varchar | 展示用章节号（`八、9`，也可能是 md 截断值），需同步改写 |
| ~~`section_number`~~ | ❌ **不存在** | 立项写错，实为 `note_section` |
| ~~`legacy_aliases`~~ | ❌ **不存在** | 源侧 sid 改落 `template_lineage.legacy_section_ids` |
| `template_lineage` | ✅ jsonb，**全库 0 条有值** | 承载 `legacy_section_ids` / `archived_sections` / `legacy_note_sections`，等于全新字段 |
| `is_empty` | ✅ bool | 目标独有章节建为 `true`（需求 2.4） |
| `status` | ✅ enum，取值**仅 `draft` / `confirmed`** | 新建空章节置 `draft`；**无 `archived` 取值** ⇒ 归档只能靠 `is_deleted` |
| `is_deleted` | ✅ bool | 源独有章节软删 |
| `table_data._cell_modes` | ✅ jsonb 内 | `manual` 单元格必须保留，用于统计 `user_edits_preserved` |
| `table_data[..].binding_id` | ✅ **446/1030 条带** | 形态「章节号.行标签.列键」，改 `note_section` 会失联 ⇒ 需求 2.7 处置 |

### `note_soe_listed_diff.json` 结构调整

| 桶 | 现状 | 目标 |
|---|---|---|
| `is_mock` | `true` | `false` |
| `common_sections[]` | `{section_title, soe_section_id, listed_section_id}` | 不变 |
| `soe_only_sections[]` / `listed_only_sections[]` | `{section_id, title}` | 不变 |
| `format_diff_sections[]` | **无 `section_id`** | 补 `soe_section_id`/`listed_section_id` 已有，消费方改读对应侧（或补 `section_id`） |

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 落盘 diff 与实时计算不一致 | WARNING + 用实时结果 | stale 数据会漏/错映射章节 |
| 单章节映射失败 | 进 `failed` 桶，继续其余 | 一章失败不该让整次转换白做 |
| 目标 sid 已存在 | 跳过并进 `skipped`，记原因 | 防重复行 |
| 命中 `FORBIDDEN_MATCH_PAIRS` | 视为不匹配，计入 `forbidden_hits` 并在预览中展示 | 让审计师看到「这两个章节故意不配对」 |
| `field_mapping` 为 null | `adapt_table_data` 保持空操作 | 现状行为；非空时才改结构 |
| 源 docx 缺失 | 守卫失败并提示路径 | 判据失效必须打红 |
| 转换由事件自动触发且失败 | 记 ERROR + 快照 id | 事后可回滚 |

## Correctness Properties

### Property 1: 差异数据非 mock 且与实时一致

`note_soe_listed_diff.json` 的 `is_mock` 为 false；四个桶的条目集合与 `compute_diff_from_templates()` 相等。

**Validates: Requirements 1.1, 1.2**

### Property 2: 不一致时以实时为准

构造落盘与实时不一致的场景，断言 `load_diff_data()` 记 WARNING 且返回实时结果。

**Validates: Requirements 1.3**

### Property 3: format_diff 可定位

`format_diff_sections` 的每一条都能被消费方定位到既有 note（现状 `fd.get('section_id')` 恒 None 必须消除）。

**Validates: Requirements 1.4**

### Property 4: adapt_table_data 语义明确

`field_mapping` 为 null 时输入 == 输出；非空时结构确实改变。

**Validates: Requirements 1.5**

### Property 5: 共有章节 section_id 被真正改写

soe→listed 后，共有章节的 `section_id` 等于 `listed_section_id`；**`note_section`**（不是 `section_number` —— 该列不存在）同步改写。

**Validates: Requirements 2.1, 2.2**

### Property 6: 源侧 sid 进 template_lineage.legacy_section_ids

改写后源侧 sid 出现在 **`template_lineage.legacy_section_ids`** 中（`legacy_aliases` 列不存在，本 spec 无迁移故落 JSONB）。

**Validates: Requirements 2.2**

### Property 7: 源独有章节归档留痕

源独有章节 `is_deleted=true` 且 `template_lineage.archived_sections` 含该 sid 与 reason。

**Validates: Requirements 2.3**

### Property 8: 目标独有章节被创建

目标独有章节存在对应 note，`is_empty=true`、`status='draft'`。

**Validates: Requirements 2.4**

### Property 9: 人工编辑保留

共有章节中 `_cell_modes[i]=='manual'` 的单元格在转换后仍存在且值不变。

**Validates: Requirements 2.5**

### Property 10: 无重复行

转换后不存在同一 `(project_id, year, section_id)` 的多条未删除记录。

**Validates: Requirements 2.6**

### Property 11: 跨变体 row_code 清单有实证且恰为 12 条

`CROSS_VARIANT_ROW_CODE_MAP` 恰含需求 3.1 列出的 12 条；每条的两侧 row_code 都能在 `report_config` 查到，且**同一 `report_type` 下两侧 `row_name` 归一化后相等**（这是「同义两码」的定义）。

**Validates: Requirements 3.1, 3.2**

### Property 12: 公式引用按清单改写

含 `ROW('IS-055')` 的公式在 soe→listed 后变为 `ROW('IS-033')`；清单外 row_code（如 `ROW('BS-002')`）保持不变。

**注**：不得用 `ROW('BS-013')→ROW('BS-016')` 作断言 —— 实测该组是「一码两义」（`BS-016` 在 soe 侧是「其中：应收股利」），照此改写会指向另一科目。

**Validates: Requirements 3.3, 3.5**

### Property 13: 一码两义禁止改写

`ONE_CODE_TWO_MEANINGS_FORBIDDEN` 含 `BS-016`/`BS-058`/`BS-059` 三条且每条附两准则 `row_name` 实测理由；把 `BS-013→BS-016`（或另两组）任一条加入 `CROSS_VARIANT_ROW_CODE_MAP` 必须打红（反向自检）。

**Validates: Requirements 3.6, 3.7**

### Property 14: MAP 不含稳定码，且与被编造过的目标码无交集

`CROSS_VARIANT_ROW_CODE_MAP` 的键集与值集**均不含稳定码**（两侧 `row_name` 相同 ⇒ 压根不需改写），且与 `ONE_CODE_TWO_MEANINGS_FORBIDDEN`（3 个被编造过的目标码）无交集。

**🔴 不得断言「MAP 与全部 78 条一码两义无交集」** —— 12 条正确映射的 value **12/12 都是两侧异名**（码位偏移的必然结果），那样断言会把正确设计判红。真不变量是「key/value 不得是稳定码」，初稿三条错在 key 两侧同名。

**Validates: Requirements 3.8**

### Property 15: 免做结论有实证依据

若报表行映射保持 `return 0`，源码 docstring 必须含实证依据描述，且不含「For now」这类临时措辞。

**Validates: Requirements 3.4**

### Property 16: mapped_notes 反映真实映射数

返回的 `mapped` 等于实际改写章节数；构造「零共有章节」场景断言返回 0 而非存量行数。

**Validates: Requirements 4.1**

### Property 17: 返回结构分类齐备

返回含 `mapped`/`archived`/`created`/`skipped`/`failed` 五类。

**Validates: Requirements 4.2**

### Property 18: 单章节失败不阻断

注入一个章节写入异常，断言其余章节仍被处理且该章进 `failed`。

**Validates: Requirements 4.3**

### Property 19: 零值带原因码

`mapped_rows`/`updated_formulas` 为 0 时附 `no_mapping_needed` 或 `not_implemented`，两者可区分。

**Validates: Requirements 4.4**

### Property 20: 匹配不使用相似度算法

`note_section_matcher` 源码不含相似度/编辑距离实现（`SequenceMatcher`/`difflib`/`ratio` 等），匹配仅走精确 + 穷举别名。

**Validates: Requirements 5.1**

### Property 21: 别名清单覆盖已实证 5 对

`SECTION_TITLE_ALIASES` 含 5 对已实证配对，每条 `evidence` 非空。

**Validates: Requirements 5.2, 5.5**

### Property 22: 禁止匹配对生效

`match_section('财务报表主要项目注释', '母公司财务报表主要项目注释')` 返回 False。

**Validates: Requirements 5.3**

### Property 23: 禁止对反向自检

把禁止对加入 `SECTION_TITLE_ALIASES` 必须让守卫打红。

**Validates: Requirements 5.4**

### Property 24: 无孤儿转换函数

`backend/app/services/note_conversion_service.py` 中每个 `convert_*`/`_map_*` 方法都有非测试调用方。

🔴 **判据口径（2026-08-07 Task 10 实测，交接 Task 11 复核）**：`_map_*` 是**私有方法**，被同类内的公开入口 `execute_conversion` 调用即属「有消费方」，**同类内调用也算**。实测 `_map_report_rows` 与 `_map_disclosure_notes` 的 `external_non_test_callers` **均为 `[]`**、`self_calls=1`（调用点在 `execute_conversion`，L391），而 `execute_conversion` 自身有真实外部调用方（`routers/note_conversion.py` + `services/event_handlers/_impl.py`）⇒ 整条链有生产消费方，**不是孤儿**。

⇒ 故本 Property 的正确判据 = 「`self.<method>(` 在任一非测试文件里出现」（守卫 `test_method_has_non_test_caller` 的现行实现正是此口径，扫描面含服务文件自身），**不得**改成「必须有服务文件之外的调用方」—— 那样会把正常的私有子步骤全部误判成孤儿。守卫已加 `test_map_methods_are_called_by_public_entry`（把 `_map_*` 的调用点必须落在 `execute_conversion` 内钉死）+ `test_external_caller_baseline_is_registered`（登记 `external=[]` 这一实证，判据被改严即打红）。

**Validates: Requirements 6.1, 6.4**

### Property 25: v2 三缺陷已修（接线分支 —— 🔴 本 spec **未选此路**，不生效）

`format_adapted_count` 在有 format_diff 时可非 0；共有章节 `section_id` 被改写。

🔴 **2026-08-07 Task 10 裁决 = 删除不接线** ⇒ 本 Property **不作为验收判据**。其语义已由生产路径承接并被 Property 26 的迁移表覆盖：`format_adapted` 的空操作守卫由 `test_note_template_diff_integrity.py::TestConsumerCountsOnlyRealAdaptations` 钉死（变异检验 M2 打红 3 条），`section_id` 改写由 `test_common_section_data_preserved` 断言。保留本条仅为记录「若当初选接线该验什么」，不得据它新建 v2 相关实现。

**Validates: Requirements 6.2**

### Property 26: 测试不丢失（删除分支 —— ✅ **本 spec 生效判据**）

删除 v2 时，其测试的断言在生产路径测试中有对应覆盖。

🔴 **数量修正（2026-08-07 实测）**：被删的 v2 测试文件是**两个**不是一个 —— `backend/tests/services/test_note_conversion_v2.py`（10 tests / HEAD 8823 B）+ `backend/tests/services/test_note_conversion_pbt.py`（11 tests / HEAD 11438 B），合计 **21 个测试**（本文档原写「11 个」只数了其中一个文件）。迁移表真源 = `backend/tests/test_note_conversion_v2_removal.py` 的 `ASSERTION_MIGRATION`（22 行覆盖 21 个源测试名，`equivalent` 12 / `stronger` 10 / `obsolete_by_design` 0），配 `test_migration_table_covers_all_v2_tests`（与 HEAD 侧 AST 实测名集合逐条相等）+ `test_no_production_test_is_orphaned`（反向：26 个生产测试无一无人指向）双向锁死。

**Validates: Requirements 6.3**

### Property 27: variant_matrix 假 null 已补

已实证的 8 个「落点在别的章」科目不再为 null；补记值在对应模板中存在。

**Validates: Requirements 7.1, 7.2**

### Property 28: variant_matrix 修正为 additive

既有非 null 取值逐字不变。

**Validates: Requirements 7.3**

### Property 29: 真 null 附理由

仍为 null 的条目都有非空理由。

**Validates: Requirements 7.4**

### Property 30: 章号映射核查结论落地

`soe ch08→listed ch03` 的 10 条与 `soe ch12→listed ch05` 的 2 条各有三态结论（正常/已修正/已豁免）；主映射分布不变。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 31: 预览无写入且与实际一致

预览端点执行后 DB 无变化；预览返回的计数与随后真实执行的计数相等。

**Validates: Requirements 9.1, 9.2**

### Property 32: 回滚往返一致

soe→listed→rollback 后，`section_id`/`is_deleted`/`template_lineage` 回到初始状态。

**Validates: Requirements 9.3**

### Property 33: 自动触发留快照

`STANDARD_CHANGED` 路径记录 snapshot_id 到日志。

**Validates: Requirements 9.4**

### Property 34: 零回归

不涉及转换的附注生成/同步/导出行为逐字节不变。

**Validates: Requirements 10.2**

### Property 35: binding_id 不因章节号改写而失联

改写 `note_section` 后，该 note 的 `table_data` 内 `binding_id` 要么前缀已同步改写、要么旧章节号已记入 `template_lineage.legacy_note_sections` 供解析回退；不得留下前缀指向旧章节号而 lineage 无记录的绑定。

判据规模锚点：实测 1030 个未软删章节中 **446 条**带 `binding_id`，形态「章节号.行标签.列键」。

**Validates: Requirements 2.7**

### Property 36: section_id 为 NULL 的存量行有明确处置

`section_id IS NULL` 的 note 要么被回填 sid 后参与映射，要么计入 `skipped` 并附原因码；断言这批行**不会**在转换后仍停留在源变体的章节号上（静默跳过即打红）。

**Validates: Requirements 2.8**

### Property 37: 真实库验收不改动真实项目口径

验收脚本源码级断言：不得出现对 `Project.template_type` / `report_scope` / `applicable_standard_v2` 的写入；无合法验收对象时输出「无法验收」+ 显式 SKIP 标记，且不得用 fixture／新建测试项目冒充通过。

**Validates: Requirements 10.6, 10.7, 10.8**

## Testing Strategy

🔴 **本表的 Property 编号 2026-08-07 全量重映射过**：原表整体错位（把 matcher 写成 P18~21 而实为 P20~23、把 variant_matrix 写成 P25~27 而实为 P27~29…），且引用了 design 里**不存在的 P12b / P12c**。按错编号写守卫会覆盖错的 Property，与「照 tasks 的 `_Requirements` 干活会做错需求」同族。

| 层 | 文件 | 覆盖 |
|---|---|---|
| 差异数据 | `backend/tests/test_note_template_diff_integrity.py` | Property 1~4 |
| 章节映射 | `backend/tests/test_note_conversion_section_mapping.py` | Property 5~10、16~19、24~26、35、36 |
| row_code 映射 | `backend/tests/test_note_conversion_row_codes.py` | Property 11~15（连库读 `report_config` 对账） |
| 匹配器 | `backend/tests/test_note_section_matcher.py` | Property 20~23 |
| variant_matrix | 扩 `backend/tests/test_variant_matrix.py` + `test_variant_matrix_null_audit.py` | Property 27~29 |
| 章号核查 | `backend/tests/test_note_chapter_mapping_audit.py` | Property 30 |
| 预览与回滚 | `backend/tests/test_note_conversion_preview_rollback.py` | Property 31~33 |
| 零回归 | characterization | Property 34 |
| 真实库验收 | `backend/scripts/diagnose/verify_note_conversion_live.py`（默认 dry-run，`--apply` 后按快照复原） | Property 37；需求 10.4~10.8 |
| CI | 新增 job `note-conversion-correctness` | 全部后端守卫 |

**变异检验清单**（每条须实测打红后还原）：把 `is_mock` 改回 true / 删 `format_diff` 的定位键 / `_map_disclosure_notes` 改回 `count(*)` / 去掉 `legacy_aliases` 追加 / 把禁止匹配对加入 ALIASES / 在 matcher 里引入 `difflib` / 清空 `CROSS_VARIANT_ROW_CODE_MAP` / 让预览产生写入 / **把 `BS-013→BS-016` 加入 `CROSS_VARIANT_ROW_CODE_MAP`（一码两义反向自检，必红）** / **从 `ONE_CODE_TWO_MEANINGS_FORBIDDEN` 删掉 `BS-059`（禁止清单完整性，必红）** / 真实库验收脚本里改真实项目 `template_type`（必红）。
