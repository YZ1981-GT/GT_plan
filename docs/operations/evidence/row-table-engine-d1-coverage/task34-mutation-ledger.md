# Task 34 变异检验台账（P1~P18）

spec: d1-sync-row-table-engine-and-d1-coverage · Task 34 子目标 A
生成于 2026-09-28，数字由脚本现测，不手抄。

## 口径

本 spec 一贯做法是「每条 Property 落地时就配变异反证」，变异证据散落在各判据文件
与 tasks.md 的 A~X 勘误节里。本台账把 P1~P18 逐条对应到其判据文件与变异证据位置，
并记录 Task 34 系统性复跑的结论。**Property 编号为 spec-scoped `D1-P{N}`**（design §上游锚定），
与 umbrella 的全局 `Property N` 不同义。

## P1~P13（后端）

| Property | 判据文件 | 变异证据 | 现跑 |
|---|---|---|---|
| D1-P1 golden digest 不变 | `scripts/check/check_sync_provider_golden_digest.py` + 自测 | 改一个 provider 的 payload ⇒ digest 变（F2/X5-d 多次实证） | 139 digest 逐个不变 |
| D1-P2 formula_mask ≡ 手写 | `test_row_table_engine_equivalence.py` | 改 formula_columns 顺序 ⇒ 必红（Task 6 记录） | ✅ |
| D1-P3 managed_field_specs ≡ sorted(...) | `test_row_table_engine_equivalence.py` | 账龄段展开顺序错乱 ⇒ 必红（Task 8 记录） | ✅ |
| D1-P4 nested/flat 派生各自等于原写法 | `test_row_table_engine_core_equivalence.py` | flat 走 nested 派生 ⇒ D6 必红（Task 7 反证式先写） | ✅ |
| D1-P5 两方向 store item 集合相等 | `scripts/check/check_store_item_two_way_parity.py` | 注册表漏一个 item ⇒ 必红（Gate 6 / X5-d 变异 3 处全红） | ✅ |
| D1-P6 注册表未命中抛错含清单 | `test_store_item_registry.py` | 改成静默 return ⇒ 必红（Task 12 P6 变异） | ✅ |
| D1-P7 注册表 O(1) | `scripts/check/check_sync_registry_lookup_is_o1.py` | 改线性 for 扫描 ⇒ 比值 671× 反证成立 | ✅ dict 1.08 |
| D1-P8 sibling binding 对齐 ≡ 泛化前 | `test_sibling_table_ref_row_shift.py` | 改对齐规则（数 sheet 而非数行 table）⇒ 必红（Task 10 P8） | ✅ |
| D1-P9 框架层零 wp_code 分支 | `scripts/check/check_framework_layer_has_no_wp_code_branch.py` | 加 `if adapter_id=='d1.…'` ⇒ 必红（Task 20 变异反证） | ✅ 扫 6 模块 0 命中 |
| D1-P10 新 spec 未接注册表必红 | `scripts/check/check_sheet_specs_fully_registered.py` | 剔掉 d1 ⇒ 必报漏项（Task 21 变异反证） | ✅ |
| D1-P11 整册 materialize + verify | `scripts/e2e/verify_d1_full_book_real_stack.py` | 去掉兄弟 Table ref 位移 ⇒ 必红（整册门穿过 verify_unmanaged_regions） | ✅ EXIT=0 |
| D1-P12 多区 sheet 自动进位移判据清单 | `test_sibling_table_ref_row_shift.py` | 清单改回硬编码 D4 ⇒ D1-4/8/16 漏覆盖（Task 24 变异反证） | ✅ D1 六张在清单内 |
| D1-P13 三端点耗时 ≤ 基线 110% | `scripts/analyze/measure_d1_sync_endpoints_baseline.py` + 守卫 | materialize 真变慢 20% ⇒ 必红（本轮 Y/子目标B 新增 4 条比对守卫） | ✅ 1.05~1.07× 全 ≤110% |

## P14~P18（前端）

| Property | 判据文件（`components/workpaper/composables/__tests__/`） | 变异证据 | 现跑 |
|---|---|---|---|
| D1-P14 D1-1 迁移金额不归零 | `d1AdjRowsFallback.spec.ts` | prefix 变异 / 去掉读侧回落 ⇒ 必红（G/H 节） | ✅ |
| D1-P15 上游变化不误标人工覆盖 | `d1AdjCellStateMachine.spec.ts` | `snapshot[field]=r.display`（D4 错法）⇒ 3 条打红（I 节决定性反证） | ✅ |
| D1-P16 autoPulled 归一到 source='tb' | `d1AdjCellStateMachine.spec.ts` / 行模型 | 保留布尔标记 ⇒ 语义未定义（design P16） | ✅ |
| D1-P17 第三写入方定序 | `d1CrossSheetWriteOrdering.spec.ts` | 摘掉 OO 门 ⇒ 6 failed（S 节变异 4 处全红） | ✅ |
| D1-P18 下游 computed 回写后正确 | `d1BadDebtDownstreamContract.spec.ts` | currentAudited 改名 ⇒ D1-15 归零（U 节变异 4 处全红） | ✅ |

## Task 34 系统性复跑的真实收获

🔴 **暴露并修掉一条从未真正执行的判据**：`test_d1_05_single_html_adjudication.py::
test_headers_match_d4_4_verdict_verbatim` 引用了从未定义的变量 `actual`
（commit `c28a1640c`，Task 27 起恒 `NameError`）。当时 Task 27 标注「10 用例全绿」
是假的 —— 那条自 2026-09-26 起一直坏，被 pytest 的 collection 顺序或局部跑掩盖。
修根因 = 补 `actual = [sheet.cell(row=5, column=c).value for c in range(1, 11)]`
（从权威模板现读表头行 5 的 A-J 十列，verdict.geometry 记明「表头行 5」），
现读与 verdict 的 `header_A_to_J` 逐字一致 ⇒ 10 passed。
**这正是「系统性变异复跑」而非「只跑一遍看绿」的价值**：局部复跑会放过它。

## 现跑汇总（2026-09-28）

- 后端 D1 判据：202 passed / 2 xfailed（D3 已登记缺口）/ 1 failed（`余额明细表G5-2`
  = G5 lane BP-21 预存，非 D1；它出现在参数化清单里反而印证 Task 24 的参数化真纳入了新 provider）
- 前端 Property 判据：81 + 14 + 11 = 106 passed
- 三端点 P13 复测：materialize 1.072× / extract 1.051× / verify 1.051× 全 ≤110%，
  store-projection/pending 在噪音地板以下豁免 ⇒ 全绿
- 整册门 `verify_d1_full_book_real_stack.py` EXIT=0（受管区 18 / sheet 12 / store item 17；
  materialize 4.6s + extract 0.8s + verify 0.6s = 6.0s；equivalent=True）
