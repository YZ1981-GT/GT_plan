# Requirements Document

## Introduction

附注同步（`sync_from_workpaper`）当前的合并粒度是**表级**：按子表名浅合并，同名表整表覆盖、未推送的表保留。
这个粒度对「各循环各推自己的表」够用（H4→H2 工程物资、H6→H1 固定资产清理都靠此绕过），
但对**一张表内按科目分段**的跨循环共享表完全无解 —— 任何单循环推该表都会整表覆盖，
把他循环段落与审计师在附注模块手填的数据一起清掉。

E1 spec（`e1-four-table-extraction-and-disclosure-alignment` Task 13）因此被迫按选项 A 收口：
外币章节只补列元数据、**不接推送**，底稿录的外币数据需人工转录到附注。用户 2026-08-02 裁决**治本**。

**受益面实测（扫全库两份 note_template）**：共 805 张表里有 **29 张是多段共享表**
（`listed` 23 张 / `soe` 6 张 —— 判据：同一张表的 `rows[]` 中出现 ≥2 个不同的 `report_row_code`），
横跨 E/D/F/H/K/L/N 七类循环。代表性表：

| 章节 | 表 | 段（`report_row_code`） | 涉及循环 |
|------|----|---------------------|---------|
| listed `五、73` / soe `八、92` | 外币货币性项目 | listed 3 段 `BS-002` `BS-006` `BS-061`（16 行）/ soe 5 段 + `BS-031` `BS-062`（25 行） | E1 / D2 / K / L |
| listed `五、32`（+「续：」表） / soe `八、93` | 所有权**或**使用权受到限制的资产（soe 用字为「所有权**和**使用权」） | listed 6 段 `BS-002` `BS-005` `BS-006` `BS-010` `BS-028` `BS-032` / soe 7 段（`BS-008` 替 `BS-010`、多 `BS-029`） | E1 / D1 / D2 / F2 / H1 / H2 / H3 |
| listed `五、30` / soe `八、31` | 未经抵销的递延所得税资产和递延所得税负债（+「以抵销后净额列示」表） | 2 段：`BS-036` `BS-067` | N1 / N3 |
| listed `五、71` | 现金流量表补充资料 · 资产负债表中的列报项目和相关信息 | 3 段：`BS-045` `BS-041` `BS-050` | K / L |
| soe `八、81` | 现金流量表项目注释 · 筹资活动产生的各项负债的变动情况 | 4 段：`BS-031` `BS-061` `BS-062` `BS-063` | K / L |
| soe `八、91` | 合并现金流量表相关事项 · 资产负债表中的列报项目和相关信息 | 3 段：`BS-045` `BS-031` `BS-037` | K / L |
| listed `十四、分部报告` | 本期或本期期末 / 上期或上期期末 | 2 段：`IS-001` `IS-002` | D4 / F5 |

**清单实测另暴露两处真实脏数据**（本 spec 只保证不被误用，不修）：
- listed 风险管理有一张表段序为 `BS-041 / BS-002 / BS-041` —— **同一 `row_code` 出现两次**。
  取段只能取**首个**（合并两段会跨过中间的 `BS-002` 段把他人行卷进来）。
- listed 风险管理有一张表 `name=""`（**空表名**）。空表名无法作为 `sub_table_data` 的键，
  段查询必须拒绝它。
- `三、` 章的 `section_number` 是 md 重建的 **10 字符截断值**（`三、重要会计政策、会`），
  与 memory 已记的截断现象一致 —— 引用时必须逐字取真源，不可「补全」。

**🔴 章节号在两份模板间会撞号**：实测 20 个章节号同时存在于两份模板，其中 **13 个标题不同**
（如 `八、1` listed = 政府补助 / soe = 货币资金；`五、42` listed = 其他应付款）。
故「章节号 → 模板」不可推导，变体必须由载荷的 `current_standard` 决定（见 Requirement 2.6）。

**关键既有资产**：模板的**段首行已经带 `report_row_code` + `account_codes`**
（实测 listed 2888 行中 95 行带 `report_row_code`、soe 1879 行中 26 行带），
即「段的归属」在模板里**已经声明好了**，本 spec 不需要新造一套段标识，只需要读它。

同一根因还有第二个受害面：**`text_content` / `_note_texts` 是整体替换**
（`note.text_content = formatted_texts`，无 `_note_texts` 时置 `None`）。
多循环共章节时（memory 已实证 G2/G3/K1 共用 `五、8`/`八、9`，三方都开了自动同步）
后同步方会把前者录的说明整体覆盖。子表已是浅合并、文本却不是，属同一粒度缺陷。

## Requirements

### Requirement 1: 行级合并的载荷契约

**User Story:** 作为底稿开发者，我要能声明「本次只负责这张表的某一段行」，让附注同步只替换我这一段、保留他人段落。

#### Acceptance Criteria

1.1. WHEN 底稿载荷在 `sub_table_data` 内提供元数据键 `_row_scope`（形如 `{表名: {"owner_row_code": "BS-002"}}`）THEN 服务端 SHALL 对该表走**行级合并**而非整表覆盖
1.2. WHEN 载荷未提供 `_row_scope` THEN 服务端 SHALL 保持**现有表级浅合并行为逐字节不变**（零回归）
1.3. `_row_scope` SHALL 与 `_note_texts` / `_removed_table_keys` 同款：作为 `sub_table_data` 内的 `_` 前缀元数据键传递，**不改动 `SyncFromWorkpaperRequest` schema**（避免前后端版本耦合）
1.4. WHEN `_row_scope` 声明的表名不在本次 `sub_table_data` 的推送键里 THEN 服务端 SHALL 忽略该条声明并记 warning（声明与数据必须配对）
1.5. `_row_scope` SHALL 支持同一次载荷声明多张表的段（一个循环可能在多张共享表里各占一段）

### Requirement 2: 段边界由模板权威推导

**User Story:** 作为平台维护者，我要段边界只有一个真源，不能让每个循环各自写死行号。

#### Acceptance Criteria

2.1. 段边界 SHALL 由 `note_template_{listed,soe}.json` 的该表 `rows[]` 推导：**段 = 从带 `report_row_code == owner_row_code` 的行起，到下一个带任意 `report_row_code` 的行之前**（末段到表尾）
2.2. WHEN 模板里找不到该表、或找不到 `owner_row_code` 对应的段首行 THEN 服务端 SHALL **跳过该表的写入**并在返回值里报告 `row_scope_unresolved`，**绝不退化为整表覆盖**（fail closed —— 覆盖他人数据比不同步更坏）
2.3. 段归属 SHALL 从**载荷声明的 `owner_row_code`** 取，服务端只校验它存在于模板段集合；**不由服务端猜**
2.4. WHEN 同一张表被两个不同 `owner_row_code` 的段声明覆盖同一行区间 THEN 前端守卫 SHALL 在测试期拦住（registry 级唯一性），服务端 SHALL 记 warning 但按载荷执行
2.5. 段边界推导 SHALL 为纯函数（无 DB / 无 IO），可单测
2.6. WHEN 需要确定查哪份模板 THEN 变体 SHALL 由载荷 `current_standard` 的前缀（`listed*` / `soe*`）决定，`note.source_template` 仅作兜底；**禁止按章节号推导**（实测 20 个章节号两份模板都有、13 个标题不同，如 `八、1` listed 是政府补助 / soe 是货币资金）
2.7. WHEN 变体既无法从 `current_standard` 也无法从 `source_template` 确定 THEN SHALL fail closed（跳过该表 + 报告），因为查错模板会算出错误的段边界

### Requirement 3: 行身份与段内替换语义

**User Story:** 作为审计师，我在自己那一段里增删币种行时，不能影响别人的段落。

#### Acceptance Criteria

3.1. 段内 SHALL 采用**整段替换**语义：结果 = `baseline[:段起] + 本次推送行 + baseline[段止:]`
3.2. 段内行数 SHALL 允许与模板不同（源模板段内有 `……` / `可无限量添加行` 可扩行，审计师会增删币种）
3.3. WHEN 落库行按标签匹配 THEN 匹配 SHALL **限定在段窗口内** —— 「其中：美元」「欧元」「港币」这些标签**在多个段里重复出现**，全局按标签匹配必然串段
3.4. 服务端 SHALL 在写入的每一行打上段归属戳（`_seg`），使下一次同步能从**落库数据本身**定位段窗口（模板行的 `report_row_code` 不随数据落库）
3.5. `_seg` SHALL 被读时投影器忽略（不渲染成列、不进 Word 导出）
3.6. WHEN 某 owner 推送空数组 `[]` 且该表有 `_row_scope` 声明 THEN 服务端 SHALL 把该段恢复为**模板骨架行**（标签保留、数值置空），而不是删掉整段（固定行集表的段不该消失）

### Requirement 4: 首次同步的基线

**User Story:** 作为审计师，第一个循环推送后，附注里其他段落也要看得见骨架，而不是只剩推送方那 5 行。

#### Acceptance Criteria

4.1. WHEN 该表在附注侧尚无落库数据（首次同步）THEN 基线 SHALL 取**模板该表的完整行骨架**（全部段的标签，数值置空），再在其上替换 owner 段
4.2. WHEN 该表已有落库数据 THEN 基线 SHALL 取**落库现状**（不回退模板，否则会抹掉他人已录数据）
4.3. 基线构造 SHALL 为纯函数，且对「模板骨架 + 落库数据行数不一致」的情形以**落库数据为准**
4.4. 基线行 SHALL 同样带 `_seg` 戳（由模板段首行的 `report_row_code` 向下传播到下一个段首之前）

### Requirement 5: `_note_texts` / `text_content` 按段合并

**User Story:** 作为审计师，我在共享章节录的说明不能被下一个同步的循环整体覆盖。

#### Acceptance Criteria

5.1. `_note_texts` SHALL 按 `section` 键**浅合并**（同 `section` 覆盖、未推送的 `section` 保留），而非整列表替换
5.2. WHEN 载荷未提供 `_note_texts` THEN 服务端 SHALL **保留**既有 `text_content`，而非置 `None`
5.3. 服务端 SHALL 支持 `_removed_text_sections`（显式删除语义），对称于 `_removed_table_keys`
5.4. WHEN 单 owner 场景（既有 `_note_texts` 的 section 键集 ⊆ 本次推送键集）THEN 合并结果 SHALL 与整替换**逐字节等价**（零回归论证）
5.5. `text_content` SHALL 由合并后的 `_note_texts` 全量重排产出（保持 `【title】\n{text}` 拼接与段序稳定）

### Requirement 6: 零回归与灰度

**User Story:** 作为平台维护者，我要能证明这次改动对现存 90+ 个已接线披露 Tab 无影响。

#### Acceptance Criteria

6.1. 无 `_row_scope` 声明的载荷 SHALL 走与改动前**完全相同**的代码路径（characterization 测试逐字节比对 `table_data`）
6.2. 既有 `wp_disclosure_sync_service` 测试套件 SHALL 全绿且**不修改断言**（除 R5 的 `text_content` 保留语义须诚实改 1~2 条并写明依据）
6.3. 改动 SHALL 覆盖 `sync_from_workpaper` 与 `sync_from_html_disclosure` **两个写入口**（两处都有同款浅合并代码）
6.4. 行级合并 SHALL **不引入新迁移**（`_row_scope` / `_seg` 都在 `table_data` JSONB 内）
6.5. WHERE 写库涉及 JSONB THEN SHALL 用 `CAST(:td AS jsonb)` + `json.dumps(..., ensure_ascii=False)`，**禁用 `sa.type_coerce`**（asyncpg 下 100% 失败，平台已实证）

### Requirement 7: E1 外币章节作为首个消费者

**User Story:** 作为审计师，我在 E1 底稿录的外币货币资金数据要能自动流到附注「外币货币性项目」的货币资金段。

#### Acceptance Criteria

7.1. 新建 `e1FxNoteSectionMap.ts` 的 `buildE1FxSyncPayload(variant, snapshot)` SHALL 推「外币货币性项目」表并声明 `_row_scope: {外币货币性项目: {owner_row_code: 'BS-002'}}`
7.2. 载荷 SHALL 投影为附注 4 列（`项目 / 期末外币余额 / 折算汇率 / 期末折算人民币余额`，`flat`），**期初留底稿**（该章节跨循环共享，不得单方面扩列）
7.3. 段内行 SHALL 为「货币资金」段首行 + 各币种「其中：」行，币种由 `e1CurrencyScope` 驱动（可增删）
7.4. 同步后 SHALL 实测他循环段（应收账款 / 短期借款 / 长期借款 / 应付债券）行**逐字未被改动**
7.5. E1 spec 的 Task 13 守卫「全前端不得有 map 推向外币章节」SHALL 改为「只允许经 `_row_scope` 声明的 map 推向该章节」，并保留「不得整表覆盖」的正向断言

### Requirement 8: 守卫与 CI

**User Story:** 作为平台维护者，我要让「谁在整表覆盖共享表」在测试期就被拦住。

#### Acceptance Criteria

8.1. 新建生成器 SHALL 从两份 note_template 产出 `backend/data/note_shared_table_segments.json`（多段共享表清单 + 各段 `report_row_code` + 行区间），并有 drift 守卫
8.2. 前端守卫 SHALL 断言：凡推向共享表清单内表名的 `build*SyncPayload`，其载荷必须带 `_row_scope`；未带即打红
8.3. 后端守卫 SHALL 含反向自检：去掉行级合并分支后，「他循环段被覆盖」的断言必须失败
8.4. CI SHALL 新增 job（`disclosure-row-level-merge` + `-frontend`），并把共享表清单的 drift 检查挂上
8.5. 守卫读源码前 SHALL 先 `stripComments()` 并加反向自检（本 spec 的说明文字里会写出被禁的反例）

## Glossary

| 术语 | 含义 |
|------|------|
| 共享表 / 多段共享表 | 同一张附注子表内按科目分段、每段归属不同循环的表（判据：`rows[]` 含 ≥2 个不同 `report_row_code`），全库实测 29 张 |
| 段（segment） | 共享表内归属单一循环的连续行区间。段首行带 `report_row_code`，段止于下一个带 `report_row_code` 的行之前 |
| `owner_row_code` | 段的归属标识，取模板段首行的 `report_row_code`（如货币资金段 = `BS-002`），由载荷声明 |
| `_row_scope` | `sub_table_data` 内的元数据键，声明「本次只负责某表的某段」→ 触发行级合并。形如 `{表名: {owner_row_code}}` |
| `_seg` | 服务端写入落库行时打的段归属戳，使下一次同步能从落库数据本身定位段窗口（模板的 `report_row_code` 不随数据落库）。读时投影器忽略 |
| 表级浅合并 | 现状语义：按子表名合并，同名表整表覆盖、未推送的表保留 |
| 行级合并 | 本 spec 新增语义：段内整段替换、段外原样保留 |
| 基线（baseline） | 段替换的底稿。首次同步取模板完整行骨架（含他段标签、数值空），已有数据则取落库现状 |
| fail closed | 段边界解析不出时**跳过写入**而不是退化为整表覆盖 —— 覆盖他人数据比不同步更坏 |
| `_removed_text_sections` | `_note_texts` 的显式删除语义，对称于 `_removed_table_keys` |
