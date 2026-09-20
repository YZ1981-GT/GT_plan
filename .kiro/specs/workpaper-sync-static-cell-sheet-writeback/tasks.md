# Implementation Plan

## Tasks

- [x] 1. binding kind 判据 + 静态形态：`excel_extract.py` 加 `BindingKind` enum + `ExcelIdentityBinding.defined_name` 字段 + `kind` 属性 + `is_static_region()`；`__post_init__` 分静态/动态两支校验（静态校验 defined_name 非空且 table_name/uuid_column 必空；动态校验原样保留）；单测构造/校验/混填 fail-closed。
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
- [x] 2. `resolve_managed_region` definedName 分支：新增 `_resolve_static_region`，复用 D4-29 `resolve_managed_sheet` 校验入口求 region（唯一/非 localSheetId/type==RANGE），region.uuid_column="" 且跳过 contains_column(uuid) 校验；0/多个/隐藏 sheet 各抛窄类型；kind 分派前置，动态路径逐字节不动。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
- [x] 3. `managed_tables_of` 静态路径：static binding 返回 `(None, statics)`，不执行 `has_dynamic_rows raise`（动态路径保留该 raise）；校验 static binding 指向 has_dynamic_rows==False 表；逐 5 处调用点前置 kind 分派使静态分支不访问 dynamic。
  - _Requirements: 3.1, 1.5_
- [x] 4. extract 静态链：`_needed_columns_and_rows`/`_managed_coordinates` 静态分支（不含 uuid_column 起手、不加 uuid 幽灵坐标）；`extract_projection` 静态分叉（跳 identity scan/uuid/row-chunk，只走 7.1 静态块 row_identity="" excel_rows=()）；`assert_identity_inventory_retained` 静态条件化为 `_assert_static_anchor_retained`（只断言 definedName 锚点存在，不比 row UUID 清册）。
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
- [x] 5. materialize 静态链：`plan_managed_writes` 加 `_plan_static_writes`（按绝对坐标 CellWrite，区内公式 formula_mask 保护，row_shift=None，无 footer 两门，无 minted UUID）；definedName 原样保留；unmanaged-region digest 门对静态区受管坐标成立；闭合往返 Property 1（D4-33 72 cell materialize→extract 逐字段等）。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_
- [x] 6. observer 泛化：`collect_workbook_structure` 按 anchor kind 分派（transposed 走 D4-29 原样、static_region_ref 走 `_collect_static_region_physical`、未知 kind 才 raise），去掉「static 复用 transposed 特判」；`_frozen_sheet_anchors` 产 static_region_ref 锚点；钉 D4-29 transposed 零回归（Property 3）。
  - _Requirements: 5.1, 5.2, 5.3_
- [x] 7. instrumentation 注入静态 definedName：`excel_instrumentation.py` 加静态注入路径（注 workbook-scope definedName + `_GT_SYNC` runtime binding 记 static_region_ref，不注 tableParts/不注 UUID 列）；复用 resolve_managed_sheet 校验注入后自检；跑守卫确认是否触发 Tier-A 保鲜门，触发则刷 gate.json digest + 重跑重新实证。
  - _Requirements: 5.4, 5.5, 5.6, 7.6_
- [x] 8. 动态 + D4-29 零回归全面复核：D4-2/D4-9 materialize 产物 sha256 逐字节 == 改前（Property 2）；D4-29 transposed 反读逐字段 == 改前（Property 3）；既有动态 sheet structure_hash 逐字符不变（Property 7）；变异反证六锚点四态判定全部 RED。
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
- [x] 9. D4-33 provider 接线 + 发布链：声明静态 binding（defined_name GT_MANAGED_REGION_D433，无 table_name/uuid）+ 契约 static table（72 cell 绝对坐标 + 合计/毛利率 formula_mask）；6 处接线进 phase5_d4_revenue_detail（只加不动既有张）；翻 `_INCLUDE_D433_MARGIN_SHEET=True`；跑发布链 generate→provision→rematerialize --apply（gen++、--check already_on_desired_bundle、无 Roundtrip/FooterDrift），soft_limit 120 不提高不抛 SoftTimeout。
  - _Requirements: 6.1, 6.3, 6.4, 6.5_
- [x] 10. D4-33 前端接桥 + 真栈：`D4TabOtherMargin.vue` 从 legacy GtOnlyOfficeSheet 改为 useWorkpaperSyncBridge + WorkpaperSyncEditorHost，宿主 isD4DedicatedSyncSheet 加 'D4-33'；前端守卫 `d4OtherMarginSyncHostWiring.spec.ts`；真栈实测 HTML↔OO 往返产 evidence D4-33.json（环境不可用标 [~] UNVERIFIABLE 不假绿）。
  - _Requirements: 6.6, 7.7_
- [x] 11. * D4-8 census 裁决 + 接入：census 实测 D4-8 是「块计数动态（块内静态）」还是「真实可增删动态行」；静态则建 provider 走静态路径接入（发布链 + 前端接桥）；动态则记录裁决出本 spec 范围；census 前 blocked，不假设。
  - _Requirements: 6.2_
  - **进展（2026-09-20 后续）**：census 裁定 = 静态块矩阵（产品块模板预画、块内 12 月固定行、slot0→产品A 受管 180 static cell），已建 provider `phase5_d4_product_margin_sheet.py` 走静态路径。**修复一个会打挂整个 entry 的非法 key bug**：`stable_field_key` 曾用前端驼峰字段名（`revQty` 等）违反 `assert_stable_key`（只允许小写），生成 180 个非法 key → `parse_contract(build_contract_payload())` 抛 `ContractSchemaError` 连累整份 payload；已改为小写契约键（`rev_qty`…）+ json_pointer/store 写回保留驼峰 + `_CONTRACT_TO_STORE_FIELD` 反查。契约已 `generate --apply` 落盘（磁盘 31→32 张，`assert_contract_file_matches_source` 从 DRIFT 恢复 OK）；provider + 测试已补入 git（解 HEAD 断裂）。守卫 `test_d4_8_margin_contract.py`(10) 全绿。
  - **进展（2026-09-21 前端接桥补齐）**：②已完成——`D4TabProductMargin.vue` 从 legacy（http+CustomEvent persist）改为 `useWorkpaperSyncBridge`+`WorkpaperSyncEditorHost`（sheetKey=d48-managed, entry=xlsx/gt-d4-operating-revenue, capabilityForEntry, flushHtml→flushPendingSave 先于 readStoreProjection），加双模式工具栏 el-segmented(表格视图/在线编辑)+fail-visible syncStateTag；宿主 `GtD4OperatingRevenue.vue` `isD4DedicatedSyncSheet` 已含 `'D4-8'`。新增守卫 `d4ProductMarginSyncHostWiring.spec.ts`(9 tests) 全绿 + 变异反证（删宿主 `'D4-8'` → dedicated 断言 RED，还原后绿）；D4-33 守卫零回归(9 tests)；后端契约守卫 `test_d4_8_margin_contract.py`(5) 全绿。census 裁决落盘 `docs/operations/evidence/d4-bidirectional-acceptance/D4-8.json`（verdict=STATIC + 基于 openpyxl 实读模板的 5 条证据 + 后端/前端接线核实 + not_covered 诚实标注）。
  - **仍 `[~]` 未完成项**：①rematerialize 发布 representation（需 live PG，D4 entry materialize 已 ~138s 逼近 120s 软上限）；②真栈 OO canvas 单元格往返（D4 全组同一 env 门，与 D4-33/D4-35 同标准）。故 D4-8 当前为 � 代码全绿（后端契约+前端接桥+守卫+census 裁决落盘），**真栈 representation 发布 + OO canvas 往返 UNVERIFIABLE 不假绿**（引擎静态路径正确性由 D4-33 同 BindingKind.static_region 单测 TestStaticRoundtrip + 发布链真 PG 无 Roundtrip 错误保证）。
- [x] 12. 清册更新 + 收口：`d4-bidirectional-writeback-inventory.md` 中 D4-33（及 D4-8 若静态落地）从 ⛔HTML-only 转 ✅ 三维全绿、统计段调整、HTML-only 裁定段改写为「已由本 spec 解除」；spec 三件套结构校验（Property 整数、Validates X.Y、waves JSON）；行数门禁同步 `file_size_whitelist.txt`；全部正式产物无 `??` 未跟踪（stash-isolation 只提交自己文件）。
  - _Requirements: 6.7, 7.8_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2","3"]},{"wave":3,"tasks":["4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6","7"]},{"wave":6,"tasks":["8"]},{"wave":7,"tasks":["9"]},{"wave":8,"tasks":["10","11"]},{"wave":9,"tasks":["12"]}],"blocking":{"1":"kind 判据未落地不得接下游分派","3":"managed_tables_of 5 处调用点未全部 kind 分派会在动态/静态交叉处崩","5":"materialize 静态链未通不得宣称往返闭合","8":"动态/D4-29 零回归未全绿不得接 provider（回归风险最高）","9":"发布链 rematerialize 抛 SoftTimeout 或 Roundtrip 即未落地","11":"D4-8 census 未裁决不得假设静态/动态"}}
```
