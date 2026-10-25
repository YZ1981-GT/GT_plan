# G5-1（Phase 5 Excel 全量 entry）：canary 可行性 runbook + 分波裁决清册

> 状态：**只读调查 + 蓝图产出**，未改生产代码、未发布任何 entry。
> 前提：四个 Excel pilot（D2-2 / H1 / G7 / B60）§9.6 真双向已 `ONLYOFFICE_VERIFIED`（见 DEC-06）。
> 采集日期：2026-09-12。数据源：`backend/data/workpaper_sync_entry_manifest.json` + `*_cycle_manifest_slice.json` + `backend/wp_templates/`（openpyxl 直读）。
> 配套清册：`evidence/g5-1-legacy-fake-wave-census.json`（由 `backend/scripts/check/check_g51_legacy_fake_wave_census.py` 现算，可复现）。

---

## 0. 一句话结论

G5-1 的真实工作性质**不是「批量造双向」，而是「按可双向性分波裁决」**：137 个 `legacy_fake_bidirectional` 里，确定的 `single_html` 终态（前端纯 checklist、OO 侧空壳）占大头（≥63），真正值得走双向发布链的 xlsx 候选约 **2 + 50**（A 循环 checklist 2 个已核 + D~J 循环业务底稿 50 个待逐 entry 核 store）。且即便最佳候选 A5-1，实测也只有 **约 1/5 的前端字段能干净映射到 xlsx 单元格** —— 前端 checklist 组件是**重新设计的录入模型，不是 xlsx 的镜像**，多数是 partial-bidirectional。

---

## 1. 分波裁决清册（137 个 legacy_fake_bidirectional）

现算命令：`python backend/scripts/check/check_g51_legacy_fake_wave_census.py`（只读，产出 `g5-1-legacy-fake-wave-census.json`）。

| 桶 | 数量 | 含义 | 建议终态 |
|---|---:|---|---|
| **A** `bidirectional_candidate_xlsx` | 2 | xlsx 权威册 + 有 HTML store 对端（cycle slice 已逐 entry 核） | bidirectional 候选（逐字段核映射，多为 partial，见 §2） |
| **B** `word_lane` | 22 | docx 权威册 | Word lane（Phase 6 / Task 62-64），**非** xlsx 单元格双向 |
| **C** `single_html_no_workbook` | 63 | 无权威册（前端纯 checklist，OO 侧空壳），slice 已逐 entry 核 | **single_html 终态**（AC 12.9：OO 侧无业务价值） |
| **D** `not_in_slice_xlsx_pending` | 50 | 未在 cycle slice 逐 entry 核的 xlsx（D/E/F/G/H/I/J 循环业务底稿） | 待逐 entry 核 store，多与 D2 同族 → 大概率 bidirectional 候选 |

**A 类 2 个**：`xlsx/gt-a51-cashflow-audit`（store=checklist_responses）、`xlsx/gt-a3-consolidation-console`（store=field_overrides）。

**D 类 50 个**（真正的业务底稿主体，与 D2 pilot 同族）：`gt-d1-notes-receivable` / `d3-prepaid` / `d4-operating-revenue` / `d5` / `d6` / `d7` / `e1-monetary-fund` / `f1`~`f5` / `g1`~`g14` / `h2`~`h10` / `i1`~`i6` / `j1-employee-compensation` 等。它们 `not_in_slice` 是因为对应 cycle slice 用了不同 entry_id 命名（如 slice 内是 `d1.xxx` 契约键，manifest 是 `xlsx/gt-d1-notes-receivable`）；它们**有专属后端 render 策略**（`render_d1_notes_receivable` 等，见 `wp_render_strategies/__init__.py` 的 `RENDERER_DISPATCH`），是结构化 HTML 组件，需逐 entry 核 `html_counterpart.store` 后定终态。

> 🔴 分类纪律：`not_in_slice` 的 50 个**不武断归 C**（脚本首版误把它们当「无权威册」）。它们只按 manifest `document_type` 粗分（docx→B / xlsx→D 待判），真实终态必须逐 entry 核 store 才能定。

---

## 2. A5-1 canary 字段→单元格映射蓝图（唯一 xlsx checklist 深核样本）

权威册：`backend/wp_templates/A/A5-1 现金流量表审计.xlsx`（60894 字节，9 sheet，已有 `GT_Custom` sheet 但内容是 C1-C8 占位、**非**真 instrumentation）。
前端：`GtA51CashflowAudit.vue` + `useA51CashflowAudit.ts`（静态常量定义 + checklist_responses store，item_id 前缀 `a51-`）。

### 2.1 逐前端表映射可行性（实测 openpyxl 直读）

| 前端表（useA51CashflowAudit.ts） | item_id 形态 | xlsx sheet | 映射可行性 |
|---|---|---|---|
| **AUDIT_ROWS**（8 行） | `a51-audit-{1..8}.unadjusted` / `.adjustment` | `A5-1-1列示于…现金及现金等价物` | ✅ **干净可映射**：audit-1→D7/E7，audit-2→D8/E8，audit-3→D9（「……」占位），audit-4→D10/E10，audit-5→D11（占位），audit-6(auto)→D12 公式，audit-7→D13/E13，audit-8(auto)→D14 公式。未审=D 列、审计调整=E 列、审定=G 列(=D+E 公式) |
| **PROGRAM_STEPS**（21 步） | `step-{N}` / `step-{N}-{M}` | `A5-1现金流量审计程序`（行 11-34） | ⚠️ **部分**：前端 step id 与 xlsx「序号」列（1 / 1.1）需对齐；但前端 checklist 值 vs xlsx「是否适用/执行情况说明」列语义不同，非逐格镜像 |
| **RECONCILE_GROUPS**（4 组 × 3-10 item） | `a51-reconcile-{g}-{i}.amount` | 无对应 sheet | ❌ **前端独有**，xlsx 无此结构 |
| **CHECK4_SECTIONS**（acquire/dispose 各 10 行） | — | `A5-1-4现金流量核查`（行 10-29） | ❌ **结构不一致**：前端扁平 10 行 vs xlsx 层级（取得/处置 + 流动/非流动资产负债明细） |
| **CHECK5_ROWS**（10 行扁平） | — | `A5-1-5现金流量核查`（行 10-20） | ❌ **结构不一致**：前端扁平 vs xlsx 层级（一、现金/二、现金等价物/三、期末余额 + 明细），列语义也不同（xlsx 差异/原报数/测算数 三列 vs 前端单值） |
| **OTHER_CF_GROUPS**（3 组 × receive/pay 各 10） | — | `A5-1-6其他现金流量`（仅经营活动 B9:B18/D9:D18） | ❌ **语义不对齐 + 组数不符**：xlsx 只覆盖经营活动一部分，行名与前端 item name 不对应 |

### 2.2 蓝图核心结论（对 D 类 50 个有普适参考价值）

- **只有 AUDIT_ROWS（约 1/5 字段）能干净单元格级映射**。其余前端表是「重新设计的扁平录入模型」，与 xlsx 原始审计模板的层级结构不是「同一数据的两个视图」。
- ⇒ A5-1 若强行全字段双向**不成立**；诚实终态是 **partial-bidirectional**（仅 AUDIT_ROWS 段双向 + 其余 single_html）或整体 **single_html**。这需要产品裁决（是否值得为 1/5 字段建双向发布链）。
- **普适推论**：任何「前端 checklist 组件 + xlsx 权威册」的 entry，都要先做 §2.1 这张逐表映射核对，**不能假设前端字段=xlsx 单元格**。D 类 50 个业务底稿里，D2 已证可干净映射（它是为 xlsx 结构化设计的组件），但 A 循环 checklist 类多半像 A5-1 一样错位。

---

## 3. bidirectional 迁移链范式（复用 B60 pilot，`pilot_simple_checklist.py`）

某 entry 走到 `bidirectional_verified` 需复制 B60 的整套模块结构（`backend/app/services/workpaper_sync/pilot_simple_checklist.py`，约 1160 行）并为该 entry 定制。**AC 12.1 的六件前置全部齐备才允许翻 `bidirectional`**（否则 Task 1/2 的 closure guard 打红）：

| 步骤 | B60 范式函数 | A5-1/新 entry 需做 | 真库写入 |
|---|---|---|---|
| 1. 契约 | `build_contract_payload()` → `a51.cashflow_audit.json` | 按 §2.1 逐字段声明 cell 坐标 / stable_field_key / json_pointer / value_type / source_ref；**只声明可干净映射的字段**（A5-1 仅 AUDIT_ROWS 段） | 否（JSON 文件） |
| 2. instrumentation | `instrumentation_spec()` / `instrumentation_definition_payload()` | identity 载体（A5-1 是固定行静态表，用固定 `row_from: <行号>`，不需 row UUID；仍需 hidden sheet / defined name 定位） | 否 |
| 3. authority | `authority_model_payload()`（`projection_contract`） | 复用 | 否 |
| 4. 发布链 | `publish_pilot_definitions(publisher)` | 顺序发布 authority→template→instrumentation→contract→**bundle**；校验 template/instrumentation digest 与 contract 声明一致 | ✅ **写 `working_paper_sync_definition_artifact` / `..._definition_bundle`** |
| 5. published representation | `projection_first_publication`（`fix_projection_first_publication.py`） | 首版发布 current representation（gen=1） | ✅ **写 `working_paper_content_representation` + entry pointer** |
| 6. adapter 注册 | `build_pilot_matcher` / `build_pilot_registration` / `register_pilot_adapter` / `attach_pilot_adapters` | matcher（精确 wp_code 集）+ registration（`declared_capability=bidirectional`） | 否（请求期 registry） |
| 7. 宿主接线 | — | 前端宿主（GtA51CashflowAudit.vue）挂 `WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge` + store-projection（参 B60 GtB60Bundle.vue） | 否 |
| 8. overlay 翻 capability | `assert_manifest_capability_enabled` | reviewed overlay 把该 entry capability 裁 `bidirectional`，重生 manifest（`generate_workpaper_sync_manifest.py`）；三项齐备门（approved contract + approved bundle typed slots + published representation）由 Task 1 owner 守 | 否（JSON） |
| 9. §9.6 真栈 e2e | — | 新写 `e2e/g5-x-{entry}-unified-path.spec.ts`（复用 `g4-1-*.spec.ts` 范式）：HTML→USER_SYNC→materialize→confirm→OO 写格→forcesave(cs_error=0)→durable callback→application applied→切回 HTML DOM 显示 marker | 真栈 |
| 10. DB 三谓词印证 | — | `working_paper_content_version`（source=onlyoffice, operation_id 非空, revision+1）/ `content_application`（applied）/ `sync_operation`（oo_to_html, applied, application_id 绑定） | 真库只读核查 |

> 真库写入（步骤 4/5）走 pytest 或专用 provision 脚本（如 `publish_pilot_definitions` 的调用点在 `test_task4x_*_pg.py`），**不经 postgres MCP**（MCP 只读）。这是 medium-risk 持久化，建议专用会话逐步做。

### 3.1 前置 gate（主控 Task 75/76/77，已交付）

- Task 75（PublishedIdentityObserver）/ 76（provisioner）/ 77（Word entry gate）是发布链前置。四 pilot 已走通，说明 75/76 生产路径可用（`build_production_registry` + `register_from_manifest` + `resolve_for_entry` + `PublishedIdentityObserver.observe`）。新 entry 复用同一路径。

---

## 4. 本轮已修复的同类真实缺陷（迁移新 entry 前应知）

推进新 entry 双向时会复用四 pilot 同一套 room/lease/roundtrip 机制，本轮修复的三处缺陷（见 `g4-1-pilots-lease-room-roundtrip-fixes-handoff.md`）对所有后续 entry 生效：
1. **僵尸 participant lease 回收**（`RoomService.expire_participant`）
2. **僵尸 room TTL 续期**（`open_or_reuse_room` 复用时续期）
3. **roundtrip 空 enum/text 等值**（`content_mutation._is_roundtrip_empty`）—— D 类业务底稿多有 enum 字段，此修复尤其关键（否则任一空 enum 行 materialize 恒 500）。

---

## 5. 建议的 Phase 5 分波执行顺序

1. **先确认 C 类 63 个的 single_html 终态**（batch，低风险）：它们 slice 已逐 entry 核为无权威册/OO 空壳，overlay 裁 `single_html` 即可，不需发布链。这是把「假双向」清成诚实态的主体工作。
2. **B 类 22 个 docx 转 Word lane**（Phase 6 处理，本 Phase 不做）。
3. **D 类 50 个逐 entry 核 store**：产出各自的 §2.1 映射核对表，区分「可干净映射→bidirectional 候选」与「结构错位→single_html/partial」。与 D2 同族的（d/e/f/g/h/i 循环主表）优先。
4. **A/D 类里映射干净的候选逐个走 §3 发布链**（每个一个会话级投入 + 真库写入 + §9.6 e2e），如 four pilot 那样逐个 verified。**A5-1 因只有 1/5 字段可映射，优先级低于 D 类业务底稿。**

---

## 6. 产物清单

| 产物 | 路径 | 状态 |
|---|---|---|
| 分波清册脚本（可复现） | `backend/scripts/check/check_g51_legacy_fake_wave_census.py` | 新增（未 commit） |
| 分波清册数据 | `evidence/g5-1-legacy-fake-wave-census.json` | 新增（未 commit） |
| 本 runbook | `evidence/g5-1-canary-feasibility-and-wave-census.md` | 新增（未 commit） |

> 未 commit 原因同本轮其他产物：工作树多会话共享，交由收口方统一提交。本 runbook 不改任何生产代码/manifest/overlay，纯调查蓝图。


---

## 6. 【2026-09-12 更新】D 类首个 canary 做实到 `bidirectional_verified`：D1-3 应收票据按客户明细

> 状态从「只读调查」升级为「**D 循环首个非 pilot canary 全链交付并真栈验证**」。
> 选 D1-3 而非 A5-1：A5-1 只 ~1/5 字段能干净映射（前端 checklist ≠ xlsx 镜像）；D1-3 与已验证的 D2-2 **同族同构**（行结构化明细、store 同为 checklist_responses 单 item JSON 数组），15 列 A-O 全可干净映射（openpyxl 逐格实测 0 mismatch）。

### 6.1 关键架构裁决：Phase 5 走「harness 无关的独立 entry 路径」，不是「第五个 pilot」

四个 pilot（B60/D2/H1/G7）是 `pilot_harness.PilotClass` **封闭枚举**的代表（源码原话「再加一类不能让分母变松」），`assess_pilot_classes()` 按 entry_id 正则归类。`xlsx/gt-d1-notes-receivable` 不含 d2/h1/g7 → 会被归进 catch-all `simple_checklist`（B60 已占）。故 D1 的选型守卫 `assert_entry_selectable` **不调** `assess_pilot_classes()`，改直接在真 manifest + 真 finder 上核四条事实（entry 存在 / independent=True / profile==D2/B60 同型 / wp_code=={D1N}）+ 零回退（D1N find/any 均 None、父码 D1 落权威模板）。这正是主控 §Phase 5 交付定义「从 manifest 动态分波、每个 entry 独立 contract/bundle/evidence、不跨 entry 复用」的落法，也是剩余 50 个 D 类候选的可复用范式。

### 6.2 全链交付物

| 环节 | 产物 | 关键值 |
|---|---|---|
| 生产模块 | `backend/app/services/workpaper_sync/phase5_d1_notes_receivable.py`（~1020 行） | PHASE5_WAVE=phase5_notes_receivable（非枚举成员）；复用共享 infra（ExcelInstrumentationSpec / DefinitionPublisher / build_excel_adapter / published_identity_observer 等），不复制判据 |
| 契约 | `backend/data/workpaper_sync_contracts/d1.notes_receivable_detail.json` | 15 字段 A-O；G/J/L/O=formula（=D+E+F / =D+H-I / =J+K / =L+M+N）；footer 行 21 合计；canonical_digest=b9b28495…；由 `generate_phase5_d1_contract.py --apply` 从模块 payload 重生（双向锁死） |
| 白名单 | `adapters/registry.py` | `_ALLOWED_PROVIDER_MODULES` + `DELIVERED_PER_ENTRY_CONTRACTS` 各加 D1 条 |
| wp_code 裁决 | `workpaper_sync_entry_wp_code_adjudication.json` | wp_codes=['D1']（**非 D1-3**）—— 查真库确认 store item `D1-cust-rows` 载荷全部落 wp_code=D1；D1-3 名字最像却 0 载荷（与 D2 同理：载荷落点才是判据） |
| overlay + manifest | `workpaper_sync_entry_overlay.json` override + 重生 `entry_manifest.json` / `workpaperSyncManifest.generated.ts` | D1 capability single_onlyoffice→**bidirectional**，adapter_id=d1.notes_receivable_detail，migration_state=adapter_registered |
| 宿主接线 | `GtD1NotesReceivable.vue` | D1-3 挂 WorkpaperSyncEditorHost + useWorkpaperSyncBridge（flushHtml→store-projection / reloadHtml→loadAll）；renderMode 按 isD1DetailSheet 分支（D1-3 走 syncBridge，其余 sheet 保留 useD1EntryDualMode） |
| OO→HTML 镜像 | `oo_to_html.py` `_mirror_store_backed_if_needed` | 加 `elif adapter_id=='d1.notes_receivable_detail'` 分支（STORE_ITEM_ID + merge_projection_into_store_rows，merge_kind=rows） |
| e2e | `audit-platform/frontend/e2e/g5-1-d1-unified-path.spec.ts` | 真栈 §9.6，1 passed (2.9m) |

真库关键 ID：project=`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，wp_id=`68c7740e-dc48-4787-a788-2e77f8560673`，bundle=`dc1f3ada-…`。

### 6.3 发布链真库执行（provisioner 复用，非 MCP 写库）

- `fix_task76_provision_projection_definitions.py --apply`：4 definition + 1 bundle 写库（artifact 26→30 / bundle 10→11），幂等（重跑全 reused / would_create 0）。
- `fix_projection_first_publication.py --apply`：首版 published representation，projection value_count=52 / row_keys={notes_receivable_detail_rows:11}（真 store 267B 解析成 11 行）。

### 6.4 §9.6 真栈 e2e + DB 三谓词印证（查数据不看退出码）

e2e 证据：`evidence/g5-1-d1-unified-path/network-and-callback.json`。OO 写受管格 **A11(customer_name)** marker=`g5h513994`（activeSheet 实测切到 `原值明细表（按客户）D1-3`），forcesave **cs_error=0 / cs_outcome=accepted**，store_mirrored=true，marker_visible=true（回流到 D1TabDetailCustomer 的 customerName 输入框，input_prop_hits=1）；0 个 /d2-sync/* 请求；callback URL 含 room_id/generation/doc_key/route_credential_id/route_token 五键。

DB 三谓词（postgres 只读查真库）：
1. **applied**：`working_paper_content_application` id=230b23ba state=**applied**（08:08，e2e 运行期）。
2. **oo_to_html 镜像**：`checklist_responses` item_id=D1-cust-rows **含 marker g5h513994**，remark_len 267→352。
3. **revision+1（源=onlyoffice）**：`working_paper_content_version` revision 1(html,首版)→2(html,切 OO materialize flush)→**3(source=onlyoffice, operation_id=c4e08aca)** —— 与 e2e 跟踪的 operation_id 逐字一致，即 OO 回写产生的新版本。

⇒ **D1-3 = bidirectional_verified**。验证了 D2 之外的 D 循环 entry 可复用双向路径，且该路径是 harness 无关的通用 Phase-5 机制（非专用 pilot）。

### 6.5 剩余 49 个 D 类候选的复用指引

同族 entry（d3/d4/d5/d6/d7/e1/f*/g*/h*/i*/j* 等）复用本 canary 的 8 步：①逐 sheet openpyxl 读权威册定受管 sheet + 字段↔列↔公式 ②`build_contract_payload` + generator 重生契约 ③registry 两处白名单 + wp_code 裁决（**查真库定 store 载荷落点码**，不按名字猜）④provisioner --apply（definition/bundle）+ first_publication --apply（representation）⑤overlay override + 重生 manifest ⑥宿主 vue 挂 WorkpaperSyncEditorHost（仅受管 sheet，其余保留原 dualMode）⑦oo_to_html 加 adapter_id 分支 ⑧新写/参数化 §9.6 e2e + DB 三谓词。每 entry 独立 contract/bundle/evidence，不跨 entry 复用。

> 未 commit（工作树多会话共享，交收口方）。本轮新增/改动：phase5_d1_notes_receivable.py、generate_phase5_d1_contract.py、d1.notes_receivable_detail.json、registry.py、workpaper_sync_entry_wp_code_adjudication.json、workpaper_sync_entry_overlay.json、workpaper_sync_entry_manifest.json、workpaperSyncManifest.generated.ts、GtD1NotesReceivable.vue、oo_to_html.py、e2e/g5-1-d1-unified-path.spec.ts、evidence/g5-1-d1-unified-path/network-and-callback.json。

---

## 7. 【2026-09-12 更新】D 类第二个非 pilot canary 做实到 `bidirectional_verified`：D7-2 合同负债按合同明细

> Phase 5 第二个非 pilot canary，同 §6 D1 范式。**新增能力面**：两级表头 + 账龄组（nested `agingPrior`/`agingAudited`），且权威模板首次经**外链净化过 OOXML 门**。

### 7.1 前置 blocker：权威模板 22 外链触 OOXML 门（D 类普遍前置）

D7 权威模板 `backend/wp_templates/D/D7 合同负债.xlsx` 携 22 个 `externalLink*`（全 `TargetMode=External`，指向早已不存在的历史机器绝对路径）+ 6 处 `[n]` 真公式引用（[21]×5 在 sheet3、[22]×1 在 sheet5，均在**非受管** sheet；受管 `明细表D7-2`(sheet7) **零外链**）。OOXML 门 `validate_ooxml_artifact`（`ooxml_security.py` §8）扫任何 `.rels` 含 `TargetMode="External"` 即 REJECT，`allow_external_relationships=False` 不放宽（DEC-11）。openpyxl round-trip 实测**不掉外链**（仍 REJECT），故必须 zip 级精准删除。

**净化脚本**（正式产物，未 commit）：`backend/scripts/fix/sanitize_d7_template_external_links.py` —— zip 级精准删除 22 个 externalLink 部件 + `.rels` + `[Content_Types].xml` Override + `workbook.xml.rels` Relationship + `workbook.xml` `<externalReferences>` 块 + 82 个含 `[n]` 的 defined name；sheet3/sheet5 去 `<f>` 保 `<v>` 缓存值。保留 374 个 `#REF!` 孤儿 defined name + Print_Area/Print_Titles（最小爆破面）。留 `.preclean.bak` 作门负例。`--apply` 后新 **TEMPLATE_SHA256=`0facd3fe2297dbf72804d513d54ca08c55d6a26a41bf1d5c59fc3d7ea1c76a9a`**（旧 `d522ac9f`）；真 OOXML 门 PASS（10 门全过），13 sheet 全加载，D7-2 114 格 0 diff、22 merge 不变、Print_Area 保留。

### 7.2 全链交付物

| 环节 | 产物 | 关键值 |
|---|---|---|
| 生产模块 | `backend/app/services/workpaper_sync/phase5_d7_contract_liabilities.py`（~962 行） | 两级表头 + 账龄组；TEMPLATE_SHA256=0facd3fe；**FOOTER_MARKER='合   计'**（A23 精确文本是「合」+3 半角空格+「计」，非「合计」——修 FooterAnchorDriftError）；`merge_projection_into_store_rows` 带 `_set_json_path` 处理 nested 账龄 |
| 契约 | `backend/data/workpaper_sync_contracts/d7.contract_liabilities_detail.json` | 27 字段（两级表头）；canonical_digest=**40a2fb4c**（净化后 template 变 + footer marker 修复两次重生）；27 stable key 全 resolve，field mapping 0 mismatch |
| 契约生成器 | `backend/scripts/gen/generate_phase5_d7_contract.py`（新） | 从模块 payload 重生（双向锁死） |
| 白名单 | `adapters/registry.py` | `_ALLOWED_PROVIDER_MODULES` + `DELIVERED_PER_ENTRY_CONTRACTS` 加 D7；wp_code 裁决=('D7',) |
| wp_code 裁决 | `workpaper_sync_entry_wp_code_adjudication.json` | wp_codes=['D7']（查真库确认 store item `D7-2-rows` 载荷落 wp_code=D7，669B）；digest=c777062b |
| overlay + manifest | `workpaper_sync_entry_overlay.json` override + 重生 `entry_manifest.json` / `workpaperSyncManifest.generated.ts` | D7 capability→**bidirectional**，adapter_id=d7.contract_liabilities_detail，migration_state=adapter_registered；manifest_digest=ccc5c5ce；approved_source_digest a3099a84→ccdc7bb3（挂载 273=273 不变，3 增 3 删全是本轮自己 D1/D7 宿主 v-if→v-else-if） |
| 宿主接线 | `GtD7ContractLiabilities.vue` | D7-2（sheet 名 `明细表D7-2`，sheet_key=`d72-managed`）挂 WorkpaperSyncEditorHost + useWorkpaperSyncBridge（flushHtml→flushPendingSave+readStoreProjection / reloadHtml→loadAll）；renderMode 按 isD7DetailSheet 分支，其余 sheet 保留 useD7EntryDualMode |
| OO→HTML 镜像 | `oo_to_html.py` `_mirror_store_backed_if_needed` | 加 `elif adapter_id=='d7.contract_liabilities_detail'`（STORE_ITEM_ID=D7-2-rows，merge_kind=rows，nested 账龄经 `_set_json_path`） |
| 导出 flush | `useD7FormData.ts` | 导出 `flushPendingSave=_flushPending`（readStoreProjection 前需 flush 2s debounce） |
| e2e | `audit-platform/frontend/e2e/g5-1-d7-unified-path.spec.ts`（新） | 真栈 §9.6，**1 passed (3.1m)** |

真库关键 ID：project=`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，wp_id=`6f23dcce-6bb2-4456-9f18-b20b04043a55`，bundle=`7baecdec-6b98-4f88-a029-86285aeaf492`，representation=`98422579-4368-4873-84ed-00ade7ea6ee5`。

### 7.3 发布链真库执行（provisioner 复用，非 MCP 写库）

- `fix_task76_provision_projection_definitions.py --apply`：template+contract 变触发重发，最终 bundle=`7baecdec-…`（authority/instrumentation reused），旧 bundle 作废。
- `fix_projection_first_publication.py --check`：state=ready_to_publish，stages **10/10 全过**（OOXML 门 + materialize + roundtrip + unmanaged_regions），projection value_count=77 / row_keys={contract_liabilities_detail_rows:14}。`--apply`：published representation 出，revision 1（source=html）。

### 7.4 §9.6 真栈 e2e + DB 三谓词印证（查数据不看退出码）

e2e 证据：`evidence/g5-1-d7-unified-path/network-and-callback.json`。OO 写受管格 **A10(contract_name)** marker=`g5d7644908`（activeSheet 实测切到 `明细表D7-2`，cellTextAfterSave 确认落格），forcesave **cs_error=0 / cs_outcome=accepted / http 202**，store_mirrored=true，marker_visible=true（回流到 D7TabDetail(.d7-detail)，input_prop_hits=1）；**0 个 /d2-sync/*** 请求；callback URL 含 room_id/generation/doc_key/route_credential_id/route_token 五键。

DB 三谓词（venv 只读查真库，postgres MCP 断连）：
1. **applied**：`working_paper_content_application` id=faa0b332 state=**applied** / logical_result_code=applied / result_revision=3 / adapter_id=d7.contract_liabilities_detail（09:51 e2e 运行期）。
2. **oo_to_html 镜像**：`checklist_responses` item_id=D7-2-rows **remark 含 marker g5d7644908**（marker 镜像进 contractName 单元格）。
3. **revision+1（源=onlyoffice）**：`working_paper_content_version` revision 1(html,首版)→2(html,切 OO flush)→**3(source=onlyoffice, operation_id=48339f7e)** —— 与 e2e 跟踪 operation_id **逐字一致**（cross-check count=1），即 OO 回写产生的新版本。

⇒ **D7-2 = bidirectional_verified**。首次验证「两级表头 + 账龄组」的宽表明细也能干净走双向路径，且权威模板经外链净化后仍过 OOXML 门 + roundtrip 无损。

### 7.5 D 类外链净化的复用指引

D3(3 外链)/D5(4)/D6(21)/D7(22) 都会被 OOXML 门拒（D1/D2 干净过门）。D3/D5/D6 净化可**复用 `sanitize_d7_template_external_links.py` 范式**（各自权威册路径 + 逐个核外链是否断链孤儿/是否受管 sheet 依赖，再 zip 级精准删除留 `.bak`）。后续同族 canary 仍按 §6.5 八步；净化作为「⓪ 前置门」插在步骤 ① 之前。

> 未 commit（工作树多会话共享，交收口方）。本轮新增/改动：sanitize_d7_template_external_links.py、generate_phase5_d7_contract.py（新）、d7.contract_liabilities_detail.json、phase5_d7_contract_liabilities.py（TEMPLATE_SHA256+FOOTER_MARKER）、registry.py、workpaper_sync_entry_wp_code_adjudication.json、workpaper_sync_entry_overlay.json、workpaper_sync_entry_manifest.json、workpaperSyncManifest.generated.ts、oo_to_html.py、useD7FormData.ts、GtD7ContractLiabilities.vue、e2e/g5-1-d7-unified-path.spec.ts、evidence/g5-1-d7-unified-path/network-and-callback.json、D7 合同负债.xlsx（净化）+ .preclean.bak。

---

## 8. 【2026-09-12 更新】D 类第三个非 pilot canary 做实到 `bidirectional_verified`：D3-2 预收账款按明细

> Phase 5 第三个非 pilot canary，同 §7 D7 范式（两级表头 + 账龄组）。**新增验证面**：①首次跑通「空 store 首版」全链（OO 编辑创建第 1 行 → 镜像回 HTML）②纠正了历史误判——D3 是**预收账款**不是预付（"预付账款"是 F1）。

### 8.1 核名实：D3 = 预收账款（纠正 summary 多处错误）

- **D3 = 预收账款**（wp_code=D3, audit_cycle=D）。所谓"预付账款"是 **F1**（另一张底稿, audit_cycle=F），不是 D3 别名；"合同资产"是 **D6**。
- 前端宿主 `GtD3PrepaidAccounts.vue`（componentType `d3-prepaid-accounts`）——**组件名 PrepaidAccounts(预付) 是历史命名错**，label 与全部内容都是预收账款。
- 受管明细 sheet = `预收账款明细表D3-2`（27 列 A-AA 两级表头，store item `D3-det-rows`）。
- **D3-det-rows 全库 0 行**（明细表从未录入，同 H1-8-rows 空表单）；sibling `D3-vc-current-rows`（抽凭）载荷落 wp_code=D3（3601B）已证 D3 store 落点=D3。

### 8.2 前置 blocker：3 外链净化过 OOXML 门

D3 权威模板 `backend/wp_templates/D/D3 预收账款.xlsx` 携 3 个断链孤儿 externalLink（`Worksheet in 5440 Inventory` / `8240 COS breakdown` / `.../桌面/.../国贸_2005_随便.xls`，全 TargetMode=External）。净化脚本 `backend/scripts/fix/sanitize_d3_template_external_links.py`（复用 D7 范式，比 D7 少一步公式中和——D3 任何 worksheet 都无 `[n]` 公式格）。`--apply` 后 **TEMPLATE_SHA256=`699a9be0e7da639f3e5cd3a2d3bfdf38f7e777b330f9ec6959f5cc390fb6c2d2`**（旧 `8a27614b`），`.preclean.bak` 作门负例。变异检验 4 态全对（原始 REJECT / 只删部件保留 _rels 仍 REJECT / 破坏受管 A10 打红 / 正常净化 ext0 diffs0）；真 OOXML 门 `validate_ooxml_artifact` 净化后 PASS、`.bak` REJECT。

### 8.3 全链交付物（八步）

| 环节 | 产物 | 关键值 |
|---|---|---|
| 生产模块 | `backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py`（~660 行） | ADAPTER_ID=d3.prepaid_receipts_detail；WP_CODES={'D3P'}（manifest 幻影码，选型/matcher 用）；TEMPLATE_ID=D32；SHEET_KEY=d32-managed；**FOOTER_MARKER='合计'（纯两字无空格，非 D7 三空格）**；两级表头 行 10/11，数据区 12-23，footer 24；公式列 H/O/Q/T（=E+F+G / =E+N-M / =O+P / =Q+R+S） |
| 契约 | `backend/data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json` | 27 字段（19 标量 + 8 账龄）；canonical_digest=2cfdb859；字段键与前端 useD3Detail.DetailRow 锁死（customerName/companyCode/nature/relationType/prior*/debit(M)/credit(N)/end*/isConfirmed/postPeriodSettlement/remark + agingPrior/agingAudited nested） |
| 契约生成器 | `backend/scripts/gen/generate_phase5_d3_contract.py`（新） | 从模块 payload 重生（双向锁死） |
| 白名单 + wp_code 裁决 | `adapters/registry.py`（两白名单）+ `workpaper_sync_entry_wp_code_adjudication.json` | wp_codes=['D3']（store_payload_evidence: D3-det-rows 全库 0 行 → 以 sibling D3-vc-current-rows 落 D3 + file_path 证据定码，同 H1 空表单模式） |
| overlay + manifest | `workpaper_sync_entry_overlay.json` override + 重生 manifest | capability→bidirectional，adapter_id=d3.prepaid_receipts_detail；approved_source_digest ccdc7bb3→**1c13bff2**（变异核实：discoverer 273=273 mount 不变，唯一变动=GtD3PrepaidAccounts.vue 的 GtOnlyOfficeSheet v-if→v-else-if，D1/D7 host 逐个核未变）；manifest_digest=31074b4e |
| 宿主接线 | `GtD3PrepaidAccounts.vue` + `useD3FormData.ts` | D3-2 挂 WorkpaperSyncEditorHost + useWorkpaperSyncBridge（flushHtml→flushPendingSave+readStoreProjection / reloadHtml→loadAll）；renderMode 按 isD3DetailSheet 分支，其余保留 useD3EntryDualMode；useD3FormData 导出 flushPendingSave=_flushPending |
| OO→HTML 镜像 | `oo_to_html.py` | 加 `elif adapter_id=='d3.prepaid_receipts_detail'`（STORE_ITEM_ID=D3-det-rows，merge_kind=rows，nested 账龄经 _set_json_path） |
| e2e | `audit-platform/frontend/e2e/g5-1-d3-unified-path.spec.ts`（新） | 真栈 §9.6，**1 passed (3.0m)** |

真库关键 ID：**project=`2aa00f57-1df4-4fe8-9840-2d65d0fd8749` / wp_id=`d35c715a-9d71-4f4f-80ee-efc846533a24`**，bundle=`246ad0e4-9fee-4caa-a84f-a2c5ebd50d77`，representation=`48e427a2-7a4c-4769-9905-11f56c75e3ee`。

### 8.4 发布链落点：为何是 project 2aa00f57 不是 0ec33ac9（BP-24 的良性面）

Task76 provisioner（带 `--project-id 0ec33ac9`）解析到 wp 144abb97；但 **first_publication 无 `--project-id`**，用 `TARGET_ORDER_SQL`（`has_store_payload DESC, created_at, id`）解析。全库 **4 个 D3 底稿的 D3-det-rows 全空**（无 store 落点 tiebreaker）→ 落在 created_at 最早的 `d35c715a`（project 2aa00f57）。definition/bundle 内容寻址、project 无关，故 representation 落哪个 wp 由 first_publication 的确定性排序决定。**不与确定性 resolver 对抗**：e2e 就跑 2aa00f57 / d35c715a。

### 8.5 §9.6 真栈 e2e + DB 三谓词印证（查数据不看退出码）

e2e 证据：`evidence/g5-1-d3-unified-path/network-and-callback.json`。OO 写受管格 **A12(customerName)** marker=`g5d3439283`（activeSheet 实测切到 `预收账款明细表D3-2`，cellTextAfterSave 确认落格），forcesave **cs_error=0 / accepted / http 202**，store_mirrored=true，marker_visible=true（回流到 D3TabDetail(.d3-detail)，input_prop_hits=1）；**0 个 /d2-sync/***；callback URL 含五键。

DB 三谓词（venv 只读查真库）：
1. **applied**：`working_paper_content_application` id=cfa51e44 state=**applied** / result_revision=3 / adapter_id=d3.prepaid_receipts_detail。
2. **oo_to_html 镜像**：`checklist_responses` item_id=D3-det-rows remark=`[{"rowId":"GTROW-D32-0012","customerName":"g5d3439283"}]` —— **空 store → OO 编辑创建第 1 行并镜像**（首次验证空首版全链）。
3. **revision+1（源=onlyoffice）**：`working_paper_content_version` revision 1(html,首版)→2(html)→**3(source=onlyoffice, operation_id=57adbf25)** —— 与 e2e 跟踪 operation_id **逐字一致**（cross-check count=1）。

⇒ **D3-2 = bidirectional_verified**。首次跑通「空 HTML store 的首版发布 + OO 首行创建镜像回 HTML」全链。

> 未 commit（工作树多会话共享，交收口方）。本轮新增/改动：sanitize_d3_template_external_links.py、phase5_d3_prepaid_receipts.py（新）、generate_phase5_d3_contract.py（新）、d3.prepaid_receipts_detail.json（新）、registry.py、workpaper_sync_entry_wp_code_adjudication.json、workpaper_sync_entry_overlay.json、workpaper_sync_entry_manifest.json、workpaperSyncManifest.generated.ts、oo_to_html.py、useD3FormData.ts、GtD3PrepaidAccounts.vue、e2e/g5-1-d3-unified-path.spec.ts、evidence/g5-1-d3-unified-path/network-and-callback.json、D3 预收账款.xlsx（净化）+ .preclean.bak。

---

## 9. 【2026-09-12 更新】D 类第四个非 pilot canary 做实到 `bidirectional_verified`：D6-2 合同资产按明细

> Phase 5 第四个非 pilot canary。**新增能力面**：账龄是 **FLAT top-level 键**（agePrior1y / ageEnd1y ...），不是 D3/D7 的 nested `agingPrior/{seg}` —— 证明契约的 `json_pointer` 单段/多段两种形态都走得通。同 §7/§8 的空 store 首版 + OO 首行创建。

### 9.1 核名实 + 前置净化

- **D6 = 合同资产**（wp_code=D6，5 项目各 1 行 file_path；D6-1..D6-9 子码是索引行无 file_path）。前端宿主 `GtD6ContractAssets.vue`（componentType `d6-contract-assets`）。受管明细 sheet = `明细表D6-2`（32 列 A-AF，受管 A-AD，store item `D6-2-rows`）。
- **D6-2-rows 全库 0 行**（明细表从未录入，同 H1/D3 空表单）；全库唯一非空 D6 载荷是 `D6-note-listed-section4-groups`（28B 披露配置，非 rows）。
- 净化脚本 `backend/scripts/fix/sanitize_d6_template_external_links.py`：**21 个断链孤儿 externalLink**（0 个 `[n]` 公式格，同 D3）。`--apply` 后 **TEMPLATE_SHA256=`88125e42d79d72813c5d460be2d925adb623d85f881a177dcb4eb7c9ec1e218c`**（旧 `591d4c68`）。变异 4 态全对；真 OOXML 门净化后 PASS、`.preclean.bak` REJECT。

### 9.2 全链交付物（八步）

| 环节 | 产物 | 关键值 |
|---|---|---|
| 生产模块 | `backend/app/services/workpaper_sync/phase5_d6_contract_assets.py` | ADAPTER_ID=d6.contract_assets_detail；WP_CODES={'D6C'}；TEMPLATE_ID=D62；SHEET_KEY=d62-managed；**FOOTER_MARKER='合   计'（3 空格，同 D7）**；两级表头 行 12/13，数据区 14-25，footer 26；公式列 J/Q/T（=G+H+I / =G+O-P / =Q+R+S）；🔴 **账龄 FLAT 键**（K-N=agePrior1y..3yAbove / U-X=ageEnd1y..3yAbove，json_path 无 nested） |
| 契约 | `backend/data/workpaper_sync_contracts/d6.contract_assets_detail.json` | 30 字段（22 标量 + 8 账龄）；canonical_digest=2c8a2800；字段键与前端 useD6Detail.DetailRow 锁死（seqNo 是 integer 不是 amount） |
| 契约生成器 | `backend/scripts/gen/generate_phase5_d6_contract.py`（新） | 从模块 payload 重生 |
| 白名单 + wp_code 裁决 | `adapters/registry.py`（两白名单）+ `workpaper_sync_entry_wp_code_adjudication.json` | wp_codes=['D6']（D6-2-rows 全库 0 行同 H1/D3，file_path 证据定码） |
| overlay + manifest | override + 重生 manifest | capability→bidirectional，adapter_id=d6.contract_assets_detail；approved_source_digest 1c13bff2→**a250dfef**（变异核实：273=273 不变，唯一变动=GtD6ContractAssets v-if→v-else-if mount_7944d497，D1/D3/D7 逐个核未变）；manifest_digest=c6e926b0 |
| 宿主接线 | `GtD6ContractAssets.vue` + `useD6FormData.ts`（导出 flushPendingSave） | D6-2 挂 WorkpaperSyncEditorHost + useWorkpaperSyncBridge；其余 sheet 保留 useD6EntryDualMode |
| OO→HTML 镜像 | `oo_to_html.py` | 加 `elif adapter_id=='d6.contract_assets_detail'`（STORE_ITEM_ID=D6-2-rows，merge_kind=rows，FLAT 键经 _set_json_path） |
| e2e | `audit-platform/frontend/e2e/g5-1-d6-unified-path.spec.ts`（新） | 真栈 §9.6，**1 passed (3.3m)** |

真库关键 ID：**project=`2aa00f57-1df4-4fe8-9840-2d65d0fd8749` / wp_id=`1ed2feaf-3c3c-4a6c-824b-3be8d6e5b377`**，bundle=`201a4334-7550-4ef9-a524-ff2c890d3103`，representation=`a5f0daa9-0a89-4da4-b58b-15eeec256b80`。（同 D3 落 project 2aa00f57，first_publication 按 created_at 定，非对抗确定性 resolver。）

### 9.3 §9.6 真栈 e2e + DB 三谓词印证

e2e 证据：`evidence/g5-1-d6-unified-path/network-and-callback.json`。OO 写受管格 **B14(contractName 文本列，A 列是 seqNo 数字列不写)** marker=`g5d6309270`（activeSheet=明细表D6-2），forcesave **cs_error=0 / accepted / 202**，store_mirrored=true，marker_visible=true（回流 D6TabDetail(.d6-tab-detail)，input_prop_hits=1）；**0 个 /d2-sync/***；callback 五键。

DB 三谓词（venv 只读）：
1. **applied**：`working_paper_content_application` id=c56f6699 state=applied / result_revision=3 / adapter=d6.contract_assets_detail。
2. **镜像**：`checklist_responses` D6-2-rows remark=`[{"rowId":"GTROW-D62-0014","contractName":"g5d6309270","seqNo":1},...]`（空 store → OO 编辑创建第 1 行并镜像，含 seqNo）。
3. **revision+1（源=onlyoffice）**：rev 1(html)→2(html)→**3(source=onlyoffice, operation_id=f9108adc)** —— 与 e2e 跟踪 op 逐字一致（cross-check=1）。

⇒ **D6-2 = bidirectional_verified**。证明契约的账龄字段 FLAT 键与 nested 键两种形态都走得通同一条双向路径。

> 未 commit（交收口方）。本轮新增/改动：sanitize_d6_template_external_links.py、phase5_d6_contract_assets.py（新）、generate_phase5_d6_contract.py（新）、d6.contract_assets_detail.json（新）、registry.py、workpaper_sync_entry_wp_code_adjudication.json、workpaper_sync_entry_overlay.json、workpaper_sync_entry_manifest.json、workpaperSyncManifest.generated.ts、oo_to_html.py、useD6FormData.ts、GtD6ContractAssets.vue、e2e/g5-1-d6-unified-path.spec.ts、evidence/g5-1-d6-unified-path/network-and-callback.json、D6 合同资产.xlsx（净化）+ .preclean.bak。

---

## 10. 【2026-09-12 更新】D 类第五个非 pilot canary 做实到 `bidirectional_verified`：D5-2 应收款项融资按明细

> Phase 5 第五个非 pilot canary。**最简形态**：两级表头但**无账龄组**（FVOCI，17 列 A-Q），组标题仅是「期初数/本期变动/期末数」的列分组。证明契约的 group_source_ref 在「非账龄」的普通列分组上也走得通。

### 10.1 核名实 + 前置净化

- **D5 = 应收款项融资**（4 项目各 1 行 file_path）。前端宿主 `GtD5ReceivablesFinancing.vue`（componentType `d5-receivables-financing`）。受管明细 sheet = `应收款项融资明细表D5-2`（17 列 A-Q，store item `D5-2-rows`）。子 Tab D5TabDetail（根 `.d5-detail`，**无搜索框**）。
- **D5-2-rows 全库 0 行**（同 H1/D3/D6 空表单）。useD5Detail.DetailRow 有 19 字段，但 **postRealized(R)/eclStage(S) 是 store-only**（模板无列），只映射 A-Q 的 17 字段。
- 净化脚本 `backend/scripts/fix/sanitize_d5_template_external_links.py`：**4 个断链孤儿 externalLink**（0 个 `[n]` 公式格）。`--apply` 后 **TEMPLATE_SHA256=`92c5f7f2d2d54340c29bef6094b24a9360edcfa730fcfd406aeb071d4d138ac4`**（旧 `53cd7518`）。变异 4 态全对；真 OOXML 门净化后 PASS、`.preclean.bak` REJECT。

### 10.2 全链交付物（八步）

| 环节 | 产物 | 关键值 |
|---|---|---|
| 生产模块 | `backend/app/services/workpaper_sync/phase5_d5_receivables_financing.py` | ADAPTER_ID=d5.receivables_financing_detail；WP_CODES={'D5R'}；TEMPLATE_ID=D52；SHEET_KEY=d52-managed；**FOOTER_MARKER='合计'（纯两字，同 D3）**；两级表头 行 10/11，数据区 12-16，footer 17；公式列 F/J/L/O（=C+E+D / =C+H-I / =J+K / =J+N+M）；🔴 **无账龄组**（group 期初数 C:G / 本期变动 H:I / 期末数 J:P 下每列是不同语义字段），17 字段的 group_source_ref 用 C10/H10/J10 |
| 契约 | `backend/data/workpaper_sync_contracts/d5.receivables_financing_detail.json` | 17 字段；canonical_digest=e902a0ba；字段键与前端 useD5Detail.DetailRow 锁死（postRealized/eclStage store-only 不入） |
| 契约生成器 | `backend/scripts/gen/generate_phase5_d5_contract.py`（新） | — |
| 白名单 + wp_code 裁决 | `adapters/registry.py`（两白名单）+ `workpaper_sync_entry_wp_code_adjudication.json` | wp_codes=['D5']（D5-2-rows 全库 0 行同 H1/D3/D6，file_path 证据定码） |
| overlay + manifest | override + 重生 manifest | capability→bidirectional，adapter_id=d5.receivables_financing_detail；approved_source_digest a250dfef→**05eda01b**（变异核实：273=273 不变，唯一变动=GtD5ReceivablesFinancing v-if→v-else-if mount_11ac71cd，D1/D3/D6/D7 逐个核未变）；manifest_digest=2c5c8517 |
| 宿主接线 | `GtD5ReceivablesFinancing.vue` + `useD5FormData.ts`（导出 flushPendingSave） | D5-2 挂 WorkpaperSyncEditorHost；其余 sheet 保留 useD5EntryDualMode |
| OO→HTML 镜像 | `oo_to_html.py` | 加 `elif adapter_id=='d5.receivables_financing_detail'`（STORE_ITEM_ID=D5-2-rows，merge_kind=rows） |
| e2e | `audit-platform/frontend/e2e/g5-1-d5-unified-path.spec.ts`（新） | 真栈 §9.6，**1 passed (3.2m)** |

真库关键 ID：**project=`2aa00f57-1df4-4fe8-9840-2d65d0fd8749` / wp_id=`629d762a-d363-4195-b1bc-5c28e3c2bd72`**，bundle=`fbf0a58a-2832-40a3-90bc-9a3508fa4c83`，representation=`33f62c29-2b52-4193-9910-8e711c66d283`。（D3/D6/D5 三个 e2e 目标 wp 全落 project 2aa00f57。）

### 10.3 §9.6 真栈 e2e + DB 三谓词印证

e2e 证据：`evidence/g5-1-d5-unified-path/network-and-callback.json`。OO 写受管格 **B12(itemName 文本列，A 列是 category enum)** marker=`g5d5979837`（activeSheet=应收款项融资明细表D5-2），forcesave **cs_error=0 / accepted / 202**，store_mirrored=true，marker_visible=true（回流 D5TabDetail(.d5-detail) itemName 输入框，**D5 无搜索框**直接扫，input_prop_hits=1）；**0 个 /d2-sync/***；callback 五键。

DB 三谓词（venv 只读）：
1. **applied**：state=applied / result_revision=3 / adapter=d5.receivables_financing_detail。
2. **镜像**：`checklist_responses` D5-2-rows remark=`[{"rowId":"GTROW-D52-0012","itemName":"g5d5979837"}]`（空 store → OO 编辑创建第 1 行并镜像）。
3. **revision+1（源=onlyoffice）**：rev 1(html)→2(html)→**3(source=onlyoffice, operation_id=af6d13d7)** —— 与 e2e 跟踪 op 逐字一致（cross-check=1）。

⇒ **D5-2 = bidirectional_verified**。至此 **D 循环 5 个 canary（D1/D3/D6/D7 + D5）全部做实**；契约字段形态覆盖：单级表头（D1）、两级表头 nested 账龄（D3/D7）、两级表头 FLAT 账龄（D6）、两级表头无账龄普通列分组（D5）—— 四种形态都走通同一条 harness 无关双向路径。

> 未 commit（交收口方）。本轮新增/改动：sanitize_d5_template_external_links.py、phase5_d5_receivables_financing.py（新）、generate_phase5_d5_contract.py（新）、d5.receivables_financing_detail.json（新）、registry.py、workpaper_sync_entry_wp_code_adjudication.json、workpaper_sync_entry_overlay.json、workpaper_sync_entry_manifest.json、workpaperSyncManifest.generated.ts、oo_to_html.py、useD5FormData.ts、GtD5ReceivablesFinancing.vue、e2e/g5-1-d5-unified-path.spec.ts、evidence/g5-1-d5-unified-path/network-and-callback.json、D5 应收款项融资.xlsx（净化）+ .preclean.bak。

---

## 11. 【2026-09-12 评估】D4 主营业务收入 —— partial 可行性评估（**结论：技术可行但需一次专项设计，不纳入本轮 D 循环收口**）

> 本节是**只读评估**，未改任何生产代码 / 未发布 D4。目的：判断 D4 能否/是否值得复用 D1/D3/D5/D6/D7 的八步范式做实到 `bidirectional_verified`。

### 11.1 D4 与已做实的 5 个 canary 的三点结构性差异

| 维度 | D1/D3/D5/D6/D7（已做实） | **D4（待评估）** |
|---|---|---|
| store 行形态 | 每列一个 camelCase 字段（field-keyed，最多 nested 账龄段） | **`months[12]` 位置数组**（`{product, months:[m1..m12], auditAdjustment, ...}`），B~M 列由**数组下标**映射，不是字段名 |
| 模板 `[n]` 公式格 | 0（D3/D5/D6）或少量非受管 sheet（D7） | **270 个**（受管明细表 D4-2 的 N 列 = SUM(B:M) 逐行 + 其余 45 sheet 大量联动公式） |
| 模板规模 | 8–14 sheet | **46 sheet**（D4-2..D4-36 + 4 个「底稿目录 (n)」+ 附注/程序表），17 外链 |
| store 载荷现状 | 全空（空首版） | **D4-2-rows 有真载荷**（2 行 1739B：`产品×12月`矩阵）+ D4-3-rows/D4-4-rows 亦有 |

### 11.2 三条落地阻碍（技术可行，但不是「照抄八步」）

1. **数组下标映射 vs 字段键映射**：现有 5 个 canary 的契约 `json_pointer` 都是 `/rows/{uuid}/<字段名>`，一列一字段。D4-2 的 12 个月列是**同一个 `months` 数组的 12 个下标**（`/rows/{uuid}/months/0` .. `/months/11`）。契约 schema 与 `_resolve_json_path`/`_set_json_path` 支持路径分段，理论上 `months/0` 能走通，但**从未在任何 canary 验证过数组下标路径**（D3/D7 的 nested 是 dict 键 `agingPrior/within1`，不是 list index）。需要先确认 extract/materialize 两侧对「list index 作为 cell 映射」的往返等值——这是一个**未验证的新形态**，属专项设计+变异检验，不能想当然。
2. **270 个 `[n]` 公式格的净化**：sanitize 需中和受管/非受管 sheet 的外链公式。D4-2 的 N 列本身就是 `=SUM(B:M)` 合法内部公式（**不是外链**，不能删），而 270 个 `[n]` 里要精确区分「外链公式（删）」vs「内部 SUM（留）」——D7 只有 6 处 `[n]` 且都在非受管 sheet，D4 的净化爆破面大得多，受管 sheet 内极可能有需保留的内部公式，`_neutralize_external_formulas` 的「去 `<f>[n]</f>` 保 `<v>`」会误伤内部公式。需要**逐 sheet 核外链 vs 内部公式**，风险显著高于 D3/D5/D6。
3. **46 sheet + 有真载荷**：D4-2 有 2 行真实业务数据（产品×月矩阵），意味着首版发布**不是空 projection**——要正确 materialize 出 12 月矩阵到 B~M 列并 roundtrip 等值，比空首版复杂。且 D4 是全循环最重的底稿（35+ 子表），OO 加载/forcesave 的 settle 时间更长，e2e 稳定性风险更高。

### 11.3 结论与建议

- **结论：D4 技术上可做实到 bidirectional_verified，但不能复用现成八步照搬**——它需要①先验证「数组下标 cell 映射」这一新形态的 extract/materialize 往返等值（最好先在一个最小 fixture 上做 PBT），②一个比 D3/D5/D6 谨慎得多的净化脚本（区分 270 个公式格里的外链 vs 内部 SUM），③针对有真载荷 + 46 sheet 的 e2e 稳定性加固。工作量约为单个 D-canary 的 **2–3 倍**。
- **建议：D4 不纳入本轮 D 循环收口，单独立一个 spec（`d4-revenue-bidirectional`）承接**。本轮 D 循环已把「字段键行」的四种形态（单级/两级 nested 账龄/两级 FLAT 账龄/两级无账龄普通分组）全部验证到 bidirectional_verified，形成可复用范式；D4 的「位置数组行」是**第五种形态**，值得作为下一个专项 canary 单独验证「数组下标 cell 映射」这条通用能力（做实后可辐射所有 `months[]`/矩阵型底稿，如 I6-2/J1 月度分析/E1 现金交易月度等，价值高）。
- **优先级：中**。D4 有真实审计价值（营业收入是核心科目），但因其复杂度与「新形态未验证」，应在字段键范式稳定收口后、作为矩阵型范式的开路 canary 单独排期，而非塞进本轮批量。

> 本节纯评估，无生产代码改动、未发布 D4、未净化 D4 模板。
