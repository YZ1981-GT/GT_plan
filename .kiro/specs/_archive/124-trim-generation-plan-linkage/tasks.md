# 任务：程序裁剪 → 生成底稿联动（生成计划）

需求 requirements.md，设计 design.md。每个任务完成须有代码 + 测试通过的证据；外部依赖未到的如实标 `[ ]*`。

- [x] 1. 后端：母码跟随下级程序行（R4，design §2.1）
  - [x] 1.1 `TrimmedScope` 建下级索引、`_decide` 三种来源、`follows_children`、`deciders`；`SUBSTANTIVE_CYCLES`
    - 粗裁应用联动 `ScopeCoverage.covered` 与清理工具改按 `deciders` 判「某条程序行管哪些底稿」（只恢复一条下级行时，按当时回报的决定者比较会漏掉母码）
  - [x] 1.2 单测 `test_procedure_scope_children_rule.py`（13）+ `test_procedure_trim_recycle_children.py`（3）；契约两组用例 + README；`tests/contracts`、既有粗裁 / 回收站联动 / 生成入口测试 96 + 17 passed，PG（`DATABASE_URL` 指本地库）scope / 回收站 / 清理 4 passed
  - [x] 1.3 真库只读探针：有程序行的项目里跟随下级的母码 —— 安徽 D2 / D4 / E1 / F2，和平药房 D2 / D4 / E1，其余 D2 / D4；判定变化 0（目前没有项目把某科目的下级程序行全部裁掉），无需移动底稿
- [x] 2. 后端：程序目录与补齐（R5，design §2.2）
  - [x] 2.1 新模块 `procedure_catalog.py`：目录来源（选用模板库查询改在保存点里，原裸 `try/except` 在 PG 上会让外层事务进入 aborted）、循环模板编码、业务分类限制、`supplement_items` / `supplement_entries`、`ensure_supplement_rows`（PG 咨询锁）；`business_category_service.template_mappings()`
  - [x] 2.2 `init_from_templates` 改为锁内「建行 / 补齐」（建行循环原样保留，源码守卫 `test_wave1_baseline` 照过）；`get_procedures` 每行加 `origin` / `category_hint`
  - [x] 2.3 `test_procedure_catalog_supplement.py` 19 passed；现算补齐 46 个（B 26 / A 17 / S 3，D~N 0），补齐后再算 0
    - 设计时补：`business_category` 也被拿来存业务类型（真库有 `IPO`），首字母不是 A / B / C 的按未填写、用 C 类（原弹窗当成「I 类」），提示写「项目未填写 A / B / C 业务分类，按 C 类判断」
- [x] 3. 后端：生成计划与粗裁状态（R1，design §2.4~2.6）
  - [x] 3.1 新模块 `procedure_generation_plan.py`：`load_cycle_confirmations`（读不到 503，不当成「没保存过」）、`build_generation_plan`、`build_scope_confirmations`
  - [x] 3.2 `routers/procedures.py` 两个 GET（readonly；404 / 503）
  - [x] 3.3 契约 `generation-plan-view.schema.json` + README（文件表、生成一节、接口数 8 → 10）+ `OPERATIONS` 登记（插在生成两接口之后，`OPERATIONS[-1]` 仍是覆盖值批量）并重新导出 OpenAPI 子集（只增 215 行）+ `PUBLISHED`
  - [x] 3.4 `test_procedure_generation_plan.py` 6 passed（含端点 401 / 403 / 200 / 404）；`tests/contracts` 73 passed；PG 一致性 `test_procedure_generation_plan_pg.py` 1 passed（全部有程序行的真实项目，计划与 `plan_generation` 逐码一致）
- [x] 4. 前端：生成计划弹窗（R2，design §3.1~3.3）
  - [x] 4.1 `apiPaths`（`procedures.generationPlan` / `scopeConfirmations`、`templates.sets.seed` / `generateFromSet`）、`generationPlanApi.ts`（生成请求带 `_silent`：错误由弹窗提示一次，也不让拦截器把 5xx 的生成请求自动重发两次）
  - [x] 4.2 `generationPlanModel.ts` + 单测 6 个（日期经 `fmtDate(parseServerTime())`，不截前 10 位）
  - [x] 4.3 `GenerationPlanDialog.vue` + 挂载测试 5 个（循环级勾选用普通列表、不放进 el-table：表格内核会接管单元格里的勾选框）；后端补 apiPaths ↔ 路由逐字一致
- [x] 5. 前端：底稿列表页（R2.7 / R6，design §3.4）
  - [x] 5.1 替换旧两步弹窗、加「✂️ 程序裁剪」入口、改提示文案、删 `WorkpaperTrimDialog.vue` 及其测试、更新三个列表页用例的桩
    - 顺带删 `useWorkpaperGenerate.ts`（旧两步流程的组合式函数，全仓零调用方、只被自己的单测引用）；后端跨语言契约 `test_generate_workpapers_selected_templates.py` 的调用点清单改为 `generationPlanApi.ts`，扫描口径加认 apiPaths 访问器写法 + 反向自检（11 passed）
- [x] 6. 前端：裁剪页联动（R3，design §3.5）
  - [x] 6.1 `components/workpaper/composables/useTrimGenerationLink.ts` + 单测 5 个（store 在计算时才取：裁剪页原先不依赖 Pinia，既有挂载用例没装 Pinia）
  - [x] 6.2 `ProcedureTrimming.vue` 接入（生成按钮与弹窗、补齐调用、`?cycle=`、保存后三选一、业务分类建议与批量、粗裁状态、补充标签、未生成提示；有未保存修改时不让生成），4089 → 4132 行（上限 4212）；模板里调用的名字逐个 `const X =` 声明（判据 D 不认解构）；裁剪页 16 个相关用例文件全过
- [x] 7. 验证
  - [x] 7.1 后端相关测试文件全跑、与 HEAD 失败集合逐条对照；契约与 OpenAPI `--check`
  - [x] 7.2 前端相关 vitest；单区域 vue-tsc（含注入错误的变异证明）
  - [x] 7.3 磁盘变异 19 条（后端 13 + 前端 6）全部红在预期断言上
  - [x] 7.4 浏览器实测：真实项目计划只读核对；【测试】项目走完补齐 → 保存粗裁 → 生成 → 回执 → 裁剪页刷新；用完走平台删除并对账
- [x] 8. 收尾：验收记录、INDEX、memory、清理探针与测试数据

## 验收记录

### 回归、类型与变异

- 后端 SQLite 相关选集：HEAD `396 passed / 7 failed`，候选树 `400 passed / 7 failed`；7 个失败节点逐条相同，本 spec 新增失败 0。失败是既有 `test_template_engine` 3 条、`test_procedure_delegation_characterization` 1 条、identity-only 棘轮 1 条、lazy import 2 条。
- 后端 PG 只读 / 回滚选集：HEAD 与候选树均 `6 passed`；本 spec 新测试另跑 SQLite `39 passed` + PG `1 passed`。`test_committed_code_imports_only_committed_modules.py` `10 passed`。
- OpenAPI `--check`：10 个接口 / 10 个组件，与应用一致。
- 前端 32 个相关文件最终 `659 passed / 4 failed`；4 条都在 HEAD 复现（`WorkpaperWorkbenchView` 行数 1769 > 1210、`WorkpaperListShell` admin / partner / manager 的 matrix 三条），本 spec 新增失败 0。此前判据 D 的新增失败已按根因修好。
- 单区域 vue-tsc：候选树与 HEAD 都是 6 条既有诊断、分布在 5 个文件，本 spec 新增 0；在验证 worktree 给 `generationPlanModel.ts` 注入 `number = string` 后准确新增 `TS2322`，逐字节恢复。
- 磁盘变异：后端 13 / 13、前端 6 / 6 全部红在预期用例；首轮 M5 存活经 3,000 组对拍证实是等价判断，删冗余代码后拆成两个真实语义变异并全部打红（详见 design §6.2）。
- 收尾后自查补修（design §6.5）：补齐会让已裁 A1 下的 A1-12 / A1-16 恢复生成，改为沿用原决定行状态与理由；新增 4 个用例（本 spec 新测试 SQLite 39 → 43 passed），另 4 条针对性变异全部打红；复跑 contracts / wave1 / 保留范围 / 生成入口 111 passed、PG 2 passed。变异合计 23 / 23。

### 浏览器与真实数据

- 真实项目「重庆医药集团医疗器械有限公司_2025」计划弹窗与只读接口一致：标准年审 1025 个编码，994 将生成、31 按业务分类默认不生成；D 循环未保存 17 / 0，其余循环状态与接口逐项一致。点击深链后发生一次不该有的初始化写入，已按精确批次恢复，恢复后 A 再次为 `not_initialized / 0`，计划数字与前值完全相同；过程失误与恢复证据见 design §6.4。
- 新建【测试】项目 `b3a18291-200e-4f2c-aa12-744bdff6087e`：`?cycle=A&from=generate` 正确选中 A；初始化得到 76 条程序行，其中补充行有明确「补充」标签；按 C 类建议裁剪 19 条并自动填理由，保存后显示 `粗裁已保存（admin 2026/10/28）`。
- 保存后的三选一进入生成弹窗，只选 A 循环；计划显示程序 `57 / 19`、将生成 69、已裁剪 31。生成请求只发送这 69 个 `to_create` 编码，6.152 秒完成，`created=69`、`failures=[]`；刷新后页面显示可进入程序裁剪，再开弹窗显示 A 为将生成 0 / 已生成 69 / 已裁剪 31。脏修改时点生成按钮不打开弹窗、不发计划请求，刷新后未保存改动消失。
- 回执同时如实提示 4 个编码建了空白底稿、54 份未填表头（既有生成质量欠账，见 design §6.5）。测试项目信息、A 循环 57 执行 / 19 裁剪、69 个 `wp_index` 均已对账；随后调用平台 `DELETE /api/projects/{id}` 软删除，项目 `is_deleted=true`、同企业代码 active=0，验收时间窗内其他项目新增底稿 0。

### 未提交

本 spec 的代码、测试与文档尚未提交 / 推送；共享工作区还有多个并发会话的改动，提交时必须按本 spec 文件与共享文件改动块分拣，不得整树提交。

### 2026-10-29 最终全链复盘验收（追加记录）

- 最终复盘新增修复：项目级事务咨询锁、取锁后现读 scope、preview 状态摘要 CAS、项目目录 503 fail-closed、归档 / 删除项目门与 RLS、重叠区间决定者、跨循环标准码、自定义程序锁、软删模板集；前端 open / project epoch、生成中不可退出、单写端点、动态权限、确认状态与循环加载竞态、年度单源、a11y / 响应式宽度 / 单展开。详见 design §6.7。
- 后端主回归选集最终 `258 passed`；其中本 spec 聚焦集 `64 passed`。守卫 HEAD / 候选均 `100 passed / 2 failed`，两条同为预存 lazy-import 欠账；characterization 加模板目录夹具后与 HEAD 同为 `3 passed / 1 failed`，预存失败是 render-config 可见性夹具。候选树新增失败 0。
- PG 回滚测试：scope / advisory lock `2 passed`；此前被并发迁移缺列阻断的程序授权矩阵在 `projects.current_audit_phase` 落库后复跑 `29 passed`。OpenAPI `--check` 为 10 个接口 / 10 个组件，与应用一致；Python `compileall` 通过。
- 前端 HEAD `614 passed / 4 failed`，候选 `649 passed / 4 failed`，新增失败 0；同 4 条预存失败为 Workbench 行数门和 WorkpaperListShell 的 admin / partner / manager matrix。最终聚焦复跑 `32 passed`。
- 新增文件单区域 vue-tsc 为 0 error；含共用大页面的选集保留 5 条 HEAD 同有诊断，本 spec 新增 0。注入 `generationPlanModel.ts` 的 `number = string` 后准确得到 TS2322，目标文件 SHA-256 恢复一致。ESLint `0 errors / 27 warnings`，均为既有状态字面量、金额与表单规则 warning。
- 原验收变异保持 `23 / 23`；最终复盘扩展套件为后端 `18 / 18`、前端 `16 / 16`，均红在指定断言。F14 首轮存活的根因是空初态夹具，先补“上一循环已有行”反例后重跑打红，不把脚本锚点失败或无效输入记为通过。
- 浏览器只读复验【测试】项目生成弹窗：15 个循环及粗裁提醒正常，循环 checkbox / 展开 / 跳转均有可访问名称；先展开 D 再展开 A 时 `.gt-gen-plan__detail` 始终为 1；390 px 视口弹窗宽 374.4 px、页面无横向溢出；console error 为 0。未点击生成或跳转裁剪，未产生写入。
- 存量 PG 只读核对仍为：跨循环程序行 0、同编码跨循环重复 0、active `(project, cycle, code)` 重复 0、软删模板集 0，现有区间均为标准区间；无需数据迁移。
- 本轮代码、测试和文档仍未提交 / 推送。后续建议按 design §6.8 排序，优先两阶段生成 + operation id、active 唯一索引。
