# Design Document

## Overview

M 循环 10 个底稿（M1~M10）覆盖所有者权益类科目，当前后端 render 全部硬编码科目码（3 个取错科目族/4 个 report_config 公式本身科目码错误），前端 19 个披露 Tab 中 13 个无同步链路、49 处金额控件千分符失效、附注模板至少 8 个章节列结构与源 xlsx 不一致。本设计将 M 循环全面接入已验证的四表库共享件 + 披露同步链路 + 附注模板对齐三层架构。

## Architecture

```
四表入库 → report_config(row_code) → account_mapping 反解
         ↓
M render 策略（复用 four_table/ 共享件）
         ↓ tb_source_codes / tb_values / adjudication_prefill
前端审定表 Tab（溯源面板 + 「从四表库带入未审数」按钮）
         ↓
前端披露 Tab（自动同步 → sync_from_workpaper → 附注 disclosure_notes）
```

按复杂度分三批（Wave）：

| Wave | 循环 | 结构复杂度 | 产物 |
|---|---|---|---|
| 1 | M3/M6/M8 | 低（标准变动表 / 固定行） | 独立 map + 幂等脚本 + 披露接线 |
| 2 | M1/M2/M10 | 中（浅合并 / 两级表头 / 动态插行） | map + 重建 UI + 前端消费点 |
| 3 | M9 | 高（多级 OCI 43 行 + 列转置调节表） | 重建 Tab + 引擎 |

M4/M5/M7 已完成（只做回归验证 + 前端 `el-input-number` 替换 + 溯源面板接入）。

## Components and Interfaces

### 后端

| 文件 | 职责 |
|---|---|
| `_m{N}_{name}.py` | render 策略，改走 `resolve_report_line_accounts` + `select_leaves` + `aggregate_leaves` |
| `four_table/report_line_accounts.py` | 现有共享件（零改动，M 是第 N+1 个消费者） |
| `four_table/leaf_aggregation.py` | 现有共享件（零改动） |
| `fix_note_m_equity_structure.py` | 幂等脚本（补 columns/guidance/行集/表名/新建章节） |
| `test_note_m_equity_structure.py` | 后端守卫（openpyxl 交叉比对源 xlsx） |
| `test_m_account_scope.py` | 科目映射契约测试 |

### 前端

| 文件 | 职责 |
|---|---|
| `composables/m{N}AccountScope.ts` | 科目单一真源（运行态取 `tb_source_codes`，常量只兜底） |
| `composables/m{N}NoteSectionMap.ts` | 披露→附注映射（章节号+子表名+列定义+载荷构建器） |
| `shared/WpFourTableSourcePanel.vue` | 溯源面板（现有共用件） |
| `m{N}/core/M{N}TabDisclosure{Listed,Soe}.vue` | 披露 Tab（接 `useDisclosureAutoSync` + `syncToDisclosureNotes`） |
| `__tests__/m{N}NoteSubtableContract.spec.ts` | 前端契约守卫 |

### 关键接口契约

1. `ReportLineAccountSpec` 声明（per-cycle）：
   - M 循环多数是**纯权益类（无备抵）** → `fallback_provision=()` / `provision_row_code=None`
   - M1 用 `row_code='BS-055'`（listed）/ 按准则分派
   - M9 用 `row_code='BS-081'`（listed）/ `'BS-115'`（soe），兜底 `('4003',)`

2. render 输出追加字段（不改现有字段，向后兼容）：
   ```python
   {
     "tb_source_codes": {...},        # 新增
     "tb_values": {"begin":..., "end":...},  # 新增
     "adjudication_prefill": [...],   # 新增（可选，叶子分类预填）
     # 现有字段保持不变
   }
   ```

3. 披露同步载荷统一走 `sync_from_workpaper`：
   - M1：`section_id` = K3 章节号（浅合并）
   - M2/M10：两级列定义用 `ColumnDef.group`
   - M6/M8：flat 列定义

## Data Models

### M8 国企新建章节（`八、新增`）

国企附注模板 `八、` 编号 1~93 连续无缺号。一般风险准备应位于盈余公积(62)与未分配利润(63)之间。做法：
- **不做编号重排**（93个章节全部重编号影响面过大）
- 使用 `sort_index` 插位：`八、62` sort_index=61，`八、63` sort_index=62 → 新增章节 `section_number='八、62-1'` 不可行
- ✅ **最终方案**：在**末尾追加** `八、94`（`sort_index=93`），`section_title='一般风险准备'`。编号连续性要求让位于零影响面。上市侧 `五、60` 已存在只需补表结构。

### M1 → K3 浅合并映射

```
M1 底稿（wp_code='M1'）
  ├── 上市 Tab 推 §五、42 的 2 张子表
  │     └── key = K3_LISTED_SUBTABLE.dividend + .dividendOverdue
  └── 国企 Tab 推 §八、42 的 1 张子表（国企无 dividendOverdue 表）
        └── key = K3_SOE_SUBTABLE.dividend
```

### 各循环 report_config 分派规则（列表）

| 循环 | listed row_code | soe row_code | 兜底标准码 | 方向 |
|---|---|---|---|---|
| M1 | BS-055 | BS-076(soe) | `('2232',)` | credit（负债类） |
| M2 | BS-075 | BS-102 | `('4001',)` | credit |
| M3 | BS-080 | BS-114 | `('4201',)` | **debit（权益备抵类）** |
| M4 | BS-079 | BS-113 | `('4002',)` | credit |
| M5 | BS-083 | BS-118 | `('4101',)` | credit |
| M6 | BS-084 | BS-125 | `('4104',)` | credit |
| M7 | BS-082 | BS-117 | `('4103',)` | credit |
| M8 | — | BS-124 | `('4302',)` | credit（仅金融企业） |
| M9 | BS-081 | BS-115 | `('4003',)` | credit |
| M10 | BS-076(listed) | BS-110 | `('4401',)` | credit |

⚠️ `BS-076` 跨准则语义不同（listed=其他权益工具，soe=其中应付股利）→ 必须 `applicable_standards` 分派。

## Error Handling

- 所有 DB 查询 fail-open（`except Exception` 记 warning + 返回兜底值），render 不因取数失败阻断。
- `report_config` 无公式 → 回退 `fallback_gross` 兜底码 → `resolved_from='fallback'`。
- 项目无某科目（如 `37814426` 无 `4301` 专项储备） → `tb_values` 全 0，前端审定表不展示预填按钮。
- 披露同步：`applicable_standards` 门控生效 → 国企项目编辑上市 Tab 不写数据（409 拦截）。

## Testing Strategy

- 后端：`test_m_account_scope.py`（10 循环科目映射 + fail-open + `report_config` 实证）+ `test_note_m_equity_structure.py`（openpyxl 交叉比对）+ 各循环 render 单测（构造 tb_balance fake 行验证叶子聚合）。
- 前端：`m{N}NoteSubtableContract.spec.ts`（P1~P6 共享 helper）+ `m{N}AccountScope.spec.ts`（源码禁硬编码）+ 各 Tab `el-input-number` 归零断言。
- CI：`note-m-equity-structure` job（`--check` exit 0）+ `m-cycle-four-table` job（后端 + 前端）。
- 实测：真实 DB 直跑 render 两项目 + 浏览器端到端。

## Correctness Properties

### Property 1: 叶子聚合自检
**Validates: Requirements 1.2**
对任一有 `tb_balance` 数据的项目，`select_leaves` 聚合结果之和 == 父科目行金额（容差 0.01）。

### Property 2: 报表映射 fail-open
**Validates: Requirements 1.1**
`report_config` 无公式时（M1/M3/M8/M10），回退 `fallback_gross` 兜底码，`resolved_from='fallback'`。

### Property 3: 前端科目单一真源
**Validates: Requirements 5**
运行态科目码取 render 下发 `tb_source_codes.gross_standard[0]`，常量 `FALLBACK_STANDARD` 只在 render 未返回时生效。源码不得出现硬编码科目码作为取数/请求参数/事件载荷。

### Property 4: 披露同步幂等
**Validates: Requirements 2.2**
M1 推送的子表键与 K3 `buildK3SyncPayload` 推送的键**无交集**（M1 推 `dividend`/`dividendOverdue`，K3 推 `summary`/`interest`/`interestOverdue`/`byNature`/`agingOver1y`）。

### Property 5: 附注模板结构一致
**Validates: Requirements 3.1**
幂等脚本 `--check` exit 0；所有 M 类章节 columns 非空 + `_aligned_by` 非空 + 子表名 ↔ 源 xlsx 逐字一致。

### Property 6: 千分符生效
**Validates: Requirements 4**
19 个披露 Tab 内 `el-input-number` 金额列计数 == 0；`WpAmountInput` 覆盖所有金额输入点。

### Property 7: M8 国企章节正确落位
**Validates: Requirements 2.6**
`note_template_soe.json` 新增 `八、94` 章节（`section_title='一般风险准备'`），与 `note_template_variant_matrix.json` 的 `yi_ban_feng_xian_zhun_bei` 条目对应。

### Property 8: 动态取数自适应
**Validates: Requirements 1.1, 1.2**
项目 `37814426`（旧准则 3xxx 科目表 + 4301=研发支出 / 4401=工程施工）在 M7 / M10 render 返回空 `tb_values`（宁缺勿造），不取到错误科目的数据。

