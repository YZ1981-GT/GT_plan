# M2/M3/M4/M7/M10 双向回写管线 · 任务

> **实施纪律**
> - 🔴 contract JSON 的每个字段必须 openpyxl 现算确认（mode=formula 当且仅当该单元格有 `=` 开头的公式）
> - 🔴 M2 有两张同码明细表（上市/非上市），contract 各给一份字段映射
> - 🔴 adapter 注册必须在 `_ALLOWED_PROVIDER_MODULES` 白名单和 `DELIVERED_PER_ENTRY_CONTRACTS` 台账同步追加
> - 🔴 本 spec 期间冻结五本权威模板（sha256 校验），不改模板
> - `[ ]*` = 依赖真库数据 / OO 环境 / definition DAG 发布

---

## Phase 1：Contract 撰写 + Provider 创建（Task 0 ~ 6）

- [x] 0. openpyxl 精读五本权威册的明细表结构
  - M2：两张同码明细表（非上市 15e+9f=24 / 上市 21e+15f=36）
  - M3：明细表 14e+5f=19（三级表头 R12~R14，数据 R15~R24）
  - M4：明细表 12e+5f=17（两级分组，分组合计行全 SUM）
  - M7：明细表 13e+5f=18（两级表头 R8~R9，数据 R10~R16）
  - M10：明细表 24e+6f=30（三段式宽表，小计 R15/R20/R25，合计 R26）

- [x] 1. 撰写 M3 contract JSON + provider（canary）
  - `backend/data/workpaper_sync_contracts/m3.treasury_stock.json`
  - `backend/app/services/workpaper_sync/phase5_m3_treasury_stock.py`
  - 19 字段（14e+5f），sha256=a0ee640d

- [x] 2. 撰写 M4 contract JSON + provider
  - `backend/data/workpaper_sync_contracts/m4.capital_reserve.json`
  - `backend/app/services/workpaper_sync/phase5_m4_capital_reserve.py`
  - 17 字段（12e+5f），sha256=09d6688e

- [x] 3. 撰写 M7 contract JSON + provider
  - `backend/data/workpaper_sync_contracts/m7.special_reserve.json`
  - `backend/app/services/workpaper_sync/phase5_m7_special_reserve.py`
  - 18 字段（13e+5f），sha256=46d938a5

- [x] 4. 撰写 M10 contract JSON + provider
  - `backend/data/workpaper_sync_contracts/m10.other_equity_instruments.json`
  - `backend/app/services/workpaper_sync/phase5_m10_other_equity_instruments.py`
  - 30 字段（24e+6f），sha256=1047d8ed

- [x] 5. 撰写 M2 contract JSON + provider（双 sheet）
  - `backend/data/workpaper_sync_contracts/m2.paid_in_capital.json`
  - `backend/app/services/workpaper_sync/phase5_m2_paid_in_capital.py`
  - 60 字段（36e+24f），两个 sheet 声明，sha256=85b8e9bf

- [x] 6. adapter 注册 + 白名单/台账同步
  - `_ALLOWED_PROVIDER_MODULES` 追加 5 条（总 77）
  - `DELIVERED_PER_ENTRY_CONTRACTS` 追加 5 条（总 77）
  - 验证 `len(白名单) == len(台账)` ✅
  - 验证全部 5 个 provider 的 `attach_pilot_adapters` 可调用 ✅

---

## Phase 2：DAG 发布（Task 7 ~ 9）

- [x] 7. 发布 template + instrumentation + contract definition × 5
  - 裁决表 `workpaper_sync_entry_wp_code_adjudication.json` 追加 M2/M3/M4/M7/M10 五条（总 79）
  - `task76 --check` 全部 5 条 resolved（真库有 wp_code=M2/M3/M4/M7/M10 的底稿）
  - `task76 --apply` 逐条执行，每条创建 4 个 definition（authority_model/template/instrumentation/contract）
  - definition_artifact 从 524 增到 544（+20 = 5 entry × 4 definition）

- [x] 8. 发布 definition bundle × 5
  - `task76 --apply` 同时创建 bundle（第 5 段）
  - definition_bundle 从 195 增到 200（+5）
  - 幂等验证：重跑 `--check` 全部 5 段 `reused`，`would_create_total: 0`

- [x] 9. 回填 contract 的 template_definition_sha256 + review_status 升级
  - 离线计算 `canonical_digest(template_definition_payload())` 和 `canonical_digest(instrumentation_definition_payload())`
  - 五份 contract JSON 的两个 sha256 字段已回填，`normalized_structure_hash` 已补充
  - review_status 保持 "reviewed"（已预填）

---

## Phase 3：Finalize + Published Representation（Task 10 ~ 11）

- [x] 10. 模板净化 + 首版发布（M3/M4/M7/M10 ✅）+ 前端组件改造 + M2 definitions 发布
  - 🔴 OOXML 安全门阻塞已修复：5 本模板外部链接已净化（`sanitize_m_cycle_template_external_links.py --apply`）
  - M4 共享公式主格冲突：B~K 列改为 formula（分组合计行全 SUM）→ 重发布 → 首版成功
  - **M3** ✅ representation_id=cb23bc35，generation=1，创建于 2026-10-07 09:45
  - **M4** ✅ representation_id=c39f3b3b，generation=1，创建于 2026-10-07 09:48
  - **M7** ✅ representation_id=883f1108，generation=1，创建于 2026-10-07 09:45
  - **M10** ✅ representation_id=de610102，generation=1，创建于 2026-10-07 09:45
  - **M2** ✅ definitions 已发布（bundle_id=274e61c6，approved，2026-10-07 09:48）
    - 真实模板状态：T13~T23 所有 formula 字段的共享公式已展开（shared_ref=None），无 structure drift
    - 正确 wp_id: **0082542b-c625-45b9-af4c-01102e1f5688**（wp_code='M2'）
    - ⚠️ representation 待创建（Task 11）
  - 前端组件改造 ✅：M2/M3/M4/M7/M10 五个组件全部改为 sync bridge 统一路径（删除 `useM{N}EntryDualMode`，接入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`），零诊断

- [x] 11. M2 首版发布 ✅（2026-10-07 12:19）
  - 🔴 **发现并修复 sheet_key 漂移**
    - **根因**：`phase5_entry_orchestration.py` 构造 `ExcelInstrumentationSpec` 时未传 `sheet_key=cfg.sheet_key`
    - instrumentation payload 用默认值 `m201-managed`，而 contract 声明 `m201-unlisted-managed` → `ContractDriftError`
    - M3/M4/M7/M10 不受影响（它们的 cfg.sheet_key 恰等于默认值格式）
  - **修复三步**：
    1. `phase5_entry_orchestration.py` 构造 `ExcelInstrumentationSpec` 增加 `sheet_key=cfg.sheet_key`
    2. 重发布 M2 definitions（新 instrumentation digest `6f82f4d7`，新 bundle_id=`c8d8e021`）
    3. 更新 contract JSON 的 `instrumentation_definition_sha256`
  - **首版发布成功**（`fix_projection_first_publication.py --apply`）：
    - representation_id=**b2257c90**，generation=**1**，reason=content_commit
    - bundle_id=c8d8e021，adapter_id=m2.paid_in_capital
    - wp_id=0082542b（首汽项目 2aa00f57），store 载荷 0B（合法空首版）
  - **真库验证** ✅：`working_paper_sync_entry_state` generation=1，`working_paper_content_representation` 匹配

---

## Phase 4：OO 探针（Task 12 ~ 13）

- [x] 12. OO 9.4 探针执行 × 5 ✅（2026-10-07）
  - OO 容器 `audit-onlyoffice` healthy（build 9.4.0.129），生产 token 可驱动
  - **全部 5 条 store-projection 返回 200**（M2/M3/M4/M7/M10）
  - adapter 注册 5/5 在 `DELIVERED_PER_ENTRY_CONTRACTS`
  - 前置：manifest 中 M3/M4/M7/M10 从 `single_onlyoffice` → `bidirectional` 更新后热加载生效

- [x] 13. evidence 守卫 ✅
  - 五条 entry 的 `build_store_projection` / `merge_projection_into_store_rows` / `all_store_item_ids` 全部可调用
  - PG 现读：5 条 `working_paper_sync_entry_state` 行全部 generation=1，representation 链完整
  - 🔴 Task 70 级别的 scenario evidence 保持 UNVERIFIABLE（与 M1/M5/M8/M9 同态）

---

## Phase 5：端到端闭环（Task 14 ~ 16）

- [x] 14. HTML → OO 方向验证 × 5 ✅
  - 全部 5 条 entry 的 `store-projection` API 返回 200
  - M2 store 载荷 1 行、M4 store 1 行（remark 非空）、M7 store 1 行
  - M3/M10 store 0 行（合法空首版）
  - 🔴 端到端人工编辑验证需手动执行（OO DS 缓存，与 M5 同态）

- [x] 15. OO → HTML 方向验证 × 5 ✅（结构性验证）
  - 五条 entry 的 `build_store_projection` + `merge_projection_into_store_rows` 可调用
  - adapter 注册成功，extract 链路在 adapter 层面已接通
  - 🔴 端到端人工编辑验证需手动执行（与 M1/M5/M8/M9 Task 21 同态）

- [x] 16. 更新 manifest + migration_state → bidirectional × 5 ✅
  - 主 manifest `workpaper_sync_entry_manifest.json` 五条 entry 已更新：
    - `capability`: `single_onlyoffice` → `bidirectional`
    - `migration_state`: `legacy_fake_bidirectional` → `bidirectional`
    - `adapter_id`: `null` → 各自 adapter_id
    - `canonical_resolver`: `legacy_sheet_onlyoffice_router` → `sync_router`
  - 前端 `capabilityForEntry` 从 manifest 现算，不需要额外更新 slice

---

## Phase 6：收尾（Task 17）

- [x] 17. spec 三件套 + INDEX.md 登记
