# Requirements Document

## Introduction

附注（disclosure notes）当前有 **496 个章节（占全库 1030 条的 48%）仍是「生成时 legacy 快照」** —— 即 `table_data.sub_table_data` 为空、数据只存在 `rows` / `_tables` 里。这批章节的三个直接后果：

1. **底稿推送不到它们**：`note_sub_table_projector` 只对 `_source in ("workpaper","workpaper_html")` 做投影，legacy 快照走另一条渲染路径 ⇒ 底稿改了附注不跟随（memory 已记「附注根本不跟随底稿内容」）。
2. **无法直接迁移**：把 legacy 快照翻成 `sub_table_data` 后，渲染改由「模板 `columns` + 推送行」决定 —— 而 **216 张待迁移表在模板里根本没有 `columns`** ⇒ 迁过去会降级成 `_needs_columns`（只显示行名、列头全丢），**比 legacy 快照更糟**。
3. **表名撞键丢整表**：`sub_table_data` 以表名为键，而模板侧有 **listed 88 张表名是表头首格泄漏（`项  目` 等）、22 张空名、19 个章节内部重名**，legacy 快照侧有 **54 个章节含重名表** ⇒ 按名建键会互相覆盖。

本 spec 的目标是**按「先补列头、再正名、最后迁移」的顺序把这条链路收口**，让附注真正跟随底稿。

### 🔴 列结构判据真源按章节类型三分（2026-08-05 全量实证，本 spec 最核心的口径）

用户裁决：**附注科目章节的列结构参照该科目底稿的两张披露 sheet，行用动态行**。实证后发现 337 张 `columns==0` 表**并非同一类**，判据真源各不相同，**不可用一套批量规则统一补**：

| 类别 | listed | soe | 合计 | 判据真源 | 归属 |
|------|--------|-----|------|----------|------|
| **① 科目章节**（有底稿披露 sheet 可参照） | 20（7 章） | 41（17 章） | **61** | **底稿 `附注披露信息（上市公司/国企）` sheet**（openpyxl 直读） | 本 spec |
| **② 母公司章**（listed 十六 / soe 十二） | 57 | 36 | **93** | 母公司章源 docx | **A spec** |
| **③ 非科目章节**（无对应底稿披露 sheet） | 163（53 章） | 20（11 章） | **183** | 附注模板 docx（`docs/模版/`） | 本 spec，但**禁止套披露表口径** |

**③ 类是最容易误判的一类**：套期 16 表 / 关联交易情况 13 / 处置子公司 12 / 金融资产转移 12 / 风险管理目标和政策 11 / 现金流量表项目注释 9 / 在合营安排或联营企业中的权益 8 / 分部报告 5 —— 这些章节**压根没有对应的底稿披露 sheet**（它们是准则要求的整体性披露，不挂在某个科目底稿下），其列结构真源只能是附注模板 docx。若按「参照披露表」的口径处理，必然自造列结构。

### 🔴 平台已建立该范式且覆盖约 35 个循环，本 spec 只补缺口

全量扫描实证：**38 个后端结构守卫**（其中 17 个用 openpyxl 直读源 xlsx 做三向比对）+ **40 个前端 `*NoteSubtableContract.spec.ts`** + **42 个 `fix_note_*_structure.py` 幂等脚本**，已覆盖 D1/D2/D3/D4/D5/D6/D7/E1/F1/F2/F3/F4/G5/G7/G 负债与损益/H1/H2/H3/H5/H7/H8/H9/H10/I/J1/J2/K1/K2/K3~K7/K8~K13/L/M/N1/N2/N4/N5 等约 35 个循环。

⇒ **本 spec 不重建范式，只按同一范式补剩余缺口**。① 类中「守卫未覆盖」的真实缺口只有 **18 章**：

- listed 4 章：`五、12 一年内到期的非流动资产` / `五、35 衍生金融负债` / `五、71 现金流量表补充资料` / `五、74 租赁`
- soe 14 章：`八、8 应收资金集中管理款` / `八、13 一年内到期的非流动资产` / `八、45 一年内到期的长期借款` / `八、46 一年内到期的应付债券` / `八、51 优先股永续债等金融工具` / `八、80 每股收益` / `八、81 现金流量表项目注释` / `八、83 股份支付` / `八、84 债务重组` / `八、85 借款费用` / `八、87 租赁` / `八、89 终止经营` / `八、90 分部信息` / `八、91 合并现金流量表相关事项`

### 🔴 动态行现状：平台无 `expandable` 语义，源模板有 6 种可扩标记写法

`row_type` 全量取值域实测 = `data`（listed 2415 / soe 1536）/ `total`（332 / 236）/ `subtotal`（62 / 58）/ `header_label`（62 / 28）/ `unowned`（0 / 1）—— **没有表达「此行可由用户增删」的取值**。而源披露 sheet 里可扩行标记有 6 种写法：`……`（116 处）/ `预留`（36）/ `可改名`（24）/ `可无限量添加行`（23）/ `......`（6）/ `…`（5）。附注 JSON 已 seed 了 90 个省略号行（listed 59 / soe 31），但前端不认它是可扩位，会被当普通空数据行渲染成占位披露行（memory 已记「预置空占位会被推成占位披露行」）。

平台既有的动态行能力散落在前端：`addRow` 865 处 / `ElMessageBox.prompt` 443 处 / `dynamicAdjudicationRows` 共享件 6 处 / `blankRows(` 3 处。**本 spec 只做「模板侧把可扩位标出来」这一层**（新增 `row_type: "expandable"` + 清理误 seed 的占位行），前端动态行交互的接入归各 per-cycle spec。

**与 A/B 两个 spec 的边界（不得重叠）**：

| spec | 负责 |
|------|------|
| **A** `parent-company-note-chapter-and-sourcing` | 母公司章节（listed 十六章 / soe 十二章）的**章节标题、slug、表结构与取数** |
| **B** `soe-listed-note-conversion-correctness` | 国企↔上市**转换**的正确性（`execute_conversion` 空操作、v2 孤儿、diff 数据） |
| **C 本 spec** | **全库**模板 `columns`/`guidance` 覆盖 + 表名唯一化 + legacy 快照迁移 |

**执行顺序依赖**：本 spec 的 Wave 1~2（模板结构修订）**必须在 A 的 Wave 2 之后执行** —— A 会重写 listed 十六章 / soe 十二章共 93 张表的 `columns`、`guidance` 与表名（其中 listed 十六章一章就占 `columns==0` 的 57 张 = 全库缺口的 17%）。若本 spec 先跑，A 的改动会被本 spec 的批量脚本按「全库统一规则」覆盖成与源 docx 不同构的形态。**Wave 3~5（迁移）不依赖 A/B**，但迁移执行（Wave 4）必须在 Wave 1~2 完成后。

**实证基线（全部来自本 spec 立项探针，`docs` 与旧记载不可信）**：

| 维度 | listed | soe | 合计 |
|------|--------|-----|------|
| 模板 sections | 204 | 188 | 392 |
| 模板 tables | 513 | 296 | 809 |
| `columns == 0` | 240 (46%) | 97 (32%) | **337** |
| `guidance` 空 | 237 | 96 | **333** |
| 表名为空 | 22 | 0 | 22 |
| 表名疑似表头泄漏 | 88 | 0 | 88 |
| 含重名表的 section | 19 | 1 | 20 |

**🔴 337 张 `columns==0` 表按列结构真源分三类（本 spec 最关键的实证，决定各自怎么补）**：

| 类别 | listed | soe | 列结构真源 | 归属 |
|------|--------|-----|-----------|------|
| **① 科目章节**（有对应底稿披露 sheet） | 20（7 章） | 41（17 章） | **底稿两张披露 sheet**（openpyxl 直读） | 本 spec |
| **② 母公司章** | 57 | 36 | 母公司章源 docx | **A spec，本 spec 排除** |
| **③ 非科目章节**（无对应披露 sheet） | 163（53 章） | 20（11 章） | 附注模板 docx | 本 spec，但**不套披露表口径** |

③ 类占 listed 缺口的 68%，是最大一块，且**不能按「参照披露表」补** —— 这批章节（套期 16 / 关联交易情况 13 / 处置子公司 12 / 金融资产转移 12 / 风险管理目标和政策 11 / 现金流量表项目注释 9 / 在合营安排或联营企业中的权益 8 / 分部报告 5 …）在 `backend/wp_templates/**` 全库 351 个模板里没有对应披露 sheet。

**① 类的真实缺口只有 18 章**（已排除守卫已覆盖的部分）：

- listed 4 章：`五、12 一年内到期的非流动资产` / `五、26 无形资产` / `五、28 商誉` / `五、31 其他非流动资产` / `五、35 衍生金融负债` / `五、71 现金流量表补充资料` / `五、74 租赁`（其中无形资产/商誉已被 `test_note_i_cycle_structure.py` 部分覆盖）
- soe 14 章：`八、8` / `八、13` / `八、45` / `八、46` / `八、51` / `八、80` / `八、81` / `八、83` / `八、84` / `八、85` / `八、87` / `八、89` / `八、90` / `八、91`

**平台已建立的「列参照披露表」范式覆盖面（勿重造）**：

| 资产 | 数量 | 说明 |
|------|------|------|
| 后端结构守卫 `test_note_*_structure.py` | **38** | 其中 **17 个 openpyxl 直读源 xlsx** 做「源 sheet ↔ 模板 headers ↔ 同步 columns」三向比对 |
| 前端子表契约 `*NoteSubtableContract.spec.ts` | **40** | 共享 helper `_disclosureSubtableContract.helper.ts` 跑 P1~P6 |
| 幂等结构脚本 `fix_note_*_structure.py` | **42** | 共享 kit `_note_structure_kit.py`（`rule`/`run_section`/`apply_plan`/`flat_columns`/`two_period_columns`） |
| 覆盖循环（反推） | ~35 | D1 D2 D3/D5/D6/D7 D4 E1 F1~F4 G5 G7 H1~H3 H5 H7~H10 J1 J2 K1~K13 L* M* N1 N2 N4 N5 |

**动态行现状**：模板 `row_type` 取值域实测 = `data`（listed 2415 / soe 1536）/ `total`（332 / 236）/ `subtotal`（62 / 58）/ `header_label`（62 / 28）/ `unowned`（0 / 1），**没有可扩行语义**。而源披露 sheet 的可扩位标记有 6 种写法共 210 处（`……` 116 / `预留` 36 / `可改名` 24 / `可无限量添加行` 23 / `......` 6 / `…` 5）；附注 JSON 已 seed 了 90 个省略号行（listed 59 / soe 31）但前端不认它是可扩位 —— 见 Requirement 11。

| 真实库维度 | 值 |
|------------|-----|
| `disclosure_notes` 有效行 | 1030（5 个项目） |
| 已有 `sub_table_data` | 191 |
| **legacy 快照章节** | **496**（listed 92 / soe 404） |
| 其中有 `_tables` | 391 |
| 其中只有顶层 `rows` | 105 |
| legacy 快照表总数 | 892 |
| 可迁移表（模板有该表名且有 columns） | 340 |
| **模板有该表但 `columns==0`** | **216** ← 迁移前置闸 |
| **模板里没有该表名** | **336** |
| 其中「表数相同、纯表名漂移」的 section | **116** ← 可自动化 |
| section 全部表可迁移 | 120 |
| section 被阻塞 | 271 |
| legacy 侧含重名表的 section | 54 |

> 与 memory 旧记载（572 章节 / 982 表 / 950 缺 columns）的差异说明：归档 spec `disclosure-note-follow-actual-content` 的 Task 8 已迁过 133 个章节，故基数从 572 降到 496；「950 缺 columns」是**全部待迁移表**口径，本 spec 的 216 是**按表名 join 到模板后仍缺列头**的口径，两者不可直接比较。

## Requirements

### Requirement 1: 判据真源与探针可复算

**User Story:** 作为平台维护者，我需要本 spec 的每个「现状缺陷」数字都能由一条可重跑的只读探针复算出来，避免像 A/B 两个 spec 那样凭印象写现状导致判据方向写反。

#### Acceptance Criteria

1.1. WHEN 运行 `backend/scripts/diagnose/diagnose_note_columns_and_legacy.py --templates` THEN 系统 SHALL 输出模板两侧的 sections / tables / `columns==0` / `guidance` 空 / 空表名 / 表头泄漏 / 重名 section 七项计数，且与本文档 Introduction 的表格逐项相等。
1.2. WHEN 加 `--db` 参数（只读连库）THEN 系统 SHALL 输出真实库九项计数（有效行/已有 sub_table_data/legacy 章节/有 `_tables`/仅 `rows`/legacy 表总数/可迁移/模板缺 columns/模板无此表名）。
1.3. WHEN 加 `--out <path>` THEN 系统 SHALL 把结构化结果落盘为 JSON，供守卫与后续任务复用，且脚本自身用 `Path.write_text(..., encoding="utf-8")` 写盘（不依赖控制台编码）。
1.4. 探针 SHALL 全程只读（无 UPDATE / INSERT / DELETE），且 `--db` 不可用时 SHALL 降级为仅模板侧输出并明确报告「DB 未连接」，不得静默返回 0。
1.5. 探针输出 SHALL 区分「表头泄漏」与「空表名」两类（前者 = 表名等于该表 `headers[0]` 或属常见表头词表；后者 = 表名为空串），不得合并计数。
1.6. 探针的「表头泄漏」判据 SHALL 复用 `migrate_legacy_note_snapshots._name_is_meaningful`（已有真源），不得另写一份判据。

### Requirement 2: 模板 `columns` 覆盖补齐（判据真源按章节类型三分）

**User Story:** 作为审计师，我需要附注每张表都有明确的列头定义，且科目章节的列结构必须与该科目底稿披露表一致，这样底稿推送过来才对得上落点，而不是只剩行名或凭空多出父表头。

#### Acceptance Criteria

2.1. WHEN 幂等脚本 `fix_note_columns_coverage.py --apply` 执行完成 THEN 本 spec 作用域内（① 类 61 张 + ③ 类 183 张 = **244 张**）模板 `columns == 0` 的表数 SHALL 为 0；母公司章 93 张按 R10.2 排除。
2.2. **① 类（科目章节）的列定义 SHALL 由 openpyxl 直读该科目底稿的披露 sheet 得出**，不得从附注 JSON 的 `headers` 反推。落法：脚本按 `wp_code` 定位 `backend/wp_templates/` 下的源 xlsx（**权威目录，`基础数据/` 是已落后的参考副本**）→ 定位 `附注披露信息（上市公司/国企）` sheet（21 种括号与后缀写法，须归一）→ 按小节切分 → 逐表取末级表头。
2.3. **③ 类（非科目章节）的列定义 SHALL 由附注模板 docx（`docs/模版/` 两份）得出**，`SHALL NOT` 套用任何底稿披露 sheet 的列结构（这些章节无对应底稿披露 sheet，套用即自造）。
2.4. WHEN 某表在源真源中找不到对应表头 THEN 脚本 SHALL 跳过该表并记入 `--check` 的欠账清单（含「找不到的原因」），不得回退到「按 JSON `headers` 补」这条捷径 —— JSON `headers` 本身可能是 md 重建压扁的产物。
2.5. 每张补齐的表 SHALL 显式表态两级结构：单级表头的表每列带 `flat: true`；两级表头的表每个数据列带 `group`（父表头名），rowspan=2 的独立列**不给** `group`（混合分组）。
2.6. 补齐的 `columns[].label` SHALL 逐字取自真源末级表头（去掉 HTML 标签与首尾空白后，**保留中间空格** —— 源模板的 `项  目`/`合 计` 是有意的字面）；`key` SHALL 与 `headers` 同序对应；已有 `columns` 的表若 `key` 已被前端映射消费，SHALL NOT 改 `key`（只改 `label`/`group`）。
2.7. WHEN 源真源列数与 JSON `headers` 长度不一致 THEN SHALL 以**源真源为准**并在 `--check` 报告「JSON headers 被压扁 N 列」，同时把该表登记进「需 per-cycle spec 复核行集」清单（行集不在本 spec 范围，见 R10.1）。
2.8. 三级表头（源真源出现三层）SHALL 按平台既有范式把顶层维度提到表名拆两张表（`{表名}` + `{表名}（续：xxx）`），`ColumnDef.group` 只承载中间层 —— `group` 含 `/` 会让前端 `activeTableColumns` 渲染崩。
2.9. 脚本 SHALL 支持 `--dry-run`（默认）/ `--apply` / `--check`，`--check` 在零欠账时 exit 0；连续两次 `--apply` 结果逐字节一致。
2.10. 脚本 SHALL 有 round-trip 自检：`json.dumps` 后若不能逐字复现原文（除本次变更外）则 exit 2，防止全文件重排与并发冲突。
2.11. 脚本 SHALL **排除**母公司章节（listed 十六章 / soe 十二章），排除由 `section_id` 前缀判定并在 `--check` 中如实报告「已排除 93 张（归 A spec）」。
2.12. 脚本控制台输出 SHALL 只用 ASCII 标记（`[OK]` / `[ERR]`），不得含 emoji（Windows GBK 控制台会在写盘之后抛 `UnicodeEncodeError`，让人误判 apply 失败）。
2.13. **② 类（已被 per-cycle 守卫覆盖的科目章节）SHALL 不由本 spec 批量脚本改动** —— 平台已有 38 个后端结构守卫 / 40 个前端子表契约 / 42 个幂等脚本覆盖约 35 个循环，本 spec 只在 `--check` 中报告它们的 `columns` 现状作为交叉验证；若发现某循环守卫已绿但 `columns` 仍为 0，SHALL 记入 Notes 并注明归属该循环的 per-cycle spec。
2.5. 脚本 SHALL 支持 `--dry-run`（默认）/ `--apply` / `--check`，`--check` 在零欠账时 exit 0。
2.6. 脚本 SHALL 有 round-trip 自检：`json.dumps` 后若不能逐字复现原文（除本次变更外）则 exit 2，防止全文件重排与并发冲突。
2.7. 脚本 SHALL **排除**母公司章节（listed 十六章 / soe 十二章）—— 它们由 A spec 的 `fix_note_parent_company_structure.py` 负责；排除清单 SHALL 由章节 `section_id` 前缀判定并在 `--check` 中如实报告「已排除 N 张（归 A spec）」。
2.8. 脚本控制台输出 SHALL 只用 ASCII 标记（`[OK]` / `[ERR]`），不得含 emoji（Windows GBK 控制台会在写盘之后抛 `UnicodeEncodeError`，让人误判 apply 失败）。

### Requirement 3: 模板 `guidance` 覆盖补齐

**User Story:** 作为审计助理，我需要每张附注表的页签上有编制提示，告诉我这张表该填什么、口径是什么。

#### Acceptance Criteria

3.1. WHEN 补齐脚本执行完成 THEN 全库模板 `guidance` 为空的表数 SHALL 为 0（当前 333），母公司章节除外（归 A spec）。
3.2. `guidance` 内容 SHALL 只允许三种来源：①源模板红字/括注原文 ②准则或财会文号条款 ③以「勾稽：」前缀标注的工具提示。**禁止自造披露口径说明**。
3.3. WHEN 某表找不到上述任一来源 THEN 脚本 SHALL 写入以「本表编制口径待补充，参见」开头的最小提示（指向该章节的 `text_sections` 或源模板 sheet 名），不得留空也不得编造内容。
3.4. `guidance` SHALL 为纯文本，不得含 markdown 粗体标记（`**`）—— 平台级脚本 `fix_note_bold_markers.py` 会剥离它，两个脚本互相打架会让同一 guidance 一天内被改两次。
3.5. `guidance` SHALL 不含 HTML 标签（`<br/>` 等）。

### Requirement 4: 表名唯一化与表头泄漏正名

**User Story:** 作为平台维护者，我需要每个章节内的表名唯一且是业务表名，因为 `sub_table_data` 以表名为键 —— 重名会让两张表互相覆盖丢整表，表头泄漏名会让底稿推送找不到落点。

#### Acceptance Criteria

4.1. WHEN 正名脚本 `fix_note_table_names.py --apply` 执行完成 THEN 全库模板不再有空表名（当前 22）。
4.2. 执行完成后每个章节内的表名 SHALL 唯一（当前 listed 19 个 + soe 1 个章节存在重名）。
4.3. 表头泄漏名（当前 88 张）SHALL 改为业务表名，命名来源优先级：①该章节 `text_sections` 里对应的 `（N）xxx` / `#### xxx` 标题 ②源模板 sheet 的表标题 ③`{section_title}（表N）` 兜底。
4.4. 每处改名 SHALL 在该表写入 `legacy_aliases: [旧名, ...]`，供 legacy 快照迁移与既有 `sub_table_data` 按旧名回落匹配（数据零丢失红线）。
4.5. 改名 SHALL 走 `_note_structure_kit.rule(aliases=...)` 机制，**不得进 `drop_tables`** —— `drop_tables` 在 `apply_plan` 之前执行，会连带把行删掉。
4.6. WHEN 改名会与该章节内已有表名冲突 THEN 脚本 SHALL 追加 `（表N）` 后缀而不是覆盖，并在 `--check` 报告该冲突。
4.7. 脚本 SHALL 同步扫描前端 `*NoteSectionMap.ts` 与 `X_*_SUBTABLE` 常量，凡引用被改名表的位置 SHALL 在 `--check` 输出为「前端待同步」清单（改名后不同步会立刻产生孤儿子表）。
4.8. 母公司章节的 6 处重名/空名 SHALL 排除（归 A spec 的 Task 4）。

### Requirement 5: 迁移前置闸不可绕过

**User Story:** 作为审计师，我不希望「迁移」把一张有表头的表变成只有行名的表 —— 那比不迁移更糟。

#### Acceptance Criteria

5.1. `migrate_legacy_note_snapshots.py` 的 `--require-columns` SHALL 保持默认开启，且**不得**提供关闭它的快捷参数别名。
5.2. WHEN 某章节任一表在模板里 `columns` 为空 THEN `select_migratable` SHALL 把该章节整体排除并计入 `skipped_no_columns`，不得部分迁移。
5.3. WHEN 运行 `--apply` 而全库仍有 `columns == 0` 的表 THEN 脚本 SHALL 在开始写库前打印警告并报告受影响章节数，让执行者知道本轮会跳过多少。
5.4. 守卫 SHALL 有一条反向自检：构造一张 `columns` 为空的模板表，`select_migratable(require_columns=True)` 必须排除它；若它被选中则守卫打红。

### Requirement 6: 新增 `name_drift` 迁移类别

**User Story:** 作为平台维护者，我需要把「表数相同、legacy 表名全是表头泄漏、模板表名全是正式业务名」这 116 个章节自动化迁移，而不是全部退回人工。

#### Acceptance Criteria

6.1. `build_note_plan` SHALL 新增 `kind = "name_drift"`，判定条件全部满足才成立：①legacy `_tables` 数量 == 模板 tables 数量 ②legacy 每个表名都**不是**业务名（`_name_is_meaningful` 为 False）或不在模板名集合中 ③模板每个表名都是业务名 ④legacy 与模板的表名集合交集为空。
6.2. `name_drift` SHALL 按**位置**对齐（第 i 张 legacy 表 → 第 i 个模板表名），并在 plan 的 `reason` 中写明「按位置对齐（表名漂移）」。
6.3. `name_drift` SHALL 与既有 `positional` 类别互斥 —— 若 legacy 表名中存在任何一个能在模板中按名命中的，则判 `positional` 或 `by_name`，不判 `name_drift`。
6.4. `name_drift` SHALL 计入 `ALWAYS_MIGRATABLE_KINDS`（与 `by_name`/`single_row` 同级默认可迁移），因为它的对齐依据是「表数相等 + 名集合完全无交集」，比 `positional` 的「表数相等但部分名能命中」更确定。
6.5. WHEN legacy 表数与模板表数不等 THEN SHALL NOT 判 `name_drift`（当前 154 个有 unmatched 名的章节里，38 个表数不等 → 仍走 manual）。
6.6. 守卫 SHALL 用替身覆盖四种边界：纯漂移必判 `name_drift` / 有一个名能命中必不判 / 表数不等必不判 / 模板名本身是表头泄漏时必不判。

### Requirement 7: 破坏性迁移安全闸

**User Story:** 作为审计师，我需要迁移可回滚、失败可隔离，不能出现「一半迁了一半没迁」的中间状态。

#### Acceptance Criteria

7.1. `--apply` SHALL 要求同时传 `--confirm`，否则拒绝执行并提示。
7.2. 每个章节的写入 SHALL 包在独立 savepoint（`async with db.begin_nested()`）+ per-note `try/except`，单条失败记入 failures 后继续，最外层一次 commit。
7.3. 迁移前的原始 `table_data` SHALL 备份到 `table_data._template_lineage._legacy_backup`（**不落 `template_lineage` 列** —— 该列已被 `group_note_baseline_service` 当 list 用、`note_auto_trim` 当 dict 用，会冲突）。
7.4. `--rollback` SHALL 能按备份逐条还原，且往返（迁移→回滚）后 `table_data` 的结构深度与行数 SHALL 与迁移前相等。
7.5. WHEN 某章节已迁移过（`_already_migrated`）THEN SHALL 跳过并计入 `skipped_already`，`--apply` 重跑 SHALL 幂等。
7.6. 写库 SQL SHALL 用 `CAST(:td AS jsonb)` + `json.dumps(td, ensure_ascii=False, default=str)`，**不得**用 `sa.type_coerce(td, sa.JSON)`（asyncpg 下抛 `Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'`，且替身单测查不出）。

### Requirement 8: 真实库迁移执行与验收

**User Story:** 作为审计师，我需要看到迁移后附注真的能跟随底稿，而不只是脚本报告「成功 N 条」。

#### Acceptance Criteria

8.1. WHEN Wave 1~2 完成后运行 `--apply --confirm` THEN 迁移成功的章节数 SHALL ≥ 120（Wave 1~2 前的 `sections_all_migratable`），且失败数 SHALL 为 0。
8.2. 迁移后 legacy 快照残留章节数 SHALL 严格小于迁移前（当前 496），并在报告中给出「残留原因分类」（模板无该章节 / 表数不等 / 重名未解 / 只有 rows 且模板多表）。
8.3. 行数守恒 SHALL 逐章节校验：迁移后 `sub_table_data` 各表行数之和 == 迁移前 `_tables` 各表行数之和（减去被 `_strip_header_labels` 剔除的 `header_label` 假行数）。
8.4. **顶层 `rows` 与 `_tables[0].rows` 逐字节相同**时 SHALL 判定为 legacy 冗余副本并只迁 `_tables`（memory 已实证 113/113 相同）；若两者不同 THEN SHALL 转 manual 不自动迁移。
8.5. 抽样 ≥3 个已迁移章节 SHALL 用 postgres 只读验证三消费方一致：`project_sub_tables()` 投影结果 / `DisclosureEditor` 读到的列头 / Word 导出的两级表头，三者列数与列名相同。
8.6. WHEN 验收在真实库无法完成（如无符合条件的章节）THEN SHALL 明确报告「无法验收及原因」，**禁止用 fixture 冒充真实库验收**。
8.7. 迁移执行 SHALL 在报告中列出每条被迁章节的 `note_section` + `kind` + 表数 + 行数，供人工抽查。

### Requirement 9: 平台守卫与 CI

**User Story:** 作为平台维护者，我需要这次修好的三件事（columns 覆盖 / 表名唯一 / legacy 残留）不会被下一次 md 重建或并发会话打回去。

#### Acceptance Criteria

9.1. 守卫 `backend/tests/test_note_columns_coverage.py` SHALL 断言全库模板 `columns == 0` 的表数为 0（母公司章节按 A spec 的排除清单豁免，且豁免清单只许变短）。
9.2. 守卫 SHALL 断言每张表的 `columns` 必须表态 `flat` 或 `group`（三态：`None` = 未声明会触发前缀推断，是缺陷）。
9.3. 守卫 SHALL 断言全库模板无空表名、每章节内表名唯一、无表头泄漏名（判据复用 `_name_is_meaningful`）。
9.4. 守卫 SHALL 断言 `guidance` 无空、无 `**`、无 HTML 标签。
9.5. 守卫 SHALL 有 legacy 残留基线常量 `LEGACY_SNAPSHOT_BASELINE`，实测值必须 ≤ 基线（只许降不许升），并配一条「基线不得被上调」的说明断言。
9.6. 每条守卫 SHALL 配反向自检（构造违规替身必须打红），且读源码型断言必须先 `stripComments()` 并断言原文确实含被禁字样（防正则失效变成空转）。
9.7. `.github/workflows/governance-checks.yml` SHALL 新增 job `note-columns-and-legacy-closure`，跑上述守卫 + 三个幂等脚本的 `--check`。
9.8. 守卫 SHALL NOT 连库（读模板 JSON 即可），以便进 CI。

### Requirement 10: 范围边界

**User Story:** 作为平台维护者，我需要本 spec 的范围被显式钉死，避免与 A/B 两个 spec 互相覆盖同一批文件。

#### Acceptance Criteria

10.1. 本 spec SHALL NOT 修改任何表的 `rows`（行集）—— 行集修订属各 per-cycle spec 与 A spec 的职责；脚本对 `rows` 一律传 `None`。
10.2. 本 spec SHALL NOT 修改母公司章节（listed 十六章 / soe 十二章共 93 张表）的任何字段 —— 归 A spec；排除由 `section_id` 前缀判定并在 `--check` 中报告排除数。
10.3. 本 spec SHALL NOT 触碰国企↔上市转换链路（`note_conversion_service` / `note_template_diff` / `note_soe_listed_diff.json`）—— 归 B spec。
10.4. 本 spec SHALL NOT 改动任何真实项目的 `template_type` / `applicable_standard_v2`（破坏性操作，需用户显式授权）。
10.5. 本 spec SHALL NOT 新增或翻转任何灰度开关（`DISCLOSURE_NOTE_FORMULA_ENABLED` 等 5 个默认关闭的开关不在范围内）。
10.6. 本 spec SHALL NOT 修改 `_infer_groups_from_headers` 的前缀推断逻辑 —— 补齐 `columns` 后它自然不再被触发；改它会波及 300+ 未迁移章节。
10.7. WHEN 执行过程中发现属于 A/B 或某 per-cycle spec 的缺陷 THEN SHALL 只记入 tasks.md 的 Notes 并注明归属，不得顺手修。
10.8. 本 spec SHALL NOT 对 ③ 类（非科目章节，listed 163 张 / soe 20 张）套用「参照底稿披露表」的口径 —— 这批章节（套期 16 / 关联交易 13 / 处置子公司 12 / 金融资产转移 12 / 风险管理 11 / 分部报告 5 等）在 `backend/wp_templates/**` **没有对应披露 sheet**，其列结构真源只能是附注模板 docx。
10.9. 本 spec SHALL NOT 改动 `note_sub_table_projector` 的投影逻辑与 `row_type` 已有五个取值（`data`/`total`/`subtotal`/`header_label`/`unowned`）的语义 —— Requirement 11 只做 additive 新增。

### Requirement 11: 动态行标记（additive）

**User Story:** 作为审计师，我需要附注表里源模板留的可扩位（`……` / `预留` / `可无限量添加行`）在界面上是「可增行」的位置，而不是一行看不懂的空数据行或一个假占位标签。

#### Acceptance Criteria

11.1. 源披露 sheet 的可扩行标记 SHALL 按实测六种写法识别，判据为**声明式词表**（单一真源）：`……`（116 处）/ `预留`（36）/ `可改名`（24）/ `可无限量添加行`（23）/ `......`（6）/ `…`（5）。词表 SHALL 落在一个共享模块内，扫描脚本与守卫共用，禁止各写一份。
11.2. 模板 JSON SHALL 新增 `row_type: "expandable"` 取值，语义 = 「该位置是源模板留的可扩行，前端渲染为增行入口而非数据行」。这是**第 6 个取值**，additive 新增，既有五个取值的语义与行为逐字不变。
11.3. 当前 JSON 已 seed 的省略号行（listed 59 / soe 31，共 90 行）SHALL 逐行核对源真源后改标 `expandable`；无法在源真源找到对应可扩位的 SHALL 保持原 `row_type` 并记入 Notes（宁缺勿造）。
11.4. `note_sub_table_projector` 与 Word 导出 SHALL 把 `expandable` 行视为**零可见内容**（不渲染成数据行、不参与合计），行为等价于当前对 `header_label` 的处理；投影出的行数 SHALL 因此减少 90 行以内。
11.5. 前端 SHALL NOT 在本 spec 内新增增行 UI —— 平台已有 `addRow`（865 处）+ `ElMessageBox.prompt`（443 处）+ `dynamicAdjudicationRows`（6 处）三套动态行范式，本 spec 只提供 `expandable` 标记这一数据侧前提，UI 接线归各 per-cycle spec。
11.6. 守卫 SHALL 断言：`row_type` 取值域恰为六个（新增即打红）/ 词表非空且每个词在源真源中确实命中 ≥1 次（反向自检，防词表失效空转）/ `expandable` 行不参与合计。
11.7. WHEN 某源可扩位在附注 JSON 里根本没有对应行 THEN SHALL NOT 凭空插入 `expandable` 行 —— 插行属行集修订，归 Requirement 10.1 排除范围。

### Requirement 12: `text_sections` 裸表名与 md 重建假行卫生

**User Story:** 作为审计师，我不希望附注正文里凭空多出「只有一个表名的段落」，也不希望表格里多出一行内容等于表头文字的空数据行 —— 这两样都是 md 重建残留，会直接出现在 Word 交付件里。

> **判据前提（2026-08-08 实证，不得凭「header_label 已是零可见」推断）**：`note_word_exporter._render_table` **不读 `row_type`**，把 `rows` 全部渲染成可见行 ⇒ `header_label` 假行在 Word 交付件里**是可见的一行**（label 列显示表头文字、数值列全空）。故本 Requirement 是真实交付件缺陷修复，不是化妆品。
>
> **与 Requirement 10.1 的关系**：10.1 禁止的是**行集修订**（改变披露行的业务集合）。本 Requirement 只删「可由该表 `headers` 证明为表头文字残留」的行（判据见 12.3），不增行、不改任何业务行的 label/值 ⇒ 属残留清理，是 10.1 的显式例外，且由 12.3 的 fail-closed 判据把两者区分开。

#### Acceptance Criteria

12.1. WHEN 幂等脚本 `fix_note_text_hygiene.py --apply` 执行完成 THEN 作用域内（排除母公司章）`text_sections` 里仍会被当正文渲染的裸表名段落数 SHALL 为 0。判定 SHALL 复用 `_note_structure_kit.find_bare_table_name_paragraphs` / `is_title_paragraph`（与后端 `disclosure_engine._is_table_title_paragraph` 同口径），不得另写一份。

12.2. 裸表名段落 SHALL 通过加 `#### ` 前缀转为标题（复用 `_note_structure_kit.titleize_text_sections`），SHALL NOT 删除该段落 —— 段落文字本身是章节结构信息。

12.3. **`header_label` 假行删除 SHALL fail-closed**：仅当该行 `label` 满足①归一化（去全部空白）后与该表 `headers` 中任一项相等，或②含 HTML 标签（`<br/>` 等）之一时才删除。两条都不满足的 SHALL 跳过并计入 `--check` 的「无法证明」清单，绝不删除 —— 平台既有语义里 `header_label` 也用于合法的表内分组标题行（`note_formula_derivation` 的求和范围含 header_label、`note_shared_table_segments` 用它判无主行），无判据地批量删会删掉业务行。

12.4. 脚本 SHALL NOT 删除标记为可扩位的行（label 命中 Requirement 11.1 词表的行）—— 那些行归 Requirement 11 标 `expandable` 保留。两条处置口径互斥且不得同时作用于同一行。

12.5. 脚本 SHALL 排除母公司章节（Requirement 10.2）；`registry_covered` 章节的 `text_sections` 标题化**允许执行**（纯文本卫生，不触碰 `tables`/`columns`/`rows`），但 SHALL 在 `--check` 中报告并断言「无任何 per-cycle 幂等脚本对该章节声明 `text_sections=`（整表替换语义）」，否则跳过该章节。

12.6. WHEN 删行改变了任何「多段共享表」的行序 THEN 派生清单 `backend/data/note_shared_table_segments.json` SHALL 由 `gen_note_shared_table_segments.py --write` 重生成，且 `test_note_shared_table_segments.py` SHALL 全绿 —— 该清单按表名与行序派生，Wave 2 已实测它会漂移。

12.7. 脚本 SHALL 支持 `--dry-run`（默认）/ `--check` / `--apply` / `--variant`，`--check` 零欠账时 exit 0；连续两次 `--apply` 结果逐字节一致；round-trip 自检不能逐字复现原文即 exit 2；控制台输出只用 ASCII 标记。

## Glossary

| 术语 | 含义（本 spec 内的精确定义） |
|------|------------------------------|
| **legacy 快照** | `disclosure_notes.table_data` 满足「`sub_table_data` 缺失/非 object/为 `{}`」**且**「有 `rows` 或 `_tables`」的记录。这是附注生成时写入的静态快照，不随底稿变化。真实库实测 **496 条 / 1030 条（48.2%）**。 |
| **已迁移形态** | `table_data.sub_table_data` 为非空 object 且 `_source in ('workpaper','workpaper_html')`，由 `note_sub_table_projector.project_sub_tables()` 读时投影渲染。实测 191 条有 `sub_table_data`、194 条 `_source=workpaper`。 |
| **`columns` 缺失** | 模板 JSON 的 `sections[].tables[].columns` 不存在或长度为 0。实测 listed **240/513（46%）**、soe **97/296（32%）**。缺失时投影降级为 `_needs_columns`（只显示行名，两级表头与金额格式全丢）。 |
| **表头首格泄漏名** | 表名等于该表 `headers[0]`，或去空格后落在 `{项目, 序号, 名称, 类别, 组合, 存货种类}` 集合内。这是 md 重建把表头首格当表名写入的产物。实测 listed **88 张**（soe 0 张）。 |
| **空名表** | `tables[].name` 为空串或全空白。实测 listed **22 张**（soe 0 张）。因表名是 `sub_table_data` 的键，空名表在推送/迁移时互相覆盖丢整表。 |
| **重名 section** | 同一 section 内存在两张同名表。实测 listed **19 个 section**、soe **1 个**（`十二、其他应收款` 的 `其他应收款（续）债务人名称`×4）。 |
| **迁移类别** | `migrate_legacy_note_snapshots.build_note_plan()` 输出的 `kind`：`by_name`（表名全部业务名且无重名且全在模板中，安全）/ `single_row`（只有顶层 rows 且模板恰好 1 张表，安全）/ `positional`（表数相等但名字对不上，须人工抽样，`--include-positional` 才纳入）/ `manual`（表数不等或模板无此章节，不迁移）。 |
| **纯表名漂移** | legacy 快照与模板**表数相同**、但快照表名全是表头首格泄漏而模板已是正式表名。实测 **116 个 section**。这批可归入 `positional`，是本 spec 最大的可兑现存量。 |
| **可迁移表 / 阻塞表** | 按「模板有同名表 且 该表 `columns` 非空」判定。实测 892 张 legacy 表中 **340 张可迁移**、**216 张模板有表但无 columns**、**336 张模板无此表名**。section 级：**120 个全部可迁移**、**271 个被阻塞**。 |
| **`flat` 表态** | `ColumnDef.flat=true` 表示显式声明单级表头，使 `_extract_column_groups` 返回 `[]` 而不走 `_infer_groups_from_headers` 前缀推断。**seed 路径与推送载荷两处都要加**，只加一处仍会被推出凭空父表头。 |
| **A spec** | `parent-company-note-chapter-and-sourcing`（母公司附注章节与取数）。其作用域 = listed 十六章 57 表 + soe 十二章 36 表，本 spec 必须排除。 |
| **B spec** | `soe-listed-note-conversion-correctness`（国企↔上市转换正确性）。与本 spec 无文件重叠。 |
