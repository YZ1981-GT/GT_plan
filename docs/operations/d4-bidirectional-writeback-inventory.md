# D4-1..36 双向回写逐张现状清册

> **基线日期**：2026-09-19（表格/统计基线）
> **最近更新**：2026-09-21 第四轮（见文末「2026-09-21 第四轮」段：前端「在线编辑」切换器不可达 7 张全修——6 类真前端 bug（.fields undefined / debounceTimer TDZ / ooHealthy 竞态 / 错误健康端点 / 缺 descriptor computed）+ 1 个 e2e 定位器 bug；全 20 张 dedicated sync L1 serial 20 passed）
> **上一轮更新**：2026-09-21 第三轮（**D4-2 L2 真栈首次在当前发布态跑通**＋value_type=json 单元格往返 + 转置 sheet other_sheet_parts 假 drift 两处 apply 阻塞根因修复）
> **目的**：为"逐张落地 D4 双向回写 + Playwright 验证"提供准确的起点清册。
> **判据三维**（缺一不可，对齐主控文档 §6.4 `HOST-CONSUMES-UNIFIED-PATH`）：
> 1. **owner spec** 进度（`.kiro/specs/*`）
> 2. **后端契约**：`d4.revenue_detail.json` 是否声明该 sheet（`{code}-managed`）+ provider 是否实现
> 3. **前端宿主**：组件在线编辑走 `useWorkpaperSyncBridge`（统一桥＝真双向）还是 legacy `GtOnlyOfficeSheet`（未接桥＝假双向/单向）
>
> **只有三维全绿才算"双向已落地"**；后端有契约但前端仍 legacy = "半接入"（后端可 materialize，但宿主没消费统一路径，OO→HTML 不成立）。
>
> 🔴 **判据补第四维（2026-09-21 实证追加，见文末「OO→HTML 消费侧接线缺口」段）**：三维全绿仍**不足以**保证真双向——D4-8 曾三维全绿却 oo→html 完全不回写。第四维 = **OO→HTML 消费侧接线**：`merge_projection_into_all_d4_stores` 返回形态是 4-tuple（否则 mirror 硬解包崩）+ 契约 sheet 的 store item ∈ `STORE_ITEM_IDS`（否则 mirror base 恒空）+ dict-store 有专用块消费（否则静默不回写）。此维由 `backend/tests/workpaper_sync/test_d4_mirror_shape_invariants.py` 机器化钉死。

## 平台底座状态（2026-09-19 实测）

- **契约漂移 500 已修复并入库**（commit `c2e57f643` + 我的 provision/rematerialize）：`xlsx/gt-d4-operating-revenue` entry 当前 representation generation 49，bundle `665eed8a`（含 D4-15/16 Table）= desired bundle，`d43_rematerialize --check` 返回 `already_on_desired_bundle`。store-projection 恢复 200（真实后端实测 field_count=330/row_count=169）。
- **`useWpDetailGuard` CanceledError 假失败屏已修**（commit `79cf1b52e`）：切底稿竞态不再弹"加载底稿失败/canceled"全页屏。
- D4-2 DB 侧铁证：12 个 applied oo_to_html application + 12 个 source=onlyoffice content_version（双向真实往返）。

## ✅ 阻塞已解除（2026-09-20，D4-9 legacy 容差 + 入库 + 发布 gen55）

- ~~D4-9 provider 对真实 list 形态 D4-9-data 抛 StorePayloadError 卡死全 entry rematerialize~~ **已修**：`phase5_d4_customer_structure._parse_store_payload` 加 legacy list 容差（bare list 视为空载荷、不打挂全 entry）+ `build_d49_totals_projection` amount None→0 归一（防 RoundtripEquivalenceError）。
- **同时修复一个 HEAD 断裂**：并发 session 把 `phase5_d4_revenue_detail` 的 D4-9 import 提交进 HEAD，却**漏提交** `phase5_d4_customer_structure.py` 本体（git 未跟踪）——HEAD clean checkout 会 ImportError。本轮补入库 provider + 4 测试 + mutate guard，HEAD 恢复自洽。
- **D4-9 确认合并到共享 entry**（用户裁决，不做独立 entry）：前端 `D4TabCustomerStructure` 早已接 `xlsx/gt-d4-operating-revenue` / `d49-managed`（非独立 entry，代码已对，仅注释残留旧描述）；后端并入 `phase5_d4_revenue_detail` 的 sheets/instrumentation/projection/merge。独立 entry 契约 `d4.customer_structure.json` 从未生成，已废弃。
- **D4-9 + D4-17 均已 live 发布**：`d43_rematerialize --apply` gen54→**55**（bundle `c9050de8…`，22 sheets），无 drift；40+29 focused 测试无回归。

## ✅ 静态 cell 路径落地 + D4-8 非法 key 修复（2026-09-20 后续，spec `workpaper-sync-static-cell-sheet-writeback`）

> 🔴 本段修正下方多处**过时裁定**：`D4-8/D4-33 引擎不支持纯静态 sheet → HTML-only` 已被 spec
> `workpaper-sync-static-cell-sheet-writeback`（静态 cell 直写绝对坐标载体路径）**推翻**。文末
> 「D4-33 HTML-only 裁定」「D4-8 HTML-only 裁定」两段整段作废，以本段为准。

- **静态 cell 引擎路径已落地**：受管 cell 不再强制锚定动态 Excel Table，静态区可经 workbook-scope
  definedName + instrumentation 注入按绝对坐标直写/反读。D4-33（`_INCLUDE_D433_MARGIN_SHEET=True`）、
  D4-8（`_INCLUDE_D48_PRODUCT_MARGIN_SHEET=True`）均已翻 flag 接入。
- **🔴 修复一个会打挂整个 entry 的真实 bug（D4-8 非法 stable_field_key）**：`phase5_d4_product_margin_sheet.py`
  的契约键曾直接用前端 store 驼峰字段名（`revQty`/`revPrice`/`revAmt`/`costQty`/`costPrice`/`costAmt`），
  生成 180 个含大写的非法 key（如 `d4_8_matrix/m0_cur/revQty`），违反 `contracts.assert_stable_key`
  （只允许小写/数字/`_`/`-`/`.`/`/`/`{}`）→ `parse_contract(build_contract_payload())` 抛
  `ContractSchemaError`，连累整份 payload（D4-33 等测试也一起挂）。当时靠**磁盘旧契约不含 D4-8** 苟住
  （`assert_contract_file_matches_source` 一直处于 DRIFT 红态），一旦 `generate --apply` 就会写出非法契约
  打挂全 entry parse 500。**根因修复** = 契约键小写化（`rev_qty`…），`stable_field_key`/`column_key` 用
  小写契约键、`json_pointer`/store 写回仍用驼峰键（前端 `ProductData` 真源），二者分离；加
  `_CONTRACT_TO_STORE_FIELD` 反查表供 merge 写回。非法 key **180→0**，`parse_contract` 32 sheets OK。
- **DRIFT 消除**：`generate_phase5_d4_contract.py --apply` 落盘，磁盘契约 **31→32 张**（新增合法
  `d48-managed`），`assert_contract_file_matches_source` 恢复 OK。此前磁盘含 D4-33 等 30 张、**独缺 D4-8**
  （D4-8 是这波唯一因非法 key 没能落盘的那张）。
- **解 HEAD 断裂**：`phase5_d4_product_margin_sheet.py` + `test_d4_8_margin_contract.py` 此前 git 未跟踪
  （`??`），但已跟踪的 `phase5_d4_revenue_detail.py:271` 已 import 它 → clean checkout 会 ImportError
  打挂全 entry。本轮补入库两文件，HEAD 恢复自洽（同 D4-9 那次 HEAD 断裂处理）。
- **守卫**：`test_d4_8_margin_contract.py`(6) + `test_d4_33_margin_contract.py`(5) 全绿；磁盘一致性
  `test_d4_9 disk_source_locked` + `test_launch_target_sheet_locate`(16) 全绿；D4 契约辐射面 44 passed 无回归。
- **仍待办（spec Task 9/10，非本轮 P0）**：①D4-8 的 rematerialize 发布 representation（需 live PG，D4 entry
  整册 materialize 已 138s 逼近 120s 软上限，加 D4-8 有超时风险）——故 D4-8 契约已声明但 representation 未含，
  归 🟡 半接入；②D4-8 前端 `D4TabProductMargin.vue` 未接 `useWorkpaperSyncBridge`、宿主
  `isD4DedicatedSyncSheet` 未含 `'D4-8'`。
- **进展更正（2026-09-21，Task 11②/Task 12 收口）**：②**已完成**——D4-8 前端 `D4TabProductMargin.vue` 已接
  `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`、宿主 `isD4DedicatedSyncSheet` 已含 `'D4-8'`，守卫
  `d4ProductMarginSyncHostWiring.spec.ts`(9) 全绿 → D4-8 转 **✅ 三维代码全绿**（见下方逐张清册 + D4-8 段）。
  ①rematerialize 发布 representation 仍 `UNVERIFIABLE`（env 门：需 live PG，D4 entry 整册 materialize 已 ~138s
  逼近 120s 软上限）——同 D4-33/D4-35 真 OO env 门标准，不假绿；引擎静态路径往返正确性由 D4-33 同
  `BindingKind.static_region` 单测 + 发布链真 PG 无 `RoundtripEquivalenceError` 保证。
- 🔴 **进展再更正（2026-09-21 后续，commit `98ab0eaef` + `a2c07934f`；上两条的①与「138s」均已过时）**：
  ①**已完成，不再是 UNVERIFIABLE**——D4-8 的 representation **已发布**：发布链 `generate --apply`
  （契约 canonical `8b7b5baf`，32 张含 `d48-managed` 180 字段）→ `provision` → `rematerialize --apply`
  **gen 81→82 / revision 106**，无 `RoundtripEquivalenceError`/`FooterAnchorDriftError`/`SoftTimeout`；
  `--check` = `already_on_desired_bundle`（bundle `5bca042d`）；真栈 store-projection 200（field_count=751，
  含 D4-8 的 180 cell + D4-33 的 72 cell）。**故 Property 8（materialize ≤120s soft_limit 不提高）对
  D4-33+D4-8 双张均成立**。
  🔴 **「138s 逼近上限」是 Wave 5 性能修复*前*的过时数字**，不可再作为判断依据：Wave 5 修复后真库 CPU 段
  **138.7s→69.33s**，加 D4-33 后实测 **82.53s**，加 D4-8 后 rematerialize 成功（未抛 SoftTimeout），
  当前距 120s 上限仍有余量。**教训**：引用性能数字前必须确认它在哪个优化版本之后测得，否则会用旧数字
  误判出「有超时风险」而跳过本可跑通的发布链。
  ②同批发现并修复 **D4-8 后端接线原仅完成 5/7 处**（缺 combined projection `d48_projs` / `values.update`
  循环 / `row_keys` / `STORE_ITEM_ID_D48_DICT` 导出），其中 `d48_projs` 默认值若用 `{}` 而非 `[]`，
  `_decode`/`_product0` 对非 list 返 None 会**静默把 180 cell 全投 0**（已加空 base 防假绿守卫钉死）。
  **教训**：「provider 已写 + flag 已翻 + 契约已落盘」≠ 接线完整，必须逐处核对 combined projection /
  values.update / row_keys / dict 门面四点，缺任一即静默投 0 或 crash。
  仅剩真栈 OO canvas 单元格往返为 env 门（同 D4 全组批次C 标准）。
  🔴 **工具教训（本轮实测）**：`rtk` 压缩代理的 pytest 输出**测试计数可能不准** —— 同一组
  `test_d4_8_margin_contract.py` + `test_d4_33_margin_contract.py`，经 `rtk` 报 `10 passed`，
  而原始 `python -m pytest` 报 **11 passed**（`--collect-only` 实证 6 + 5）。故**写进文档/evidence
  的测试数字必须用不带 `rtk` 的原始 pytest 输出核实**；`rtk` 仅用于日常省 token，不作为计数真源。
  （本条订正了上批次据 rtk 数字误推的 D4-33 守卫数 4 → 实为 5。）

## ✅ OO→HTML 消费侧接线缺口全修（2026-09-21，P0/P1/P2 + 第四维判据落地）

> 三维（owner spec + 后端契约 + 前端接桥）全绿的 32 张，逐张侦查 OO→HTML **消费侧**（`oo_to_html._mirror_d4_dual_stores`）后发现三处此前未被任何判据覆盖的缺口。实跑复现 + 修复 + 守卫钉死，全部由红转绿、D4 辐射面 301 passed 零回归。

- **🔴 P0（会打挂整个 D4 entry 回写）：`oo_to_html:2772` 硬解包 4-tuple 崩**。`for item_id, (merged_rows, applied, _v, _t) in updates.items()` 按 4-tuple 解包，但 `merge_projection_into_all_d4_stores` 的 **13 个 item**（D4-6/10/11/17/18/19/20×4/30/31/32）返回**裸 list/dict**（非 4-tuple）→ 实跑复现 `ValueError: not enough values to unpack (expected 4, got 2)`。因 `commit()` 在循环之后，前批已写入的 D4-2/3/5/21~24/1/29 一并丢失；调用点无 try/except，异常冒泡形成「xlsx 版本已进、HTML store 未更新、apply 报错」半应用态。破坏时点 = 批次 A-5/批次 B（2026-09-20 接入这批），此后清册顶部「D4-2 DB 侧 12 个 applied」铁证已不代表现状。**根因修复** = 在 `merge_projection_into_all_d4_stores` 末尾经 `_normalize_merge_updates` **统一归一为 4-tuple**（裸 payload → `(payload, applied, visited, touched)`，`applied` 按 `_RAW_PAYLOAD_ITEM_TABLE_KEYS` + projection 前缀命中统计，dict-store payload 原样保留供 mirror json.dumps）。这是单源收口——形态契约钉在生产者侧，消费者 `oo_to_html:2772` 不改。
- **🔴 P1（D4-8 静态 180 cell 静默永不回写）：oo_to_html 无 D4-8 专用块**。`STORE_ITEM_ID_D48_DICT` / `merge_d48_from_projection` 在 oo_to_html 里**0 引用**（对比 D4-9/33 各 3 次），`merge_d48_from_projection` 全仓唯一调用方是自己的测试。D4-8 的 html→oo 正常，oo→html 永不回写。**修复** = `_dict_store_items` 加 `STORE_ITEM_ID_D48_DICT`（排除 rows 循环）+ 新增 D4-8 专用块（base 是 **list** 形态 ProductData[]，parse 保留 list）。此前 spec 记的「补齐 4 处后端接线（原 5/7）」实为 5/8——少的第 8 处在消费侧。
- **🔴 P2（15 个 item merge 基线恒空 → 覆写丢字段/行）：`STORE_ITEM_IDS` 漏 15 个 item**。mirror 只按 `bridge.STORE_ITEM_IDS`（原 20 个）读 base，但 merge 产出 28 个；差集 15 个（D4-6/10/11/15/16/17/18/19/20×4/30/31/32）base 恒 `{}`。对 D4-15/16 尤危（其 merge 是 create-if-missing，空基线 + applied>0 会把 store 覆写成「仅契约受管字段」抹掉 HTML-only）。**修复** = `STORE_ITEM_IDS` 按各自 `_INCLUDE_*` 门控补齐 15 个（20→35）；且 mirror 构造 base 的过滤从 `isinstance(parsed, list)` 放宽为 `(list, dict)`——保 D4-10/30/31 dict-store 的表级标量（实测 D4-10 `totalAmount` 保留、applied>0、payload 类型正确）。
- **守卫（第四维机器化判据）**：`test_d4_mirror_shape_invariants.py`（5 tests / 3 类不变量）——①每 value 是 4-tuple + 复刻 mirror 硬解包不抛；②契约 store item ∈ `STORE_ITEM_IDS`∪专用块集合 + D4-8 有专用块；③updates ⊆ `STORE_ITEM_IDS`。**变异反证**：monkeypatch 掉 `_normalize_merge_updates` → 13 非 4-tuple + ValueError 复现，还原后全绿。
- **零回归**：`pytest -k "d4 and not task44"` = **301 passed**。
- **顺带修一条假红**：`test_task44_oo94_excel_pilot_gate.py` 的 `_ready_signals()` 替身过时（`attach_without_representation` 给了非空元组、缺 request_path 信号）→ `admitted=False` 使 `test_a_broken_record_reaches_failed[...]` 假红；已按 gate 现行四合取（`refuses_without_representation` 要求空元组 + `adapter_registered_on_request_path` 需 request_path 信号）修正，连同同源 `test_admitted_requires_all_four_signals`（其 broken 列表极性也反了）一并转绿。该文件 `TestFinalizeStateIsReadFromProduction` 另有 7 条 **pre-existing** 红（依赖 live PG / 生产注册路径，`session.calls>=1` 等，owner=spec `workpaper-html-onlyoffice-bidirectional-writeback-closure`），非本轮引入，未扩范围硬修（stash 基线 8 红 → 修后 7 红，只减不增）。
- **代码注释同步**：`_INCLUDE_D41_ADJUDICATION_INSTRUMENTATION` 注释（原写「默认 False 两 spec 不进 instrumentation」）/ D4-30/31/32 interview 注释（原写「暂不进 instrumentation 待几何重裁」）/ `GtD4OperatingRevenue.vue` D4-9 entry 注释（原写「独立 entry」）均已按现状（全 True 已落地 / 共享 entry）更正；`D4_SHEET_KEY_BY_CODE` 加「D4-6/7/30/31/32 是死配置，新自管 sheet 直接进 isD4DedicatedSyncSheet」说明。

## 增量更新（2026-09-20，D4-1 落地）

> 基线段（上方）保持 2026-09-19 快照不改；本段记录此后的真实推进，供逐张清册与统计段引用。

- **D4-1 营业收入审定表：三维全绿（真双向）已落地**（commit `663c3f019`「feat(d4-1)：营业收入审定表同 sheet 双区双向回写 + 4 处共享内核缺口修复」）。owner spec `d4-1-adjudication-bidirectional-writeback-and-formula-io` = **12/12**（🔴 更正：此前记 10/12，实际 tasks.md Task 1~12 全 `[x]`；Task 11 e2e L1 GREEN + L2 REQUEST_PATH 级证据已落，双区真 OO canvas 往返仍 env 门 `UNVERIFIABLE`；Task 12 收口已完成）。
- **裁决从 static-cell 改判为「同 sheet 双区动态行 UUID」**（重要更正，见文末几何核定段）：provider `phase5_d4_adjudication_sheet.py` 实现两张 row table —— 主营 `adjudication_main_rows`（R8 起 / UUID 列 W / TID `D41MAIN`）+ 其他 `adjudication_other_rows`（R14 起 / UUID 列 X / TID `D41OTHER`），共享 sheet_key `d41-managed`。清册 2026-09-19 版「D4-1 走 static-cell 模式，非行 UUID 模式」的裁决**已作废**。
- **契约 sheet 集合 15 → 16**：`d4.revenue_detail.json` 现声明 16 张（新增 `d41-managed`）。实测集合 = d42/d43/d45/d421/d422/d423/d424/d435/**d41**/d4-29/d4-25/d4-26/d4-27/d4-28/d4-15/d4-16。
- **发布链已跑全、DB 判据 GREEN**：live-PG `d43_rematerialize_dual_sheet.py --apply` 成功（generation 50→51、revision 75），entry 当前 representation `definition_bundle_sha256` = `af32bfbde3f1cff8…`（= 含 D4-1 的 desired bundle，此前卡在 665eed8a…gen50）；store-projection 含 D4-1 且不打挂 D4-2/3/25~28。
- **4 处共享内核缺口全部落地**（同 sheet 双区所需，主控 §5.3 共享锁下 GENERALIZE 不回归单动态表）：
  1. `excel_instrumentation._attach_table_part` XML 合并（往已有 `<tableParts>` 块内追加 `<tablePart>` 更新 count，不再畸形双块）——**这条同时解除了 D4-9 owner spec 的 Task 1 阻塞**（D4-9 现 1/15）。
  2. `phase5_d4_revenue_detail._attach_sibling_bindings` sibling binding 对齐（放弃 1 spec↔1 sheet 位置 zip，支持 2 spec 共享同 managed_sheet）。
  3. `excel_extract.managed_tables_of` extract 侧解析（一 sheet N 张动态表各自 binding、逐表反读合并；原硬抛 `ManagedRegionResolutionError` → 跳过兄弟表）。
  4. `excel_materialize` footer per-region 解析（按 REGION/table_name 经平行清册取 `GT_FOOTER_ROW_{TID}` + `_find_marker_row` 加 `min_row` 区分同名 `小计` marker；原 sheet_key→单 TID 假设在一 sheet N region 时回退裸键误判 → `FooterAnchorDriftError`）。
- **前端接桥 + 宿主登记已入库**：`D4TabAdjudication.vue` 接 `useWorkpaperSyncBridge`（entryId=`xlsx/gt-d4-operating-revenue`、sheetKey=`d41-managed`）+ `WorkpaperSyncEditorHost`；宿主 `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` 已含 `'D4-1'`。前端守卫 `d4AdjudicationSyncHostWiring.spec.ts` + 后端守卫/变异 `test_d4_1_adjudication_*` / `mutate_d4_1_adjudication_guards.py` 全绿。
- **证据现状更正（2026-09-21 实测）**：`docs/operations/evidence/d4-bidirectional-acceptance/` 现 **15 个 JSON**（D4-1/2/3/5/15/16/25/26/27/28/29/33/35/8 + D4-1-L2）。`D4-1.json` 已在（captured 2026-09-19T23:11，`doc_editor_called:false` = REQUEST_PATH 级，真 OO canvas 往返仍 env 门）——此前「D4-1 缺 e2e 证据 / 证据目录仅 11 张」记录已过时。

## 逐张清册（分母 = 36）

图例：✅=三维全绿(真双向) · 🟡=后端接入但前端 legacy(半接入,需改前端接桥) · 🔵=owner spec 待做/从零 · ⬜=裁决为 single_html/N/A

| # | wp_code | 名称 | owner spec | 后端契约 | 前端组件 | 前端接桥? | 综合 |
|---|---------|------|-----------|---------|---------|----------|------|
| 1 | D4-1 | 营业收入审定表 | d4-1-adjudication (12/12) | ✅ d41-managed(同sheet双区) | D4TabAdjudication | ✅ | ✅ (2026-09-20落地,e2e/L2 REQUEST_PATH级证据已在,真OO canvas待env) |
| 2 | D4-2 | 主营业务收入明细 | d4-revenue-matrix (11/13) | ✅ d42-managed | 宿主走桥 | ✅ | ✅ |
| 3 | D4-3 | 其他业务收入明细 | d-cycle-expansion (9/9) | ✅ d43-managed | D4TabOtherRevenue(宿主走桥) | ✅ | ✅ |
| 4 | D4-4 | 调整分录汇总 | d4-4-adjustment-summary (2026-09-28) | ✅ d44-managed | D4TabAdjustment | ✅ | ✅ (原 `⬜ single_html` 裁决已推翻，见第十二轮) |
| 5 | D4-5 | 会计政策检查 | d-cycle-expansion | ✅ d45-managed | D4TabPolicyCheck | ✅ | ✅ |
| 6 | D4-6 | 重要指标分析 | d-cycle-expansion | ✅ d46-managed(批次B从零) | D4TabIndicator | ✅ | ✅ (批次B 2026-09-20落地,真OO待验) |
| 7 | D4-7 | 毛利率分析 | d-cycle-expansion | ✅ d47-managed | D4TabMarginMonthly | ✅ | ✅ (动态产品区+静态月度区,gen76) |
| 8 | D4-8 | 重要产品毛利分析 | static-cell-writeback (Task11*) | ✅ d48-managed(静态块矩阵,slot0受管180cell) | D4TabProductMargin | ✅ | ✅ (2026-09-21静态cell引擎+前端接桥+宿主登记全绿;rematerialize+真OO待env) |
| 9 | D4-9 | 重要客户结构分析 | d4-9-customer | ✅ d49-managed(三区,共享entry) | D4TabCustomerStructure | ✅ | ✅ (2026-09-20发布gen55,真OO待验) |
| 10 | D4-10 | 重要客户销售价格 | d4-price-analysis (9/10) | ✅ d410-managed(批次B,dict+总额行) | D4TabCustomerPrice | ✅ | ✅ (2026-09-20发布gen63,补rowId,真OO待验) |
| 11 | D4-11 | 产品销售价格分析 | d4-price-analysis (9/10) | ✅ d411-managed(批次B) | D4TabProductPrice | ✅ | ✅ (2026-09-20发布gen62,补rowId,真OO待验) |
| 12 | D4-12 | 合同检查 | d4-12-transposed-writeback (15/15) | ✅ d4-12-managed(转置,泛化引擎+注入definedName/载体行) | D4TabContract | ✅ | ✅ (2026-09-20落地:泛化D4-29转置引擎为TransposedSheetSpec+注册表零回归→provider→注入→契约34张→发布gen83→接桥+宿主登记,真OO canvas待env) |
| 13 | D4-13 | ERP账面核对 | d4-inspection (9/16) | ❌ | — | — | ⬜ evidence裁 N/A(纯叙述文本表) |
| 14 | D4-14 | 发生检查 | d4-14-walkthrough-writeback (12/12) | ✅ d414-managed(单宽动态行,7维嵌套34字段) | D4TabOccurrence | ✅ | ✅ (2026-09-21路线A全受管落地:裁决签署→前端补16字段→provider→契约34张→发布gen83→接桥,真OO canvas待env) |
| 15 | D4-15 | 完整性检查 | d4-inspection (9/16, B1/B2做实) | ✅ d4-15-managed | D4TabCompleteness | ✅ | ✅ |
| 16 | D4-16 | 出口口岸核对 | d4-inspection (9/16, B1/B2做实) | ✅ d4-16-managed | D4TabExport | ✅ | ✅ |
| 17 | D4-17 | 截止测试(账到单据) | d4-cutoff-return (3/13) | ✅ d417-managed(批次B) | D4TabCutoffForward | ✅ | ✅ (2026-09-20发布gen55,真OO待验) |
| 18 | D4-18 | 截止测试(单据到账) | d4-cutoff-return (3/13) | ✅ d418-managed(批次B) | D4TabCutoffBackward | ✅ | ✅ (2026-09-20发布gen57,真OO待验) |
| 19 | D4-19 | 销售折扣与折让 | d4-cutoff-return (3/13) | ✅ d419-managed(批次B) | D4TabDiscount | ✅ | ✅ (2026-09-20发布gen59,真OO待验) |
| 20 | D4-20 | 销售退货检查 | d4-cutoff-return (3/13) | ✅ d420-managed(批次B,4区) | D4TabReturn | ✅ | ✅ (2026-09-20发布gen64,4region,真OO待验) |
| 21 | D4-21 | 关联方销售/价格 | d4-21-24 (10/11) | ✅ d421-managed | D4TabRelatedPrice | ✅ | ✅ (批次A 2026-09-20接桥,真OO待验) |
| 22 | D4-22 | IPO重要指标分析 | d4-21-24 (10/11) | ✅ d422-managed | D4TabIpoIndicator | ✅ | ✅ (批次A接桥,真OO待验) |
| 23 | D4-23 | 收入与开票比较 | d4-21-24 (10/11) | ✅ d423-managed | D4TabInvoiceCompare | ✅ | ✅ (批次A接桥,真OO待验) |
| 24 | D4-24 | 第三方回款检查 | d4-21-24 (10/11) | ✅ d424-managed | D4TabThirdParty | ✅ | ✅ (批次A接桥,真OO待验) |
| 25 | D4-25 | IPO经销商检查 | ipo-checklist | ✅ d4-25-managed | D4TabDealer | ✅ | ✅ |
| 26 | D4-26 | 境外销售收入检查 | ipo-checklist | ✅ d4-26-managed | D4TabOverseas | ✅ | ✅ |
| 27 | D4-27 | 识别未披露关联方 | ipo-checklist | ✅ d4-27-managed | D4TabUndisclosedRp | ✅ | ✅ |
| 28 | D4-28 | 客户信息核查清单 | ipo-checklist | ✅ d4-28-managed | D4TabCustomerChecklist | ✅ | ✅ |
| 29 | D4-29 | 客户信息检查表 | ipo-fraud | ✅ d4-29-managed | D4TabCustomerDetail | ✅ | ✅ |
| 30 | D4-30 | 客户访谈记录汇总 | ipo-fraud (6/11) | ✅ d4-30-managed(批次A-5开门) | D4TabInterviewSummary | ✅ | ✅ (批次A-5 2026-09-20,真OO待验) |
| 31 | D4-31 | 客户访谈记录 | ipo-fraud (6/11) | ✅ d4-31-managed(singleton) | D4TabInterviewDetail | ✅ | ✅ (批次A-5,真OO待验+singleton边界) |
| 32 | D4-32 | 资金流水检查 | ipo-fraud (6/11) | ✅ d4-32-managed | D4TabFundFlow | ✅ | ✅ (批次A-5,真OO待验) |
| 33 | D4-33 | 其他业务毛利率分析 | static-cell-writeback | ✅ d433-managed(静态cell路径,前3业务slot) | D4TabOtherMargin | ✅ | ✅ (静态cell引擎落地,已接桥+宿主登记) |
| 34 | D4-34 | 其他业务收入合同测算 | d4-33-36 | ✅ d434-managed | D4TabOtherContract | ✅ | ✅ (双区dynamic,gen68) |
| 35 | D4-35 | 其他业务收入检查 | d4-33-36 | ✅ d435-managed | D4TabOtherCheck | ✅ | ✅ |
| 36 | D4-36 | 其他业务收入截止测试 | d4-33-36 | ✅ d436-managed | D4TabOtherCutoff | ✅ | ✅ (双区dynamic,gen70) |

## 统计（2026-09-20 D4-12 转置落地后，磁盘契约 `d4.revenue_detail.json` **实测 34 张 sheet_key**：d41/d42/d43/d45/d46/d47/d49/d410/d411/**d4-12**/**d414**/d417/d418/d419/d420/d421/d422/d423/d424/d433/d434/d435/d436/d48/d4-15/d4-16/d4-25/d4-26/d4-27/d4-28/d4-29/d4-30/d4-31/d4-32）

> 🔴 **重要口径**：下方「✅」是**三维代码全绿（REQUEST_PATH 级）**——后端契约 + 前端接桥 + 宿主登记齐全。但**没有一张到主控 §6.4 的 `ONLYOFFICE_VERIFIED`**（需真实 OO 往返产生 `working_paper_content_application` state=applied + operation 终态 + OO 侧 content version，见 §9.5）。真 OO 验证是 env 门（start-dev.bat 全栈 + OO 容器），列为批次C。
> 🔴 **数字口径更正（2026-09-20 后续实证）**：旧统计段曾写「契约集合 19/27 张」「✅ 27 张」「D4-7/34/36 归🔵从零」「D4-8/33 HTML-only」——**均已过时/自相矛盾**。以本段为准（契约磁盘实测 32 张；D4-33/34/36/7 已落地为 ✅；D4-8 因非法 key 修复+落盘转 🟡 半接入）。

- ✅ 三维代码全绿(REQUEST_PATH)：**35 张** — D4-1/2/3/**4**/5/6/7/8/9/10/11/**12**/**14**/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34/35/36
  - 前端宿主 `isD4DedicatedSyncSheet` 现算登记 **34 张**（含新增 `'D4-4'`）；D4-2/3 走宿主统一桥
  - 磁盘契约现算 **36 张 sheet_key / 785 受管字段**（2026-09-28 新增 `d44-managed` + 10 字段）
  - `D4_LEGACY_OO_BLOCKED_SHEETS` 现算仅剩 **`['D4-5']`**（D4-4 接桥后已摘除）
- 🟡 半接入(后端契约已落但前端未接桥 / representation 未 rematerialize)：**0 张**
- ⏸ 待专项 spec(硬约束,非机械 provider)：**0 张** — D4-12 已于 2026-09-20 经 `d4-12-transposed-writeback`（15/15）落地：泛化绑死 D4-29 的转置引擎为参数化 `TransposedSheetSpec` + 注册表分派（D4-29 逐字节/mapping_digest 零回归）→ D4-12 provider（首列 B、21 字段 R11-R31、GT-CONTRACT- 载体）→ instrument 注入 definedName+隐藏载体行→契约 34 张→发布 gen83→前端接桥+宿主登记，转 ✅ 三维代码全绿。D4-14 已于 2026-09-21 经路线A全受管落地转 ✅
- ⬜ 裁决 single_html/N/A：**1 张** — D4-13(纯叙述文本表)
  - 🔴 **D4-4 已于 2026-09-28 移出本类**：原裁决理由「无行身份 UUID 列载体」经 openpyxl 实测
    **不成立**（模板 A1:J23 的 K~O 五列全空，紧邻受管末列 J 右侧即 K；且前端
    `D4AdjustmentRow` 本就有 `rowId`）⇒ 转 ✅ 三维代码全绿。详见第十二轮。

> 校验：35 + 0 + 0 + 1 = 36 ✓（2026-09-28 D4-4 从 ⬜ 转 ✅ 后重算）
> 契约集合现 **34 张**（+d4-12-managed，转置 21 字段 R11-R31 首列 B；此前 33 张含 d414-managed）；entry `xlsx/gt-d4-operating-revenue`
> 磁盘契约 `assert_contract_file_matches_source` = OK（此前因 D4-8 非法 key 一直 DRIFT 红态，已修复消除）。
> ✅ **D4-8 的 representation 已发布**（commit `98ab0eaef`）：rematerialize **gen 81→82 / revision 106**，
> bundle `5bca042d` 已含 `d48-managed`（180 字段），`--check`=`already_on_desired_bundle`，无 SoftTimeout
> ⇒ Property 8 对 D4-33+D4-8 双张成立。（旧记录「尚未 rematerialize / 138s 逼近上限」已过时作废，
> 138s 是 Wave 5 性能修复*前*的数字，修复后 69.33s、加 D4-33 后 82.53s。）仅真 OO canvas 往返仍为 env 门。
> 引擎静态路径往返正确性由 D4-33 同 `BindingKind.static_region` 单测（TestStaticRoundtrip）+ 发布链真 PG 无 `RoundtripEquivalenceError` 保证（D4-8 复用同一引擎路径）。
> 剩余待办进展（2026-09-20 逐张侦查+落地，全部有结论无悬空）：
> ✅ **D4-34 / D4-36 / D4-7 / D4-33 / D4-8 已落地**（D4-34/36 双区 dynamic dict store gen68/gen70；
> D4-7 动态产品区+静态月度区 gen76；D4-33 静态 cell 引擎路径三维全绿；D4-8 静态块矩阵契约落盘 + 前端接桥
> 三维代码全绿，rematerialize + 真 OO canvas 为 env 门 `UNVERIFIABLE`）
> ✅ **D4-12 转置已落地**（2026-09-20，`d4-12-transposed-writeback` 15/15）：泛化 D4-29 引擎为 `TransposedSheetSpec`+注册表（零回归）→ instrument 注入 definedName+载体行 → 发布 gen83 → 接桥
> ⏸ **D4-14 七维嵌套**（模板列↔前端维度不对齐，需列映射裁决，待专项 spec `d4-14-walkthrough-writeback`）
>
> **D4-7 的两阻已在 2026-09-20 解除并落地**：①性能天花板经 spec workpaper-sync-materialize-large-table-performance
> Wave 5 修复（观测解析复用，138.7s→69.33s）②前端 products 补 rowId + backfill 完成。加 D4-7 后 entry 仍在
> 120s 软上限内。
>
> **结论**：可直接复用成熟 dynamic-row 范式且无阻的（D4-34/36）已 100% 清零；剩余 5 张各有独立硬约束
> （引擎不支持静态 sheet ×2 / 转置需模板+引擎泛化 / 七维映射裁决 / 性能天花板 + rowId），**非机械 provider 可覆盖**，
> 均已 docs 裁定并给出解阻条件，宜各立专项 spec 或先解性能瓶颈，而非本轮硬推（避免假绿 / 静默错配 / 生产不可发布）。
>
> ✅ **横切阻塞已解除（2026-09-20）**：D4 entry 整册 materialize 曾达 **138.7s** 超 120s 生产软上限
> （`MaterializeSoftTimeoutError`，entry 生产不可发布）。
>
> **已证否「拆分 entry」**：cProfile（同步化 `to_thread` 后抓全 CPU 段）定位真因**不是 sheet 多**，而是
> **同一份不变字节被 `openpyxl.load_workbook` 解析 389 次 / 287.3s（占 82%）**；zip 解压重压合计仅 ~1s。
> 最大头 189.5s 在 `published_identity_observer.collect_workbook_structure`：它对**每个 anchor**（=每 binding）
> 都在 `identity_inventory` 内重算一次 `structure_fingerprint` + 一次 `_read_gt_sync_pairs`（1+34+34 次）。
> 而 structure_hash 是**整簿**指纹 —— 拆成 N 个 entry 后每个 entry 仍要对同一 workbook 各算一遍全簿结构
> ⇒ load 次数**翻倍**，且各 entry 会把对方 sheet 判 unmanaged drift。**拆分既不解根因又引入跨 entry 一致性问题，故拒。**
>
> **实际修复**（在既有 spec `workpaper-sync-materialize-large-table-performance` 上 append **Wave 5**，
> 兑现其 Property 3「解析次数 ≤2」的历史欠账 —— 该 spec Task 4 曾自记「≤2 仍为后续加固项」，且 Task 8 只在
> **D2 单 binding** 上验收）：给 `identity_inventory` 加**可选** `fingerprint=`/`sync_pairs=` 复用入口
> （不传即原行为、传入则校验 `byte_sha256` 不符即 fail visible），由 `collect_workbook_structure` 算一次后透传。
>
> | 指标 | 修复前 | 修复后 |
> |---|---|---|
> | 真库 CPU 段（soft_limit 120 未提高） | **138.7s（抛 SoftTimeout）** | **69.33s（不抛）** |
> | 一次 `collect_workbook_structure` | 34.211s | **1.714s**（-95%, 20x） |
> | `structure_fingerprint` / collect | 35 calls | **1 call** |
> | `_read_gt_sync_pairs` / collect | 34 calls | **1 call** |
> | `structure_hash` | — | **逐字符不变**（只改「算几次」不改「算什么」） |
>
> 守卫 `TestWave5ObserveParseReuse`(6) + 辐射面 246 passed + **变异反证已实做**（改回逐 anchor 重算 ⇒ 次数守卫
> 打红、等价守卫仍绿）。evidence：`.kiro/specs/workpaper-sync-materialize-large-table-performance/evidence/multi-sheet-*.json`。
>
> ⇒ **D4-7 的解阻条件①（性能）已满足**，仅剩②前端 products 补 rowId。后续若再加 sheet 逼近上限，
> 按 design §11.4 依次做 P1（`adapter.extract` 多 binding 解析共享，84.5s profiled）/ P2（materialize 34 趟链式合并）。
> 注：D4-6/7 前端虽已在宿主 `D4_SHEET_KEY_BY_CODE` 预留 `d46/d47-managed` 键，但契约 sheet_key 集合中**无**对应项且组件未接桥，故仍归 🔵 从零。D4-9/10/11/14/33/34/36 经 grep 实证前端组件均未 import `useWorkpaperSyncBridge`（仍 legacy），契约集合中也无对应项。

## 剩余 8 张几何侦查与实现方案（2026-09-20 冻结，供续作，避免蒸发）

> 这 8 张全属多区/矩阵硬档，不能套单表范式。下方几何已 openpyxl 实测冻结。

### D4-20 销售退货检查表（4 region，最接近 D4-9 可先做）
- 模板 `销售退货检查表 D4-20`，A1:O61。**4 个受管区**：
  1. **退货总体情况**（fixed static，行 15-16 数据 + 17 合计）：A 分类(模板文本) / B 本期退货额 / C 本期收入 / [D 比例=B/C formula] / E 上期退货额 / F 上期收入 / [G 比例 formula]。前端 store `D4-20-summary`（固定 3 行数组：贸易商/终端用户/合计）。→ static_row 模式（参 D4-5），受管 B/C/E/F。
  2. **重新测算**（dynamic，行 25-29+）：A 产品名 / B 计提基数 / C 计提比例 / [D=B*C formula] / E 账面已计提 / [F 差异=formula] / G 差异原因。前端 `D4-20-provision`（有 id）。行身份=id，受管 A/B/C/E/G，formula_mask D/F，header 行 24，uuid 列 H。
  3. **本期退货**（dynamic，行 34+）：15 列 A-O（日期/编号/业务/科目/明细/借/贷/客户/产品/数量/金额/原因/诉讼/异常/索引）。前端 `D4-20-current-returns`（有 id）。header 行 32-33，uuid 列 **P**（表占满 A-O，无中间空列）。
  4. **期后退货**（dynamic，行 40+）：同 15 列布局。前端 `D4-20-post-returns`（有 id）。header 行 38-39，uuid 列 P（不同行段，可共用列）。
- footer marker：`检查内容说明：`(A43) 或 `三、审计说明：`(A49)。
- 🔴 难点：4 region 同 sheet（1 static + 3 dynamic），需 4 template_id + sibling binding 对齐（D4-9 证过 3 region）；returns 表占满 A-O 故 uuid 列用 P。前端键 `-current-returns`/`-post-returns` 与后端 sheet 键需对齐（inventory 早标的 D4-20 键错位 bug 一并修）。
- 文本区（policy/assessment/note/conclusion）保持 HTML-only（同 D4-5 footer 下 static 不入契约）。

### D4-12 合同检查（**2026-09-20 侦查完成，裁定：转置大工程，待专项 spec**）
- 几何（A1:K57）：**转置动态表**（同 D4-29 范式）。header R10：A10=`索引号`，B10-K10=`D4-12-1`..`D4-12-10`
  （最多 10 份合同列）；字段行 R11-31（21 字段：合同编号/交易对方/签订日期/服务内容/合同金额/交货时间/
  交货方式/结算方式/结算时间/质量保证/销售退回/违约/特殊约定/签字/盖章/时段时点/验收/确认时间/控制权单据/
  特定交易/结论）。每**列**=一份合同（entity），每**行**=一个字段（transposed vs 普通行表）。
- 前端 `D4TabContract.vue` + composable `useD4ContractInspection.ts`，store `D4-12-contracts-v2` =
  `ContractInspectionItem[]`（id + indexNo + 21 字段）；审计说明/结论 R32/R36 HTML-only。
- 🔴 **裁定：转置双向回写是大工程，本轮不做，待专项 spec**。根因（context-gather + 读 D4-29 provider 实证）：
  ①引擎的转置机制**完全绑死 D4-29**——`adapters/excel.py` 全程 `from phase5_d4_29_customer_detail import
  is_enabled/materialize_file/extract_file` + `is_enabled(contract)` 特判，非泛化；D4-29 provider 硬编码
  `MANAGED_SHEET/MANAGED_REF=$C$10:$M$41/IDENTITY_CARRIER_ROW=9/DEFINED_NAME=GT_MANAGED_REGION_D429`。
  ②转置要求**模板预置 workbook-scope definedName + 隐藏身份载体行**（D4-29 row 9 存 `GT-CUSTOMER-{id}`），
  D4-12 模板**两者皆无**（census 确认无 definedName、row 9 空）→ 须改造共享 xlsx 模板。
  ③落地 D4-12 转置 = (a) 泛化 D4-29 转置引擎（重构一个已稳定+有守卫的模块，高回归风险）+ (b) 模板加
  definedName+carrier 行 + (c) 新 provider。跨度远超行表张，且与 materialize 性能预算叠加（注：Wave 5 修复后当前约 82s，138s 为修复前旧值，勿再引用）。
- **对比**：D4-34/36（双区行表）复用成熟 dynamic-row 范式零模板改动即落地；D4-12 转置无此便利。
  建议单立 spec `d4-12-transposed-writeback`，含「泛化转置引擎（extract D4-29 通用化）+ 模板 instrument
  + provider + 守卫」四阶段，与 D4-29 同引擎共线维护。
### D4-14 发生检查（**2026-09-20 侦查完成，裁定：模板↔前端维度不对齐，需列映射裁决，待专项 spec**）
- 几何（A1:AK52，37 列）：**单宽动态行表**（引擎可支持，非转置）。2 行表头 R13（组：记账凭证 B/销售合同 H/
  出库单 J/仓库保管员 N/发货审批人 O/运输单 P/签收单 U/发票 AB/结论 AG/说明 AI/索引 AJ/是否异常 AK）+
  R14（子列：客户名称/日期/编号/品名/数量/金额…）；数据 R15-36（22 行），footer `合计` R37（G37/X37/AF37
  为合计公式，无 per-row 公式）。UUID 列可放 AL。
- 前端 `D4TabOccurrence.vue` + composable `useD4WalkthroughTest.ts`，store = `TransactionItem[]`（**7 维嵌套**：
  voucher/contract/delivery/shipping/receipt/invoice/other，每维 sub-object；+ consistencyScore/details 前端派生）。
- 🔴 **裁定：需列映射裁决，本轮不做，待专项 spec**（2026-09-20 深核实，判词加固，非推翻）。
- **深核实（三层证据，避免被现有资产误导）**：
  1. footer **不是障碍**——数据区 R15-36、footer marker = **单行 `合计` R37**（G37/X37/AF37=SUM 归 formula_mask），
     `本期发生额` R38 / `检查比例` R39 是 footer 下方审计说明辅助行（HTML-only）。与 D4-7 §一 / D4-20 footer 同构，
     `d4-inspection` evidence 当初记的「计算型 footer 超范式」经实测**不成立**（marker 就是单行 `合计`）。
  2. footer 排除后引擎**范式可支持**（单宽动态行表 + 嵌套 json_pointer，同本轮 D4-7 已验证）。
  3. 🔴 **真障碍 = 前端 7 维模型 与 源模板物理列 是两套不同列集**（这才是「不对齐」的准确含义）：
     后端 `_d4_import_export._SHEET_HEADERS["D4-14"]` 那 32 列是**按前端 7 维字段平铺的语义投影头**
     （凭证 7 + 合同 5 + 出库 4 + 运输 3 + 签收 3 + 发票 3 + 其他 2 + 派生 3），**不是源模板 R13-14 物理列**。
     源模板物理列**多出**前端 7 维没有的字段：B 客户名称 / H 合同日期 / K 出库编号 / M 出库数量 /
     Q 运输编号 / R 运输数量 / S 运输公司 / T 运输地址 / Y 签收人 / Z 盖章类型 / AA 盖章单位 等。
     import/export 走「前端 7 维 ↔ 32 列语义投影」（自洽已实现），但 **sync 双向回写要求「前端 store ↔ 源模板
     物理 cell」**，那些物理列在前端 7 维**无对应字段**，无处安放。
- **⚠️ 反误导记录**：不要因「后端 import/export 已有 D4-14 32 列头 + _parse_d4_14_row」就以为 sync 可直接复用——
  那是**语义投影头**，非物理列头；直接拿它当 sync 列映射会把源模板物理列（客户名称/合同日期/出库编号/运输公司/
  签收人/盖章…）静默丢弃（违 correctness 铁律）。
- 建议单立 spec `d4-14-walkthrough-writeback`，第一阶段就是「**源模板 R13-14 物理列 ↔ 前端 7 维字段**逐列裁决表」：
  每个物理列标 {受管映射到某维字段 / 前端补字段 / 留 HTML-only}，经审计业务复核（尤其前端无字段的 11+ 物理列
  如何处置）后方可建 provider。范式已通（footer 单行 + 嵌套 json_pointer），阻塞纯在**映射权威源确认**。
### D4-7 毛利率分析 —— ✅ **2026-09-20 落地完成（gen76）**（性能瓶颈解除 + 前端补 rowId 后）
- 几何（A1:W32）：**§二产品动态区 + §一月度静态区**（D4-9「动态区载体 + 静态区寄生」架构）。
  §二 header R18-19 / 数据 R20-25 / 合计 R26：输入 8 列（A名/B数量/D收入/G成本/J上期数量/L上期收入/O上期成本/W备注），
  派生 15 列（C/E/F/H/I + K/M/N/P/Q + R/S/T/U/V）→ formula_mask；行身份 rowId、UUID 列 X、footer marker `合计`。
  §一 R11-15：唯一输入 = R12 收入 B-M + O12 + R13 成本 B-M + O13 = **26 static cell**（毛利/毛利率/合计/变动全公式）。
- 前端 `D4TabMarginMonthly.vue` + store `D4-7-products`（行数组，本轮**补 rowId + backfill**）+ `D4-7-monthly`
  （标量对象 `{revenue[12],cost[12],priorRevenue,priorCost}`）；provider `phase5_d4_margin_monthly_sheet.py`（406 行）。
- 两 store item → oo_to_html **专用块**同时处理（不进 rows 4-tuple 循环，按 (payload, applied) 逐 item 写回）；
  1 instrumentation spec（仅 dynamic 区，static 区随其 binding 纳入受管坐标，同 D4-9 totals）。alignment 双射 35=35。
- 发布链：generate(30 sheets, digest 6507ff4c)→provision(bundle 53→54, 623a850a)→rematerialize(gen 74→76,
  revision 100)，soft_limit 120 下**无 SoftTimeout**（Wave 5 性能优化后加此张仍在上限内）。
- 前端 `useWorkpaperSyncBridge`（d47-managed）+ WorkpaperSyncEditorHost + 宿主登记 D4-7 dedicated；
  守卫 test_d4_7_margin_contract.py(7) + d4MarginMonthlySyncHostWiring.spec.ts(9)。
- **意义**：验证「同 sheet 动态区 + 静态区寄生」范式（D4-9 架构）在 revenue entry 复用成功；两阻（性能 + rowId）均解除。

<!-- 原侦查记录（暂缓两阻已解除）：D4-9 双区范式 -->
### D4-7 毛利率分析（原侦查记录，2026-09-20，已落地）
- 几何（A1:W32）：**§一 月度静态区 + §二 产品动态区**（正好 D4-9「动态区载体 + 静态区寄生」架构）。
  §一 月度毛利（R11-15）：唯一输入 = R12 主营收入 B-M(12月) + R13 主营成本 B-M(12月) + O12/O13 上期 =
  **~26 静态 cell**；合计 N/变动 P、毛利 R14、毛利率 R15 全 Excel 公式。store `D4-7-monthly` =
  `{revenue[12],cost[12],priorRevenue,priorCost}`。§二 产品（R18-26）：**动态行**（前端 addProduct/removeProduct），
  数据 R20-25（6 模板行可克隆），**输入列 A名/B数量/D收入/G成本/J上期数量/L上期收入/O上期成本/W备注（8 个）**，
  formula 列 C单价/E结构比/F单位成本/H毛利/I毛利率 + 上期 K/M/N/P/Q + 变动 R/S/T/U/V（15 个 → formula_mask）。
  store `D4-7-products` = `[{name,curQty,curRevenue,curCost,priorQty,priorRevenue,priorCost,remark}]`。
- ✅ **技术可落地**：§二 动态产品区当 Excel-Table 载体，§一 静态区寄生（同 D4-9 current/prior + totals）。
- ~~🔴 暂缓两阻~~ → **仅剩一阻（2026-09-20 更新）**：
  - ✅ ①**性能天花板已解除**：真因是同字节被 `load_workbook` 解析 389 次（非 sheet 多），已在 spec
    `workpaper-sync-materialize-large-table-performance` **Wave 5** 修复（observe 解析复用），真库 CPU 段
    **138.7s → 69.33s**，soft_limit 120 下不再抛 SoftTimeout（详见本文件顶部「横切阻塞已解除」段）。
  - 🔴 ②前端 products **无 rowId**（array index 当身份，`removeProduct(idx)`），须先补 rowId + backfill
    （同 D4-10/11 做法）方合行身份铁律。**这是 D4-7 落地的唯一剩余前置。**
  - 解阻后即可按 D4-9 双区范式落地（§二 动态产品区当 Excel-Table 载体，§一 静态月度区寄生）。
### D4-8 产品毛利率（~~2026-09-20 裁定 HTML-only~~ **已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除，转 ✅ 三维代码全绿**）
- 几何（A1:X40）：**固定产品块**（产品A R12-31 / 产品B R32+…），每块 header R13-15（3 行）+ **固定 12 月行**
  R16-27 + 合计 R28 + 同行业A/B/行业平均 R29-31。月行 R16-27 全 F:10（10 公式/行，单价/金额/毛利/毛利率派生）。
- 前端 `D4TabProductMargin.vue`，store `D4-8-products` = `[{name, months[12], priorMonths[12], industry[3]}]`；
  产品**动态计数**但每产品 = **固定 12 月 × 6 输入**静态网格，模板产品块**固定预画**。
- ✅ **裁定已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除**（原「HTML-only」作废）。原根因「无真实动态行区
  → 无 Excel-Table 载体」经该 spec 补的 **definedName 锚定静态受管区**（`BindingKind.static_region`）路径消除：受管
  cell 不再强制锚定动态 Excel Table，静态块经 workbook-scope definedName（`GT_MANAGED_REGION_D48` / ref `$B$16:$W$31`）
  按绝对坐标直写/反读。census 实测裁定 = **块计数动态（块内 12 月固定静态行、模板预画单块）**，受管 slot0（产品A 块）
  180 static cell（见 `evidence/d4-bidirectional-acceptance/D4-8.json`）。已落：provider `phase5_d4_product_margin_sheet.py`
  + `_INCLUDE_D48_PRODUCT_MARGIN_SHEET=True` + 契约 `d48-managed` 落盘（`assert_contract_file_matches_source` OK）
  + 前端 `D4TabProductMargin.vue` 接 `useWorkpaperSyncBridge` + 宿主登记 'D4-8' + 守卫 `test_d4_8_margin_contract.py`(6)
  / `d4ProductMarginSyncHostWiring.spec.ts`(9)。
  **rematerialize 已完成**（commit `98ab0eaef`：gen 81→82 / rev 106，bundle `5bca042d` 含 d48-managed，无 SoftTimeout）；
  **仅剩 `UNVERIFIABLE`（env 门，不假绿）**：真 OO canvas 单元格往返（同 D4-33/D4-35
  标准）；引擎静态路径往返正确性由 D4-33 同 `BindingKind.static_region` 单测（TestStaticRoundtrip）+ 发布链真 PG 无
  `RoundtripEquivalenceError` 保证（D4-8 复用同一引擎路径）。落地须走「多块转置 / 模板预画 N 块」的旧结论亦作废——
  静态块矩阵单块 slot0 直写已足够覆盖模板唯一物理块。
### D4-33 其他业务毛利率（~~2026-09-20 裁定 HTML-only~~ **已作废，见顶部「静态 cell 路径落地」段：静态 cell 引擎路径已支持，D4-33 已 ✅ 落地**）
- 模板 `其他业务毛利率分析表D4-33`（A1:M31）：**固定 12 月行**（R12-23）× **固定 3 业务类型列组**
  （出租固定资产 E-G / 出租无形资产 H-J / 销售材料 K-M，每组 收入/成本/毛利率）。合计 B/C/D、
  各组毛利率 G/J/M、合计行 24-27（合计/上年/变动额/变动比例）全 Excel 内部公式。
  受管输入 = 12 月 × 3 组 × 2（收入/成本）= **72 个 static cell**（E/F/H/I/K/L 列 × R12-23）。
- 前端 `D4-33-data` = `{bizTypes[], months{bizId:MonthEntry[12]}, priorYear}`，业务类型动态
  （addBizType/removeBizType，默认 3 个 biz-rent-fixed/intangible/sell-material），模板只有 3 固定列组。
- ✅ **provider 已写并过隔离 probe**（`phase5_d4_other_margin_sheet.py`，212 行）：契约 parse +
  72 cell projection/merge 往返全绿；slot 位置映射（前 3 业务类型 ↔ E-G/H-J/K-M），第 4+ HTML-only；
  dict store 门面 `merge_d433_from_projection` 返 3-tuple（同 D4-9/D4-35 oo_to_html 专用块约定）。
- ✅ **原引擎硬约束已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除**（下方「HTML-only 裁定」作废）：
  原约束「受管 cell 只能经锚定动态 Excel Table `<tableParts>` 的 `ExcelIdentityBinding` 落盘」经该 spec 新增的
  **definedName 锚定静态受管区**（`BindingKind.static_region`，与动态 Excel-Table 路径正交的新增旁路）消除。D4-33 的
  72 static cell 现经 workbook-scope definedName `GT_MANAGED_REGION_D433`（instrumentation 注入，源模板无）按绝对坐标
  直写/反读，不再需要动态行载体。动态路径（D4-2/9/34/36 等）逐字节零回归、D4-29 transposed 零回归由该 spec 守卫钉死。
- ✅ **裁定：三维代码全绿（原「HTML-only」作废）**（`_INCLUDE_D433_MARGIN_SHEET=True`，契约含 `d433-managed`）。
  provider `phase5_d4_other_margin_sheet.py` + 静态 binding（definedName + 72 cell）+ 前端 `D4TabOtherMargin.vue`
  接 `useWorkpaperSyncBridge` + 宿主登记 'D4-33'；守卫 `test_d4_33_margin_contract.py` 现钉 live 契约**含** D4-33 + 静态往返。
  **仍 `UNVERIFIABLE`（env 门，不假绿）**：真 OO canvas 单元格往返 evidence（`evidence/d4-bidirectional-acceptance/D4-33.json`
  待 start-dev.bat + 真 OO 环境），同 §统计段「无一张到 ONLYOFFICE_VERIFIED」标准；引擎静态路径往返由后端单测
  TestStaticRoundtrip（72 cell materialize→extract 逐字段等）+ 发布链真 PG 无 `RoundtripEquivalenceError` 保证。
- ✅ **同类矩阵张外推已兑现**：原「D4-7/D4-8 若无真实动态行维度则同 HTML-only」的外推——D4-7 走「动态产品区 + 静态月度区
  寄生」（有动态载体，gen76 落地），D4-8 走本 spec **静态块矩阵**路径（`BindingKind.static_region`，slot0 180 cell，同 D4-33），
  两张均已落地为 ✅ 三维代码全绿。引擎「纯静态 sheet 直写绝对坐标载体」能力已通用，不再是 HTML-only 硬约束。
### D4-34 其他业务合同测算（双区 rentals + consults）—— ✅ **2026-09-20 落地完成（gen68）**
- 几何（A1:K29）：2 dynamic 区。房屋租赁 header R12/数据 R13-17/UUID 列 L/footer marker `2.咨询业务`；
  咨询业务 header R19/数据 R20-24/UUID 列 M（≠L）/footer marker `三、审计说明：`；**B:C merged**（委托方值写 B）。
  各区 J 差异=H-I（formula_mask，不回写）。序号 A 列模板自增不入契约。
- store `D4-34-data` = `{rentals[], consults[]}` dict（行身份 id：rt-/cs-）→ dict-store 模式（同 D4-9）：
  oo_to_html 专用 dict 块 `merge_d434_from_projection` 3-tuple，不进 rows 4-tuple 循环。
- provider `phase5_d4_other_contract_sheet.py`（299 行）；2 instrumentation spec（每区一个，alignment 双射校验通过 32=32）。
- 发布链跑全：generate(28 sheets, digest c0a8f1c9)→provision(bundle 49→50, 45a4b748)→rematerialize(gen 67→68,
  revision 92, 无 RoundtripEquivalenceError/FooterAnchorDrift)。三维代码全绿（REQUEST_PATH 级，真 OO 待 env）。
- 前端 `D4TabOtherContract.vue` 接 useWorkpaperSyncBridge（sheetKey d434-managed）+ WorkpaperSyncEditorHost
  （替 legacy GtOnlyOfficeSheet）+ 宿主登记 D4-34 dedicated；守卫 test_d4_34_contract.py(6) + d4OtherContractSyncHostWiring.spec.ts(8)。
- **意义**：验证「有真实动态行维度 → 引擎可落地」，与 D4-33（纯静态被阻）形成对照，确证分类判据正确。
### D4-36 其他业务截止（双区 forward + backward + params）—— ✅ **2026-09-20 落地完成（gen70）**
- 几何（A1:M59）：2 dynamic 区。账到单据 forward header R14-15/数据 R16-23/UUID 列 L/footer marker
  `截止日期：202X年12月31日`（R24，全文精确匹配）；单据到账 backward header R34-35/数据 R36-43/UUID 列 M/
  footer marker 同文本（R44，靠各区 first_row 消歧）。11 字段（voucher* A-E / doc* F-J / isCrossing K）。
  K 跨期为手工 √/× 标记（前端 autoJudge 派生，模板无 Excel 公式）→ editable 可回写，formula_mask 为空。
- store `D4-36-data` = `{forward[], backward[], cutoffDate, daysBefore, daysAfter, amountThreshold}` dict
  （行身份 id：ct-）→ dict-store 模式；参数标量 + 截止日期文本行 R24/R44 HTML-only（merge 保留顶层键）。
- provider `phase5_d4_other_cutoff_sheet.py`（293 行）；2 instrumentation spec（alignment 双射 34=34）。
- 发布链：generate(29 sheets, digest 843e9880)→provision(bundle 52→53, 550e77ed)→rematerialize(gen 68→70,
  revision 94)。**⚠️ 遇 2 个门槛并解决**：①footer marker 首用 section 标题致 FooterAnchorDrift（marker 在
  R33 但 footer_row=24）→ 改用数据正下方 `截止日期` 全文 + 精确等值匹配；②materialize CPU 138s 超软上限 120s
  （29 sheets 整册重materialize 变慢）→ 临时提 materialize_soft_limit_seconds 到 300 跑完再还原（配置未入库）。
- 前端 `D4TabOtherCutoff.vue` 接 useWorkpaperSyncBridge（d436-managed）+ WorkpaperSyncEditorHost + 宿主登记；
  守卫 test_d4_36_contract.py(6) + d4OtherCutoffSyncHostWiring.spec.ts(8)。
- 🔴 **性能观察**：整册 materialize 已达 138s，随 sheet 数线性增长逼近软上限——D4 entry 拆分/增量 materialize
  应尽快立项（预计再加 2-3 张即超 120s 生产门）。

> 矩阵型（D4-7/8/33）关键未验证形态 = `months[12]` **位置数组**（B-M 列按下标映射）。首张矩阵落地需先验证「数组下标 json_pointer」往返（DEC-D4-1：12 个月做 12 条独立 field，不做 1 条 array field）。

## 逐张推进优先级（建议，2026-09-20 修订）

> 🔴 **本段（2026-09-20 版）整段作废**：其「修半接入 7 张 / 做从零 15 张」与统计段「32 张三维代码全绿 / 0 张半接入」直接矛盾——那批张已在批次 A/B/A-5 全部接入。以下为 2026-09-21 现状优先级：

1. **真 OO canvas 往返验证（唯一 env 门，批次C）**：34 张三维代码全绿但**无一张到 `ONLYOFFICE_VERIFIED`**（需 start-dev.bat 全栈 + OO 容器，OO canvas 非 DOM，Playwright 无法可靠编辑单元格）。逐张产 `evidence/.../D4-*.json` 的 `doc_editor_called:true` + `working_paper_content_application` state=applied。此前的 REQUEST_PATH 级证据（含 D4-1）已在。
2. **D4-8 rematerialize 已完成**（commit 98ab0eaef，gen81→82，真栈 store-projection 200 含 180 cell）——原「representation 未含」记录过时；仅剩真 OO canvas 往返 env 门。
3. **D4-14 已落地**（2026-09-21，路线A全受管）：源模板物理列↔前端 7 维裁决经审计业务复核**签署确认路线A**（`evidence/d414-column-mapping-adjudication.md`），前端补 16 字段（voucher.customerName/contract.date/delivery.number·quantity·shippingApprover/shipping.number·quantity·company·address/receipt.quantity·signer·sealType·sealEntity/invoice.productName·quantity/other.anomalyNote），provider `phase5_d4_14_occurrence`（单宽动态行 + 7 维嵌套 json_pointer + 34 受管字段 + formula_mask G37/X37/AF37/G39 + UUID列AL），契约 34 张（含 d4-12 + d414），发布 gen82→83（contract 0e2023fa **同时含 d4-12 + d414**），前端接桥 + 宿主登记 'D4-14'，守卫 `test_d4_14_occurrence_contract`(7)/`test_d4_14_walkthrough_roundtrip`(3,真instrument往返)/`test_d4_14_mirror_consume`(4)/`mutate_d4_14_guards`(5锚点全RED)/`d4OccurrenceSyncHostWiring.spec.ts`(10) 全绿；真 OO canvas 往返 env 门（批次C，同全组标准）。
4. **D4-12 转置已落地**（2026-09-20，`d4-12-transposed-writeback` 15/15，三维代码全绿，真 OO canvas env 门）。
   - ✅ **落地记录（2026-09-20）**：核心 = 把绑死 D4-29 的转置引擎**泛化**为参数化 `TransposedSheetSpec`（geometry/identity/store 形态全字段）+ `transposed_registry.resolve_transposed_specs` 注册表分派，`adapters/excel.py` 4 处旁路（materialize 单/多 binding + extract + verify）从「if is_enabled 单例」改「for spec 遍历」，`published_identity_observer` 转置 anchor 识别一并泛化（原硬编码 D4-29 SHEET_KEY/DEFINED_NAME/首列 C）。**D4-29 零回归实证**：materialize sha256 count=0/2/12/14 逐字节 == 泛化前、extract 逐字段 ==、mapping_digest `e3193dd9…` 逐字符不变（`evidence/d429-zero-regression.json` + 变异守卫 `test_d429_unaffected_when_registry_only_d429`）。D4-12 provider `phase5_d4_12_contract`（首列 **B**≠D4-29 的 C、21 字段 R11-R31、扁平 store `D4-12-contracts-v2`、`GT-CONTRACT-` 载体、`contractAmount` value_type=amount、mapping_digest `2d3a1c5f…` 冻结）。instrument 注入走既有 `excel_instrumentation` transposed_sheets 分支（实测 D4-29 的 definedName+载体行也是 instrument 注入而非模板预置，故 D4-12 零新注入代码）。发布链 gen82→83（contract `0e2023fa`，34 张含 d4-12-managed），无 Roundtrip/FooterAnchor/SoftTimeout。前端 `D4TabContract.vue` 接 `useWorkpaperSyncBridge`+`WorkpaperSyncEditorHost`（替 legacy `GtOnlyOfficeSheet`）+ 三态中文 tag，宿主 `isD4DedicatedSyncSheet` 含 'D4-12'。守卫 `test_transposed_registry`(10)/`test_d4_12_contract`(6)/`test_d4_12_transposed_roundtrip`(11,真 instrument 往返)/`test_d4_12_mirror_consume`(5,第四维)/`mutate_d4_12_transposed_guards`(4 锚点全 RED + 每条 D4-29 回归绿)/`d4ContractSyncHostWiring.spec.ts`(10) 全绿；D4 辐射面 340 passed 零回归。真 OO canvas 往返 env 门（批次C，同全组标准）。
   - 🔴 **发布链途中修复一处 pre-existing bug（与 D4-12 无关）**：`d43_rematerialize_dual_sheet._read_store_map` 对缺失 store item 统一塞 `EMPTY_STORE_PAYLOAD("[]")`，但 dict-store（D4-31 singleton `{}` / D4-9 / D4-35）拿 `"[]"` 被 `build_store_projection` 判「必须是单对象/字典」抛 `ValueError` 打挂整册 rematerialize。修复 = 缺失时**不塞该 key**（fixed_ids 除外），让 `build_combined_store_projection` 的 `payloads.get(item, <per-item 默认>)` 用 provider 单源默认；回归守卫 `test_dict_store_missing_key_uses_provider_default_not_empty_list`。
   - ✅ **D4-14 已完成（2026-09-21，见上方第 3 条）**：源模板物理列冻结（`营业收入发生检查表D4-14` A1:AK52，37 物理列，R13-14 两级表头，数据区 R15-36，footer 单行 `合计` R37），footer/引擎非障碍。裁决门经审计业务复核**签署确认路线A（全受管）**，14+2 无对应字段列全补前端字段，Phase 0-5 全落地。（此前"12 任务全未开始 / 待签署"记录已过时作废。）
5. ~~**D4-4/D4-13** 保持裁决（single_html / N/A），不做单元格双向。~~
   🔴 **D4-4 部分已作废（2026-09-28）**：其 `single_html` 裁决的两条理由经实测均不成立，
   已落地真双向（spec `d4-4-adjustment-summary-bidirectional-writeback`，见第十二轮）。
   **D4-13 的 N/A 裁决仍然有效**（纯叙述文本表，无行维度）。

## 关键教训（写入本清册以防再犯）

- **"契约里有 sheet" ≠ "双向已落地"**（历史教训，D4-21/22/23/24 **已于批次A 解决**）：曾后端契约齐全但前端在线编辑仍 legacy `GtOnlyOfficeSheet`，OO→HTML 统一路径未消费。必须三维全绿。现四张均已接 `useWorkpaperSyncBridge` + 宿主登记 dedicated。
- **前后端可能反向不一致**（历史教训，D4-30/31/32 **已于批次A-5 解决**）：曾前端已接桥但后端 `_INCLUDE_IPO_INTERVIEW_SHEETS=False` 契约无这些 sheet，前端调 materialize 因 sheet 不在契约而失败。现 flag=True、契约含三张、gen52 rematerialize 无 drift。
- **🔴 三维全绿 ≠ 真双向：OO→HTML 消费侧是第四维**（2026-09-21 新教训）：D4-8 三维全绿却 oo→html 完全不回写（无专用块）；13 个 item 因 merge 返回裸 payload 在 mirror 硬解包处崩、连累整个 entry；15 个 item 因漏登记 `STORE_ITEM_IDS` 而 merge 基线恒空。前三维（spec/契约/前端接桥）**都不覆盖消费侧**，必须补机器化守卫（`test_d4_mirror_shape_invariants.py`）：返回形态 4-tuple + 契约 store item ∈ STORE_ITEM_IDS∪专用块 + dict-store 有专用块。这是历史 4 次同源缺漏（D4-8×2 / D4-9 / D4-15/16）的统一判据面。
- **半成品接入会打挂整个 entry**：D4-15/16 曾因契约声明但 representation 未 rematerialize，导致整个 `gt-d4-operating-revenue` entry（连累 D4-2/3/25~28）store-projection 全线 500。改契约后必须跑 provision + rematerialize 发布链。
- **裁决 static-cell vs 动态行必须实测模板行为，不能只看当前数据区行数**：D4-1 清册初判 static-cell（因看到 R8-11/R14-17 只 4 行），但模板数据区实为**可扩动态行**，且前端早已用 `D4-1-rows` 动态行模型 —— 硬套 static 会与前端模型对不齐。裁决动态/静态要看「业务上能否增删行」，不是「当前占几行」。
- **同 sheet 双区双向 = 4 处共享内核缺口，不是加个 sheet 那么简单**（D4-1 实测）：`_attach_table_part` XML 合并 / sibling binding 对齐 / `excel_extract` 一 sheet N 表逐 binding 反读 / `excel_materialize` footer per-region 解析（同名 `小计` marker 靠 `min_row` 区分、`GT_FOOTER_ROW_{TID}` 靠平行清册）。任一没修都会在 rematerialize 阶段以 `ManagedRegionResolutionError` 或 `FooterAnchorDriftError` 暴雷。改这些共享文件受主控 §5.3 共享锁约束，须 GENERALIZE 不回归单动态表（既有 358 单 sheet 工作簿注入字节 sha256 零漂移 + 变异守卫）。
- **跨 spec 借道要双向登记**：D4-1 落地时顺带把 D4-9 owner spec 的 Task 1（`_attach_table_part` 合并）做实了，D4-9 因此从 0/15 变 1/15。这类"A spec 解除 B spec 阻塞"的情况，两边 tasks.md 和本清册都要同步，否则 B spec 会重复评估已完成的阻塞项。
- **flag 翻 True ≠ 收口，非法 key 会打挂整个 entry**（D4-8 实测，2026-09-20）：`stable_field_key` 必须过 `contracts.assert_stable_key`（只允许小写/数字/`_`/`-`/`.`/`/`/`{}`），直接把前端 store 的驼峰字段名（`revQty` 等）拼进契约键 → 生成非法 key → `parse_contract(build_contract_payload())` 抛 `ContractSchemaError`，**连累整份 payload**（同 entry 其它张测试一起挂）。契约键要小写化、`json_pointer`/store 写回另用驼峰键（前端真源），二者分离。**且 flag 翻 True 但 spec 收口任务（零回归/发布链）未完成时，靠"磁盘旧契约没这张"苟住只是把雷埋在 `assert_contract_file_matches_source` DRIFT 里——一次 `generate --apply` 就爆。落 flag 前先确认契约能 parse + 磁盘 source 一致。**
- **未跟踪文件 + 已跟踪模块 import 它 = HEAD 断裂**（D4-8 / D4-9 两次同源）：provider/测试若 `??` 未入 git，但已入库的父模块 import 了它，clean checkout 会 ImportError 打挂全 entry。落地一张的收口清单必含「provider + 测试 + 前端守卫全部 `git add`」，收口后 `git status` 应无自己的 `??`。

## D4-1 几何核定与落地记录（2026-09-20 更新，对齐已入库实现 `phase5_d4_adjudication_sheet.py`）

> ⚠️ **裁决更正**：2026-09-19 版曾判「D4-1 走 static-cell 模式，非行 UUID 模式」——该结论在实现阶段被推翻。真实模板的两段数据区是**可扩的动态行**（不是固定 4+4 骨架），前端 `useD4Adjudication` 早已用 `D4-1-rows` 动态行模型 + per-field，故最终按**同 sheet 双区动态行 UUID** 落地（参照 D4-9 多 table 结构，非 D4-5 static_row）。static-cell 段整段作废。

**结构**（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `营业收入审定表D4-1`，dims A1:I80）：
- 表头：行 5「项目/本期数/上期数」+ 行 6「未审数/账项调整/重分类调整/审定数」（两级，本期 B-E / 上期 F-I）
- 主营业务收入段（section `main-revenue`）：数据行 **8 起**（R8-11 预留） + 行 12 小计；UUID 列 **W**；table `adjudication_main_rows` / TID `D41MAIN`
- 其他业务收入段（section `other-revenue`）：数据行 **14 起**（R14-17 预留） + 行 18 小计；UUID 列 **X**；table `adjudication_other_rows` / TID `D41OTHER`
- 行 19 合计、行 20 试算平衡表数(只读回显 `D4-1-adj-tb-6001/6051`)、行 21 差异数、行 22+ 审计说明/结论
- 列：A=项目名 · B/C/D=本期未审/账项调整/重分类(受管输入) · **E=本期审定(公式 `=SUM(B:D)`)** · F/G/H=上期三输入 · **I=上期审定(公式)**
- 受管字段 = 每区 label + 6 金额（B/C/D/F/G/H）；formula_mask = E/I 数据行 + 小计/合计/差异行（12/18/19/21）的 B-I。

**已落地（commit `663c3f019`，owner spec 12/12）**：
- provider `phase5_d4_adjudication_sheet.py`：两 row table + `MANAGED_FIELD_SPECS`(7 字段) + `_formula_mask_cells` + `sheet_payload_d41`(2 table) + `instrumentation_spec_d41`(2 spec 共享 sheet_key) + `build_store_projection_d41`(按 sectionKey 分流) + `merge_projection_into_d41_rows`；`EXPECTED_MAPPING_DIGEST_D41` 冻结。
- 6 点集成进 `phase5_d4_revenue_detail`（只加不动 D4-2/3/5/15/16/25~28）。
- **4 处共享内核缺口全修**（见上「增量更新」段①~④）——这是 D4-1 的真实工作量核心，也顺带解除了 D4-9 Task 1 阻塞。
- 发布链跑全：契约 `--check` OK / provision 幂等 / `d43_rematerialize --apply` gen50→51、bundle=desired `af32bfbd…`；store-projection 含 D4-1 不打挂 entry（DB 三判据 GREEN）。
- 前端 `D4TabAdjudication.vue` 接桥 + 宿主 `isD4DedicatedSyncSheet` 含 'D4-1'；`publishAdjudicated` 发布门不动（TB 发布分离，双向切换不触发 TB 发布）。
- 守卫全绿：后端 `test_d4_1_adjudication_contract.py`(10/10)/`test_d4_1_dual_region_managed_tables.py`(7)/`test_d4_1_sibling_binding_alignment.py`/`test_d4_1_footer_anchor_per_region.py`(10) + 变异 `mutate_d4_1_adjudication_guards.py`；前端 `d4AdjudicationSyncHostWiring.spec.ts`。

**仍待办**（🔴 更正：tasks.md 中 Task 11/12 现均已 `[x]`，非 `[~]`）：
- Task 11 e2e（`d4-bidirectional-acceptance.spec.ts` 加 D4-1 + 证据 `evidence/.../D4-1.json` + `D4-1-L2.json`）：L1 GREEN（进在线编辑走统一路径、callback 四项齐、0 旁路、OO 挂载），L2 双区 roundtrip 因目标 wp 无 D4-1 受管双区行而**如实 SKIP/blocked**（真实库唯一有 D4-1-rows 的 wp 无 published representation），不伪造 cs_error=0。完整往返待 seed「同时有 published representation + D4-1-rows(main+other)」的 wp（`D4_ACCEPT_L2_WP_ID` 指向）后即绿——归真 OO canvas env 门批次C。
- Task 12 收口已完成（三件套校验 + git 入库）。
- 🔴 风险已缓解但仍需真栈确认：D4-1 是审定枢纽（下游 K9/D4-10/D4-21 取审定数 + TB 发布）；离线/DB 判据已绿，e2e 真栈双区往返（OO 改主营/其他行→切回 HTML 值一致、两区不串）是最后一道未验证门（env 门）。

## 2026-09-21 第二轮现状核对（全部结论经磁盘/git/真 PG 实证，不引用文档自述）

> 本段只记「与上方既有记录不一致」或「上方从未覆盖」的事实。上方各段保持原样（append-only）。

### 🔴 一、工作区 detached HEAD 事故（最高优先级，已修复；这是本轮最大发现）

核查开始时工作区**停在 detached HEAD `c5e456990`**，即分支 `work/2026-09-14-d4-dual-mode-p0-fixes`
tip（`3e894ed48`「feat(d4-14+d4-12)」）的**父提交**。reflog 实证是 2026-09-20 23:13/23:14/23:15
三次 `checkout` 来回切换（疑似零回归/变异核查）后**停在了父提交没切回来**。

后果（当时磁盘实测，全部与上方文档记载相反）：

| 判据 | 文档记载 | detached HEAD 实测 |
|---|---|---|
| 磁盘契约 sheet 数 | 34 | **32**（无 `d4-12-managed` / `d414-managed`） |
| provider | `phase5_d4_12_contract.py` / `phase5_d4_14_occurrence.py` / `transposed_registry.py` | **三个文件都不存在**（只剩 `__pycache__` 里的 `.pyc` 残骸） |
| 前端接桥 | D4TabContract / D4TabOccurrence 已接桥 | **两个都还是 legacy `GtOnlyOfficeSheet`** |
| 宿主登记 | 32 张 | **30 张**（缺 'D4-12'/'D4-14'） |
| 守卫 | `d4ContractSyncHostWiring.spec.ts` / `d4OccurrenceSyncHostWiring.spec.ts` | **两个文件都不存在** |
| spec 三件套 | `d4-12-transposed-writeback` / `d4-14-walkthrough-writeback` | **两个目录都不存在** |
| definition_store | bundle `2a8db807` / contract `0e2023fa` / instrumentation `cfc97557` | **三个 artifact 文件都不存在** |

而**真 PG 的 `working_paper_sync_entry_state` 当时已是 generation 84 / bundle `2a8db807…`（34 张）**
—— 即「DB 已发布 34 张，磁盘源码只能产 32 张、且 bundle/contract artifact 文件缺失」的**自相矛盾态**。
这正是清册「半成品接入会打挂整个 entry」警示的同型故障，只是成因从「漏 rematerialize」换成了
「检出停在旧提交」。

**处置**：`git checkout work/2026-09-14-d4-dual-mode-p0-fixes` 恢复（零风险：worktree 干净、
tip 已 push 到 `origin/`、父提交内容是 tip 的子集，无任何丢失可能）。恢复后全部判据与文档记载一致：
契约 34 张 ✓ / 三个 provider 在 ✓ / 两组件接桥 ✓ / 宿主 32 张 ✓ / 守卫在 ✓ / artifact 在 ✓ /
`d43_rematerialize --check` = **`already_on_desired_bundle`（gen 84，desired == current，无漂移）** ✓。

**🔴 教训（新增，与既有教训同级）**：
1. **「切到父提交做零回归/变异核查」必须配对切回，且要有收尾检查**。收尾清单应加一条：
   `git status` 干净 **且** `git branch --show-current` **非空**（detached 即视为未收尾）。
   本次若不是逐张核查磁盘，几乎必然把「D4-12/14 前端未接桥、守卫文件不存在」误报成**真实回归**
   —— 本轮前半程确实一度得出了这个错误结论，靠 `git ls-tree` + reflog 才定位到是检出问题。
2. **判断「某产物是否存在」必须落到磁盘/git 实证**（`Test-Path` / `git ls-tree` / python `Path.exists()`），
   不能只靠 IDE 侧的文件读取 —— 本轮 IDE 的 `read_file`/`list_directory` 返回的是**分支 tip 的缓存视图**，
   与 detached HEAD 的真实磁盘内容**不一致**（读得到 `.kiro/specs/d4-14-walkthrough-writeback/tasks.md`，
   而 `Test-Path` 判 False）。两套视图打架时**以磁盘为准**。

### 二、owner spec 进度数字更正（上方「逐张清册」表内 6 处过时）

上方表格 owner spec 括号里的进度是历史快照，现按磁盘 tasks.md 复选框实测更正：

| 清册记载 | 实测（2026-09-21） | 说明 |
|---|---|---|
| `d4-revenue-matrix (11/13)` | **13/14**（13 `[x]` + 1 `[~]`） | 剩 Task 13 C4 逐表验收（含 Playwright），env 门 |
| `d4-9-customer (1/15)` | **12/15**（12 `[x]` + 3 `[~]`） | 「1/15」是 D4-1 顺带解阻当时的旧数；剩 13/14/15 全 env 门/总纲 gate |
| `d4-cutoff-return (3/13)` | **13/13 全绿** | D4-17~20 四张已落地，spec 已收口 |
| `ipo-fraud (6/11)` | **11/11 全绿** | D4-30/31/32 批次A-5 已收口 |
| `gap-closure (0/5)` | **1/5 `[x]` + 4/5 `[-]` N/A** | Task 2-5 已显式裁 N/A 作废（D4-4 single_html / D4-8 归 static-cell spec / D4-12 已归专项 spec） |
| `d4-14-walkthrough-writeback (12/12)` | **12/13 `[x]` + 1 `[~]`** | 🔴 本轮把漏勾的 **Task 3** 补为 `[x]`（前端 7 维模型对齐实为已完成，见下条）；Task 11 的 e2e 子项保持 `[~]` env 门 |

另外 `d4-inspection-writeback-formula-io` 机械计数是「9/16」，**与实际状态相反**：草案代任务 1-7
已被做实代 T1-T7/B1-B3（全 `[x]`）逐条承接或显式裁决，无一条待开工。已在该 spec tasks.md 末尾
append「任务状态归并表」作为唯一权威对照，后续统计请按 T/B 代计（**10/10**），勿把 1-7 重复计入分母。

### 三、D4-14 Task 3（前端 7 维模型对齐）实为已完成，本轮补勾

实测证据：7 维 sub-object 已按路线A补齐（voucher 11 / contract 10 / delivery 10 / shipping 10 /
receipt 10 / invoice 8 / other 6 字段，`customerName`·`shippingApprover`·`anomalyNote` 等 16 个新字段
全在，`anomalyNote` 标 `optional: true` 不参与完整性判定）；`_SHEET_HEADERS["D4-14"]` 语义投影头
**32 → 48 列**，与路线A全受管严格同序（消除「语义投影头 ≠ 物理列」再分叉）；
`useD4WalkthroughTest.spec.ts` **50 passed**（新字段已进 fast-check PBT）+
`d4OccurrenceSyncHostWiring.spec.ts` **10** + `d4ContractSyncHostWiring.spec.ts` **10** = **70 passed**。

### 🔴 四、新实证：当前 bundle 上的 OO→HTML apply 次数 = 0

真 PG 查询（`working_paper_content_application` / `working_paper_content_version`）：

- entry `xlsx/gt-d4-operating-revenue` 累计 **applied 14 / error 5 / conflict 3 / authorization_stale 2**；
  `working_paper_content_version` 的 `source=onlyoffice` **14 条**。
- 但**按 bundle 分组后，`definition_bundle_sha256 = 2a8db807…`（= 当前 gen84 的 34 张 bundle）的
  application 记录数 = 0**。最后一条 applied 打在旧 bundle `d91cf0f2…` 上，时间 2026-09-20 **02:25Z**；
  而当前 bundle 的 contract artifact 落库时间是同日 **13:58Z**、gen84 是 **14:54Z**。

**含义（上方任何段落都未覆盖）**：
1. 清册顶部「D4-2 DB 侧铁证：12 个 applied oo_to_html application」确实是真实往返，但**全部发生在旧
   bundle 上**，不能代表当前 34 张 bundle 的回写链可用。
2. commit `808505a15` 修的三处 OO→HTML 消费侧缺口（P0 硬解包崩 / P1 D4-8 静默不回写 / P2 15 item
   基线恒空）**目前只有离线守卫（`test_d4_mirror_shape_invariants.py` 5 tests）覆盖，真实 apply 路径
   一次都没走过**。P0 那条原本就是「实跑才复现」的 `ValueError`，纯离线守卫不足以证明修复在真栈成立。
3. 同理，D4-12（转置）/ D4-14（7 维嵌套）/ D4-8（180 静态 cell）三条**新引擎路径**的 apply 侧
   `_mirror_d4_dual_stores` 消费，也从未在真栈执行过。

⇒ 所以「34 张三维代码全绿」的口径依然成立，但**批次C 的紧迫性被低估了**：它不只是「补证据 JSON」，
而是「当前发布态的回写链从未被真实验证过一次」。

### 🔴 五、第三维（前端接桥 + 宿主登记）缺机器化闭集守卫

第四维已由 `test_d4_mirror_shape_invariants.py` 钉死（契约 store item ∈ `STORE_ITEM_IDS` ∪ 专用块集合）。
但**第三维没有同型的闭集守卫**：实测 `audit-platform/frontend/src/components/workpaper/__tests__/`
下有 **20 个 `d4*SyncHostWiring.spec.ts`**，每个都各自复制一份 `extractDedicatedList` helper，
只断言**自己那一张**在 `isD4DedicatedSyncSheet` 里。

后果：这些守卫只能防「已有守卫的那张被删掉」，**防不住新增的那张忘记登记** —— 而这恰恰是历史上
复发 4 次的同源缺漏（D4-15/16、D4-21~24、D4-25~28、D4-30~32 全是「后端契约已落、宿主漏登记 →
双切换器叠加 + 误入 legacy 整册 `GtOnlyOfficeSheet`」）。第 35 张 sheet 明天落地时，同一个坑仍然敞开。

**建议补一个闭集守卫**（第三维机器化判据，与第四维同型）：读
`backend/data/workpaper_sync_contracts/d4.revenue_detail.json` 的 sheet_key 全集 → 对每个 sheet_key
反查「有 `D4Tab*.vue` 引用该 sheetKey 且 import `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`」
+「其 D4 编码 ∈ 宿主 `isD4DedicatedSyncSheet`」，任一缺失即红；宿主自管的 `d42/d43-managed` 与
裁决 single_html/N/A 的 D4-4/D4-13 走显式白名单（白名单本身也要断言不含契约里的张）。落地后
20 个重复 helper 可收口成一个共享工具，不必逐张再写。

### 六、附带发现：工作树有一份在途未提交的 writer gate 修复（非 D4 直接产物但由 D4 迁移触发）

恢复分支后 `git status` 显示 4 个文件有未提交改动（不是本轮核查产生的，是此前会话的在途工作，已原样保留）：
`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md` /
`backend/data/workpaper_writer_domain_overlay.json` / `backend/data/workpaper_writer_inventory.json` /
`backend/scripts/gen/generate_workpaper_writer_inventory.py`。

内容是一条**由 D4 双向回写迁移触发的 writer gate 崩溃修复**：D2/D4 迁移把 `d4_import_data` 从
direct content writer 改成**委派** writer，使调用它的 `_d4_import` 从 `_propagate_content_writers` 的
**单跳**传播里掉出发现面，overlay 仍裁决着它 → 门崩在 `assert_inventory_is_current`
（`WriterInventoryError: writers ... no longer exist in source`）。修法是把委派传播改成**对 writer 图的
有界闭包**，补回 33 个真实多跳 writer 入口，分母 327 → 371，红基线 658 → 788 条 blocking facts
（`unadjudicated_writer` 0 → 36 等是新补回入口尚无 overlay 裁决的真实欠账显形，非放宽判据）。

**提醒**：这份改动**尚未提交、也不在任何 commit 里**（`git log --all -S"_propagate_content_writers"`
只命中它的引入 commit `42d2f6e6f`，改动本身无归属）。属易丢工作，宜尽快独立入库。

---

## 2026-09-21 第三轮：D4-2 真栈彻底跑通 + 两处 apply 阻塞根因修复（本轮）

> **本轮结论**：D4-2 L2 真栈（真 OO canvas 写 A12 → forcesave → mirror 回 HTML → applied）**首次在当前发布态跑通**。
> 逐层暴露并根治了两个此前挡在 apply 前的真实 bug（一个 correctness、一个 verify 假红），均配机器化守卫 + 变异反证。
> 上方「四、当前 bundle 上 apply 次数 = 0」的紧迫性由此**部分解除**：当前发布态回写链已被真实验证过一次（D4-2）。

### ① value_type=json 单元格往返 bug（correctness，Property 65 真红）

- **真因**：D4-30 `custom_dimensions` / D4-31 `q1_relation` 是 `value_type=json` 的受管单元格字段。
  materialize 侧 `excel_materialize._normalised_write_value` 返回 `merge.normalize_value` 的 canonical
  **bytes**（`{"v": value}` 包裹，本意只作比较口径的键）；`inline_text` 渲染 `str(write.value)` 把 bytes 写成
  Python repr（**带 `b'...'` 前缀**）落盘；extract 读回该字符串后 `normalize_value` 再包一层
  `{"v": "<那串>"}` → 与提交侧 `{"v": value}` **永不等值** → materialize 报
  `roundtrip_projection_mismatch`（真栈实测「提交 `{}` → 反读 `'b\'{"v":{}}\''`」）。
  这是 D4-30 把 `custom_dimensions` 变成投影字段后暴露的既有隐患（此前该字段未进投影，从未跑到）。
- **对称修复**（不弱化 normalize_value 的比较口径）：
  - `excel_materialize._normalised_write_value`：json 落盘写 **value 自身**的 JSON 文本（`json.dumps`，
    `{}`/`[]`/`{"a":1}`），仍先过 normalize_value 校验（拒 NaN/Infinity/非可序列化）；
  - `excel_extract._collect_fields`：json 单元格文本 `json.loads` 解回 Python 对象（解析失败保留原串，
    交下方 normalize 记 `type_normalization_failure`，绝不静默吞）。两侧都持对象后 normalize 对称等值。
- **守卫**：`test_json_cell_roundtrip.py`（9 passed，含空 dict 最小复现 + 7 参数化 JSON 值 + 负向断言）；
  **变异反证**：把 materialize 改回 `return normalized`（bytes）→ 7 RED 精确复现 `b'{"v":{}}'` 形态。

### ② 转置 sheet other_sheet_parts 假 drift（verify 假红，方案 A）

- **真因**：转置 sheet（D4-29 `客户信息检查表` / D4-12 `合同检查表`）走 **carrier-row 身份机制、无
  `ExcelIdentityBinding`**（不在 `instrumentation_specs` 受管表清单里）。verify 时其 sheet part 不在
  `all_managed_parts` → 落进 `other_sheet_parts` 桶做**原始字节比对**（`_part_digest` 纯 sha256）。而转置
  materialize 用 openpyxl `wb.save()` 全量重序列化目标 sheet part，其字节**依赖整簿内部状态**：materialize
  侧在 34-binding 链式改写后的 workbook 上跑、verify 中性化侧在**原始 before** 上跑 → 两侧非受管列字节
  （dimension/style xf 索引/属性序）不一致 → 假 `adapter_unmanaged_region_drift`（D4-29 非空真栈复现；
  D4-12 空表同类，此前靠 `if not after_rows: continue` 空守卫绕过，非空则复发）。
- **方案 A 修复**（`adapters/excel.py` verify wrapper）：把转置 sheet 的 part（`resolve_transposed_specs`
  的 `managed_sheet` 经 `_sheet_parts` 解析）**并入 `all_managed_parts`**，从 `other_sheet_parts` 原始
  字节比对里排除——与「有 binding 的 sheet 走各自 `managed_sheet_*` aspect、不进 other_sheet_parts」同口径。
  转置 sheet 受管内容（列）由 `extract_transposed_workbook` 往返 + fail-closed 校验（公式格拒绝 / carrier
  强校验）守护；保护区（label 列 A/B / footer / static prompt）materialize 不写、只被 openpyxl 重序列化碰
  字节，排除原始字节比对**不损失篡改检测**。
- **守卫**：`test_d4_12_transposed_roundtrip` + `test_transposed_registry`（33 passed 含既有空表 AST 守卫，无回归）。

### ③ 真栈验证结果

- **D4-2 L2 e2e：`1 passed (5.0m)`** —— store-projection 200 → pending-mutations 200 → **materialize 200**
  → OO canvas 写 A12（via `Asc.editor`）→ callback 4 项齐全 → mirror 回 HTML → applied。
- **D4-25/26/27/28/29 L1（serial，含转置 D4-29 + json 相关 IPO 表）：`5 passed (47.7s)`**。
  ⚠️ 先前 5-worker **并行**版全挂 = OnlyOffice 8080 并发 contention（`ooHealthy`/挂载超时），**非** wiring gap
  也非本轮后端修复——serial 版全绿即证。逐张 L1 必须 `--workers=1` 跑（OO 单实例扛不住并行编辑会话）。
- D4 全套后端回归 **348 passed 0 failed**（含 3 个新 json 守卫，零回归）。

### ④ 诚实暴露：7 张 L1 仍未过（前端「在线编辑」切换器 gap，非本轮范畴）

serial 跑其余 15 张，**8 passed / 7 failed**（过：D4-9/21/23/24/11/31/32；未过：**D4-14/22/10/30/33/34/36**）。
7 张失败**全部卡在前端**「在线编辑」切换器 `element not found`（20s 超时），**根本没走到 materialize**——
用 chrome-devtools 手动点 D4-30 页签实证：点击后主内容区未渲染 `D4TabInterviewSummary`、`el-segmented` 为空，
是**前端 UI 页签导航 / host-wiring gap**（与本轮后端 sync 引擎修复无关，属独立待办）。同组件模式的 D4-31
（InterviewDetail）却过、D4-30（InterviewSummary）不过，说明是**逐张导航/渲染时序**问题而非系统性缺失。
→ 独立登记为待办：**前端 D4-14/22/10/30/33/34/36 在线编辑切换器不可达**，需前端 host 侧排查（页签点击后
dedicated sync 组件未挂载）。

### ⑤ pre-existing 失败已核验（非本轮引入）

`test_task26_oo_to_html_pg::TestAppliedHappyPath::test_p29`（applied 场景 `materialize` 调用数 0≠1）——
`git stash` 掉本轮 3 个后端源文件（excel_materialize/excel_extract/adapters·excel）后**同样失败**，确认
pre-existing，已恢复改动。属 apply 半应用态的既有欠账，非本轮 json/transposed 修复触及。

### 本轮改动文件（sync 修复，与 writer-gate 在途拆开独立提交）

- `backend/app/services/workpaper_sync/excel_materialize.py`（json 落盘写文本 + 既有 timeout structure_hash）
- `backend/app/services/workpaper_sync/excel_extract.py`（json 单元格 json.loads 解回对象）
- `backend/app/services/workpaper_sync/adapters/excel.py`（转置 part 并入 all_managed_parts + 既有 timeout）
- `backend/app/services/workpaper_sync/phase5_d4_ipo_checklist_sheets.py`（8 处 value_type，上轮第3层-A）
- `backend/app/services/workpaper_sync/phase5_d4_ipo_interview_sheets.py`（D4-30 缺 fields 段容差，上轮第3层-C）
- `backend/app/services/workpaper_sync/store_projection_response.py`（P0-A 缺失 item 不预填 empty）
- `backend/data/workpaper_sync_contracts/d4.revenue_detail.json` + 新 bundle/contract artifact（value_type regenerate）
- 守卫：`test_json_cell_roundtrip.py`（新）/ `test_d4_interview_missing_fields_tolerance.py`（新）/
  `test_d4_12_transposed_roundtrip.py` / `test_d4_ipo_all_four_bidirectional_roundtrip.py`

---

## 2026-09-21 第四轮：前端「在线编辑」切换器不可达 7 张全修，D4 全 20 张 dedicated sync L1 全绿（本轮）

> **本轮结论**：上一轮（第三轮 §④）诚实登记的「前端 D4-14/22/10/30/33/34/36 在线编辑切换器不可达」7 张
> **全部根治**。逐张 chrome-devtools/playwright 实证 console 错误定位（非猜），挖出并触类旁通修掉 **6 类**
> 真前端 bug + 1 个 e2e 定位器 bug。全 20 张 dedicated sync 底稿 L1 serial（`--workers=1`）**20 passed**。

### 判据先厘清：为什么之前 7 张卡住

7 张失败**不是** `currentSheet` 路由错（render-config 真实 sheet_name 全部干净以编码结尾，正则派生正确），
而是**子组件 mount 期崩溃 / 静默不发请求**。逐张 devtools 实证的 console 错误锁定 6 类真因：

### ① D4-30 render crash：`.fields` undefined（`Cannot read properties of undefined (reading 'time')`）

- 卡片视图 `activeCustomer.fields[field.key]` / 矩阵 `cust.fields[row.key]`。后端 store 里一条客户行可能只有
  `{id,name}`（合法半成品，**与后端 `phase5_d4_ipo_interview_sheets`「缺 fields 段 → None」容差同源**）→
  `fields` undefined → 组件渲染抛错被 ErrorBoundary 捕获 → 子组件不挂载 → 在线编辑切换器不可达。
- 修：`D4TabInterviewSummary.vue` `loadData` 加 `normalizeCustomers` 归一 `fields` 为对象（单源）。
- **触类旁通**：`useD4CustomerDetail.ts`（D4-29）同一 `.fields[]` 模式（`relatedCount`/`completionRate` 也会崩）
  同型修。守卫 `useD4CustomerDetail.normalize.spec.ts`（2 passed + 变异反证 RED）。

### ② D4-10 TDZ crash：`Cannot access 'debounceTimer' before initialization`

- `D4TabCustomerPrice.vue` 的 `immediate: true` watch 在 setup 期即跑 `persistData → debounceSave`，访问
  `let debounceTimer`（声明在文件后段，处于 TDZ，`let` 不提升）→ ReferenceError 打挂组件。
- 修：`debounceTimer` 声明上移到 setup 顶部（任何 immediate watch 之前）。
- **级联发现**：D4-14/22/33/34/36 在批量 serial 里曾被 D4-10 崩溃**级联连累**（ErrorBoundary 捕获后同会话
  后续 tab 受影响）——D4-10 修好后它们的渲染自愈，只剩各自的健康竞态（③④）。

### ③ ooHealthy 竞态：切「在线编辑」静默 no-op（L1 判据1 `hits.length=0` 真因）

- `switchMode`/`activateOnlineEdit` 里 `if (props.isReadonly || !ooHealthy.value) return`——`ooHealthy` 初始
  `false`，`checkOoHealth()` 是 mount 期异步（端点 20ms 但仍可能晚于用户/自动化点击）。点击早于健康响应
  到达 → 读到初始 false → **静默 return** → `switchToOnlyOffice` 从不触发 → store-projection/materialize
  一个都不发 → 卡在「正在打开同步编辑器…」。
- 修（D4-14/10/22/33/34/36）：健康未就绪时**当场 `await checkOoHealth()` 再判**，OO 真不可用才 return
  （fail-visible 由桥/后端给）。D4-22 另去掉 `modeOptions` 的 `!ooHealthy` disabled（切换器保持可点，
  健康门禁移进 `switchMode`），否则 disabled 段忽略点击、`switchMode` 根本不触发。

### ④ 错误健康端点：`/api/onlyoffice/health` 404 + 错响应字段

- D4-33/34/36 + D4-7(`D4TabMarginMonthly`)/D4-8(`D4TabProductMargin`) 打 `/api/onlyoffice/health`（**404**，
  正确是 `/api/workpapers/onlyoffice/health`）且读错字段 `status === 'healthy'`（正确是 `.healthy` bool）→
  `ooHealthy` 恒 false → 叠加 ③ 直接锁死在线编辑。
- 修（触类旁通全 5 处）：URL → `/api/workpapers/onlyoffice/health`，判定 → `r.data?.data?.healthy ?? r.data?.healthy`。

### ⑤ D4-30 缺 descriptor 计算属性（L1 判据4 `wp-sync-host` 超时）

- `D4TabInterviewSummary.vue` 模板 `<WorkpaperSyncEditorHost v-if="d4SyncDescriptor" ...>`，但脚本**漏声明**
  `d4SyncDescriptor` → 恒 undefined → materialize 成功拿到 descriptor 也永不挂载 OO 宿主。
- 修：补 `const d4SyncDescriptor = computed(() => d4SyncBridge.descriptor.value)`（与已工作的 D4-31 同取法）。

### ⑥ e2e 定位器 bug：`D4-22(?!\d)` 误命中 `D4-22A`

- 验收 spec 的 tab 正则 `sheet.code + '(?!\\d)'`：对 code `D4-22` → `D4-22(?!\d)` **同时命中**「…D4-22」与
  「…D4-22A（程序表）」，且 D4-22A 页签在 DOM 靠前 → `.first()` 误点到 `D4TabIpoProcedure`（无 dedicated
  sync 桥、走 legacy OO）→ 点在线编辑不发 `/sync/` → `hits.length=0`。属**测试**bug 非产品。
- 修：`e2e/d4-bidirectional-acceptance.spec.ts` 正则改 `(?![\dA-Za-z])` 排除字母后缀，精确区分编码与编码+字母变体。

### 真栈验证

- **全 20 张 dedicated sync 底稿 L1 serial（`--workers=1`）：20 passed**（store-projection 200 → materialize 200
  → callback 4 项齐全 → 无 /d2-sync/* 旁路 → OnlyOffice DocEditor 真实挂载）。
- 逐张手动 chrome-devtools/playwright MCP 实证：点击「在线编辑」→ store-projection/pending-mutations/materialize
  三连 200 + OO iframe active（D4-14/22/30 各实证）。
- 前端 vitest 回归：`useD4WalkthroughTest`(50) + `d4OccurrenceSyncHostWiring`(10) + `d4ContractSyncHostWiring`(10)
  + 新 `useD4CustomerDetail.normalize`(2) = 72 passed 零回归。
- ⚠️ 并行跑法（多 worker）仍会因 OnlyOffice 8080 单实例并发 contention 假失败——逐张 L1 **必须 `--workers=1`**。

### 本轮改动文件（11 个，纯前端 + e2e，与后端 sync 修复不同层）

- `D4TabInterviewSummary.vue`（normalizeCustomers + d4SyncDescriptor computed）
- `useD4CustomerDetail.ts`（normalizeCustomers）+ 守卫 `__tests__/useD4CustomerDetail.normalize.spec.ts`（新）
- `D4TabCustomerPrice.vue`（debounceTimer 上移 + switchMode 健康 await）
- `D4TabOccurrence.vue`（activateOnlineEdit 健康 await）
- `D4TabIpoIndicator.vue`（switchMode 健康 await + 去 !ooHealthy disabled）
- `D4TabOtherMargin.vue` / `D4TabOtherContract.vue` / `D4TabOtherCutoff.vue`（健康端点修正 + switchMode 健康 await）
- `D4TabMarginMonthly.vue` / `D4TabProductMargin.vue`（健康端点修正）
- `e2e/d4-bidirectional-acceptance.spec.ts`（tab 正则 `(?![\dA-Za-z])`）
---

## 2026-09-22 第五轮：30 张全绿之后的 5 处真根因修复 + 2 处判据/证据保真（本轮）

> **本轮定位**：第四轮把「点不进在线编辑」的前端 gap 清零后，D4 全量 30 张证据（`docs/operations/
> evidence/d4-bidirectional-acceptance/D4-{1..36}.json`，缺 D4-4 = owner 去重后不独立成表）
> `console_errors` / `http_errors` **全部为 0**。本轮修的是「全绿之后仍在真栈稳定复现」的深层缺陷：
> 一个把用户锁死在 500 死循环的 room 生命周期误判、一个恒假成功的删除、一个破坏公式键 identity
> 的正则、一对拖慢切页面的健康探针。全部**先复现 → 再定位根因 → 修主代码 → 补守卫**。

### ① 僵死 lease 打挂在线编辑：500 死循环（P0，真栈稳定复现）

**现象**：某些 D4 entry 点「在线编辑」永远停在「正在打开同步编辑器…」，`materialize` 稳定 **500
`room_not_writable`**；重新 flush 无效，反复重试仍回到同一间房。真栈同一 entry 已堆积 **6 个
从未确认即被遗弃的代际**（g69/76/77/78/80/93）。

**根因（两层，缺一不可）**：

1. `_join_or_reuse_participant` 发现僵死 lease 后**无条件**按「写会话被撤销 ⇒ 内容可能已污染 ⇒
   作废整代」处理（`revoke_participant` fence+1 + `refresh_required` → `supersede_room`）。该安全
   论证（「OO 的 `c=drop` 只证明会话被逐出，**不证明**已合入内容被移除」）预设 **OO 会话真实接管过
   文档**。而另有一类僵死 lease 根本没接管过：用户点了在线编辑、room 建好、**descriptor 确认从未
   到达**（OO 没加载完 / 用户切走），lease 随后自然到期。
2. 旧 `except _ExpiredLeaseRoomSuperseded` 分支拿**同一个** representation 去 `open_or_reuse_room`
   重开。但 `room.generation ≡ representation.generation`，`uq_wpoor_generation` 使 superseded 代际
   **永不可同代重开** ⇒ 撞 `RoomNotWritableError` → 500。而 materialize 是**读取路径**，手里只有
   冻结的旧 representation，**无法旋转 generation**（那是 `content_commit` 发布路径的职责）；且
   「重新 flush」在内容未改时走 business-identity 复用路径、**同样不旋转** ⇒ 永远回到同一间死房。

**修复（治本分流，按「这一代是否真正接管过内容」决定反应强度）**：

- 新增纯判据 `rooms.room_never_took_custody(room)`：room 停在 `opening`、`refresh_required_at` 为空、
  `client_confirmed_*` 四项全空、`last_applied_version_id` / `latest_durable_application_id` /
  `close_leader_intent_id` 全空、request/durable/close_barrier 序列为 0、`write_fence_epoch` 仍是初值 1。
  判据**全部取保守方向**（任何一项显示可能动过内容即 `False`），新增承载托管语义的列必须在此登记。
- 新增 `RoomService.release_stale_lease_on_pristine_room()`：判据为真 ⇒ participant `active → expired`
  （`uq_wpoop_active_lease` 是 `WHERE state IN ('active','closing')` 的 partial unique，转出即腾槽位），
  **并续租** `room.expires_at`（不续租会让用户进得去却存不了——`assert_can_initiate_request` 的
  room 过期门会拒 forcesave），随后在**同代 room** 上重新 join 一个干净 lease。用户当场回到在线编辑：
  不烧 generation、不抛 409。`ParticipantState.expired` 与 `PARTICIPANT_EDGES` 里的 `active → expired`
  早已定义却从未被任何代码使用——这条轻量迁移正是当初设计好、缺了接线的那一环。
- 判据为假（真接管过）⇒ 保持原重型反应，但 `except` 分支改抛 **409** `DescriptorSubstrateStaleError`
  （`error_code=launch_descriptor_substrate_stale`，前端 `classifySyncFailure` 已识别为「不可原地重试」），
  让客户端重新 flush → commit，由 D4/G7 canary 的 `_next_generation_probe`（`max(rep,room)+1`）发布新
  generation，下一次 materialize 用干净新代 room 开成功。**不再同代重开**。

**守卫**：`test_pristine_room_stale_lease_recovery.py`（新，判据侧纯函数 + 承载列登记反证）、
`test_task21_room_service_pg.py` §⑨b（真 PG：轻量释放 + 续租 + 立即重新 join 同代）、
`test_task25_materialize_coordinator_pg.py::test_expired_write_lease_refuses_with_409_stale_not_500_room_not_writable`
（阶段 8a-bis 采证 + `STALE_ON_ROOM_OPEN_MARKER` 区分「room 打开侧」与「重放侧」两条 stale 判据）。

### ② 公式删除恒假成功（P0，静默数据不一致）

`wp_formula.delete_formula` 调 `wp_formula_service.delete(db, formula_id)` **不传 `project_id`**，而服务层
第一道 ownership 门是「`project_id` 为 None 即拒绝并 `return False`」（Req 10.6）⇒ 永不执行 `db.delete()`；
路由又**忽略返回值**、无条件返回 `{"deleted": ...}` ⇒ 前端显示删除成功，刷新后公式仍在（真栈实测：
DELETE 200 之后 GET /formulas 仍返回该条）。同款缺陷在 `list_by_wp` 路径上已修过，delete 是当时漏掉的
最后一处。修：补传 `project_id=wp.project_id`，返回 `False` 时抛 404，不得再返回 200「已删除」。
守卫：`test_wp_formula_endpoint.py` 在 `DELETE 200` 之后**补回读断言**（原来只断言 200 ⇒ 正好漏掉这个缺陷）。

### ③ 公式 stable key 被展示前缀吃掉（P0，公式与单元格失联）

`stable_key._ORDER_PREFIX_RE` 原式 `[一二三四五六七八九十]+[、.．]?\d*[、.．]?`：`\d*` 本意吃掉 "五、1 "
这类**子序号**，却会贪心吃掉**正文**——PBT `test_property_key_stable_across_sheet_rename` 抽到反例
`base='0'`（`'0'` vs `'一、0'`）：整串被剥成空串 ⇒ `stable_sheet_key=''` 且 `needs_review=True`，而未加前缀
的 `'0'` 得到 `'0'` ⇒ 「加展示前缀不得改键」这条 identity 不变量被破坏。修：子序号 `\d+` 只在其后紧跟空白或
`、.．` 时才并入前缀（区分子序号与正文的判据就是**分隔符**：`"五、1 "` 带尾随空白，`"五、审定表D2-1"` 的
正文紧跟标点）；同时要求中文序号后**必须**有 `、.．`（原式 `[、.．]?` 会把 `"五1 "` 也当前缀，剥得过宽）。

### ④ OO 健康探针拖慢切页面（P1，一人慢拖累所有人）

- **后端**：`OnlyOfficeCallbackService.health_check` 标了 `async def` 却用同步阻塞的
  `urllib.request.urlopen`，在方法体内**真阻塞事件循环**最多 `timeout` 秒。调用方
  `wp_onlyoffice_router.get_onlyoffice_health` 是 D4 每次切底稿都会打的无鉴权探针，一次阻塞连累同进程内
  **所有**并发请求。改用本文件已有的 `httpx.AsyncClient`（真异步，不引入新依赖）。
  守卫：`test_onlyoffice_health_check_nonblocking.py`（新）。
- **前端**：`useD4SyncMode()` 每次被调用（=== 每切一张 D4 底稿，**不论是否点在线编辑**）都无条件
  `void checkOoHealth()`，30 张共用同一段 mount 逻辑。改为模块级共享 TTL 缓存（15s）+ **in-flight 去重**
  （多组件同时挂载只发一次真实请求）；`switchMode` 的竞态兜底传 `forceRefresh=true` 绕过缓存——用户已点击，
  不能信一个可能刚好卡在缓存边界的旧值挡住这次真实点击。测试专用 `__resetOoHealthCacheForTests()` 防跨用例污染。

### ⑤ 判据收窄 + 扩面：room 序号守卫（本轮 ① 暴露出的守卫精度问题）

`test_room_service_does_not_compute_request_sequence` 原判据是「剥注释/字符串后，模块正文里不得出现子串
`latest_request_sequence`」——① 的新纯判据只是**只读比较** `latest_request_sequence == 0` 就被打红。

该判据有两个毛病：**过宽**（把「只读观测」与「第二处推进」混为一谈；模块 docstring 自己把禁令写成「故意不提供
`next_request_sequence()`」，`_advance_canonical_fence_locked` 的 docstring 写成「那三行**算术**委派给
`repo.advance_room_durable_fence()`」——要守的一直是「算」不是「读」；旁证：兄弟字段 `latest_durable_sequence`
本来就被服务层 L1679 读着建快照，从未有人认为那违反本不变量）；**过窄**（只盯一个字段，`latest_durable_sequence`
此前**一条守卫都没有**，服务层今天写一行 `room.latest_durable_sequence = n` 不会有任何测试发现）。

改为 AST 判据 `_room_field_usages()`：把用法分成 `write`（赋值目标）/ `arith`（参与算术）/ `dynamic`
（字段名以字符串形态出现在调用实参或 dict 键，即 `setattr` 绕道）/ `read`（其余取值）四类——**前三类一律禁止**，
只读仅限逐字段登记的 `_SEQUENCE_READ_ALLOWLIST`（fail-closed：新函数想读必须显式登记并写明理由）。两个字段同判据。
**变异反证已实跑**：注入 `room.latest_request_sequence = 0`（write）与 `room.latest_durable_sequence + 1`（arith）
各打红一次，文件已还原。

### ⑥ 证据保真：`sheet_name` 改记观测值

`e2e/d4-bidirectional-acceptance.spec.ts` 的证据字段 `sheet_name` 原取调用方在 `D4_ACCEPT_SHEETS` 里传入的
`name`。本轮全量重跑用 `name === code` 的简写调用，30 份证据的 `sheet_name` 全退化成「D4-13」这类纯编码，
丢掉「到底点中哪张表」这个最关键的可复核信息——而页签**定位只用 `code`**，`name` 纯属证据字段，于是**没有
任何判据能发现它被传坏了**。改为记录**实际点中的页签文本**（`observedTabText`），清单声明值另存
`sheet_name_expected`。证据只记观测到的事实，不记输入参数。
⚠️ 本项**代码已改、未实测**：前端 3030 dev server 未运行，e2e 无法重跑，需下次验收运行才体现在证据 JSON 里。

### 真栈/回归验证

- PG 真栈：`test_task21_room_service_pg` + `test_pristine_room_stale_lease_recovery` **81 passed**；
  `test_task25_materialize_coordinator_pg` **52 passed**。
- 定向回归（含 ①④ 所有消费侧）：`test_task21_room_service` / `test_task25_materialize_coordinator` /
  `test_room_launch` / `test_task22_callback_claim` / `test_task28_sync_router` / `test_wp_onlyoffice_router` /
  `test_deliverable_onlyoffice` 合计 **494 passed**（1 pre-existing 红，见下）。
- 公式侧：`test_wp_formula_endpoint`(+`test_onlyoffice_health_check_nonblocking`) **6 passed**、
  `test_wp_formula_stable_key` **17 passed**。前端 `useD4SyncMode.spec.ts` **10 passed**。
- ⚠️ `tests/workpaper_sync` 全量约 180 文件，整目录跑 30 分钟只到 60%，不适合当回归口径；按改动模块定向跑。

### 诚实暴露：pre-existing 红（本轮逐一验证过「与本批无关」，登记为独立待办）

1. **OnlyOffice `enabled` 契约漂移（安全相关，待拍板）**：生产代码已改成
   `enabled = bool(settings.ONLYOFFICE_URL)`（commit `a60198b6a`，注释「JWT 为可选鉴权」），且
   `verify_callback_jwt` 在无 secret 时**直接放行**。但 `test_deliverable_onlyoffice::test_property_54`
   与 `test_deliverable_center_p1::test_onlyoffice_disabled_without_secret` 仍锚定旧契约（无 secret ⇒
   `enabled is False` / `verify_callback_jwt is False`）⇒ 两处红。已用 `git show HEAD:` 版本覆盖
   `onlyoffice_callback_service.py` 复跑确认**与本轮 httpx 改造无关**。
   含义：若部署时配了 `ONLYOFFICE_URL` 却没配 JWT secret，callback 端点会接受**未鉴权**的内容写入。
   两条路（收紧生产契约 / 更新测试到新契约）取向不同，**未擅自改，待决策**。
2. `test_d2_sync_retirement.py` 11 红——前瞻性退役门禁，phase 仍 `pre_delete`，legacy `d2_sync_router.py`
   与 `wp_html_save.py` 里的 `d2-sync` 字面量未删（门禁是「等退役执行后才转绿」的设计）。
3. `test_d2_store_value_equivalence.py` 3 红——`d2_bidirectional_bridge` 已无
   `merge_projection_into_store_rows`（API 漂移，测试未跟上）。
4. `test_task26_oo_to_html_pg::TestAppliedHappyPath::test_p29`——第三轮 §⑤ 已登记的既有欠账（apply 半应用态）。

### 本轮改动文件

- `backend/app/services/workpaper_sync/rooms.py`（`room_never_took_custody` + `release_stale_lease_on_pristine_room`）
- `backend/app/services/workpaper_sync/materialize_coordinator.py`（僵死 lease 分流 + 同代重开改抛 409）
- `backend/app/routers/wp_formula.py`（delete 补 `project_id` + 404 而非假 200）
- `backend/app/services/formula_management/stable_key.py`（`_ORDER_PREFIX_RE` 收窄）
- `backend/app/services/onlyoffice_callback_service.py`（health_check 改 httpx 异步）
- `audit-platform/frontend/src/components/workpaper/d4/composables/useD4SyncMode.ts`（健康 TTL 缓存 + 去重）
- `audit-platform/frontend/e2e/d4-bidirectional-acceptance.spec.ts`（`sheet_name` 改记观测值）
- 守卫：`test_pristine_room_stale_lease_recovery.py`（新）/ `test_onlyoffice_health_check_nonblocking.py`（新）/
  `test_task21_room_service_pg.py` §⑨b / `test_task25_materialize_coordinator_pg.py` 阶段 8a-bis /
  `test_task21_room_service.py`（AST 判据收窄+扩面）/ `test_wp_formula_endpoint.py`（回读断言）/
  `useD4SyncMode.spec.ts`（缓存/去重/forceRefresh）
- 证据刷新：`docs/operations/evidence/d4-bidirectional-acceptance/D4-{1..36}.json`（30 份，全量重跑）

---

## 2026-09-28 第六轮：D4-4 裁决复核（两条理由均已不成立）+ legacy OO 活口封堵 + 三处口径勘误

> **本轮触发**：用户要求「聚焦 D4-4」复核双向回写与公式管理的改进空间。逐条重算上方清册对 D4-4 的
> `⬜ single_html` 裁决后发现：**两条理由现均不成立**，且 D4-4 当时存在一条**活的 legacy OnlyOffice
> 通道**（能进、能编、改动不回 store）。本段同时勘误四处已过期的统计口径。
> **本轮只做低风险即修项 + 出 spec**；`d44-managed` 的真双向落地跨前后端且需 live PG 发布链，按铁律
> 「>500 行 / 3+ 组件 / 跨前后端 = 先写 spec」另立专项 spec，不在本轮直接改。

### ① D4-4 裁决两条理由逐条复核 —— 均已不成立

上方 `d4-adjustment-and-analysis-gap-closure` Task 1 的原裁决：「owner 已裁决 = single_html
（不可单元格级双向），理由实证成立：**hub store 被 A13/借贷平衡语义占用**、**模板无行身份 UUID 列载体**」。

**理由①「模板无行身份 UUID 列载体」→ 不成立**（openpyxl 实测三本含该 sheet 的册，几何逐字一致）：

| 项 | 实测值 |
|---|---|
| sheet 名 / 范围 | `营业收入调整分录汇总D4-4` / `A1:J23` |
| 表头 | R5，A~J **10 列**（调整事项说明/类别/报表项目/科目名称/附注项目/……/借方调整金额/贷方调整金额/索引/备注） |
| 数据区 | R6~R20（15 行空白），R21 = 提示文本（非合计行） |
| **数据区公式格** | **0**（该册仅 6 个公式在 R3/R4 表头引用「底稿目录」，不在受管区） |
| **UUID 载体候选** | **K/L/M/N/O 五列全空**；紧邻 `max_column`(J) 右侧第一个空列即 **K** |
| sheet-scope definedName | 0（两本）/ 4（一本，均非 `GT_` 前缀） |

「模板没有 UUID 列」是事实，但**从来不是阻塞**：D4-12 的落地方式正是 instrument 注入 definedName +
隐藏载体行，D4-8 是 definedName 锚定静态区。D4-4 有现成空列，**连隐藏行都不用加**，门槛低于 D4-12。
且该理由隐含的「前端无行身份」**已过期**：`useD4Adjustment.ts` 的 `D4AdjustmentRow` 已有 `rowId`
（`d4a-{base36}-{rand}`），`removeRow(rowId)` **按身份删**（非 index），真库 3 行全带 rowId。
对比 D4-7 当初的阻塞之一正是「前端 products 无 rowId，须补 rowId + backfill」—— **D4-4 这一步已不用做**。

**理由②「hub store 被 A13/借贷平衡语义占用」→ 不成立**（现读 `useD4Adjustment.ts` 287 行）：

- `debitTotal` / `creditTotal` / `balanceDiff` / `isBalanced` 全是 `computed`，**不落库**
- `pushToA13(rowIds)` / `publishAdjustment()` 只读 `rows` 后 `eventBus.emit`，**不写 store**
- `useAdjustmentCentralSync.ts`（218 行）**零写路径**（无 `api.post/put`、无 `.set()`、无 dispatchEvent）

落库的 `D4-4-rows` 就是纯粹的 10 字段行数组 JSON。对比 D4-1 审定表 —— 其 store 还要承载
`publish-to-tb` 发布门，语义占用**更重**，却已落地 `d41-managed`（同 sheet 双区 14 字段）。

**第三个可能阻塞（footer）亦排除**：`contracts.py:712` 为 `footer_anchor: FooterAnchorSpec | None = None`
（可选），且已有 **3 个无 footer 声明的 D4 provider 先例**（`phase5_d4_erp_check_sheet` /
`_other_margin_sheet` / `_product_margin_sheet`）。D4-4 无「合计」行不构成阻塞。

⇒ **结论**：D4-4 是 D4 剩余表中**几何最简、落地成本最低**的一张（单区动态行表、10 列 1:1、公式格 0、
无 footer、非转置、非静态矩阵），却是唯一被永久裁 N/A 的。已立专项 spec 承接（见 §④）。

### ② 🔴 已修：D4-4 的 legacy OnlyOffice 活口（本轮真实风险，优先于落地双向）

宿主 `GtD4OperatingRevenue.vue` 的 legacy 分支原条件为
`renderMode === 'onlyoffice' && !isD4DedicatedSyncSheet && currentSheet !== 'D4-5'`。逐项代入现算名单
（`isD4DetailSheet` 7 码 = D4-2/3/6/7/30/31/32；`isD4DedicatedSyncSheet` **33** 码；`KNOWN_HTML_SHEETS`
38 码）得 **legacy 实际命中集 = {D4, D4A, D4-4, D4-22A, D4-31T}** 共 5 张。其中 D4/D4A/D4-22A/D4-31T
无结构化 store（目录页 / 程序表 / 访谈示例），走 legacy「看原册」是**合理用途**；**只有 D4-4 有 store
载荷**。按本文件顶部判据三维自身的定义（「走 legacy `GtOnlyOfficeSheet`（未接桥＝**假双向/单向**）」），
用户可在 D4-4 点「在线编辑」正常进入 OO 并编辑，改动不回 HTML store —— **静默数据丢失**，比「不给入口」
更危险。`ooSheetName` 经 `resolveD4SheetLabel('D4-4', …)` 解析为真实存在的
`营业收入调整分录汇总D4-4`，即**确实打得开**，不是打不开。

**修复**（诚实降级优于静默丢失）：新增 `d4Constants.ts` 的 `D4_LEGACY_OO_BLOCKED_SHEETS`
（legacy 禁入名单**单一真源**，含三条入名单判据与移除条件），宿主据此：`renderMode` getter 对禁入表
恒 `'html'`（不能只靠模板分支挡 —— `dualMode.mode` 是宿主级单例且切 sheet 不重置，会残留
`onlyoffice` 使 segmented 选中态错位）、setter no-op、「在线编辑」选项恒 `disabled`、工具栏显示
`本表暂不支持在线编辑`（带 title 说明原因）。原 `currentSheet !== 'D4-5'` 单点特判**收敛进该名单**
（D4-5 已在 dedicated 内，本不可能命中，属冗余残留；行为逐字等价）。

守卫 `composables/__tests__/d4LegacyOoBlocked.spec.ts`（7 tests）采**双向判据**：正向 D4-4/D4-5 被挡
+ **反向变异证明**（D4/D4A/D4-22A/D4-31T 仍放行）—— 否则「把 legacy 通道整个堵死」也能让正向变绿，
而那会破坏 4 张无载荷表的合理用途。另 `d45SyncHostWiring.spec.ts` 原锚定字面量
`/currentSheet\s*!==\s*['"]D4-5['"]/` 的断言**等价更新**为行为层 + 门控源码层（守护意图不变）。
**变异反证已实做**：名单改空集 → 5 红（含「D4-4 被挡」），还原后 7 passed。

⇒ **D4-4 的 `⬜ single_html` 现在是"名实相符"的**：此前是「标 single_html 但实际有 OO 单向活口」。

### ③ 四处统计口径勘误（本轮现算，上方各段对应数字已过期）

| 项 | 上方记录 | **2026-09-28 现算** |
|---|---|---|
| 契约 `d4.revenue_detail.json` sheet 数 | 34 张 | **35 张**（新增 `d413-managed`） |
| 受管字段总数 | 751 | **775**（`text 327 / amount 417 / ratio 9 / boolean 20 / json 2`） |
| 宿主 `isD4DedicatedSyncSheet` 登记 | 32 张 | **33 张**（含 D4-13） |
| 裁决 `⬜ single_html/N/A` | **2 张**（D4-4 / D4-13） | **1 张**（仅 D4-4） |
| 平台 `legacy_fake_bidirectional` | 137 | **135** |

🔴 **其中最需更正的是 D4-13**：上方逐张清册记「D4-13 ⬜ evidence 裁 N/A（纯叙述文本表）」，但契约现已
含 `d413-managed`（2 字段 `process`/`conclusion`，静态 `defined_name_ref` 锚定 `GT_MANAGED_REGION_D413`，
provider `phase5_d4_erp_check_sheet.py`），前端 `D4TabErpCheck.vue` 已接（`d413-managed` ×2），宿主
dedicated 已含 `'D4-13'` ⇒ **D4-13 早已落地，该 N/A 裁决已作废**。故 ⬜ 实际只剩 D4-4 一张。

**另两处需一并知悉（非本文件记录，但与本文件结论相关）**：
- `_archive/14-d4-bidirectional-writeback/README.md` 的「L2 只做了 1 张（D4-2）」**已过期**：
  `evidence/d4-bidirectional-acceptance/d4-fleet-bidirectional-status.json`（captured 2026-09-25）实测
  **L1 passed 35/35；L2 `applied_store_ok=15` / `applied_store_miss=1`（D4-22）/ `empty_payload_skip=19`
  / `pipeline_failures=0`**。19 张 skip 的根因是真库该 item 无载荷（空表），属**需先 seed 才能验**，
  不是 wiring gap。另注意 `d4-l2-oo-to-html-all.json`（35 cases 批量）`store_ok_count=0` 而
  `d4-l2-oo-to-html-serial.json`（5 cases 串行）`applied_store_ok=4` —— **批量与串行结果不一致**，
  该差异尚无结论，留待 L2 专项复核。
- 第五轮 §⑥ 登记的「`sheet_name` 改记观测值——代码已改、未实测」**已兑现**：证据目录现算 44 个文件，
  其中 36 份有 `sheet_name` 且**全部为观测文本，退化为纯编码的 0 份**。

### ④ 🔴 口径盲区登记：entry 级 manifest 表达不了「entry 内部分 sheet 未迁」

`backend/data/workpaper_sync_entry_manifest.json` 现算 155 entry，**D4 仅 1 个 entry**
（`xlsx/gt-d4-operating-revenue`，`capability=bidirectional`、`migration_state=adapter_registered`）。
D4-4 没有独立 entry，故**不计入** `legacy_fake_bidirectional`(135)；但修复前它的运行时行为确是假双向。
⇒ **父 entry 标 `bidirectional` 会掩盖其下个别 sheet 仍走 legacy 的事实**，manifest 这一层无法表达。
本轮的 `D4_LEGACY_OO_BLOCKED_SHEETS` 是前端侧的补偿表达；根治需要 sheet 粒度的能力声明（建议纳入
平台总纲 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 考虑）。

### ⑤ 本轮其他修复（D4-4 分析的副产物）

1. **D4-4 导入导出漏 2 列（静默丢数据）**：`_SHEET_HEADERS["D4-4"]` 原 **8 列**，漏源模板 **F 列「……」**
   （前端 `placeholder`）与 **J 列「备注」**（`remark`）。后果不是报错而是导出不带出 + 导入不解析，
   前端 `safeParseRows` 对缺键兜底空串 ⇒ 用户填的内容无声消失。已补至 10 列（F 列导出头命名为
   「补充说明」），并把原内联导出分支抽成 `_export_d4_4_row()`（对齐 `_export_d4_1_row` 既有范式）。
   守卫 `backend/tests/test_d4_4_import_export_roundtrip.py`（12 passed）三层判据：列数/列序
   **直接读权威册 R5 表头对账**（钉死到物理列）+ `len(export) == len(headers)` 等长不变量 + 往返等值
   + **接线断言**（防「抽了函数但调用点没接上」—— 其余用例直调函数，不接线也会全绿）。
   **变异反证**：headers 改回 8 列 → 8 红。
2. **sheet label 错名 + 双源冲突**：`d4SheetLabels.ts` 的 `'D4-附注国企'` 值为
   `附注披露信息（国有企业）`，而三本权威册真名是 **`附注披露信息（国企）`**；因 `resolveD4SheetLabel`
   有 `includes('国企')||includes('国有')` 兜底，**错名长期不可见**（M 轮 MC-23「fallback 掩盖错名」同型）。
   已修 + 新建 `backend/tests/test_d4_sheet_labels_match_workbook.py`（6 passed）：**每个 label 值必须在
   `wp_templates/D/D4*.xlsx` 十本册 sheetnames 并集内逐字存在**（哨兵 `'D4'` 除外，白名单钉死为恰
   `['D4','D4-目录']`），两条自检防恒真。**变异反证**：改回错名 → 2 红。
3. **`generated/dSheetLabels.ts` 过期产物**：该文件 55 对中 48 对 sheet 名不含自身编码、22 个值在册内
   根本不存在（D4-1/2/3/4 全指向「主营业务收入审计程序表D4A（修订前）」等）。**根因不是脚本 bug 也不是
   ACNR 数据错** —— 现算 `global_catalog.json` 的 D4 条目 36 条**完全正确**（name 不以 code 结尾 = 0/36、
   不在册内 = 0/36），`generate_sheet_labels.py` 逻辑忠实；错的是**该文件从未随 catalog 重新生成**。
   且 CI 守卫 `check_sheet_labels_generated.py` **早已接进 `governance-checks.yml:233` 并一直是红的
   （exit=1）**，属「被忽略的红」。已重新生成 → **111 条**，守卫 exit 0；两侧 D4 段共同键 36 个
   **值冲突 31 → 0**；generated 值不在册内 **0 / 111**。该文件生产消费方现算仍为 **0**（正确但未被消费），
   保留不删（ACNR 体系产物 + 有 CI 守卫，删除需同步改 CI job）。

### ⑥ 诚实暴露：PRE-EXISTING 红（已实证与本轮无关）

`backend/tests/test_d4_price_import_formula_preserve.py::test_parse_d4_9_and_d4_11_field_mapping`
—— 以 bytes 级 `git show HEAD:` 临时替换 `_d4_import_export.py` 复跑，HEAD 版同样 `1 failed, 4 passed`
⇒ PRE-EXISTING。根因判断为**生产代码正确、测试输入过期**：`_parse_d4_9_row` 现返回含 `rowId`（行身份）
与 `_period`（本期/上期），是 `d4-9-customer-structure-bidirectional-writeback` 双区落地的正确产物；
而测试仍传 4 元组 `("客户乙", 200, 5, "3")`，D4-9 headers 加列后位置错位（实测 `name='5'`、`amount=3.0`）。
owner = D4-9，不属 D4-4 范围，按第五轮先例不擅自扩范围硬修，登记为独立待办。

### ⑦ 本轮改动文件

- `audit-platform/frontend/src/components/workpaper/composables/d4Constants.ts`（legacy 禁入名单单一真源）
- `audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue`（门控接线 + 降级提示）
- `audit-platform/frontend/src/components/workpaper/composables/d4SheetLabels.ts`（国企附注错名）
- `audit-platform/frontend/src/generated/dSheetLabels.ts`（重新生成，55 → 111 条）
- `backend/app/routers/wp_render_strategies/_d4_import_export.py`（D4-4 补 2 列 + 抽 `_export_d4_4_row`）
- 守卫：`d4LegacyOoBlocked.spec.ts`（新，7）/ `test_d4_4_import_export_roundtrip.py`（新，12）/
  `test_d4_sheet_labels_match_workbook.py`（新，6）/ `d45SyncHostWiring.spec.ts`（断言等价更新）

### ⑧ 运行时实测（2026-09-28，start-dev.bat 全栈 + OO 容器已启，Playwright MCP）

环境探活：后端 9980 `healthy`（postgres ok / redis ok）· 前端 3030 200 · OO 8080 `true` ·
平台探针 `/api/workpapers/onlyoffice/health` → `{"healthy": true, "active_sessions": 0, "max_sessions": 10}`。
用例场地 = project `0ec33ac9…a49` / wp `b3ab3c46…923f`（wp_code `D4`，真库 54 行载荷）。

**正向（D4-4 禁入生效）✅**：tab「营业收入调整分录汇总D4-4」选中后，
`radio "结构化视图" [checked]` + `radio "在线编辑" [disabled]` + 标签
`本表暂不支持在线编辑`（title = 「本表尚未接入双向同步，在线编辑的改动无法回写到结构化数据，
故暂不开放，以免数据丢失」），**console 0 errors**。截图 `d4-4-legacy-oo-blocked-verified.png`。

**反向（未一刀切堵死）✅**：D4-2（宿主桥）与 D4A（legacy 合理用途）的「在线编辑」均**无 `[disabled]`、
有 `cursor=pointer`、无禁用标签** —— 证明禁入名单只挡该挡的那一张。

#### 🔴 实测抓到一个设计缺口（已补进 spec Req 2.5 / 5.7 + design §5.1b + Task 13b）

`D4TabAdjustment.vue` 的 `el-table` 恰 **8 个业务列**（DOM 取 `thead th` =
`[摘要, 分类, 报表项目, 会计科目, 附注项目, 借方, 贷方, 索引号]`，源码注释亦编号 1~8），
而模板有 **10 列**、`D4AdjustmentRow` 类型有 **10 个字段**、`safeParseRows` 解析 **10 个**、
导入导出（本轮已补）**10 列** —— **只有 UI 少 `placeholder`(F「……」) 与 `remark`(J「备注」) 两列**。

含义：若把 10 列全纳入受管而 UI 仍 8 列，用户在 OO 侧改 F/J → 回写进 store → 切回结构化视图
**看不见**，表现为「改动丢了」（实为存了但不可见），**比不回写更难排查**。而「这 2 列不纳入受管」
同样被拒 —— 模板里真实存在这两列 ⇒ OO 侧可编辑 ⇒ 不纳入则 materialize 会用 store 旧值覆盖用户输入。
⇒ 唯一正确解是**五层一致**（模板 / 类型 / 解析 / UI / 导入导出 都 10 列），已写进 spec Task 13b。

⚠️ **同名陷阱（记录以免后人误判）**：该文件有 6 处 `placeholder="摘要"` 之类，那是 **el-input 的
占位文本属性**，与 `D4AdjustmentRow.placeholder` **字段**同名却无关。只 grep `placeholder` 会误判
「该字段已在 UI」。判断某受管字段是否有 UI 列，须看 `el-table-column` 的 `label` 与
`row.<field>` / `updateCell(..., '<field>', ...)` 绑定，不能看占位属性。

#### 🔴🔴 实测发现 D4 entry 的 materialize 当前处于 500（与本批无关，但阻塞全部 D4 在线编辑）

在 D4-2（宿主桥）真实点「在线编辑」：`store-projection` **200** → `pending-mutations` **200** →
`materialize` **500**（自动重试 3 次全 500）。响应体：

```
error_code: roundtrip_projection_mismatch
message: staged representation 反读出未提交的受管字段
  ['adjudication_main_rows/xsheet-main-L2MARK-D4-2-4fel/current_unadjusted', ...]（共 338 个）
  —— 受管区域被写入了不属于本次 projection 的值
```

**根因链**：字段身份里的 `L2MARK-D4-2-4fel` / `L2MARK-D4-2-nmna` 是 **L2 验收 e2e 写入的标记**
（`e2e/d4-l2-oo-to-html-all.spec.ts` 与 `e2e/d4-l2-fast-batch.spec.ts` 里的
`L2MARK-${c.code}-${Date.now()}`）。历史批量 L2 跑测时把标记写进了 OO canvas → 进了 xlsx staged
representation，但 HTML store 侧没有对应行（**正是 `store_ok_count=0` 的表现**）⇒ 现在 materialize
的往返校验反读出 338 个不在当前 projection 里的受管字段 ⇒ fail-closed 500。

🔴 **这解释了本文件 §③ 登记的那个未解之谜**：`d4-l2-oo-to-html-all.json`（35 cases 批量）
`store_ok_count=0` 而 `d4-l2-oo-to-html-serial.json`（5 cases 串行）`applied_store_ok=4` ——
**批量在同一 entry 上连写 34 处，污染了 representation，后续 materialize 全部失败**；串行每次只写
一处且逐次确认，故能通。⇒ 「批量 vs 串行不一致」不是并发 contention，是**测试数据残留导致的
representation 污染**。

**与本批无关的静态实证**（不是推理）：materialize 链路五个核心模块
（`materialize_coordinator` / `excel_materialize` / `adapters/excel` / `phase5_d4_revenue_detail` /
`oo_to_html`）**全部不 import** `_d4_import_export`；`workpaper_sync` 全目录 import 它的文件 **= 0**；
反向 `_d4_import_export.py` 既不 import `workpaper_sync` 也不含 `materialize`。而本批后端改动
**只有** `_d4_import_export.py` 一个文件。

**建议处置（另立，不在本批）**：①清理 staged representation 里的 L2MARK 残留行（或重新 rematerialize
到干净代际）②给 L2 e2e 加**测试后清理**（写标记 → 验证 → 还原原值），否则每跑一次批量 L2 就再污染一次
③批量 L2 改为串行或每 case 独立 entry 代际。

> ⚠️ 另记：切底稿时有 `PATCH /api/editing-locks/workpaper/{wpId}/heartbeat` **404** 的 console error。
> 端点与注册都存在（`routers/editing_locks.py` + `router_registry/collaboration.py`），404 属「无活跃锁
> 可续期」的业务响应，非路由缺失；前端未静默处理该 404 而已。与本批无关。

---

## 2026-09-28 第七轮：materialize 500 的根因定位 + L2 e2e 根治（数据清理受阻于引擎缺口）

> 承接第六轮 §⑧ 登记的「D4 entry materialize 500」。本轮把根因挖到底、**根治了"再污染"**，
> 但**现存污染的清理受阻于一处平台级引擎缺口**，按「不擅自弱化 fail-closed 判据、不 hack 数据」
> 原则登记待裁决，未硬改。

### ① 根因链（三层，全部实证）

1. **`useD4Adjudication.ts:691`**：D4-1 派生行身份 = `` `xsheet-${section}-${labelKey(label)}` `` ——
   **行身份由业务字段 `label` 派生**。现算：387 个 `rowId`/`rowKey` 模板串命中里，**这是全前端
   唯一一处「用业务字段值派生行身份」**（其余全是常量 / index / 时间戳 / section key 派生）。
2. **L2 e2e 的 `SKIP_KEYS` 不含 `label`** ⇒ 测试挑"安全格"时选中 label 列 ⇒ 写入 `L2MARK-…`
   ⇒ **行身份漂移** ⇒ 在 xlsx 里造出 store 侧不存在的孤儿行。
3. **污染由 gen 165（2026-09-28 04:58 的 `content_commit`）固化**，不是 9-25 的历史遗留：
   那次 commit 的 intended 是 **merged projection**（store + OO 变更），OO 侧有 L2MARK 行故不报错；
   而"用户点在线编辑"时 materialize 的 intended 是 **flushHtml 给的纯 store projection**，
   没有这些行 ⇒ `extra` ⇒ fail-closed 500。

xlsx 实测（gen165 artifact，L2MARK 共 **18 处**）：

| sheet | cell | 值 | 性质 |
|---|---|---|---|
| 营业收入审定表D4-1 | **W20 / W21** | `xsheet-main-L2MARK-D4-2-{nmna,4fel}` | **UUID 身份载体列 = 孤儿根源** |
| 营业收入审定表D4-1 | A20 / A21 | `L2MARK-D4-2-{nmna,4fel}` | label 列 |
| 营业收入审定表D4-1 | X36 | `xsheet-other-L2MARK-D4-3-2wi7` | store 里**有**此身份 ⇒ **非**孤儿 |
| 主营业务收入明细表D4-2 | A12 / A24 | `L2MARK-D4-2-*` | 产品名被改写（store 的 `D4-2-rows` 无 L2MARK） |

D4-1 共 26 个行身份 = 8 个 `GTROW-D41*`（instrumentation mint）+ 18 个 `xsheet-*`（含 2 个 L2MARK 孤儿）。

### ② 🔴 平台级引擎缺口（本轮最重发现，待裁决）

**`excel_materialize` 没有「清空 substrate 上 store 已无对应的受管行」的能力。**

- 引擎的 `orphan` 是**反向**概念：`orphan = [身份 for 身份 in projection.row_keys if 该身份在 substrate 上无物理行]`
  ⇒ 触发**插行**。反方向（substrate 有、projection 无）**无任何处理**。
- `tombstoned_row_keys` 看似是出口，实测**不是**：`_scan_row_identities` 只把它加进 `taken`
  （防 mint 时复用已删 ID）+ 算 `reused_tombstones`，**不排除那些行**。且
  `publish_first_generation` 恒传 `()`（注释自陈「首版没有任何已删除行」）。
- `_scan_row_identities` 对「UUID 列空但业务列有内容」的行按 `assign_new_id` **mint 新身份**
  ⇒ 这些 mint 出来的身份进 extracted projection ⇒ 与 store 比就是 `extra`。

**后果（比本次事故更广）**：只要 xlsx 与 store 的受管行集不一致，**该 entry 的「点在线编辑」就永久
失败**，而「从 OO 侧 forcesave」却仍能成功（intended 是 merged projection）—— 这是一处**结构性不对称**，
且形成死锁：进不去 OO 就无法用 OO 侧路径修复。
⚠️ **推论（需独立验证）**：按此机制，**用户在 HTML 侧删一行**就会造成 store 少行 / xlsx 多行 ⇒
下次点在线编辑即 500。这条比测试污染严重得多，建议优先验证。

### ③ 两条清理路径均被该缺口挡住（已实测，非推理）

| 路径 | 结果 |
|---|---|
| 增量 materialize（点在线编辑） | **500** `roundtrip_projection_mismatch`，extra **338** 个 |
| 模板重建 `d43_rematerialize_dual_sheet.py --apply --force` | **同样失败**，extra **77** 个，但 table 变成 `d4_10_rows/GTROW-D410-0013+` |

模板重建为何也失败：`stage_instrumented_substrate` 的 `source_bytes = provider.read_authoritative_template()`
⇒ 从**权威模板**重建；而权威模板 `重要客户销售价格分析D4-10` 的 **R13~R33 预置了 21 行示例数据**
（`大额客户一` / `产品1`…），而 store 的 `D4-10-data` 是 **`{"rows": []}`** ⇒ 这 21 行模板示例行
被 mint 身份后全部变成孤儿。
⇒ **「模板自带示例数据 + store 该表为空」的 sheet，从模板重建必然 extra 失败**。D4 组里这类 sheet
不止 D4-10，需普查。

✅ **失败无副作用**：`--apply --force` 抛异常前未 commit，实测 DB 仍 gen 165 / 190 reps /
latest 仍 04:58 ⇒ 事务正确回滚，**无半应用态**。
✅ **已备份**：190 个历史 representation 副本存于 `%TEMP%\d4-remat-backup-20260928`；
原目录旧代际本身亦天然保留（gen 1~165 的 xlsx 全在）。

### ④ 本轮已交付：L2 e2e 根治（防再污染，零风险）

- `e2e/d4-l2-oo-to-html-all.spec.ts`：`SKIP_KEYS` **加 `label`**；把原先只在 amount 分支单独判、
  **文本分支漏判**的 `group_label` 并入集合；补完整根因注释。
- `e2e/d4-l2-fast-batch.spec.ts`：`SKIP_KEYS` 加 `label`。
- **新增测试后还原块**：校验完立即写回 `oldValue` + 再 forcesave 一次（`L2_NO_RESTORE=1` 可关），
  `SheetResult` 加 `restored: 'ok'|'skipped'|'type_fail'|'save_timeout'`。
  不还原的后果不是"测试不干净"而是 **L2MARK 永久留在真实业务数据里**（审计师会看到
  `L2MARK-D4-3-2wi7` 这种产品名）并随 content_commit 一代代传下去。
- 新建守卫 `src/components/workpaper/composables/__tests__/l2RowIdentityGuard.spec.ts`（8 tests）：
  从 `useD4Adjudication.ts` 源码**现算**身份派生源字段（**不写死 `['label']`**），断言其必须全部
  出现在两个 e2e 的 `SKIP_KEYS` 里 ⇒ 将来新增别的派生源也会被抓。含 2 条防恒真自检。
- 验证：`npx playwright test --list` 成功解析两个 e2e（转译通过）；
  **变异反证已实做**（摘掉 `label` → 2 红含解释消息，还原后 8 passed）。

🔴 **两处工具教训**：
① `npx tsc --noEmit -p tsconfig.json` 对 `e2e/` 是**恒真检查**（`include` 只有 `src/**`），
   差点当成有效验证 ⇒ e2e 的语法/转译校验改用 `npx playwright test --list`。
② 守卫首版断言 `/colKey === 'group_label'/` **命中了自己的注释**而假红 ⇒ 已加 `stripComments()`。
   这是「grep 命中必判注释 / 代码」铁律的同型，**在自己写的守卫里同样会踩**。

### ⑤ 待裁决的解阻选项（均需独立 spec，本轮不做）

| 选项 | 说明 | 风险 |
|---|---|---|
| (a) 引擎补「store 无对应的受管行 → 清空业务内容 + 清 UUID」 | 治本，且能一并解决「HTML 侧删行」这条更广的缺陷 | 动核心引擎，需完整 spec + 变异反证 |
| (b) 回退代际到 gen 164（09-25 14:44，污染前） | 见效快 | 丢 gen 165 的内容；且若 gen 164 也已行集不一致则无效 |
| (c) 一次性运维工具「按身份清除指定孤儿行」 | 范围可控、可审计 | 需新工具 + 只治本次症状不治根因 |

> 建议顺序：先验证 ②的推论（HTML 侧删行是否也会卡死）。若成立，(a) 的优先级应显著提高 ——
> 那不是"测试污染的善后"，而是**一条用户日常操作就能触发的 entry 级卡死**。

### ⑥ 🔴 更正本轮 §② 的结论：不是「引擎没有删行能力」，而是「能力已建、接线缺失」

§② 写的「`excel_materialize` **没有**清空/删除 substrate 上 store 已无对应受管行的能力」
**表述不准确，就此更正**。准确事实（逐项实证）：

**引擎有完整的删行能力**，在 `app/services/workpaper_sync/excel_workbook_row_change.py`
（spec `excel-workbook-wide-row-change-propagation` 的产物）：

| 导出 / 实现 | 位置 |
|---|---|
| `build_delete_plan` | L1903（`__all__` 导出） |
| `resolve_deleted_row_keys` | L1785（`__all__` 导出，名字即「算出哪些行被删了」） |
| `shrink_sheet_rows(xml, *, delete_at, count)` | L1836 |
| `_validate_delete` / `is_deleted_row` / `_delete_remap` | L546 / L627 / L2265 |

且**测试覆盖充分**：`backend/tests/workpaper_sync/` 下 **14 个** `test_workbook_row_change_*` /
`test_multi_sheet_workbook_change_merge` / `test_sibling_table_ref_row_shift` 等文件，
其中 `test_workbook_row_change_delete.py` 覆盖 Property **P10~P15 + P35**，并已在 D2（删得成的
正常路径）与 K11（100% 阻断的 fail-closed 路径）**两个载体**上双向取证。

**真正的缺口是接线** —— 各生产消费方实际 import 的符号：

| 消费方 | import 的符号 |
|---|---|
| `excel_materialize.py` | `plan_workbook_row_change_for_insert` · `PropagationDriftError` · `_escape` ← **只有 insert** |
| `excel_extract.py` | `normalise_propagated_part` |
| `adapters/excel.py` | `merge_workbook_row_change_propagations` |
| `adapters/base.py` · `g7_oo_crash_if_neutralize.py` | 无直接 import |

⇒ **`build_delete_plan` 与 `resolve_deleted_row_keys` 在生产代码里零消费方**（全仓唯一调用方
是它们自己的测试）。`excel_materialize.py` 全文唯一含 "delete" 的地方是 L1870 的一句**注释**
（提到 `delete_policy=tombstone`）。

**这与 memory 里 D4-8 的 `merge_d48_from_projection`「全仓唯一调用方是自己的测试」完全同型** ——
「能力已建 + flag 已翻 + 测试全绿」≠ 接线完整。本轮是该模式的第二个实例，且后果更重：
materialize 只插不删 ⇒ store 少行时 substrate 多出的行留着 ⇒ extract 反读出来 ⇒ `extra` ⇒ 500。

#### 修复形状（接线，非新建能力）

在 `plan_managed_writes` 的行集一致性段（现有 §6.2「orphan → 插行」与 §6.6「行集一致性」之间）
补反方向处理：对 `substrate 有身份 / projection 无该身份` 的行，经 `resolve_deleted_row_keys`
判定后走 `build_delete_plan` + `shrink_sheet_rows`。

🔴 **但有一个必须先由设计裁决的语义问题，不能由实施者单方面定**：
materialize 如何区分下面两种「projection 里没有这行」？

| 情形 | 应有行为 |
|---|---|
| 用户在 HTML 侧**删了**一行 | 应删除 substrate 上的物理行 |
| 该行是**模板预置示例数据**（如 D4-10 的 R13~R33「大额客户一/产品1」，store 恒 `rows: []`） | 删掉是否正确？模板占位行被删后，用户下次想填就没有模板样式行了 |

两者在 projection 层**无法区分**（都表现为「substrate 有、projection 无」）。需要显式的删除意图
或「模板预置行」标记才能分流。而现状是前端 bridge **只传 `{sheetKey, expectedRevision, projection}`**
（已现读 `useWorkpaperSyncBridge.ts` / `workpaperSyncApi.ts` 确认，无 tombstone / deleted_rows 字段），
即**删除意图根本没被传到后端**。

⇒ 故本轮**不直接改引擎**：这是跨前后端的设计级变更（`excel_materialize.py` 3600+ 行核心路径，
影响所有 entry），且「接错会静默删用户数据」比现在的 fail-closed 500 危险得多。
按铁律另立 spec，建议名 `workpaper-sync-row-delete-wiring`，范围：
①前端传删除意图 ②`resolve_deleted_row_keys` / `build_delete_plan` 接进 `plan_managed_writes`
③模板预置行与用户删行的分流判据 ④全 entry 回归 + 变异反证。

#### 本轮两次自我更正（方法论教训）

1. 先断言「引擎没有删行能力」—— **错**。根因：只在 `excel_materialize.py` 里 grep，没查模块全集。
2. 再断言「`excel_workbook_row_change` 生产消费方 = 0」—— **也错**（真值 5）。根因：
   PowerShell `Select-String -Path backend\app\**\*.py` 的 `**` **不递归**，得到假零。
   ⇒ 「结构性零须配变异证明」这条铁律，对**工具本身的口径**同样适用：报 0 之前先用另一条通路
   （Python `rglob`）复核一次。本轮两个错误结论都是"零/不存在"型断言，且都源于扫描面不足。

---

## 2026-09-28 第八轮：materialize 500 的根因**更正** —— L2MARK 只占 1.5%，主因是行身份不稳定 + 只插不删

> **本轮定位**：第七轮把 materialize 500 归因为「L2 e2e 造的 L2MARK 孤儿行」。本轮把 `extra`
> **字段级全集**算出来后，该归因被**证伪**：L2MARK 只占 402 个 extra 字段中的 **6 个（1.5%）**。
> 真正的主因是一条此前完全没看见的链：**行身份每次重建都重新 mint** ⇒ substrate 累积同一份
> 业务数据的多个副本 ⇒ 叠加「materialize 只插不删」⇒ 永久性 `roundtrip_projection_mismatch`。
>
> 🔴 **两个结论反转**（与第七轮相反，以本轮为准）：
> 1. **删除孤儿行是安全的** —— 三批 `d4r-*` 内容逐字相同，是重复副本而非独有数据；
>    第七轮「删会丢用户数据」的担忧**不成立**。
> 2. **真实风险是反向的** —— 不删则 entry 永久不可用，且孤儿**仍在持续新增**
>    （最新一批时间戳是本日 12:57:59）。

### ① `extra` 字段级全集：402 字段 / 73 身份

口径与生产判据逐字对齐（`content_mutation.py:1868` 的 `extra = sorted(set(right) - set(left))`）：

- `left`（intended）= live `store-projection` 端点返回的 `projection.values`，**909** 字段
- `right`（extracted）= 对 gen165 **已发布 substrate 字节**跑真 `adapter.extract`，**1311** 字段
- 口径自证：`common = 909`、`missing = 0` ⇒ 两侧 key 命名空间完全可比（若 common=0 则清单不可信）

| table | extra 字段 | extra 身份 | 性质 |
|---|---|---|---|
| `revenue_detail_rows` | 281 | 26 | **14 个 `d4r-*` 重复副本** + 12 个 `GTROW-D42-*` |
| `d4_10_rows` | 49 | 21 | `GTROW-D410-*`，模板占位骨架 |
| `customer_prior_rows` | 20 | 10 | `GTROW-D49P-*` |
| `customer_current_rows` | 18 | 9 | `GTROW-D49C-*` |
| `invoice_compare_rows` | 12 | 12 | `GTROW-D423-*`（仅 `month` 一个字段） |
| `key_indicator_rows` | 12 | 12 | `GTROW-D422-*`（仅 `metric_name`） |
| `adjudication_main_rows` | **6** | **2** | **`xsheet-main-L2MARK-*` —— 第七轮以为的主因，实占 1.5%** |
| `d4_31_interview` | 4 | 1 | `GTROW-D431-0005` |

⇒ 三类孤儿，性质与处置**各不相同**，不能一刀切：

| 类 | 身份数 | 来源 | 可否安全丢弃 |
|---|---|---|---|
| A `d4r-*` 旧批 | 14 | 前端 rowId 生成器每次重建都 mint 新值 | **可** —— 内容与 store 现存批逐字相同 |
| B `GTROW-*` | 57 | instrumentation 给**模板占位行** mint 的身份 | **可** —— 占位骨架非业务数据 |
| C `xsheet-*L2MARK*` | 2 | L2 e2e 写业务字段致身份漂移（第七轮已根治再污染） | **可** —— 测试垃圾 |

### ② 主因实证：同一份业务数据在 substrate 上有 **3 个副本**

D4-2（`主营业务收入明细表D4-2`）的身份载体列 `W` 上有 **21 个 `d4r-*` 行**，按时间戳分三批
（`d4r-{Date.now().toString(36)}-{random}`，解码后）：

| 批次 | 时间戳解码 | 行数 | substrate 行号 | 在 live store 里 |
|---|---|---|---|---|
| `d4r-mtl69x8j-*` | 2026-09-03 14:57:08 | 7 | R24~R30 | ❌ 孤儿 |
| `d4r-muclbqzb-*` | 2026-09-22 19:28:14 | 7 | R31~R37 | ❌ 孤儿 |
| `d4r-muks1021-*` | **2026-09-28 12:57:59** | 7 | R38~R44 | ✅ 唯一在 store 的一批 |

**三批内容逐字相同**（这是「可安全丢弃」的判据本身，不是推测）：
`营业收入_批发_分销` / `_纯销` / `_终端` / `_服务费及其他` / `_物业与租赁_物业` / `_租赁` /
`_物流_仓储`，且 12 个月金额完全一致（如纯销 `B=55287496.99 … N=764410208.16` 三批逐值相同）。
唯一差异是第一批 R24 的 `A` 列已被 L2 e2e 改成 `L2MARK-D4-2-4fel`（即 C 类污染的来源）。

live `store-projection` 的 `revenue_detail_rows` 只有 **7 行 = 单批 `muks1021`**
⇒ store 被**整批替换**，前两批在 store 侧已不存在，但在 substrate 上被永久保留。

**DB 侧交叉实证**（`checklist_responses`，只读查询）：
`item_id='D4-2-rows'`、`remark` 1739 B、`updated_at` 2026-09-28 05:48:32 UTC（= 13:48 本地）、
`remark LIKE '%rowId%'` 为 **True** ⇒ store 里的行**带** `rowId` 字段，
故 `useD4RevenueDetail.ts:78` 的 `raw.rowId || generateRowId()` fallback **未触发**，
整批替换发生在别处（`importFromLedger` 是 push 语义、提示语明写「现有行保留」，也不是它）。
⇒ **替换者尚未定位**，这是本轮留下的唯一未闭合问题（见 ⑤）。

### ③ 机制层：为什么孤儿只增不减

`materialize` 的 `orphan` 是**反向**概念（projection 有、substrate 无 ⇒ **插行**）；
substrate 上「store 已无对应」的受管行**没有任何代码会去清除**。第七轮已实证接线缺口：
`excel_materialize.py` 只 import `plan_workbook_row_change_for_insert`，
而 `build_delete_plan`(L1903) / `resolve_deleted_row_keys`(L1785) **生产零消费方**。

⇒ 每次「行身份漂移一次」= substrate 上永久多留一批行。本轮 D4-2 的 3 批就是这条链跑了 3 次的
**端到端实物证据**。第七轮把「HTML 侧删行也会卡死 entry」列为**未验证的推论**，
本轮据此**升级为已证实**（不再是仅有机制层面的两条间接实证）。

### ④ rematerialize 被堵死的真原因（更正第七轮的描述）

第七轮记录 `--apply --force` 报 77 个 `d4_10_rows` extra，归因为「模板预置了 21 行示例数据」。
本轮直读权威模板 `backend/wp_templates/D/D4 收入底稿.xlsx` 的 `重要客户销售价格分析D4-10`，
把这件事**精确化**（原描述「示例数据」不够准，它其实是**公式骨架**）：

- R13~R33 内容：`A` 列序号 1~7、`B` 列 `大额客户一`~`大额客户五` / `异常客户X` / `异常客户Y`
  （只在每组首行）、`C` 列 `产品1/2/3`、`H` 列 `0`，而 **`E`/`G`/`J`/`M` 四列是 `=IF(...)` 公式**
- 本 sheet **无 Excel Table（`ws.tables` 为空）、无 definedName（44 个里命中 D4-10 的为 0）、
  `xl/tables/` 下 0 个 part** ⇒ 受管区完全由**契约显式声明**，不是从 Table 推出来的
- extract 把 `B`/`C`/`H` 的占位文本读成 `customer` / `product` / `unit_price` 业务值

⇒ 与 store 的 `D4-10-data = {"rows": []}` **必然冲突**。这不是「偶然撞上脏数据」，
而是**模板占位骨架与受管区语义的结构性冲突**：只要受管行区内预置了非空占位内容，
「从权威模板重建」这条清理路径就恒被堵死。⇒ 两条清理路径（增量 / 模板重建）
被**两个不同的**缺口挡住，不是同一个（第七轮记作「同一缺口」，此处更正）。

### ⑤ 本轮未闭合 + 上游缺陷（`importFromLedger` 的身份幂等性）

**未闭合**：谁整批替换了 `D4-2-rows`（使 store 只剩最新一批）尚未定位。
已排除 L78 fallback（store 带 `rowId`）与 `importFromLedger`（push 语义）。

**上游缺陷（已定位，需裁决）**：`useD4RevenueDetail.ts:308` 的 `importFromLedger`
对每个台账产品**无条件** `rowId: generateRowId()`，即使该产品行已存在。
⇒ 同一产品重复导入即产生**内容相同、身份不同**的行，是「持续制造孤儿」的上游。
改它属**行为变更**（现提示语承诺「现有行保留」，去重/复用 id 会改变既有语义），
故本轮只登记不擅改，留待裁决。备选：按 `product` 名复用已有行 `rowId`（幂等导入）／
导入前提示已存在同名产品并让用户选择覆盖或新增。

### ⑥ 探针口径教训（两条独立通路互校才发现漏报）

身份级普查探针 `_d4p_orphan_census.py` 的前缀族学习用了 `len(token) >= 4` 过滤，
把 **`d4r`（长度 3）整族漏掉** ⇒ 该探针报「孤儿 288 个、其中 L2MARK 2 个」，
把本轮真正的主因（14 个 `d4r-*`）**全部漏报**。是字段级探针（走真 `adapter.extract`）
才把它抓出来。

⇒ 教训：**「自造匹配器 + 单一通路」会系统性漏报，且漏掉的恰好可能是主因**。
凡要下「某类东西共 N 个」的结论，必须有第二条独立通路（最好是走生产代码路径）交叉验证；
本轮两条通路的结论不一致（288 vs 73 身份），正是互校起作用的信号。

另：本轮违反过自己既有的铁律 —— 用 `python -c` 跑含正则的核验，导致终端卡死 120s 超时
（PowerShell 把引号/反斜杠解析坏了）。已改回「含正则一律写探针文件」。

### ⑦ 归因更正：当前 500 形态是 commit `e52e5e5ce`（本日 13:39）的副作用，且是一个两难

第七轮把 500 归因为「gen 165 的 `content_commit`（本日 04:58）固化了 L2MARK 污染」。
本轮查到**另一个并发会话**的提交改变了这件事的性质：

```
e52e5e5ce  2026-09-28 13:39:05 +0800  Kiro
fix(d4-sync): overlay 行集合以 store row_keys 为权威，不再从旧 substrate 带入已删除行
```

该提交改了 `projection_first_publication.py` 的 overlay 规则
（`baseline ⊕ store` 的 `row_keys` 合并）：

- **改前**：按**并集** ⇒ baseline 的旧行被带回 intended
- **改后**：`store` 声明了该 table → **store 行集为权威**；store 未声明的 table → baseline 原样

改动的动机在其注释里写得很清楚，而且引用的实测数字**与本轮完全吻合**：

> 若按并集合并，旧行全部被带回——materialize 写 33 行进只有 12 行数据区的模板，
> 产生大量空行 / 旧数据残留（**2026-09-28 D4-2 实测 7→33 行事故形态**）。

本轮独立实测的 D4-2：store **7** 行 ｜ substrate **21** 个 `d4r-*` + **12** 个 `GTROW-D42-*`
= **33** 个身份 ⇒ 与注释里的 `7→33` 逐值一致。

**完整时间线**（三件事都发生在本日）：

| 时刻 | 事件 | 后果 |
|---|---|---|
| 12:57:59 | `d4r-muks1021-*` 批身份生成 | store 变成 7 个全新身份，旧两批成孤儿 |
| **13:39:05** | `e52e5e5ce` 把 overlay 改为 store 权威 | 修掉「33 行写进 12 行数据区」的写爆 |
| 13:48:32 | store `D4-2-rows` 落库（7 行） | intended 定格为 7 行 |

⇒ **这是一个两难，两条路都不通**：

| overlay 规则 | 后果 |
|---|---|
| 并集（改前） | 旧行被带回 intended ⇒ materialize 写 33 行进 12 行数据区 ⇒ 写爆 / 旧数据残留 |
| store 权威（改后） | 旧行不在 intended ⇒ extract 仍读得到 ⇒ `extra` 402 ⇒ **materialize 恒 500** |

缺的是**第三件事**：把 substrate 上 store 已不认领的受管行**清掉**。
只要它缺位，读方向（overlay 主动丢弃旧行）与写方向（materialize 只插不删）就永久不自洽。
`e52e5e5ce` 的注释预期「模板脚手架行…由 identity carrier 机制自动处理…roundtrip 校验中
extract 读到但投影没有的 **protected** 字段会被豁免」—— 本轮 402 个 extra 即该预期的**反例**：
它们是 `customer`/`product`/`period_total` 一类**业务字段**，不是 protected，不在豁免范围内。

⇒ 修复落点三选（详见 spec）：

| 落点 | 做法 | 评价 |
|---|---|---|
| (a) materialize 侧 | 把 store 声明的 table 的受管区**收缩到 store 行集** | **正解**，与 overlay 规则严格对偶；但动核心引擎 |
| (b) 判据侧 | 豁免「store 声明的 table 内、store 未列出的行」的字段 | 止血；但 substrate 永久残留旧行，OO 侧用户仍看见 33 行 |
| (c) overlay 侧 | 回退成并集 | **不可行**，直接复现 33 行写爆事故 |

🔴 **(a) 的分流判据不需要新协议**（这更正第七轮「必须先传删除意图才能分流」的判断）：
判据可直接取自 projection 自身 —— **凡 store 在本次 projection 的 `row_keys` 里声明了该
table，则该 table 受管区内 store 未列出的受管行即应被清除；store 未声明的 table 一律不碰**。
这与 overlay 的取舍规则是同一条规则的两个方向，因此不会误删（store 没声明 ⇒ 不动）。
真正需要裁决的只剩一件小得多的事：D4-10 这类 `rows: []` 的表，清除占位骨架后
用户下次填写就没有模板样式行了 —— 这是 UX 取舍，不是正确性问题。

---

## 2026-09-28 第九轮：extra 真实规模的**再更正**（77 不是 402）+ 方向裁决 C + store_mirror 抽取

> **本轮定位**：第八轮把 extra 记作 402 并据此立了一个「公式格豁免」任务。本轮用**生产判据
> 口径**重算后，两件事都被证伪：真实 extra 是 **77**，且公式格豁免**本来就存在并生效**。
> 随后确定根治方向为 **C（materialize 侧收敛）**，并先行完成了一项独立的正确重构
> （`store_mirror` 抽取）。

### ① 🔴 最重要的更正：裸差集口径让 extra 连续两轮虚高

第八轮（402）与本轮首算（126）都用了**裸差集**：

```python
extra = set(extracted) - set(intended)        # ❌ 没应用生产豁免
```

而生产判据 `_assert_roundtrip_equivalent`（`content_mutation.py:1819`）在算 extra **之前**
先跑 `_managed()`，剔除两类字段：

```python
word_only  = {spec.stable_field_key for spec in contract.all_fields()
              if spec.mode is FieldMode.word_only}
protected  = {spec.stable_field_key for spec in contract.all_fields()
              if spec.mode in PROTECTED_MODES}          # {formula, auto_source}
left, right = _managed(intended), _managed(extracted)   # ← 豁免在此生效
extra = sorted(set(right) - set(left))
```

实测（D4 契约）：

| 口径 | extracted | intended | extra |
|---|---|---|---|
| 裸差集（本轮首算，错） | 1311 | 1185 | **126** |
| `_managed`（生产判据，对） | 1238 | 1161 | **77** |

差额 **73** 全是公式字段，且**全部已被现有豁免命中**（逐 key 验证）：
`period_total` 33 + `amount_ratio` 20 + `quantity_ratio` 20，
对应 D4 契约里 5 个 `mode=formula` 模板（`revenue_detail_rows/{row_uuid}/period_total`、
`customer_current_rows` 与 `customer_prior_rows` 各自的 `amount_ratio`/`quantity_ratio`）。

⇒ **spec 的 Task 10「公式格豁免」是假命题，无需实现**（第八轮 §④ 里「豁免机制未覆盖公式列」
的论断据此作废）。豁免的 `{row_uuid}` 模板匹配对 `GTROW-D42-0013` 这类身份**工作正常**。

🔴 **方法论教训（第三次同型）**：
本轮之前已有两条铁律——「结构性零须配变异证明」、「报 0 前换第二条通路复核」。
本轮补第三条：**凡计数类结论要喂给判据，必须用生产判据自己的口径复算，不得自造差集**。
自造差集不但让数字虚高 3.9 倍（402 vs 真实约 103），还凭空立了一个任务。

### ② extra 77 的真实构成：三种成因混在一起（全是 `editable`）

| table | extra 字段 | 成因 |
|---|---|---|
| `d4_10_rows` | 49 | **模板占位骨架**：`GTROW-D410-0013~0033`，值为「大额客户一~异常客户Y / 产品1~3 / unit_price=0」，store 的 `D4-10-data` 恒 `{"rows": []}` —— 从未被认领 |
| `key_indicator_rows` | 12 | **双重身份**：同一指标既有 `GTROW-D422-0012`（metric_name=年度预算）又有 label 派生身份 `key_indicator_rows/年度预算` |
| `invoice_compare_rows` | 12 | **双重身份**：`GTROW-D423-0012`(1月) 与 `invoice_compare_rows/1月` 并存 |
| `d4_31_interview` | 4 | **L2 测试污染**：`GTROW-D431-0005` 的 4 个字段全是 `L2MARK-D4-31-uxqb` |

「双重身份」是第八轮 `useD4Adjudication.ts` label 派生身份问题的**同型再现**：
部分前端组件用业务字段值（月份名/指标名）派生 rowId，而 instrumentation 用 `GTROW-*`，
substrate 上两套身份并存，store 只认一套 ⇒ 另一套恒为 extra。

⇒ 这 77 行**都不是 store 当前认领的数据**（store 认的是另一套身份或另一批行），
故 C 的收敛（清空/删除）对它们是安全的。

### ③ 方向裁决：C（materialize 侧收敛）为根治主线，P0 反向收敛降级

本轮先实现了 P0 反向收敛端点（`adopt-substrate`），真调后发现**核心假设失效**：

`store_mirror` 的 merge 语义是「以 base（当前 store）行集为权威，只更新已有行、
**不追加** base 没有的行」——这与 overlay 读方向「store 为权威」是**一致的设计**
（两个方向都不无中生有）。所以 adopt 无论跑多少次，store 都追不上 substrate：
extra 只从 402（裸差集）降到 77（`_managed` 口径下仍 77），`changed_item_count` 报 0。

实测佐证：`merge_projection_into_all_d4_stores` 在**空 base** 下能产出完整行
（`D4-10-data applied=49`），但在**真实 base**（当前 store）下对「projection 有 / base 无」
的行不追加。

⇒ **P0 不是解阻路径**。裁决走 **C**，理由：

| | P0 反向收敛（substrate→store） | **C（materialize 侧收敛）** |
|---|---|---|
| 语义方向 | 把 substrate 累积的重复/占位行灌回表单，让审计师手工删 | **表单权威、在线编辑跟随**（审计场景的自然预期） |
| 是否治病根 | 否——「只插不删」仍在，下次编辑继续累积 | **是**——补上删除侧，extra 从源头不再产生 |
| 对既有脏数据 | 让 store 吞下 | 由收敛逻辑自动清掉 |

一句话：**A/B 是让病人吞下病灶，C 是切除病灶。**

### ④ C 的收敛落点与判据（已定位，未实现）

落点：`excel_materialize.plan_managed_writes`（L1625），紧接 6.2 orphan 插行之后。
该处已有全部所需变量：

```python
physical         = dict(scan.row_identity_by_row)        # substrate 现有 row→identity
row_of_identity  = {identity: row}                       # 反向表
wanted           = projection.row_keys[table_key]        # store 声明的行
orphan           = [i for i in wanted if i not in row_of_identity]   # ← 已有：插行方向
# 缺的反向：stale = [row for row, i in physical.items() if i not in wanted]
```

**判据（与 overlay 严格对偶）**：仅当 `table_key ∈ projection.row_keys`（store 声明了该
table）才收敛；未声明一律不碰。这保证「少做而非多做」，不会误删。

**动作**：经用户裁决改为**删物理行**而非留空行。理由：动态插行能力**已具备且生产在用**
（6.2 的 `_plan_row_shift` + `plan_workbook_row_change_for_insert`），既然不够用时能动态插，
就不该靠预留空行凑数 —— 留空行是半吊子。

🔴 **删行的悬空引用风险已由引擎自带保护化解**：`build_delete_plan`（`excel_workbook_row_change.py:1903`）
第一件事就是 `find_dangling_sites`，若删行会让任何公式变 `#REF!` 即抛 `DanglingReferenceError`
（默认 `allow_ref_errors=False` fail-closed）。
⇒ 第八轮 R2「不知 stale 行是否被公式引用」**无需我自己写正则判定**（那个口径已证失效），
引擎会精确判定并拒绝。

**待实现时处理的技术约束**：`build_delete_plan` 的 `at`/`count` 是**连续区间**语义，
而 stale 行可能不连续 ⇒ 需按 (sheet, 连续区间) 分组、每组一个 plan、且**从下往上删**
（先删高行号，避免行号位移影响后续定位）。

### ⑤ 本轮已交付的独立重构：`store_mirror` 抽取（与 C 无关，但必须保留）

问题：「把 Projection 按 provider 分发、逐 store item merge 后写回 `checklist_responses`」
这件事有**两个**触发方（OO callback 落地 / 反向收敛端点），若各写一套就是第二真源。
而原实现是 `OoToHtmlCoordinator` 的**私有方法**（绑死 coordinator 状态），外部无法复用。

交付：

- 新建 `backend/app/services/workpaper_sync/store_mirror.py` —— 把三个方法
  （`_mirror_store_backed_if_needed` 111 行 / `_mirror_dedicated_dict_stores` 82 行 /
  `_mirror_d4_dual_stores` 277 行，共 **472 行**）搬成**会话无关**模块级函数，
  入参只有 `(session, adapter_id, project_id, wp_id, merged_projection, commit)`
- `oo_to_html.py` 三方法改**薄转发**（3686 → 3233 行），行为逐字节等价
- 抽取前先现算确认依赖面极干净：这三个方法只用 `self._session` 与
  `state.frozen.{adapter_id, project_id, wp_id}`，无其它 coordinator 状态

🔴 **抽取过程暴露并修掉两个真缺陷**（都是真调 adopt 才触发的）：

1. **缺模块级 `import json`** —— 原 `_mirror_dedicated_dict_stores` 靠 `oo_to_html` 外层
   作用域的 `import json`，搬成独立模块函数后失去它 ⇒ `json.loads` 抛 `NameError` ⇒ 500。
   ⇒ 教训：**搬移代码必须检查函数体内使用的名字是否都在新作用域可见**，AST 解析通过
   ≠ 运行期名字可解析（`NameError` 是运行期的）。
2. **逐 item commit 破坏原子性** —— `store_mirror` 有 **6 处** `await session.commit()`
   （OO callback 幂等重放场景可接受），但 adopt 中途失败会留**部分写入**（实测发生：
   D4 store 137 → 154 行）。⇒ 三个函数加 `commit: bool = True`（默认不变，OO callback
   逐字节等价），adopt 传 `commit=False` 并自己统一 commit + 异常 rollback。
   审计留痕也移到 commit **之前**入同一事务（否则「改了 store 却没留痕」，回滚快照丢失
   —— 首次 500 正是这样丢掉了快照）。

两个既有守卫**跟随执行层迁移**改扫描目标（判据意图不变，都额外加了「OO 侧转发未被误删」断言）：
`test_d4_mirror_shape_invariants::test_d4_8_has_dedicated_consumption_block`、
`test_d2_store_value_equivalence::_oo_to_html_tree`。

回归：镜像直接面 **35 passed**；扩展面（task26 OO callback + b60/g7h1/d4_12/d4_14 mirror +
store_item_registry + d4_store_item_wiring_gap）**192 passed**；commit 参数化后复跑 **167 passed**。

### ⑥ `adopt-substrate` 端点：降级为运维工具（保留，附已知局限）

端点本身可用（`POST {USER_SYNC_PREFIX}/adopt-substrate`，body `{dry_run, expected_revision}`），
带完整保护：published 准入 fail-closed（**不得降级成空 projection = 清空整表**）、
`expected_revision` 并发锁（409）、覆盖前留存原值 + hash-chain 审计、原子事务。
`adopt_substrate` 已登记进 `_WRITE_ACTIONS`（未登记则 `_action_authorizer` 恒 403）。

🔴 **两条已知局限（不修则误用）**：

1. **merge 语义 ≠ 覆盖语义**：它「不追加 base 没有的行」（见 §③），所以「以 OO 侧为准
   覆盖表单」实际**覆盖不完整**。作为运维工具使用时须知晓。
2. **`changed_item_count` 不可信**：`_snapshot_store` 的 after 快照在**同一未提交事务**内
   读取，读不到 store_mirror 自己的未提交写 ⇒ 实测报 0 而真实改了 12 个 item。

### ⑦ live D4 store 的污染现状与处置裁决

盘点：D4 的 **39 个 store item 中 30 个带测试污染标记**
（`l2-seed-*` 14 / `GTROW-*` 10 / `L2MARK-*` 8 / `probeB` 1 / `xsheet-*` 1），
且**绝大多数是 2026-09-25 及更早的历史遗留**，非本轮造成。
本轮 adopt 真正新增的只有 3 项：`D4-2-rows`（+15 行 substrate 重复副本，
原 7 行 `muks1021` 批**完好保留** ⇒ 纯增量无丢失）、`D4-30-customers`、`D4-32-groups`。
另 10 项只是 `updated_at` 被刷新（值相同的无条件 UPDATE），内容未变。

⇒ **裁决：不清理，保留污染态作为 C 的回归靶子。** 理由：

- 这个底稿的 store 从建立起就是测试数据堆积，**没有干净基线可回退**（且无 adopt 前快照）
- 单清 store 会让问题**更严重**：store 空 + substrate 仍 33 行 ⇒ extra 从 77 涨到接近 1238
- 要真「用新数据重测」得双侧一起重置，而重置后 extra 天然为 0、materialize 自然会过 ——
  **那验证的是「空底稿能物化」，不是「C 收敛逻辑正确」**，反而失去验证靶子
- 当前 77 个 extra 是理想回归样本：真实、可复现、覆盖三种成因

⇒ **用 C 治污染，而不是先清污染再验 C。** C 落地后这 77 个 extra 会被收敛逻辑自动清掉，
那既是修复验证，也顺带治好了污染。

### ⑧ 本轮交付状态

| 项 | 状态 |
|---|---|
| extra 口径更正（402/126 → **77**）+ 公式豁免本已存在 | ✅ 实证并登记 |
| 方向裁决 C + 收敛落点/判据/删行方案定稿 | ✅ 已定，**未实现** |
| `store_mirror` 抽取 + 2 缺陷修复 + 2 守卫迁移 | ✅ 交付，回归全绿 |
| `adopt-substrate` 端点（降级运维工具）+ 局限登记 | ✅ 交付 |
| **C 的收敛实现（Task 11/12/13）** | ⏸ **一行未写** —— D4 的 materialize 仍 500 |
| live 污染 | 保留（作 C 的靶子，已裁决） |
| 探针与临时产物 | ✅ 全清（18 探针 + 6 产物） |

---

## 2026-09-28 第十轮：C 方案落地（受管行收敛 + 模板骨架豁免）—— extra 归零，暴露第五层根因

> **本轮定位**：按用户裁决实施 C（materialize 侧收敛）。过程中判据被实测连续修正**三次**，
> 最终形态与初始设计相差很远。结果：`extra` 从 77 归零（真实链路确认不再报 extra），
> 但 500 未解除 —— 错误推进到 `missing`，暴露一个与本 spec 无关的既有缺陷（第五层根因）。

### ① 判据的三次修正（每次都由实测推翻，不是设计推演）

| 版本 | 判据 | 被什么推翻 |
|---|---|---|
| v1 | `stale = physical 里不在 store row_keys 的行`，一律删 | `test_d4_1_materialize_extract_realchain` **4 红**：`IdentityRetentionError: OO 往返后丢失 3 个 row identity, 首个 'GTROW-D41MAIN-0009'` |
| v2 | v1 + 排除模板骨架行（`GTROW-{template}-{4位}`，非 MINTED） | 4 红转绿，但**对 D4 无效**：46 个 stale 身份 **100%** 是模板骨架 ⇒ 全被跳过 ⇒ extra 仍 77 |
| v3（终态） | v2 + **roundtrip 侧豁免**模板骨架行的 extra（E3） | extra 归零 ✅ |

**v1 为什么错**：instrumentation 给模板的**每个**受管行预生成 `GTROW-{template}-{row:04d}` 身份，
而 store 只声明「有业务数据的行」⇒ 骨架行不在 `row_keys` 里是**常态**，不代表用户删了行。

**v2 为什么不够**：D4 的 extra 全部来自模板骨架行（模板在受管区自带非空业务值），
排除它们等于什么都不收敛。

### ② E3 豁免的设计：合取条件，不弱化 fail-closed

```python
# content_mutation._assert_roundtrip_equivalent，算出 extra 后过滤
if (identity
        and identity not in declared          # ② store 未声明该行
        and is_template_skeleton_identity(identity)):   # ① 是模板骨架
    continue   # 豁免
```

②是关键。语义诚实：**store 没声明的行，其 Excel 侧内容不是 materialize 写的**
（materialize 只写 projection 里有的东西），判它「反读出未提交的受管字段」本就是归因错误。

两种情形**仍然报错**（已由变异反证锁住）：

| 情形 | 为何仍报 |
|---|---|
| store **声明了**骨架行却缺字段 | ②不成立 ⇒ store 认领了就要字段完整（否则静默丢数据） |
| 非骨架孤儿（`d4r-*` / `xsheet-*` / `GTROW-MINTED-*`） | ①不成立 ⇒ 那才是真孤儿，交收敛逻辑删除 |

### ③ 为什么 D2（清模板占位）被否决 —— 实测数据推翻了我的推荐

我原推荐清理权威模板的受管区占位内容。实测 166 个 editable 非空字段后**撤回**：
它们混着两类完全不同的东西。

| 类别 | 身份数 | 内容 | 可否清 |
|---|---|---|---|
| 真示例 | ~23 | `大额客户一`/`产品1`（D4-10 21 行）、`客户1`/`新增主要客户`（D4-28 2 行） | 可清 |
| **模板应有内容** | ~60+ | `key_indicator_rows` 12 行 = `年度预算`/`主营业务收入`/`销售人员数量`…（审计指标**正式名称**）；`invoice_compare_rows` 12 行 = `1月`~`12月`（表的**固有结构**）；`d45_policy_groups` = `1.销售商品收入`/`（1）收入会计政策`（会计政策**条目标题**）；`customer_totals` 4 = 合计初始值；`d4_32_groups` 34 = 分组编号 | **不可清** |

清掉后者会让审计师打开 D4-22 看到 12 行空白、D4-23 没有月份 —— **破坏模板业务语义**。

🔴 **这反而指向第四层根因**：如果 `1月`~`12月`、`年度预算` 是模板**应有**的行，它们
**本就该在 store 里**（作为行的初始数据），而不是只存在于 Excel 侧。extra 的深层成因是
**这些 table 缺少「模板固有行 → store 初始化」的接线**。E3 是在判据层承认这个现状，
而非修它（修它 = 逐 table 定义「哪些是固有行」并实现初始化，远超本 spec 范围）。

### ④ 交付清单（4 个文件）

| 文件 | 改动 |
|---|---|
| `contracts.py` | 新增 `is_template_skeleton_identity()` + `_TEMPLATE_ROW_IDENTITY_RE`。🔴 **放在 contracts（底层无依赖）而非 excel_materialize/excel_extract**：收敛判据与 roundtrip 豁免**两处都要用**，各写一份就是第二真源（漂移时症状分别是「误删模板行」与「误报 extra」，相距很远） |
| `content_mutation.py` | `_assert_roundtrip_equivalent` 加模板骨架豁免（合取三条件） |
| `excel_materialize.py` | 6.2b 收敛判据（与 overlay 对偶）+ 6.8b **分级**动作 + 阶段 0 删行执行 + `_shrink_managed_table_ref`（Table ref 对称收缩）+ `shrink_sheet_rows` **首个生产接线点**（闭合「能力已建 ≠ 接线完整」） |
| `test_managed_row_convergence.py`（新） | 22 tests / 3 组不变量，每组配变异反证；含 3 条**源码锁**（防判据形态被「简化」后变异反证仍绿） |

**分级动作**（更正 6，由 D4-31 实测确立）：

| 情形 | 动作 |
|---|---|
| 删后受管区仍剩 ≥1 行有身份数据行 | 删物理行（行数精确跟随 store） |
| 删后受管区归零（D4-31 是 `A5:K5` **单行区**） | 清空 editable 字面值格，保留物理行 + 身份载体 + 公式格 |

后者的依据：纯删行在 D4-31 实测撞 `IdentityCarrierMissingError`
（「Table ref 覆盖的行区间内一个 row identity 都没反读到」），整个 entry 反而彻底不可用。
⇒ 「清空」与「删行」**不是二选一，而是按受管区容量分流**——最初的清空建议与后来的删行
裁决各覆盖了分级的一侧。

### ⑤ 结果：extra 归零，但 500 未解除 —— 第五层根因（既有缺陷，非本轮引入）

真实链路（UI 点「在线编辑」，D4-3 受管 sheet）现在报的是 **`missing`** 而不是 `extra`：

```
staged representation 反读后缺少受管字段
adjudication_main_rows/xsheet-other-g5d43680692/{current_unadjusted,label,prior_unadjusted}（共 3 个）
```

离线实证根因（`_c3_missing` 探针，只读）：

| 口径 | `xsheet-other-g5d43680692` 的 table 归属 |
|---|---|
| `store-projection` 端点的 `row_keys` | `adjudication_other_rows` ✅ |
| provider 纯 store 投影的 `row_keys` | `adjudication_other_rows` ✅ |
| **端点的 `values` key 前缀** | **同一行有两套**：`adjudication_main_rows/…` ＋ `adjudication_other_rows/…` 🔴 |
| provider 纯 store 投影的 `values` key | 只有 `adjudication_other_rows/…`（且字段更全，含 `current_aje`/`current_rje`） |

⇒ `main_rows/` 那三个 key **由 overlay 引入**，即 **substrate extract 把 D4-1 同 sheet 双区的
other 区身份按主表 `table_key` 产出了字段 key**。materialize 拿到
`adjudication_main_rows/xsheet-other-*` 后，在 main 受管区找不到该身份的物理行（它在 other 区）
⇒ 没写入 ⇒ 反读缺失 ⇒ `missing`。

🔴 这是 **D4-1 双区 extract 的 table 归属缺陷**，与受管行收敛无关，且**未由本轮引入**
（本轮没碰 extract 的 table 归属）。影响面推测涵盖所有同 sheet 多受管区底稿
（D4-1 / D4-9 / D4-20 / D4-34 / D4-36 等），需独立排查。

### ⑥ 回归与 pre-existing 红的权威判定

- 收敛与豁免相关面：`test_task38_excel_materialize` / `test_d4_1_materialize_extract_realchain` /
  `test_task15_content_mutation_pg` / `test_single_pass_failure_atomicity` /
  `test_projection_first_publication` 合计 **238 passed**；新守卫 **22 passed**
- `test_projection_first_publication.py` **3 红**已用 `git stash` **权威判定为 pre-existing**
  （stash 掉本轮三个文件后照样红）：
  ① `test_row_keys_merge_preserves_order_and_dedupes` —— 断言 overlay 的 row_keys 按**并集保序**
  （`('a','b','c')`），而实际 `('b','c')`：这是并发会话 commit `e52e5e5ce` 把 overlay 从并集
  改成「store 权威」留下的**测试欠账**
  ② `test_host_target_codes_equal_the_reviewed_adjudication` —— 「只比对了 34/51 个已交付 entry」
  分母不足
  ③ `test_row_bearing_table_key_agrees_with_every_declaring_provider` —— E1 provider 缺
  `ROWS_TABLE_KEY` 声明（`ProviderCapabilityError`）

### ⑦ 方法论教训（第四条，补入铁律）

前三条是「结构性零须配变异证明」「报 0 前换第二通路复核」「计数类结论须用生产口径复算」。
本轮补第四条：

🔴 **判据设计必须先在真实样本上跑一遍再写实现** —— 本轮判据被实测推翻三次
（v1 删骨架行致 4 红 → v2 对 D4 完全无效 → v3 才成立）。若按 v1 直接实现完再验，
会在「已改核心引擎 + 已动 live 数据」之后才发现方向错。
先用离线探针把「这个判据在真实数据上会命中什么」量清，代价远低于事后回滚。
---

## 第十一轮（F1 + G2 + G3）：D4 materialize 500 **已修复并真实链路验收通过**

第十轮结束时 500 仍在，卡在第五层根因。本轮连做三处修改把余下三层全部收口，
**真实链路**（点 D4-3「在线编辑」）已返回 **200 OK**、OnlyOffice 编辑器正常加载。

### ① 完整错误演进链（七层，每层都有实证）

| 层 | 报错形态 | 成因 | 处置 |
|---|---|---|---|
| 1 | `extra` 402 / 126 | **裸差集**未应用生产 `_managed` 豁免 ⇒ 两轮都虚高 | 改用生产口径，真值 **77** |
| 2 | `extra` 77 | substrate 有模板骨架行 / store 未声明 | **E3** roundtrip 豁免（合取：是骨架 ∧ store 未声明） |
| 3 | `missing` 3 个 | overlay 把 other 区身份归进 main 表 row_keys（错位 key） | **F1** overlay 逐 table 判据 |
| 4 | — | 上述两处修完后暴露：main 区 R22 承载 other 段身份 | 由 6.2b 收敛判 stale |
| 5 | `extra` 7 个 `GTROW-MINTED-*` | **删行**缺兄弟 Table ref 收缩 ⇒ other 区出现 uuid 空行 ⇒ 反读被重新 mint | **G2** 删行降级为清空 |
| 6 | `extra` 1 个 `label` | 清空对 text 写**空串** ⇒ 落成「存在且值为空串」的格 ⇒ 反读仍算有值 | **G3** 新增 `CellWriteKind.blank` |
| 7 | **200 OK** | — | ✅ |

🔴 第 5 层是**本轮自己引入**的（删行是新增路径），不是既有缺陷 —— 如实登记。

### ② G2 裁决：删物理行降级为「清空业务格」

删行牵动**一整套行号位移联动**，而插行路径为此已积累专门处理：

* `_shift_sibling_table_refs` —— 同 sheet 兄弟 Table 的 ref 位移
  （D4-1 是 main `R8~R22` / other `R25~R36` **双区**，删 main 区一行就动 other 区）
* footer anchor 与 `GT_FOOTER_ROW` 重冻结、合计公式区间扩张
* `_apply_workbook_propagation` —— definedName 与**引用侧 sheet** 的跨表公式行号

删行要**全部对称实现**才安全。实测代价：只补了自己那个 Table ref 的收缩（未补兄弟 ref）
就让 other 区出现 uuid 空行 ⇒ `_scan_row_identities` 按 tombstone 策略**重新 mint**
`GTROW-MINTED-*` ⇒ 新身份不在 intended ⇒ 又一轮 `extra`。

拒绝方案 G1（补齐兄弟 ref）的理由：每补一处暴露下一处，远超「修 D4 的 500」的范围。

⇒ `shrink_sheet_rows` / `_shrink_managed_table_ref` / `MaterializePlan.stale_deleted`
**代码保留但刻意不启用**，并有守卫**反向断言**「收敛不得产出删行计划」，
留给后续独立 spec 补齐多区位移联动后再开。

### ③ 🔴 G3 根因：「清空」与「写空文本」在 OOXML 是**两种不同的格**

`_cell_xml` 对 `CellWriteKind.inline_text` 的 `None` 与 `""` **一视同仁**，都渲染成：

```xml
<c r="A22" s="42" t="inlineStr"><is><t xml:space="preserve"></t></is></c>
```

—— 一个**存在且值为空串**的格。`xml:space="preserve"` 明确保留空串，extract 反读得 `""`，
于是 **cell 仍算有值** ⇒ 仍产出该字段的 key ⇒ `extra` 消不掉。

而 amount 字段「恰好」好了是**巧合**：`_render_number("")` 落成 `<v></v>`（空数值节点），
openpyxl 读回 `None`。**靠巧合不能作判据**，且 `<v></v>` 本身不是干净形态。

⇒ 这精确解释了为什么 extra 从 **7 个降到 1 个**：main 表 7 个字段里 6 个是 amount（消失），
1 个是 text 的 `label`（残留）。**数字对得上不是偶然，是同一机理的两种落盘形态。**

**修法**：新增 `CellWriteKind.blank`，渲染 `<c r=".." s=".."/>`（无 `t`、无 `<v>`、无 `<is>`，
**保留样式** `s=` 符合 AC 3.5），收敛清空对**所有** value_type 统一用它，消除 text/number 分叉。

先例同型（不是新发明）：`boolean_literal` 对 `None` 也刻意落真空格而不是 `<v>0</v>` ——
后者把「未填」变成「填了 false」，对「是否函证」这类审计字段是实质性语义错误（BP-22）。

### ④ 真实链路验收（权威判据，非离线）

点 D4-3「在线编辑」→ `POST .../materialize` **200 OK**：

* `generation` 165 → **166**、`replayed: false` ⇒ 真实执行而非重放缓存
* `artifact_sha256: d7d15bc3…`、OnlyOffice iframe 正常加载、页面 **0 errors**

新 substrate `000000166-d7d15bc324af.xlsx`（sha256 与端点返回一致）四条判据全过：

| 判据 | 实测 |
|---|---|
| ① 身份载体列**未被动** | `W22 = 'xsheet-other-g5d43680692'` ✅（否则会被重新 mint） |
| ② 业务格**全空** | `A22~H22`（A/B/C/D/F/G/H）7 格全空；`label` 从 `g5d43680692` 变空 ⇒ **收敛真实执行** |
| ③ 公式格**完好** | `E22 = =SUM(B22:D22)` / `I22 = =SUM(F22:H22)` 未被破坏 |
| ④ 无新 uuid 空行 | other 区 `X25~X36` 身份全在 ⇒ 第 5 层不复发 |

🔴 判据①③是「**清空不等于清行**」的正面证据：身份与公式都必须留，
清了身份 ⇒ 重新 mint（第 5 层复发）；清了公式 ⇒ 毁模板（且公式本就被 `PROTECTED_MODES` 豁免）。

### ⑤ 回归

`test_managed_row_convergence.py` **26 passed**（本轮新增 2 条）：

* `test_clearing_uses_blank_kind_not_empty_string` —— 源码锁：收敛必须用 blank，
  且**显式反断言**「退回 `_write_kind_for(spec)` + 空串」这一失败形态
* `test_blank_kind_renders_a_truly_empty_cell` —— 渲染形态断言，含**变异反证**：
  同样传 `None`，`inline_text` **仍然**产出 `<is><t xml:space="preserve">` ⇒
  证明两者不可互换、本条判据有真实区分力（不是在断言恒真的事）

相关面 **230 passed 零回归**：`test_task38_excel_materialize` /
`test_d4_1_materialize_extract_realchain` / `test_task15_content_mutation_pg` /
`test_single_pass_failure_atomicity` / `test_static_region_writeback`。

### ⑥ 方法论教训（第五条，补入铁律）

🔴 **「部分生效」比「完全不生效」更容易误判方向** —— 本轮 extra 从 7 降到 1 时，
很容易把它当成「还有一层独立的新问题」。实际上 7→1 与 6:1 的 amount/text 构成比
**是同一个机理的两种落盘形态**：数字本身就是根因的指纹。

⇒ 判据：**修一处后若报错数量变了但没归零，先算「消失的那些」与「残留的那些」有什么系统性差别**
（本轮是 value_type ⇒ 落盘 kind ⇒ 空值语义），而不是直接假设又遇到新一层。
按类型/分组给残留项分桶，往往一步就指到真因。

### ⑦ 遗留（各自另立 spec，本轮不做）

1. **删行的多区位移联动** —— 兄弟 Table ref / footer 重冻结 / definedName / 跨 sheet 公式。
   代码已在（`shrink_sheet_rows` + `_shrink_managed_table_ref` + `stale_deleted`）但不启用，
   有守卫反向断言守着，开启前必须先补齐全部对称处理。
2. **模板固有行 → store 初始化接线**（第四层根因）—— 166 个 editable 非空字段里 ~60+ 是
   模板应有内容（`年度预算` 等审计指标正式名、`1月`~`12月` 固有结构、会计政策条目），
   它们缺「模板固有行进 store」的接线。E3 是在**判据层承认现状**，不是根治。
3. **D4-1 `W22` 被写入 other 段身份的原始成因** —— 本轮只做了收敛清理，
   未追查它最初是怎么写进 main 区的（`A22=g5d43680692`、`B/E/F/I=0`，R22 是 main 区追加插入点）。

### ⑧ 补充实证：收敛是**幂等**的（跨 sheet 复验）

换 **D4-2** 再点一次「在线编辑」：同样 **200 OK**，且三个信号同时成立：

| 信号 | 值 | 含义 |
|---|---|---|
| `generation` | 仍 **166**（未递进） | 产物逐字节相同 ⇒ 无需新 generation |
| `artifact_sha256` | `d7d15bc3…` 与上次**完全相同** | 同上，字节级确认 |
| `replayed` | **`false`** | 不是重放缓存，**真跑了一遍**得到同样结果 |

⇒ 收敛**一次到位且稳定**：首次把 stale 行清空后，后续 materialize 找不到新的 stale 行，
于是产出不变。若收敛有震荡（例如清空又被重新 mint、或每次清不同的行），
这里会看到 generation 持续递进 —— 那正是第 5 层（`GTROW-MINTED-*`）的症状。

🔴 **`replayed: false` + generation 不变** 这个组合是判断幂等的关键：
单看「200」不能区分「真的稳定」与「被缓存挡住了」。

### ⑨ 任务 #2 结论：live「部分收敛态」无需人工处置

原担心：live store 只有 154 行（含历史测试污染），而 substrate 有 440 个物理身份行，
差 286 行 —— 是否需要人工清理？

**不需要**。生产 roundtrip 已通过（200 OK + 幂等），因为那 286 行差额的构成是：

* **模板骨架行**（`GTROW-{template}-{NNNN}`）—— 由 E3 豁免，是**设计允许**的状态
  （store 只声明有业务数据的行，模板预置行不进 store 是常态，非「用户删了行」）
* 公式字段 —— 由 `PROTECTED_MODES` 豁免

🔴 **这里踩了一次「同一个坑的第三次」**：我写了个离线探针想复算 extra，得 126 个
（形如 `customer_current_rows/GTROW-D49C-0014/amount_ratio`）。**探针是错的** ——
它的 `_iter_fields` 走 `contract.dynamic_tables`，而 `SyncContract` **没有这个属性**
（同一天早些时候刚实测过），于是 `protected_templates` 近乎为空，
**公式字段与骨架行两类豁免全都没应用**。

这与第八/九轮「裸差集得 402/126」是**同一形态的第三次复发**。
⇒ 强化铁律：**凡自建差集复算，第一步必须先断言豁免集非空**
（`assert protected_templates`），否则「豁免没生效」会静默地表现为「有一堆 extra」。
生产判据（真实链路 200）永远优先于自建探针。

那 286 行差额指向的是**遗留项 2（模板固有行→store 初始化接线）**，
不是本轮要修的东西，也不影响 D4 可用性。

---

## 第十二轮（2026-09-28）：D4-4 调整分录汇总接成真双向 —— **全组最后一张 `single_html` 清零**

spec `d4-4-adjustment-summary-bidirectional-writeback`。本轮把 D4-4 从 `⬜ single_html`
接成 ✅ 三维代码全绿，使逐张清册的 `⬜` 从 2 张降到 **1 张**（仅剩 D4-13 纯叙述文本表）。

### ① 原 `single_html` 裁决的两条理由经实测**均不成立**

| 原裁决理由 | 实测复核 |
|---|---|
| 模板无行身份 UUID 列载体 | **不成立**。`A1:J23`，**K~O 五列全空**，紧邻受管末列 J 右侧即 K；前端 `D4AdjustmentRow` **本就有 `rowId`**。对比 D4-19 是「模板无空列 → 注入列 P」才落地的，D4-4 连注入都不用 |
| hub store 被 A13/借贷平衡语义占用 | **不成立**。`debitTotal`/`creditTotal`/`balanceDiff`/`isBalanced` 全是 `computed` 不落库；`pushToA13`/`publishAdjustment` 只读 rows 后 `eventBus.emit`；`useAdjustmentCentralSync` 零写路径。落库的 `D4-4-rows` 就是干净的 10 字段行数组 |

它反而是剩余表里**几何最简**的一张：单区动态行、模板 10 列 ↔ 前端 10 字段 **1:1 双射**、
数据区公式格 **0**、R6~R20 完全空白、无合并、非转置。

### ② 几何冻结现算（11 项零更正）

`D4 收入底稿.xlsx`（199,176 B / 46 张 sheet）的 `营业收入调整分录汇总D4-4`：
`max_row=23` / `max_column=10` / 表头 R5 十列逐字全对 / 数据区 R6~R20（**15 行**）/
footer marker A21「提示：」（**63 字**）/ 数据区公式格 **0** / 非空格 **0** /
合并仅 `A1:J1`+`A2:J2` 且数据区无合并 / **K~O 五列全空** / `LAST_DATA_ROW(20) < FOOTER_ROW(21)`。

### ③ 🔴 两处 spec 前提在实施时已过期（如实登记，以现算为准）

**其一（文件迁移）**：spec Task 2 要求确认「`oo_to_html.py` 的 4-tuple 硬解包行仍在（现算 L2842）」。
现算它**已不在 `oo_to_html.py`** —— 本会话此前的 spec `workpaper-sync-managed-row-convergence`
Task 3 把三个 `_mirror_*` 抽到了会话无关模块 `store_mirror.py`（OO callback 与 adopt-substrate
共用，避免第二真源）。现算位置：`store_mirror.py` **L314**；`_mirror_d4_dual_stores`(×2) 与
`_dict_store_items`(×7) 也都在该模块。⇒ Task 7/8 的目标文件随之改为 `store_mirror.py`，
守卫文件头的过期描述已一并更正。

**其二（接线点数）**：design §3 的表列了 **8 处**接线，现算 D4-19 的真实接线点是 **11 处**
（design 把 `values.update` / `row_keys` / `results` 几处合并计了）。全部照做：
1 import · 2 flag · 3 `STORE_ITEM_IDS` · 4 `instrumentation_specs` · 5 `sheets` ·
6 `d44_projs` · 7 `values.update` 循环 · 8 `row_keys` 合并 · 9 `d44_results` ·
10 `**d44_results` 展开 · 11 `_RAW_PAYLOAD_ITEM_TABLE_KEYS`。
⇒ 「D4-8 曾只完成 5/8 处」的教训在本轮变成「按 8 处做会漏 3 处」。

**其三（命名）**：design 写 `_INCLUDE_D44_SHEET`，而既有 5 个同类 flag 都是
`_INCLUDE_D{n}_{名字}_SHEET`（D419_DISCOUNT / D417_CUTOFF / D420_RETURN / D434_CONTRACT /
D48_PRODUCT_MARGIN）⇒ 采用 `_INCLUDE_D44_ADJUSTMENT_SHEET`。

### ④ 🔴 变异反证抓到一个「归一幂等」造成的潜在假绿

`merge_projection_into_all_d4_stores` **末尾自己就调了** `_normalize_merge_updates`，
所以它的返回**已经是** 4-tuple。守卫若只断言「归一后是 4-tuple」，对
「`_RAW_PAYLOAD_ITEM_TABLE_KEYS` 的登记生效」与「登记冗余」**无法区分**（重复归一是幂等透传）。

摘掉登记重跑：`applied = 0`；带登记：`applied = 10`。
⇒ **`applied=0` 的后果不是报错**，而是 `store_mirror` 的护栏
``if applied <= 0 and base_rows: continue`` 把 D4-4 的回写**静默丢掉**（不报错、不落库）
—— 比 `ValueError` 难查得多。该反证已固化为守卫
`test_mutation_dropping_raw_payload_registration_collapses_applied`。

### ⑤ Req 2.5 的「五层不一致」已补齐

2026-09-28 实测：模板有 F/J 列 ✓ · `D4AdjustmentRow` 有字段 ✓ · `safeParseRows` 解析 ✓ ·
导入导出 ✓ · **UI 只有 8 列** ✗（源码注释编号 1~8）。

不补的后果不是「少两列」：F/J 在模板里真实存在 ⇒ OO 侧可编辑 ⇒ 用户改完回写进 store，
但切回结构化视图**看不见** ⇒ 表现为「改动丢了」（实为存了但不可见），比不回写更难排查。
⇒ 已补 `补充说明`(F/`placeholder`) 与 `备注`(J/`remark`) 两列，五层一致。

⚠️ **同名陷阱**：该文件另有 6 处 `placeholder="…"` 是 **el-input 的占位文本属性**，
与 `D4AdjustmentRow.placeholder` **字段**同名但无关。守卫判据因此锚定
`updateCell(row.rowId, 'placeholder', v)` 而不是 `placeholder` 字符串本身。

### ⑥ `_rows()` 两层强度（本轮设计裁决）

| 层 | 强度 | 理由 |
|---|---|---|
| 容器层 | **容差**（None/空串/空白/坏 JSON/dict/数字/bytes/含非对象元素 → `[]`，不抛） | 与另外 35 张 sheet 共享 entry，这里抛异常会打挂**整个 entry** 的 rematerialize（D4-9 真实事故） |
| 行层 | **fail-closed**（缺 `rowId` / 空串 / 重复 → `ValueError`） | 丢行身份会让 materialize 在错误受管区插行 + extract 反读错位 key，极难归因（D4-1 的 W22 追了七层）；不得退回数组下标作身份（Property 23） |

**禁加 rowId 格式正则**：本表行身份两种格式并存（前端 `d4a-{base36}-{rand}` /
导入侧 `uuid4()`），加校验会拒掉导入产生的行。

### ⑦ 契约规模现算对账

apply 前磁盘 **35 张 / 775 字段**（与文档一致），源码 36/785，差额恰 +1/+10；
`--apply` 后磁盘 **36 张 / 785 字段**（文件 555,518 → 562,622 B），
增量校验「+1 张 / +10 字段 / 新增 sheet_key 只有 `d44-managed` / 该表恰 10 字段」全通，
`assert_contract_file_matches_source()` 无 DRIFT。

**CS-13 空分母已显式记录**：d44 字段 mode 集合 = `['editable']`、`mode=='formula'` 字段数 **0**、
`formula_mask=[]` ⇒ 「formula 字段必须落在 formula_mask 内」的**分母为 0**，空分母成立，
**不得**因 mask 为空而判违规。

### ⑧ 🔴 方法论：同一条铁律的正反两向在一天内都踩到

「判断代码是否真做了 X 一律用 AST，禁文本匹配 —— 注释/docstring 正反两向都会骗过扫描器」：

* **反向**（此前）：docstring 写「权限：`require_project_access`」冒充真实现 ⇒ **漏报**；
* **正向**（本轮）：我在 provider 的 docstring 里写了禁令**反例**
  「写 `assert rowId.startswith('d4a-')` 之类断言会…被拒」，而首版探针用文本匹配查
  「有无 rowId 格式断言」⇒ 把这段**说明文字**当成真断言 ⇒ **假阳**。

⇒ 改用 AST（只看 `Call` 节点；docstring 是 `Expr(Constant)`、`#` 注释不进 AST ⇒ 天然排除），
并加**变异反证**（对真实 `rid.startswith('d4a-')` 必须命中，证明判据非恒绿）。

另一处同型：前端守卫的 `stripComments` 自检首版用单字母样本 `a`/`b`/`c`，而保留内容
`code` 里就含 `c` ⇒ 断言自撞打红。**判据本身写错了**，不是被测对象有问题。

### ⑨ 🔴 发明了一条不存在的基准（自查纠正）

前端守卫首版写了「dedicated 列表与 legacy 禁入名单**不得有交集**」—— **那是我臆想的规则**。
实际 `D4-5` 刻意同时在两处（`d4Constants.ts` 注释明说它是「历史冗余项，已接子组件桥
`d45-managed`，故实际不可能命中 legacy 分支」）。发明一条不存在的基准会把**有意设计判成缺陷**。

⇒ 判据收窄为「只断言 D4-4 的迁移完成」，D4-5 走**带反向断言的显式豁免**：
不只写理由文本（那是加一行就变绿的后门），而是断言它声称的条件真的成立 ——
`D4TabPolicyCheck.vue` 确实 `useD4SyncMode` + `d45-managed`。

### ⑩ 另一处「期望值不变但成因改变」

spec Task 13 预期 `d4LegacyOoBlocked.spec.ts` 的「推导 legacy 命中集」用例期望值要
**从 4 张变 5 张**。现算结论是 **期望值不变**（仍 4 张）：D4-4 原先被禁入名单挡住、
现在被 `bridged`（dedicated）排除，**两条路径都不进命中集**。

⇒ 只看结果无法区分这两种状态。已补一条独立用例
`① D4-4 的排除成因是「已接 dedicated 桥」而非「在禁入名单里」` 把成因本身钉死。
这与「口径不同 ≠ 有偏差」是同一条纪律。

### ⑪ 交付物与测试

**新增**：`backend/app/services/workpaper_sync/phase5_d4_adjustment_sheet.py`（325 行，12 函数）·
`backend/tests/test_d4_4_adjustment_contract.py`（**48 tests**）·
`audit-platform/frontend/src/components/workpaper/__tests__/d4AdjustmentSyncHostWiring.spec.ts`（**21 tests**）

**改动**：`phase5_d4_revenue_detail.py`（11 处接线，2728→2783 行）·
`d4.revenue_detail.json`（35→36 张 / 775→785 字段）·
`test_d4_mirror_shape_invariants.py`（+D4-4 专项 12 tests，含 2 条变异反证）·
`D4TabAdjustment.vue`（接桥 + 补 2 列）· `useD4Adjustment.ts`（导出 `flushPendingSave`）·
`GtD4OperatingRevenue.vue`（dedicated +`'D4-4'`）· `d4Constants.ts`（legacy 名单 −`'D4-4'`）·
`d4LegacyOoBlocked.spec.ts`（期望翻转 + 成因判据 + 变异反证）

**测试**：后端相关面 **71 + 55 passed**；前端 D4 接桥面 **98 passed**。
`A9-1 mode switch` 那条红经 `git stash` 归因为**预存失败**（与本轮无关）。

### ⑫ 环境门 —— **2026-09-30 已全部在真栈跑通（原 `UNVERIFIABLE` 清零）**

原记录：Task 10*（发布链）需 live PG；14*（L1）/ 15*（L2 seed）/ 16*（L2 真 OO canvas
往返）需 start-dev.bat 全栈 + OO 容器，按全组既有标准列为 env 门。
**2026-09-30 全栈起齐后逐项跑完，5 项全 ✅**（D4 是全组第一张把 L2 真 OO canvas
往返做到 application `applied` + 真库逐值对账的底稿）：

| # | 结果 | 关键证据 |
|---|---|---|
| 10* | ✅ | gen 166→167→**168** / revision 188；途中修一处 footer marker 全等匹配真缺陷 |
| 15* | ✅ | `seed_d4_4_adjustment_l2.py`（幂等 4 模式），3 行借贷各 168000 平衡；substrate R21~R23 十列全对、footer 正确下移 R24 |
| 14* | ✅ | L1 `1 passed / 1.8m`，`D4-4.json`：`d2_sync_hits=0` / `console_errors=0` / `http_errors=0` / `oo_iframe_count=1` |
| 16* | ✅ | L2 `1 passed / 1.2m`，OO 写 `J21` → `cs_error=0`/`cs_outcome=accepted`（非 `4=no_changes`）→ operation `oo_to_html` `applied` → application gen169 `applied`/rev 190/conflict 0 → 真库 `D4-4-rows` 第 1 行 `remark` 变 marker、另 2 行逐字未动 |

三条可复用的结论（对后续各循环 L1/L2 都成立，非 D4-4 专属）：

1. **`doc_editor_called` 不是有效判据**：现算 **36 张 L1 证据全部为 `false`**，无一例
   `true` ⇒ 该 init-script 猴补在本平台从未触发，是全 fleet 一致的探针失效。OO 挂载应由
   `oo_iframe_count=1` + `sync_host_mounted=true` + `materialize_ok=true` 三项承担。
   （一个在所有样本上取同一值的字段没有判别力，写成判据等于永假门。）
2. **点「在线编辑」前必须等切换器解除 `disabled`**：`useD4SyncMode.switchMode` 首行
   `if (busy.value && ...) return` 会**静默吞掉** busy 期的点击，报错却落在 3 分钟后的
   materialize 轮询上。且 D4 是整册 37 sheet materialize，**轮询要 300s 不是 180s**
   （实测超时后 18 秒才出现 `applied` operation）。
3. **forcesave 的 `cs_error` 必须从 `await waitForResponse()` 的 Response 直接
   `await res.json()` 取**：`page.on('response')` 里 `void res.json().then(...)` 异步塞的
   变量在 `waitForResponse` resolve 时常还是 `null`（它只等响应头）⇒ 把一次
   `cs_error=0` 的真实成功误判成失败。证据自相矛盾时（`cellTextAfterSave` 已是 marker、
   forcesave 已是 202，却报失败）应先怀疑取值时序，别先怀疑被测对象。

另：本轮顺带发现 `audit-platform/frontend/playwright.config.ts` 自身 IPv4/IPv6 口径
不一致 —— `use.baseURL` 写死 `127.0.0.1:3030` 而 `webServer.url` 用 `localhost:3030`，
本机 Vite 现算**只监听 IPv6**（`netstat` 仅 `TCP [::1]:3030 LISTENING`）⇒ webServer
探活能过、所有相对 `page.goto` 必 `ECONNREFUSED`，**本机任何 e2e 都跑不起来**，与 D4-4
无关。Playwright 1.60.0 无 `--base-url` CLI 选项，本轮用一次性 `playwright._d44.config.ts`
只覆盖 baseURL 绕过（不改共享配置，避免影响并发会话），根因登记为遗留项。
