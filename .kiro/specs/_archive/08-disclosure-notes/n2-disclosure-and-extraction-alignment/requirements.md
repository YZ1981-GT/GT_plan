# Requirements Document

## Introduction

N2 应交税费底稿的完整数据链路对齐：**四表入库 → 科目分类预填 → 审定表/明细表 → 披露表自动带入 → 推送附注模块**。

源模板权威 = `backend/wp_templates/N/N2 应交税费.xlsx`。

现状缺陷：
1. `_classify_tax_type` 把增值税分到了城建税的 `urban` 键（P0 bug）
2. 披露行骨架只有 5/10 种（源模板 13 种）
3. 附注模板只有 5/10 行（源模板 13 行）
4. 披露表无法从审定表/明细表自动带入数据（四表入库后到附注的链路断裂）
5. 税种名称在三层（源模板/明细表/分类器）之间不一致

## Requirements

### 1. 科目分类修正（P0）

- 1.1 `_classify_tax_type` 增值税必须返回独立键 `vat`（而非 `urban`）
- 1.2 新增缺失税种：资源税 `resource` / 矿产资源补偿费 `mineral-compensation` / 代扣代缴外国企业所得税 `withholding-foreign-cit` / 代扣代缴个人所得税 `withholding-iit`（与「个人所得税」`iit` 分开）
- 1.3 所有分类结果键必须可逆映射到源模板 13 行 label（一对一，无合并）
- 1.4 `_build_adjudication_prefill` 的输出键集必须覆盖源模板全部 13 税种
- 1.5 修正后不破坏已有数据（已录入的 `N2-1-urban-*` 键仍被读取，新键补充不覆盖）

### 2. 披露行骨架对齐源模板（P1）

- 2.1 `N2_LISTED_TAX_ITEMS` 从 5 种扩充到源模板 13 种，label 逐字取自 R8~R20
- 2.2 `N2_SOE_TAX_ITEMS` 从 10 种扩充到源模板 13 种，label 逐字取自 R8~R20
- 2.3 保留动态增删行能力（源模板 R21~R22 是预留空行 `可改名`）
- 2.4 保留合计行（源模板 R23 `合  计`）

### 3. 附注模板行骨架对齐（P1）

- 3.1 `note_template_listed.json` §五、41 rows 从 5 种扩充到 13 种 + 合计
- 3.2 `note_template_soe.json` §八、41 rows 从 10 种扩充到 13 种 + 合计
- 3.3 通过幂等脚本实现（`fix_note_n2_tax_structure.py --dry-run / --check`）
- 3.4 新增行的 `row_type: data`，label 逐字取源模板

### 4. 审定表 → 披露表数据自动带入（P1）

- 4.1 披露表首次恢复时若无持久化数据，从 `N2-1-adjudication-rows` 按 `taxType` 归一匹配自动带入
- 4.2 上市版带入字段：`期末余额 = endAudited`、`上年年末余额 = beginAudited`
- 4.3 国企版带入字段：`期初余额 = audBegin`（from N2-2）、`本期应交 = audPayable`（from N2-2）、`本期已交 = audPaid`（from N2-2）、`期末余额 = 行内公式`
- 4.4 归一映射规则 = `_normalizeTaxNameForN4` 的逻辑扩展（覆盖源模板 13 种 → 统一名）
- 4.5 手工覆盖优先：用户编辑过的行不再被自动刷新覆盖
- 4.6 从审定表带入时使用**审定期末数**（endUnadj + endAje + endRje）

### 5. 附注推送正确性（P1）

- 5.1 推送 13 行 + 动态增行 + 合计行，附注模块正确渲染
- 5.2 列键与附注模板 columns 逐字对齐（上市 end/prior / 国企 opening/payable/paid/end）
- 5.3 动态行区域：源模板 R21~R22 对应用户增加的自定义税种行，推送时正常带入
- 5.4 合计行合并推送（`is_total: true`）

### 6. 税种名称归一映射表（跨层真源）

- 6.1 建立从 tb_balance `account_name` → 源模板披露 label 的归一映射表
- 6.2 该映射表为审定预填、披露带入、N4 联动三处共用的单一真源
- 6.3 映射须覆盖已知变体名（车船牌照税 = 车船税 / 城镇土地使用税 = 土地使用税 / 代扣代缴个人所得税 ≠ 个人所得税 等）

### 7. 公式预设核查

- 7.1 确认 `prefill_formula_mapping.json` 的 N2 审定表 5 公式与 `_build_adjudication_prefill` Python 实现**语义一致**
- 7.2 如存在不一致，以 Python 实现为权威（它是运行态真源），更新 JSON 使两者对齐
- 7.3 明细表 AUX 公式暂不消费（未来由公式管理面板统一接入），本 spec 只核查不实现
