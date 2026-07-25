# K 循环编码双方案歧义（数据治理待办）

> 状态：**已在显示层消歧**（公式管理树/选字段树用 `sheet_display_names.json` +
> `prefill_formula_mapping.json` 给出正确名称）；**编码语义歧义本身需致同编码 owner 确认收敛**，
> 前端无法单方面决定。本文档记录事实，供治理决策。

## 现象

系统内 K 循环存在**两套并行编码方案**，对同一/相近科目分配了不同编码：

| 编码 | 名称（`prefill_formula_mapping.json`） | 科目 |
|------|------|------|
| K7 | 递延收益审定表 | 2401 递延收益 |
| K10 | 其他收益审定表 | 6117 其他收益 |
| **K14** | 资产处置收益审定表 | 6115 资产处置收益 |
| **K15** | 其他收益审定表 | **6117 其他收益**（与 K10 重叠）|
| **K16** | 投资收益审定表 | 6111 投资收益 |
| **K17** | 公允价值变动收益审定表 | 6101 公允价值变动收益 |
| **K18** | 递延收益审定表 | **2401 递延收益**（与 K7 重叠）|

- K1~K13 是致同标准编号（K1 其他应收款 … K13 营业外支出）。
- K14~K18 是**上市公司损益类**的另一套 K 编号，与 K7/K10 的科目**重叠**。
- `wp_index`（项目实例）里 K14~K18 的名称**跨模板集互相冲突**（如 K14 出现过
  「内部控制缺陷程序表」「资产处置收益审定表」「底稿K14」三种），说明不同模板集
  各自复用了 K14~K18 编码 → **无单一权威名**。

## 证据来源

- `backend/data/prefill_formula_mapping.json`（mappings，含 wp_name + account_codes，单一命名）
- `backend/data/wp_account_mapping.json`（致同标准 206 编码，**不含** K14~K18）
- `workpaper_sheet_classification`（K14~K18 仅裸编码，无描述名）
- `wp_index`（K14~K18 名称跨项目冲突）

## 已做的显示层处理（不改数据）

- `sheet_display_names.json` 生成器（`scripts/gen_sheet_display_names.py`）用
  `prefill_formula_mapping.json` 兜底补名 → K14~K18 在树里显示为
  「资产处置收益/其他收益/投资收益/公允价值变动收益/递延收益审定表」。
- 各源均无 distinct 名时，前端 `composeSheetLabelsForGroup` 追加序号（1）（2）消歧。

## 风险 / 建议

1. **报表/附注映射**若也按 K 编号取数，K15↔K10（其他收益 6117）、K18↔K7（递延收益 2401）
   的重叠可能导致同一科目被两处引用/双算 —— 建议核查 report_line_mapping / note 映射
   是否同时挂了两套 K 编码到同一 account_code。
2. **收敛建议**：由致同编码 owner 明确 K14~K18 是否为**上市版专属**（与 K7/K10 互斥、
   按报告准则二选一），并在 `wp_account_mapping.json` 补齐权威条目（含 report_row/
   note_section），使其成为单一真源；届时 `prefill` 兜底可退役。
3. 在收敛前，**禁止**前端/后端臆造 K14~K18 的「唯一」名称覆盖项目实例的实际命名。
