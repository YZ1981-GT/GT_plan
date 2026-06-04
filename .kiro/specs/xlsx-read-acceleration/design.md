# Design: xlsx 读路径 calamine 加速推广

## Overview

**现状勘察修正**：python-calamine 并非从零引入——它已在账表导入链路成熟落地（feature flag `ledger_import_use_calamine`=True / `excel_parser_calamine.py` / 行为等价测试 `test_excel_parser_calamine.py` / 按 sheet 行数 500k 阈值动态切 engine / 内存压力降级回 openpyxl）。memory.md 记的 "3.4× 加速" 即此。

本 spec 的真实目标：**把已验证的 calamine 纯读能力，从 ledger import 推广到底稿模板提取的 `data_only=True` 只读场景**，复用已验证的等价性方法论与降级策略，不动写路径。

## 现状勘察

### calamine 已有资产（复用）
- `backend/app/services/ledger_import/parsers/excel_parser_calamine.py`：`iter_excel_rows_from_path_calamine` / `_load_sheet`（CalamineWorkbook）
- `feature_flags.py`：`ledger_import_use_calamine`（pilot→production）+ 项目级 `set_project_flag` 回退
- `pipeline.py`：`_choose_excel_iter` 按 sheet 行数动态选 engine + 内存降级
- 等价测试：`test_excel_parser_calamine.py`（数值语义相等 / data_start_row / chunk / forward_fill / sheet 缺失 / 类型差异）

### calamine 与 openpyxl 已知差异（等价测试已固化）
- 数字 int vs float：calamine 可能 `123` 或 `123.0`
- 空单元格：calamine 可能读为 `""`，openpyxl 为 `None`
- **calamine 只读纯值**（不含样式/公式/合并单元格元数据）——这是关键约束

### 候选迁移点分类（按是否纯读 + 是否需样式）

| 读点 | 模式 | 是否需样式/公式/合并 | 可迁移 calamine |
|------|------|---------------------|----------------|
| `wp_grid_extract.py` extract_grid | data_only=True | **需要**（fill/bold/merged_cells/col_width）| ❌ 否（依赖样式提取，calamine 无样式）|
| `wp_program_extract.py` | data_only=True | 仅取值（定位表头+文本）| ✅ 是 |
| `wp_audit_sheet_extract.py` extract_audit_rows/sections | data_only=True | 仅取值 | ✅ 是 |
| `wp_generic_processor.py` | data_only=True, read_only=True | 仅取值 | ✅ 是 |
| `wp_template_diff_service.py` | data_only=True, read_only=True | 仅取值 | ✅ 是（diff 比值）|
| `wp_fine_rule_engine.py` | data_only=True, read_only=True | 仅取值 | ✅ 是 |
| `import_template_service.py` | data_only=True, read_only=True | 仅取值 | ✅ 是 |
| `xlsx_to_univer.py` | data_only=False + True 双载 | **需公式文本+样式** | ❌ 否 |
| `wp_xlsx_export_service.py` / `report_excel_exporter.py` / `wp_header_service.py` / `prefill_engine.py` 写回 | data_only=False 写 | **写路径** | ❌ 否（写仍 openpyxl）|

> 结论：**仅迁移"纯取值、不依赖样式/公式/合并"的只读提取点**。需样式的（wp_grid_extract）和写路径（导出/预填回写）保持 openpyxl。

## Architecture

### 统一只读取值适配器（`xlsx_read_adapter.py` 新建）

把"按 sheet 名取二维值数组"的能力抽成统一入口，内部按 flag + 可用性选 engine，复用 ledger import 的 calamine 加载逻辑：

```python
# backend/app/services/xlsx_read_adapter.py
def read_sheet_values(
    path: str | Path,
    sheet_name: str | None = None,   # None=活动表/第一个表
    *,
    prefer_calamine: bool = True,
) -> list[list[Any]]:
    """统一只读取值：返回 sheet 的二维值数组（不含样式/公式）。

    prefer_calamine 且 calamine 可用 → CalamineWorkbook（复用 excel_parser_calamine 加载）
    否则 → openpyxl read_only=True, data_only=True
    数值归一化：与 ledger import 等价测试一致（int/float 容忍、空→None 归一）
    """

def list_sheet_names(path) -> list[str]: ...
```

- 归一化层：把 calamine 的 `""`→`None`、`123.0`→保持（消费方已容忍）统一，确保替换 openpyxl 后行为等价
- 全局开关 `XLSX_READ_USE_CALAMINE`（默认 True）+ 单点 `prefer_calamine=False` 局部回退

### 各提取点改造（最小侵入）

每个可迁移点：把 `openpyxl.load_workbook(...).` + `ws.iter_rows(values_only=True)` 替换为 `read_sheet_values(path, sheet_name)`，逻辑不变。

```python
# wp_program_extract.py 示意（改造前）
wb = openpyxl.load_workbook(str(fp), read_only=False, data_only=True)
ws = wb[sheet_name]
for row in ws.iter_rows(values_only=True): ...

# 改造后
from app.services.xlsx_read_adapter import read_sheet_values
rows = read_sheet_values(fp, sheet_name)
for row in rows: ...
```

### 安全网：行为等价测试先行

参照 `test_excel_parser_calamine.py` 模式，对每个迁移点补"calamine vs openpyxl 输出等价"测试，**先证等价再切**。等价不成立的点（如发现某模板的合并单元格展平差异影响提取）→ 该点保留 openpyxl，记录原因。

## 配置

```python
XLSX_READ_USE_CALAMINE: bool = True   # 只读取值统一开关（独立于 ledger_import_use_calamine）
```

- 与 ledger import 的 flag 解耦（各自可独立回退）
- 出问题：全局 flag 关 / 单点 prefer_calamine=False

## Error Handling

| 场景 | 处理 |
|------|------|
| calamine 未安装 | read_sheet_values 自动降级 openpyxl（import 失败捕获） |
| sheet 不存在 | 与 openpyxl 一致抛/返回空（按 ledger import 等价语义） |
| 样式依赖点误迁移 | 等价测试拦截；wp_grid_extract 明确不迁移 |
| 数值类型差异（int/float） | 归一化层 + 消费方已容忍（等价测试覆盖） |
| 合并单元格展平差异 | 仅影响取值点的"跨合并区取值"——等价测试逐点验证，不等价则回退该点 |

## 性能验证

- 微基准：对真实底稿模板（D1.xlsx 等）跑 read_sheet_values calamine vs openpyxl，记录耗时（预期 3-5× 提速，与 ledger import 基线一致）
- 序时账非本 spec 范围（已在 ledger import 覆盖）

## 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| calamine 加载 | `excel_parser_calamine._load_sheet` 逻辑 | `xlsx_read_adapter` 统一只读入口 |
| 等价方法论 | `test_excel_parser_calamine.py` 模式 | 各迁移点等价测试 |
| 降级 | feature flag + project override 模式 | XLSX_READ_USE_CALAMINE + prefer_calamine 局部开关 |
| 写路径 | openpyxl（不动） | — |
