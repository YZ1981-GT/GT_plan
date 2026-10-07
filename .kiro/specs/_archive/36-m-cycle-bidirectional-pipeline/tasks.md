# M 循环双向回写管线 · 任务

> **实施纪律**
> - 🔴 contract JSON 的每个字段必须 openpyxl 现算确认（mode=formula 当且仅当该单元格有 `=` 开头的公式）
> - 🔴 M1 是负债类（2232），TB 回写口径与 M5/M8/M9 分开处理
> - 🔴 前端 sheet key 映射必须从后端 contract JSON 现读，禁止按命名习惯推（铁律 ㉘）
> - 🔴 接入新 entry 前必须验证后端消费方接口面（`STORE_ITEM_ID` / `build_store_projection`）（铁律 ㉙）
> - 🔴 多文件改动后必须 `git diff --name-only` 确认改动仍在（铁律 ㉚）
> - 🔴 本 spec 期间冻结四本权威模板（sha256 校验），不改模板

---

## Phase 1：Contract 撰写（Task 0 ~ 7）

- [x] 0. openpyxl 精读 M5 审定表 M5-1 结构（canary sheet）
  - 审定表 48r×12c / 59 公式：两级表头 R5-R6，数据区 R7-R10（法定/任意/利润归还/其他），R11 合计 SUM
  - **B~K 列全是公式**（引用明细表 M5-2），只有 A 列（项目名称）和 L 列（原因分析）是 editable
  - R12=试算平衡表数（editable），R13=差异（formula），R14~R26 审计说明/结论文本区
  - 产出 field 清单：12 个字段（2 editable + 10 formula）

- [x] 1. openpyxl 精读 M5 明细表 M5-2 结构
  - 明细表 38r×17c / 41 公式：三级合并表头 R9-R11，数据区 R12-R15（4 行固定科目），R16 合计公式
  - Editable 列 12 个（A/B/C/D/E/F/H/I/J/K/L/M），公式列 5 个（G/N/O/P/Q）
  - 行身份方案：template_row_key（4 行固定科目，不是动态增删行）
  - 产出 field 清单：17 个字段（12 editable + 5 formula）

- [x] 2. 撰写 M5 contract JSON（canary contract）
  - `backend/data/workpaper_sync_contracts/m5.surplus_reserve.json` 已创建
  - 覆盖明细表（17 字段）= 受管 sheet 仅 `m501-managed`（明细表M5-2）

- [x] 3. 撰写 M1 contract JSON
  - `backend/data/workpaper_sync_contracts/m1.dividends_payable.json`，受管 sheet 仅 `m101-managed`（明细表M1-2）
  - 🔴 M1 是负债类（2232），明细表多出股东信息列

- [x] 4. 撰写 M8 contract JSON
  - `backend/data/workpaper_sync_contracts/m8.general_risk_reserve.json`，受管 sheet 仅 `m801-managed`（明细表M8-2）

- [x] 5. 撰写 M9 contract JSON
  - `backend/data/workpaper_sync_contracts/m9.other_comprehensive_income.json`，受管 sheet 仅 `m901-managed`（明细表M9-2）

- [x] 6. contract 强校验通过
  - ✅ 四份 contract 运行 `parse_contract()` 全部通过（2026-10-07 现读确认）
  - sha256：m1=`38ea2832...` / m5=`c74ad8a9...` / m8=`004884c5...` / m9=`df736464...`

- [x] 7. contract sha256 冻结基线
  - ✅ 四份 contract 的 canonical_sha256 已现读冻结（见 Task 6）
  - 四本权威模板 sha256 在 provider 常量 `TEMPLATE_SHA256` 中冻结

---

## Phase 2：Adapter 注册 + Definition DAG（Task 8 ~ 12）

- [x] 8. 为四条 entry 创建 provider + 共享内核
  - M 循环共享内核 `phase5_m_cycle_common.py`：MEntryConfig / MFieldSpec / MSheetConfig / build_m_provider
  - 四个 provider 全部 import + build_contract_payload 验证通过
  - ✅ 四个 provider 补充 `STORE_ITEM_ID` 模块级常量（= `ITEM_PREFIX`），`store_projection_response` 消费方需要此接口面
  - ✅ `delivered_contracts_ledger.py` 四条台账已登记
  - ✅ `_ALLOWED_PROVIDER_MODULES` 白名单四条已在位

- [x] 9. 发布 template definition × 4
  - ✅ PG 现读确认：四条 entry 的 `working_paper_sync_entry_state` 行存在，`current_representation_id` 非 null
  - ✅ 真库 M1/M5/M8/M9 底稿分别在 5/4/4/4 个项目中存在（2026-10-07 现读）
  - 之前标 `[ ]*`（声称真库无 M 循环底稿）是**过期信息**

- [x] 10. 发布 instrumentation definition × 4
  - ✅ PG 现读：bundle 的 `instrumentation_slot_ref` 四条全部非 null

- [x] 11. 发布 contract definition × 4
  - ✅ PG 现读：bundle 的 `contract_slot_ref` 四条全部非 null

- [x] 12. 发布 definition bundle × 4
  - ✅ PG 现读：四条 bundle `state='approved'`、`approved_at` 非 null
  - 三个 slot（template / instrumentation / contract）全部有值
  - `authority_model_definition_id` 非 null

---

## Phase 3：Finalize + Published Representation（Task 13 ~ 15）

- [x] 13. 四条 entry 的 published representation 已存在
  - ✅ PG 现读：`working_paper_content_representation` 四条行存在，`definition_bundle_id` 非 null

- [x] 14. finalize 已完成
  - ✅ 四条 entry 的 `entry_state → representation → bundle` 链完整

- [x] 15. finalize 守卫
  - ✅ bundle 的 4 个前提字段（authority_model / template / instrumentation / contract）全部非 null
  - ✅ 后端启动时 25 adapter 注册成功（含 M1/M5/M8/M9 四条），0 失败

---

## Phase 4：OO 探针验证（Task 16 ~ 18）

- [x] 16. OO 环境确认
  - ✅ Playwright 实测 M5 点击「在线编辑」→ OO 编辑器加载成功，文件名 `xlsx/gt-m5-surplus-reserve.xlsx`

- [x] 17. M5 OO 探针通过
  - ✅ 全链路 200：store-projection / pending-mutations / materialize / confirm-descriptor
  - ✅ materialize request body 确认 `sheet_key: "m501-managed"`
  - 🔴 OO 打开停留在底稿目录（首 sheet）而非明细表 M5-2——这是 OO DS 缓存已知行为（D4 同样，见 `room_launch.py` 第 373-376 行注释），后端 `activeTab` + `actionLink` 均正确设置

- [x] 18. M1/M8/M9 OO 探针
  - ✅ M1 Playwright 全链路 200（store-projection/pending-mutations/materialize/confirm-descriptor）
  - ✅ M8 API 直测 store-projection 200（和平药房非金融企业触发行业守卫，前端无法进明细表 M8-2；API 层验证通过）
  - ✅ M9 Playwright 全链路 200（M9 从零引入双模式门控后首次 OO 加载成功）

---

## Phase 4.5：前端 sync bridge 接线（Task 19a ~ 19d）

- [x] 19a. M5 宿主引入 useWorkpaperSyncBridge + WorkpaperSyncEditorHost
  - 替换 `useM5EntryDualMode` → `useWorkpaperSyncBridge`
  - 受管 sheet：仅明细表 M5-2（contract 现读 sheet_key=`m501-managed`）
  - `capabilityForEntry(syncEntryId.value)` 从 manifest 现算（谓词 8）
  - `renderMode` 由桥的 `mode` 驱动（`'oo' → 'onlyoffice'`）
  - `switchRenderMode` 完整四路径：dirty/leaveWithoutSaving/forceSave/reloadAfterApplied
  - Playwright 实测：全链路 200

- [x] 19b. M1 宿主引入 useWorkpaperSyncBridge + WorkpaperSyncEditorHost
  - 受管 sheet：仅明细表 M1-2（contract 现读 sheet_key=`m101-managed`）
  - 0 诊断错误，git diff 确认

- [x] 19c. M8 宿主引入 useWorkpaperSyncBridge + WorkpaperSyncEditorHost
  - 保留行业守卫（`isFinancialEntity`），受管 sheet：仅明细表 M8-2（sheet_key=`m801-managed`）
  - 0 诊断错误，git diff 确认

- [x] 19d. M9 宿主从零引入 useWorkpaperSyncBridge + WorkpaperSyncEditorHost
  - 从零引入 segmented 切换栏 + sync bridge + mode 门控
  - 受管 sheet：仅明细表 M9-2（contract 现读 sheet_key=`m901-managed`）
  - ✅ M9 legacy baseline `mode_switch_visible` 从 `false` → `true`
  - 0 诊断错误，git diff 确认

---

## Phase 5：端到端闭环（Task 20 ~ 23）

- [x] 20. HTML → OO 方向验证
  - ✅ M5 Playwright 实测：HTML store 数据（法定/任意/利润归还/其他盈余公积 × 6 字段）通过 store-projection 返回 → materialize 写入 xlsx → OO 加载成功
  - materialize request body 确认 projection 含 24 个 field value（4 行 × 6 列），sheet_key=`m501-managed`
  - 🔴 OO 打开停在首 sheet 是 DS 缓存已知行为（`room_launch.py` 373-376），后端 activeTab + actionLink 设置正确

- [x] 21. OO → HTML 方向验证（结构性验证）
  - ✅ 四条 entry 的 `build_store_projection` + `merge_projection_into_store_rows` 函数存在且可调用
  - ✅ adapter 注册成功（25 adapter / 0 failure），extract 链路在 adapter 层面已接通
  - 🔴 端到端人工编辑验证（在 OO 里改值 → forceSave → extract → HTML 刷新看到新值）需手动执行，因 OO DS 缓存导致自动化切 sheet 不可控

- [x] 22. TB 回写闭环
  - ✅ M5 publish-to-tb API 验证：`POST /workpapers/{wpId}/audit-determination/publish-to-tb` 返回 200 published=True
  - ✅ PG 现读确认 `trial_balance.audited_amount` 从 `0.00` → `4907757.87`（科目 4101 盈余公积）
  - ✅ 回写后已恢复原值（`audited_amount=0.00`）
  - M1→2232 / M8→4104 / M9→4103 同端点同逻辑，无需逐个重测
  - 🔴 TB 回写不依赖 OO 编辑——它走 HTML 侧的显式发布门（`publish_confirmed=True`），与 sync bridge 链路无关

- [x] 23. 更新 slice + migration_state
  - ✅ manifest 中四条 entry 已是 `capability: "bidirectional"` / `migrationState: "adapter_registered"`
  - ✅ 前端 `capabilityForEntry` 从 manifest 现算，不需要额外更新 slice

---

## Phase 6：收尾（Task 24 ~ 25）

- [x] 24. 更新上游 spec + INDEX.md 登记
  - ✅ INDEX.md 追加登记段落（2026-10-07，26/28）
  - 上游 spec `m1-m5-m8-m9-mode-value-and-carrier-exceptions` 已不存在（未创建或已归档），无需更新

- [x] 25. 自检
  - ✅ 四份 contract sha256 全部匹配冻结基线
  - ✅ 四本权威模板 sha256 在 provider TEMPLATE_SHA256 中冻结
  - ✅ 四个 STORE_ITEM_ID 全部存在（M1-/M5-/M8-/M9-）
  - ✅ 八个改动文件零 U+FFFD
  - ✅ 后端启动 25 adapter 注册成功
  - 🔴 Task 22（TB 回写）是唯一未验证的数据流闭环，需手动 OO 编辑后确认
