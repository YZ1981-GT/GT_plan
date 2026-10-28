# 任务：审计年度兜底取今年 / 写死年度（audit-year-calendar-fallback-ratchet）

> 首版草稿（随 `25a506a57` 入库，只有前端、口径「不减 1 且行内含 year」）已按实施结果改写，口径变化见 requirements 头注。
> 任务 1 随 `formula-fetch-followup-defect-closure` 任务 8.1 交付；任务 2 起另行排期，开工前先确认 R3.2（单一来源最终兜底：A 去年 / B 提示）。

## 0. 优先：程序表执行人编辑刷新后丢失（R0，2026-10-25 插入）

- [x] 0.1 后端 render-config `a-program-console` 两个分支回传 `override_scope`；端点级测试（真库回滚事务：执行人按回传 scope 与项目年度写覆盖 → 再取 render-config 能看到）
- [x] 0.2 前端年度单一来源：`resolveAuditYearOrNull` + `useProjectAuditYear` / `fetchProjectAuditYear` / `requireProjectAuditYear`；vitest
- [x] 0.3 写入方改造：程序表控制台、A1 / A2 / A3、G8~G12 回填（`writeProgramStepOverrides`）；配对读请求；vitest + 变异
- [x] 0.4 下调年度棘轮基线与冻结上限；单区域 vue-tsc、ESLint
  - 证据：前端基线 280 文件 / 326 总数 = `FROZEN_TOTAL_CAP`，后端 72 文件 / 130 总数 = `FROZEN_TOTAL_CAP`，两端棘轮测试均全绿（前端 4 passed、后端 6 passed）；
    Python 同口径脚本复核两端基线与现算逐文件一致；
    单区域 vue-tsc（`tsconfig._pcfc.json` + 精简 `tsconfig._t04.json`）：目标文件本身 0 error，18 处 error 全在未修改的传递依赖里（g6/g8/g10/g11/g12 CrossHelpers、useWorkpaperScaffold、GtA112 等），
    注入 `number = string` 报 TS2322 确认非空转；ESLint 0 error（60 warning 全为 `gt-audit/*` 预存领域警告）
- [x] 0.5 存量位置修复工具（dry-run 报告；真实项目 `--apply` 待用户确认）
  - 证据：`backend/scripts/fix/fix_program_override_placement.py`（核心 `fix_placement` 只执行不提交，可 `--project` 限定；原 `--apply` 写不存在的
    `audit_logs` 表、UPDATE 后整批失败，改为平台操作日志 `logs`）；`test_fix_program_override_placement_pg.py` 2 例真 PG 回滚事务
    （表名取表码、年度改项目审计年度、无年度的项目不改年度、目标已有值或两行同一目标都算冲突且预演与执行结论一致、只动指定项目、留痕），
    变异 MFX1~MFX7 全部打红。2026-10-25 真库 dry-run：10 行错位、3 行冲突、7 行可移动（6 行是空的执行说明，1 行是重药安徽 A1 第 1 行状态「已完成」）
- [x] 0.6 浏览器实测：执行人改状态 / 执行说明后刷新仍在；未设置审计年度的项目提示且不发请求
  - 证据：执行人 ptgd_auditor 在【测试】项目 H1A 第 2 行改状态 / 执行说明，刷新后仍在；库里是 2025 年度、`procedure_table:H1A`。
    无审计年度的 `proj_*` 项目打开底稿整页显示「未设置审计年度」，网络里没有字段覆盖写请求；组件级「提示且不写」由 vitest 覆盖。
    A3 合并流程中控台补了漏掉的 import（原先挂载即 ReferenceError），`GtA3ConsolidationConsole.mount.spec.ts` + 变异 MA3-1~MA3-4

## 1. 守卫：只许减少（R1）

- [x] 1.1 前端 vitest 棘轮 `src/__tests__/auditYearCalendarFallbackRatchet.spec.ts` + 基线 `auditYearCalendarFallbackBaseline.json`
  - 证据：`bf7685b1d` 干净检出扫 5332 个源码文件，288 个文件 340 处；同口径脚本生成的基线与 vitest 现算逐文件一致（4 passed）；
    单区域 vue-tsc 0 错（注入 `number = 'x'` 报 TS2322，非空转）、ESLint 通过。
    主工作区（含并发会话未提交改动）现算只差一组挪动：`g10DisclosureSyncPayload.ts` 2 处挪到 `g10NoteSectionMap.ts`，守卫按设计报两条
    （该会话提交时需把基线条目一起挪过去）
- [x] 1.2 后端 pytest 棘轮 `tests/test_audit_year_calendar_fallback_ratchet.py`（AST，基线在文件内）
  - 证据：扫 `backend/app` 2771 个文件，72 个文件 130 处（今天的年份 34、写死年度 96）；干净检出与主工作区均 6 passed
- [x] 1.3 变异
  - 证据：前端 MY1~MY9（基线外新增 / 修掉不改基线 / 整行注释与行尾注释口径失效 / 扫描根写错 / 漏认 `(new Date()).getFullYear()` /
    基线净增 / 测试文件也计入 / `__tests__` 目录也扫）、后端 MB1~MB7（新增写死默认值 / 修掉不改基线 / 全大写常量也计 / 只认 `now()` /
    不认 `Query(2025)` / 扫描根写错 / `or` 不看前项）全部打红在预期断言上，跑完逐字节恢复

## 2. 逐处判定（R2）

- [x] 2.1 前端 340 处、后端 130 处逐处判定写请求 / 读请求 / 日历用途 / 单一来源兜底，产出 `evidence/classification.md`（按 import 闭包追到请求发出点）
- [x] 2.2 日历用途进豁免表（前后端各一张，理由 + 可证伪：文件仍命中口径），对应条目从基线移出
- [x] 2.3 盲区补查：先存 `new Date()` / `datetime.now()` 再取年份的写法，按文件人工过一遍并登记

## 3. 前端写请求（R3.1、R3.2）

- [x] 3.1 `resolveAuditYearOrNull` + `resolveEffectiveAuditYear` / `useAuditContext` / `useProjectSelector` 改为取不到返回 null（调用方同步处理）
- [x] 3.2 写请求的年度缺失时不发请求、提示「未设置审计年度」；下调基线；vitest + 单区域 vue-tsc
- [x] 3.3 浏览器实测（【测试】项目，含未填审计年度与审计期末的项目）

## 4. 前端读请求 / 展示（R3.3）

- [x] 4.1 按组件族分批（底稿 D~N 循环各一批，其余页面一批）改为空态 + 提示，或不传年度由后端取；每批下调基线、跑该族 vitest
- [x] 4.2 浏览器实测（同 3.3）

## 5. 后端写死年度（R4.1、R4.2）

- [x] 5.1 `routers/wp_prefill_preview.py` 两处改单一来源，取不到 ⇒ 422；端点级测试
- [x] 5.2 `year: int = 2025` / `Query(2025)` 等参数默认值逐端点改（改前现查前端调用方是否都传年度）；`x or 2025` / `.get("year", 2025)` 同改
- [x] 5.3 下调基线；触及的既有测试按新语义改写

## 6. 后端今天的年份（R4.3）

- [x] 6.1 兜底类改单一来源；日历类按 2.2 进豁免表
- [x] 6.2 下调基线；端点级测试

## 7. 收尾

- [x] 7.1 基线清零或只剩豁免；变异复跑；回归（改动涉及的测试目录对比改动前）
- [x] 7.2 INDEX / memory 更新

## 8. 推送前复核补修（2026-10-26，与程序链会话合成单一提交）

> 标 24/24 时的交付有缺口：43 个文件（17 前端 + 26 后端）只在工作区、没进暂存，干净检出时两端棘轮都红；全量 vue-tsc、全量回归与浏览器复测又抓到一批运行时问题。本节如实补登，前面 24 项的勾选不回改。

- [x] 8.1 补暂存 43 个文件，候选提交干净检出复跑两端棘轮
  - 证据：临时分离头 worktree（候选提交）里后端 `test_audit_year_calendar_fallback_ratchet.py`、前端 `auditYearCalendarFallbackRatchet.spec.ts` 全绿；`check_staged_tree_self_consistency.py` 两道门 exit 0
- [x] 8.2 全量 vue-tsc（40GB 堆，约 5 分钟）候选树对比 HEAD，修运行时错；全量 vitest 对比 HEAD，修新增失败
  - 证据：按（文件, 错误码, 信息）计数比较，先抹平信息里的检出绝对路径（否则 TS7016 / `import()` 类型全成假新增）；修约 35 处：找不到名字、不存在的 `props.year`、声明前使用、缺返回值、字符串年度当数字（N2-11 抽凭）。全量 vitest 新增失败 20 个文件逐个修：`GtAProgramLinkedChips` 恢复被删的 `chipCompletionKey` 属性（运行时 TypeError）、`ImpairmentSummaryDialog` 缺年度不发请求并跟随 `props.year`、`WorkpaperWordEditor` 年度改为宿主 > 路由 > 项目信息且写前提示、`buildFinanceLeaseAmortization` 没有起始年不再返回空表（日期留空）、`recalcRentalRow` 只跳过月数推算（原先整行公式列都不再重算）、`GtCNoteTable` 自动取数用路由年度或项目审计年度、`GtC24LedgerImport` 用例的 store 桩改成与 pinia 一样的 getter。余下 443 条全是 `number | null` 与 `number` 不符，见 8.5
- [x] 8.3 后端：公式执行与红用例按新语义收口
  - 证据：`excel_html` 公式执行原按 `year=None` 查试算表写 0，改取项目审计年度；`resolve_project_audit_year_for_request` 只吞 UUID 解析错误（查库失败照常抛，避免把连接故障说成「未设置审计年度」）；签认 / 导出缺年度 422 且不写记录、签字状态 PBT 夹具、附注 AI 三端点（会计政策 / 变动分析 / 完整性检查）用例按前端带年度，另加缺年度用例（成员 422、业务 0 次，外人照旧 403，项目填 2024 后取数用 2024）；「仅登录不校项目」基线 193→191（程序行任务物化两端点补委派人鉴权，属程序链 spec）。候选提交真检出跑 381 个后端文件（不跑提交真库的 procedure_delegation 用例），与 HEAD 逐条比对：候选独有 0（另 2 条只在整批顺序下 ERROR、单独跑与 HEAD 相同）；HEAD 因 `'[]'::jsonb` 建表失败而 ERROR、掩盖了用例体的 32 条，在 HEAD + 同一处模型修正上逐条同红、原因相同，属既有失败
  - 🔴 比对脚本自身的坑：`-rfE` 摘要行的参数化 id 含转义中文与空格，按 `\S+` 取节点 id 整行匹配失败、静默丢弃 ⇒ 第一轮少算 6 条候选独有失败；改为按方括号配平取 id
- [x] 8.4 浏览器复测（chrome-devtools 隔离上下文；真实项目只读、不写数据）
  - 证据：无审计年度的项目整页「未设置审计年度」+ 返回、不发写请求；重药安徽 H1-2 取数正常，H1-18 / 宜宾 N2-11 请求带 `year=2025`（HEAD 为 2026），A16 字段覆盖读 `year=2025`，J1A 关联底稿 chip 正常；合并附注下推模板未绑定明细模板时只提示、不发写请求
  - 🔴 复测抓到本 spec 引入的回归：底稿编辑页取项目信息与同页其他组件同址 GET，被 GET 去重取消后落进 catch，只给场景默认值、年度留空 ⇒ 后端稍慢就整页「未设置审计年度」（重药安徽已填 2025，打开 J1A 复现）；4xx / 5xx 因 `validateStatus: s < 600` 也当成功解析，同样落成「未设置」。已抽出 `views/workpaper-editor/useWorkpaperProjectMeta.ts`（`_dedupe: false`、不吞非 2xx、失败与重试单独显示、只认最后一次请求），`AuditYearMissingResult` 加读取失败态；单测 9 + 4 例，变异 5 条全部打红；浏览器注入请求失败后显示「读取项目信息失败」，点重试后底稿正常打开；`SHELL_RATCHET` 1472→1456
- [x] 8.5 类型债：`number | null` 与 `number` 不符约 443 条（运行时已按 null 分支处理，只是声明没跟上）；按组件族分批收紧，不在本次推送内
  - 由 `post-push-residual-defect-closure` R2（其 tasks 6.1~6.4）收口：候选树（HEAD `709b21275` + 该 spec）全量 vue-tsc 相对 HEAD 减少 447 条，年度相关新增清零。勘误：「运行时已按 null 分支处理」不成立 —— 集中调整同步年度为空仍发请求、抽凭 / 截止测试默认截止日拼成 `null-12-31`、挂凭计数与导入照发请求、七个底稿把 ComputedRef 对象当年度传。遗留：store 年度初值去年致无年度项目仍按 2025 取数，见该 spec tasks 6.5
- 范围外发现（登记，不在本 spec 修）：前端 37 处 `GET /api/projects/{id}/trial-balance` 不带 `year`（端点 `year` 必填，且不认 `account_prefix`）⇒ 恒 422、被 catch 吞成「待取数」（H1 / H3 / H4 / H5 / H10 / I1~I6 / K2~K13 / N4 / G7 / H2 / K5 / M2 的试算表勾稽；浏览器实测 H3-14 6051 勾稽即此）；HEAD 同数，与日历兜底无关，宜另立 spec
