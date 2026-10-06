# 设计文档：合并企业树按三码自动构建

> 需求：#[[file:.kiro/specs/consol-tree-three-code-autobuild/requirements.md]]
> 迁移号：V167 / R167（2026-09-29 现扫 `backend/migrations` 最高 V166）
> 前置：合并四阶段已归档（`_archive/09-consolidation-phases/`）；本 spec 改的是它们共用的企业树与计算口径。

## 一、现状实证（2026-09-29 现读代码 + 真库 + 一次性探针）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 计算用树只认 `parent_project_id`，11 个合并服务都经 `build_tree` | `consol_tree_service.build_tree` + 全仓 grep |
| F2 | `parent_project_id` 写入点只有 4 处：批量导入、attach-subsidiaries、PATCH parent-code、连续审计（原样复制上年值 ⇒ 指向上年母项目） | grep `parent_project_id\s*=` |
| F3 | 向导三码只在「合并报表」时显示且无格式校验；`createProject` 只在合并时发送三码；向导回填不恢复三码 | `BasicInfoStep.vue` / `stores/wizard.ts` |
| F4 | 真库 8 个活跃项目上级代码、控制方代码全空；合并项目 0；抵销、差额表、合并试算均 0 行 | SQL 现查 |
| F5 | B1 汇总只取叶子，中间节点不含本体 ⇒ 母公司自身数据进不了合并 | `_collect_leaves` |
| F6 | 差额表按 `related_company_codes` 把一笔分录计到每个相关节点 ⇒ 两方抵销双计（探针：应 1000 实得 1200） | `_batch_load_eliminations` |
| F7 | 试算路径抵销取「借减贷」直接加到正数口径审定数 ⇒ 贷方性质科目方向反；单体调整分录已用 `resolve_account_direction` 归一 | `recalculate_trial` 对照 `trial_balance_service.recalc_adjustments` |
| F8 | 合并类型是项目上的单选，`branch` 时整体跳过抵销 | `recalculate_trial` / 基本信息表单 |
| F9 | 差额表科目只取分录表头代表科目；试算不为只出现在分录里的科目建行 | `_collect_account_codes` / `recalculate_trial` |
| F10 | 修改分录不更新明细行；读取单笔分录不排除软删 | `elimination_service.update_entry/get_entry` |
| F11 | 集团森林年度只看审计期末日（真库全空 ⇒ year=2025 得 0 棵树）；同代码合并与单体后者覆盖前者；`/api/projects/tree` 只校验登录 | `build_group_trees_from_projects` + 探针 |
| F12 | 合并页中栏自造「差额表」节点与手工「添加企业」；全部组件以 `company_code` 作键 | `ConsolMiddleNav.vue` / `OrgNode.vue` |
| F13 | 合并页取树失败时回退 `listChildProjects`，而后端项目列表不支持 `parent_project_id` 过滤 ⇒ 回退结果是全部可见项目 | `ConsolidationIndex.loadGroupTree` / `list_projects` |

## 二、节点模型

| 角色 `role` | 名称 | 类型 `kind` | 金额来源 | `project_id` |
|---|---|---|---|---|
| `consol` | {名称}（合并） | aggregate | Σ 直接子节点 | 合并项目 |
| `consol_elim` | {名称}（合并差额） | elim | 归属本节点的已审批分录 | 空；`host_project_id` = 承载分录的合并项目 |
| `parent` | {名称}（母公司） | 无分公司 data / 有分公司 aggregate | 母公司单体审定数 / Σ(母分差额+本部+分公司) | 无分公司时为单体项目，否则空 |
| `hq` | {名称}（本部） | data | 单体项目审定数 | 单体项目 |
| `branch_elim` | {名称}（母分差额） | elim | 归属本节点的已审批分录 | 空；`host_project_id` 同上 |
| `subsidiary` | {名称} / 有分公司时 {名称}（汇总） | data / aggregate | 同 `parent` | 同 `parent` |
| `branch` | {名称} / 有分公司时 {名称}（汇总） | data / aggregate | 同 `parent` | 同 `parent` |

- `node_key = {企业代码}:{角色}`，树内唯一；同一企业代码可以不同角色出现（合并户与母公司户）。
- `consol_worksheet.node_company_code` 改存 `node_key`（列宽 50，最长 18+1+11=30），列名不改。
- 关系标签（子公司/分公司）独立于角色展示；子节点顺序：差额节点 → 本企业节点 → 其余成员按（名称，代码）。
- 数据叶子缺项目（如母公司未建单体）仍生成节点，金额计 0，标诊断，不静默省略。

## 三、树构建（纯函数 + 薄 DB 装载）

### 3.1 候选集与企业实体
- 年度 Y = `resolve_project_audit_year(root)`；无法解析 ⇒ 只返回根节点并记诊断 `year_unresolved`（绝不跨年混建）。
- 候选集 = 同年度、未删、企业代码非空的全部项目（按 `resolve_project_audit_year` 再过滤一次）。
- 企业实体 = 按企业代码合并两个口径项目：`consol`（合并项目）、`standalone`（单体项目）。
  名称取单体项目客户名，缺失取合并项目。
- 实体集团关系（上级代码 / 控制方代码 / 与上级关系）取单体项目，单体缺失或其上级代码为空取合并项目；
  两者都非空且不一致 ⇒ 诊断 `relation_conflict`（取值规则仍为「单体优先」，确定性）。
- 关系为空而上级代码非空 ⇒ 按子公司处理并记诊断 `relation_defaulted`（树构建**不**做名称推断，只信落库值）。

### 3.2 关系边与异常
- 上级代码在实体集内 ⇒ 边 `上级 → 本企业`（带关系）；上级代码等于本企业代码 ⇒ 用户已确认「本企业就是上级企业」
  （需求 1.5），视为没有另外的上级：本企业是顶层，只出一个实体节点，不建自环边。三码相同时它就是最终控制方根。
  「有效上级代码」的判定只有一处：`group_relation.effective_parent_code`（前端 `effectiveParentCode` 同规则），
  树构建、关系默认、控制方补齐、批量预校验都调它，不各自比较字符串。
- 上级代码不在实体集内 ⇒ 脱挂 `detached`；若其控制方代码等于根企业代码，则作为根合并节点的直接成员展示，否则不入本树。
- 循环：沿上级链遍历检测；同一环内取企业代码最小者断开其上级边并标 `cycle_break`（与遍历顺序无关）。

### 3.3 构建规则（`E` 为实体；`figures(E, role)` 生成 E 的「本企业数据」节点）

```
consol_node(E):                                   # E 有合并项目
  E:consol ── [ E:consol_elim(host=E.consol),
                figures(E, "parent"),
                *members(E, host=E.consol) ]

figures(E, role):                                 # role ∈ parent/subsidiary/branch
  若 E 有分公司下级 B1..Bn:
    E:role(aggregate) ── [ E:branch_elim(host=当前承载合并项目),
                           E:hq(data, E.standalone),
                           *[figures(Bi, "branch") for Bi] ]
  否则: E:role(data, E.standalone)

members(E, host):                                 # E 的子公司类成员，挂在当前合并节点下
  对 E 及其分公司闭包内每个企业的「子公司」下级 S（按名称/代码排序）:
    S 有合并项目 ⇒ consol_node(S)
    否则 ⇒ figures(S, "subsidiary")，并把 members(S, host) 提升到当前合并节点，标 via=S
```

- 承载合并项目 `host` = 最近的外层 `consol` 节点的合并项目；因此同一企业的子树无论从哪一级根构建都完全相同（P6）。
- 没有集内上级的企业（未填、填为本企业、脱挂、断环）按最终控制方挂到其合并节点下（控制方须有合并项目）。
  挂靠边与上级边合起来仍可能成环（两家互为控制方、控制方其实是其下级）：沿「放置上级」检测，
  环内取有挂靠边的企业代码最小者不挂靠，记 `cycle_break`（实施时 3000 例随机探针抓到该 P6 反例后补）。
- 边角：分公司自己又建了合并项目 ⇒ 上级树仍把它折进母公司汇总（诊断 `branch_consol_ignored`），
  它的合并项目只在以它为根的树里展开；该分公司及其下级的派生链接按 §七 取「沿上级链最近的合并项目」，
  即该分公司的合并项目 —— 与上级树的放置位置不同，属双重消费，已知不改。
- 根项目不是合并项目 ⇒ 返回单一 data 节点并记诊断 `root_not_consolidated`（兼容旧调用方，不抛异常）。
- 每个单体项目恰好出现一次（P2）；实体只会以一个 `figures` 位置出现。

### 3.4 诊断（随树返回，前端提示）
`year_unresolved` · `root_not_consolidated` · `detached` · `cycle_break` · `relation_conflict` ·
`relation_defaulted` · `standalone_missing`（数据叶子无单体项目）· `via`（经中间企业间接持有，信息级）·
`orphan_entries`（分录找不到归属节点）· `link_mismatch`（库存 `parent_project_id` 与推导不一致）。

## 四、合并方式识别

对每个 `consol` 节点，统计其子树内全部成员实体的与上级关系：

| 子树内关系 | `mode` | 页面标签 |
|---|---|---|
| 只有子公司 | `subsidiary` | 母子合并 |
| 只有分公司 | `branch` | 总分汇总 |
| 两者都有 | `mixed` | 母子合并＋总分汇总 |
| 都没有 | `none` | 未识别到下级 |

- 两种并存时两类差额节点同时存在、各自计入（结构上就是两类节点，不需要额外分支）。
- 计算链路不读 `projects.consolidation_type`；列保留仅作历史，配置接口写入即 400。

## 五、计算口径

### 5.1 节点金额（逐科目 a）
- data：`TB(project_id).audited_amount[a]`（项目为空计 0）。
- elim：`Σ sign(a)·(借−贷)`，对归属本节点的已审批分录的**明细行**求和；`entry_type=other` 进调整列，其余进抵销列。
- aggregate：`Σ 直接子节点[a]`；自身调整/抵销列恒 0。
- 差额表行：`children_amount_sum` 仅 aggregate/data 有值；elim 节点 `net_difference = consolidated_amount`。

### 5.2 符号归一（与单体调整同源）
`sign(a) = +1` 若 `resolve_account_direction(a, name(a))` 为借方，否则 `−1`；`name(a)` 取数据叶子 TB 的科目名，
缺失取分录行科目名。差额表与试算两条路径调用同一函数，保证逐科目同值。

### 5.3 分录归属（唯一真源 `attribute_entry`）
- 装载范围 = 树内全部 `consol` 节点的合并项目 × 年度 × `approved` × 未删（多级合并纳入下级抵销）。
- `branch_entity_code` 为空 ⇒ `{承载项目企业代码}:consol_elim`；非空 ⇒ `{branch_entity_code}:branch_elim`，
  且该节点 `host_project_id` 必须等于分录 `project_id`。
- 找不到节点 ⇒ 孤儿分录：两条路径都不计入，诊断列出（P9）。`related_company_codes` 只作留痕与筛选。

### 5.4 科目集合与建行
科目集合 = 数据叶子 TB 科目 ∪ 已归属分录明细行科目。试算为只在分录里出现的科目建行（名称取分录行）。

### 5.5 旧行清理
全量重算后，差额表中 `node_company_code` 不在本次树 `node_key` 集合内的行软删（覆盖旧的纯代码键与已消失节点）。

### 5.6 两条路径恒等（P8）
`根.consolidated[a] = Σ数据叶子[a] + Σelim[a] = individual_sum[a] + consol_adjustment[a] + consol_elimination[a]`，
前提是两条路径共用同一棵树、同一归属函数、同一符号函数 —— 实现上把三者放进同一模块、两条路径只调它。

### 5.7 溯源
`consolidation_breakdown.by_company` 每行增加 `node_key` / `role`，按数据叶子逐行记录；合计仍等于 `individual_sum`。

## 六、数据层（V167 / R167）

| 对象 | 变更 |
|---|---|
| `projects.relation_to_parent` | `VARCHAR(20)` 可空，CHECK ∈ {`subsidiary`,`branch`}；ORM `Mapped[str \| None]` |
| `elimination_entries.branch_entity_code` | `VARCHAR(50)` 可空；ORM 同步 |
| 索引 | `ix_projects_group_parent (audit_year, parent_company_code) WHERE is_deleted=false`；`ix_elim_entries_project_year_branch (project_id, year, branch_entity_code) WHERE is_deleted=false` |
| `projects.consolidation_type` | 不动（历史列，不再读写） |

- 幂等：`ADD COLUMN IF NOT EXISTS`、约束用 `DO $$ … IF NOT EXISTS (pg_constraint)`、`CREATE INDEX IF NOT EXISTS`。
- 存量：真库上级代码全空、分录与差额表 0 行 ⇒ 无回填；R167 逆序删索引、约束、列。

## 七、派生链接 `parent_project_id`

- 定义：单体项目 ⇒ 本企业合并项目；本企业无合并项目 ⇒ 沿上级链最近的合并项目；合并项目 ⇒ 沿上级链
  （从上级开始）最近的合并项目；都没有 ⇒ 空。含分公司边与子公司边，遍历带访问集防环。
- 实现：`sync_group_links(db, year)` 对该年度全部项目一次性推导，只更新值有变化的行（与建项顺序无关，P5），
  返回受影响合并项目集合 ⇒ 广播 `consol.scope_changed` + 标记其合并试算陈旧。
- 调用点：建项、保存基本信息、PATCH 上级代码、attach-subsidiaries（改写三码后调用）、批量导入（整批一次）、
  连续审计建下年项目（新年度）、删除/批量删除、回收站恢复项目、修改报表类型、准则统一写报表类型。
- 同企业两口径互相同步（需求 1.8）：保存基本信息与 PATCH 上级代码 ⇒ 本项目值写到同代码同年度另一口径项目；
  建项时新项目为空的字段先继承另一口径项目；批量导入自动建的合并根只继承不外推。
- 运维：`backend/scripts/ops/resync_group_links.py [--year Y] [--dry-run]`。

## 八、接口变更

| 接口 | 变更 |
|---|---|
| `POST /api/projects`、`PUT /api/projects/{id}/wizard/basic_info` | 接收 `relation_to_parent`；上级/控制方代码非空须过 USCC；上级=本企业按顶层企业处理（关系置空、响应说明，不再 422）；关系为空按名称补默认；触发两口径同步与 `sync_group_links`；响应带 `notices` |
| `GET /api/projects/{id}` | 响应增加三码、名称与 `relation_to_parent` |
| `PATCH /api/projects/{id}/parent-code` | 同时写同企业同年度两口径项目，调用 `sync_group_links`，不再自己解析链接 |
| `POST /api/projects/{id}/attach-subsidiaries` | 改写下级项目上级代码=本企业、控制方代码=本企业控制方（空则本企业）、关系缺省按名称；再同步 |
| `GET /api/projects/{id}/available-subsidiaries` | 候选排除已在本树中的项目；结果带推断关系 |
| `DELETE /api/projects/{id}`、`POST /api/projects/batch-delete`、回收站恢复 | 完成后 `sync_group_links` |
| `PUT /api/projects/{id}/config` | `consolidation_type` 非空 ⇒ 400；`report_scope` 变化 ⇒ 同步链接；`GET` 不再返回 `consolidation_type` |
| `GET /api/consolidation/worksheet/tree` | 返回 `{tree, mode, diagnostics, year}`；节点含 `node_key/role/kind/display_name/relation/host_project_id/flags` 且保留旧字段 |
| `GET /api/consolidation/worksheet/accounts` | 新增：本树数据叶子与已有分录涉及的科目清单（差额录入选科目用） |
| `/aggregate`、`/drill/*`、`/pivot` | 节点参数按 `node_key` 解析，传纯企业代码时取该代码首个节点（兼容） |
| `GET/POST/PUT /api/consolidation/eliminations` | 增加 `branch_entity_code` 字段与按 `node_key` 筛选；创建/修改校验归属节点；修改同步明细行；读取排除软删 |
| `GET /api/projects/tree` | 按用户可见项目过滤；实体节点合并两口径；年度用统一解析；未传年度时按（控制方,年度）分树 |
| 批量建项模板/导入/预校验/导出 | 末尾追加「与上级关系(relation)」列（下拉 子公司/分公司）；旧 9 列文件照常导入 |

## 九、前端

- 基本信息表单：「集团架构」分组对所有项目显示；新增「与上级关系」下拉（上级代码为空或等于本企业代码时置灰、
  否则必填，默认值按共享规则随名称变化，手动选择后不再覆盖）；上级/控制方代码加 USCC 校验；
  上级代码等于本企业代码时保存前弹确认「本企业就是上级企业」（三码相同时改为「本企业即为最终控制方
  （集团总部或母公司）」），取消不保存，已确认或从已保存数据回填的同一组代码不再重复询问；
  移除「合并类型」单选；提示文案改为「合并项目的下级企业按各项目的上级代码自动识别」。
- 合并页：树只渲染后端推导结果，组件键 `node_key`，名称用 `display_name`，按角色区分图标与色块；
  头部「合并类型」单选改为只读识别标签 + 诊断提示；点击差额节点打开「差额分录」面板
  （列表/新增/修改/删草稿/提交审批/审批；承载项目非当前项目时只读并给出前往链接）。
- 中栏树：删除自造差额节点、「添加」与「同步」按钮及手工企业存储；事件载荷增加 `nodeKey/role/kind`。
- 合并工作底稿：公司列回退取「子公司类成员」（排除母公司与差额节点）；总分汇总提示改看识别结果。
- 集团架构森林/项目列表树视图/批量导入预览：节点显示关系标签与「合并/单户」口径标签。
- 配置合并范围弹窗：改为展示自动识别出的下级企业与关系，未识别时给出填写指引。

## 十、正确性属性

| # | 属性 | 测试形态 |
|---|---|---|
| P1 | 同一输入（项目集合任意排列）推导出的树（node_key 集合与父子关系）完全相同 | hypothesis |
| P2 | 每个单体项目在树中恰好出现一次；每个合并项目恰好对应一个 `consol` 节点；node_key 树内唯一 | hypothesis |
| P3 | 每个 `consol` 节点恰有一个 `consol_elim` 与一个 `parent` 直接子节点 | hypothesis |
| P4 | 有分公司的实体其本企业节点为 aggregate，且含恰一个 `branch_elim` 与一个 `hq` | hypothesis |
| P5 | `sync_group_links` 结果与建项顺序无关，且幂等（再跑一次零更新） | hypothesis + SQLite |
| P6 | 同一企业的 `consol` 子树从本级根与上级根构建完全相同（嵌套一致） | hypothesis |
| P7 | 每个 aggregate 节点金额 = 直接子节点金额之和（逐科目） | hypothesis |
| P8 | 差额表根合并数 = 试算合并数（逐科目，容差 0.01） | SQLite 真 ORM |
| P9 | 每笔已审批非孤儿分录只计入一个 elim 节点；孤儿分录两条路径都不计入 | hypothesis |
| P10 | 借方性质科目分录借 100 使合并数 +100；贷方性质科目分录贷 100 使合并数 +100 | 示例 + SQLite |
| P11 | 名称默认规则前后端对同一份用例清单给出相同结论 | pytest + vitest 共读夹具 |
| P12 | 旧 9 列批量模板导入结果与新模板空关系列一致 | pytest |
| P13 | 无分公司的母公司：报表母公司列与附注母公司章输出与改造前逐字节一致 | 特征测试 |
| P14 | `/api/projects/tree` 对非 admin/partner 只返回其参与的项目 | 端点测试 |

## 十一、架构决策

**ADR-CTREE-001 三码为唯一权威源，`parent_project_id` 降为派生值**
计算树改为实时推导、不存树结构；`parent_project_id` 保留给「所属集团」链接、陈旧标记、跨企业汇总等既有消费方，
由 `sync_group_links` 在所有写路径后按年度整体重算。否决「继续以 `parent_project_id` 为真源、补齐写入点」：
写入点散落 10 处，顺序相关（先建子后建母就断），且与三码两套真源必然漂移（F1/F2 即此）。

**ADR-CTREE-002 节点键 `code:role`，差额表列复用不改名**
合并户与母公司户同代码是模型的必然结果，节点身份必须含角色。列名 `node_company_code` 不改以避免迁移与
全仓改名；语义在模型注释与本设计登记。真库差额表 0 行，旧键行由 5.5 清理自然消化。

**ADR-CTREE-003 差额节点独占分录，`related_company_codes` 退出金额计算**
一笔分录的金额只属于一个差额节点（合并差额或某企业母分差额），由新字段 `branch_entity_code` 显式声明；
否决「按 related 推断归属」：两方抵销天然涉及两家企业，推断必然双计或需要任意规则（F6）。

**ADR-CTREE-004 合并方式由关系推导，取消单选**
单选无法表达「子公司与分公司并存」；推导值与下级填写的关系同源，不可能打架。`consolidation_type` 列保留不删
（历史数据与回滚安全），配置接口拒写以防新数据继续写入。

**ADR-CTREE-005 分录金额按科目自然方向归一**
试算与差额表的审定数都是正数口径，分录「借减贷」必须经 `resolve_account_direction` 归一后才能相加，
与单体调整分录同源（F7）。这会改变贷方性质科目上既有分录的合并结果 —— 真库分录 0 行，无存量影响。

**ADR-CTREE-006 母公司汇总只做本年数**
有分公司时母公司列/母公司章取汇总节点；上年数依赖上年合并结转（范围外），留空并注明原因，不填 0。

## 十二、风险与范围外

| 风险 | 处置 |
|---|---|
| 旧测试按旧语义断言（中间节点不含本体、branch 跳过抵销、parent_project_id 手工挂接） | 按新模型改写并在测试 docstring 注明是有意的口径变更；不以旧断言为正确性依据 |
| 前端差额分录面板是新入口，旧「合并抵消分录」表同步后端恒 422 | 旧表缺陷登记范围外；新面板走独立接口，不复用旧同步函数 |
| `ConsolNoteTab` 若干 URL 未插值 | 范围外登记；本 spec 只改其汇总树的节点键 |
| 批量导入按位置解析列 | 新列追加在末尾保持旧文件兼容（P12） |
| 真库无集团数据，合并计算真实 UAT 仍缺数据 | Playwright 实测用界面现造一个小集团，测后清理 |

**范围外**：旧「合并抵消分录」表同步 422、`ConsolNoteTab` URL 缺陷、上年合并数结转、持股比例与少数股东按节点重算、
`companies` 表写入口（真库无生产写入方）。

**实施中发现的预存缺陷（任务 3，2026-09-29 真库回滚探针复现）**

| 缺陷 | 处置 |
|---|---|
| 连续审计复制科目映射用了不存在的属性（`client_account_code`/`confidence` 等）⇒ 上年只要有映射，建下年项目即 500；真库 9 个未删项目里 7 个有映射（SQL 现查） | 已修（按 ORM 真实字段），真 SQLite 用例 + 变异咬住 |
| 连续审计第 8 步结转语句语法残缺（缺右括号与列清单、未传参），每次必失败；PG 事务内失败即中止事务，异常被吞后路由照常提交 ⇒ PG 把提交当回滚，新项目静默丢失而接口返回 200 | 已修：附注裁剪方案改 ORM 复制并放进 SAVEPOINT；源码守卫钉住「吞异常的库操作必须在 SAVEPOINT 里」 |
| 试算期初复制未按年度过滤 ⇒ 上年项目存有多年度行时撞唯一索引 | 已修（只取上年度行） |
| 程序实例（`procedure_instances`）结转从未生效：行内 `parent_id` 指向上年实例、`wp_id` 指向上年底稿、状态是上年执行结果，整行照抄会造出跨年引用 | **不结转**（与修复前实际效果相同），需单独设计 id 重映射与状态重置；`note_wp_mapping` 真库无此表，已删 |
| 全仓「try 里执行 SQL、except 吞异常、既无 SAVEPOINT 也无回滚」写法：AST 现算 1022 处 / 468 个文件（多为只读兜底，真实出错时才毒化同请求后续语句） | 平台级风险，规模超本 spec，只登记不改；本 spec 新写代码不引入该写法 |
| 回归清单内两条红与本 spec 无关：`test_parent_company_scope::test_parent_only_code_path_allowlist`（白名单只含 `wp_render_config.py`，`wp_render_pipeline.py` 自 2026-09-08 起也有该取值）、`test_parent_company_note_sourcing::test_parent_chapter_tables_carry_row_codes`（`note_template_listed.json` 2026-09-27 提交后缺 BS-005 行码） | 两文件本轮未改、工作树也未改，HEAD 即红；任务 13 动母公司口径前须先由对应 spec 修复或在此复核 |
