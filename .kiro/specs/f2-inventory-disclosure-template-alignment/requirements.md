# Requirements Document

## Introduction

存货循环的披露链路有两个落点：

1. **底稿披露表**（F2 底稿内的两个 Tab）
   - `F2TabDisclosureListed.vue` ← 源模板 sheet「附注披露信息（上市公司）」
   - `F2TabDisclosureSoe.vue` ← 源模板 sheet「附注披露信息（国企）」
   - 源模板：`基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/4.风险应对-实质性程序（D-N）/F 存货循环/F2 存货及跌价准备/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx`

2. **附注模块**「报表主要项目附注 → 存货」
   - 上市版 `note_template_listed.json` §五、9
   - 国企版 `note_template_soe.json` §八、10
   - 源模板：`基础数据/附注模版/上市报表附注.md`、`基础数据/附注模版/国企报表附注.md`

两者由 `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper` 单向连接（披露表 → 附注）。

经逐单元格核对，**分类行与取数口径已对齐**，缺口集中在比例口径、章节切分、缺表、附注列结构四类。本 spec 以源模板为唯一权威，修复这四类缺口。

## Glossary

| 术语 | 含义 |
|------|------|
| 计提比例 | 本组合存货跌价准备 ÷ 本组合账面余额（源模板 `F52=D52/B52`） |
| 占比 | 本组合账面余额 ÷ 合计账面余额（源模板 `C52=B52/B54`） |
| `_column_groups` | 附注表两级表头渲染元数据 `[{group, start, span}]`，被 `DisclosureEditor.activeTableColumns` 与 `note_word_exporter` 共同消费 |
| `header_label` 行 | 历史上把源模板第二行表头降级成数据行的产物，渲染为假数据行 |
| `ColumnDef.group` | 同步载荷列头元数据的分组父表头字段，后端 `_extract_column_groups` 据此产出 `_column_groups` |
| ⑤数据资源存货表 | 附注存货章节第 5 张表「确认为存货的数据资源」，校验口径见 `check_presets_md.F9-7~F9-13a` |

## Requirements

### Requirement 1: 上市披露表「按组合计提」比例口径修正

**User Story:** 作为审计助理，我在上市披露表 (3) 填入组合的账面余额与跌价准备后，希望「比例(%)」列显示的是计提比例，与源模板和附注一致，避免披露错误。

#### Acceptance Criteria

1. WHEN 某组合账面余额 = 1000、跌价准备 = 150 THEN 系统 SHALL 在「存货跌价准备-比例(%)」显示 `15.00%`（150/1000），而非该组合跌价占跌价合计的比例
2. WHEN 合计行账面余额 = 5000、跌价准备合计 = 400 THEN 系统 SHALL 在合计行「存货跌价准备-比例(%)」显示 `8.00%`（400/5000）
3. WHEN 某组合账面余额 = 0 THEN 系统 SHALL 在该行「存货跌价准备-比例(%)」显示 `-`，且不出现 `#DIV/0!` / `Infinity` / `NaN`
4. WHEN 渲染「账面余额-比例(%)」列 THEN 系统 SHALL 保持原口径（本组合账面余额 ÷ 合计账面余额），合计行为 `100.00%`
5. WHEN 渲染期末余额表与上年年末余额表 THEN 系统 SHALL 对两表采用同一算法

### Requirement 2: 上市披露表章节切分对齐源模板

**User Story:** 作为现场经理复核披露表，我希望页面小节编号与源模板一一对应，便于逐条核对。

#### Acceptance Criteria

1. WHEN 打开上市披露 Tab THEN 系统 SHALL 把「(4) 存货期末余额中含有借款费用资本化金额的说明」渲染为独立小节卡片，不再嵌在 (3) 卡片内部
2. WHEN 渲染 (4) 小节 THEN 系统 SHALL 展示源模板提示语「15号文第十九条（六）披露存货期末余额中含有的借款费用资本化金额及其计算标准和依据。」
3. WHEN 渲染 (4) 小节 THEN 系统 SHALL 提供「合同履约成本本期摊销金额的说明」文本框（源：附注模版「（说明合同履约成本本期摊销金额。）」）
4. WHEN 触发同步到附注 THEN 系统 SHALL 把该文本框内容随 `_note_texts` 以 `listed-note-amort` 推送
5. WHEN 修订完成 THEN 系统 SHALL 保持 (1)(2)(3)(5)(6)(7) 小节编号与表结构不变

### Requirement 3: 两版披露表补「确认为存货的数据资源」表

**User Story:** 作为审计助理，存货中含数据资源时，我希望在披露表一次录入数据资源三段式明细，直接同步进附注，而不必在附注模块重新手填。

#### Acceptance Criteria

1. WHEN 打开上市或国企披露 Tab THEN 系统 SHALL 各渲染一张「确认为存货的数据资源」表，列为：项目 / 外购的数据资源存货 / 自行加工的数据资源存货 / 其他方式取得的数据资源存货 / 合计
2. WHEN 渲染该表行 THEN 系统 SHALL 逐字采用附注模版的 21 行结构（一、账面原值含 1~4 与「其中」子项；二、存货跌价准备（国企作「二、跌价准备」）；三、账面价值）
3. WHEN 用户在三个来源列填入数值 THEN 系统 SHALL 自动求和到「合计」列且该列只读
4. WHEN 小节行（如「2.本期增加金额」）下存在「其中」子项 THEN 系统 SHALL 允许小节行独立录入，不被子项自动覆盖
5. WHEN 计算「4.期末余额」THEN 系统 SHALL 按 `期初余额 + 本期增加 − 本期减少` 自动计算且只读
6. WHEN 计算「三、账面价值」THEN 系统 SHALL 令「1.期末账面价值」= 原值期末 − 跌价期末、「2.期初账面价值」= 原值期初 − 跌价期初，且两行只读
7. WHEN 触发同步到附注 THEN 系统 SHALL 把该表作为子表「确认为存货的数据资源」推送并携带 `columns` 列头元数据
8. WHEN 该表全部录入行为 0 THEN 系统 SHALL 提示该表可不填，且不阻断保存
9. WHEN 某「其中」子项之和超过其父项 THEN 系统 SHALL 行内告警提示，且不阻断保存

### Requirement 4: 附注模块存货章节列结构按模板修复

**User Story:** 作为编制附注的审计助理，我打开「报表主要项目附注 → 存货」时，希望看到与附注模版一致的两级表头，而不是「项目」「组合」这类假数据行。

#### Acceptance Criteria

1. WHEN 加载上市 §五、9「存货分类」THEN 系统 SHALL 提供 7 列：项目 + 期末余额{账面余额, 跌价准备/合同履约成本减值准备, 账面价值} + 上年年末余额{同 3 列}，并带 `_column_groups`
2. WHEN 加载上市 §五、9「存货跌价准备及合同履约成本减值准备」THEN 系统 SHALL 提供 7 列：项目 / 期初余额 / 本期增加{计提, 其他} / 本期减少{转回或转销, 其他} / 期末余额
3. WHEN 加载上市 §五、9 的 4 张「按组合计提」表 THEN 系统 SHALL 各提供 7 列：组合 + 账面余额{金额, 比例(%)} + 存货跌价准备{金额, 计提标准, 比例(%)} + 账面价值
4. WHEN 加载国企 §八、10「存货分类」THEN 系统 SHALL 提供 7 列（期末数 / 期初数 各 3 列）
5. WHEN 加载国企 §八、10「存货跌价准备及合同履约成本减值准备」THEN 系统 SHALL 提供 8 列：存货种类 / 期初数 / 本期增加{计提, 其他} / 本期减少{转回, 转销, 其他} / 期末数
6. WHEN 修订被修复的表 THEN 系统 SHALL 删除其 `row_type: header_label` 行（语义已由 `_column_groups` 承载）
7. WHEN 修订完成 THEN 系统 SHALL 令各表 `len(headers) - 1` 等于每行 `values` 长度，且合计行回填不串列
8. WHEN 存在重名的「续：」表 THEN 系统 SHALL 改为可区分且与同步子表键一致的名称
9. WHEN 修订完成 THEN 系统 SHALL 补齐源模版缺失的 `text_sections`（国企数据资源提示段等）
10. WHEN 重复执行修订 THEN 系统 SHALL 保持幂等：不产生重复表、不重复追加文本段

### Requirement 5: seed 列元数据贯通到附注渲染

**User Story:** 作为编制附注的审计助理，我不做任何同步操作、只用模板生成的附注，也应看到两级表头。

#### Acceptance Criteria

1. WHEN seed 模板表带 `columns` 或 `_column_groups` THEN 系统 SHALL 令生成的 `note.table_data._tables[i]` 携带同名字段
2. WHEN seed 模板表未声明这些字段 THEN 系统 SHALL 不写入该字段，对既有章节零影响
3. WHEN 附注来源为 workpaper 同步 THEN 系统 SHALL 保持 `project_sub_tables` 投影路径与 `_source` 优先级不变
4. WHEN 导出 Word THEN 系统 SHALL 复用同一 `_column_groups` 渲染两行表头

### Requirement 7: 数据资源表与分类表交叉勾稽

**User Story:** 作为审计助理，我在数据资源明细表填完三段式后，希望系统提示它与（1）分类表「数据资源」行是否勾稽，避免附注两张表自相矛盾。

#### Acceptance Criteria

1. WHEN 数据资源表账面原值段「4.期末余额」合计列 ≠ （1）分类表「数据资源」行期末账面余额 THEN 系统 SHALL 显示差异告警（对应 `check_presets_md.F9-12`）
2. WHEN 账面原值段「1.期初余额」合计列 ≠ 分类表「数据资源」行期初/上年年末账面余额 THEN 系统 SHALL 显示差异告警（`F9-12a`）
3. WHEN 跌价准备段「4.期末余额」合计列 ≠ 分类表「数据资源」行期末跌价准备 THEN 系统 SHALL 显示差异告警（`F9-13`）
4. WHEN 跌价准备段「1.期初余额」合计列 ≠ 分类表「数据资源」行期初跌价准备 THEN 系统 SHALL 显示差异告警（`F9-13a`）
5. WHEN 差异绝对值 < 0.01 THEN 系统 SHALL 视为勾稽通过，不告警
6. WHEN 数据资源表全空 THEN 系统 SHALL 不因分类表有数而告警（避免未填即报错）
7. WHEN 告警展示 THEN 系统 SHALL 与（2）跌价变动表 `tieDiff` 采用一致的视觉与文案风格（同页标准统一）
8. WHEN 存在勾稽差异 THEN 系统 SHALL 不阻断保存与同步

### Requirement 8: 披露 Tab 接入 AI 辅助 / 复核 / 导入导出三件套

**User Story:** 作为审计助理，披露表和 F2 其它底稿页一样，我希望文本框能用 AI 起草、能挂复核意见、表格能与 Excel 互导。

#### Acceptance Criteria

1. WHEN 打开上市或国企披露 Tab THEN 每个文本域 SHALL 在其所属 section 标题行右侧提供「AI 辅助」按钮
2. WHEN AI 不可用（`aiAvailable` 为假）或页面只读 THEN 该按钮 SHALL 禁用
3. WHEN 点击 AI 辅助 THEN 系统 SHALL 走 F2 既有 `useF2AiGenerate` 的生成 + 确认流程，不新建 AI 通道
4. WHEN 打开披露 Tab THEN 系统 SHALL 提供 `F2ReviewChip` 复核入口，`section-id` 与该 section 一一对应且不与其它 Tab 冲突
5. WHEN 打开披露 Tab THEN 系统 SHALL 提供「导入导出▾」下拉（复用 `CycleImportExportDropdown`），多区块导出 SHALL 分 sheet
6. WHEN 接入完成 THEN 系统 SHALL 复用既有 `F2SheetToolbar` 或与其行为一致，不重复实现三件套

### Requirement 9: 金额显示与录入回归平台单一真源

**User Story:** 作为审计助理，我在顶栏「显示设置」切成千元后，披露表的金额也应跟着变，而不是只有附注侧变。

#### Acceptance Criteria

1. WHEN 只读金额渲染 THEN 系统 SHALL 走平台单一真源（`@/utils/formatters` 的 `fmtAmount` + `displayPrefs`，或 `GtAmountCell`），删除 Tab 内本地 `fmtAmount` 副本
2. WHEN 用户切换全局金额单位（元/千元/万元）或小数位 THEN 披露表只读金额 SHALL 同步变化
3. WHEN 渲染只读金额单元格 THEN 系统 SHALL 保持右对齐 + 千分符 + `tabular-nums` 不折行
4. WHEN 编辑金额 THEN 系统 SHALL 使用 `composables/wpAmountInput.ts` 的 formatter/parser 并以 `el-input` 承载，使录入态也显示千分符
5. WHEN 该字段为比例 / 计提标准 / 项目名称等非金额 THEN 系统 SHALL NOT 套用金额 formatter
6. WHEN 改造完成 THEN 既有数值断言与 Playwright 实测值 SHALL 保持不变（纯显示层改造，不改数值口径）

### Requirement 10: 房企单级表抑制凭空父表头

**User Story:** 作为复核人，开发成本/开发产品/周转房在源模板是单行表头，我不希望附注里多出「本期」这层。

#### Acceptance Criteria

1. WHEN 附注渲染 F2 房企 3 表 THEN 系统 SHALL NOT 显示源模板不存在的父表头
2. WHEN 实现该抑制 THEN 系统 SHALL 采用显式声明方式，不修改 `_infer_groups_from_headers` 推断算法本身
3. WHEN 其它未声明该标记的表 THEN 系统 SHALL 保持现有推断行为不变

### Requirement 11: 补齐自设计承诺的验证手段

**User Story:** 作为质量控制复核合伙人，我要求 design 里承诺的验证方式与实际交付一致，不能留不实标注。

#### Acceptance Criteria

1. WHEN design 标注某 Property 用 PBT 验证 THEN 系统 SHALL 存在对应的 property-based 测试，否则 SHALL 修正 design 措辞
2. WHEN 附注存货章节含两级表头 THEN 系统 SHALL 实测 Word 导出该章节渲染为两行表头（合并单元格正确）
3. WHEN 实测发现导出不符 THEN 系统 SHALL 修复后重验，不得以「单测已覆盖」替代实测

### Requirement 12: 跨会话共享文件的守卫前移

**User Story:** 作为工程治理负责人，并发会话回退别人的模板对齐时，我希望 CI 立刻报红，而不是靠下一个人偶然发现。

#### Acceptance Criteria

1. WHEN 附注模板存货章节结构被回退 THEN CI SHALL 通过 `fix_note_inventory_structure.py --check` 失败并提示重跑修订脚本
2. WHEN 校验脚本名称与其实际校验对象不符 THEN 系统 SHALL 更名或在文档中明确区分，避免被误当 JSON 守卫
3. WHEN 更名脚本 THEN 系统 SHALL 同步更新全部引用点（测试 / CI / 文档），不留悬空引用

### Requirement 6: 回归保护

**User Story:** 作为质量控制复核合伙人，我需要确认本次结构性改动没有破坏既有披露同步与附注生成链路。

#### Acceptance Criteria

1. WHEN 运行 `useF2DisclosureListed` / `useF2DisclosureSoe` 单测 THEN 系统 SHALL 全部通过（比例断言按 Requirement 1 更新）
2. WHEN 运行披露同步契约检查（`disclosureSyncUrlContract` / `check_disclosure_columns_coverage`）THEN 系统 SHALL 全部通过
3. WHEN 运行 `test_note_template_row_type` 与 note formula 相关后端测试 THEN 系统 SHALL 全部通过
4. WHEN 运行 `fix_note_inventory_structure.py --check` THEN 系统 SHALL 校验通过（附注 JSON 结构真守卫；`validate_note_docx_placeholders.py` 只校 docx 占位符，其失败为既有基线）
5. WHEN 用 Playwright 实测两个披露 Tab 与附注存货章节 THEN 系统 SHALL 正确渲染两级表头与 TAB 页签
