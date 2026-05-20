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
- **死代码立即删除**：不留 DEPRECATED/保留作 fallback 等注释，否则每次复盘都会重复提议（2026-05-10 明确）
- **复杂重构先做 spec 三件套**：体系化、精准、可回滚；避免"每次单独尝试都跑大样本"；要求"全部改完再跑一次测试"（2026-05-10）
- **避免折中方案**：要"根本解决"不要"折中"；partial index 类改动收益有限不算根本方案
- **spec 不硬编码数字（强制铁律）**：spec 文档"数量/条数/百分比/容差"narrative 区域允许快照值（如 "当前 ≥ 179 条"），但 task / Property / 验收标准 / 测试断言必须改为运行时表达式（`sum(len(json.load(f)['entries']) for f in seed_files)` / SQL COUNT / 文件 glob 实时读取）；禁止 `expected_count = 179` / `26.5%` / `316/1191` 字面量；详见 dev-history.md "D16 硬编码计数审查规则"
- **spec 文档碎裂时必须整文件 fsWrite 重写，禁止继续 strReplace 修补**（多次增量编辑可致章节倒置/表格切碎/文本拼接错乱，2026-05-18 D 销售循环 requirements.md 实战）
- **spec tasks 总数核验铁律**：必须 grep `- [x]/- [ ]` 按 section 计数，禁止信摘要表自报值（D 销售循环摘要写 38 实际 53）
- **三件套一致性核查按维度矩阵**：F-N 编号 / 数量 / ADR 编号连续性 / 工时 / UAT 项数 / 依赖 spec / 数据基线（如 cross_wp_ref ≥ 39 条）逐维 grep 多文件比对；ADR 用次级编号（如 D14a）会破坏排序应统一连续编号；过时数字引用保留"反向修正注解"作历史溯源不要简单删除
- **Sprint 0 实测脚本铁律**：spec 三件套实施前 Sprint 0 必须跑实测脚本输出 N_* 基准变量（如 `N_prefill_total/N_d_audited_entries/N_cwr_d_count`），禁止凭 README 估算值写 design/tasks；D 销售循环实战经历早期估算 54→v1.3 修正 39→Sprint 0 实测 40 三次偏差，最严重时 F1 修复方式根本性误读（entry 内容已对齐而错位的是 wp_code 标签，不是 formula）
- **Sprint 0 基线 grep 必须全仓库**：不能只看单文件；如修复 wp_code 错位应 grep 全部含该 wp_code 的 JSON/py 文件（D 销售循环实战：prefill_formula_mapping 修了但 wp_template_metadata_dn_seed 漏了，E2E 才暴露）
- **UAT 清单每项必须有对应 task 编号**：无编码 task 的 UAT 项在 Sprint 规划时补 task 或标"依赖外部 spec"；D 销售循环 #20/#21 partial 即因 D14 无独立 task
- **spec 编号区间起草时必须 grep 现有 max**：如 cross_wp_references 新增区间应基于 `max(ref_id)` 而非凭记忆写死（D 销售循环写 CW-108~CW-147 但 E1 已占到 CW-135）
- 底稿编码体系：致同 2025 修订版 D/F/K/N 循环，映射文件 `backend/data/wp_account_mapping.json`（206 条 v2025-R5）
- **F2 存货两级 prefill 链路**：TB/AUX → F2-2 明细汇总表（76R，prefill 扩展重点）→ F2-1 审定表（487 cross_sheet 公式自动计算）；与 D2-1 直接从 TB 取数不同，F2 的 prefill 目标是中间 sheet 而非审定表本身
- **`_should_skip_historical_sheet` 需扩展**：F2 模板含 `G2-*-删除` / `G2-*-移至` / `(示例)` 三种新历史遗留模式，当前 regex 只匹配"修订前/(原)"不覆盖；F spec Sprint 1 第一个 task 应扩展此函数
- **F 循环 spec 完成（2026-05-19）**：F2_IPO_CODES = F2-61~F2-72（12 条）/ B51-4 触发；通用 `_ensure_ipo_loaded(prefix)` + 向后兼容包装 `_ensure_d4_ipo_loaded`（剥离 prefix 字段保持原 schema），D spec 18/18 IPO 回归全绿
- **F2 两级 prefill 链路实测落地**：F2-2 明细汇总表 20 cells（=AUX/=TB 中间 sheet，禁止 =WP 防循环引用）→ F2-1 审定表 487 cross_sheet 公式自动算；F-cycle 总 cells 45→109（+64，超 60 目标）
- **F-F11 计价测试三层抽样**：weighted_average / fifo / standard_cost 三方法，按金额分层 high/mid/low（high_threshold=100k 默认）；20 笔均匀分配 6/6/8
- **F-F12 跌价 ECL stub**：成本与 NRV 孰低 + 库龄三级（<12 low / 12-23 medium / ≥24 high）+ 重要性提示阈值
- **prerequisite-status 路由按 wp_code 前缀 routing**：E1 / D\d → D_CYCLE_PREREQUISITES / F\d → F_CYCLE_PREREQUISITES（B23-3/C4/B51-4），WorkpaperEditor v-if `isFCycle` 已联动
- **WorkpaperAuditNav resolveProcedureSheetKey**：按 wp_code 前缀路由 procedure_status sheetKey（F2→f2a, D4→d4a, D2→d2a, E1→e1a 默认），32 项 F2A 程序通过 useProcedureStatus 加载
- **通用化重构铁律**：抽取 `_ensure_ipo_loaded(prefix)` 后，原 `_ensure_d4_ipo_loaded` 必须保留为薄包装并剥离新增字段（如 `prefix`）以维持原 schema（`added_codes`/`skipped_existing`/`errors`），否则破坏既有断言（D spec 18 IPO 测试一发命中此陷阱）
- **prefill 一次性脚本幂等保护**：批量追加 `prefill_formula_mapping.json` 时用 `(wp_code, sheet)` 作 key 检查 existing 跳过；多次跑同脚本不会重复追加（F-F10 实战）
- **vue-tsc element-plus d.ts 告警是 pre-existing**：`GlobalComponents` Index signature / `__VLS_Slots` 类警告与本仓库无关，不要被吓到；判断本次改动是否新增 TS 错误需 grep 改动文件路径过滤
- **UAT 分级铁律**：标 ✓ pass 必须"功能在用户层可用"，stub/占位实现一律标 ⚠ stub，部分实现标 ⚠ partial；不要一律 ✓ 误导上线决策（F spec UAT 复盘教训：#16~#19 应分别标 stub/partial 而非 ✓）
- **程序化 UAT 验收方法**（H spec 实战 2026-05-19）：写一次性脚本 `_uat_check.py` 跑量化指标（sheet 数 / cells / cross_wp_ref 数 / VR 规则数 / 4-arg AUX 校验等）+ 复用已有 pytest/vitest 断言 + 代码锚定核验（router prefix / composable 字典 / 路由路径），按 19 项验收一次输出全部 ✓/⚠/✗ 分级；脚本用完即删；比手动 UAT 快 10x，但仅适用于"可量化"指标（不涉及业务流程交互的项需补真实人工验收）
- **测试覆盖伪绿警示**：schema/枚举/字段存在性测试 ≠ 业务正确性测试；prefill cell 测试必须 grep 真实 sheet 名（openpyxl）+ 真实 tb_aux 辅助账维度后才能定义 cell 映射，否则跑起来全 0（F-F10 教训：14 处占位 AUX 名）
- **prefill 占位辅助账名禁止臆造**：`=AUX('1403','主仓库','期末余额')` / `=AUX('1403','库龄_1年内','期末余额')` 等字符串必须 `SELECT DISTINCT aux_value FROM tb_aux WHERE account_code LIKE '14%'` 实测后再写
- **API 数据返回必须配套写回**：F-F11/F-F12 类「自动抽样/AI 分析」按钮，后端返回结果后必须 PATCH workpaper.parsed_data 写回 sheet，仅 toast 显示笔数 = 用户点了等于啥都没发生
- **工时压缩比 > 5× 必须诚实标注**：明确哪些任务做的是 stub（F spec 实测 ~0.7 天 vs 估 12.5 天 = 18×，但 F-F11/F-F12/F-F13 多数为 stub 或不完整实现，不应一律标 ✓）
- **新增 router 默认接入 RBAC**：仅 `Depends(get_current_user)` 不够，必须校验用户对 project_id 的访问权限（F-F11/F-F12 路由当前漏校验，本仓库 wp_* 路由横向问题）
- **F spec 待办 followup 5 项 P0/P1**（已识别未实施）：①prefill 65 cells 真实辅助账实测重写 ②F2 sheet 真名 openpyxl 提取 ③F-F11/F-F12 写回联动 ④F2 IPO trigger e2e 测试（参 D spec monkeypatch）⑤UAT 重新分级 stub/partial
- **F spec 已修复（2026-05-19 P0/P1/P3 修复轮）**：backend 174→206 / frontend 40→42 / UAT 重分级 16 ✓ + 1 partial + 2 stub；剩余 stub/partial 转后续 spec：O-LLM-Integration（#7/#17）+ F-Procedure-Seed（#18）
- **PBT 设计铁律：避免恒真断言（tautology）**：测 `(p and X<C) or (not p and X>=C)` 当 `p := X<C` 时是恒真断言，毫无业务价值；正确做法用业务不变量（恒等点/边界内/边界外/对称性/单调性）+ parametrize 显式边界用例覆盖（F-F4 PBT-P4 教训）
- **prefill =AUX 4-arg 强制约定**：`(account_code, aux_type, aux_code, column)`，3-arg 调用时 prefill_engine._resolve_aux_formula 直接 return None；测试必须 grep `=AUX(` 校验逗号数 == 3（即 4 args）；其他 prefill 公式语法见 backend/data/prefill_formula_mapping.json 已有 entries 抽样核对
- **API 写回联动模式**：后端 endpoint 加 `apply_to_sheet: str | None`，写入 `working_paper.parsed_data.{namespace}[sheet]={method/applied_at/data}`；前端弹窗加 `targetSheet` prop + 「采纳并写回」按钮 + emit `applied` 事件，由父组件再 emit `workpaper:saved` 触发刷新
- **复盘"形式 vs 实质"原则**：spec 完成后必须做"复盘 → 找出形式合规但本质未到位 → 列 P0/P1/P2 修复轮 → 修完再标 ✓"循环；F spec 首版 19/19 ✓ 是过度乐观，复盘后真实评级 16 ✓ + 3 限定（含 P0 真实性 / 测试伪绿 / RBAC 漏洞）
- **审计循环代号映射**（致同 2025 实测）：A=报表/调整/重要性 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=（预留） / L=筹资 / M=股东权益 / N=税费 / S=专项程序；用户口语"M 固定资产"实际是 H 循环
- **B/C 类底稿架构决策（2026-05-20 确认）**：B/C 是定性判断类（控制有效/无效、风险高/中/低），不需要独立循环 spec；已有 bcas_cycle_validation_rules.json 25 条 VR + usePrerequisiteStatus 联动（C2~C15→各循环前置横幅）+ CWR 26 条（source 18 + target 8）；无 prefill（无科目余额填充）/ 无独立计算引擎 / 无 sheet 分组 composable；后续如需 B/C 控制测试工作流可单独立 spec，但不属于"循环底稿未完成"
- **跨底稿联动缺口已补充（2026-05-20）**：CW-382~CW-400 共 19 条新增；B15 重要性水平→10 循环抽样范围（materiality_linkage）+ C 控制测试结论→9 循环实质性程序范围（control_test_linkage）；cross_wp_references 总计 400 条；B/C→各循环方向联动缺口已消除
- **H 循环 Sprint 0 关键发现（2026-05-19）**：①0 历史遗留（H 模板比 D/F 干净）②同名 sheet 多版本（H1-12 折旧 3 版 / H3-1+H7-1 成本/公允双模式 / H8-8 折旧 2 版）→ 不能简单去重 ③两模式切换需新 scenario 类型（成本 vs 公允价值，非 IPO）④H8↔H9 租赁两表强联动（类似 F0↔F2 反向回填）⑤折旧/减值多分支（不含/含/多次减值）需 prefill 指引 ⑥prefill 极度欠覆盖（仅 12 entries / 56 cells，目标 ≥ 100 cells）
- **H 循环关键架构决策（requirements.md 落地 2026-05-19）**：①归一化策略升级 — 同 wp_code 多版本必须保留（按"sheet 名+括号修饰词+文件来源"三元组归一化）②新增 `MEASUREMENT_MODEL_FILTER`（cost / fair_value）独立于 SCENARIO_TO_FILE_FILTER ③H9→H8 cross-ref 反向回填（租赁两表）④4 种折旧方法计算引擎（直线/双倍余额/年数总和/工作量）作为 H-F11 独立 endpoint ⑤致同 H 模板未提供 IPO 应对类专属文件，H-F14 降级为占位 + 文档化机制
- **审计循环代号映射纠正**：用户口语"M 固定资产"实际是 H 循环；致同 2025 中 M=权益（M1~M10）/ H=固定资产（H0~H10）/ I=无形资产+商誉（I1~I6）/ J=职工薪酬+股份支付（J1~J3）；spec 起草前必须用 wp_account_mapping.json 核验 cycle 字母
- **审计循环前置底稿真实编号（实测 backend/wp_templates/B+C/）**：D 循环→C2 / E 循环→C3 / F 循环→C4 / 投资 G→C5 / 固定资产 H→**C6** / 在建工程→**C7** / 无形 I→C8 / 研发→C9 / 薪酬 J→C10 / 管理→C11 / 税金→C12 / 债务 L→C13 / 租赁 H8/H9→**C14** / 关联方→C15；B23 类**没有按业务循环拆分**（仅 B23-15 信息处理 + B23-XX-5 职责分离通用模板）；B51 类**仅有 -3 货币资金 + -5 收入**两份业务专项，H/F/L 等无对应 B51-X 资产舞弊专项；spec 起草必须用此真实编号映射，不要凭印象写"B23-3 采购循环业务控制"等臆造
- **多版本 sheet 实测铁律（H 循环教训）**：Excel 同 workbook 内不允许同名 sheet → 模板里"H1-12 折旧 3 版 / H3-1 双模式"等同 wp_code 多版本，sheet 名后缀已带括号修饰词区分（如"折旧测算表（含减值）H1-12"），openpyxl 读出来本就是不同 sheet；归一化时含括号修饰词的 normalized key 也不同，**不会被误去重**；H 实测同文件内多版本误去重数=0，全部 28 个去重都是跨文件合法去重（底稿目录/GT_Custom 等）；真实问题是前端按 wp_code 路由会撞多个 sheet → 归 sheet 分支选择器（H-F3）解决，而非合并去重
- **spec requirements.md 标准 8 章结构（F spec 成熟版定义，H spec 体检发现）**：①变更记录 + 依赖矩阵 ②为什么做（业务痛点 7+ 类 / 技术根因 / 边界）③范围边界（必做/排除清单）④功能需求（按 EARS 范式 WHEN/IF/WHILE/THE...SHALL，可机械对照测试）⑤非功能需求（性能/兼容性回归白名单/可观测性）⑥测试矩阵（单测文件清单 + PBT + 集成测试 + UAT）⑦成功判据汇总（量化指标）+ 术语表 + Sprint 0 偏差段 ⑧附录 A 基线变量；UAT 表必带优先级 P0/P1/P2 列 + 上线门槛说明
- **spec 起草后必做"对照成熟版体检"**：新 spec 起草完成后应对照已上线成熟 spec（如 F spec v1.0+P0/P1 修复轮）逐条 diff，找出结构性缺失（依赖矩阵/EARS 范式/测试矩阵/术语表）+ 内容质量（Sprint 0 偏差段/痛点细化）；首版信息密度约为成熟版 60% 是常见现象，需补齐到 ≥ 90% 再启动 design.md
- **EARS 范式改写优先级**：requirements 起草后 EARS 化 7 项核心需求即可（>50% 覆盖核心架构改动），其余 8 项延后到 design 阶段补完，避免起草过早全 EARS 化导致大量重复修改
- **Sprint 0 偏差归零原则**（spec requirements 必备段落）：实测后必填 §三·B 表格列出"起草前假设 vs Sprint 0 实测 vs 偏差影响 vs 修正方案"6 项以上对比；典型偏差类型：①模板历史遗留模式数 ②同名多版本 sheet 数 ③IPO 应对类底稿存在性 ④B/C 前置底稿真实编号 ⑤prefill 覆盖度 ⑥业务专属 sheet 数（如监盘/资产组）
- **UAT P 列优先级标注**：F spec 缺失（仅备注 P0 #1/#2/#3），H spec v1.2 升级为表格 P 列；P0 项数 = 关键架构改动数 × 2~3（H 8 项 vs F 3 项是因 H 引入了 measurement_model + wp_code 多 sheet 路由 + 跨表 VR 三个新架构）
- **Alembic 迁移必须独立成 task**：H-F2 是首个需要 DB schema 变更的循环 spec（project 表加 measurement_model 列），迁移和前端逻辑不能混在同一 task（迁移失败会阻断整个 Sprint）；拆为 task-a（迁移+回滚验证）+ task-b（前端逻辑）
- **Sprint 0.X 前置实测必须独立段落**：不能混在 Sprint 2 某个 task 里（如 2.22），应在 Sprint 1 和 Sprint 2 之间独立执行（0.5 天），含 aux_type/aux_code SQL 实测 + openpyxl 表头提取；如果 tb_aux_balance 无 160x 数据则 H-F10 降级为仅 =TB/=LEDGER（目标从 ≥ 110 降为 ≥ 70 cells）
- **task 标 [x] 铁律**：只有跑过 pytest/vitest 且全绿才能标 [x]；"假设复用已有逻辑 = 0 改动"不等于验证通过（H task 1.1 教训：chain_orchestrator 可能没注册 H 循环到 merge 流程）
- **PBT 策略选择**：用 `st.floats` + 后转 Decimal 验证（hypothesis 对 float shrinking 成熟 + 生成快 10x），不要直接用 `st.decimals`（慢且 shrinking 不成熟）
- **PBT 已注册 vs 未注册 prefix 必须分开测**（H spec PBT-P7 教训）：`_ensure_ipo_loaded` 对未注册 prefix 返回 `errors=[{'code':'*','error':'unsupported prefix: XXX'}]` 而非 `errors=[]`；用 `st.text().filter(lambda s: s.upper() not in REGISTERED)` 拆出独立 property 验证降级行为，避免主 property 被未注册 case 污染
- **跨 spec 引擎复用模式**（H→I 实战）：H-F11 折旧引擎 4 方法（直线/双倍余额/年数总和/工作量）→ I-F2 摊销引擎 2 方法（直线/工作量）通过 import `_calc_straight_line` + `_calc_units_of_production` + `_quantize` 复用，新建 wp_i_amortization.py 仅 ~300 行 + 双 router（router_i1 + router_i4）共享 _execute(_run_amortization, _maybe_apply_amortization_to_workpaper) 入口；规模子集语义对齐（4 方法 ⊃ 2 方法）；写回 namespace 用 `parsed_data.amortization_calcs[sheet]` 与 H 的 `depreciation_calcs[sheet]` 对称但区分；51 H 折旧测试 0 回归
- **跨 spec 重新过滤 ref_id 区间铁律**（H→I 实战教训）：cross_wp_ref 测试用 `ref_id ≥ N` 过滤"new entries"会被后续 spec 的新条目污染（H test 过滤 211+ 抓到 I 的 243+；F test 过滤 176+ 抓到 H/I 的 211+/243+）；正确做法 = 双重过滤 `(N_lo ≤ ref_id ≤ N_hi) AND cycle_membership(source_wp 或 target wp_code 以 X 开头)`，每个 spec 测试明确闭区间
- **UAT ⚠ partial 标注准确性铁律**（I 复盘教训）：UAT partial 标注必须用代码锚定的真实原因（grep wp_code/科目对应 + SQL 实测），不能凭印象；I-cycle UAT #14 标"5601 无 aux 数据"但 5601 是 I6 研发费用科目（不是 I1 摊销，I1-10/I1-11 用 1701/1702）→ 真实原因是降级目标 ≥ 8 给摊销分配偏少（10 vs 12 原始）；建议落地"UAT 标注核验脚本"扫描 wp_code/科目对应关系
- **分项目标 vs 总目标必须分别 verify**（I 复盘教训）：spec task "目标分布"细分项（如 I1-10/I1-11 ≥ 12 cells）和"总目标"（≥ 60/40 cells）必须分别列、分别检查；UAT 表只看总数会掩盖分项缺口（I 总 77 cells 达 ≥ 70 但摊销分项 10 < 12 被掩盖）；UAT 程序化脚本应同时输出"原始目标"和"降级目标"两套结果
- **跨 spec 引擎复用必须加 term 参数**（H→I 实战教训）：H-F11 折旧引擎复用到 I-F2 摊销引擎时，schedule 字段名带源 spec 烙印（H 的 `depreciation` 漏到 I 的 `amortization`），需在写回时手动改名 + 前端兼容两个字段；后续跨 spec 引擎复用应在引擎层加 `term: Literal['depreciation','amortization']` 参数统一术语，避免命名脱钩
- **optional PBT task 跳过必须注明**（I 复盘教训）：spec 起草时把 PBT 列为"分散到对应 Sprint 实施"但实施时全部 `[ ]*` 跳过，形成"显式列出但隐式跳过"的偏差；跳过决策（实施/等价 case 覆盖/性价比不足）须在 spec 末尾"已知缺口"段落留一句话注明；或 run_all_tasks 把 optional 全部归到独立 Sprint 末尾批次集中处理
- **CGU 商誉减值分摊"剩余分摊到资产"下半段易遗漏**（I 复盘教训）：`_allocate_goodwill_impairment` 通常只算 `(goodwill_writedown, other_assets_writedown_total)` 汇总值，但 CAS 8 / IFRS 36 真正难点是"剩余按账面价值比例分摊到 CGU 内各资产，且不低于各资产可收回金额"——需输入"CGU 内资产清单 + 各账面价值"输出"各资产分摊额"；G/I/J 商誉相关 spec 应明确"分摊一半 vs 完整分摊"的范围标注
- **optional PBT tasks 标 `[ ]*` 但实际已实现的情况**（H spec 教训）：spec 起草时把 PBT 散在各 Sprint 标 `[ ]*` 可选，但实施 task 2.10/2.11 等同时把对应 PBT-P4/P5 实现并通过；执行 run-all 时这些 optional task 状态不会自动 [x]，最终需人工核对 `pytest --collect-only` 与 task 编号对照确认


## 环境配置

- Python 3.12（.venv），Docker 28.3.3，PG 16 ~188 表，Redis 6379
- 后端 9980，前端 3030，vLLM 8100，Univer（纯前端 Core Preset）
- 测试用户：admin/admin123（role=admin）
- 后端路由 204 / 服务 327 / 模型 56 / 前端视图 96 / 组件 283 / composables 52 / stores 9
- 后端 Worker 10 个 / Alembic 迁移 59 版本 / 测试文件 293 个
- 前端 services 30 / utils 23 / common 组件 28 / apiPaths.ts 1558 行
- 底稿模板 473 个 / 精细化规则 347 个 / 模板索引 363 条
- cross_wp_references 400 条 / prefill_formula_mapping 1035 cells / validation_rules VR-D4-01~04 + VR-H1-01~03 + VR-H8-01 + VR-I1-01 + VR-I3-01 + VR-I6-01 + VR-G7-01 + VR-G11-01 + VR-G1-01 + VR-G14-01 + VR-J1-01~03 + VR-L8-01 + VR-L1-01 + VR-L3-01 + VR-M6-01 + VR-M2-01 + VR-N2-01 + VR-N5-01
- git 分支：master + feature/ledger-import-view-refactor + feature/e2e-business-flow（当前 HEAD）

## 活跃待办（精简版，详情见 #dev-history）

### P0 已完成（可归档）
- ~~F6 AJE 创建 500（MissingGreenlet）~~：已修复，`deps.py` 已用 `begin_nested()` SAVEPOINT
- ~~workpaper-e1-cash-optimization~~：91/91 task 全部完成 ✅
- ~~v3-linkage-stale-propagation~~：23/23 全部完成 ✅
- ~~v3-r10-linkage-and-tokens~~：68/68 全部完成 ✅
- ~~v3-r10-editor-resilience~~：48/48 全部完成 ✅

### P0 进行中
- ~~**workpaper-d-sales-cycle**~~：**53/53 completed + UAT 20/21 ✓ pass ✅ 达到上线门槛**（2026-05-19 UAT 验收 + #20 修复；#21 D14 风险规则 LLM stub 属 P2 打磨）
- ~~**workpaper-f-purchase-inventory**~~：**44/44 completed + UAT 19/19 ✓ pass ✅ 达到上线门槛**（2026-05-19 spec 三件套全量执行 + UAT 验收一次过；F2_IPO_CODES 12 条 / cross_wp_ref 175→210 / prefill F-cycle 45→109 cells / 174 backend tests + 40 frontend tests + 18 D regression 全绿）
- ~~**workpaper-h-fixed-assets-cycle**~~：**全部 required + optional tasks completed + UAT 16✓+2 partial+1 stub ✅ 达到上线门槛**（2026-05-19）；P0 关键项 8/8 全 ✓ pass；388 tests green（263 backend + 118 frontend + 7 PBT）；产出：cross_wp_ref 9→41 条 H-cycle（CW-211~CW-242）/ prefill H-cycle 56→148 cells（+92，降级目标 ≥70 达成）/ H9→H8 反向回填（CROSS_REF_UPDATED 事件链）/ usePrerequisiteStatus H 路由（C6+C7+C14 条件逻辑）/ wp_h_depreciation.py 4 方法折旧引擎 + DepreciationCalcDialog / wp_h_impairment.py DCF stub + AssetImpairmentDialog / resolveProcedureSheetKey H 循环路由 / _IPO_CONFIG['H1'] 占位注册；UAT 降级项：#16 H1-14 减值 ⚠ partial（8 cell vs 12 原始目标，1603 无辅助账数据）/ #8 #18 ⚠ stub（LLM 待 wp_ai_service 升级）
- ~~**workpaper-i-intangible-assets-cycle**~~：**全部 required + Sprint 4 复盘修复 11/11 + 二轮复盘 P2 修复 3 项 completed + UAT v2 14✓+1 partial+0 fail ✅ 达到上线门槛**（2026-05-19 Sprint 4 + 二轮复盘）；P0 关键项 5/5 全 ✓ pass；397 backend 测试全绿（PBT-P4/P5 32 + cross_spec_ref 4 + term 参数 6 + amortization 字段修复 3 + RE-I1/I3 stub flag/summary interp 4）+ 40 frontend vitest + vue-tsc 零错误；二轮复盘 P2 落地（RE-I1 is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动 / RE-I2 9 条 I→报表 CWR severity info→warning blocking 6 + warning 23 + info 0 健康 / RE-I3 summary 完整变量插值 CGU/占比/现金流/折现率/Gordon g / RE-I5 已存在 unit test 撤回 false positive）；TD-I11/I12/I13/I14 二轮修复落地标记
- **二轮复盘 P2 修复落地模式**（I spec 2026-05-19 实战）：①stub 标志由 config 驱动（添加 `WP_AI_SERVICE_ENABLED: bool = False` to backend/app/core/config.py + `is_llm_stub_flag = not settings.WP_AI_SERVICE_ENABLED` + monkeypatch 测试两态）②CWR severity 重审用一次性脚本（grep N 条 ref_id → 升级 → 删除脚本）③summary 文案 f-string 模板补 5+ 变量（避免审计日志信息量 0）④"已存在覆盖"撤回前必须 grep 验证（避免误判建议浪费时间）
- **配置驱动型 stub 测试模式**：用 `monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", False/True)` 切换两态，验证 endpoint 响应字段 `is_llm_stub` 同步切换 + summary 文案条件分支正确（无配置时附"待 wp_ai_service 接入"提示，配置后提示自动消失）
- **跨 spec 引擎复用 term 参数标准模式**（H→I 落地 2026-05-19 Sprint 4 task 4.8）：H-F11 折旧引擎 `_calc_*(*, term: Literal['depreciation','amortization'] = 'depreciation')` 默认值保持向后兼容（H 测试 0 修改），I-F2 摊销引擎调用时显式传 `term='amortization'`；schedule 输出字段名按 term 切换（depreciation→amortization）；写回时直接读取 `s["amortization"]` 不需手动改名兼容；前端 ScheduleItem 接口字段简化为单 `amortization: string` 不再两可（删 scheduleAmount 兜底）；后续跨 spec 引擎复用（如 I→J 商誉摊销）应直接采用此模式
- **跨 spec ref_id 区间过滤铁律实战落地**（Sprint 4 task 4.7）：单边 `int(...) >= N` 过滤会被后续 spec 新条目污染（H test 抓到 I 条目 / F test 抓到 H/I 条目）；正确做法 = 双重过滤 `(N_lo <= ref_id <= N_hi) AND cycle_membership(source_wp.startswith(L) OR target_wp.startswith(L))`；test_cross_spec_ref_id_ranges.py 含 SingleSidedFilterDetection 自动扫描全仓 cross_wp_refs tests 检测违规；闭区间已对齐：F 176-210 / H 211-242 / I 243-266；D 区间 (1-175) 是历史累积段含跨循环条目（cycle membership 违规率 61%）不做严格 membership 检查
- **PBT 跳过决策"显式列出"铁律**（Sprint 4 task 4.9）：optional task 跳过必须在 spec 末尾"已知缺口"段落留一句话决策（实施/等价 case 覆盖/性价比不足）；I spec 落地：P1 normalize_idempotent 跳过（H-PBT-P1 等价覆盖）/ P2 historical_filter_regression 跳过（test_i_merge_dedup 22 测试覆盖）/ P3 ref_id_unique 跳过（test_cross_spec_ref_id_ranges 覆盖）/ P4 vr_i_triangle_formula 实施（200 examples + 9 boundary）/ P5 sheet_group_completeness 实施（200 examples + 18 explicit cases）
- **VR 三角勾稽 PBT 设计模板**（Sprint 4 task 4.9 落地）：避免恒真断言用 drift ∈ [-2,2] 区间生成 closing = expected + drift，业务不变量 `passes ↔ |drift| < tolerance`；boundary 用 parametrize 显式覆盖临界点（drift=0/±0.99/±1.0/±1.5）；金额用 `st.floats(0, 1e9)` + 后转 Decimal 避免极端值异常
- **复盘核验"先实测再修复"铁律**（I Sprint 4 task 4.4/4.5/4.6 实战 2026-05-19）：复盘怀疑某项不达标时必须先 grep 现状 + 跑核验脚本实测，再决定是否写补丁脚本；I3-2/I2-6/I1-10+I1-11 prefill 复盘前以为各 4/0/10 cells，实测发现 Sprint 2 实施时已 9/4/14 cells 全部超原始目标，UAT 表过时未更新形成 partial 假象；复盘 task 实际只需"核验 + 更新 UAT 标注"无需重新追加 prefill
- **UAT 数量指标语义铁律 — 总数 vs 新增段**（I Sprint 4 task 4.3 UAT v2 实战）：spec UAT "≥ N 条"类指标默认是"总条目数"（含基线 + 新增），脚本不应误用闭区间过滤导致基线不计；I-cycle UAT #10 ≥ 25 条 — 第一版 v2 脚本误把 CW-243~266 区间过滤得 24 < 25 ✗ fail，修正为"涉 I 总数 29"（基线 5 + 新增 24）→ ✓ pass；闭区间过滤仅用于"新增段"度量，绝对不能替代总数核验
- **sub-agent overload 直接执行降级**（2026-05-19 实战）：sub-agent 反复 high load 时不要重试浪费 turn，直接在主 agent 执行 task（保持进度），完成后再批量委托后续；批量委托建议每批 4-5 task，单 task 不值得委托
- **二轮复盘"形式 vs 实质"自查铁律**（I spec 2026-05-19 第二轮复盘）：Sprint 4 P0/P1/P2 修复完成后必须再做"形式合规但本质未到位"自查；典型隐患：①stub 标志硬编码（如 `is_llm_stub=True` 写死，未来真实接入忘记切换）②CWR severity 偏松（info 占比过高）③LLM summary 文案模板写死（无变量插值）④隐式覆盖（PBT 跳过的"等价覆盖"未形式化证明）⑤ADR 与实施偏差（design 写 A 实施做 B）⑥工时估时压缩比 > 5× 未做归因（复用 task 应按 30% 估时）⑦CWR ref_id 起编 max+1 流程做对但工具未沉淀；I 二轮发现 RE-I1~I10 共 10 项（4 P2 + 6 P3），P2 合计 0.22 天可消除上线门槛后的最后隐患
- **stub 标志铁律**：API 返回字段如 `is_llm_stub` / `is_mock` 等不能写死 True/False，应由 `settings.WP_AI_SERVICE_ENABLED` 类配置驱动；未配置才 True，配置后自动 False；否则 LLM 真实接入后字段持续撒谎
- **CWR severity 三级语义铁律**：blocking = 阻断签字 / warning = stale 标记 + 提示用户 / info = 仅披露引用不影响流程；新增 CWR 时 info 占比应 < 25%，超过说明可能漏报关键变更
- **CWR blocking 比例由业务性质决定**（N 二轮复盘 2026-05-20 实证）：N 循环 blocking 占比 42% (5/12) 显著高于 M 循环 7% (1/15)，因 N→报表/N→税金内部联动错误均阻断签字（报表勾稽强约束），而 M 权益变动多为披露性质；不应套用统一 blocking 阈值，按"目标错误是否阻断签字"判定 severity
- **workpaper-g-investment-cycle**：**全部 required + optional PBT tasks completed ✅ 达到上线门槛**（2026-05-19 全量执行）；307 backend tests + 83 frontend vitest + 210 D/F/H/I 回归全绿；产出：3 router（wp_g_fair_value / wp_g_ecl / wp_g_classification）/ 4 VR 规则 + consistency_gate 集成 / cross_wp_ref 8→34 条（CW-267~292）/ prefill 74→134 cells（+60，降级目标 ≥60 达成）/ 3 前端弹窗（FairValueTestDialog / ECLCalcDialog / ClassificationCheckDialog）/ 12 类 sheet 分组 composable + WorkpaperEditor 路由 / G7 三种核算方式 per-investment 显隐 / G 循环前置横幅 C5 + 审计导航图 sheetKey 路由（G1→g1a / G4→g4a / G7→g7a / G11→g11a）/ 6 PBT property 全部实现（P1 normalize idempotent / P2 historical filter / P3 ref_id unique / P4 VR triangle 4 rules × 200 examples + 9 boundary / P5 sheet group completeness / P6 ECL monotonicity）
- **三循环执行进度（H/I/G 2026-05-19）**：H ✅ 完成 + UAT 上线 / I ✅ 完成 + UAT 上线 / G ✅ 完成（全量执行，待 UAT 验收）
- **H Sprint 0.X 降级结论（已确认落地）**：tb_aux_balance 1601/1602 无辅助账数据（仅 1604 在建工程有 aux_type='项目名称'）→ H-F10 降级为仅 =TB/=LEDGER 公式（不含 =AUX for 1601/1602），prefill 目标降为 ≥ 70 cells（实际达成 92 new cells）；I-F10 同步降级
- **G Sprint 0.X 0x.1 实测结论（已确认落地 2026-05-19）**：tb_aux_balance G 类账户 110%/150% 全 0 行；151%（长投 1511）有 27 distinct (aux_type, aux_code)（aux_type='客户' 26 个 + '减值方式' aux_code=NULL）；152%（其他权益工具 1521-1527）有 tb_balance 余额但无辅助账；153%（其他金融资产 1531.02）有 12 行 distinct（'客户'+'项目名称'）→ **G-F10 部分降级**：G7（1511）保留 =AUX 真实链路 + G6（1531.02）保留 1-2 个 =AUX 示例；G1/G4/G8/G11/G13/G14 全部 =TB/=WP；总目标 ≥ 80 → ≥ 60 cells（介于全 H 模式 ≥50 与原 ≥80 之间）；details 见 `.kiro/specs/workpaper-g-investment-cycle/design.md` ADR-G4 实测结果段落
- **VR 汇总类规则校验时机铁律**（G/I spec 共同教训）：当 VR 规则涉及"A = B1+B2+...+Bn 汇总"时，A 先保存而 B 全部未保存 → 必须 skip 不 blocking；正确约束 = "A 和至少 1 个 B 都已保存时才触发 blocking"；适用于 VR-G11-01（G11=G1+G4+G6+G7+G8）/ VR-G14-01（G14=G4+G6）/ VR-I6-01（I6=费用化+资本化）
- **e2e-business-flow**：50/58 completed（86%）
- **template-library-coordination**：63/64 completed（差 1 个）
- **workpaper-m-equity-cycle**：**全部 24 required tasks completed + UAT 10/10 pass（P0 5/5 全 ✓）✅ 达到上线门槛**（2026-05-20 全量执行）；233 M-cycle backend tests + 71 frontend vitest + 2066 prior-cycle 回归全绿；产出：cross_wp_ref 8→25 条 M-cycle（CW-353~369，17 新增）/ prefill M-cycle 52→87 cells（+35，M2 =AUX 9 cells + M4/M5/M6/M9/M10 =TB/=WP/=PREV）/ m_cycle_validation_rules.json 2 VR（VR-M6-01 blocking 未分配利润勾稽 + VR-M2-01 warning 实收资本）+ check_m_cycle_triangle_reconciliation 注入 consistency_gate / wp_m_equity_movement.py 6 列变动汇总 + apply_to_sheet + is_llm_stub config 驱动 + EquityMovementDialog（已 wired 到 WorkpaperEditor M6 toolbar）/ useMEquityCycleSheetGroups 8 类（索引/程序表/审定表/明细表/变动分析/检查表/附注+调整/其他）/ usePrerequisiteStatus M_CYCLE_PREREQUISITES=[]（无独立 C 类，A 类覆盖）/ resolveProcedureSheetKey M2→m2a/M4→m4a/M5→m5a/M6→m6a/M9→m9a/M10→m10a / _IPO_CONFIG['M2'] 占位注册（codes=[]）/ 4 PBT property 全部实现（P1 normalize 100 + P2 VR-M6-01 triangle 200+9 + P3 sheet group 200 + P4 ref_id unique 50）；实际工时 ~2.8 天（估计 5.5 天，压缩比 0.51×，第 8 个循环复用红利）
- **workpaper-n-tax-cycle**：**全部 24 required tasks completed + UAT 10/10 pass（P0 5/5 全 ✓）✅ 达到上线门槛**（2026-05-20 全量执行）；211 N-cycle backend tests + 90 frontend vitest + 65 prior-cycle 回归全绿；产出：cross_wp_ref 14→26 条 N-cycle（CW-370~381，12 新增）/ prefill N-cycle 28→64 cells（+36，N2 =AUX 4-arg aux_type='税率' + N1/N3/N4/N5 =TB）/ n_cycle_validation_rules.json 2 VR（VR-N2-01 blocking 应交税费期末勾稽 + VR-N5-01 warning 所得税费用）+ check_n_cycle_triangle_reconciliation 注入 consistency_gate / wp_n_income_tax_calc.py 税率调节表+递延调整+apply_to_sheet+is_llm_stub config 驱动 + IncomeTaxCalcDialog（已 wired 到 WorkpaperEditor N5 toolbar）/ useNTaxCycleSheetGroups 8 类（索引/程序表/审定表/明细表/税费计算/递延所得税/附注+调整/其他）/ usePrerequisiteStatus N_CYCLE_PREREQUISITES=[C12] / resolveProcedureSheetKey N1→n1a/N2→n2a/N3→n3a/N4→n4a/N5→n5a / _IPO_CONFIG['N2'] 占位注册（codes=[]）/ 4 PBT property 全部实现（P1 normalize 100 + P2 VR-N2-01 triangle 200+9 + P3 sheet group 200 + P4 ref_id unique 50）；Sprint 0.2 关键偏差：CWR 基线从 45 修正为 14（原与 dedup_sheets 混淆）；Sprint 0.X 降级：仅 N2(2221) 保留 =AUX，N1/N3/N4/N5 降级 =TB（1811/1812/6801 无辅助账数据）
- **全部 11 个审计循环 spec 100% 完成**（2026-05-20）：D(53) + E(91) + F(58) + G(55) + H(59) + I(62) + J(38) + K(38) + L(39) + M(28) + N(27) = **548/548 tasks 全部 [x]**（含 optional PBT + 文档 review）；cross_wp_ref 381 条 / prefill 1035 cells / VR 覆盖全循环 / PBT 全循环实现
- **workpaper-l-debt-cycle**：**全部 26 required tasks completed + UAT 15/15 ✓ pass + P0 6/6 全 ✓ ✅ 达到上线门槛**（2026-05-20 全量执行 + 复盘修复 3 项）；299 L-cycle backend tests + 63 frontend vitest（51 原有 + 12 新增 Dialog spec）+ 26 prior-cycle IPO 回归全绿；产出：cross_wp_ref 6→26 条 L-cycle（CW-333~352）/ prefill L-cycle 44→90 cells（+46，7 sheet 全覆盖）/ l_cycle_validation_rules.json 3 VR（VR-L8-01 blocking 利息汇总 + VR-L1-01 blocking 短期借款余额 + VR-L3-01 warning 长期借款重分类）+ check_l_cycle_triangle_reconciliation 注入 consistency_gate / wp_l_interest_calc.py 3 计息基准×3 复利频率 + InterestCalcDialog（已 wired 到 WorkpaperEditor L1/L3 toolbar）/ wp_l_bond_amortization.py 实际利率法+收敛性尾差调整+is_llm_stub config 驱动 + BondAmortizationDialog（已 wired 到 WorkpaperEditor L5 toolbar）/ useLDebtCycleSheetGroups 10 类（利息测算 priority=6 前置于检查表 priority=7）/ usePrerequisiteStatus L_CYCLE_PREREQUISITES=[C13] / WorkpaperEditor isLCycle 接入 / resolveProcedureSheetKey L1→l1a/L3→l3a/L5→l5a/L8→l8a / _IPO_CONFIG['L1'] 占位注册（codes=[]）/ 4 PBT property（P1 normalize 100 + P2 VR-L8-01 triangle 200+9 + P3 sheet group 200 + P4 ref_id unique 50）
- ~~**k-admin-cycle-post-review-fix**~~：**13/13 completed ✅**（2026-05-20 全量执行）；311 K backend + 510 vitest + 952 prior-cycle 全绿（无新增失败）；产出：WorkpaperEditor K8/K9/K11 toolbar 按钮 wired + ExpenseAnalysisDialog.spec.ts + ImpairmentSummaryDialog.spec.ts + test_k_prefill_ledger_detail.py 5 tests + test_k_vr_integration.py 2 tests + test_k11_schema_verification.py 9 tests + 函证辅助分组 priority=7.5 + 费用明细 regex 扩展 K(8|9|1[0-3]) + L spec max(ref_id) 防护注记 + wp_account_mapping tracking issue
- **"形式合规但用户不可达" UAT 标注铁律**（K spec 复盘 2026-05-19 教训）：UAT 标 ✓ 必须验证"用户在 UI 层实际能触达功能"，不能仅基于"组件文件存在 + 后端单测全绿"；前端 Dialog 类组件必须**同时**满足：①组件创建 ②WorkpaperEditor 集成（toolbar 按钮 / 右键菜单 / sheet 顶部入口）③vitest 覆盖 buildBody/formatRate/flag 映射；缺任一项应标 ⚠ partial 而非 ✓
- **sub-agent 高负载降级硬规则**（K spec 实战 2026-05-19）：sub-agent 报 "high load" 时**只重试 1 次**，第二次失败立刻在 main agent 直接执行（保持进度），不要反复重试浪费 turn；本次 task 1.6 + 2.1 各浪费 1 turn 才切换；建议固化为铁律
- **PBT 量化精度铁律**（K spec PBT-P5 实战 2026-05-19）：被测函数若内部 quantize 到 N 位小数（如 `_calc_yoy` rate_change 量化到 4 位），property 用极小 delta 会因量化损失等值，**严格单调性会失败**；正确做法 = ①property 改为非严格（`>=`）+ ②独立 property 在更"原始"字段（如 amount_change）验证严格单调；hypothesis 失败 case 形如 "rate_low=rate_high=-0.9983"
- **PBT 阈值边界严格不等式陷阱**（K spec PBT-P5 实战）：源码用 `if rate < -THRESHOLD` 严格不等式时，恰好 ±THRESHOLD 整点归 normal 而非 anomaly；parametrize 边界用例必须仔细对照源码不等号严格性（≤/< 区别）
- **WorkingPaper 模型 wp_code 在 WpIndex 上不在主表**（K spec task 3.1 实测教训）：`WorkingPaper` 只有 `wp_index_id` FK，不直接含 `wp_code`；按 wp_code 查询底稿必须 `select(WorkingPaper).join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id).where(WpIndex.wp_code == wp_code)`；K spec 跨循环减值汇总查询 H1/I3/G14/F2 时一发命中此陷阱（test 失败 6 个）
- **K 循环 sheet 分类优先级铁律**（K spec K-F2 落地）：10 类规则中"费用明细" priority=3 前置于"明细表" priority=4，专门匹配 `^明细表K[89]-`（K8-2/K9-2 销售/管理费用月度明细）；"往来款检查" priority=6 仅匹配 K1-/K3- 含业务关键词，但被前置的 priority 4/5 抢先（如"坏账准备明细表K1-3"含"明细表"→"明细表"）
- **正则 negative lookbehind 防误命中**（K spec K-F2 落地）：sheet 名 `会计提示` 的"计提"二字会被通用"计提"规则误命中检查表，用 `(?<!会)计提` 排除前缀为"会"的情况；前后端 regex 同款；同类陷阱：常见词的字符子串歧义（"会计提示" / "调节表" vs "调整分录"）
- **附注披露 5 种括号变体**（K spec task 2.1 实测）：`附注披露信息(上市公司)` / `附注披露信息(国企)` / `附注披露信息（上市公司）` / `附注披露信息（国企）` / `附注披露信息（国有企业）` 5 种全角/半角括号 + "国企"/"国有企业"双称呼组合，前端测试必须遍历 5 变体确保全覆盖
- **K Sprint 0 基线偏差修正**（K spec task 1.1 实测）：spec 起草时引用 N_k_dedup_sheets=114 / N_k_cross_file_dups=38，task 1.1 openpyxl 实测复核为 109 / 43；按"Sprint 0 偏差归零原则"同步修正三件套；43 跨文件去重分布：底稿目录 14×→13 / 附注披露(上市公司) 13×→12 / 附注披露(国企) 12×→11 / GT_Custom 8×→7 = 43；边缘 case：`附注披露信息(国有企业)` 1 份与 `附注披露信息(国企)` 归一化 key 不同不去重
- **wp_account_mapping.json K 循环编号与模板文件编号双轨并存**（2026-05-19 实测确认）：wp_account_mapping 按科目表顺序编号（K2=6601 销售费用 / K3=6603 财务费用 / K8=2241 其他应付款），模板文件按底稿业务分类编号（K2=其他流动资产 / K3=其他应付款 / K8=销售费用）；prefill_formula_mapping 中两套编号混用（K2 和 K8 都标注"销售费用审定表"）；**运行时以模板文件 sheet 名为准**（`审定表K8-1` = 销售费用），K spec 按模板文件编号写是正确的；wp_account_mapping 的 K 循环编号是历史遗留数据质量问题（仅 K0/K1/K6/K9 四个一致），后续需独立修正
- **K spec 首版结论修正**：K8=销售费用 / K9=管理费用 / K11=资产减值损失 按模板文件编号是正确的，不需要整体重写；requirements.md 段落重复已修复 + "已知数据问题"标注已加入；Sprint 0.X 实测已完成填充；信息密度 95%+；启动条件 7/9 满足（仅待 J+L 执行）
- **workpaper-k-admin-cycle**：**全部 required + optional PBT-P5 tasks completed + UAT 14/14 ✓ pass + 6/6 P0 全 ✓ ✅ 达到上线门槛**（2026-05-19 全量执行 + PBT-P5 补充）；361 K-cycle backend tests（274 + 87 PBT）+ ~67 K frontend vitest + 327 prior-cycle 回归全绿；产出：cross_wp_ref 17→37 条 K-cycle（CW-313~332）/ prefill K-cycle +40 cells（K8-2/K9-2 LEDGER_DETAIL 按月度 + K1-2/K3-2 AUX 4-arg + K5-2 含空格 + K8-4 PREV+TB）/ k_cycle_validation_rules.json 3 VR + check_k_cycle_triangle_reconciliation 注入 consistency_gate / wp_k_expense_analysis.py 3 维度（YoY/budget/industry）+ ExpenseAnalysisDialog / wp_k_impairment_summary.py 4 来源跨循环汇总（H1/I3/G14/F2）+ ImpairmentSummaryDialog / useKAdminCycleSheetGroups 10 类（费用明细 priority 3 前置于明细表 4，往来款检查 K1-/K3- 业务专项）/ usePrerequisiteStatus K_CYCLE_PREREQUISITES=[C11] / WorkpaperEditor isKCycle 接入（首个 spec 把 K nav 完整 wired 到 sheetNav facade）/ resolveProcedureSheetKey K1/K3/K5/K8/K9/K11 路由 + K10/K12/K13 fallback / _IPO_CONFIG['K8'] 占位注册（codes=[]）/ 5 PBT property（P1 normalize 100 + P2 VR-K8-01 triangle 200+9 + P3 sheet group 200 + P4 ref_id unique 50 + P5 YoY 单调性 200+200 + 9 阈值边界 + 50 防御性）+ 87 K PBT tests
- **PBT 量化精度铁律**（K spec PBT-P5 实战 2026-05-19）：被测函数若内部 quantize 到 N 位小数（如 `_calc_yoy` 的 rate_change 量化到 4 位），property 测试用极小 delta 会因量化损失等值，**严格单调性会失败**；正确做法 = ①property 改为非严格单调（`>= ` 而非 `>`，量化容忍）+ ②另写独立 property 在更"原始"的字段（如 amount_change，未量化或量化损失更小）上验证严格单调；hypothesis 失败 case 通常表现为"prior=589, current_low=1.0, delta=0.03 → rate_low=rate_high=-0.9983"
- **PBT 阈值边界严格不等式陷阱**（K spec PBT-P5 实战）：源码用 `if rate < -THRESHOLD` / `if rate > THRESHOLD` 严格不等式时，恰好 ±THRESHOLD 整点归 normal 而非 anomaly；parametrize 边界用例必须仔细对照源码不等号严格性（≤/< 区别），否则 expected_flag 写错会失败；典型场景：阈值 0.20 时 rate=-0.20 → normal，rate=-0.20001 → decrease_anomaly
- **K Sprint 0 基线偏差修正**（K spec task 1.1 实测）：spec 起草时引用 N_k_dedup_sheets=114 / N_k_cross_file_dups=38，task 1.1 openpyxl 实测复核为 109 / 43；按"Sprint 0 偏差归零原则"同步修正三件套（requirements/design/tasks）；实测分布：底稿目录 14×→13 dup / 附注披露(上市公司) 13×→12 / 附注披露(国企) 12×→11 / GT_Custom 8×→7 = 43 跨文件去重；边缘 case：`附注披露信息(国有企业)` 1 份与 `附注披露信息(国企)` 归一化 key 不同，不去重，需在测试中显式覆盖
- **K 循环附注披露 5 种括号变体**（K spec task 2.1 实测）：`附注披露信息(上市公司)` / `附注披露信息(国企)` / `附注披露信息（上市公司）` / `附注披露信息（国企）` / `附注披露信息（国有企业）` 5 种全角/半角括号 + "国企"/"国有企业"双称呼组合，全部归 `附注+调整` 类且 defaultHidden=true；前端测试必须遍历 5 变体确保全覆盖
- **WorkingPaper 模型 wp_code 在 WpIndex 上不在主表**（K spec task 3.1 实测教训）：`WorkingPaper` 模型只有 `wp_index_id` FK，不直接含 `wp_code`；查询特定 wp_code 的底稿必须 `select(WorkingPaper).join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id).where(WpIndex.wp_code == wp_code)`；K spec 跨循环减值汇总查询 H1/I3/G14/F2 时一发命中此陷阱（test 失败 6 个），后续涉及"按 wp_code 查 WorkingPaper"路由需注意
- **K 循环 sheet 分类优先级铁律**（K spec K-F2 落地）：10 类规则中"费用明细" priority=3 前置于"明细表" priority=4，专门匹配 `^明细表K[89]-`（K8-2/K9-2 销售/管理费用月度明细），其余 K1-2/K3-2/K5-2/K10-2 等仍归通用"明细表"；"往来款检查" priority=6 仅匹配 K1-/K3- 含业务关键词（检查/账龄/挂账/关联方/三阶段/未收回/大额/坏账/核销/转回/替代程序/信用减值），但被前置的 priority 4/5 抢先（如 `坏账准备明细表K1-3` 含"明细表"→"明细表"，`大额其他应收款情况分析表K1-5` 含"分析"→"分析程序"）
- **正则 negative lookbehind 防误命中**（K spec K-F2 落地）：sheet 名 `会计提示` 的"计提"二字会被通用"计提"规则误命中检查表，用 `(?<!会)计提` 排除前缀为"会"的情况；前端 TS regex `/(?<!会)计提/` + 后端 Python regex `r"(?<!会)计提"` 同款；同类陷阱场景：常见词的字符子串歧义（"会计提示" / "调节表" vs "调整分录"）
- **K-F4 cross_wp_ref 起编铁律**（K spec task 1.5 落地）：J spec 占至 CW-312，K spec 起编 CW-313 闭区间 CW-313~332；新增 20 条按 5 分组分布（K 内部 4 + K→跨循环来源 5 + K→报表 4 + K→附注 4 + K→其他循环 3）；severity 比例 4 blocking + 13 warning + 3 info（info 15% < 25%）；CW-316/329 source_sheet 用真实 sheet 名 `明细表 K5-2`（含空格），与 ADR-K3 实测一致；后续 spec（M/N）应基于运行时 max+1 起编（J+L 执行后才能确定）
- **K 循环 aux 实测结论**（2026-05-19）：6601 销售费用 aux_type='客户'（20+ distinct）/ 6602 管理费用 aux_type='区域2'+'客户' / 1221 其他应收款 aux_type='三方收款标识'+'代收代付类别' / 2241 其他应付款 aux_type='代收代付类别'；全部有数据不降级；但 aux_type 与业务预期（费用类别/往来对象）不匹配 → 费用明细表按模板月度结构用 =LEDGER_DETAIL，往来款明细表用 =AUX
- **真实 sheet 名末尾空格陷阱**（J 循环 Sprint 0 实测 2026-05-19）：openpyxl 读 J1 模板发现 `审定表J1-1 ` / `明细表J1-2 ` 末尾**带空格**，prefill cell 的 `sheet` 字段必须包含真实空格，否则 prefill_engine 按"明细表J1-2"（无空格）匹配会落空；spec 起草时 sheet 名核对必须用 `repr(name)` 输出避免肉眼漏看 — 与 F-F10 臆造 sheet 名同款教训
- **M7A 前导+末尾双空格**（M 循环 Sprint 0 实测 2026-05-20）：` 专项储备实质性程序表 M7A ` 前导空格+末尾空格（非仅末尾），`_normalize_sheet_name` 幂等性仍满足但 prefill sheet 字段必须用 `repr()` 确认完整空格模式
- **workpaper-j-payroll-cycle 执行进度**（2026-05-19）：**全部 required tasks completed ✅ 达到上线门槛**；Sprint 0 ✅ + Sprint 0.X ✅ + Sprint 1 ✅（117 tests）+ Sprint 2 ✅（2.1~2.12 全部完成，含 4 PBT）+ Sprint 3 ✅（3.1~3.4 + 3.6 完成，3.5 optional 跳过）；305 tests green（227 backend + 44 frontend + 34 D/F/H IPO 回归）；产出：wp_j_payroll_calc.py 薪酬计提引擎（12 月度序列 + 5 险一金 + apply_to_sheet）/ wp_j_share_payment.py Black-Scholes 引擎（含股息率 q + is_llm_stub config 驱动 + 费用摊销计划）/ PayrollCalcDialog + SharePaymentDialog 前端弹窗 / resolveProcedureSheetKey J1→j1a/J2→j2a/J3→j3a / _IPO_CONFIG['J1'] 占位注册（codes=[]）/ 4 PBT property 全部实现（P1 normalize idempotent / P2 VR-J1-01 triangle 200+9 / P3 sheet group completeness 200 / P4 ref_id unique 50）
- **L Sprint 0.X aux 实测结论（2026-05-20）**：tb_aux_balance L 类账户：200%（短期借款 2001）有 aux_type='借款性质'(3)+'金融机构'(34) = 37 distinct → L1-2 保留 =AUX；250%（长期借款 2501）0 行 → L3-2 降级 =TB；6603%（财务费用）有 aux_type='客户' 50+ distinct → L8-2 保留 =AUX；2502%（应付债券）0 行 → L5-2 维持 =TB；270%（长期应付款 2701）有 aux_type='成本中心'(28)+'客户'(1)+'项目名称'(1) = 32 distinct → L6-2 保留 =AUX；**不降级**，目标 ≥ 40 cells 保持
- **L Sprint 0 基线偏差修正（2026-05-20）**：spec 起草时假设 N_l_cross_file_dups=19 / N_l_dedup_sheets=80，openpyxl 实测为 20 / 79（附注披露变体多 1 类）；cross_wp_ref max_id 从起草时 292 更新为 332（J+K 已执行）；L 起编 CW-333（非原假设 CW-313）；L4-7/L4-8 各有 2 个付息方式变体（到期一次还本付息/分期付息到期一次还本）是合法业务多版本不影响去重
- **L 循环 sheet 分组特殊规则**（L-F2 落地）：利息测算 priority=6 前置于检查表 priority=7（"利息测算表L1-5"含"利息测算"→利息测算类，不被"检查表"误命中）；摊余成本归入检查表类（priority=7）；L4A 末尾空格 sheet 通过 `[A-Z]\d*A\s*$` 正则正确匹配总控台
- **`_should_skip_historical_sheet` 已扩展 `-删除` 通用后缀**（J spec task 1.1 落地）：新增 `s.endswith("-删除")` 规则覆盖 J 循环 5 个 sheet（原有 `G\d+.*删除` 仅覆盖 F 循环 G 编号模式）；D/F/H/I/G 回归 163 tests 全绿；"J1A-原版/L1A-原"确认不被误过滤
- **现有 prefill 数据科目错位风险**（J spec 复盘发现）：prefill_formula_mapping.json 中 J3 股份支付 entry account_codes=['2211']（应付职工薪酬）与 J3 业务实质（资本公积-股份支付 4001/4002）不符，应在 spec 实施时一并修正；起草 spec 时不能仅 grep 现有 prefill 复用账号，必须代码锚定核验科目对应（与 wp_account_mapping.json 比对）

### P1 待启动/待验收
- ~~**workpaper-f-purchase-inventory**~~：已上线 ✅（44/44 + UAT 19/19）
- ledger-import-view-refactor 239/243 completed（98.4%），剩 4 个运维/手动验证
- 性能测试（真实 PG + 大数据量 load_test.py，验证 6000 并发）
- 合并模块需找真实项目做业务测试（技术 85%，业务 60%）

### P2 长期
- PBC 清单 / 函证管理真实实现（后端当前 stub）
- 全局联动真正闭环（docs/GLOBAL_LINKAGE_ARCHITECTURE_PROPOSAL.md 方案已输出）
- 暗色模式 / 全局 Ctrl+K 搜索 / vitest 全量基建

## 关键引用指南

- 详细技术事实 / 端点速查 / PG schema 细节 → `#dev-history` grep 关键词
- 项目架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 规范 / Spec 工作流规约 → `#conventions`
- 各 spec 状态总览 → `.kiro/specs/INDEX.md`
