# 公式管理平台全面审计【草稿报告】
> 审计日期：2026-10-25。证据基线以 `779d8b43619c5946c198e11ca35b1ad9330c5dfa` 为主；调查期间 HEAD 因并发 S-cycle 工作前移，但专项报告确认核心公式路径无差异。本稿只综合既有只读调查，不改生产代码、配置、数据库业务数据、spec 或 Git。

## 0. 证据口径与限制
证据等级：**A（强）**＝生产源码与真实运行/真实 PostgreSQL 只读数据或直接探针相互印证；**B（中）**＝生产源码、路由注册、前端真实挂载和契约闭合；**C（辅助）**＝本次实际执行的自动化测试；**D（弱）**＝历史 spec/测试名称/注释声称，不能单独证明实现。主要证据为 `[G] .agents/tasks/formula-management-comprehensive-assessment-2026-10-25/00-ground-truth.md`、`[A] .../10-architecture.md`、`[C] .../12-global-conflict-edit-template.md`、`[D] .../13-lineage-governance-tests.md`。
**证据缺口：指定的 `11-coverage-matrix.md` 不存在，目录复核仅见 00、10、12、13 四份文件。** 因此本稿的覆盖矩阵是对 `[A][C][D]` 已证事实的合并，不代表缺失角度已独立复核；尤其不新增任何模块逐值结论。

## 1. 一句总判断与成熟度
**总判断：平台已经具备“较强的公式治理骨架 + 多个局部真闭环”，但核心执行、传播和溯源仍是多运行时且存在真实错值，所以现在不能称为平台灵魂，也不能称为贯穿全平台的单一公式中枢。** 综合成熟度 **54/100（约 2.7/5）**：定义与治理 14/20、执行正确性 7/20、跨模块闭环 10/20、模板与二次编辑 12/15、溯源与可观测 5/15、安全/测试可信度 6/10。【A：`[A] §一~七`；B/C：`[C] §1、§5~10`、`[D] §一~四`】

## 2. 一页式管理摘要
| 分类 | 管理结论 | 当前事实与边界 | 证据 |
|---|---|---|---|
| 已真正实现 | V199 全局/项目/模板定义治理、CAS、发布、订阅、三方冲突、pending adopt/keep/custom；相关 API 与主要 UI 已挂载 | 是真内核，不是空壳；但 live 六张 V199 业务表全为 0，尚无现场采用链 | A/B：`[C] §2~3、§8、§10` |
| 已真正实现 | Formula Push 四阶段后端闭环 | 真实 81 bindings、375 active rules；和平药房一次 run 写 139、unchanged 28、kept 4、skipped 92，并更新 28 章节/44 底稿；是当前最佳样板，不代表 81 条均完成真实 UAT | A/C：`[A] §五`、`[D] §4` |
| 部分实现 | report、cross_check、note、consol_note、wp 项目公式的编辑与执行 | report 存量存在 50/410 漂移且 49 条 false-fresh；note 多写方；wp 的全局继承不进入部分 runtime/Tier A；consol_note 仅 UAT 合并项目 | A/B：`[A] §一、§五`、`[C] §6、§9` |
| 部分实现 | 模板复用与“一处改、多项目应用” | 模板 CRUD/版本/订阅/冲突是真代码；模板→项目与模板→全局可用，全局→模板只给 hint；项目保存后的应用范围仅 3/7 域接线 | A/B：`[C] §5.1、§6、§10` |
| 未实现或高风险 | 单一执行器、统一错误语义、可信一键刷新、统一逐值溯源 | Runtime 真实 WP 公式 18/18 与严格求值器不一致；中央 API 可把错误/缺引用变 0；全局刷新多个域只走 runtime/marker；统一 lineage 有确定性断链 | A：`[A] §一~四、§六`、`[D] §2.3` |
| 未实现或高风险 | 可靠传播、完整回滚与不可抵赖审计 | settings 事件无 durable outbox；全局/模板无业务回滚；审计 helper 41 调用点缺并发锁；时间轴 3/5 数据源字段漂移后静默为空 | A/B：`[C] §7~8`、`[D] §3.5~3.6` |
| 用户当前可安全使用 | 受控查看/编辑、单项目预览、已验证 Formula Push、冲突 pending 的人工决策 | 必须先逐值预览并保留人工复核；不可仅凭“fresh/已刷新/无 lineage”判断正确；不建议直接在生产做广域全局发布、模板升级或一键刷新 | 综合 `[A] §八~九`、`[C] §12`、`[D] §六` |
| 当前不应承诺 | “所有模块均已贯通”“一处修改自动应用全部”“最终值随处可追溯”“模板已被其他人真实引用” | 有路由/组件/测试只证明存在；live 治理表 0 行，且缺登录态写入型 UAT | A/B/C：`[G] §1.1~2`、`[C] §2`、`[D] §4.2~4.3` |

**安全使用边界：**（1）Formula Push 仅限已有 binding、已核项目数据且用户审阅 run 明细的单体场景；（2）report/cross-check/wp/note 的项目级编辑可用于受控编制，但保存后必须复核实际值和错误，不得只看成功回执；（3）tb_detail 当前只能视为公式中心里的管理/手工执行视图，不能视为 TB 权威写入；（4）统一 lineage、时间轴和 stale 标志不能单独作为审计证据；（5）全局发布、模板批量升级和“一键刷新”在 P0 收口及【测试】项目真实 UAT 前不进入生产广域使用。【`[A] §二、§五~六`；`[C] §6、§9`】

## 3. 当前架构与数据流
```text
V199 Definition/Governance（project > subscribed-template materialization > global exact/* > preset）
  ├─ publish / apply / subscribe → 三方比较 → inherit/follow/same/conflict/pinned/frozen → pending 决策
  └─ effective definitions → 按域分流而非进入一个执行器
       ├─ ReportFormulaParser / ReportEngine
       ├─ strict WP evaluator / Formula Runtime / prefill / 前端 autosync
       ├─ note generator / binding evaluator / formula push / 前端 payload builder
       ├─ cross-check 独立校验器 / Excel A1 evaluator / consol linear analyzer
       └─ 中央 L1 FormulaEngine（20 函数）
            → 各域 writer → EventBus / stale / recalc / push / SSE
            → 分散 trace、push_state、refs、audit_log、V1 Registry / ACNR / V2 dependency
```
实际边界是“统一治理框架 + 多执行轨”。同一公式在解析、引用装载、缺数、除零、精度、写入、stale 清除和 trace 上可得到不同结果；V1 Address Registry、ACNR、V2 静态依赖图和 V199 regex dependency 也尚未收敛为执行器的单一入口。【A：`[A] §二~四`】

## 4. 详细覆盖矩阵
| 模块/域 | 定义与编辑 | 执行/权威写入 | 传播与 stale | 溯源/展示 | Verdict | 等级与路径 |
|---|---|---|---|---|---|---|
| 四库表/TB | TB 主链叶子聚合与审定恒等式较可靠；L1/TB resolver 并存 | 业务行 519 条排除 UAT 后恒等式 0 不符；中央 `/formula/execute` 却只读 unadjusted 并冒充多口径 | TB 事件能触发部分 push/recalc；`tb_detail` 设置不被 TB/四表消费者读取 | 地址目录存在，最终值没有统一 provenance | **底层数据链较稳，公式管理接线不闭环** | A：`[A] §一、§三`；B：`[C] §6` |
| report | 318 active 公式；项目/全局配置、编辑、有效层是真接线 | ReportEngine 真消费，但全量/affected/stale 三条路径失败语义不同；410 行中 50 漂移 | 可标 stale 并重算，但 49 个差异行 false-fresh | 单条 route 的 value 与空上下文重演 trace 可矛盾；batch trace 空 | **可用但存在 P0 正确性风险** | A：`[A] §一、§五` |
| wp/底稿 | `wp_formula` 29 行，preset/custom/reference 模型；主 UI 丢来源/refs 等元数据 | strict evaluator 真执行；Formula Runtime 对 18 个 WP 引用 18/18 错 | 全局继承仅初始化/重新预填，runtime/Tier A 不读；prefill stale 清除不稳定 | `refs` 29/29 空、last_computed_at 29/29 空；tooltip 仅 2 个生产宿主 | **项目编辑局部可用，全局与运行时不可托底** | A：`[A] §一、§四`；B：`[C] §6、§9`、`[D] §2` |
| note/附注 | 项目公式保存、V199 materialize、表内 preset 均存在 | 公式执行与 push 真写，但 67 builder/57 files、144 autosync 引用与 push 大量所有权重叠 | 227 stale notes，source 全 NULL；值不变时可能不清 stale | 普通附注无统一输入值/版本/步骤展开 | **真执行但多写方与 stale 风险高** | A：`[A] §五`；B：`[C] §4、§6` |
| consol_note | 51 条 active seed 公式；模板级编辑存在，项目适配 UI 缺失 | 填数路径真读 effective formulas | scope 错把最多 84 个单体项目列入；只有 1 个 UAT consolidated 项目 | 有局部公式/数据字段，无业务集团闭环 | **代码接线，业务证据不足** | A/B：`[A] §二`、`[C] §6.1` |
| push | 375 active rules、81 bindings，可编辑规则受 policy 限制 | 四阶段 source→evaluate→write/CAS/savepoint 真闭环 | 成功可清 note stale；合并项目显式 skip | run/state 能展示公式值、当前值、已推送值 | **当前最成熟样板，非全平台统一引擎** | A/C：`[A] §五`、`[D] §4.1` |
| cross_check/提示规则 | V199 用户规则 + 1603 项目录 | 用户规则真并入执行；目录至少 6 条“注册但未接执行” | 发布后可重跑并落结果 | IssuePanel 有左右值/差异，但 addr_id 不可跳 | **局部真闭环，目录不等于执行覆盖** | A/B：`[A] §二`、`[C] §6`、`[D] §2.4` |
| tb_detail | 动态默认 + 项目保存 + 手工 batch 预览 | 无 TrialBalanceService、四表、prefill、生成消费者 | 仅把全部 WP 标 stale，可能制造误导 | 公式结果只留前端 `formulaResults` | **治理 CRUD/预览，不是业务闭环** | B：`[A] §二`、`[C] §3.3、§6、§9.1` |
| global/template | CAS、发布、模板版本、订阅、冲突、promote 均为真代码与真 UI | 各域消费者不齐；模板订阅项目跳过全局更新 | post-commit best-effort EventBus，无 durable outbox | 治理层有版本，结果层未绑定所用版本 | **真治理内核，live 零采用，未证明现场闭环** | A/B/C：`[C] §2~3、§7~10` |
| lineage/audit | 分散 trace/refs/source_scope/push state/hash chain | UnifiedLineage WP 调用少参数后被吞为空；附件查询不按项目隔离 | 审计 helper 并发可能分叉，timeline 3/5 源静默失效 | GraphPanel 生产 0 挂载，tooltip 生产 2 文件/5 挂点且均不传时间 | **不可作为全平台逐值审计证据** | A/B：`[A] §六`、`[D] §2~3` |

## 5. 六项核心能力明确 verdict
| 能力 | Verdict | 明确结论 |
|---|---|---|
| 全局设置 | **部分实现（内核真、全域闭环假）** | 7 域治理接口存在，但 `tb_detail` 无自动消费者，wp 全局层不进部分执行轨；`wired` 是常量，不是能力探测。【`[C] §1、§5~6`】 |
| 项目适配 | **较完整但语义分裂** | 项目 override、模板物化、pinned、恢复上游和 CAS 已有；空值/disabled 在 report/wp/note/push 含义不一致，consol_note 缺正常项目 UI。【`[C] §3~4、§9`】 |
| 冲突弹窗 | **真接线但有 P0/P2 缺陷** | 全局/模板/订阅/项目应用和常驻 pending 对话框已接；项目→项目 pending 无版本令牌，同 slot 跨域 key 不含 domain。【`[C] §8`】 |
| 二次编辑 | **多域可用，不是统一体验/硬门** | report/wp/note/cross-check/tb_detail/push 均有入口；3/4 preset 挂点只改内存，reference 主流程不可达，report/tb/cross generic 保存缺统一语法/引用硬门。【`[C] §9`】 |
| 模板复用 | **代码层真模板，现场使用未证明** | V199 模板有版本、可见性、订阅、升级、冲突、退订、promote；live 模板/版本/订阅为 0，无旧版回滚、指定版本订阅、已有模板新增 slot。【`[C] §2、§10`】 |
| 溯源 | **未形成用户可依赖闭环** | 调试器/push 专项可见部分输入值，普通最终值不能统一展示来源、输入、步骤、版本、时间和跳转；统一 lineage 还有确定性故障与项目隔离缺口。【`[D] §2`】 |

## 6. 缺陷与差距分级
| 级别 | 缺陷（机制） | 影响范围/证据或复现路径 | 建议修法 |
|---|---|---|---|
| P0 | Formula Runtime 只把 addr_id 值放入 row_cache，表达式函数仍读空 tb/wp/note map；环节点被原序追加 | 真实 29 条 wp_formula 生成 29 mutation，18 个 WP 引用与严格 evaluator **18/18 不一致**；一键刷新生产路径可应用错值。【`[A] §一、§三~四`】 | 立即冻结 runtime mutation apply；统一 typed resolver 后逐条与严格 evaluator 对拍，环一律 blocked |
| P0 | 中央 execute 用 unadjusted 冒充审定/余额并把未知函数、除零、缺引用变 0/ok | 华氏 1001 审定应 100 却返回 0；`EVIL()`、`1/0`、缺 ROW 均 error=null。【`[A] §一、§三`】 | 路由改用统一 resolver；保留 blocked/errors，不允许写入型调用消费 fail-open 值 |
| P0 | DraftRefresh 四域只走 Formula Runtime，preset 只写 marker | 和平药房 report runtime_units=0/page_keys=7，note/adjudication 0/0，workpaper:D 0/4。【`[A] §一`】 | 各域调用权威 generator/writer；marker 不计成功；真实业务表 before/after 对账 |
| P0 | 报表重算路径语义不一致，stale 标志未反映漂移 | 5 个业务项目 410 行中 50 不一致、49 标 fresh，最大差额 3,928,889,818.20。【`[A] §一、§五`】 | 统一 report 执行合同；全量重算并重建 stale 基线，失败保留旧值+blocked |
| P0 | UnifiedLineage 调 WP trace 少传 source；附件 lineage 无 project 过滤 | wrapper 探针上下游均 `[]`；相同 target_ref 可能串项目附件。【`[D] §2.3、§3.1`】 | 修真实签名并加不 mock wrapper 契约测试；附件表补/回填 project_id 或可靠 join 校验 |
| P0 | 项目→项目 pending 无 upstream version | 旧弹窗可采用来源项目后来再次推送、用户未看过的定义。【`[C] §8.3 C1`】 | pending 引入 revision/updated_at CAS；过期决策 409 并强制重载 |
| P0 | timeline 3/5 数据源字段错误且 broad catch 返回空 | audit/publish/template version 使用不存在字段，页面静默“暂无”；live 已有 audit 也会漏。【`[C] §8.3 C3`】 | 改真实 ORM 字段；返回 partial/unavailable_sources，禁止异常伪装空数据 |
| P0 | 审计 helper 并发读取相同 prev_hash | `append_audit_log` **41 calls/25 files**，无 worker 同款 advisory xact lock，可能分叉。【`[D] §一、§3.5`】 | 统一加项目链锁；prev_hash 查询 fail-closed；全链从 genesis 验证边界 |
| P1 | 语言、arity、缺数、除零、精度与 PREV/PRIOR 多轨 | 前端 21 函数而 L1 20，前端多 PRIOR；`%`/单 `=` 与后端不闭合；strict 与代 0/保旧并存。【`[A] §三`】 | 建单一 executable grammar/registry/status enum，前后端生成元数据；统一 Decimal/舍入边界 |
| P1 | wp 全局层与 tb_detail 没有真实全域消费者，应用范围只接 3/7 域 | wp runtime/Tier A 不读 effective；tb_detail 后端仅 router import；wp/note/consol_note/push 保存不弹推广范围。【`[C] §5.1、§6`】 | 先定义 tb_detail 产品语义；所有执行轨只读 effective；未支持域明确禁用推广而非假 wired |
| P1 | note 多写方、stale 清除条件不统一 | 56 个可解析 builder wp_code 全与 81 binding 重叠；50 autosync code 中 46 与 push 重叠；227 stale note 无 source。【`[A] §五`】 | 建 domain+target/field writer ownership；按“重算成功”清 stale并记录 source/version/error |
| P1 | settings 传播非 durable | 定义先提交，EventBus 失败只 warning；无 outbox/retry，内存 degraded 重启丢失。【`[A] §五`、`[C] §7`、`[D] §3.6`】 | 定义与 outbox 同事务；worker 重试、幂等，UI 显示 pending/failed |
| P1 | 写入校验、资源预算、自定义函数治理不统一 | timeout 配置仅 2 处展示/定义，无执行消费；无 AST 节点/深度预算；自引用 custom function 最终 ok=true/value=0。【`[D] §3.2~3.3`】 | 所有写入口共用 validator；增加长度/节点/深度/批量预算；不需要 custom function 则退役，需要则持久化+DAG |
| P1 | 模板/全局无业务回滚，项目回滚接受客户端 target_formula | live OpenAPI 中 global/template rollback 0；UI 不传 expected_version。【`[C] §7.2、§10.3`、`[D] §3.4`】 | 以旧 snapshot 发布“新版本”实现可审计回滚；服务端从日志取目标并做 CAS/hash 校验 |
| P1 | 最终值 provenance 未绑定计算版本 | FormulaResult trace 临时、WP refs/时间未被主 UI消费、普通 report/note/wp 无统一展示。【`[D] §2.1~2.2`】 | 持久化 provenance envelope，并让最终值组件直接消费与跳转 |
| P2 | 多域冲突 identity 不含 domain | 后端 3 个构造/消费点 + 前端 1 个契约；同名 slot 可碰撞。【`[C] §8.3 C2`】 | key 统一 `{project}|{domain}|{slot}`，迁移旧 pending 并加跨域同名用例 |
| P2 | consol_note scope/权限与统一规则偏离 | 1 个 consolidated 项目却可把最多 84 个单体计入；partner/manager 可绕 admin 改全局层。【`[C] §6.1、§8.4`】 | scope 必筛 consolidated；全局写权限统一，UI 与后端同一能力矩阵 |
| P2 | 模板产品闭环不完整 | 新项目“去订阅”落到无订阅按钮页面；无版本 diff/回滚/新增 slot；live 六表全 0。【`[C] §10`】 | projectId 直开订阅对话框；支持 diff、新增 slot、回滚发新版本；【测试】项目完成端到端 UAT |
| P2 | 预设编辑/参照公式是假入口或断路 | 4 个 preset mount 只有 1 个 handler；reference 后端真能力在主 UI 不可达。【`[C] §9.2`】 | 无保存宿主改只读；主编辑器保留 formula_source/reference_formula_id 并验证引用 DAG |
| P3 | 术语和状态误导 | 7 域常量 `wired`、项目“全局公式管理”其实只是本项目总览、四类“模板”混名。【`[C] §5、§10.4`】 | 拆分 crud/effective-read/auto-exec/propagation/UI 状态；按“模板/公式包/预设/导入导出/项目总览”改名 |
| P3 | spec/测试可见假绿 | 166+117 绿仍漏 runtime 错值、report 漂移、trace 矛盾；历史 spec 存 `[x]` 与“未做”并存。【`[A] §七`、`[D] §4~5`】 | 完成门禁绑定 HEAD、生产调用、真实 PG shape、逐值断言和真实宿主挂载，不以 mock/组件存在判完成 |

### 6.1 反模式全仓规模
| 反模式 | 已证规模 | 审计解释 |
|---|---:|---|
| broad `except Exception` | `backend/app` 3542 处/1147 文件；formula 路径 158 处/53 文件；timeline 6 处 | 规模是风险面，不代表每处都是缺陷；已确认 timeline 3 源、lineage wrapper 等存在“错误→空” |
| 附注潜在多写方 | 67 个 `build*SyncPayload` 定义/57 文件；144 个生产文件引用 autosync；70 个 watch+schedule；141 文件含 sync endpoint | 能确认 ownership 重叠，不能未经字段对拍断言每格双写 |
| 应用范围未接 | 7 治理域仅 3 个保存链调用 | report/tb_detail/cross_check 已接，wp/note/consol_note/push 未接 |
| preset 假保存 | 4 个生产 mount，仅 1 个 edit handler | 其余 3 个刷新即丢 |
| lineage 可见性 | tooltip 2 个生产文件/5 挂点；GraphPanel 生产 0 挂载；TracePopover 生产 0 挂载 | 组件/测试存在不等于用户链路 |
| 审计并发面 | helper 41 calls/25 files | 共用无锁 helper 的直接调用面 |
| 项目鉴权平台基线 | path project_id 424 个，identity-only 200；body/query 227 个，identity-only 88 | 公式命名路由定向清零，但 lineage 附件隔离不在该扫描口径；不可外推全平台安全 |
| 决策键缺 domain | 后端 3 点 + 前端 1 契约 | 与 DB 的 project+domain+slot 唯一身份不一致 |
| live 治理采用 | V199 六表全部 0 行；report project override 0；模板/订阅/发布 0 | 证明迁移在，不证明用户使用链 |

## 7. 目标架构与单一来源
| 层 | 单一职责/来源 | 现有能力处理 |
|---|---|---|
| Formula Definition | 逻辑统一的不可变版本定义：domain、slot、scope、expression/rule、disabled、owner、approval、base/version；物理可分表但只能经一个 Repository/Effective API | **保留并强化** V199 store/effective/CAS/template/sync；把 report/wp/consol 的特殊表封装在统一接口后，禁止旁路写 |
| Resolver | ACNR `addr_id` 作为稳定身份；typed ref 统一解析 TB/ROW/REPORT/NOTE/WP/AUX/PREV/ADJ，返回 value+missing/error+source metadata | **保留** TrialBalanceResolver、严格 preload 与 ACNR；**合并** V1/V2/V199 dependency 为 ACNR 视图；禁止空 context 重演 trace |
| Execution | 单一 parser/grammar/function registry/status/Decimal/预算；预览与写入同一次 evaluation result；domain adapter 只负责装载和持久化 | **合并** L1、ReportFormulaParser、strict WP、note/cell evaluator 的公共语义；**冻结/退役** 当前错误 Formula Runtime 直接写入，修复后仅作统一执行编排 |
| Propagation | 定义提交+outbox 同事务；worker 按 definition version/run id 幂等传播；统一 stale 状态机 pending/running/succeeded/blocked/failed | **保留** EventBus/SSE 作为通知、push 四阶段与 report fail-visible；**新增** durable outbox；退役 marker-only“成功” |
| Lineage | 持久化 `formula_version/evaluated_at/run_id/writer/input[{addr_id,value,project,year,version}]/steps/manual_override/error` read model | **合并** trace、wp refs/source_scope、push_state、report source_accounts、audit；修 UnifiedLineage；挂到真实 TB/report/note/wp 最终值 |
| Governance | 统一 validate→preview impact→permission/approval→CAS publish→conflict→audit→rollback-as-new-version；能力状态可探测 | **保留** V199 conflict/template UI；**退役** 常量 wired、客户端任意 rollback target、无 handler 的假入口；模板/全局真实试点后再开放广域发布 |

单一来源不是“把所有行塞进一张表”，而是每层只有一个权威接口：定义只能经 Definition Repository，引用只能经 Resolver，求值只能经 Execution Contract，写入只能经域级 Authority Writer，传播只能经 Outbox，用户解释只能读 Lineage Read Model。附注前端 builder 与后端 push 在拍板前按字段 ownership 共存，严禁同一字段双权威。【综合 `[A] §二~六`、`[C] §3、§6、§10`、`[D] §2~3`】

## 8. 实施路线
| 阶段 | 交付单元与建议顺序 | 依赖/迁移风险 | 验收标准 |
|---|---|---|---|
| 近期 1~2 周 | ①冻结 Formula Runtime mutation 和广域一键刷新；②修中央 execute/trace；③修 report false-fresh 并统一三条重算状态；④修 UnifiedLineage 签名与项目隔离、timeline 字段；⑤pending revision CAS 与跨域 key；⑥建立真实 PG shape/逐值回归 | 先冻结再修；附件 project 归属可能需迁移；report 重算不能覆盖人工值；只用【测试】项目做写入验收 | 18 个 WP 与 strict evaluator 18/18 一致；环 blocked；TB 审定 100 返回 100；未知/除零不再 ok；410 报表逐值一致或有明确 blocked/stale；lineage 非空/跨项目隔离；旧 pending 409 |
| 中期 1~2 月 | ①发布统一 grammar/function/status；②以 report→wp→note 顺序接统一 Resolver/Execution；③定义 writer ownership 与 stale 状态机；④settings durable outbox；⑤provenance envelope + TB/report/note/wp 真挂载；⑥模板【测试】双项目完整试点 | 前后端语法兼容；历史 formula/version 回填；note 多写方必须先做字段矩阵；传播需幂等与重放 | 同式在 preview/batch/report/wp/note/push 数值与状态一致；事件故障可恢复；重算成功即清 stale；最终值可显示来源、输入、步骤、版本、时间并跳转；global→template→subscribe→conflict→resolve→recalc 全链可复验 |
| 长期 | ①迁移 consol/cross-check/Excel A1/剩余 prefill；②V1/V2 变 ACNR 派生视图；③双人发布/审批与回滚发版；④性能、6000 并发与灾难恢复；⑤按验收退役重复执行器和假入口 | 大规模定义迁移、历史审计兼容、跨年度/合并会计口径、性能容量；需要产品和会计裁决先冻结 | 全域无旁路执行/写入；依赖/lineage 可全链查询；全局发布可预览、审批、重放、回滚；真实集团 UAT、故障注入和容量测试通过 |

原则：**先封错写、修闭环与正确性，再统一语言/传播/溯源，最后扩域和新增功能。** 不以新增函数、模板数量或组件数量代替逐值正确性。

## 9. 需要用户拍板的产品/会计口径
| 决策 | 推荐方案 | 替代方案与 trade-off |
|---|---|---|
| 公式冲突默认行为 | **默认 ask + 保留本地，不自动覆盖；无响应保持 pending，旧 revision 禁采用。** inherit/follow 可自动，conflict/pinned 必确认 | 默认采用上游操作少，但会静默覆盖项目判断；默认 keep 安全但“一处改全部”弱、长期漂移 |
| 预设停用语义 | **显式 `{disabled:true}` tombstone，空值只表示未定义/回退；所有域一致，并记录原因与版本。** system/derived 若法律/会计必需则不可停用但可申请例外 | “清空即停用”直观但无法区分删除、回退、禁用；wp/note 当前差异会继续制造意外恢复 |
| 模板共享范围 | **personal/team/group/firm 四级保留；订阅必须显式，范围收窄时既有订阅转 pinned 并通知，不静默继续。** firm 仅管理员发布 | 自动全员继承推广快但风险大；范围收窄立即断订阅更严格，却可能让项目结果突然变化 |
| 全局发布权限 | **管理员发起 + 第二名管理员/合伙人复核；按受影响项目/域设阈值，超阈值强制分批。** project candidate 可由编辑者提交 | 单管理员发布效率高，但当前无 outbox/回滚时爆炸半径过大；仅合伙人发布又可能缺平台治理能力 |
| 写入型公式是否必须审批 | **预览/校验公式无需审批；会自动改 report/note/wp/TB/合并结果的定义，首发与扩大范围必须审批。项目本地小范围修改可即时保存但结果进入“待复核”，签发前阻断。** | 所有编辑都审批最安全但拖慢现场；完全即时写入效率高却不适合审计证据链和广域传播 |
| 附注权威源/交接边界 | **按 section+field 建 ownership：当前前端 `build*SyncPayload` 继续作为既有权威，Formula Push 仅写明确 owned keys；完成逐值对拍后按章节分批移交后端，移交即删除前端同字段写权。** | 立即全迁后端可快速统一但 67 builders 风险高；永久留前端可保现状，却无法进入统一 definition/execution/lineage |
| tb_detail 产品语义（追加） | **若目标是公式中心的试算预览则改名且不标 WP stale；若目标是 TB 权威层则必须经过审批发布门并由 TrialBalanceService 唯一消费。建议后者另立专项，不在当前 CRUD 上直接扩写。** | 维持现状成本低，但用户会持续误解“已改 TB 取数” |
| 自定义函数（追加） | **若没有明确客户场景，退役当前 API；若保留，先完成持久化、参数、DAG/循环、预算、权限和多 worker 一致性。** | 保留实验 API 灵活，但当前单请求状态和递归 fail-open 不可生产使用 |

## 10. 实际运行的命令/测试与结果
下列是专项调查报告记录的实际运行证据，本综合步骤**没有重跑测试或写 DB**，仅读取五个指定路径（其中 11 缺失）并用只读目录列举确认文件存在性。
| 命令/探针 | 结果 | 来源 |
|---|---|---|
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/test_formula_engine.py tests/test_formula_audit_pbt.py tests/services/test_unified_lineage_service.py tests/formula_settings/test_endpoints.py tests/formula_settings/test_formula_endpoint_authz.py tests/test_project_endpoint_authorization_baseline.py tests/test_project_endpoint_authz_body_carried.py -q -p no:playwright`（cwd backend） | 146 passed，4 warnings，124.32s | `[D] §4.1` |
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/test_formula_push_coverage.py tests/test_formula_push_rules.py tests/test_formula_push_account_single_source.py tests/test_formula_push_k1_integration.py -q -p no:playwright` | 98 passed，213 warnings，22.09s | `[D] §4.1` |
| `rtk ..\.venv\Scripts\python.exe -m pytest tests/formula_settings/test_templates.py tests/formula_settings/test_template_endpoints.py tests/formula_settings/test_propagation.py -q -p no:playwright` | 21 passed，1 warning，12.29s | `[D] §4.1` |
| `rtk npx vitest --run` tooltip/history/LineageGraphPanel/component mounts 4 文件 | 33 tests passed，39.52s | `[D] §4.1` |
| `rtk npx vitest --run` settings tests + template manage/subscribe + push panel 9 文件 | 66 tests passed，28.29s | `[D] §4.1` |
| 架构角度核心后端/前端定向套件 | 后端 166 passed/1 warning；前端 6 files/117 passed；custom function 3+1 xfailed | `[A] §七` |
| live `GET /api/health`、`GET /openapi.json` | health 200/healthy、migrations 203；OpenAPI 含主要公式路由（lineage 报告统计 111 个路径名含 formula） | `[G] §1.1~1.2`、`[D] §4.1` |
| 只读/进程内探针 | Runtime 18/18 错值；report 50/410 漂移；route trace 值 4,467,536.12→0；lineage wrapper 上下游均空；双引号公式求值 123 但依赖为空；自引用 custom function 最终 ok=true/value=0 | `[A] §一、§四~六`、`[D] §4.1` |

## 11. 未验证项
- `11-coverage-matrix.md` 缺失，覆盖角度证据不足；本稿未伪造该分支结论。
- 未做登录态 Playwright：会产生 session/Redis/审计或自动保存副作用；因此“UI 已挂载”不等于真实用户流程已验收。
- 未运行 pg_only/CAS 真 PG 写测试，未调用 publish/apply/rollback/delete/push 等写 API；live V199 六表仍为 0，模板真实采用和全局冲突链未获现场证明。
- 未跑全量 pytest/vitest；已运行测试仍有 SQLite、MagicMock、人造 payload 和允许空结果的盲区。
- live 服务健康不证明运行进程与 HEAD 字节完全一致；路由注册不证明业务执行正确。
- 合并附注仅有 UAT consolidated 项目；无真实业务集团数据，不能背书会计口径闭环。
- 附注写方重叠已证到 wp_code/章节所有权层，尚未逐字段证明每个交集都会双写；修复前必须生成 ownership 矩阵。

## 12. 草稿结论
公式管理确实具备成为平台“灵魂”的基础：V199 治理、模板订阅/冲突、严格取数部件、Formula Push、CAS 与部分审计都值得保留；但目前最重要的不是继续扩函数和入口，而是先阻断错误 Runtime、统一求值与失败语义、建立权威写方、可靠传播和逐值 lineage。只有当同一公式在 TB、报表、附注、底稿、推送的预览与实际写入得到同一数值/状态，并且全局变更能被可靠传播、冲突可恢复、最终值可追到版本化输入后，平台才可以被称为“单一公式中枢”。【综合 `[A] §八~九`、`[C] §12、§17`、`[D] §六`】
