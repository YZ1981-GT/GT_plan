# 设计：统一合并附注模板与单体附注模板的表头格式

## §1 方案概述

**不改存量数据，只改模板和消费端**：

1. 模板生成脚本 `seed_consol_note_sections.py` 增加 `_column_groups` 字段的自动推导
2. 合并附注端点 `consol_note_sections.py` 返回数据带 `_column_groups`
3. 前端 `ConsolNoteTab.vue` 优先按 `_column_groups` 渲染（P0 的 `multi_header` 解析保留降级）
4. 后端 `consol_note_formula_service.py` 按 `_column_groups` 定位列
5. `refresh_note_by_formula` 按列 key 取数

## §2 `multi_header` → `_column_groups` 自动推导

算法（与 P0 的 `parsedMultiHeader` computed 同源，Python 版）：

```python
def multi_header_to_column_groups(multi_header, headers):
    """从 multi_header 推导 _column_groups。
    
    multi_header 第一行的非空连续区间 = 一个分组。
    headers[0]（标签列）跳过。
    """
    if not multi_header or len(multi_header) < 2:
        return None
    row0 = multi_header[0]
    groups = []
    i = 1  # 跳过标签列
    while i < len(row0):
        text = (row0[i] or "").strip()
        if text:
            # 找这个分组的 span
            span = 1
            while i + span < len(row0) and not (row0[i + span] or "").strip():
                span += 1
            if span > 1:
                groups.append({"group": text, "start": i, "span": span})
            i += span
        else:
            i += 1
    return groups if groups else None
```

输出写入模板 JSON 的每张表中（与 `headers`/`rows`/`multi_header` 同级）。

## §3 列定位改进

`consol_note_formula_service.value_column()` 当前逻辑：
```python
# 现有：遍历 headers，找"期末"/"本期"关键词
keys = [header_key(h) for h in headers]
if any(not k for k in keys[1:]):
    return None, "表头有空列名（多级表头未展开），列不确定"  # ← 这就是 multi_header 导致的
```

改进后：
```python
def value_column(table, report_type):
    """优先按 _column_groups 定位，降级到 headers 匹配。"""
    groups = table.get("_column_groups")
    if groups:
        # 按 group 名找：资产负债表项目找"期末"组的第一个子列，利润表找"本期"组
        ...
    # 降级：原 headers 匹配逻辑
    ...
```

## §4 ConsolNoteTab 渲染统一

优先级链：
1. `_column_groups` 存在 → 用分组表头渲染（与 DisclosureEditor 同）
2. `multi_header` 存在 → 用 P0 的 `parsedMultiHeader` 解析渲染
3. 都没有 → 扁平 `headers` 渲染

前端不需要处理行格式统一——合并附注的行格式（二维数组）在编辑模式下用 `row[colIndex]` 索引，字典行用 `row.end_amount` 索引。两种行格式的渲染已分别实现（`ConsolNoteTab` 用数组索引，`DisclosureEditor` 用字段名）。

## §5 向后兼容

- **已保存的合并附注数据**（`consol_note_data` 表）是二维数组 `rows`，不迁移
- 模板层加 `_column_groups` 不影响已保存数据——`_column_groups` 只用于表头渲染和公式种子定位
- `refresh_note_by_formula` 对新保存的数据可以用字典格式，但旧数据必须兼容二维数组格式

## §6 风险

- **seed 脚本的 Word 提取逻辑**：`seed_consol_note_sections.py` 的 multi_header 提取可能有边界情况（如三行表头的中间行为空），推导 `_column_groups` 时需要处理
- **3 张 multi_header 表的公式种子**：解锁后可能暴露其他问题（如行标签不匹配报表行名）


## §7 已知限制（2026-10-05 复盘追加）

### L1：`_column_groups` 只描述顶层分组

三行表头如五-5-2 有三层（期末数 → 账面余额 → 金额）。当前 `_column_groups` 只描述第一层（`{group: "期末数", start: 1, span: 5}`），第二层（账面余额/坏账准备/账面价值）未建模。

对公式种子和列定位够用（`value_column` 只需找到"期末数"组的 start 列），但未来若需精确定位"期末数/坏账准备"列（二级子列），需扩展为嵌套结构 `{group, start, span, children: [...]}`。当前无此需求，记录留后续。

### L2：导入导出路径未感知分组表头

`batchExportAllData` / `batchExportAllTemplates` 导出 Excel 时只写一行表头（扁平 `headers`，斜杠拼接），对 multi_header 表导出的 Excel 没有分组表头效果。导入时按第一行匹配无功能问题（扁平 headers 唯一映射），但体验不如分组表头直观。

改进方向：导出时对有 `_column_groups` 的表写多行表头（第一行分组名 + 合并单元格，第二行子列名），导入时兼容两种格式。不在本 spec 范围。

### L3：`--check` 依赖 md 源文件

seed 脚本的 `--check` 模式依赖从 md 源重新解析后比较。md 源不在仓库中（gitignore），CI 环境跑不了。已改为不依赖 md 的幂等校验（§7.1 补充），见 seed 脚本。
