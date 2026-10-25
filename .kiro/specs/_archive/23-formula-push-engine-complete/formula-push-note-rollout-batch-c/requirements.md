# 公式推送附注铺开 · 批 C：已注册码加附注规则

## 背景

上游 `formula-push-all-subjects-rollout`（26/26 ✅）完成了平台化改造和 E1 附注推送 canary。
当前 20 个已注册 binding 中**只有 E1 有附注推送规则**（`has_note_rules: true`）。
本 spec 为其余已注册 binding 中**有附注章节映射的科目**添加附注推送规则。

## 现状实证（2026-10-05 现算）

| 编号 | 事实 |
|------|------|
| C-S1 | 已注册 binding 20 个：E1 + K1 + 18 个 Tier A（D1~D7/H5~H10/I1~I6） |
| C-S2 | 四套附注模板编号体系各不相同：单体 soe `八、N` / 单体 listed `五、N` / 合并 soe `五-N-M` / 合并 listed `五-N-M`。同一科目在四套中编号完全不同，偏移量不固定 |
| C-S3 | `wp_account_mapping.json` 的 `note_section`（如 `五、5`）是**上市版单体编号**，与其他三套无固定映射关系，且部分条目指向的章节内容与科目不匹配 |
| C-S4 | 四套模板可按**科目名**（`section_title` / `parent_section`）做精确跨版匹配——科目名在四套中一致 |
| C-S5 | 有附注推送规则的：仅 E1（`has_note_rules: true`） |
| C-S6 | 四套编号对照异常 24 条：部分科目有单体无合并（如"一般风险准备"），部分有合并无单体（如"费用性质列示"的多个子项），科目名措辞国企/上市有差异（如 soe "资产处置收益" vs listed "资产处置收益（损失以"-"填列）"）|
| C-S7 | 合并附注模板（`consol_note_sections_*.json`）用 `parent_section`（科目名）分组，`section_id`（如 `五-5-1`）做定位；单体模板用 `section_number`（如 `八、5`）+ `section_title`（科目名） |

## 术语

| 术语 | 含义 |
|------|------|
| 四套模板 | 单体 soe / 单体 listed / 合并 soe / 合并 listed |
| 科目名定位 | 用科目名（如"货币资金"）而非编号（如"八、1"/"五、1"）跨四套模板定位同一科目的附注章节 |
| 章节四元组 | 同一科目在四套模板中的编号集合 `(single_soe, single_listed, consol_soe, consol_listed)` |

## 需求

### 需求 1：章节映射基础设施

1. SHALL 建立**按科目名的四套模板章节映射表**（生成式，`--check` 幂等），产出每个科目的章节四元组
2. 映射逻辑 SHALL 以**科目名精确匹配**为主，科目名在国企/上市版措辞不同时 SHALL 支持别名（如 soe "资产减值损失" ↔ listed "资产减值损失（损失以"—"号填列）"）
3. 推送规则的 `section_by_template` SHALL 直接引用该映射表的产出，不硬编码编号

### 需求 2：Tier A 附注推送能力

1. `TierAAnchorBinding.note_rows()` SHALL 按规则声明的附注字段，从试算表取数构建附注行
2. 行数据格式 SHALL 与 E1 的 `note_rows` 输出一致
3. 单科目的 Tier A SHALL 只推主表一行（科目名=行标签）
4. 多科目的 Tier A（如 I1 = 1701+1702+1703）SHALL 推多行 + 合计行

### 需求 3：K1 附注推送

1. `K1Binding.note_rows()` SHALL 输出其他应收款主表的期末/期初合计值
2. 只推主表合计行，不推子表

### 需求 4：附注推送规则

1. 每个目标科目 SHALL 在 `formula_push_rules.json` 中有附注推送规则
2. 规则中章节编号 SHALL 分别声明 listed 和 soe 两版的**单体附注章节编号**
3. 两版中任一版无对应章节的 SHALL 声明为 null（推送时跳过该版）
4. 规则 `target.fields` SHALL 为 `["end_amount", "prior_amount"]`

### 需求 5：验收

1. 每个新增附注规则 SHALL 有真 ORM 集成测试
2. 规则清单校验通过；现有推送测试全绿无回归
3. 合并附注推送（`consol_note_formula_service`）不在本 spec 范围，但 SHALL NOT 被破坏

## 交付范围

**目标科目**（2 个，探针按科目名匹配到附注模板的）：

| 编码 | 科目名 | 科目码 | 上市附注 | 国企附注 | 主表列 | 备注 |
|------|------|------|------|------|------|------|
| K1 | 其他应收款 | 1221 | **五、8** | **八、9** | end_amount + prior_amount | `note_section` 五、5 指向应收账款，已由探针校正 |
| I3 | 商誉 | 1711 | **五、28** | **八、29** | end + begin（变动表） | `note_section` 五、13 指向其他流动资产，已由探针校正；🔴 主表是变动表非简单期末/期初 |

**因表结构复杂或模板缺失而排除的**（8 个）：
- H5：listed 模板无"油气资产"章节，仅 soe 有（八、25），且为变动表
- H7/H8/I1/I4：按名搜可匹配但主表结构为复杂变动表或多分类表，非简单期末/期初
- H9/I6：按名搜可匹配（H9 listed 五、47 / soe 八、52；I6 listed 五、66 / soe 八、67）且结构简单，但原 requirements 排除在外
- H10：两版模板均无"资产处置损益"独立章节
- **注**：原排除理由"`note_section` 映射错位"在探针实证后发现**10 个全部错位**（含 K1/I3），错位不是排除原因而是全局性质。真正的排除原因是表结构复杂或模板缺失

## 非目标

- 未注册的 28 个底稿编码的 binding 和附注推送（另立批 D spec）
- D1~D7 的附注推送（这些科目在 `wp_account_mapping` 中无 `note_section`）
- `wp_account_mapping.json` 的 `note_section` 映射修正（独立维护任务）
- 复杂附注子表（坏账变动、账龄分布等）——本 spec 只推主表合计数
- 合并附注（`consol_note_sections`）——本 spec 只涉及单体附注
