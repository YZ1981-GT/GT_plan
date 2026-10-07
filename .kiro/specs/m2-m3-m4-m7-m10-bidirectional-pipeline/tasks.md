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

- [x] 10. 模板净化 + 首版发布（M3/M4/M7/M10 ✅，M2 待修）
  - 🔴 OOXML 安全门阻塞已修复：5 本模板外部链接已净化（`sanitize_m_cycle_template_external_links.py --apply`）
  - M4 共享公式主格冲突：B~K 列改为 formula（分组合计行全 SUM）→ 重发布 → 首版成功
  - **M3** ✅ representation_id=cb23bc35，generation=1
  - **M4** ✅ representation_id=c39f3b3b，generation=1
  - **M7** ✅ representation_id=883f1108，generation=1
  - **M10** ✅ representation_id=de610102，generation=1
  - **M2** ❌ `sync_contract_structure_drift`：`audited_closing` locator T:row_identity 不一致
    - 根因：非上市明细表 T14 是共享公式主格（`ref="T14:T22"`），openpyxl resave 已展开但结构校验器仍检测到字段坐标与模板实际 cell 布局不匹配
    - 🔴 需要精确对齐 contract 字段坐标与权威模板净化后的实际 cell 结构

- [ ]* 11. M2 结构漂移修复 + 首版发布
  - `--check` 全 10/10 stages 通过 + `ready_to_publish` ✅
  - `--apply` 在 `adapter_built` 阶段报 `ContractDriftError`（T:row_identity）
  - 离线诊断：stage + plan + bundle digest 全部一致（NO DRIFT），磁盘 contract 与 bundle 冻结 contract 的 sha256 匹配
  - 🔴 根因：`--check` 走只读路径（6 阶段 loader.load）通过，`--apply` 走 `publish_first_generation` → `ContentMutationService.commit` 内部有额外的 structure drift 检查，该检查使用了 materialization 后重新观测的 structure（可能与 pre-materialization 的不同）
  - 下一步：在 `commit()` 内部的 `_stage_projection` 或 `_assert_roundtrip_equivalent` 之后的 structure 重观测处加诊断断点

---

## Phase 4：OO 探针（Task 12 ~ 13）

- [ ]* 12. OO 9.4 探针执行 × 5
  - 🔴 OO 环境不可用时标 `[ ]*`

- [ ]* 13. evidence 守卫
  - 断言 verification_state == "VERIFIED" × 5

---

## Phase 5：端到端闭环（Task 14 ~ 16）

- [ ]* 14. HTML → OO 方向验证 × 5
  - 🔴 需要真库有效业务载荷

- [ ]* 15. OO → HTML 方向验证 × 5
  - 🔴 formula 字段 OO 侧修改后 extract 应忽略

- [ ]* 16. 更新 slice + migration_state → bidirectional × 5

---

## Phase 6：收尾（Task 17）

- [x] 17. spec 三件套 + INDEX.md 登记
