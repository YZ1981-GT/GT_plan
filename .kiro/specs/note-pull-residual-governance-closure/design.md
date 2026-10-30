# 附注取数残留与治理收口 — 设计

## 1. 当前事实与边界（2026-10-29 现算）

### 1.1 功能链

| 缺口 | 当前机制 | 风险 |
|---|---|---|
| G12 | `onMounted → pullLatestAdjudicated → applyAdjudicationPatch → persist`；来源缺失被转 0 | 只打开页面即可覆盖已存非零值 |
| G13 | 先 patch 本期并保存，再 patch 上期但不再保存 | 页面看对、重进又丢；只读挂载也可写 |
| H3 | 宿主 Map 枚举键，内部 `useH3FormData` 空 Map 取值 | 已存数据读回为 0，随后自动同步可覆盖附注 |
| H5 | `inject('saveResponse', () => {})`，宿主未 provide | 用户文字看似保存，刷新后丢失 |
| M 自动同步 | 13 个 Tab 把 `syncFn` 当 options 传入，再无参调用 `scheduleAutoSync()` | 800ms 后 TypeError 被吞，静默零请求 |
| 公式来源 | `_push_note` 对任意成功写入都补 `_source=workpaper` | 原生 `_tables` 被误当投影，结构语义错误 |

M 的 13 个错误 Tab：M1 listed/soe、M2 listed/soe、M3 listed、M6 listed/soe、M8 listed/soe、M9 listed/soe、M10 listed/soe。
M1/M2/M3/M8 已有非零离屏等价基础；M6/M9/M10 必须先修模板结构。

### 1.2 离屏覆盖

`note_workpaper_sync_registry.json` 为 78 个唯一 wp_code，`HEADLESS_PROVIDERS` 为 67，差集固定为：

`E1 F1 G7 H1 H3 K3 L4 L5 M6 M9 M10`

F1 的 `f1HeadlessDisclosure.ts` 已存在但未注册、无等价测试，是孤儿 provider。其余十项阻塞仍成立。

### 1.3 治理链

- `gen_edit_level_impact_inventory.py --check` 在生成前被 3 项 `LEVEL_UNDETERMINED` 阻断：OCR 条件表达式、附件 helper 参数级别、函证按方法定级。
- identity-only 当前 HEAD：直接路径 165（基线 166）、router-prefix 236（基线 238）、body/query 80（基线 80）。
- domain checker：1470 现存 / baseline 897 / known 879 / new 591 / resolved 18。
- `06be17bbe` 可归因新增为 18 条；其余 573 条不是本轮债务。baseline 不得增长。
- 当前最高 migration 为 V214；本轮如需 migration，实施时重新现扫，使用 V215/R215 或更高空闲号。

### 1.4 真实验收

Task 23.1 仍为 `[ ]*`。历史【测试】公式同步集团数据只能作候选，不写死 UUID；前 N 名专用路径不需要明细映射。浏览器验收必须备份和恢复 `disclosure_notes`、`consol_note_data`，若重建映射再扩到五张映射表。

## 2. 架构裁决

### ADR-NRG-001：无来源不是零

所有挂载回填函数返回结构化 patch 结果：

```ts
interface PatchResult {
  changed: boolean
  sourceFound: boolean
  fieldsChanged: number
}
```

只有 `sourceFound && changed && !readonly` 才保存。显式来源值 0 是有效值；缺字段 / 缺行不转成 0。

### ADR-NRG-002：单一响应 Map

H3/H5 的 Tab 不再拥有第二份脱离宿主的响应状态。读、写、保存均通过共享 adapter：

```ts
interface ChecklistResponseStore {
  responses: Ref<Map<string, ChecklistResponse>>
  get(id: string): ChecklistResponse | undefined
  save(id: string, patch: Partial<ChecklistResponse>): Promise<void> | void
}
```

宿主负责真实保存；离屏传 no-op saver，但读同一份 Map。生产路径禁止默认 no-op。

### ADR-NRG-003：自动同步调用形态由 AST 守护

合法形态只有：

```ts
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
autoSync.scheduleAutoSync(syncToDisclosureNotes)
onBeforeUnmount(autoSync.cancelPending)
```

AST 守卫逐文件验证 `useDisclosureAutoSync` 首参和 `scheduleAutoSync` 实参数量，且必须有卸载取消。M6/M9/M10 在结构修好前由显式 `autoSyncEnabled=false` 隔离，不用错误调用“碰巧禁用”。

### ADR-NRG-004：共享章节按会计科目 owner 分区

`五、42 / 八、42` 的唯一写权：

| owner | 科目 / 行域 | 允许表 |
|---|---|---|
| L2 | 应付利息 | 应付利息、逾期利息明细及主表对应行 |
| M1 | 应付股利 | 应付股利、超一年未支付股利及主表对应行 |
| K3 | 其他应付款 | 按性质、账龄超一年及主表对应行 |

请求带 `_row_scope` / owner table keys；服务端浅合并。K3 不再生成或删除 M1/L2 所有的表。跨 owner 顺序对拍必须相同。

### ADR-NRG-005：离屏接入门是“非零等价”，不是“有 provider 文件”

每码接入顺序固定：

1. Tab 的恢复 / 快照 / builder 抽为共享纯模块；
2. fixture 注入非零已存数据，证明重挂载读回；
3. 挂真实 Tab捕获请求，与 provider 每章节请求体逐字节比较；
4. 证明 provider 零 checklist PUT、零 UI / 全局监听副作用；
5. 注册并从冻结清单删除；
6. 跑该循环 strict/foundation 守卫。

增加反向盘点：扫描所有生产 `*HeadlessDisclosure.ts` 导出的 provider，必须恰好在一个 provider 组注册。冻结例外只许变短，F1 首批清零。

### ADR-NRG-006：G7 删除基线归附注侧

G7 不再在同步成功后回写底稿 `previouslySyncedTables`。同步请求声明当前 owner 表集合；附注 `table_data` 维护 `_workpaper_owned_tables[wp_code]`。服务端在同一事务内计算：

`removed = previous_owned - incoming_owned`

只删除该 wp_code 独占且没有其他 owner 的表，然后更新 owner 集合。失败不推进。Tab 和离屏共用同一请求契约。

### ADR-NRG-007：动作来源与结构来源分开

- JSON `_source`：只表示 `sub_table_data` / 投影结构。
- ORM `last_sync_source`：表示最近动作，公式推送写 `formula_push`。
- JSON `_last_sync_*`：只表示底稿披露同步指纹。

公式推送改原生 `_tables` 时保持 `_source` 不变；只有本次新建 `sub_table_data` 骨架才设结构来源。历史误标兼容读取，但 dry-run 修复器严格要求“无业务 sub_table_data + ORM formula_push + 无披露同步指纹”。

### ADR-NRG-008：门禁级别支持按 HTTP 方法推导

`GateSpec` 增加结构化方法策略，而非字符串回调：

```py
@dataclass(frozen=True)
class MethodLevel:
    readonly_methods: frozenset[str] = frozenset({"GET", "HEAD"})
    default: str = "edit"
```

`recognize_endpoint` 已有 `DeclaredRoute.method`，router dependency 展开时用当前 method 解析。`recognize_function` 单独扫描 gate 定义时知道它是 method-derived，不能再把内部参数级别报成全局 unresolved。

附件 helper 登记为参数级 GateSpec；OCR 改显式分支，不扩 AST 表达式求值器。

### ADR-NRG-009：域边界只清本轮归因

18 条分四类处理：

1. 生成物噪声 3：`components.d.ts` 从 production scan 精确排除；
2. Python package alias 假边 1：`from app.services import note_edit_gate` 解析真实 submodule；
3. owner 路径缺失 8：对 consolidation note formula、notes formula adapter、`src/composables/workpaper/**` 补精确 owner；
4. 层级倒置 6：移动前端纯算法；抽低层 decimal helper；把 wp→notes 写入改经 notes 侧窄 facade。

安全基线策略：

- 普通检查仍报告全仓 573 条其他新增债；
- 新增 `--write-baseline` 有 new 时拒绝；
- `--shrink-baseline` 只写 `baseline ∩ current`，绝不吸收 new；
- 本轮提供归因清单测试，18 条逐一变成 resolved / 不再出现。

### ADR-NRG-010：真实浏览器写入可逆

新增正式 e2e 辅助脚本，默认 dry-run：

1. 经 API 动态识别【测试】合并项目和所有叶子；
2. PG 只读快照相关整行、主键集合及 SHA-256；
3. 浏览器完成普通映射拉数、根汇总、前 N 名跨企业重排；
4. 独立 GET 和页面硬刷新核对；
5. 关闭页面；
6. 以主键白名单恢复原行、删除本次新增行；
7. 前后主键集合和规范化整行哈希一致。

脚本若发现非【测试】项目、现有运行锁或快照漂移，必须 fail closed。

## 3. 分批实现

### 3.1 批 A：先阻止静默数据损坏

- G12：`readAdjudicationContext` 保留 nullable；`buildG12DisclosureSyncPatch` 只更新有证据的字段；`applyAdjudicationPatch` 返回 `PatchResult`。
- G13：拆 `applyDetailPatch` / `applyPriorPatch`，`pullLatestAdjudicated` 聚合 changed 后最多调用一次 `persist`。
- H3：`useH3FormData` 支持注入现成 Map；Tab 不再创建第二份状态。
- H5：宿主提供真实保存 adapter，Tab prop 显式必传；测试环境可传 no-op，但 production mount 守卫禁止缺失。
- M1/M2/M3/M8：修正确自动同步调用和卸载取消。

### 3.2 批 B：模板与共享写权

- 读取两版单体附注模板作为权威表头 / 行名。
- M6 统一模板行模型，显示字段可保留但 wire snapshot 只按模板投影。
- M9 拆 BS / PL 两份状态；国企第二表按模板和底稿数据可用性裁决。
- M10 采用“只发送拥有且有完整输入的表”；在 UI 未提供基本情况 / 持有者输入前，不发送空表。
- K3 / M1 / L2 落 `_row_scope` 与 owner table 集合，移除跨 owner delete。

### 3.3 批 C：11 个 provider

顺序按风险从低到高：

1. F1（已有 provider，先补等价测试与注册）；
2. H3；
3. L4、L5；
4. M6、M9、M10；
5. K3；
6. H1（补 project context）；
7. G7（服务端 owner 基线）；
8. E1（多章节 + row scope）。

每完成一项立即从 `NOT_YET_HEADLESS` 删除并跑总登记 / 孤儿 / 循环守卫。最终差集为空。

K 文件数门沿用 `baseline - deleted + added`：现算当前新增文件清单并逐文件登记，新增 K3 文件只追加到 added ledger，不改历史 baseline。L 新文件用小写根 composable 命名，避免误入 strict 文件名规则；原 Tab 改动仍跑 L 全套。

### 3.4 批 D：公式来源、鉴权与域边界

- 反转 `test_push_note_source_marked_after_write`；补旧格式、新骨架、真实 workpaper sync 三类测试。
- OCR 显式分支；附件 GateSpec；函证 MethodLevel；重生 edit inventory。
- 下调 identity-only 两个基线到现算值，body 保持。
- 域边界 checker / manifest / 文件移动和 facade；baseline 仅 shrink，不吸收新增。

### 3.5 批 E：真实环境与回归

- 服务健康、项目空闲、测试项目全叶子校验。
- 普通章节优先复用 `五-5-6`；前 N 名按项目口径动态选择（历史上市候选 `五-8-18`）。
- 测试数据带本次唯一 run id，验证同名合并、排除集团内单位、排序、截 N、合计、比例、近似提示。
- 自动恢复后再标验收完成。

## 4. 测试矩阵

| 层 | 必跑 |
|---|---|
| 单元 | G12/G13 patch；H3/H5 store；M6/M9/M10 builder；owner merge；source semantics；gate method policy；domain resolver |
| 前端集成 | 每个修复 Tab 非零重挂载；自动同步 fake timer；11 个 provider 逐字节等价；孤儿 / 覆盖清单 |
| 后端集成 | G7 owner 状态；公式 push 三来源；edit inventory 双生成；domain checker synthetic；identity baselines |
| 循环守卫 | K / L / M / H / G / E foundation 与 strict 域，现算后对 HEAD 归因 |
| 浏览器 | 127.0.0.1:3030；【测试】集团真实重汇总 / 前 N 名；页面刷新与控制台 |
| 全局 | 相关 pytest、相关 vitest、全量 vue-tsc 候选对 HEAD、行数门、gitleaks、清册 `--check` |

PBT `max_examples=5`。测试发现预存红，必须在同一基线提交复现后再归因。

## 5. 风险与回滚

| 风险 | 控制 |
|---|---|
| 自动同步修好后把历史错误载荷真正写库 | M6/M9/M10 结构门先于启用；非零等价测试 |
| 共享章节后写覆盖先写 | 行域 owner + 顺序交换测试 |
| provider 离屏副作用 | no-op saver + effectScope stop + 网络方法白名单 |
| G7 删除表基线漂移 | 附注侧同事务 owner ledger，失败不推进 |
| 真库验收污染 | 【测试】限定、整行快照、精确主键恢复、哈希复核 |
| 清册假绿 | 双生成 + `--check` + 逐处变异；不忽略动态门 |
| 域基线吸收新债 | new 存在时拒绝 write；shrink-only |
| 并发会话覆盖 | 分离头 locked worktree；提交前 fetch 后重放到远端最新；不 stash |

## 6. 复盘评估规则

复盘建议按以下矩阵评分：

- 收益：是否防错数 / 丢数据 / 越权 / 用户可见死链；
- 规模：改动文件数、是否跨 schema；
- 风险：是否改变已有数据、共享章节或自动保存时序；
- 可逆性：能否单提交撤销、是否需要存量迁移；
- 证据：是否有非零反例、真实 PG / 浏览器证据。

本轮可直接追加实施的建议必须满足：收益高，文件数不超过约 8，风险低至中，有现成回归落点。大文件拆分若会制造循环 import 或扩大共享改动，只登记拆分轴，不在收尾阶段强拆。

## 7. 实施结果、偏离与勘误

### 7.1 设计裁决的最终落点

- `HEADLESS_PROVIDERS` 与职责 registry 精确覆盖 78/78 个唯一 wp_code，`NOT_YET_HEADLESS` 为空，生产 provider 孤儿为 0。每个本轮 provider 都以非零持久化 fixture 挂真实 Tab，对逐章节 HTTP body 做 JSON 字节等价比较。
- G7 清册最终键为 `_workpaper_table_owners`，结构为 `{version: 1, owners: {owner_key: ...}}`；owner 身份是 `G7:listed` / `G7:soe`，不是早期设计文字里的 `_workpaper_owned_tables[wp_code]`。真实表数据、列定义、payload hash 和 owner 在同一个 `DisclosureNote.table_data`、同一行锁与事务中更新。
- `五、42 / 八、42` 的共享主表没有交给任一前端 owner。L2/M1/K3 只发送各自独占明细，后端 `wp_disclosure_derived_tables.rebuild_other_payables_summary` 在 owner 删除之后按三份明细确定性重建四行主表；这比“主表对应行也由三个请求分别写”更能消除到达顺序依赖。
- E1 主表继续由公式推送维护。Tab 与 provider 只共享说明、外币表、受限资金和受限资产请求计划；`restrictedRows: undefined` 表示没有可信来源，空数组只表示“明确管理但为空”。
- 安全收缩命令最终命名为 `--shrink-only`，不是设计草案中的 `--shrink-baseline`。`--write-baseline` 发现任何 new identity 时拒写且保持文件字节不变。
- 本轮没有 schema 变更或 migration。UAT 工具只备份、注入和恢复既有 8 张表。

### 7.2 域边界数字勘误

开工时的 `1470 / 897 / new 591 / resolved 18` 使用旧 checker，包含 generated declaration 与 package alias 假边。最终 checker：

- 精确排除 generated 目录、`*.generated.*`、`*.d.ts`；
- package import alias 指向真实 submodule；
- owner specificity 并列时返回 `ambiguous_owner`，不按 manifest 顺序猜；
- baseline 经 `--shrink-only` 从 897 降至 724，删除 18 条已解决归因边与 155 条 generated 假 identity，未加入任何当前 new identity；
- 用最终 checker / manifest 对同一开工 HEAD 与候选树重算，均为 1301 条，identity 差集 `added=0 / resolved=0`；两树相对 724 基线都同报 577 条。因此 577 是当前治理基线之外的既有平台债，不是本轮回归，也没有被本轮冒领。

### 7.3 验收期追加修复

最终门禁发现并当轮修复以下高收益、低风险问题：

1. `wp_disclosure_sync_service.py` 因新增 owner/batch 超过行数棘轮。没有抬白名单，抽出纯 owner ledger 和事务 batch runner；原服务保留同签名薄包装并在调用时注入 `sync_from_workpaper`，测试 monkeypatch 接缝与事务顺序不变。K 域 30 个新增文件账本也抽成 companion facts，历史 367/368 基线不改。
2. 全量 `vue-tsc` 首轮发现 18 条候选新增诊断。除测试回调类型外，L5 国企 `top5.other` 把 `{endAmount, priorAmount}` 当成 `{end, prior}`，运行时会把非零“其他长期应付款”静默写成 0，已做显式字段投影并加 321/123 与小计回归。M10 的 `el-input-number` 清空值在组件边界由 `undefined` 归一为 `null`，明确 0 保留。
3. `disclosure:note-text-updated` 保持 `timestamp` 必填，补可选 `wpId/sectionId`；F2/H4/K4 调用方补时间、项目和权威章节上下文，K4 两处移除 `as any`。这完成旧窄事件类型只暴露第一层报错后的迁移，不把类型门改成可选或开放字典。
4. gitleaks 把 `owner_key: G7_OWNER_KEYS.soe` 识别成 generic API key。该值是业务 owner 命名空间，使用只覆盖这一行的 `gitleaks:allow` 注释，未扩大全局 allowlist。

### 7.4 UAT 环境偏离

Docker Desktop 的宿主端口转发中途失效，宿主到临时 backend/PG 会断连。没有改业务参数绕过：

- DB 工具和 HTTP 探针放入 `gt_workplan_default` 网络；
- browserless 与反向代理共享网络命名空间，浏览器地址仍为规定的 `http://127.0.0.1:3030`；代理把 `/api/*` 发给候选 backend，把静态请求发给独立候选 Vite；
- PG 因本机大量长期连接达到上限时，仅重启本地 `audit-postgres` 容器清空连接，数据卷不变；随后先 capture-after，再 restore 和独立 verify；
- 最终所有临时写入均恢复到 before 的主键集合与规范化整行 hash。

## 8. 五角色整体复盘

| 角色 | 复核结论 | 仍需关注 |
|---|---|---|
| 业务合伙人 | “无来源”不再被解释为 0；E1 公式主表、L2/M1/K3 明细权威源和 Top-N 分母均有明确来源。共享章节不再由最后写入者决定。 | 根节点 Top-N 基于下级已保存前 N 名重排，仍是有意的近似结果；界面已显示近似原因，重大余额仍需审计判断。 |
| 项目经理 | 78/78 码形成一张可复算清单；自动同步、离屏同步、真实 Tab 使用同一恢复器/builder，减少“只打开页面才同步”的人为步骤。 | 148 个文件属于一次跨域收口，虽按用户要求单提交，后续维护应按 provider/owner/治理三类变更分批评审。 |
| 质控 | 非零反例、缺来源、明确 0、只读、卸载、人工覆盖、row-scope 失败、owner 排列、硬刷新和恢复 hash 都有门禁；全量类型差集新增 0。 | 最终远端树仍有 2987 条既有 vue-tsc 诊断和 580 条 baseline 外域债；本轮只证明没有增加，不代表全仓已经清零。 |
| 审计助理 | 浏览器中普通映射和 Top-N 的金额、合计、比例、来源标签均可见，硬刷新不丢；自动同步失败不再静默推进 G7 删除基线。 | provider 运行失败目前主要靠刷新结果汇总呈现，跨多个底稿时仍缺按 wp_code/章节聚合的运维视图。 |
| EQCR | owner ledger 带稳定 payload hash，鉴权清册能按 HTTP 方法区分 readonly/edit，UAT 写前后逐行可证明，未触碰非测试项目。 | 本机 PG 连接饱和曾两次影响验收。虽未造成数据损失，但平台级连接治理应独立跟进，不能靠人工重启作为常态。 |

复盘未发现新的 P0 数据错误、越权或不可恢复写入。验收期发现的 L5 静默归零、类型契约、行数门和密钥扫描误报已在本轮修复并重跑相关验证。

## 9. 后续优化建议与 ROI

| 优先级 | 建议 | 预计文件数 | 收益 | 风险 / 裁决 |
|---|---|---:|---|---|
| P1 | 建立 headless 同步运行观测：按 wp_code/章节统计 applied、manual-blocked、scope-skipped、row-scope-unresolved、耗时和最后错误，并在刷新结果页提供下钻。 | 6~8 | 高：78 码从“有能力”变成“可运营” | 中；涉及事件/持久化与 UI，另立 spec，不在收尾期加新写路径。 |
| P1 | 治理本地/生产连接饱和：定位 SSE、测试客户端、MCP 长连接的连接占用，增加池上限告警、连接来源标签和 UAT 前置只读诊断。 | 4~8 | 高：避免 capture/restore 被连接耗尽阻断 | 中；需压测与 Docker/PG 运行证据，另立运维 spec。 |
| P1 | 将 577 条域边界债按 SCC 与 owner 分批收缩，每批只允许 baseline 下降。 | 100+（分批） | 高：降低跨域耦合 | 高；规模远超本轮“≤8 文件直接修”条件，禁止一次硬清。 |
| P2 | 为 `disclosure:note-text-updated` 建 AST cast 棘轮：typed emit 必带 timestamp，`as any` 只许减少；逐步把历史 window/mitt 兼容载荷收成判别联合。 | 3~5 | 中：防事件字段再次静默漂移 | 低至中；当前事件已修，但全量历史调用属于独立治理。 |
| P2 | 建全量 vue-tsc 诊断基线工具，以规范化 `(文件, TS 码, 信息)` 多重集只许减少，替代人工双树日志比较。 | 3~6 | 中：把本轮有效方法固化为 CI | 低至中；需先处理绝对路径、重复诊断和 OOM 退出，避免永假门禁。 |
| P3 | 评估由职责 registry 生成 provider 注册骨架，减少手工 provider 组漏登。 | 5~8 | 中 | 中；当前 78/78 精确守卫已能防漏，代码生成收益暂不高，暂缓。 |

建议下一轮先做“headless 运行观测”和“PG 连接来源/饱和治理”。域边界与类型债继续使用只许减少的分批策略，不与业务功能混成一次大改。

### 7.5 远端最新重放补记

提交前 fetch 发现目标分支已从开工基线 `8107371f0` 前进 22 个提交至 `5d0a4b60a`。本轮 151 个路径与远端 209 个变化路径只有 `INDEX.md`、`memory.md` 重叠；在新的锁定 detached worktree 以临时 commit 对象执行三方重放，INDEX 取远端完整首部后插入本条，memory 自动合并。

远端新增了 3 个鉴权门点和 1 个直接 permission 比较，旧清册因而正确地在 `--check` 下变红；在重放树重新生成后为 755 门点 / 725 端点 / 198 文件，二次 `--check` 通过。note 清册仍为 101。

终验必须以远端最新为比较基线：后端 267 passed、前端 619 passed；全量 vue-tsc 为远端 3089 条 / 1531 unique，候选 2988 条 / 1482 unique，规范化多重集 `added=0 / resolved=101`，两边无 OOM。域边界远端与候选均 1304，identity 差集为 0；相对 724 debt baseline 均有 580 条。开工时的 577 与最终 580 都是真实快照，增加的 3 条来自远端 22 个提交，不得归给本轮，也不得吸收入本轮 baseline。

### 7.6 推送预演后二次远端前进

`push_version.py --dry-run` 在首次本地提交后再次 fetch，发现目标分支新增 sibling commit `43b189d49`（`fix(notes): close disclosure formula and consolidation refresh chain`，并占用 v1.0.42）。没有强推或直接覆盖；重新从该提交建立锁定 detached 候选，再将本轮单提交以 `--no-commit` 三方重放。

四个重叠文件中只有 INDEX 发生文本冲突。最终 Python 合并同时保留：远端提交后的 `NOTE_SECTION_SAVED`、成功同步清 stale、headless→push→refill→公式刷新顺序；以及本轮原生 `_tables` 不改结构 `_source`、batch owner/strict、L2/M1/K3 派生主表及 pushed-cell touched 并集。

语义复核发现一个 Git 不会报冲突的缺口：owner 用空集合放弃旧来源表时，`rebuild_other_payables_summary` 仍可能改变共享主表，但旧外层门只看 `clean_sub_table_data`，导致派生主表跳过公式拥有格重放。最终门改为 `clean_sub_table_data or derived_tables`；测试构造 L2 放弃“应付利息”、M1“应付股利”仍在的反例，旧门稳定打红、修复后通过。

最终远端接缝回归：后端 238 passed、前端 38 passed；全量 vue-tsc 远端 3088 / 1530 unique、候选 2987 / 1481 unique，`added=0 / resolved=101`；域边界两树均 1304、identity 差集 0。首次本地提交只作临时保护，不得推送；最终必须在 `43b189d49` 之上重新形成唯一提交并重新取得版本号。
