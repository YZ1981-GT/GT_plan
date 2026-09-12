# Design Document

## Overview

两条主线并行：**横向补齐**（缺入口的明细表接上四表库取数）+ **纵向收敛**（把两套实现合成一套）。设计的核心约束是"不新造第 5 套归集逻辑"，所有取数走同一条管道。

```
报表行映射（report_config / ReportLineAccountSpec）
        │ 解析出科目原始码前缀（禁硬编码）
        ▼
four_table.aux_aggregation.aggregate_aux_by_name
        │ ① get_active_filter（只取 active dataset）
        │ ② pick_aux_type（先锁定单一维度）
        │ ③ account_code LIKE 前缀（非精确等值）
        ▼
AuxEntry[] (aux_name, opening, debit, credit, closing)
        │ 各循环的纯函数行构建器（只写录入列）
        ▼
checklist_responses[item_id].remark（merge 语义）
        │
        ▼
前端 reload → 明细 Tab → 审定表 → 附注（读同一 store）
```

## Architecture

### 现状分层（实扫）

| 层 | 正确范式（F1/G7/K1/D1） | 历史版本（D3/D5/D6/D7） |
|---|---|---|
| 数据集过滤 | `get_active_filter` | 裸 `is_deleted = false` ❌ |
| 维度锁定 | `pick_aux_type` 先定 `aux_type` | 直接 `GROUP BY aux_name` ❌ |
| 科目来源 | 报表映射解析（如 K1 走 BS-009，兜底注明） | 字面量 `'2203%'` 等 ❌ |
| 归集实现 | 共享件 `aux_aggregation` | 各自裸 SQL（D6 抽到 `detail_aggregation.py` 但仍裸 SQL）❌ |
| 账龄 | 无来源则留空 | 全额塞 `within1` ❌ 伪造 |

`aggregate_aux_by_name` 已是共享件且签名足够（`db, project_id, year, account_prefixes`），迁移主要是**替换调用 + 补 year 参数 + 科目码改解析**。

### 缺口分类（Requirement 1.3 的 gap 类型）

- **G-A**：后端端点有 + 前端按钮无（如 K1 只有 AutoSeed）→ 只补前端
- **G-B**：后端端点无 + 具备取数能力 → 端点 + 按钮都补，端点直接用共享件（不会产生历史债）
- **G-C**：两侧都有但实现违铁律（D3/D5/D6/D7）→ 迁移
- **G-D**：评估为不适合（源模板无列 / 数据只在序时账 / 无维度挂账）→ 只登记理由，不动代码

### fail-open 治理（Requirement 5.1）

`aggregate_aux_by_name` 现在 `except Exception: return [], None, 0`（连 `db.rollback()` 也吞）。这正是平台记过的"最贵一类"假绿：接线错误（列名拼错、传错客户端形态）会伪装成"本项目无此数据"。改法：**保留 fail-open 的返回契约**（调用方无需改），但异常必须 `logger.exception` 记 ERROR，并把原因码带回调用方：

```
AuxAggregationResult
  entries: list[AuxEntry]
  aux_type: str | None
  total_units: int
  reason: 'ok' | 'no_prefixes' | 'no_aux_type' | 'no_rows' | 'error'
```

端点按 `reason` 产出不同中文提示（Requirement 4.4 / 5.2）。为不破坏既有 4 个消费者，新增 `aggregate_aux_by_name_ex()` 返回上述结构，旧函数改为其薄壳（保持返回三元组）。

## Components and Interfaces

### 后端

1. `backend/app/services/four_table/aux_aggregation.py`（改）
   - 新增 `aggregate_aux_by_name_ex(...) -> AuxAggregationResult`，异常记 ERROR
   - 旧 `aggregate_aux_by_name` 变薄壳，返回值逐字段不变（既有 4 消费者零改动）
   - 修正 docstring 里过期的「`period_type`/`balance` 必 500」表述
2. `_d3/_d5/_d6/_d7_import_export.py`（改）+ `d_cycle_extraction/detail_aggregation.py`（改）
   - 删裸 SQL，改调共享件；科目前缀由报表映射解析，兜底值保留但注明来源
   - 账龄字段留空（不再塞全额）
3. G-B 类新端点：`POST /api/workpapers/{wp_id}/{x}/import-aux-balance`，结构照 K1（最新、最薄的那份）

### 前端

1. 明细表 toolbar 补「从余额表导入」按钮（与 `+ 添加行` 同排，`:disabled="isReadonly"`，带 loading）
2. 宿主已有「导入导出 ▾」下拉的，作为下拉项接入
3. 有 AutoSeed 的底稿（F1/K1）保留 AutoSeed，手动入口按 merge 语义（Requirement 4.5）
4. 成功后走宿主既有 reload（保证审定表/附注级联刷新，Requirement 4.6）

## Data Models

不新增表。写入落既有 `checklist_responses(wp_id, item_id, remark)` JSON 数组，字段与各循环前端 `serializeRows` 的持久化子集逐字一致（派生列不写）。

来源可追溯（Requirement 5.4）：行上带既有的来源标记字段（各循环命名不一，Task 1 清册中统一登记）；无该字段的循环以"取数行 `companyCode`/`relationType` 留空 + message 计数"作为弱证据，并在清册中标注为待增强项，不在本 spec 强行加字段。

## Correctness Properties

### Property 1

对任意 project/year/科目前缀，`aggregate_aux_by_name_ex` 的 SQL 必须包含 active dataset 谓词；移除该谓词时，存在至少一个真库样本使归集金额变为原值的整数倍（≥2×）。

**Validates: Requirements 2.6**

### Property 2

对任意挂了 ≥2 个 `aux_type` 的科目，归集结果必须只来自单一 `aux_type`；`sum(entries.closing)` 不得等于跨全部 `aux_type` 的合计。

**Validates: Requirements 3.5**

### Property 3

对任意 merge 写入，已存在的业务键（客户名/合同名/单位名）行的所有字段逐字节不变，新增行只追加。

**Validates: Requirements 3.4**

### Property 4

端点返回的行 dict 的键集合必须是前端持久化子集的**子集**（不含任何派生列）。

**Validates: Requirements 3.3**

### Property 5

当四表侧无账龄来源时，账龄字段必须缺键或为空，且 `sum(账龄段) != 期末余额`（不得被伪造成相等）。

**Validates: Requirements 2.5, 5.3**

### Property 6

对任意抛异常的内部调用，`aggregate_aux_by_name_ex` 返回 `reason='error'` 且日志含一条 ERROR；`reason='no_rows'` 时日志无 ERROR。二者不可混淆。

**Validates: Requirements 5.1, 5.2**

### Property 7

缺口清单中每条 G-A/G-B 条目，在交付后都必须能 grep 到「按钮 → handler → 端点」三段的真实连接（按钮有唯一消费方、handler 真发请求、端点已注册路由）。

**Validates: Requirements 1.3, 6.3**

## Testing Strategy

1. **共享件单测 + PBT**：`pick_aux_type` 已有守卫（`backend/tests/four_table/test_aux_aggregation.py`）；新增 `aggregate_aux_by_name_ex` 的 reason 分支与 ERROR 日志断言（Property 6）
2. **迁移前后金额对照**：对 D3/D5/D6/D7 在真库跑迁移前/后归集，落对照表；若下降为整数倍，写明是 ①或② 的双算修正（Requirement 6.5）
3. **变异检验**：`backend/scripts/diagnose/mutate_four_table_entry_guards.py`，锚点 ≥3（去 active filter · 去 `aux_type` 锁定 · merge→overwrite），四态判定
4. **前端 vitest**：按钮存在 + `isReadonly` 禁用 + 点击真调端点 URL（断言 URL 字面量，防接错循环）
5. **真栈实测**：Playwright 选一张 G-A/G-B 底稿，0 行 → 点按钮 → 行数 = 只读 SQL 查出的户数，抽 2 行金额逐字对齐
6. **反向自检**：所有守卫先写"故意接错"版本确认必红，再改回

## Open Decisions

- **DEC-1**：按钮摆法。倾向**沿用既有「从余额表导入」平铺按钮**（8 个宿主已如此，一致性优先），仅在宿主已有「导入导出 ▾」下拉时并入下拉。备选（全平台统一收进下拉）会改动 8 个既有宿主，超出本 spec 范围。
- **DEC-2**：D2 的 `importFromAuxBalance(projectId)` 签名与其余不同且 `wp_bound_entry_coverage.json` 中**无** `d2/import-aux-balance` 路由 ⇒ Task 1 必须核实它实际打哪个端点，据此归入 G-C 或 G-B。
- **DEC-3**：科目码解析源。K1 走报表行（BS-009）+ 兜底常量是当前最好范式；若某循环无干净的报表行映射，允许保留显式常量但必须注明 `source_ref`（哪张表/哪行），不得裸字面量。
- **DEC-4**：是否给取数行加统一 `source` 标记字段。倾向**本 spec 不加**（会动 5+ 循环的 store 形态与契约 digest），只在清册中登记为待增强；若 Task 1 发现多数循环已有等效字段则升级为本 spec 范围。
- **DEC-5**：G-B 类新端点的数量上限。若 Task 1 清册产出 > 6 个 G-B，建议按循环拆批次交付（每批 ≤3），避免一次动太多宿主导致 manifest/契约面失控。
