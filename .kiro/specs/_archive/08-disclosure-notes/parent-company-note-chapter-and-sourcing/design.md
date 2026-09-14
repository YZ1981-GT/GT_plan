# Design Document

## Overview

本设计把母公司附注章节从「结构错位 + 零取数」修到「结构对齐源模板 + 可从母公司单体项目取数」，并让报表与附注共用同一套母公司口径定位。

三条设计主线：

1. **结构层**：以 `docs/模版/` 两份源 docx 为唯一裁决者，用幂等脚本修 soe 章标题/标识、补两版列元数据与 guidance、正名重名空名表、还原长期股权投资被压扁的两级表头。
2. **口径层**：新建单一真源 helper `parent_company_scope.py`，按 `(company_code, audit_year, report_scope)` 定位同代码兄弟项目；附注取数与报表母公司列**共用**它。
3. **接线层**：`variant_matrix` 增母公司维度 → 母公司章科目可解析 → 取数指向母公司单体项目 + 溯源展示 + 无兄弟项目时显式留空。

设计约束（来自平台既有铁律）：

- 两级表头只走 `ColumnDef.group`，单级显式 `flat`，禁新建机制
- `columns` 必须 seed 路径与推送载荷**两处**都表态，只改一处会让另一路径被前缀推断塞出凭空父表头
- 结构修订一律幂等脚本 + `--check`，禁手改巨型 JSON（listed 1.35 MB / soe 851 KB，并发会话会互相回退）
- 守卫直读源 docx，不得以 JSON 自证；每个守卫必须做变异检验
- 母公司章无数据来源时**留空并提示**，不得显示 0

## Architecture

```
判据真源（只读）
  docs/模版/…上市公司财务报表附注模板…docx   ← listed 第16章
  docs/模版/…国企财务报表附注…docx           ← soe  第12章
        │ python-docx 直读 Heading 1 定位章 + 逐表提取 headers
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 结构层（Wave 1~2）                                            │
│  backend/scripts/fix/fix_note_parent_company_chapter.py      │
│    · soe 第12章 title/section_id 修正 + legacy_aliases        │
│    · 两版 columns(group/flat) + guidance 补齐                  │
│    · 长期股权投资 3 表两级表头还原                              │
│    · 表名唯一化（表头泄漏/空名 → {科目名}（表N））                │
│  --dry-run / --check（0 欠账 exit 0）/ 幂等                     │
└─────────────────────────────────────────────────────────────┘
        │
┌─────────────────────────────────────────────────────────────┐
│ 口径层（Wave 3）单一真源                                        │
│  backend/app/services/parent_company_scope.py                │
│    resolve_parent_standalone_project(db, consol_project)      │
│    resolve_consolidated_sibling(db, standalone_project)        │
│    is_parent_company_project(db, project)                      │
│  依据 uq_project_company_year_scope 保证唯一                   │
└─────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│ 附注取数（Wave 4）          │   │ 报表母公司列（Wave 4）          │
│ variant_matrix 增母公司维度 │   │ report_excel_exporter        │
│ 母公司章 report_row_code   │   │  _load_parent_row_index()     │
│ 取数指向单体项目 + 溯源     │   │  改用同一 helper + 补 scope/year│
└──────────────────────────┘   └──────────────────────────────┘
        │
┌─────────────────────────────────────────────────────────────┐
│ 守卫层（Wave 5）                                              │
│  test_note_parent_company_chapter.py  三向比对 + 反向自检      │
│  test_parent_company_scope.py         口径 + 交叉锁死          │
│  test_report_parent_column_scope.py   旧行为复现必红            │
│  characterization: 合并章逐字节不变 / 其余100科目 matrix 不变    │
│  CI job: parent-company-note-chapter                          │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. `parent_company_scope.py`（新建，口径单一真源）

```python
async def resolve_parent_standalone_project(
    db: AsyncSession, consol_project: Project
) -> Project | None:
    """定位母公司单体项目（与合并项目同企业代码、同年度、口径为 standalone）。

    仅当入参为 consolidated 项目时成立；非合并项目返回 None。
    三个查询条件必须齐备：company_code / audit_year / report_scope。
    找不到返回 None（合法状态：合并项目尚未建母公司单体）。
    """

async def resolve_consolidated_sibling(
    db: AsyncSession, standalone_project: Project
) -> Project | None:
    """反向：某 standalone 项目是否有同代码同年度的合并兄弟。"""

async def is_parent_company_project(db: AsyncSession, project: Project) -> bool:
    """该项目是否为母公司（standalone 且存在合并兄弟）。
    口径必须与 project_display.get_project_display_name() 一致
    （实测函数名逐字为此，签名 (project: dict, all_projects: list[dict]) -> str）。"""
```

设计要点：

- **不新增 DB 列、不新增表**。母公司身份完全由既有三元组推导。
- `report_scope` 归一走既有 `normalize_report_scope`，但**入口显式要求 `consolidated`**，避免 `parent_only` 被静默回退带来的歧义（需求 8.6 的处置：不扩展取值域，改为「合并项目 + 跨项目取数」表达母公司口径，并在模块 docstring 登记该决定）。
- 返回 ORM `Project` 对象而非 id，便于调用方直接读 `name`/`company_code` 做溯源展示。

### 2. `fix_note_parent_company_chapter.py`（新建，幂等结构脚本）

复用平台既有共享件 `backend/scripts/fix/_note_structure_kit.py`（`flat_columns` / `two_period_columns` / `rule` / `run_section` / `apply_plan` / `build_cli`），与 D1/H2/H7/K1 同款范式。

处理顺序（顺序即优先级，避免互相打架）：

1. soe 第 12 章 `section_title` + `section_id` 改写，6 子节 `section_id` 前缀同步，旧 slug 进 `legacy_aliases`
2. 表名唯一化（**先正名再补列**，否则按表名索引的列规则会落空）
3. 长期股权投资 3 表两级表头还原（`group` + 叶子 `label`，**`key` 不动**以免既有数据丢落点）
4. 其余表补 `columns`（单级标 `flat`）+ `guidance`

CLI：`--dry-run`（默认）/ `--apply` / `--check`。`--check` 输出欠账清单，0 欠账 exit 0。

### 3. `variant_matrix` 母公司维度（Wave 4）

现状 4 个变体键 `soe_standalone`/`soe_consolidated`/`listed_standalone`/`listed_consolidated`，且 standalone ≡ consolidated。

**不新增变体键**（会波及 102 科目 × 全部消费方），改为新增顶层可选字段：

```json
{
  "account_key": "ying_shou_zhang_kuan",
  "section_title": "应收账款",
  "variants": { "...": "不变" },
  "parent_company_sections": { "listed": "十六、应收账款", "soe": "十二、应收账款" }
}
```

- 只给母公司章覆盖的科目加该字段（listed 6 个 / soe 6 个，其中 4 个科目两版都有）
- 既有消费方读 `variants` 逐字不变 ⇒ 零回归
- 新字段缺省 = 该科目无母公司章落点

### 4. 母公司章取数与溯源（Wave 4）

- 取数入口读 `parent_company_sections` 判定当前章节是否属母公司章
- 属母公司章 → `resolve_parent_standalone_project()` → 用返回项目的 `project_id` 走既有 `trial_balance` / 底稿取数链路（**不新建取数管道**）
- 溯源载荷含 `source_project_name` / `source_company_code` / `source_scope='standalone'`，复用既有溯源面板范式
- 兄弟项目不存在 → 载荷标 `parent_project_missing: true`，前端显示「本项目未建母公司单体」灰态，**不填 0**

### 5. `report_excel_exporter._load_parent_row_index()` 修正（Wave 4）

```python
# 旧（缺陷）：按上级公司代码，且无 scope/year 过滤
parent_code = project.parent_company_code
select(Project).where(Project.company_code == parent_code, Project.is_deleted == False).first()

# 新：复用 helper
parent_project = await resolve_parent_standalone_project(self.db, project)
if parent_project is None:
    return {}   # 保持既有 fail-open：该列留空
```

`:parent` 占位符与 `current_parent` 坐标语义、填充位置均不变。

## Data Models

### 不涉及 DB schema 变更

本 spec **无迁移**。母公司身份由 `projects` 既有三元组推导，取数复用既有 `trial_balance` / `disclosure_notes`。

### `note_template_soe.json` 第 12 章变更

| 字段 | 旧值 | 新值 |
|---|---|---|
| `section_title` | `股份支付` | `母公司财务报表的主要项目附注` |
| `section_id` | `chapter-12-gu-fen-zhi-fu` | `chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu` |
| 6 子节 `parent_section_id` | 同上旧值 | 同上新值 |
| 6 子节 `section_id` 前缀 | `chapter-12-gu-fen-zhi-fu-*` | `chapter-12-mu-gong-si-*` |
| `legacy_aliases` | 无 | 追加旧 slug |
| `sort_index` | 12 | **不变** |

### 母公司章表结构目标态

listed 第 16 章（6 子节）：

| 子节 | 类型 | 表数 | 列结构来源 |
|---|---|---|---|
| 应收票据 | 同构 | 与五、4 一致 | 合并章 |
| 应收账款 | 同构 | 与五、5 一致 | 合并章 |
| 其他应收款 | 同构 | 与五、8 一致 | 合并章 |
| 长期股权投资 | **自有** | 3 | 源 docx 7 / 9 / 13 列，均两级 |
| 营业收入与营业成本 | 同构 | 与五、62 一致 | 合并章 |
| 投资收益 | **自有** | 1 | 源 docx 3 列 16 行 |

soe 第 12 章（6 子节）：

| 子节 | 类型 | 表数 | 列结构来源 |
|---|---|---|---|
| 应收账款 | 同构 | 与八、对应科目一致 | 合并章 |
| 其他应收款 | 同构 | 同上 | 合并章 |
| 长期股权投资 | **自有** | 3 | 源 docx 5 / 7 / 12 列（表 3 两级） |
| 营业收入与营业成本 | 同构 | 同上 | 合并章 |
| 投资收益 | **自有** | 1 | 源 docx 3 列 21 行 |
| 现金流量表补充资料 | **自有** | 1 | 源 docx 3 列 31 行 |

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 源 docx 缺失 | 守卫**明确失败**并提示路径 | 判据失效必须打红，不能静默跳过变空转 |
| 母公司单体项目不存在 | helper 返 None + INFO 日志；附注留空提示、报表列留空 | 合并项目尚未建单体是合法状态 |
| 同代码存在多条 standalone | 唯一索引保证不可能；helper 仍加断言，出现即 ERROR | 防索引被误删后静默取错 |
| 入参非 consolidated 项目 | helper 返 None | 母公司口径只在合并项目下成立 |
| 长期股权投资表 `key` 与既有数据不匹配 | 只改 `label`/`group`，`key` 保持不变 | 改 key 会让整表已录数据丢落点 |
| 表名正名后旧数据成孤儿 | 旧名进 `legacy_aliases`；确认废弃的进 `_removed_table_keys` | 表名是 `sub_table_data` 键 |
| 幂等脚本 `--apply` 中断 | 写入按章节 savepoint，逐章提交 | 避免部分状态 |

## Correctness Properties

### Property 1: 母公司章存在且不可删除

两份 `note_template_*.json` 中母公司章标题行与全部子节必须存在；断言子节数 listed = 6、soe = 6。

**Validates: Requirements 1.5, 4.8**

### Property 2: 判据来自源 docx 而非模板 JSON

守卫必须能从 `docs/模版/` 两份 docx 读出母公司章 Heading 1 与逐表 headers；源文件缺失时守卫失败。

**Validates: Requirements 1.1, 1.2**

### Property 3: 两版子节集合不对称且不被对齐

listed 子节含「应收票据」且不含「现金流量表补充资料」；soe 反之。任何把两版子节集合改成相等的改动必须打红。

**Validates: Requirements 1.3**

### Property 4: 同构/自有表两类清单与源 docx 依据一致

每个「同构子节」在源 docx 中确实无自有表；每个「自有表子节」在源 docx 中确实有表且表数匹配。

**Validates: Requirements 1.4, 4.1, 4.2**

### Property 5: soe 第十二章标题为母公司章且源 docx 无股份支付章

`note_template_soe.json` 第 12 章标题等于源 docx Heading 1 原文；且国企源 docx 的 14 个 Heading 1 中不含「股份支付」。

**Validates: Requirements 2.1, 2.4**

### Property 6: section_id 改写保留旧别名

第 12 章及 6 子节的 `section_id` 已改写；旧 slug 出现在 `legacy_aliases` 中，使既有行仍可解析。

**Validates: Requirements 2.2, 2.3**

### Property 7: 章序不变

soe 第 12 章 `sort_index` 与其在 14 章中的相对位置不变。

**Validates: Requirements 2.5**

### Property 8: listed 标题偏差双向锁死

断言 JSON 现值为「母公司财务报表主要项目注释」**且**源 docx 现值为「公司财务报表主要项目注释」；任一侧变化即打红。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 9: 长期股权投资表列数与两级表头匹配源 docx

listed 3 表列数 = 7/9/13；soe 3 表列数 = 5/7/12；两级表头表的 `group` 非空，单级表标 `flat`。

**修订前 JSON 实测现值**（2026-08-05 逐表数，守卫的「改前必红」锚点）：

| 变体 | JSON 现值 | 源 docx 目标 | 压扁情况 |
|---|---|---|---|
| listed | `[3, 6, 5]` | `[7, 9, 13]` | 3 张表全部压扁 |
| soe | `[5, 7, 5]` | `[5, 7, 12]` | **仅表 3 压扁**；表 1(5 列)、表 2(7 列) 与源一致 |

⚠️ soe 表 1/表 2 列数**已经正确**，Property 9 的守卫不得把它们当欠账重写 —— 只有 soe 表 3 与 listed 全部 3 表需要还原两级表头。误改已正确的表会造成无谓 diff 并破坏零回归判据。

**Validates: Requirements 4.3, 4.4, 4.5**

### Property 10: 结构行与可扩行保留

源 docx 中 `…` 可扩行与 `一、合营企业`/`二、联营企业` 分组行在模板中保留，未被当占位删除。

**Validates: Requirements 4.6**

### Property 11: 投资收益不套用合并章结构

母公司章投资收益为 1 张表（listed 16 行 / soe 21 行含表头），不等于合并章的 2 张表结构。

**Validates: Requirements 4.7**

### Property 12: 列元数据与指引齐备且显式表态

母公司章全部表 `columns` 非空，每张表显式 `group` 或 `flat`；`guidance` 非空且不含 markdown 粗体。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 13: 幂等脚本可复算

`--check` 在修订后 0 欠账 exit 0；连续两次 `--apply` 结果逐字节一致。

**Validates: Requirements 5.4, 5.5**

### Property 14: 表名唯一非空

母公司章每个子节内表名唯一且非空；不存在表头首格泄漏式表名。

唯一性判据按「同子节内表名集合大小 == 表数量」（需求 6.6），**不是**只查空串 —— 只查空串放不过「`类  别`×6 塌成 1 键」这类重名塌键；失败消息逐子节输出实际表数 / 去重后键数 / 塌键张数。正名覆盖面为实测受影响的全部 6 个子节（需求 6.5），listed 应收账款的 6 张空名表逐张获得稳定唯一名。

**Validates: Requirements 6.1, 6.2, 6.4, 6.5, 6.6**

### Property 15: 表名正名保留旧映射

正名过的表，其旧名可在 `legacy_aliases` 或 `_removed_table_keys` 语义中找到。

**Validates: Requirements 6.3**

### Property 16: helper 三条件齐备

`resolve_parent_standalone_project` 的查询同时含 `company_code`、`audit_year`、`report_scope='standalone'` 三个条件；源码级断言 + 行为断言双查。

**Validates: Requirements 7.1, 7.2**

### Property 17: helper 边界行为

入参非 consolidated → None；找不到兄弟 → None 且不抛异常。

**Validates: Requirements 7.3, 7.4**

### Property 18: helper 与展示层口径交叉锁死

对同一组项目输入，`is_parent_company_project()` 判为母公司的集合与 `project_display.get_project_display_name()` 加「（母公司）」后缀的集合相等。

**命名注**：该展示层函数实测名为 `get_project_display_name(project: dict, all_projects: list[dict]) -> str`（**不是** `build_project_display_name`）。按错名写守卫会 0 命中变成空转，故守卫须 import 真实符号而非按名 grep。它只吃 dict 列表、不连库，交叉锁死时需把 ORM 对象投影成 dict。

**Validates: Requirements 7.5, 7.6**

### Property 19: variant_matrix 母公司维度为 additive

新增 `parent_company_sections` 字段；102 个科目的 `variants` 取值逐字不变。

**Validates: Requirements 8.1, 10.4**

### Property 20: 母公司章取数指向单体项目

母公司章取数使用 `resolve_parent_standalone_project()` 返回的项目 id，而非合并项目自身 id。

**Validates: Requirements 8.2**

### Property 21: 母公司章 report_row_code 有实证依据

母公司章表的 `report_row_code` 非 None 且在 `report_config` 中存在，行名与该 row_code 的 row_name 可比对。

**Validates: Requirements 8.3**

### Property 22: 无兄弟项目时留空不填零

母公司单体项目缺失时，载荷标记缺失状态，金额字段为 None 而非 0。

**Validates: Requirements 8.4**

### Property 23: 母公司取数具备溯源

载荷含来源项目名、企业代码、口径三项。

**Validates: Requirements 8.5**

### Property 24: 附注层母公司口径处置已登记

`normalize_report_scope` 的取值域决定在模块 docstring 中显式登记，且 `parent_only` 不出现在附注层取数路径。

**Validates: Requirements 8.6**

### Property 25: 报表母公司列改用共享 helper

`_load_parent_row_index` 不再引用 `parent_company_code`，改引用 `resolve_parent_standalone_project`。

**Validates: Requirements 9.1**

### Property 26: 报表母公司列口径反向自检

构造同代码同时存在 consolidated 与 standalone 的场景：复现旧实现取到合并项目（打红），新实现取到单体项目（通过）。

**Validates: Requirements 9.2, 9.4**

### Property 27: 报表列 fail-open 与占位语义不变

母公司项目缺失时返回空 dict、该列留空不崩；`:parent` 占位与 `current_parent` 坐标语义不变。

**Validates: Requirements 9.3, 9.5**

### Property 28: 合并章零回归

listed 第 5 章与 soe 第 8 章的 `tables`/`rows`/`columns`/`text_sections` 逐字节不变。

**Validates: Requirements 10.3**

### Property 29: 守卫做过变异检验

每个新增守卫文件配套记录变异检验结果（改一处必红并已还原）。

**Validates: Requirements 10.1, 10.2**

### Property 30: 真实库验收诚实报告

真实库无 consolidated 项目时，验收脚本明确输出「无法验收：本库无合并项目」，不得用 fixture 冒充通过。

**Validates: Requirements 10.5, 10.6**

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 结构守卫（后端） | `backend/tests/test_note_parent_company_chapter.py` | Property 1~15、28；直读源 docx 三向比对 + 反向自检 |
| 口径守卫（后端） | `backend/tests/test_parent_company_scope.py` | Property 16~18、24；含源码级三条件断言 |
| 取数守卫（后端） | `backend/tests/test_parent_company_note_sourcing.py` | Property 19~23 |
| 报表守卫（后端） | `backend/tests/test_report_parent_column_scope.py` | Property 25~27；旧行为复现必红 |
| 幂等脚本自检 | 脚本内 `--check` + 测试调用 | Property 13 |
| 真实库验收 | `backend/scripts/diagnose/verify_parent_company_note_live.py`（只读，默认 dry-run） | Property 30 |
| CI | `.github/workflows/governance-checks.yml` 新增 job `parent-company-note-chapter` | 全部后端守卫 + `--check` |

**零回归判据**：合并章 characterization 逐字节比对 + `variant_matrix` 102 科目 `variants` 快照比对。

**变异检验清单**（Property 29 要求，每条须实测打红后还原）：删除母公司章子节 / 把 soe 第 12 章标题改回「股份支付」 / 把两版子节集合改成相等 / 长期股权投资表列数改错 / 投资收益套用合并章结构 / 表名改成重名 / helper 去掉 `report_scope` 条件 / helper 去掉 `audit_year` 条件 / 报表侧改回 `parent_company_code`。
