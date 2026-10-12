# 需求：D2 在线编辑恢复与「任意企业首次打开」平台闭环

spec：`d2-online-edit-platform-closure` · 2026-10-10 新建

## 背景

用户在 D2 应收账款「明细表D2-2」点「在线编辑」进不了 OnlyOffice，并明确要求：修平台，不是逐个企业修。
2026-10-10 现场排查确认是 6 个平台缺陷叠加（证据与链路见 design §1；R1~R9），验收期又逐条暴露 14 个（R10~R21，含 R13b / R13c；design §7），其中第 6 条决定了「修一次是否对所有企业生效」：
平台目前只给每个 entry 的**一张**底稿（canary）发布过首版 representation，生产代码里**没有**运行时首版路径 ——
其他企业点在线编辑必然得到 `materialize_substrate_not_published`。

## 需求

**R1 注册链不因单个 provider 的编码错误整体崩溃**
1. N1/N2/N3/N5 的 `attach_adapters` 必须调用 L 循环骨架真实存在的 `attach_l_entry_adapter`（与 N4、L1~L8 同形）。
2. 新增守卫：`backend/app/services/workpaper_sync/` 下所有「模块别名.属性」访问（含函数体内延迟 import）必须能在目标模块上解析；配变异证明（改回 `_L.attach_adapters` 必红）。

**R2 发布链冻结的 instrumentation 必须覆盖契约声明的全部受管 sheet**
1. D2 发布链（`publish_pilot_definitions`）发布的 instrumentation 走复数 `instrumentation_specs()`，覆盖 `d22-managed` / `d23-managed` / `d21-managed`。
2. D2 契约内嵌的 `instrumentation_definition_sha256` 与发布链同源（复数）；磁盘契约重新生成并通过 `--check`。
3. 新增守卫：对每个已交付 provider，用记录型 publisher 跑一遍真实发布链，断言「契约 sheet_key ⊆ 实际发布的 instrumentation 声明的 sheet_key」；配变异证明。

**R3 attach 构造的 adapter 必须带兄弟受管区 binding**
1. 编排工厂允许 provider 注入复数 specs；注入时 attach 调用 `attach_sibling_bindings`，与发布链同一对齐内核。
2. 未注入的 provider（D3/D5/D6/D7/K/M 等单 sheet）行为逐字节不变。

**R4 兄弟受管 sheet 的跨表引用按声明逆替换**
1. 某受管 sheet 本身无行变更、但被工作簿级行传播**按声明**改写了引用（D2-1 的 `SUMIF('明细表D2-2'!…$25)` → `…$754`）时，未管理区域校验对该 sheet 的单元格与结构块按同一份声明逆替换后再比对。
2. 声明之外的任何改动（值 / 样式索引 / 公式）仍判漂移；单元格 digest 仍包含样式索引 `s`。
3. 有自身行变更（`row_shift` 非空）的 sheet 不走本归一化（避免与位移归一化重复）。

**R5 新 representation 的 generation 不得落在已不可复用的 room 代际上**
1. 新 content version 的候选代际 = entry pointer 当前代际（无 pointer 时为 1）；候选代际的 room 不存在或可复用 ⇒ 沿用；已不可复用（state 不在 opening/active/close_barrier，或 refresh-required）⇒ 取 entry 全局 `max(rep, room)+1`。
2. 「不可复用」的判定与 `RoomService.open_or_reuse_room` 共用一份实现。
3. G7 / D4 的「无条件 max+1」保留不变。
4. （设计期补充）materialize 打开的当前代际 room 已**终结**（superseded / closed）时，materialize 为同一 content version 换代（revision 不变、artifact 与 bundle 复用、doc_key 换掉）后照常发 descriptor；与「僵死写会话」既有换代路径共用 `_rotate_generation_for_stale_room`。
5. 非终态的拒绝（refresh-required / closing / recovery-required）不换代，按 R6 透出。

**R6 materialize 遇 room 不可写返回 409**
`RoomNotWritableError` 登记进 materialize 拒绝码表，HTTP 409，消息为后端中文原因；前端生成契约同步。

**R7 任意企业首次打开在线编辑自动生成首版**
1. 新写端点 `POST {USER_SYNC_PREFIX}/first-publication`，action `ensure_first_publication`（登记为写 action，workflow 锁定下拒绝，鉴权链与 materialize 同）。
2. 服务复用 `resolve_plan` + `stage_instrumented_substrate` + `publish_first_generation`；不新增第三条 representation 写入路径，不放宽任何判据。
3. 幂等：已有 current representation 返回 `already_published`；并发重复发布被 revision CAS 拦下后，复查指针存在即按 `already_published` 返回。
4. store 读取与 store-projection 共用一份实现；store 为空且 provider 无空载荷合法状态（`EMPTY_STORE_PAYLOAD is None`）时 422 + 中文原因。
5. 前端桥在 materialize 返回 `materialize_substrate_not_published` 时调用该端点**一次**，成功后从 flush 重新走完整链路；失败显示后端中文原因，不进入编辑器。
6. 端点级测试（TestClient 真发请求）覆盖：未登录 401、无项目权限 403/404、已发布幂等、首版成功、空 store 422。

**R8 数据**
1. 参考 representation（和平药房_2025 的 D2）走正规链重发布：生成契约 → provision → rematerialize，**不绕过任何校验**。
2. 恢复 2026-10-10 误改的 bundle `0c8426e6` 的 `approved_at`。

**R9 验收（真栈 + 浏览器）**
1. 和平药房_2025、重药控股安徽_2025 两家的 D2-2 点「在线编辑」均进入 OnlyOffice（后者走 R7 首版）。
2. OO 里改一格并保存，切回结构化视图能看到改动（OO→HTML）。
3. HTML 改一格，再进在线编辑能看到（HTML→OO）。

## 需求（验收期新增，2026-10-11 真栈逐条暴露）

R1~R8 修完后按 R9 真栈验收，每一轮都在更靠后的环节撞上新的平台缺陷（链路与证据见 design §7）。
以下各条全部落在**所有 entry / 所有企业共用**的路径上，修一次即对全部企业生效；逐企业的只有数据处置（R8 及 design §7.4）。

**R10 OO 重算的受保护字段按「分」比较**
1. 公式字段与 formula mask 内的格（OO 打开时会重算）：金额两侧按分（0.01，四舍五入）取整后相等 ⇒ 不是篡改：保留 current、零冲突、不要求客户端重载。
2. 差一分及以上仍判 protected 冲突；auto-source 字段（OO 不重算）保持精确比较。
3. 可编辑字段不走本规则：OO 不重算它们，任何差异都是用户真改的；按两位取整会吞掉用户多录的小数位。
4. 非金额数值（rate / ratio / percent_points）不按两位取整，只吸收 15 位有效数字以外的 float 尾差。

**R11 store 镜像对 provider 硬取的属性，注册表里每个 plan 都必须真有**
1. 多 store item 型 provider（D2 bridge）补齐镜像会无保护解引用的 item 清单与整体 merge 函数。
2. 守卫按全注册表逐 plan 参数化；镜像新增无保护解引用点而模型未跟上时先红。

**R12 模板骨架行在 OO→HTML 镜像里的去留**
1. 模板原样的骨架行（D2-2 `GTROW-D22-*`、D2-3 个别 / 组合区）不建 store 行。
2. 用户在骨架行里填了内容 ⇒ 照常镜像（不静默丢数据）；base 里已有的骨架行照常更新。
3. 组合区「无 category 不猜」的 fail-closed 不放宽。

**R13 新内容不得沿用已被编辑器确认打开过的代际**
1. 不随会话的提交（HTML→OO 物化，`plan.room_id is None`）：候选代际的 room 已有 client-confirmation ⇒ 换代。
2. 随会话的提交（OO→HTML）沿用会话所在代际；room 不存在 / 从未确认 ⇒ 沿用；终态 room 与 G7/D4 既有行为不变。

**R13b 回写落地后回表单释放 participant lease**：`reloadAfterApplied()` 调用与 clean close 同一个 leave 端点；dirty 照实上报（不写死 false）；leave 失败不阻断回表单、不记 lastError。

**R13c 「保存并回到表单模式」落地后自动回表单**：本宿主发起的保存落地（applied）且编辑器无新改动 ⇒ 短暂停留后自动回表单；落地后又改过 ⇒ 留在编辑器；宿主卸载即取消。改在共享宿主组件，所有循环同时生效。

**R14 请求期 adapter 绑在目标底稿自己的 current representation 上**
1. entry 级注册之上按「目标底稿 + representation」绑定，两家企业交替请求各用各的冻结身份（行身份清册 / tombstone / 动态列绑定）。
2. provider 绕过共享解析器 / 两次读取之间并发发布 / 目标不可见 ⇒ fail closed，不回落到别家企业。
3. 生产三个调用点（同步请求 / callback apply / prewarm）都按本请求的底稿绑定。

**R15 entry 级注册缓存的指纹不随「保存」变**：指纹 = entry pointer 集合 + 指针所指 representation 的 bundle；同 bundle 的新代际（每次保存都会产生）不变，首版发布 / bundle 重发布才变。

**R16 callback apply 复用同一份 entry 级注册缓存**：命中跳过冷建、未命中照常冷建；绑定失败按既有失败分类落库，不冒出 apply。

**R17 OO 里清空的可编辑格必须回写 HTML store**
1. 镜像视图对「进过三方 merge、最终 projection 缺失、xlsx 行域可编辑未受保护、所在行仍存活」的键补显式 null。
2. 发布出去的 projection 不变；docx 不适用（键缺失可能是真实的载体删除）。

**R18 同一页面连续两次在线编辑保存都能落地**：每次进入在线编辑（flush 开始）重置上一会话的 operation 观测面与 canonical application 围栏；同一会话内换了 canonical application 仍判 rebase（围栏本身保留）。

**R19 application 落终态 ⇒ 绑定的 forcesave request 同事务终结**（代码与测试里编号 `D1`，与 design §3 的决策 D1 无关）
1. 映射单源 `REQUEST_STATE_FOR_TERMINAL_APPLICATION`：applied / refresh_required → terminal，superseded → superseded，authorization_stale → authorization_stale；error / conflict 不结算（仍可重试 / 裁决）。
2. 覆盖 origin request ∪ primary 与折叠 duplicate shell 的 request；已终态跳过；写 `finished_at`；锁序 room → request。
3. 全部 application 终态写入方（协调器单一写入点、`supersede_application`）都结算；operation 终态写 `finished_at`；`terminate_without_callback` 与撤销取消补 request `finished_at`。
4. 历史滞留数据用正式工具处置（委派生产结算函数，不另写一套 SQL 规则）。

**R20 切「在线编辑」前，HTML 侧尚未落库的编辑必须先落库**
1. 双向桥在每次调用宿主 `flushHtml` 之前等待全部已登记的待写盘：防抖型写入方（子 Tab 私有防抖）立即发起写入，在途写入等到返回；失败不阻断切换（失败由写入方自己提示）。
2. 注册表是平台模块（不随循环各写一份）；H 循环既有的 `hPendingWrites` 改为它的别名，共用同一张表。
3. D2 全部「私有防抖 + 写盘」的子 composable 登记；宿主注入给子 Tab 的保存函数追踪在途写入。
4. 其余循环同形写入方现算冻结为棘轮（新出现即红、接入后必须从表里删）。

**R21 事件驱动的 operation 补读失败不得变成未捕获 rejection**：与轮询定时器同口径吞掉（下一次轮询 / 事件会再读，快照去重兜住）。

## 非目标

- 注册日志里另外 7 条 entry 失败（F2 盘点 / G6 / K1 / K2 / K4 / K6 / M9），只登记分型，不在本 spec 修。
- 「参考 representation 选择」的脆弱性（见 design §5 风险 2），只登记。R14 之后请求期按目标底稿重绑，但 entry 级冷建仍取全序第一张可见底稿，风险 2 仍在。
- 验收期发现但未修的问题见 design §7.5，只登记。
