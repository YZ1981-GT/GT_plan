# H0 列配置与 xlsx 冲突决议

> Phase 0 产出 · 2026-07-05  
> 依据：`h0_structure_summary.json`（openpyxl 实读）+ `blockColumnConfigsH05.ts` + F0-5/G0-6 已验证模式

## 决议原则

1. **HTML 交互层**以 `confirmation-alternative-h05` 四区块宽表为准（复用 D0-5 Dashboard/Master/CheckBlock）。
2. **xlsx 源模板** `替代程序H0-5`（35×29，6 公式）为**单公司纵向版式**；导入导出采用 **G0-6 四 sheet 分区块** 结构，不按 xlsx 逐格 1:1 映射。
3. **wp_code_overrides** `H0-5 → confirmation-alternative-h05` 优先于 `H0.yaml` 自动生成字段。

## 结构对照

| 维度 | xlsx（替代程序H0-5） | HTML（alternative-h05-v1） |
|------|----------------------|----------------------------|
| 布局 | 单 sheet 35 行 × 29 列，按公司纵向展开 | Master-Detail：公司清单 + 4 区块检查表 |
| 区块 | 模板内 1~4 节标题行（测试范围/特定样本） | block1~4 独立列组（见 blockColumnConfigsH05） |
| 公式 | 6 个单元格公式（A3/F3/K3 等） | 前端 `useH0FormulaEngine` 重算比例与异常 |
| 比例 | 模板文案描述抽样范围 | 权属证据比例 = 区块②合计/期末余额；验收证据比例 = 区块①凭证合计/期末余额 |

## 四区块列决议（HTML 权威）

| 区块 | HTML title | 导入 sheet 名 | 关键证据列 |
|------|------------|---------------|------------|
| block1 | 期后验收/权属证据检查 | ①期后验收/权属证据 | 验收单、权属证书 |
| block2 | 期末余额支持性证据 | ②期末余额支持性证据 | 合同/发票/付款 |
| block3 | 本期新增资产检查 | ③本期新增资产检查 | 请购/到货/转固 |
| block4 | 抵押担保/融资租赁证据 | ④抵押担保/融资租赁 | 抵押/租赁/他项权证 |

xlsx 中「固定资产/工程物资/使用权资产…」合并标题行 → 映射为 `balance.item_name` 默认值「固定资产/在建工程」。

## 跨底稿引用

| 字段 | 决议 |
|------|------|
| `ref_index` | 可链 H1/L1/L3；导入导出保留文本列 |
| H0-1 → H0-5 | `wp-id-by-code` + render-config 取 `confirmation-v1` 未回函行，映射为公司清单（同 G0-1→G0-6） |

## 未决 / 后续

- OCR 行级识别：H0-5 暂未接入 contract-ocr（固定资产单据类型待专项映射）。
- xlsx OnlyOffice 降级：保留 `GtGridSheet` 只读旧格式路径。
