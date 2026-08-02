# Requirements Document

## Introduction

E0 货币资金函证循环下有四张「发函记录表」（发函前清单）：

| sheet | 索引号 | 列数 | 当前 componentType | 本 spec 范围 |
|---|---|---|---|---|
| 货币资金发函记录表E0-3 | E0-3 | 16（A~P） | `d-form-table` | ✅ 新建专属组件 |
| 借款发函记录表E0-4 | E0-4 | 16（A~P） | `d-form-table` | ✅ 新建专属组件 |
| 应付银行承兑汇票发函记录表E0-5 | E0-5 | 10（A~J） | `d-form-table` | ✅ 新建专属组件 |
| 理财产品发函记录表E0-6 | E0-6 | 11（A~K） | **`confirmation-wealth-list`（已落地）** | ⚠️ **只做符合度核查**，不换 componentType |

> 🔴 **E0-6 的现状已变（2026-08-02 实测，本 spec 首版基于过时基线）**：并发会话在
> `e0-confirmation-completion` 的 Task 12.5（用户裁决插入项，已 `[x]`）里交付了 E0-6 专属组件
> `confirmation-wealth-list`，全链已就位 —— `wp_code_overrides.json` **短键与全名键双登记**、
> 后端 `_CONFIRMATION_COMPONENTS`（`wp_render_config.py`）+ `wp_render_config_helpers._FORMAT`
> (`wealth-list-v1`) + `wp_classification_service`、前端 `htmlRendererRegistry` +
> `confirmation/wealthList/GtConfirmationWealthList.vue`，且 **`test_confirmation_sheet_override_contract.py`
> 已硬断言两个键都必须是 `confirmation-wealth-list`**。
> 故本 spec **不再新建 `confirmation-send-list-e06`**（详见 R1.1 与「与 `e0-confirmation-completion`
> 的边界」）—— 新建会造成同一 sheet 两个组件相争、打红既有契约、并让 E0-6 的 legacy 载荷被迁移两次。

它们是函证工作的作业清单：把账户/借款/票据/理财产品逐个摊开，标出发函对象、函上要证实的内容、以及资金归集与受限等风险标记，再汇入 `函证结果汇总表E0-1`。

**本 spec 要解决的是「列定义对了、值和界面都不对」**。2026-08-02 只读调查的实证基线：

1. **界面上的数据是模板示例**。`d-form-table` 不在 `RENDERER_DISPATCH`、只在 `_ONLYOFFICE_HTML_WHITELIST` 中，因此落到 `wp_render_config.py` 最后一档兜底 `extract_grid(_tpl, sheet) + strip_standard_header`。`extract_grid` 用 **`data_only=True`** 加载模板 → 读到的是外部工作簿引用的**缓存值**；E0-3 的 `D6:D24` 缓存值就是 `XX银行`/`XX财务公司`、`G`/`K` 缓存值是 `0`。剥掉行 1~4 后表头行 5 成为新行 1、行 6~24 成为 19 行"数据" → **用户看到 19 行 `XX银行 | 0 | 0`**。

2. **那份已人工审定的列定义在 HTML 渲染路径上零消费**。`E0.yaml` 的四张 sheet 已 `_reviewed: true`，`field`/`label`/`type`/`enum`/`render` 与源模板逐字一致（真源 `backend/data/e0_send_list_source_manifest.json`，守卫 `backend/tests/test_e0_send_list_columns.py` 12 组）。但 `dynamic_table` 只被 `wp_xlsx_export_service` 与 `wp_export/serialization` 用于**导入导出**，渲染路径根本不读它 → 枚举点选、日期选择、金额格式、字段语义全部落空。

3. **源模板声明的上游取数完全没有实现**。E0-3 的三列公式指向外部工作簿 `'[43]银行存款及其他货币资金明细表(仅人民币)E1-3'`：`D 开户银行←E1-3.A` / `G 银行账号←E1-3.C` / `K 账户余额（原币）←E1-3.K`。行映射 `6→13…14→21, 15→23…17→25, 18→27…24→33` **精确跳过 E1-3 的两个分组 SUM 小计行**（22 `其他金融机构（存放财务公司款项）：` / 26 `其他货币资金：`；12 `银行：` 同样不在映射内），且**只取「（一）存款本金」三段明细，不取「（二）应计利息」段与 34 行小计**。平台侧全无对应实现。

4. **既有守卫把这条源模板自带的联动一起挡住了**。`test_no_fabricated_pull_or_source_columns` 禁一切含 `pull/auto_/source/data_source` 的列，`e0-send-list-components` spec 的决策原文是「四表库无账户级维度时不臆造账户明细」。该决策对**四表库**方向正确，但 E1-3 → E0-3 是**源模板自己声明**的底稿间联动，不是臆造。这是范围划漏，不是守卫写错。

5. **legacy 载荷已存在，迁移不能丢数**。实测项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877`（重药控股安徽_2025）的 `parsed_data.html_data` 已有 `理财产品发函记录表E0-6` 键，形态是 grid 表格编辑器载荷（`rows:[{_row_id}]` / `cells` / `column_meta` / `header_rows` / `merged_cells` / `conclusion:{audit_explanation, overall_conclusion, remarks}`），**无 `_format`**。

6. **E0-5 的上游是 `明细表F3-2`，而且「是否函证」列就在那里**（2026-08-02 openpyxl 直读
   `backend/wp_templates/F/F3 应付票据.xlsx` 补充调查）。`明细表F3-2` 两级表头 R13:R14 逐字为：
   `票据号 | 票据类别 | 关联方类型 | 票据关系人(出票人/承兑人/收款人) | 票据期限(出票日/到期日/期限) |`
   `票面利率 | 是否承兑 | 期初余额 | 本期开票 | 本期承兑 | 期末未审数 | 账项调整 | 重分类调整 |`
   `期末审定数 | 已计利息 | **是否函证** | **票据保证金比例** | **保证金金额** | 备注`。
   平台侧 `composables/useF3Detail.ts` 已有全部字段（`ticketNo`/`noteType`/`acceptor`/`issueDate`/
   `dueDate`/`faceValue`/`depositAmount`/`isConfirmed`），`F3TabDetail.vue` 已算出
   `bankUnconfirmed`（`noteType.includes('银行') && isConfirmed !== '是'`）。
   → **R6.2 原先对 E0-5 的解释「筛选动作发生在 E0-3/E0-4 内」是错的**：E0-5 的范围决策发生在 **F3-2**，
   E0-5 只承载已决定函证的银承。E0-5 的 10 列有 6 列可直接从 F3-2 带入（见 R13）。
7. **`wp_code_overrides` 查表「尾码优先于全名」，R10.3 的消歧方案不成立**。
   `wp_render_config.py` 多 sheet 分支顺序是 **尾码 → 全名 → `{wp_code}-{sheet_name}`**：
   `_m = _SHEET_CODE_RE.search(sheet_name)` 先查 `_WP_CODE_OVERRIDE[尾码]`，全名只是 `if not _sheet_ovr`
   的兜底。两张 sheet 都以 `E0-5` 结尾 → 只要 `E0-5` 短键存在（现为 `d-form-table`），
   **只登记全名键 `应付银行承兑汇票发函记录表E0-5` 的话 `confirmation-send-list-e05` 永不渲染**；
   反向亦然（`e0-confirmation-completion` 要把核对表实现成真 componentType 也会被同一短键遮蔽）。
   今天没暴露，是因为 `skip` 判定走**全名精确匹配**且在更早的 `wp_render_config.py` sheet 过滤处执行，
   核对表被整张过滤掉、走不到 componentType 解析。
   实测全库 1797 个 classification sheet 名中，**同时命中全名键与尾码键且取值不同的只有 2 张**
   （`银行函证其他信息核对表E0-5` 尾码 `d-form-table` / 全名 `skip`；
   `长期应付职工薪酬实质性程序表 L2A` 尾码 `l2-interest-payable` / 全名 `skip`），
   两者全名值都是 `skip`（已由更早的过滤生效）→ **把查表顺序翻成「全名优先、尾码兜底」，今天行为零变化**。见 R15。

参照对象是 D0/G0/L0 函证循环的专属精美 HTML 组件范式（`confirmation-*` 系 17+ 个 componentType）：**专属 componentType + `RENDERER_DISPATCH` 里的 render 策略 + `_format` 版本化载荷 + 前端 `htmlRendererRegistry` 注册**。这套范式的关键副作用正是解决第 1 条 —— 一旦 componentType 有了 renderer，`wp_render_config` 的分发在 grid 兜底分支**之前**就返回，示例缓存值自然消失。

### 与 `e0-confirmation-completion` 的边界（必须先读）

`.kiro/specs/e0-confirmation-completion/`（0/17，并发会话建）做的是**函证枢纽打磨**：13 要项核对表、品种矩阵、共享列集/备忘录/可靠性改造、`importE0ListsToSummary` 取数纠偏（Task 11）、E0-3/E0-6 受限 → E1 联动（Task 12）、override 与预设纠偏（Task 13/14）。

两者**互补不重叠**。**原「硬冲突」条已因 E0-6 落地而失效并重写**，现为一处已解冲突 + 三处依赖 + 两处状态同步：

- **~~硬冲突~~ → 已解（2026-08-02 复核）**：原文写「该 spec 的 Task 13 计划把 `E0-6` 的 override
  落为 `d-form-table`，本 spec 接管并改为 `confirmation-send-list-e06`」。**两个前提都已过时** ——
  该 spec 的 Task 12.5 已把 E0-6 交付为 `confirmation-wealth-list`（全链 + 契约测试就位，见 Introduction）。
  **裁决：E0-6 保留 `confirmation-wealth-list`，本 spec 只做三张（E0-3/E0-4/E0-5）+ 对 E0-6 做符合度核查**。
  依据三条：①已交付且有 `test_confirmation_sheet_override_contract.py` 硬断言保护，改名只换来命名一致、
  代价是打红契约 + `_format` 由 `wealth-list-v1` 变 `send-list-e06-v1` 使 legacy 载荷被迁移两次；
  ②E0-6 **无上游底稿取数需求**（理财产品在平台无对应明细底稿，不像 E0-3←E1-3 / E0-5←F3-2），
  旧路径 `_CONFIRMATION_COMPONENTS` 已够（它同样在 grid 兜底**之前** return，且 E0-6 源模板
  R6:R20 全空、本就无示例值污染）；③共享引擎仍可复用 —— 让 `GtConfirmationWealthList` 内部改用
  本 spec 的 `sendListSpec.ts` / `useSendListData.ts`，**复用发生在组件内部而不是换 componentType**。
- **依赖 1**：该 spec 的 Task 11（四清单 → E0-1 带入）与 Task 12（E0-3/E0-6 受限 → E1）要**读清单行数据**
  → 本 spec 决定 E0-3/E0-4/E0-5 的行存储形态（业务键 dict + `_format`），是它们的前置；
  E0-6 的行形态由已落地的 `wealth-list-v1` 决定，**不由本 spec 改**。
- **依赖 2（新增）**：该 spec 的 Requirement 3「E0-1 下区品种矩阵」的「抽取样本的发函金额」
  最终来自四张清单 → 本 spec 的行形态变更会影响它的取数，两者验收要串。
- **状态同步 1**：该 spec 的 **Task 11 实际已落地**（`importE0ListsToSummary.ts` 已由 124 行改到 357 行，
  含 `票面金额`/`产品净值`/`借款类型`/`E0_LIST_SPEC`/`hasConfirmFlag`/`account_no` 去重键），
  但其 tasks.md 仍是 `[ ]` → **属"假红"，会让批量执行器重复实现**。请该 spec 更正标记。
- **状态同步 2**：该 spec 的 **Task 4（CrossRef 按循环）与 Task 10（品种矩阵）确认未做** ——
  `GtConfirmationSummary.vue` 里 `buildCrossRefRules` 0 命中、`D0-5`/`D0-7` 字面仍在（1+2 处）、
  `其他货币资金`/`应付票据`/`占账面` 全 0 命中。本 spec 不接管这两项。
- **两 spec 不并行推进**（memory 铁律：多 spec 改同一批文件时不要并行）。

## Glossary

| 术语 | 含义 |
|---|---|
| 发函记录表 / 发函清单 | E0-3~E0-6 四张表。函证工作的作业清单：逐个摊开发函对象与函上要证实的内容，再汇入 E0-1 |
| grid 兜底 | `wp_render_config.py` 最后一档分发：无 renderer 且在 `_ONLYOFFICE_HTML_WHITELIST` 内的 sheet，用 `extract_grid` 从模板抽单元格给前端。`data_only=True` 故会读到公式缓存值 |
| 公式缓存值 | xlsx 里公式的上次计算结果。E0-3 的跨工作簿引用缓存值就是模板示例 `XX银行` / `0` |
| `_format` | confirmation 组件载荷的版本标记（如 `send-list-e03-v1`）。前端据此区分新格式与 legacy；无 `_format` 即 legacy |
| legacy grid 载荷 | 表格编辑器旧形态：`rows:[{_row_id}]` + `cells` + `column_meta` + `header_rows` + `conclusion`，无 `_format` |
| Confirm_Flag | E0-3/E0-4 的「是否函证」列，决定函证范围（进 E0-1 的候选）。E0-5/E0-6 无此列 |
| 段语义取数 | 按 E1-3 的三个分组 SUM 行（`银行：` / `其他金融机构（存放财务公司款项）：` / `其他货币资金：`）识别段边界后取段内明细行，替代硬编码行号 |
| 金额口径 | E1-3 里同一账户有三个期末金额列：未审期末（H/M原币）、期末审定数（J/AA原币）、期末对账单余额（K/AD）。本 spec 做成可切换三态 |
| 一码两表 | 同一索引号 `E0-5` 对应两张 sheet：`应付银行承兑汇票发函记录表E0-5` 与 `银行函证其他信息核对表E0-5` |
| 手工优先 | 取数带入时已有非空值不覆盖，只填空位；平台共享实现 `composables/shared/adjudicationPrefillPlan.ts` |
| 宁缺勿造 | 上游无数据时返空并提示，不臆造行/不拿 0 冒充 |
| **「三 + 一」命名** | 四张清单的 componentType **有意不统一**：E0-3/E0-4/E0-5 = `confirmation-send-list-e03/e04/e05`（本 spec），E0-6 = **`confirmation-wealth-list`**（`e0-confirmation-completion` Task 12.5 已落地，`_format='wealth-list-v1'`，且 `test_confirmation_sheet_override_contract.py` 硬断言两个 override 键都指向它）。统一命名的三笔代价（改契约硬断言 / `_format` 二次迁移 / 删重写七件套）大于「命名整齐」的收益 → **本条写进 Glossary 就是为了让下个会话不再提一次统一**（见待裁决 5） |
| **裁决门 A** | 「三张 hidden 底稿是否仍要实现」这一裁决项，**2026-08-02 用户裁决 = A-否**（不实现）。落地：本 spec 的 R17.2/R17.3（资金归集勾稽）**永久留遗留**；R15 由「翻转 override 查表顺序」改为「只钉死全名 `skip` 不变式」（待裁决 2 随之关闭，Task 14 降级、不再阻塞 Task 5）；`e0-confirmation-completion` 的 R1/R7.1·R7.5/R8.6 与其 Wave 6 已删除 |
| **hidden sheet** | `openpyxl` 的 `ws.sheet_state == 'hidden'`。E0 的 20 个 tab 里 10 张是 hidden；`底稿目录` D9:F11 只索引 9 张，与 10 个 visible（含目录）互为旁证。**判某 sheet 是否真实底稿必须同时看这两处**，`wb.sheetnames` 不够 |

## Requirements

### Requirement 1: 三张发函清单落专属 HTML 组件（E0-6 复用已落地组件）

**User Story:** 作为审计助理，我打开 E0-3~E0-6 时要看到按源模板列语义渲染的可编辑清单表（枚举点选、日期选择、金额千分符），而不是一张吃了模板示例值的裸网格。

#### Acceptance Criteria

1.1. WHEN 用户打开 `货币资金发函记录表E0-3` / `借款发函记录表E0-4` / `应付银行承兑汇票发函记录表E0-5`
   THEN 系统 SHALL 渲染对应的专属 HTML 组件，componentType 分别为
   `confirmation-send-list-e03` / `-e04` / `-e05`。
   **`理财产品发函记录表E0-6` SHALL 保持 `confirmation-wealth-list`**（已落地，见 Introduction），
   系统 SHALL NOT 为它新建 `confirmation-send-list-e06`。

1.1b. WHEN 对 E0-6 的已落地组件做符合度核查 THEN SHALL 逐条比对本 spec 的
   R1.3~R1.7 / R2 / R3 / R6.5 / R8 / R9，产出「已满足 / 需补 / 有意差异」三分类清单；
   **需补项 SHALL 以最小改动补在 `confirmation/wealthList/` 内部**（含改用本 spec 的共享
   `sendListSpec.ts` / `useSendListData.ts`），SHALL NOT 通过换 componentType 实现。
   核查结论 SHALL 写进 Notes，SHALL NOT 因"看起来差不多"跳过核查。
1.2. 四个 componentType SHALL 各自在 `RENDERER_DISPATCH` 注册 render 策略（对齐 `_l0_confirmation.py` / `_g0_confirmation.py` 范式），使分发在 grid 兜底分支之前返回。
1.3. 组件渲染的列 SHALL 由声明式列 spec 驱动，其 `field`/`label`/`type`/`enum`/`render` 与 `backend/data/e0_send_list_source_manifest.json` 逐字一致（该 manifest 保持唯一真源地位，本 spec 不改它的 `field`/`label`/`type`）。
1.4. `type: 'enum'` 列 SHALL 渲染为 `el-select` 点选（交互点选优先铁律）；`type: 'date'` SHALL 渲染为 `el-date-picker`；`render: 'amount'` SHALL 使用 `WpAmountInput`（失焦千分符），**且 SHALL NOT** 用于 `interest_rate` / `holding_shares` 等非金额数值列。
1.5. 表格 SHALL 遵循底稿表格 UI 铁律：13px 字号、金额右对齐 `tabular-nums` 防折行、只读金额走 `displayPrefs.fmtAmount`。
1.6. E0-3（16 列）与 E0-4（16 列）SHALL 提供 ⚙ 列显隐设置（宽表铁律）。
1.7. 组件 SHALL NOT 出现任何 `el-input-number :formatter`（该 prop 在 EP 2.13.6 不存在，是空操作）。

### Requirement 2: 模板示例值污染消除

**User Story:** 作为审计助理，新建项目打开发函清单时应该是空表（或由取数带出的真实账户），不能是 `XX银行 | 0 | 0`。

#### Acceptance Criteria

2.1. WHEN 四张 sheet 无持久化载荷 THEN render 策略 SHALL 返回**空的新格式初始载荷**（`{_format, rows: [], conclusion: {...}}`），SHALL NOT 调用 `extract_grid` 或以任何方式返回模板公式缓存值。
2.2. 守卫 SHALL 断言四个 componentType 均在 `RENDERER_DISPATCH` 中，且 render 策略源码不含 `extract_grid` / `data_only` 字样。
2.3. 守卫 SHALL 断言初始载荷的 `rows` 为空数组，且载荷中不出现 `XX银行` / `XX财务公司` 字样（反向自检：以模板缓存值构造的 fixture 必红）。
2.4. **平台级**：新增守卫断言前端 `htmlRendererRegistry` 中所有 `confirmation-*` componentType 都已被后端认领（在 `RENDERER_DISPATCH` ∪ `_CONFIRMATION_COMPONENTS` 之中）。未认领的 componentType 会被 `wp_render_config` 改写成 `onlyoffice-sheet`，专属组件永不渲染。豁免须逐条登记理由（`confirmation-hub` 是 workbook 级 placeholder，本就不注册组件）。
2.5. **平台级（只报告不改）**：交付一个只读诊断脚本，扫全库统计有多少 sheet 走 `extract_grid` 兜底且其模板对应 sheet 含公式缓存值（即同款示例值污染候选），输出清单供后续独立 spec 决策。

### Requirement 3: 动态行，源模板行容量不作业务上限

**User Story:** 作为审计助理，真实项目有 50+ 个银行账户，我不能被源模板的 19 行卡住。

#### Acceptance Criteria

3.1. 四张表的数据区 SHALL 为动态行（新增/删除/排序），初始 SHALL NOT 预置任何空占位行（预置空行会被下游当占位数据）。
3.2. 系统 SHALL NOT 以源模板的行容量作为行数上限。源模板实测行容量（openpyxl `dims` + 逐行边框，2026-08-02 复核）：
   E0-3 `A1:S26`（数据区 R6:R26，其中 R6:R24 是外部工作簿引用公式、R25/R26 空白带边框）/
   **E0-4 `A1:P20`（数据区 R6:R20 共 15 行空白带边框，R16 残留孤立 `G16=0 / H16=0`）** /
   E0-5 `A1:J20`（R6:R20 共 15 行）/ E0-6 `A1:K20`（R6:R20 共 15 行）。
   旁证：四张表都设了 `print_area`（E0-3 `$A$1:$P$29` / E0-4 `$A$1:$P$21` / E0-5 `$A$1:$J$21` / E0-6 `$A$1:$K$20`），
   即那些空白行是**打印骨架**而非数据，与 3.1「不预置空占位行」互为印证。
   ⚠️ 本条原写「E0-3 19 行 / E0-4 19 行」，与实测不符（已纠正）；引用行容量前必须 openpyxl 复核。
3.3. 每行 SHALL 有稳定 `_row_id`（沿用 legacy grid 载荷的 `_row_id` 生成形态），SHALL NOT 用行标签或序号作键。
3.4. WHEN 用户删除某行 THEN 系统 SHALL 同时清掉该行在载荷中的全部字段，不留孤儿键。

### Requirement 4: E1-3 → E0-3 上游取数（源模板声明的联动）

**User Story:** 作为审计助理，银行存款明细表（E1-3）已经录好了账户，我不想在发函清单里把开户银行和账号再敲一遍。

#### Acceptance Criteria

4.1. 系统 SHALL 提供「从 E1-3 带入账户清单」动作，从 `银行存款及其他货币资金明细表` 取明细行 seed 到 E0-3。
4.2. 取数 SHALL 按**段语义**识别明细行，而非硬编码行号：以 `银行：` / `其他金融机构（存放财务公司款项）：` / `其他货币资金：` 三个 SUM 行作段起点，取段内明细行；SHALL 排除三个分组 SUM 行、`存款本金小计` 行、以及整个「（二）应计利息」段。
   - 依据：两版 E1-3 行号完全不同（仅人民币版三段明细起于 13/23/27；人民币及外币版起于 13/19/23），硬编码行号不可移植。
4.3. 系统 SHALL 按项目实际存在的 E1-3 版本分支取数：`银行存款及其他货币资金明细表(仅人民币)E1-3` 与 `银行存款及其他货币资金明细表(人民币及外币)E1-3`。
   - 仅人民币版：`A 开户银行` / `C 银行账号` / `H 期末余额(未审)` / `J 期末审定数` / `K 期末对账单余额` / `Q 受限金额` / `R 受限原因`；**无币种列、无原币列、无利率列**。
   - 人民币及外币版：`A 开户银行` / `C 银行账号` / `E 原币币种` / `M 期末余额(原币)` / `AA 期末审定(原币)` / `AD 期末对账单余额` / `AJ 受限金额` / `AK 受限原因` / `AL 利率`。
4.4. 带入 SHALL 至少覆盖 `bank_name`（←A）、`bank_account`（←C）、`balance_orig`（口径见 4.5）；外币版 SHALL 额外覆盖 `currency`（←E）与 `interest_rate`（←AL）。
4.5. **金额口径 SHALL 可选且默认为「期末余额（未审）」**，可切换为「期末审定数」或「期末对账单余额」；UI SHALL 以 tooltip 标明源模板原公式指向的是**对账单余额**（仅人民币版 K 列）这一事实。
   - 依据与待裁决点：源模板 `E0-3.K ← E1-3.K = 期末对账单余额`，但 E0-3 表头写「账户余额（原币）」。发函清单在**发函前**编制、此时通常尚无对账单余额，且函证目的正是验证**账面**余额，故默认取未审期末；但也存在"先取对账单余额填清单再发函"的作业顺序可能。**本 spec 不单方面改口径，默认值待用户确认，源模板事实由守卫钉死。**
4.6. 带入 SHALL 走平台共享的 plan→resolve→describe（`composables/shared/adjudicationPrefillPlan.ts`）：**手工优先**（已有值不覆盖）、幂等、可预览、有变化时弹确认、支持「仅补空值」。
4.7. WHEN 项目的 E1-3 无数据或两版都不存在 THEN 系统 SHALL 提示「上游 E1-3 暂无账户明细」并零写入（宁缺勿造，不臆造账户）。
4.8. `account_subject`（所属科目）SHALL 由科目映射带出（`1002` 银行存款 / `1012` 其他货币资金，按段归属），`account_holder`（账户名称）SHALL 可由 E1-3 的 `B 总账银行名称` 带出；两者带不出时留空不臆造。
4.9. 既有守卫 `test_no_fabricated_pull_or_source_columns` 的边界 SHALL 被收窄并写明理由：禁的是**四表库臆造账户明细**，不是源模板声明的底稿间联动；本 spec SHALL NOT 向 manifest 注入任何取数/来源**列**（取数结果写进既有 `field`，不新增列）。

### Requirement 5: legacy grid 载荷迁移零丢数

**User Story:** 作为审计助理，我在旧网格里已经填过的理财产品清单，换成新组件后不能消失。

#### Acceptance Criteria

5.1. WHEN sheet 的持久化载荷是 legacy grid 形态（有 `cells`/`column_meta`/`header_rows` 而无 `_format`）THEN render 策略 SHALL 将其迁移为新形态，按**列字母 → field** 映射（manifest 的 `cell_columns` 键即列字母）。
5.2. 迁移 SHALL 保留 `_row_id`；SHALL 保留 `conclusion` 的 `audit_explanation` / `overall_conclusion` / `remarks` 三键。
5.3. 迁移 SHALL 为纯函数且幂等（对已是新形态的载荷为空操作）。
5.4. WHEN legacy 载荷的 `cells` 中出现 manifest 未声明的列字母 THEN 迁移 SHALL 把该值收进 `_unmapped_cells` 保留（不静默丢弃），并在 UI 提示存在未识别列。
5.5. 迁移 SHALL NOT 写库（render 期 transient），落库由用户下一次保存触发；守卫断言 render 不产生写操作。
5.6. 迁移前 SHALL 有真实库快照，迁移逻辑上线后 SHALL 对实测项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877` 的 `理财产品发函记录表E0-6` 验证往返无损。

### Requirement 6: 四张表的差异化列集按表声明，不得共用

**User Story:** 作为现场经理，我要求每张清单只出现它自己该有的列 —— 源模板里这四张表并不同构。

#### Acceptance Criteria

6.1. 列集 SHALL per-sheet 声明（16/16/10/11 列），SHALL NOT 用一份共用列集覆盖四张表。
6.2. `is_confirm`（是否函证）列 SHALL 只出现在 E0-3 与 E0-4；E0-5 与 E0-6 SHALL NOT 有该列。
   - 依据：openpyxl 实证 E0-5/E0-6 的表头行无该列 —— 这两张表是"已决定要函证的对象清单"。
   - **范围决策的落点按表分别登记（勿笼统写「发生在 E0-3/E0-4 内」）**：
     E0-3/E0-4 的筛选在**表内**（自带 `是否函证` 列）；
     **E0-5 的筛选在 `明细表F3-2` 的「是否函证」列**（源模板 R13 `T` 列，见 Introduction 第 6 条）；
     E0-6 源模板与 F 循环均无对应筛选列，入表即视为发函对象。
   - E0-5 SHALL NOT 为「已知但决定不函证」的票据新增记录列（源模板无该列，`test_no_fabricated_pull_or_source_columns` 亦禁）；
     该痕迹由 F3-2 承载，E0-5 侧以反向提示呈现（见 R14.5）。
6.3. **E0-3 与 E0-4 两张表**的 `is_confirm` 在源模板里都是**隐藏列**（各自 `E: hidden=True`，openpyxl `column_dimensions['E'].hidden` 实测，2026-08-02 复核）；平台侧 SHALL 显式呈现该列（Confirm_Flag 是函证范围的决定项，隐藏它会让用户无法操作），并在守卫里记录"源模板隐藏、平台显式化"这一有意差异。
   ⚠️ 本条原只写 E0-3，漏了 E0-4 —— 而 E0-4 的 E 列同样 hidden。这解释了为什么用户在 WPS 里打开 E0-4 看到的是**15 列**（列字母从 D 直接跳到 F）、误以为「源模板没有『是否函证』列」；**「列被隐藏」与「列不存在」是两件事**，判定只能看 `column_dimensions[x].hidden`，不能靠截图数列。
   E0-5 / E0-6 是真正**没有**该列（`hidden cols == {}` 且表头 10/11 列里确实无 `是否函证`）→ 与 R11 的 `hasConfirmFlag=false` 一致。守卫必须同时正向断言两组事实，防把两种情形混成一种。
6.4. `account_type`（账户类型）的 5 项枚举 SHALL 被标注为**平台增强**（源模板该列无数据验证），与源模板口径区分登记。
6.5. 源模板数据验证事实 SHALL 由守卫钉死：E0-3 仅 `L6:L26` 与 `O6:O26` 为 `是,否` 下拉；E0-6 的 `K` 列验证范围在源模板只到 `K6:K10` 而数据区更长 —— 平台侧 SHALL 整列启用，SHALL NOT 照抄残缺范围。
6.6. 各列的表头文字 SHALL 逐字取自源模板（含 `是否属于资金归集（资金池或其他资金管理）账户`、`是否存在冻结、担保或其他使用限制（如是，请注明）` 等长标签），SHALL NOT 简写。

### Requirement 7: 受限标记与 E1-3 勾稽

**User Story:** 作为审计助理，受限信息我只想录一次，两张表之间要能互相校验。

#### Acceptance Criteria

7.1. 系统 SHALL 提供勾稽项：WHEN E1-3 某账户的 `受限金额` 非零 AND E0-3 同账号行的 `has_restriction` 不为「是」THEN 报 error 级不一致。
7.2. 勾稽 SHALL 按 `bank_account` 匹配；匹配不上的行 SHALL 记为 `unmatched` 提示而非 error（账号可能未录）。
7.3. E0-3 的 `has_restriction` 是 是/否 枚举，受限**原因** SHALL 落 `remark`（备注）列；系统 SHALL NOT 新增「受限金额」列（源模板未定义，既有守卫已禁）。
7.4. E0-6 的 `has_restriction`（`是否被用于担保或存在其他使用限制`）SHALL 同样纳入勾稽面板，但其下游落点（E1 ②表 vs 受限资产附注段）**归 `e0-confirmation-completion` 的 Task 12**，本 spec 只保证数据可读。
7.5. 勾稽面板 SHALL 为紧凑单行 bar + 可折叠明细，带规则 tooltip 与 `GtIndexChip` 追溯（对齐 `h1DisclosureConsistency` / `d1DisclosureConsistency` 范式）。

7.6. **承兑保证金链路 SHALL 纳入勾稽面板**：WHEN `明细表F3-2` 的 `保证金金额` 合计非零
   AND E0-5 对应票据行的 `抵（质）押品` 为空 THEN SHALL 报 warning。
   - 依据（源模板明写，非平台自拟）：`明细表F3-2` 的「二、审计过程」第 1 条逐字要求
     「核对应付票据明细表与应付票据备查簿的相关内容……**复核其应存人银行的承兑保证金，并与其他货币资金科目勾稽**」。
   - 现状：`F3TabDetail.vue` 有 P1-6 横幅（「票据保证金合计 X 元属受限货币资金，应重分类至其他货币资金，
     并在货币资金(E1)受限资产及附注中披露」）、`E1TabAnalysis.vue` 有「银行承兑汇票保证金测算请交叉索引
     应付票据底稿 F3-2」——**两处都是纯文字，零数据联动**。本条把它做成可判定的勾稽项。
7.7. 承兑保证金**写入 E1 受限货币资金 ②表**（受限类别「银行承兑汇票保证金」）SHALL NOT 由本 spec 实现，
   归 `e0-confirmation-completion` 的 Task 12 扩围（该 Task 原只覆盖 E0-3/E0-6 受限 → E1，漏了本条链路）。
   本 spec 只保证 F3-2 保证金与 E0-5 抵（质）押品可读、可勾稽，并在 Notes 记录交接。

### Requirement 8: 审计说明、结论与 AI 辅助

**User Story:** 作为审计助理，我要在清单页就地写审计说明与结论，并能用 AI 起草、提交复核，而不是点了 AI 按钮没反应。

#### Acceptance Criteria

8.1. 四张组件 SHALL 各有「审计说明」与「审计结论」两个文本区，用 `el-card` 包裹（底稿表格 UI 铁律）。
8.2. 每个文本区 SHALL 配 🤖 AI 辅助按钮与 💬 复核触发（`GtReviewTrigger`）。
8.3. AI 调用 SHALL 走 `POST /api/workpapers/{wpId}/ai/generate-text`，body `{section, prompt, context: dict[str,str], existingContent}`（**驼峰** `existingContent`；`context` 的值必须全为字符串，否则 422），读 `(res.data?.data ?? res.data)?.content`。
8.4. 每个 AI section SHALL 在后端 `review_dialog._SECTION_PROMPTS` 登记专属 prompt，且每条 prompt SHALL 写明源模板口径并含「不得虚构」约束。
8.5. AI 按钮 SHALL 有 `:loading` 与 `:disabled="isReadonly"`；SHALL NOT 是只 `emit('save', ...ai-trigger)` 的 marker stub。
8.6. 文本区键集 SHALL 与后端 prompt 登记项交叉校验（守卫：新增文本区必然要求补 prompt，孤儿 prompt 必红）。

### Requirement 9: 导入导出

**User Story:** 作为审计助理，客户给的账户清单是 Excel，我要能导入；也要能把清单导出给项目组线下核对。

#### Acceptance Criteria

9.1. 四张组件 SHALL 提供 `el-dropdown「导入导出 ▾」`（导出模板 / 导出数据 / 导入数据），复用平台既有下拉范式。
9.2. 导入导出 SHALL 复用 `E0.yaml` 已审定的 `dynamic_table`（`start_row` / `header_row` / `columns`）作列映射真源，SHALL NOT 另写一份列表。
9.3. 导出模板 → 立即用导入校验器验一遍 SHALL 通过（往返自检；防 openpyxl 纵向合并清空第二行表头导致"导入自家模板失败"）。
9.4. WHEN 导入部分区块失败 THEN UI SHALL 明确提示失败项，SHALL NOT 无论成败都提示「导入成功」。

### Requirement 10: componentType 全链注册

**User Story:** 作为平台维护者，我要求新组件在前后端各处登记齐备，否则它会被静默改写成 OnlyOffice 渲染、专属组件永不出现。

#### Acceptance Criteria

10.1. **三个**新 componentType SHALL 在以下各处注册：前端 `htmlRendererRegistry`（union type + entry + icon + label）、后端 `RENDERER_DISPATCH`、`wp_classification_service` 的 VALID 集合、`wp_code_overrides.json`。
   E0-6 的 `confirmation-wealth-list` **已在四处注册齐备**（实测），本 spec SHALL NOT 重复登记、SHALL NOT 改它。
10.2. `wp_code_overrides.json` SHALL 同时登记 **wp_code 短键**（`E0-3`/`E0-4`）与**全名 sheet 键**（如 `货币资金发函记录表E0-3`），因为 E0 是多 sheet 工作簿、sheet 级 override 才是可达路径。
   `E0-6` 的双键已是 `confirmation-wealth-list`（且被 `test_confirmation_sheet_override_contract.py` 断言），
   SHALL 原样保留。
10.3. `E0-5` 存在**一码两表**（`应付银行承兑汇票发函记录表E0-5` 与 `银行函证其他信息核对表E0-5`，后者 T3 索引号误引 `底稿目录!F9` 得 `E0-6`）。**归属裁决 = 源模板 `底稿目录` F8=`E0-5` ↔ E8=`应付银行承兑汇票发函记录表`；核对表在底稿目录里没有索引号**；`workpaper_sheet_classification` 亦只给前者建了 `wp_code='E0-5'` 行（后者只有 `wp_code='E0'`）→ 按编码定位 render sheet **不会**串到核对表。

10.3.1. **但 componentType 解析层未消歧**：`wp_code_overrides` 查表是**尾码优先于全名**（见 Introduction 第 7 条），两张 sheet 都以 `E0-5` 结尾。故「只登记全名键、不用短键」**不可行** —— `E0-5` 短键仍会先命中。本 spec SHALL 按 R15 先修平台查表顺序，再登记全名键；R15 未落地前 SHALL NOT 认为全名键生效。

10.3.2. 该消歧结论 SHALL 与 `e0-confirmation-completion` 保持一致；不一致时以源模板 `底稿目录` 索引号列为准。
10.4. 各 componentType SHALL 有独立 `_format` 版本号（`send-list-e03-v1` / `-e04-v1` / `-e05-v1`），便于逐表迁移与灰度。
   E0-6 的 `_format` SHALL 保持已落地的 `wealth-list-v1`，SHALL NOT 改为 `send-list-e06-v1`
   （改动会让 E0-6 的 legacy grid 载荷被迁移两次，且打红既有契约）。
10.5. 契约测试 SHALL 交叉比对四处注册的一致性，并含反向自检（删任一处必红）；
   E0-6 SHALL 作为**显式豁免**登记（走旧路径 `_CONFIRMATION_COMPONENTS` 而非 `RENDERER_DISPATCH`，
   理由：无 render 期取数需求 + 源模板数据区全空无污染），豁免须写明理由。

### Requirement 11: E0 公式预设与本 spec 的关系

**User Story:** 作为平台维护者，我要求本 spec 与并发的 `e0-confirmation-completion` 边界清晰，不互相覆盖对方的改动。

#### Acceptance Criteria

11.1. 本 spec SHALL NOT 修改 `prefill_formula_mapping.json`；E0 那一块的双重贴错标签（`sheet="审定表E0-1"` 源 xlsx 无此 tab、真实为 `函证结果汇总表E0-1`；`wp_name="银行询证函"`）归 `e0-confirmation-completion` Task 14。
11.2. 本 spec 的 E1-3 取数 SHALL 由 render 策略直接实现（底稿间联动），SHALL NOT 经公式预设 / `WP()` 表达式（源模板是跨工作簿引用，平台侧对应的是 render 期取数，不是单元格公式）。

### Requirement 12: 源模板事实固化与实测

**User Story:** 作为质量控制复核合伙人，我要求清单的列与取数口径能追溯到源模板原件，且改造结果在真实项目上验证过、测试数据已复原。

#### Acceptance Criteria

12.1. 守卫 SHALL 用 openpyxl 直读源模板 `backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx`，三向比对：源 xlsx 表头 ↔ `e0_send_list_source_manifest.json` ↔ `E0.yaml` 的 `dynamic_table.columns`。
12.2. 守卫 SHALL 钉死本次调查的源模板事实：四张 sheet 的真实 tab 名、表头行号、列数与逐字标签、**E0-3 与 E0-4 的 `E` 列隐藏（且 E0-5/E0-6 无任何隐藏列）**、**四张表的 `dims` 与数据区行范围 + `print_area`（R3.2 的实测值）**、数据验证范围、E0-3 三列公式的目标 sheet 与列（`$A`/`$C`/`$K`）、行映射跳过的小计行号（22/26）、**E0-4 R16 的孤立残留 `G16=0 / H16=0`**（防迁移时把它当一条借款记录）。
12.3. 守卫 SHALL 用 openpyxl 直读 `E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx` 钉死两版 E1-3 的段起点与列语义（R4.3 的两组列）。
12.4. 所有源码型守卫 SHALL 先 `stripComments()` 再断言，并配反向自检（本 spec 的踩坑说明注释里会写反例，不剥注释会把说明文字数成真实用法）。
12.5. 读源模板时 SHALL 跳过 `~$` 锁文件；SHALL 先比对 `backend/wp_templates/` 与参考副本的文件大小（运行时权威只认前者，参考副本已知落后）。
12.6. 实测 SHALL 用真实项目走浏览器 + postgres 只读：四张 sheet 逐个打开验挂载与零 console error、**验界面不再出现 `XX银行`**、动态行增删、枚举点选、金额千分符（`1234567.5` → `1,234,567.50`）、E1-3 带入、勾稽面板、legacy E0-6 载荷往返无损。
12.7. 实测 SHALL 先快照后改、按 md5 逐字节复原；不可复原字段如实记录；会话结束前清理 `tmp_*` 产物。
12.8. CI SHALL 登记两个 job：后端源模板守卫 + 前端组件契约。

12.9. 守卫 SHALL 用 openpyxl 直读 `backend/wp_templates/F/F3 应付票据.xlsx` 钉死 `明细表F3-2`
   的两级表头（R13:R14 逐字 19 列，含 `是否函证` / `票据保证金比例` / `保证金金额`）、
   R9「二、审计过程」第 1 条含「承兑保证金……与其他货币资金科目勾稽」原文、
   以及 `逾期票据检查F3-5` 的列集（R5:R6 两级，含 `期后支付金额` / `抵押情况(物品名称/金额)`）。

### Requirement 13: F3-2 → E0-5 上游取数（与 R4 对称）

**User Story:** 作为审计助理，应付票据明细表（F3-2）已经逐张登记了银行承兑汇票，我不想在 E0-5 里把票号、出票日、到期日、票面金额再敲一遍。

#### Acceptance Criteria

13.1. 系统 SHALL 提供「从 F3-2 带入承兑汇票清单」动作，从 `明细表F3-2` 取票据行 seed 到 E0-5。

13.2. 带入 SHALL 只取满足**两个条件**的行：`isConfirmed === '是'` **且** `noteType` 含「银行」。
   - 依据：E0-5 表名是「应付**银行**承兑汇票发函记录表」；商业承兑汇票的承兑人是企业不是银行，
     函证对象与渠道均不同（走 D0/K0 往来函证，不进 E0）。
   - `noteType` 判定 SHALL 复用 `F3TabDetail.vue` 现有口径 `(noteType || '').includes('银行')`，不另写一份。

13.3. **供应链票据 SHALL NOT 自动带入**，只提示人工判断。
   - 依据：供应链票据（2023-01-01 起按应付票据处理）的承兑人可能是供应链平台或保理公司而非银行，
     是否向银行函证需会计判断；代码不得代替判断（宁缺勿造）。

13.4. 字段映射 SHALL 为：`bill_no ← ticketNo` / `bank_name ← acceptor`（银承的承兑人即承兑银行）/
   `face_amount ← faceValue`（口径见 13.5）/ `issue_date ← issueDate` / `due_date ← dueDate` /
   `pledge ← depositAmount + depositRatio` 的可读表述。
   `settle_account`（结算账户账号）与 `currency`（币种）**F3-2 无对应列 → SHALL 留空**，
   SHALL NOT 从别处猜（可另由 E1-3 补，属 R4 范围）。

13.5. `face_amount` 口径 SHALL 可选，默认 `faceValue`（票面金额），可切换 `期末审定数`。
   - 依据与待裁决点：E0-5 表头是「票面金额」，与 F3-2 的 `faceValue` 同名同义 → 默认取它；
     但 E0-1 的发函金额最终要与 2201 审定数勾稽，故保留切换。**默认值待用户确认。**

13.6. 带入 SHALL 走平台共享的 plan→resolve→describe（`composables/shared/adjudicationPrefillPlan.ts`）：
   **手工优先**（已有值不覆盖）、幂等、可预览、有变化时弹确认、支持「仅补空值」。匹配键 SHALL 为 `bill_no`（票据号）。

13.7. WHEN 项目的 F3-2 无数据、或无任何「银承 + 是否函证=是」的行 THEN 系统 SHALL 提示
   「上游 F3-2 暂无待函证的银行承兑汇票」并零写入（宁缺勿造）。

13.8. 本 spec SHALL NOT 向 `e0_send_list_source_manifest.json` 注入任何取数/来源**列**
   （取数结果写进既有 `field`，与 R4.9 同口径）。

### Requirement 14: E0-5 质量红线与一函多票呈现

**User Story:** 作为现场经理，我要一眼看出这批函覆盖了哪些票、金额与账面是否对得上、有没有漏函或重复登记。

#### Acceptance Criteria

14.1. **发函完整性三方勾稽** SHALL 提供：`Σ(E0-5 票面金额)` ↔
   `Σ(F3-2 中 noteType 含「银行」且 isConfirmed='是' 的 期末审定数)` ↔ `trial_balance 科目 2201`（银承部分）。
   前两者不等报 error；与 2201 的差异报 warning 并允许填写说明（存在商承/供应链票据占比属正常差异）。
   - 依据：应付票据是**低估负债**的高发位置，漏一张票即漏一笔未记录负债；
     现有勾稽（R7）只覆盖 E0-3↔E1-3 受限，无金额完整性校验。

14.2. **一函多票 SHALL 按索引号分组呈现**：同一 `索引号` 的多行归为一组，组内显示票面金额小计，
   使「一封函要证实 N 张票、合计 X」与 E0-1 的一行直接对应。
   - 依据：源模板 `函证结果汇总表E0-1!F8` 的应付票据分支是
     `SUMIF(E0-5!$A:$A, E0-1!$B, E0-5!$G:$G)` —— **单条件按索引号求和**，是四张清单里唯一如此的。
   - 分组 SHALL 为展示层派生，SHALL NOT 改变行存储形态（仍是扁平 `rows` + 稳定 `_row_id`）。

14.3. **票据号唯一性 SHALL 校验**：同一 `bill_no` 出现两行报 error（票号在电子商业汇票系统内唯一，
   重复即重复登记或重复函证）；并与 `明细表F3-2` / `逾期票据检查F3-5` 做票号一致性提示
   （E0-5 有而 F3-2 无 → warning「账面未登记」；F3-2 有银承待函证而 E0-5 无 → warning「可能漏函」）。

14.4. **到期日风险 SHALL 派生标记**：`due_date ≤ 报表截止日` → 「已到期未兑付」（与 `逾期票据检查F3-5` 交叉提示）；
   `due_date − issue_date` 超出期限阈值 → 「期限异常」。
   - 🔴 期限阈值 SHALL 按会计期间可配置，SHALL NOT 在代码里写死月数
     （商业汇票最长付款期限有过监管变更，写死会在跨期项目上误报）。

14.5. **范围决策反向提示 SHALL 呈现**：页头显示「F3-2 银承未函证 N 笔」，N 取自 F3-2 侧既有计算
   （`F3TabDetail.vue` 的 `bankUnconfirmed`），并在审计说明模板里固化
   「本表为已决定函证的全部银行承兑汇票，未纳入函证的票据及理由见 F3-2『是否函证』列」。
   - 这是 R6.2「不为 E0-5 新增 `是否函证` 列」前提下保住范围决策痕迹的解法。

14.6. `抵（质）押品`（源模板 J 列，自由文本）SHALL 保持单列不拆
   （`test_no_fabricated_pull_or_source_columns` 禁自造列）；保证金金额从 F3-2 带入后
   SHALL 以展开行或 tooltip 分开呈现「保证金金额 / 保证金比例 / 其他质押物文本」。

14.7. 上述红线 SHALL 全部走只读派生（对齐 R7.5 的紧凑 bar + 可折叠明细 + `GtIndexChip` 追溯），
   SHALL NOT 阻断保存。

### Requirement 15: `E0-5` 一码两表 —— **查表顺序不改，改为钉死不变式**（2026-08-02 重写）

**User Story:** 作为平台维护者，我要求「一码两表」的两张 sheet 各自路由正确，
且这个正确性不能靠"碰巧"—— 必须有守卫把它依赖的那个配置条目钉死。

**✅ 待裁决 2 已关闭（随裁决门 A = A-否）**：原 R15 假设「尾码优先 → 全名级 override 无效
→ 必须翻转查表顺序」。实证 `wp_render_config.py` 后发现**两条判定顺序相反**，
当前配置**已经正确**，方案 A（翻顺序）与方案 B（删短键）**都不需要做**：

| 判定 | 行 | 匹配方式 | 对两张 `E0-5` 的作用 |
|---|---|---|---|
| **skip** | L709 | **完整 sheet_name 精确** | `银行函证其他信息核对表E0-5` → `skip` → `continue`，**永不进入下方解析** |
| skip | L722 | 尾码 `_SHEET_CODE_RE` | 尾码 `E0-5` 取值非 `skip` → 不拦 |
| **componentType** | L749~758 | **尾码优先**，全名与 `{wp_code}-{sheet_name}` 作 fallback | `应付银行承兑汇票发函记录表E0-5` → 尾码 `E0-5` → 取值 |

→ 本 spec 把短键 `E0-5` 由 `d-form-table` 改成 `confirmation-send-list-e05` 后仍然安全。
**原「R15 是 Task 5 的前置」关系解除**。

**但这构成一条必须钉死的不变式** —— 当前正确性完全依赖那一个 `skip` 条目：

> `银行函证其他信息核对表E0-5` 的**完整 sheet_name** `skip` 条目
> SHALL NOT 被删除或改成其它值。

#### Acceptance Criteria

15.1. 守卫 SHALL 断言 `wp_code_overrides.json` 里 `银行函证其他信息核对表E0-5`
   的**全名键**存在且值为 `skip`。
   SHALL NOT 接受「尾码键也指向 skip 所以没事」的论证 —— 本 spec 正是要把尾码值改成非 skip。

15.2. 守卫 SHALL 钉死影响面：全库 classification sheet 名中「同时命中全名键与尾码键
   且取值不同」的集合 SHALL == 当前已知 2 条
   （`银行函证其他信息核对表E0-5`、`长期应付职工薪酬实质性程序表 L2A`，两者全名值均 `skip`）。
   集合变大时守卫 SHALL 红，迫使重新评估是否又出现了新的一码两表。

15.3. 守卫 SHALL 含**反向自检**：用**与任何真实循环无关的替身** sheet
   （如 `替身核对表XX-9` + `替身清单XX-9`）断言
   「全名 `skip` 在 → 该 sheet 不渲染；全名 `skip` 移除 → 按尾码解析」。

15.4. 本需求 SHALL NOT 修改 L709 / L722 / L749 三处判定的实现 —— 只加断言。
   误改 `skip` 过滤路径会让 `长期应付职工薪酬实质性程序表 L2A` 之类历史遗留表重新出现。

15.5. 🔴 本需求与 `e0-confirmation-completion` 的 **Task 19 / Property 28** 是**同一条不变式**。
   两侧 SHALL 择一实现、另一侧在 Notes 引用文件路径，**SHALL NOT 各写一份**
   （各写一份 → 改一处另一处不红，等于没守卫）。
   建议由**本 spec 实现**：它才是把尾码值改成 `confirmation-send-list-e05`、
   真正让这条不变式变关键的一方。

15.6. ~~翻转查表顺序（原方案 A）~~ / ~~删 `E0-5` 短键（原方案 B）~~ **均已作废**。
   当前顺序恰好正确，改动只会引入回归风险（波及全库 2 条已知一码两表 + 单 sheet 路径）。

### Requirement 16: E0-3 函证范围完整性红线（准则明文要求）

**User Story:** 作为业务合伙人，我要确认没有哪个"该函的银行账户"被漏掉 —— 零余额账户、本期内注销的账户、
发生额大但余额小的账户，全都必须函证；不函证的必须写明理由。体外账户是货币资金舞弊的第一入口。

**背景（源模板明文，不是平台自拟）**：
- `函证程序表E0A` 程序 1 逐字：「以积极方式对银行存款（**包括零余额账户和在本期内注销的账户**）……实施函证程序」
- `函证结果汇总表E0-1` 下区「二、样本选择」O28 逐字：「所有银行账户全部函证（包括零余额账户和在本期内注销的账户）。」
  O29：「**如果存在未函证的银行账户应记录不执行函证程序的理由。**」
  O30~O31：「审计准则规定的可以不执行银行函证程序的理由是：银行存款、借款及与金融机构往来的其他重要信息
  对财务报表不重要且与之相关的重大错报风险很低。」
- `回函情况汇编` 编制说明 2：「如无合理理由，应当将**发生额较大但余额较小的、零余额的、在本期内注销的**
  银行账户纳入函证范围。」说明 3：「重点关注本期交易活跃但期末已注销的银行账户的交易情况。」
  说明 1：「对完整性存有疑虑，应当亲自到中国人民银行或基本存款账户的开户行查询并打印《已开立银行结算账户清单》。」

**现状**：数据齐备（E0-3 有 `是否函证`(E) / `账户余额（原币）`(K) / `起始日期`(M) / `终止日期`(N)；
E1-3 有本期发生额；E1-10 有央行已开立账户清单），但**平台侧零校验** ——
R14 只做了 E0-5 的票据红线，E0-3 侧没有任何完整性红线。

#### Acceptance Criteria

16.1. 系统 SHALL 在 E0-3 提供「函证范围完整性」只读红线校验（对齐 R7.5 / R14.7 的紧凑 bar +
   可折叠明细 + `GtIndexChip` 追溯），SHALL NOT 阻断保存。

16.2. WHEN 某行 `账户余额（原币）` 为 0（含空视为未填、不判定）AND `是否函证` ≠「是」
   AND `备注` 未填不函证理由 THEN SHALL 报 **error**「零余额账户未纳入函证范围且未记录理由」。

16.3. WHEN 某行 `终止日期` 落在本审计期间内（即**本期内注销**）AND `是否函证` ≠「是」
   AND `备注` 未填理由 THEN SHALL 报 **error**「本期内注销账户未纳入函证范围且未记录理由」。
   `终止日期` 为空视为账户仍存续，SHALL NOT 判定。

16.4. WHEN 能从 E1-3 取到该账号的本期发生额 AND 发生额 ≥ 重要性水平（或可配置阈值）
   AND 余额 < 该阈值 AND `是否函证` ≠「是」THEN SHALL 报 **warning**「发生额较大但余额较小的账户未函证」。
   取不到发生额 THEN 该项 SHALL 为 `skip`，SHALL NOT 拿 0 当发生额。

16.5. WHEN 存在任一未函证账户 THEN SHALL 提示「E0-1『二、样本选择』需汇总记录不执行函证程序的理由」
   并提供跳转；源模板 O30~O31 的准则理由原文 SHALL 作为编制指引就地展示（琥珀色左边线范式）。

16.6. 阈值（重要性水平 / 发生额判定线）SHALL 可配置且优先取项目重要性水平（B15），
   SHALL NOT 在代码里写死金额。

16.7. 全部判定 SHALL 遵循 skip-on-missing：任一输入不可得时该项返 `skip` 而非用 0/空比较。

16.8. **账户完整性四方比对**（四表 `1002`/`1012` 叶子 ∪ E1-10 央行清单 ∪ E0-3 发函清单 ∪ 回函）
   SHALL NOT 由本 spec 实现（涉及新数据源，够独立 spec），但本条的红线 SHALL 为它预留
   `bank_account` 作为统一比对键，并在 Notes 登记该后续 spec 的入口。

### Requirement 17: 资金归集账户链路登记（不实现，只登记与提示）

**User Story:** 作为现场经理，资金池/资金归集账户的询证函必须附「附表(资金归集)」，
我要能看到"哪些账户标了资金归集、对应的函有没有核对这一项"。

**背景（源模板三处呼应）**：
- `E0-3` L 列逐字「是否属于资金归集（资金池或其他资金管理）账户」
- `函证程序表E0A` 程序 2：「必要时还应函证上市公司与银行间可能存在的其他安排，如
  **集团资金管理协议、控股股东资金池安排**等」
- `银行函证其他信息核对表E0-5` R 列 = 13 要项之一「**15.附表(资金归集)**」

**现状**：L 列在两份 spec 里都只是普通 `是/否` 枚举，**下游零消费**；
而核对表是隐藏 sheet 且 override 为 `skip`
→ **裁决门 A = A-否（2026-08-02 用户）后，这条链路的落点已确定为「永久不存在」**，
不再是"未裁决"状态。故 17.2/17.3 由「暂不实现」改为**永久留遗留**。

#### Acceptance Criteria

17.1. 本 spec SHALL 在 E0-3 组件上把 L 列标注为「风险标记」（与 O 列受限标记同款视觉），
   并在列 tooltip 写明源模板 E0A 程序 2 的要求原文。

17.2. 本 spec SHALL NOT 实现 L 列 → 核对表「15.附表(资金归集)」的勾稽
   —— **对侧表永久不存在**（`银行函证其他信息核对表E0-5` 为 hidden + `skip`，
   用户 2026-08-02 裁决不实现）。**宁缺勿造**：不得为了"有个勾稽"而自造一张对侧表。

17.3. 该链路 SHALL 在 Notes **永久登记为遗留**（不是"待裁决"），并写明：
   - 已裁决不实现的依据（`sheet_state` = hidden + `底稿目录` 只索引 9 张 + 用户裁决）
   - 若将来平台侧解决「隐藏 sheet 可控纳入渲染」并另立 spec 实现 13 要项表，
     则勾稽判定为「E0-3 有 L=是 的账户 但核对表该索引号行的『15.附表(资金归集)』为空」→ warning
   - **`E0A` 程序 2 的要求原文**（集团资金管理协议 / 控股股东资金池安排）SHALL 留存，
     它是 L 列存在的唯一依据 —— 载体的下游表不实现，但这条准则要求本身不消失

17.4. 资金归集账户同时意味着**关联方资金占用**（母公司资金池归集）→ SHALL 在 Notes 登记
   与 D2/K1 关联方往来的潜在提示点，SHALL NOT 在本 spec 实现。
