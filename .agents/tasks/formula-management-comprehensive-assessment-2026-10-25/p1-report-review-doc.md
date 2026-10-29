# 公式管理阶段一报告（36 分修订版）：R3-01~07 均已关闭，剩余是计分说明与验收清单的小缺口

本版按上一轮意见把第 20 项拆成回滚、删除、恢复三个子能力计分（1/2/0，取最小为 0），把公式管理中心“保存全部”与新增报表行被服务端拒绝后仍报成功的情形计入第 16 项主路径（2→1），并在规则（1）（5）写明“正常前置下可触发”与子能力粒度，总分由 38 降为 36/100（1.8/5），成熟度仍为“集成原型级”。新数字与新判断经源码、只读 SQL 和仓库外脚本复算全部成立：写请求 23 处/13 个文件、GET 120 处/44 个文件，builder 109/79 即 67/57 加 42/25 且三个提交结果相同，第 16、20 项的新分值与所引代码一致；上一轮 R3-03 说 109/79 不可复现，是我自己的统计口径错了。全文没有把文件、组件、路由、绿测或 Playwright 规格写成用户链路已实现，F-01~F-04 与 P1R-01~07 维持关闭，也没有与 36/1.8/集成原型级矛盾的残留数字。剩下五处都不阻断：第 13、17 项同属“局部”却一计 1、一计 2；“删除 2”的理由没回应规则（1）新加的并发示例；P0-2/R2 的少参清单漏了 `SUM_ROW`；R7 的回滚验收在入口隐藏后无法执行；三处措辞与本版事实不符。

Watch for: **confirmed** — 第 13 项与第 17 项同被规则（5）列为“局部”，却分别计 1 与 2，依据栏没写“局部”怎么折分，第三方可得 35~37（叠加 §1.3 已列读法最高 39，档位不变）；**confirmed** — `SUM_ROW` 少于 2 个参数时恒返回 0 且 ok、与数据无关，不在 P0-2/R2 的清单里，也不会被“缺引用”判据接住；**confirmed** — R7 一边要求回滚入口只对能定位的历史显示，一边要求“对表间审核与底稿公式的历史点回滚，界面报失败”，前者落地后后者无法执行。

**Verdict**: APPROVED

## High-level view

上一轮七项意见都已关闭，第 16、20 项的新分值与所引代码一致（依据见 Details 末节）。R3-03 的原意见不成立：`export\s+function\s+build\w*SyncPayload` 不加词尾边界时同时命中复数名 `…SyncPayloads`，109/79 在工作树和三个提交上都能复算出来，这是我上一轮的统计错误。

计分按文复算为 36，小计与总分自洽。剩下的不确定在“局部”怎么折分：规则（5）把第 13 项（Runtime/Tier A 不读全局层）和第 17 项（3/7 域接推广）归为同一类，一计 1、一计 2，依据栏没说区别。第 20 项“删除 2”只论证了缺 `expected_version` “不是确定性错值”，没回应规则（1）的“不可控写入”与“并发修改同一公式”示例；第 20 项取最小仍为 0，总分不受影响。

P0 六项与定级理由没有变化。按“结果是否被改成 0”划界后，`SUM_ROW` 单参漏网：终点取空串、区间恒为空，返回 0 且不记错误，也不经过取数查找；系统定义里没有这种写法，暴露面只在用户自写公式。R7 的内容与验收互相矛盾，照抄进 spec 会得到一条无法执行的验收。

另有三处措辞与本版事实不符：R3-03 行说 `[V]`“口径或代码已变”不成立，同一行又说差别只在口径；“其中 2 个含登录态写入”漏了 `formula-engine-e2e.spec.ts`；§5.4 的“删除、恢复和回滚按域分裂”中的“恢复”容易与第 20 项“删除后恢复，各域都不存在”混淆。

<details>
<summary>Issues (5)</summary>

1. **R4-01 第 13、17 项“局部”折分不一致（非阻断，confirmed）** — 在规则（5）或第 13 项依据栏写明“局部”如何折分（如名称要求全覆盖的“全轨消费”在主执行轨缺失时只有局部材料，按刻度计 1；主要入口已挂载、只缺部分域时按挂载层计 2），并把第 13 项计 2 的读法补进 §1.3 计分敏感性（最高 39）。
2. **R4-02 “删除 2”的理由未回应规则（1）（非阻断，likely）** — 写明删除不触发“不可控写入”、也不属 P0 ② 的理由（删除后的状态正是删除者要的“该公式位没有公式”，P0-6 写入的是没人审阅过的定义），或把删除计 1；两种处理下第 20 项与总分都不变。
3. **R4-03 P0-2/R2 的少参清单漏了 `SUM_ROW`（非阻断，confirmed）** — R2 验收改成通用判据（实参少于该函数最少参数个数一律非 ok），例子补 `SUM_ROW('BS-001')`，并注明 `AUX`/`NOTE`/`WP`/`ROW` 少参落入“缺引用”判据。
4. **R4-04 R7 的回滚验收与入口隐藏冲突（非阻断，confirmed）** — 验收改为“这两类历史不显示回滚入口；显示入口的历史在服务端拒绝时界面报失败、表格不变”。
5. **R4-05 三处措辞与本版事实不符（非阻断，confirmed）** — R3-03 行改为“`[V]` 所说代码已变、以及把 109/79 当作对 67/57 的勘误都不成立”；“2 个含登录态写入”改为 3 个并注明 `formula-engine-e2e` 默认跳过；§5.4 的“恢复”改为“恢复上游”。

</details>

<details>
<summary>Details</summary>

## 第 13 项与第 17 项同为“局部”，一计 1、一计 2

**非阻断，confirmed。** 位置：§1.2 规则（5）、第 13 项与第 17 项、§1.3 计分敏感性。

规则（5）新写的粒度条款是：“按域或作用范围的覆盖缺口（如第 13 项 Runtime/Tier A 不读全局层、第 16 项合并附注没有项目入口、第 17 项只有 3/7 域接推广）记为‘局部’，在该项分值内体现”。第 16 项另有规则（1）封顶，可以不论；第 13 项与第 17 项都只有覆盖缺口、都没有引规则（1），第 13 项计 1，第 17 项计 2。刻度里“局部”出现在 1 分档（“仅已编码/局部材料存在”），第 17 项的“局部”却按 2 分档（已挂载）处理，规则没有说哪一种覆盖缺口落 1、哪一种落 2。

报告的做法可以有一致的解释：第 13 项名称里的“全轨”是检查目标本身，主执行轨（Runtime、Tier A）不读全局层，目标能力只在初始化、预填两条辅助轨上有局部材料，于是落 1；第 17 项名称不要求全域，3 个域的入口已挂载，于是落 2。这个解释没有写进规则或依据栏，第三方按字面可以把两项都读成 1（总分 35）或都读成 2（37）。叠加 §1.3 已列的两种 +1 读法，最高是 39，不是现在写的 38；各种读法仍在 21~40 档，成熟度不变。

## “删除 2”的理由没有回应规则（1）的并发示例

**非阻断，likely。** 位置：§1.2 规则（1）、第 20 项“删除”子能力、§6.2 P0-6、§6.3 P1-8。

规则（1）本版补写了正常前置的例子，其中有“并发修改同一公式”；触发条件也不只确定性错值，还有错误成功与不可控写入。第 20 项给删除计 2 的理由是“删除缺 `expected_version` 是并发丢失更新风险，不是确定性错值”，只排除了其中一种。`wp_formula.py::delete_formula` 按 id 删除、不收版本号，`formula_templates.py::delete_template` 只收模板 id：另一个用户刚改过同一条公式时，删除照样成功，删掉的是删除者没见过的新版本。P0-6 同样是缺版本校验（用户审阅的是旧内容，写入的是没见过的新内容），却定为 P0 ②，删除只在 P1-8。

两者有实际区别：删除后的状态（这个公式位不再有公式）正是删除者要的结果，P0-6 写进去的却是没人审阅过的定义；第 20 项“回滚 1”对“不可控写入”的用法（写入值取自客户端请求体）也与这个区分一致。把这层区别写进依据栏即可；如果不采纳，删除按规则（1）计 1。两种处理下第 20 项都是 0，总分不变。

## P0-2 的少参清单漏了 `SUM_ROW`

**非阻断，confirmed。** 位置：§6.1 第 4 条、§6.2 P0-2 机制与修法栏、§9.1 R2 验收。

本版按“结果是否被改成 0”划界，清单是 `IF` 不是 3 个参数、`MAX`/`MIN` 少于 2 个参数、`ROUND()`、`AUX` 只给科目。`formula_engine._handle_sum_row` 只有一个参数时把终点设为空串，循环条件 `start_code <= code <= ''` 对任何非空行次都不成立，于是 `SUM_ROW('BS-001')` 返回 0 且不写 `errors`，与上下文数据无关，`SUM_ROW()` 同理。它也不会被 R2 的“缺引用 → 非 ok”接住，因为这条路径根本不做取数查找。真库 `report_config` 318 条公式里 65 条含 `SUM_ROW`，全是两参，`backend/data` 下的 JSON 也没有单参写法，暴露面与清单里其他函数一样只在用户自写公式。

`AUX`、`NOTE`、`WP`、`ROW` 少参时都会落到一次查不到键的取数（`NOTE('五、1')` 取空行名，`ROW()` 取空行次），R2 的缺引用判据能覆盖。建议 R2 验收写成通用判据“实参少于该函数最少参数个数一律非 ok”，例子补上 `SUM_ROW('BS-001')`。函数注册表里的 `arity` 不是最少参数（`TB` 登记 2 但允许单参取默认列，`AUX` 登记 3 但允许两参），验收不能直接引用它。

## R7 的回滚验收在入口隐藏后无法执行

**非阻断，confirmed。** 位置：§9.1 R7。

R7 内容写“回滚入口只对服务端能定位的历史显示”，验收写“对表间审核与底稿公式的历史点回滚，界面报失败且表格不变”。按源码，这两类历史一定定位失败：表间审核由 `rollback_from_log` 抛 400，底稿公式历史 `module=workpaper`、没有 `slot_key`，由 `_locate` 抛 404。入口按 R7 隐藏后，验收里要点的按钮不存在。两条修法本身都对，验收要分开写：这两类历史不显示回滚入口；对显示入口的历史，服务端拒绝（例如定位不到的旧报表条目 404、版本冲突 409）时界面报失败、表格不变。这条会直接进 spec 的验收清单，宜在报告里先改好。

## 三处措辞与本版事实不符

**非阻断，confirmed。**

§0.4 R3-03 行说“`[R3]`‘24 种口径无一得 109/79’与 `[V]`‘口径或代码已变’都不成立”，同一行又说“两组数都可复现，差别只在口径”。`[V]` 的原话是“口径或代码已变”，口径这一半成立；不成立的是“代码已变”，以及 `[V]` 把 109/79 当作对 67/57 的“数字修正”。

§0.4 R3-02 行写“其中 2 个含登录态写入”，第 25 项与 §11.3 第 17 条也只点名自定义底稿公式绑定与全局刷新两个规格。`e2e/formula-engine-e2e.spec.ts` 同样在界面登录后打开报表配置、改公式并点保存，只是未设 `RUN_FULL_E2E=1` 时整体跳过，应算第 3 个含登录态写入步骤的规格。第 25 项的 L1 结论不受影响。

§5.4 写“预览、审批、停用、删除、恢复和回滚按域分裂”。第 20 项把“恢复”定义为删除后恢复，并判定各域都不存在；§5.4 说的是恢复上游（报表、推送有，tb_detail 没有），宜写明，否则读者会以为删除后恢复在某些域存在。

## 关闭判断的核对依据

R3-01：`formula_settings.py`、`formula_templates.py` 的路由里没有恢复端点；`formula_settings/stores.py` 的项目层删除是物理删除、全局删除是软删，`wp_formula_service.delete` 调 `db.delete`，回收站 `_RECYCLABLE_TABLES` 的 12 类对象不含公式表。回滚对 `cross_check` 历史抛 400、对 `module=workpaper` 历史（无 `slot_key`）抛 404，而 `canRollback` 只看角色、动作与旧公式，`onRollback` 带 `validateStatus: s < 600`。小计 9/9/7/5/6 合计 36，§1.3 的 32 与 38 两端按现分值复算一致。

R3-02：6 个规格与报告列举一致；`ci.yml` 只跑 pytest 与 vitest，render-smoke 只跑 `tests/render-smoke/` 且工作流未设 `RENDER_SMOKE_BACKEND_URL`，`formula-runtime-completion` 只检查刷新规格的文件形状。真库 `wp_formula` 29 行都是“Playwright自定义底稿”（编码 `PW…`），全属项目 `37814426…`。

R3-03：上一轮说 109/79 不可复现是错的。非测试 `.ts/.vue` 不加词尾边界得 109 个定义/79 个文件，其中单数结尾 67/57、复数 42/25（3 个文件两类都有），含测试 111/81；`git grep` 在审计基线、`072cb8459`、`40561d2c6` 上结果相同。

R3-04：按包围参数的最内层调用归属方法（跳过字符串、注释与泛型实参 `api.get<T>(`），得 POST 19 处/12 个文件、PUT 4 处/3 个文件、GET 120 处/44 个文件，23 处写请求的分布与 §6.6 逐项相符。`onSaveAllFormulas` 的底稿公式 PUT、新增报表行 POST 都带该参数，`utils/http.ts` 的成功拦截器不看状态码，`wpFormulaSaveNotice` 只看 `eval_warnings`；`wp_formula.py` 对不支持的函数与校验问题返回 422、缺版本 428、版本冲突 409；新增行编码取 `CUSTOM-{行数+1}`，两人同时在同一报表节点新增时，后到者被 `save_overrides` 拒为 428。真库 `formula.changed` 只有 1 条（`module=workpaper`、`action=create`）。

R3-05、R3-06：`_mergeSavedTbSummary` 读 `data.rows`/`rows`，接口返回 `content`；源码里以 `tb_summary_*` 为键的调用方只有试算平衡表页与高级查询，`consol_worksheet_data` 的其余读者（整表 GET、上年取数、Runtime 合并工作底稿读取器）按调用方给的表键读；真库仍只有 1 行、断开标记 0。各 `_handle_*` 的少参与多参行为与 §11.3 第 19 条一致。

R3-07：`*.round2.*`、`*.round3.*` 的 SHA-256 与报告所记前缀一致，`p1-report-review.*` 在本轮写入前与 `*.round3.*` 逐字节相同。本轮写回同一路径，下一次修订引用本轮前请照例先另存副本。

F-01~F-04、P1R-01~07：本版只调整了轨迹与引用，结论不变。残留扫描（`\d{2}/100`、`/5`、`→`、档位名、维度小计、“N 分”）只在 §0.4 的历史行与轨迹说明、§1.3 的轨迹句命中旧数字，均标为历史。

HEAD 已从报告所记的 `40561d2c6` 前移到 `b5fc200e0`（2026-10-26 00:39 的 S-cycle 提交），两者之间只改 5 个 S 循环联动文件，其中 `wp_account_mapping.json` 只给 S6、S15、S17、S20、S33-5 加了 `linked_workpapers`，推送只读 D~N 编码；所引公式路径与工作树未提交改动都不受影响。

</details>

<details>
<summary>File map</summary>

- `report.md` — 被复核的阶段一最终报告（36 分修订版）；与 HEAD 中的上一版相比改了 §0、§1.2、§1.3、§2、§4.2、§5.4、§6.1~6.4、§6.6、§7、§9.1、§11.3~11.4、§12。
- `p1-report-review-doc.round3.md` / `p1-report-review.round3.json` — 上一轮复核原文（R3-01~07），本轮写入前核对哈希一致。
- `p1-report-review-doc.round2.md` / `p1-report-review.round2.json`、`review-doc.md` / `review.json` — 第二轮与第一轮复核。
- 证据：`00-ground-truth.md`、`10-architecture.md`、`11-coverage-matrix.md`、`12-global-conflict-edit-template.md`、`13-lineage-governance-tests.md`、`p1-00-baseline-recon.md`、`p1-10-defect-verification.md`、`p1-20-new-angles.md`。
- 只读源码：`services/formula_settings/{rollback,audit,stores,project_ops,legacy_report,errors,definitions}.py`、`services/wp_formula_service.py`、`routers/{wp_formula,formula_settings,formula_templates,formula_audit_log,report_config,recycle_bin,consol_worksheet_data,custom_query}.py`、`services/formula_engine.py`（`_handle_*` 与注册表）、`services/formula_ref_preload.py`、`services/formula_runtime/value_loader.py`、`services/formula_push/bindings/note_direct.py`；前端 `components/formula/{FormulaHistoryTab,FormulaManagerDialog}.vue`、`components/formula/composables/useCrossCheckRules.ts`、`views/TrialBalance.vue`、`utils/http.ts`、`e2e/*.spec.ts` 与 `tests/e2e/draft-refresh-regression.spec.ts`；`.github/workflows/{ci,governance-checks}.yml`；`backend/scripts/check/check_formula_runtime_completion.py`。
- 只读 SQL：`audit_log_entries`（`formula.changed`）、`wp_formula` 按底稿与项目分组、`consol_worksheet_data` 行数、`report_config` 中 `SUM_ROW` 写法计数。
- 仓库外临时脚本（已删除）：builder 多口径计数、`validateStatus` 调用面扫描、报告前后版本差异、`wp_account_mapping.json` 两个提交间的条目差异。

本轮未运行测试，未写数据库或仓库源码；只改写本复核文档与 verdict JSON。

</details>
