# Task 5 — G-B 类新端点：文档化 NO-OP 交付

**Task:** 5. G-B 类新端点（照 K1 范式）
**Requirements:** 3.1, 3.2, 3.3, 3.4
**结论:** **NO-OP（宁缺勿造）** —— 冻结清册 `gap-inventory.json` 中 G-B = `[]`（`g_b_count == 0`），本任务不新增任何端点，也不修改任何生产代码。

---

## 1. 新鲜度门禁（Requirement 1.6）

冻结基线 `aggregate_digest = sha256:da5aeae67f2edbb333d6449061f18c09e13de59d813bcda8c52f3a176c0b3651`。
本任务开始前重算 `source_snapshot.files` 的 5 个 sha256 摘要，逐字节比对：

| 文件 | 角色 | 冻结 sha256 (前 8) | 实测 sha256 (前 8) | 结果 |
|------|------|------|------|------|
| `.../registry/entries/forms.ts` | 枚举驱动（宿主全集） | `961be1df` | `961be1df` | **MATCH** |
| `.../registry/entries/specialized.ts` | 枚举驱动（宿主全集） | `b27cd926` | `b27cd926` | **MATCH** |
| `backend/app/data/wp_code_overrides.json` | 枚举驱动（wp_code→componentType） | `ecb63b62` | `ecb63b62` | **MATCH** |
| `backend/app/security/wp_bound_entry_coverage.json` | 枚举驱动（后端端点清册） | `1392d1a5` | `1392d1a5` | **MATCH** |
| `backend/app/services/four_table/aux_aggregation.py` | 共享件（**非枚举驱动**） | `e0300984` | `d1326ce9` | **DRIFT（预期允许）** |

**门禁判定：PASS。**

- 4 个**枚举驱动**文件（宿主全集 + wp_code 映射 + 后端端点清册）全部逐字节 MATCH。这 4 个文件正是决定「哪些宿主已挂载」「哪些后端端点已存在」「哪些 wp_code 具备四表能力」的唯一输入。它们未漂移 ⇒ 清册对 G-A/G-B/G-C 的分类结构性依然成立，G-B=0 的推导前提未被推翻。
- `aux_aggregation.py` 发生 DRIFT（7809 → 12505 bytes），系 **Task 3** 已完成的共享件增强（`aggregate_aux_by_name_ex(...) -> AuxAggregationResult` + reason 码 + `logger.exception` ERROR 日志）。该文件是**消费侧共享件**，不参与任何 G-B 宿主的枚举，其变更**不会**新增或删除任何 G-B 条目。按 Task 5 指令，此漂移为「预期/允许」，不构成阻塞。
- 因此 `aggregate_digest` 整体值虽因单文件漂移而不同（`1eb60d3f…` ≠ `da5aeae6…`），但**门禁语义**（枚举底座是否漂移）判定为 PASS。

> 重算脚本为一次性只读运行（无落盘、无临时文件残留），命令：
> `python -c "<hashlib.sha256 over the 5 files>"`（cwd = `d:\GT_plan`）。

## 2. 冻结清册确认 G-B = 0（Requirement 1.5）

`gap-inventory.json` 是 Task 4/5/7 的唯一真源。其 `gap_summary` 明确：

```json
"gap_summary": {
  "G-A": ["K1"],
  "G-B": [],
  "G-C": ["D2", "D3", "D5", "D6", "D7"],
  "G-D": [],
  "compliant_baseline": ["D1", "F1", "G7"],
  "g_b_count": 0,
  "dec5_batch_note": "G-B count is 0, so DEC-5 batch-splitting (>6 G-B) does not apply."
}
```

`G-B == []` 且 `g_b_count == 0`。G-B 的定义是「后端端点**缺失** + 具备四表能力 → 需同时新建端点与按钮」。清册枚举结果中**无任何 wp_code**落入此类。

## 3. D2 的分类归属（DEC-2 → G-C，非 G-B）

设计阶段 DEC-2 曾怀疑 D2 可能属 G-B（其明细表有从余额表导入按钮，但覆盖 JSON 里查无 `d2/import-aux-balance` 端点）。Task 1 核实后**归类为 G-C**，理由（`inventory[].dec2_resolution`）：

- `useD2Detail.importFromAuxBalance(projectId)` 并**不打**任何 `d2/import-aux-balance` 端点；它调用**通用只读**端点 `GET /api/projects/{project_id}/ledger/aux-balance-detail?account_code=1122&dim_type=客户`，然后在 **TypeScript 前端**按 `aux_name` 做客户端归集（第 5 套归集副本）。
- 该只读端点本身**铁律合规**（`get_active_filter` + `aux_type==dim_type` + `account_code LIKE` 前缀）。违规点在 D2 **前端**：硬编码 `1122` 未走报表映射（`D2_SPEC/BS-006` 已存在于 `d_account_resolver.py`），且绕过共享 `aggregate_aux_by_name` 管道。
- 故 D2 = **G-C**：在 **Task 4** 下迁移——新建一个基于共享件的 `POST /api/workpapers/{wp_id}/d2/import-aux-balance`、前缀由 `D2_SPEC(BS-006)` 解析、删除客户端归集。清册 `downstream_contract.note_task4_vs_task5` 明确 D2 由 **Task 4** 处理（G-C-with-endpoint-creation），**不**在 Task 5 作为新 G-B 端点创建。

**结论：D2 已被明确从 G-B 排除，改由 Task 4 处理。Task 5 无 D2 归属。**

## 4. DEC-5 批次拆分不适用

DEC-5 规定「G-B > 6 个时按每批 ≤3 拆成独立 release gate」。当前 `g_b_count == 0`，远小于阈值 6，**DEC-5 不触发**（与清册 `dec5_batch_note` 一致）。

## 5. 交付说明（宁缺勿造）

- 本任务**不新增**任何 `POST /api/workpapers/{wp_id}/{x}/import-aux-balance` 端点。
- 本任务**不修改**任何生产代码（后端/前端）。
- 若强行为凑数编造 G-B 端点，将违反 Requirement 1.4（宁缺勿造）与清册唯一真源约束（Requirement 1.5）。因此 Task 5 的正确交付是**记录性 NO-OP**，本证据文件即交付物。

## 6. Requirements 覆盖对照

| Requirement | 本任务如何满足 |
|-------------|----------------|
| 3.1 复用共享件、禁第 5 套归集 | 无新端点 ⇒ 无新归集 SQL，天然满足（无违反） |
| 3.2 归集不足须扩展共享件 | 无新场景需覆盖（G-B=0） |
| 3.3 端点只写录入列（Property 4） | 无新端点，无行写入 |
| 3.4 merge 语义 + 显式 overwrite（Property 3） | 无新端点，无 store 写入 |

四条验收标准均以「无 G-B 端点 ⇒ 无可违反面」的方式被动满足；实质性 merge/录入列/共享件复用约束由 Task 4（G-C 迁移，含 D2 新建）与既有 8 个合规端点承载。
