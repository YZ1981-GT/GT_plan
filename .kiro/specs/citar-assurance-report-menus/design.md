# 设计：CITAR「鉴证报告」四个菜单

## 0. 现状核对（2026-11-03 现算）
- 样表「税审底稿10.16.xlsx」207 个 sheet；计算模型 `backend/data/tax_workpaper_model.json` 192 个，缺 15 个：申报表封面、表单、A107011 / A107012 / A107041 / A107042 / A108020 / A108030 / A109010、审核报告说明及 -页眉页脚 / -格式、格式编制说明、封面、索引。原因：模型只收录 162 张底稿编号 sheet 及其公式传递引用到的格，A 类表只进了被引用的部分格。
- 案例 1：汇算申报表 36 张 A 类表非零数逐格与案例底稿一致（仅 A000000 H28/H29 投资方比例是手填）；报告正文 25 行 = `1-01报告正文` = A100000 对应行；审核说明由 `审核报告说明` 623 行规则生成；单体报表引用审计软件导出的审定报表，格式为 2001《企业会计制度》（A000000 第 107 项 = 300）。
- `审核报告说明` 1605 个公式中 1543 个带外部链接 `[1]`，指向样表旧文件名（同一工作簿），生成脚本原有 `_EXTERNAL_RE` 已剥除；用到 `TEXT(x,"#,##0.00")` 54 次，引擎未实现。

## 1. 计算模型扩展（生成脚本）
- 新增「额外编号」：申报表 37 张 + 审核说明 3 张进入 `codes`，编号用 ASCII：`TR-COVER`（申报表封面）、`TR-FORMS`（表单）、`A000000`…`A109010`、`RN-RULES`（审核报告说明）、`RN-HEADER`（-页眉页脚）、`RN-FORMAT`（-格式）。清单写在生成脚本 `EXTRA_CODES`（不进底稿索引 `taxWorkpaperIndex.ts`，底稿目录不受影响）。
- 这些 sheet 与底稿编号 sheet 同样：打印区内全部格进模型，公式传递引用照收；`readonly_codes`（RN-*）不接受保存。
- 前端显示结构：申报表 37 张输出到 `views/tax-return/sheets/<编号>.json`（与底稿 `sheets/` 分目录，两边 stale 检查互不影响），目录 `taxReturnIndex.json`（编号、表名、样表默认是否填报、表单行号）。
- 引擎补 `TEXT(value, format)`：支持 `#,##0.00` / `0.00` / `0` / `0%` / `0.00%` 等数字格式（千分位、小数位、百分比），文字原样返回。

## 2. 后端接口（`routers/tax_assurance.py`，前缀 `/api/projects/{pid}/tax-assurance`）
| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/tax-return/sheets/{code}` | readonly | 复用 `tax_workpaper_service.compute_sheet`（编号限申报表） |
| PUT | `/tax-return/sheets/{code}` | edit | 复用 `save_sheet_inputs`（含表单「是否填报」格） |
| GET | `/tax-return/export` | readonly | xlsx |
| GET | `/report-body` | readonly | 封面 + 正文字段、25 行金额、报告日期 |
| PUT | `/report-body` | edit | 保存报告日期（版本号） |
| GET | `/report-body/export` | readonly | docx |
| GET | `/review-notes` | readonly | 段落列表 |
| GET | `/review-notes/export` | readonly | docx |
| GET | `/financial-statements` | readonly | 自动选格式 + 各表行与金额 |
| GET | `/financial-statements/export` | readonly | xlsx |

- 报告日期存 `tax_workpaper_inputs`（`sheet_code='__assurance__'`，同表同版本机制，不新增表）。
- 编号校验：申报表接口只收 `TR-*` / `A\d{6}`，底稿接口拒收 `RN-*`（只读）。

## 3. 报告正文
- 值取 `compute_sheet('1-01')`：封面 A4、正文 A4 / E3（报告号单元格改取参数 B15）、F17~F41。0 值显示空（与案例一致）。
- 年度文字：样表常量里的「2025年度」按审核年度替换（`assurance_text.year_text`，报告正文、审核说明、申报表封面共用）。
- Word 模板 `backend/data/tax_assurance/report_body.docx`：生成脚本从案例 docx 把公司名、年度、报告号、日期、25 个金额格换成 `{{占位}}`；导出时逐段替换（处理 run 拆分：整段文字合并到首个 run）。

## 4. 审核说明（`services/tax_review_notes.py`）
- 规则行：`RN-RULES` 第 2 行起，列 A 标记 / B 内容 / C 格式（2~9 标题层级、文本1 / 文本2 正文）/ G 编号格式 / H 缩进 / I 占位数 / J~X 值。
- 显示规则（用案例 1 缓存值反推，模拟比对见 §8）：
  1. 「死行」：占位值全是字符串 `"0"`（规则表用 `IF(..,"0",..)` 表示不适用）⇒ 不显示，※ 也不显示。
  2. 标题行：※ = 上级显示即显示；﹟ = 上级显示 且（自带占位值 ⇒ 看自身「有数」；否则看其后第一个正文行是否显示，若其后紧跟子标题则看任一子标题是否显示）。
  3. 正文行：※ = 上级显示即显示；无标记 = 上级显示 且「有数」。
  4. 「有数」：只看后面紧跟「元」的占位（人、万元、项目名不算）；没有金额占位时任一占位非空非零即有数；没有占位的固定文字随上级显示。
  5. 同一列表（同编号格式、连续）最后一个显示项句末「；」改「。」。
  6. ※ 标题下没有任何显示的正文 ⇒ 补一段「无。」。
- 编号：标题格式按 G 列编号格式 1~7 → 一、/（一）/1、/（1）/①/I./i.，上级标题出现时下级计数清零；以文字写入段首。
- 金额格式：数字 `#,##0.00`；文字原样。
- Word：模板 `review_notes.docx` = 案例 docx 清空正文、保留样式 / 页眉页脚 / 节设置；格式 → 样式：4→`4`、2→`2`、3→`3`、5~9→`5`~`9`、文本1→`11`、文本2→`21`；H 列缩进 → 左缩进厘米。页眉单位名称取参数。

## 5. 单体财务报表（`services/tax_financial_statements.py` + `backend/data/tax_assurance/fs_enterprise_system.json`）
- 数据源：`standard_balance_view_service.build_standard_balance_view`（试算平衡表页同一份）：期末 = 审定数（自然正数按方向转借正贷负），资产负债表上年年末 = 期初；利润表本期 = 损益科目审定数；上期取 `prior_year_context.resolve_prior_source` 的上年同一视图，取不到时上期列空并写原因。
- 行定义：`{key, label, indent, bold, side: debit|credit, accounts:[{code, sign, exclude:[...]}], formula: "C7+C8-C9"}`；科目按前缀汇总（与报表 `TB()` 同口径），`exclude` 剔下级（应付工资 = 2211 剔 221102 等）。借方行取借正值，贷方行取负值（备抵科目用 sign = -1）。标准科目表无对应科目的行（待摊费用、预提费用、其他应交款、应收补贴款等）不配科目，显示空并在行上注明。
- 格式选择：`A000000!F6`（107 项）计算值 → 3xx = 企业会计制度、1xx = 企业会计准则；空 ⇒ 按项目 `accounting_standard`（enterprise→准则）并提示；其他 ⇒ 不支持提示。
- 企业会计准则：读平台已生成 `financial_report`（资产负债表、利润表、现金流量表、补充资料），未生成提示去「审定报表」生成。
- 现金流量表（两种格式）：取平台 `cash_flow_statement` / `cash_flow_supplement` 已生成数；企业会计制度格式按 `fs_enterprise_system.json` 的 `cf_row` 对应平台行编码。
- 校对：资产总计 = 负债和所有者权益总计、未分配利润勾稽，不平时页面提示差额。

## 6. 前端
- 菜单段：`report-body` / `review-notes` / `tax-return`（复用旧段，换组件）/ `financial-statements`。
- `views/tax-return/`：目录 + 表格（复用 `TaxWorkpaperGrid`、值接口格式一致）。
- `citar/screens/`：`CitarReportBody.vue`、`CitarReviewNotes.vue`、`CitarFinancialStatements.vue`。导出走 `downloadFile` 统一下载。

## 7. 测试
- 引擎 TEXT 单测；审核说明显示规则单测（构造规则行覆盖 1~6 条）；财务报表行公式单测（构造视图行）；四组端点 TestClient（401 / 403 / 200）；生成脚本 `--check`。
- 案例 1 验收脚本 `backend/scripts/check/check_tax_assurance_case.py --case-dir`：用案例底稿的输入值走模型，比对汇算申报表逐格、报告正文 25 行、审核说明段落结构。

## 8. 已知差异（案例 1 验收实测，2026-11-03）
- 汇算申报表：A000000 H28 / H29 投资方比例案例在申报表上手填；平台申报表这两格是公式（取底稿 1-12），应在底稿填。
- 审核说明 13 段差异，均为案例 docx 人工改动，不按规则生成、不为凑数改规则：单位名称 / 信用代码 / 法定代表人 / 盖章 4 段匿名化；职工福利费、职工教育经费、广告费 3 段法规引用版本不同（案例用旧版法规表述）；固定资产折旧、长期待摊、资产损失 3 段法规列举不同；弥补亏损段案例简写为「根据税法规定」；抵免所得税额段案例改写为短句；收入类调整一段案例删去句首「经审核，」。
- 编号：平台把编号写进段首文字，案例多数段落用 Word 自动编号；打印效果相同。
