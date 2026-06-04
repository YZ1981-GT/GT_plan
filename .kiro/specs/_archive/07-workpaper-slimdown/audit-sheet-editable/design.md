# Design: 审定表可编辑升级 (GtAuditSheet)

## Overview

参照合并工作底稿 `NetAssetSheet` 架构,将审定表从只读 `GtGridSheet` 升级为结构化可编辑组件 `GtAuditSheet.vue`。核心思路:el-table + el-input-number 直编 + computed 自动算 + TB() 取数 + 保存写回 parsed_data + 导入导出 Excel。

## 现状勘察

### 当前链路
1. `wp_classification_service.py`: `F-` 前缀 → componentType=`univer`（blanket 映射）
2. `wp_render_config.py`: componentType=`univer` + 无持久化 cells → `_generate_grid_data()` 从模板提取只读网格
3. 前端 `GtWpRenderer.vue`: univer 分支 → `_has_grid_cells` 真 → `GtGridSheet`（只读 HTML table）
4. `GtGridSheet.vue`: 纯展示,formula_hint 图标/tooltip,无编辑能力

### 改造切入点
- `wp_classification_service.py` 的 `_CLASS_TO_COMPONENT` 中 `F-` → `univer` 需拆分:
  - `F-审定表` → `audit-sheet`（新）
  - 其余 F-/G- 保持 `univer`
- `htmlRendererRegistry.ts` 注册 `audit-sheet` → `GtAuditSheet`
- `wp_render_config.py` 对 `audit-sheet` 走新的数据准备逻辑（结构化行 + TB 取数）
- 前端 GtAuditSheet 参照 NetAssetSheet 实现

## Architecture

### 数据流

```
模板 xlsx (D1.xlsx 审定表D1-1 sheet)
    │
    ├─ 后端解析 → AuditSheetRow[] (行项目名 + 层级 + account_code 映射)
    │
    ├─ SQL 查 trial_balance 表 → tb_values（每次实时查,不持久化）
    │   - standard_account_code 映射自 wp_account_mapping.json
    │   - unadjusted_amount = 本期未审数
    │   - opening_balance = 期初未审数（上年结转,通常含审计调整）
    │   - aje_adjustment = 系统汇总的 AJE（参考值,用户可覆盖）
    │   - rje_adjustment = 系统汇总的 RJE（参考值,用户可覆盖）
    │
    └─ 返回 render-config response:
         sheet.html_data = {
           audit_rows: AuditSheetRow[],   ← 仅含行结构+用户编辑值(adj/reclass/reason)
           tb_values: { row_key: { opening_unadjusted, current_unadjusted,
                                    sys_aje, sys_rje } },  ← 实时查,不持久化
         }

前端 GtAuditSheet:
    ├─ 加载 audit_rows + tb_values → 合并为 tableData
    ├─ TB 列（只读,实时值）+ 系统调整参考值
    ├─ 用户编辑调整/原因 → v-model（覆盖系统值）
    ├─ computed → 审定数/变动额/变动率 实时算
    └─ 保存 → POST /api/workpapers/{wp_id}/save
              → parsed_data.html_data[sheet].audit_rows = [...]
              （仅持久化: 行结构 + 用户编辑的 adj/reclass/reason + 自定义新增行）
              （不持久化: TB 实时值——下次加载重新从 trial_balance 查）
```

**持久化分层原则**:
- `audit_rows[]` 只存**用户编辑列**（adj_amount / reclass_amount / reason）+ 自定义新增行的完整数据
- TB 列（opening_unadjusted / current_unadjusted / sys_aje / sys_rje）每次加载实时从 `trial_balance` 表查,不持久化——用户重新导入 TB 后自动刷新
- 前端展示时合并: TB 实时值 + 用户编辑持久化值 + computed 计算值

**期初审定数来源决策**（简单方案）:
- 期初审定数 = `trial_balance.opening_balance`（上年末结转余额,通常已含上年审计调整）
- 精确方案（跨项目查上年 `audited_amount`）作为后续增强,当前不做（`prior_year_project_id` 可能为空）

### 数据模型

```typescript
// 前端 AuditSheetRow（持久化部分 + 运行时合并 TB 值后展示）
interface AuditSheetRow {
  id: string              // row-{n}
  item: string            // 项目名（如"应收票据-原值"）
  indent: number          // 缩进层级（0/1/2）
  bold: boolean           // 是否粗体（分节行/合计行）
  isComputed: boolean     // 是否自动汇总行（合计）
  isSection: boolean      // 是否分节标题行（一、二、三）
  account_code: string | null  // 科目编码（映射 trial_balance 取数）

  // ─── 用户编辑列（持久化到 parsed_data）───
  adj_amount: number | null           // 账项调整（可编辑,覆盖系统 AJE）
  reclass_amount: number | null       // 重分类调整（可编辑,覆盖系统 RJE）
  reason: string                      // 原因分析（可编辑）

  // ─── TB 实时值（运行时合并,不持久化）───
  opening_unadjusted?: number | null  // 期初未审数 ← trial_balance.opening_balance
  current_unadjusted?: number | null  // 本期未审数 ← trial_balance.unadjusted_amount
  sys_aje?: number | null             // 系统汇总 AJE（参考值）
  sys_rje?: number | null             // 系统汇总 RJE（参考值）

  // ─── computed（前端实时计算,不持久化）───
  // audited_amount = current_unadjusted + (adj_amount ?? sys_aje ?? 0) + (reclass_amount ?? sys_rje ?? 0)
  // opening_audited = opening_unadjusted（简单方案；精确方案需跨项目查上年审定）
  // change_amount = audited_amount - opening_audited
  // change_rate = change_amount / opening_audited（opening_audited≠0 时）
}
```

```python
# 后端返回结构（render-config 内 sheet.html_data）
{
  "audit_rows": [
    {
      "id": "row-1",
      "item": "一、应收票据",
      "indent": 0, "bold": True, "isSection": True, "isComputed": False,
      "account_code": null,
      # 仅持久化用户编辑值（TB 列不存）:
      "adj_amount": None, "reclass_amount": None, "reason": ""
    },
    {
      "id": "row-2",
      "item": "  原值",
      "indent": 1, "bold": False, "isSection": False, "isComputed": False,
      "account_code": "1121",  # 映射到 trial_balance 查数
      "adj_amount": 5000.00, "reclass_amount": None, "reason": "确认坏账"
    },
    ...
  ],
  # TB 实时值（每次加载从 trial_balance 查,不持久化到 parsed_data）
  "tb_values": {
    "row-2": {
      "opening_unadjusted": 100000.00,   # trial_balance.opening_balance
      "current_unadjusted": 120000.00,   # trial_balance.unadjusted_amount
      "sys_aje": 0.00,                    # trial_balance.aje_adjustment（参考）
      "sys_rje": 0.00                     # trial_balance.rje_adjustment（参考）
    }
  }
}
```

### 后端改动

#### 1. 分类映射拆分 (`wp_classification_service.py`)

仿 D 类 `_D_SUB_ROUTING` 精确匹配模式（非往 `_CLASS_TO_COMPONENT` dict 加键——因为前缀循环 `F-` 会先命中）：

```python
# 新增 F 类 sub-routing（精确匹配优先于前缀 fallback）
_F_SUB_ROUTING: dict[str, str] = {
    "F-审定表": "audit-sheet",
}

# 在 derive_component_type 中，F- 前缀匹配前先查 _F_SUB_ROUTING：
if class_code.startswith("F-"):
    component_type = _F_SUB_ROUTING.get(class_code)
    if component_type:
        return component_type
    # fallback: 其余 F- 仍返回 univer
    return "univer"
```

保留 `_CLASS_TO_COMPONENT["F-"] = "univer"` 不变（仅作 G- 等非 F- 精确匹配到的 fallback）。

#### 2. 行提取服务 (`wp_audit_sheet_extract.py` 新建)

```python
def extract_audit_rows(file_path: str, sheet_name: str) -> list[dict]:
    """从模板 xlsx 提取审定表行项目结构。
    
    解析策略：
    - 定位"项目"列（通常 A 列）
    - 跳过标题区（致同/表名/编制信息）
    - 从第一个含"项目"/"科目"关键词的表头行开始
    - 逐行提取：项目名/缩进/是否粗体/是否合计行/是否分节
    - 降级返回 [] 不抛异常
    """
```

#### 3. render-config 数据准备 (`wp_render_config.py`)

```python
# 在 sheet_configs 组装中:
if component_type == "audit-sheet":
    sheet_html_data = await _generate_audit_sheet_data(
        file_path=working_paper.file_path,
        sheet_name=classification.sheet_name,
        existing=sheet_html_data,
        project_id=project_id,
        db=db,
    )
```

`_generate_audit_sheet_data`:
1. 持久化优先:若 `html_data.audit_rows` 已有,直接返回
2. 否则调 `extract_audit_rows` 从模板生成默认行
3. 调 `formula_engine` TB() 批量取数填充 `tb_values`

#### 4. 保存端点复用

复用现有 `POST /api/workpapers/{wp_id}/save`（`wp_html_save.py`）,前端把 `audit_rows` 作为 `html_data[sheet_name]` 的一部分提交。

### 前端改动

#### 1. 注册 componentType (`htmlRendererRegistry.ts`)

```typescript
{
  componentType: 'audit-sheet',
  component: defineAsyncComponent(() => import('./GtAuditSheet.vue')),
  icon: '📊',
  label: '审定表',
  emits: ['save', 'field-change'],
}
```

#### 2. GtAuditSheet.vue（新建,参照 NetAssetSheet）

核心结构:
- `el-table :data="tableData" border size="small"`
- 固定列:序号/项目(缩进)/期初未审/期初审定/本期未审/账项调整(可编辑)/重分类(可编辑)/审定数(computed)/变动额(computed)/变动率(computed)/原因(可编辑)
- 工具栏:全屏/公式/导出模板/导出数据/导入Excel/+新增行/删除/还原/保存
- 合计行自动汇总(isComputed=true 的行用 computed 求和)
- 保存 emit → 父组件调 POST /save

#### 3. useWpRenderer 类型扩展

`HtmlComponentType` 联合类型追加 `'audit-sheet'`。

### 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| 模板解析 | `wp_grid_extract` 的 data_start_row 探测 | `wp_audit_sheet_extract` 专门提取行结构 |
| TB 取数 | `formula_engine` TB() | 批量取数接口 |
| 保存 | `POST /api/workpapers/{id}/save` | audit_rows 结构化字段 |
| 导入导出 | `useExcelIO` composable（NetAssetSheet 已用） | 审定表列适配 |
| 公式编辑 | FormulaEditDialog | 审定表上下文 |
| 缓存失效 | `touch_after_parsed_data_commit` | 已有 |

## Error Handling

| 场景 | 降级 |
|------|------|
| 模板文件不存在/解析失败 | 返回空行列表,前端空态+手动新增 |
| TB 数据不存在 | 未审数列显示"—",可编辑列正常 |
| 保存失败 | ElMessage.error,数据保留不清空 |
| 导入 Excel 格式异常 | 显示跳过行数,仅匹配项写入 |
| audit_rows 与模板行不一致（用户删/增行后模板更新） | 以 audit_rows 为准,不自动同步 |
