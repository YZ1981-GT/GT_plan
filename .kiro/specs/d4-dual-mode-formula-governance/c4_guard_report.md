# C4 行为守卫报告

## 覆盖的 Requirement

| Guard | Requirement | 说明 |
|-------|-------------|------|
| Guard 1 | Req 1.1 | C0 矩阵恰好 36 个 wp_code，无重复，D4-1..D4-36 连续 |
| Guard 2 | Req 2.2 | 同字段异值必产生冲突（禁 LWW）；不同字段自动合并 |
| Guard 3 | Req 3.2 | F-SHELL v2 白名单：eval/exec/URL/非法函数名均被拒绝 |
| Guard 4 | Req 4.1 | DAG 循环检测 + topological_sort 对循环图抛 ValueError |
| Guard 5 | Req 5.1 | D4 提取模块不复制科目 SQL，必须通过 four_table 服务 |

## UNVERIFIABLE 项（不在本文件中假绿）

- Playwright E2E 测试（需 start-dev.bat 环境）
- OO/OnlyOffice roundtrip（需外部服务）
- 权限隔离验证（需真实多用户环境）
- CAS save() baseVersion 缺失（C2 已知机制缺口）
- TB 发布显式确认端点（C3 已知机制缺口）

## 受管区行几何守卫（D4 IPO 四表，2026-09-19 复核后补齐）

> 起因：review D4-25/26/27/28 三件套时对「D4-25 最下面行次 / D4-26 首行」的行定位提出质疑。
> 结论：openpyxl 直读源模板 + 真 instrumented workbook 字节级双重实测，**生产 provider
> `phase5_d4_ipo_checklist_sheets._SHEETS` 的行锚点全部正确，无 bug**。误判源自 spec 文档
> 曾沿用已删死函数 `rowsToSheet/sheetToRows` 的 `dataStartRow` 单值口径描述运行时行为。

### 行锚点权威值（真源 = 后端 provider，随 mapping_digest 冻结）

| sheet | header_rows | first_data_row | last_data_row | footer_row（A 列「三、审计说明：」） | uuid_col |
|---|---|---|---|---|---|
| D4-25 经销商检查 | 11 | 12 | 21 | 23 | N |
| D4-26 境外销售收入检查 | 11, 12 | 13 | 22 | 30 | T |
| D4-27 识别未披露的关联方 | 14 | 15 | 24 | 27 | S |
| D4-28 客户信息核查清单 | 12, 13 | 14 | 24 | 25 | P |

### 新增守卫（对应平台契约 `c_platform_contracts.md` §A.1.2 CS-12「拒绝行号作为 footer anchor」的 D4 落地实证）

| Guard | 覆盖点 | 文件 | 变异实证 |
|-------|--------|------|---------|
| footer 源模板守卫 | provider `footer_row` 必须精确指向源模板 `A{footer_row}` == 「三、审计说明：」（含反向自检） | `backend/tests/test_ipo_checklist_column_contract.py::test_provider_footer_row_points_to_marker_in_source_template` | D4-26 若误抄 footer=23（D4-25 行号）→ A23=None ≠ marker → 立即红。历史确曾误抄过一次 |
| 超占位不截断守卫 | 行数超模板占位（`last_data_row-first_data_row+1`）时投影/merge 不截断，坐实 `last_data_row` 非运行时写入截断点（运行时硬上限 = `_ROW_LIMIT`=500） | `backend/tests/workpaper_sync/test_d4_ipo_checklist_store_roundtrip.py::test_rows_beyond_template_placeholder_are_not_truncated` | 给超占位 5 行，投影行数 != 输入即红 |

### 通用治理原则（跨表适用，供其它受管表复用）

1. **受管区行几何的运行时真源在后端 store-projection provider**（`first/last/footer/uuid_col`），
   随 `mapping_digest` 冻结；spec 文档只作展示，**禁止用已删死代码的口径描述运行时行为**。
2. **`last_data_row` 仅模板占位末行基线，不是运行时写入截断点**：动态行超占位时插行下移 footer 结论区，
   运行时唯一硬上限是 `_ROW_LIMIT`。误当截断点会吞掉超占位数据。
3. **footer（结论区）是受管数据区的硬下边界**，必须有源模板守卫钉死其行号（CS-12 的具体落地），
   防「行号误抄 / 差一行 / 指到别表行号」这类静默漂移。

## 运行方式

```bash
# cwd=backend
python -m pytest .kiro/specs/d4-dual-mode-formula-governance/c4_guard_tests.py -v --tb=short
```

所有导入失败 → `pytest.skip()`，保证在完整后端环境下可运行。
