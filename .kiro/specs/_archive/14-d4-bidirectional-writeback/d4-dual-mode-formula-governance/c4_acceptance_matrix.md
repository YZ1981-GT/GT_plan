# C4 逐表验收矩阵 — D4-1..D4-36

> 状态：PARTIAL（Playwright 全部 UNVERIFIABLE；部分机制缺口待实现）
> 依据：Requirement 8.1
> 生成依据：C0-C3 契约文件 + grep 实证（2026-06-01）
> 生成时间：2026-06-01
> 本 spec owner：`d4-dual-mode-formula-governance`

---

## 验收状态图例

| 符号 | 含义 |
|------|------|
| ✅ | 已实证（有代码/文件证据，可确认） |
| ❌ | 已知缺口（必须修复后才能验收；有代码证据确认缺口存在） |
| 🟡 | P1 待改进（部分实现，需补充） |
| 🔴 | P0 阻塞项 |
| ⬜ | N/A（不适用） |
| UNVERIFIABLE | 无实测证据，不假绿（Requirement 8.1） |

---

## 验收维度说明

| 维度 | 含义 | 数据来源 |
|------|------|---------|
| 源模板 | 模板文件+sheet 在 `backend/wp_templates/` 实证存在 | C0 owner_matrix |
| contract/identity | C1+C2+C3+C_platform 契约对本 wp_code 的接入状态 | C1/C2/C3/C_platform |
| HTML→Excel→HTML | 该 wp_code 的 roundtrip 实测证据 | 运行时 E2E 环境 |
| 公式/冲突 | C2 六态公式机制 + C1 冲突处理对该 wp_code 的接入 | C1/C2 |
| 权限 | C_platform §B 权限矩阵对该 wp_code 端点的覆盖 | C_platform |
| Playwright | 运行时 Playwright 端到端验收 | E2E 环境（全部待环境） |

---

## 验收矩阵
| # | wp_code | owner_spec | 源模板 | contract/identity | HTML→Excel→HTML | 公式/冲突 | 权限 | Playwright |
|---|---------|-----------|--------|-------------------|-----------------|---------|------|------------|
| 1 | D4-1 | d4-dual-mode-formula-governance | ✅ 已实证 | C1 FROZEN；C2 key schema❌（stable_key/row_key 未落地）；C3 TB发布无显式确认🔴；C_platform 导入无CMS接入🔴 | UNVERIFIABLE | C2协议FROZEN；missing/damaged/blocked三态❌；CAS save()无baseVersion❌ | D4-1 save走EventBus✅；TB发布无显式确认🔴 | UNVERIFIABLE |
| 2 | D4-2 | d4-revenue-matrix-bidirectional | ✅ 已实证 | 由owner spec负责；本spec登记owner_spec=已分配 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 3 | D4-3 | d4-revenue-matrix-bidirectional | ✅ 已实证 | 由owner spec负责；本spec登记owner_spec=已分配 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 4 | D4-4 | d4-adjustment-and-analysis-gap-closure | ✅ 已实证 | gap spec负责（复用A13/集中调整）；C0缺口登记：身份键/roundtrip/Playwright均缺 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 5 | D4-5 | d-cycle-sheet-bidirectional-expansion | ✅ 已实证 | 由owner spec负责；C2 render schema Y；公式引擎接线待C4 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 6 | D4-6 | d-cycle-sheet-bidirectional-expansion | ✅ 已实证 | 由owner spec负责；C2 render schema Y；公式引擎接线待C4 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 7 | D4-7 | d-cycle-sheet-bidirectional-expansion | ✅ 已实证 | 由owner spec负责；C2 render schema缺失（27/36无schema） | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 8 | D4-8 | d4-adjustment-and-analysis-gap-closure | ✅ 已实证 | gap spec负责（复用月度毛利计算）；C0缺口：产品维度身份键/preset-custom/roundtrip均缺 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 9 | D4-9 | d4-9-customer-structure-bidirectional-writeback | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 10 | D4-10 | d4-price-analysis-writeback-linkage | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 11 | D4-11 | d4-price-analysis-writeback-linkage | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 12 | D4-12 | d4-adjustment-and-analysis-gap-closure | ✅ 已实证 | gap spec负责（复用合同卡片/OCR/AI）；C2 render schema Y；C0缺口：身份键/mask/roundtrip均缺 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 13 | D4-13 | d4-inspection-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema Y；DAG接入待C4 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 14 | D4-14 | d4-inspection-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 15 | D4-15 | d4-inspection-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 16 | D4-16 | d4-inspection-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 17 | D4-17 | d4-cutoff-return-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 18 | D4-18 | d4-cutoff-return-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 19 | D4-19 | d4-cutoff-return-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 20 | D4-20 | d4-cutoff-return-writeback-formula-io | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 21 | D4-21 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | ✅ 已实证 | 由owner spec负责；C2 render schema Y；跨sheet公式待C4 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 22 | D4-22 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | ✅ 已实证 | 由owner spec负责；C2 render schema Y | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 23 | D4-23 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 24 | D4-24 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 25 | D4-25 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 26 | D4-26 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 27 | D4-27 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 28 | D4-28 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 29 | D4-29 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 30 | D4-30 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 31 | D4-31 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 32 | D4-32 | d4-ipo-fraud-writeback-formula | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 33 | D4-33 | d4-33-36-writeback-formula-and-io-closure | ✅ 已实证 | 由owner spec负责；C2 render schema Y | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 34 | D4-34 | d4-33-36-writeback-formula-and-io-closure | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 35 | D4-35 | d4-33-36-writeback-formula-and-io-closure | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |
| 36 | D4-36 | d4-33-36-writeback-formula-and-io-closure | ✅ 已实证 | 由owner spec负责；C2 render schema缺失 | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE | UNVERIFIABLE |

---

## GREEN/RED/UNVERIFIABLE 汇总

| 类别 | ✅ 计数 | ❌ 计数 | UNVERIFIABLE 计数 | wp_code |
|------|--------|--------|-------------------|---------|
| 源模板（C0 已实证） | 36 | 0 | 0 | 全部 36 个 |
| contract/identity | 0 | 3 | 33 | D4-1 有明确缺口；其余 35 个由 owner spec 负责 |
| HTML→Excel→HTML roundtrip | 0 | 0 | 36 | 全部 UNVERIFIABLE（需运行时环境） |
| 公式/冲突 | 0 | 3 | 33 | D4-1 有明确 C2 缺口；其余由 owner spec 负责 |
| 权限 | 0 | 0 | 36 | 全部 UNVERIFIABLE（端点级验证需 E2E） |
| Playwright | 0 | 0 | 36 | 全部 UNVERIFIABLE（需 start-dev.bat 环境） |

### 按 wp_code 汇总

| 状态类别 | 计数 | wp_code |
|---------|------|---------|
| 全部 6 维度 UNVERIFIABLE（纯 owner 委托） | 29 | D4-2/3/5/6/7/9/10/11/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34/35/36 |
| 有明确 ❌ 缺口 + 部分 UNVERIFIABLE | 3 | D4-4/8/12（gap spec 负责） |
| 专属 + 有明确 ❌ 缺口 | 1 | D4-1（本 spec 负责） |
| **合计** | **36** | — |

---

## D4-1 专属缺口明细（本 spec owner）

D4-1 是本 spec 专属治理的底稿（审定表），以下缺口必须在本 spec 范围内收口：

| 缺口 | 来源契约 | 严重度 | 说明 |
|------|---------|--------|------|
| C2 公式 key schema 未落地 | C2 §A.3 | 🔴 P0 | `sheet_name` 非 stable；`target_cell` 非 row_key/field_key；唯一索引与冻结 key 不匹配；`preset_version` 与 `definition_version` 混同 |
| C2 missing/damaged/blocked 三态不存在 | C2 §B.2 | 🔴 P0 | `lifecycle_state` 7 值集与六态不同构；三态机制完全缺失 |
| C2 `wp_formula_service.save()` 无 CAS | C2 §D.5 | 🔴 P0 | 未校验 `baseVersion`，直接 upsert 覆盖 |
| C2 `_eval_func_node` 兜底返 0 | C2 §D.6 | 🔴 P0 | 违反「不得静默仅存值」；须改为抛 `FormulaBlockedError` |
| C2 编辑/保存入口无 schema 白名单 gate | C2 §F.3 | 🟡 P1 | 表达式白名单校验仅在求值时兜底，编辑入口无独立校验点 |
| C2 preset+custom 并存态无法表达 | C2 §E.3 | 🟡 P1 | `formula_source` 是互斥枚举，需新增 `preset_expression`/`custom_expression`/`is_custom_active` |
| C3 TB 发布无显式确认 | C3 §B.2 | 🔴 P0 | `_on_d_audit_determination_saved` 在 WORKPAPER_SAVED 自动触发，无确认步骤 |
| C3 TB 发布无 durable ack | C3 §B.2 | 🟡 P1 | 回写成功后仅 `logger.info()`，无持久化确认表 |
| C3 单 writer 冲突仲裁缺失 | C3 §A.2 | 🟡 P1 | `trial_balance.audited_amount` 写入无并发锁 |
| C_platform D4 导入绕过 CMS | C_platform §E.1 | 🔴 P0 | `/d4/import-data` 直接写 `parsed_data`，未调用 `ContentMutationService.commit()` |
| C_platform D4 导入无 CAS | C_platform §E.1 | 🔴 P0 | 无 `expected_revision`，并发导入可能静默覆盖 |
| C_platform D4 导入无编辑权限强制 | C_platform §E.2 | 🟡 P1 | 仅 `get_current_user`，`readonly` 用户可执行导入写入 |

---

## 关键阻塞项（进入 GREEN 的必要条件）

### 必须修复后才能将 D4-1 验收状态从 PARTIAL 推进到 GREEN：

1. **🔴 C2 公式 key schema 落地**：`WpFormula` 表 + ORM + Service 三层必须使用冻结的 `wp_id + stable_sheet_key + row_key + field_key + #custom` 五元组；当前 DB schema 与冻结契约不一致
2. **🔴 C2 三态机制实现**：`missing`/`damaged`/`blocked` 三态必须显式建模并与 `lifecycle_state`（执行态）正交；当前完全缺失
3. **🔴 C2 CAS 校验接线**：`wp_formula_service.save()` 必须校验 `baseVersion`；当前直接 upsert 覆盖
4. **🔴 C2 兜底行为修正**：`formula_engine._eval_func_node` 遇未知函数必须抛 `FormulaBlockedError`，不得返 0
5. **🔴 C3 TB 发布显式确认**：D4-1 审定表保存后 TB 发布必须经用户显式确认；当前自动触发
6. **🔴 C_platform D4 导入接入 CMS**：`/d4/import-data` 必须走 `ContentMutationService.commit()` + CAS
7. **🟡 C2 编辑入口白名单 gate**：公式编辑/保存入口必须有独立的 schema 白名单校验
8. **🟡 C2 preset+custom 并存态**：`WpFormula` 需支持同 key 上 preset 与 custom 并存

### 外部依赖（非本 spec 可独立修复）：

9. **Playwright E2E 环境**：36 个 wp_code 的 HTML→Excel→HTML roundtrip + Playwright 验收均需 `start-dev.bat` 运行时环境
10. **owner spec 完成**：D4-2/3/5/6/7/9/10/11/13~36 的 contract/identity/formula/permission 验收由各 owner spec 负责
11. **gap spec 完成**：D4-4/8/12 的缺口收口由 `d4-adjustment-and-analysis-gap-closure` 负责

---

## 变更控制

- 本矩阵为 C4 验收基准。任何修改必须：
  1. 有对应的代码变更（非仅文档更新）
  2. 更新 `GREEN/RED/UNVERIFIABLE 汇总` 计数
  3. UNVERIFIABLE 不得降级为 ✅（必须从 UNVERIFIABLE 先经 ❌ 再由 ✅）
- 状态推进路径：UNVERIFIABLE → ❌（有代码证据确认缺口）→ ✅（缺口修复+测试通过）
- **UNVERIFIABLE 不计 GREEN**（Requirement 8.1）
