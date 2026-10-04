# B1 + B2 收尾证据（2026-09-19）

参照已完成姊妹 spec `d4-ipo-checklist-dual-mode-writeback-and-formula`（D4-25~28）把
D4-15/16 的后端 provider（B1）+ 前端 sync bridge 迁移（B2）做实收尾。

## 范围裁决（诚实边界）

| 表 | 处置 | 理由 |
|----|------|------|
| D4-15 营业收入完整性检查表 | ✅ B1+B2 做实 | 三维嵌套（发货单/发票/记账凭证），可套 IPO 受管行表范式 |
| D4-16 出口收入电子口岸系统核对 | ✅ B1+B2 做实 | 两级表头 + 差异重算列，可套范式 |
| D4-14 营业收入发生检查表 | ❌ 本轮不做 | 32 列七维嵌套 + 计算型 footer（合计/本期发生额/检查比例 A37-39），超 IPO「一行 marker footer + 直列映射」范式，风险不可控；单列待 D4-15/16 跑通后评估 |
| D4-13 营业收入账面金额与 ERP 系统核对记录 | 登记 N/A | 纯叙述文本表（核对过程/核对结论两段），无行集，不适配受管行表模型 |

## B1 后端 provider（做实）

- 新建 `backend/app/services/workpaper_sync/phase5_d4_inspection_sheets.py`
  - 照 IPO 数据驱动 `_SHEETS` dict + `mapping_digest` 冻结范式
  - D4-15：15 字段三维嵌套 `json_path`（`delivery/*` `invoice/*` `voucher/*`），Q 一致性列入 `formula_mask`（前端重算，不进受管契约）
  - D4-16：7 字段（前端 `ExportCheckRow` 单 portsPeriod+单 taxIndex 建模），D/I 差异列入 `formula_mask`
  - `mapping_digest` 冻结：D4-15=`418b3629…` / D4-16=`ca120930…`
  - 别名导入 `INSPECTION_*` 后缀，避免与 IPO 的 `SHEET_KEY_BY_CODE` 等符号冲突
- 装配 `phase5_d4_revenue_detail.py` 6 点：import 别名 / instrumentation_specs / digest 断言 / sheet_payload / store item 映射 / build+merge 投影
- 重生成契约 `backend/data/workpaper_sync_contracts/d4.revenue_detail.json`
  - canonical_digest `3f2751d0…`，`generate_phase5_d4_contract.py --check` OK
  - instrumentation_specs 12→14，contract sheets 13→15

### B1 测试

- `backend/tests/workpaper_sync/test_d4_inspection_store_roundtrip.py` — 18 passed（含三维嵌套专项）
- 回归 IPO + inspection roundtrip 合计 58 passed
- 契约守卫 `--check` 绿（digest 一致）

## B2 前端 sync bridge 迁移（做实）

- `D4TabCompleteness.vue`（D4-15）+ `D4TabExport.vue`（D4-16）：
  - 迁 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
  - `capabilityForEntry('xlsx/gt-d4-operating-revenue')` 现算（禁内联 bidirectional 字面量）
  - `flushHtml`：先 `flushPendingSave()` 再 `readStoreProjection()`（防投影旧值）
  - `sheetKey` 锁 `d4-15-managed` / `d4-16-managed`
  - `ContentMutationService`（spec 草案臆想名）全库零引用，本组件不引用
- `useD4CompletenessCheck.ts` 补 `flushPendingSave`
- 🔴 **修复宿主漏登记 bug**：`GtD4OperatingRevenue.vue::isD4DedicatedSyncSheet` 原列表
  `['D4-5','D4-25'..'D4-32']` **未含 D4-15/16** → 宿主对它们仍渲染 legacy
  `GtEntrySyncCapabilityNotice`（「两侧数据未互通」）+ 走 legacy `useD4EntryDualMode`，
  与子组件自管的 sync 切换器叠加（IPO D4-25~28 此前踩过的同一坑）。补登记后消除。

### B2 测试 + 真栈验收

- 前端守卫 `d4InspectionSyncHostWiring.spec.ts` — 19 passed
  - 含新增「宿主 GtD4OperatingRevenue 必须把 D4-15/16 登记为 dedicated sync sheet」+3 断言
- IPO 姊妹守卫 `d4IpoSyncHostWiring.spec.ts` — 38 passed（无回归）
- `get_diagnostics` 全 clean

**真栈 Playwright 验收**（wp `b3ab3c46-828f-4f48-950e-aee9bbdc923f` 重药控股安徽 2025，
project `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，唯一有 D4 published representation 的真实 wp）：

| 检查项 | D4-15 | D4-16 |
|--------|-------|-------|
| legacy「两侧数据未互通」通知 | noticeCount=0 ✅ | noticeCount=0 ✅ |
| 模式切换器数量 | segCount=1 ✅（无双切换器） | segCount=1 ✅ |
| sync 状态标签 | 已同步 ✅ | — |
| 切「在线编辑」→ WorkpaperSyncEditorHost + OO iframe | 渲染成功 ✅（OO spreadsheeteditor 加载 D4-15 xlsx） | — |
| console errors | 0 ✅ | 0 ✅ |

截图：`evidence/d4-16-live-clean.png`

### 早前「切在线编辑失败 3 errors」根因证伪

前一会话观察到切在线编辑后 `hasEditorHost=false` + 3 console errors，曾假设为
「representation 未含新受管表 → descriptor 解析不出」的预期边界。本轮证伪：

- 3 errors 实为 `GET .../sync/entries/xlsx/gt-d4-operating-revenue/store-projection`
  **间歇 500 + 请求耗时 23-24s**（慢请求），伴随 ledger-import active-job 每 5s 轮询超时、
  OO 冷启动、并发 vitest —— 是**瞬时后端负载**，非代码缺陷。
- 直接探针（登录 → 连调 store-projection 4 次）：**全部 200，耗时 0.07-0.14s**，
  projection 有效（330 字段 / 169 行 / overlay_applied=true）。
- 负载消退后真栈复测：iframe 正常渲染、0 errors（见上表）。

### DB 无污染

- `working_paper_sync_entry_state` 该 wp 仅 1 条 entry（`xlsx/gt-d4-operating-revenue`），
  `representation_generation` 递增（39→49）属正常 materialize（任何用户打开 sync 编辑器均如此），
  非本轮遗留脏数据；无 stray managed 行。
- 一次性探针脚本 `backend/scripts/_probe_store_projection.py` 用完即删。
