# D2 检查底稿双向回写覆盖 — Design

## 待勘测（实施前）

本 spec 的 design 需要在完成以下勘测后补充：

1. **逐子组件现读**：D2TabRelatedParty / D2TabVoucherCheck / D2TabPolicyCheck / D2TabEcl / D2TabWriteoffCheck / D2TabPledgeCheck / D2TabBizModel / D2TabAnalysis 各自的数据模型、store item_id、行身份、行增删逻辑
2. **wp_code 映射**：确认 D2-6至D2-13 工作簿在数据库里的 wp_code（可能是 D2-1），以及它在 manifest 中的归属
3. **逐 sheet openpyxl 精读**：确认表头行、数据区起止、公式列语义、UUID 列位置

## 预估架构

### 方案 A：归入现有 entry（`xlsx/gt-d2-accounts-receivable`）

如果 D2-6~D2-13 工作簿的底稿与 D2 主底稿共用同一个 `wp_id`（或通过 sibling 关系挂载），则可以：
- 在现有 provider `pilot_d2_large_json.py` 的 `build_contract_payload()` 里加 sheet
- 每张 sheet 写一个 `phase5_d2_XX_*.py` 模块声明字段映射
- 前端 `isD2SyncedSheet` 的 `D2_MANAGED_SHEET_KEYS` map 扩展

### 方案 B：新建独立 entry

如果 D2-6~D2-13 是独立的 `working_paper`（有自己的 wp_id），则需要：
- manifest 新增 entry（如 `xlsx/gt-d2-inspection`）
- 独立的 provider / 契约 / instrumentation
- 前端宿主新增该 entry 的桥实例

### 预估工作量

| 项 | 数量 | 估计 |
|---|---|---|
| sheet 精读 | 9 张 | 各 ~30 min |
| provider 模块 | 9 个 | 各 ~2 小时 |
| 契约 JSON | 1 个 | ~1 小时 |
| instrumentation | 9 张 | 随 provider 生成 |
| 前端 store 持久化 | ~7 个子组件 | 各 ~1 小时 |
| 前端接桥 | 宿主扩展 | ~2 小时 |
| roundtrip 验证 | 9 张 | 各 ~30 min |
| **合计** | | **~40 小时** |
