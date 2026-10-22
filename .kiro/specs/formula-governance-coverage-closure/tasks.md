# 任务清单：公式治理全覆盖收口

> spec：`formula-governance-coverage-closure` · requirements R1~R7 · design §1~§11
> 实施顺序：R1 → R7a → R2 → R3 → R4 → R6 → R5 → 交付。每完成一组立即提交 WIP（多会话并发，未提交改动有被覆盖风险）。

## 1. 越权修复（R1）

- [x] 1.1 `formula_debug.debug_formula` 首句校验请求体项目 readonly；非成员 403 且不取数（R1.1）
- [x] 1.2 `wp_user_formulas` 列表 / 保存 / 恢复预设改用 `authorize_wp_read` / `authorize_wp_edit`（R1.2）—— 勘误：生产本已挂 router 级可见性门，这是第二道（design §2.1）
- [x] 1.3 `validate_formula` 反查底稿项目 + 请求体项目一致性 + 预览用反查项目（R1.3）
- [x] 1.4 `import_data`：带项目校验 readonly；`persist` 需写预设角色；管理员写数据库预设、其余提交候选；切断在线端点对 seed 文件的写入（`upsert_seed_presets` 保留给离线生成脚本）（R1.4 / R1.5）
- [x] 1.5 `reports.consistency_check` 改 `require_project_access("readonly")`；0 条可执行时 `no_result`；前端审核对话框空态；配置公式改真实严格求值（`report_audit_checks.py`）；前端映射透传汇总计数与分类（R1.6）
- [x] 1.6 端点级测试：`tests/formula_settings/test_formula_endpoint_authz.py`（权限世界真实判定链，业务层计数桩：被拦请求 0 次业务调用）+ `test_draft_refresh_endpoint.py` 门禁调用断言；一次性变异（各端点模块里把判定换成放行）4/4 被测出（R1.1~R1.6）
- [x] 1.7 鉴权守卫第三维 `tests/test_project_endpoint_authz_body_carried.py`：额外项目级标识证明链 + 绑定检查、已修钉子（本维 6 个 + 路径维 2 个）、合成样本与真实源码 AST 变异双向；冻结仅登录 93 / 无鉴权 5 / 自鉴权 1。共享基线第一维现算 200（常量 207，未改共享文件，见 design §2.1）（R1.7）
- [x] 1.8 第三维抓到的公式链路端点：一键刷新 / 回滚 / 刷新范围 / 新增自定义预设 / 批量刷新取数 / 附注公式开关补项目级判定；前端一键刷新入口改「合伙人 + 本项目编辑级成员」；范围外发现登记 design §2.2（R1.7 / R1.8）

## 2. 表间审核严格取数（R7a）

- [x] 2.1 新模块 `formula_ref_preload.py`：PREV / AUX 预载与严格缺数报错；AUX 走 `get_active_filter(strict=True)`，读库包保存点；表间审核 `_evaluate` 先按值代入再求值（`enable_prev/aux=False`，不经 report_engine 预载分支）；报表「审核」的配置公式经同一入口自动受益。`report_engine` 改调并删除重复分支 —— 该文件正被另一会话修改，留待其提交后收口（design §3 调整）（R7.1）
- [x] 2.2 更新 `test_user_rules_run…` 断言（AUX 已进支持矩阵，改断言具体原因）；`test_formula_ref_preload.py` 10 例（AUX 缺数 + 另一侧 0、PREV 无上年、前缀聚合与上年缺科目为 0、4 参按名称 / 编码且只取当前数据集、3 参类型合计、三类报因、写法识别不了、`TB_AUX` 不被误认、非严格置 0、上下文缺失）+ `test_report_audit_checks.py`（勾稽 / 合理性真实求值、本项目适配生效）；一次性变异（去掉严格报因 / 回到旧口径）3/3 打红且红在「判成通过」（R7.1）

## 3. 推送规则纳入治理内核（R2）

- [x] 3.1 `definitions` 加 push 域；`push_settings.py`：`PushStore`、`validate_push_definition`、`effective_push_rules`（R2.1~R2.3 / R2.6）—— 补第五类拒绝「推送取数给不出数」`push_context_errors`（design §4.5）；`_structure` 收而不存、读出按清单补
- [x] 3.2 接线：`get_store` / `validate_definition` / `display_formula` / `rollback` / `dependencies` / `WIRED_DOMAINS` / 审计模块标签（R2.1 / R2.8）；公式目录随 `DOMAINS` 纳入 push 域
- [x] 3.3 引擎读有效规则 + 失效进提示（按规则底稿编码过滤）+ 触发来源 `FORMULA_CONFIG_CHANGED`（选规则按手动口径，记录保留原值）（R2.4 / R2.5）
- [x] 3.4 传播 handler `propagate_push`：按清单反查底稿编码；无规则 / 无年度 / 合并 / 归档跳过；业务不可推记 `not_pushable`（R2.7）
- [x] 3.5 规则列表接口：本项目有效规则（含停用 / 失效）+ 层级、可用操作、本项目版本号、清单原式、失效原因（R2.8）
- [x] 3.6 后端测试 `tests/formula_settings/test_push_settings.py` 13 例（四类拒绝 + 取数上下文、清单内 5 条恒推 0 冻结、叠加 / 失效跳过、写入各层都校验、引擎改写生效 / 停用不推 / 失效不推不回退、新触发来源、传播重推与五类跳过）+ 端点 2 例（层级与操作；旧「30 条」写死改现算）+ 端点鉴权 AST 守卫豁免全局静态端点并反向断言；一次性变异 8/8 打红（去取数校验 / 失效回退预设 / 引擎读静态清单 / 不跳过合并 / 结构落库 / 系统值可停用 / 新触发按原值选规则 / 列表只列 active）。干净 worktree 对比：push + formula_settings + formula_management 全套相对 HEAD 新增失败 0（`test_stats_aggregation` 因目录纳入 push 已改现算）、修好 2 例，其余 37 例 HEAD 同红（R2.2~R2.7）
- [x] 3.7 前端：`formulaPushView.ruleActions` / `ruleStatusText` / `layerTagType` + 触发来源「公式规则变更」；`definitionText` 停用显示与中文算式兜底；推送面板层级列与「本项目适配」列（改写公式 / 本项目停用 / 启用 / 恢复上游）；公式历史模块标签；反向校验面板错误显示；单测 `formulaPushRuleActions.spec.ts` 12 例 + 既有面板 14 例 + 全局设置相关 58 例全绿；单区域 vue-tsc 本次改动 0 错（探针变异 TS2322 证明在检查）（R2.8）

## 4. 校对规则统一目录（R3）

- [x] 4.1 `formula_check_catalog.py` 登记表 12 个来源 + 加载器；`GET /api/formula-catalog/check-rules`（登录即可；清单 / `source` / `q` 三形态，见 design §5.1）（R3.1 / R3.2）
- [x] 4.2 登记守卫 + 测试 `tests/formula_settings/test_formula_check_catalog.py` 7 例：真实数据目录全登记或带理由排除；临时目录双向用例（未登记 / 登记文件不存在 / 排除项失效 / 缺理由）；10 个静态来源计数与规则文件现算一致；只读全局层（排除项目层、停用、已删、自动运算、空公式）；单来源失败隔离；端点未登录拒绝 + 三形态。一次性变异 6/6 打红（漏登记 / 混进项目行 / 停用照列 / 只算勾稽 / 失败拖垮 / 不查失效排除项）（R3.4）
- [x] 4.3 前端 `FormulaCheckCatalog.vue`（来源清单可键盘选、执行位置 / 去哪编辑 / 规则文件、跨来源搜索）+ 全局设置页「校对规则目录」页签（`?tab=checks&source=`）+ 表间审核面板「全平台校对规则目录」入口 + 编辑弹窗「从预置选用」；单测 5 例；单区域 vue-tsc 0 错；ESLint 仅既有的 el-form 规则提示（HEAD 同样有）（R3.3）

## 5. 零挂载组件处置（R4）

- [x] 5.1 问题清单接入表间审核面板：`formulaIssueHint.ts`（同一次 report-cross-check 响应 → 问题项 / 逐条结论 / 提醒 / 计算时间，按树节点裁剪），`useCrossCheckRules` 增 `execRun / execLoading / refreshExec`（刷新只重跑勾稽、不重载用户规则；换项目先清旧结论；失败如实呈现，去掉把 403 / 500 吞成「无结果」的 `validateStatus < 600`）；`FormulaCrossCheckPanel` 挂 `GtFormulaIssuePanel` + 失败重试 + 无结果说明 + 提醒内联；树点击放开表间审核分组节点（原先有子节点就选不中 ⇒「报表 ↔ 附注」「合并 ↔ 报表」的规则集点不到）。删除 `GtFormulaHintPanel` + `useFormulaIssueHint.ts`（无产出方：真库 33 次运行提醒全 0；接口给字符串、组件按对象收）（R4.1 / R4.2）
- [x] 5.2 导入导出下拉按数据分开挂（`mode`）：预设库 Excel 挂「公式预设库」弹窗（导入按 `PRESET_WRITE_ROLES` 门控，与后端 `_CUSTOM_PRESET_WRITE_ROLES` 守卫逐值对齐；非管理员提示「已提交为全局候选」；导入入库后刷新清单）；本项目公式包挂公式管理中心顶栏（`composables/formula/formulaPackage.ts`：导出只收本项目适配、任一类读失败不出文件；导入 `PUT overrides` + 本地修订号，相同不写，适用范围不同 / 已归档整类跳过，逐类报告；类别清单取后端含推送规则）；`FormulaTab` 角色判断改用同一函数（R4.1 / R4.2 / R1.8）
- [x] 5.3 行名对齐弹窗行列表改用 `GtRowNameAlignmentTag`（弹窗内模式：点击不发打开事件、「重新确认」= 激活该行；未知状态照实显示），删除弹窗里的 `stateLabel / stateTagType`（R4.1）
- [x] 5.4 删除 `GtDraftStateBadge`（无数据源，另立 spec）；`NoteFormulaDialog` 改判为**接入**：附注章节公式集的保存只有它在调，公式管理中心里附注行原按「其余 → report」分派、编辑必失败 / 新增不保存 / 保存报「已保存 0 个」⇒ `formulaRowKind` 增 `note` 分派，附注节点「✏️ 编辑本章节公式」（无具体章节时禁用）与行编辑 / 新增 / 保存都交给它，根节点行按该行所属**本项目**章节打开，保存后强制重取本章节（R4.1）
- [x] 5.5 挂载守卫 `components/formula/__tests__/formulaComponentMounts.spec.ts`：每个组件至少被一处生产代码引用（import 路径 / PascalCase / kebab 标签；测试、`components.d.ts`、stories、注释、自身不算），扫描面非空自检 + 判据双向自检（R4.3）
- 证据（2026-10-22）：单测新增 7 个文件、改动 8 个；一次性变异 18/18 打红（吞失败 / 刷新重载规则 / 无关节点显示 / 没跑画清单 / 导出全部层级 / 不带修订号 / 不查适用范围 / 预设导入不门控 / 角色漂移 / 弹窗内重开 / 附注回落报表 / 行编辑走通用框 / 保存全部不交弹窗 / 新增未挂载组件 / 唯一挂载点只剩注释 / 分组又只认叶子 / 附注行不查本项目章节 / 保存后不重取），未变异基线全绿、逐字节恢复；前端相关目录 3774 例中 12 例红，HEAD 干净检出同红（8 个文件：aging ×2 / C24 / 销售标签 / AI 能力 / C 控制测试 / formulaPaths 两例（他会话新面板的 4 个未登记 URL 与 barrel）/ views composables），本次新增失败 0；单区域 vue-tsc 本次文件 0 错（报出的 18 处均在 HEAD 同样存在）；ESLint 0 错误。浏览器（无头 Chromium）：【测试】甲表间审核「报表 ↔ 附注」问题清单 2 项、单条节点 1 项、「报表 ↔ 底稿」不显示、打开期间勾稽只执行 1 次；公式包【测试】甲建 1 条适配 → 导出 1 条 → 导入【测试】乙「已写入 1 条」→ 再导入「已写入 0 条；1 条与本项目相同未改」→ 两项目恢复全局、对账回到导入前；预设库弹窗菜单 3 项、管理员可导入、模板下载成功；安徽附注（只读）根节点按钮禁用、模板章节号「五、1」本项目没有时提示、「八、1 货币资金」打开附注公式弹窗。行名对齐弹窗未做浏览器实测（需底稿刷新出待确认行，真实项目底稿页会自动同步写库），由真挂载单测覆盖

## 6. 底稿可编辑公式补齐函数（R6）

- [x] 6.1 预载层 `_load_aux`（按写法逐个取数，L1 同键 `aux_ref_key`，旧维度键兜底）/ `_load_report_rows`（没给 row_cache 时读本年度本期金额）/ 取数缺口改为 `preload(gaps=…)` 出参（不加 `ctx.missing`，见 design §7.1）（R6.5）
- [x] 6.2 求值器：不支持函数不求值 → 跨 sheet → PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 严格按值代入（`substitute_value_refs`，先于 TB）→ WP / SUM_TB / TB（允许空白）→ 残留写法报错 → ADJ 经 preload（底稿口径）→ L1；取不到数写进错误清单（R6.1~R6.3）
- [x] 6.3 函数矩阵 wp_evaluator 十函数全支持 + golden + 前端矩阵同步、对拍绿；保存 422 逐项原因 + 列出支持函数；F2 拒绝清单独立；地址库三处缺陷（ROW 期间名 / 附注域 / AUX 类型与前缀）；附注结构编辑器公式栏按 note_executor 门控并传年度 / 模板、取数弹窗用登记写法、地址库未加载先加载、回退改真实附注目录接口（R6.4）
- [x] 6.4 测试：求值器 16 例（13 个用例函数：7 个函数 + 各类缺口 + ADJ 底稿 / 报表两口径 + 不支持的 4 种写法不取数 + 写法残留 + 预载层两例）、地址库 7 例、保存端点 6 例（真发请求）、前端 5 例（取数写法 / 地址库先加载 / 回退接口 / 每个公式栏挂载点声明执行器）；d-cycle 契约测试按新契约更新（R6.1~R6.3）
- 证据（2026-10-22，提交 ebd13ffe6）：干净检出基线 e018fc336 与本提交同一测试集失败集合逐条相同（92 = 92，HEAD 预存），通过 1476 → 1506；一次性变异后端 23 / 前端 8 全部打红，未变异基线全绿、逐字节恢复；真库只读核对（安徽 / 【测试】甲，事务回滚）各函数取数与缺数报因、单区域 vue-tsc（新增 0）、浏览器只读实测（附注结构编辑器门控与取数弹窗）见 design §7.2；底稿可编辑公式保存 / 求值的浏览器实测并入 R5

## 7. 真库全链路走查（R5）

- [x] 7.1 选定【测试】甲（上市单体，审计年度 2025，试算表 1001 / 1002 / 1012）、【测试】乙（同构）；推送链路要底稿 ⇒ 甲经平台「按编码生成」建 E1 —— 该端点对任何调用都 500，走查中修复（7.4 ①）。偏离 design §8 第 1 步：tb_detail / push 的全局层适用范围是「*」，全局发布会触达真实项目 ⇒ 改用报表公式（上市单体只有甲 / 乙）（R5.3）
- [x] 7.2 六步接口 + 浏览器（无头 Chromium）双证（R5.1 / R5.2）：
  ① 甲本项目改 BS-002（接口）→ 全局设置页改 BS-002 发布 v2：预览「乙直接生效 1、甲冲突 1」，提示「1 个项目的有效公式已更新，1 处交项目确认」；接口甲待确认 1（冲突）、乙 = 新全局
  ② 进入甲：待确认弹窗自动弹出、三方对比；选「保留本项目」→ 弹窗关、角标消失；接口待确认 0、基线版本 2
  ③ 甲「保存为模板」（1 条）→ 乙订阅（预览直接生效 1）→ 有效层「模板」；模板抽屉改 BS-002 发布 v2（预览「自动跟随 1」）→ 乙跟到 v2、报表 BS-002 重算、订阅项目页 v2
  ④ push 域（甲 E1）：推送页改写 `E1.tb_amount.ending`（系统值：可改写不可停用）→ 层级「本项目」、触发「公式规则变更」重推，审定表期末 350 → 300；停用 `E1.note.main_rows`（可编辑值）→「本项目 · 已停用」，下一次运行明细里不再有该规则（29 → 28 条）。甲无附注，该规则原本只「跳过：附注尚未生成」，「停用后不再写入值」在甲上无值可观察，如实登记
  ⑤ 停用系统值规则 `E1.tb_amount.opening`（界面不给按钮，接口直发）→ 400「系统值规则不能停用 —— 它写的目标是推送独占键…」；改写成越界科目 1122 → 400「科目 1122 不在本底稿推送取数的科目内」
  ⑥ 校对规则目录：接口 12 来源 1650 条，逐来源与规则文件 / 真库独立现算一致（10 个文件来源 + 全局层 0 + 报表审核公式 0）；界面「共 12 个来源 · 1650 条规则」
  R6 并入：甲 E1 保存 `ROW('BS-002')` = 300、TB 两科目 = 300；缺数三条报原因不写 0（上期金额为空 / 上年（2024）试算表无数据 / 本年度附注没有章节 五、1）；PREV 三参、LEDGER 422 逐项原因。从 E1 底稿页打开公式管理原样再存 B6 两次：提示写明原因、第二次不 409
- [x] 7.3 清理对账（全走平台路径：乙退订回到全局 → 删除模板 → 全局 BS-002 发布回原公式 v3 → 甲待确认选保留后恢复全局 → 推送两条规则「恢复上游 / 启用」→ 删底稿公式 5 条）：甲 / 乙 258 个报表公式位全部回到全局、待确认 0、无订阅、本项目报表行 0、BS-002 = 350；E1 期末回到 350、推送规则全回系统预设。保留项：发布记录 3、已处理待确认 2、已删模板 1 + 版本 2 + 模板层定义 1（已删）、已退订订阅 1、审计日志 +47（哈希链）、甲推送运行 9 / 状态 25、运行时外发 +12（公式管理中心打开时的表间审核执行事件）、上市单体 BS-002 版本号 1 → 3（内容同 v1）；甲 E1 底稿（索引 / 底稿各 1 行 + `backend/storage/projects/4c77…/workpapers/E/E1.xlsx` 空白工作簿）保留 —— 平台没有删除底稿的入口（design §9）（R5.3）
- [x] 7.4 走查发现并修复（design §8.2）：①按编码生成底稿恒 500（函数体 import 全仓不存在的 `populate_parsed_data`）→ 与准则转换共用 `ensure_parsed_data_placeholder`，懒导入守卫基线删该条，端点守卫 4 例真发请求；②底稿公式求值有错时网格照写 0、回「0」（R6.3 禁止）→ 格子留空、只回原因；公式管理中心 / 自定义底稿编辑器 / 公式状态面板提示写明原因（原：「公式已保存」或只报条数）；③公式管理中心保存后从回执顶层读版本（实际在 `saved` 下）⇒ 同一行第二次保存必 409；自定义底稿编辑器不带 `expected_version` ⇒ 改已有公式恒 428；④「保留本项目」也提示「会按新定义重算」→ 接口回 `recalc_domains`；⑤模板发布预览版本列整列「— → —」→ 无逐位版本不显示；⑥订阅弹窗先等域清单再加载 ⇒ 露出「没有可订阅的模板」→ 并行；⑦树上「E1 货币资金」工作簿节点点了只高亮、推送页误报「本底稿尚未接入」→ 可选中整本、空状态区分「未选底稿」；⑧推送面板 / 表间审核历史时间显示 ISO 原串 → 格式化；⑨`getDisclosureNoteTree` 丢弃第三参（AI 采纳目标的静默请求失效，HEAD 上 vue-tsc TS2554）、公式管理中心 / 编辑公式弹窗对无附注项目每次弹「附注数据不存在」且跳过模板目录 → 透传配置、404 静默改用模板目录、其他错误提示
- 证据（2026-10-22）：后端新增 / 改测 `test_generate_from_codes_endpoint.py` 4、`test_wp_formula_save_gate.py` +2（真发请求：缺数留空清旧值 / 成功照写）、`test_endpoints.py` +1（保留不发事件、`recalc_domains` 空）；前端 `wpFormulaSaveNotice.spec.ts` 9（含调用方守卫：每处保存经提示函数、带版本号、不读回执顶层版本）、`noteTreeSilentFallback.spec.ts` 2、`auditPlatformApiNoteTree.spec.ts` 2、待确认 / 发布预览 / 订阅弹窗 / 树节点各 +1。验证 worktree 一次性变异 21/21 打红（生成 4 + 后端 3 + 前端 14；两个存活项已处理：一个是等价变异已换成无条件回值、一个是多余的加载态赋值已删），未变异基线全绿、逐字节恢复；主工作树相关后端 7 个文件 61 例全绿；验证 worktree 同一测试集（formula_settings / formula_management / d-cycle / f2 / 推送引擎与端点 / 鉴权两维 / 懒导入 / 生成管线 / 底稿公式 / 地址库；前端 formula / composables/formula / 自定义底稿 / services 等）HEAD 70e718922 对本轮：后端 98 红 / 1512 绿 → 98 红 / 1519 绿，前端 70 个文件 8 红 / 842 绿 → 73 个文件 8 红 / 859 绿，失败集合逐条相同；单区域 vue-tsc 两组本次新增 0（HEAD 上 `chatTargetOptions.ts` 的 TS2554 因 ⑨ 消失）。d-cycle Tier A 三个测试文件 28 例 HEAD 同红（假会话缺 `get`、`list_formulas` 形参改名，基线 92 内），其中「网格缺数」用例已按新口径改写 —— 但该文件全部用例在进入保存逻辑之前就因假会话缺 `get`（`deps.py:189`）报错，改写后的用例同样执行不到断言；新口径的真实覆盖是 `test_wp_formula_save_gate.py`（真发请求）

## 8. 回归与交付（R7）

- [x] 8.1 全量回归：`formula_settings` / `formula_push` / 鉴权基线 / 矩阵对拍 / 前端 formula 目录；预存失败在干净检出上复现并登记（R7.2）
  证据（2026-10-23）：验证 worktree 干净检出 HEAD 3256fc491，与「HEAD + 本轮要提交的文件」（树 fd26263d5）跑同一测试集。后端 32 个路径 + 43 个 `test_formula_push_*.py`（formula_settings / formula_management 含函数矩阵对拍 / 推送全套含真库 canary / 鉴权两维 / 懒导入 / 底稿公式 / d-cycle / f2 / 分支命名守卫；基线少本轮新增的 1 个文件）：137 红 / 2998 绿 / 14 跳过 → 137 红 / 3005 绿 / 14 跳过，失败集合逐条相同（唯一差异是改名的 d-cycle 用例，两边都红在假会话）；前端（formula / composables / services / views 测试 / 自定义底稿 / 模板库 / AI 采纳等）：286 个文件 20 红 / 4039 绿 → 289 个文件 20 红 / 4056 绿，失败清单逐条相同。预存失败在本 spec 开工点 d28f1de8a（主线，只有三件套）复现：后端 137 例里 135 例在该点同红、改名用例的原名同红；余下 `test_formula_push_k2_canary_pg` 单独跑通过，排在其他推送测试之后跑则 d28f1de8a 与 HEAD 都红（`proactor_events.py`：`'NoneType' object has no attribute 'send'`，连接池里留着已关闭事件循环的连接，测试间污染）；前端 9 个文件 20 例在该点同红。本 spec 新增失败 0；分类登记 design §9
- [x] 8.2 干净 worktree 验证要提交的树；提交并推送（R7.3）—— 2026-10-22 用户裁定：不新建分支、不建 PR，推送到 `spec/disclosure-note-doc-upload-and-batch-fill`；`spec/formula-management-deep-optimization` 已快进并入该分支后删除（本地 + 远端，无关联 PR）。pre-push 的分支命名守卫不认 `_archive/NN-<name>` 归档形态 ⇒ 已修（c555dd831）
  证据（2026-10-23）：R1~R6 各轮已分别提交并推送（74c7c0a8f / 1e1d73f64 / cb320d128 / d90cef69e / 1d8600593 / ebd13ffe6 / 645a79b8f），其合计效果由 8.1 在干净检出上对开工点复核；R5 与交付这一提交：代码与 8.1 验证的树相同，提交前在验证 worktree 暂存同一组文件跑行数门禁 / 分支命名 / 暂存树自洽，提交的树与该暂存树相同（write-tree 比对），提交说明「formula-governance-coverage-closure R5」；行数门禁抓到 `wp_template.py` 是 HEAD 已 870 行且未登记的历史大文件（本轮 +2），按先例登记白名单 872 并写明拆分方向
- [x] 8.3 INDEX.md 登记 + memory 更新（R7.3）—— INDEX 本 spec 一行改为 36/36 与各轮提交；memory 增本 spec 一节（教训 6 条 + 范围外登记），同时把已全部修完的「待修 bug」一节压成两行，全文 ≤ 300 行
