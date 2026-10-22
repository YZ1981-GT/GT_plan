# 合并附注从单体附注拉取数据 — 技术方案（v2，基于真库实测修正）

## §0 真库实测修正记录

> 2026-10-22 基于 5 个真实项目的四次探针，修正了原始设计中的多项假设。

### 修正 1：数据格式分布

原假设：单体附注主要用 sub_table_data（F2/F3 格式）。

真实情况（1047 条有数据的 disclosure_notes）：
- **_tables 是真源**：1030 条（98.4%）有 `_tables`
- **sub_table_data 是补充层**：141 条（13.5%）有 `sub_table_data`，**且它们 100% 同时有 `_tables`**
- 仅 _tables 无 sub：889 条（84.9%）
- 行结构：`{label, values:[], is_total, row_type, _cell_meta}` — values 是位置数组

结论：**读取必须以 _tables 为主路径**，sub_table_data 仅作补充。

### 修正 2：推送覆盖率

原假设：21 个八章科目需要补公式推送规则。

真实情况：
- 17 个是手工填写章节（无科目码、列结构特殊），不需要自动推送
- 4 个可补但 ROI 低（变动表结构复杂：现金流量表注释、外币等）
- **现有 70 个规则已经足够**，问题是部分项目没有底稿（华氏 wp=0、医疗器械 wp=0），导致推送从未触发

### 修正 3：章节映射精确度

真实匹配率：SOE 110 个合并章节组中 **96 个可按 parent_section ↔ section_title 自动匹配**，14 个未匹配主要是名称截断（"关联方应收应付款" vs "关联方应收应付款项"）。

## §1 架构总览

### 1.1 新数据流

```
┌─────────────────────────────────────────────────────────┐
│  合并项目 ConsolidationIndex / ConsolNoteTab            │
│                                                         │
│  "🔄 重新汇总"  ──POST─→  reaggregate 端点              │
│  "ƒx 按公式填入" ──POST─→  fill-by-formula 端点（不变） │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   路径 A：单体附注拉取            路径 B：公式引擎（现有，不动）
   consol_note_aggregator          consol_note_formula_service
          │                             │
          │  遍历企业树数据叶子           │  TB()/REPORT()/SUM_TB()
          │  按章节映射查 disclosure_notes │  走 CalcBasis → node_measures
          │  读 _tables 格式（主）        │
          │  或 sub_table_data（补）      │
          │  按行标签+列标签匹配          │
          │  汇总个别数                   │
          └──────────┬──────────────────┘
                     ▼
           reaggregate 全走路径 A
           fill-by-formula 全走路径 B
           两个按钮、两条路径、互不干扰
                     ▼
           fill_rows() → consol_note_data 持久化
```

### 1.2 核心原则

- **不侵入现有公式引擎**：路径 B 保持不动，路径 A 是新增的平行路径
- **两个按钮两条路径**：reaggregate 走 A，fill-by-formula 走 B
- **_tables 是主读取路径**：84.9% 的章节只有 _tables，读取逻辑必须以此为主
- **复用 note_writer 的 locate_table() 定位策略**：优先 sub_table_data → 降级 _tables → 降级 rows

## §2 章节映射

方案不变，参照原 design §2。

自动匹配 96/110（87%），手工补 14 个截断名。生成脚本 + JSON 配置文件。

## §3 核心服务：consol_note_aggregator.py

### 3.1 单体附注读取（修正）

基于真库格式分布，读取逻辑按优先级：

```python
async def _read_standalone_note_table(
    table_data: dict,
    table_name: str | None,
    consol_headers: list[str],
) -> StandardizedTable | None:
    """从单体附注 table_data 读取一张表的标准化数据。

    读取优先级（与 note_writer.locate_table 一致）：
    1. sub_table_data[table_name] — 有明确业务键（end_amount 等）
    2. _tables 中按 table_name 匹配的表 — 用 values[] 位置数组 + headers 列名
    3. _tables[0] — 首表兜底（单表章节）
    """
```

### 3.2 _tables 行读取（新增，原设计未覆盖）

_tables 的行是 `{label, values:[], is_total, row_type}`，values 是位置数组，需要配合 headers 解读：

```python
def _read_tables_row(
    row: dict,
    headers: list[str],
    target_col_map: dict[int, str],  # 合并模板列号 → 列名
) -> dict[str, float | None]:
    """读 _tables 行的数值。

    headers = ["项目", "期末余额", "期初余额"]
    values  = [100.5, 200.3]  # 位置对应 headers[1:] 

    返回 {"期末余额": 100.5, "期初余额": 200.3}
    """
    values = row.get("values", [])
    result = {}
    for i, header in enumerate(headers[1:]):  # 跳过首列（标签列）
        norm = _norm_header(header)
        val = values[i] if i < len(values) else None
        if val is not None:
            try:
                result[norm] = float(val) if val != "" else None
            except (ValueError, TypeError):
                result[norm] = None
        else:
            result[norm] = None
    return result
```

### 3.3 列匹配（修正）

合并模板的列名（如 "期末余额"）需要在单体附注的 headers 中找到对应列。

```python
# 列名词表（复用 note_writer.py 的词表）
_END_SYNONYMS = {"期末余额", "期末数", "期末", "期末金额", "期末账面价值", ...}
_PRIOR_SYNONYMS = {"期初余额", "期初数", "期初", "期初金额", "年初余额", ...}

def _match_column(consol_col: str, standalone_headers: list[str]) -> int | None:
    """合并模板列名 → 单体附注列号（headers 中的下标）。

    1. 精确匹配
    2. 归一化后匹配
    3. 同义词组匹配（期末余额 ≈ 期末数）
    """
```

### 3.4 汇总逻辑

```python
async def aggregate_section(
    db, tree, project_id, year, consol_section_id, template_type,
) -> AggregateResult:
    # 1. 查章节映射
    standalone_section = resolve_standalone_section(template_type, consol_section_id)
    
    # 2. 批量查所有数据叶子的 disclosure_notes（一次 IN 查询）
    leaf_project_ids = [leaf.project_id for leaf in data_leaves(tree) if leaf.project_id]
    notes = await _batch_load_notes(db, leaf_project_ids, year, standalone_section)
    
    # 3. 加载合并模板结构
    consol_table = find_table(template_type, consol_section_id)
    consol_headers = consol_table.get("headers", [])
    consol_rows = consol_table.get("rows", [])
    
    # 4. 逐叶子读取 + 列匹配 + 行匹配 + 累加
    cell_values: dict[tuple[int,int], CellValue] = {}
    for leaf in data_leaves(tree):
        note = notes.get(leaf.project_id)
        if note is None:
            # 记入 unmatched_leaves
            continue
        table = _read_standalone_note_table(note.table_data, ...)
        if table is None:
            continue
        for ri, consol_row in enumerate(consol_rows):
            label = consol_row[0] if isinstance(consol_row, list) else consol_row.get("label", "")
            # 在单体表中找匹配行
            source_row = table.find_row(label)
            if source_row is None:
                continue
            for ci in range(1, len(consol_headers)):
                # 列匹配
                value = source_row.get_value(consol_headers[ci])
                if value is not None:
                    cell = cell_values.setdefault((ri, ci), CellValue(ri, ci))
                    cell.individual = (cell.individual or 0) + value
                    cell.by_company.append({...})
    
    # 5. 合并数 = 个别数（差额节点暂不参与 Phase 1）
    for cell in cell_values.values():
        cell.consolidated = cell.individual
    
    return AggregateResult(cells=list(cell_values.values()), ...)
```

## §4 reaggregate 端点改造

不变，参照原 design §4。reaggregate 走路径 A，fill-by-formula 不动。

## §5 前端改造

不变，参照原 design §5。汇总结果弹窗增加子企业读取状态。

## §6 章节映射配置文件生成

不变，参照原 design §6。

## §7 分阶段实施（修正）

### Phase 1（本 spec 范围）

1. 章节映射配置文件生成 + 运行时加载
2. `consol_note_aggregator.py` 核心服务
   - **主路径读 _tables 格式**（values 位置数组 + headers 列名匹配）
   - 补充路径读 sub_table_data（业务键 end_amount 等）
   - 行匹配复用 find_row() 三级策略
   - 列匹配用 _END_HEADERS/_PRIOR_HEADERS 词表
3. reaggregate 端点改造
4. 前端汇总结果弹窗增强
5. 测试：覆盖货币资金（简单两列）+ 存货（多表 + values 数组）

### Phase 2（后续）

1. 差额节点的调整/抵销按行级分配到附注单元格
2. stale 联动（子企业附注修改 → 合并附注标 stale）
3. 4 个可补的八章科目公式推送规则（八、81/91/92/93）
4. 合并单元格表头（multi_header）的表格完善

## §8 涉及文件清单（修正）

### 新建

| 文件 | 说明 |
|------|------|
| `backend/app/services/consol_note_aggregator.py` | 核心服务：从单体附注 _tables 读取 + 行列匹配 + 汇总 |
| `backend/app/services/consol_note_section_mapping.py` | 章节映射加载与查询 |
| `backend/data/consol_note_section_mapping_generated.json` | 映射配置文件 |
| `backend/scripts/seed/gen_consol_standalone_note_mapping.py` | 映射生成脚本 |
| `backend/tests/test_consol_note_aggregator.py` | 核心服务测试 |

### 修改

| 文件 | 说明 |
|------|------|
| `backend/app/routers/consol_notes.py` | reaggregate 端点实现替换 |
| `audit-platform/frontend/src/components/consolidation/ConsolNoteTab.vue` | 汇总结果弹窗增强 |

### 不修改

| 文件 | 说明 |
|------|------|
| `backend/app/services/consol_note_formula_service.py` | 路径 B 保持不动 |
| `backend/app/services/formula_push/` | 公式推送引擎保持不动 |
| `backend/data/formula_push_rules.json` | 推送规则不变（70 个够用） |

## §9 真库验证基准

基于探针数据，Phase 1 可用的验证基准：

| 项目 | TB 非零行 | 底稿数 | 推送运行 | 附注已推送 | 可用于合并测试 |
|------|---------|--------|---------|----------|------------|
| 安徽 | 48 | 1060 | 28 | 45 | ✅ 首选 |
| 和平 | 52 | 324 | 27 | 48 | ✅ |
| 宜宾 | 24 | 1026 | 1 | 26 | ✅ |
| 华氏 | 45 | 0 | 0 | 0 | ❌ 无底稿 |
| 医疗器械 | 54 | 0 | 0 | 0 | ❌ 无底稿 |

端到端验证使用安徽+和平+宜宾三个有真实推送数据的项目。
