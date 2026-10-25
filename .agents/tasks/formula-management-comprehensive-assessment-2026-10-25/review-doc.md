# 公式管理评估守住了能力边界，但风险档位与优先级仍未闭合

最终报告没有把文件、组件、路由或绿测直接写成用户闭环；六项核心 verdict、模块覆盖矩阵和“先正确性、后扩功能”的路线总体与指定证据一致。上一轮指出的 report 传播项封顶错误和成熟度无固定分档已经修正。当前仍有三项会影响管理结论的阻断问题：41 分由一个混合检查项跨证据层计分维持，当前系统尚未证明满足“受控试点”准入条件，而且 P0 的“确定性错误成功”标准没有一致应用到 lineage 和 timeline。缺失的 `11-coverage-matrix.md` 已披露，但仍构成一项明确的证据缺口。

Watch for: **confirmed** — “早期受控试点级”使用了尚未落地的冻结、隔离、回退和写入 UAT 作为试点边界；**likely** — 第 21 项让 L3 的 Formula Push 替 L2 的普通调试器/最终值可观测性取得 3 分，且这一分正好决定 41/40 档位；**confirmed** — UnifiedLineage 和 timeline 的确定性假空结果符合报告自己的 P0 文字标准，却仍列 P1；**confirmed** — 指定的独立覆盖矩阵证据文件不存在。

**Verdict**: NEEDS_CHANGES

## High-level view

报告在能力定性上是克制的。全局设置、项目适配、冲突弹窗、二次编辑和模板均停在 L2，模板 live 零采用、应用范围仅接 3/7 域、preset 假保存、reference 主流程不可达等边界都写得清楚；溯源也拆开了后端原材料、前端真实展示和最终值逐值闭环，没有拿零挂载组件或 Mock 绿测冒充可用。

覆盖矩阵的主要格子能从 `10-architecture.md`、`12-global-conflict-edit-template.md` 和 `13-lineage-governance-tests.md` 交叉复核。中央 execute、Runtime、report false-fresh、Draft Refresh 和附件项目隔离均有源码或真实只读运行反证；Formula Push 只被定为局部 L3 样板；tb_detail 只被定为 CRUD/预览。不存在的 `11-coverage-matrix.md` 使矩阵缺少用户指定的独立角度，但报告没有隐瞒或伪造该来源。

数值评分仍有一项证据聚合问题。“调试器与 push 专项可观测”把两个成熟度不同的子能力合并为一个检查项，并只用 push 的真实 run/state 支撑 3 分；普通最终值、tooltip、GraphPanel 和调试展示仍只有局部挂载或零挂载证据。由于总分恰为 41，该项如何计分会改变“集成原型级”与“早期受控试点级”的分档。

风险准入门槛比数值分数更关键。报告自己规定：若隔离、回退或人工复核条件不具备，应继续下调；但当前冻结 Runtime、限制 Draft Refresh、双项目写入 UAT、全局/模板业务回滚都还是整改动作或未验证项，不是现行控制。故 41 分可以保留为结构性评分，但不能直接推出当前已经达到“受控试点”风险档。

P0/P1 主体排序方向正确，近期路线也已把 lineage 真调用链和 timeline 放入 R4/R5；然而分类表仍与统一标准冲突。UnifiedLineage 在正常调用下确定性吞掉 TypeError 并返回空上下游，timeline 的 3/5 数据源在已有记录时确定性吞 schema 错误并显示为空，均属于报告定义的“错误成功”，却列为 P1。

<details>
<summary>Issues (4)</summary>

1. **受控试点准入未成立（阻断，confirmed）** — 当前冻结、隔离、回退和登录态写入 UAT仍是建议或未验证项，不能按报告自己的风险门槛把现状定为“早期受控试点级”；应降为“集成原型级”，或补出已生效控制的证据路径。
2. **可观测性混合项跨层计分（阻断，likely）** — 第 21 项用 Formula Push 的 L3 证据为普通调试器与 push 的组合项计 3 分，这一分正好决定 41/40 档位；应拆项、按较弱能力计分，或补普通调试器的 L3 证据。
3. **P0 错误成功标准未一致应用（阻断，confirmed）** — UnifiedLineage 和 timeline 均在正常前置下确定性吞错并返回假空结果，却列为 P1；应收窄 P0 定义，或将两项升级并同步摘要与路线。
4. **独立覆盖矩阵证据缺失（非阻断，confirmed）** — `11-coverage-matrix.md` 不存在；应补交该证据，或正式删除该交付项并把报告矩阵明确命名为其余材料的综合汇总。

</details>

<details><summary>Details</summary>

## 当前状态尚未满足“早期受控试点级”的风险准入门槛

**阻断，confirmed。** 位置在 `report.md` §1.2 的总体封顶与准入说明、§2“修复前的受限试点边界”、§11 未验证项。报告规定 41~60 分只有在“明确范围、人工复核和可回退”条件下才是早期受控试点，并进一步写明若隔离、回退或人工复核条件不具备就要下调。可是 §2 的“立即冻结 Runtime mutation apply”“report 只允许只读对比”“publish/apply/rollback/delete 不开放广域生产”等都是建议中的风险缓解动作，材料没有证明这些限制已经由权限、feature flag、服务端拒绝或发布流程实际执行。

指定证据反而确认关键控制尚未具备：`10-architecture.md` §一、§八确认错误 Runtime 和 Draft Refresh 仍是生产分派路径；`12-global-conflict-edit-template.md` §7.2 确认全局/模板没有业务回滚 API；`13-lineage-governance-tests.md` §4.3 及 `report.md` §11 确认没有登录态写入 UAT、没有调用 publish/apply/rollback/delete 写 API。人工复核也不能把已知错误求值器或跨项目附件查询变成受控能力。

建议把 `41/100` 明确命名为“结构/证据评分”，风险调整后的**当前**成熟度降为“集成原型级”；待服务端冻结错写路径、双项目隔离与登录态写入 UAT、可回退机制有证据后，再升到“早期受控试点级”。替代做法是保留该档位，但必须给出已经生效的控制点和证据路径，而不是引用未来动作。

## “调试器与 push 专项可观测”混合计分会改变总档位

**阻断，likely。** 位置在 `report.md` §1.2 第 21 项。该项将普通公式调试器和 Formula Push 专项可观测性合并后计 3 分，依据只写“真实 push state/run 与只读探针可见”。`10-architecture.md` §五支持 push 的真实 run/state 为 L3；但 `13-lineage-governance-tests.md` §2.1~2.2、§4.2 同时说明普通最终值没有统一输入展开，tooltip 只有两个生产宿主且未传计算时间，GraphPanel/TracePopover 零生产挂载，FormulaDebugPanel 仅是临时编辑/调试能力且缺直接展示测试。这些材料不支持把“调试器与 push”整体判为 L3 用户可观测能力。

这一项不是无关紧要的四舍五入：若组合项按较弱子能力取 2 分，总分由 41 降为 40，分数档从“早期受控试点级”变为“集成原型级”。建议拆成可独立复算的两个检查项并保持总分母不变，或明确组合项采用最低证据层并改为 2 分；若坚持 3 分，须补出普通调试器生产函数/真实用户展示的 L3 证据路径，并说明为何一个子能力可代表整个组合项。

## P0 的“确定性错误成功”标准未一致应用

**阻断，confirmed。** 位置在 `report.md` §6.1、§6.3 P1-1/P1-2。统一标准把“生产入口可达、正常前置满足时确定地产生错误成功”定义为 P0。`13-lineage-governance-tests.md` §2.3 已用生产签名和直接探针确认 UnifiedLineage 少传 `source` 后恒抛 TypeError，再被 broad catch 吞成空数组；本次唯一源码窄查也确认 `UnifiedLineageService._query_wp_upstream/_downstream` 实际以三参调用四参函数并返回空。`12-global-conflict-edit-template.md` §8.3 C3 则确认 timeline 的 5 个源中 3 个使用不存在字段，在库已有 `formula.changed` 时仍被吞成“暂无”。

两项都满足报告文字上的“确定性错误成功”，但被列为 P1；与之相邻的 P0-2/P0-3 正是因 0/成功或 marker/成功被定为 P0。近期路线虽已把它们放在 R4/R5，降低了实施顺序风险，却没有解决分级标准自相矛盾。建议二选一：把 P0 定义收窄为“影响业务数值/权威写入、安全隔离的确定性错误成功”，并说明 lineage/timeline 属审计可观测性 P1；或按现有宽定义将 P1-1、P1-2 升为 P0，并同步 P0 数量、管理摘要和近期交付。

## 指定覆盖矩阵证据文件缺失

**非阻断，confirmed。** 用户指定的 `11-coverage-matrix.md` 实际不可读/不存在，`00-ground-truth.md`、`10-architecture.md`、`12-global-conflict-edit-template.md`、`13-lineage-governance-tests.md` 均可读。`report.md` §0.2、§4、§11 已如实披露，并把矩阵定位为其余三份材料的交叉汇总，因此没有发现借不存在文件过度背书的行为。

建议补交独立的 `11-coverage-matrix.md`，或在交付清单中正式删除该证据项并把 §4 改名为“综合覆盖矩阵”，避免后续读者误以为矩阵经过第五角度独立复核。在补齐前，涉及矩阵独有的逐格结论不得提升证据等级。

## 已修复的上一轮问题与其余核对结果

上一轮 review 指出的第 11 项 report 传播 P0 封顶错误已修：该项现为 1 分，跨模块传播为 7/20，总分为 41。成熟度固定区间、P0 总体封顶和准入条件也已补入 §1.2。这两项不再作为本轮 finding。

六项 verdict 均明确并有对应证据：全局/适配/冲突/编辑/模板停在 L2，溯源为局部 L3、平台整体 L1；没有把 live 六表为 0、路由注册、组件存在或测试通过提升成 L4。后端保存与前端展示、HEAD 已提交与未提交依赖、注册与实际调用均有显式区分。用户拍板清单对冲突默认、停用语义、tb_detail、模板范围、发布权限、审批、附注权威源、模板跟随、自定义函数和审计强度均给出推荐与替代 trade-off。路线按“先阻断错写/隔离，再统一执行和传播，最后扩域与模板共享”排序，与证据支持的风险方向一致。

</details>

<details>
<summary>File map</summary>

- `report.md` — 被复核的最终总判断、41 分评分、覆盖矩阵、六项 verdict、P0~P3 与路线。
- `00-ground-truth.md` — HEAD/未提交边界、live 健康与路由注册、调查地图。
- `10-architecture.md` — Runtime、execute、Draft Refresh、report 漂移和 push 的源码/真实只读运行证据。
- `11-coverage-matrix.md` — 指定证据缺失；最终报告已披露。
- `12-global-conflict-edit-template.md` — 全局、项目、冲突、编辑、模板与 live 零采用证据。
- `13-lineage-governance-tests.md` — lineage、安全、审计、测试假绿与真实探针证据。
- `backend/app/services/unified_lineage_service.py` — 本轮唯一源码窄查，确认 wp trace 少参并吞错返回空、附件查询未使用 `project_id`。

完整被复核报告：`d:/GT_plan/.agents/tasks/formula-management-comprehensive-assessment-2026-10-25/report.md`。本轮未重跑测试或写数据库。

</details>
