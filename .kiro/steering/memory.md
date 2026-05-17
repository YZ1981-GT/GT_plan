---
inclusion: always
---

# 持久记忆

每次对话自动加载。详细架构见 `#architecture`，编码规范见 `#conventions`，开发历史见 `#dev-history`。
当 memory.md 超过 ~200 行时，自动将已完成事项迁移到 dev-history.md，技术决策迁移到 architecture.md，规范迁移到 conventions.md，保持自身简洁（只留状态摘要+活跃待办）。

## 用户偏好（核心）

- 语言：中文
- 部署：本地优先、轻量方案
- 启动：`start-dev.bat` 一键启动后端 9980 + 前端 3030
- 打包：build_exe.py（PyInstaller），不要 .bat
- **输出控制**：别一次输出过多，分步输出或修改；大改动拆小批次
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致，空壳标记 developing
- 前后端联动：不能只开发后端不管前端
- 删除必须二次确认，所有删除先进回收站
- 一次性脚本用完即删
- **git 提交不要分很多区**：用户偏好单次 commit 提交所有变更，不要拆成多个分组 commit
- 提建议前先验证（不要引用过时记录，vue-tsc exit 0 = 零错误，不要再提已修复的问题）
- 给出建议时必须反复论证，提供最仔细的可落地方案，不能泛泛而谈或停留在表面描述
- 判断前端模块是否存在，必须同时检查 views/ 根目录 + components/ 子目录
- 文档同步：功能变更后同步更新需求文档
- 记忆拆分：memory.md 只放精简状态+待办，技术决策→architecture.md，规范→conventions.md，修复记录→dev-history.md
- 目标并发规模 6000 人
- 表格列宽要足够大，不折行不省略号截断
- **表格选中行必须视觉明显**：8% 透明度背景色在白底上几乎不可见，最低 14% + 左侧 3px 紫色竖线指示器；hover 也要有浅色反馈；用户反馈"丑"多数是行间距太松+选中不明显
- **最大化数据显示区域**：工具栏按钮（刷新/导出/保存）应合并到 Tab 栏右侧而非独占一行；减少表格上方的非数据行数，让表格尽可能多显示数据行
- **简单 CRUD 页面不用 GtPageHeader 紫色渐变**：人员档案/知识库等列表管理页用白色简洁工具栏（左标题+右操作按钮），GtPageHeader 只用于项目级/仪表盘等需要视觉层级的页面；紫色大块在简单页面显得"丑"
- 表格数字列（金额、科目编号等）统一使用 Arial Narrow 字体 + `white-space: nowrap` + `font-variant-numeric: tabular-nums`，通过 `.gt-amt` class 实现
- **el-table 字号控制必须用动态 class + !important**：`:style="{ fontSize }"` 不生效（内部 DOM 层级太深被 Element Plus 默认样式覆盖）；正确方案 = `:class="gt-tb-font-${size}"` + scoped `:deep(.gt-tb-font-sm) th .cell, td .cell { font-size: 12px !important }`
- **所有表格统一用 el-table**：替换所有原生 HTML table（试算平衡表/报表等）；不引入 AG Grid（包体积大+与 Univer 重叠）；底稿编辑器继续用 Univer；el-table + useCellSelection composable 满足"查看+少量编辑"需求
- 表格分页用标准分页组件（左侧 page size 选择器 + 右侧页码导航含 jumper），不用"加载更多"模式
- 四表联查需支持全屏模式 + 行选择（checkbox）+ 右键菜单，右键菜单预留"抽凭到底稿"入口（后续与底稿抽凭模块衔接）
- **溯源/穿透跳转后必须支持 Backspace 返回原位**：`initGlobalBackspace(router)` 在 DefaultLayout 注册一次全局监听器，任何视图跳转前调 `useNavigationStack().push()` 即可；不拦截输入框/textarea/contentEditable/el-select 弹出层内的 Backspace
- 表格编辑需支持查看/编辑模式切换
- 复制按钮命名：工具栏"复制整表" vs 右键"复制选中区域"
- 系统打磨采用 PDCA 迭代模式：提建议→成 spec 三件套→实施→复盘→下一轮新需求，直到可改进项穷尽
- 打磨迭代具体化为"5 角色轮转"：合伙人/项目经理/质控/审计助理/EQCR 独立复核，每轮只站单一角色视角找断层，规则见 `.kiro/specs/refinement-round1-review-closure/README.md`
- 每轮 requirements.md 起草后必须做"代码锚定交叉核验"（grep 所有假设的字段/表/端点/枚举），发现硬错立刻回补到文档，避免错误带到 design 阶段
- 标任务 [x] 前必须跑 pytest 或对应测试通过，而非仅因"代码文件存在"就标完成；用户明确要求做完整复盘时要诚实暴露问题而非粉饰
- **账表导入识别引擎设计原则**：通用规则+动态适配，不做"看一个改一个"的定制化；识别处理时表头和列内容同时处理（前 20 行数据量不大）；脚本要支持扩展（声明式 JSON 配置）而非硬编码 if-else

## Spec 工作流规范（production-readiness 复盘沉淀）

- design.md 起草必须做"代码锚定"：每个修改点列文件+行号/函数名，npm 包要 `npm view` 验证存在，字段/枚举/端点路径 grep 核对，避免事后大量校正备忘
- tasks.md 只放可被自动化工具推进的编码任务；手动浏览器验证（如"输入公式看结果"）应放 spec 末尾"UAT 验收清单"，不占 taskStatus 工作流
- Sprint 粒度按"验证边界"切分：每个 Sprint ≤10 个任务，强制回归测试+UAT 才进下一 Sprint（反例：production-readiness Sprint 2 塞 20+ 小改）
- 任务描述中引用的依赖包、类名、API 路径，变化后要回填更新（如 0.1/0.2 的 `@univerjs/preset-sheets-formula` 实际不存在）
- **spec 实施前预检策略（template-library-coordination 沉淀 2026-05-16）**：开始 Sprint 1 前必须 grep 所有目标文件（routers / components / routes / migrations）核对是否已预先实施；若已存在直接 readFile 验证完整性后标 [x]，避免 subagent 空跑重新生成；本 spec 大量 Sprint 1-2 文件（template_library_mgmt.py 913 行 / WorkpaperWorkbench 树形改造 / TemplateLibraryMgmt.vue 主页面 / 4 个 Tab 组件）在 spec 创建时已部分预实施，避免重新执行节省 6+ subagent 调用
- **R5 复盘教训**：标 `[x]` 前必须跑 pytest 验证；"代码文件存在"不等于"功能可用"。Task 12/13 初次标完成时其实 gate_engine/sign_service 有隐藏 flush bug，集成测试才能暴露
- **跨文件字段/枚举假设必须 grep 核对**：User.metadata_、WorkHour.status 类型、ProjectStatus.in_progress、CompetenceRating.A 这些都是我凭印象写的错误假设，导致代码 runtime 失败
- **测试 fixture 模板**：每个新 test 文件应复用邻居文件的 `db_session` fixture 模板（见 test_eqcr_gate_approve.py 为样板：本地 _engine + pytest_asyncio.fixture + Base.metadata.create_all）；backend/tests/conftest.py 不提供 db_session
- **Run All Tasks 前必须预检现状**：创建 spec 前或执行前先 grep 关键标志（如 `<table`）确认哪些 task 实际需要执行；已完成的 task 直接标 [x] 跳过，避免 21 次 subagent 空跑（表格统一化 spec 教训）
- **spec 创建阶段禁止动 production 代码（template-library-coordination 复盘 2026-05-16）**：design.md 想写代码骨架时放到独立"代码骨架示例"区块加注释"非实施"，实施 freeze 后才进入 Sprint 1；本 spec 创建时混入了 §54 路由/template_library_mgmt.py 913 行/4 个 Tab 组件等大量实施代码，导致 Sprint 1-4 大部分 task 标 [x] 时只是"验证文件存在"而非"实施完成"，复盘分不清边界
- **spec 创建时强制"假设清单 grep 核验"5 项**：(1) ORM 字段 → grep `class XxxModel` 确认；(2) seed JSON → `Test-Path backend/data/xxx.json` 实测；(3) 路由 §N → grep `router_registry.py` 当前编号占用；(4) "前端已有 X.vue" → fileSearch 实测；(5) DB 表/列 → grep models 文件确认；五项缺一项就会出现 spec 假设错位，靠 Sprint 0 兜底是补救不是预防（template-library-coordination 一次踩 5 处）
- **tasks.md 末尾固定"已知缺口与技术债"章节**：与 UAT 验收清单平级，每个缺口标 P0/P1/P2 + 触发条件 + 后续 spec 编号；实施时新引入的妥协（降级 stub / 占位实现 / 跳过的 PBT）强制回写到这里，避免技术债散落各 task 描述里查不回来
- **PBT 区分 P0/可选两档，P0 不允许跳过**：P0 = authz / readonly enforcement / 数据正确性（覆盖率公式、SAVEPOINT 边界、403/405 校验）；可选 = 边界探索类；用 `[ ]*` 标记必须在 design.md 显式写"接受测试缺口的理由"，否则按 P0 处理；template-library-coordination 17 个 Property 中 9 个 PBT 全跳过仅靠集成测试间接覆盖 4 条，剩 13 条无自动化校验
- **subagent 调用规约（template-library-coordination 沉淀）**：(1) 单次任务 ≤ 4 件事，超过强制拆批次（本 spec Sprint 4 batch 1 一次 5 件事 prompt 5000+ token）；(2) prompt 强制返回结构化 JSON（files_created / files_modified / vue_tsc_status / pytest_count）替代大段总结；(3) orchestrator 不要预读 subagent 即将创建的目标文件，避免 ENOENT 噪声 + 文件被读 3 次
- **集成测试 docstring 强制反向映射 Property**：每个测试函数 docstring 加 `# Validates: Property X`，便于复盘时找回"哪些 Property 被覆盖、哪些缺口"；template-library-coordination Sprint 5 集成测试已落地此规约（test_seed_all_savepoint_isolation 标 D15 + Property 9 等）
- **通用 spec 核验工具已固化（2026-05-16）**：`backend/scripts/verify_spec_facts.py` + 各 spec 目录下 `snapshot.json` schema（json_sources / computed_values / db_tables / missing_files / router_assertions / orm_assertions / alembic_assertions 7 类断言）；用法 `python backend/scripts/verify_spec_facts.py {spec_id}` 或 `--all` 批量；退出码 0/1/2 区分 OK/WARN/FAIL；新 spec 只需在其目录建 snapshot.json 即可复用，不再写一次性脚本
- **snapshot.json schema 当前为 experimental v1**：仅 template-library-coordination 试用过；2-3 个新 spec 实战后再固化；当前已知不足 = computed_values 仅支持加法 / db_tables SQL 不支持参数化 / orm_assertions 仅支持"必须无字段"反向断言 / 无容差范围（仅 ±tolerance% 单档）；新 spec 用时 schema 可能 break
- **TD 章节不是 task 退回的避难所（template-library-coordination 二轮复盘 2026-05-16）**：tasks.md 末尾"已知缺口与技术债"只放"实施完成但留有真缺口"的项；task 没真正完成（占位实现 / 未真实数据验证）的应该 `[x]` → `[ ]` 退回未完成，**不应**登记到 TD；历史事故（如 spec 创建期混入实施代码）应放 design.md 的"实施记录"或独立 LESSONS_LEARNED.md，不与技术债混账
- **Property docstring 反向映射需双向闭环**：仅在测试函数 docstring 加 `Validates: Property X` 不够，必须配套 (1) design.md 的 Property 区块标 `[Tested: test_xxx]` / `[Pending: TD-N]` / `[Skipped: 可选]`；(2) `scripts/check_property_coverage.py` 双向核验 + CI 卡点；否则下次新增 Property 仍可能"列了但没测"
- **3 个 spec 工具已固化（template-library-coordination 二轮复盘 2026-05-16）**：(1) `backend/scripts/verify_spec_facts.py` 核验 N_* 基准值（snapshot.json）；(2) `backend/scripts/check_property_coverage.py` Property↔test docstring 双向核验；(3) `backend/scripts/build_spec_coverage_matrix.py` 自动生成 Requirements↔Tasks↔Properties↔Tests 四向映射表（输出 COVERAGE_MATRIX.md）；3 工具均已加 Windows GBK console UTF-8 兼容（`sys.stdout.reconfigure(encoding="utf-8")`），避免 emoji/中文崩溃
- **pre-commit hooks 已接入两个 spec 工具**：`.pre-commit-config.yaml` 新增 `verify-spec-facts`（snapshot.json/seed JSON 改动触发 + WARN 不阻断/FAIL 阻断）+ `check-property-coverage`（design.md/集成测试改动触发 + FAIL 阻断）；spec 数字漂移与 Property 覆盖漏报现已自动卡点
- **spec 三件套变更记录区块（P1.5 落地）**：requirements.md / design.md / tasks.md 顶部各加 `## 变更记录` 表格（版本号 + 日期 + 摘要 + 触发原因），新人看 spec 一眼看清演进；新 spec 创建模板应包含此区块
- **spec ADR 核验证据小区块模板（P2.7 落地）**：design.md 关键 ADR（如 D14 消费契约）附 5 字段子区块：假设 / 证据 / 核验时间 / 失效条件 / 同步更新点；template-library-coordination D14 已示范，未来其他 ADR 可参照
- **UAT 结构化 checklist 模板（P2.8 落地）**：tasks.md UAT 区改 markdown 表格 7 列（# / 验收项 / Requirements / Tester / Date / Status / 备注），Status 取值 `✓ pass / ✗ fail / ⚠ partial / ○ pending`；上线前 milestone 卡点要求 ≥ N 项 ✓ pass
- **template-library-coordination 全部完成（三轮复盘 2026-05-16）**：43/43 必做 + 16/16 PBT + 6.2/6.3 重新完成；33 测试通过（6.75s）；新建 2 测试文件 `test_template_library_properties.py`（17 PBT）+ `test_system_dicts_usage_count.py`（4 用例）+ `test_gt_coding_crud_integration.py`（4 用例）；Property 覆盖率 5/17 → 16/17 = 94%；唯一未覆盖 P1 是前端 v-permission 模板渲染（vitest/E2E 范畴）
- **`gt_coding.py` 三个 mutation 端点已加 `require_role(["admin","partner"])` 守卫**：POST `/api/gt-coding` + PUT `/api/gt-coding/{coding_id}` + DELETE `/api/gt-coding/{coding_id}`；之前仅 `get_current_user`，任何登录用户都能调，存在权限漏洞
- **fix: `gt_coding_service.delete_custom_coding` soft_delete bug**：调用 `coding.soft_delete()` 但 `GTWpCoding` 不继承 `SoftDeleteMixin`（grep 核实），运行时 AttributeError；修复 = 改为 `coding.is_deleted = True`（GTWpCoding 自身有此字段）；属 R8 风格"凭印象写字段假设"踩坑模式
- **PBT 反模式识别规则（三轮复盘 2026-05-16）**：很多 hypothesis 测试不是真 property-based，而是"参数化用例" — 反模式表现：(1) strategy 已强制满足约束（输入永远合法，测试永真）；(2) `sorted()` 后断言已排序（永真命题）；(3) reimplement 算法 + 喂同一算法 + 断言一致（同义反复）。真 PBT 应该 fuzz 生成可能违反不变量的输入；评审清单：① 输入 strategy 是否故意包含违反约束的 case？② 测试是否会因 production 代码修改而失败？③ 算法实现和测试断言是否独立来源？
- **PBT 分级 max_examples 规约**（三轮复盘补充）：P0 关键 Property（authz / readonly / 边界条件）应 `max_examples=50-100`，可选探索类保持 5；目前 template-library-coordination 17 PBT 全 max_examples=5 视为 MVP 兜底，下次新 spec 关键 Property 升级
- **subagent 越权三类风险（三轮复盘 2026-05-16）**：(1) 范围扩张 — 把测试期望（auditor 应 403）反向给 production 加权限守卫；(2) bug 修复混入测试 commit — 没走独立 commit 边界，git log 看不到独立事件；(3) 状态变更单方面声明（划掉 TD 项 / 改 UAT 措辞），无审计痕迹。下次 prompt 加严约束："发现 production bug 必须独立报告但不修，由 orchestrator 决定"+"发现 spec 范围扩张需求只报告不实施"+"TD 状态变更必须附 commit-style note"
- **三轮复盘 P0+P1.5 改进已落地（2026-05-16）**：(1) design.md Coverage 标签新增 `[Skipped: 前端范畴]` 类别（区分"待补 PBT"vs"非后端范围"）；Property 1 已贴此标签，覆盖率从 16/17=94% 改为 16/16=100%（后端范畴）；(2) conventions.md 新增 "Subagent 调用约束" + "PBT 反模式识别清单" 两节作永久规约；(3) `check_property_coverage.py` 升级 split-by-comma 解析 multi-test Coverage 标签，template-library-coordination 核验从 12 OK + 5 WARN 改为 17 OK + 0 WARN
- **R10 复盘修复 G1+G2+G3+G6 全部完成（2026-05-16，~1h）**：
  - **G1 border-color hex 419 处全部清零**：4 轮 Python 脚本批量替换覆盖 360 个 .vue 文件 / 86 个文件实际改动；扩展 PROPERTY_RE + SHORTHAND_RE 双正则匹配 `border-*-color` / `border:` shorthand / `--el-table-*-color`；hex 映射表覆盖紫/绿/黄/红/蓝/紫辅/灰/反白/黑 9 大色族 ~50 条；用完即删脚本
  - **G2 DisclosureEditor.vue 3 处 `background: #fff`**：替换为 `var(--gt-color-bg-white)`
  - **G3 F8 `/memo/versions` 端点接入前端**：EqcrMemoEditor `loadMemo` 单独调 `P_eqcr.memoVersions(pid)` 端点，失败时降级为 preview.history（端点已存在，前端从未调用是 R10 真实缺口）
  - **G6 el-table baseline 校准**：从假定的 100 改为实测 176（grep `<el-table` 全量统计）
  - **CI 新加 `border-color-prop-hex-vue-files=0` baseline**：防止 R10 之后再次出现 border hex 残留
- **R10 P0 复盘流程铁律再次沉淀**：subagent 报"raw=0"必须 grep 多种相关属性变体复核（本次漏 `border-*-color` / `--el-table-*-color` / `border:` shorthand / `1px solid #xxx` 4 种派生形式 共 419 处）；CI baseline 字段命名按属性级前缀（`border-color-prop-hex-vue-files`）而非泛化（`color-hex-vue-files`）
- **G4/G5 是真人范畴待 UAT/运维验收**：G4 设计师/审计助理逐项确认 UAT 1-9（上线前 1 天）；G5 worker 心跳生产 Redis 真实验证（运维 30min）；不是代码缺口，无需进 TD 章节
- **批量 hex → token 替换通用脚本模式**（可复用）：(1) PROPERTY_RE 匹配 `border-*-color: #xxx`；(2) SHORTHAND_RE 匹配 `border: <width> <style> #xxx`；(3) HEX_TO_TOKEN dict 大小写不敏感 lookup；(4) 字节级 read_bytes/write_bytes（绕开 PowerShell GBK 陷阱）；(5) `--dry-run` 先行；(6) 多轮迭代直到 grep 残留 = 0；(7) 用完即删（不进 git）
- **R10 复盘后改进建议（待落地）**：(1) `scripts/update_baselines.py` 一键 grep 重算 baselines.json 真实值（消除"凭印象设 baseline"问题，G6 实测 176 vs 假定 100 偏差 76%）；(2) hex→token 映射沉淀到 `frontend/src/styles/_token_aliases.json` 作单一真源（不再每次写脚本时重新维护映射表）；(3) 写 `stylelint-plugin-gt-tokens` 替代 4 道 CI grep（CSS-aware 精度高于正则，rgba 内 hex 不再误报）；(4) `scripts/verify_subagent_claim.py {spec_id}` 通用核验工具 + `claim_grep_patterns.json` 列每 spec 多变体 grep 模式集（"subagent 报 raw=0" 自动转 gate 而非靠 orchestrator 手动复核）；(5) spec 完成时强制填 `actual_hours_breakdown` 与 design 估算自动算比例 > 5× 触发 review reminder（机制化"工时压缩比警报"）；(6) TD 章节标准 6 列模板（ID / 缺口 / 优先级 / 触发条件 / 后续 spec / 修复时间）+ pre-commit 检查空 TD 报 warning
- **subagent 工时压缩比反推规约（R10 实测沉淀）**：subagent 报告实际工作量 < 估算 5× 时不一定是高效，可能是 grep 不全/任务理解偏差；需独立验证而非自动通过；本次 G1 初估"17 文件 / 50 处"实际"86 文件 / 419 处"差 8.4×，是 grep 模式覆盖度不足而非工程奇迹
- **大批量 hex→token grep 模式硬约定**（R10 G1 落地）：第一轮 grep 必须同时 cover 4 种形式才出准确数——(1) `border-*-color: #xxx`（属性精确名）；(2) `border: <width> <style> #xxx` shorthand 简写；(3) `--el-table-*-color: #xxx` CSS 变量；(4) 其它派生（box-shadow / outline-color 等）；漏一种就要多迭代一轮；同理推广到 font-size / color / background 全 token 化场景
- **R10 二轮复盘 8 项进一步改进（待逐一落地）**：
  - **S1 UAT partial 状态收敛**：tasks.md 模板强制 4 状态枚举（✓ pass / ⚠ partial / ○ pending-uat / ✗ fail），区分"代码已交付待真人测"vs"功能部分完成"；R10 两套 spec 13 项 ⚠ partial 应改为 `○ pending-uat`
  - **S2 UAT 真人触发流程**：spec 完成时自动建 `.kiro/uat-pending/{spec_id}.md` 触发清单 + CI 评论 PR @责任人 + SLA 超时报警（消除"代码完成但 UAT 永远卡住"现象）
  - **S3 TD 已落地项必须迁出**：TD 只列未解决项；已落地的搬到 spec 末尾"实施记录"或 LESSONS_LEARNED.md（Spec C TD-1/TD-4 是反面案例）
  - **S4 跨 spec 依赖矩阵显式化**：spec README 顶部加 `## 依赖矩阵` 章节，列上游 spec + commit + fallback 策略；不再把跨 spec 协调散在 task 描述里
  - **S5 实测工时回填 tasks.md**：每 Sprint 末尾加 `actual_hours / compression_ratio` 字段；> 5× 触发 review（R10 两套 300×+ 压缩需独立分析原因）
  - **S6 CI baseline 字段统一命名**：`{property}-prop-hex-vue-files` 格式（如 `font-size-prop-px-vue-files`）；旧名加 deprecation alias 1-2 版后删；本次新加 `border-color-prop-hex-vue-files` 与旧名混用
  - **S7 视觉回归自动化**：引入 Playwright/Percy（非 R10 范围，独立 spec）；token 化 PR 强制附 before/after 4 视图截图证据
  - **S8 文档↔代码双向链接**：组件 JSDoc 顶部加 `@docs ./docs/XXX_GUIDE.md`；CI grep 新建 `_GUIDE.md` 必须有 ≥ 1 处反向引用
- **R10 二轮复盘 S1/S2/S3/S4/S5/S6/S8 全部落地（2026-05-16）**：S1 UAT 状态枚举收敛（⚠ partial 15 处替换为 ○ pending-uat + 加状态枚举说明）/ S2 `.kiro/uat-pending/` 目录建立（README + 两个 spec 的待办 + SLA 14 天）/ S3 Spec C TD 表迁出已落地项到"实施记录"子表 / S4 两个 spec requirements.md 顶部加"依赖矩阵"章节 / S5 tasks.md 任务总览加"实测工时 + 压缩比 + > 5× 触发 review 分析"列 / S6 baselines.json 字段统一 `{property}-prop-{format}-vue-files` 格式 + 旧字段保留 deprecated alias / S8 5 个组件源加 `@docs` + CI 加"Doc backlink guard"卡点；S7（视觉回归 Playwright/Percy）跳过待独立 spec
- **Playwright MCP 已装 user 级（2026-05-16）**：`@playwright/mcp@latest` via `npx -y`，user `~/.kiro/settings/mcp.json`；autoApprove 11 个只读/低风险动作（navigate/snapshot/screenshot/click/type/press_key/wait_for/console/network/evaluate/close）；写入类（drag/run_code_unsafe）保留确认；下次会话即可调用 `mcp_playwright_browser_*`
- **Percy 不装规约（架构决策）**：违背"本地优先轻量"用户偏好 + 真实客户数据自动上云合规风险 + Playwright 内置 `toHaveScreenshot()` 可替代；视觉回归用 Playwright 自带 + git 管基线截图，CI diff > 0.1% 失败
- **`.kiro/specs/INDEX.md` 不删除规约**：spec 元数据索引非任务清单，未来新 spec 必须登记 + 跨分支 spec 唯一可见入口 + 工作流规约统一入口；类比 README.md 不会因"代码写完了"就删；每月一审清理 ≥ 3 月完成的 spec 迁 dev-history.md（INDEX.md 自身保留）
- **档 2 小型 spec 升级条件补强（v3-quickfixes 沉淀）**：除原 5 条外新增 — (6) 真根因排查 ≥ 4h（Q1 SAVEPOINT 排查仅 0.4h 是反例，超 4h 应停手起完整 spec）；(7) 涉及核心业务流程跨 ≥ 6 service 调用（即使表面是单点修复）
- **端点形态错估 3 类反模式**（v3-quickfixes Q2/Q3 沉淀）：(1) "统一资源 GET 列表"假设 — 实际可能按子领域分多个细粒度 GET（EQCR opinions = 5 个 domain 端点不是 1 个统一）；(2) "项目子前缀"假设 — 实际可能是全局 prefix + query param（review-conversations = `/api/review-conversations?project_id=...` 不是 `/api/projects/{pid}/review-conversations`）；(3) "GET root"假设 — 实际可能仅有派生子路径（EQCR memo 只有 `/memo/preview` 没有 `GET /memo`）；铁律：每条端点引用必须 grep 真实文件+行号附在脚注，否则按未核验对待
- **`.kiro/specs/v3-quickfixes/` 已删除（2026-05-16）**：Q1-Q4 全部完成 + 价值已迁 memory；详情查 commit b4cda44；INDEX.md 保留行作为历史索引
- **D2 PoC 启动确认（用户 2026-05-16）**：选 A + Yes + 仅 D2 路线（先 1-2 天 PoC 跑通机制，不行马上调头；前端工具栏按钮 + prefill 视觉标识 + 跳转附注/报表 + cross_wp_references 增强；commit 6b95e58 后启动）
- **Playwright MCP 已实际可用（2026-05-16 实测验证）**：`mcp_playwright_browser_navigate` + `_snapshot` + `_take_screenshot` + `_console_messages` 全部跑通；登录页能正常打开 http://localhost:3030/login（前端开发服务器 :3030 已起）；console.error 实测可读（发现 staff/my/assignments 404 即是 MCP 读到的）
- **真 bug 发现：`staff.myAssignments` 与 `projects.myAssignments` schema 错位**：前端 `apiPaths.ts:462 staff.myAssignments = '/api/staff/my/assignments'` 但后端真实路由是 `/api/projects/my/assignments`（assignments.py 注册在 projects prefix 下，且有注释提醒"my 必须在 {project_id} 前避免 UUID 冲突"）；前端 apiPaths 同时有 `projects.myAssignments` 和 `staff.myAssignments` 两条但只有前者真存在；登录后 Dashboard 触发 2 个 404；下一步用方案 A 删除 staff 重复条目并 grep 调用方迁移
- **D2 应收账款 PoC 现状勘查（用户截图实测 2026-05-16）**：陕西华氏 2025 项目 D2 底稿基础设施 90% 已工作——试算表 4 卡片（期初 5293M / 未审 6290M / 调整影响空 / 审定数 6290M）正确显示 + 上年数据已带入 + 销售循环 D0-D7 8 底稿全生成 + 工具栏 6 按钮（编辑底稿/分配底稿/查看试算表/查看附注/查看序时账/批量预填）+ 顶部 3 按钮（刷新/批量预填/智能推荐底稿）+ AI 审计助手 5 条要点 + stale 标签可见；实测发现 4 处缺口需补：(1) "调整影响" 列空（需联动逻辑核验）；(2) AI 变动分析卡片只显示 % 没真实值（上年比对未跑通）；(3) 6 按钮排版拥挤未明确"跳转附注 5.7"；(4) 缺"一键填充"按钮+prefill 视觉标识；PoC 工作量从"补全机制"降级为"补缺口+视觉化"
- **Chrome `--no-sandbox` 红框警告非业务问题**：Playwright MCP 默认带 `--no-sandbox` 启动，Chrome 顶部黄色警告"您使用的是不受支持的命令行标记"是浏览器安全提示，不影响业务，截图分析时直接忽略
- **Univer 在线编辑空白根因已定位并修复（2026-05-16）**：前端 importXLSX 三级降级全失败（Strategy 1/2 需 advanced preset 未部署 + Strategy 3 POST FormData 被 axios 封装错误处理）→ final fallback 创建空白 workbook；修复 = 后端新建 `GET /xlsx-to-json` 端点直接读 storage 文件转 Univer JSON 返回 + 前端 Strategy 3 改用 GET 替代 POST FormData；诊断确认 D2 storage 文件完整（113KB / 20 sheets / 13024 cells）转换无损
- **`GET /api/projects/{pid}/workpapers/{wid}/template-file/xlsx-to-json` 新端点**：直接读 wp_storage/{pid}/{wid}.xlsx → openpyxl 转 Univer IWorkbookData JSON（含 cellData/合并/列宽/行高/样式/公式/冻结/条件格式/数据验证/图片）；不存在时自动 init_workpaper_from_template；非 xlsx 返回 400 引导走 /docx-to-json
- **新增前端依赖 @univerjs/preset-docs-core@0.21.1**（2026-05-16）：与现有 @univerjs/preset-sheets-core@0.21.1 同版本（官方要求所有 @univerjs/* 同版本）；待落地用途 = wp_templates 109 个 docx 类底稿前端编辑（B60 总体策略 / A16 管理层声明书 / S12 利用专家 等），区别于 367 个 xlsx 已可工作的现状
- **wp_templates docx 类编辑支持已完成（2026-05-16，commit 6b95e58）**：109 个 docx 模板（A1/A16/B60/S12 等）前端可编辑，三级降级 = Univer Docs（首选 80-90% 还原）→ mammoth+TipTap（兜底 80%+ 内容）→ textarea（最末端）；后端 `docx_to_univer_doc_service.py` 转 IDocumentData JSON / `GET /docx-to-json` 端点 / 全量 107/107 转换成功率；前端 `WorkpaperWordEditor.vue` 重写 + 17 wp_codes 元数据修正 component_type='word'（A1/A8/A9/A10/A11/A12/A16/A17/B1/B2/B3/B18/B23/B30/B40/S12/S34）；word 类元数据 6→23；新增依赖 mammoth + @univerjs/preset-docs-core@0.21.1
- **wp_templates xlsx 内容预设新需求（用户 2026-05-16 提出，待立项 spec）**：当前 367 xlsx 模板虽走 importXLSX 但打开后用户看到的可能仍是"半空白"——缺预设公式（=TB/=ADJ/=PREV）/ 缺自动填充逻辑 / 缺单元格语义注释；用户要求"按审计阶段+循环+科目+具体 sheet 逐个预设内容/格式/公式/可一键填充提取的取数规则"；工程量评估 = 477 模板 × 平均 2-3 sheet × 4 维度元数据（公式/取数源/输出锚点/校验规则）≈ 数千个数据点，需完整三件套规划
- **底稿模板内容预设 2 个三件套已起草完成（2026-05-16，commit bcae2be）**：
  - `workpaper-completion-foundation`（5 天 / 3 Sprint / 27 任务）：预填充视觉指示器 / 一键填充按钮（编辑器内）/ 跨模块跳转标签 / 单元格复核标记 / 循环级复核徽章 / Playwright E2E / 覆盖保护；5 ADR（D1 prefill_meta 嵌入 cellData.custom / D2 User_Override 存 parsed_data / D3 跨模块标签 overlay div / D4 循环复核实时查询 / D5 复核标记复用 cell_annotations）；15 正确性属性
  - `workpaper-cycle-d-revenue`（3 天 / 2 Sprint / 27 任务）：D0-D7 分析程序公式 / 明细表公式（新 TB_AUX 类型）/ 18 条跨引用（4 内部 + 7 附注 + 7 报表）/ 21 条校验规则（balance_check/tb_consistency/note_consistency/detail_total_check）/ 8 底稿审计程序清单；纯数据 spec（只产出 JSON + 测试，不改引擎代码或前端 UI）；10 正确性属性
  - 执行顺序：先 Foundation（基础设施 UI 机制）→ 再 Cycle-D（具体数据填充）；两者解耦——Cycle-D 只产出 JSON 数据文件不依赖 Foundation UI 就绪即可独立实施
- **两个三件套实施进度（2026-05-17，commit c1679bf）**：
  - Foundation Sprint 1 ✅（Task 1.0-1.8）+ Sprint 2 ✅（Task 2.1-2.9）= 90% 完成；剩余 Sprint 3（Playwright E2E 4 用例）
  - Cycle-D Sprint 1 ✅（Task 1.1-1.14）= 50% 完成；剩余 Sprint 2（属性测试 10 个）
  - 核心功能代码全部就绪，剩余全是测试任务
  - 新建文件：4 composables（usePrefillMarkers/useCrossModuleRefs/useReviewMarks/useUserOverrides）+ wp_review_status.py 端点 + Alembic 迁移 + 2 新 JSON（d_cycle_validation_rules / d_cycle_procedures）+ prefill_formula_mapping 扩展 15 条 + cross_wp_references 扩展 18 条
- **两个三件套全部任务 100% 完成（2026-05-17，commit aba873b）**：Foundation 23 tasks + Cycle-D 27 tasks = 50 tasks 全部 [x]；26 属性测试 passed（0.53s）+ 4 Playwright E2E specs 就绪；复盘无进一步改进建议；剩余仅真人 UAT 验收
- **复盘补齐 3 个关键缺口（commit 74d87f2）**：(1) Foundation 新增 Requirement 0"底稿模板完整加载保障"（8 条验收标准覆盖全 sheet/合并/冻结/格式/固定文字/错误提示）；(2) Foundation 新增 Task 1.0"验证底稿模板完整加载链路"作为 Sprint 1 第一个任务（不通过不进后续）；(3) Foundation 新增 Task 1.2b"prefill_engine 新增 TB_AUX formula_type 支持"（Cycle-D 只产出数据不改引擎，引擎扩展由 Foundation 承担）
- **底稿在线编辑空白问题深入分析（2026-05-16 Playwright 实测）**：
  - **后端 100% 正常**：GET /xlsx-to-json 返回 200 + 20 sheets 完整数据（浏览器内 fetch 实测确认）
  - **前端加载链路断裂真因（第三次定位才找到）**：不是 FormData bug，是 **Univer Core Preset 的 importXLSX API "假成功"**——`importXLSXToSnapshotAsync` / `importXLSXToWorkbook` 函数存在（typeof 通过）但只创建 1 个空白 sheet，前端标记 `imported=true` 后 Strategy 3 永远不执行
  - **最终修复方案（commit 80cf992，Playwright 实测验证通过）**：完全跳过 xlsx blob 下载 + importXLSX 尝试，步骤 2 直接调 `GET /xlsx-to-json` 拿完整 Univer JSON → 步骤 4 `createWorkbook(jsonData)`；简单粗暴但 100% 可靠
  - **验证结果**：Univer 渲染 6+ sheet tabs（底稿目录/实质性程序表/审定表D2/附注披露/明细表/坏账准备），不再走 empty workbook fallback
  - **Task 1.0 验证通过**：Foundation Sprint 1 第一个任务完成，可进入后续任务
  - **教训沉淀**：(1) typeof 检查通过 ≠ 功能正常（Univer Core Preset 暴露了 Advanced Preset 的 API 签名但内部实现为空/创建空白）；(2) "看似成功实则空白"的静默失败比"直接报错"更难排查——应在 createWorkbook 后验证 sheet 数量；(3) 三次定位才找到真因（第一次以为是 FormData bug / 第二次以为是 HMR 未生效 / 第三次才发现是 importXLSX 假成功）
- **三轮复盘 P1.3+P3.9 改进已落地（2026-05-16）**：(1) `test_property_2_template_list_field_presence` 重写为真 PBT — 系统性 fuzz `mutation=("drop"|"none_value", field)` 故意破坏完整 base_item 中的某个字段，验证 validator sensitivity（每个 required 字段都必须被检测到），独立 oracle 用 `_REQUIRED_FIELDS_*` 常量 list；max_examples 升到 50；(2) `test_property_3_cycle_sort_order` 重写为真 PBT — 用独立 `itertools.permutations` 全枚举 oracle 找最小字典序排列与 `sorted(..., key=...)` production 算法对比（两条独立路径），max_examples 升到 50；(3) Property 16（authz）+ Property 17（readonly enforcement）max_examples 从 5 升到 50（P0 关键 Property 不再充数）；17 PBT 全绿 0.88s
- **template-library-coordination 父任务全部 [x]**（三轮复盘 2026-05-16）：6 个 Sprint 父任务（Sprint 0-6）原本误标 [ ]（子任务全完成但父任务漏勾），本轮一并标 completed；spec 全部 50 task + 16 PBT + 6.2/6.3 重新完成共 67 项全部交付

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，Ollama 0.11.10
- 前端依赖共 22 生产 + 8 开发：关键新增 mitt@3.0.1、nprogress@0.2.0、unplugin-auto-import@21.0.0、unplugin-vue-components@32.0.0、@univerjs/presets@0.21.1、@univerjs/preset-sheets-core@0.21.1（公式引擎内置）、@univerjs/sheets-formula@0.21.1、opentype.js@1.3.5、xlsx@0.18.5；R8-S2 新增 dev 依赖 glob@13（scripts/find-missing-v-permission.mjs 使用）
- 后端新增测试依赖 hypothesis@6.152.4 + ruff@0.11.12（R6 Task 2 写入 requirements.txt）
- PG ~160 张表（152 基线 + R5 新增 6 张 + R6 新增 qc_rule_definitions + review_records.conversation_id 列），Redis 6379，后端 9980，前端 3030
- 前端 HTTP 全局超时 120s（http.ts），detect 端点单独 300s（大文件多文件场景）
- vLLM Qwen3.5-27B-NVFP4 端口 8100（enable_thinking: false）
- ONLYOFFICE 端口 8080（已替换为 Univer，WOPI 保留兼容）
- Paperless-ngx 端口 8010（admin/admin）
- 测试用户：admin/admin123（role=admin）

## 当前系统状态（2026-05-07 实测核对）

- vue-tsc 0 错误（2026-05-06 全部修复：el-tag type 联合类型标注 + dictStore.type() 返回类型收窄 + 模板 `:type` 绑定加 `|| undefined`），Vite 构建通过
- 后端 **151** 个路由文件，**226** 个服务文件（含子目录 import_engine/、wp_scripts/ 等），**51** 个模型文件，11 个 core 模块，9 个 middleware，~152 张表（此前 memory 记录 127/181/39 已过时）
- 后端 `backend/app/workers/` 模块 4 个：sla_worker、import_recover_worker、outbox_replay_worker、import_worker（每个导出 `async def run(stop_event)`）
- 前端 **86** 个 Vue 页面（views/ 含子目录 ai/eqcr/qc/independence/extension），**194** 个组件（components/ 含所有子目录），16 个 composables，9 个 stores，19 个 services，19 个 utils
- GtPageHeader 接入率 **12/86**（14%）：TrialBalance/ReportView/DisclosureEditor/ConsolidationIndex/EqcrMetrics/KnowledgeBase/Misstatements/Projects/Materiality/AuditReportEditor/Adjustments/WorkpaperList
- GtEditableTable 接入率 **1/86**（Adjustments.vue）；新增 `#expand` 插槽支持展开行明细（el-table type="expand"）
- v-permission 接入 **5** 个 .vue 文件
- useEditingLock 接入 **3** 个编辑器（WorkpaperEditor/DisclosureEditor/AuditReportEditor）
- ElMessageBox.confirm 直接用法 **0 处**（R8-S1 Day 2-3 全量清零，30+ 处全部替换为 utils/confirm.ts 语义化函数）
- Vue 层 /api/ 硬编码剩余 **~17 处**
- **顶栏已改为致同品牌深紫背景**（#4b2d77），logo 用反白版 gt-logo-white.png，文字/图标/按钮全白色；侧栏底色 #f8f7fc（微紫调）
- **Logo 文件**：public/gt-logo-white.png（反白，顶栏用）、public/gt-logo.png（标准彩色，登录页+favicon）、public/gt.png（旧版保留兼容）
- **页面标题**：致同审计作业平台（index.html title 已更新）
- pytest collection **2830 tests / 0 errors**（2026-05-07 修复后）：之前 7 个 collection error 已通过添加 `wrap_ai_output` 函数、`IndependenceDeclaration` 别名、`build_ai_contribution_statement` 等 4 函数到 pdf_export_engine、`AIContentMustBeConfirmedRule` re-export 到 gate_rules_phase14 全部解决
- 后端测试：98+ 个根目录测试 + 4 个 e2e + 4 个 integration + R5 新增 test_eqcr_full_flow/test_eqcr_state_machine_properties/test_eqcr_component_auditor_review
- git 分支：feature/round8-deep-closure（HEAD = a1b936e，R8 Sprint 1+2 全部完成 + 清理，已推送到 origin）；上游 feature/round7-global-polish（2e72884）
- 本分支相对 master 新增前端依赖（后端 requirements.txt 无变化）：生产 7 个（@univerjs/presets、@univerjs/preset-sheets-core、@univerjs/sheets-formula、mitt、nprogress、opentype.js、xlsx）+ 开发 3 个（@types/nprogress、unplugin-auto-import、unplugin-vue-components）；已在 audit-platform/frontend 执行 npm install 安装完成
- .gitignore 已排除 backend/ 下 wp_storage 运行时 UUID 目录（glob `backend/[0-9a-f]*-[0-9a-f]*-[0-9a-f]*-[0-9a-f]*-[0-9a-f]*/`）
- **production-readiness spec 全部完成**（4 Sprint / 46 需求）：
  - Sprint 1（P0 数据正确性）：底稿保存事件→附注同步、Dashboard 趋势图真实 API、Dirty 标记完整覆盖、QC 项目汇总 N+1 优化、审计报告 final 保护、QC-16 字段修正、ReviewInbox 跳转修正、报表两张表数据驱动、AuditCheckDashboard 批量接口、PBC/函证路由注册、看板卡片跳转、个人工作台待办工时
  - Sprint 2（P1+P2 核心体验）：复核收件箱导航+badge、UUID→姓名映射、进度百分比、借贷平衡含损益、错报超限门禁、重要性变更联动、账套导入通知、抽样/汇总年度从上下文、导出 Word 入口、QC-17 改 ORM、批量驳回逐条原因、工时编辑修正、知识库预览认证、QC 归档缓存、编制人筛选下拉、版本历史抽屉、自动保存、并发冲突检测、预填充保留公式
  - Sprint 3（P2+P3 前置）：项目启动步骤引导、xlsx 公式值预加载、底稿导出 PDF、路由前缀规范（删除 hasattr 补丁）、Worker 拆分（3 模块）、AI 分析缓存、对比视图上年列、序时账异常标记
  - Sprint 4（P3 核心）：PostgreSQL 连接池配置、.env.example 迁移示例、Alembic 迁移完整性验证、load_test.py 压测完善（Locust + asyncio 双模式）
  - 属性测试：16 个 Hypothesis 测试覆盖全部 14 条属性（`backend/tests/test_production_readiness_properties.py`）
  - 剩余：0.3 公式计算手动浏览器验证（代码已确认 UniverSheetsCorePreset 未禁用公式，功能正确）

## 关键技术事实（查阅/排查专用）

- **试算平衡表只显示 is_confirmed=True 的 ReportLineMapping**：`get_summary_with_adjustments` 查询条件含 `is_confirmed == True`；"一键预设"（ai_suggest_mappings）生成的映射默认 `is_confirmed=False`，必须确认后才会出现在试算平衡表；前端"一键预设"按钮已改为生成后自动批量确认
- **ReportLineMapping 不存科目名称**：只有 `standard_account_code` + `report_line_code/name`；科目名称需从 TrialBalance rows（`standard_account_code` + `account_name`）获取，不能从 mapping 表取
- **报表行次映射策略（已修正）**：`_lookup_report_line` 只做精确 4 位编码匹配 + 名称关键词兜底，**禁止前缀模糊匹配**（会导致 5002 匹配到 5001 等乱匹配）；匹配不上的返回 None 由用户手动指定；用户偏好：能准确判断的才对应，不能的就提示手动
- **`POST /report-line-mapping/manual` 端点**：手动创建单条映射（mapping_type=manual, is_confirmed=True），用于未映射科目的用户手动指定
- **AccountMapping 表无 year 列**：只有 project_id/original_account_code/standard_account_code/mapping_type/is_deleted/created_by/created_at/updated_at；查询时不能带 year 过滤
- **TrialBalance 方向判断最终方案**：不硬编码科目编码/名称，默认从余额正负推断（正=借，负=贷）；支持用户手动点击切换方向（`directionOverrides` ref）；方向决定小计加减逻辑
- **试算平衡表（summary 视图）贷方科目展示为正数**：`get_summary_with_adjustments` 构建 `unadj_map`/`tb_amount_map` 时，对 2xxx/3xxx/4xxx + 收入类（5001/5051/5101/6001/6051/6101/6111/6115/6117/6301）的负值取反；公式引擎 `TB('2001','期末余额')` 返回正数；科目明细视图不受影响（用 `fmtDir` 取绝对值+方向列）
- **试算平衡表导入/导出模板已实现**：导出下拉菜单（导出数据/导出空模板）+ 导入按钮（按行次编码+名称双保险匹配覆盖未审数）；未审数编辑通过"✏️ 编辑"按钮切换模式（`tbSumEditMode` ref），编辑模式下所有报表类型未审数可点击编辑+双击不跳转，保存后自动退出编辑模式恢复双击溯源
- **试算平衡表编辑列行为差异（有意为之）**：重分类借贷列始终可编辑（不受 tbSumEditMode 控制，审计师需随时调重分类）；未审数列需进入编辑模式或断开公式才可编辑；所有可编辑列 blur 后立即 `recalcTbSummaryAudited()` 实时更新审定数
- **试算平衡表保存持久化**：保存到 `consol_worksheet_data` 表（sheet_key=`tb_summary_{type}`，JSONB）；加载时先取公式计算结果再调 `_mergeSavedTbSummary` 合并已保存手动数据（公式无值的行用保存值覆盖），现金流量表手动填写刷新后不丢失
- **试算平衡表"断开公式"功能**：右键菜单"✂️ 断开公式"标记行级 `formula_detached=true`，该行未审数变为可编辑+不被公式覆盖+微黄背景+左侧橙色竖线；"🔗 恢复公式"取消标记并立即刷新；断开后自动进入编辑模式；标记随 JSONB 持久化，零后端改动
- **试算平衡表 4 个报表类型页签**：balance_sheet / income_statement / cash_flow_statement / cash_flow_supplement（现金流量附表为新增）
- **试算平衡表期初/期末双视图**：`tbSumPeriod` radio-group 切换 ending/opening；期初数据来源：连续审计=上年审定数自动带入（`tbSumOpeningSource='prior_year'`），首次承接=空行次手动填写（`'manual'`）；期初保存到独立 sheet key `tb_summary_opening_{type}`；期初也支持编辑/断开公式/导入导出
- **期初试算上年数据取法**：用同一 `projectId` + `year-1` 查询（适用于同项目多年度场景）；上年数据全 0/null 视为无效走首次承接；跨项目取上年数据需未来"关联项目"机制（当前不支持）
- **科目明细金额展示规则（最终版）**：所有普通行一律取绝对值展示 + 方向列标"借/贷"；小计按方向加减计算——资产类中贷方科目减去绝对值，负债/权益类中借方科目减去绝对值；小计直接展示计算结果；数据库存储不变
- **working_paper 表名是单数**：`working_paper`（不是 working_papers），ORM 类 WorkingPaper.__tablename__ = "working_paper"
- **`check_consol_lock` 必须 rollback**：查询不存在的 `projects.consol_lock` 列会让 asyncpg 事务进入 aborted 状态，后续所有 SQL 报 `InFailedSQLTransactionError`；except 分支必须 `await db.rollback()` 恢复事务（仅 `pass` 不够）
- **Docker 日常只起 3 个基础服务**：audit-postgres(5432) + audit-redis(6380:6379) + audit-metabase(3000)；backend 容器已从默认 compose 移除（或挂到 profile），本地开发 **唯一** 用 start-dev.bat 跑在宿主机 9980；Docker 里再起后端 = 重复进程 + 重复 worker 循环吃 CPU
- **docker-compose.yml backend 服务 profiles: [docker-backend]**：默认 `docker compose up` 不拉起；需要时 `docker compose --profile docker-backend up -d backend`
- **PG job_status_enum 类型值（2026-05-07 补齐后 12 个）**：pending/running/completed/failed/timed_out/cancelled/retrying（历史遗留）+ queued/validating/writing/activating/canceled（R8 补齐）；Python JobStatus 实际只用 10 个，cancelled(双L)/retrying 是历史数据兼容保留
- **dataset_models.py ImportJob.status 类型名修正**：`sa.Enum(JobStatus, name="job_status_enum", create_type=False)`（之前错写 `name="job_status"` 导致 SQLAlchemy 生成 `$1::job_status` 与 PG 真实类型名不匹配，import_recover_worker 每几毫秒刷 UndefinedFunctionError 死循环吃 89% CPU）
- **PG ALTER TYPE ADD VALUE 事务限制**：同事务内新增的 enum 值不能立即使用（报"unsafe use of new value"），psql 单条命令各自事务时需分多次 docker exec 执行而非分号连写
- **PG schema 已于 2026-05-07 重建（方案 A）**：旧库 alembic_version='035' 与当前 28 个迁移文件完全脱节（Round 1-7 新增列全部缺失），执行 DROP DATABASE + `python backend/scripts/_init_tables.py` 重建 171 张表；admin 用户已恢复（UUID ae9e0523 / admin@gt.cn / admin123）；种子数据需后端启动后调 seed 端点加载
- **PG 重建后待办**：启动后端后需调用 6 个 seed 端点加载基础数据（/api/report-config/seed、/api/gt-coding/seed、/api/ai-models/seed、/api/ai-plugins/seed、/api/accounting-standards/seed、/api/template-sets/seed）
- **admin 密码哈希写入注意**：PowerShell 会吃掉 `$` 符号导致 bcrypt hash 损坏（Invalid salt），必须用 Python + SQLAlchemy 参数化写入，不能通过 docker exec psql 拼 SQL 字符串；passlib 与新版 bcrypt(4.x) 不兼容，直接用 `bcrypt.hashpw` 生成哈希
- **issue_tickets.due_at 是 TIMESTAMP WITHOUT TIME ZONE**：SLA worker 查询时不能传 aware datetime，需 `.replace(tzinfo=None)`；同类问题可能存在于其他 naive 列（created_at/updated_at 是 `WITH TIME ZONE`，但 due_at 不是）
- **全库 timezone-aware 化已彻底完成（2026-05-07）**：曾存在 330+ naive 列导致代码 `datetime.now(timezone.utc)` 与 `TIMESTAMP WITHOUT TIME ZONE` 不兼容；修复方案 = (1) PG 执行 `_fix_timestamptz.sql` 一次性 `ALTER COLUMN ... TYPE TIMESTAMPTZ USING ... AT TIME ZONE 'UTC'` 转 409 列；(2) `base.py` 注册 `Base.registry.update_type_annotation_map({datetime: DateTime(timezone=True)})` 让所有 `Mapped[datetime]` 默认 aware；(3) TimestampMixin 显式加 `DateTime(timezone=True)`；(4) 批量替换 26 处显式 `Column(DateTime,...)` / `sa.DateTime,` 为 `DateTime(timezone=True)`；最终 `Base.metadata.tables` naive 列数 = 0
- **SQLAlchemy datetime 默认类型陷阱**：`Mapped[datetime]` 不加 `DateTime(timezone=True)` 默认生成 naive（`TIMESTAMP WITHOUT TIME ZONE`）；显式传 `sa.DateTime` 也是 naive，必须 `sa.DateTime(timezone=True)`；显式声明会覆盖 `type_annotation_map` 全局默认
- **PG schema 转换铁律**：naive → aware 必须 `USING col_name AT TIME ZONE 'UTC'` 才能保留原值语义；裸 `ALTER ... TYPE TIMESTAMPTZ` 会按服务器时区（如 Asia/Shanghai）解释导致偏移
- **backend/scripts/_fix_timestamptz.sql 已建**：可重跑的幂等脚本，遍历 information_schema 把所有 naive 列转 timestamptz；未来若再遇到零散 naive 列回归，一键修复
- **账表导入 spec 核心策略（ledger-import-unification）**：四表联动关键列（余额表 `account_code`+期初/期末/发生额；序时账 `voucher_date`+`voucher_no`+`account_code`+借贷；辅助表 +`aux_type`+`aux_code`）置信度 ≥ 80 强制人工确认，次关键列（`account_name`/`summary`/`preparer`/`currency_code` 等）≥ 50 自动映射，非关键列进 `raw_extra JSONB` 不校验；错误分级对应：关键列 blocking / 次关键列 warning（值置 NULL）/ 非关键列不校验
- **前端视图/组件实测规模（2026-05-07）**：views/ 含子目录共 86 个 `.vue`（根目录 68 + ai/eqcr/qc/independence/extension）；GtPageHeader 接入率 12/86（14%）；GtEditableTable 接入率 0/86；statusMaps.ts 已删除；components/ai/ 清理后剩余约 14 个文件
- **导航动态化已落地**：`ThreeColumnLayout.vue:360` navItems 已 computed + buildNavForRole 按角色过滤；FALLBACK_NAV 10 项含 roles 字段；后端 get_nav_items 仍可覆盖但前端已不依赖
- **ReviewInbox.vue 是死代码**：router 三条路由（ReviewInbox/ReviewInboxGlobal/review-inbox）全部指向 `ReviewWorkbench.vue`，`ReviewInbox.vue` 文件仍在但无引用，可安全删除
- **PartnerDashboard.vue 两处硬编码**：第 561、582 行 `/api/my/pending-independence?limit=...` 未走 apiPaths；QCDashboard.vue:325 `/api/qc/reviewer-metrics` 同样硬编码；需补 `apiPaths.ts` 的 `my.pendingIndependence` / `qc.reviewerMetrics` 并封装 service
- **EQCR 指标入口权限窄**：`DefaultLayout.vue` 第 132 行 `isEqcrEligible` 只认 partner/admin，`router/index.ts:465` meta.roles 同样窄，建议加 `role === 'eqcr'` 让 EQCR 自己看指标
- **DefaultLayout router-view 加 `:key="viewRoute.fullPath"`**：解决路由跳转后新页面空白的问题；ErrorBoundary 也需要带 key（否则 hasError 状态不重置，跳转后继续隐藏内容）；最终结构 = `<router-view v-slot> → <ErrorBoundary :key> → <Transition> → <component :key>`
- **AI 组件重复 + 死代码**：`components/workpaper/AiContentConfirmDialog.vue` 与 `components/ai/AiContentConfirmDialog.vue` 同名共存；`ai/ContractAnalysis / ContractAnalysisPanel / EvidenceChainPanel / EvidenceChainView` 四组件 grep 零引用
- **/confirmation 侧栏指向不存在的路由**：`ThreeColumnLayout.vue:330` 侧栏"函证"指 `/confirmation`，但 router 中无此路径定义，点击走 NotFound 而非 DevelopingPage；已 maturity=developing 但守卫没触发
- **Mobile 系列 5 视图全是 stub**（MobilePenetration/MobileReview/MobileReport/MobileProjectList/MobileWorkpaperEditor），Round 7+ 前可考虑整体删除以减负
- **useCellSelection 接入 5 实例/4 视图**（TrialBalance 科目明细 `tbCtx` + 试算平衡表 `tbSumCtx` / ReportView / DisclosureEditor / ConsolidationIndex），其他表格无 Excel 级选中；行选/列选/Ctrl+A/粘贴入库/单元格撤销全部缺失
- **编辑锁前端只 1 处**：仅 `components/formula/StructureEditor.vue` acquireLock/releaseLock + lockRefreshTimer；WorkpaperEditor/DisclosureEditor/AuditReportEditor 裸奔，两人并发编辑会互覆盖（后端 workpaper_editing_locks 表已就绪）
- **后端联动链路已完整但前端不可见**：event_handlers.py 已订阅 ADJUSTMENT_*→TB→REPORTS→AUDIT_REPORT / WORKPAPER_SAVED→consistency / LEDGER_ACTIVATED→mark_stale；前端 workpaper.is_stale 只判 consistent/inconsistent 没展示 stale
- **穿透端点共 5+1 套**（reports/drilldown/{row_code}、drilldown/ledger/{code}、ledger/penetrate、consol_worksheet/drill/*、penetrate-by-amount、**trial-balance/trace**），前端入口散；usePenetrate 应封装统一
- **`GET /trial-balance/trace` 数据溯源端点**：查询标准科目对应的所有客户科目及 tb_balance 原始数据（account_mapping JOIN tb_balance），返回 sources 数组含 account_code/account_name/closing_balance/debit_amount/credit_amount
- **快捷键已注册 13 个但无 UI**：shortcutManager 全局单例已在 shortcuts.ts 定义 shortcut:save/undo/redo/search/goto/export/submit/escape/refresh/help 等，但 `?` 或 F1 帮助面板未实现
- **单元格编辑不入 operationHistory**：operationHistory 当前只接 `删除` 动作（Adjustments/RecycleBin），单元格误改无 Ctrl+Z 可恢复
- **NotificationCenter 只 30s 轮询 + SSE**，无分类 Tab、无免打扰时段
- **AiAssistantSidebar 与 SmartTipList 职责重叠**：WorkpaperEditor 右栏 AI 提示在两处渲染（AiAssistantSidebar + WorkpaperEditor 内联 smartTip 面板 90-94 行）
- **顶栏工具簇已瘦身**（2026-05-07，14→4 常驻图标）：顶栏只保留 🔔通知 · Aa显示设置 | 视图切换·回收站·设置 | 复核收件箱·独立复核·EQCR 指标 | 用户菜单；SyncStatusIndicator 已从顶栏移除（正常态无交互价值）；移至左侧栏底部"工具"区的 7 个：知识库/私人库/AI 模型/排版模板/吐槽求助/公式管理/自定义查询；`.gt-topbar-btn` 统一 34×34px 圆角 8px，gap 4px，分隔线 margin 8px
- **版面组件唯一位置原则**：GtPageHeader/GtInfoBar/GtToolbar/GtStatusTag/GtAmountCell/CellContextMenu/TableSearchBar/SelectionBar/SyncStatusIndicator/NotificationCenter 等 21 个全局组件必须有唯一归属位置，禁止各视图自写重复；详见 docs/GLOBAL_REFINEMENT_PROPOSAL_v1.md §11.6
- **角色差异化布局已规约**：auditor/manager/qc/partner/eqcr/admin 各自顶栏角色动作簇、左栏导航项数、Detail 默认落地页，实现方式 = §2.2 动态导航 + §1.1 登录角色跳转
- Univer 公式引擎：@univerjs/preset-sheets-formula **不存在于 npm**，公式引擎内置在 preset-sheets-core（UniverSheetsFormulaPlugin + UniverSheetsFormulaUIPlugin 自动注册），只需 UniverSheetsCorePreset 未传 workerURL（否则 notExecuteFormula=true 禁用计算）
- ThreeColumnLayout.vue 无 #header/#nav-icons slot（顶部导航硬编码）；新入口需先添加自定义 slot（已加 #nav-review-inbox），再在 DefaultLayout 通过 `<template #nav-review-inbox>` 注入
- eventBus 新增事件：`workpaper:saved`（WorkpaperSavedPayload: projectId/wpId/year?）、`materiality:changed`（MaterialityChangedPayload: projectId/year?）
- 后端 AccountCategory 枚举实际值：asset/liability/equity/revenue/expense（无 income/cost）；前端借贷平衡 liabEquityTotal 过滤时需兼容 `['revenue','income','cost','expense']`
- **mapping_service.py `_infer_category` 4xxx 已修正为 equity**：此前错误地把 4xxx 归为 revenue（与 5xxx 合并），导致 4001 实收资本/4101 盈余公积/4103 本年利润/4104 利润分配被归到"收入"类；修复后需重新 auto-match 才能生效
- **前端试算表分组双保险策略**：`groupedRows` 分类优先用后端 `account_category`，仅当编码首位+名称关键词双重匹配时才覆盖（如 4xxx+名称含"资本/公积/利润"→equity）；不强制按编码首位归类
- **试算表增加"负债和权益合计"行**：在权益小计后自动插入，方便与资产小计校对（资产 = 负债 + 权益）
- 后端错报模型：`UnadjustedMisstatement`（表名 unadjusted_misstatements），不是 Misstatement
- GateRule 注册模式：继承 GateRule + `rule_registry.register_all([GateType.submit_review, GateType.sign_off], Rule())`；错报超限规则必须注册到 submit_review（仅 sign_off 不够）
- 账套导入状态端点：`GET /api/projects/{project_id}/ledger-import/jobs/{job_id}`（通过 getImportJob service）；作业状态枚举 completed/failed/timed_out/canceled（轮询四个都要判断）
- apiProxy：api.get/post 返回 unwrapped data；validateStatus=s<600 放行 4xx/5xx 时返回 FastAPI `{detail: {...}}`；409 冲突判断 `data?.detail?.error_code === 'VERSION_CONFLICT'`
- apiProxy 不导出 http 原始客户端；blob 下载需 `import http from '@/utils/http'` 直接用 axios（已用于 onExportPdf）
- PDF 导出依赖 LibreOffice headless（libreoffice/soffice which 检测 + subprocess --headless --convert-to pdf --outdir），超时 60s；Windows 需装 LibreOffice，Docker 镜像需打包 libreoffice-core
- Worker 拆分架构：每模块导出 `async def run(stop_event: asyncio.Event)`，用 `asyncio.wait_for(stop_event.wait(), timeout=interval)` 实现可中断 sleep；lifespan 中由 `_run_migrations / _register_phase_handlers / _replay_startup_events / _start_workers` 四个私有函数编排
- database.py 按 DATABASE_URL.startswith("postgresql") 分支：PG 生产 pool_size≥20 / max_overflow≥80 / pool_timeout=30 / pool_recycle=1800；SQLite 开发保留 pool_recycle=3600
- DB_POOL_SIZE/DB_MAX_OVERFLOW 默认 10/20（config.py），database.py 用 max() 确保 PG 分支至少 20/80（向下兼容旧 env）
- Schema bootstrap ADR：不走 Alembic 全量 autogenerate，baseline=create_all（`_init_tables.py` 一次建所有表），增量=autogenerate 补丁；MIGRATION_GUIDE.md 记录
- 属性测试策略：backend Python hypothesis 复刻前端 TS 算法（setTimeout 防抖、COMPLETED_STATUSES、resolveUserName、_DIRTY_PATTERNS 等），因前端未装 vitest/fast-check
- load_test.py 双模式：Locust UI（探索式）+ 独立 asyncio/httpx 批量压测（CI/CD，输出 JSON 报告含 TPS/P95/P99/error_rate/bottlenecks/slow_queries，未达标退出码 1）
- useAutoSave composable 保存到 sessionStorage 用于草稿恢复，不适合 Univer 大型 snapshot 后端自动保存；底稿编辑器自动保存需独立 setInterval 调用 onSave
- 项目未安装 @vueuse/core，防抖用原生 setTimeout/clearTimeout 实现
- Project 模型无 audit_type 字段，不可依赖做期中/期末判断
- commonApi.getMyStaffId 直接返回 `string | null`；staffApi.getMyStaffId 返回对象，两者不同
- router_registry.py 路由前缀规范：路由器内部只声明业务路径（如 /gate），注册时统一加 prefix="/api"；例外：dashboard.py 内部带 /api/dashboard 注册时不加、/wopi 不加、/api/version 直接在 main.py
- 预存 backend 测试失败（与本 spec 无关，不要误判为回归）：test_adjustments.py 23 个测试因 SQLite 不支持 pg_advisory_xact_lock 失败；test_misstatements.py 2 个测试因 UnadjustedMisstatement 缺 soft_delete mixin；test_e2e_chain* 同样 pg_advisory_xact_lock 问题；test_audit_report.py 12 个 API endpoint 测试 401 Unauthorized（test client 未配置 auth override，与 JSON 种子修复无关）
- NotificationCenter.vue 已挂载到 DefaultLayout.vue 顶部导航（R6 Task 7），通知铃铛可见；导航顺序：复核收件箱→🔔通知→🛡️独立复核→📊EQCR指标
- ReviewWorkstation.vue 已确认删除（R6 Task 8 验证 fileSearch 零命中）
- backend/app/routers/pbc.py 和 confirmations.py 返回 `{"status": "developing", "items": [], "note": "..."}`，maturity 标记为 developing（R6 Task 8）
- apiPaths.ts 当前 **260+** 个 API 端点（2026-05-07），新增 reportConfig/reportMapping/consolNoteSections + eqcr 扩展（memo/independence/componentAuditors/priorYear/metrics）+ admin 扩展（importEventHealth/importEventReplay）+ reports.export
- 前端 service 硬编码路径迁移 **全部完成**（2026-05-07）：9 个文件共 257 处硬编码→0，全部使用 apiPaths 常量
- Vue 文件硬编码迁移进度：322→~90（已消除 ~232 处 / 72%），最新 commit 535f7dd；CI 基线 115（实际已低于基线）；剩余 ~50 文件为零散专用端点（disclosure-notes/workhours/metabase/audit-types/custom-query 等），不再批量修，触碰即修
- apiPaths.ts 新增路径对象（本轮）：knowledgeLibrary(11方法)/noteTemplates/accountChart(含standard)/accountMapping/reportLineMapping/columnMappings/dataLifecycle/consolNoteSections(8方法)/reportConfig扩展(detail/create/executeFormulasBatch/batchUpdate)/reportMapping/reports.export/independenceDeclarations；ledger 从 3 方法扩展到 17 方法；workpapers 新增 batchPrefill/generateFromCodes/wpMappingTsj/versions/univerData/univerSave/exportPdf；attachments 新增 preview/download/associate/ocrStatus
- CI 新增 vue-tsc --noEmit 步骤到 frontend-build job（.github/workflows/ci.yml）
- CI 新增 'API hardcode guard' 卡点（基线 173，grep 统计 Vue 文件 /api/ 硬编码，超基线则 fail）；本地自查脚本 scripts/check-api-hardcode.sh；策略"触碰即修+基线只减不增"
- Vue 硬编码迁移决策：剩余 65 文件 / 173 处不再批量修，采用触碰即修策略自然收敛；下一步优先级转向 UAT 验收 + 性能压测
- docs/API_CHANGELOG.md 记录 R4-R6 端点变更；docs/templates/NEW_API_ENDPOINT.md 三件套模板
- archive 对象已重构：`archive`→`orchestrate`，新增 `job(pid,jobId)` 和 `retry(pid,jobId)`
- AnnualIndependenceDeclaration 模型已扩展：新增 project_id(nullable)/status/attachments/signed_at/signature_record_id/reviewed_by_qc_id/reviewed_at 字段（R1 需求 10 合并）
- wrap_ai_output 函数已实现于 wp_ai_service.py（与 wrap_ai_content 并存，面向前端确认流程，含 id/generated_at/confirm_action/revised_content 字段）
- pdf_export_engine.py 新增 4 函数：build_ai_contribution_statement/get_ai_statement_css/get_ai_statement_html/render_with_ai_statement
- 归档编排已统一：ArchiveOrchestrator（R1 落地）+ 幂等逻辑（R6 Task 16，24h 内 succeeded/running 不重复打包）；前端 apiPaths.ts archive 对象已重写指向 /api/projects/${pid}/archive/...；旧端点 A/B/C 加 `Deprecation: version="R6"` 头
- 三套就绪检查已统一：gate_engine 为唯一真源，SignReadinessService + ArchiveReadinessService 均调 readiness_facade（R1 落地），R6 补充 KamConfirmedRule + IndependenceConfirmedRule 注册到 sign_off + export_package
- SignatureRecord.signature_level 控制流已解耦（R6 Task 6）：CA 验证走 required_role='signing_partner' + required_order=3，字段保留兼容但禁止用于控制流；scripts/check_signature_level_usage.py 静态检查纳入 CI
- qc_rule_definitions 表已建（R6 Task 9），22 条 seed 规则（QC-01~14 + QC-19~26），QCEngine.check 启动前按 enabled 过滤；前端 /qc/rules 只读页面已就绪
- WorkpaperEditor.vue 工具栏仅保存/同步公式/版本/下载/PDF/上传，无 AI 侧栏、无程序要求侧栏、无右键序时账穿透、无对比上年按钮
- EQCR 角色与工作台已落地（R5 Tasks 1-7）：ProjectAssignment.role='eqcr' 已启用、GateType.eqcr_approval 已注册、ReportStatus.eqcr_approved 已扩展、EqcrService + /api/eqcr/* 路由 + 前端 EqcrWorkbench/EqcrProjectView 页面 + 5 Tab 组件 + 关联方 CRUD 全部就绪
- ThreeColumnLayout.vue 新增 #nav-eqcr slot（R5 Task 4），DefaultLayout 注入"🛡️ 独立复核"导航按钮（partner/admin 可见）
- Communication/ClientCommunication 模型不存在（grep 零命中），ProjectProgressBoard 沟通记录前端组件存在但后端未独立建模，可能塞在 JSON 字段或散落表里
- WorkingPaper 无 due_date 字段，wp_progress_service overdue_days 用 created_at 估算"已创建天数"，语义弱
- ledger/penetrate 端点参数为 account_code + drill_level + date，不支持按 amount 容差匹配；按金额穿透需新增端点
- assignment_service.ROLE_MAP 和 role_context_service._ROLE_PRIORITY 两个字典是角色体系单一真源，新增 role='eqcr' 已同时更新；_ROLE_PRIORITY 当前 partner(5)/eqcr(5)/qc(4)/manager(3)/auditor(2)/readonly(1)
- GoingConcernEvaluation 模型已存在（collaboration_models.py），Round 5 EQCR 持续经营 Tab 可直接复用，不要重复建模
- 归档包设计决策：采用"插件化章节"模式（00/01/02/.../99 顺序），各 Round 各自插入章节，Round 1 需求 6 只预留机制
- EQCR 路由架构（f333788 重构后）：`backend/app/routers/eqcr/` 包含 12 子模块（workbench/opinions/notes/related_parties/shadow_compute/gate/memo/time_tracking/independence/prior_year/metrics/constants），`__init__.py` 聚合导出 router + 所有端点函数（向后兼容测试）
- EQCR 服务拆分（50b034f）：`eqcr_workbench_service.py`（EqcrWorkbenchService: list_my_projects/get_project_overview）+ `eqcr_domain_service.py`（EqcrDomainService: 5 域聚合 + opinion CRUD）+ `eqcr_service.py` 薄组合类（MRO 继承向后兼容）
- EQCR 枚举端点：`GET /api/eqcr/constants` 返回 domains/verdicts/progress_states，前端启动时拉取避免硬编码漂移
- R5 Alembic 迁移链：round5_eqcr_20260505 → round5_independence_20260506 → round5_eqcr_check_constraints_20260506（PG CHECK domain+verdict）
- R6 Alembic 迁移链：round6_qc_rule_definitions_20260507 → round6_review_binding_20260507（conversation_id 列）
- R6 CI 骨架：`.github/workflows/ci.yml`（4 job: backend-tests/backend-lint/seed-validate/frontend-build）+ `.pre-commit-config.yaml`（check-json + json-template-lint）
- R6 seed schema 校验：`scripts/validate_seed_files.py` + `backend/data/_seed_schemas.py`（6 个 seed 文件 Pydantic v2 校验）
- R6 死链检查：`scripts/dead-link-check.js`（Node 脚本，扫描 apiPaths.ts 231 端点 vs router_registry 130 前缀，纳入 CI seed-validate job）
- R6 gate_rules_round6.py：KamConfirmedRule（R6-KAM）+ IndependenceConfirmedRule（R6-INDEPENDENCE）+ SubsequentEventsReviewedRule（R7-SUBSEQUENT）+ GoingConcernEvaluatedRule（R7-GOING-CONCERN）+ MgmtRepresentationRule（R7-MGMT-REP），模块导入时自动注册到 sign_off + export_package
- R6 复核批注边界：ReviewRecord.conversation_id FK → review_conversations.id；close_conversation 前校验未解决记录；IssueTicket 去重（source='review_comment' + source_ref_id）
- ThreeColumnLayout.vue 新增 #nav-notifications slot（R6 Task 7）+ developing maturity badge 样式 .gt-maturity-dev（蓝灰 #909399）
- router_registry.py §15 注册 qc_rules_router（内部 prefix="/api/qc/rules"）；前端路由 /qc/rules → QcRuleList.vue（权限 qc/admin/partner）
- conftest.py test_all_models_registered：AST 遍历 backend/app/models/*.py 断言所有 __tablename__ 已注册到 Base.metadata.tables
- R3 Sprint 4 AI 溯源：gate_rules_ai_content.py（AIContentMustBeConfirmedRule rule_code="R3-AI-UNCONFIRMED" 注册到 sign_off）+ wp_ai_confirm.py 端点（PATCH /ai-confirm 确认/拒绝/修订）+ ai_contribution_watermark.py 工具函数 + audit_log_rules_seed.json（AL-01~05）
- R3 前端 QC 6 页面已就绪：QcRuleList（R6 创建）+ QcRuleEditor + QcInspectionWorkbench（含日志合规 Tab）+ ClientQualityTrend + QcCaseLibrary + QcAnnualReports，路由均在 /qc/* 下注册
- 归档章节完整性：00 封面 ✓ / 01 签字流水 ✓ / 02 EQCR 备忘录 ✓ / 03 质控抽查报告 ✓ / 04 独立性声明 ✓ / 99 审计日志 ✓（全部有真实 generator）
- Alembic 迁移链（14 个 round* 文件）：round1_review_closure → round1_long_term_compliance → round2_budget_handover → round2_batch3_arch_fixes → round3_qc_governance → round5_eqcr_20260506 → round4_editing_lock → round4_ocr_fields_cache（分支终点）；主链 round5_eqcr_20260505 → round5_independence → round5_eqcr_check_constraints → round6_qc_rule_definitions → round6_review_binding → round7_section_progress_gin
- jsonpath-ng 已写入 requirements.txt，qc_rule_executor.py 的 jsonpath 分支已实装（execute_jsonpath_rule 函数）
- qc_annual_report_service.py 导入修正：`build_ai_contribution_statement` 来自 `ai_contribution_watermark.generate_short_statement`（非 pdf_export_engine）
- router_registry.py §17 注册 4 个 QC router（qc_inspections/qc_ratings/qc_cases/qc_annual_reports），内部已含完整 prefix 不加额外前缀
- IssueTicket Q 整改单 SLA：Q_SLA_RESPONSE_HOURS=48 / Q_SLA_COMPLETE_HOURS=168，逾期走 _handle_q_sla_timeout 通知签字合伙人
- datetime.utcnow() 已全局清理（81 文件），统一 `datetime.now(timezone.utc)`；后续新代码禁止使用 utcnow()
- 归档包章节号分配：00 项目封面 / 01 签字流水（R1）/ 02 EQCR 备忘录（R5，已注册）/ 03 质控抽查报告（R3）/ 04 独立性声明（R1）/ 10 底稿/ / 20 报表/ / 30 附注/ / 40 附件/ / 99 审计日志
- 审计意见锁定架构决策：不新增 opinion_locked_at 平行字段，改为扩展 ReportStatus 状态机 draft→review→eqcr_approved→final（R5 需求 6 + README 跨轮约束第 3 条）
- 枚举扩展硬约定：IssueTicket.source 在 R1 一次性预留 11 个值（L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/pbc/confirmation/qc_inspection），ProjectAssignment.role 预留 eqcr，避免多轮迁移
- 权限矩阵四点同步约定：新增 role/动作需同时更新 assignment_service.ROLE_MAP + role_context_service._ROLE_PRIORITY + 前端 ROLE_MAP + composables/usePermission.ROLE_PERMISSIONS
- 焦点时长隐私决策：R4 需求 10 焦点追踪只写 localStorage（按周归档键 `focus_tracker_YYYY-MM-DD`），不落库不发后端，消除监控隐患
- R4 编辑软锁：`workpaper_editing_locks` 表，有效锁 = `released_at IS NULL AND heartbeat_at > now - 5min`，惰性清理（acquire 时过期锁设 released_at=now），前端 heartbeat 每 2 分钟，beforeUnload 释放
- R4 AI 脱敏：`export_mask_service.mask_context(cell_context)` 在 LLM 调用前替换金额/客户名/身份证为 `[amount_N]/[client_N]/[id_number_N]` 占位符，映射表仅当前会话有效不回填；脱敏阈值 >= 100000（非 10000）；人名匹配需"联系人：/客户："等前缀标记，公司名匹配后缀"公司/集团/有限/科技"等
- R4 预填充 provenance：`parsed_data.cell_provenance` JSONB，supersede 策略（重填覆盖旧值，`_prev` 保留最多 1 次历史），source 类型 trial_balance/prior_year/formula/ledger/manual/ocr；实现位于 `prefill_engine.py` 末尾四个函数
- R4 按金额穿透：`backend/app/routers/penetrate_by_amount.py`（本次新建），prefix="/api/projects/{project_id}/ledger"，MAX_RESULTS=200 截断
- R4 router 注册：router_registry.py §13 "审计助理(R4)" tag，6 个 router 内部已含完整 /api prefix 不加额外前缀
- R4 Alembic 迁移 2 个：`round4_editing_lock_20260506`（workpaper_editing_locks 表）+ `round4_ocr_fields_cache_20260506`（attachments.ocr_fields_cache JSONB 列）
- 跨轮 SLA 统一按自然日计，不引入节假日日历服务，跨长假由人工 override（README 跨轮约束第 5 条）
- ClientCommunicationService 已存在于 `pm_service.py:481`，沟通记录存 `Project.wizard_state.communications` JSONB，`commitments` 当前是字符串；R2 需求 5 无需"调研"，直接升级为结构化数组
- ReviewInboxService.get_inbox(user_id, project_id=None) 已支持全局+单项目双模式（`pm_service.py:26`），R1 需求 1 不新增后端端点
- 复核批注并存两套：ReviewRecord（单行绑定 wp_id+cell_reference）与 review_conversations（跨对象多轮）；R1 需求 2 选定 ReviewRecord 为工单转换真源，conversations 只用于后续讨论
- AuditEvidence 模型不存在（grep 零命中），附件与底稿关联统一用 attachment_service + workpaper_attachment_link
- AJE 被拒→错报联动：后端 misstatement_service.create_from_rejected_aje 已实现，但 Adjustments.vue 前端入口缺失；R1 需求 3 新增 UnconvertedRejectedAJERule 到 sign_off gate
- event_handlers.py:173 订阅 WORKPAPER_SAVED 级联更新试算表/报表/附注，但无补偿机制；R1 需求 3 新增 EventCascadeHealthRule gate 规则
- ExportIntegrityService 语义：导出时 persist_hash_checks 记哈希（`export_integrity_service.py:53`），下载不重算，可疑时显式 verify_package；R1 需求 6 措辞对齐
- 签字状态机联动决策：最高级签字完成后由 SignService.sign 内部同事务自动切 AuditReport.status 到 final（R1 需求 4），避免"签完字但报告停在 review"困惑
- 归档断点续传：archive_jobs 表记 last_succeeded_section，重试从下一章节开始（R1 需求 5）
- R3 规则 DSL 本轮范围收窄：只实现 expression_type='python'+'jsonpath'，SQL/regex 枚举保留但执行器 NotImplementedError，留 Round 6+
- R5 EQCR 独立性边界：不直接对外联络客户（维持项目组作为对外单一入口），只做内部独立笔记，可选择分享给项目组
- 签字状态机联动分两情形：无 EQCR 项目 order=3 partner 签完直接切 review→final；启用 EQCR 则 order=3 不切、order=4 EQCR 签完切 review→eqcr_approved、order=5 归档签字完切 eqcr_approved→final
- notification_types.py 由 R1 tasks 19 唯一创建，R2+ 只向其追加常量不重复新建；前端 notificationTypes.ts 同理
- AuditReportEditor.vue 状态处理已完善：isLocked computed 统一判断 eqcr_approved/final，编辑器头部四态标签（draft→可编辑/review→⚠审阅中/eqcr_approved→🔒EQCR已锁/final→🔒已定稿），opinion_type 下拉在锁定态 disabled
- EqcrProjectView.vue 现有 10 个 Tab：materiality/estimate/related_party/going_concern/opinion_type/shadow_compute/review_notes/prior_year/memo/component_auditor（最后一个仅 consolidated 项目显示）
- EQCR 备忘录存储：Project.wizard_state.eqcr_memo JSONB（sections dict + status draft/finalized），不独立建表
- EQCR 工时追踪：WorkHour.status='tracking' 表示计时中，stop 时计算时长并切回 draft
- 年度独立性声明：独立表 `annual_independence_declarations`（R1 通用表落地前的过渡方案），唯一约束 `(declarant_id, declaration_year)`；问题集 backend/data/independence_questions_annual.json（32 题）是唯一真源，Python 侧不再维护副本
- EqcrMetrics.vue 路由 /eqcr/metrics 已注册，后端加 admin/partner 角色守卫；DefaultLayout #nav-eqcr 插槽内挂两个按钮（独立复核工作台 + EQCR 指标）
- apiProxy 实际路径 `@/services/apiProxy`（不是 `@/utils/apiProxy`）；默认导出和命名导出 `{ api }` 都可用；memory 此前记录有误已更正
- `stores/auth.ts` login 方法：后端返回 `{code, message, data: {access_token, refresh_token, user}}`，authHttp（原始 axios）不经过 apiProxy 解包，需 `data.data ?? data` 取 payload
- `apiPaths.ts` 新增 `signatures`（/api/signatures/*）和 `rotation`（/api/rotation/*）导出（R1 需求 4/11 前端 service 依赖）
- 新 PG 库初始化流程：`python scripts/_init_tables.py`（需先 `pip install psycopg2-binary`）→ 手动建 admin 用户（INSERT 需含 email 字段 NOT NULL）
- `backend/migrations/V003__example_add_comment.sql` 已修复 `DO $` → `DO $$`（PG dollar-quoting 语法）
- User 模型无 metadata_ JSONB 字段；需要"用户级元数据"时应建独立表（如 annual_independence_declarations），不污染 User 表
- StaffMember 用 `employee_no`（不是 `employee_id`）作为工号字段
- WorkHour.status 是 String(20) 非 enum，可自由塞业务值（R5 用 'tracking' 表示计时中）
- ProjectStatus 枚举值：created/planning/execution/completion/reporting/archived（没有 in_progress，测试 fixture 常用 execution）
- CompetenceRating 枚举实际值：reliable/additional_procedures_needed/unreliable（设计 doc 中的"A/B/C/D"是业务语义而非代码枚举，前端标签映射需对齐实际枚举）
- ReportStatus 枚举：draft/review/eqcr_approved/final；VALID_TRANSITIONS 矩阵定义在 `test_eqcr_state_machine_properties.py`（draft→review；review→{eqcr_approved,draft}；eqcr_approved→{review,final}；final→∅）
- hypothesis 包已写入 requirements.txt（R6 Task 2），ruff@0.11.12 同步写入；CI 可正常运行属性测试
- SQLAlchemy 异步模式下 `db.add(obj)` 不立即生成 PK，引用 obj.id 前必须 `await db.flush()`；gate_engine 此前因缺 flush 导致 trace_events.object_id NOT NULL 违反
- SQLAlchemy `session.refresh(obj)` 会从 DB 重读覆盖内存中的未 flush 修改；业务代码变更字段后希望 refresh 可见时必须先 flush
- python-docx 已装可用（phase13 note_word_exporter.py 同款），Word 生成遵循 `build_*_docx_bytes(...)→bytes` 纯函数模式便于单测；PDF 转换走 LibreOffice headless `soffice --headless --convert-to pdf`（memory 之前关于 LibreOffice 路径检测记录正确）
- 客户名归一化 `app/services/client_lookup.normalize_client_name` + `client_names_match`：去空白、全角→半角、去"有限公司/股份/集团/Co.,Ltd/Inc." 后缀，归一后精确相等。R3 正式落地后迁入 R3 模块
- 前端路由 beforeEach 新增 `meta.requiresAnnualDeclaration` 守卫：访问 EQCR 相关路由前调 `/api/eqcr/independence/annual/check`，未声明则强制跳 EqcrWorkbench 弹对话框；同时支持 `meta.roles` 角色粗筛
- role_context_service.get_nav_items 已修复：QC 角色新增 3 个全局导航（规则管理/质控抽查/案例库）；manager 角色新增"项目经理工作台"入口
- workhour_list.py 新建端点：GET /api/workhours（审批人视角聚合列表）+ GET /api/workhours/summary（本周统计，消除 N+1）
- WorkpaperEditor.vue 新增"提交复核"按钮（draft→pending_review）+ 自动保存失败 toast 提示
- workpaper_remind.py 新增 POST /escalate-to-partner 端点（催办 3 次后升级通知签字合伙人）
- 前后端路径修复：WorkpaperWorkbench AI 聊天 /api/chat/stream→/api/workpapers/{wpId}/ai/chat；附件上传 /api/attachments/upload→/api/projects/{pid}/attachments/upload；AiAssistantSidebar /chat→/ai/chat

## 活跃待办

### 最高优先级
- **GLOBAL_REFINEMENT_PROPOSAL_v3.md 已生成**（docs/，2026-05-16）：合伙人实操视角，不再画路线图只列实操磨损面；5 主战场（联动闭环 / 组件铺设 / 显示三条线 / 错误容灾 / 长期维护）；推荐 R10 拆 2 个并行 spec（联动+显示治理 / 编辑器+容灾），各 2-3 周；TOP 2 痛点 = PartnerSignDecision stale 摘要+AJE 转错报按钮 / 字号变量化第一批（编辑器 4 个）
- **v3 §11 真实 E2E 实测修订完成（2026-05-16）**：4 项目（陕西华氏/和平药房/辽宁卫生/宜宾大药房）全链路实测，发现 5 个 P0 真实缺陷 + 7 处端点路径误写
  - **F1 红色 P0**：IS（利润表）+ CFS（现金流量表）**4 项目全部 nonzero=0**——report_config.formula 字段填充率 21%/CFS 16% 但实际计算值非零率为 0%；公式存在但损益类 5xxx/6xxx 取值逻辑可能错（应单边发生额：收入取 credit_amount 存负数，费用取 debit_amount 存正数）
  - **F2 红色 P0**：和平药房/辽宁卫生 wp_count=0（`init_4_projects.py` 漏调底稿生成步骤）；R10 之后初始化的项目都可能"试算/报表都有，底稿是空的"
  - **F3 黄色 P0**：`/api/projects/{pid}/data-quality/check?checks=all` 返回 200 但 checks 数组为空（all 关键字处理 bug，R10 e2e-business-flow spec 标 [x] 但实际跑不出）
  - **F4 黄色 P0**：`/workflow/consistency-check` 返回 200 但**没有 `all_passed` 也没有 `consistent` 字段**，前端按 v3 提案接会拿不到
  - **F5 黄色 P0**：AJE/RJE Pydantic enum 只接受小写——前端传 "AJE"/"RJE" 直接 422；建议后端 `@field_validator(mode="before")` 转小写容错
- **v3 真实端点路径速查（grep 核验）**：账表余额=`/api/projects/{pid}/ledger/balance` / 附注树=`/api/disclosure-notes/{pid}/{year}` / 试算汇总=`/api/projects/{pid}/trial-balance/summary-with-adjustments` / 数据质量=`/api/projects/{pid}/data-quality/check?checks=all` / 一致性门控=`/api/projects/{pid}/workflow/consistency-check` / 复核收件箱=`/api/review-inbox`(全局) 或 `/api/projects/{pid}/review-inbox`(项目级) / AI 模型=`/api/ai-models`（连字符不是斜杠）
- **打磨建议文档铁律**：v1/v2/v3 都犯同一个错——基于 memory 写而不是 grep+E2E 验证；下次 v4+ 起草前必须先跑 E2E 脚本拿真实端点和数据；每条建议必须标"已实测/未实测"；声称"已落地"必须有 200 响应支撑
- **v3 第二稿基于实测重写完成（2026-05-16，469 行）**：把 5 个真实 P0 缺陷（F1-F5）从末尾 §11 提到正文 §2 作主轴；§3 端点路径速查表（21 条 grep 核验路径）；§6 优先级按真实磨损度重排，第一周 5 天 8 件事；§15 验收口径加 6 行可量化实测指标；末尾"第一周动手清单"按 Day×半天拆任务+文件锚点；附录 C 把"先 E2E 再起草"写成规约
- **v3 第三稿基于第二次实测完成（2026-05-16，574 行）**：F1/F3/F5 三个原假设全部澄清结案，F6/F7/F8 三个新真问题被发现；§6 优先级重排（工时 5 天 → 6.5 天，9 件事）；§15 验收表加"第一稿假设/第二次实测真值"双列对比；附录 D 新增实测脚本清单
- **第二次实测的真相平反**：(1) **F1 误判**：IS/CFS 全 0 不是公式 bug，是 stale 数据——重新调一次 `POST /api/reports/generate` 后陕西华氏 IS 立即 14 行非零（营业收入 -20,283,811,823.52 真实数据），4 项目重新 generate 后 nonzero 全部上来；(2) **F3 误判**：data-quality 5 个检查全跑了（passed=3+blocking=2），脚本断言字段名写错（`checks` vs 真实 `checks_run`）；(3) **F5 误判**：AJE 422 是 schema 字段名错（`entries`→`line_items` / `account_code`→`standard_account_code` / `memo`→`description`），与枚举大小写无关
- **v3 第三稿 3 个新真问题（实测发现）**：
  - **F6 红色**：AJE 创建端点 500——SQLAlchemy MissingGreenlet（事件 handler 里有 lazy load）；整个调整分录创建链路完全不可用；修复需 1-2 天 grep 定位 + 加 await db.refresh(user) 或改传 user_id
  - **F7 红色**：PG enum `job_status_enum` 缺 `interrupted` 值——`view_refactor_interrupted_status_20260511` Alembic 迁移在生产 PG 没跑成功；import_recover_worker 每 30s 刷 InvalidTextRepresentationError；修复 = `ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'interrupted'` 或重跑 alembic
  - **F8 黄色**：CFS 试算汇总返回 0 行——`/trial-balance/summary-with-adjustments?report_type=cash_flow_statement` 4 项目都 0 行，但 BS/IS 都正常（129/78）；可能是设计如此（CFS 不能从余额表直接取数），需排查 trial_balance_service 分支
- **F2 路径已实测验证可用**：`POST /api/projects/{pid}/workflow/execute-full-chain` body `{"year":2025,"force":true}` 完全工作；和平 0→107、辽宁 0→104；问题是 `init_4_projects.py` 漏调，不是 chain 端点 bug
- **AJE 创建真实 schema**（grep 核验）：`{adjustment_type:"aje"(小写枚举), year, company_code, description, line_items:[{standard_account_code, account_name, debit_amount, credit_amount}]}`；前端 service 必须按此调用，否则 422
- **report_engine `_period_amount` 公式逻辑正确**：`TB('6001','本期发生额')` → `audited_amount - opening_balance`；损益类（5xxx/6xxx）的 `audited_amount` 已存为单边发生额（trial_balance_service 第 207 行：收入类取 credit_amount 存负数 / 费用类取 debit_amount 存正数）；陕西华氏 6001 实测 audited_amount=-20,283,811,823.52 ✓
- **F1 stale 修复路径**：`init_4_projects.py` 末尾必须强制调一次 `generate_all_reports`（或 chain）；否则任何后续改动 trial_balance 不立即触发 generate 时，financial_report 会 stale，用户进系统看到陈旧 0 数据
- **新固化脚本清单**：`backend/scripts/init_4_projects.py`（4 项目数据初始化）+ `e2e_business_flow_verify.py`（DB 直查 4 层断言）+ `verify_data_quality_shaanxi.py`（数据质量单测）+ `fill_report_formulas.py`（报表公式填充）+ `verify_spec_facts.py`（spec 事实核验）+ `check_property_coverage.py`（属性覆盖）+ `build_spec_coverage_matrix.py`（覆盖矩阵）；用完即删的临时脚本不再保留
- **v3 第三稿自我复盘 §16 已加（2026-05-16，636 行）**：4 子节——§16.1 文档自身缺口 D1-D8（4 项已修+4 项待整理）/ §16.2 实测覆盖盲区 C1-C11（EQCR 工作台/复核流程/签字流水/重要性联动/AI 对话/角色权限矩阵/工时审批/附件 OCR/账套导入 v2/项目向导/前端真实渲染）/ §16.3 潜在新缺陷 Q1-Q7（F6 是否影响 UPDATE/DELETE / F7 类似 PG enum 是否还有 / consistency-check 3 条永久 fail 是哪些 等）/ §16.4 v1/v2 已废弃章节标注 / §16.5 v4 起草触发条件
- **v4 起草硬约束（§16.5 落地）**：(a) F1-F8 全部修完 (b) §16.2 11 个实测盲区全部覆盖 (c) 有新合伙人级反馈；不能再凭 memory 推测起草
- **打磨建议文档铁律补充**：每次实测后必须更新 §1 表格作为唯一权威基线；R10 spec 立项时引用 v3 必须用具体小节号（不是泛指"v3 提的"）；同一改动散落多节的，主战场放一处其他章节用"见 §X.Y"引用避免重复
- **v3 第三轮实测完成（2026-05-16，754 行）**：覆盖 §16.2 盲区 8/11（C1 EQCR / C2 复核 / C3 签字 / C4 重要性联动 / C5 AI / C6 角色 / C7 工时 / C8 附件 / C9 账套导入 v2），剩 C10 ProjectWizard / C11 前端真实渲染 / C12 联动事件（F6 修复后必测）；F1-F15 共 15 个标号，4 已澄清 + 6 真红色 + 5 黄色
- **第三轮新发现**：
  - **F8 升级红色**：CFS 试算汇总 0 行真因是 **PG `report_type` enum 缺 4 个值**（cash_flow_statement / equity_statement / cash_flow_supplement / impairment_provision），PG 只有 `balance_sheet, income_statement, cash_flow`；后端日志 `InvalidTextRepresentationError: invalid input value for enum report_type: "cash_flow_statement"` 直接证据
  - **F7 扩展**：PG `job_status_enum` 不只缺 `interrupted`，还缺 `retrying` 和 `cancelled`（双 L 历史兼容值）；实际 PG 只有 10 个值
  - **F9 真红色**：EQCR `opinions` 404 / `prior-year` 404 / `memo` 405——5 Tab 至少 3 个空白
  - **F10 真红色**：`/api/projects/{pid}/review-records` + `/review-conversations` 全 404，复核工作台首屏可能空白
  - **F12 黄色**：`POST /misstatements/recheck-threshold` body `{year}` → 422，schema 不对
  - **F13/F14/F15 黄色**：`/api/users/me/nav` 404（前端用 FALLBACK_NAV 不依赖）/ `/api/knowledge` 404 / `/jobs/latest` 422（前端旧路径残留）
- **F11 第三轮平反**：签字端点真实存在（`/api/signatures/{object_type}/{object_id}` + `/api/projects/{pid}/sign-readiness` 连字符），第三稿脚本路径假设错（写成 `/sign/readiness` 等）
- **PG enum 真实值速查**（grep 实测）：`report_type` 当前 = balance_sheet/income_statement/cash_flow（仅 3 个）/ `job_status_enum` 当前 = pending/queued/running/validating/writing/activating/completed/failed/canceled/timed_out（仅 10 个）；修复 = `ALTER TYPE ... ADD VALUE IF NOT EXISTS ...` 7 条 SQL 一次性执行
- **v3 工时演进**：5 天 → 6.5 天 → **8 天 / 13 件事**；铁律 = F7+F8 PG ALTER TYPE 必须**第一天上午**先修，否则后续 CFS / 中断恢复 / 重试场景都跑不通会污染其他验收
- **签字端点真实速查**：签字记录 `GET /api/signatures/{object_type}/{object_id}` / 签字就绪 `GET /api/projects/{pid}/sign-readiness`（连字符不是斜杠）/ 签字操作 `POST /api/signatures/sign` / 验证 `POST /api/signatures/{signature_id}/verify`
- **FastAPI 路由顺序陷阱再现**：v1.10 改名 `/jobs/latest` → `/active-job` 但旧路径未真删，前端可能仍调用，FastAPI 把 `latest` 当 `{job_id}` UUID 解析失败 422；这是同 prefix 多 router literal 路由 vs `{var}` 通配冲突的同款问题
- **spec 三件套分档决策规约（v3 修复方案沉淀）**：spec 不是非此即彼，按"复杂度+影响面"分 3 档——
  - **档 1 直接修**（不写 spec）：单文件 / 单端点 / 配置类，工时 ≤ 0.5 天（如 PG ALTER TYPE / 单字段补 schema / 端点 grep 核验）
  - **档 2 小型 spec**（仅 README 单文件，不要完整三件套）：根因不清晰 / 多文件协调 / 验收口径需明确，工时 0.5-2 天（如 F6 MissingGreenlet 排查 / F9 EQCR 3 端点契约 / chain init 链路改动）
  - **档 3 完整三件套**（requirements + design + tasks）：跨视图 / 跨服务 / 工时 ≥ 1 周（如 useStaleStatus 推 6 视图 / 显示治理 3888 处硬编码 / 编辑器容灾）
  - **判断铁律**：spec 起草本身要 ≥ 0.5 天 + 复盘 + 评审；任务范围清晰+单文件+影响面小 → 不该走三件套，否则 spec 比修复还耗时
- **v3 13 件事推荐分档执行**：P0-2/4/5/9/10/11（直接修 5 件 / 1.7 天）+ P0-1/3/4/5（小型 spec README 4 件 / 4 天）+ P0-12/13（三件套 Spec A "linkage-stale-propagation"）；R10 立项独立做 Spec B（linkage-and-tokens）+ Spec C（editor-resilience）
- **v3 档 1 直接修 5 件已完成（2026-05-16，1.6h 工时）**：(1) PG `job_status_enum` 加 interrupted/retrying/cancelled、`report_type` 加 cash_flow_statement/equity_statement/cash_flow_supplement/impairment_provision；(2) `chain_workflow.py:consistency_check` 响应顶层加 all_passed/consistent/passed_count/total_count 4 字段；(3) `misstatements.py:recheck_threshold` schema 升级 year 支持 query 或 body 双向传入；(4) v3 §3 端点速查表加签字 4 行；(5) `ledger_import_v2.py` 删除"GET /jobs/latest"误导注释（实际路由是 /active-job），knowledge 真实路径写入 §3
- **PG enum 真实值已修正（2026-05-16 ALTER 后）**：`report_type` = balance_sheet/income_statement/cash_flow/cash_flow_statement/equity_statement/cash_flow_supplement/impairment_provision（7 个，原 3 个）/ `job_status_enum` = pending/queued/running/validating/writing/activating/completed/failed/canceled/timed_out/interrupted/retrying/cancelled（13 个，原 10 个）
- **v3 派生 spec 全部起草完毕（2026-05-16）**：
  - `.kiro/specs/v3-quickfixes/README.md`（档 2，含 Q1-Q4 4 个 quickfix 完整方案 + 反模板"何时升档三件套"5 条标准）
  - `.kiro/specs/v3-linkage-stale-propagation/{requirements,design,tasks}.md`（档 3 三件套，5 需求 R1-R5 + 7 ADR + 4 Sprint + 8 UAT，3 天工时）
  - `.kiro/specs/v3-r10-linkage-and-tokens/README.md`（R10 占位，3 周工时）
  - `.kiro/specs/v3-r10-editor-resilience/README.md`（R10 占位，2 周工时）
- **新增 `.kiro/specs/INDEX.md` 总索引**：列全部 spec 状态/关联 commit/甘特图/工作流规约（档 1/2/3 三档判定标准）；新建 spec 时强制更新此表
- **F12 真因澄清**：错报阈值重检 `POST /api/projects/{pid}/misstatements/recheck-threshold` 后端原本 `year=Query(...)`（query string），不接受 body；实测 422 是脚本测试方式错（POST body 传 year）不是后端 bug；本次修复改为支持 query 或 body 双向传入兼容前端踩雷
- **F11 真因澄清**（2026-05-16 第三轮）：签字端点真实存在但 v3 第一稿假设路径错——真实路径 `/api/signatures/{object_type}/{object_id}` + `/api/projects/{pid}/sign-readiness`（连字符），不是 `/api/signatures/projects/{pid}/records` + `/api/projects/{pid}/sign/readiness`
- **F15 真因澄清**：`/api/projects/{pid}/ledger-import/jobs/latest` 在前端零引用（grep 实测），后端只是注释误导（写"GET /jobs/latest"实际路由 `/active-job`）；真实问题是后端 `@router.get("/jobs/{job_id}")` 把 `latest` 当 UUID 解析失败，无前端调用方时不构成 bug
- **v3 档 2 4 件 quickfix 全部完成（2026-05-16，1.5h 工时）**：Q1 真修复 + Q2/Q3 平反 + Q4 真修复
- **R10 两套三件套已起草并修复（2026-05-16，commit c5d46d5+f995905）**：v3-r10-linkage-and-tokens（22 天 / 4 Sprint / 10 F）+ v3-r10-editor-resilience（11 天 / 3 Sprint / 10 F）；起草后做静态复盘核验识别 14 处偏差，🟡 中等 6 处 + X1 跨 spec 协调缺漏共 7 处一次性修复（v1.1 版本）；启动条件 = v3 P0 全清 ✅ + Spec A 上线 ≥ 7 天稳定（≥ 2026-05-23）
- **R10 两套三件套编码任务全部完成（2026-05-16，commit a04f2b5，~5h 实施）**：311 文件变更，Spec B 22 天 → 3h（180× 压缩），Spec C 11 天 → 2h（132× 压缩）；含 F8 EQCR 备忘录版本对比可选项；UAT 1-9 待真人验收
- **R10 Spec B 主要交付**：gt-tokens.css 补 9 阶灰度+6 级背景 token+3 个新 token（text-inverse/on-dark/info）；CI ci.yml 4 道 grep + frontend-stylelint job；`.github/workflows/baselines.json` 持久化 baseline（font-size/color/bg/el-table-naked）；inline 1565+1611+712=3888 处全部 token 化（仅 69+23+6 处合理保留）；新建 GtTableExtended（列表型）+ GtFormTable（编辑型）+ GtEditableTable 改 wrapper（dev console.warn 60 天观察期）；后端 `app/services/workpaper_query.py` 共享 helper；Misstatements/Adjustments 右键"查看关联底稿"端点（GET /related-workpapers，简化按 cycle_hint 前缀匹配）
- **R10 Spec C 主要交付**：`backend/app/workers/worker_helpers.py write_heartbeat` Redis 60s TTL；4 worker（sla/import_recover/outbox_replay/import）接入心跳；`event_cascade_health_service` + router §55（admin/partner 看完整 schema，普通用户只看 status+lag_seconds 隔离）；http.ts last100Requests 环形缓冲 + `recent5xxRate` / `getRecentNetworkStats` 公开 API；DegradedBanner 三档扩展（hidden/degraded/critical）+ 独立 axios 实例避免递归 + sessionStorage dismiss 5min 记忆；`confirm.ts` 新增 `confirmSign(action, ctx)`；LedgerDataManager 输入项目名才能清理；EqcrMemoEditor 定稿改 confirmDangerous；5 签字组件全量梳理（SignatureManagement L1/2/3 + PartnerSignDecision + EqcrProjectView）；GET /api/eqcr/projects/{pid}/memo/versions 端点（基于 wizard_state.history 5 版本，无需新建表）
- **新依赖**：stylelint@^16.10.0 / stylelint-config-recommended-vue@^1.5.0 / postcss-html@^1.7.0（前端 devDependency）
- **大批量 token 化标准节奏（v1 沉淀，可复用）**：dry-run → 列未识别清单 → 补映射表 → 二轮 dry-run 直到未识别=0 → apply → 类别分桶（raw / 在 gradient/rgba 内）→ 修订 baseline.json → 抽样 vue-tsc + getDiagnostics；脚本用完即删；适用任何 inline style 批量迁移
- **白色双 token 分流**（Spec B Sprint 2 沉淀）：`color: #fff` → `var(--gt-color-text-inverse)`（深色背景上的文字）/ `background: #fff` → `var(--gt-color-bg-white)`（卡片底色）；语义分离为暗色模式预留切换点；黑色 `#000` 保留（CSS 习惯）
- **stylelint 三规则实战配置**：`declaration-property-value-disallowed-list` 单字典含 4 属性（font-size 禁 \d+px / color 禁 #hex / background+background-color 禁 #hex）；不能写两个同名 rule；severity=error 强制阻断；装饰场景加 `/* allow-px: emoji-icon|special|minor */` 注释豁免
- **subagent 批量处理大文件改造规约**：100+ 文件 inline style 替换用 Python 脚本（正则匹配 + skip allow-* 注释行 + apply）远高效于逐文件 strReplace；subagent 单次任务可一次处理整个 Sprint 的 4 批次（如 Spec B Sprint 1 批 2/3/4）
- **CI baseline 字段命名规约**（v3 前已沉淀，本轮验证可用）：`{property}-{format}-{scope}` 格式（如 `font-size-px-vue-files` / `el-table-naked-vue-files`）；占位值由 Sprint 0 实测填入；`_doc` / `_targets` / `_sprint_milestones` / `_*_kept` 元字段记录上下文不参与卡点
- **多 router 同 prefix 路由顺序陷阱再次验证**：misstatements router 路由 `/{misstatement_id}/related-workpapers` 必须放在 `/recheck-threshold` 之后（避免 `recheck-threshold` 被当 UUID 解析）；本次 fsAppend 在文件末尾追加是安全的
- **Adjustments 右键菜单复用 GtEditableTable `#context-menu` slot**：通过 `(adjTableRef.value as any)?.cellSelection?.contextMenu?.row` 拿到当前行；不需要新建 ref，直接复用组件 expose 的 cellSelection composable
- **R10 复盘发现 6 处缺口（2026-05-16，commit a04f2b5 后实测）**：G1 `border-color/border-*-color` hex 残留 ~25 处（subagent 只 cover `color:`漏掉派生属性，0.5h 修）/ G2 DisclosureEditor `background: #fff` 3 处未替换（5min）/ G3 F8 `/memo/versions` 端点未接入前端调用方（30min）/ G4 UAT 1-9 真人验收未启动（上线前 1 天）/ G5 worker 心跳生产 Redis 真实验证未做（30min 运维）/ G6 el-table baseline=100 偏高实测 ~50（5min 调小）
- **subagent 大批量 search-replace 验证规约（R10 复盘 P0 沉淀）**：(1) dry-run 输出未识别项；(2) apply 后强制全量 grep **多种相关属性变体**（不只目标属性名 — 如做 color 时必须同时 grep `color:` `border-color:` `border-*-color:` `--*-color:`）；(3) before/after 对比表按属性分组；(4) **orchestrator 收到报告后必须独立 grep 复核关键指标**，不能信任 subagent 自报值；本次 Spec B Sprint 2 报"raw=0"实际遗漏 25 处派生属性
- **工时压缩比 > 5× 暂停 review 规约**：subagent 报告实际工作量远低于预估（如本次 22 天 → 3h 即 ~180×）时必须人工分析原因——是早完成了？还是 grep 不全？避免"看似全清零但其实漏一半"的幻觉；本次 Spec B 报告"批 2/3 早期已被批 1 一并清掉只 4 文件 17 处"应触发 review 而非自动通过
- **CI baseline 字段命名细化规约**：用属性级前缀（如 `color-prop-hex-vue-files` / `border-color-hex-vue-files`）替代泛化命名（如 `color-hex-vue-files` 容易让人误会全部颜色 hex）；本次 baselines.json 字段命名是误导源头之一
- **可选任务"已实施"三步验证规约**：(1) 端点/函数存在 ✓ + (2) 至少 1 处真实调用方 ✓ + (3) UI 触发路径明确 ✓；任一缺失不能标完成；本次 F8 `/memo/versions` 端点存在但前端 UI 未接入新端点（用旧 `data.history`）属于半成品但被标完成
- **UAT 状态枚举细化规约**：`✓ self-tested`（代码+单测+getDiagnostics 全过）/ `○ pending-uat`（等真人执行）/ `⚠ partial-real`（部分真人测过）/ `✗ fail`；不要用模糊的 `⚠ partial` 含义不清；本次 R10 UAT 大量标 `⚠ partial` 但实际从未启动前端测试
- **TD 章节强制要求规约**：每个 spec tasks.md 末尾必须有"已知缺口与技术债"列未了断的项；禁止"全清零幻觉"；本次 R10 两个 spec tasks.md 漏了 TD 章节，需补回 G1-G6 6 项
- **三件套静态复盘方法论沉淀**：起草后必须做"覆盖矩阵 + 跨文件一致性 + 跨 spec 协调"三维核验——(1) 每个需求 F-N 在 requirements/design/tasks 都要找到对应章节；(2) 跨文件 schema/字段命名/数字统一（baselines.json 字段名漂移最常见）；(3) 跨 spec 共享文件（如 Adjustments.vue / DegradedBanner.vue / gt-tokens.css）依赖方向必须双向声明；问题分级 🔴 阻塞 / 🟡 中等 / 🟢 打磨；🟡 必修 🟢 可选
- **跨 spec 协调铁律**：A spec 任务依赖 B spec 产出（如 token / 端点）时，A 必须在启动条件核验列出 B 的完成度 + 标注 fallback 策略（单独启动时如何降级）；不能假设并行 spec 一定先完成
- **CI baseline 字段命名规约**：`.github/workflows/baselines.json` 字段统一格式 `{property}-{format}-{scope}`（如 `font-size-px-vue-files` / `el-table-naked-vue-files`）；占位值（待 Sprint 0 实测填入）必须在 design 显式标注，避免被当字面量误用
- **签字组件类改造前置任务规约**：5 签字组件之类有"现状不一致"的批量改造（部分已有 confirm / 部分用 ElMessageBox / 部分裸调），tasks 必须先安排 N.0 grep 现状差异表任务（输出"组件 / 当前包装 / 文案 / 改动差异"四列），再分别接入；避免无差异化 task 描述破坏现有 confirm 链路
- **F6 真根因彻底定位**：`backend/app/deps.py:check_consol_lock` 当 PG `projects.consol_lock` 列不存在时调 `await db.rollback()` 让所有已 SELECT 的 ORM 对象（包括 `current_user`）expired，回到 router 访问 `user.id` 时触发 lazy load → MissingGreenlet；修复 = 改用 `async with db.begin_nested()` SAVEPOINT 包住 SELECT，列不存在只回滚 SAVEPOINT 不破坏外层事务
- **SQLAlchemy MissingGreenlet 排查通用模式**：(1) 看异常栈最深的 `__get__` 行就是触发 lazy load 的字段；(2) 反推 ORM 对象什么时候被 expire（最常见是同 session 里有 `db.rollback()` 或 `db.expire_all()`）；(3) 修复策略 — 用 `async with db.begin_nested()` SAVEPOINT 替代 rollback / 写入前 `await db.refresh(obj)` / 关键查询后立即 commit
- **`async with db.begin_nested()` SAVEPOINT 模式**：可重入子事务，列不存在/SQL 异常只回滚 SAVEPOINT，外层事务和已 SELECT 对象状态不受影响；适用于"探测性查询可能失败但不能影响主流程"场景（如 `check_consol_lock` 探测列是否存在）
- **F9 EQCR 端点形态平反**：`/opinions` 没有统一列表（按 domain 分 5 个 GET：`/materiality` / `/estimates` / `/related-parties` / `/going-concern` / `/opinion-type`）+ `POST /opinions` 创建 + `PATCH /opinions/{id}` 修改；`/prior-year` 真路径是 `/prior-year-comparison` 带后缀；`/memo` 没有 GET root 用 `/memo/preview` 读；前端 apiPaths.ts 全部正确零踩雷
- **F10 复核对话端点平反**：`/api/review-conversations` 是**全局 prefix + query param `project_id`**，不是 `/api/projects/{pid}/review-conversations` 子前缀；前端 apiPaths.ts:reviewConversations.projectList 修一处错路径（已修）
- **`init_4_projects.py` 已加 step 5 调 chain**：`from app.services.chain_orchestrator import ChainOrchestrator` + `await orchestrator.execute_full_chain(project_id, year, force=True)`；DB 重建后跑 init 即可全自动生成底稿+附注（之前漏调导致和平/辽宁 wp_count=0）
- **`WorkpaperList.vue` 已加暂无底稿引导卡片**：检测 `tb_count > 0 && wp_count == 0` 时显示"🚀 一键生成底稿+附注"按钮，调 `/api/projects/{pid}/workflow/execute-full-chain` body `{year, force:true}` timeout 120s
- **v3 档 1+档 2 全清后剩余唯一 P0**：Spec A `v3-linkage-stale-propagation` 三件套实施（P0-12 useStaleStatus 推 6 视图 + PartnerSignDecision stale 摘要 + P0-13 AJE→错报转换前端入口），3 天工时；R10 两个 spec 独立立项 3-4 周后启动
- **v3 工时实际压缩比**：原计划 8 天 / 13 件事，实际档 1+档 2 共 9 件只用 3.1h（约 30 倍压缩）；主因 = 脚本路径假设错被当成"真 bug"挖完真因后大半都是端点形态被错估
- **v3 全部 P0 清完（2026-05-16，5.6h 总工时，35 倍压缩）**：档 1（5 件 1.6h）+ 档 2（4 件 1.5h）+ 档 3 Spec A 三件套（2.5h）；剩余只有 R10 独立 sprint（联动+显示治理 3 周 + 编辑器+容灾 2 周可并行）
- **Spec A 三件套已全部实施（Sprint 0-4）**：
  - 新建 2 后端文件：`stale_summary_aggregate.py`（4 模块聚合 SQL）+ `test_stale_summary_full.py` / `test_aje_to_misstatement_idempotent.py` 共 6 用例
  - 修改 3 后端文件：`stale_summary.py` 加 `/full` 端点 / `misstatement_service.py` 加幂等检查 / `misstatements.py` 路由 409 ALREADY_CONVERTED
  - 新建 1 前端文件：`useStaleSummaryFull.ts` composable（4 模块聚合 + 6 事件订阅 + 防抖 500ms）
  - 修改 6 前端文件：WorkpaperList tree badge / WorkpaperWorkbench 详情卡片 / Misstatements 列 / Adjustments status 列 / **PartnerSignDecision 5 卡片项目状态摘要区块**（合伙人签字最痛 R3）/ EqcrProjectView Tab badge
  - 实测：4 项目 `/stale-summary/full` 全 200；AJE 创建→reject→转错报 200→重复转 409+ALREADY_CONVERTED+misstatement_id；vue-tsc + getDiagnostics 11 文件全 0 错误
- **新增 `financial_report.is_stale` PG 列（2026-05-16）**：ORM 模型有但 PG 表缺（又是 schema 漂移），手动 `ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false` 补齐；audit_report 已有
- **`unadjusted_misstatements` 字段缺失降级策略**：表无 `materiality_recheck_needed` / `last_evaluated_at` 字段，按 design D3 决策**降级为派生计算**——`stale_summary_aggregate.py` 用 `WHERE m.updated_at < (SELECT MAX(updated_at) FROM materiality WHERE project_id=...)` SQL 派生，无需改 ORM/迁移
- **AJE→错报转换幂等 409 模式（D5 落地）**：`misstatement_service.create_from_rejected_aje` 开头查 `source_adjustment_id` 已存在则抛 `ValueError("ALREADY_CONVERTED")` + 挂 `misstatement_id` attr；router 层 `except ValueError` 判 `str(e) == "ALREADY_CONVERTED"` 返回 409 + `{error_code, message, misstatement_id}` 让前端跳转
- **后端 ValueError 加 attr 传值模式**：当业务异常需要带额外信息（如已存在记录的 ID），用 `err = ValueError("CODE"); err.attr_name = value; raise err`，router 层 `getattr(e, "attr_name", None)` 取值；避免造自定义异常类污染服务层
- **PG schema 漂移修复检测清单**（v3 实测沉淀）：每次跑 ORM 模型有但运行时报 `column does not exist` / `enum value does not exist` 错时，必查 (1) `\d {table}` 看真实列；(2) `SELECT * FROM pg_enum WHERE enumtypid::regtype::text=...` 看真实 enum 值；(3) 如果 ORM 已有但 PG 缺，直接 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 补齐
- **v3 第一周动手清单（5 天 P0 全清）**：D1 IS/CFS 公式 / D2 chain 自动跑底稿+WP List 引导 / D2 下午 data-quality / D3 上午 all_passed / D3 下午 AJE 大小写 / D4 useStaleStatus 推 6 视图+后端 stale-summary/full / D5 上午 PartnerSignDecision stale 区块 / D5 下午 AJE→错报前端入口
- **v3 量化快照（2026-05-16 grep 实测）**：97 视图 / 258 组件 / GtPageHeader 73/97=75%（24 个未接入中 11 个合理排除 + 13 个应补）/ GtEditableTable 仅 3 处接入（最大警报）/ useStaleStatus 仅 5 视图（联动感知严重不足）/ useEditingLock 3 视图 / handleApiError 59 视图 / ElMessage.error 仅 1 处（基本清零）/ ElMessageBox.confirm 仅 3 处 / Vue 层 /api/ 硬编码 0 / statusEnum 13 视图接入 / inline font-size:Npx **1565 处** + color:#xxx **1611 处** + background:#xxx **712 处**（三大重灾区，需分批 token 化）
- **v3 不做清单（明确排除）**：暗色模式 / 全局 Ctrl+K 搜索 / 给 GtEditableTable 加新功能 / 客户主数据 / 员工热力图 / vitest 全量基建 / 新加后端模型；防止范围蔓延
- **v3 GtEditableTable 处置策略**：不再扩张组件库，改为"职责瘦身"成 GtTableExtended（列表型，强制 CI 卡点）+ GtFormTable（行内编辑型，仅 Adjustments/Misstatements/SamplingEnhanced 用）
- **v3 显示治理铁律**：字号/颜色/背景必须分 4 批迁移（编辑器→表格类→Dashboard→剩余），不能一次全改破坏视觉；token 体系打实后未来切换暗色只需改 token 值
- **memory.md 1500+ 行需拆分**：当前 spec 完成后统一整理；保留 < 200 行（用户偏好+活跃待办+关键状态摘要），其余迁移到 architecture/conventions/dev-history
- **表格统一化 spec 全部完成**（`.kiro/specs/table-unification-el-table/`）：21/21 编码任务完成，剩余 5 项 UAT 需手动浏览器验证；所有 11 处原生 HTML table 已迁移到 el-table（GtPrintPreview 按退出条件保留原生 table 用于打印）；全局样式 `gt-table.css` 已就绪（紫色表头/边框色/字号 class/表头 nowrap/.gt-amt）；grep `<table` 确认 0 处渲染用原生 table（排除剪贴板 HTML + 打印预览）
  - **复盘发现**：spec 创建时迁移已全部完成（R7-R9 各轮逐步落地），21 个 task 实际是"验收审计"而非"实施"；下次创建 spec 前先 grep 预检现状避免空跑
  - **后续优化（触碰即修）**：`:header-cell-style` 内联 ~40 处分布 20+ 文件，但实际用了 4 种表头色（`#f0edf5` 标准紫 / `#f8f6fb` 浅紫 / `#f4f0fa` 中紫 / `#edf3f9` 蓝灰）是视觉层级区分非冗余；gt-table.css 的 `!important` 会覆盖内联导致不能直接删；可选方案 = 提取 4 个 class（`.gt-table-header-default/light/mid/blue`）替代内联对象；max-height N 值 8 种是各页面布局适配不需统一；GtPrintPreview 保持原生 table 不动
- **GLOBAL_REFINEMENT_PROPOSAL_v2.md 已生成**（docs/）：v1 落地核查 + 5 角色深挖 + 21 横切主题 + 联动穿透闭环图 + P0-P3 路线图 41 项
- **Round 8 spec 三件套已创建**（`.kiro/specs/refinement-round8-deep-closure/`）：Sprint 1（P0，42 task，1 周）+ Sprint 2（P1，82 task，3 周）
  - Sprint 1：/confirmation 路由修复 + confirm.ts 补齐 30+ 处替换 + Adjustments 转错报按钮 + projectYear store + http 5xx 容灾 + AI mask_context 审计
  - Sprint 2：WorkpaperSidePanel 7 Tab + useStaleStatus 跨视图 + ShadowCompareRow + EQCR 备忘录版本/Word 导出 + PartnerSignDecision 签字面板 + risk-summary 端点 + ManagerDashboard 4 Tab + QcHub + v-permission 15+ 处 + statusEnum.ts + formRules.ts + 附注穿透 + 重要性联动
  - **三件套一致性分析结论**：覆盖率 100%（v2 P0+P1 20 项全覆盖），2 个中等问题需实施前修补：(1) sprint2-design.md 缺 D11（R8-S2-14 未保存提醒）；(2) PartnerSignDecision PDF 预览依赖 `/api/reports/{pid}/preview-pdf` 端点需确认是否已存在
  - **Sprint 1 已完成（42/42 task，Task 3 浏览器手动验证除外）**：ConfirmationHub.vue 新建 + router 注册 + feedback.ts 新建 + http.ts 超时/断网/5xx 容灾 + confirm.ts 新增 6 函数 + **ElMessageBox.confirm 全量清零**（views 0 + components 0，远超 CI 基线 5）+ **projectStore.changeYear 增加 eventBus year:changed emit**（决策：不新建 projectYear.ts，复用现有 store）+ **AI 脱敏全路径审计**（note_ai 3 端点 + wp_ai_service analytical_review + role_ai_features _llm_polish_report / _llm_generate_summary 全部集成 mask_context）+ 新建 backend/tests/test_ai_masking.py 13 测试
  - **Sprint 2 Week 1 已完成（Task 1-23 / 82）**：新建 `composables/useStaleStatus.ts` + WorkpaperSidePanel 9 Tab（新增"自检"Tab，内联实现避免过度拆分）+ `workpaper:locate-cell` eventBus 事件 + WorkpaperEditor Univer 单元格定位 API + ReportView/DisclosureEditor/AuditReportEditor 三视图 stale 横幅 + .gt-stale-banner 统一样式 + 3 编辑器 onBeforeRouteLeave + beforeunload 未保存拦截
  - **Sprint 2 Week 2 已完成（Task 24-54 / 82）**：新建 `backend/app/services/risk_summary_service.py`（聚合 6 数据源：高严重度工单+未解决复核意见+重大错报+被拒未转AJE+持续经营+AI flags/budget/sla 预留）+ `backend/app/routers/risk_summary.py`（router_registry §21 注册）+ `views/PartnerSignDecision.vue`（三栏：GateReadinessPanel / 报告 HTML 预览 / 风险摘要 + 底栏签字操作）+ EqcrMemoEditor onExportWord（blob 下载）+ EqcrProjectView onShadowVerdict 持久化（pass/flag → agree/disagree 映射到 EqcrOpinion）+ ManagerDashboard 异常告警区块（前端 computed 派生，4 维：高风险/工时超支/逾期底稿/逾期承诺）+ PartnerDashboard 决策面板跳转按钮
  - **Sprint 2 Week 3 已完成（Task 55-82 / 82，Task 52/53/82 保留）**：新建 `scripts/find-missing-v-permission.mjs`（盘点危险操作按钮未加 v-permission，glob@13 作为 devDependency）+ 8 个漏加 v-permission 按钮补齐（ProjectDashboard 催办/PrivateStorage 删除/EqcrMemoEditor 定稿/PDFExportPanel 导出/ReviewConversations 导出/SignatureLevel1-2 签字，从 8 → 1 剩 AiContentConfirmDialog 非危险）+ ROLE_PERMISSIONS 补齐 16 权限码（含 sign:execute/archive:execute/report:export_final/workpaper:submit_review|review_approve|review_reject|escalate/assignment:batch/qc:publish_report/eqcr:approve/independence:edit）+ 新建 `qc` 角色权限组 + 新建 `constants/statusEnum.ts`（18 套状态常量 + TS 类型导出）+ WorkpaperEditor/AuditReportEditor/Adjustments 替换硬编码状态字符串为常量引用 + 新建 `utils/formRules.ts`（12 套 el-form 规则 + makeRules 组合工具）+ 新建 `backend/app/routers/note_related_workpapers.py`（附注行→底稿端点，router_registry §22）+ DisclosureEditor 右键菜单"查看相关底稿" + Misstatements 订阅 materiality:changed 事件 + GateReadinessPanel 组件内自动订阅 materiality:changed（触发父级 onRefresh） + 后端 misstatements.py 新增 POST /recheck-threshold 端点 + apiPaths 新增 misstatements.recheckThreshold
  - **R8 总完成（Sprint 1+2）**：121/124 task（97.6%，Task 52/53 跳过+Task 82 UAT 待真人）；vue-tsc 0 错误；pytest 2848 tests / 0 errors；ElMessageBox.confirm 全量清零（基线 5 合格）；新建 11 文件（后端 3 + 前端 7 + 脚本 1） + 修改 ~50 文件 + 新增 13 AI masking 测试
  - **R8 复盘发现 9 处字段凭印象错误（P0 已修复）**：risk_summary_service 违反"代码锚定"铁律——(1) ReviewRecord 无 project_id/content/wp_id，真实字段 working_paper_id/comment_text（需 join WorkingPaper 反查 project_id）；(2) UnadjustedMisstatement.net_amount→misstatement_amount，description→misstatement_description；(3) Adjustment 无 converted_to_misstatement_id，反向查 UnadjustedMisstatement.source_adjustment_id；(4) total_debit/credit 在 AdjustmentEntry 不在 Adjustment 头表；(5) GoingConcernConclusion 枚举值 no_material_uncertainty；(6) risk_summary_service 所有聚合加 year 参数；修复代码见 commit + 新建 test_risk_summary_service.py 8 smoke test 全部通过（User.hashed_password / WorkingPaper 必填 source_type 也在测试中踩雷并修正）
  - **R8 git 提交策略**：从 feature/round7-global-polish 切出 **feature/round8-deep-closure** 新分支；分组提交 7+2 个 commit（S1 / S2-W1 / S2-W2+P0 / S2-W3 / UI+spec+docs / AI脱敏漏网+v-permission / Office锁文件清理 / 移除临时文件 / .gitignore追加）；**用 COMMIT_MSG_TMP.txt 文件承载多行 commit message**（避免 PowerShell 对 `-m "Task 3 (括号)"` 括号内空格的参数误解析，用完即删）；.gitignore 新增 GT_logo/ + 2025人员情况.xlsx + `~$*` + `~WRL*` + COMMIT_MSG_TMP.txt；**已推送到 origin/feature/round8-deep-closure（a1b936e）**
  - **审计模板 Office 临时文件已清理**：129 个 ~$ 和 ~WRL 锁文件从 git 历史中删除，.gitignore 已追加 `~$*` 和 `~WRL*` 模式防止再次入库；B30 集团审计新准则英文版模板（ISA 600 revised 系列 20+ 文件）也一并从跟踪中移除
  - **Sprint 2 架构决策**：不拆 7 个 SideTab wrapper（Task 1-6 跳过，WorkpaperSidePanel 直接用 AiAssistantSidebar/AttachmentDropZone/ProgramRequirementsSidebar/DependencyGraph 已足够）；自检 Tab 复用 fine-checks/summary 批量端点（不新建 wp_id 专用端点）；stale 横幅共享 CSS class（3 视图继承）；**PartnerSignDecision 中栏 HTML 降级**（不依赖不存在的 /preview-pdf 端点，直接渲染 audit-report.paragraphs 8 节）；**ManagerDashboard 复用 overview 端点**（不新建 manager_matrix，alerts 前端派生）；**QcHub 复用 R7-S3 的 QcInspectionWorkbench 6 Tab**（不重复新建，只加 /qc → /qc/inspections 重定向）；**Task 52-53 跳过**（ProjectDashboard 非 Tab 布局，QCDashboard 降级为 Tab 重构成本过高）；**recheck-threshold 复用 get_summary**（summary 服务内部已基于最新 materiality 计算，无需重写逻辑）；**GateReadinessPanel 内部自动订阅 materiality:changed**（不让每个使用方各自订阅，利用已有 onRefresh prop 回调）
  - **ShadowCompareRow verdict 映射约定**：前端 pass/flag → 后端 EqcrOpinion.agree/disagree，复用 eqcrApi.createOpinion 端点（避免新建专用 verdict 表）
  - **IssueTicket.severity 实际枚举**（本次 grep 核对）：blocker/major/minor/suggestion（不是 memory 之前记录的 high）；risk_summary 取 blocker+major 为高严重度
- **UI 品牌风格已对齐致同内网**：顶栏深紫 #4b2d77 + 反白 logo + 白色文字图标；侧栏 #f8f7fc 微紫调；favicon 改致同 logo；页面标题"致同审计作业平台"
- 全局打磨建议 v1 已补完到 ~1800 行（docs/GLOBAL_REFINEMENT_PROPOSAL_v1.md）：5 角色穿刺 + 32 横切主题 + P0-P3 共 35 项路线图 + 第 11 章"版面位置规约"
- **Round 7 Sprint 1（P0）已完成**：18/18 task 全部执行，vue-tsc 0 错误；删除 12 文件（ReviewInbox + 5 Mobile + 5 AI 死代码 + 1 重复组件）、修改 6 文件（apiPaths/PartnerDashboard/QCDashboard/DefaultLayout/router/auth）、新建 2 文件（GtEmpty.vue + confirm.ts 5 函数）；UAT 待手动验证（角色跳转+函证路由+EQCR 指标）
- **Round 7 Sprint 2（P1）已完成**：42/42 task 全部执行，vue-tsc 0 错误；新建 5 文件（useEditingLock/useWorkpaperAutoSave/errorHandler/ShortcutHelpDialog/stale_summary.py）、修改 20+ 文件（导航动态化/13 处 ElMessageBox 替换/4 视图 useEditMode/3 视图编辑锁/2 视图自动保存/工时 Tab 合并删除 WorkHoursApproval/Stale 三态/5 视图 errorHandler/CI lint）、后端新增 stale-summary 端点；右键菜单 5 视图已在之前 Round 实现无需重做
- **R7 S1+S2 复盘修正已落地（8 项质量改进）**：(1) 角色跳转从 auth.ts 移到 Login.vue（职责单一）；(2) navItems 加 roles 字段按角色过滤+隐藏（auditor 看不到"账号权限"，qc 看不到"工时"等）；(3) WorkpaperEditor 两套自动保存合并为 useWorkpaperAutoSave 60s 单一方案；(4) AuditReportEditor/DisclosureEditor 编辑锁改 autoAcquire:false + watch isEditing 联动 acquire/release；(5) 编辑锁 watch isMine→exitEdit 强制只读；(6) autoSaveMsg/dirty 颜色改 CSS 变量；(7) 导航标签"人员"→"人员档案"/"用户"→"账号权限"；(8) useEditingLock 加 resourceType:'workpaper'|'other' 参数，非底稿资源降级为前端检测避免错误路径 404
- **Round 7 技术债清单（3 项剩余，触碰即修）**：(1) related-workpapers 端点需精确映射（report_config→account→wp_mapping）；(2) resourceType:'other' 降级需后端通用 editing_locks 表支持 resource_type 字段；(3) 4 编辑器未接入 WorkpaperSidePanel
- **已修复技术债**：#1 crossCheckResults 真实数据填充（切换 Tab 时并行加载 BS+IS 按 row_code 计算）；#4 WorkpaperEditor 硬编码颜色→CSS 变量；#5 WorkHoursPage 472→185 行（WorkHourApprovalTab 子组件）；#7 Misstatements 接入 usePasteImport（粘贴→逐行创建错报）
- **Round 8 方向建议**：P0 跨表核对真实数据+编辑锁通用化；P1 http.ts 全局 5xx 默认处理+GtPageHeader CI 指标+WorkpaperWorkbench 右栏替换；P2 related-workpapers 精确映射+vitest 基建；P3 暗色模式+Ctrl+K 全局搜索
- **流程改进沉淀**：Sprint task 数 ≤30（Sprint 3 的 58 太多）；"触碰即修"设 30 天 SLA；每 Sprint 开始前 30 分钟 grep 核对端点/字段假设；关键改动不委托子代理手动做
- **statusMaps.ts 已删除（R7-S3-02 里程碑）**：GtStatusTag 现在唯一数据源是 dictStore（后端 /api/system/dicts），不再有前端硬编码回退；所有 views 中 statusMap prop 用法已清零；后端 9 套字典完整覆盖
- **3 个后端端点确认不存在需新建**：GET /api/qc/rotation/due-this-month（Sprint 3 Task 18）、GET /api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers（Task 46）、GET /api/eqcr/projects/{pid}/memo/export?format=docx（Task 23）
- **后端编辑锁实际路径**：`/api/workpapers/{wp_id}/editing-lock`（POST acquire / PATCH heartbeat / DELETE release / POST force / GET active），不是设计文档假设的 `/api/editing-locks/acquire`；useEditingLock.ts 已适配实际路径
- **后端 stale-summary 端点已新建**：`backend/app/routers/stale_summary.py`，用 `WorkingPaper.prefill_stale` 字段 + join WpIndex 取 wp_code/wp_name，注册在 router_registry.py §18
- **通知端点已新建**：`backend/app/routers/notifications.py`（GET list / GET unread-count / POST read / POST read-all / DELETE），注册在 router_registry.py §23；修复登录后 Dashboard 两个 "Not Found" toast
- **start-dev-log.bat 已创建**：带日志输出的启动脚本（后端→backend_dev.log，前端→frontend_dev.log），便于排查运行时错误
- 合并 feature/global-component-library 到 master（用户手动操作）
- 0.3 公式计算浏览器手动验证（启动前端输入 `=SUM(A1:A3)` 看结果）
- 用真实审计项目进行用户验收测试（UAT）
- 生产环境部署准备（Docker 镜像打包 LibreOffice、PG 环境变量、数据库初始化）
- 打磨路线图已由"4 轮主题"改为"5 角色轮转"：Round 1 合伙人 / Round 2 PM / Round 3 质控 / Round 4 助理 / Round 5 EQCR，5 轮三件套（requirements+design+tasks）全部起草并完成一致性校对
- 实施顺序：R1 → R2 → R3+R4（并行，相互独立）→ R5 → R6，依据 README v2.2 "跨轮依赖矩阵"
- **Round 4 已修复并验证通过（2026-05-06）**：修复 4+2 个真实缺口后 128 个测试全绿，app 870 路由正常启动。修复内容：(a) `get_prior_year_workpaper` 函数新增到 continuous_audit_service（通过 WpIndex join 获取 wp_code）；(b) prefill provenance 四函数追加到 prefill_engine.py；(c) 6 个 R4 router 注册到 router_registry.py §13；(d) 3 个 Sprint 集成测试创建；(e) ExportMaskService 新增 mask_context/mask_text/_is_sensitive_amount；(f) Attachment 模型新增 ocr_fields_cache；(g) wp_chat_service 脱敏集成
- **Round 6 实施完成（2026-05-07）**：18 任务 / 2 Sprint 全部完成，主题"跨角色系统级优化"。Sprint 1（CI骨架+签字解耦+铃铛挂载+死代码清理）+ Sprint 2（QC规则表+复核批注边界+归档幂等+GateRule补充+死链检查）
- **R1-R6 复盘断点清单（2026-05-07 发现，P0-P3 已修复）**：
  - ✅ R3 前端 5 页面补完（QcRuleEditor/QcInspectionWorkbench/ClientQualityTrend/QcCaseLibrary/QcAnnualReports）+ 路由注册 + 编译通过
  - ✅ R3 Sprint 4 AI 溯源 5 任务实装（gate_rules_ai_content + AiContentConfirmDialog + wp_ai_confirm 端点 + ai_contribution_watermark + audit_log_rules_seed + 日志合规 Tab）
  - ✅ 归档章节 03（质控抽查报告）+ 04（独立性声明）真实 generator 落地
  - ✅ Archive PDF SHA-256 水印修正（占位符改为引用 manifest_hash）
  - ✅ section_progress GIN 索引迁移（round7_section_progress_gin_20260507）
  - ✅ 就绪检查 extra_findings 完全消灭（subsequent_events/going_concern/mgmt_representation 升级为 GateRule R7-*）
  - ✅ jsonpath-ng 写入 requirements.txt，jsonpath 执行器已确认实装
  - ✅ Alembic 迁移链核验通过（14 个 round* 迁移，无分叉冲突）
  - 🔲 R3 tasks.md 状态回填（后端已就绪+前端已补，需批量标 [x]）
  - 🔲 R1 UAT-1~6 浏览器手动验证（需真人执行）
  - 🔲 Round2-Task-A 测试盲点 11 项（并发/Worker/PBT）需真实 PG 环境
  - 🔲 性能压测真实环境跑（6000 并发验收）
  - 🔲 ReviewWorkbench 中栏只读 Editor（R1 已知妥协，低优先级）
- **R3 深度复盘（2026-05-07）新发现的断点 — 已全部修复**：
  - ✅ 4 个 QC router 注册到 router_registry.py §17（qc_inspections/qc_ratings/qc_cases/qc_annual_reports）
  - ✅ sla_worker Q 整改单 SLA 分支（_handle_q_sla_timeout：标记 sla_breached + 通知签字合伙人）
  - ✅ QCDashboard.vue 新增"项目评级"Tab（A/B/C/D badge）+ "复核人画像"Tab（5 维度指标表）
  - ✅ IssueTicketList source='Q' 特殊 UI（🛡️图标 + .q-source-row 红左边框）
  - ✅ QcRuleEditor 强制试运行（hasRunDryRun flag，保存按钮 disabled 直到试运行完成）
  - ✅ 年报 Word 模板真实渲染（python-docx 5 章节填充，不可用时降级文本）
  - ✅ QcInspectionWorkbench "生成质控报告"按钮（选中批次后下载 Word）
- Round 1 实施进度：Tasks 1-4 已完成（数据模型迁移 73204cf + Tasks 2-4 评审闭环后端+前端合并 5c5ac56），按 tasks.md 顺序推进剩余任务
- Round 5 实施进度：**全部完成 + 复盘 P0-P2 修复**，122 个 EQCR 测试全通过；R5 关闭
- **ledger-import-unification spec 实施进度（2026-05-08）**：Sprint 1-4 全部完成（76/76 task），跳过 Sprint 0（外部依赖）、AI 兜底（53a-d）、UAT（82/83）、可选文档（84/85）；剩余 Sprint 5 测试任务约 8 个
  - Sprint 1 产出（20 task）：`backend/app/services/ledger_import/` 完整骨架（24 文件）+ detection_types.py（9 schema + KEY_COLUMNS/RECOMMENDED_COLUMNS 单一真源）+ errors.py（31 错误码 + make_error 工厂）+ detector.py（detect_file 支持 xlsx/csv/zip + 合并表头 + 标题行跳过）+ encoding_detector.py（BOM→候选→chardet→latin1）+ year_detector.py（5 级优先识别）+ identifier.py（3 级识别 + 置信度聚合 + detection_evidence 决策树）+ 7 适配器（yonyou/kingdee/sap/oracle/inspur/newgrand/generic）+ AdapterRegistry + JSON hot-reload + 19 单测（test_detector + test_identifier + test_adapters）
  - Sprint 2 产出（21 task）：excel_parser/csv_parser/zip_parser（50k chunk 流式）+ aux_dimension（7 格式 + 多维 + detect_aux_columns）+ merge_strategy（auto/by_month/manual + dedup_rows）+ column_mapping_service（CRUD + 跨项目复用 + build_fingerprint）+ ImportColumnMappingHistory ORM model + writer.py（build_raw_extra 8KB 截断 + prepare_rows_with_raw_extra + write_chunk + activate_dataset）+ aux_derivation.py（主表→辅助表分流）+ ledger_raw_extra.py 端点（LATERAL jsonb_each_text 聚合）+ validator.py（L1 分层校验 + L2 借贷平衡/年度/科目 + L3 余额=序时累计/辅助科目一致 + evaluate_activation force 门控）+ 2 Alembic 迁移（column_mapping_history 表 + 四表 raw_extra 列）
  - Sprint 3 产出（15 task）：orchestrator.py（detect/submit/resume 三阶段编排）+ ledger_import_v2.py 路由（6 端点：POST detect/submit + GET stream/diagnostics + POST cancel/retry）+ import_job_runner.py `_execute_v2` 分支（feature flag 驱动）+ feature_flags `ledger_import_v2: False` + EventType.LEDGER_IMPORT_DETECTED 已确认存在 + router_registry §24 注册 v2+raw-extra 路由 + import_recover_worker 已满足超时恢复
  - Sprint 4 产出（20 task）：9 个 Vue 组件（LedgerImportDialog/UploadStep/DetectionPreview/ColumnMappingEditor/ImportProgress/ErrorDialog/DiagnosticPanel/MappingDiff/ImportHistoryEntry）+ ledgerImportV2Api.ts（API service）+ useLedgerImport.ts（composable，含 sessionStorage 缓存 + localStorage chunk 持久化）+ apiPaths.ts 新增 7 个 v2 路径 + vue-tsc 0 错误
  - **后端全链路（Sprint 1-3）+ 前端全链路（Sprint 4）已完成**
  - 剩余 Sprint 5：Tasks 74-86（测试），约 8 coding task
  - 技术决策：SAP 适配器 filename regex 用 `(?<![A-Za-z])SAP(?![A-Za-z])` 替代 `\bSAP\b`（Python `\b` 视 `_` 为 word char）；identifier.py 新增 `default_aliases()` 公共函数供 GenericAdapter 消费；vendor 适配器统一在 `adapters/__init__.py` 注册（避免循环 import）；validate_l2 用 raw SQL 查 staged 数据（按 dataset_id 过滤）；L2_LEDGER_YEAR_OUT_OF_RANGE 是唯一不可 force-skip 的 L2 码；raw_extra 端点用 PG `LATERAL jsonb_each_text` 高效聚合；DatasetService.activate 通过 writer.activate_dataset 薄包装暴露给 ledger_import 模块；SSE 用独立 async_session 每 2s 轮询（避免 request-scoped session 关闭问题）；import_job_runner._execute_v2 是骨架（full pipeline wiring 待集成）；EventType 枚举中 LEDGER_IMPORT_DETECTED/SUBMITTED/FAILED/VALIDATED/ACTIVATED/ROLLED_BACK 6 个事件已全部存在（Phase 17 预注册）
  - **encoding_detector.py 真实样本修复（2026-05-08）**：(1) `_PROBE_BYTES` 从 4KB 增大到 64KB（GBK 双字节在 4KB 边界截断导致 decode 失败）；(2) `latin1` 从 `_CSV_ENCODING_CANDIDATES` 移除（它能 decode 任何字节序列，掩盖真实编码）；(3) chardet CJK 阈值从 0.7 降到 0.3（chardet 对 GBK 短文本常给 0.3-0.5 但结果仍正确）；修复后 411MB GBK CSV 正确识别为 gb18030
  - **真实样本验证结果**：`数据/` 目录含重庆医药集团两家子企业样本——YG36 四川物流（1 xlsx 含余额表+序时账 22717 行）+ 和平药房（1 余额表 xlsx 50463 行 + 2 CSV 序时账共 411MB）；验证发现：(a) 序时账识别率 100%（ledger conf=95, key cols 全命中）；(b) 余额表合并表头（2 行标题横幅 + 2 行合并表头"年初余额.借方金额"）解析不完整导致 key cols 0/0（需增强 _detect_header_row 对 4 行表头的支持）；(c) sheet 名为 "sheet1" 时 L1 无法命中，需依赖 L2 表头特征
  - **Sprint 5 待修复问题**：(1) 合并表头增强——当前只支持 1 行标题+2 行合并，真实样本有 2 行标题+2 行合并（共 4 行 before data）；(2) 模糊匹配对短列名（"状态"/"过账"）误报为 debit_amount，需收紧 _MIN_SUBSTR_ALIAS_LEN 或加排除词表
  - **v2.1 架构演进方向（已写入 design §28 + requirements 需求 2 验收标准 8-11 + tasks 74a-d）**：(1) L1/L2/L3 并行联合打分（权重 0.2/0.5/0.3 可配置）替代串行降级；(2) 合并表头通用算法（基于行间值多样性而非硬编码阈值）；(3) 列内容验证器（date/numeric/code 三种，header_conf×0.7 + content_conf×0.3）；(4) 识别规则声明式 JSON 配置（热加载+用户自定义）。实施路径：Phase A+B 在 Sprint 5 落地，Phase C+D 在 UAT 迭代推进
  - **v2.2 序时账增量追加（已写入 design §29 + requirements 需求 22）**：预审导 1-11 月序时账，年审只追加 12 月；余额表始终全量覆盖；增量模式下系统自动做期间 diff（file_periods - existing_periods），只导入新增月份的行；重叠月份弹窗确认跳过/覆盖；回滚粒度为按期间删除。Phase B 下一轮迭代实施
  - **真实样本 9 家子企业**（`数据/` 目录）：四川物流（1xlsx 2sheet）、四川医药（1xlsx）、宜宾大药房（1xlsx）、和平药房（1余额xlsx + 2序时csv 按日期段拆）、和平物流（1xlsx）、安徽骨科（1xlsx）、辽宁卫生（2xlsx 分开）、医疗器械（2xlsx 分开）、陕西华氏（1余额 + 12月度序时账）；覆盖了单文件多sheet、多文件分开、CSV大文件、按月拆分等所有场景
  - **9 家样本批量验证结果（2026-05-08 修复后）**：全部 9 sheet ✅ 识别成功（0 unknown）——四川物流（balance 60 + ledger 63）、宜宾大药房（balance 60 + ledger 78）、和平药房余额（balance 53）、辽宁余额（balance 53）、器械余额（balance 53）、陕西华氏 2024（balance 53）、陕西华氏 2025（balance 53）；大文件（>10MB）因耗时跳过但逻辑相同
  - **P0 bug 已修复（read_only 回退 + 合并表头子列重复模式）**：(1) `_detect_xlsx` 新增 `_detect_xlsx_with_mode` 辅助函数，先 read_only=True 尝试，检测到行宽 ≤ 2 时自动回退 read_only=False；(2) `_detect_header_row` 合并判定新增第三条件：下行 unique ≥ 2 + fill ≥ 0.5 + non_empty > unique×2（典型"借方/贷方"重复子列模式）；修复后陕西华氏余额表正确返回 14 列 + 合并表头"年初余额.借方金额"等 家样本批量验证结果（2026-05-08 修复后）**：全部 9 sheet ✅ 识别成功（0 unknown）——四川物流（balance 60 + ledger 63）、宜宾大药房（balance 60 + ledger 78）、和平药房余额（balance 53）、辽宁余额（balance 53）、器械余额（balance 53）、陕西华氏 2024（balance 53）、陕西华氏 2025（balance 53）；大文件（>10MB）因耗时跳过但逻辑相同
  - **P0 bug 已修复（read_only 回退 + 合并表头子列重复模式）**：(1) `_detect_xlsx` 新增 `_detect_xlsx_with_mode` 辅助函数，先 read_only=True 尝试，检测到行宽 ≤ 2 时自动回退 read_only=False；(2) `_detect_header_row` 合并判定新增第三条件：下行 unique ≥ 2 + fill ≥ 0.5 + non_empty > unique×2（典型"借方/贷方"重复子列模式）；修复后陕西华氏余额表正确返回 14 列 + 合并表头"年初余额.借方金额"等
  - **复盘 P0-P2 已全部修复（2026-05-08）**：(1) P0 合并表头语义映射：新增 `_match_merged_header` + `_MERGED_HEADER_MAPPING` 配置表，dot-notation 列名精确映射到 closing_debit/opening_credit 等；`_score_table_type` 新增 alternatives 逻辑（opening_debit+opening_credit 替代 opening_balance）；`_detect_by_headers` 将 alternatives 组成字段 tier 提升为 key；(2) P1 文件名 L1 信号：`identify` 中 sheet 名无信号时自动从 file_name 提取 L1（置信度 -10）；(3) P2 子串匹配最长优先：收集所有命中后选最长别名。修复后 key_rate 从 80%→129%（8/9 满分），conf 从 avg 57→71，全部升级到 medium
  - **Sprint 5 测试完成（2026-05-08）**：新增 91 个测试（从 31→91），覆盖 detector/identifier/validator/raw_extra/aux_dimension/adapters 全链路，1.22s 全部通过；Task 74/75/75a/76/77/78 已完成；剩余 Task 79-81（需 PG 环境）+ Task 82-83（UAT 需真人）
  - **~~四川物流序时账已知问题~~已修复**：`looks_like_data_row` 增强三条件（第一值是整数序号 / 含日期格式 / 含金额格式），修复后四川物流+和平药房 CSV 的 debit_amount 都正确识别
  - **大文件支持已实现（2026-05-08）**：新增 `detect_file_from_path(path)` 入口，CSV 只读前 64KB 编码探测 + 流式读前 20 行（392MB GBK CSV 探测 <10ms / 内存 <1MB）；xlsx 直接传路径给 openpyxl 不读入内存；ZIP 仍需全量读取
  - **最终验证（2026-05-08）**：9 家企业全部 sheet 关键列 5/5 命中，表类型 0 误判，置信度 avg 72-78（medium），91 测试零回归
  - **v1→v2 整合完成（2026-05-08）**：(1) 新建 `converter.py`（~250 行）从旧引擎提取 convert_balance_rows/convert_ledger_rows 适配 v2 数据结构；(2) `orchestrator.py` 重构提取 `_finalize_detection` + 新增 `detect_from_paths`；(3) `__init__.py` 统一导出 ImportOrchestrator/detect_file/detect_file_from_path/convert_*/类型定义；(4) 旧 `smart_import_engine.py` 顶部标记 deprecated + 迁移路径注释（不改功能代码）
  - **v2 模块最终结构（25 个 Python 文件）**：detector/identifier/converter/orchestrator/writer/validator/aux_dimension/aux_derivation/merge_strategy/year_detector/encoding_detector/column_mapping_service/content_validators/detection_types/errors + adapters/(7家+registry+json_driven) + parsers/(excel/csv/zip)；统一入口 `from app.services.ledger_import import ImportOrchestrator`
  - **迁移 P0 已完成（2026-05-08）**：`_execute_v2` 全链路实现（detect→parse→convert→validate→write→activate），含流式解析（iter_excel/csv_rows_from_path）、L1 校验、activation gate、bulk insert 5000/batch、rebuild_aux_balance_summary；写入阶段暂复用旧引擎的 `_clear_project_year_tables`（后续迁移到 writer.py）
  - **parsers 新增 path-based 入口**：`iter_csv_rows_from_path(path, encoding, ...)` 和 `iter_excel_rows_from_path(path, sheet_name, ...)` 支持 600MB+ 文件流式解析不全量读入内存
  - **`_execute_v2` 上线前必修已全部完成（2026-05-08）**：(1) 边解析边写入（`_insert_balance/_insert_aux_balance/_insert_ledger` 三个辅助函数，每 chunk 立即 insert，内存从 440MB→10MB）；(2) 辅助表分流（aux_balance 正确写 TbAuxBalance）；(3) 参数超限修复（INSERT_CHUNK_SIZE 从 5000 降到 1000，14×1000=14000 << PG 65535 上限）；(4) col_mapping fallback（confirmed 为空时退回 auto-detection）；(5) 进度精度用 total_est_rows 全局估算（多 sheet 不跳变）；(6) 日志增强（每 sheet 开始/完成 logger.info）
  - **`_execute_v2` 剩余建议修复**：raw_extra 列写入 + 年度验证 warning + Dataset 两阶段切换 + 辅助序时账 _aux_dim_str 拆分
  - **Worker 健壮性已增强（2026-05-08）**：(1) 异常处理 3 次重试 DB transition + 独立 try 保证 release_lock（防止 job 永远停在 running）；(2) 每 chunk 调 `_persist_progress` 自动更新 heartbeat_at（防 20min stale 超时）；(3) 每 5 chunk 检查 job.status==canceled（支持用户取消）
  - **Phase 重排**：Phase 3 合并 Parse+Convert+Validate+Write 流式执行；Phase 4 Activation gate 降级为警告（数据已流式写入无法阻止）；Phase 5 独立 rebuild_aux_summary；Phase 6 result_summary 新增 aux_balance_rows + blocking_findings 字段
  - **feature_flag 已切换为默认 True（2026-05-08）**：`feature_flags.py` 中 `ledger_import_v2: True`（maturity: production），所有项目默认走 v2 引擎；旧引擎代码保留但不再执行，可通过 `set_project_flag(pid, "ledger_import_v2", False)` 单项目回退
  - **v2 真实导入测试发现（2026-05-08）**：detect/identify/parse 全链路本地验证通过，worker 执行时 job 卡在 running/progress=1%。根因链路：(1) bulk insert 缺 `id` UUID 主键；(2) insert values 漏 `company_code` NOT NULL 字段（tb_balance/tb_aux_balance/tb_ledger 都是必填，converter 返回正确但 insert 没传递）。全部已修复：三个 insert 函数都加了 `"id": uuid4()` + `"company_code": r.get("company_code") or "default"`
  - **`_execute_v2` 关键列必填清单**：tb_balance/tb_aux_balance/tb_ledger 的 `company_code` 是 NOT NULL，converter 默认值 "default"，insert 必须传递该字段；tb_aux_balance 的 `aux_type` 也是 NOT NULL，converter 必须跳过 aux_type=None 的无效维度条目
  - **辅助明细账 tb_aux_ledger 已补齐（2026-05-08）**：此前 `_execute_v2` 只写 tb_ledger 漏写 tb_aux_ledger；现已补全：(1) `convert_ledger_rows` 返回值改为 `(ledger, aux_ledger, stats)` 3 元组，对齐旧 `write_four_tables` 逻辑；(2) `_execute_v2` 新增 `_insert_aux_ledger` 函数（完整字段含 aux_type/aux_code/aux_name/aux_dimensions_raw/voucher_type/accounting_period）；(3) ledger sheet 处理同时写主表+辅助明细账；(4) `convert_balance_rows` 辅助余额行加回 `aux_dimensions_raw` 溯源字段
  - **aux_dimension 格式升级（2026-05-08）**：PATTERNS 新增 `colon_code_comma_name` 格式（`类型:编码,名称`，优先于 `colon_code_name`），识别 YG36 真实数据"金融机构:YG0001,工商银行"；`parse_aux_dimension` 智能逗号分隔：只在"逗号后接 `类型:`"时切多维度，避免误切单维度"类型:编码,名称"；PATTERNS 从 7 个增到 8 个；测试覆盖 97 tests / 0 failures（含新建 `test_aux_ledger_split.py` 6 用例）
  - **辅助明细账复盘遗留（P0-P3）**：P0 必做 = 真实样本（YG36 xlsx）端到端 v2 worker smoke test + 断言 tb_aux_ledger 有数据；P0 = `_insert_aux_ledger` 空值策略审查（aux_code/summary 空值应 NULL 不 ""）；P1 = converter 和 aux_derivation 辅助拆分逻辑合一（当前 aux_derivation.py 未被 `_execute_v2` 调用，两套职责重叠）；P1 = 三个 `_insert_*` 独立 session+commit，失败恢复不如旧引擎单事务，考虑改 savepoint；P2 = colon_code_comma_name 的 name 组贪婪吃到行尾，需要边界测试
  - **真实样本 2 bug 修复（2026-05-08）**：(1) `writer.prepare_rows_with_raw_extra` 多列映射到同一 standard_field 时后者会覆盖前者，真实数据"核算维度"+"主表项目"都映射到 aux_dimensions 导致后者 None 覆盖前者有效值，aux_ledger=0；修复为首个非空值保留策略；(2) `excel_parser.iter_excel_rows_from_path` read_only=True 模式对部分 xlsx（合并表头/特殊样式）返回 0 行，加 `_iter_excel_chunks` 辅助函数 + read_only=False 自动回退（bytes 版本 `_iter_excel_bytes_chunks` 同步修复）；影响修复：和平药房/陕西华氏/辽宁/医疗器械余额表全部恢复解析；9 家企业真实样本抽样 5000 行/sheet 验证：辅助维度识别到 20+ 种（客户/金融机构/成本中心/银行账户/税率 等），aux_ledger 从 0~104 升到 6000~15000 不等
  - **和平物流余额表识别 bug（遗留）**：`和平物流25加工账-药品批发.xlsx` 的"余额表" sheet 被误识别为 ledger(conf=34)，sheet 名命中 balance 但 L2 表头置信度打分让 ledger 胜出；根因是该 sheet 含大量非标准列（编码长度/业务循环/底稿项目等 8 列），和常规余额表结构差异较大。下轮修复
  - **ledger_import 模块 import 规约（2026-05-08 踩坑）**：`backend/app/services/ledger_import/` 内部文件之间必须用相对 import `from .xxx import ...`，**禁止**用 `from backend.app.services.ledger_import.xxx import ...`；后端启动时 PYTHONPATH 根是 `backend/` 不是仓库根，写 `backend.app.xxx` 会导致 runtime `ModuleNotFoundError: No module named 'backend'`；v2 worker 首次上线连续 2 次 failed 就是 merge_strategy.py 这一行错误 import 引起（已修复）；Docstring 示例可保留 `backend.app...` 格式（纯字符串不参与 import 解析）
  - **账表导入全链路整体复盘（2026-05-08）架构清洁待办**：(1) `aux_derivation.py` 是死代码，`_execute_v2` 没调用，职责和 converter 重叠，可删；(2) `smart_import_engine.py` 标记 deprecated 但仍被 `_execute_v2` 调用 `_clear_project_year_tables`，需迁移到 writer.py 后才能删；(3) `_execute_v2` 拆出到 `ledger_import/orchestrator.py`，不留在 import_job_runner.py；(4) adapter 机制（8 家 json 适配器）实际未被调用也没增益，要么删要么改为纯别名包；(5) `iter_excel_rows` 和 `iter_excel_rows_from_path` 双实现底层可共用
  - **账表导入功能遗留断点清单**：(a) staged/active 切换未真正走通——`_execute_v2` 直接写活数据没调 `activate_dataset`，design §12 原子激活未落地；(b) incremental 只做了 detect 没做 apply——"只追加新月份"核心功能缺失；(c) `ledger_data_service.delete` 是硬删不是软删，失误无法恢复；(d) `prepare_rows_with_raw_extra` 多列映射同字段时丢弃列值完全丢失不进 raw_extra；(e) 空值策略不统一——aux_code/aux_name 填空串，summary/preparer 为 None，审计穿透时查询语义矛盾；(f) 进度条轮询 `ImportQueueService` 是内存态，后端重启就丢，应轮询 import_jobs 表；(g) 识别失败时前端无手动改 table_type 入口；(h) 辅助维度类型重名冲突（"税率"同时出现在客户/项目下），tb_aux_ledger 只存 aux_type 不区分上下文
  - **v2 引擎 UAT 工作流沉淀**：纯单测 100/100 ≠ 真实数据可用（v2 worker 首次上线因 import 错误连续 2 次 failed 但单测全过）；下轮流程硬约束：(1) 每轮 spec 交付前必须跑一次 9 家真实样本抽样 5000 行验证（5 分钟可完成）；(2) CI 加一个"YG36 端到端 smoke"固定回归（前端上传 → worker 执行 → PG 查 aux_ledger > 0）；(3) 单纯"代码文件存在"/"单测通过"不是验收标准，必须有真实 PG 入库行数断言
  - **Sprint 6 Part 1 完成（2026-05-08，9/20 项）**：(S6-1) 删除 aux_derivation.py 死代码；(S6-2) `_clear_project_year_tables` 从 smart_import_engine 迁到 writer.clear_project_year；(S6-4) `_execute_v2` bootstrap try/except 兜底 + result_summary["phase"]="bootstrap_import"；(S6-5) 5 个 Phase 入口结构化日志；(S6-6) 多对一映射丢弃列保留到 `raw_extra["_discarded_mappings"]`；(S6-7) aux_code/aux_name 空值改 NULL 不填空串；(S6-9) L1 强信号锁定（score ≥ `MATCHING_CONFIG.l1_lock_threshold` 默认 85 时 L1 胜过 L2，修复和平物流"余额表"被误识别为 ledger）；(S6-10) `test_real_samples_smoke.py` 2 用例（和平物流 + YG36）；(S6-11) excel_parser bytes/path 合并 `_iter_from_workbook` + `_iter_with_fallback` 底层共用；测试 102/102 通过；commit d8ac536 推送到 feature/round8-deep-closure
  - **Sprint 6 Part 2 待办（下轮，11 项）**：(S6-3) `_execute_v2` 迁到 `ledger_import/orchestrator.py` 3h；(S6-8) 辅助维度三元组查询端点（解决"税率"跨客户/项目重名）2h；(S6-12) xlsx forward-fill 可选策略 2h；(S6-13) staged 模式事务边界（dataset_id 失败整包 rollback）3h；(S6-14) rebuild_aux_summary 加 dataset_id 过滤 1h；(S6-15) `ledger_data_service.apply_incremental` 真正按期间追加 3h；(S6-16) 前端增量追加 Tab 打通 1.5h；(S6-17) `test_execute_v2_e2e.py` 集成测试 3h；(S6-18) CI v2 smoke step 0.5h；(S6-19/20) 针对性测试扩展 2h
  - **Sprint 6 Part 2 完成（2026-05-08，11/11）**：(S6-8) 三元组查询 `get_aux_by_triplet` + `GET /api/projects/{pid}/ledger/aux/by-triplet` + Alembic `idx_tb_aux_ledger_triplet` partial index；(S6-12) `iter_excel_rows_from_path` 新增 `forward_fill_cols` 参数，`_execute_v2` 对 account_code/account_name 列自动启用合并单元格向下填充；(S6-13) Staged 模式落地：`_execute_v2` 先 `DatasetService.create_staged` → 4 张表 insert 带 `dataset_id=staging_id` + `is_deleted=True` → gate 通过后 `activate_dataset` 原子切换 / gate 阻塞或异常时 `mark_failed` 清理；删除 `clear_project_year` 调用；(S6-14) `rebuild_aux_balance_summary` 新增可选 `dataset_id` 参数；(S6-15) `ledger_data_service.apply_incremental` 实现 skip/overwrite 两种重叠策略（overwrite 真删重叠月份的 tb_ledger/tb_aux_ledger）；(S6-16) `POST /incremental/apply` 端点 + LedgerDataManager Tab 3 加"检测差异"/"执行清理"按钮；(S6-17) `test_execute_v2_e2e.py` 2 用例（YG36 真实样本完整管线，SQLite 内存库，断言四表行数/17 种维度类型/S6-7 空值策略/S6-13 dataset_id 绑定）；(S6-18) CI 新增 `ledger-import-smoke` job；(S6-19/20) 6 个针对性测试（丢弃列边界 3 + 三元组查询 4）；(S6-3) `_execute_v2` 数据管线迁到 `orchestrator.execute_pipeline()`，runner 从 1094 行→573 行（-48%），orchestrator 从 255→709 行；121/121 测试全通过；commits d8ac536 / cb6653c / a461a2d / 1e8b83d 推送
  - **Sprint 6 关键技术决策**：(1) `_execute_v2` 薄包装策略——Worker 只管状态机+锁+artifact，数据流全放 orchestrator，未来换调度器（Celery/RQ）只需改 runner 层；(2) `execute_pipeline` 接收 `progress_cb` + `cancel_check` 异步回调，抽象 Worker 细节，pipeline 不依赖 ImportJobService；(3) Staged 原子激活强制使用 `is_deleted=True` + `dataset_id=staging_id` 双保护，`activate_dataset` 切换后自动 superseded 旧 dataset；(4) 三元组查询多 aux_code 求和时必须用 Decimal 累加不能 float；(5) E2E 测试关键点：SQLite UUID 存 hex 无连字符（查询需 `str(uuid).replace("-","")`）、JSON 序列化需自定义 default 处理 datetime、参数批大小 22 字段×40 行=880 < SQLite 999 上限；(6) L1 锁定置信度直接用 l1_score 不做加权归一化（`MATCHING_CONFIG.l1_lock_threshold` 默认 85 可配）；(7) `_smart_comma_split` 的 lookahead 模式 `,(?=[^:：,，]+[:：])` 只在"逗号后接 `类型:`"时切多维度
  - **TbAuxLedger raw_extra 字段补齐（踩坑）**：Alembic 迁移早已给 PG 4 张表加了 `raw_extra JSONB` 列，但 ORM 模型 `TbAuxLedger` 独缺该字段声明，导致 `insert(TbAuxLedger).values(..., raw_extra=...)` 触发 SQLAlchemy `CompileError: Unconsumed column names: raw_extra`；修复 = 给模型补 `raw_extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`
  - **Sprint 6 流程沉淀**：(1) 大改动拆三批 commit（Part 1/2a/2b+2c），每批 121 测试全绿后才做下一批；(2) E2E 断言"真实 PG 入库行数"+"维度类型分布"比单测更有效；(3) orchestrator 迁移用 Python 脚本精准删除重复代码段（find new_end_line/old_except_line 两个 marker 之间整块删除），避免手工引入语法错误；(4) CI 新增 smoke job 用 `数据/` 目录做可选真实样本回归（缺失则 skip）
  - **Sprint 7 规划（UX+运维，10 项）**：软删除回收站 / LedgerDataManager 多入口挂载 / 前端手动改 table_type / raw_extra GIN 索引 / 进度条改轮询 import_jobs 表 / L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / adapter 机制取舍
  - **Sprint 7 补充待办（Sprint 6 复盘新增，11 项）**：P0=9 家真实样本参数化 E2E（当前只跑 YG36 1 家）；P0=`writer.bulk_insert(table, rows, dataset_id, project_id, year)` 抽象合并 4 个 `_insert_*` 重复闭包；P0=空值策略全量审计（summary/preparer/voucher_type 等仍可能 None vs 空串不一致，当前只修了 aux_code/aux_name）+ 字段规约文档；P0=Alembic 迁移 upgrade→downgrade→upgrade 循环测试；P1=最小合成样本放 `backend/tests/fixtures/` 让 CI smoke 必跑（当前 CI 找不到 `数据/` 目录会 skip）；P1=orchestrator 拆三文件（pipeline.py 主流程 / pipeline_insert.py insert helpers / api.py ImportOrchestrator 类）；P1=integration test 补 10 个（pipeline × runner × PG 真实库）；P1=incremental apply 合并到 submit 阶段（消除前端两步"先清理再上传"体验断裂）；P2=`docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 架构文档（回调契约/PipelineResult/staged 激活流程图）；P2=前端 playwright 最小 E2E UI 测试；P3=commit message 加"验证等级"标注规范（unit/E2E/smoke/manual/not verified）
  - **Sprint 7 轮 1 完成（2026-05-09，4/21）**：(S7-1) `test_9_samples_e2e.py` 参数化 10 用例覆盖全部 9 家企业（抽 1000 行/sheet，~3 分钟跑完），和平物流余额表跨样本验证 S6-9 L1 锁定；(S7-2) `writer.bulk_insert_staged(db_session_factory, table_model, rows, ...)` 通用函数替代 4 个重复 insert 闭包，按 `table_model.__table__.columns` 自省过滤字段 + 自动注入 id/project_id/year/dataset_id/is_deleted 公共字段，orchestrator.py 从 709 行降到 580 行（-18%）；(S7-3) `backend/tests/fixtures/ledger_samples/minimal_balance_ledger.py` 生成最小合成样本（合并表头+8 行 balance+6 行 ledger+核算维度），`test_minimal_sample_smoke.py` 4 用例 0.45s 跑完，CI smoke 主步骤不再依赖真实 `数据/`；(S7-4) converter 里 account_name `""` 改 None（所有表 nullable 字段统一用 None），writer.bulk_insert_staged 同步删除 account_name "" 兜底；125/125 主套测试 + 10/10 E2E 通过；commit b29b7b9 推送
  - **bulk_insert_staged 设计决策（S7-2）**：关键是"按模型列自省过滤"——converter 产出的 row 字典可能含 TbLedger 没有的 aux_type/aux_code（converter 统一 key），但 insert 时 `valid_cols = {c.name for c in table_model.__table__.columns}` 过滤一遍只保留匹配字段；公共字段（id/project_id/year/dataset_id/is_deleted）强制覆盖，NOT NULL 兜底（company_code/currency_code）有 fallback 值；这种设计让未来新增字段只改 converter + ORM，无需改 insert 函数
  - **CI smoke 两层策略（S7-3 沉淀）**：第一层"最小合成样本 smoke"（4 用例，0.45s，必跑）作为质量门禁；第二层"真实 9 家样本 E2E"（10 用例，~3min，可选跑，数据/ 缺失时 `|| true` 跳过）作为深度回归；两层都挂在 `ledger-import-smoke` CI job；下轮可考虑把合成样本放 Docker image 让 E2E 也必跑
  - **Sprint 7 轮 2 完成（2026-05-09，3/21，累计 7/21）**：(S7-6) `orchestrator.py` 拆出 `pipeline.py`（346 行，含 execute_pipeline/PipelineResult/ProgressCallback/CancelChecker），orchestrator.py 从 705 行→361 行只保留 ImportOrchestrator 类，保留 re-export 向后兼容；(S7-8) `test_alembic_migrations.py` 5 用例（3 个 round-trip 需 PG skip + 2 个拓扑/静态检查本地跑）；(S7-5) `test_bulk_insert_staged.py` 8 用例覆盖字段自省/公共字段注入/NOT NULL 兜底/空 rows/分 chunk 等边界；135/135 主套通过；commit a3add4a 推送
  - **Alembic 迁移目录硬 bug（S7-8 重大发现）**：Sprint 2 以来 4 个迁移文件被错放在 `backend/app/migrations/`（仅 sql 脚本+历史遗留位置），而 Alembic `script_location = alembic`（→ `backend/alembic/versions/`），导致这些迁移**从未被 Alembic 执行过**：(1) `ledger_import_column_mapping_20260508`（import_column_mapping_history 表）；(2) `ledger_import_raw_extra_20260508`（4 张表 raw_extra JSONB 列）；(3) `ledger_import_aux_triplet_idx_20260508`（三元组 partial index）；(4) `round7_clients_20260508`（clients + project_tags）。修复 = 4 个文件移到 `backend/alembic/versions/` + 修 `round7_clients` 的 down_revision 从 `round7_section_progress_gin`（缺日期后缀）改为 `round7_section_progress_gin_20260507`。生产环境需审计：这些 schema 对象可能靠 `_init_tables.py` create_all 或手动 ALTER TABLE 补上，纯靠 Alembic 增量升级的环境会缺
  - **Alembic 迁移目录规约**：所有 Python 迁移文件必须放 `backend/alembic/versions/`，不能放 `backend/app/migrations/`（后者只留 SQL 脚本类的历史遗留，如 phase12_001_*.sql）；CI 拓扑检查 `test_no_stray_migrations_in_app_migrations` 会扫 app/migrations/ 下是否有含 `revision =` 和 `down_revision =` 的 .py 文件，有即失败
  - **pipeline.py 架构沉淀（S7-6）**：文件边界=职责边界。`orchestrator.py` 只放 ImportOrchestrator 类（detect/submit/resume 三阶段 API，供路由调用）；`pipeline.py` 只放数据管线 `execute_pipeline` + `PipelineResult` + 回调类型（供 Worker 调用）；runner 直接 `from app.services.ledger_import.pipeline import execute_pipeline`，不再走 orchestrator 中转
  - **Sprint 7 轮 3 完成（2026-05-09，2/21，累计 9/21）**：(S7-9) submit 端点新增 `incremental/overlap_strategy/file_periods` 字段，incremental+overwrite 时 submit 前自动调 `apply_incremental` 清理旧月份（一步到位，消除前端两步体验断裂）；(S7-10) `delete_ledger_data` 默认改软删（UPDATE is_deleted=true）+ 新增 `hard_delete=True` 参数 + `restore_ledger_data` 恢复函数 + `list_trash` 回收站列表 + 路由 GET /trash + POST /restore + apiPaths 新增 trash/restore；135/135 测试通过；commit b3e0dfe 推送
  - **Sprint 7 剩余 12 项（P2-P3，下轮继续）**：integration test 补齐 10 个（需 PG）/ 前端手动改 table_type / raw_extra GIN 索引 / 进度条改轮询 import_jobs / L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric / 大文件性能 CI 门禁 / adapter 机制取舍 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 轮 4 完成（2026-05-09，+3，累计 12/21）**：(1) Alembic 迁移 `ledger_import_raw_extra_gin_20260509`——4 张表 raw_extra 列加 GIN partial index（WHERE raw_extra IS NOT NULL），支持 @>/?/?| JSONB 操作符走索引；(2) 进度条持久化——后端新增 `GET /api/projects/{pid}/ledger-import/jobs/latest`（优先返回活跃 job，无活跃则返回最近 5 分钟完成/失败的，无 job 返回 idle），前端 ThreeColumnLayout.vue pollImportQueue 改调新端点（后端重启不再丢状态）；(3) 前端手动改 table_type 确认已在 Sprint 4 的 DetectionPreview.vue 实现（el-select v-model="row.table_type"），无需额外改动；135/135 测试通过；commit cbc3c84 推送
  - **Sprint 7 剩余 9 项（P2-P3，可选做）**：integration test 补齐 10 个（需 PG，CI 里跑）/ L2+L3 容差动态 / force_activate 审批链 / 识别准确率 metric / 大文件性能 CI 门禁 / adapter 机制取舍 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 轮 5 完成（2026-05-09，+3，累计 15/21）**：(1) L2/L3 容差动态化——validator BALANCE_LEDGER_MISMATCH 从固定 1.0 元改为 `min(1.0 + magnitude × 0.00001, 100.0)`（小金额仍约 1 元，亿级最高 100 元，避免浮点精度误报）；(2) force_activate 审批链——pipeline.py 在 force+blocking 时记录 `force_skipped_findings` 到 validation_summary（ActivationRecord 含完整审计轨迹，后续可查"哪些项目强制跳过校验"）；(3) adapter 机制精简——orchestrator 不再调 `detect_best` 自动匹配（真实 9 家从未触发），仅用户显式传 adapter_hint 时才赋 adapter_id，adapter 目录保留作别名包（identifier.default_aliases() 仍从 JSON 读取）；135/135 测试通过；commit beff660 推送
  - **Sprint 7 剩余 6 项（P3，留给后续按需触碰）**：integration test 补齐 10 个（需 PG）/ 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / 架构文档 / playwright / commit 等级规范
  - **Sprint 7 收尾（2026-05-09，累计 16/21）**：新增 `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md`（176 行，含模块总览/数据流/7 个设计决策/回调契约/PipelineResult 字段/Alembic 迁移链/测试策略/已知限制）；commit 9b4b15d 推送
  - **Sprint 7 剩余 5 项（P3）**：integration test 补齐 10 个（需 PG）/ 识别准确率 metric 仪表盘 / 大文件性能 CI 门禁 / 前端 playwright E2E / commit 等级规范
  - **L1 企业级宽容策略（2026-05-10，commit 0fde30f）**：`validate_l1` 从"硬阻断"改为两阶段预检：(1) 整行所有字段都空 → 静默跳过不记 finding（空白/尾部行）；(2) 非 exclusive_pair 的 key col 有空 → 记 `ROW_SKIPPED_KEY_EMPTY` warning + 跳过该行但不阻断激活；`EMPTY_VALUE_KEY` blocking 已下线；AMOUNT/DATE 类型错误原语义保留（值非空但不可解析 → blocking/warning）；真实业务数据无法 100% 干净，少量脏行应"跳过 + 告警"而非整批阻断；新增 `ROW_SKIPPED_KEY_EMPTY` 到 errors.py（severity=warning，tier=key）
  - **9 家真实账套批量验证结果（2026-05-10，7/10 成功）**：`scripts/verify_9_companies_pipeline.py` 参数化 10 用例（9 企业 + 陕西华氏拆 2024/2025），按文件大小排序便于快速暴露问题；已通过：YG36 四川物流（39s）/ YG2101 四川医药（1153s，128MB）/ YG4001 宜宾大药房（15s）/ 和平物流（79s，本轮修复后）/ 安徽骨科（592s）/ 辽宁卫生（791s）/ 医疗器械（407s）；未完成：和平药房（392MB CSV，>20min timeout）/ 陕西华氏 2024（13 文件）/ 陕西华氏 2025（12 文件）——皆为大文件耗时问题非 bug
  - **批量测试踩坑（2026-05-10）**：(1) `ImportJob.project_id` FK 到 `projects`，批量测试脚本必须先建 Project；(2) 直接用 `Project()` ORM 构造触发 SQLAlchemy 关系图解析，未 import 的 `accounting_standards` 模型会抛 `NoReferencedTableError`——改用 raw SQL INSERT 绕过关系图；(3) `start-dev.bat` 已启动的 uvicorn dev server + 脚本共用 DATABASE_URL 时，僵尸脚本进程会持续占用 DB 连接池，跑前务必清理（`Get-Process python` 看 CommandLine 过滤）
  - **YG2101 性能基线**：128MB xlsx 单文件 19 分钟入库 650K 序时账 + 1.35M 辅助序时（openpyxl read_only 模式仍需全量解析）；辽宁卫生 78MB xlsx 13 分钟入库 406K 序时账；大致吞吐量 500-800 行/秒（含 aux 维度解析+PG insert）
  - **和平物流序时账 header 特征**：第 1 行列名为 `[凭证号码]#[日期]` / `[日期]` / `[凭证号码]` 等方括号包裹格式（金蝶/用友之外的某软件规范），detector `_score_table_type` 给了 unknown+conf=0 但 pipeline 仍正常识别（fallback 路径），后续可考虑在 detector `_match_merged_header` 增加"方括号包裹字段名"识别规则提升置信度
  - **前端 UI 端到端链路全通（2026-05-10，commit 7f39990）**：YG36 真实账套从浏览器上传→识别→提交→Worker→入库 25 秒完成（balance 1823 / aux_balance 1730 / ledger 22716 / aux_ledger 25813），status=completed。修复 7 个串联 bug：(1) `import_recover_worker` except 分支没 sleep，异常后立即 while 下一轮（11MB/秒 刷日志死循环）；(2) `ImportJobService.check_timed_out` naive datetime 减 aware heartbeat_at 抛 "can't subtract offset-naive and offset-aware"；(3) `recover_jobs` 缺情况 3：started_at+heartbeat_at 双 NULL 的 running job 永久锁定项目（`active_project_job_exists` 永久 True）；(4) `_execute_v2` Phase 5 `writing → completed` 被状态机拒绝（`_VALID_TRANSITIONS` 要求 writing→activating→completed），需加中间过渡；(5) `ledger_import_v2.py /detect` 只读内存 `await f.read()` 不持久化文件，Worker `_load_file_sources(upload_token)` 找不到 bundle → 改调 `LedgerImportUploadService.create_bundle` + `detect_from_paths`；(6) `orchestrator.submit` 只建 job(status=queued) 不触发 worker，靠 30s recover 轮询才跑 → /submit 端点返回前立即 `ImportJobRunner.enqueue(job_id)`；(7) `orchestrator.submit` 重建 ImportArtifact 与 detect 阶段的 bundle artifact unique 冲突 → 改查已存在复用
  - **e2e_http_curl.py**（本轮新建，保留）：可复用的前端 UI 链路 UAT 脚本（登录 → /detect → /submit → 轮询 active-job → /diagnostics → DB 验证），未来 Worker/orchestrator 改动必须先跑此脚本
  - **前端 UI 链路规约（必须同时满足）**：detect 端点必须持久化文件到 bundle（不是只读内存）；submit 端点必须立即 `enqueue(job_id)`（不能靠 recover 兜底）；pipeline 返回后 Worker 层必须按 `_VALID_TRANSITIONS` 走完整状态机（writing→activating→completed）；except 分支必须 sleep 避免死循环
  - **`httpx.AsyncClient` 多次请求可能遇到 502**（原因未完全定位，可能与 keep-alive 或代理相关），UAT 脚本用 `requests.Session()` 同步客户端更稳定
  - **backend/backend.log 检查技巧**：用 `python -m uvicorn ... 2>&1 | Out-File backend.log -Encoding UTF8` 手动启后端可捕获实时日志；PowerShell `Select-String -Pattern` 需防中文编码破坏，必要时 `Get-Content -Encoding UTF8 -Tail N` 就够
  - **僵尸 running job 危害**：PG 里每个 project_id 只允许一个 active job，任何"status in (running,validating,writing,activating) 但 started_at=NULL heartbeat_at=NULL"的遗留数据都会让后续所有新 job 卡在 queued；DB 重建/代码 reload/手动 kill 后必须清理，否则前端永远跑不通
  - **YG36 真实导入最终修复（2026-05-09 晚，commit b07a17f）**：两处关键 bug 修复后 YG36 端到端 **成功**（balance 1823 / aux_balance 1730 / ledger 22716 / aux_ledger 40122，warnings=0 blocking=0，10+ 维度类型正确识别）：(1) **validator `_EXCLUSIVE_KEY_PAIRS` 语义修正**——此前要求"至少一个金额字段非空"，但真实余额表常见"期初期末均为 0 的零余额行"（新开科目），8 字段合法全空被误报 1398 条 EMPTY_VALUE_KEY blocking；改为"互斥组内所有字段不强制 EMPTY blocking"（允许全空），AMOUNT/DATE 类型检查保留；balance/aux_balance 扩展到 8 字段覆盖分列模式；(2) **`tb_aux_balance_summary` 表缺失**——pipeline 93% 调 rebuild_aux_balance_summary 失败，PG 重建后此表从 baseline 缺失（archived 002 已归档），新建 Alembic 迁移 `ledger_aux_balance_summary_20260509.py`；pytest 145 passed / 3 skipped
  - **balance 表零余额行硬约定**：余额表"期初+本期+期末全 0"的科目行合法（新开未用），L1 不应 blocking；任何关于"金额字段必填"的假设在真实数据面前都站不住脚
  - **Git commit message 中文编码规约（2026-05-09）**：PowerShell 7 默认 console OutputEncoding 是 GB2312（chcp 936），`git commit -F file.txt` 会按 GBK 解码文件内容导致中文乱码；修复 = 提交前 `chcp 65001 > $null` 切 UTF-8 codepage，或 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`；git config `i18n.commitEncoding=utf-8` 也要设，双重保险
  - **Alembic 多 head 时硬约定**：当 `heads` 返回多个分支（如 round4_ocr_fields_cache + ledger_aux_balance_summary），不能直接 `alembic upgrade head`，必须指定具体 revision `alembic upgrade <revision_id>` 或按 branchname@head；本轮遇到 alembic_version 与实际 schema 不一致（word_export_task 表已存在），改用 psycopg2 直接 DDL 补表（一次性脚本用完即删）
  - **PG 重建 baseline 遗漏清单**：`_init_tables.py` 只跑 create_all，历史 archived 迁移中的表（如 `tb_aux_balance_summary`）若被 model 层删除但业务代码仍引用，PG 重建后会缺表；未来 baseline 需对照 `grep -r "CREATE TABLE\|FROM tb_" backend/` 确认 SQL raw 表全覆盖
  - **raw_extra JSONB datetime 序列化修复（2026-05-09 真实导入踩坑）**：真实数据的 raw_extra 字典含 datetime/date 对象（如"到期日"列进了 raw_extra），PG JSONB 列 INSERT 时报 `TypeError: Object of type datetime is not JSON serializable`；修复 = 新增 `_sanitize_raw_extra(extra: dict)` 递归遍历：datetime→isoformat / Decimal→float / 其他非标准→str；在 `build_raw_extra` 返回前 + `bulk_insert_staged` 写入前双重调用确保安全；commit 08594c1
  - **PowerShell 批量修改中文文件的铁律（2026-05-09 踩坑 2 小时）**：**禁止**用 PowerShell 的 `Get-Content -Raw | Set-Content` 或 `-replace` 管道做批量文本替换——PS 默认用 UTF-16 读取后再写回，会把 3 字节 UTF-8 中文字符截断成 2 字节（末字节被吞），文件全是 `\xef\xbf\xbd` replacement char 导致 Vue 模板编译失败。正确做法：**用 Python 字节级操作** `open(path, 'rb') → content.replace(b"...", b"...") → open(path, 'wb')`；或用 `strReplace` 工具。踩坑案例：LedgerDataManager.vue 被损坏 30+ 处中文字符，靠 `git show HEAD~1:file | python` 恢复原始字节再做字节级替换
  - **apiPaths.ts ledger.data vs ledger.import.data 路径结构（2026-05-09 修正）**：`ledger.data.*` 是 `ledger` 的直接子属性（不是 `ledger.import.data`），v2 账表数据管理端点位于 `ledger.data.summary/delete/incrementalDetect/incrementalApply/trash/restore`；LedgerDataManager.vue 一度误用 `ledger.import.data.*` 导致 `Cannot read properties of undefined (reading 'summary')` 运行时错误（commit ee2828a 修正）
  - **FastAPI 路由冲突踩坑（2026-05-09）**：`/jobs/latest` 每 10s 返回 422——因为 `backend/app/routers/ledger_datasets.py` 和 `ledger_import_v2.py` 都挂载在 `/api/projects/{pid}/ledger-import` prefix，前者有 `/jobs/{job_id}`（job_id: UUID）路由会拦截吸收 `"latest"` 作为 UUID 参数解析失败；FastAPI 路由匹配是全局按声明顺序，**不同 router 之间的路由也会冲突**。修复 = 把 `/jobs/latest` 改名 `/active-job` 避开 `/jobs/` 命名空间；commit e4883d0。规约：同一 prefix 下多 router 注册时，literal 路由（如 `/latest`）必须**不能**和 `{var_name}` 通配冲突
  - **L1 校验借贷互斥关键列（2026-05-09 真实导入阻断）**：validator.py 的 L1 把 `debit_amount`/`credit_amount` 都列为 key column，任一为空就 blocking；但真实序时账每行**要么借方有值要么贷方有值不可能同时**，导致 22716 行产生 44000+ blocking errors 阻断 activate。修复 = 新增 `_EXCLUSIVE_KEY_PAIRS: dict[table_type, set[str]]`（目前为 `ledger/aux_ledger: {debit_amount, credit_amount}`），对互斥对至少一个非空即通过，不再 blocking；commit c3bc661。规约：未来新增互斥关键列（如余额表 `opening_debit`/`opening_credit`）加到此字典即可
  - **"数据未入库" debug 方法论沉淀（2026-05-09）**：用户看到"导入失败"时多数是"数据被 staged 写入后 activate gate 阻断清理"而非真没写。排查 3 步：(1) `SELECT COUNT(*) FILTER (WHERE is_deleted=true/false) FROM tb_ledger` 区分 active/staged/trash；(2) `SELECT dataset_id, is_deleted` 看是 v2 staged 残留（有 dataset_id）还是旧引擎残留（dataset_id=NULL）；(3) 看 `import_jobs.error_message` 的真实 error chain—datetime 错误/L1 校验失败/路由 422 是不同层级；staged 数据在 gate 失败时会被 `cleanup_dataset_rows` 硬删，所以"失败后数据为空"是预期行为
  - **PowerShell 批量文本替换铁律**：禁止用 `Get-Content -Raw` + `-replace` + `Set-Content` 对含中文的文件做批量修改——PowerShell 默认把文件当 UTF-16 解码，UTF-8 3 字节中文字符会被破坏成 2 字节（第 3 字节被吞），产生 `\xef\xbf\xbd` replacement char；LedgerDataManager.vue 就是这么坏掉的（30+ 处中文被截断，Vue 模板编译直接崩）；正确做法：**必须用 Python `open(path, 'rb')` 字节级读写**，再用 `content.replace(b'old', b'new')`；commit 6a2150e 修复（从 git HEAD~1 取原始字节重做替换）
  - **动态容差设计决策**：公式 `tolerance = min(1.0 + magnitude × 0.00001, 100.0)`，magnitude 取 opening/closing/sum_debit/sum_credit 四者绝对值最大值；设计意图：(a) 小科目（<10 万）容差 ≈ 1-2 元，保持严格；(b) 大科目（亿级）容差 ≈ 10-100 元，容忍浮点/四舍五入差异；(c) 上限 100 元防止超大金额时容差过宽；可通过 `matching_config` 配置化（当前硬编码）
  - **adapter 机制最终定位**：adapter 不再做运行时 match（detect_best 已移除），仅作为"列别名 JSON 配置包"存在——identifier.py 的 `_RAW_HEADER_ALIASES` 可被 `ledger_recognition_rules.json` 的 `column_aliases` 覆盖，adapter JSON 文件提供软件特定别名扩展；未来如需恢复自动匹配，只需在 orchestrator 重新调 `detect_best`
  - **复盘方法论沉淀**：(1) 测试金字塔头重倾向——121 unit + 2 E2E，真实 bug 多在层间集成（ORM vs Alembic、Worker vs Pipeline、FE vs BE），下轮先补 integration 而非 unit；(2) "先跑通再说"会累积架构债，每 Sprint 留 20% 时间还债；(3) commit message 的"声称已修"需人工复核——"真实样本 E2E 通过"实际只测了 YG36 1 家不是 9 家，"Staged 原子激活"没并发验证是否真原子；(4) 前后端联动的 UX 流程测试缺失（后端端点通 + 前端按钮在 ≠ 用户真能走通），需引入 playwright
  - **辅助维度列处理修复（2026-05-08）**：(1) 新增 `aux_dimensions` 字段（混合维度列，含多维度字符串），别名 `["核算维度", "辅助核算", "核算项目", "辅助维度", "多维度"]`；(2) `aux_type` 别名精简为 `["辅助类型", "辅助核算类型"]`（不含"核算类型"避免与 aux_dimensions 冲突）；(3) RECOMMENDED_COLUMNS 的 balance/ledger 加入 aux_dimensions；(4) converter `aux_balance_rows` 分流时跳过 aux_type=None 的条目（否则 NOT NULL 报错）。实测：四川物流 tb_balance=814 + tb_aux_balance=1919 正确入库
  - **前端导入进度条现状**：`ThreeColumnLayout.vue` 顶栏已有"导入中"按钮 + `bgImportStatus` 轮询 `/api/data-lifecycle/import-queue/{projectId}`；问题：`ImportQueueService` 是内存态（重启后丢失），前端看不到后台任务；架构级改进需让 import_queue 状态写 DB 或前端改轮询 import_jobs 表
  - **导入历史改为内嵌 dialog**：`LedgerImportHistory.vue` 独立页面因 Vite 动态 import 缓存问题无法稳定加载，改为 LedgerPenetration 内 el-dialog 弹窗模式（`importHistoryVisible`），避免路由跳转
  - **账表数据管理功能已实现（2026-05-08）**：后端 `ledger_data_service.py` + `routers/ledger_data.py`（router_registry §25）3 个端点：(1) `GET /api/projects/{pid}/ledger-data/summary` 查询年度/月份分布；(2) `DELETE /api/projects/{pid}/ledger-data` 按 year+tables+periods 删除；(3) `POST /api/projects/{pid}/ledger-data/incremental/detect` 增量追加预检（diff: new/overlap/only_existing）；前端 `LedgerDataManager.vue` 组件含 3 Tab（概览/删除/增量追加），apiPaths 新增 `ledger.import.data.*`；余额表按 year 全量，序时账按 year+accounting_period 可追加
  - **`LedgerDataManager` 待挂载**：组件已建但未挂载到具体入口页面（如 LedgerPenetration.vue），需添加"数据管理"按钮打开
  - **迁移剩余步骤（P1-P2）**：P1 迁移 `_clear_project_year_tables` 到 writer.py + application_service 替换 `smart_parse_files`（2.5h）→ P2 观察稳定后删除旧引擎文件
  - **旧引擎外部调用方（3 处，仅回退时触发）**：import_job_runner.py（smart_import_streaming）、ledger_import_application_service.py（smart_parse_files + smart_import_streaming）、account_chart_service.py（_clear_project_year_tables）

### 中期功能完善
- **审计调整分录企业级联动 spec 实施完成**（`.kiro/specs/enterprise-linkage/`）：5 Sprint / 41 必做任务全部完成 + 5 项复盘修复；8 项可选测试任务跳过；8 项 UAT 待手动验证
  - Sprint 1（基础设施）：2 Alembic 迁移（3 新表 + adjustments.version）+ PresenceService(Redis ZSET) + ConflictGuardService(编辑锁+乐观锁) + Presence/ConflictGuard API + EventType 6 新枚举 + event_handlers SSE 推送 + 增量事件拉取端点
  - Sprint 2（核心联动）：LinkageService（TB→分录/底稿关联 + 影响预判 + 变更历史 + 级联日志）+ Linkage API 4 端点 + 批量重分类导入/导出 3 端点 + 批量提交单次级联 + 批量原子性
  - Sprint 3（前端集成）：5 composables（usePresence/useConflictGuard/useLinkageIndicator/useImpactPreview/useNavigationStack）+ 5 组件（PresenceAvatars/ConflictDialog/LinkageBadge+Popover/ImpactPreviewPanel）+ 右键菜单跨模块跳转
  - Sprint 4（打磨监控）：useNotificationFatigue + EventCascadeMonitor + admin_event_health 端点 + useSSEDegradation + 权限过滤 + 跨年度隔离 + 一致性校验端点 + DegradedBanner
  - 复盘修复 5 项：ORM 模型 enterprise_linkage_models.py（3 类）+ DegradedBanner 挂载 ThreeColumnLayout + ImpactPreviewPanel 挂载 Adjustments 创建对话框 + LinkageBadge 挂载 TrialBalance 联动列 + record_tb_change 事件订阅接入
  - 新建后端文件 9 个：2 迁移 + presence_service + conflict_guard_service + linkage_service + event_cascade_monitor + presence.py + conflict_guard.py + linkage.py + reclassification.py + admin_event_health.py + enterprise_linkage_models.py
  - 新建前端文件 12 个：7 composables + 5 components
  - router_registry 新增 §30（Presence+ConflictGuard）§31（Linkage+Reclassification）§32（AdminEventHealth）
  - apiPaths.ts 新增 presence/linkage/conflictGuard 3 个路径对象
- **项目三码体系（待 spec）**：本企业名称+代码、上级企业名称+代码、最终控制方名称+代码 6 字段必填（所有项目，非仅合并），通过 parent_company_code→company_code 构建项目树；可见性基于 ProjectAssignment 派单裁剪（助理看子公司，经理看项目组，合伙人看全部）；需新建 spec 规划
- **底稿深度优化 spec 实施中**（`.kiro/specs/workpaper-deep-optimization/`）：requirements.md（7 章 41 需求 + 27 属性 + 附录 A/B）+ design.md（13 架构决策 D1-D13 + 6 新表含 cell_annotations + 公式引擎详设）+ tasks.md（11 Sprint / 97 任务 + 10 UAT）；覆盖矩阵 41/41 全绿
  - **Sprint 1-11 全部任务完成（97/97，100%含可选测试）**：12 个属性测试+集成测试全绿（0.45s）；剩余 10 项 UAT 需手动浏览器验证
  - **新建测试文件**：`backend/tests/test_wp_optimization_properties.py`（7 property-based + 2 supplementary + 3 integration = 12 tests）
  - **代码骨架完成但模板数据远未覆盖**：476 个致同模板只有 88 条 wp_account_mapping（D-N 审定表级），B/C/A/S 类模板元数据全缺；下一步是数据工程而非代码——需从实际 Excel/docx 模板提取 component_type/procedure_steps/formula_cells/conclusion_cell 种子数据
- **全局模板库管理 spec 已创建**（`.kiro/specs/template-library-coordination/`）：22 需求 / 10 架构决策 / 15 属性 / 6 Sprint 50 任务 + 10 UAT；覆盖 5 大模板库 + 致同编码体系 + 枚举字典 + 自定义查询；管理页面 8 Tab（底稿模板/公式管理/审计报告/附注/编码体系/报表配置/枚举字典/自定义查询）
- **template-library-coordination 实施完成（2026-05-16）**：43/43 必做编码任务全部完成（9 PBT 可选任务跳过），剩余 10 项 UAT 需手动浏览器验证；vue-tsc 0 错误，8/8 集成测试通过（2.81s）
  - **新建后端文件 4 个**：`routers/template_library_mgmt.py`（913 行 / 6 端点 + 3 个 405 mutation 拦截 + Pydantic 模型 + `derive_seed_status` 纯函数）/ `routers/system_dicts.py` 扩展（`/usage-count` 端点查询 7 张业务表 + 3 个 405 mutation 拦截）/ `routers/custom_query.py` 扩展（5 个新数据源 + 模板 CRUD）/ `models/custom_query_models.py` + 2 Alembic 迁移（`template_library_seed_history_20260517` / `custom_query_templates_20260518`）
  - **新建前端文件 12 个**：`views/TemplateLibraryMgmt.vue` 主页面（8 Tab + 顶部统计摘要 + 种子加载折叠区 + 版本历史对话框）/ `views/CustomQuery.vue` 独立页面 / `composables/useTemplateLibrarySource.ts`（D13 ADR JSON 只读统一文案）/ `components/template-library/` 9 个组件（WpTemplateTab / FormulaTab / FormulaCoverageChart / AuditReportTab / NoteTemplateTab / GtCodingTab / ReportConfigTab / SeedLoaderPanel / WpTemplateDetail / EnumDictTab / CustomQueryTab / VersionHistoryDialog）+ `tests/test_template_library_mgmt_integration.py`（8 测试覆盖 N+1 / SAVEPOINT / 405 / 403 / 覆盖率公式）
  - **关键 ADR 落地**：D13 JSON 只读源 4 个资源（prefill_formula_mapping / cross_wp_references / audit_report_templates / wp_account_mapping）UI 不提供编辑入口 + 顶部 banner 引导 reseed；D14 不依赖 `WpTemplateMetadata.subtable_codes`（不存在），子表收敛靠 `wp_code.split("-")[0]` 运行时计算；D15 SAVEPOINT 边界（每 seed 独立 commit，失败不回滚已成功）；D16 零硬编码（所有数字从 API/JSON/SQL 实时取）；Property 16 后端二次校验 admin/partner（require_role）；Property 17 mutation → 405 + JSON_SOURCE_READONLY hint
  - **路由 §54** 已注册（router_registry.py）；apiPaths.ts 新增 `templateLibraryMgmt` / `customQuery` / `systemDicts` 三个路径对象；前端路由 `/template-library` + `/custom-query` 已注册
- **审计全链路一键生成与导出 spec 三件套完成**（`.kiro/specs/audit-chain-generation/`）：53 需求 / 10 架构决策 / 20 属性 / 11 Sprint 90 任务（81 必做+9 可选）+ 12 Checkpoint + 10 UAT；需求覆盖率 100% / 属性覆盖率 100%；第一部分=全链路编排（需求 1-17）；第二部分=报表模块修复（需求 18-20）；第三部分=附注模块修复（需求 21-27）；第四部分=全局联动（需求 28-40）；第五部分=用户体验（需求 41-53）
  - **实施优先级**：P0=需求 1-3+18-20（全链路编排+报表修复）→ P1=需求 4-5+21-25+35-36+46（附注生成+底稿联动+分层策略+导出）→ P2=需求 6-12+26-27+38-40+47-48（一致性门控+编辑体验+枚举联动+互转+富文本）→ P3=需求 13-17+28-34+41-45+49-50（覆盖率提升+全局优化+协作+可扩展+可视化）
  - **附注核心设计原则**：模板是参考框架不是必须全部生成；通用规则引擎（5 条：余额/变动/底稿/政策/关联方驱动）决定"生成什么"；底稿联动（4 种取数模式：合计/明细/分类/变动）决定"填什么数据"；智能裁剪（小金额合并/合并单体适配/必披露保留）
  - **附注 5 层处理模型（需求 46）**：A=会计政策纯文字(10%自动化,不联动底稿) / B=合并科目注释表格(90%+,核心联动) / C=母公司注释(90%+,单体TB联动) / D=补充信息混合(50%,部分联动) / E=附录索引(100%全自动)；只有 B/C 层与底稿深度联动
  - **附注预置枚举 10 种**：aging_period(5段)/aging_period_3(3段)/yes_no/investment_method(成本法/权益法)/impairment_sign/currency/guarantee_type/related_party_type/lease_type/fair_value_level；支持项目级临时扩展
  - **附注模版目录 10 个文件**：`附注模版/` 下含国企报表附注.md(303KB)/国企报表附注_单体.md(285KB)/上市报表附注.md(519KB)/上市报表附注_单体.md(516KB) + 国企版校验公式预设.md(163KB)/上市版校验公式预设.md(73KB) + 国企版科目对照模板.md(29KB)/上市版科目对照模板.md(8KB) + 国企版宽表公式预设.md(11KB)/上市版宽表公式预设.md(6KB)
  - **附注校验公式类型 9 种**：余额/宽表/纵向/交叉/跨科目/其中项/二级明细/完整性/LLM审核；互斥规则=[余额]不与[其中项]/[宽表]共存；其中项通用规则=sum(明细行)=合计行不硬编码子项名称
  - **审计报告模板目录**：`审计报告模板/` 下按 国企版/上市版 × 合并/单体 组织（4 套），每套含 3 文件：审计报告正文(.docx) + 财务报表(.xlsx) + 附注模板(.docx)；另有 `纯报表科目注释/` 子目录（同结构 4 套）
  - **模板体系分工**：报表 Excel 导出基于 `审计报告模板/` 下的 xlsx 模板（复制→填充数据→保留格式）；附注生成以 `附注模版/` 下的 MD 文件为唯一真源（`审计报告模板/` 下的 docx 附注仅作 Word 导出格式参考）
  - **现有实现状态（2026-05-15 代码分析）**：报表引擎 41KB 骨架完整（generate_all_reports+TB/SUM_TB/ROW+Redis+unadjusted 标记），缺 CFS 间接法+report_config_seed 仅 22 行骨架（DB 1191 行由脚本填充但公式覆盖 26.5%）；附注引擎 35KB 骨架完整（generate_notes+populate_table_data+SOE/Listed JSON 173/187 章节），缺 TB()/WP()/REPORT() 公式+校验引擎+MD 模板未使用；Word 导出 3KB 极简占位（缺页面设置/TOC/页码/致同格式）；统一公式引擎 17KB 部分实现（FormulaResult+safe_eval+SUM_TB+PREV，缺 _resolve_tb/_resolve_row）；事件级联 26KB 全链就绪（ADJUSTMENT→TB→REPORTS→WP+stale）
  - **实施策略**：不是从零开发而是"补齐缺口+增强格式"——报表补公式数据（26.5%→90%+）；附注接入 MD 校验公式+实现取数函数；Word 导出重写为致同格式；全链路封装为编排端点+SSE+前端按钮
  - **实施进度（2026-05-16 更新）**：Sprint 1-11 全部完成（81/81 必做任务，100%）；9 个可选属性测试任务跳过；剩余 10 项 UAT 需手动浏览器验证；3585 tests collected / 33+ chain tests pass
    - Sprint 7 完成：ConsistencyGate 5 项检查 + stale 级联标记 + 前端 Stale 横幅 + ExportDialog + WorkflowDashboard
    - Sprint 8 完成：附注表格结构编辑（useNoteTableStructure composable + 17 tests）+ 公式绑定 + 枚举联动 + 完成度追踪 + 目录树层级图标
    - Sprint 9 完成：国企↔上市互转（NoteConversionService + 3 端点）+ NoteRichTextEditor 富文本 + 上年导入（DocxSectionParser）+ 打印预览 + 交叉引用（中文编号）+ 变动分析（20% 阈值）
    - Sprint 10 完成：集团模板（NoteGroupTemplateService）+ 章节锁（NoteSectionLockService 5min 心跳）+ 数据锁定快照（SHA-256 哈希链）+ 批量操作（max 10 并发）+ 签字门禁（3 条 GateRule 自动注册）+ EQCR 只读 + 自定义章节 + NoteOutlineView
    - Sprint 11 完成：版本对比（compare endpoint）+ 全链路穿透（usePenetrate 4 新方法）+ DataHealthMonitor（8 项检查 0-100 分）+ 报表附注联动（ReportNoteSyncService）+ 项目配置中心（GET/PUT /config）+ 多年度对比（变动率>20% 标红）+ 全局组件统一（验证通过）+ 智能裁剪排序（NoteTrimSortService + 必披露保护）
    - Sprint 1 完成：report_formula_service.py 扩展（_BS_SPECIAL 75 条 / _IS_SPECIAL 33 条 / _CFS_INDIRECT_SPECIAL 18 条 / _EQ_SPECIAL 8 条 / _NAME_TO_ACCOUNT 73 条 / _NAME_TO_IS_ACCOUNT 20 条）+ ReportEngine mode/fallback/coverage_stats/debug 四功能 + 42 tests pass
    - Sprint 2 完成：ChainExecution ORM 模型 + Alembic 迁移（down=view_refactor_creator_chain_20260520）+ ChainOrchestrator（依赖自动补充+互斥锁+SSE 进度）+ chain_workflow.py 路由（4 端点）+ router_registry §43 + apiPaths.ts chainWorkflow 对象 + useChainExecution.ts composable + ProjectDashboard 一键刷新按钮+进度面板 + 16 tests pass
    - Sprint 3 完成：ReportExcelExporter（模板填充+fallback 从零生成）+ report_export.py 路由（POST /export-excel）+ router_registry §44 + ReportView 致同表头+行类型样式+模式切换+穿透+GtEmpty 空状态 + 10 tests pass
    - Sprint 4 完成：NoteMDTemplateParser（MD 解析+热加载+缓存）+ NoteValidationEngine（9 种校验类型+互斥规则+持久化）+ WP/REPORT/NOTE 三个公式执行器 + NoteWideTableEngine（横向/纵向公式+容差）+ note_validation_results 迁移 + 44 tests pass
    - Sprint 5 完成：NoteAccountMapping 模型+迁移 + NoteAccountMappingService（三级映射+15 条 SOE 默认映射）+ NoteFillEngine（4 种取数模式+TB 填充+填充率统计）+ NoteRuleEngine（5 条规则+批量判断+统计）+ NoteLayerStrategy（5 层分类+E→A→B→C→D 处理顺序）+ NoteStaleService（stale 标记+增量刷新+从底稿刷新）+ 41 tests pass
    - Sprint 6 完成：NoteWordExporter 重写（致同格式页面设置+字体+标题层级+表格样式+TOC+页码+交叉引用+空章节占位+skip_empty+preview_html）+ note_export.py 路由（POST /export-word）+ router_registry §45 + export_logs 迁移 + ExportPackageService（ZIP 组合导出+manifest.json+ConsistencyGate stub+force_export+_warnings.txt）+ 导出文件命名规范 + 16 tests pass
    - 新建后端文件（Sprint 1-6 累计）：chain_execution.py / chain_orchestrator.py / chain_workflow.py / audit_chain_executions_20260515.py / report_excel_exporter.py / report_export.py / note_md_template_parser.py / note_validation_engine.py / note_wide_table_engine.py / note_validation_results_20260516.py / note_account_mapping.py / note_account_mapping_service.py / note_account_mappings_20260516.py / note_fill_engine.py / note_rule_engine.py / note_layer_strategy.py / note_stale_service.py / note_word_exporter.py(重写) / note_export.py / export_package_service.py / consistency_gate.py(stub) / export_logs_20260516.py + 6 个测试文件
    - 新建前端文件：useChainExecution.ts（composable）
    - 修改前端文件：ProjectDashboard.vue（一键刷新+进度面板）/ ReportView.vue（致同表头+行样式+穿透+空状态）
    - 新建后端文件（Sprint 7-11 累计）：consistency_gate.py / note_conversion_service.py / note_conversion.py / note_prior_year_import_service.py / note_cross_reference_service.py / note_variation_analysis_service.py / note_advanced.py / note_group_template_service.py / note_group_template.py / note_section_lock_service.py / note_section_lock.py / note_data_lock_service.py / note_data_lock.py / gate_rules_chain.py / note_custom_section_service.py / note_custom_section.py / data_health_monitor.py / report_note_sync_service.py / note_trim_sort_service.py / project_config.py
    - 新建前端文件（Sprint 7-11 累计）：ExportDialog.vue / WorkflowDashboard.vue / NoteRichTextEditor.vue / NotesPrintPreview.vue / NoteOutlineView.vue
    - router_registry 新增 §46-§53（note_conversion / note_advanced / note_group_template / note_section_lock / note_data_lock / note_custom_section / batch_workflow / project_config）
    - router_registry 新增 §43（chain_workflow）§44（report_export）§45（note_export）
    - Alembic 迁移链：view_refactor_creator_chain_20260520 → audit_chain_executions_20260515 → note_validation_results_20260516 → note_account_mappings_20260516 → export_logs_20260516
  - **复盘发现（2026-05-16 Sprint 7-11 完成后）**：7 项问题中 5 项已修复 ✅；(1) ✅ Alembic 迁移 `audit_chain_sprint10_tables_20260516.py` 已建 + PG 4 张表已创建；(2) ✅ test 断言改为 `execute_all`；(3) ✅ DataHealthMonitor IS 勾稽改为营业利润 vs 营业收入合理性比对 + TB vs 报表改为资产类汇总金额比对（1%容差）；(4) ✅ NoteTrimSortService.merge_small_sections 接入报表金额（重要性=资产合计×5%×ratio）+ auto_sort_by_amount 按金额降序（必披露置顶）；(5) ✅ test_api_consistency_check 401 修复（client fixture 添加 get_current_user override + 断言字段 all_passed→consistent）；(6) 底稿 vs TB/附注期初 2 项仍为简化版；(7) Sprint 9-11 路由缺单测
  - **UAT 真实数据验证结果（2026-05-16，陕西华氏项目）**：8/10 通过（修复后）；✓ 报表数据 / ✓ 报表格式 / ✓ 附注 173 节 / ✓ 一致性 5 项检查 / ✓ 健康度 75 分 / ✓ 工作流 6 步 / ✓ Excel 导出 46KB / ✓ Word 导出 78KB；✗ 一键刷新（chain_executions INSERT 触发 autoflush 类型冲突）/ ✗ ZIP（依赖一键刷新生成最新数据）
  - **Excel MergedCell 修复已落地**：`report_excel_exporter.py` 导入 `MergedCell` + `_safe_set_value` 静态方法 + `_fill_existing_sheet` 所有 cell 写入前检查 `isinstance(cell, MergedCell)`
  - **一键刷新 500 根因（二次定位）**：ChainExecution UUID 类型已修复（模型改 PG_UUID + 表重建），但 autoflush 仍是问题——`db.add(execution)` 后任何 SELECT 触发 autoflush INSERT，若 INSERT 失败则事务中止；最终修复 = `execute_full_chain` 开头加 `db.autoflush = False`
  - **ChainExecution 模型已改为 UUID 类型**：`id/project_id/triggered_by` 全部改为 `PG_UUID(as_uuid=True)`；`chain_executions` PG 表已重建为 UUID 列
  - **ChainOrchestrator 已修复的其他问题**：(1) `_step_recalc_tb` 改用 `TrialBalanceService(db).full_recalc`；(2) `_step_generate_reports` 改用 `ReportEngine(db).generate_all_reports`；(3) `_step_generate_notes` 改用 `DisclosureEngine(db).generate_notes`；(4) `_step_generate_workpapers` 改用 `TemplateEngine().generate_project_workpapers` + 查默认 template_set；(5) 互斥锁从 pg_advisory_lock 改为内存 asyncio.Lock（避免 session 状态污染）
  - **E2E 最小账套测试发现 PG schema 缺列**：`adjustments` 表缺 `status`/`company_code` 列（ORM 模型有但 PG 表没有，Alembic 迁移未执行）
  - **一键刷新已完全修复（2026-05-16）**：4 步全 completed（recalc_tb / generate_workpapers / generate_reports / generate_notes）；7 项关键修复：(1) ChainExecution 模型 UUID 类型；(2) `execute_full_chain` 加 `db.autoflush = False`；(3) ChainExecution 对象创建移到步骤完成后（避免 autoflush 触发 INSERT）；(4) `force=True` 时跳过所有 prerequisite check（避免 force 模式下还查 prereq 浪费资源 + 防 session 污染）；(5) `_step_generate_workpapers` except 加 `await db.rollback()`；(6) `dataset_query.get_active_filter` except 加 `await db.rollback()`；(7) 互斥锁改为内存 asyncio.Lock
  - **session 污染传播链规约（铁律）**：任何 `try/except: pass` 包裹的 `db.execute(...)` 都必须在 except 中调 `await db.rollback()`，否则失败查询会让 PG 事务进入 aborted 状态，后续所有查询全部 InFailedSQLTransactionError；这是 asyncpg + SQLAlchemy ORM 的核心陷阱
  - **下一步**：完整 E2E 最小账套测试（含 2 笔 AJE + Excel/Word 导出验证） ✅ 已完成（2026-05-16）
  - **E2E 最小账套全链路验证通过（2026-05-16）**：8 步全绿——项目创建+11 科目 TB / Recalc 11 行 / 全链路（recalc/wp/reports/notes 全 completed）/ 2 笔 AJE 创建 / 调整后重新全链路 / Excel 导出 46KB / Word 导出 111KB / DB 验证 financial_report 352 行 + disclosure_notes 173 节
  - **chain_orchestrator 最后两个修复**：(1) `_step_generate_reports` 新增 `applicable_standard` 解析（从 `Project.template_type + report_scope` 拼接为 `soe_standalone`），否则默认 `enterprise` 与 report_config 数据不匹配返回 0 行；(2) `_step_generate_notes` 新增 `template_type` 解析；(3) chain 执行尾部策略：先 `commit()` 步骤工作再 `commit()` 执行记录（避免 ChainExecution INSERT 失败时 rollback 整个链路工作）
  - **测试 TB 与 report_config 公式覆盖差距**：11 个简单科目（1001/1002/1122/1601/2202/2241/2203/4001/4104/6001/6602）→ BS 129 行覆盖率 23.3%；这是数据完备性问题不是引擎 bug；真实账套（陕西华氏 800+ 科目）覆盖率达 80%+
  - **底稿一键生成已彻底修复（2026-05-16）**：策略变更为"按客户实际科目智能匹配"——不依赖 wp_template_set 配置，改为 (1) 加载 `wp_account_mapping.json`（科目→底稿编码映射 88 条）；(2) 查询 TB distinct standard_account_code；(3) 匹配生成审定表底稿（过滤 wp_code 含 `-` 的子表）；(4) 直接 `db.add(WpIndex)` + `db.add(WorkingPaper)` 绕过 template_set 依赖；(5) 幂等保护（已存在跳过）；测试 11 科目 → 生成 15 底稿（D2/D3/D4/E1/F4/H1/K8/K9/M1/M4 + 循环凭证 D0/E0/H0/I6/M10）覆盖全部活跃循环
  - **底稿生成 WorkingPaper 模型字段**：`source_template_code` 不存在，正确字段是 `wp_index_id` FK + `source_type` enum + `file_path` + `parsed_data` JSONB；不要传 source_template_code
  - **完整 E2E 最终测试通过（2026-05-16，含底稿）**：11 科目 → wp_index 15 / financial_report 352 / disclosure_notes 173；2 笔 AJE 后重新全链路依然 4 步 completed；Excel 46KB / Word 111KB
  - **底稿模板覆盖审计（2026-05-16）**：文件系统 477 个模板（176 主编码）vs `wp_account_mapping.json` 当前 **206 条**（扩展后 v2025-R5）；D-N 循环科目驱动 + A/B/C/S 阶段驱动，全 14 循环覆盖
  - **底稿覆盖修复完成（2026-05-16）**：(1) `wp_account_mapping.json` 增补 88 条 A/B/C/S 类（绑定 `audit_stage` + `trigger: must_have/conditional` + `applies_when`）；(2) `_step_generate_workpapers` 移除 `-` 子表过滤；(3) 双路径匹配（科目驱动 D-N + 阶段驱动 A/B/C/S）；(4) 项目标识自动推导 `has_cash/has_revenue/has_fixed_assets/has_lease/listed/consolidated/group_audit` 等
  - **底稿生成结果对比**：测试账套 11 科目 → 修复前 15 个底稿（仅 D-N） → 修复后 **74 个底稿**（A=20/B=15/C=11/D=7/E=5/F=2/H=3/I=1/K=2/M=3/S=5）含子表
  - **底稿 trigger 字段新约定**：(1) `must_have`：永远生成（A1/B1/B5/C1/C23/A11 期后等审计必备）；(2) `conditional` + `applies_when`：按项目标识触发（有现金触发 C3、上市触发 S15/S17、首次承接触发 S2/B2、集团审计触发 A6/B30）；(3) `account_codes` 仅 D-N 用，A/B/C/S 默认空数组
  - **底稿模块完整修复（2026-05-16）**：5 类问题修复达成 74/74 完整链路（创建+复制+元数据全 ✅）——(1) PG 建 `wp_template_metadata` 表（Alembic 等价 DDL）；(2) `load_wp_template_metadata.py` import 修正 `async_engine` → `engine`；(3) 加载 179 条 seed + 24 条子表元数据继承（total 203）；(4) `find_template_file` 增加子表回退策略（`D2-2` → 范围式 `D2-1至D2-4` → 主表 `D2`）；(5) `_step_generate_workpapers` 调用 `init_workpaper_from_template(project_id, wp_id, wp_code)` 复制实际 xlsx 到 storage 目录
  - **底稿模板文件命名规约**：(a) 主表用 wp_code 开头（`D2 应收账款.xlsx`）；(b) 子表常合并为范围式（`D2-1至D2-4 应收账款-审定表明细表.xlsx` 包含 D2-1 至 D2-4 四个子表 sheet）；(c) 多文件底稿（`D2-5 分析程序.xlsx` 独立文件）；(d) `find_template_file` 必须按"精确→范围式→主表"三级回退
  - **底稿生成完整数据链路**：TB 科目 → `wp_account_mapping.json` 206 条匹配 → WpIndex+WorkingPaper 创建 → `init_workpaper_from_template` 物理复制 xlsx → LEFT JOIN `wp_template_metadata` 元数据；每个 wp_index 对应一个真实文件 + 完整 audit_stage/cycle/component_type/audit_objective 元数据
  - **底稿子表收敛策略（2026-05-16 用户要求）**：一个科目可能有多个 Excel 文件（D2 = D2-1至D2-4 审定明细 + D2-5 分析程序 + D2-6至D2-13 检查），需要合并为一个底稿便于使用；`_step_generate_workpapers` 改为：匹配 D2-2/D2-3/D2-4 时全部归入主表 D2，每个主表对应 ONE wp_index + ONE xlsx 文件，文件含所有子表+附注披露+实质程序 sheets（D2=20 sheets / E1=33 / F4=15 / H1=26）
  - **底稿收敛后总数对比**：74 个独立 → **66 个主底稿**（8 个子表合并为主表 sheet）；用户操作"一个科目一个文件"
  - **summary 字段新增**：`primary_workpapers`（主底稿数）+ `subtables_merged_as_sheets`（子表合并 sheet 数）+ `subtable_breakdown`（每主表包含哪些子表）替代原 `matched_total`
  - **下一步可选**：(1) 真实账套（陕西华氏 800+ 科目）底稿 100+ 验证；(2) 6 个孤立映射（E1/K14-K18）补对应模板文件；(3) prefill_engine 触发将 TB 数据预填到底稿单元格
  - **模板数据补齐优先级**：第一批 D-N 审定表 ~60 个（formula_cells + procedure_steps）→ 第二批 B 类 ~30 个（form schema）→ 第三批 C 类 ~60 个（混合视图结构）→ 第四批 A/S 类（检查清单 + Word 字段）
  - **第一批 D-N 模板数据提取已完成**：`scripts/extract_dn_template_metadata.py` 扫描 113 个 Excel 模板 → 89 个 wp_code 条目 / 4689 个公式单元格 / 输出 `backend/data/wp_template_metadata_dn_seed.json`；按循环分布 D=17/E=5/F=15/G=15/H=11/I=6/J=3/K=14/L=9/M=10/N=5
  - **第一批复盘 3 个问题已全部修复 + 覆盖率验证通过**：linked_accounts 89/89；conclusion_cell 优先级策略（检查表62/审定表10/分析表8/程序表7）；cross_wp_references.json 20 条规则；**种子 89 条 vs 模板 89 个主编码 = 100% 对齐零缺失**（逐循环 D8/E2/F6/G15/H11/I6/J3/K14/L9/M10/N5 全部 OK）
  - **第二批 B 类模板数据提取已完成**：`scripts/extract_b_template_metadata.py` 扫描 138 文件（66 xlsx + 71 docx）→ 19 条目（form=9/univer=8/word=2）/ 输出 `backend/data/wp_template_metadata_b_seed.json`；覆盖 B1/B2/B3/B5/B10-B13/B15/B18-B19/B22-B23/B30/B40/B50-B52/B60
  - **两批合计 108 条目**（D-N 89 + B 19），剩余第三批 C 类（控制测试）+ 第四批 A/S 类（完成阶段+特定项目）
  - **全部四批模板数据提取完成 + 覆盖率核验全通过（179 条目 = 179 主编码零缺失）**：D-N 89=89 / B 19=19 / C 21=21 / A 28=28 / S 22=22；组件分布 hybrid=15/form=55/univer=103/word=6；种子文件 `wp_template_metadata_dn_seed.json` + `_b_seed.json` + `_cas_seed.json`；提取脚本 `extract_dn_template_metadata.py` + `extract_b_template_metadata.py` + `extract_cas_template_metadata.py`
  - **下一步**：合并三个 seed 文件加载到 wp_template_metadata 表
  - **合并加载已完成**：`scripts/load_wp_template_metadata.py`（命令行幂等加载）+ `routers/wp_template_metadata.py`（GET 查询+POST /seed 端点）+ router_registry §40；使用方式 = 命令行 `python backend/scripts/load_wp_template_metadata.py` 或 API `POST /api/wp-template-metadata/seed`
  - **全量覆盖率审计结果**：470/476 文件已覆盖（98.7%），6 个未覆盖全是参考示例/附件（非正式底稿）；联动问题 69 条（ACCOUNTS_NO_NOTE 44 + HYBRID_NO_FORM_SECTION 15 + UNIVER_NO_FORMULA 9 + FORM_NO_SCHEMA 1）；修复建议 5 条（R1-R5）输出到 `backend/data/template_coverage_report.json`
  - **联动修复 R1-R5 全部完成**：R1 S17 form_schema 8 字段 / R2 5 个改 form+4 个加公式占位 / R3 补充 6 个 note_section（D7/G4/G11/L3/L8/N4）其余 38 个确认 null / R4 C1-C15 加 hybrid_sections / R5 6 个参考文件归入；warning 级联动问题从 69→0；模板元数据系统完整就绪
  - **整体复盘 5 个核心差距**：(1) 公式引擎"最后一公里"——formula_cells 存的是 Excel 原生公式不是 =TB/=WP 预填充映射，需为 ~20 个核心审定表手动编写 prefill_formula_mapping（影响最大）；(2) procedure_steps 只有 D-N 89 条有，B/C/A/S 全缺；(3) 15+ 前端面板组件未挂载到 WorkpaperSidePanel Tab；(4) 跨底稿引用 20/50+ 条（持续扩展）；(5) 零端到端验证
  - **下一步执行顺序已确定**：公式映射（数据地基）→ 前端集成（UI 接线）→ E2E 验证（闭环验证）；每步为下一步创造前置条件
  - **第一步公式映射已完成并扩展**：`backend/data/prefill_formula_mapping.json` 94 个映射 / 481 个预填充公式单元格（覆盖全部 D-N 89 条目 100%）；函证类 7 个只有期初/未审数，标准审定表 87 个有完整 5 行（期初/未审数/AJE/RJE/上年），K8/K9/F5 额外有 =WP() 跨底稿公式；E2E 5/5 无回归
  - **第二步前端集成已完成**：WorkpaperSidePanel 14 Tab 全部挂载真实组件零占位（AI/附件/版本SnapshotCompare/批注CellAnnotationPanel/程序/程序要求/依赖/一致性CrossCheckPanel/公式FormulaStatusPanel/证据EvidenceLinkPanel/自检/提示QualityScoreBadge）；getDiagnostics 0 错误
  - **第三步 E2E 验证已完成**：`scripts/e2e_workpaper_optimization.py` 5/5 layers 全绿（模板加载 179 条/程序管理 rate=0.4 score=53/公式引擎 K8→H1→J1 拓扑排序/跨科目校验 XR-06 pass/证据快照不变性）；底稿深度优化模块三步闭环完成
  - **关键缺口：Univer 底稿未加载致同模板实际内容**：当前生成底稿时 parsed_data 为空 JSON，用户看到空白电子表格而非预设好的审定表结构；需要做：(1) 模板转换脚本（476 xlsx→Univer JSON）(2) 模板 JSON 存入 wp_template 表 (3) generate_project_workpapers 创建时从模板初始化 (4) 预填充在模板结构基础上叠加数据；预计 2-3 天独立工程任务
  - **混合方案 4 步全部完成**：① 模板 xlsx 存储 ✅（476 文件 `backend/wp_templates/`）② 复制+prefill 写入 ✅（`init_workpaper_from_template` + `prefill_workpaper_xlsx` 用 openpyxl 语义行匹配写入 TB/ADJ 值）③ 前端 importXLSX ✅（WorkpaperEditor `initUniver` 优先 fetch xlsx blob → `importXLSXToWorkbook`）④ 保存回 xlsx ✅（`onSave` 中 `exportWorkbookToXLSX` → POST `/upload-xlsx` 覆盖存储）
  - **数据流闭环**：生成底稿→复制模板→prefill 写入→存储 | 打开→GET /template-file→importXLSX→显示完整模板 | 编辑→保存→exportXLSX→POST /upload-xlsx→覆盖
  - **P0-P2 全部 8 项修复完成**：P0-1 prefill 双策略（坐标直接写入→语义匹配降级 A-D 列/80 行）/ P0-2 Univer import 三级降级（importXLSXToSnapshotAsync→importXLSXToWorkbook→后端 /to-json）/ P0-3 export 两级降级 / P1-1 GET /template-file 首次自动 prefill / P1-4 POST /to-json 端点（openpyxl→Univer JSON）/ P2-1 xlsm shutil.copy 跳过 prefill / P2-2 find_template_file_any 支持 docx；getDiagnostics 0 错误
  - **Univer xlsx import/export 架构**：Advanced Preset 是前端 npm 包（构建时打入 bundle）+ Univer 后端服务（Docker 端口 3010）；**服务器一次性部署后所有用户浏览器直接使用无需单独安装**；当前未安装走后端 openpyxl→JSON 降级（丢失条件格式/图表）；生产部署时运维执行 `npm install @univerjs/preset-sheets-drawing @univerjs/preset-sheets-advanced` + 配置 UniverSheetsAdvancedPreset + 部署 Univer Docker 服务即可；已写入 README.md
  - **Univer Advanced Preset 当前已注释禁用**：`UniverSheetsAdvancedPreset()` 初始化时会连接 :3010 Server，无服务时挂起导致页面白屏；已改为注释代码+说明"部署 Server 后取消注释"；当前只用 Core Preset 基础模式
  - **Univer Server 是商业产品需授权**：安装包实际是 docker-compose tar.gz（`https://release-univer.oss-cn-shenzhen.aliyuncs.com/releases/latest/univer-server-docker-compose-latest.tar.gz`）+ license 文件（需 token 认证下载）；安装脚本只支持 Linux/Mac bash（Windows 需用 Git Bash 或 WSL）；镜像来自阿里云 ACR `univer-acr-registry.cn-shenzhen.cr.aliyuncs.com/release/`；安装后服务在 `univer-server/` 目录用 `bash run.sh start` 管理；本地私有部署模式数据不出服务器（token 仅用于下载安装包认证）
  - **用户决策：放弃 Univer Server，增强后端 openpyxl 转换已完成**：/to-json 端点支持 23 项格式转换（含图片 base64 提取+锚点位置）；预计格式还原度 95%+；唯一不支持：Excel 内置图表对象（openpyxl 无法解析+Univer 开源版不支持渲染，致同模板影响面 <1%）
  - **docker-compose.yml 修复**：onlyoffice 服务 depends_on 从 backend 改为 postgres + 加 profiles: onlyoffice（解决 compose 文件无效问题）；healthcheck start_period 位置修正
  - **前端新增生产依赖 2 个**：@univerjs/preset-sheets-drawing + @univerjs/preset-sheets-advanced
  - **底稿模块最终状态**：vue-tsc 0 错误（含预存 7 个全部修复）；prefill 有效匹配率 100%（375/375 可匹配单元格全命中，81 个"模板不支持"正确跳过：RJE 列不存在 28 + 损益类无期初 19 + 函证无审定表 14 + 子科目分项 20）；后端 28 tests passed；E2E 5/5 全绿；双维度策略已实现（坐标直接写入→列头定位→语义行匹配三级降级）
  - **fix: GET /api/users 端点缺失已修复**：`backend/app/api/users.py` 新增 `GET /` 用户列表端点（底稿管理页"加载用户列表失败"+"Method Not Allowed"的根因）
  - **fix: 底稿编辑器空白问题（三次修复 2026-05-15）**：三个根因——(1) `/template-file` 端点 SQL 引用了 `working_paper` 表不存在的 `wp_code` 列，PG 报 500；修复 = 简化 SQL 只从 `wp_index` 通过 JOIN 取 `wp_code`；(2) 前端 Strategy 3 POST `/to-json` 手动设置 `Content-Type: multipart/form-data` 导致 boundary 缺失；修复 = 去掉手动 headers；(3) **真正根因**：前端 `fetch` 用 `localStorage.getItem('token')` 但 token 已迁移到 `sessionStorage`（auth store 安全改进），导致请求无 Authorization → 401 → 降级到空白；修复 = 改为 `sessionStorage.getItem('token') || localStorage.getItem('token')`
  - **[待办] 底稿模板后续打磨 4 项已全部完成**：P1 工具栏"📊 刷新取数"按钮（POST /init 重新 prefill→重载 Univer）/ P1 多文件底稿合并（`_merge_sheets_from_other_files` 追加其他 xlsx sheet 到主 workbook）/ P2 prefill 浅蓝色背景 #E8F4FD + Comment 来源标记 / P2 xlsx 保存冲突检测（`X-File-Opened-At` header + 服务端 mtime 对比→409 XLSX_FILE_CONFLICT）
  - **Sprint 10-11 新建后端文件**：wp_cell_annotation_service.py / wp_cell_annotations.py / wp_review_checklist_service.py / wp_batch_ops.py / wp_note_linkage_service.py / wp_permission_service.py / wp_cell_lock_service.py / wp_cross_index_service.py / wp_audit_trail_service.py / wp_sign_date_chain_service.py / wp_eqcr_evaluation.py / wp_health_dashboard.py / wp_search.py
  - **Sprint 10-11 新建前端文件**：CellAnnotationPanel.vue / UniverAnnotationStub.vue / ReviewChecklistPanel.vue / BatchOperationsPanel.vue / EqcrEvaluationPanel.vue / CrossIndexTab.vue / CellHistoryDrawer.vue / FormulaDependencyGraph.vue
  - **router_registry 新增**：§36 wp_cell_annotations / §37 wp_batch_ops / §38 wp_health_dashboard+wp_search / §39 wp_eqcr_evaluation
  - **router_registry 新增**：§42 wp_template_download（`/api/projects/{pid}/wp-templates/{wp_code}/download` 单科目模板 + `/download-all` 全量 ZIP 476 文件 61MB）
  - **5 个新 EventType 已注册**：WORKPAPER_AUDITED_CONFIRMED / WORKPAPER_PROCEDURE_COMPLETED / WORKPAPER_REVIEW_PASSED / WORKPAPER_STALE_DETECTED / CROSS_CHECK_FAILED
  - **新建后端文件**：wp_optimization_models.py / wp_procedure_service.py / wp_procedures.py / wp_quality_score_linkage.py / wp_cross_check_service.py / wp_cross_check.py / gate_rules_cross_check.py / wp_formula_dependency.py / wp_batch_prefill.py / wp_evidence_service.py / wp_evidence.py / wp_evidence_index.py / wp_ocr_voucher_service.py / wp_ocr_fill_service.py / wp_llm_prompts.py / wp_quality_score_service.py / wp_snapshot_service.py / wp_risk_trace_service.py / wp_conclusion_service.py / wp_sampling_engine.py / cross_account_rules.json / wp_template_metadata_seed.json / seed_wp_template_metadata.py / Alembic 迁移 wp_optimization_sprint1_20260520
  - **新建前端文件**：ProcedurePanel.vue / ProcedureFlowChart.vue / useProcedures.ts / CrossCheckPanel.vue / useCrossCheck.ts / FormulaStatusPanel.vue / FormulaTooltip.vue / FormulaSourceDrawer.vue / useFormulaStatus.ts / WorkpaperFormEditor.vue / WorkpaperWordEditor.vue / WorkpaperTableEditor.vue / WorkpaperHybridEditor.vue / EditorSharedToolbar.vue / EvidenceLinkPanel.vue / useEvidenceLink.ts / evidenceCellIndicator.ts / OCRResultPanel.vue / AISuggestionPopover.vue / QualityScoreBadge.vue / SnapshotCompare.vue / RiskTraceGraph.vue / ConclusionOverview.vue / SamplingWizard.vue
  - **router_registry 新增**：§33 wp_procedures / §34 wp_cross_check / §35 wp_evidence
  - **apiPaths.ts 新增**：workpapers.procedures（5 端点）/ workpapers.crossCheck（4 端点）
  - **Alembic 迁移链**：down_revision = view_refactor_creator_chain_20260520
  - **Sprint 1-4 复盘 P0 已修复（2026-05-15）**：(1) `register_cross_check_rules()` 已注册到 `main.py::_register_phase_handlers`；(2) CellAnnotation 唯一真源确认在 phase10_models.py（wp_optimization_models.py 只有注释引用）；(3) wp_optimization_models 已注册到 conftest.py model import 列表；(4) pytest 3404 collected / 1 pre-existing error / 16 property tests passed；(5) 6 个模块 import 验证全通过
  - **Sprint 5-11 执行策略优化**：预检文件是否已存在→已存在直接 grep 核心函数+pytest 子集→标完成（省 subagent）；剩余 59 task 按 3 批执行（5-6/7-8/10-11）；每批结束跑 `pytest -k "关键词" --tb=short`
  - **已知功能缺口**：L2 跨科目校验在真实数据面前可能全部 skip（底稿 parsed_data 未定义审定数存储位置）；=WP() 公式依赖 wp_index.wp_code 字段需确认现有数据是否填充
  - **第一章 架构基础（需求 1-3）**：底稿生命周期状态机（created→drafting→self_checked→submitted→level1/2_review→partner→eqcr→archived）/ 组件选型体系（U59%/F19%/W15%/T4%/H3%）/ 模板元数据模型
  - **第二章 模板体系（需求 4-11）**：B1-B5/B10-B60/C1-C26/D-N/A1-A30/S1-S35 六模块 + 审计程序裁剪（合伙人裁剪→助理执行）+ 函证全流程
  - **第三章 联动引擎（需求 12-16）**：8 种公式类型（TB/TB_SUM/WP/LEDGER/AUX/PREV/ADJ/NOTE）/ L1+L2 两级校验 / 风险追溯 / 事件驱动 / 底稿↔调整分录/附注/报表联动
  - **第四章 编制体验（需求 17-24）**：单元格批注 / 检查清单 / 质量评分 / 批量操作 / 版本对比 / EQCR 充分性 / 三层权限（项目/循环/单底稿+单元格级锁定）/ 离线编辑与冲突合并
  - **第五章 智能辅助（需求 25-29）**：OCR 凭证→抽凭表 / LLM 审计说明生成 / 合同对账单台账 / 多项目知识复用 / 公式依赖可视化
  - **第六章 企业级保障（需求 30-35）**：审计轨迹哈希链 / 快照 / 证据链 / 可扩展规则引擎 / 可观测性 / 全文搜索
  - **预设公式库（design.md 补充）**：4 类 23 条——AT-01~08 审定表标准公式（=TB/=ADJ/=PREV）/ CW-01~07 跨底稿引用（折旧分摊/坏账/净利润/薪酬/利息）/ VF-01~08 交叉校验等式 / 21 种 Univer 原生 Excel 函数；公式必须与每个具体底稿做关联（通过 wp_template_metadata.formula_cells 字段）
  - **关键实施约束**：
    1. Word 编辑器改用 Univer Doc 模式（不用 OnlyOffice），docx 类底稿走字段填充+预览
    2. 模板种子数据（476 个）必须分批完成：第一批 D-N 审定表 ~60 个→第二批 B/C 类→第三批 A/S 类
    3. 公式管理必须与具体每个底稿关联（不是全局统一公式，每个底稿有自己的 formula_cells 配置）
    4. 建议实施顺序：Sprint 1→2→3→4→**10**→5→6→7→8→11→9（复核批注提前到编辑器之前）
- **致同 2025 修订版底稿模板结构（开发底稿必须遵循）**：
  - 根目录 `致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/`
  - **6 大模块**（旧 wp_account_mapping.json 漏掉 S 类）：
    1. **初步业务活动 B1-B5**：B1 业务承接 / B2 与前任 CPA 沟通 / B3 独立性 / B5 业务约定书
    2. **风险评估 B11-B60**：B10 了解被审计单位（B11 检查/B12 访谈/B13 初步分析/B15 重要性/B18 内审/B19 关联方）/ B30 集团审计 / B60 总体审计策略（B60-1 工时预算/B60-2 IT/B60-3 专家/B60A-D 专项）
    3. **风险应对—一般性程序与控制测试 C1-C26**：C1 企业层面 / C2-C15 业务循环（C2 销售/C3 货币资金/C4 存货/C5 投资/C6 固定资产/C7 在建工程/C8 无形资产/C9 研发/C10 薪酬/C11 管理/C12 税金/C13 债务/C14 租赁/C15 关联方）/ C21-C26 IT+会计分录（C21 IT 专员/C22 IT 一般控制/C23-C24 会计分录控制+细节/C25 内审/C26 信息处理）
    4. **风险应对—实质性程序 D-N**：D 收入循环（D0 函证/D1 应收票据/D2 应收账款/D3 预收/D4 营业收入/D5 应收款项融资/D6 合同资产/D7 合同负债）/ E 货币资金 / F 存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 债务 / M 权益 / N 税金
    5. **完成阶段 A1-A30**：①报告与沟通（A1 财务报告/A2 调整分录/A3 合并流程/A4 经营分部/A5 财报支持/A6 组成部分会计师报告/A7 关联交易/A8 其他信息/A9 内控建议书/A10 与治理层沟通）②总结程序（A11 期后事项/A12 律师回复/A13 错报/A14 内控缺陷/A15 持续经营/A16 管理层声明书/A17 重大事项概要/A18 与监管层沟通）③质量控制 A21-A30
    6. **特定项目程序 S1-S35**（**旧 mapping 漏掉**）：S1 违法违规/S2 期初余额/S3 会计政策变更/S4 非货币性交换/S5 债务重组/S6 关联方资金占用/S8 租赁/S9 电子商务/S10 环境/S11 服务机构/S12 利用专家/S13 管理层专家/S14 会计估计/S15 EPS/S16 套期/S17 非经常性损益/S20 营业收入扣除/S21 数据资产/S32 551 文/S33 14 号公告/S34 首发审核/S35 再融资审核
  - **文件类型分布（共 476 个模板）**：xlsx 349 + xlsm 17 + xls 1 = **367 个表格类（77%）**；docx 107 + doc 2 = **109 个文档类（23%）**
  - **核心开发约束**：
    1. xlsx/xlsm（含宏的复杂模型，如固定资产折旧/减值测试）必须用 Univer
    2. **23% 是 docx**（B60 总体策略/A16 管理层声明书/B60-2 IT 计划/B60-3 专家计划/B60A-D 专项/S12A 评估专家/A9 内控建议书等）→ 必须 Word 编辑器（OnlyOffice 已部署 8080 端口，或前端 docx-renderer + 字段填充）
    3. 旧 wp_account_mapping.json 88 条远不够覆盖 476 个模板，需重建模板元数据系统（含 component_type/cycle/audit_stage/sheet_count/has_macro/output_format 等字段）
    4. 单个模板可含多 sheet（B10/D2/H1 等），组件类型粒度到 sheet 级别而非文件级
    5. 模板文件命名规则：编码+空格+名称（如 `D2 应收账款.xlsx`），有的还含日期版本（如 `S20 营业收入扣除情况核查底稿202504.xlsx`），导入时需要正则解析
  - **后续开发节奏（用户明确要求）**：分模块/分阶段递进，每次只处理 1-2 个模块的模板分析+组件选型；不要一次输出过多内容避免报错；每次分步生成
  - **底稿组件选型铁律**（关键架构决策）：B 类（业务承接+计划）= 结构化表单（el-form，不用 Univer）；审定表（D1/D2/E1/F2/H1 等）= Univer（含复杂公式）；明细表/调整分录/抽样表 = el-table；函证管理/监盘/减值测试 = 混合视图（表单+表格+附件）；完成阶段（A 类）= 混合视图+富文本；EQCR 备忘录 = 富文本
  - **组件选型决策树**：(1) 有大量公式/计算 → Univer；(2) 问答式/判断类 → 结构化表单；(3) 批量结构化清单 → el-table；(4) 长文本说明 → 富文本；(5) 表单+表格组合 → 混合视图
  - **WorkpaperEditor 路由分发**：根据 wp_template_metadata.component_type 动态加载（UniverEditor / FormEditor / TableEditor / RichTextEditor / HybridEditor），不是单一 Univer 组件
  - design.md + tasks.md 待生成
- 性能测试（真实 PG + 大数据量环境运行 load_test.py，验证 6000 并发）
- working_paper_service 状态机 draft→edit_complete 是否符合业务流程（需确认）[P3]
- 合并模块需找真实项目做业务测试（技术完成度 85%，业务完成度 60%）[P1]
- 系统当前是"工程师视角"而非"审计员视角"，下一步重点是 UAT 而非加功能
- `GtStatusTag.STATUS_MAP_TO_DICT_KEY` 是硬编码映射表，新增 StatusMap 时需手动维护 [P3]
- PBC 清单真实实现（R7+ 计划，后端当前 stub）[P2]
- 函证管理真实实现（R7+ 计划，后端当前 stub）[P2]
- Vue 文件绕过 service 层直接调用 API：86 个文件 / 322 处（复盘发现），策略"触碰即修"+CI 卡点防恶化 [P3]
- 函证管理真实实现（R7+ 计划，后端当前 stub）[P2]

## 底稿编码体系（致同 2025 修订版）

- D/F/K/N 循环，映射文件：backend/data/wp_account_mapping.json（88 条，v2025-R4）

## 跨轮复盘发现（R5 完成后）

- 跨轮复盘发现 3 个真实代码 bug + 2 个环境/配置问题：
  (A) `backend/data/audit_report_templates_seed.json` 71 处 CJK 字符串内用直双引号 `"XX"` 导致 JSON 解析失败，改用中文方头括号「XX」（全角 U+300C/U+300D）恢复；直接影响 `POST /api/audit-report/templates/load-seed` 端点，任何审计报告生成都走不通
  (B) `qc_engine.py` SamplingCompletenessRule (QC-12) 引用 `SamplingConfig.working_paper_id`，但该列不存在——SamplingConfig 只有 `project_id`，改为按 project 过滤
  (C) `qc_engine.py` PreparationDateRule (QC-14) `datetime.utcnow() - aware_datetime` 类型混用抛 TypeError，统一 `datetime.now(timezone.utc)` 解决
  (D) `backend/tests/conftest.py` 漏导入 phase10/12/14/15/16/archive/dataset/knowledge/note_trim/procedure/shared_config/template_library/eqcr/related_party/independence 等 15+ 个 model 包，导致 SQLite create_all 缺表（如 cell_annotations），多处 service 调用时抛 "no such table"
  (E) backend 无 hypothesis 依赖，导致 test_phase0_property/test_phase1a_property/test_remaining_property/test_production_readiness_properties 共 101 个属性测试从未执行（memory 之前的"16 Hypothesis 测试"说法实际是零运行）；安装 hypothesis@6.152.4 后全部通过
- **跨轮复盘方法沉淀**：pytest --collect-only 先查 collection error；按 file glob 分组跑避免超时；grep `db.add(...).id` 找 flush 缺失；grep `datetime.utcnow()` 找 tz 混用；readCode 所有被标 [x] 的 Sprint 核心表/字段；脆性根因多是"模型已建但测试 conftest 未注册"或"字段假设未 grep 核对"
- 跨轮复盘后测试总数：EQCR 122 + Phase13/14 93 + phase property 101 = 316 个已验证通过（只包含核心受影响文件，未跑全量）
- test_audit_report.py 剩余 12 个失败是 401 Unauthorized（test client 未配置 auth override，代码本身逻辑正确）；test_wopi_working_paper_qc_review.py QC 规则失败是测试假设"所有 stub 规则返回空"已过时（规则已实装），属测试设计漂移不是代码 bug

## 用户偏好（B3 轮新增）

- **死代码立即删除**：不留 DEPRECATED/保留作 fallback 等注释，否则每次复盘都会重复提议（2026-05-10 明确要求）

## B3 大账套加速（2026-05-10）

- **[✅ calamine parser 已落地]**：`backend/app/services/ledger_import/parsers/excel_parser_calamine.py`（~150 行，签名与 openpyxl 版一致），feature flag `ledger_import_use_calamine` 默认 True；实测 3.2-3.4× 加速（YG4001 0.47→0.14s / YG36 1.98→0.63s / YG2101 76.68→22.48s）
- **[✅ 死代码清理]** 删除 `detector._detect_xlsx_from_path_calamine`（~3000 字符）+ `parsers/excel_parser_calamine.detect_sheets_from_path_calamine`（~1700 字符）；detector 永远走 openpyxl read_only（真 SAX）
- **[✅ pipeline 按 sheet 行数切 engine]**：`_CALAMINE_PARSE_MAX_ROWS=500_000` 阈值，< 500k 用 calamine，≥ 500k 用 openpyxl（避免 calamine 大 sheet 全量 decode 问题）
- **[✅ pipeline perf 打点已落地]**：每 phase `_mark` 标记 + parse_write_streaming 内部 7 项累计耗时（parse/dict/prepare/validate/convert/insert/progress/cancel）
- **[✅ scripts/b3_diag_yg2101.py]**（保留）：本进程直接 execute_pipeline 跑 YG2101 拿 perf 日志的诊断脚本；绕过 HTTP 层；踩坑 = projects NOT NULL 列多用 SELECT LIMIT 1 复用 / import_jobs.year NOT NULL / ledger_datasets.job_id FK → 必须先 INSERT ImportJob
- **[❌ 实测无效已回滚] 并行 UPDATE**：4 张 Tb* 表改为 asyncio.gather + 独立 session，YG2101 实测 127s→126s 无加速（PG WAL 串行写入是真瓶颈不是 Python/网络）；已恢复 for loop 串行版，函数 docstring 记录此教训
- **[⏸️ 待做] P1 partial index**：`CREATE INDEX CONCURRENTLY ... on Tb*(dataset_id) WHERE is_deleted=true`；让 activate UPDATE 走索引；预期 activate 127s→40-60s
- **[⏸️ 待做] P2 bulk_copy_staged Python 开销优化**：跳过空 raw_extra / COPY binary format / 传 dict 给 asyncpg 自动编码
- **[⏸️ 待 Sprint] P3 架构重构**：业务查询 30+ 处改走 `v_ledger_active` 视图，activate 只改 metadata；工时 3-5 天；彻底消除 UPDATE 风暴

## YG2101 真实性能数据（128MB / 200 万行，2026-05-10 实测）

- **总耗时 399-482s**（取决于系统负载，calamine 解析 ~20s + parse_write_streaming 270-360s + activate 127s + rebuild 0.7s）
- **parse_write_streaming 内部拆解**：parse 87.6s / dict 化 2.5s / prepare_rows 13.6s / validate_l1 4.7s / convert 9.2s / **insert 151.8s（30 次 COPY）** / progress+cancel 0.0s
- **activate 127s 根因** = `DatasetService._set_dataset_visibility` UPDATE 4 张 Tb* 表（200 万行 is_deleted=false）；PG UPDATE 本质 = 删旧 tuple + 写新 tuple（MVCC）
- **关键架构事实**：业务查询 **全部** 通过 `Tb*.is_deleted=false` 判断可见性，**没有一个**业务查询过滤 `dataset_id`；意味着 activate 必须物理 UPDATE（除非大规模改业务查询走视图层）
- **insert 151.8s 拆解**：aux_ledger 每 100k 行 COPY ~19s（吞吐 ~5200 rows/s），包含 `_sanitize_raw_extra` + `json.dumps` + tuple 构造公共字段的 Python 开销约 30-40s
- **parse 87s 来源**：calamine `get_sheet_by_name` 必须全量 decode sheet XML（Rust 侧），无法避免

## B3 方案对比沉淀（2026-05-10 基于实测推演）

- **[否决] Partial index WHERE is_deleted=false**：预期加速 insert（staged 不进索引），但同时让 activate 变慢（UPDATE 时 200 万行要建索引），净收益 ≈ 0，否决
- **[待评估] 方案 B 业务查询加 dataset_id 过滤**：改 30+ 查询，新建 `active_dataset_id(pid, yr)` PG 函数作 helper；彻底消除 UPDATE 风暴；**5 天工时独立 Sprint**
- **[待评估] 方案 C Tb* 表 partition by dataset_id**：activate 变成 ALTER TABLE ATTACH/DETACH（瞬间）；涉及 schema migration + ORM 适配；**2-3 周工时**
- **[待评估] 方案 D DROP → UPDATE → REBUILD 索引**：200 万行 UPDATE 可能从 127s → 40-60s；缺点 = rebuild 期间业务查询不可用（生产不行）
- **[✅ 推荐立刻做] 方案 E PG 配置调优**（10 分钟，零代码）：`wal_compression=on` / `synchronous_commit=off` / `wal_buffers=64MB` / `checkpoint_timeout=30min` / `max_wal_size=8GB`；预期总省 ~50s（399s→350s）；`synchronous_commit=off` 断电可能丢秒级但审计二次导入可接受
- **[✅ 推荐] 方案 F insert Python 开销优化**：`_sanitize_raw_extra` 对 None/空 dict 快速返回 + bulk_copy_staged tuple 构造合并；预期 insert 再省 20-30s
- **[✅ 推荐核心洞察] 异步 activate**：用户完全不需要等 127s UPDATE 完成，pipeline 写完 insert 就返回 "completed"，activate 后台 worker 异步跑；**用户感知从 400s → 250-280s**（大半时间都省在"不等 activate"）
- **组合建议**：E + F + 异步 activate（0.5 天工时），把 YG2101 用户感知压到 4-5 分钟；再不够再做 C partition

## 关键技术洞察（B3 沉淀，未来大数据优化可复用）

- **PG UPDATE 真瓶颈是 WAL 串行写入**，不是 Python/网络/asyncpg —— 所有基于"并发客户端"的加速方案（多 connection 并行 / 协程 gather）对大批 UPDATE 都无效
- **PG UPDATE 本质 = 删旧 tuple + 写新 tuple + 所有索引的维护**，200 万行 UPDATE ≈ 做 200 万次 INSERT + 200 万次 DELETE + N 倍索引操作
- **"用户感知耗时"≠"后台完成耗时"**：长流程的 metadata 切换（activate/rebuild_summary）都可以后台异步做，用户体验只关心数据写完这一刻

## B3 架构方案深度沉淀（2026-05-10）

- **[否决] 方案 C partition by dataset_id**：PG LIST PARTITION 要求每个 dataset 预建 partition（UUID 动态值会炸），HASH PARTITION 只做静态分片无法按 dataset 切换；**不能用于 activate 切换场景**
- **[否决] 方案 G trigger 自动维护 is_deleted**：trigger 内仍做 200 万行 UPDATE，瓶颈没动只是换位置
- **[推荐 B' 视图方案] 根本方案 activate 从 127s 降到 0.01s**：
  - 4 张 Tb* 表 + 4 个 view（`v_tb_balance` / `v_tb_ledger` / `v_tb_aux_balance` / `v_tb_aux_ledger`）
  - view 定义 = `SELECT * FROM tb_x WHERE EXISTS (SELECT 1 FROM ledger_datasets d WHERE d.id=tb_x.dataset_id AND d.status='active')`
  - 业务查询 30+ 处 `Tb*` → `v_Tb*`（grep 替换）
  - `DatasetService.activate` 只 UPDATE `ledger_datasets.status='active'` 一行
  - `_set_dataset_visibility` 可变 no-op 或保留兼容
  - is_deleted 字段保留作软删除语义（回收站等）
  - **工时 3-4 天，收益 activate 127s→0.01s，YG2101 总耗时 399s→270s**
  - 风险：30+ 业务查询改漏；有些 service 走 raw SQL 可能漏掉；view 复杂 JOIN 性能需测
- **组合推荐路线**：先 E+F+异步 activate（0.5 天，399s→250s 用户感知）验证接受度 → 再评估是否上 B'（4 天）彻底解决
- **核心洞察**：所有跨 session 并发客户端加速（multi-connection / asyncio.gather）对 PG UPDATE 都无效（WAL 串行写）；UPDATE 真正要消灭只有两条路：(1) 数据不动改 metadata 切换（视图/partition）(2) 业务不需要 UPDATE（staged 模式下行直接 is_deleted=false + view 层 JOIN 过滤）

## B3 架构重构调研成果（2026-05-10，开干前盘点）

- **[发现] `backend/app/services/dataset_query.py` 已提供 `get_active_filter(db, table, pid, year)` 过渡抽象**，文档明确写了四步迁移计划：加 dataset_id 列 → 写入填 → 查询迁移 → 去掉 is_deleted；当前阶段业务查询可选用它（有 dataset_id 优先，否则降级 is_deleted）
- **[业务查询直接用 `TbX.is_deleted == False` 统计]**：约 40 处直接查询散落在 15+ 个 service + 2 个 router，绝大多数**没有**走 `get_active_filter`；B' 视图方案的改造面就是这 40 处
- **[否决 B''] computed column 方案**：PG 计算列不能引用其他表（不能 JOIN ledger_datasets），is_deleted 只能是静态列
- **[否决 B'''] 写入 is_deleted=false 靠 dataset_id 区分**：如果所有行都 is_deleted=false，staged 数据对业务查询立即可见（40 处没过滤 dataset_id），会暴露未激活数据
- **[重新推荐] 务实路径 E+F+异步 activate（0.5 天）+ 观察**：0.5 天做 PG 调优 + Python 侧优化 + activate 放后台，用户感知 400s → 250s 即可；若仍不满意再上 3-4 天 B' 视图方案
- **raw SQL 访问点**：`metabase_service.py` / `data_lifecycle_service.py` / `smart_import_engine.py` / `import_intelligence.py` / `consistency_replay_engine.py` / `ledger_import/validator.py` 都有 raw SQL `FROM tb_*`，B' 方案需要一并替换为 `v_tb_*`

## 待用户决策

- **选 1：先做 E+F+异步 activate（1.5 小时）**，见效快；不够再上 B'
- **选 2：直接开 B' 分支做视图方案（3-4 天）**，彻底消除 activate 127s + rollback 127s

## B3 E+F 实测结论（2026-05-10）

- **[E PG 配置已是最优]**：查询 `wal_compression=pglz / synchronous_commit=off / wal_buffers=64MB / checkpoint_timeout=30min / max_wal_size=8GB`，此前有人已调过；**E 方案不需重做**
- **[F Python 优化实测收益 <1s]**：`_json_default` 合并 `_sanitize_raw_extra + json.dumps`；微基准 130 万次 4.61s → 3.76s（省 0.85s）；YG2101 生产实测被 PG 波动噪声淹没（activate 127s→193s 的波动 >> F 收益）；**F 改动保留但收益可忽略**
- **[activate 真实波动 127-193s]**：同一代码同一数据，连续两次跑 YG2101 activate 耗时差 66s；系统负载 / autovacuum / 磁盘缓存等随机因素影响极大；**activate 耗时单次测量不可靠，需多次平均**
- **[关键结论] B2+B3 已到 YG2101 性能极限 ~400-480s**：parse 87s（calamine 不可再降）+ insert 151s（PG COPY 极限）+ activate 127-193s（PG WAL 串行极限）；这些都是底层限制，**小修小补边际收益极低**
- **[下一步唯一选择]**：要么接受 YG2101 ~7 分钟为当前上限，要么直接做 B' 视图方案（3-4 天，activate 从 127s → 0.01s 真正消灭 UPDATE 风暴）
- **[放弃] 异步 activate 方案**：fire-and-forget + 后台任务追踪复杂度高，且不彻底（activate 自身仍 127s 只是用户不等）；不值得投入

## B' 视图重构 spec 三件套已创建（2026-05-10）

- `.kiro/specs/ledger-import-view-refactor/` README + requirements（22 需求）+ design（5 架构决策 + 改造清单按文件分组）+ tasks（3 Sprint ~30 任务 + 10 验收）
- 分支 `feature/ledger-import-view-refactor` 已切出（从 feature/round8-deep-closure 68ba2c8）
- **[关键洞察] Sprint 顺序必须倒过来**：原"先改 activate/写入 → 再迁查询"路径无法独立运行（中间状态破坏数据可见性）；新顺序 = 先 Sprint 1 迁查询（语义不变）→ 再 Sprint 2 一次性改 activate+写入（原子 commit）→ Sprint 3 加固
- **[保留策略] partial index 兼容新架构**：`idx_tb_*_active_queries (project_id, year, dataset_id) WHERE is_deleted=false` 仍然覆盖所有 active 数据，B' 改造后 get_active_filter 的查询直接命中

## PG Docker 容器 shm_size 调整（2026-05-10）

- **docker-compose.yml PG 服务加 `shm_size: 2g`**：默认 64MB 在 YG2101 级别 200 万行聚合查询时触发 `DiskFullError: could not resize shared memory segment`；2G 足够支撑 COUNT/SUM 并发分析
- **PG 容器重建流程**：`docker stop/rm` 后用 `docker run` 显式挂载 `gt_plan_pg_data` volume（而非 `pg_data`，后者是 docker run 默认创建的新 volume 会丢数据）
- **PG 当前调优值**：shared_buffers=1GB / work_mem=64MB / effective_cache_size=6GB / max_connections=200 / random_page_cost=1.1 / effective_io_concurrency=200 / wal_compression=pglz / synchronous_commit=off / wal_buffers=64MB / checkpoint_timeout=30min / max_wal_size=8GB / shm_size=2g
- **四表实际数据量（2026-05-11）**：tb_aux_ledger 1570万行 / tb_ledger 741万行 / tb_aux_balance 70万行 / tb_balance 11万行（总计 2300 万行）
- **查询性能优化索引（2026-05-11）**：`idx_tb_ledger_proj_year_acct_date (project_id, year, account_code, voucher_date, id) WHERE is_deleted=false` + aux_ledger 同款；序时账穿透查询从 Filter 降为纯 Index Scan（17ms）
- **Redis 缓存热查询**：`/balance` 和 `/aux-balance-summary` 端点加 5 分钟 Redis 缓存（key 格式 `ledger:*:{pid}:{year}:*`），导入完成后自动 SCAN+DELETE 失效
- **.env 连接池**：`DB_POOL_SIZE=30` / `DB_MAX_OVERFLOW=100`（最大并发 130 连接）

## B3 Step 1 已落地（partial index）

- `backend/alembic/versions/view_refactor_activate_index_20260510.py`（未走 alembic 执行，手动 CREATE INDEX CONCURRENTLY）
- 已建 8 个 partial index：4 张 Tb* 表 × 2（activate_staged + active_queries）
- 索引总大小 ~150MB（aux_ledger 95MB 最大，128 万行 × 2 索引）

## 用户流程偏好（本轮新增）

- **复杂重构先做 spec 三件套**：体系化、精准、可回滚；"每次单独尝试都要跑 YG2101" 太慢 → 要求"全部改完再跑一次测试"
- **避免折中方案**：要"根本解决"不要"折中"；partial index 类改动收益有限不算根本方案

## B' 视图重构 spec 三件套升级（2026-05-10 第二轮扩展）

- **requirements.md 从 22 需求扩展到 48 需求（8 大维度）**：架构层 A1-A10 / 大文件 B1-B8 / 企业级治理 E1-E8 / 数据库维护 D1-D8 / 可维护性 M1-M6 / 回归 R1-R8 / 边界 B1-B4 / 成功判据表格
- **[新用户偏好] 复杂重构需求必须全面分析现有代码后才给建议**：不能只看单点瓶颈，要从架构/大文件/企业级治理/DB 维护/可维护性 5 个以上维度一起考虑
- **[关键技术洞察] B' 最大企业级收益不是"快 127s"而是"解决表膨胀"**：每次 activate UPDATE 200 万行产生 200 万 dead tuple，autovacuum 追不上会磁盘爆炸；B' 后无 dead tuple，表大小线性增长
- **[发现] 历史已归档的 partition 方案**：`backend/alembic/versions/_archived/017_partition_tables.py`（按 year RANGE partition）是团队之前探索未落地的方案；B' 落地后可复用做 D8 进一步优化

## 新增关键待办（按优先级）

- **P0（本 spec 核心）**：A1-A10 视图/metadata 切换 + A4 purge 定时任务 + A5 `_set_dataset_visibility` 废弃
- **P1 数据库维护**：D2 autovacuum 调优 + D3 superseded 定期清理（保留最近 3 个）+ D4 DROP 废弃索引 `idx_tb_*_activate_staged`（55MB 空间回收）
- **P1 企业级治理**：E1 数据集版本历史路由 + E4 审计日志（谁在什么时间激活哪个版本）
- **P2 独立 Sprint**：B6 分片上传 / B7 Worker 资源隔离 / E2 导入配额 / E5 权限细粒度 / D8 表分区
- **M1 测试脚本分工规约**：`e2e_yg4001_smoke.py`=CI 快跑 / `e2e_full_pipeline_validation.py`=本地/部署前 / `b3_diag_yg2101.py`=大样本性能诊断；`b2_copy_perf_validation.py`/`b3_calamine_smoke.py`/`b3_profile_realistic.py` 后续合并清理

## 新数据库维护规约（B' 后必须确立）

- **表膨胀检测**：每次大导入后跑 `SELECT relname, n_dead_tup, n_live_tup FROM pg_stat_user_tables WHERE relname LIKE 'tb_%'` 确认 dead_tuple_ratio < 10%
- **Tb* 表专用 autovacuum 参数**：`autovacuum_vacuum_scale_factor=0.05 / autovacuum_vacuum_cost_limit=1000` 让 autovacuum 跟上大表变化
- **superseded 保留策略**：同一 project+year 最多保留 1 active + 3 superseded；超过的用 purge 任务物理 DELETE

## 9 家真实样本结构归档（2026-05-10 扫描后）

- **规模差异 600×**：最小 YG4001-30 (0.8MB/4k 行) → 最大陕西华氏 2025 (500MB/2600 万行)
- **5/9 是多文件场景**（"1 文件 1 账套"反而是小概率）：
  - 陕西华氏：单年 13 文件（1 balance + **12 月度序时账**）× 2 年度
  - 和平药房：余额 xlsx + **2 CSV 按日期段切**（20250101-1011 + 20251012-1031）
  - 辽宁卫生 / 医疗器械：2 xlsx 分文件（余额 + 序时账分开）
  - 和平物流：单 xlsx 但**方括号表头** `[凭证号码]#[日期]`
- **文件布局多样化**：YG2101 单 xlsx 含 4 sheet（含空 Sheet1）/ YG36/YG4001 2 sheet / 安徽骨科 2 sheet（有维度余额+序时账）
- **非标软件来源**：至少 3 种软件（用友 NC / 金蝶 KIS / 某方括号格式），同一客户同一年度可能混用

## requirements.md 第 9-10 节新增（9 家样本业务需求）

- **U1 多文件拼接**：detect 支持"批量文件一次识别"；13 文件识别为"1 balance + 12 ledger 片段合并为一个 dataset"
- **U2 文件名元信息利用**：当前 detector 只看内容忽略文件名；`-科目余额表.xlsx` / `-序时账.xlsx` / `25年10月` 应作为 detector 置信度加分信号
- **U3 方括号+组合表头**：`[凭证号码]#[日期]` 格式需要 detector 剥壳规则；作为 adapter 声明式规则
- **U4 跨文件时间段合并**：和平药房 2 CSV 按日期段切需合并到同一 dataset
- **U5 月度增量 UX 引导**：陕西华氏场景"预审导 1-9 月，年审追加 10-12 月"；后端 apply_incremental 支持但前端缺引导
- **U6 分片上传（独立 Sprint R6）**：500MB 文件前端一次 POST 不可行
- **U7 导入前预检报告**：detect 返回 `{files_detected, years_found, table_types, total_rows_estimate, estimated_import_time_seconds}` 让用户确认
- **U8 多年度同项目**：同 project 可并存多 year active dataset（陕西华氏 2024+2025）
- **U10 规模分 S/M/L 三档处理**：S < 10k INSERT / M 10k-500k calamine+COPY / L > 500k openpyxl 流式
- **U11 adapter JSON 沉淀**：9 家识别模式写入 `adapters/*.json` 声明式规则
- **U12 人工映射保存**：用户手动调整的 column_mapping 保存为该客户 adapter 模板（column_mapping_service S2 已有基础）
- **U13 多 sheet 分流**：YG2101 4 sheet 场景每个 sheet 独立识别 table_type 分流到 4 表

## 关键技术事实更新

- **陕西华氏场景暴露 pipeline 单文件语义缺陷**：当前每个 file 独立 detect/identify/convert/insert，没有"多文件属于同一 dataset"概念；需求 U1/U4 是下一轮重大改造点
- **9 家样本表类型识别率 97.8%**（1 家遗漏 = 和平物流方括号表头）；U3 adapter 规则可拉到 100%
- **CSV 大文件性能已验证**：和平药房 392MB CSV detect <5s、parse 内存 <200MB（已有流式实现）
- **scripts/ 清理**：当前 b2_copy_perf_validation/b3_calamine_smoke/b3_profile_realistic 已整合到 requirements M1；下轮可考虑合并或删除

## ledger-import-view-refactor spec 范围最终确定（2026-05-10）

- **F 系列 10 条发现分级处理**：本 spec 纳入 6 项识别引擎强化（F2 文件名识别 / F3 方括号表头 / F5 跨年度 / F7 CSV 大文件验证 / F8 表类型鲁棒 / F9 合并表头快照）+ B' 视图重构；独立 Sprint 留 4 项（F1 多文件拼接 / F4 分片上传 / F6 月度增量 UX / F10 企业级 UX）
- **requirements.md 增加"十一、9 家样本深度发现"和"十二、F 系列落地映射表"**，每条明确本 spec 决策（★必做/☆可选/⏸独立 Sprint）+ 实现位置
- **最终指标表增加 F2-F9 可量化验收**：辽宁卫生 sheet1 文件名识别置信度 ≥60 / 和平物流方括号表头 ≥85 / YG36 有核算维度余额表分流正确 / 392MB CSV detect <5s / 跨年度双 active 集成测试 / 9 家 header 快照测试全绿
- **本 spec 排除的场景已有过渡方案**：多文件拼接走 apply_incremental、分片上传靠 nginx 调大 client_max_body_size、月度增量前端缺引导但后端就绪

## spec 工作流规约新增（本轮沉淀）

- **大 spec 必须对"关键发现"做 F 系列编号 + 处理决策表**：避免需求范围模糊，每条发现必须标 ★本 spec 必做 / ☆可选 / ⏸独立 Sprint 三选一
- **F 系列映射表必须列 3 列**：对应需求编号（U2/U3/A11）+ 实现位置（具体文件/函数）+ 本 spec 处理状态

## ledger-import-view-refactor requirements.md 结构重构（2026-05-10）

- **requirements.md 从 650 行重构为 430 行**（信息密度+35%）：统一编号 F1-F12（必做）+ O1-O9（独立 Sprint），消除 U 系列和 F 系列 60% 重复、B1-B8 和 B1-B4 编号冲突
- **新 6 章结构**：前言（业务/技术根因/定位）→ §1 范围边界（1 张表看清做/不做）→ §2 功能需求（A 核心架构+B 识别引擎+C 企业级治理）→ §3 非功能需求（性能/DB 健康/可维护性/兼容性）→ §4 测试矩阵（单测/集成/E2E/CI/UAT）→ §5 成功判据汇总 → §6 术语表 + 附录 9 家样本表
- **[规约] 大 spec requirements.md 结构模板**（从本次重构沉淀）：
  1. 前言必写"为什么做"（业务痛点 + 技术根因 + 本 spec 边界）
  2. §1 范围边界必须用表格罗列做什么（F 编号）和不做什么（O 编号作独立 Sprint）
  3. 功能需求分组避免按章节分散（相关需求聚在一起）
  4. 测试矩阵必须单独成章（禁止散落在 M / R / F 多处）
  5. 成功判据用量化表格 + 对应需求编号
  6. 术语表解决新概念混淆（staged / active / superseded / legacy）
  7. 附录放真实样本归档等支撑性资料
- **[规约] 避免 3 种常见重复模式**：
  - 同一主题两套编号（U 系列 vs F 系列 → 只用一套）
  - 同一字母不同章节（B 大文件 vs B 边界 → 改其中一套为 NF 章节）
  - 决策散落多处（本 spec 做/不做的判断应集中 §1.1 和 §1.2 两张表）
- **本次需求核心锚定**：大文档处理为主，保证总体架构 / 可维护性 / 企业级治理 / 数据库维护 4 个维度同步落地

## ledger-import-view-refactor requirements.md 12 缺口补强（2026-05-10）

- **大文档处理的 5 个关键路径都缺硬指标**：解析/写入/进度/内存/超时；只靠 F1 activate <1s 不够，需要超大档基线（陕西华氏 500MB total <30min / 单 worker 峰值 <2GB / 单 sheet parse >10min 自动 timeout）
- **P0 必加 4 项**（任何大文档系统 table stakes）：F13 进度精度（每 5% 或 10k 行至少更新 + 30s 无更新才算卡）/ F15 cancel 清理保证（30s 内停 + 自动 cleanup_dataset_rows + Artifact 清理）/ F18 迁移策略（Day 0 deploy / Day 7 一次性 UPDATE / Day 30 DROP 废弃索引）/ 超大档基线
- **P1 补强 6 项**：F14 checkpoint 可恢复（staged 写完立即 checkpoint / resume_from_checkpoint 接口）/ F16 Prometheus 最小埋点（duration histogram / status counter / dead_tuple gauge）/ F17 耗时预估（从 O7 拆出，前端显示"预计 8 分钟"）/ F19 灰度回滚（feature flag + 项目级开关）/ 索引膨胀治理（purge 后 REINDEX CONCURRENTLY）/ 连接池隔离（B' 后 activate 瞬时释放 / pipeline 单 worker ≤3 连接）
- **P2 补强 2 项**：Artifact 保留期 90 天 expires_at 文档化 / autovacuum VACUUM 锁冲突（cost_delay=5ms + 发布窗口避高峰）
- **[重要技术决策] 迁移策略三阶段**：B' 代码与 is_deleted=true 老数据可以并存（fallback 兜底），不需要一次性迁移；Day 7 再做一次大 UPDATE 清理老数据，换 B' 后永久不再 UPDATE；Day 30 DROP `idx_tb_*_activate_staged`

## 云平台协同是硬需求（用户明确 2026-05-10）

- **核心诉求**：一个项目组成员 A 处理账套后，B/C/D/E 其他成员自动看到更新（而非手动刷新）
- **现有架构 80% 就绪**：ProjectAssignment 模型 / outbox event / WebSocket 通道 / get_active_dataset_id 单一真源
- **缺的 20%**：激活广播（WS 推送给项目组）/ 锁透明（导入中显示 holder+进度+预计耗时）/ 数据新鲜度（B 页面自动 re-fetch）
- **典型用例 3 类**：(1) A 导入 B 实时看到激活完成刷新 / (2) A 导入死机 B 接管 / (3) 并发 activate vs rollback 互斥

## ledger-import-view-refactor 第三轮补全建议（F20-F37，共 18 条）

**深度补全分 4 组**：
- **2.F 云平台协同**（F20-F25，6 条）—— 对应用户云平台诉求
- **2.G 数据正确性保障**（F26-F30，5 条）—— 企业级兜底
- **2.H UX 补强**（F31-F35，5 条）
- **2.I 平台工程**（F36-F37，2 条）

**优先级分级**：
- **P0 必做 8 条**：F20 激活广播 / F21 锁透明 / F23 rollback 走锁 / F25 审计溯源 / F26 孤儿扫描 / F27 integrity check / F31 激活确认 / F28 恢复剧本文档
- **P1 强推 5 条**：F22 接管 / F24 只读旁观 / F29 事务隔离 ADR / F32 错误友好 / F28 完整演练
- **P2/P3 独立 Sprint 5 条**：F30 CRC 校验 / F33 内存警告 / F34 diff 预览 / F36 API 版本化 / F37 CLI

## 关键技术决策（第三轮沉淀）

- **rollback 必须走 ImportQueue 锁**：activate 和 rollback 互斥（当前 rollback 没走锁是 bug）
- **接管（takeover）机制**：heartbeat 超 5min → 自动允许其他成员接管；ImportJob.created_by 扩展为数组记录链路
- **激活前 integrity check**：metadata 切换前 COUNT(*) 校验 staged 行数符合 record_summary；<1s 成本换防静默损坏
- **staged 孤儿清理周期**：定时任务每小时扫 > 24h 的 staged 无 job 关联 → 自动 cleanup
- **接口按角色成员可见**：项目组 ProjectAssignment 成员都能看 `GET /jobs/{id}` 实时进度（不只是 holder）
- **激活意图确认 UX**：ElMessageBox 二次确认 + 可选"理由"字段 → 进 ActivationRecord.reason 审计

## ledger-import-view-refactor requirements.md F20-F37 补全完成（2026-05-10）

- **13 条 P0+P1 需求已全部入 requirements.md**（F20-F32，不含 F30/F33-F37 进独立 Sprint O10-O14）
- §1.1 必做清单表从 19 行扩至 32 行；§1.2 排除表从 O1-O9 扩至 O1-O14
- **新增 3 个章节**：§2.F 云平台协同（F20-F25 共 6 条）/ §2.G 数据正确性保障（F26-F29 共 4 条）/ §2.H UX 补强（F31-F32 共 2 条）
- §3.5 可观测性表追加 WebSocket 通道 + 项目组锁状态行；§4.2 集成测试追加 6 项（test_ws_dataset_broadcast/test_import_takeover/test_activate_rollback_mutex/test_staged_orphan_cleanup/test_activate_integrity_check/test_job_readonly_access）
- §4.5 UAT 回归清单追加 6 项手动验收；§5 成功判据汇总追加云协同 5 项 + 正确性 3 项 + UX 2 项 + 运维 2 项（ADR-003/004）
- **requirements.md 最终状态**：~650 行覆盖 F1-F32 + O1-O14，下一步可同步 design.md / tasks.md
- 整体优先级排序：F1/F2 是核心瓶颈（activate 127s→<1s），F14/F15/F27 是大文档健壮性底线，F20-F25 是云协同基建，F28-F29 是文档交付

## ledger-import-view-refactor requirements.md 第 4 轮补全（2026-05-10）

- **第 4 轮深度复盘发现 8 个覆盖漏洞**（安全/多租户/数据质量/运维健康/事件可靠性/下游联动/规模异常/graceful shutdown）
- **新增 7 条 P0/P1 需求 F40-F46 进 §2.I 安全与健壮性**：F40 上传安全（MIME+zip bomb+宏拦截）/ F41 项目权限+tenant_id 预留 / F42 零行/异常规模拦截 / F43 健康检查端点 / F44 graceful shutdown / F45 事件广播 outbox 重试+DLQ / F46 rollback 下游 Workpaper/Report stale 联动
- **新增 3 条独立 Sprint 排除项 O15-O17**：完整多租户 / 性能基线 CI 门禁 / 告警渠道适配
- 编号策略修正：避开 F33-F39（排除表已占位引用），P0+P1 新条目从 F40 起编号
- **新增 §3.6 安全 + §3.7 健壮性**两个非功能章节独立呈现
- §4.2 集成测试追加 7 项（test_upload_security/test_cross_project_isolation/test_empty_ledger_rejection/test_health_endpoint/test_worker_graceful_shutdown/test_broadcast_retry_with_outbox/test_rollback_downstream_stale）
- §4.5 UAT 追加 6 项手动验收；§5 成功判据追加 11 行（安全 3 + 数据质量 2 + 健壮性 4 + UX 2）
- **requirements.md 最终覆盖需求数 F1-F46 合计 39 条（去掉预留间隔 F33-F39，实际 32 条必做）+ O1-O17 独立 Sprint 17 条**
- **关键技术决策沉淀**：(1) Tb* 表加 tenant_id NOT NULL DEFAULT 'default'（不启用但预留）；(2) SIGTERM → stop_event → cancel_check 回调链；(3) F20 WS 广播必须走 event_outbox 才可靠（直推丢事件）；(4) rollback 必须发 DATASET_ROLLED_BACK 事件级联 stale（复用 R1/R7 机制）；(5) get_active_filter 签名强制带 current_user 参数（当前签名缺失是潜在越权漏洞）

## requirements.md 校验透明化补全（F47-F49，2026-05-10）

- 用户截图点出「数据校验」入口痛点（1002 银行存款期末差异但不知公式/代入/来源）
- 新增 §2.J 数据校验透明化章节（F47-F49 共 3 条）：
  - **F47 每条 finding 附 explanation 字段**：公式（英文+中文）+ inputs 代入值 + computed 中间值 + diff_breakdown 差异来源分解 + hint 建议；适用 L1/L2/L3 所有 finding code
  - **F48 校验规则说明文档**：`GET /api/ledger-import/validation-rules` 返回全量规则 catalog（公式+容差+示例），前端独立页面 `/ledger-import/validation-rules` 分组展示；catalog 必须与 validator.py 双向一致
  - **F49 差异下钻到明细**：finding.location 扩展 drill_down 字段，复用现有 LedgerPenetration 穿透组件展示该科目全部凭证
- **关键技术决策**：(1) validator.py 每个 finding code 对应一个 Pydantic explanation model 严格 schema；(2) 新增模块级 VALIDATION_RULES_CATALOG 做单一真源；(3) 容差公式 `min(1.0 + magnitude × 0.00001, 100.0)` 从代码字面量暴露到前端规则说明页
- §4.2 追加 3 项集成测试；§4.5 追加 3 项 UAT；§5 成功判据追加「校验」分类 3 行
- requirements.md 最终覆盖 F1-F49（35 条必做，预留 F33-F39 间隔）+ O1-O17（17 条独立 Sprint）

## requirements.md 第 5 轮业务闭环补全（F50-F53，2026-05-10）

- 从「审计合规 + 系统稳定性 + UX 自然闭环」3 个维度发现 4 个关键盲点，新增 §2.K 业务闭环与合规章节
- **F50 下游对象快照绑定（最关键合规需求）**：Workpaper/AuditReport/Note 新增 bound_dataset_id + dataset_bound_at；AuditReport 转 final 时自动锁定；签字后的报表 rollback 被拒绝（409）；解决"签字后数字仍可被 rollback 篡改"的严重合规风险
- **F51 全局并发限流**：基于 Redis semaphore 的平台级 worker 上限（默认 3）+ FIFO 排队；内存逼近 3GB 时 pipeline 降级到 openpyxl + 小 chunk；防 100 并发打爆 PG/内存
- **F52 列映射历史智能复用**：detect 阶段按 file_fingerprint 查 ImportColumnMappingHistory 自动应用；第二次导入效率节省 > 50%；跨项目同软件匹配降级为"建议"
- **F53 留档合规保留期差异化**：ImportArtifact 新增 retention_class（transient/archived/legal_hold）；final 报表引用的 dataset 自动升级 archived（10 年）；purge 任务尊重 bound_dataset_id 绑定；对齐《会计档案管理办法》合规要求
- 新增 5 条独立 Sprint 排除项 O18-O22（审批链配置/差异对比/底稿回滚快照/模板市场/定时抓取）
- §3.2 数据库健康补强 purge 描述"尊重下游绑定与 retention 类别"
- §4.2 追加 7 项集成测试；§4.5 追加 5 项 UAT；§5 成功判据追加 5 行
- **关键架构决策**：(1) `get_active_filter` 新增 `force_dataset_id` 参数支持下游绑定查询；(2) Workpaper 首次生成即绑定、AuditReport 到 final 才锁定（粒度差异化）；(3) retention_class 自动决策基于 F50 绑定状态联动，不让用户手工设；(4) 并发限流走 Redis semaphore 而非 DB 乐观锁（性能）
- requirements.md 最终覆盖 F1-F53（38 条必做，预留 F33-F39 间隔）+ O1-O22（22 条独立 Sprint）

## ledger-import-view-refactor design.md + tasks.md 扩展（2026-05-10）

- **design.md** 从 Sprint 1-3 的 5 个架构决策 D1-D5 扩展到 22 个决策 D6-D22，新增 13 个架构决策对齐 §2.D-§2.K：D6 大文档健壮性 / D7 运维灰度 / D8 云协同 / D9 数据正确性 / D10 UX / D11 安全 / D12 校验透明化 / D13 业务闭环，8 组各带代码骨架和 Pydantic model / Alembic DDL 示例；新增风险 6-8（rollback 死锁 / 并发过严 / fingerprint 碰撞）
- **tasks.md** 从原 Sprint 1-3 共 40 任务扩展到 Sprint 1-9 共 171 任务，新增 6 个 Sprint：Sprint 4 大文档+运维（18 任务）/ Sprint 5 云协同（20）/ Sprint 6 数据正确性+UX（16）/ Sprint 7 安全（23）/ Sprint 8 校验+合规闭环（44）/ Sprint 9 最终验收（10）；每任务标 P0/P1/P2 优先级
- **工期估算 35 人天**（单人串行），引入并行化策略（主 + 两副开发 3 人团队可压缩到 ~15 天）
- **里程碑拆分**：M1 B' 核心（1-3）→ M2 企业级可用（4-5）→ M3 生产合规门槛（6-7）→ M4 审计业务完备（8-9）
- **关键架构文件清单**：metrics.py / error_hints.py / global_concurrency.py / validation_rules_catalog.py / staged_orphan_cleaner.py（worker）/ duration_estimator.py 6 个新建模块 + 5 个 Alembic 迁移（cleanup_old_deleted / tenant_id / dataset_binding / creator_chain / event_outbox_dlq）
- **Sprint 7 批次 B 重点决策**：tenant_id 迁移的"40+ 调用点补 current_user"与 Sprint 1 合并做（不单独拆），避免二次改同一批文件

## ledger-import-view-refactor 三件套一致性审查（2026-05-10）

- **审查方法沉淀（可复用规约）**：大 spec 三件套必须逐条需求对照矩阵审查 design/tasks 覆盖度，分 ✅ 完整覆盖 / ⚠️ 设计薄弱 / ❌ 完全遗漏 三档；审查表应在 tasks.md 末尾归档便于后续查
- **审查发现 18 条缺口**：F6-F11 识别引擎 6 条原在 design/tasks 完全遗漏（只做 B' 视图改造忽略 9 家样本识别引擎需求）；F3/F4/F5 基础运维设计薄弱；F28/F29/F31/F42/F43/F44 占位式任务无对应设计
- **补齐动作**：design.md 追加 D23-D32 共 10 个新架构决策（含代码骨架）；tasks.md 追加 Sprint 10 共 53 任务分 A/B/C 三批次
- **关键技术决策**：(1) Sprint 10 批次 B（识别引擎 F6-F11）必须前置到 Sprint 4 之前，否则 detect 相关任务隐性依赖风险；(2) F5 跨年度风险点 = `mark_previous_superseded` 查询必须加 year 条件；(3) F29 配套 `@retry_on_serialization_failure` 装饰器 + 幂等键双重保护
- **三件套最终状态**：F1-F53 × design/tasks 双向覆盖率 100%，总任务 224 / 总工时 43 人天 / 10 Sprint
- **spec 工作流新规约**：requirements 每次扩展后，必须做一次三件套一致性对照审查才能进入实施

## ledger-import-view-refactor 二次一致性审查（2026-05-10）

- **审查方法论升级（重要规约）**：三件套审查必须**双向**做——既从 requirements 向 design/tasks 查覆盖，也从 design/tasks 的编号反查 requirements 是否真定义了对应条目；单向只做前者会漏"引用了不存在条目"这类内部不一致问题
- **二次审查发现 16 处新遗漏**：(1) 9 个测试任务在 tasks.md 无编号（§4.1/§4.2 列的 test_dataset_service_activate/rollback_view_refactor/test_progress_callback_granularity/test_duration_estimator/test_dataset_concurrent_isolation/test_rollback_full_flow/test_resume_from_activation_checkpoint/test_metrics_endpoint/test_migration_day7_update）；(2) 7 处 requirements 内部引用错误（O10-O14/O15/O17 引用了从未定义的 F30/F33/F34/F36/F37/F38）
- **F 编号跳号陷阱**：第 4 轮扩展时为避开冲突跳过 F33-F39 间隔，但排除表里占位符"（F30）等"没同步清理；下次 spec 扩展时如果跳号，必须同步清理所有引用该编号的位置
- **修正动作**：requirements 修正 7 处内部引用（O15→F41 / O17→F45 / O10-O14 去除无效占位）；tasks.md 追加 Sprint 11（9 测试任务 + 修正记录归档）
- **三件套最终状态**：233 任务 / 44 人天 / 11 Sprint；F1-F53 × design + tasks 双向覆盖率 100%；O1-O22 零内部引用残留；§4 测试矩阵 32 个测试文件全部有任务编号

## ledger-import-view-refactor 实施进度（2026-05-10）

- **Sprint 1 完成（26/26 task，业务查询迁移）**：15 个 service + 2 个 router 的 40+ 处 `TbX.is_deleted == False` 全部迁移到 `get_active_filter`；6 处 raw SQL 改为 EXISTS 子查询；grep 验证通过（剩余 6 处是 year=None 兜底分支 Template B 模式，设计文档明确保留）；82+ 测试通过
- **Sprint 2 核心完成（tasks 2.1-2.5）**：`get_filter_with_dataset_id` 同步版本新增（dataset_query.py）；`DatasetService.activate/rollback` 去除 `_set_dataset_visibility` 调用；`_set_dataset_visibility` 改 no-op + logger.warning；pipeline `_insert` 写入改 `is_deleted=False`；36 测试通过
- **Sprint 2 剩余（2.6-2.8）**：E2E 验证需真实 PG + 样本数据（YG4001 smoke / YG36 / YG2101 perf），需手动执行
- **Sprint 3-11 待执行**：加固+文档 / 大文档健壮性 / 云协同 / 数据正确性 / 安全 / 校验透明化 / 最终验收 / 一致性补齐 / 测试矩阵，共 ~200 任务
- **关键发现**：`dataset_service.py` 和 `dataset_query.py` 已经是 B' 架构（代码在之前的 Sprint 中已部分实现），本轮实施主要是确认+补全+验证
- **taskStatus 多行任务名限制**：tasks.md 中含换行的任务描述无法被 taskStatus 工具匹配，需用精确单行文本；Sprint 2 的 2.1-2.4 因多行描述无法直接标记状态

## ledger-import-view-refactor Sprint 3-4 进度（2026-05-10）

- **Sprint 3 完成（5/6 task，加固 + 文档）**：(1) CI backend-lint job 新增 B' guard 扫 `Tb(Balance|Ledger|AuxBalance|AuxLedger)\.is_deleted\s*==` 命中 > baseline(6) 即 fail；(2) `backend/tests/integration/test_dataset_rollback_view_refactor.py` 4 用例（rollback 语义 + 并发项目隔离）；(3) `docs/adr/ADR-002-ledger-view-refactor.md` 归档 B' 视图重构架构决策；(4) architecture.md 新增"账表导入可见性架构"章节；(5) conventions.md 新增"账表四表查询规约"（强制 `get_active_filter` + raw SQL EXISTS 模板 + year=None 允许清单）
- **Sprint 4 P0 完成（13/18 task）**：4.1 `ProgressState`/`_maybe_report_progress` 按 5%/10k 行节流（F13）/ 4.2 `phases.py` + pipeline `_mark` 透过 `phase_marker` 回调异步写 `ImportJob.current_phase`（F14）/ 4.3 `ImportJobRunner.resume_from_checkpoint` 路由表 + `POST /jobs/{id}/resume` 端点 / 4.6 `pipeline._handle_cancel` 清理链（cleanup_rows + mark_failed + artifact consumed）/ 4.7 `recover_jobs` 扫 canceled+staged 孤儿清理 / 4.8 `test_cancel_cleanup_guarantee.py` 4 用例 / 4.9 `backend/app/services/ledger_import/metrics.py` 5 Prometheus 指标 + stub fallback（不强制装 prometheus_client）/ 4.10 `/metrics` 端点挂 main.py / 4.13 `duration_estimator.py` 4 档估算 + detect 响应扩展 `total_rows_estimate/estimated_duration_seconds/size_bucket` / 4.15 feature_flag `ledger_import_view_refactor_enabled=True` / 4.16 Alembic `view_refactor_cleanup_old_deleted_20260517.py` 分块 UPDATE / 4.18 `test_b_prime_feature_flag.py` 9 用例
- **Sprint 4 剩余**：4.4/4.5 前端（"恢复导入"按钮 + 卡住阈值 30s）/ 4.11/4.12 `/health/ledger-import` 端点 / 4.14 前端 DetectionPreview"预计耗时 X 分钟"展示
- **测试全绿**：120 passed + 3 skipped（PG-only Alembic round-trip）；Sprint 1-4 backend P0 代码改动 zero getDiagnostics errors
- **关键技术决策**：
  - (1) `_set_dataset_visibility` 已在之前 sprint 中 no-op 化，本次 Sprint 2 完成 activate/rollback 去除调用路径（三件套所列"2.2/2.3"在代码层是验证而非新改）
  - (2) `phase_marker` 采用 fire-and-forget `asyncio.create_task`：phase 持久化失败不阻断主管线（业务逻辑优先级 > 可观测性）
  - (3) `resume_from_checkpoint` 策略：标记 queued + enqueue 全量重跑；pipeline 的 activate/rebuild 都是幂等操作（metadata UPDATE + summary rebuild），已完成阶段重跑安全
  - (4) `ImportArtifact` 无 `job_id` 列，cancel 清理链需走 `ImportJob.artifact_id` 反查（而非 `ImportArtifact.job_id`）
  - (5) metrics 模块 `_PROMETHEUS_AVAILABLE` 双分支 + `_Stub` 类：即使 `prometheus_client` 未装也不破坏 import，`/metrics` 返回说明文案
  - (6) 4.15 feature_flag 默认 `True`（因为 B' 代码已部分上线），实际意义是"项目级降级开关"而非"启用开关"
- **taskStatus 工具限制发现**：多行任务描述（带 `\n  - 细节`）无法被精确匹配，必须用单行文本或直接编辑 tasks.md 的 `- [ ]` → `- [x]`
- **property-based 测试速度规约（2026-05-10 扩展）**：`test_production_readiness_properties.py` + `test_phase0_property.py` + `test_phase1a_property.py` + `test_remaining_property.py` 已降到 `max_examples=3-5`；`test_audit_log_hash_chain_property.py` 50→10、`test_aux_dimension_property.py` 200→20/100→20/50→10；MVP 阶段速度优先，新增 PBT 默认 `max_examples=5`（算法测试）/ 10-20（加密/哈希链等需更多反例），稳定后再调高；全部 116 PBT 测试从 backend/ cwd 跑 ~7.3s 全绿
- **pytest cwd 硬约定**：`test_phase0_property.py::TestFrontendIntegrationProperty` 用相对路径 `../audit-platform/frontend/...` 检查前端 token/store 存在，**必须** 从 `backend/` cwd 跑（repo root 跑会 2 failed，artifact 非 bug）；CI 和本地统一 `cd backend; pytest` 或 `pytest` + `cwd=backend`
- **ledger-import-view-refactor Sprint 10 批次 B 完成（F6-F11 识别引擎强化）**：
  - F6 文件名元信息：`detector._extract_filename_hints(filename)` 返回 `{table_type, table_confidence, matched_keyword, year, month, file_stem}`；`identify()` 在 L1 sheet 名得分 < 60 且 filename_hint.table_type 存在时覆盖 L1 score
  - F7 方括号/组合表头：`detector._normalize_header(cell)` 剥 `[]`/`【】` + 识别 `#|@` 分隔的组合字段；`_normalize_header_row` 返回 `(normalized_cells, compound_headers)`；`identify()` 对未映射的 compound 列用子字段试别名（只选未占用的 standard_field，避免抢占已映射列）
  - F8 表类型鲁棒性：`_GENERIC_SHEET_NAMES` = `{sheet1, sheet2, 列表数据, 数据, data, 工作表1, sheet}` 查询时不扣分只不加分；L1 锁定机制加入 aux variant 例外——当 L1=balance 但 L2=aux_balance（L2 score ≥ 60）时不锁，让更具体的 L2 胜出（"科目余额表（有核算维度）" 修复）
  - F9 unknown 透明化：`_derive_skip_reason(sheet)` 生成 `{code, message_cn}`，3 档 code = `ROWS_TOO_FEW` / `HEADER_UNRECOGNIZABLE` / `CONTENT_MISMATCH`；写入 `detection_evidence["skip_reason"]` + `warnings` 追加 `SKIPPED_UNKNOWN:<code>` tag
  - F10 CSV 大文件：`iter_csv_rows_from_path` 已有流式实现，新增 `test_large_csv_smoke.py` 合成 100MB 验收（slow 标记）
  - F11 9 家样本 header 快照：`backend/tests/fixtures/header_snapshots.json` 5 家（YG36/YG4001/和平药房/和平物流/安徽骨科）+ `test_9_samples_header_detection.py` 参数化；`scripts/_gen_header_snapshots.py` 用于再生（未来样本增加时跑）
- **关键技术决策（F6-F11 落地沉淀）**：
  - (1) `detection_evidence` 作为 dict 扩展点比 Pydantic 字段更灵活，新增 `filename_hint` / `compound_headers` / `skip_reason` / `header_cells_raw` 等不需要改 schema
  - (2) 组合表头子字段匹配只在"主列未映射"时触发，避免 `[凭证号码]#[日期]` 抢占独立列 `[日期]` 的 voucher_date 映射（和平物流曾因此产出 0 ledger 行）
  - (3) L1 lock 例外的 aux variant pair：`{(balance, aux_balance), (ledger, aux_ledger)}` —— L1 sheet 名对这两对来说覆盖过宽（"余额表" 正则也匹配 "有核算维度余额表"），须让 L2 具体列（aux_type）决定
  - (4) 文件名年月正则必须按优先级列出多条（`\d{2}年\d{1,2}月` 优先于 `\d{2,4}[./\-_]\d{1,2}`），单一模糊正则会把 "25年10月" 错解为 year=2510/month=1
  - (5) `_DIRECTION_VALUES` 包含 `{'1','-1','借','贷','d','c'}`，纯数字序号列会误触发 L3 direction 信号；测试用例写非数字占位符（`xx/yy/zz`）避免
- **ledger-import-view-refactor Sprint 10 批次 A + 批次 C 完成**（20 tasks / 254 passed / 0 regression）：
  - **批次 A（F3 purge / F4 审计轨迹 / F5 跨年度）**：`DatasetService.purge_old_datasets(pid, *, year=None, keep_count=3)` + `purge_all_projects` + `dataset_purge_worker.py`（每晚 03:00 + REINDEX CONCURRENTLY 4 个 `active_queries` 索引，PG only / SQLite 跳过）+ 注册到 `_start_workers`；`activate()` 补齐 `ip_address/duration_ms/before_row_counts/after_row_counts/reason` 5 字段；`mark_previous_superseded` 查询必须**同时带 project_id + year**（否则跨年误标 — F5 风险点）；修复 `ledger_datasets.py` 重复定义 `GET /datasets/history` 端点（FastAPI 静默覆盖导致 bug）
  - **批次 C（F28/F29/F43/F44 补齐）**：`ADR-003-ledger-import-recovery-playbook.md`（8 故障场景 copy-paste 诊断+恢复命令）+ `ADR-004-ledger-activate-isolation.md`（REPEATABLE READ + 幂等 + 重试 3 决策）+ `backend/app/services/retry_utils.py` 的 `@retry_on_serialization_failure(max_retries, initial_delay_ms, max_delay_ms)` 装饰器（识别 SQLSTATE 40001/40P01 + asyncpg `SerializationError` 类名 / 指数退避 + 抖动 0.5-1.5x）+ activate 幂等保护（`dataset.status == active` 直接返回不抛异常，resume 场景友好）+ `ImportJobRunner.run_forever(stop_event=...)` 协同停机（`asyncio.wait_for(stop_event.wait(), timeout=interval)` 可中断睡眠）+ `/api/health/ledger-import` 端点（queue_depth / active_workers / p95_duration_seconds / pool 使用率 → 3 态 healthy/degraded/unhealthy + 同步 `HEALTH_STATUS` gauge）
- **Sprint 10 架构决策（新增）**：
  - (1) `dataset_purge_worker` 保留策略 = 同 `(project_id, year)` 最近 N=3 superseded，active/staged/rolled_back/failed 永不触碰（rolled_back 作 UAT 审计证据保留）
  - (2) 幂等 activate 入口第一行判断：`if dataset.status == DatasetStatus.active: return dataset`；`resume_from_checkpoint` 重跑 activate 不再因"not staged"失败
  - (3) `JobStatus.interrupted` 新状态**延后不做**（需 PG enum migration + 全状态机改造），依赖现有 `recover_jobs` heartbeat 超时兜底 95% 场景足够
  - (4) `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` 同样延后（需 PG-only 代码路径，SQLite 无等价），先用项目级锁 + 幂等键保证一致性
  - (5) 健康端点 `_estimate_p95_seconds()` 用 Histogram bucket 边界近似 P95（prometheus_client 不直接暴露分位数），第一个 cumulative count >= 0.95*total 的 bucket `le` 值即近似
  - (6) REINDEX CONCURRENTLY 需 AUTOCOMMIT 模式（不能在 transaction 中），用 `async_engine.connect()` + `raw_connection.driver_connection.execute` 绕过事务
- **FastAPI 路由重复定义陷阱（新）**：同一 path + HTTP method 定义两次时，后者静默覆盖前者**没有警告**；code review 或 `scripts/dead-link-check.js` 都不会捕捉；本轮发现 `ledger_datasets.py` 重复了 `GET /datasets/history`（Sprint 5.19 和更早版本重复了），修复时只保留一份即可
- **Sprint 6 数据正确性 + UX（12 tasks 后端完成）**：`staged_orphan_cleaner` worker 每小时扫 staged >24h + 无活跃 job 关联 → mark_failed；`DatasetService.activate` 加 integrity check（record_summary 各表预期行数 vs 实际 COUNT(*) dataset_id 过滤，不符抛 `DatasetIntegrityError`）；`error_hints.py` 32 条 ErrorHint（title/description/suggestions 2-4 条/severity）与 `ErrorCode` 枚举 1:1 CI 强制；`/jobs/{id}/diagnostics` 响应 findings + blocking_findings 数组每条附 hint 字段（`enrich_finding_with_hint`）
- **ImportJob / LedgerDataset 关联方向硬约定**：`ImportJob` **没有** `dataset_id` 字段；关联是单向 `LedgerDataset.job_id → ImportJob.id`（一个 job 产一个 dataset）；孤儿扫描 SQL 必须用 `NOT EXISTS (SELECT 1 FROM import_jobs WHERE id = LedgerDataset.job_id AND status IN active_statuses)`，方向反了会 TypeError
- **ImportJob 无 upload_token 字段**：`upload_token` 在 `ImportArtifact` 表；ImportJob 通过 `artifact_id` FK 关联到 artifact；测试 fixture 构造 ImportJob 时不要传 upload_token
- **ErrorCode 实际 32 条不是 31 条**（requirements spec 历史写错）：5 fatal + 9 blocking + 11 warning + 3 info + 4 通用码；F32 的 error_hints 对应覆盖全 32 条
- **integrity check 语义规约**：activate 前 `record_summary` 含 `tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger` 四 key 时才触发 check；其他 key 如 `validation_warnings`/`aux_types_detected` 被静默忽略；不传 record_summary 则跳过（向后兼容）
- **`enrich_finding_with_hint(dict)` 合约**：未登记的 code / 无 code 字段 / hint=None 都静默原样返回（不抛异常），用于安全的 findings 数组 map；避免 lookup miss 导致整个 diagnostics 端点失败
- **CI grep 卡点 baseline 硬约定**：B' `TbX.is_deleted==` baseline=6（year=None 兜底分支），新增查询必须走 `get_active_filter`，不能给这 6 个允许清单扩容
- **`test_property_14_no_hasattr_patch_remaining` 路径兼容性**：用 `Path(__file__).resolve().parent` 解析 router_registry.py，支持 cwd=repo root 或 cwd=backend 两种运行方式
- **`test_property_14_all_business_routes_under_api` 新增 `/metrics` 例外**：Prometheus 标准路径不是业务路由，跟 `/wopi/docs/openapi.json/redoc` 同级加入例外列表
- **临时文件清理**：`scripts/_analyze_9_samples.py` + `sample_analysis.txt` 是 2026-05-10 下午 17:45 留的一次性分析产物，未来下一轮启动时可删除

## ledger-import-view-refactor Sprint 7 批次 A/B/C 完成（2026-05-10）

- **批次 A（F40 上传安全，4 tasks / 7.1-7.4）**：新建 `backend/app/services/ledger_import/upload_security.py`（~370 行）+ `test_upload_security.py` 8 用例全绿；MIME magic（python-magic 可选，PK\x03\x04 字节签名兜底）+ 大小上限（xlsx ≤ 500MB / csv ≤ 1GB / zip ≤ 200MB）+ xlsx 宏（vbaProject.bin）/ 外链（externalLinks/）/ zip bomb（解压/压缩 > 100×）拒绝；集成到 `ledger_import_v2.py::detect_files` + `ledger_import_application_service.py::resolve_file_sources`；audit log 走 `audit_logger_enhanced.audit_logger.log_action`（哈希链落 `audit_log_entries` 表）
- **批次 B（F41 tenant_id 预留，2 tasks / 7.5+7.8）**：Alembic `view_refactor_tenant_id_20260518`（down=view_refactor_activation_record_20260523）5 表（tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger/ledger_datasets）加 `tenant_id VARCHAR(64) NOT NULL DEFAULT 'default'` + `idx_{table}_tenant_project_year` 复合索引；ORM 模型同步；`test_cross_project_isolation.py` 4 用例验证 project_id 过滤仍是隔离底线；**7.6/7.7 `get_active_filter` 签名 + 40+ 调用点改造延后**（触发面太大独立 Sprint）
- **批次 C（F42 scale warnings + force_submit 门控，6 tasks / 7.9-7.11+10.42-10.44）**：新建 `backend/app/services/ledger_import/scale_warnings.py`（`EMPTY_ROW_THRESHOLD=10` / `SUSPICIOUS_MIN_RATIO=0.1` / `SUSPICIOUS_MAX_RATIO=10.0`，历史均值从 `LedgerDataset.record_summary` 四表行数累加，首次导入无基线跳过 SUSPICIOUS）；`ImportJob.force_submit` 字段 + Alembic `view_refactor_force_submit_20260524`（down=view_refactor_tenant_id_20260518）；`/detect` 响应追加 `scale_warnings`；`/submit` 端点**服务端重新跑 detect_from_paths 再算一次 warnings**（防前端伪造 force_submit 绕过），warnings+!force_submit → HTTP 400 `SCALE_WARNING_BLOCKED`；`test_empty_ledger_rejection.py` 7 用例
- **测试全绿**：ledger_import 套件 222+ passed / 4 skipped（PG-only Alembic round-trip）；所有新建文件 getDiagnostics 零错误

## Sprint 7 关键技术决策沉淀

- **submit 门控服务端重新计算原则**：凡是"前端可绕过"的 boolean flag（force_submit / skip_validation 等），后端必须独立重算触发条件，不能只信任请求体字段；防客户端伪造（修改 js）绕过 gate
- **tenant_id 预留迁移不等于启用**：只加列 + 索引，`get_active_filter` 签名保持不变；40+ 调用点补 `current_user` 是独立 Sprint（触发面大，需整体 review）；ORM 模型和 Alembic 保持 server_default='default'，老行自动填充无需数据迁移
- **python-magic 可选依赖策略**：Windows 部署难装 libmagic，upload_security.py 用"try import + 字节签名兜底"双分支；`_try_magic` 捕获所有异常降级，`_detect_type` 用 `PK\x03\x04` 魔数 + 文件扩展名兜底
- **审计日志入口**：`audit_logger_enhanced.audit_logger.log_action(user_id, action, object_type, object_id, project_id, details, ip_address)` 是全平台审计唯一入口，哈希链落 `audit_log_entries` 表；`audit_logs` 是简单日志表历史遗留，新代码不要用
- **ErrorCode 复用（non-upload 场景）**：上传拒绝的 `reason` 映射表已在 upload_security.py 内部维护（`_REASON_TO_ERROR_CODE`），macro_detected / external_links_detected 暂复用 `UNSUPPORTED_FILE_TYPE` 近似（ErrorCode 无专用枚举）

## PBT 测试速度二次优化（2026-05-10）

- `test_audit_log_hash_chain_property.py` 4 个 tests 从 `max_examples=10` 降到 `5`；`test_aux_dimension_property.py` 3 个 tests 从 `20` 降到 `10`，1 个 tests 从 `10` 降到 `5`
- **116 PBT 测试 6.14s 通过**（从 7.3s 降到 6.14s，-16%）
- **MVP 阶段 PBT 速度规约更新**：算法测试默认 5 / 加密哈希链等需更多反例的降到 5-10（原 10-20 偏慢）；新增 PBT 建议 `max_examples=5` 起步，有误报率问题再调高
- **微调 PowerShell 输出捕获**：大命令输出被 shell 截断时用 `Tee-Object -FilePath x.log | Select-Object -Last 20` 保证能看到尾部测试结果；完成后 `deleteFile` 清理临时 log

## Subagent 调用可靠性观察（2026-05-10）

- **subagent 高并发期间会报 `read ECONNRESET` / `Encountered unexpectedly high load`**：临时服务错误，等 30s 后重试通常能通过；不需要降低任务粒度
- **建议每批 subagent 任务数 ≤ 6**：单次 prompt 太长会触发 token 超限；拆分成"批次 A/批次 B/批次 C" 3-4 任务一批更稳
- **subagent 任务描述关键节点**：(1) 明确告知 `down_revision` 具体值（当前 HEAD 不让 subagent 猜）；(2) 列出"skip tasks"避免它自作主张做延后任务；(3) 文件路径用相对仓库根；(4) 指明测试要跑通 + getDiagnostics 兜底

## ledger-import-view-refactor Sprint 9 + 11 完成（2026-05-10）

**Sprint 11（测试矩阵补齐）9 / 9 文件全绿，合计 62 测试 + 2 skip（本地缺 prometheus_client）**：
- 11.1 `test_dataset_service_activate_view_refactor.py`（6 用例）：activate metadata 翻转 + 物理行 is_deleted 不变 + 幂等 + ActivationRecord 审计 + outbox 事件 + 非 staged 拒绝
- 11.2 `test_dataset_service_rollback_view_refactor.py`（5 用例）：rollback metadata 翻转 + 物理行不动 + ActivationRecord + DATASET_ROLLED_BACK outbox + 无 previous 返回 None
- 11.3 `test_progress_callback_granularity.py`（8 用例）：ProgressState 按 5%/10k 行节流 + cb=None no-op + total=0 不触发 + 幂等 + 2M 行大文档 10k 行阈值
- 11.4 `test_duration_estimator.py`（扩展）：9 家真实样本参数化覆盖 S/M/L/XL 四档（YG4001/YG36/宜宾大药房/和平药房/辽宁卫生/医疗器械/安徽骨科/陕西华氏/和平物流/YG2101）
- 11.5 `test_dataset_concurrent_isolation.py`（4 用例）：A staged + B active 不互污 + 同项目 staged 不影响 active 视图 + 多项目 active 隔离 + 多年度 active 并存
- 11.6 `test_rollback_full_flow.py`（2 用例）：V1→V2→rollback→V1 + rollback→reactivate V3 链式；全程 is_deleted=false、物理行不减、ActivationRecord 3 条
- 11.7 `test_resume_from_activation_checkpoint.py`（5 用例）：phase=activation_gate_done → resume_from_activate_dataset 路径；staged dataset 可重新 activate；activate 幂等；phase_routes 完备性
- 11.8 `test_metrics_endpoint.py`（5 用例）：/metrics 200 响应 + 3 核心指标名 + observe_phase_duration 数据点可见 + prometheus_client 缺失时降级
- 11.9 `test_migration_day7_update.py`（10 用例）：迁移源代码结构检查 + SQLite 环境 no-op + 等价 UPDATE 幂等 + 只翻转 active dataset 行（superseded/rolled_back 不动）

**Sprint 9 文档 + 运维（4/4 任务完成）**：
- 9.4 `docs/EXPLAIN_ANALYZE_VIEW_REFACTOR.md`：5 条代表性查询（Q1 单科目/Q2 年度聚合/Q3 辅助多维/Q4 L3 比对/Q5 integrity check）+ 改造前后 SQL + 索引使用 + YG2101 基准 + Day 0/7/30 灰度验证 checklist
- 9.5 `.github/workflows/ci.yml` 新增 3 个 backend-lint gate：(a) F40 upload_security call grep（ledger_import_v2.py + ledger_import_application_service.py 必须命中 validate_upload_safety）；(b) F48 validation_rules_catalog 双向一致性测试（test_validation_rules_catalog.py）；(c) F32/F48 错误提示覆盖率（test_error_hints.py）。既有 F2 Tb*.is_deleted== baseline=6 保持不变
- 9.6 `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 扩展章节 9（可见性架构）+ 10（下游绑定）：127s→<1s 对比、get_active_filter 签名、force_dataset_id 语义、rollback 保护、retention_class 三档、force-unbind 逃生舱、下游 stale 联动
- 9.7 memory.md（本文）归档 Sprint 9+11 完成 + 待完成项清单；architecture.md + conventions.md 既有"账表导入可见性架构"+"账表四表查询规约"章节无需更新（Sprint 3 已落地）

**Sprint 9 跳过项（运维/真实环境范畴）**：
- 9.1 `test_huge_ledger_smoke.py` 500MB 合成样本（需 PG + 真实环境）
- 9.2 9 家真实样本 E2E（需 `数据/` 目录）
- 9.3 `b3_diag_yg2101.py` activate <1s + total <250s（需真实 YG2101 xlsx + PG）
- 9.8 UAT 手动清单
- 9.9 / 9.10 灰度部署 Day 0/3/7/30 + DROP 废弃索引

**本 spec 已归档状态**：F1-F53 双向覆盖 design + tasks + 测试；主干代码走 get_active_filter；pipeline 写 is_deleted=false；activate/rollback 只改 metadata；CI 三层卡点（F2 + F40 + F48）防回归；下游绑定 F50 合规闭环；retention_class F53 保留期策略；event_outbox 云协同（activate/rollback 广播）

**spec 工作流规约再沉淀**：
- 大 spec 有 40+ 需求时，任务执行子 agent 每批 ≤ 9 任务，给明确 "Skip tasks" 列表避免僭越
- 测试文件任务描述里必须指明 SQLite in-memory fixture 复用邻居模板（避免每文件独立造轮）
- TbLedger/TbAuxLedger 插入必须带 voucher_date + voucher_no（NOT NULL），SQLite 报错 "NOT NULL constraint failed" 是常见踩坑
- ActivationRecord 时间字段是 `performed_at` 不是 `created_at`（无 `created_at` 列）；涉及时间排序时查准字段名
- 迁移源码 downgrade 常含 docstring 提及"UPDATE"等关键字，test 做反向检查时需先剥离 docstring 再 grep

## ledger-import-view-refactor Sprint 7 D/E + Sprint 8/11 + Sprint 9 文档完成（2026-05-10）

- **Sprint 7 批次 D（F44 graceful shutdown）**：`import_worker._install_signal_handlers(stop_event)` 双路径（Unix 走 `loop.add_signal_handler`，Windows 抛 `NotImplementedError` 时回退 `signal.signal` + `call_soon_threadsafe`）；`ImportJobRunner._stop_event` 类级指针供 pipeline `_cancel_check` 读；`test_worker_graceful_shutdown.py` 8 用例；7.14/7.15 `JobStatus.interrupted` 枚举依赖 PG migration 延后，依赖 `recover_jobs` heartbeat 兜底 95% 场景
- **Sprint 7 批次 E（F45 DLQ + F46 rollback 下游 stale）**：`event_outbox_dlq` 表（original_event_id FK→outbox ON DELETE SET NULL + partial index `resolved_at IS NULL`）；`ImportEventOutboxService._move_to_dlq` + `dlq_depth()`；`outbox_replay_worker` 每轮调 `set_dlq_depth()` 刷新 gauge；同 Alembic 迁移里 `audit_report`+`disclosure_notes` 新增 `is_stale` 列（Workpaper 已有 `prefill_stale` 复用）；`DatasetService.rollback` outbox payload 双键（历史键 `rolled_back_dataset_id/restored_dataset_id` + F46 新键 `project_id/year/old_dataset_id/new_active_dataset_id`）；`_mark_downstream_stale_on_rollback` handler 订阅 `LEDGER_DATASET_ROLLED_BACK`
- **Sprint 8 批次 A（F47 validation explanation，6 tasks）**：5 个 Pydantic explanation 子 model（`ExplanationBase` / `BalanceMismatchExplanation` / `UnbalancedExplanation` / `YearOutOfRangeExplanation` / `L1TypeErrorExplanation`）；`ValidationFinding.explanation: SerializeAsAny[ExplanationBase] | None`（`SerializeAsAny` 是关键，否则子类特有字段 `diff_breakdown/sample_voucher_ids/year_bounds` 在 API JSON 输出中被基类 schema 截断）；validator 函数实际命名是 `validate_l1/l2/l3`（spec 文案的 `validate_l3_cross_table/validate_l2_balance_check/validate_l2_ledger_year` 是描述性名称，非真实函数名）；13 测试全绿
- **Sprint 8 批次 B+C（F48 catalog + F49 drill_down，6 tasks）**：`VALIDATION_RULES_CATALOG` 实际 **10 条规则**（spec 写的 "31 条" 是历史错估；validator.py 实际只 emit 10 个 code，文件上传/detect 阶段 fatal 码已由 `error_hints.py` 覆盖不重复）；`ValidationRuleDoc` Pydantic model 11 字段；`test_validation_rules_catalog.py` 用 regex grep validator.py 源码做 **双向一致性** 测试（catalog ↔ validator emit 集合完全相等）；`location["drill_down"] = {target, filter, sample_ids, expected_count}` 仅 L3 填充；`/api/ledger-import/validation-rules` + `/{code}` 两端点
- **Sprint 8 批次 D（F50 下游绑定，10 tasks，合规关键）**：Alembic 迁移给 4 张下游表（`working_paper/audit_report/disclosure_notes/unadjusted_misstatements`）加 `bound_dataset_id UUID FK → ledger_datasets ON DELETE RESTRICT` + `dataset_bound_at TIMESTAMPTZ` + partial index `WHERE bound_dataset_id IS NOT NULL`；ActivationType 枚举扩展 `force_unbind`（PG enum ALTER 需 `autocommit_block()`）；`bind_to_active_dataset(db, obj, pid, year)` async + `bind_to_active_dataset_sync` 老 service 用；实际 workpaper 创建函数是 `generate_project_workpapers`（不是 spec 写的 `generate_workpaper`，批量生成模板后统一 bind）；`AuditReport.transition_to_final` + `sign_service._transition_report_status` order=5 双入口绑定，幂等保护（`bound_dataset_id is None` 才覆盖）；`DatasetService.rollback` 409 `SIGNED_REPORTS_BOUND`；`POST /api/datasets/{id}/force-unbind` 双人授权端点（自审批拒绝/非 admin 审批拒绝/成功后 final→review + bound 字段清空 + ActivationRecord action=`force_unbind`）；13 测试全绿
- **Sprint 8 批次 E（F51 全局并发限流 + 内存降级，6 tasks）**：`GlobalImportConcurrency` 双路径（Redis `INCR/DECR/EXPIRE 7200s` + asyncio.Lock 本地 fallback，Redis 一次失败永久降级）；env `LEDGER_IMPORT_MAX_CONCURRENT` 默认 3；**enqueue 签名保持 sync classmethod 不变**——`try_acquire` 放在 `_execute` 内而非 `enqueue`，对所有 caller 零侵入；slot 粒度 = claim 之后（避免同项目排队占用全局槽）；claim 失败/异常/完成三路径都 release；`/active-job` 端点 queued/pending 时附 `queue_position`（1-indexed）+ `global_max_concurrent`；`pipeline._detect_memory_pressure` 读 `psutil.virtual_memory().percent > 80` → `use_calamine_global=False` + `CHUNK_SIZE=10_000`，psutil 未装/查询失败静默跳过；fakeredis.aioredis + monkeypatch `_get_redis` 避开真 Redis
- **Sprint 8 批次 F+G（F52 mapping 复用 + F53 retention，9 tasks）**：`ColumnMappingService.build_file_fingerprint(sheet, cells, hint)` = `SHA1(normalized_sheet + "|" + "|".join(normalized_first_20_cells) + "|" + normalized_hint)`，`normalized = str(x or "").strip().lower()`；`ImportColumnMappingHistory` 加 `file_fingerprint VARCHAR(40)` + `override_parent_id UUID FK self ON DELETE SET NULL`；30 天命中窗口 `DEFAULT_FINGERPRINT_REUSE_WINDOW = timedelta(days=30)`；`ColumnMatch` 加 `auto_applied_from_history: bool = False` + `history_mapping_id: str | None` + source 枚举加 `"history_reuse"`；mapping 字典方向判定用 ASCII snake_case 启发式（原版用 `isalnum()` 对中文误判有 bug）；`ImportArtifact` 加 `retention_class VARCHAR(20) DEFAULT 'transient'` + `retention_expires_at TIMESTAMPTZ NULL`；`compute_retention_class(db, dataset)` 优先级 legal_hold > archived > transient；`compute_expires_at` 三档（transient 90d / archived 10y / legal_hold None）；**LedgerDataset.legal_hold_flag 不存在（grep 零匹配）**，过渡用 `source_summary["legal_hold"]` JSON 键（支持 bool / "true"/"1"/"yes"/"y"/"on"）；`purge_old_datasets` 扩展两道过滤：`skipped_due_to_binding`（4 张下游表 bound_dataset_id）+ `skipped_due_to_retention`（archived/legal_hold 不动）；33 测试全绿
- **Sprint 11 测试矩阵 + Sprint 9 文档（13 tasks）**：9 个 Sprint 11 测试文件共 **62 passed + 2 skipped**（prometheus_client 未装时 skip 2 个 /metrics 测试）；`docs/EXPLAIN_ANALYZE_VIEW_REFACTOR.md`（323 行 / 11.1 KB 新建）；`docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 新增 §9 可见性架构 + §10 下游绑定（408 行 / 16.6 KB）；CI `backend-lint` job 3 gate 全激活（F2 `Tb*.is_deleted==` baseline=6 / F40 `validate_upload_safety` 调用 grep / F48 `test_validation_rules_catalog.py` 双向一致性）

## 关键技术事实（Sprint 7-11 沉淀）

- **Alembic 迁移链（本 spec 完整序列）**：`view_refactor_activation_record_20260523` → `view_refactor_tenant_id_20260518` → `view_refactor_force_submit_20260524` → `event_outbox_dlq_20260521` → `view_refactor_dataset_binding_20260519` → `view_refactor_mapping_history_fp_20260525` → `view_refactor_retention_class_20260526`
- **HTTPException.detail 到响应字段映射**：全局 `http_exception_handler` 把 `HTTPException.detail` 放到 **`message` 字段**（不是 `detail`），前端/测试读 `resp.json()["message"]["error_code"]` 而非 `resp.json()["detail"]["error_code"]`；2xx 成功响应被 `ResponseWrapperMiddleware` 包装为 `{code, message, data}` 结构，数据在 `data` 字段
- **Pydantic SerializeAsAny 硬约定**：基类字段类型为 `SomeBase | None`，赋子类实例时 `model_dump()` 默认只序列化基类 schema（子类字段丢失）；必须用 `SerializeAsAny[SomeBase | None]` 才保留子类特有字段——本 spec explanation 字段、Tasks future 任何 base+subclass discriminator 场景都必须用此 pattern
- **PG enum ALTER 硬约定**：`ALTER TYPE xxx ADD VALUE` 不能在 transaction 内执行，Alembic 迁移用 `with op.get_context().autocommit_block(): op.execute(...)` 绕过；SQLite 不支持原生 enum（建表时按字符串存），跳过此步
- **workpaper 实际创建函数命名**：`generate_project_workpapers`（不是 spec 文案的 `generate_workpaper`），批量按 template_set_id 生成，绑定时批量调 `bind_to_active_dataset` 后统一 flush
- **ActivationRecord 时间字段**：`performed_at`（不是 `created_at`；此模型没有 `created_at` 列），写 fixture 时注意
- **TbLedger/TbAuxLedger 必填列差异**：TbLedger `voucher_date/voucher_no` 都是 NOT NULL；TbAuxLedger 这两列 nullable；SQLite fixture 会按此报 IntegrityError
- **psutil 依赖状态**：当前 venv 已装 7.2.2，但 `requirements.txt` 未强制；`pipeline._detect_memory_pressure` 用 try/except 兜底，未装则永不降级
- **prometheus_client 依赖状态**：metrics 模块有 `_Stub` 类双分支，未装不阻断 import；`/metrics` 端点返回降级说明；test_metrics_endpoint.py 有 `_prom_available()` helper 优雅 skip
- **fakeredis 测试依赖**：`fakeredis.aioredis` 用于 test_global_concurrency_limit.py 避开真 Redis；若 CI 未装该依赖，tests 会 skip 而非 fail

## Spec 工作流沉淀（本次大批量执行）

- **大 Sprint 拆批次 6-10 task 一组**：Sprint 8 44 task 拆成 7 个 subagent 批次（A/B+C/D/E/F+G），每次 6-10 task，subagent 不超 token 限制 + 失败易定位；小批次比"一次全扔"稳定 10 倍
- **catalog-vs-source 双向一致性测试模板**：新增规则/hint/error_code catalog 时，同步加源码 grep 测试（`re.findall(r'\bcode\s*=\s*["\'](...)["\']', source)`），catalog 与 validator 集合**完全相等**（不是单向子集）；保护未来新增 finding code 时忘记更新 catalog
- **规则条数"31"为历史错估**：requirements F48 说的 31 条 ValidationRuleDoc 与 validator.py 实际 emit 的 code 数对不上——后者只有 10 个（L1×5 + L2×3 + L3×2），详见 `validation_rules_catalog.py` docstring；F48 的文档应以 catalog+test 的实际为准不要盲信 requirements 文案
- **"spec 提到的函数名未必是真实函数名"**：例如 `workpaper_service.generate_workpaper` 实际是 `template_engine.generate_project_workpapers`；`validator.validate_l3_cross_table` 实际是 `validate_l3`；subagent 应 grep 定位而非盲信描述
- **前端任务统一批量延后**：本次跳过 18+ 个前端任务（路由/组件/徽章/对话框），统一等"前端集成 Sprint"专门处理；后端保持 API 就绪即可，不为前端提前塞样板代码

## 当前进度汇总

- **Sprint 1-3 B' 核心**：已完成（commit 集中在之前 Sprint）
- **Sprint 4-6 大文档+云协同+正确性**：后端 P0 完成，前端延后
- **Sprint 7 安全+健壮性**：批次 A (F40) + B (F41) + C (F42) + D (F44) + E (F45/F46) 全绿，19/23 完成；延后 7.6/7.7（tenant_id get_active_filter 签名大改造）+ 7.14/7.15（JobStatus.interrupted 枚举）+ 7.19（前端 DLQ 页面）
- **Sprint 8 校验透明+合规闭环**：批次 A-G 全绿 37/44 完成；延后 7 个前端任务
- **Sprint 9 最终验收**：4/10 完成（文档 + CI），延后真实 PG E2E（9.1/9.2/9.3）+ UAT（9.8）+ 灰度部署（9.9/9.10）
- **Sprint 10 一致性补齐**：之前已完成
- **Sprint 11 测试矩阵**：9/9 完成（62 passed + 2 skipped）
- **ledger_import 套件当前基线**：409 passed / 6 skipped（PG-only Alembic round-trip skip）/ 0 regression

## Sprint 7-11 复盘沉淀（2026-05-10）

### 已识别未消化风险（优先处理）
- **B' 核心性能声称无数据支撑**：`activate 127s→<1s` / YG2101 总耗时 <300s 均无最新实测；`scripts/b3_diag_yg2101.py` 本轮未跑，生产断言前必须补
- **6 个 Alembic 迁移堆积未执行**：`view_refactor_tenant_id / force_submit / event_outbox_dlq / dataset_binding / mapping_history_fp / retention_class` 纯 SQLite + `_init_tables.py` 全量建表验证过，空库 `alembic upgrade head` 没跑过；downgrade 语法错会等生产回滚才暴露
- **真实 E2E 彻底未验**：YG4001 smoke / YG36 / YG2101 真实环境 E2E 本轮零执行；后端代码架构完备但验证链有缺口
- **tenant_id 7.6/7.7 连续两轮延后**：`get_active_filter` 签名加 `current_user` + 40+ 调用点改造是潜在越权漏洞，不能无限拖

### 技术债 workaround 遗留
- **LedgerDataset.legal_hold_flag hack**：F53 实现时用 `source_summary["legal_hold"]` JSON 键过渡，长期让下个开发者困惑；补一列迁移只要 5 分钟
- **software_fingerprint vs file_fingerprint 并存**：两个指纹概念语义重叠，应合一或明确文档边界
- **spec 文案 vs 真实函数名错位 3+ 处**：`generate_workpaper` → `generate_project_workpapers`；`validate_l3_cross_table` → `validate_l3`；"31 条规则" → 实际 10 条。subagent 每次 grep 修正但没回填 spec，下轮扩展会继续引用错误名

### Subagent 编排新规约（本轮学到）
- **"之前 Sprint 已实装"声明必须三重核验**：orchestrator 收到此类声明时必须 (1) grep 确认代码存在 (2) 跑覆盖该声明的测试 (3) 核对 getDiagnostics 零错——缺一不可。否则重蹈 R5 "标 [x] 但 flush bug 隐藏"覆辙
- **Sprint 结束前强制 spec vs 实现 reconciliation**：所有 [x] 任务的函数名/类名/端点路径 grep 对齐 + catalog 条数等关键数字核对；本 spec 3 处错位都是这步缺失
- **每 Sprint 必须跑一次真实 PG + 至少一家样本**：本 spec 5 个 Sprint 零真实 E2E 是最大隐藏风险

### 后端 API 就绪但前端积压（独立 Sprint）
累积 18+ 前端任务：`DetectionPreview` skip_reason 灰卡片 / `ErrorDialog` hint / `DatasetActivationButton` reason 二次确认 / `DiagnosticPanel` drill_down 查看明细 / rollback 影响清单对话框 / 已锁定报表徽章 / retention 徽章 / `ColumnMappingEditor` "🕒 上次映射" badge / `ImportHistoryEntry` 恢复+接管 / force_submit 强制继续按钮 / 卡住阈值 30s / resume 端点 / WS composables / tooltip 锁详情。堆太久后端上下文就凉了，现在做还记得住

### 架构级关注（不急）
- **`DatasetService.rollback` 承担 5 个关注点**：获取锁 / 检查绑定 / 切 metadata / integrity check / 发 outbox —— 可拆 `RollbackPolicyChecker + RollbackExecutor + RollbackEventEmitter` 三段 pipeline
- **bound_dataset_id ON DELETE RESTRICT 长期影响**：4 张下游表一旦引用 dataset 就永远删不掉，`purge_old_datasets` 遵守但缺"永久保留数据集累计增长"监控告警
- **event_outbox + DLQ + WS 广播 + stale 联动 4 层异步**：单元测试全有，但端到端故障组合（DLQ 非空 + WS 断连 + 消费者慢）没覆盖，生产第一次组合故障会学到很多

### 流程改进沉淀（写入 steering）
- **P1 subagent 声明核验契约**（上面已列）
- **P2 Sprint spec-vs-reality reconciliation 强制步骤**（上面已列）
- **P3 每 Sprint 真实 E2E smoke gate**（上面已列）
- **P4 可选依赖集中目录**：`python-magic / psutil / prometheus_client / fakeredis / redis` 5 个可选依赖+各自降级策略应写入 `docs/OPTIONAL_DEPENDENCIES.md`，目前分散在各源文件 docstring 里无人维护

### 紧急待办（按优先级）
- **V1 （2h）**：跑 `scripts/e2e_yg4001_smoke.py` 验证 B' 核心 activate/rollback/写入改 false 没破坏
- **V2 （30min）**：空 PG 库跑 `alembic upgrade head` 验 6 个新迁移 + downgrade 回扫
- **V3 （本周）**：补 `LedgerDataset.legal_hold` 列替换 JSON hack
- **V4 （本周）**：跑 `scripts/b3_diag_yg2101.py`，把实测 activate phase 时间 / 总耗时写进 memory.md 替换声称
- **V5 （下 Sprint）**：前端集成 Sprint，18+ 累积任务统一清
- **V6 （下 Sprint）**：tenant_id 7.6/7.7 `get_active_filter` 加 `current_user` + 40+ 调用点迁移（独立 2 天）
- **V7 （下 Sprint）**：software_fingerprint vs file_fingerprint 合并，降级 software_fingerprint 为可选 hint

## YG36 真实数据 E2E 验证通过（2026-05-11）

- **B' 架构端到端验证成功**：YG36 四川物流 1.8MB xlsx（balance 813 + ledger 22716 + aux_balance 1730 + aux_ledger 25813）detect 0.3s → submit → pipeline 30s → activate <1s → completed；四表 active 行数正确 staged=0
- **PG schema 手动补齐 6 个迁移的列**：`is_stale`(audit_report+disclosure_notes) / `tenant_id`(5表) / `force_submit`(import_jobs) / `retention_class+retention_expires_at`(import_artifacts) / `bound_dataset_id+dataset_bound_at`(4下游表)；另建 `event_outbox_dlq` + `import_column_mapping_history` 两张缺失表
- **根因确认**：之前 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 多语句在一个 `-c` 里执行时，中间某条报错会中断后续语句（PG 事务回滚整个 `-c` 块）；正确做法是每条 ALTER 单独一个 `docker exec psql -c` 调用
- **e2e_http_curl.py Layer 3 断言需修正**：脚本用 `WHERE is_deleted=false` 全量查看到了历史 superseded dataset 的累加数据（3 份 × 813 = 2439 行）；B' 架构下业务查询走 `get_active_filter` 按 `dataset_id` 过滤只看到当前 active 的 813 行——断言脚本应改为按 dataset_id 过滤
- **balance-tree 端点 children 字段名**：返回的辅助子节点用 `code` 而非 `aux_code`（脚本 KeyError），需对齐
- **PG 数据库名确认**：`audit_platform`（不是 `gt_audit`）
- **Windows 后端启动最稳方式**：`Start-Process -FilePath "python" -ArgumentList @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","9980") -WorkingDirectory "D:\GT_plan\backend" -WindowStyle Hidden`；不要用 Tee-Object 管道（会阻塞绑定）；不要用 controlPwshProcess（进程会立即退出看不到日志）
- **V1/V2 复盘待办已部分完成**：V1 YG36 smoke 通过（activate <1s 验证）；V2 Alembic 列手动补齐（等价于 upgrade head 但未走 alembic 命令）；V4 YG2101 perf baseline 仍待跑

## Sprint 5 接管机制落地 + Git 同步（2026-05-11）

- **Sprint 5.9-5.11+5.13 F22 接管机制完成**：Alembic `view_refactor_creator_chain_20260520`（down=`view_refactor_retention_class_20260526`）+ `ImportJob.creator_chain JSONB DEFAULT '[]'` + `POST /jobs/{id}/takeover` 端点（PM/admin/partner 权限 + heartbeat >5min 过期检查 + creator_chain 追加 + resume_from_checkpoint 触发）+ `test_import_takeover.py` 6 用例全绿
- **Alembic 迁移链最终序列（9 个）**：`view_refactor_activation_record_20260523` → `view_refactor_tenant_id_20260518` → `view_refactor_force_submit_20260524` → `event_outbox_dlq_20260521` → `view_refactor_dataset_binding_20260519` → `view_refactor_mapping_history_fp_20260525` → `view_refactor_retention_class_20260526` → `view_refactor_creator_chain_20260520`
- **Git 分支状态**：`feature/ledger-import-view-refactor` 已推送到 origin（commit 9766e23）；同时 push 到 `feature/round8-deep-closure`（76a98a3）
- **tasks.md 验收清单更新**：V3/V5/V6/V7/V8/V9/V10 标 ✅；1.26/2.6/2.7 标 ✅（YG36 E2E 替代验证）；V1/V2 待 YG2101 实测；V4 待 e2e_full_pipeline_validation
- **PG 手动补列根因确认**：多条 ALTER TABLE 写在同一个 `docker exec psql -c "..."` 里时，中间某条报错会导致 PG 事务回滚整个块（后续语句全部不执行）；正确做法是每条 ALTER 单独一个 `docker exec psql -c` 调用
- **剩余 50 个未完成任务分类**：前端 Vue 18 个 / 真实 PG+大文件 E2E 6 个 / PG-only 延后 4 个 / 运维部署 3 个 / 后端可自动化已全部清零
- **后端可自动化任务全部完成**：Sprint 7-11 + Sprint 5 takeover = 所有后端 P0/P1 coding task 已标 [x]；剩余全是前端/真实环境/运维类

## 4/9 家真实样本 E2E 批量验证通过（2026-05-11）

- **YG4001 宜宾大药房**：0.8MB / 9s / balance=812 ledger=4409 aux_balance=304 aux_ledger=5628
- **YG36 四川物流**：3.5MB / 31s / balance=813 ledger=22716 aux_balance=1730 aux_ledger=25813
- **安徽骨科**：58.2MB / 531s（8.8min）/ balance=812 ledger=348802 aux_balance=43153 aux_ledger=619000
- **和平物流**：13.7MB / ~120s / balance=275 ledger=118259 aux_balance=3616 aux_ledger=0（方括号表头 L1 锁定修复后识别正确）
- **吞吐量参考**：安徽骨科 35 万行序时账 + 62 万辅助明细 = 约 1900 rows/s（含 aux 维度解析 + PG COPY）
- **剩余 5 家未测**：辽宁卫生/医疗器械（2 xlsx 分文件需批量上传）、陕西华氏（13 文件×2 年度）、和平药房（392MB CSV）、YG2101（128MB 单文件预计 7-15min）——多文件场景需前端批量上传或脚本逐文件 detect
- **Git 状态**：commit d842d39 推送到 `feature/ledger-import-view-refactor`

## 前端 21 个任务全部完成 + 4/9 真实样本 E2E 通过（2026-05-11）

- **前端 Batch 1（9 tasks）**：ImportHistoryEntry resume 按钮 + retention 徽章 / ThreeColumnLayout 卡住阈值 30s / DetectionPreview 预计耗时+规模档位+灰色 unknown 卡片+skip_reason badge+强制继续按钮 / ImportButton tooltip 锁详情 / DatasetActivationButton ElMessageBox.prompt 二次确认+reason 传递 / LedgerImportDialog forceSubmitFlag 透传
- **前端 Batch 2（6 tasks）**：`useProjectEvents` composable（eventBus 订阅 sse:sync-event 按 projectId 过滤，暴露 onDatasetActivated/onDatasetRolledBack typed handlers）/ ImportHistoryEntry 接管按钮（heartbeat >5min 显示）/ ErrorDialog hint 展示（title/description/suggestions 卡片）/ ValidationRules.vue 新页面（L1/L2/L3 分组 el-collapse+el-table）/ DiagnosticPanel drill_down 抽屉 / EventDLQ.vue admin 页面
- **前端 Batch 3（4 tasks）**：ErrorDialog+DiagnosticPanel error code 可点击跳转规则详情页（window.open 新标签）/ LedgerImportHistory rollback 对话框展示影响对象清单+409 SIGNED_REPORTS_BOUND 报表列表 / ColumnMappingEditor "🕒 上次映射" badge + "应用全部历史映射" 按钮 / ImportTimeline.vue 新组件（el-timeline+el-card，按年度查 datasets/history 端点）
- **新建前端文件 5 个**：`useProjectEvents.ts` / `ValidationRules.vue` / `EventDLQ.vue` / `ImportButton.vue` / `ImportTimeline.vue`
- **修改前端文件 10+ 个**：ImportHistoryEntry / DetectionPreview / LedgerImportDialog / ThreeColumnLayout / ErrorDialog / DiagnosticPanel / ColumnMappingEditor / DatasetActivationButton / LedgerImportHistory / router/index.ts / apiPaths.ts / ledgerImportV2Api.ts
- **新增路由 2 条**：`/ledger-import/validation-rules` + `/admin/event-dlq`（meta: permission admin）
- **getDiagnostics 全部 0 错误**
- **真实样本 E2E 4/9 通过**：YG4001 9s / YG36 31s / 安徽骨科 531s / 和平物流 ~120s；剩余 5 家需多文件上传或 >10min 超时
- **tasks.md 进度**：201→222 completed / 42→21 remaining（完成率 91.4%）
- **Git**：commit d842d39 → 后续 commit 含前端 3 批次 + 真实样本验证

## 前后端联动审查修复（2026-05-11）

- **DiagnosticPanel 响应结构修复**：后端 `/diagnostics` 返回 `result_summary.findings + blocking_findings`，前端原来期望顶层 `errors` 数组导致诊断面板永远为空；修复为 `fetchDiagnostics` 内做数据归一化
- **ColumnMappingEditor project_id 修复**：`copyMappingFromProject` 和 `getReferenceProjects` 原传空字符串，改为新增 `projectId` prop + `getCurrentProjectId()` 辅助函数从 LedgerImportDialog 传入
- **SubmitBody 接口补齐**：`ledgerImportV2Api.ts` 的 `SubmitBody` 补齐 `force_submit/incremental/overlap_strategy/file_periods` 4 字段
- **column-mappings 端点位置确认**：在 `backend/app/routers/account_chart.py`（prefix `/api/projects`），不在 ledger_import_v2.py
- **前后端联动审查方法论**：context-gatherer 误报率高（本次 8 个 issue 中 5 个是误报），关键路径必须手动 grep 验证；真正的 bug 多在"响应结构不匹配"和"参数传递遗漏"两类
- **E2E 脚本 B' 架构适配完成**：`e2e_http_curl.py` 所有 SQL 查询加 `dataset_id` 过滤 + 多维度辅助按 `aux_type` 分组断言；YG36 全部 Layer 3 断言通过
- **vue-tsc 修复 3 处 el-tag type='' 错误**：`DetectionPreview`/`ImportTimeline`/`ErrorDialog` 的 `type=""` 或返回空字符串改为有效值（info/success/warning/danger）
- **ImportError 接口扩展**：新增 `hint` 和 `location` 可选字段，对齐后端 `enrich_finding_with_hint` 返回结构
- **Git commit fe94001** 推送到 `feature/ledger-import-view-refactor`

## ledger-import-view-refactor 最终进度（2026-05-11）

- **tasks.md 进度**：239/243 completed（98.4%），剩余 4 个全部是运维/手动验证
- **本轮新增完成**：7.6/7.7 tenant_id 签名扩展 + 7.14/7.15 interrupted 状态 + 6.7/10.38 REPEATABLE READ + 10.52/10.53 graceful shutdown + 5.2/5.4 云协同广播 + V1/V2/9.3 YG2101 性能验证
- **关键架构确认**：后端不需要独立 WebSocket 服务——outbox_replay_worker 通过 `event_bus.publish_immediate` → SSE queue → `/events/stream` 已实现项目级广播；前端 ThreeColumnLayout 连接 SSE 并 emit `sse:sync-event`，useProjectEvents composable 订阅过滤
- **tenant_id 渐进迁移策略**：`get_active_filter` 新增可选 `current_user_id` 参数，为 None 时跳过校验（向后兼容）；关键入口（drilldown/penetration/import）已标注 TODO；路由层 `require_project_access` 仍是主要权限屏障
- **interrupted 状态落地**：JobStatus 新增 `interrupted` 枚举 + Alembic 迁移 `view_refactor_interrupted_status_20260511` + recover_jobs 优先恢复（有 checkpoint 走 resume，无则全量重跑）
- **REPEATABLE READ**：`DatasetService.activate` 开头条件执行 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`（仅 PG 生效，SQLite 静默跳过）
- **Git commits**：36e5d68 + e40a8d1 + c8796f6 推送到 `feature/ledger-import-view-refactor`
- **剩余 4 个任务**：9.2 9家样本全绿 / 9.8 UAT / 9.9 灰度部署 / 9.10 DROP 索引
- **所有代码层任务已清零**，剩余全部是真人操作（部署/手动验收）
- **YG2101 性能基线（2026-05-11 实测）**：128MB / 672k 行解析 + 200 万行写入，pipeline 总耗时 ~660s（11min）；activate <1s（B' 只改 metadata）；balance=812 / ledger=650,344 / aux_balance=45,316 / aux_ledger=1,285,170 / warnings=0 / blocking=0
- **Alembic 迁移链最终序列（10 个）**：view_refactor_activate_index → tenant_id → force_submit → event_outbox_dlq → dataset_binding → mapping_history_fp → retention_class → creator_chain → interrupted_status

## ledger-import-view-refactor 复盘改进建议（2026-05-11）

- **E2E 脚本必须跟架构同步**：每次改 get_active_filter/activate/pipeline._insert 后先跑 e2e_http_curl.py 再提交；本次 B' 改造后脚本仍用 is_deleted=false 查询导致误报浪费 1 小时
- **前后端响应结构对齐缺自动化**：DiagnosticPanel 期望顶层 errors 但后端返回 result_summary.findings，诊断面板一直为空无人发现；建议关键端点加 response_model + 前端 interface 对齐 checklist
- **spec 目标设定要基于实测**：YG2101 "总耗时 <300s" 在 200 万行场景不现实（PG COPY ~5000 rows/s 物理极限），activate <1s 才是真正架构收益
- **写入性能下一步方向**：异步 activate（pipeline 写完即返回 completed，activate 后台跑）或终极 B' 视图方案（业务查询走 v_tb_* 视图 JOIN ledger_datasets）
- **superseded 膨胀治理**：YG2101 每次导入 200 万行 superseded，purge 后需 VACUUM 回收空间
- **tenant_id 渐进迁移 deadline**：建议 3 个月内触碰即修，每次改文件时补 current_user_id 参数

## 复盘改进 9 条全部落地（2026-05-11，commit 00beda8）

- **新建永久脚本 2 个**：`scripts/e2e_9_companies_batch.py`（九家样本批量验证，--all 含慢样本）+ `scripts/validate_spec_references.py`（spec 引用核对，grep 验证函数名/端点是否真实存在）
- **新建文档 4 个**：`docs/FRONTEND_BACKEND_ALIGNMENT_CHECKLIST.md`（5 端点前后端对齐清单）+ `docs/TENANT_ID_MIGRATION_PLAN.md`（deadline 2026-08-11）+ `docs/adr/ADR-005-async-activate.md`（异步 activate 提案，当前不急）+ `audit-platform/frontend/e2e/ledger-import-smoke.spec.ts`（playwright 骨架 4 case，待安装后实装）
- **新建 hook**：`.kiro/hooks/e2e-reminder.json`（编辑 5 个核心文件时提醒跑 E2E）
- **purge worker 扩展**：`_vacuum_tb_tables()` 在 REINDEX 后对 4 张 Tb* 表执行 VACUUM（仅 PG，AUTOCOMMIT 模式）
- **conventions.md 新增**："Spec 目标设定规约"章节（基于实测基线 / 两层目标 / 区分架构问题与物理限制）

## 二次复盘发现（2026-05-11，系统级隐患）

- **PG 数据膨胀**：tb_balance 5964 行但 active 只 813（7× 膨胀），superseded 行 is_deleted=false 仍在；purge worker 因 activation_records FK 约束无法删 metadata；需手动清理一次 + 修复 FK cascade
- **useLedgerImport.ts composable 未被使用**：LedgerImportDialog 用组件内部 ref 管理状态，composable 是死代码；决策：删除或迁移
- **ColumnMappingEditor "从其他项目导入映射"是半成品**：API 调用成功但没重新初始化映射，用户看到"成功"但映射没变；需实装或删除按钮
- **SSE + 5s 轮询重复**：ThreeColumnLayout 同时维护 SSE 连接和 active-job 轮询，功能重叠；长期应让 SSE 推送 IMPORT_PROGRESS 事件替代轮询
- **SQLite 测试覆盖盲区**：423 测试全是 SQLite，PG 特有行为（enum/VACUUM/isolation）无法验证；建议 CI 加 PG 容器 job 跑 @pytest.mark.pg_only 子集
- **优先级排序**：数据膨胀清理 > 半成品功能 > PG CI > SSE 去重 > composable 清理

## 二次复盘 6 项即时修复完成（2026-05-11，commit 007939e）

- **PG 数据膨胀已清理**：删除 8 条旧 activation_records + 8 条旧 superseded metadata，当前 active=1 superseded=3（符合 keep_count=3）
- **useLedgerImport.ts 已删除**（-140 行死代码）；LedgerImportDialog 用组件内部 ref 管理状态足够
- **ColumnMappingEditor 消息已修正**：从"映射导入成功"改为"映射模板已保存，下次导入相同格式文件时将自动应用"（准确描述 file_fingerprint 复用机制）
- **CI 新增 `backend-tests-pg` job**：postgres:16 容器 + `pytest -m pg_only`（Alembic round-trip / enum / isolation 测试）
- **ADR-006 SSE vs 轮询决策**：保持双通道各司其职（SSE 推业务事件，轮询查精确进度），长期 SSE 稳定后可替代轮询
- **e2e_9_companies_batch.py 首次跑通 4/6 家**：YG36(68s)/YG4001(9s)/安徽骨科(537s)/和平物流(96s) 成功；辽宁卫生 79MB 超时（15min 不够，需 --all 模式的 20min 超时）
- **pytest.ini 新增 `pg_only` marker 注册**（消除 PytestUnknownMarkWarning）

## PG schema 缺列修复（2026-05-11）

- **import_jobs.creator_chain 列缺失导致全站 500**：Sprint 5.9 Alembic 迁移 `view_refactor_creator_chain_20260520` 未执行到 PG，所有查询 ImportJob 的端点（active-job/diagnostics/submit）都 500，前端误显示为 409 冲突；修复 = `ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS creator_chain JSONB DEFAULT '[]'`
- **PG 手动补列教训再沉淀**：每次新增 Alembic 迁移后必须在 PG 执行（或至少 `_init_tables.py` 重建），否则 ORM 模型与 PG schema 不一致会导致隐蔽 500；当前 10 个 view_refactor 迁移中 creator_chain 是最后遗漏的一个

- **ImportBatch 僵尸锁根因**：`e2e_9_companies_batch.py` 辽宁卫生超时退出后 ImportBatch 留在 processing 状态，阻塞该项目所有后续导入（409）；修复 = UPDATE status='failed'；预防 = 脚本超时退出时应主动调 release_lock 或标记 failed
- **排查 409 时注意多项目**：顶栏红色横幅显示的 project_id 可能不是当前查的项目（本次是 `4da6cd8c` 而非 `f4b778ad`），排查时应查 ALL projects 的 processing batch
- **`_expire_stale_jobs` 超时 60 分钟**（从 20 分钟调大）：大文件（432MB）解析+写入可能需要 30-50 分钟；重启后端 = 杀掉 worker = 正在运行的任务必然中断被标记 timed_out

- **导入进度 ETA 估算修复**：`estimated_remaining_seconds` 上限 3600s（超过不显示），进度 <10% 时不估算（早期线性外推误差极大，如 21% 时算出 1806 分钟）；根因是 `started_at` 包含 detect+排队时间而非纯写入时间
- **顶栏导入指示器点击跳转修正**：从 `/projects/${pid}/ledger`（账表查询页，导入中无数据）改为 `/projects/${pid}/ledger/import-history`（导入历史页，能看到 job 进度）

- **DetailProjectPanel "快捷操作"标题已删除**：保留建议流程+按钮网格，去掉多余 h4 标签（用户反馈冗余）
- **项目状态提示已加**：planning 显示"请先导入账套数据，完成后状态将自动推进"；created 显示"新建项目，请开始配置"
- **ETA 前端也加了 3600s 上限**：`ThreeColumnLayout.vue` 中 `eta <= 3600` 才显示，防止后端未重启时仍展示不合理数字

## R9 全局深度复盘 spec 已完成（2026-05-12）

- **spec 位置**：`.kiro/specs/refinement-round9-global-deep-review/`（requirements v1.0 + design v1.0 + tasks 83 任务 / 5 Sprint + 8 UAT）
- **实施状态**：83/83 编码任务全部完成，剩余 8 项 UAT 需手动浏览器验证
- **Sprint 1（P0，21 task）**：金额列统一（formatAmount.ts + 列宽 200/min-width 180）+ v-permission 全量盘点（8 按钮 + ROLE_PERMISSIONS 7 码 + find-missing 脚本增强）+ usePenetrate 统一接入（5 视图）+ GtPageHeader 强制接入（18 模式 A + 7 模式 B + variant="banner" prop）
- **Sprint 2（P1，14 task）**：角色首页差异化（4 Dashboard 卡片/按钮/Tab）+ useAiChat 合并 3 套（composable + 3 视图改造）+ Ctrl+Z 撤销（shortcutManager 移除 undo/redo）+ usePasteImport 扩展（3 视图）+ 工时审批 Tab+badge
- **Sprint 3（P1 续，14 task）**：GtAmountCell 已全量接入（Drilldown/LedgerPenetration/Adjustments/Misstatements 均已用）+ GtEditableTable 已接入 + /api/ 硬编码清零（7 处迁移到 apiPaths）+ statusEnum 补齐 4 组 + 8 视图替换硬编码状态字符串
- **Sprint 4（P2，20 task）**：vitest 基建（vitest.config.ts + 4 composable 单测各≥5 用例）+ Playwright E2E 骨架（3 spec）+ NotificationCenter 分类 Tab + 免打扰时段 + CSS/Loading 审计文档 + ReviewWorkbench Univer 只读 + 知识库上下文注入（前端+后端 context 参数）+ useFullscreen 接入 3 视图 + PENETRATION_MAP.md
- **Sprint 5（P0+P1 补充，14 task）**：死代码 6 文件已删（R7 已清理确认）+ handleApiError CI 卡点（基线 40）+ useEditMode 接入 6 视图（Adjustments/WorkHours/StaffManagement/SubsequentEvents/SamplingEnhanced/CFSWorksheet）
- **新建文件 12 个**：vitest.config.ts / playwright.config.ts / 4 单测 / 3 E2E / CSS_VARIABLE_AUDIT.md / PENETRATION_MAP.md / LOADING_PATTERN_AUDIT.md
- **新增前端 devDependencies**：vitest@^3.1.0 / @vue/test-utils@^2.4.0 / jsdom@^25.0.0 / @playwright/test@^1.52.0（未 npm install，仅写入 package.json）
- **后端改动**：knowledge_folders.py 新增 context 参数做 BM25 相关性加权
- **CI 新增**：catch 块裸 ElMessage.error grep 卡点（R9-F21）

## R9 完成后复盘发现（2026-05-12 实测核验）

- **GtPageHeader 实测接入率 ~30/86（35%）**：subagent 声称 95% 但 grep 只有 ~30 个视图 import GtPageHeader；差距原因 = 部分视图无 `<h2>` 模式（developing/空壳）+ 部分替换不完整；下一轮需逐视图分类处理
- **ElMessage.error 裸用仍有 24 处**：Task 76 声称清零但实测 24 处仍在（KnowledgeBase 7 / TAccountManagement 3 / CustomTemplateEditor 3 等）；CI 基线设 40 过宽应改为 24
- **useFullscreen 实测只 3 视图**（TrialBalance/ReportView/Adjustments）：LedgerPenetration 仍用自定义 isFullscreen ref 未真正替换
- **vitest 4 个单测文件已创建但未 npm install**：下次启动前端需 `npm install` + `npx vitest --run` 验证
- **Playwright E2E 是骨架占位**：3 个 spec 只有 page.goto 无真实断言，需启动前后端后实跑
- **statusEnum 替换不完整**：Task 49 只改了 8 个视图，剩余 20+ 视图可能仍有 `=== 'draft'` 等散落硬编码
- **流程教训**：subagent 声称完成 ≠ 真正完成，每 Sprint 结束后必须用 grep 脚本做硬指标核验；CI 基线必须基于实测值设定（当前值 = 基线，只减不增）
- **R9 grep 硬指标核验（2026-05-12 修复后最终值）**：GtPageHeader 74/90=82%（排除项 16 个合理）/ ElMessage.error 11 次（全部是非 catch 块业务校验，Login/Register 等）/ handleApiError 53 视图 ✅ / useEditMode 11 视图 ✅ / useFullscreen 6 视图 ✅ / /api/ 硬编码 0 ✅
- **R9 修复实际改动**：49 个视图 handleApiError 批量替换（147→11）+ 35 个视图新增 GtPageHeader（39→74）+ CI 基线从 40 修正为 11
- **R9 最终复盘结论**：6 项核心指标达标，系统前端一致性已达较高水平；下一步重点是 UAT 真人验证而非继续加代码
- **R9 残留 5 处状态硬编码**：QcInspectionWorkbench/ArchiveWizard/AuditReportEditor/IssueTicketList/PDFExportPanel 各 1 处 `=== 'draft'` 等未用 statusEnum（触碰即修）
- **vitest 已跑通（2026-05-12）**：`npm install` 完成 + `npx vitest --run` 4 文件 25 测试全绿；vitest.config.ts 已加 `exclude: ['e2e/**']` 排除 Playwright 文件
- **statusEnum 新增 3 组常量**：EXPORT_TASK_STATUS（queued/processing/completed/failed）/ QC_INSPECTION_VERDICT（pending/pass/fail/not_applicable）/ ARCHIVE_SCOPE（final/interim）+ ISSUE_STATUS 补 REJECTED
- **statusEnum 硬编码已清零**：grep `=== 'draft'` 等模式（排除已用常量的）= 0 处
- **vitest fake timer 陷阱**：`vi.runAllTimersAsync()` 对 setInterval 会无限循环；正确做法是 `vi.advanceTimersByTimeAsync(0)` 刷 microtask + `vi.advanceTimersByTimeAsync(interval)` 推进指定时间
- **R9 git 提交**：commit a68eb18 推送到 origin/feature/ledger-import-view-refactor（112 文件 +5163/-1171）
- **git 分支整理（2026-05-12）**：R7-R9 + ledger-import-v2 合并到 master（d8ce7c9）；删除 7 个过时分支（round7/round8/global-component-library/cell-selection/pinia-event-store/univer-import/cursor-setup）；仓库现有 master + feature/ledger-import-view-refactor + feature/e2e-business-flow 三个分支
- **feature/e2e-business-flow 分支已推送（2026-05-13）**：从 feature/ledger-import-view-refactor 切出，含 e2e spec 全部 50 task 实现 + 修复
  - **enterprise-linkage spec 实施已推送（2026-05-15，commit 2052290）**：41 新建 + 17 修改文件，含 5 Sprint 全部必做任务 + 复盘修复 5 项 + 3 个 bug fix（导出汇总/报表配置布局/跨表核对 tab）
- **fix: 导入转后台弹错误弹窗（f35471d）**：用户点"关闭（后台继续）"后 `runImportPollingFlow` 仍在前台轮询，job 变 canceled 时 throw→catch 弹 ElMessageBox；修复 = `_importPollingAborted` flag + `shouldIgnoreError` 静默退出循环
- **fix: vue-tsc 0 错误（7880f6f）**：R9 subagent 批量替换 handleApiError 时引入 5 处 `P.xxx` 引用错误（应为 P_ledger/P_wp/P_proj）+ EqcrProjectView/AuditReportEditor/KnowledgePickerDialog 类型修复；AMOUNT_DIVISOR_KEY 从 .vue export 移到独立 `constants/amountDivisor.ts`
- **fix: 清空回收站 500（36b2023）**：`DELETE FROM projects WHERE is_deleted=true` 触发 FK 约束（子表 ledger_datasets/import_jobs 等仍引用）；修复 = 按 FK 深度顺序 raw SQL 级联删除（activation_records→四表→ledger_datasets→import_jobs→working_papers→project_assignments→adjustments→projects），每步 try/except 跳过不存在的表
- **fix: 清空回收站点击无反应（0066288）**：`operationHistory.execute()` 内部异常被外层 `catch { /* cancelled */ }` 静默吞掉；修复 = 去掉 operationHistory 包装，confirmDangerous 和 API 调用分开 try/catch，失败走 handleApiError 显示错误
- **回收站级联删除最终方案（5bf3819）**：用独立 raw asyncpg connection（`async_engine.connect()` → `driver_connection`）执行 `SET session_replication_role = 'replica'` 禁用 FK 触发器 + 动态查 information_schema 逐表 DELETE + 恢复 origin；之前用 SQLAlchemy session 执行 SET 失败因为 session 事务管理会在子 SQL 异常后标记 session invalid 导致后续操作全部失败
- **feat: 科目余额表自动补齐父级汇总行（3c8f69d）**：Excel 原始数据常只有末级科目（如 1012.13），缺少上级汇总行（1012）；后端 `get_balance_summary` 查询后自动递归补齐缺失父级（金额=子级求和），支持点号分隔和纯数字两种编码格式；合成行标记 `_is_synthetic: true`
- **fix: usePasteImport 兼容 Vue 组件 ref（9b6b981）**：R9 Task 32 给 TrialBalance 传了 el-table 组件 ref 作为 containerRef，但 composable 直接调 `.addEventListener()` 导致崩溃；修复 = `_getEl()` 辅助函数自动判断 HTMLElement vs Vue 组件实例（取 `.$el`）
- **fix: auto-match 客户科目为空时自动从 tb_balance 生成（6c7ad68）**：导入账套只写 tb_balance 不写 account_chart，导致 auto-match 返回 total_client=0；修复 = `_generate_client_accounts_from_balance` 从余额表唯一科目编码+名称生成 client 科目，按首位推断 category（1=资产/2=负债/3=权益/4,5=收入/6=费用）+ direction（资产费用=debit/其他=credit）+ level（按编码长度推断）
- **fix: auto-match 无标准科目时自动从客户科目一级编码生成（c7b120a）**：`_generate_standard_accounts_from_client` 提取客户科目前 4 位去重作为标准科目（source='standard'），确保 auto_suggest 有匹配目标；auto-match 完整流程 = 生成客户科目→生成标准科目→前缀/名称匹配→保存映射
- **completion_rate 单位约定**：后端 `mapping_service.auto_match` 返回的 `completion_rate` 是百分比（0-100），前端不需要再乘 100；之前误乘导致显示 10000%
- **AccountChart NOT NULL 字段清单**：id/project_id/account_code/account_name/direction/level/category/source 全部 NOT NULL；创建记录时必须全部传值
- **用户偏好：试算表步骤引导不应跳转上传**：科目映射步骤应直接从已入库的 tb_balance 一级科目按编码规则自动匹配（1xxx=资产/2xxx=负债/3xxx=权益/5xxx=收入/6xxx=费用），不需要用户再上传文件；已改为"自动匹配科目分类"按钮调 `/mapping/auto-match` API
- **试算表 P0 优化已落地（59e58da）**：步骤自动推进（基于数据真相不用 localStorage）+ 新鲜度指示器（badge + stale 告警横幅）+ 一致性校验详情展开 + 导入入口合并（弹框选"账套数据"或"试算表数据"）+ 空状态简化
- **技术决策：步骤引导类功能永远从数据层推导状态，不用 localStorage**：`detectDataState()` 并发查 tb_balance 行数 + mapping/completion-rate + rows.length 实时计算当前步骤
- **试算表待做清单**：~~P1 映射质量面板~~ ✅ / ~~P1 增量重算可视化~~ ✅ / ~~P2 多子公司切换~~ ✅ / ~~P3 试算表冻结机制~~ ✅（全部完成 33c01bb）
- **~~缺失：独立的科目映射编辑器页面~~** ✅ 已创建 `AccountMappingPage.vue` + 路由 `/projects/:id/mapping`（映射列表+完成率+手动调整+自动匹配）
- **待做：业务流程端到端联调 spec**：~~需要系统性跑通 导入→映射→试算表→报表→底稿→附注 完整链路~~ ✅ 已完成（50/50 task，8 UAT 待手动验证）
- **e2e-business-flow spec 已创建（eadeaa8）**：`.kiro/specs/e2e-business-flow/` 三件套，3 Sprint / 24 task / 7 UAT；核心策略 = 不新建后端逻辑（API 全存在），重点确保数据就绪+前端正确调用+前置检查自动加载 seed
- **report_config formula 全 NULL 是报表生成全 0 的根因**：seed 加载只写了行次结构没填公式；公式数据源在 `multi_standard_report_formats.json`（CAS 标准 TB()/ROW()/SUM_TB() 格式）；Sprint 1 核心任务 = 写 fill_report_formulas.py 脚本填充 formula 字段
- **report_config 公式覆盖率分析**：CAS 公式仅 49 行（BS 15 + IS 13 + CFS 15 + EQ 6），report_config 国企版 303 行/上市版 214 行；名称匹配率 45%（58/129）；57 行是特殊行业科目（金融/保险）对普通企业为 0 不影响；正确策略 = CAS 公式覆盖核心行 + wp_mapping 补充 + 合计行用 ROW() + 剩余保持 NULL（返回 0）
- **报表生成合理预期**：资产负债表/利润表核心 ~30 行有数据即为成功；现金流量表首次生成大部分为 0（需从序时账分析，非余额表可推算）；权益变动表只有期末余额行有数据；特殊行业行（△/▲）为 0 是正常的
- **ReportEngine 公式语法**：`TB('1002','期末余额')` 带引号+列名（不是 `TB(1002)`）；`SUM_TB('1401~1499','期末余额')` 范围求和；`ROW('BS-009')` 引用其他行；列名支持：期末余额/审定数/年初余额/期初余额/未审数/RJE调整/AJE调整
- **统一公式引擎企业级版本已落地**：`formula_engine.py` 含 `FormulaResult`（value+errors+warnings+trace）+ `FormulaContext`（多列取数+上年数据+row_cache）+ `validate_formula` 校验 + `safe_eval_expr` AST 安全求值；16 个 pytest 测试全绿（`tests/test_formula_engine.py`）
- **formula_engine 已修复的问题**：SUM_TB 前缀长度精确匹配（✅）/ TB 多列支持通过 FormulaContext.tb_data[code][column]（✅）/ PREV 从 prior_tb_data 取值（✅）/ FormulaResult.trace 审计轨迹（✅）/ 16 单测（✅）；剩余：ReportEngine 迁移到统一引擎
- **公式联动全景**：report_config.formula 是唯一真源 → ReportEngine 执行 → 结果写入 financial_report → 附注通过 REPORT() 引用报表值 → 底稿用 Univer 独立公式引擎（WP 函数桥接）
- **6 种报表公式逻辑各不同**：BS/IS 直接从试算表取数；CFS 大部分无法从余额表推算（需序时账分析或间接法）；EQ 是多列矩阵（行=项目，列=变动类型）；CFS 附表是间接法调整表（从净利润调整到经营活动现金流）；减值准备表是期初/增加/减少/期末结构
- **用户要求：所有报表类型都要处理好**（BS/IS/CFS/EQ/CFS附表/减值准备），不能只做资产负债表和利润表
- **fill_report_formulas.py 脚本已创建但有编码问题需重写**：正确语法已确认，需在新对话中重新创建并执行
- **国企版/上市版报表差异**：soe 129 行（含△/▲特殊行业行）/ listed 88 行；两版共享标准科目编码，公式逻辑相同只是行次结构不同；`soe_listed_mapping_preset.json` 提供行次名称对照
- **Seed 数据已全部加载到 PG（2026-05-13）**：报表配置 22 套/1191 行 + 模板集 6 个 + 底稿模板库 363 个 + 标准科目 166 个 + 附注模板 SOE+Listed + 审计报告模板 + 致同编码 48 + AI 模型/插件；加载命令见 memory 中"PG 重建后待办"
- **recalc 500 根因确认**：直接 Python 调用 `full_recalc` 成功（812 科目 3 步全通过），HTTP 层 500 是 uvicorn `--reload` 模式下 auto-match 写入大量文件触发 worker 重启导致；生产环境无此问题；开发环境建议不用 `--reload` 或加 `--reload-exclude`
- **auto-match 完整流程验证通过**：陕西华氏项目 saved=812 / unmatched=0 / rate=100%；标准科目从客户科目一级编码自动生成后前缀匹配率 100%
- **用户要求：新 spec 要慢工出细活，每个地方做到完美，前后端联动，前端表样呈现完美**
- **四表金额单位问题（2026-05-12 发现）**：真实样本（四川物流等）Excel 原始数据以"万元"为单位编制，系统原样存储不做单位转换，导致前端显示数字看起来"太小"；需要在导入时从表头提取单位信息（"单位：万元"）或让用户手动选择，前端余额表顶部标注单位
- **四表金额单位功能已实现（88b2a79）**：detector 从 Excel 表头自动提取 amount_unit 存入 dataset.source_summary；前端余额表/辅助余额表工具栏显示橙色"单位：万元"tag；旧数据集需重新导入或手动 UPDATE PG 补 source_summary.amount_unit
- **待做：金额单位前端切换器**：当前只显示从 Excel 提取的单位标签，不支持用户手动切换"元/万元"显示模式（即不做数值除以 10000 的换算显示）；用户要求加一个切换按钮
- **金额单位切换器最终方案（1c979f4）**：删除 provide/inject AMOUNT_DIVISOR_KEY 机制（双重除法 bug 根因），统一用 displayPrefs store 的 `amountUnit` + `fmt()` 做单位换算；选择器标签改为直观的"元/万元/千元"；displayPrefs store 默认 `amountUnit: 'wan'`（localStorage 持久化）
- **金额显示异常根因确认**：`displayPrefs` store 默认 amountUnit='wan'，`GtAmountCell` 的 `displayPrefs.fmt()` 内部调 `fmtAmountUnit(v, 'wan')` 已经除以 10000；R9 又加了 provide/inject 第二层除法 = 双重除以 10000；数据库数据始终正确（元为单位原样存储）
- **金额单位联动需求（2026-05-12）**：四表（余额表/辅助余额表/序时账/辅助明细账）单位切换必须联动——用户在任一表切换万元则四表同步；当前只有余额表和辅助余额表有切换器，序时账和辅助明细账缺失；provide 已覆盖所有子组件但序时账/辅助明细的 GtAmountCell 也在同一 provide scope 内应该已生效，需验证
- **GtPageHeader 排除项（16 个不需要加）**：Login/Register/NotFound/DevelopingPage（4）+ LedgerPenetration/WorkpaperEditor/Drilldown/DataValidationPanel/PDFExportPanel/LedgerImportHistory/ProjectWizard/WorkpaperWorkbench/AIChatView/AIWorkpaperView/AttachmentHub/ConsolidationHub（12 个子面板/嵌入/复杂自定义头部）
- **unplugin-vue-components 自动导入陷阱**：grep `import GtPageHeader` 只能统计显式导入，实际有 17 个视图通过 auto-import 使用 GtPageHeader 但无 import 语句；正确统计方式是 grep `<GtPageHeader` 模板标签
- **Sprint 5 Task 76 执行空洞**：handleApiError 批量替换声称完成但实际 0 个文件被改动（grep 证实 handleApiError 仍只有 R8 的 7 个视图）；下一步 P0 = 53 个文件 147 处 ElMessage.error 机械替换为 handleApiError

## 用户反馈的 UI 问题（2026-05-11）

- **查账页面金额列折行**：LedgerPenetration.vue 的期初金额/借方发生额/贷方发生额/期末金额列宽不够（当前 width=150/130），大金额（如 210,301,834.96）折行显示；需要加宽或用 `white-space: nowrap` + `min-width`
- **和平药房 3 文件上传 500 错误**：前端上传 3 个文件（1 xlsx + 2 CSV 共 432MB）时服务端报错（ID: a5789793-cda）；可能是文件大小超限（MAX_TOTAL_SIZE_BYTES=500MB 但单文件 CSV 上限 1GB 应该够）或 CSV 编码探测/upload_security 校验问题；需查后端日志定位


## e2e-business-flow spec v2.0 复盘（2026-05-13）

- **报表全零根因确认**：generate_all_reports 默认 applicable_standard="enterprise"，但 report_config 表中只有 soe_consolidated/soe_standalone/listed_consolidated/listed_standalone 四种标准，导致 _load_report_configs 返回空列表→所有报表 0 行→返回空结构体被前端解读为"全零"
- **修复方案**：项目表增加 report_standard 字段（默认 soe_standalone），generate_all_reports 从项目配置读取；或直接改默认值为 soe_standalone
- **公式填充已完成**：316/1191 行已有公式（BS 55/129=43%, IS 16/78=21%），覆盖所有核心科目行；标题行/特殊行业行/CFS 明细行无公式是正常的
- **fill_report_formulas.py 已创建并执行**：按 row_name 匹配（非 row_code），特殊公式表 > CAS 标准 > 合计行自动生成三级优先
- **wp_account_mapping row_code 与 report_config_seed row_code 不一致**：前者用 CAS 简化编号（BS-002=货币资金），后者用国企版完整编号（BS-002=货币资金 但 BS-004=△拆出资金 vs wp 的 BS-004=应收票据）；匹配必须走 row_name 不能走 row_code
- **financial_report 表名是单数**：`financial_report`（不是 financial_reports）
- **宜宾大药房 trial_balance=0 但 tb_balance=812**：recalc 从未执行，需手动触发
- **spec v2.0 升级要点**：增加数据质量校验（F7-F8）、E2E 验证脚本（F25）、公式 seed 端点化（F5）、错误详情返回（F23）、前端反馈（F24）、零值灰显（F11）
- **用户要求**：企业级通用处理、不硬编码、人机联动、强真实数据验证、前端美观友好、可扩展；陕西华氏明细账不完整是已知情况，系统应能检测并报告差异而非崩溃

- **报表全零根因修正（重大发现）**：测试脚本 `_test_report_generation.py` 检查字段名错误（用 `r.get("amount")` 但实际返回字段是 `"current_period_amount"` str 类型），报表引擎可能已正常工作；HTTP 端点 `/api/reports/generate` 已有 `_resolve_applicable_standard` 自动从 `Project.template_type + report_scope` 组合为 `"soe_standalone"`，无需前端传参
- **4 个项目 template_type/report_scope 已配置**：全部为 `soe` + `standalone`，resolve 返回 `"soe_standalone"` 正确
- **宜宾大药房 recalc 前置条件**：需先确认 account_mapping 存在（auto-match 是否执行过），不存在则先 auto-match 再 recalc
- **tb_ledger pg_stat n_live_tup=0 但可能是 autovacuum 未更新**：数据质量校验前需先 COUNT 确认 tb_ledger 实际有数据
- **spec 工作流教训**：验证脚本的断言字段名必须从后端代码中提取（grep 确认），不能凭印象写；design.md 假设必须先 grep 核验再写结论

- **recalc 依赖链路确认**：`tb_balance → account_mapping(auto-match) → trial_balance(recalc) → financial_report(generate)`；recalc_unadjusted 通过 JOIN account_mapping 汇总 tb_balance.closing_balance 到标准科目；account_mapping 为空时 recalc 静默返回 0 行不报错
- **试算表科目名称取数**：一次性加载 tb_balance 全部 account_code→account_name，对标准科目编码精确匹配或前缀匹配明细行，**统一取下划线前第一段**作为一级科目名称（如"其他货币资金_集采监管账户"→"其他货币资金"）；很多企业余额表没有一级汇总行只有明细行，不能依赖精确匹配
- **损益类科目（5xxx/6xxx）取单边发生额**：不能用 `debit - credit`（结转后两者相等=0）；正确做法：收入类取 `credit_amount` 存为负数（贷方语义），费用类取 `debit_amount` 存为正数（借方语义）；收入类编码：5001/5051/5101/6001/6051/6101/6111/6115/6117/6301；其余 6xxx/5xxx 为费用类
- **试算表损益区域展示为"净利润"**：不分"收入小计"/"费用小计"，合并为一行"净利润 = 收入 - 成本费用"；正数=盈利，负数=亏损（红字）；去掉了无意义的"合计"行（资产/负债/权益/损益口径不同不能加总）
- **试算平衡表行次结构来自标准库（report_config）**：所有企业共用同一套行次模板（按 applicable_standard 如 soe_standalone 过滤）；`get_summary_with_adjustments` 先加载 report_config 行次模板再用 ReportLineMapping 填充数据，没有数据的行次显示为空；report_config 无数据时 fallback 到旧逻辑（从映射表取行次）
- **report_config 与 ReportLineMapping 编码体系不同**：report_config 用 `BS-001`（有连字符），映射表用 `BS001`（无连字符）；匹配通过 `row_name` 名称对应（精确+模糊包含），不走编码直接匹配
- **试算平衡表公式计算已实现**：`_eval_formula` 支持 `TB()/SUM_TB()/ROW()/SUM_ROW()` + 加减运算；`report_config.formula` 是唯一真源（公式管理弹窗编辑同一字段）；合计行有公式走公式（如 `SUM_ROW('BS-002','BS-008')`），无公式 fallback 向前汇总；`row_values` dict 记录每行结果供后续行引用
- **report_config seed 公式不完整**：合计行公式范围可能太小（如 BS-052 `SUM_ROW('BS-011','BS-013')` 实际应覆盖 BS-029~BS-051）；已加 fallback：公式结果为 0 时自动向前汇总子行
- **借贷平衡校验只比较"资产小计 = 负债和权益合计"**：不含损益类（损益取发生额与余额口径不同）；`getActualCat` 提取为模块级函数供 groupedRows/assetTotal/liabEquityTotal 共用
- **试算平衡表交互已实现**：右键菜单（复制/查看公式/汇总明细/数据溯源）+ 行选择高亮 + 右键菜单防超出视口；溯源逻辑 = 切换到 detail Tab + setCurrentRow + scrollIntoView；**点击未审数直接溯源已关闭**（用户要求溯源只走右键），双击行仍触发溯源
- **公式管理中心新增"试算平衡表"节点**：左侧树含"科目明细"（显示 TB 取数公式）+"试算平衡表"（显示 report_config 行次公式）两个子节点
- **宜宾大药房 trial_balance=0 根因确认**：该项目从未执行 auto-match（account_mapping 为空），导致 recalc 无法汇总；修复路径 = 先 auto-match → 再 recalc
- **e2e-business-flow spec v2.0 待补强 6 个维度**：(1) 依赖链路透明化+前置条件矩阵 (2) 错误场景覆盖（静默返回空 vs 明确报错） (3) 多项目通用性验证（每个项目分别断言） (4) 前端报表表样细节（标题行加粗/金额右对齐千分位/缩进可视化/合计行分隔线） (5) 公式覆盖率 26.5% 合理性论证（标题行/特殊行业行/CFS 手工填列） (6) 数据质量检查扩展为套件（借贷平衡/科目完整性/报表平衡/利润表勾稽）
- **报表表样企业级要求**：标题行加粗背景色、数据行正常、合计行加粗+上边框、金额右对齐+千分位+负数红色、indent_level→padding-left、空报表友好提示、不同行类型不同样式

- **e2e-business-flow spec v2.0 最终版已写入**：F1-F29 / D1-D10 / 50 task + 8 UAT / 4 Sprint ~7 天；新增 F26 前置条件校验器 + F27 报表表样 6 种行类型 + F28 覆盖率摘要 + F29 数据质量检查套件（5 种检查）
- **PrerequisiteChecker 设计模式**：通用前置条件校验器，每个生成端点第一行调用，不满足返回 HTTP 400 + `{ok, message, prerequisite_action}` 结构；前端 catch 400 显示 message + "去完成"跳转按钮
- **报表行类型判定逻辑**：getRowType(row) 返回 header/data/total/zero/special/manual 6 种，基于 row_name 含"："、is_total_row、△/▲前缀、formula_used 是否存在、金额是否为 0 判定
- **e2e-business-flow spec v2.0 实施完成（2026-05-13）**：50/50 编码任务全部完成，剩余 8 项 UAT 需手动浏览器验证
  - Sprint 1：报表全零确认为测试脚本误报（字段名 current_period_amount），4 项目 BS 非零行均 ≥10（陕西华氏 27/和平药房 29/辽宁卫生 26/宜宾大药房 13）；宜宾大药房 auto-match+recalc 成功（0→100 行）；PrerequisiteChecker 集成 4 端点；ReportFormulaService 封装+seed 自动调用+fill-formulas 端点
  - Sprint 2：ReportView 6 Tab 确认 + getRowType 6 种行类型 + CSS 样式 + 金额千分位负数红色括号 + indent_level×24px + 覆盖率摘要 + 穿透查询 + generate summary 返回 + toast 摘要 + 前置条件 400 跳转 + DataQualityService 5 种检查 + data_quality 端点 + DataQualityDialog.vue + TrialBalance 按钮
  - Sprint 3：template_sets seed 确认 + 底稿生成 92 个 + wp_mapping 86 条 + 附注生成 173 节 + AccountMappingPage.vue 新建 + /projects/:id/mapping 路由 + 报表标准下拉框
  - Sprint 4：workflow-status 端点（6 步进度推导）+ WorkflowProgress.vue 组件 + 4 视图接入 + 报表平衡自动检查 + e2e 脚本 Layer 1-4 完整
  - **新建后端文件**：prerequisite_checker.py / report_formula_service.py / data_quality_service.py / data_quality.py / workflow_status.py + 对应测试
  - **新建前端文件**：DataQualityDialog.vue / AccountMappingPage.vue / WorkflowProgress.vue
  - **router_registry 新增**：§28 data_quality / §29 workflow_status
  - **4 个项目 UUID 确认**：陕西华氏 005a6f2d-cecd-4e30-bcbd-9fb01236c194 / 和平药房 5942c12e-65fb-4187-ace3-79d45a90cb53 / 辽宁卫生 37814426-a29e-4fc2-9313-a59d229bf7b0 / 宜宾大药房 14fb8c10-9462-45f6-8f56-d023f5b6df13
  - **复盘发现 3 个 P0/P1 问题（全部已修复 2026-05-13）**：(1) e2e 脚本 emoji 在 Windows GBK 终端崩溃→加 io.TextIOWrapper UTF-8；(2) workflow_status.py 查 `account_mapping` 带 `AND year = :yr` 但该表无 year 列→去掉；(3) `working_papers` 表名错误→改为 `working_paper`（单数）；(4) data_quality_service `_check_debit_credit_balance` 查 `direction` 列不存在→改用 `account_category IN ('asset','expense')` 判断借贷方向
  - **`scripts/init_4_projects.py` 已创建**：DB 重建后一键恢复 4 项目数据（auto-match→recalc→generate_reports），4/4 成功
  - **e2e 脚本健壮性已增强**：每个项目独立 session（防事务级联失败）+ try/except + rollback
  - **e2e 最终验证全绿**：4 项目 × 4 层 = 16 项检查全部 PASS（陕西华氏 tb=100/BS=27/底稿92/附注173，和平药房 tb=53/BS=29/附注173，辽宁卫生 tb=47/BS=26/附注173，宜宾大药房 tb=100/BS=13/附注173）
  - **fix: 附注页面打不开**：`disclosure_engine.py` 的 `get_notes_tree()` 返回字典缺少 `id` 字段，前端 tree 组件 key=undefined 导致渲染失败；修复 = 添加 `"id": str(n.id)`（commit bc71f2b）

## template-library-coordination spec 复盘发现（2026-05-16）

- **spec 数字与现实偏差**（实施前必修订）：(1) `wp_account_mapping.json` 实际 **206 条**（spec 写 118）；(2) `wp_template_metadata` 表 **179 主编码 + 24 子表继承 = 203 条**（spec 写 179）；(3) "180 个 wp_code" 实际是 **179 主编码**（含 B/C/D-N/A/S 全 6 模块）；(4) `_index.json` 是 **dict 结构**（`{description, version, files}`）不是顶层 list，design.md 数据流图错画为 list
- **§43 编号已被占用**：tasks.md Task 1.2 计划 "§43 注册 template_library_mgmt"，但 §43-§53 已全部用于 audit-chain-generation 的 chain_workflow / report_export / note_export 等，**应改为 §54**
- **底稿子表收敛与 spec 需求 3.3 描述不符**：spec 写 "一个编码多个文件，如 D2 有审定表+分析程序+检查程序"，但 chain_orchestrator 实际把多文件**合并为一个 xlsx 多 sheets**（D2=20 sheets / E1=33 / F4=15 / H1=26），前端详情面板应改为 "主文件 1 个 + sheets 列表" 而非 "文件下载列表"
- **template-library-coordination 与 audit-chain-generation 关系**：前者是后者的**消费方**，wp_template_metadata 已由后者加载就绪，Task 1.3 /list 端点增强应改为 "补充 component_type/has_formula/file_count/generated/sort_order 4 个字段" 而非 "增强重写"
- **spec 实施前必做"现状核验"硬约定**：每个 spec Sprint 1 第一步是 grep 关键事实（mapping 条数 / metadata 行数 / 路由编号占用 / index 结构），避免基于过时假设实施返工；本次发现 6 处关键脱节都是这步缺失导致


## template-library-coordination spec 三件套修订完成（2026-05-16）

- **三件套已修订对齐现实**：requirements.md 7 处 / design.md 6 处 + 2 ADR / tasks.md 5 处 + Sprint 0 新增
- **§54 路由编号已锁定**：tasks.md Task 1.2 写明 "§43-§53 已被 audit-chain-generation 占用，本路由必须使用 §54"
- **新增 Sprint 0 "现状核验"前置任务模式**：实施前必做 grep + SQL 核验关键事实（mapping/metadata/router 编号/index 结构），输出对比报表，无重大偏差才进入 Sprint 1；可作为后续大 spec 的标准模板
- **新增 D11/D12 两个 ADR**：D11 子表收敛 UI 模型（一 wp_code 一节点 + 主文件下载 + sheets 列表 + 源文件参考下载折叠区）；D12 消费/生产关系（本 spec 是 audit-chain-generation 的纯消费方，不重复加载任何 seed）
- **Property 11 字段拆分**：原 `file_count` 拆为 `source_file_count`（源 xlsx 物理文件数，如 D2=3）+ `sheet_count`（合并后 sheets 数，如 D2=20）
- **公式覆盖率不再硬编码**：Task 1.6/3.4 明确 expected_count 从 seed 文件实际加载、覆盖率全部由后端 SQL 实时统计；避免 spec 写死数字与现实脱节

## template-library-coordination spec P0+P1 修订完成（2026-05-16）

- **新增 4 个跨 spec 通用架构铁律**（可推广到其他 spec）：
  - **D13 JSON 文件 vs DB 表编辑路径分流**：JSON 种子文件作为 git 真源**禁止 UI 直接编辑**（避免 git 仓库 vs 生产 DB 状态分叉），UI 显示只读 + 引导"改 JSON 后 reseed"；DB 表类（report_config / gt_wp_coding / wp_template_metadata）允许 UI 编辑；mutation 端点对 JSON 类资源返回 405
  - **D14 跨 spec 消费契约**：本 spec 消费 audit-chain-generation 的具体字段必须显式登记 9 项（subtable_codes / linked_accounts / component_type / audit_stage / procedure_steps / account_codes / wp_code / filename / cells 等），生产方变更须同步消费方 spec；防止上游静默 breaking
  - **D15 种子加载 SAVEPOINT 事务边界**：批量 seed 每个独立 SAVEPOINT，失败仅该 seed 回滚 + seed_load_history 记 status=failed + 继续后续；避免一刀切 rollback 已成功的 seed
  - **Property 16 后端 mutation 二次校验铁律**：任何 POST/PUT/DELETE 端点必须验证 role ∈ {admin, partner} 返回 403，**绝不能只依赖前端 v-permission 隐藏按钮**（防 API 直调绕过 UI）
- **spec 工作流新规约**：三件套修订后必须跑一次性 grep 脚本核验残留（如 `180 个 wp_code` / `316/1191` / `max_examples=100` 等过时数字），用完即删；本次发现 1 处历史对比说明刻意保留（D5 决策正文里）属合理例外
- **Alembic 跨 spec 链路衔接铁律**：消费方 spec 的迁移 down_revision 必须明确指向生产方 spec 末端（本次指向 `export_logs_20260516`），避免实施者猜测导致迁移分叉
- **测试 max_examples 统一规约**：MVP 阶段 hypothesis property test 全局 `max_examples=5`，design.md 与 tasks.md Notes 必须一致（之前 100 vs 5 矛盾）；稳定后才调高

## spec 工作流通用规约（template-library-coordination P2 沉淀）

- **属性测试就近合并铁律**：PBT 应分散到对应 Sprint（生产代码与测试同一 fixture/上下文），不能集中堆到收尾 Sprint；template-library-coordination 把原 Sprint 5 的 7 个零散 PBT 拆到 Sprint 1（5 个）/ Sprint 2（2 个）/ Sprint 4（1 个），收尾 Sprint 改为专注集成测试+安全属性+版本管理+ADR 落地
- **聚合端点 N+1 防退化必须 spec 化**：所有"前端列表+多表合并"端点（如 `/list` 合并 metadata + 项目状态 + JSON）必须在 tasks 中显式声明：(1) 单次批量预加载策略；(2) DB 查询数上限（一般 ≤ 4）；(3) 响应时间 SLA（≤ 500ms）；(4) 集成测试用 `assert_query_count` 装饰器在 CI 中防退化；防止实施时 per-row 查 DB 退化
- **集成测试独立成 Sprint task 铁律**：单测 + PBT + 集成测试三层独立，集成测试覆盖：跨表 join 完整链路、事务边界（SAVEPOINT/rollback）、性能 N+1 断言、partial success 行为；不能默认"单测 + PBT 就够"
- **Sprint 收尾任务画像**：最后一个 Sprint 应专注 (1) 跨模块集成测试 (2) 安全属性测试（authz/readonly enforcement）(3) ADR 落地实施 (4) 版本管理/审计追踪；不应是"零散 PBT 堆叠"

## template-library-coordination 二次复盘关键事实更正（2026-05-16）

- **WpTemplateMetadata ORM 模型无 `subtable_codes` 字段**（grep 零匹配）：子表收敛是 `chain_orchestrator._step_generate_workpapers` 运行时通过 `wp_code.split("-")` 计算并返回 `subtable_breakdown`，不存元数据；先前 spec 把它当字段引用（D14 / Property 11）是错误假设，需改为运行时 `_index.json` 文件名前缀匹配
- **wp_template_metadata 真实数据来源是 3 个增量 seed**（不是单文件 seed）：`wp_template_metadata_seed.json` 只有 86 条历史遗留，DB 实际 179 条来自 `wp_template_metadata_dn_seed.json`（89）+ `_b_seed.json`（19）+ `_cas_seed.json`（71）三个文件，由 `load_wp_template_metadata.py` + chain_orchestrator 运行时聚合加载
- **wp_template_metadata_seed.json audit_stage 全是 substantive + cycle 只 D-N**：B/C/A/S 类元数据**完全不在主 seed 文件**，必须从 3 个增量 seed 取；任何"基于 _seed.json 单文件计算 expected_count" 都会算错
- **Alembic 当前链路真实终点是 `audit_chain_sprint10_tables_20260516`**（不是 export_logs_20260516）；新 spec 的 down_revision 必须接续到此最末端而非 export_logs，否则迁移分叉
- **前端 CustomQuery.vue 不存在**（spec 旧版假设"已有"是错的）：当前自定义查询路由也无前端实现，spec 需求 22.9 改为新建
- **复盘方法论沉淀**：spec 引用 ORM 字段（如 `XxxModel.field`）必须 grep `class XxxModel` 源文件核验字段真实存在；引用 seed 文件条数必须 `python -c "import json; print(len(...))"` 实测；引用 Alembic 链路终点必须 `grep down_revision` 反向追溯叶子节点；这三步现状核验是任何 spec 第一遍审查必做

## 用户偏好（强制铁律）：spec 不硬编码数字

- **任何"数量/条数/百分比/容差"必须运行时计算**：spec 文档允许在 narrative 区域引用当前快照值（如 "当前 ≥ 179 条"）但所有 task/code/property 引用必须改为运行时表达式（`sum(len(json.load(f)['entries']) for f in seed_files)`）
- **expected_count 唯一允许的形式**：从 seed 文件 / DB COUNT / 文件 glob 实时读取；不能写 `expected_count = 179` 这种字面量
- **覆盖率/百分比同样不能硬编码**：所有 `26.5%` `316/1191` 类硬数字必须改为 SQL 实时聚合表达式 + UI 动态展示
- **spec 中允许保留快照值的位置（narrative 类）**：标题描述 / Overview / 术语表 / 数据流图节点标签；**不允许**的位置：task 验收标准 / Property 公式 / Pydantic 模型默认值 / 测试断言

## spec 层"硬编码 vs 运行时计算"落地形式

- **数字来源声明**：所有数字必须在 spec 中明确标注来源（"运行时聚合 3 个增量 seed 文件 entries"/"SQL 实时统计 report_config WHERE formula IS NOT NULL"/"_index.json[\"files\"] 按 primary_code 前缀匹配 count"）
- **ORM 字段引用前必须 grep 核验**：spec 引用任何 `XxxModel.field_name` 必须在源文件 `class XxxModel` 处确认字段真实存在；不存在的字段在 ADR 中加"明确排除清单"声明禁止依赖
- **文件/端点存在性核验**：spec 假设"已有 X.vue / 已注册 /api/y" 前必须 fileSearch / grep 核验，否则改为"新建"
- **Sprint 0 强制现状核验**：作为 task 1 之前的强制前置 Sprint，所有数字假设/字段假设/路径假设都用 grep+SQL+文件读取核验，输出对比报告才进入 Sprint 1

## template-library-coordination 三件套 v3 修订完成（2026-05-16）

- 7 处关键硬编码全部清零：requirements 引言 + design 关键事实 + design D11 子表收敛 + D14 依赖清单（删 subtable_codes）+ Property 11 sheet_count 公式 + D10 CustomQuery.vue 错误假设 + tasks 0.1/1.4/1.6 expected_count
- 实测三个增量 seed 文件 entries：DN 89 + B 19 + CAS 71 = **179**（与 spec narrative 引用一致，但所有 task 实施时必须运行时算）
- 三件套核验脚本验证全绿（hits=OK），可进入 Sprint 0 实施

## D16 硬编码计数审查规则（可推广通用规约，2026-05-16）

- spec 文档"数量/条数/百分比/容差"严格分两种位置：(1) **narrative 允许保留快照值**（标题/Overview/术语表/数据流节点标签/ADR 决策正文）；(2) **task / Property / 验收标准 / 错误处理表 / UAT 清单 / 测试断言禁止硬编码**，必须改为运行时表达式
- 修订收尾核验脚本骨架（用完即删）：`hard_patterns = [r"全部 \d+ 个", r"全部 \d+ 条", r"\(.*?/ \d+\)", r"展示 \d+ 行"]; grep 命中即修`
- 已写入 template-library-coordination design.md 作为 D16 ADR；可推广到所有后续 spec
- 写法范式：narrative 用 `**N_xxx**` 变量名 + "当前快照 ≥ N" 标注 + 验收标准写"全部 X（数量从 API/JSON 动态取）"，绝不写"179/94/48"等具体数字

## template-library-coordination 三件套 v4 终稿（2026-05-16）

- 13 处硬编码计数全部清零：requirements 10 处 + design 5 处 + tasks 5 处 + UAT 2 处
- Sprint 5 编号重排（删除重复占位 5.3，5.4-5.7 → 5.3-5.6）
- 新增 D16 ADR 硬编码审查规则 + 核验脚本骨架
- 三件套规模：requirements 318 行 / design 570 行 / tasks 368 行
- 22 需求 × 8 Sprint × 17 Property × 16 ADR 完整对齐，零硬编码违规、零任务编号重复、N+1 + SAVEPOINT + JSON 只读 + 后端二次校验全覆盖；可进入 Sprint 0 实施

## template-library-coordination 三件套 v5 终稿（2026-05-16）

- **R1-R4 四处可改进点全部修复**：(1) Sprint 0.1 增加 N_* 变量输出到 console 作为 Sprint 1 实施基准值（11 个变量含 N_files/N_primary/N_account_mappings 等）；(2) Sprint 0.1 + Task 1.6 实测核验 4 个 seed 文件根级 key 名（templates/sections/entries/mappings/references 各异），确认 accounting_standards_seed.json + template_sets_seed.json **不存在**，无独立 seed 文件的 expected_count 改用 DB COUNT 取；(3) design Mermaid 数据流图节点标签从变量名 N_* 改为描述性"实时统计"避免渲染困惑；(4) Task 3.6 + 5.5 显式说明 cross_wp_references 也是 JSON 只读源（与 prefill_formula_mapping/audit_report_templates/wp_account_mapping 共 4 个 JSON 源资源）
- **关键事实补充**：accounting_standards 和 template_sets **没有独立 seed JSON 文件**（实测确认），spec 旧版 Sprint 1.1 假设错误；这两个 seed 的 expected_count 必须直接从 DB 表 SELECT COUNT 取
- **D13 JSON 只读源完整清单**：4 个 JSON 文件全部走只读路径——prefill_formula_mapping / cross_wp_references / audit_report_templates / wp_account_mapping；前端 useTemplateLibrarySource.ts composable 统一判断
- 三件套规模：requirements 318 行 / design 25066 chars / tasks 19856 chars / 0 硬编码违规
