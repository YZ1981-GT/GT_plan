# Requirements Document

## Introduction

修复「国企↔上市」附注转换的正确性缺陷。该转换是**自动触发**的（准则切换事件 `STANDARD_CHANGED` → `_on_standard_changed_notes` → `execute_conversion`），另有 `POST /note-conversion/execute` 手工入口，因此下述缺陷一旦遇到合并/准则切换场景就会实际发生，不是纸面风险。

**生产路径实测**（2026-08-05 逐方法读 `NoteConversionService.execute_conversion` 源码）：

| 步 | docstring 声称 | 实际实现 |
|---|---|---|
| 1 | 快照当前状态 | ✅ `_create_snapshot` |
| 2 | 更新 `project.template_type` | ✅ |
| 3 | **按 row_name 映射报表行 row_codes** | ❌ **`return 0` 空操作**（注释自承认「For now, return 0 as the chain refresh will handle regeneration」） |
| 4 | **映射 disclosure_notes 到新模板结构** | ❌ **只 `SELECT count(*)` 返回行数**，一行数据不改 |
| 5 | 更新公式 row_code 引用 | ❌ **`return 0` 空操作**（理由「两准则 row_code 方案相同」） |
| 6 | 触发全链刷新 | ✅ `execute_full_chain(force=True)`，fail-open（失败仅 warning） |

由此产生三个后果：

1. **数据错位**：`disclosure_notes` 的 `section_number` / `section_id` 一行不改，而 `template_type` 已切换 ⇒ 读取时按新模板渲染。两份模板有 **20 个章节号重合且 13 个标题不同**（`八、1` 在 soe 是货币资金、在 listed 是政府补助）⇒ 原「八、1 货币资金」数据显示在上市模板的「八、1 政府补助」位置。
2. **假成功反馈**：Step 4 的 `count(*)` 结果作为 `mapped_notes` 返回给调用方，审计师看到「已映射 N 个章节」，实际零映射。
3. **Step 5 的免做理由不成立，但原因与最初判断相反**（2026-08-05 `report_config` 全表实证修正）：`applicable_standard` 四值下共 339 个 `row_name`、201 个两侧都有，其中 **78 个存在跨变体 row_code 差异**、**12 条是干净的 1↔1 映射**（详见需求 3.1 清单）⇒ 公式里的 `ROW('IS-055')` 在 soe→listed 后应改写为 `ROW('IS-033')`，不改写即指向错行。

   **⚠️ 立项初稿曾把 `BS-013`↔`BS-016`、`BS-053`↔`BS-058`、`BS-043`↔`BS-059` 列为跨变体映射，实证证明方向完全相反**：这三组是**「一码两义」**（同一 row_code 在不同准则下是不同科目），不是「同义两码」——

   | row_code | listed 侧 row_name | soe 侧 row_name |
   |---|---|---|
   | `BS-013` | 一年内到期的非流动资产 | 一年内到期的非流动资产（四变体一致） |
   | `BS-016` | 一年内到期的非流动资产 | **其中：应收股利** |
   | `BS-053` | 其他流动负债 | 其他流动负债（四变体一致） |
   | `BS-058` | 其他流动负债 | **交易性金融负债** |
   | `BS-043` | 衍生金融负债 | 衍生金融负债（四变体一致） |
   | `BS-059` | **流动负债合计** | 衍生金融负债 |

   按初稿去改写 `ROW('BS-013')→ROW('BS-016')`，在 soe 项目上会把「一年内到期的非流动资产」指向「应收股利」；`BS-043→BS-059` 更会把明细行指向**合计行**。故这三组必须进**禁止改写清单**（需求 3.6）。

   （「`BS-013`/`BS-016` 都叫一年内到期的非流动资产」这一记载的真实语境是 **listed 侧内部有两个同名行**，用于说明「按 row_name 拦公式会漏兄弟行」，与跨准则映射无关。）

**（立项时的判断，🔴 已被 Task 10 实测推翻）真正实现了映射逻辑的 `convert_disclosure_notes_v2` 是孤儿**：`Called by` 共 11 处**全部是测试**，生产零调用方（属平台已登记的「未完成的重构」缺陷模式）。且它自身另有 3 个缺陷：

> 🔴 **2026-08-07 实测修正（勿再照本段的「唯一已实现」定性行事）**：「v2 是唯一已实现的正确骨架」在 Task 8/9 落地后**不再成立** —— 生产路径 `_map_disclosure_notes` 已完整实现章节映射，且**严格强于** v2（别名桥接 / `binding_id` 前缀重写 / `section_id` 为 NULL 时回填 / 章节号占用检查 / 逐章 savepoint 隔离，这五项 v2 全无）。故 Task 10 裁决 = **删除 v2，不接线**（接线会造出第二份真源）。本段下列三个缺陷描述仍然准确，保留作「为什么不值得接线」的依据。

- `format_diff_sections` 条目**没有 `section_id` 键**（实际键 = `field_mapping` / `listed_format` / `listed_section_id` / `section_title` / `soe_format` / `soe_section_id`），而代码读的正是 `fd.get("section_id")` ⇒ 恒 None ⇒ `format_adapted_count` 恒 0，33 条格式差异一条都用不上。
- `field_mapping` **全部为 null（0/33）**，实测 `adapt_table_data()` 在 `field_mapping=None` 时**输入 == 输出**（某章节 soe 1 表 / listed 5 表，转过去仍是 1 表）。
- **共有章节只计数、不改写 `note.section_id`**：第 649 行按当前类型取 sid 判断是否存在，但从未把 `section_id` 改成目标类型的 sid ⇒ 即便接线，共有章节在新模板下仍然对不上。

**差异数据源缺陷**（`backend/data/note_soe_listed_diff.json` + `note_template_diff.py`）：

- 落盘 JSON 自标 **`is_mock: True`** 且**已 stale**：实时 `compute_diff_from_templates()` 返回 `is_mock=False` 且数量不同（common 106 vs **107** / soe_only 60 vs 60 / listed_only 71 vs **70** / format_diff 33 vs **39**，common 集合比对结果 `False`），而生产走 `load_diff_data()` 拿的是落盘的 stale 那份。
- **按 `section_title` 精确匹配导致 20 对措辞差异被误判成「各自独有」**，转换时走「源独有→归档 + 目标独有→新建空章」**丢已录数据**：

| 国企 | 上市 | 相似度 |
|---|---|---|
| 财务报表编制基础 | 财务报表**的**编制基础 | 0.94 |
| 递延所得税资产**和**递延所得税负债 | 递延所得税资产**与**递延所得税负债 | 0.93 |
| 所有权**和**使用权受到限制的资产 | 所有权**或**使用权受到限制的资产 | 0.93 |
| 营业收入**、**营业成本 | 营业收入**和**营业成本 | 0.89 |
| **研究**开发支出 | 研发支出 | 0.80 |
| 财务报表主要项目注释 | **母公司**财务报表主要项目注释 | 0.87 ⚠️ |

最后一对是陷阱：把阈值放宽到 0.85 就会让国企的**合并**章节错配到上市的**母公司**章节，必须人工钉死为「不可匹配」。

- **章号映射存在可疑错配**：soe ch08→listed ch05（49 条）与 soe ch04→listed ch03（26 条）正确，但 **soe ch08→listed ch03 有 10 条**（财务报表项目注释映到会计政策章），另有 soe ch12→listed ch05 两条。
- **`variant_matrix` 有假 null**：标 listed 侧 null 的 25 个科目里，至少 12 个在 listed 模板其实有落点，只是归在「三、重要会计政策」「十四、日后事项」「十七、补充资料」章 —— `三、资产减值损失（损`、`三、营业外收入（注：`、`三、现金流量表项目注`（9 表）、`三、优先股、永续债等`、`三、借款费用`、`三、债务重组【不适用`、`十四、终止经营`、`十七、净资产收益率和每股收益`。矩阵按「同章节」找不到就记 null，导致底稿同步误判「上市不适用」。

**判据真源**：附注模板的源 docx 位于 `docs/模版/`（listed `3.2025年度上市公司财务报表附注模板-2026.01.15.docx` / soe `1.1-2025国企财务报表附注20260119.docx`）。docx 章号是 Word 自动编号，定位章节必须按 `Heading 1` 样式。

### 🔴 `disclosure_notes` 的真实列名（2026-08-07 实证 39 列，立项初稿三处写错）

| 立项写的 | 真实情况 | 处置 |
|---|---|---|
| `section_number` | **该列不存在**。章节号存在 **`note_section`**（取值如 `八、9`、也可能是 md 截断的 `十、重要的资产负债表`） | 全部改写为 `note_section` |
| `legacy_aliases` | **该列不存在** | 源侧 sid 落 **`template_lineage.legacy_section_ids`**（JSONB，本 spec 无迁移；实测全库 `template_lineage` **0 条**有值，等于全新字段） |
| `is_empty` / `status` / `is_deleted` / `section_id` / `parent_section_id` / `template_lineage` | ✅ 均存在（`status` 枚举实测仅 `draft` / `confirmed`，**没有** `archived`） | 可直接用 |

⇒ 按初稿字面实现会 `column "section_number" does not exist`。另注：`status` 无 `archived` 取值，故「归档」只能靠 `is_deleted=true` + `template_lineage.archived_sections` 表达（需求 2.3 已如此写）。

### 🔴 连带缺陷：附注公式 `binding_id` 内嵌章节号（立项未登记）

实测 1030 个未软删章节中 **446 条**的 `table_data` 含 `binding_id`，形态是「**章节号**.行标签.列键」（`五、11.分公司B.prior_year_value` / `八、52.租赁负债净额.opening_balance`）。⇒ 改写 `note_section` 会让这批绑定**静默失联**（公式取数变空，而不是报错）。必须在章节映射任务里一并处置，见需求 2.7。

**`section_id` 大面积为 NULL**：抽样 12 条里 8 条 `section_id`/`level`/`parent_section_id` 全 NULL 而 `note_section` 有值 ⇒ 任何「按 `section_id` 驱动映射」的实现都必须对 `section_id IS NULL` 的存量行有明确处置（否则那批行静默不参与转换），见需求 2.8。

**范围外**：母公司章节结构与取数（`parent-company-note-chapter-and-sourcing`）；附注模板 columns 补齐与 legacy 快照迁移（`note-template-columns-and-legacy-snapshot-closure`）；合并附注 V2 与跨模板翻译两个灰度开关。

**🔴 执行顺序依赖：本 spec 必须在 `parent-company-note-chapter-and-sourcing`（下称 A）之后执行**。

理由（2026-08-05 实证）：`note_template_soe.json` 第十二章的 `section_title` 当前被错写为「股份支付」（真值 = 母公司章「母公司财务报表的主要项目附注」，国企源 docx 14 个 Heading 1 中根本不含「股份支付」章），且其 6 个母公司子节的 `section_id` 全部带错误 slug 前缀 `chapter-12-gu-fen-zhi-fu`。由此：

- 需求 8.2 的 `soe ch12 → listed ch05` 那 2 条章号映射，是**该标题错误的连带产物**（soe 母公司子节「营业收入与营业成本」「投资收益」与 listed 第五章合并章同名 → 按 `section_title` 精确匹配就配到了合并章），A 修好标题与 slug 后须复跑核查确认其消失，**本 spec 不独立调查这 2 条**。
- 需求 5.3 的禁止匹配对「财务报表主要项目注释 ↔ 母公司财务报表主要项目注释」直接涉及 A 的母公司章标题，A 若调整标题，本清单须同步。
- 若在 A 之前执行本 spec，`common_sections` / `soe_only_sections` 的划分会建立在错误章名之上，重生成的 diff JSON 需要再重做一次。

## Requirements

### 需求 1：差异数据源重建与去 mock

**User Story:** 作为维护者，转换依赖的差异数据必须与当前模板一致且可复算，不能是 stale 的 mock。

#### Acceptance Criteria

1.1. THE `note_soe_listed_diff.json` SHALL 由 `backend/scripts/gen/generate_note_soe_listed_diff.py` 重新生成，且 `is_mock` SHALL 为 `false`。

1.2. THE 守卫 SHALL 断言落盘 JSON 与 `compute_diff_from_templates()` 实时计算结果逐项相等（四个桶的条目集合而非仅数量），模板一改即打红。

1.3. WHEN 落盘 JSON 与实时计算不一致 THEN `load_diff_data()` SHALL 记 WARNING 并以实时计算为准，而非静默使用 stale 数据。

1.4. THE `format_diff_sections` 条目 SHALL 补 `section_id` 键（按 `current_type` 取对应侧 sid），或消费方改读 `soe_section_id`/`listed_section_id`；两种处置任选其一但 SHALL 在守卫中钉死所选方案。

1.5. THE 守卫 SHALL 断言 `format_diff_sections` 的 `field_mapping` 若为 null 则 `adapt_table_data()` 必须是空操作（当前行为），并要求非空 field_mapping 时真正改变结构。

### 需求 2：章节映射真正落地

**User Story:** 作为审计师，切换准则后我已录入的附注数据必须出现在新模板的正确章节，而不是错位到同章节号的别的科目下。

#### Acceptance Criteria

2.1. THE `execute_conversion` 的章节映射步骤 SHALL 真正改写 `disclosure_notes` 的 `section_id` 与 **`note_section`**（章节号，**不是** `section_number` —— 该列不存在）到目标变体，不得只返回计数。

2.2. WHEN 章节属 `common_sections` THEN 系统 SHALL 按 `soe_section_id ↔ listed_section_id` 双向改写 `section_id`，并把源侧 sid 追加进 **`template_lineage.legacy_section_ids`**（`legacy_aliases` 列不存在；本 spec 无迁移，故落 JSONB），保历史可解析性。

2.3. WHEN 章节属源侧独有 THEN 系统 SHALL 软删并把归档信息记入 `template_lineage.archived_sections`（含 `section_id` / `archived_at` / `reason`）。

2.4. WHEN 章节属目标侧独有 THEN 系统 SHALL 创建空章节（`is_empty=true` / `status='draft'`）。

2.5. THE 用户已编辑单元格（`_cell_modes[i] == 'manual'`）SHALL 在共有章节转换后保留。

2.6. THE 转换 SHALL 不产生「同一 `(project_id, year, section_id)` 重复行」。

2.7. WHEN 改写 `note_section` THEN 系统 SHALL 同步处置该 note 的 `table_data` 内 `binding_id` 前缀（实测 446 条带 binding，形态「章节号.行标签.列键」）：改写前缀 **或** 把旧章节号记入 `template_lineage.legacy_note_sections` 供解析回退；二选一但 SHALL 在守卫钉死所选方案，**不得**静默留失联绑定。

2.8. WHEN 存量 note 的 `section_id` 为 NULL（实测大面积存在）THEN 系统 SHALL 有明确处置：按 `note_section` + `section_title` 回填 sid 后参与映射，**或** 计入 `skipped` 并附原因码；**不得**静默跳过（静默跳过会让这批行在转换后永久停留在源变体的章节号上）。

### 需求 3：报表行与公式引用映射

**User Story:** 作为审计师，切换准则后附注公式引用的报表行不能指向另一个科目。

#### Acceptance Criteria

3.1. THE 系统 SHALL 建立「跨变体同语义行」映射清单 `CROSS_VARIANT_ROW_CODE_MAP`，内容 SHALL 为下述 12 条 `report_config` 实证结果（`soe → listed`，反向由反转生成）：

| 报表 | row_name | soe | listed |
|---|---|---|---|
| balance_sheet | 其中：优先股 | `BS-111` | `BS-077` |
| balance_sheet | 永续债 | `BS-112` | `BS-078` |
| cash_flow_statement | 处置子公司及其他营业单位收到的现金净额 | `CFS-038` | `CFS-016` |
| income_statement | （一）不能重分类进损益的其他综合收益 | `IS-055` | `IS-033` |
| income_statement | 1. 重新计量设定受益计划变动额 | `IS-056` | `IS-034` |
| income_statement | 2. 权益法下不能转损益的其他综合收益 | `IS-057` | `IS-035` |
| income_statement | 3. 其他权益工具投资公允价值变动 | `IS-058` | `IS-036` |
| income_statement | 4. 企业自身信用风险公允价值变动 | `IS-059` | `IS-037` |
| income_statement | （二）将重分类进损益的其他综合收益 | `IS-062` | `IS-039` |
| income_statement | 4. 其他债权投资信用减值准备 | `IS-066` | `IS-043` |
| income_statement | 6. 外币财务报表折算差额 | `IS-068` | `IS-045` |
| income_statement | 9. 其他 | `IS-071` | `IS-048` |

3.2. THE 清单 SHALL 由脚本从 `report_config` 按「同 `(report_type, row_name)` 在 soe 侧与 listed 侧各恰有 1 个 row_code 且两者不等」的判据生成，人工确认后冻结；**不得**按名称模糊推断或按 row_code 数字相邻推断。

3.3. WHEN 转换发生 THEN 附注公式中的 `ROW('X')` 引用 SHALL 按该清单改写；清单未覆盖的 row_code 保持不变。

3.4. THE `_update_formula_references` SHALL 接上改写函数并返回**实际改写条数**；**但当 `report_config` 域内可改写对象实证为 0 时，SHALL 保留返回 0 并附原因码 `no_mapping_needed` + 实证依据**，且 SHALL 删除「For now」这类临时措辞。

**🔴 立项原文「SHALL 不再 `return 0`（实证已证明存在 12 条真实差异）」的前提不成立**（2026-08-06 四条实证）：① `report_config` **无 `project_id` 列** = 纯模板表，按 `applicable_standard` 分行，切 `template_type` 天然读另一套配置行，不存在「项目级公式要跟着改写」；② 全库 `report_config.formula` 引用那 12 个 row_code 的行数 = **0**（`ROW()` 引用集只覆盖 `BS-002`~`BS-128`/`CFS`/`CFSS`/`EQ`/`IMP`/`IS-001`~`IS-030` 等主表行）；③ `wp_formula` 表 **0 行**；④ 附注侧**不存在 row_code 级公式** —— `binding_id` 是「章节号.行标签.列键」，而 `note_source_resolvers` 的 `ROW()` 参数是**单元格坐标**（`R2C1`）。⇒ 12 条映射清单仍必须建（判据真源 + 防「凭 row_name 相同就建映射」的护栏），但当前无对象可改；原因码必须能区分 `no_mapping_needed`（已扫描确无对象）与 `not_implemented`（没做）。

3.5. THE 守卫 SHALL 用正向断言证明清单生效：构造含 `ROW('IS-055')` 的公式，断言 soe→listed 后变为 `ROW('IS-033')`；且构造含清单外 row_code（如 `ROW('BS-002')`）的公式，断言保持不变。

3.6. THE 系统 SHALL 建立**禁止改写清单** `ONE_CODE_TWO_MEANINGS_FORBIDDEN`，至少含 `BS-016` / `BS-058` / `BS-059` 三条，并附各自在两准则下的 `row_name` 实测值作为理由。

3.7. THE 守卫 SHALL 用反向自检钉死禁止清单：WHEN 把 `BS-013→BS-016`（或 `BS-053→BS-058` / `BS-043→BS-059`）任一条加入 `CROSS_VARIANT_ROW_CODE_MAP` THEN 守卫 SHALL 打红。

3.8. THE 守卫 SHALL 断言 `CROSS_VARIANT_ROW_CODE_MAP` 的键与值集合**均不含「稳定码」**（两侧 `row_name` 相同的 row_code），且与 `ONE_CODE_TWO_MEANINGS_FORBIDDEN`（3 个被编造过的目标码）无交集。

**🔴 立项原文「两个清单互斥」按字面不可满足**（2026-08-06 实证）：「一码两义」实为 **78 条**（不是 3 条），而 12 条正确映射的 value **12/12 都是两侧异名** —— 这是码位偏移的必然结果（`soe BS-077` = ▲应付手续费及佣金 / `listed BS-077` = 其中：优先股），正因为同一码在两侧是不同科目，才需要把 soe 的 `BS-111` 改写成 listed 的 `BS-077`。⇒ 「两侧异名」本身**不构成禁止理由**，要求 MAP 与全部 78 条无交集会把正确设计判红。

**真不变量 = MAP 的 key/value 都不得是稳定码**：初稿三条错的根因是 **key 两侧同名、压根不需改写**（`BS-013`/`BS-053`/`BS-043`），不是「目标码有两义」。守卫按此实现，并保留对那 3 个被编造过的目标码的显式禁止登记。

### 需求 4：消除假成功反馈

**User Story:** 作为审计师，转换结果的数字必须反映真实发生的映射，否则我无法判断转换是否成功。

#### Acceptance Criteria

4.1. THE `execute_conversion` 返回的 `mapped_notes` SHALL 为**实际改写的章节数**，不得用存量章节 `count(*)` 冒充。

4.2. THE 返回结构 SHALL 区分 `mapped`（共有改写）/ `archived`（源独有归档）/ `created`（目标独有新建）/ `skipped`（无需处理）/ `failed`（逐条错误），与 v2 的返回口径一致。

4.3. WHEN 某章节映射失败 THEN 系统 SHALL 记入 `failed` 并继续处理其余章节（不整体回滚），且 `failed` 非空时调用方 SHALL 收到明确提示。

4.4. THE `mapped_rows` 与 `updated_formulas` 若为 0 SHALL 附带原因码（`no_mapping_needed` / `not_implemented` 二者必须可区分）。

### 需求 5：章节匹配归一化与人工确认

**User Story:** 作为维护者，措辞差异不该让审计师的数据被归档丢失，但也不能靠模糊匹配把不同科目混为一谈。

#### Acceptance Criteria

5.1. THE 章节匹配 SHALL 在精确匹配之外增加归一化匹配：仅去除空白与「的/和/与/、」等虚词差异，**不做**通用模糊/相似度匹配。

5.2. THE 归一化匹配 SHALL 由**显式配对清单**驱动（穷举而非算法推断），至少覆盖已实证的 5 对：财务报表编制基础 / 递延所得税资产和(与)递延所得税负债 / 所有权和(或)使用权受到限制的资产 / 营业收入、(和)营业成本 / 研究开发支出↔研发支出。

5.3. THE 配对清单 SHALL 显式包含**禁止匹配对**，且必须含 `财务报表主要项目注释` ↔ `母公司财务报表主要项目注释`（相似度 0.87，属不同口径章节）。

5.4. THE 守卫 SHALL 用反向自检证明：若把禁止匹配对加入允许清单，必须打红。

5.5. THE 每条配对 SHALL 附源 docx 依据（两侧章节标题原文）。

### 需求 6：v2 实现的处置

**User Story:** 作为维护者，我需要「真正实现了映射的那份代码」有明确归属，而不是留一份孤儿让下个会话误以为功能已具备。

#### Acceptance Criteria

6.1. THE 系统 SHALL 二选一处置 `convert_disclosure_notes_v2`：接线到生产路径（`execute_conversion` 内部调用它）**或**删除并把其逻辑并入生产路径。

> 🔴 **实际裁决（Task 10，2026-08-07 实测落地）= 后者「删除」**。五条依据：①生产 Step 4 已调 `_map_disclosure_notes`，语义完整；②v2 生产零调用方（11 处全是测试）；③v2 自身三缺陷（见 6.2）在生产路径上本就不存在或已修；④生产版**严格强于** v2（别名桥接 / `binding_id` 前缀重写 / sid NULL 回填 / 章节号占用检查 / 逐章 savepoint）；⑤接线必造第二份真源。⇒ **6.2（接线分支）不生效、6.3（删除分支）生效**，两条 AC 均保留以记录裁决空间。

6.2. IF 选择接线 THEN 其三个自身缺陷 SHALL 一并修复：`format_diff` 的 `section_id` 键、`field_mapping` 全 null 的空转、共有章节未改写 `section_id`。

6.3. IF 选择删除 THEN 其 11 个测试 SHALL 同步迁移到生产路径的测试上，不得直接删测试。

6.4. THE 守卫 SHALL 断言不存在「有实现但零生产调用方」的转换函数（防再次出现孤儿）。

### 需求 7：variant_matrix 假 null 修正

**User Story:** 作为审计师，某科目在上市模板里其实有披露落点时，底稿同步不应告诉我「不适用」。

#### Acceptance Criteria

7.1. THE 系统 SHALL 复核 `variant_matrix` 中 listed 侧 25 个 null 与 soe 侧 10 个 null，逐条判定「真无落点」还是「落点在别的章」。

**实证分类（2026-08-06，判据真源已冻结进 `note_variant_matrix_null_audit.py`）**：35 条 = **假 null 13 + 部分落点 7 + 真 null 15**。**🔴 首轮精确标题匹配把 8 条误判成真 null**（`实收资本` ↔ listed `五、53 股本` / `股本` ↔ soe `八、58 实收资本`（**两版用语互换**）/ `外币折算` ↔ `五、73 外币货币性项目` / `分部信息` ↔ `十四、分部报告` / 三条「一年内到期的 X」↔ `五、43 一年内到期的非流动负债`（**明细行归入父章**）/ `其他综合收益` ↔ soe `八、79 归属于母公司所有者的其他综合收益`）⇒ **判「某科目有无落点」必须四层**：精确匹配 → 关键词复核 → 别名对（用语互换）→ 明细归并父章；缺一层就会把「有落点」判成「不适用」，让底稿同步误报。

7.2. WHEN 落点在别的章 THEN 系统 SHALL 补记该落点（而非留 null），至少覆盖已实证的 8 个：资产减值损失 / 营业外收入 / 营业外支出 / 现金流量表项目注释 / 优先股永续债 / 借款费用 / 终止经营 / 净资产收益率和每股收益。

7.3. THE 修正 SHALL 为 additive：既有非 null 取值逐字不变。

7.4. WHEN 某科目确实两版都无落点 THEN 该 null SHALL 附理由，并由守卫要求理由非空。

### 需求 8：章号映射错配核查

**User Story:** 作为维护者，章号级映射的异常分布需要被解释，不能默认正确。

#### Acceptance Criteria

8.1. THE 系统 SHALL 逐条核查 `soe ch08 → listed ch03` 的 10 条映射，判定属真实错配还是章节归属差异。

8.2. THE `soe ch12 → listed ch05` 的 2 条映射**已结案**：其成因是 soe 第十二章（母公司章）的 `section_title` 被错写成「股份支付」，其母公司子节「营业收入与营业成本」「投资收益」与 listed 第五章合并章**同名**，按 `section_title` 精确匹配即配到合并章。该错误由 spec `parent-company-note-chapter-and-sourcing`（需求 2）修复。本 spec SHALL 在 A 完成后复跑核查脚本，断言这 2 条**消失**，而非单独调查。

8.3. THE 核查结论 SHALL 落成守卫可断言的清单（正常映射 / 已修正 / 已登记豁免三态）。

8.4. THE 守卫 SHALL 断言主映射分布不变：`soe ch08 → listed ch05` 与 `soe ch04 → listed ch03` 仍为多数。

### 需求 9：转换预览与回滚

**User Story:** 作为审计师，切换准则前我要能看到将发生什么，切错了要能退回。

#### Acceptance Criteria

9.1. THE 转换 SHALL 提供预览端点，返回「将改写 X 个 / 归档 Y 个 / 新建 Z 个 / 保留 N 处人工编辑」。

9.2. THE 预览 SHALL 不产生任何写入。

9.3. THE 既有 `rollback_conversion` SHALL 能把 `section_id` 改写与归档一并回退，并由测试覆盖往返一致性。

9.4. WHEN 转换由 `STANDARD_CHANGED` 事件自动触发 THEN 系统 SHALL 记录快照 id 到日志，使事后可回滚。

### 需求 10：守卫与零回归

#### Acceptance Criteria

10.1. THE 每个新增守卫 SHALL 实际执行变异检验（改一处必红并已还原）。

10.2. THE 不涉及转换的既有附注行为 SHALL 逐字节不变，由 characterization 测试钉死。

10.3. THE 修正 SHALL 挂 CI job。

10.4. THE 真实库验收 SHALL 覆盖一次 soe→listed→soe 往返；若真实库无可安全切换的项目，SHALL 明确报告「无法验收」而非用 fixture 冒充。

10.5. THE 验收 SHALL 在只读 dry-run 下先输出预期改写清单，`--apply` 后按快照复原。

10.6. **THE 验收 SHALL NOT 为了凑验收条件而改动任何真实项目的 `template_type` / `report_scope` / `applicable_standard_v2`**。转换会改 `project.template_type` 并触发 `execute_full_chain(force=True)` 全链重算，属**破坏性操作**；真实库当前 8 个项目全部 `report_scope='standalone'` 且无一 `consolidated`（`consol_scope`/`consol_trial`/`companies` 三表 0 行），故 soe↔listed 往返**当前无合法验收对象**。

10.7. WHEN 真实库无合法验收对象 THEN 验收脚本 SHALL 输出「无法验收：本库无可安全切换的项目（原因：<实测计数>）」并以非零退出码或显式 SKIP 标记结束，且 SHALL NOT 用 fixture／新建测试项目冒充通过。

10.8. IF 需要真实验收 THEN SHALL 由用户显式提供或授权一个专用测试项目，且该授权 SHALL 记录在 spec 的 Notes 中（含项目 id 与授权时间）。

## Glossary

| 术语 | 定义 |
|---|---|
| **生产路径** | `execute_conversion()`，由 `POST /note-conversion/execute` 与 `STANDARD_CHANGED` 事件两处调用 |
| **v2 实现** | `convert_disclosure_notes_v2()` / `preview_conversion_v2()`，曾实现 section_id 驱动映射但**生产零调用方**（11 个调用方全是测试）。**🔴 已于 Task 10（2026-08-07）删除**，21 条测试断言迁至 `test_note_conversion_section_mapping_production.py`，删除留证与迁移映射表见 `test_note_conversion_v2_removal.py` 的 `ASSERTION_MIGRATION`。本词条保留仅供理解历史记载，**不代表该实现仍存在** |
| **共有章节** | `common_sections`，两变体都存在的章节，按 `soe_section_id ↔ listed_section_id` 配对 |
| **假 null** | `variant_matrix` 中记为 null 但目标模板其实有落点（只是归在别的章）的条目 |
| **禁止匹配对** | 相似度高但语义不同、必须人工钉死为不可匹配的章节对，典型为「财务报表主要项目注释」↔「母公司财务报表主要项目注释」 |
| **同义两码** | 同一 `row_name` 在 soe 与 listed 下挂**不同** row_code ⇒ 跨变体转换时公式引用**需要**改写。实证 12 条（见需求 3.1） |
| **一码两义** | 同一 row_code 在 soe 与 listed 下是**不同科目** ⇒ 跨变体转换时**禁止**改写。实证 3 条（`BS-016`/`BS-058`/`BS-059`，见需求 3.6） |

### 已裁决事项

1. **归一化匹配用穷举配对清单，不用相似度算法**：0.87 的「合并 ↔ 母公司」对证明相似度阈值无法安全区分。
2. **落盘 diff JSON 与实时计算不一致时以实时为准**，并 WARNING 提示重新生成。
3. **本 spec 不改合并章节与母公司章节的结构**（分别属零回归约束与另一 spec）。
4. **🔴 row_code 映射的方向已由实证钉死（2026-08-05，此前立项写反）**：立项曾把 `BS-013`↔`BS-016`、`BS-053`↔`BS-058`、`BS-043`↔`BS-059` 当作「跨变体同语义映射」要求改写公式，实测三组**全部是「一码两义」**（`BS-016` soe 侧 = 其中：应收股利 / `BS-058` soe 侧 = 交易性金融负债 / `BS-059` listed 侧 = **流动负债合计**），按原写法改写会把明细行指向另一科目、甚至指向合计行。真实需要改写的是另外 **12 条**「同义两码」。**后续会话不得凭 `row_name` 相同就建立映射，必须按 `applicable_standard` 四值逐一比对**。
5. **本 spec 必须在 A（`parent-company-note-chapter-and-sourcing`）之后执行**，理由见 Introduction 的执行顺序依赖段。
6. **真实库验收禁止改动真实项目的 `template_type`**：转换会触发全链重算，属破坏性操作（需求 10.4/10.6）。
