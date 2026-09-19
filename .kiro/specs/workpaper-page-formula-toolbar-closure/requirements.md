# Requirements Document

## Introduction

本 spec 收敛 **workpaper route 内** 的页面级公式入口、活动位置、公共能力壳层、AI 复核、人工复核和 right-rail。TB、报表、附注等独立业务域已有的 domain dialog 不属于本 spec 的“唯一全局管理器”范围，不得误删。

已确认红基线：`GtWpToolbar.vue` 只有 `.gt-wp-toolbar__right` CSS 容器，**没有 Vue slot**；当前 `OpenFormulaManagerPayload` 主要依赖 `nodeKey`；用户公式 batch API 是 `dict[cell_key, formula]`，没有 base version、逐项冲突和历史；`formula_type` 同时被用作函数名和业务分类；审计写失败只 warning 后继续 commit；多个 AI/review/rail 链和 fixed offset 并存。

本 spec 消费 guidance 的 `G-C0/G-ID/G-RAIL`，不复制共享 contract。它唯一拥有：

- `CanonicalLocationState` 的 runtime store/provider；
- workpaper route 的 `WorkpaperCapabilityShell`；
- 真实 toolbar outlets、页面级 FormulaManager owner、formula provider 聚合；
- review/guidance/AI right-rail DOM/CSS 仲裁。

后续 custom spec 只消费 `F-SHELL`，不能再建第二个 location owner、公式按钮、dialog 或 fixed rail。

## Requirements

### Requirement 1: workpaper host 清册与范围边界

**User Story:** 作为维护者，我希望先枚举真实 workpaper 宿主和 outlet 能力，再决定按钮位置，且不误伤其他业务域的公式对话框。

#### Acceptance Criteria

1. WHEN 生成 host capability inventory THEN 必须从 workpaper renderer registry、render-config、真实 mounted host adapters 与 runtime custom entries 推导，不写死页面数量
2. WHEN inventory 记录 entry THEN 必须包含 host kind、route scope、primary outlet、compatibility outlet、location granularity、formula/AI/review/rail capability、reason、source digest 与 evidence state
3. WHEN host/outlet/renderer dispatch 变化 THEN 旧 placement evidence 必须 stale 并重新裁决；grep 到 class、组件名或按钮文字不得作为 mounted capability
4. WHEN 检查唯一 FormulaManager THEN 范围仅为 active workpaper route；TB/report/note 等 domain-owned dialogs 明确列入 out-of-scope inventory，不得删除或计重复
5. WHEN reachable workpaper host 无可用 outlet/capability THEN 必须显示 BLOCKED reason、owner 和 remediation；不能以 fallback 到任意 DOM 节点伪装覆盖

### Requirement 2: C0 契约消费与唯一 runtime location owner

**User Story:** 作为公共能力提供者，我希望所有能力读取同一个稳定活动位置，且 owner 初始化、阻断和 ready 状态可区分。

#### Acceptance Criteria

1. WHEN 本 spec 启动 THEN 必须消费 `G-C0` 的 `CanonicalWorkpaperLocation/EvidenceEnvelope/GuidanceRailAdapter` 与 `G-ID`，不得复制同名 interface/schema
2. WHEN runtime location 尚未建立、被阻断或已就绪 THEN 必须使用 `CanonicalLocationState = uninitialized | blocked | ready`，不能用全空对象代表三种状态
3. WHEN workpaper owner 变化 THEN `ownerEpoch` 必须单调递增；同一 owner 内 identity/anchor 变化使 `contextRevision` 单调递增
4. WHEN initial/deep-link/wp/sheet/section/cell/host 变化 THEN 只能由 `WorkpaperCapabilityShell` 的 location reducer 发布 ready snapshot；host adapters 只 dispatch facts，不得成为第二 owner
5. WHEN location 无法证明 cell/sheet THEN 必须使用 C0 stable locator union 的 page/sheet/document/whole-workbook 边界；不得用 label、数组下标、旧 nodeKey 或 DOM 文本猜 identity
6. WHEN异步结果返回 THEN 只有 subject identity、ownerEpoch 和 contextRevision 全匹配才可落地；旧结果必须丢弃并可观测

### Requirement 3: capability/权限前置硬门

**User Story:** 作为平台管理员，我希望公式、AI 和复核能力在加载或执行前先得到服务端能力裁决，而不是功能完成后再补权限。

#### Acceptance Criteria

1. WHEN 进入 workpaper route THEN shell 必须先获取版本化 capability snapshot，覆盖 formula view/edit/history、AI review、AI assist、human review、guidance、artifact/location 范围与 disabled reasons
2. WHEN capability snapshot 尚未 ready、过期或与 owner epoch 不匹配 THEN provider 查询、保存、AI、review 和 rail action 必须 blocked；不能硬编码 true
3. WHEN 前端显示 disabled/hidden THEN 服务端 endpoint 仍必须复验 visibility、project/wp/sheet membership、role/capability 与 operation scope
4. WHEN 权限/项目成员/底稿状态变化 THEN 打开的 dialog/rail 必须 revalidate；旧 capability 不得持续到下一次刷新
5. WHEN capability 被拒绝 THEN UI 必须显示中文 reason、owner、next action 与可见期限，不泄漏无权公式、线程数量或 guidance 标题

### Requirement 4: 真实 ToolbarHostAdapter、命名 outlet 与仲裁

**User Story:** 作为底稿编制人，我希望公式入口确实挂到可渲染的工具栏位置，并在异步宿主挂载时仍保持唯一。

#### Acceptance Criteria

1. WHEN 公共 toolbar 提供能力位置 THEN 必须通过真实 Vue named slot/outlet 与 `ToolbarHostAdapter` 注册；`.gt-wp-toolbar__right` CSS class 不得被文档或实现当作 slot
2. WHEN 紫色主工具栏可用 THEN `ƒx 公式管理` 必须位于 AI助手之后、金额单位之前的 primary outlet，直接可见且不进入“更多”
3. WHEN primary adapter 尚在异步挂载 THEN 仲裁状态必须为 `pending`，compatibility 不得抢先渲染造成闪烁/重复
4. WHEN primary 明确 unavailable 且 compatibility adapter 已注册 THEN 才在 `GtWpToolbar` 的真实命名 compatibility outlet 渲染同一入口
5. WHEN primary/compatibility mount/unmount 或 owner epoch 变化 THEN arbiter 必须按 registration lease 重算；每个 active workpaper DOM 中入口恰好一个或明确 blocked
6. WHEN outlet registration 重复、过期或跨 owner THEN 必须拒绝并记录 collision，不得按最后挂载者静默覆盖

### Requirement 5: 唯一事件链、全局管理器与草稿位置

**User Story:** 作为审计人员，我希望任一入口只打开当前 workpaper route 的唯一页面级管理器，切页时不会把草稿写错位置。

#### Acceptance Criteria

1. WHEN 点击页面级入口 THEN 只能通过 shell command 打开 `ThreeColumnLayout` 既有的唯一 `FormulaManagerDialog`；业务组件不得挂第二份 dialog
2. WHEN command payload 生成 THEN 必须携带 C0 location snapshot 与 capability epoch；legacy `nodeKey` 只能作迁移 metadata，不能承担 identity
3. WHEN 页面级管理器打开 THEN 不得误开单元格级 `FormulaEditDialog`；后者仅是有权限条目的下钻编辑器
4. WHEN dialog 无 dirty draft 且 location 改变 THEN 可跟随最新 ready location 并重新加载
5. WHEN dialog 有 dirty draft 且 location 改变 THEN 必须 pin 原 location，显示位置变化并提供保存原位置/丢弃/取消；禁止把草稿静默重绑新 sheet
6. WHEN 当前位置没有已登记公式 THEN 显示真实 empty/partial/blocked 状态和下一步，不构造占位公式行

### Requirement 6: 正交 provider descriptor 与聚合结果

**User Story:** 作为现场经理，我希望在一处看清不同来源、规则类型、执行引擎和保护级别，而不是由一个混合枚举掩盖差异。

#### Acceptance Criteria

1. WHEN 注册 provider THEN descriptor 必须正交区分 `origin`、`rule_kind`、`engine`、`protection`，不得用 platform/user/logic/frontend 混成单一 `FormulaSource`
2. WHEN 聚合现有真源 THEN 至少覆盖 platform formula、user formula、auto_data_source、logic/reasonableness checks、frontend formula engine 五类 adapter，且不复制其权威存储
3. WHEN descriptor 返回 THEN 必须含 stable formula id、stable target/location、`formula_function`、`rule_category`、表达式/摘要、refs、值状态、override、version、owner、updated metadata 与 provenance
4. WHEN 多 provider 返回同一 stable id THEN 只有语义 digest 相同才可按声明 precedence 合并；不同语义必须 collision blocked，不能取第一条
5. WHEN provider 超时/失败/不支持当前粒度 THEN `AggregateResult` 必须标 complete/partial/blocked、逐 provider verdict、errors/collisions 和 retry；其他 provider 结果可见但不能伪装 complete
6. WHEN location 只有 page/sheet 粒度 THEN provider 只能查询可证明范围；不得选择第一行、默认 section 或空 target 猜测

### Requirement 7: 值、影响面、保护与 stale

**User Story:** 作为质量控制复核人，我希望每条规则能追到输入、输出、保护原因和失效影响。

#### Acceptance Criteria

1. WHEN 展示 descriptor THEN 必须显示 current value/status、calculated_at、project/year/standards/dataset fingerprint 与 manual override
2. WHEN formula 有地址关系 THEN 必须通过 ACNR/linkage bus 展示 upstream/downstream/cross-workpaper refs/stale，并使用安全 location 跳转
3. WHEN ACNR、resolver 或依赖服务降级 THEN 必须显示 partial/unavailable reason，不能返回空数组成功态
4. WHEN protection 为 protected/system_managed THEN UI 必须显示 owner 与保护原因；普通用户不能通过 user mutation API 改写
5. WHEN source/version/target/context fingerprint 变化 THEN descriptor、current value 与 evidence 必须 stale；相同 label 不得复用旧 identity

### Requirement 8: v2 用户公式 mutation、冲突、历史与审计

**User Story:** 作为获授权编制人，我希望逐项保存用户公式，冲突和部分失败不丢草稿，历史可恢复。

#### Acceptance Criteria

1. WHEN 调用用户公式 API THEN 必须使用 versioned v2 resource/command contract；现有 `dict[cell_key, formula]` 旧 API 不得承载新语义
2. WHEN 创建/更新/删除/恢复 THEN 每项必须携带 operation id、action、stable target/location、formula function、rule category、expression/refs、base item version 与 reason
3. WHEN formula function 与业务分类传输 THEN 必须使用不同字段；响应函数名 `TB/WP/...` 与数据库分类 `auto_calc/logic_check/reasonability` 不得继续共用 `formula_type`
4. WHEN batch mutation 执行 THEN 返回逐项 success/conflict/forbidden/invalid/error、server version 与 field conflicts；overall status 明确 success/partial/failed
5. WHEN base version stale 或部分失败 THEN 保留对应草稿并支持刷新/对比/重试；成功 toast 不得覆盖任一 4xx/5xx
6. WHEN mutation 成功 THEN durable audit/outbox 必须与变更同事务或同一 commit gate；审计写失败不得 warning 后继续 commit
7. WHEN 查看/恢复历史 THEN 必须按 project/wp/location/formula id 返回 immutable versions；恢复创建新版本，不覆盖历史

### Requirement 9: AI review、AI assist 与重复链清理

**User Story:** 作为审计师，我希望 AI 复核和 AI 辅助对话概念清晰、范围准确，业务区不再重复挂载。

#### Acceptance Criteria

1. WHEN shell 声明 AI actions THEN 必须分离 `ai_review_page/ai_review_batch` 与 `ai_assist_chat`；人工 review 和生命周期提交复核也保持独立 taxonomy
2. WHEN 页面支持 AI review THEN 只保留公共 `GtWpAiReviewToolbar` 的直接可见入口；业务内容区同名按钮、local refs、handlers 和重复 ReviewPanel 必须成组删除
3. WHEN 发起 page/batch AI review THEN scope 必须来自最新 ready location 或显式 selection snapshot，并绑定 owner/capability epoch
4. WHEN使用 AI assist THEN 只能通过公共 DSH adapter/PlatformAiChatPanel 链，不得由 guidance 或 WorkpaperEditor 再裸挂第二条链
5. WHEN capability 不允许或 host 不支持 THEN 显示具体原因；不得静默 no-op 或借 AI assist 权限调用 AI review

### Requirement 10: 人工 review provider、线程键与迁移

**User Story:** 作为五类复核角色，我希望线程稳定绑定原 sheet/anchor，并在旧键迁移后不丢失或串页。

#### Acceptance Criteria

1. WHEN active workpaper 可复核 THEN shell 必须恰好挂载一份 `GtWpReviewRail`，HTML、Univer、OnlyOffice、Grid、Word 共用 provider scaffold
2. WHEN 创建线程 THEN canonical key 必须包含 `project_id + wp_id + sheet_uid-or-whole + anchor_id`；label、数组下标和旧 nodeKey 不承担身份
3. WHEN迁移 legacy thread keys THEN 必须先生成 deterministic mapping/collision/orphan report，再幂等迁移并保存 rollback evidence；冲突不得静默合并
4. WHEN创建、回复、关闭、重开或刷新 THEN 线程必须耐久并绑定原 canonical key；切 location 不得串线程
5. WHEN 五角色操作 THEN 服务端 capability matrix 必须分别验证 create/reply/resolve/reopen/read；无权时可解释禁用
6. WHEN host 无稳定细粒度 anchor THEN 使用 page/sheet/document/whole-workbook anchor 并明确粒度，不能伪造 cell thread

### Requirement 11: WorkpaperCapabilityShell 与 right-rail 唯一所有权

**User Story:** 作为底稿用户，我希望 review、guidance、AI 入口和展开面板统一仲裁，不重叠、不重复、不遮挡编辑区。

#### Acceptance Criteria

1. WHEN shell 组合公共能力 THEN 它必须是 location runtime、toolbar outlets、global dialog command、capability snapshot 与 right-rail arbiter 的唯一 owner
2. WHEN接入 guidance THEN 只消费 `G-RAIL` 的 adapter；不得重定义 adapter 或让 guidance 写 shell offset
3. WHEN接入 AI/human review THEN AI 只走 DSH adapter，human review 只走统一 provider；每个 adapter 有 stable id、visibility、reason、draft 与 epoch
4. WHEN panel 展开 THEN 同时最多一个 open；切换保留各自草稿，visible=false/epoch stale 项不渲染且不占 slot
5. WHEN shell 布局 THEN 固定 review→guidance→ai 逻辑顺序，但所有 DOM、gap、top/right、z-index、panel width、content inset 与 responsive CSS 只由本 spec 拥有
6. WHEN custom workpaper 接入 THEN 只能注册 host facts/outlet/anchors/providers 并消费 `F-SHELL`；不得复制公式按钮、dialog、location store 或 fixed rail

### Requirement 12: 响应式、可访问性、错误与可观测性

**User Story:** 作为不同屏幕和键盘用户，我希望公共壳层可达且失败可见，同时不泄漏敏感公式。

#### Acceptance Criteria

1. WHEN viewport 为 1280/1440/1920 或文字缩放 200% THEN toolbar、rail、表格、输入区和底部操作不得重叠；内容 inset 由 shell 统一计算
2. WHEN 使用键盘 THEN outlets、dialog、rail 和线程操作必须有中文 accessible name、可见焦点、合理 tab 顺序、Escape、scroll lock 与 return focus
3. WHEN provider/save/review/adapter/location 失败 THEN UI 保留当前工作并显示结构化中文错误；broad catch 后 success 不允许
4. WHEN记录 telemetry/audit THEN 包含 correlation、canonical subject、operation/provider、epoch/version 与 verdict，但不记录 token、完整敏感表达式或附件正文
5. WHEN Word host 可达 THEN 必须纳入 mounted/Playwright 证据；只有具备 owner、期限和来源 digest 的正式 exemption 才能暂不支持，不能从分母消失

### Requirement 13: 跨 spec、行为验证与完成门

**User Story:** 作为项目负责人，我希望共享依赖、真实挂载、变异和浏览器证据共同决定完成，而不是代码中出现一个按钮就结束。

#### Acceptance Criteria

1. WHEN tasks 编排 THEN 必须显式声明 `G-C0→F1`、`G-ID→location runtime`、`G-RAIL→shell integration` 以及 `F-SHELL→custom UI/runtime`，不得隐藏在段落中
2. WHEN 建立自动化守卫 THEN 必须覆盖 inventory、location state/reducer、capability gate、outlet registration/arbitration、dialog/draft、provider aggregation、v2 mutation、AI taxonomy、review migration 与 rail arbiter
3. WHEN 运行变异 THEN 至少覆盖把 CSS class 当 slot、fallback 抢挂、payload 丢 stable location、dirty draft 跟页、provider 维度混用、collision 取首项、旧 dict API、审计 warning commit、重复 AI、legacy thread key、visible=false 占位；每项准确 RED
4. WHEN 运行 Playwright THEN 必须覆盖所有 reachable HTML/Univer/OnlyOffice/Grid/Word workpaper hosts、首次/切页/定位、权限变化、五类 provider、保存冲突、AI/review/rail、三档 viewport
5. WHEN 保存 evidence THEN 必须使用 C0 `EvidenceEnvelope`，包含 location/capability epoch、network、DOM 唯一性、trace、截图、console、角色和版本
6. WHEN 宣称 closure THEN required hosts 已裁决，入口/manager/AI/review/rail 重复为 0，unconsumed adapter/stale evidence 为 0，v2 API/audit/权限全闭环，正式产物 tracked 且 clean checkout 可复现

### Requirement 14: 页面真实接线补验

1. WHEN 打开底稿 THEN GtWpRenderer 在 page-capabilities-compatibility 插槽、关联附件之前提供公式管理入口；本次指定位置优先于 R4 历史 primary 放置规则。
2. WHEN 点击入口 THEN 复用 ThreeColumnLayout 唯一 FormulaManagerDialog，传真实 wpId/projectId/year/wpCode/sheetName，不按编码反查实例。
3. WHEN 弹窗打开 THEN 默认当前底稿全册，显示来源位置，清除上次分类、搜索和选择；sheetName 不隐式过滤全册。
4. WHEN 查询失败或上下文缺失 THEN 中文明确显示错误；切换、关闭或重开后旧请求不得覆盖新结果及 loading。
5. WHEN 用户公式 tab 加载 THEN 使用真实 wpId；确认操作期间位置变化不得错删新底稿。
6. WHEN 验收 THEN 定向行为测试并尝试 localhost:3030 Playwright；登录或环境阻塞如实登记，不继承历史全绿。

## Glossary

| 术语 | 含义 |
|---|---|
| `WorkpaperCapabilityShell` | workpaper route 内 location、toolbar、dialog command、capability 与 right-rail 的唯一 runtime owner |
| `ToolbarHostAdapter` | 向 shell 注册真实 mounted named outlet 的宿主适配器 |
| primary outlet | 紫色主工具栏中 AI助手后、金额单位前的真实命名挂载点 |
| compatibility outlet | 仅在 primary 明确不可用时，由 `GtWpToolbar` 提供的真实命名挂载点 |
| `CanonicalLocationState` | `uninitialized/blocked/ready` 的 runtime 状态；ready 内含 C0 location snapshot |
| dirty draft pin | dialog 有未保存草稿时固定原 location，不自动跟随页面 |
| `F-SHELL` | 本 spec 向 custom 提供的已验证公共壳层里程碑 |
