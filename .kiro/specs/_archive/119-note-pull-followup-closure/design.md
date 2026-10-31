# 附注取数收口后续建议逐项修复 — 设计

## §1 现状实证（2026-10-27，只读调查 + 现算）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 离屏同步只登记 D2；provider 只能回一个章节；冻结 77 个编码。前端 109 个 builder（67 个 `…SyncPayload` + 42 个返回多章节的 `…SyncPayloads`），注册表 78 码都有 builder（G6 国企、H5 上市、M3 / N4 国企单边）。按输入分四类：P1 composable 自带快照 9 码（F4 I4 I5 I6 K1 N1 N2 N4 N5）/ P2 Tab 自建 FormData 17 码（L1–L5 L7 L8 M1–M10）/ P3 只依赖外壳回复 33 码 / P4 还依赖跨表、渲染配置、注入等 18 码 | `noteHeadlessDisclosure.ts`、`noteHeadlessDisclosureCoverage.spec.ts`、`note_workpaper_sync_registry.json` |
| F2 | 子表推送规则 118 条（上市 105 / 国企 104 口径对），其中 99 条字段一个都不映射到取数行的期末 / 期初值（取数行只有 ending / opening）⇒ 永远写不出数；且行对上时 `row[f"{vk}_resolved"]` KeyError ⇒ 整张底稿回滚。209 个口径对里 74 对表名在该口径模板中不存在（生成器取先扫到那一版的表名、两版都填章节）。旧格式附注 `_pick_table` 表名对不上回退首表；标题不符按 `section_title` 改投到同前缀另一节 | `gen_subtable_push_rules.py`、`engine._push_note`、`note_writer.locate_table` |
| F3 | 主表规则章节错挂：H10 上市 五、46、L6 五、40 / 八、40、N3 五、22 / 八、22、F5 写成合并口径编号 五-62-1 / 五-65-1 | `formula_push_rules.json` |
| F4 | 前端披露同步按表名整表替换行、推送按格写，后写的赢；推送写 `_last_sync_wp_id` ⇒ 推送过的章节在取数结果里成了 `synced_before=True`，离屏同步「已有人工填写不覆盖」失效；HTML 同步入口整体替换 `sub_table_data`（没推的子表丢失）；没有任何前后端同格同值对拍 | `wp_disclosure_sync_service.py`、`engine._push_note`、`note_workpaper_pull_service._mark_synced_sections` |
| F5 | 单体模板 `columns[].group` 含「/」0 处、嵌套分组 0 ⇒ 模板层没有三层表头；三层只来自期间层（`note_table_period_layout.json`，读时挂 `_display_layout`） | 现算两版模板 |
| F6 | bindings manual 占位 4668 格（「待审计师手工填或从底稿同步」3619 / 「待 P-1 审计师手工标注」973 / 「未识别列语义」76）；生成时标 `_cell_modes=manual` ⇒ 推送 keep_manual、附注公式与合计回填只写自动格 ⇒ 这些格永远进不来数。编辑器改值不写 `_cell_modes`（只有「清除公式」会批量改 manual） | `disclosure_engine._build_with_binding`、`policy.decide_note`、`DisclosureEditor.getCellMode` |
| F7 | 「列1」是写进数据的：`seed_consol_note_sections.py` multi_header 整列为空即写「列{n}」；上市合并 12 张表 headers[0]='列1'（五-5-6~10 / 五-10-6~7 / 五-16-5~9） | seed 脚本 |
| F8 | 合计判不准：国企单体 16 / 上市 17 / 国企合并 3 / 上市合并 4 张；整表判不准的「多个合计」含 国企 八、22「固定资产情况」（每段合计在段首：一、账面原值合计 / 其中：土地资产 / 房屋… / 二、累计折旧合计 …） | `note_total_terms` 现算 + golden |
| F9 | 模板中文 `check_presets`（其中项 / 余额 / 纵向 / 宽表 / 交叉 / 跨科目 / LLM审核 / 完整性 / 二级明细 / 账龄衔接 / 期间衔接）是审核类，由 `note_validation_engine.PRESET_TO_RULE` 消费，缺「期间衔接」；`section_preset_formulas` 仍调旧生成器，`_check_presets` 非空时旧求和（不分段、其中与减项都加）覆盖按结构生成的预设；`_check_presets` 在 app 内无写入方；覆盖率统计 `calc_formula_coverage` 用旧生成器 | `note_formula_tables.py`、`note_formula_generator.py` |
| F10 | `note_total_recalc` 生产调用方 0 | grep |
| F11 | 合并「前五名」表：按行名跨企业相加、比例列被加总、不重排不截 N | `consol_note_detail_apply_service` |
| F12 | 映射「一条来源行名 → 一个目标」，一条映射吃掉全部同名行；读取层 `_rows_from` 已算出现序号未输出 | 同上、`consol_note_standalone_reader._rows_from` |
| F13 | `_pushed_optional_active` 拉数链路不读，没有界面置 false；`test_optional_deactivated_excluded` 只断言夹具（假绿） | 同上 |
| F14 | `check_structure_lock` 0 调用方；锁按合并章节号存，子企业按单体章节号查 ⇒ 恒 None | `consol_note_structure_lock_service` |
| F15 | 拉数 / 重新汇总骨架取全部模板行，修复前建的模板 required「……」照写一行 | apply / reaggregate |
| F16 | V202：规则模板库 / 结构锁 + 锁企业 / 值确认 4 表 + `consol_note_mapping_rule.promoted_to_template_id`；前端 `useConsolNoteReuse` 0 个组件引用；4 个端点只校验登录；下推写结构锁、子企业保存降级值确认 | V202、`consol_note_mapping_templates.py` |
| F17 | 后端披露表 builder（`disclosure_payload_builder_service` + `disclosure_builders`）app 内 0 调用方，4 个测试文件依赖 | grep |
| F18 | 编辑态 `.gt-cell-editable{justify-content:flex-end}` 也作用于行名格；`gt_note_auto_advance` 未设置即开启 | `DisclosureEditor.css` / `.vue` |
| F19 | edit 级清单比对键 `(file, function, form)`，HEAD 6 个重复键 ⇒ 检查模式恒报错；加 level + ordinal 后 0 重复。清册 index 是 LF、干净检出是 CRLF、检查模式比原始字节 ⇒ 干净检出恒红；`.gitattributes` 已有 3 处同类 `eol=lf` | 生成器、`git ls-files --eol` |
| F20 | `PUT …/formula-gray` 写 `projects.wizard_state`（灰度开关），门禁 = 角色门 + 本项目 edit；清册类别 E、目标默认附注编辑门禁 ⇒ 被卷进覆盖集合，3 个测试红 | 清册、`disclosure_notes.py` |
| F21 | V205 未应用；`word_export_task_versions` 没有 `snapshot_id` ⇒ 全量重启 V205 必 42703；ORM 有、库缺 3 列（`export_jobs_v2.readiness`、`word_export_task_versions.snapshot_id / file_sha256`），磁盘没有迁移加它们 | `/api/health` schema_drift、`schema_version` |

## §2 裁决

- **ADR-1 离屏同步只复用不复制**：快照计算从 SFC 抽成模块函数，Tab 与 provider 调同一个；provider 用工厂声明（取数方式 + composable + 快照 + builder + 章节），在 `effectScope` 里实例化 composable。不离屏挂载 SFC（SFC 依赖外壳 inject / 界面副作用，挂载失败面大）。
- **ADR-2 子表规则宁缺勿造**：取不到值的规则删除（停用仍出现在推送页、仍有崩溃路径）；子表定位只认精确表名。
- **ADR-3 主表审定数归推送、明细归披露同步**：主表金额与报表同口径（试算表审定数，过发布门后才变），披露 Tab 的主表金额是发布前底稿值；推送写过的格在披露同步时保持推送值并逐格回报差异（运行时对拍）。推送只记 `last_sync_source=formula_push` 与推送状态表，不写同步指纹。
- **ADR-4 三层表头不改存储**：模板层没有三层；期间层按 note-pull-header-formula-closure ADR-3 只在显示 / 导出还原。持久化逐列路径会与读时增强成两份真源，且 `_header_paths` 在导出里是「合成 / 加层」信号（见到即画 N 行），故不做。
- **ADR-5 没有绑定 ≠ 人工**：人工 = 用户改过（编辑器标），生成不再把未绑定的格标 manual。
- **ADR-6 结构保护按行标记校验**：子企业保存比对新旧行的下推标记，不依赖结构锁表（锁表随 V202 退役）。
- **ADR-7 前 N 名走专用分支**：行随数据变化，不经映射骨架。

## §3 取数设计（R1 / R2 / R3）

- R1：`noteHeadlessDisclosure.ts` 的 provider 改为 `(ctx) => Promise<{ sections: {section, rows}[] }>`（D2 适配）；新增 `defineHeadlessProvider`（`loader: 'responses' | 'formData'`、`needs: {aging, renderConfig}`、`setup`、`snapshot`、`build`、`post`）；结果按章节展开进 `outcomes`。逐组接入：P1 → P2 → P3 → P4，每组一条等价用例（同一份回复 / FormData 夹具，Tab 路径与 provider 路径 POST 的载荷逐字节相同）。
- R2：静态分桶脚本（仓库外探针）+ 真库回滚探针；删除规则直接改 `formula_push_rules.json`；生成器只输出「字段映射到 ending / opening 且该口径模板有此表」的规则、逐口径写 `table_by_template`；引擎 `_push_note` 对 `*.note.subtable_*` 跳过按标题改投、`locate_table(…, exact=True)` 不回退首表；`row.get(f"{vk}_resolved")`。守卫 `test_formula_push_note_rule_targets.py`：章节存在且标题与规则表对得上（主表）/ 表存在（子表）、字段可取值、与注册表同底稿章节一致。
- R3：同步入口合并后调用 `push_owned.reapply(note, td)`：读本章节推送状态表里最近一次写入（action=write / 状态非人工锁定）的格，按（表名, 行名, 期间）在新数据里找到格，值不同 ⇒ 写回推送值并记差异；响应加 `push_kept: [{table, row, period, pushed, incoming}]`。推送删去 `_last_sync_wp_id / _last_sync_at` 写入；`synced_before` = 有底稿披露同步标记（`_last_sync_sheet` 键，或新写的 `_disclosure_synced_at`）。HTML 入口改浅合并。

### §3.1 R2 清点结论（2026-10-27 现算：静态分桶 + 重药安徽 / 【测试】甲 dry-run 回滚探针）

- 子表规则 118 条 / 209 个口径对：字段一个都映射不到取数行值（取数行只有 `ending` / `opening`）的 99 条 —— 永远写不出数；
  其余 19 条里 5 条按语义删除（F2 跌价准备变动表 / 开发产品 / 周转房：binding 不给子表出行；K2 碳排放配额变动表：
  科目余额不是配额变动；M2「股本（单位：万股）」：试算表金额是元），保留 14 条（均在 `_BREAKDOWN` 合计兜底裁决里，
  10 条只在一版模板有表 ⇒ 口径收窄到那一版；K3「按款项性质列示」上市版补 `table_by_template`「其他应付款（按款项性质列示）」）。
  74 个表名错版的口径对：60 对随删除消失，14 对随收窄消失。
- 主表规则错挂：H10 上市写成 五、46（L4 应付债券）⇒ 改 五、78（注册表）；L6 / N3 / F5 注册表无章节（L6 专项应付款表在 L5 章节、
  N3 递延所得税负债在 N1 章节的未经抵销表里、F5 用了合并附注编号 五-62-1 / 五-65-1）⇒ 删除这 3 条附注规则（取数规则不动）。
- 真库 dry-run（重药安徽）：HEAD 现算 skipped 196（子表规则 105 处全是跳过）/ coverage 227；改后 skipped 99（子表 0）/ coverage 231。
  HEAD 的 196 里 20 处是「binding 声明的分册在本项目不存在」——2026-10-24~25 本项目 131 张已裁底稿移入回收站
  （procedure-trim-generation-delegation-chain），不是推送回归；`test_formula_push_note_skip_pg` 按现算重定棘轮并新增 S / P 两类。
- 引擎：子表规则（`*.note.subtable_*`）只按精确表名定位（`note_writer.locate_table(exact=True)`、`has_table`）、不按章节标题改投、
  缺表不建骨架；取数行没有某字段值键 ⇒ 跳过并说明（原 `row[f"{vk}_resolved"]` KeyError 让整张底稿回滚）。
- 生成器 `gen_subtable_push_rules.py`：只出取得到值的字段、只给模板里真有同名表的那一版、`EXCLUDED_TABLES`（按（底稿, 表名））
  拦住删过的规则；守卫 `test_formula_push_note_rule_targets.py` 断言重跑产出为空。
- 真库残留：`formula_push_state` 里 D2 4 条已删子表规则的状态（和平药房 / 两个【测试】项目）不删 —— 交接只认有效规则
  （`effective_push_rules`），这些状态不再被引用。

### §3.2 R3 实施

- `note_push_ownership.reapply_pushed_cells`：读本章节推送状态（`auto`、有推送值、规则仍有效），同步写过的表里推送拥有的格恢复推送值；
  合计分两种 —— 表里有推送写的数据格 ⇒ 合计是按本表重算的，只在恢复了数据格时用 `note_writer.total_formula` 重算；只有合计格是
  推送写的（合计行兜底写入科目合计）⇒ 与数据格一样恢复。整节 `_manual_override` 不动。`sync_from_workpaper` 与 `sync_from_html`
  都调；HTML 入口按表名浅合并（原整体替换，未推的子表丢失）。「规则仍有效」= 有效规则清单里有、且 `status == "active"`：
  `effective_push_rules` 对本项目停用 / 定义失效的规则仍逐条列出（`status=disabled|invalid`），只判「在不在」会让本项目停用的
  规则继续占着格（变异 B-M12 首轮存活才暴露，原变异与生产等价）。
- 推送不再写 `_last_sync_wp_id` / `_last_sync_at`（只写 ORM 列 `last_sync_source=formula_push` 等）；`synced_before` 只认披露同步写的指纹。
- 响应：`SyncFromWorkpaperResponse` / `SyncFromHtmlResponse` 原先只声明 6 个字段，FastAPI 按 response_model 过滤 ⇒ 服务层早就返回的
  `row_scope_unresolved(_reasons)`（行级合并 fail closed 提示）前端读到的恒为 undefined —— 前端守卫只查源码里「读了这个字段」，假绿。
  响应模型补齐服务层全部键（AST 守卫 `test_response_models_declare_every_service_key`），并把「没有审计年度」的跳过结果改为 422
  （原来构造响应缺必填字段 ⇒ 500）。
- 前端：`utils/disclosureSyncPushNotice.ts` 装在全局 http 实例上（main.ts），三个同步端点响应有 `push_kept` ⇒ 每个章节提示一次
  「…由公式推送维护，已保持试算表审定数」；`_silent`（离屏同步）不弹，由离屏同步汇总（R1）。
- 范围外登记：`POST /api/wp-disclosure-sync/{wp_id}/sync-html` 只校验登录、不校项目成员（对象 id 型，属鉴权基线冻结的那一类）。

### §3.3 R1 实施结果（2026-10-27~28）

- 框架：`headless/headlessFramework.ts` 的 `defineHeadlessProvider`（`prefix` 只取本底稿回复、`needs.aging` 先预取账龄配置、
  `needs.renderConfig` 取渲染配置、`setup` 在 effectScope 里实例化 Tab 同一个 composable、`prepare` = 挂载时的初始化、`build`
  回一个或多个章节载荷、`post` 自定义发送）；provider 按组登记在 `headless/providers/*.ts`（懒加载）；结果逐章节回报
  （synced / skipped / failed + 原因 + 推送保持格数）。副作用置空：保存回调为空、不弹提示、没有组件实例时不挂生命周期 / 不订阅
  事件（`getCurrentInstance()` + `onScopeDispose` 退订），用完 `scope.stop()`。
- 接入 67 / 78 码（D1–D7、F2–F4、G1–G6、G8–G14、H2、H4–H10、I1–I6、J1、J2、K1、K2、K4–K13、L1–L3、L7、L8、M1–M5、
  M7、M8、N1、N2、N4、N5），每码一条等价用例：同一份回复 / FormData，挂载真实 Tab 点「同步到附注」发出的请求体与 provider
  发出的逐字节相同。11 码不接、逐码写明原因（`noteHeadlessDisclosureCoverage.spec.ts` 的 `NOT_YET_HEADLESS`：E1 F1 G7 H1 H3 K3
  L4 L5 M6 M9 M10；原因不许以「待接入」开头、不少于 40 字，清单只许变短）。原 P1–P4 四组按输入来源分，实施时按「快照从哪来」
  逐码处理：Tab 内联的默认行 / 读回 / 快照抽成 `*DisclosureTabState.ts` / `*DisclosureForm.ts` / `*DisclosureSnapshot.ts`，
  Tab 与 provider 调同一函数，P1–P4 常量删除。
- 与 Tab 不完全同路的逐码处理：G4 / G6 的 Tab 回显读不到已存数据（G4 读 `checklist_responses` / `responses`，render-config 实发
  `responses_snapshot`；G6 外壳不读 `G6-disclosure-` 前缀）⇒ provider 直接读本底稿回复，推上次保存的披露表（缺陷登记在下面）；
  H2 的外壳种子内联在宿主里 ⇒ 外壳会种子时这一节跳过并写明原因；H4 的外壳种子是纯函数 `buildH4DetailSeedRows` ⇒ 按同一函数
  复现（取不到 render-config 跳过写明）；K6 国企负债块为空时 Tab 也发 八、43 清理载荷，provider 同样发；J2 上市净负债期末为负另推
  五、17，与 Tab 同；M7 的附注自动取数经新导出的纯函数 `readNoteAutoFillValues`；K11–K13 行身份工厂由调用方注入（Tab 传
  `newRowIdentity('row')`），K12 / K13 读回按版本写字面量模板（K 宽口径守卫按字面量计数，保持 899）。
- 顺带修的缺陷（Tab 与离屏同受益）：M8 快照取 `beginAmount / increaseAmount / decreaseAmount`（行字段是 `beginBalance /
  currentIncrease / currentDecrease`）⇒ 载荷恒 0；M1 国企取 `endAmount / priorAmount`（实为 `beginBalance / endBalance`，上市上年数
  是 `priorYearEnd`）⇒ 两列恒 0，且「合计」输入行当明细发出、builder 再自算一行合计（两行合计、合计翻倍）；K4 国企读回只读
  `value`（回复只有 `remark`）⇒ 已存四段从不读回、下次编辑写回空表；K1 / F4 国企 composable 只读 `applicableStandards.value`，
  Tab 传的是 getter ⇒ 适用准则恒 undefined；D5 Tab 的 `handleDisclosureSyncError` import 写在块注释里 ⇒ 同步失败时 catch 里
  ReferenceError；G7 上市 / 国企、H1 上市、H2 上市 / 国企、H6 的同步调「保存 + 排同步」⇒ 每次同步 800 ms 后又排一次、页面开着就
  无限循环，拆成「只保存」与「保存 + 排同步」（守卫 `disclosureSyncIndirectSelfSchedule.spec.ts`）；L3 国企 / G7 走的批量同步端点
  在项目没有审计年度时读 `results[-1]["synced_at"]` KeyError ⇒ 500，与 R3 单章节同口径改 422 中文原因、整批回滚。
- 浏览器实测抓到的保存丢表（实施前已在 HEAD）：公式推送对旧格式附注兜底写 `_tables` 并标 `_source=workpaper`，编辑器保存时
  `prepareNoteTableData` 对 workpaper 来源一律剥 `_tables`（当它是 `sub_table_data` 的读时投影）⇒ 保存一次，首表以外的表整张消失、
  这次在 `_tables` 上的编辑也丢（【测试】甲 五、1「受限制的货币资金明细」没了、改的 101 回到 100；已按浏览器快照复原）。真库这种
  形态和平 48 / 宜宾 37 / 重药安徽 32 个章节（多表 55 个），尚无已受害的章节。改为与后端 GET 同口径：子表数据投影非空才剥
  `_tables`（`noteTableWritebackPersistedTables.spec.ts`）。推送把旧格式章节标成 workpaper 来源本身未改（下面登记）。
- 已发现、待定或另修（未改）：M1 / M2 / M3 / M6 / M8 / M9 / M10 Tab 把同步函数传给 `useDisclosureAutoSync`（该参数是选项），
  随后 `scheduleAutoSync()` 不带函数 ⇒ 自动同步从不触发，M6 / M9 / M10 页面也没有手动同步按钮（修了会让 M6 / M9 / M10 与模板结构
  不符的载荷开始写附注，需先定）· H3 Tab 自建 `useH3FormData` 从不加载 ⇒ 已存披露行读不回、同步恒 0 · G12 挂载回填无条件按 G12-1 /
  G12-2 重算并保存，G12-1 没数时把已存金额写成 0 · G13 挂载回填先保存、后按 G13-1 填上期 ⇒ 上期数不进保存 · H5 宿主不 provide
  `saveResponse` ⇒ 国企补充披露文字从不保存 · `K7-1-audited-by-type` 没有写入方（K7 自动取数恒取不到）· K1 / G2 / G3 共用章节的
  `_note_texts` 同用键 `listed-audit-note`（互相覆盖）· G4 Tab 回显读不到 `responses_snapshot` · G6 外壳前缀漏 `G6-disclosure-` ·
  L7 整表键读回成功即返回、结论（国企另有专项说明）不再读回 · H2 Tab 不传适用准则 ⇒ `current_standard` 恒单体口径 · M3 builder
  合计把「一、库存股合计」与其「其中」明细一起加 · 公式推送把 `_source` 为空的旧格式章节标成 workpaper（数据仍在 `_tables`、没有
  `sub_table_data`）。接入时报告、本次未复核：H8 国企 Tab 的 TypeError、K12 备注信封丢金额、D4 第 6 段读回。
- 验证：前端离屏同步 76 个用例文件 390 passed；磁盘变异框架批 F 39/39、接入批 G 33/33（首轮 28/30，G-K11 / G-H4c 存活后补
  「行身份走注入工厂」「已存明细不取渲染配置」用例再跑打红，另加 K11b / K5e / K6e）、批量 422 批 H 3/3、保存丢表批 I 3/3、
  J1 导入导出镜像改读共用骨架批 J 5/5（原 category 判据只查「出现过」，改掉一行照样全绿 ⇒ 改为逐行比对）。
  锚点：`useM8FormData` / `useN1FormData` 改动后按 `resync_data_line_anchors.py --only` 平移 15 个锚点（未平移时 M 循环
  `test_formdata_refs_really_hit_the_prefix_filter_and_the_calls` 红）；H slice 位置化清单 family_b 的 H2 上市抵押行读回随代码从 Tab
  移到 `h2DisclosureTabState.ts#L156`，锚点改指新处（HEAD 上原锚点已错 2 行、守卫两侧同红，改后转绿；批 J2 2/2：下移一行 / 去掉
  下标前缀都打红）；K 循环 slice 的 BP-8 / 位置化清单锚点是修复前的历史快照（引入时那一行是 `id: \`row-${idx}\``，HEAD 已不存在），
  不平移。浏览器（chrome-devtools，独立上下文）：真 bundle 动态加载 67 个
  provider，在宜宾（国企 67 码全有）与【测试】乙（上市 F2 / D4）只读演练 —— 拦掉一切非 GET 请求、章节一律经 `sectionGuard` 跳过
  —— 0 抛错、0 写请求、章节号全部落在注册表口径。

## §4 公式与表头（R4 / R5 / R6 / R7 / R8 / R9）

- R5：`_build_with_binding` 没有 binding / manual 无预填值 ⇒ 不写 mode、`_cell_meta[c] = {unbound: true, semantic}`；编辑器 `commitProjectedCellValue` 对 `_tables` 形态的格写 `_cell_modes[c]='manual'`（底稿来源表的投影格不写）；修复工具 `scripts/fix/fix_note_manual_placeholders.py --dry-run|--apply --project`。
- R6：seed 脚本空标签列表头取单体同名表 headers[0]；`noteColumnTree` 叶子名空时不回落「列N」；【测试】合并项目 consol_note_data 的「列N」表头一次性修正。
- R7：`total_terms` 新增段首合计判定 —— 所有合计都是本段第一行（分段标题式「一、…合计」）、下面是明细 ⇒ 每个合计 = 本段明细（段内「其中：」只许是段内第一行，表示列举构成）；前端 `noteTotalTerms.ts` 同步；golden 重生成后逐表核对新增判定。
- R8：删 `section_preset_formulas` 里的旧生成器调用；`calc_formula_coverage` 改用 `section_preset_formulas`；`PRESET_TO_RULE` 补「期间衔接」（映射到跨期衔接规则）；守卫：两版模板出现的中文预设名 ⊆ PRESET_TO_RULE 键。

### §4.1 R7 / R8 实施结果（2026-10-27）

- R7：`note_total_terms._segment_head_terms` 先于原判定（前端 `segmentHeadTerms` 同一判定，golden 交叉锁）。逐表对照（工作区前后
  两版逐表现算）：单体判不准的合计行 192 → 166、含判不准行的表 142 → 136，变化的恰是 6 张国企表（八、21 以成本 / 以公允价值计量、
  八、22 固定资产情况、八、25 油气资产、八、26 使用权资产、八、27 无形资产情况，共 26 个段首合计，每个 = 本段明细，八、27 的「……」
  不算）；上市 七、8 表2/4/6、九、2 表8、合并 九-1-8 照旧判不准；合并模板 51 不变。表首单个分段标题式合计（「（一）…」下面是明细）
  同样按本段算（真模板没有这种表；`test_note_formula_tables` 一条合成用例按新判定改写）。
- R8 实证：旧生成器在两版模板上只产出明细行取数公式（行上 `account_codes` 215 格、`report_row_code` 18 格），与结构预设零撞目标；
  真库 2042 条附注 0 条行上带 `account_codes` / `_wp_mapping`、0 条带 `_check_presets`（`report_row_code` 只出现在指引文字里）。
  实现偏离 §4 原文一处：不整删旧生成器调用（`test_note_formula_l4_extension` 的「明细行按科目取 TB」是既有能力），改为不再传预设名、
  同目标以结构为准（`setdefault`）、比例 / 说明列不取数 —— R8.1 要的是「求和结果不再覆盖」，这样同样成立且不丢能力。
  覆盖率函数实名 `compute_formula_coverage`（无生产调用方，只有测试）改用同一套预设、按全部表的金额列计。
- 「期间衔接」：新增 `ValidationType.PERIOD_CONTINUITY` + 执行器 `_execute_period_continuity`（本期列期初行 = 上期列期末行；有上年附注时
  上期列期末 = 上年本期列期末；按行名认行、空格不比、认不出结构 skip）。生成附注的注入白名单 `_VALID_VALIDATION_PRESETS` 原是另一份
  11 项清单，改为由 `PRESET_TO_RULE` 派生；真库 785 条附注带 `_validation_rules`，均不含「期间衔接」—— 重新生成附注时补上
  （注入在新建的表数据上做，不改存量）。三份「恰好 11 项」的契约测试按授权新增改为 12。
- 范围外登记：旧生成器的英文预设名分支（求和 / 变动 / 账面价值）已无生产入口，只剩测试引用，留待删除；`test_note_preset_wave4` 4 条
  读不到仓库外的校验预设 md（HEAD 同红）；`test_consol_note_formulas::test_seed_counts_on_real_templates` 两版「五-34-1 交易性金融负债」
  首行科目种子缺失（HEAD 干净检出同红，非本 spec）。
- R9：删 `note_total_recalc.py` 与 `test_note_total_recalc.py`，`test_note_expandable_rows` 改指 `note_total_terms`。

### §4.2 R4 / R5 / R6 实施结果（2026-10-27）

- R4 核实（现算两版模板）：国企 308 张表、上市 515 张；`columns[].group` 含「/」0、嵌套分组 0、`multi_header` ≥ 3 行 0 ⇒ 模板层
  没有三层表头，按 ADR-4 不改存储。
- R5 判定 `disclosure_engine.binding_cell_unbound`：没有 binding / 没有取数来源，或 binding 为 manual（或来源 manual）且没有预填值
  （预填 0 也算值）。生成：值留空、不写 `_cell_modes`、`_cell_meta` 记 `unbound`（locked 照旧标 locked）。重新生成合并
  （`note_cell_merge`）对 unbound 且新值为空的格保留旧值（推送 / 公式 / 人工写入的），生成给了值就用新值并去掉标记；刷新
  （`refill_sections`）跳过这类格；推送对无模式格照常写入。编辑器只给用户直接改的那一格标 manual（合计、横向公式等派生写入不标），
  ✏️ 在编辑态点了恢复自动（有绑定的格记 auto、unbound 的格去掉模式，值不清）；期间并列 / 续表合成表的模式与元信息随列平移。
- R5 存量：`scripts/fix/fix_note_manual_placeholders.py` 只改「manual、值空、无预填 / 备份值、现行 binding 判 unbound」的格（用户
  「一键清除公式」改的 manual 不动；`_tables` 与顶层镜像各自按格判），默认只出报告，`--apply` 只对【测试】项目、写前备份。【测试】甲
  改回 6945 格（另顶层镜像 2168），重跑 0；真实项目只出报告，共 23661 格（医疗器械 3723 / 宜宾 3864 / 和平 2025 3783 / 重药安徽 3864
  / 华氏 1482），实写待用户定。
- R6：合并种子 `merge_multi_headers` 整列留白写空；标签列表头取单体同名表（表名去空白比，同名取第一张首列非空的）的首列表头，取不到
  留空；Word 同步工具三处建 / 重建条目同法补。只改平表头，`multi_header` 照 Word（Word 同步工具按它比对，改了会让「无可写」守卫红）。
  上市合并 12 张「组合计提项目：…」表 `headers[0]`「列1」→「账龄」/「账  龄」，种子 `--check` 一致。已存数据用
  `scripts/fix/fix_consol_note_placeholder_headers.py`（只改标签列的「列N」，模板也是占位时留空；同样只限【测试】项目实写），【测试】集团
  改 2 条（五-5-6）。前端各列树与合并附注页本就不兜底「列N」，加守卫钉住。
- 变异补出的用例：locked 无来源、unbound 只挡空值覆盖、表名去空白、同名表取第一张非空、生成调用补表头、两个修复工具的【测试】限定 /
  备份内容 / 不改已读对象 / `--all --apply` 不实写、编辑器写入函数把选项传下去（首轮 E-F9 存活即此处）。

## §5 合并设计（R10 – R17）

- R10：新模块 `consol_note_topn.py`（`topn_limit(表名)`、`rerank(各企业来源行, 列角色, 分母, 集团内单位)`）；apply 在映射累加前分流；重新汇总汇总节点按下级已保存行同法重排；比例列分母 = 同章主表合并期末合计，取不到留空回原因。
- R11：`_rows_from` 输出 `_occurrence`；映射元素可选 `source_occurrence`；suggest / 自动映射 / apply 用（行名, 序号）；apply 对同一来源行只累加一次。
- R12：读取层带出 `_pushed_category / _pushed_optional_active`；apply 跳过 false；指纹排除；e2e 用例改走读取层 + apply。
- R13：`update_note` 比对新旧 `_tables`：旧数据中 `_pushed_category='required'` 的行在新数据里必须仍有同 `_pushed_row_id`、同行名比较键、标记未剥离；否则 409 `PUSHED_ROW_PROTECTED` 列行名。
- R14：编辑器行名格对固定行只读（tooltip 写明「集团下推的固定行」）；可选行开关；删 `NoteTableEditor.vue` 与 components.d.ts 登记。
- R15：apply / reaggregate 骨架先去掉占位行（dynamic_zone / 占位行名），按行名重映射手工 / 锁定格与已存行。
- R16：删路由文件、3 个服务、4 个模型 + 列、`useConsolNoteReuse` 与 apiPaths；下推去掉 `_activate_structure_lock`；`on_note_section_saved` 只标 `is_stale`；suggest 去掉规则模板级；新迁移删表 / 删列 + 回滚脚本。
- R17：删服务与包与 4 个专属测试；PG 用例故障注入点改到现行路径；守卫改为文件不存在 + 全仓无 import。

### §5.1 R10 – R16 实施结果（2026-10-27）

- R10：识别 = 合并模板表名「前 N 名」（两版共 4 张：国企应收 / 预付 / 其他应收、上市其他应收）。列角色按表头：比例列（比例 / %）、
  文字列（性质 / 账龄 / 原因 / 说明 / 备注 + 标题行库判说明）、其余金额列，排名用第一个不含「准备」的金额列。分母 = 同章第一张
  「按账龄披露 / 列示」表本节点已保存的期末账面余额（有小计取小计，即扣准备前的毛额，否则取合计），按表头语义认列，不写死章节
  对照；取不到 ⇒ 比例留空、`_topn.reasons` 写原因。同名单位按 `name_key` 合并；集团内单位 = 企业树全部企业名，不进排名；手工 /
  锁定格按单位名称对到新行（对不上的进 `lost_protected`），合计按含手工值的行重算。汇总节点只能基于下级已保存的前 N（下级第 N
  名之后的单位看不到）⇒ `_topn.approximate`，界面 `ConsolNoteTopnNotice` 写明；差额户不参与；映射里排除的企业照样不计入
  （数据叶子拉数与对汇总节点直接拉数两条路都判）。自动映射跳过前 N 名表（不建明细模板）。
- R11：出现序号键 = 去空白行名；不进结构指纹（与 R11 前算法实算值逐字相同，已确认的绑定不失效）。建议只对重复的行名逐个给
  （第 k 次出现对模板第 k 个同名 / 别名行；模板只有一个同名行时都对它，此时按序号确认过的历史优先）；旧规则不带序号 = 全部同名行，
  apply 记 `consumed`，同一来源行被两条映射认领时只累加一次。
- R13 / R14：保护在独立模块 `note_pushed_row_guard`、由 `update_note` 调用（不接已退役的结构锁）。类别缺省按固定行算，前后端同口径。
  编辑器固定行行名格只读 + 锁标记；可选行编辑时可勾「本企业不适用」，查看时只在不适用时标出。删 `NoteTableEditor.vue`（0 挂载）
  及其 components.d.ts / 行数基线 / 域边界债务登记。
- R16：删整个 V202 路由（含科目参考、待更新汇总两个只读端点：前者 0 调用方且越权读别的项目，后者与现行 `is_stale` 横幅重复）、
  3 个服务、模型文件、`promoted_to_template_id`、`EventType.CONSOL_NOTE_VALUE_CHANGED`（从未有发布方）、`useConsolNoteReuse` 与
  apiPaths、建议的规则模板级（前端「规则模板」匹配方式中文名一并删）；下推请求体不再有 `activate_lock`（旧前端带了照常下推，
  模型不禁多余字段）。保留 `on_note_section_saved` 的标 `is_stale`（只看已确认 / 结构已变化的绑定，不再收行数据、不算值指纹）与
  `find_previous_year_rules`（只读 `consol_note_mapping_rule`，仍零调用方，接不接进预览要产品定）。迁移另起 V208（不改 V202：
  运行时迁移按版本记 checksum），先删列再按依赖反序删表；R208 按 V202 原样重建（守卫逐条比对语句）。
- 范围外登记：`ConsolidationIndex.vue` 删掉的 `consol.note_mapping_template_promoted` 分支本就只能由已删的提升端点触发。

## §6 工程（R18 – R24）

- R18：行名格加 `gt-cell-editable--label`（flex-start）。R19：默认 `=== 'true'`。
- R20：`_POINT_KEY = (file, function, form, level, ordinal)` 只用于比对，`build()` 断言唯一，自检样例加「同函数同门禁两处」。
- R21：`.gitattributes` 加 `backend/data/authz/*.json text eol=lf`；两个 `check_against` 与双生成测试按 `\r\n→\n` 归一比较。
- R22：`note_write_target_declarations.json` 加 keep_current 声明（理由 + 证据）；重生成清册。
- R23：提交树上现算 `_IDENTITY_ONLY_BASELINE / _PREFIXED_…`，常量与注释改为现算值。
- R24：V205 开头补 3 列 `ADD COLUMN IF NOT EXISTS`、类型转换改 DO 块按列类型判断；R205 同步；`MigrationRunner.run_pending()` 落本地库并复查 health。

## §7 验证

- 每批：相关后端 / 前端用例 + 磁盘变异（摘掉修复点须红在预期断言）+ 对照 HEAD 干净检出逐条归因 + 浏览器实测（【测试】项目）。
- 提交：fetch → 干净临时检出（要提交的树）跑本 spec 与上一 spec 的全部用例 → 两份鉴权清册在该树上重生、`--check` 为 0 → 提交 → 推送当前分支 → 主工作树对齐。
