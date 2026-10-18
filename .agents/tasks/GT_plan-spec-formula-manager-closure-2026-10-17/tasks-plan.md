# tasks.md 大纲计划 · formula-manager-closure

> 本文件是 tasks.md 的编写计划（骨架 + 逐任务元信息），供下一步 wf-coder 据此落笔 tasks.md。
> 目标 spec：`d:\GT_plan\.worktrees\fm-closure-spec\.kiro\specs\formula-manager-closure\tasks.md`
> 权威输入：同目录 requirements.md（20 条需求）、design.md（§0~§13，九条 ADR、八步整改、§7 门禁）、
> 审计报告 `docs/proposals/formula-management-platform-audit-2026-10-17.md`（第九/十/十二/十三节）。

---

## 0. tasks.md 开头须有的元信息段（wf-coder 必须先写）

tasks.md 文件顶部（任务列表之前）须包含如下引言段，逐项写入：

- **关联三件套**：requirements.md（20 条需求 EARS）+ design.md（九条 ADR、§5 八步、§7 门禁）。
- **锚点绑定声明**：本 spec 所有「现状 grep / 行号锚点」绑定 HEAD `4934142a1c221afb785cdfcddee8aaaba7fb7527`（design §0）。
- **实施前强制提醒（design §10）**：动任何生产代码前，必须先完成 Task 1（重做 §1 全部 20 条现状 grep 确认），逐条标「确认成立 / 已变化 / 需调整」；任一「已变化」先更新 design 对应锚点再动手。坐标漂移不报错、只会把补丁打错位置。
- **证据纪律（requirements 引言）**：严格区分「已坐实缺陷（改代码）」与「count=0 未证明（先诊断后决策）」；禁把 count=0 写成「重写/重建链路」。
- **仓库布局**：前端在 `audit-platform/frontend/src/...`，后端在仓库根 `backend/...`（非 `audit-platform/backend`）。
- **Phase 结构声明**：8 个 Phase 严格对齐 design §5 八步，顺序不可改；Phase 8（P2 治理）内任务可用 `*` 标记为可选/条件项（design §5 步骤 8 声明 ROI 不足可条件处置但须记录边界）。
- **验收纪律**：每个任务的「验收」须是可跑测试/门禁/对拍（取自 design §9 + §7 + 报告第十三节待办表「验收门禁」列），不以 grep 命中为验收；守卫须配变异反证（memory 铁律㉒㉖）。

---

## 1. tasks.md 任务骨架（逐 Phase）

> 每个任务统一四项标注：【需求】requirements 编号；【design 锚点】ADR-FMC-0x / §5 步骤 x / §1 #n / §7；【验收判据】可跑测试/门禁/对拍；【待办 ID】报告第十三节待办表缺陷 ID。
> 任务编号采用 `Phase.序号`（如 1.1、1.2），子项用 `.a/.b/.c` 或缩进复选框。

### Phase 1 · 步骤 1 P0 止错（串页 / surfaced 伪装 / 错保存域 / 字段误读）
> design §5 步骤 1（改动点 ①②③）、ADR-FMC-01/02；覆盖需求 1、2、13（wp 收敛）。

- **Task 1.1（前置·强制）· 实施前重做 §1 全部 20 条现状 grep 确认**
  - 【需求】贯穿（design §10 强制前置）
  - 【design 锚点】§0 锚点绑定、§1 #1~#20、§10、§11
  - 【验收判据】产出一张「20 条锚点 × {确认成立/已变化/需调整}」核实表（随当时真实 HEAD）；重点复核：前端是否仍 `audit-platform/frontend/`、后端是否仍在仓库根 `backend/`、`matchSheetCode`、`onFormulaEditSave` 的 `row.id` 分支、`_build_surfaced_formulas` 的 `readonly:True`、各端点鉴权依赖、`createOpenFormulaManagerCommand` 是否仍零生产调用、`stable_sheet_key` 是否仍可空且由 V163 新增/R163 回滚、`wp_code_overrides.json` 路径、`stable_key.py` 单一真源仍在。任一「已变化」先更新 design 锚点再继续后续任务。
  - 【待办 ID】全部（前置动作，不单独对应某 ID）
  - 备注：本任务是所有后续 Phase 的硬前置，必须最先完成。

- **Task 1.2 · 右栏串页修复（改动点 ①，ADR-FMC-01）**
  - 【需求】需求 1（1.1~1.4）、需求 13.1
  - 【design 锚点】ADR-FMC-01、§5 步骤 1 改动点①、§1 #1/#19；稳定键单一真源 `backend/app/services/formula_management/stable_key.py`
  - 【验收判据】单测：`matchSheetCode` 改为按 `stable_sheet_key`/`sheet_uid` 结构化精确等值，`E1-1` vs `E1-10/14/15`、`D2-1` vs `D2-10/12` 反例逐一判不串页；缺结构身份行 fail-closed 排除（不退 `includes`）；后端 `wp_formula.py` 公式投影须带 `stable_sheet_key`。变异反证：注入 `includes` 旧逻辑应打红反例用例。
  - 【待办 ID】FM-P0-01

- **Task 1.3 · 历史缺值行 stable_sheet_key 回填（改动点①附属，ADR-FMC-01 后果）**
  - 【需求】需求 1.4
  - 【design 锚点】§5 步骤 1 改动点①「回填为主、标注为过渡」；ADR-FMC-01「后果」；§9 集成可测
  - 【验收判据】一次性回填脚本复用单一真源 `stable_key.derive_stable_key`/`normalize_sheet_key`（禁另写规范化）；集成测试断言回填逻辑与 `derive_stable_key` 对同一 `(sheet_name, target_cell)` 产出一致；回填后仍无法解析身份的 `needs_review` 行才 fail-closed 排除，右栏标注「无结构身份已排除 N 行」。前端若本地归一，单测断言其结果与 `normalize_sheet_key` 对同一组 sheet 名（含带排序前缀、全角空格、大小写敏感 wp_code）产出一致。
  - 【待办 ID】FM-P0-01

- **Task 1.4 · surfaced/extraction 前端强制只读 + 保存按 kind 分派（改动点 ②，ADR-FMC-02）**
  - 【需求】需求 2.1、2.2、2.3、2.5、需求 13.1
  - 【design 锚点】ADR-FMC-02、§5 步骤 1 改动点②、§1 #2/#3
  - 【验收判据】单测：前端据后端 `readonly` 标志渲染只读（无「编辑」按钮、无「自定义/健康度100%」伪装）；`onFormulaEditSave` 保存链按 kind 分派——wp 行走 `wpFormula.upsert`（`PUT /api/workpapers/{wp_id}/formulas`）、surfaced/extraction 拒绝保存、report 行才走 `P_rc.detail`；后端 `save_formula` 对非 wp kind 拒收（纵深防御）。门禁变异：把 save 改回写 report_config 应被断言⑤c 捕获（见 Task 8.x）。
  - 【待办 ID】FM-P0-02

- **Task 1.5 · 字段名修正 formula_category/formula_description → category/description（改动点 ③，独立，MEDIUM-3）**
  - 【需求】需求 2.4
  - 【design 锚点】ADR-FMC-02「后果」独立改动点、§5 步骤 1 改动点③、§1 #2b、§7.2 断言⑤c、§9 单元可测
  - 【验收判据】单测断言：保存请求体字段 = 契约字段 `category/description`；右栏渲染读的是契约字段。此点独立于 kind 分派（即便分派正确，字段名读错仍致显示/保存错位）。
  - 【待办 ID】FM-P0-02

### Phase 2 · 步骤 2 统一入口（ADR-FMC-03）+ 10 个 classification 404 一次性归类
> design §5 步骤 2；覆盖需求 3、9。

- **Task 2.1 · 生产真正调用 createOpenFormulaManagerCommand + 统一 testid**
  - 【需求】需求 3.1、3.2、3.3、3.5、需求 9.1
  - 【design 锚点】ADR-FMC-03、§5 步骤 2、§1 #5/#16/#17/#18
  - 【验收判据】每个可渲染页恰一个 `data-testid=formula-manager-open`，点击调用统一命令提交完整 `CanonicalWorkpaperLocation`（projectId/wpId/wpCode/sheetUid）；删除 E1 页内第二按钮与 D4-33~36 node-only 旁路（或改为提交完整 location）；A1（`a1-dashboard`）与 Univer 主路径补同一 outlet。门禁断言①②③守护（见 Task 8.x）；变异「删按钮」命中①、「去 wp_id」命中③。
  - 【待办 ID】FM-P0-03、P1-A1/Univer 无入口

- **Task 2.2 · B15 redirect-materiality 正式豁免登记**
  - 【需求】需求 3.4
  - 【design 锚点】ADR-FMC-03、§5 步骤 2、§7.3
  - 【验收判据】`redirect-materiality` 登记为带 owner/reason/expires_at 的可伪证豁免（含「判据抽不到值」防空转断言）；并入 §7.3 门禁分母豁免登记。
  - 【待办 ID】FM-P0-03

- **Task 2.3 · 220 componentType 覆盖闭合 + 10 个 classification 404 一次性归类（实施期重算，MEDIUM-1 / NIT-2）**
  - 【需求】需求 3.5、需求 9.2、9.3、9.4
  - 【design 锚点】§5 步骤 2 404 归类子任务、ADR-FMC-03、§1 #20（`wp_code_overrides.json`）、§7.1/§7.3、§9 集成可测
  - 【验收判据】枚举 220 个声明 componentType，每项恰有「当前页入口覆盖」或「带期限正式豁免」，无未知未覆盖项；对**实施期当时真实项目**重跑 classification API 得出的 404 `wp_code`，逐个查 `wp_code_overrides.json`：命中→判「数据漂移」（记应补 override/classification 行，仍计入按钮分母）；未命中→判「口径外」（从 §7.1 分母显式剔除 + 登记带可验证理由字段的豁免）。清单**禁写死**、须现算（design §0/§5 步骤 2/§11 漂移纪律）。
  - 【待办 ID】FM-P0-03、P1-A1/Univer 无入口（含报告第四节 404 子类）

### Phase 3 · 步骤 3 左右栏契约收敛（ADR-FMC-01、ADR-FMC-05）
> design §5 步骤 3；覆盖需求 6。

- **Task 3.1 · 右栏服务端精确过滤 GET formulas?project_id&wp_id&sheet_uid**
  - 【需求】需求 6.2、需求 1.1（服务端口径）
  - 【design 锚点】ADR-FMC-01、§5 步骤 3
  - 【验收判据】后端 `GET formulas` 按 `project_id&wp_id&sheet_uid` 服务端精确过滤；每行带同一 location identity（projectId/wpId/sheetUid）。门禁断言⑤a 守护（右栏 stable_sheet_key 精确相等）。
  - 【待办 ID】FM-P0-01、P1-左栏非当前页地址

- **Task 3.2 · 左栏改为当前页 anchors + 显式全局浏览按钮 + 缺 identity fail-closed（ADR-FMC-05）**
  - 【需求】需求 6.1、6.2、6.3、6.4
  - 【design 锚点】ADR-FMC-05、§5 步骤 3、§1 #6（`loadAcnrTree/buildWpDomainTree/acnrDrivenTree`）
  - 【验收判据】左栏默认调 `GET addresses?project_id&wp_id&sheet_uid`（或等价 listCells），只显精确当前 sheet 的 `addr_id`；「全局浏览」作独立显式按钮、不作缺上下文默认回退；缺 location identity 时 fail-closed（告警 + 空集），不退全局树。门禁断言④守护（左侧 addr_id 全属精确当前 sheet）。
  - 【待办 ID】P1-左栏非当前页地址

### Phase 4 · 步骤 4 收敛权威源与执行语义
> design §5 步骤 4、ADR-FMC-04；覆盖需求 4、8、14、15（报表口径）。

- **Task 4.1 · 附注权威源收敛：execute_note_formulas 合并消费 _formulas ∪ _user_formulas（ADR-FMC-04）**
  - 【需求】需求 4.1、4.2、4.3、4.4、需求 14.1、14.2
  - 【design 锚点】ADR-FMC-04、§5 步骤 4、§1 #14/#15、§9 单元可测
  - 【验收判据】`execute_note_formulas` 合并消费两键；合并默认口径：同一目标单元格键冲突时用户集优先覆盖模板预设，拓扑排序对合并去重集合统一重算；单测构造「用户公式覆盖同键模板公式」样本断言覆盖 + 统一重算。中央弹窗附注节点改调 `list_note_formulas`（含用户集）。附注三端点鉴权保持不变（ADR-FMC-07，Task 不动）。若 §6.2 最小数据运行对拍出更合理口径，可在实施期调整并记录。
  - 【待办 ID】FM-P0-04

- **Task 4.2 · 函数支持矩阵禁静默 0（需求 8）**
  - 【需求】需求 8.1、8.2、8.3、8.4、需求 13.2
  - 【design 锚点】§5 步骤 4「函数支持矩阵」、§1（报告第三/五/九节）、§9 单元可测
  - 【验收判据】为每个函数（NOTE/REPORT/ROW/AUX/PREV/ADJ）按执行器维护「函数×执行器→支持/不支持」矩阵，覆盖 wp evaluator（真支持 TB/SUM_TB/WP）、report 路径（当前强制 PREV/AUX=0）、note 执行器、中央 batch（ADJ 实时注入）；单测：不支持者 UI 显式禁用/标注、禁点击后静默返回 0；支持者运行产生真实结果不以空 ctx 回退 0。
  - 【待办 ID】P1-函数按钮/运行不一致

- **Task 4.3 · 报表链口径澄清（按 distinct 模板计，不按项目克隆夸大）**
  - 【需求】需求 15.1
  - 【design 锚点】§5 步骤 4「report=report_config」、§3 数据流表「报表链」、深化 12.3
  - 【验收判据】文档化口径：报表链「生产实证」按 distinct 模板/标准计（≈82 条模板公式），不按项目数（6）夸大为 6 倍（6×82=492 是同一模板 6 份克隆）；`formula_push` 明确文档化为自动物化层、非权威定义源。（本任务以口径澄清 + 测试断言口径为主，不改模板范式。）
  - 【待办 ID】FM-P0-05（报表侧）

### Phase 5 · 步骤 5 项目鉴权与原子性（ADR-FMC-06、ADR-FMC-07）
> design §5 步骤 5、§6.1；覆盖需求 5、15（鉴权）、16（tb-detail 鉴权）。

- **Task 5.1（前置·先坐实）· FM-P0-05 跨项目越权 TestClient 坐实（§6.1，ADR-FMC-06）**
  - 【需求】需求 5.1、5.2、5.8
  - 【design 锚点】ADR-FMC-06、§6.1、§1 #4/#7/#9/#10/#11
  - 【验收判据】一条 TestClient 用例：以项目 A 凭据对项目 B 的 `wp_formula` 读/写、`report_config` 更新、`/api/formula/execute`、`formula-scope/{project_id}`、`tb_detail` 读/写发请求；加固前记录实际响应（预期多数 200 坐实 IDOR），加固后断言全部 403 且 0 副作用。用例须 `dependency_overrides` 内层 `get_current_user/get_db`（禁直接覆盖 `require_project_access` 工厂——每次返回新函数对象，覆盖静默失效，memory 教训㉕①）；鉴权口径穷举（避免漏判 `require_project_delegator`/`require_wp_edit_permission` 等别名）。若某端点加固前已 403，据运行时结果更新定级（需求 5.8），不继续按「已越权」处置。
  - 【待办 ID】FM-P0-05
  - 备注：本任务是 Phase 5 加固任务与门禁断言⑦的硬前置。

- **Task 5.2 · 对象型端点加固（对象 id 反查 project + require_project_access + body/query project_id 校验）**
  - 【需求】需求 5.3、5.5、需求 16.1、16.2
  - 【design 锚点】ADR-FMC-06、§5 步骤 5、§1 #4/#9/#11
  - 【验收判据】TestClient：`wp_formula`（list/save/delete）、`formula-scope/{project_id}`、`tb_detail` 读端补 `require_project_access("readonly")`、写端在 `require_role` 外叠加项目归属校验；路径只有 `{wp_id}` 的对象型端点先最小反查 `project_id` 再 `require_project_access`；body/query 的 `project_id` 与路径对象反查出的 project 不一致 → 403。附注端点不动（ADR-FMC-07）。
  - 【待办 ID】FM-P0-05、P1-缓存未隔离/传播（tb-detail 侧归 FM-P0-05）

- **Task 5.3 · 全局模板 / 全局自定义函数写限 admin（report_config CRUD + formula.py 注册/注销）**
  - 【需求】需求 5.4、需求 15.2
  - 【design 锚点】ADR-FMC-06、§5 步骤 5、§1 #7/#10
  - 【验收判据】TestClient：`report_config` 的 list/get/clone/update/create/delete/execute-batch 补 `require_project_access`（body/query project_id 同样校验）+ 全局模板写限 admin；`formula.py` 自定义函数注册/注销限 admin；非 admin 写/注册返回 403。
  - 【待办 ID】FM-P0-05（报表侧）

- **Task 5.4 · 批量单事务 + CAS + wp CRUD 写审计哈希链**
  - 【需求】需求 5.6、需求 13.4
  - 【design 锚点】§5 步骤 5、§8 错误处理（批量行数限额 + 单事务 CAS）
  - 【验收判据】批量保存单事务 + CAS；直接 `wp_formula` CRUD 写 `append_audit_log` 哈希审计链；TestClient 断言审计链写入。service 只 flush、router 统一 commit（memory 操作铁律）。
  - 【待办 ID】FM-P0-05

- **Task 5.5（条件项·不实施）· tb_detail 传播 FORMULA_CONFIG_CHANGED（NIT-3）**
  - 【需求】需求 16.3
  - 【design 锚点】§5 步骤 5「tb_detail 传播条件项」、§3 数据流表、NIT-3 响应
  - 【验收判据】本轮 tb_detail 真库=0、无传播需求，`FORMULA_CONFIG_CHANGED` 列为**条件项不实施**（`*` 标记），仅诊断发现需要时开；任务显式记录「本轮不实施 + 触发条件」边界。
  - 【待办 ID】FM-P0-05（tb-detail，复核发现）

### Phase 6 · 步骤 6 执行/传播可观测性
> design §5 步骤 6；覆盖需求 7（表间审核）、10（缓存/年份/单行 stale）、9（report-config/types）。

- **Task 6.1 · report-config/types 路由修复（§1 #8）**
  - 【需求】需求 9（report-config/types 侧）
  - 【design 锚点】§5 步骤 6、§1 #8、§8 错误处理表
  - 【验收判据】新增真实 `GET /types` 路由或前端改走正确端点，`/types` 不再被 `GET /{config_id}` 的 UUID 路由捕获为 422；TestClient 断言 `/types` 返 200 正确响应。
  - 【待办 ID】P1-表间审核契约错（关联 report-config/types）

- **Task 6.2 · report-cross-check year 必填 + 按执行结果解析 + 规则落库 + 树 key↔规则 map key 一致（MEDIUM-2）**
  - 【需求】需求 7.1、7.2、7.3、7.4、7.5
  - 【design 锚点】§5 步骤 6、§1 #13、§9 单元可测（树 key↔规则 map key 一致性）
  - 【验收判据】前端 GET 带 `year` 不再恒 422；前端按「执行结果」解析响应（非「规则列表」）；新增/编辑规则落库持久化（关闭再打开仍可见）；空结果显式「无结果」（不以静态示例冒充）；表间审核树父/叶节点 key 与规则 map key 用同一 key 生成，单测构造不一致样本应判失败。
  - 【待办 ID】P1-表间审核契约错

- **Task 6.3 · 缓存按 project key 隔离 + 单行保存触发统一 stale + 保存用项目年（需求 10）**
  - 【需求】需求 10.1、10.2、10.3、10.4、需求 13.3
  - 【design 锚点】§5 步骤 6、§9 集成可测（缓存按 project key 隔离、保存用 props.year）
  - 【验收判据】`report/note/cross-check` 缓存按 project key 隔离，切项目失效旧缓存、旧响应不覆盖新项目结果；「保存全部」与单行保存用 `props.year`（项目年）；单行保存触发与「保存全部」相同统一 stale 传播；ACNR GET abort 后重发不污染跨项目上下文。单测/集成断言缓存隔离与年份来源。
  - 【待办 ID】P1-缓存未隔离/传播

- **Task 6.4 · 每次执行写 run/issue/hint/outbox/audit 同 run_id + 去掉「执行 0 条仍成功」**
  - 【需求】需求 10（传播侧）、需求 11.4（run_id 贯穿，运行坐实在 Phase 7）
  - 【design 锚点】§5 步骤 6、§8 错误处理表（执行 0 条显式「无结果」）
  - 【验收判据】每次执行写 run/issue/hint/outbox/audit 且可查询、贯穿同一 `run_id`；去掉「执行 0 条仍成功」，0 条可执行时显式「无结果」。（落库逐值由 Phase 7 最小数据运行坐实。）
  - 【待办 ID】P1-缓存未隔离/传播

### Phase 7 · 步骤 7 + §6.2 最小数据运行（先诊断后决策）
> design §5 步骤 7、§6.2、ADR-FMC-09；覆盖需求 11、17、18、19。

- **Task 7.1 · standalone 一套最小数据运行坐实（需求 11）**
  - 【需求】需求 11.1、11.2、11.3、11.4、11.5
  - 【design 锚点】§6.2 standalone、§5 步骤 7、§9 最小数据运行可测
  - 【验收判据】在未删除 standalone 项目造一套隔离公式并保存 → 重开右栏与保存一致 → 执行使目标值改变、`last_computed_at` 更新 → `stale`/`formula_runtime_outbox`/audit 均带同一 `run_id`；以逐值对拍权威表为准，不看组件/mock。造数用幂等脚本、名称带可识别前缀、用完经项目回收站删除、探针放仓库外。
  - 【待办 ID】P1-正式运行数据为空

- **Task 7.2（两段式·先诊断）· consolidated 合并三类最小数据运行诊断（§6.2，ADR-FMC-09）**
  - 【需求】需求 17.1、18.1、19.1
  - 【design 锚点】§6.2 consolidated（12.5/12.6/12.7 表）、ADR-FMC-09
  - 【验收判据】在未删除 consolidated 项目造一套隔离合并公式 + 触发推送/重算，一次运行覆盖 12.5（`consol_report_values`）/12.6（`consol_note_data`）/12.7（随前两者同一运行）；逐值对拍并观察 `consol_push_run` 是否落库。产出诊断报告（落库/对拍结果）。**禁写「重写合并链」**。
  - 【待办 ID】三 consol 子节统一（12.5/12.6/12.7）

- **Task 7.3（两段式·后决策）· 合并三类据诊断结果决策**
  - 【需求】需求 17.2/17.3/17.4、18.2/18.3、19.2/19.3
  - 【design 锚点】ADR-FMC-09「结果分支」、§6.2 纪律
  - 【验收判据】据 Task 7.2 结果二分决策：落库且对拍一致 → 判「已打通（仅数据阻塞）」**不改代码**，记录结论；不落库/不一致 → 判「已断裂」，据失败点定位**最小改动**（禁预设重写整条链）并实施+复测。需求措辞禁写「重写/重建合并链」。
  - 【待办 ID】三 consol 子节统一（12.5/12.6/12.7）

### Phase 8 · 步骤 8 P2 治理收敛 + 全量门禁（可用 `*` 标记条件项）
> design §5 步骤 8、§7 全量门禁；覆盖需求 20、12。

- **Task 8.1 · 全量门禁 formula-manager-all-accessible-pages.spec.ts（需求 12，§7）**
  - 【需求】需求 12.1、12.2、12.3、12.4、12.5、12.6
  - 【design 锚点】ADR-FMC-08、§7.1/§7.2/§7.3/§7.4/§7.5
  - 【验收判据】项目 API 枚举全部可访问 `working_paper` → 逐张 GET render-config 展开「每真实 sheet + whole_workbook + redirect」形成运行时权威分母（每项记 project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType）；每非 redirect 项跑 8 条断言（①唯一入口 ②单弹窗 ③完整 location ④左栏精确 ⑤a 右栏精确/⑤b surfaced 只读去伪装/⑤c 保存契约字段+目标端点 ⑥切换隔离 ⑦权限分层-pending ⑧零错误）；redirect/口径外 404 用带 owner/reason/expires_at 可伪证豁免；幂等输出（§7.4：内容不变不改时间戳、排序稳定、无机器名/绝对路径、`--check` 不用 `--write`+diff、子进程 `PYTHONIOENCODING=utf-8`+`errors='replace'`+断言 stdout 内容）；四变异 + surfaced 变异各命中对应子断言（§7.5），每变异配反向断言。
  - 【待办 ID】P2-spec 归档 100%≠可靠（配套门禁）
  - 备注：断言⑦在 Phase 5（ADR-FMC-06 全部对象型端点加固 + Task 5.1 坐实）合入前标 skip/pending、不计入分母红；任一端点未合入则整条⑦保持 pending、不做部分硬化（NIT-2）。

- **Task 8.2* · 20.1 ≥7 套 local formula dialog/drawer 收敛或明确分工登记**
  - 【需求】需求 20.1
  - 【design 锚点】§5 步骤 8 · 20.1
  - 【验收判据】枚举 ≥7 套局部公式弹窗/抽屉，逐个登记「组件路径 + 当前权威源 + 去留决策（收敛进中央弹窗 / 保留但标注分工边界 / 废弃）」；能收敛者走 `createOpenFormulaManagerCommand`，保留者写明不收敛理由（权威源不同/UX 专用），禁「按钮同名、能力/权威源不同」的隐性碎片化。ROI 不足可 `*` 条件处置并记录边界。
  - 【待办 ID】P2-局部 dialog 碎片化

- **Task 8.3 · 20.2 两条历史假红/脆化前端测试修为反映真实行为 + 变异反证**
  - 【需求】需求 20.2
  - 【design 锚点】§5 步骤 8 · 20.2
  - 【验收判据】`FormulaManagerPageWiring`（竞态脆化：按序消费或显式等待对应请求）与 `formulaStatusPanelDisplay`（历史假红：更新期望为「HTML 面板已有入口按钮」）各修为反映当前真实行为（非放宽蒙绿、非删测试）；各配变异反证（注入对应真实缺陷仍能打红），避免恒绿。
  - 【待办 ID】P2-spec 归档 100%≠可靠

- **Task 8.4* · 20.3 formula_push 套件 1164 warnings 收敛（定位 Connection._cancel 根因）**
  - 【需求】需求 20.3
  - 【design 锚点】§5 步骤 8 · 20.3
  - 【验收判据】定位 `Connection._cancel was never awaited` 根因（异步连接取消未 await），在测试 fixture/连接管理处补 await 或改同步关闭；验收 = 套件 warnings 显著下降且无新增失败；不以 `-W ignore` 掩盖。ROI/环境受限可 `*` 条件处置并记录边界。
  - 【待办 ID】P2-门禁告警噪声

- **Task 8.5 · 20.4 RTK 吞失败退出码修正（复用 §7.4③ 口径）**
  - 【需求】需求 20.4
  - 【design 锚点】§5 步骤 8 · 20.4、§7.4③
  - 【验收判据】门禁子进程断言 stdout/stderr 含预期内容（非仅看 returncode），对 RTK 包装命令显式校验内层退出码或输出标志；变异：内层命令失败而 RTK 返 exit 0 时门禁应打红。
  - 【待办 ID】P2-门禁告警噪声

---

## 2. 覆盖自检

### 2.1 20 条需求 → 任务承接
| 需求 | 承接任务 |
|---|---|
| 需求 1 串页精确匹配 | 1.2、1.3、3.1、8.1(⑤a) |
| 需求 2 surfaced 只读+upsert+字段名 | 1.4、1.5、8.1(⑤b/⑤c) |
| 需求 3 统一入口/删 node-only/补 A1·Univer | 2.1、2.2、2.3、8.1(①②③) |
| 需求 4 附注用户公式可执行 | 4.1 |
| 需求 5 坐实并整改项目隔离 | 5.1、5.2、5.3、5.4、5.5* |
| 需求 6 左栏当前页地址 | 3.1、3.2、8.1(④) |
| 需求 7 表间审核契约 | 6.1、6.2 |
| 需求 8 函数支持矩阵禁静默 0 | 4.2 |
| 需求 9 A1/Univer 入口 + 404 归类 | 2.1、2.3 |
| 需求 10 缓存隔离/单行 stale/项目年 | 6.3、6.4 |
| 需求 11 最小数据运行坐实空数据 | 7.1、6.4(run_id) |
| 需求 12 全量门禁 8 断言+幂等 | 8.1 |
| 需求 13 底稿 wp 收敛 | 1.2、1.4、4.2、5.2、5.4（汇） |
| 需求 14 附注 note 收敛（不动鉴权） | 4.1 |
| 需求 15 报表 report 口径与鉴权 | 4.3、5.3 |
| 需求 16 试算表 tb 鉴权与传播 | 5.2、5.5* |
| 需求 17 合并报表先诊断后决策 | 7.2、7.3 |
| 需求 18 合并附注先诊断后决策 | 7.2、7.3 |
| 需求 19 合并底稿先诊断后决策 | 7.2、7.3 |
| 需求 20 碎片化/spec 状态/门禁噪声 | 8.2*、8.3、8.4*、8.5 |
**结论：20 条需求全部有任务承接，无遗漏。**

### 2.2 design §5 八步 → Phase 对齐
| design §5 步骤 | Phase | 任务 |
|---|---|---|
| 步骤 1 P0 止错 | Phase 1 | 1.1（前置 grep）、1.2、1.3、1.4、1.5 |
| 步骤 2 统一入口 + 404 归类 | Phase 2 | 2.1、2.2、2.3 |
| 步骤 3 左右栏契约 | Phase 3 | 3.1、3.2 |
| 步骤 4 权威源与执行语义 | Phase 4 | 4.1、4.2、4.3 |
| 步骤 5 项目鉴权与原子性 | Phase 5 | 5.1、5.2、5.3、5.4、5.5* |
| 步骤 6 执行/传播可观测性 | Phase 6 | 6.1、6.2、6.3、6.4 |
| 步骤 7 最小数据运行 | Phase 7 | 7.1、7.2、7.3 |
| 步骤 8 P2 治理 + 全量门禁 | Phase 8 | 8.1、8.2*、8.3、8.4*、8.5 |
**结论：八步全对齐，结构不改。**

### 2.3 design §7 全量门禁 → 任务
- §7.1 运行时权威分母、§7.2 八断言（含⑤拆 ⑤a/⑤b/⑤c、⑦ pending）、§7.3 豁免、§7.4 幂等三条、§7.5 四变异 + surfaced 变异 → **全部由 Task 8.1 承接**；断言⑦ pending 前置 = Phase 5 加固 + Task 5.1 坐实；变异映射到 Task 1.2(⑤a)/1.4+1.5(⑤b/⑤c)/2.1(①③)。
**结论：§7 门禁全要素有任务承接。**

### 2.4 报告第十三节 14 条待办 → 任务
| 待办 ID | 承接任务 |
|---|---|
| FM-P0-01 当前 sheet 串页 | 1.2、1.3、3.1 |
| FM-P0-02 surfaced 假可编辑+错保存域 | 1.4、1.5 |
| FM-P0-03 多入口丢上下文 | 2.1、2.2、2.3 |
| FM-P0-04 附注用户公式保存后不执行 | 4.1 |
| FM-P0-05 项目隔离缺失 | 5.1、5.2、5.3、5.4、5.5*（+报表侧 4.3、5.3） |
| P1-左栏非当前页地址 | 3.1、3.2 |
| P1-表间审核契约错 | 6.1、6.2 |
| P1-函数按钮/运行不一致 | 4.2 |
| P1-A1/Univer 无入口 | 2.1、2.3 |
| P1-缓存未隔离/传播 | 6.3、6.4、5.2(tb-detail) |
| P1-正式运行数据为空 | 7.1 |
| P2-局部 dialog 碎片化 | 8.2* |
| P2-spec 归档 100%≠可靠 | 8.3、8.1（门禁配套） |
| P2-门禁告警噪声 | 8.4*、8.5 |
| 三 consol 子节统一（12.5/12.6/12.7） | 7.2、7.3 |
**结论：14 条待办 + 三 consol 子节全部有任务承接，无遗漏。**

### 2.5 其他硬约束核对
- design §10 实施前重做 §1 全部 20 条现状 grep → **Task 1.1（Phase 1 首任务、强制前置）**。✅
- Phase 7 合并三类「先诊断后决策」两段式 → Task 7.2（诊断）+ Task 7.3（决策），禁「重写合并链」。✅
- P2（Phase 8）可用 `*` 标记条件项 → Task 5.5*/8.2*/8.4* 已标，并要求记录边界。✅
- tasks.md 开头元信息段（关联三件套 / HEAD 4934142a 锚点 / 实施前必重做 grep 提醒）→ 第 0 节已规定。✅

---

## 3. 给 wf-coder 的落笔提示
- 每个任务复选框后按 requirements.md 现有格式写「子项复选框」，并在任务行下用缩进列出【需求】【design 锚点】【验收判据】【待办 ID】四项标注。
- 验收判据一律写成可跑命令/测试名/对拍动作，禁以 grep 命中作验收；守卫须注明变异反证。
- `*` 任务（5.5/8.2/8.4）在任务标题后紧跟 `*`，并在验收判据里显式写「本轮仅登记/条件实施」的决策边界。
- 不在 tasks.md 里写死任何计数（220 componentType、82 模板、10 个 404、29 wp_formula 等均为撰写期快照，实施期须现算）。
