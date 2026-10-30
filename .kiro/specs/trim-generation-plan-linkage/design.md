# 设计：程序裁剪 → 生成底稿联动（生成计划）

需求见 requirements.md（R1~R6），本文只写怎么做。

## 1. 总体

```
裁剪页（procedure_instances）──粗裁 preview/apply──▶ 粗裁应用凭证（consumed）
        │ 初始化 / 补齐（委派人）                         │
        ▼                                                  ▼
TrimmedScope（含母码跟随）◀───────── 生成计划（只读）── 粗裁状态（谁 / 何时）
        │                                   │
        ▼                                   ▼
 plan_generation（生成七入口）      生成弹窗（按循环勾选）──POST /generate──▶ 回执
```

- 唯一判定源仍是 `procedure_scope_retention.TrimmedScope`：计划与生成接口用同一份判定，计划说「将生成」的编码，生成接口必须判为新建（PG 一致性测试钉死，§5）。
- 业务分类只在「没人保存过的循环」里当默认方案；保存过的循环以程序行为准（R1.4）。业务分类在裁剪页上以建议出现（R3.4），不再是弹窗里看不见的默认不勾。
- 不新增迁移：粗裁状态取 `procedure_operation_previews` 里已消费的 `trim` 凭证（`request_payload_snapshot.entries` 里 `kind=scope` 的 `cycle`），2026-10-28 真库 53 条已消费凭证、只有重药安徽（B~N）与和平药房（D）保存过粗裁，A / S 没有任何项目保存过。

## 2. 后端

### 2.1 母码跟随下级程序行（R4，`procedure_scope_retention.py`）

`TrimmedScope.from_rows` 额外建 `children`：对每条普通行（编码不含「至」）取 `code_lineage(code)[1:]`，对每条合法区间行的每个成员取 `code_lineage(member)[1:]`，把行编码登记到这些母码名下。不合法区间（按普通编码处理的 `F1-5至F2-9`）不登记，否则会凭空造出 `F1-5`、`F1` 的「下级」（契约用例里 `F1-5 → null` 会被打破）。

判定改成内部 `_decide(code) -> (owner, trimmed, via)`，`via ∈ {lineage, range, children}`：
1. 区间码本身、谱系逐级查找：与现行完全相同。
2. 都没命中、编码首字母在 `SUBSTANTIVE_CYCLES = DEFGHIJKLMN`、且 `children[code]` 非空 ⇒ 跟随：下级行全部已裁才算已裁。决定者取「按规范化编码排序后的第一条已裁下级行」（全裁时）或「第一条执行的下级行」（保留时），排序保证 Python 与 Java 结果一致。
3. 否则 `None`（保留）。

`decided_by / is_trimmed / trim_owner / split / decide` 签名不变，全部经 `_decide`；新增 `follows_children(code) -> bool` 供计划标注。`to_payload` 不变（快照规范形不含派生的 children）。

影响面：13 个 `load_trimmed_scope` 调用方自动生效。粗裁应用联动（`procedure_trim_recycle`）会把「科目程序全部裁掉」时已生成的审定表一起列进移入回收站预览（有编制内容的仍要确认），这是本规则的预期结果；存量项目不主动移动（R4.4 只读核对）。

契约：README「粗裁判定」加一条；`trimmed-scope.cases.json` 加一组「实质性循环母码跟随下级程序行」（全裁 / 部分裁 / 区间成员 / 更深下级 / B 类不适用 / 不合法区间不算下级），`generation-plan.cases.json` 加一条母码分流用例。

### 2.2 程序目录与补齐（R5，新模块 `procedure_catalog.py`）

从 `ProcedureService.init_from_templates` 抽出并扩展，`procedure_service.py` 只调用它：

- `catalog_items(db, project_id, cycle)`：现行 init 的来源顺序（项目选用的模板库 → `gt_template_library.json`），`gt_template_library.json` 读一次缓存。`WpTemplate` 降级分支保留在 init 里不动。
- `cycle_template_items(cycle)`：`wp_account_mapping.json` 里该循环的模板编码（与生成弹窗、标准年审模板集同一份），保持文件顺序。
- `category_restriction(code)`：该编码在 A / B / C 三类里不适用的类别集合（映射条目的 `applicable_categories` + 参考标准排除清单，复用 `business_category_service.is_template_applicable`）。
- `supplement_items(rows, items)`（纯函数）：`scope = TrimmedScope.from_rows(rows)`；补「`scope.decided_by(c) is None`」的编码，和「决定者不是自己、且 `category_restriction(c) != category_restriction(决定者)`」的子码（现算只有 `A1-12`、`A1-16`：A1 行里只有这两张是上市专用）；已有行的编码、含「至」的编码跳过；保持模板顺序。按目录初始化全部循环时预计补 46 个：B 26、A 17（15 个没有程序行的 + A1-12 / A1-16）、S 3（实施时现算核对）；D2 / D4 / E1 / F2 由 §2.1 跟随下级，不补。
- `ensure_supplement_rows(db, project_id, cycle)`：PG 下先取 `pg_advisory_xact_lock(hashtextextended('procedure_init:{project}:{cycle}', 0))`（SQLite 跳过，与项目里其他咨询锁同写法），再读该循环未删除的行、算缺的、插入：`procedure_code = wp_code = 编码`、`procedure_name = 模板名称`、`is_custom = False`、`sort_order` 接在现有最大值之后；状态由 `supplement_entries` 给出 —— 没有程序行管的补 `execute`，适用性分裂的子码沿用原决定行（原决定行已裁 ⇒ 补的行同状态、理由沿用，没有理由时写「随程序行 X 一起裁剪」），保证补齐前后生成判定不变。返回补了几行。

`init_from_templates` 改为：取锁 → 已有行则只补齐 → 没有行则按目录建行再补齐 → 返回 `get_procedures`。原来「两个并发初始化都看到 0 行、各建一套」的竞态一并消除（检查放到锁内）。

`get_procedures` 每行加两个键（只增不改，`_to_dict` 原有键不动）：
- `origin`：`custom`（`is_custom`）/ `catalog`（编码在该循环目录里）/ `supplement`。
- `category_hint`：本行决定的模板编码（`TrimmedScope` 只用本循环的行）全部按项目业务分类不适用时为 `{"reason": "…"}`，否则 `null`。理由取 `business_category_service` 的 `applicable_reason`；项目没有填写 A / B / C 分类（包括真库里把该字段写成 `IPO` / `refinancing` 的情况）时按 C 类判断，并在提示中明说。

### 2.3 为什么补成可裁的程序行而不是「必做」

44 个编码按名称核对：B1-3 / B1-4 / B1-7（承接评价、尽调、质控委员会记录）、B5-1~B5-9-2 与 B5附件（13 份约定书变体，按业务类型只用其一）、B60A~D（内控 / IPO / 国企 / 监管）、B60-2-x 与 A27（IT 审计）、B60-3（专家）、A18（监管报送）、A24 / A25（非大型国企 / 大型国企二选一）、A26（专业技术委员会）、S32 / S35 / S33-REV（IPO / 再融资 / 综合核查修订）都是按条件才需要；大多数项目都要的只有 B5、B60、A21~A23 这类少数几份，而裁剪页本来就要求裁剪必须填理由并留痕。补成程序行、默认执行：生成结果与现在一致，经理可以带理由裁掉不适用的那几份，也能给它们指定底稿主编（现在这 44 份在裁剪页上连主编都指派不了）。

### 2.4 粗裁状态（R1.3 / R1.8，`procedure_generation_plan.py`）

`load_cycle_confirmations(db, project_id)`：查本项目 `operation='trim' AND consumed_at IS NOT NULL` 的凭证（列：`consumed_at`、`actor_user_id`、`request_payload_snapshot`），Python 里展开 `entries`，取每个循环最近一次；保存人姓名按 `staff_members.user_id` 取 `name`，取不到用 `users.username`。返回 `{cycle: {"confirmed_at", "confirmed_by"}}`。没变化地保存一次也算保存（裁剪页保存时每条程序行都会作为条目提交）。

### 2.5 生成计划（R1，`procedure_generation_plan.py`）

`build_generation_plan(db, project_id, template_set_id | None) -> dict`：

1. 编码全集：给了模板集按其 `template_codes`（不存在 → `LookupError` → 404）；没给按映射表全部编码。
2. 业务分类：`projects.business_category` 首字母，空则按 C 并标 `defaulted`。
3. 程序行：一次查询本项目未删除的 `procedure_instances`（在保存点里，失败抛 `TrimScopeUnavailable` → 503），`TrimmedScope.from_rows((coalesce(wp_code, procedure_code), status))` —— 与 `load_trimmed_scope` 同一规则；同时得到每个循环的程序行明细。
4. `wp_index_states`（现有函数）判已生成 / 在回收站；`load_cycle_confirmations` 判循环粗裁状态；`catalog_items` 算 `origin`。
5. 每个编码的状态按优先级取第一个成立的：`trimmed`（`scope.is_trimmed`）> `in_recycle` > `existing` > `category_excluded`（循环未打开 / 未保存，且业务分类不适用）> `to_create`。已保存循环里业务分类不适用但判为生成的标 `category_conflict = true`。
6. 按循环分组，顺序 `B C D E F G H I J K L M N A S`，其余按字母排在后面；循环状态 `not_initialized`（没有程序行）/ `unconfirmed` / `confirmed`。

返回形状（契约 `generation-plan-view.schema.json`）：

```
{ template_set: {id, set_name, code_count} | null,
  business_category: {code, defaulted},
  totals: {total, to_create, existing, in_recycle, trimmed, category_excluded},
  cycles: [{ cycle, trim_state, confirmed_at, confirmed_by, counts: {同 totals},
             programs: [{code, name, status, skip_reason, origin}],
             items: [{wp_code, wp_name, state, decided_by, follows_children,
                      category_applicable, category_reason, category_conflict}] }] }
```

前端只从 `items` 推导要发送的编码，计划本身不再另给一份 `to_create` 列表（单一来源）。

### 2.6 路由与契约

`routers/procedures.py`（已在协作组注册、前缀 `/api/projects`）加两个 GET，路径段沿用 `procedure-scope`（避开 `/procedures/{cycle}` 捕获，也不落进 `/working-papers/` 的底稿入口账本）：
- `/{project_id}/procedure-scope/generation-plan`（`require_project_access("readonly")`；`template_set_id` 可选；404 / 503）。
- `/{project_id}/procedure-scope/confirmations`（readonly）。

权限说明：计划只给出模板目录里的编码与名称、粗裁结论、各编码是否已生成 / 在回收站，与裁剪页 `GET /procedures/{cycle}`（readonly，行上带 `wp_id`）暴露的信息同级。

契约：新文件 `generation-plan-view.schema.json`（`$defs/plan`、`$defs/confirmations`），README 文件表与「生成」节各加一行；`export_procedure_chain_openapi.py` 的 `OPERATIONS` 登记两个接口并重新导出；契约测试 `PUBLISHED` 加入新 schema。

## 3. 前端

### 3.1 接口

- `services/apiPaths/workpaper.ts` 的 `procedures` 加 `generationPlan(pid)`、`scopeConfirmations(pid)`。
- 新文件 `services/generationPlanApi.ts`：类型 + `getGenerationPlan(pid, templateSetId?)`、`getScopeConfirmations(pid)`、`generateWorkpapers(pid, {templateSetId, year, codes})`（搬自 WorkpaperList：先模板集生成，5xx 回退按编码生成）。调用方自己处理错误的请求带 `_silent`。

### 3.2 纯函数（`components/workpaper/generation/generationPlanModel.ts`）

`CYCLE_ORDER` / `CYCLE_LABELS`（与裁剪页页签同名）、`orderCycles`、`defaultSelectedCycles(plan, initialCycle?)`（给了初始循环只选它，否则选所有将生成 > 0 的循环）、`codesToGenerate(plan, selected)`、`groupItemsByProgram(cycle)`（按 `decided_by` 归到程序行，`null` 的归「尚无程序行」）、`trimStateText`、`itemStateMeta`、`pendingTrimCycles(plan)`（未打开 / 未保存且有将生成的循环）。

### 3.3 弹窗 `components/workpaper/generation/GenerationPlanDialog.vue`

- props：`modelValue`、`projectId`、`year: number | null`、`initialCycle?`；emits：`update:modelValue`、`generated(result)`、`navigate-cycle(cycle)`。
- 打开时：幂等 seed 模板集 → 列模板集（只留「标准年审」与自建，与原过滤口径相同）→ 默认选第一个 → 取计划。切换模板集重新取计划。
- 布局：顶部模板集选择、业务分类（项目未填写时注明按 C 类）、审计年度；未保存粗裁提醒（列出循环，每个可点「去粗裁」）；循环汇总表（勾选列只在循环级、将生成为 0 的禁用；列：循环、粗裁状态、程序 保留 / 裁掉、将生成、已生成、在回收站、已裁剪、业务分类不生成、操作「去程序裁剪」），展开行按程序行分组列底稿（状态标签区分颜色，跟随下级的标「跟随下级程序」，冲突的标「业务分类不适用」）；底部「已选 N 个循环，将生成 M 个底稿」+「生成 M 个底稿」。
- 生成前年度为空直接提示（与原逻辑同）；生成成功 `emit('generated')` 并按回执提示，关闭弹窗；失败按原 `handleApiError`。
- 「去程序裁剪」只 `emit('navigate-cycle', cycle)` 并关闭弹窗，由宿主决定怎么跳（裁剪页要先过未保存修改确认，R3.8）。

### 3.4 底稿列表页

`onGenerateWorkpapers` 只做年度检查 + 打开弹窗；删掉 ElMessageBox 选模板集、`WorkpaperTrimDialog` 与它的三个 ref、`h` 导入；`navigate-cycle` ⇒ `router.push({ name: 'ProcedureTrimming', params, query: { cycle, from: 'generate' } })`；工具栏加「✂️ 程序裁剪」（不带循环）。`WorkpaperTrimDialog.vue` 与它的测试删除（无其他引用，`template-list` 接口留给其他调用方，本 spec 不动）。旧两步流程的 `composables/useWorkpaperGenerate.ts` 也已确认全仓零生产调用并删除；跨语言调用点守卫改认新的 `generationPlanApi.ts` 与 `apiPaths` 访问器形态。

### 3.5 裁剪页（逻辑放 `components/workpaper/composables/useTrimGenerationLink.ts`）

- 组合式函数提供：`initialCycleFromRoute(route, cycles)`、`confirmations` 状态与 `loadConfirmations()`、`confirmationText(cycle)`、`categoryHintRows(procedures)`、`adoptCategoryHint(row)` / `adoptAllCategoryHints(rows)`（设为裁剪并填理由，仍需保存）、`promptAfterSave()`（返回 `generate | delegate | stay`）。
- 视图改动：工具栏加「⬇️ 生成底稿」（`canEditInProject && 未归档`）并挂弹窗（`initial-cycle = activeCycle`，`navigate-cycle` 走已有的 `jumpToCycleFromOverview`，生成后 `loadProcedures()`）；`loadProcedures` 委派人先调 `initProcedures`（补齐），失败或只读成员再 `getProcedures`；`onMounted` 先读 `?cycle=`；保存粗裁后的「前往委派」确认改成三选一；「裁剪建议」列在没有其他建议时显示业务分类建议与「按建议裁剪」；建议条旁边加「按业务分类建议裁剪 N 项」；表格工具栏显示粗裁状态；「来源」列加「补充」；「未生成」提示改为指向「⬇️ 生成底稿」。
- 行数预算：视图现 4089 行，上限 4212；净增控制在 80 行内。

## 4. 不做的事 / 范围外

- 方案二（生成前按模板细裁、先委派后生成）另立项。
- 一键智能裁剪不吸收业务分类建议（`decideTrim` 的档位与冻结枚举不改），只在建议列与批量按钮里体现。
- 其他六个生成入口不加业务分类判定（与现状一致）。
- 「必做、不可裁」清单不在本 spec 内做（§2.3）；如需，可在裁剪页给这几份加只读保护，另议。
- `GET /api/workpapers/template-list` 留着（`/reference` 仍被业务分类选择器使用），本 spec 不删。

## 5. 验证设计

- 后端单测：母码跟随（全裁 / 部分 / 区间成员 / 更深下级 / B 类不适用 / 不合法区间 / 决定者排序）、补齐（未覆盖 + 适用性分裂、幂等、不改已有行、SQLite 跳锁）、`origin` / `category_hint`、计划（五态优先级、循环三态、默认方案只用于未保存、冲突标记、模板集过滤与 404、母码标注、循环顺序、按 schema 校验）、粗裁状态（只认已消费 `trim` 凭证里的 scope 条目、取最近一次、姓名回退）。
- 端点测试（TestClient 真发请求，只覆盖 `get_current_user` / `get_db`）：未登录 401、非成员 403、成员 200、模板集不存在 404。
- 契约测试：共享用例 + 新 schema + OpenAPI `--check`。
- PG 测试（回滚事务，只读）：每个真实项目的计划里「将生成」的编码，`plan_generation` 全部判为 `to_create`；「已裁剪」的全部判为 `skipped_trimmed_codes`。
- 真库只读探针：母码跟随新判为已裁的编码与是否已生成（R4.4），结果写进 tasks 验收记录。
- 前端：`generationPlanModel.spec.ts`、`GenerationPlanDialog.spec.ts`（循环顺序、只有循环级勾选、未保存提醒、发送编码 = 所选循环的将生成、读取失败禁用生成、`navigate-cycle`）、`useTrimGenerationLink.spec.ts`；现有 WorkpaperList / ProcedureTrimming 用例全跑。
- 磁盘变异最终扩为 19 条：后端 13 条覆盖母码、全裁、非法区间、联动决定者、补齐两类边界、适用性分裂、业务分类默认、五态优先级、凭证消费、重初始化、建议完整性、鉴权；前端 6 条覆盖发送编码、循环可选性、初始循环、初始化、建议与保存后分流。每条必须红在预期断言上。
- 浏览器实测：真实项目（重庆医药集团医疗器械）只打开弹窗查看；写入（补齐、保存粗裁、生成）在新建的【测试】项目上做，用完走平台删除。

## 6. 实施勘误与复盘（2026-10-28）

### 6.1 设计中途改正

- 最初把裁剪页覆盖不到的文档概括为「必做」是错误的。逐项核对后，约定书、IPO / IT / 专家文档、A24 / A25 等多数按条件适用，因此改为**默认执行、可以带理由裁掉的补充程序行**。最终现算补 46 个编码（B 26 / A 17 / S 3），不是早期口头估计的 44 个。
- 组合式函数的设计路径写成了 `components/workpaper/trim/`，实现遵循现有目录放在 `components/workpaper/composables/`；本节已更正。旧 `useWorkpaperGenerate` 不是需要兼容的公共入口，而是零生产调用的旧两步流程，实施时一并删除。
- `business_category` 在真库里还存有 `IPO` / `refinancing`。按首字母把 `IPO` 当 I 类没有产品含义；只有 A / B / C 算已填写分类，其余明确提示并按 C 类默认判断。

### 6.2 M5 存活不是测试缺口，而是等价代码

首轮变异删除 `code in existing` 后仍全绿。追到 `TrimmedScope` 后确认：已有普通编码行一定先被 `decided_by(code)` 回报为「由自己决定」，后续的 `verdict[0] != code` 已经排除它，所以 `code in existing` 是同一条件的重复写法。用真实目录、随机状态、删行、规范化差异和区间行跑 3,000 组旧 / 新实现对拍，结果差异为 0。处理方式不是添加一个永远构造不出的测试，而是删掉冗余判断；M5 改成两个可证伪的语义变异（把「自己决定」也加入补齐、允许区间编码补齐），两条都被现有用例打红。

### 6.3 测试和协作中暴露的问题

- `trimDecisionWiring.spec.ts` 的判据 D 只识别 `const X =`，不识别组合式函数返回值解构；首轮因此报自由调用。为不扩大守卫，本次按既有判据显式声明各名字。这个约束偏脆，后续若治理应单独改 AST 判据。
- 裁剪页原先不依赖 Pinia，既有挂载用例没有安装 Pinia；组合式函数若在 setup 顶层立即取 store 会让整个页面挂载失败，因此改为在 computed 求值时取，缺上下文时保守返回不可生成。
- 跨语言调用点守卫最初只认字面 URL / 旧函数调用，`apiPaths` 访问器会被误报为「没有调用方」；实现中补了访问器形态和反向自检。
- 验证期间主工作区 HEAD 被并发会话前移 121 个提交，且共享文件存在他人暂存块。回归和磁盘变异都放在锁定的分离头 worktree，两个共用页面只叠加本 spec 的未暂存 diff，避免覆盖并发改动。
- 共享终端有过 `^C` 干扰，长跑改为隐藏子进程 + 独立日志；退出码异常时以 JUnit / JSON 产物是否完整为准，不把中断当通过。

### 6.4 浏览器走查中的过程失误与恢复

真实项目只读走查时，我错误地用 admin 点击了「去程序裁剪」。裁剪页按既定产品逻辑会让委派人调用初始化接口，因此意外新增了 A 循环 76 条默认程序行，违反了本次「真实项目只读」的验证约束。发现后立即把页面停到 `about:blank`，核对 76 行同一事务时间、全是默认值、无父子引用、无粗裁凭证、未生成底稿；用带行数 / 时间戳 / 字段 / 引用 guard 的脚本先 dry-run，再精确删除这批行（删除前的 76 行原样备份在 `backend/backups/trim_plan_accidental_real_A_init_20261028.json`，该目录不入库）。删除后重新调用只读计划接口，A 循环恢复为 `not_initialized`、`program_count=0`，1025 / 994 / 31 等全计划数字与走查前逐项一致。

这是测试流程失误，不应粉饰成产品验证。以后真实项目走查写路径页面只能使用只读成员账号，或在浏览器层明确阻断写请求；不能因为「只点导航」就假定页面不会初始化。

### 6.5 收尾后自查发现的缺陷：补齐会让已裁的分裂子码恢复生成

收尾后补跑了一个此前没写成测试的不变量：「补齐前后每个模板编码的生成判定不变」（需求里写了「生成结果与现在相同」，但只验证了补几行、不改已有行，没验证判定）。真实目录 + 随机状态下，A 循环 300 组里有 200 组变化：A1 整行已裁时，A1-12 / A1-16 原本跟着 A1 不生成，补成「执行」后变成生成。裁剪页对委派人每次打开都走初始化，所以上线前已把 A1 裁掉的项目会在下次打开时悄悄恢复这两份底稿。真库现在 4 个有程序行的项目都没有触发（A 循环没人裁过 A1），属于潜在缺陷。

修复：新增纯函数 `supplement_entries`，分裂子码沿用原决定行的状态与理由（§2.2）。新增 4 个用例：随机状态不变量（80 组 × 15 循环，并断言确实遇到过「原决定行已裁」）、理由兜底、真实初始化路径（上线前已裁 A1 的项目再初始化）、目录缺下级时的唯一例外。4 条针对性磁盘变异全部打红。

唯一允许的判定变化：项目选用的模板库缺了某个下级编码时，补上的下级行是「执行」，跟随它的科目母码会从「下级全裁」变为保留。这与该下级照常生成一致，也与本规则上线前母码恒保留一致；用例把这个例外钉成「只允许 D~N 母码、只允许从裁到保留、必须有新补的执行下级」。标准目录下 D~N 补 0 行，不会出现。

### 6.6 已知未收口项

- 【测试】项目实际生成回执为 69 个成功、0 个失败，但其中 A13-2~A13-5 没有模板而建了 4 份空白底稿，54 份未自动填表头。这是既有生成质量欠账，不是本次计划联动造成的；本 spec 如实保留回执，不顺手改模板域。
- `openGenerateDialog` 的脏修改拦截已在浏览器验证为不打开弹窗、也不发计划请求，但还没有直接的组件级自动用例。
- 「生成前按模板细裁、先委派后生成」仍是方案二，按用户裁决另立项，本 spec 不扩范围。

### 6.7 最终全链复盘新增收口（2026-10-29）

这轮不是只复看页面，而是按「裁剪决定 → 生成计划 → 生成写入 → 回执 → 页面重开」重走判定、权限、事务和竞态：

- 同一项目的 `plan_generation`、粗裁 apply、循环初始化、自定义程序新增 / 删除统一取得 PG transaction advisory lock；生成在取锁后重新读取 scope，调用方传入的旧 `scope=` 只保留签名兼容。这样同时闭合「生成与裁剪交错」「两个下级并发裁剪漏回收母码」「并发生成重复」三类竞态。
- 粗裁 preview 的 `target_versions` 纳入 `scope:{procedure_instance_id}` 状态摘要，旧 preview 不能覆盖保存后的新决定。现有 JSONB 已足够表达该 CAS，本轮不为此新增迁移。
- 项目模板目录只有“查询成功且 0 行”才能回退全局目录；SQL / ORM 查询失败统一返回 503。归档、删除和不存在项目在 delegator guard 内 fail-closed，并在跨项目检查后把 RLS 恢复到当前项目。
- 重叠区间仍执行 execute-wins，但代表决定者必须来自产生最终结论的来源，`deciders()` 返回全部参与来源；跨循环标准编码不能被当作另一循环自定义行写入；软删模板集在计划与实际生成两处都按不存在处理。
- 生成弹窗以 open / project epoch 隔离旧读取和旧回执；生成中禁止关闭、Esc、取消和跳去裁剪，且只调用一次模板集生成端点。权限或归档状态变化会即时禁用提交。粗裁状态 GET 禁用请求去重并以请求序号接纳结果，瞬时失败保留上次成功状态。
- 裁剪页切循环先清旧表体，旧响应不能覆盖新循环，失败后禁止保存；同一循环的并发初始化共享在途请求。底稿列表年度和项目名称只读 `projectStore` / `ProjectContextGate`，不再发第二份项目详情 GET。
- 弹窗循环 checkbox 和展开按钮都有可访问名称；一次只展开一个循环；390 px 视口实测弹窗宽 374.4 px、无横向溢出。

最终回归还抓到三处测试自身过期：跨语言契约仍强制前端同时调用两个写端点，与“禁止 5xx 改调第二写端点”冲突；`AsyncMock` 把同步的 `AsyncSession.get_bind()` 伪造成 coroutine；SQLite characterization 夹具漏建刚进入读取路径的模板目录表。三处均按真实生产契约修正。F14 变异最初存活，是因为“失败清空旧表体”用例从空表开始，删掉清空语句仍然得到空数组；用例改为先放入上一循环行后，变异准确打红。这个过程再次说明，全绿只说明给定输入没失败，不能替代故障注入。

### 6.8 后续优化建议（本 spec 不扩范围）

1. **P1，两阶段生成 + operation id。** 当前事务咨询锁会随生成事务持有，69 份底稿实测约 6 秒，更大模板集会拉长裁剪等待。建议短事务锁内记录 scope revision 与生成 operation，锁外生成临时文件，再在短事务锁内 CAS revision 后提交；请求带稳定 operation id，超时重试返回同一回执。
2. **P1，active 程序行唯一索引。** 为 `(project_id, audit_cycle, normalized_procedure_code)` 建只约束 active 行的唯一索引，数据库兜住未来遗漏项目锁或旁路写入。
3. **P2，粗裁当前态投影。** `load_cycle_confirmations` 目前仍需扫描历史 preview JSON。可新增每项目 / 循环当前 revision 投影，历史凭证继续留作审计，读取改为 O(循环数)。
4. **P2，拆分业务分类字段。** `business_category` 同时存 A/B/C 与 `IPO` / `refinancing`，建议把交易 / 上市类型拆成独立字段，避免继续靠首字母和兜底解释。
5. **P2，只读 UAT 身份与写请求阻断。** 真实项目走查固定使用只读账号，并在自动浏览器上下文拦截 POST / PUT / PATCH / DELETE；这比依赖操作者记住“不要点”可靠。
6. **P3，按实测决定明细虚拟化。** 当前单展开已限制 DOM；只有性能跟踪证明单个循环明细仍超预算时再引入虚拟列表，避免为尚未出现的瓶颈增加复杂度。
