# Design Document

## Overview

本 spec 收口附注模板的**列元数据缺失**与 `disclosure_notes.table_data` 的 **legacy 快照残留**两件互相绑定的欠账。

核心判断（全部由本会话探针实证，非估算）：

- **🔴🔴 列真源不是模板 JSON 自身，而是三分的（2026-08-05 用户澄清 + 全量实证）** —— 用户明确要求「附注列结构参照底稿的两张披露表、行走动态行」。全量扫 351 个源模板 / 2722 sheet 得 **170 张披露 sheet**，按此把 337 张 `columns==0` 表分三类，**判据真源各不相同、不可互相套用**：

  | 类别 | listed | soe | 列真源 | 归属 |
  |---|---|---|---|---|
  | ① 科目章节（有底稿披露 sheet 可参照） | 20（7 章） | 41（17 章） | **底稿披露 sheet**（openpyxl 直读 `backend/wp_templates/`） | 本 spec，按已有范式 |
  | ② 母公司章 | 57 | 36 | 母公司章 docx | **A spec，本 spec 排除** |
  | ③ 非科目章节（**无**披露 sheet） | 163（53 章） | 20（11 章） | 附注模板 docx（`docs/模版/`） | 本 spec，但**禁套披露表口径** |

  ③ 类是本 spec 立项初稿最大的误判来源：套期 16 / 关联交易 13 / 处置子公司 12 / 金融资产转移 12 / 风险管理 11 / 分部报告 5 等章节在 `backend/wp_templates/**` **压根没有对应披露 sheet**，按「参照披露表」补列等于自造。

- **🔴 用户要求的范式平台已建立且覆盖大半，本 spec 只补缺口不重造** —— 实测已有 **38 个后端结构守卫**（其中 **17 个 openpyxl 直读源 xlsx 做三向比对**：D1/D2/D4/E1/G5/G7/H2/H3/H5/H7/H8/H9-H10/I/J1-J2/K复杂/预付款项/受限资产）+ **40 个前端 `*NoteSubtableContract.spec.ts`** + **42 个 `fix_note_*_structure.py` 幂等脚本**，覆盖约 35 个循环。① 类真缺口只有 **18 章**（listed 4 + soe 14，见下表），不是 20+41 张表全新做。

- **不能先迁移** —— 892 张 legacy 快照表里只有 **340 张（38%）** 在模板中既能按名定位又有 `columns`；**216 张模板有表但 `columns==0`**、**336 张模板里找不到该表名**。对后两类执行迁移，读时投影会降级成 `_needs_columns`（只显示行名、丢列头），**比 legacy 快照更糟** —— 快照至少自带 `headers`。
- **表名正名必须早于列补齐** —— 336 张「模板无此表名」里，**116 个 section 是纯表名漂移**（快照表数 == 模板表数、快照名是表头首格泄漏如 `项  目`、模板已是正式业务名如 `交易性金融资产`）。这批只要建立 `legacy_aliases` 就能按序安全对齐；而列补齐规则按表名索引，名字没定死就无法索引。
- **既有资产可复用，不重写** —— `migrate_legacy_note_snapshots.py`（约 29.7 KB）已有 `build_note_plan` / `select_migratable` / `build_migrated_table_data` / `build_rollback_table_data` 四个纯函数与四类判定（`single_row` / `by_name` / `positional` / `manual`）、`--require-columns` 内容闸、per-note savepoint、`--rollback`。本 spec 只**扩展**它的对齐能力（alias 层），不重造迁移器。

### 事实基线（Wave 1 将冻结为 JSON，守卫据此打红）

**模板侧**（`backend/data/note_template_{listed,soe}.json`）：

| 指标 | listed | soe |
|---|---|---|
| section 总数 | 204 | 188 |
| table 总数 | 513 | 296 |
| `columns == 0` | **240（46%）** | **97（32%）** |
| `guidance` 为空 | 237 | 96 |
| 表名为空串 | **22** | 0 |
| 表名疑似表头泄漏（`项  目`/`类别`/`种  类`…） | **88** | 0 |
| 含重名表的 section | **19** | 1 |

`columns==0` 的章节分布 top：listed `十六、`**57**（母公司章）/ `三、在`16 / `三、套`16 / `十一、`16 / `十四、`15 / `五、7`13；soe `十二、`**36**（母公司章）/ `八、8`23 / `十一、`13 / `八、9`9。
→ **母公司章 93 张表（listed 57 + soe 36）归 A spec，本 spec 按 `section_id` 前缀排除**，实际作用域 = listed 183 + soe 61 = **244 张表**。

#### ① 类真缺口 = 18 章（科目章节且既有守卫未覆盖）

| 侧 | 章节 | 说明 |
|---|---|---|
| listed | 五、12 一年内到期的非流动资产 / 五、35 衍生金融负债 / 五、71 现金流量表补充资料 / 五、74 租赁 | 4 章 |
| soe | 八、8 应收资金集中管理款 / 八、13 一年内到期的非流动资产 / 八、45（1）一年内到期的长期借款 / 八、46（2）一年内到期的应付债券 / 八、51 优先股、永续债等金融工具 / 八、80 每股收益 / 八、81 现金流量表项目注释（9 表）/ 八、83 股份支付 / 八、84 债务重组 / 八、85 借款费用 / 八、87 租赁 / 八、89 终止经营 / 八、90 分部信息 / 八、91 合并现金流量表相关事项 | 14 章 |

其余 ① 类章节（listed 五、26 无形资产 / 五、28 商誉 / 五、31 其他非流动资产、soe 八、27 / 八、32 等）已被既有守卫覆盖，只是个别表漏补 —— 走对应 per-cycle 的既有 `fix_note_*_structure.py` 增量补，**不新建脚本**。

#### 🔴 动态行现状：平台无 `expandable` 语义

`row_type` 实测取值域仅 **5 个**：`data`（listed 2415 / soe 1536）、`total`（332 / 236）、`subtotal`（62 / 58）、`header_label`（62 / 28）、`unowned`（0 / 1，受限资产 spec 引入）。**没有表示「可扩位」的取值**。

而源披露 sheet 的可扩标记有 **6 种写法**（全量扫描）：`……` 116 处 / `预留` 36 / `可改名` 24 / `可无限量添加行` 23 / `......` 6 / `…` 5。附注 JSON 已 seed **90 个省略号行**（listed 59 / soe 31）+ 27/9 个带可扩标记的行，但前端**不认它们是可扩位** —— 它们被当 `data` 行渲染成空白披露数据行（memory 已记「预置空占位会被推成占位披露行」）。

平台既有的动态行能力散落在前端：`addRow` **865** 处 / `ElMessageBox.prompt` **443** 处 / `dynamicAdjudicationRows` 共享件 **6** 处 / `blankRows(` **3** 处。→ 本 spec 只做**模板侧标记这一层**（新增第 6 个取值 `expandable` + 清理误 seed 的占位行），UI 接线归各 per-cycle spec。

**库侧**（真实库，5 个项目）：

| 指标 | 值 |
|---|---|
| `disclosure_notes` 有效行 | 1030 |
| 已是 `sub_table_data` 形态 | 191 |
| **legacy 快照** | **496**（listed 92 / soe 404） |
| `_source = workpaper` | 194 |
| 曾同步过（`last_sync_at` 非空） | 66 |
| legacy 中有 `_tables` | 391 |
| legacy 中仅顶层 `rows` | 105 |
| legacy 快照内的表总数 | **892** |
| 快照表自身也无 `columns` | listed 50/50、soe 674/842 |

**join 判据**（legacy 快照 × 模板）：

| 分类 | 表数 | section 数 |
|---|---|---|
| 可迁移（名字命中 + 模板有 columns） | **340** | — |
| 模板有该表但 `columns==0` | **216** | — |
| 模板中找不到该表名 | **336** | — |
| section 级：全部表可迁移 | — | **120** |
| section 级：被阻塞 | — | **271** |
| 含重名表的 section（按名建键必丢表） | — | **54** |
| section 在模板中完全找不到（变体/编号漂移） | — | **1** |
| 表名 unmatched 的 section | — | 154 |
| └ 其中表数相同且全名不同（**纯名漂移**，可按序对齐） | — | **116** |

## Architecture

### 顺序依赖（不可调换）

```
Wave 1  事实真源 + 守卫（守卫必须先对当前数据打红）
   │
   ├─ 探针 extract_note_columns_facts.py  →  backend/data/note_columns_facts.json
   └─ 守卫 test_note_template_columns_coverage.py（预期 FAIL）
   │
Wave 2  表名正名与去重（必须早于 Wave 3）
   │      规则按表名索引 ⇒ 名字不定死无法索引
   │      产出 legacy_aliases（Wave 4 的对齐依据）
   │
Wave 3  columns / guidance 批量补齐（分 4 批）
   │      判据真源 = 快照 headers ∪ 同步载荷 columns ∪ 源 docx
   │
Wave 4  legacy 迁移（扩既有迁移器 + alias 对齐）
   │      必须在 Wave 3 之后：require_columns 闸此时才放行
   │
Wave 5  CI + 真实库验收 + 收口
```

### 与既有资产的关系

| 资产 | 本 spec 的动作 |
|---|---|
| `backend/scripts/fix/migrate_legacy_note_snapshots.py` | **扩展**：`build_note_plan` 增 alias 解析（新 kind `by_alias`），不改既有四类判定的行为 |
| `backend/app/services/note_template_reflow_service.py` | **只读复用** `_load_template_sections` / `_pick_template_section` |
| `backend/app/services/note_sub_table_projector.py` | **不改**（`normalize_sub_table_data` 逆投影是既有规范） |
| `backend/scripts/fix/_note_structure_kit.py` | **复用** `flat_columns` / `two_period_columns` / `rule` / `run_section` / `apply_plan` / `build_cli` |
| `backend/scripts/diagnose/diagnose_note_template_drift.py` | 只读参考，不改 |
| `_infer_groups_from_headers` | **不改**（补齐 columns 后自然不再触发） |

### 新增件

```
backend/scripts/diagnose/extract_note_columns_facts.py     只读探针 → facts JSON
backend/data/note_columns_facts.json                        事实真源（守卫读它）
backend/scripts/fix/fix_note_table_names.py                 Wave 2：正名 + 去重 + alias
backend/scripts/fix/fix_note_columns_batch{1..4}.py          Wave 3：分批补 columns/guidance
backend/scripts/fix/fix_note_row_type_expandable.py         Wave 3：省略号行 → row_type=expandable
backend/tests/test_note_template_columns_coverage.py        守卫：列覆盖 + 表名唯一 + alias 完备
backend/tests/test_legacy_snapshot_alias_alignment.py       守卫：alias 对齐纯函数
backend/scripts/diagnose/verify_legacy_migration_live.py    Wave 5：真实库验收（默认 dry-run）
```

## Components and Interfaces

### 1. `extract_note_columns_facts.py`（只读探针）

```python
def scan_templates() -> dict:
    """扫两份模板 JSON，产出 columns/guidance/表名 三维缺口清单。
    返回 {variant: {sections, tables, cols0, no_guidance, leak, empty,
                    dup_sections, by_section: {...}, parent_chapter_excluded: N}}
    """

def scan_legacy_notes(db) -> dict:
    """连库扫 legacy 快照，逐表 join 模板，产出四分类计数与逐条明细。"""

def is_parent_chapter(section: dict) -> bool:
    """按 section_id 前缀判定母公司章（chapter-16-* / chapter-12-*），
    这些表归 A spec，本 spec 排除并计数上报。"""
```

CLI：`--variant {listed,soe,both}` / `--db`（不给则只扫模板） / `--out <path>` / `--check`。
**必须自己写盘 UTF-8**（PowerShell `>` 会腌坏中文）。

### 2. `fix_note_table_names.py`（Wave 2）

```python
NAME_LEAK_TOKENS = frozenset({"项目","序号","名称","类别","组合","种类",
                              "存货种类","被投资单位","债务人名称","承兑人名称"})

def is_leaked_name(name: str, headers: list) -> bool:
    """表名 == headers[0]，或去空白后落在 NAME_LEAK_TOKENS 内 → 泄漏名。
    与既有 migrate_legacy_note_snapshots._name_is_meaningful 同口径（守卫交叉锁死）。"""

def resolve_unique_name(section: dict, idx: int, proposed: str) -> str:
    """正名策略（顺序即优先级）：
    1) 源 docx / 同步载荷已有正式表名 → 用它
    2) section_title + 序号后缀 `{科目名}（表N）`
    3) 重名/空名兜底 `{科目名}（表N）`
    结果必须在本 section 内唯一。"""
```

**唯一动作是改 `tables[].name` 并写 `tables[].legacy_aliases: [旧名...]`**；
`rows` 一律 `None`（不动行集）。已有 `legacy_aliases` 时**追加去重**，不覆盖。

### 3. `fix_note_columns_batch*.py`（Wave 3）

四批按章节族切分，各自 `--dry-run` / `--check` / `--apply`：

| 批 | 作用域 | 表数（约） |
|---|---|---|
| 1 | soe `八、*`（金额类主表，判据最硬） | 40 |
| 2 | listed `五、*` + `三、*`（科目注释） | 90 |
| 3 | listed `十一、` `十四、` + soe `十一、`（关联方/日后事项） | 44 |
| 4 | 其余（`三、套`/`三、在`/`九、`等） | 70 |

列判据取值优先级（每条变更必须在脚本内标 `source_ref`）：

1. **该表既有同步载荷的 `columns`**（`*NoteSectionMap.ts` 已声明的，逐字镜像）
2. **快照 `headers`**（真实项目里正在显示的列头）
3. **源 docx 表头**（A spec 的 `extract_parent_note_facts.py` 同款 python-docx 直读）

三者冲突时以源 docx 为裁决者，并在脚本内写明分歧。

**`flat` / `group` 必须显式表态**：单行表头一律 `flat: true`（否则 `_infer_groups_from_headers` 会凭空推出父表头）；两级表头写 `group`。

### 4. 迁移器扩展（Wave 4）

在 `migrate_legacy_note_snapshots.py` 内新增：

```python
def resolve_by_alias(legacy_names: list[str],
                     tpl_tables: list[dict]) -> list[str] | None:
    """纯函数：用模板 legacy_aliases 把快照表名映射到当前表名。
    返回与 legacy_names 等长的当前表名列表；任一项无法唯一确定 → None。
    """

# build_note_plan 内新增 kind = "by_alias"，插在 by_name 之后、positional 之前
ALWAYS_MIGRATABLE_KINDS = ("single_row", "by_name", "by_alias")
```

`by_alias` 的安全前提三条（缺一即退回 `positional`/`manual`）：
① 每个快照表名恰好命中一个模板表的 alias；② 映射后无重名；③ 快照表数 == 模板表数。

**既有 `positional` 仍需 `--include-positional` 显式 opt-in，不改。**

### 5. `verify_legacy_migration_live.py`（Wave 5）

默认 dry-run；`--apply` 真跑并按快照自动复原。逐项断言：
① 迁移后 `project_sub_tables()` 三消费方（前端投影 / Word 导出 / 校对）不出现 `_needs_columns`；
② 行数守恒（扣除 `header_label` 假行与顶层 `rows` 冗余副本）；
③ `_legacy_backup` 存在且 `build_rollback_table_data` 往返无损；
④ 未迁移章节逐字节不变。

## Data Models

### `backend/data/note_columns_facts.json`

```jsonc
{
  "generated_at": "2026-08-05T...",
  "templates": {
    "listed": {
      "sections": 204, "tables": 513,
      "cols0": 240, "cols0_in_scope": 183, "cols0_parent_chapter": 57,
      "no_guidance": 237, "leak": 88, "empty": 22, "dup_sections": 19,
      "by_section": { "五、7": { "tables": 13, "cols0": 13, "leak": 2 } }
    },
    "soe": { "...": "同构" }
  },
  "legacy": {
    "sections": 496, "tables": 892,
    "tbl_migratable": 340, "tbl_tpl_no_columns": 216, "tbl_not_in_tpl": 336,
    "rows_only_sections": 105,
    "sections_all_migratable": 120, "sections_blocked": 271,
    "dup_name_sections": 54, "section_not_in_template": 1,
    "pure_name_drift_sections": 116,
    "details": [ { "variant": "soe", "note_section": "八、2",
                   "snap_names": ["项  目"], "tpl_names": ["交易性金融资产"],
                   "verdict": "pure_name_drift" } ]
  }
}
```

### 模板 `tables[]` 的新增字段

```jsonc
{
  "name": "交易性金融资产",
  "legacy_aliases": ["项  目"],          // 新增：Wave 2 写入，只增不删
  "columns": [ { "key": "项目", "label": "项目", "flat": true }, ... ],
  "guidance": "...",
  "_aligned_by": "note-template-columns-and-legacy-snapshot-closure"
}
```

### 迁移备份位置

沿用既有约定：`table_data._template_lineage._legacy_backup`
（**不写 `template_lineage` 列** —— 该列已被 `group_note_baseline_service` 当 list、`note_auto_trim` 当 dict 使用，会冲突）。

## Correctness Properties

### Property 1: 事实探针的模板计数与真实文件一致
`scan_templates()` 输出的 `tables` / `cols0` / `leak` / `empty` / `dup_sections` 必须等于对两份模板 JSON 独立重算的结果，且 listed `tables==513`、soe `tables==296`。
**Validates: Requirements 1.1, 1.2**

### Property 2: 母公司章排除且计数上报
`cols0_in_scope + cols0_parent_chapter == cols0`，且 `cols0_parent_chapter` 为 listed 57 / soe 36；作用域内不得出现任何 `section_id` 以母公司章前缀开头的表。
**Validates: Requirements 1.3, 10.2**

### Property 3: 列覆盖守卫在 Wave 3 之前必须打红
守卫对当前模板 JSON 运行时，作用域内 `columns==0` 的表数必须 > 0 并逐条列出；只有该断言先红过，才能证明后续变绿不是空转。
**Validates: Requirements 1.4, 2.1**

### Property 4: 泄漏名判据与既有迁移器同口径
`fix_note_table_names.is_leaked_name` 对任意 `(name, headers)` 的判定，必须与 `migrate_legacy_note_snapshots._name_is_meaningful` 取反后逐例相等（同一组样本参数化），防两处判据漂移。
**Validates: Requirements 3.1, 3.5**

### Property 5: 正名后 section 内表名唯一
任一 section 的 `tables[].name` 去重后长度 == 表数，且无空串、无落在 `NAME_LEAK_TOKENS` 内的名字。
**Validates: Requirements 3.2, 3.3**

### Property 6: 正名只改名不动行
`fix_note_table_names` 的 plan 中每条变更只允许触及 `name` / `legacy_aliases` / `_aligned_by`；`rows` / `headers` / `columns` 的前后值必须逐字节相等。
**Validates: Requirements 3.4**

### Property 7: `legacy_aliases` 只增不删且覆盖全部旧名
正名后，每个被改名的表的 `legacy_aliases` 必须包含其改名前的名字；已有 alias 项一个不少。
**Validates: Requirements 3.6, 6.2**

### Property 8: alias 在 section 内不与任何当前表名冲突
任一 section 内，所有表的 `legacy_aliases` 并集与所有 `name` 集合的交集为空（否则迁移时一个旧名同时命中两张表）。
**Validates: Requirements 3.7, 6.3**

### Property 9: 补齐后作用域内 `columns` 覆盖率 100%
Wave 3 全部批次 `--check` 归零后，作用域内（排除母公司章）不得有任何 `columns == 0` 或 `columns` 长度与 `headers` 长度不等的表。
**Validates: Requirements 2.1, 2.2**

### Property 10: 每列必须显式表态 `flat` 或 `group`
新补的每个 `ColumnDef` 至少声明 `flat: true` 或 `group: "..."` 其一；单行表头表不得声明 `group`，两级表头表不得整表 `flat`。
**Validates: Requirements 2.3**

### Property 11: 补列不得改变既有同步载荷的键
对已有 `*NoteSectionMap.ts` 声明 columns 的表，模板新补的 `columns[].key` 必须与载荷逐字相等（否则同步来的行找不到列落点）。
**Validates: Requirements 2.4, 2.7**

### Property 12: 每条列变更带 `source_ref`
Wave 3 各脚本的每条 rule 必须携带判据出处（`load` / `snapshot_headers` / `source_docx` 之一 + 定位信息），`--check` 输出可逐条追溯。
**Validates: Requirements 2.5**

### Property 13: `guidance` 为纯文本
新补的 `guidance` 不得含 markdown 粗体 `**`、不得含 HTML 标签；内容只许取源模板红字 / 附注模版括注 / 准则条款，或以「勾稽：」前缀的工具提示。
**Validates: Requirements 2.6**

### Property 14: 表头纯文本
被触及的表其 `headers` 与 `columns[].label` / `group` 不得含 `<br/>` 等 HTML（平台已有 133 处欠账，本 spec 至少不新增）。
**Validates: Requirements 2.8**

### Property 15: 迁移前必须过 `require_columns` 闸
`select_migratable(..., require_columns=True)` 选中的每个 plan，其所有 `TablePlan.columns_from_template` 必须为 True；该闸默认开启，关闭需显式 flag。
**Validates: Requirements 4.1, 4.2**

### Property 16: `by_alias` 的三条安全前提
`resolve_by_alias` 仅在「每个旧名恰好命中一个 alias」「映射后无重名」「表数相等」三条同时成立时返回非 None；任一不成立返 None（配反向自检逐条构造反例）。
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 17: `by_alias` 覆盖纯名漂移集合
对 facts JSON 里 116 个 `pure_name_drift` section，Wave 2 完成后 `build_note_plan` 必须全部判为 `by_alias`（不再落 `positional` / `manual`）。
**Validates: Requirements 5.4**

### Property 18: `positional` 仍需显式 opt-in
`allowed_kinds(include_positional=False)` 不得含 `positional`；`ALWAYS_MIGRATABLE_KINDS` 只允许 `single_row` / `by_name` / `by_alias`。
**Validates: Requirements 5.5, 4.3**

### Property 19: 既有四类判定行为零回归
对同一组输入，扩展后的 `build_note_plan` 在不涉及 alias 的样本上产出的 `kind` / `tables` / `reason` 与扩展前逐字段相等（characterization 测试）。
**Validates: Requirements 5.6, 9.1**

### Property 20: 重名 section 一律不自动迁移
54 个含重名表的 section 在 Wave 2 正名之前必须判 `manual`；正名之后若仍有重名则继续 `manual`（按名建键会丢整表）。
**Validates: Requirements 4.4, 3.2**

### Property 21: 行数守恒
迁移后 `sum(len(rows) for 各子表)` == 迁移前 `_tables` 行数总和 − 被剥离的 `header_label` 假行数；仅顶层 `rows` 的章节按单表守恒。
**Validates: Requirements 4.5**

### Property 22: 顶层 `rows` 与 `_tables[0].rows` 的冗余判定
当两者逐字节相同时判为 legacy 冗余副本、丢弃顶层 `rows` 合法；不同时必须判 `manual` 并报告，不得静默取其一。
**Validates: Requirements 4.6**

### Property 23: 备份与回滚往返无损
迁移写入的 `_template_lineage._legacy_backup` 经 `build_rollback_table_data` 还原后，与迁移前 `table_data` 逐字节相等；备份不得写入 `template_lineage` 列。
**Validates: Requirements 6.4, 6.5**

### Property 24: per-note 事务隔离
迁移在 `--apply` 下对每个 note 使用 savepoint + per-note `try/except`；任一条失败时该条零写入且不影响其余条，最外层一次 commit。
**Validates: Requirements 6.1, 6.6**

### Property 25: 迁移不改变未选中章节
`--apply` 前后，未被 `select_migratable` 选中的 note 其 `table_data` 逐字节相等（真实库验收脚本按快照比对）。
**Validates: Requirements 4.7, 8.3**

### Property 26: 三消费方不降级
迁移后 `note_sub_table_projector.project_sub_tables()` 对每个迁移章节返回的每张表都带非空 `_sub_table_columns`，不出现 `_needs_columns` 标记；Word 导出与「校对附注」读到同构列。
**Validates: Requirements 7.1, 7.2, 7.3**

### Property 27: `_column_groups` 不凭空产生
迁移后声明 `flat` 的表其 `_column_groups == []`；声明 `group` 的表其 `_column_groups` 与声明逐项相等；不得出现由 `_infer_groups_from_headers` 前缀推断产生的父表头。
**Validates: Requirements 7.4, 10.6**

### Property 28: 幂等
Wave 2/3 各脚本第二次 `--apply` 的 plan 为空、`--check` 归零；迁移器对已迁移章节（`_already_migrated`）跳过不重写。
**Validates: Requirements 9.2, 9.3**

### Property 29: 范围边界
本 spec 的全部脚本与守卫不得引用 `note_conversion_service` / `note_template_diff` / `note_soe_listed_diff.json`（B spec 范围），不得改动任何项目的 `template_type` / `applicable_standard_v2`，不得新增或翻转灰度开关。
**Validates: Requirements 10.3, 10.4, 10.5**

### Property 30: 真实库验收如实报告
`verify_legacy_migration_live.py` 在库中缺少可验收样本（如某类别 0 条）时必须明确报告「无法验收」及原因，不得用 fixture 或合成数据冒充通过。
**Validates: Requirements 8.1, 8.2, 8.4**

### Property 31: 列真源按章节三分且互斥
每张待补列的表必须被归入 ① 科目章节（有底稿披露 sheet）/ ② 母公司章（A spec 排除）/ ③ 非科目章节（无披露 sheet）恰好一类，三类计数之和等于全库 `columns==0` 表数（337）。① 类的 `source_ref` 必须指向 `backend/wp_templates/**` 的 xlsx 单元格；③ 类的 `source_ref` 必须指向 `docs/模版/` 的 docx；**③ 类出现 xlsx 型 `source_ref` 即打红**（等于给无披露 sheet 的章节套用了披露表列结构 = 自造）。
**Validates: Requirements 2.1, 2.2, 2.3, 10.8**

### Property 32: ① 类必须复用既有 openpyxl 三向比对范式
① 类的每个循环若已有 per-cycle 结构守卫（38 个后端守卫之一）则**不得**由本 spec 的批量脚本改动该章节；本 spec 只处理「守卫未覆盖」的 18 章（listed 4 / soe 14）。守卫断言：批量脚本的作用域章节集合 ∩ 既有 per-cycle 守卫覆盖的章节集合 == ∅。
**Validates: Requirements 2.4, 2.5, 10.7**

### Property 33: `row_type` 取值域恰为六个且 `expandable` 零可见内容
`row_type` 全库取值恰为 `{data, total, subtotal, header_label, unowned, expandable}`；出现第七个取值即打红。`expandable` 行在 `project_sub_tables()` 投影与 Word 导出中均不产生可见数据行、不参与任何合计；行为与 `header_label` 等价。
**Validates: Requirements 11.1, 11.2, 11.4, 11.6**

### Property 34: 可扩标记词表非空且每词在源真源命中
可扩标记词表 `{……, …, ......, 可无限量添加行, 预留, 可改名}` 六个词，每个词必须在 `backend/wp_templates/**` 的披露 sheet 中命中 ≥1 次（实测 116/5/6/23/36/24），命中为 0 即说明词表失效或源模板变更，守卫打红。`expandable` 改标只针对 JSON 里**已存在**的省略号行（listed 59 / soe 31），不得凭空插行。
**Validates: Requirements 11.3, 11.6, 11.7**

> **🔴 Property 33 的前提修正（2026-08-08 实证）**：Property 33 原文写「行为与 `header_label` 等价」，
> 实测 **`note_word_exporter._render_table` 完全不读 `row_type`**，把 `rows` 全部渲染成可见行
> ⇒ `header_label` 在 Word 导出侧**并不是**零可见内容。故 `expandable` 的零可见必须**显式实现**
> （在 `_render_table` 加按 `row_type` 的跳过分支），不能靠「照 header_label 那样」。
> 又因 Requirement 10.9 禁止改动既有五个取值的语义，该跳过分支**只对 `expandable` 生效**，
> `header_label` 的渲染行为逐字不变（它的假行由 Requirement 12 删除解决，不由渲染层过滤解决）。
>
> **词表顺序即匹配优先级**：`……` 含 `…`、`......` 含 `...` ⇒ 长串必须先匹配，
> 否则 116 处 `……` 会被 `…` 抢走、统计与改标全部错位（守卫有一条反向自检钉死该顺序）。

### Property 35: 裸表名只标题化不删除，且判据与后端同口径
`text_sections` 里「段落文字 == 某张表的 `name` 且 `is_title_paragraph` 为 False」的段落，
执行后必须全部变为以 `#### ` 开头；段落总数前后相等（**只加前缀不删段**）。
判定必须复用 `_note_structure_kit.find_bare_table_name_paragraphs` /
`is_title_paragraph`（后者与 `disclosure_engine._is_table_title_paragraph` 同口径），
守卫另有一条断言钉死「带 `（N）` / `N.` 编号的段落本就被判为标题、不得被重复加前缀」。
**Validates: Requirements 12.1, 12.2**

### Property 36: `header_label` 假行删除 fail-closed 且不吃可扩位
删除的每一行必须可由该表 `headers` 证明为表头文字残留（归一后与任一 header 相等 **或** label 含 HTML 标签）；
无法证明的一律跳过并进「无法证明」清单。
`label` 命中 Requirement 11.1 词表的行**永不删除**（归 Property 33 标 `expandable`），
两条处置的作用行集合交集必须为空。
反向自检：构造一个 label 与 headers 全不相同、也不含 HTML 的 `header_label` 行，脚本必须跳过它。
**Validates: Requirements 12.3, 12.4**

### Property 37: 删行后派生段清单必须重生成且共享表段语义不变
若删行触及「多段共享表」（同表 `rows` 上出现 ≥2 个不同 `report_row_code`），
则 `backend/data/note_shared_table_segments.json` 必须重生成，且重生成前后
每张共享表的 **段代码序列**（`[segment.row_code]`）逐项相等 —— 允许行序整体前移，
不允许段归属发生变化。守卫断言该清单与当前模板重算结果一致（stale 检测）。
**Validates: Requirements 12.5, 12.6, 12.7**

### Property 38: `row_type` 判据单一真源，禁任何写者硬编码 `data`
`row_type` 有**多个写者**：本 spec 的 `fix_note_expandable_rows.py`、共享行构造器
`scripts/fix/_note_structure_kit.data_row()`、以及若干 per-cycle 幂等脚本
（`fix_note_h_policy_chapter_structure.py` 的 `ADD_TABLES` 走 `tables[0] != want`
**深比较整表**后整表重写 rows）。判据分散在各脚本 ⇒ 写者互相翻转：实测 soe
`四、生物资产` 的 4 行 `……` 被翻回 `data`（2026-08-08，标记落地后被下一次
per-cycle `--apply` 覆盖）。

故判据本体收敛到 `backend/app/services/note_expandable_markers.py`（纯函数、
stdlib-only、无 IO），并规定：

1. 词表（`MARKERS` / `LABEL_MARKERS` / `LABEL_MARKER_EXCLUDED`）与匹配函数
   （`match_marker` / `match_label_marker` / `label_candidates` / `normalize_label` /
   `row_type_for_label` / `is_zero_visible_row`）**只在该 service 声明一份**；
   生成器、幂等脚本、投影器、Word 导出、守卫一律 import 它（投影器可 re-export
   以保住既有 import 路径）。
2. **任何** `backend/scripts/fix/**` 脚本不得构造「label 是可扩位标记 + `row_type`
   硬编码 `"data"`」的行 —— 判据用 **AST**：`ast.Dict` 同时含
   `"label": <marker 常量>` 与 `"row_type": "data"`；或本地行构造 helper
   （`def x(label…) -> {..., "row_type": "data"}`）被 marker 字面量调用。
   「检测/删除用的 marker 集合」（`ast.Set` / `in {...}`）与「打印截断的 `…`」
   （`JoinedStr` 内）**不算冲突**，守卫必须能区分（否则会打红 7 个合法脚本）。
3. 冲突消解的验收判据 = **两个写者的 `--check` 同时为 0 欠账**：
   `fix_note_expandable_rows.py --check` 与 `fix_note_h_policy_chapter_structure.py --check`。

**Validates: Requirements 11.1, 11.2, 12.1**

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 模板 JSON 里 section 在库中找不到（1 条） | 记入 facts，判 `manual`，不迁移 | 变体/编号漂移属 A/B 范围 |
| 快照表数 ≠ 模板表数且名字对不上 | `manual` + 报告 | 无法安全对齐，宁缺勿造 |
| alias 命中多个模板表 | `resolve_by_alias` 返 None → 退回 `positional`/`manual` | 一名多表会写错落点 |
| 迁移写库单条失败 | savepoint 回滚该条，记 failures，继续 | 避免部分状态 |
| `--apply` 被中断 | 已提交的部分保留；判成败查数据不看退出码 | 平台既有教训 |
| 补列时载荷与快照 headers 冲突 | 以源 docx 裁决，脚本内写明分歧 | 交付物以源模板为准 |
| 库中无 consolidated 项目 / 无某类样本 | 如实报告无法验收 | 禁 fixture 冒充 |
| 探针脚本自身字段名错 | 全错（判据违规数 == 组合总数）几乎必是脚本 bug | 平台既有教训 |

## Testing Strategy

### 守卫（不连库，可进 CI）

- `test_note_template_columns_coverage.py`
  - Property 1/2/3/5/9/10/11/12/13/14/28/29
  - 读 facts JSON + 两份模板 JSON 交叉比对
  - **反向自检**：构造一个 `columns==0` 的替身 section，断言守卫必红；把母公司章前缀改掉，断言排除计数变化
- `test_legacy_snapshot_alias_alignment.py`
  - Property 4/6/7/8/16/17/18/19/20/22
  - `resolve_by_alias` 纯函数参数化 + 三条安全前提各构造反例
  - **characterization**：扩展前后 `build_note_plan` 在非 alias 样本上逐字段相等

### 连库验收（Wave 5，不进 CI）

- `verify_legacy_migration_live.py`：Property 21/23/24/25/26/27/30
- 一次 `asyncio.run` 取全部快照后同步断言（连接池绑定首个事件循环）
- 默认 dry-run；`--apply` 后按快照自动复原并二次核实

### 变异检验（必做）

每个守卫写完后逐条改一字看是否变红：改 `columns` 表态、改 alias 一项、把 `require_columns` 默认改 False、把 `positional` 塞进 `ALWAYS_MIGRATABLE_KINDS`、删掉母公司章排除。**变异未打红说明守卫有缺陷**。备份写 `.bak` 并提供 `--restore`，还原放 `finally`。

### 回归

- `backend/tests/` 全部 `test_note_*` + `test_disclosure_*`
- 前端 `disclosureColumnsCoverage.spec.ts` / 各 `*NoteSubtableContract.spec.ts`
- `_note_structure_kit` 既有消费方（各 per-cycle `fix_note_*_structure.py --check`）
