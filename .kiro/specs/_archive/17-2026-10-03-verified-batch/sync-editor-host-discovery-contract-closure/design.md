# Design — 同步编辑器宿主纳入挂点发现契约

## 一、现状 grep 确认（设计前置，全部现算 2026-10-01）

| 项 | 现算值 | 取法 |
|---|---|---|
| 发现器组件白名单 | **3** 条硬编码 `TARGETS` Map | `discover-workpaper-sync-mounts.mjs` L20-35 |
| `mountId` 身份 | `[file, component, templateNodeOrdinal, sheetExpression, wpExpression]` 的 sha256 前 20 位 | 同文件 L210-218 |
| `sourceDigest` | `sha256(JSON.stringify({mounts, dispatchers}))` ⇒ **含 sourceSpan，行号一动就变** | 同文件 L386 |
| 分组键 | `(file, component)` | `generate_workpaper_sync_manifest.py` L231-243 |
| `_entry_id` | `(document_type, source_file)`，**不含 component** | 同文件 L148-158 |
| 碰撞检查 | `stable entry_id collision` | 同文件 L339 |
| EditorHost props | 只有 `descriptor` / `bridge` / `documentServerUrl` / `docsApiLoader` / `contentRefresh` | `WorkpaperSyncEditorHost.vue` L147-152 现读 |
| EditorHost 服务的文档类型 | **Excel 与 Word 都服务**（文件头注释首行） | 同文件 L2 |
| 挂 EditorHost 的宿主 | **96** | 全仓扫 `.vue` |
| 其中双挂（含 legacy） | **45**，legacy document_type **全为 xlsx**，混用 xlsx+docx 的 **0** 个 | 现算 |
| 其中仅 EditorHost | **51** = 34 个 `d4/**` tab + 17 个 A 类 | 现算 |

🔴 **三条结论直接决定设计**：

1. **document_type 无法从 EditorHost 挂点自身推出** —— props 里没有，组件本身两种都服务。
2. **碰撞只在同 document_type 内发生** —— `GtOnlyOfficeSheet` 是 xlsx、两个 Word 组件是 docx，
   而现算**没有任何宿主同时挂 xlsx 与 docx 的 legacy 组件** ⇒ 按 `(file, document_type)` 分组
   不会把现有的任何两个 entry 并成一个。
3. **entry_id 绝对不能改** —— 它是 adapter 注册、契约归属、representation 身份的持久化主键。

## 二、方案选择

### 被否决：A 方案「entry_id 加入 component」

`_entry_id(document_type, source_file, component)` ⇒ 碰撞消失，但**全部既有 entry_id 取值改变**。
entry_id 是持久化主键（`DELIVERED_PER_ENTRY_CONTRACTS` / store item / representation 全以它为键），
改它等于让所有已交付契约与已落库 representation 失去归属。**一票否决**。

### 被否决：B 方案「EditorHost 只在宿主没有 legacy 挂点时才发现」

最小改动、不撞碰撞。但它制造一个**不连续性**：宿主删掉最后一个 legacy 挂点的那一刻，
entry 的派生路径整体换轨（从 legacy 组派生变成 EditorHost 组派生），而迁移中间态
（双挂）下 EditorHost 根本不进清册 ⇒ 「这个宿主已接真双向」这个事实在清册里**依然不可见**。
缺口只是从「迁移完成后消失」变成「迁移中不可见」，没有彻底解决。

### 被否决：C 方案「默认 document_type = xlsx」

现算 96/96 都是 xlsx，所以今天"对"。但第一个 docx 宿主迁移时会**静默**落到 xlsx ⇒
它的 entry_id 前缀错、与已交付契约失配，且没有任何判据能看见。
**与「禁第四层兜底」是同一条铁律**：默认值把「解析不出来」变成「解析出一个错的」。

### 采纳：D 方案「分组键换成 (file, document_type) + 三层源码优先的身份解析链」

两个正交的改动：

**D-1 分组**：`(file, component)` → `(file, document_type)`。
- 45 个双挂宿主的 EditorHost 挂点并入其既有 entry（同 `xlsx`）⇒ **entry_id 不变、能力不变**；
- 现算零宿主混用 xlsx/docx legacy ⇒ 不会把任何现有 entry 并掉；
- 碰撞检查保留（它守的是「同 (file, document_type) 出现两次」，分组后天然不可能，
  但仍作为回归锁保留 + 配变异证明）。

**D-2 身份解析链**（严格 L1 → L2 → L3，无第四层）：

| 层 | 判据 | 覆盖 | 人工输入 |
|---|---|---:|---|
| **L1** 同文件存在 legacy 挂点 ⇒ 取兄弟挂点的 `documentType`（多个不同则 fail closed） | 源码事实 | **45** | 零 |
| **L2** 无 legacy 兄弟，但模板里有**恰好一个**静态 `entry-id="{xlsx\|docx}/…"` 字面量 ⇒ 以它为身份声明，前缀即 document_type | 源码事实 | **21** | 零 |
| **L3** 以上皆无 ⇒ overlay reviewed glob 规则 | 人工复核 | **30**（全在 `d4/`） | **1 条 glob** |

🔴 L1+L2+L3 = 45+21+30 = **96** ✓ 闭合，且三层各自非零（Requirement 2.6 的空分母防护据此成立）。
🔴 **41 个宿主同时有 L1 与 L2 信号，两者 document_type 现算零冲突** ⇒ 交叉校验可用且已通过。

**身份声明 → entry 关系的判定**（L2/L3 共用）：
- 声明值 == `_entry_id(doc, 该文件)` ⇒ **独立 entry**（现算 17 个 A 类）
- 声明值 != 自身派生值 ⇒ **`parent_duplicate`**，`parent_entry_id` = 声明值
  （现算 4 个 d4 tab 走 L2、30 个走 L3，共 34 个，父级全是 `xlsx/gt-d4-operating-revenue`）

🔴 **复用既有 `parent_duplicate` 机制，不新造状态** —— 那条被删掉的
`d4/**` × `GtOnlyOfficeSheet` parent_rule 说的就是同一件事（「D4 各 tab 转发 D4 根身份」），
本设计等于把它按新载体重新表达。

## 三、组件优先级：为什么 legacy 排在 EditorHost 之前

一个组含多 component 时，entry 的 `capability` / `html_store` / `canonical_resolver` /
`migration_state` / `expected_profile` 默认值取谁？

**采纳：legacy 优先**（`GtOnlyOfficeSheet` > `OnlyOfficeWordDialog` > `WorkpaperWordEditor`
> `WorkpaperSyncEditorHost`）。

理由不是「legacy 更重要」，而是**零 churn**：45 个双挂宿主的 entry 取值因此逐字不变。
若反过来让 EditorHost 优先，45 条 entry 的 `capability` / `html_store` / `canonical_resolver`
会一次性全变 ⇒ 把「修发现契约」和「重新裁决 45 条 entry 的能力」两件事捆在一起做，
任何一处出错都无法归因。**能力裁决属各 lane 的 overlay override，不属本 spec。**

EditorHost 的存在改为以**两个 source-backed 字段**表达，不动默认值：
- `mount_components`: `["GtOnlyOfficeSheet", "WorkpaperSyncEditorHost"]`（排序后）
- `sync_editor_host_mounted`: `true`

这两个字段让「该宿主已接真双向载体」首次成为清册里的可查事实 —— 而这正是缺陷的本体。

## 四、L2 为什么用 `entry-id` prop 而不是别的形态

现算四种候选形态在 96 个宿主上的覆盖：

| 形态 | 命中宿主 |
|---|---:|
| `entry-id="…"`（`GtEntrySyncCapabilityNotice` prop，模板静态字面量） | **62** |
| 任意 `'{xlsx\|docx}/…'` 裸字符串字面量 | 65 |
| import 闭包里的 `ENTRY_ID` / `entryId:` 常量 | 10 |

选 `entry-id` prop，三条理由：
1. **它在模板 AST 里、是静态字面量** —— 与发现器读 `sheet-name` 的口径完全同构，
   不需要跨文件闭包分析（跨文件扫描实测噪声极大：有宿主 import 的共享模块里列了 **51 个**
   entry_id 字面量，按「任意裸字面量」取会得到一个无法判定的集合）。
2. **它语义就是「我是哪条 entry」** —— `GtEntrySyncCapabilityNotice` 的职责就是按 entry
   显示能力提示，宿主写这个 prop 就是在声明身份。
3. **L2 只需覆盖 51 个「仅 EditorHost」宿主中的 21 个**，其余 30 个走 L3；
   而 62 > 21 ⇒ L2 的信号量足够，不必为了多覆盖几个而引入脆弱的闭包扫描。

🔴 **不采纳「给 EditorHost 加一个必填 `sync-entry-id` 属性」**：那要改 96 个 `.vue`，
其中 17 个是并发会话未提交的在途文件，必然撞改动冲突；且本 spec 的目标是修**发现契约**，
不是改前端接线形态。该形态可作为后续独立收口（见 §八）。

## 五、改动点清单（逐文件）

### 5.1 `audit-platform/frontend/scripts/discover-workpaper-sync-mounts.mjs`

1. `TARGETS` 增加第 4 条：`workpapersynceditorhost` → `{component: 'WorkpaperSyncEditorHost',
   canonicalFile: '…/sync/WorkpaperSyncEditorHost.vue', localName, documentType: null}`。
   🔴 `documentType: null` 是**刻意的**：它标记「本组件的文档类型必须由解析链给出」。
2. 新增 `resolveEditorHostDocumentType(file, mounts, declarations)`：实现 L1 + L2。
   - L1：同文件其他挂点的 `documentType` 集合，size==1 取之，size>1 抛错。
   - L2：模板 AST 里扫 `entry-id` 静态属性字面量（**不扫注释、不跨文件**），
     去重后 size==1 取其前缀，size>1 抛错。
   - 两层都不成立 ⇒ 该挂点的 `documentType` 留 `null`、并带上
     `entryIdDeclaration: null` + `needsOverlayRule: true`，交由生成器的 L3 处理。
3. 挂点新增两个字段：`entryIdDeclaration`（L2 命中时的声明值，否则 null）、
   `documentTypeSource`（`'sibling_mount'` / `'entry_id_declaration'` / `null`）。
4. `stats.byComponent` 自动包含第 4 个键（它按 `TARGETS` 遍历，无需改）。
5. 🔴 **`mountId` 不变**：它已含 `component`，新组件天然不与旧挂点撞；
   但因 `sheetExpression`/`wpExpression` 对 EditorHost 恒空，**同一文件内多个 EditorHost 挂点
   只靠 `templateNodeOrdinal` 区分** —— 这已足够（ordinal 在文件内唯一），
   且现算 96 个宿主里每个只有 1 个 EditorHost 挂点。仍须加 mountId 唯一性变异证明。

### 5.2 `backend/data/workpaper_sync_entry_overlay.json`

1. 新增 reviewed 键 `sync_host_entry_rules`（L3）：
   ```json
   [{"file_glob": "audit-platform/frontend/src/components/workpaper/d4/**/*.vue",
     "component": "WorkpaperSyncEditorHost",
     "entry_id": "xlsx/gt-d4-operating-revenue",
     "reason": "D4 各 tab 经 useD4SyncMode 转发 D4 根 entry 身份；本规则是被 commit cd9592ff5 之后删掉的 `d4/**` × GtOnlyOfficeSheet parent_rule 的新载体表达"}]
   ```
2. 新增 `defaults_by_component["WorkpaperSyncEditorHost"]`：reviewed 默认值 +
   `expected_profile`（取值域须由 51 个新 entry 的派生结果实证，不可照抄 GtOnlyOfficeSheet）。
3. 更新 `approved_source_digest` + `review_basis`（归因：新增 96 条 EditorHost 挂点）。
4. 把 a51 裁决从 `deferred_overrides` 移回 `overrides`，删空 `deferred_overrides`。

### 5.3 `backend/scripts/gen/generate_workpaper_sync_manifest.py`

1. `_group_source_facts`：分组键 `(file, component)` → `(file, document_type)`。
   EditorHost 挂点若 `documentType is None` ⇒ 先经 L3 解析补齐，仍为 None 则抛
   `ManifestGenerationError`（fail closed）。
2. 新增 `_resolve_editor_host_identity(group, rules)`：实现 L3 + 「独立 / parent_duplicate」判定。
3. `_primary_component(group)`：按声明的优先级元组取主组件，供
   `defaults_by_component` / `_source_match` / `_assert_expected_profile` 使用。
4. entry 新增 `mount_components` / `sync_editor_host_mounted` 两个字段，
   并加进 `_REQUIRED_ENTRY_FIELDS`。
5. `parent_entry_id` 的来源扩展：除既有 `parent_rules` 外，L2/L3 解析出的「声明值 != 自身」
   也产出 `parent_duplicate`。两条来源 SHALL 互斥（同时命中 ⇒ 抛错）。
6. `sync_host_entry_rules` 加入 stale-rule 门（零匹配规则 ⇒ 抛 `stale overlay sync_host_entry_rules`）。

### 5.4 守卫

新建 `backend/tests/workpaper_sync/test_sync_editor_host_discovery_contract.py`：
缺口不变量、三层覆盖闭合、stats 自洽、parent 关系正确、`deferred_overrides` 已空，
以及**每条判据的变异证明**。

## 六、影响面与**不做**的边界

### 6.1 产物变化（必然且可预期）

| 产物 | 变化 |
|---|---|
| `sourceDigest` | 变（+96 挂点）⇒ `approved_source_digest` 门跳闸一次，须复核批准 |
| `entry_count` | **138 → 189**（+17 独立 A 类 + 34 d4 parent_duplicate） |
| `independent_entry_count` | 125 → 142 |
| `parent_duplicate_count` | 12 → 46 |
| `stats.byComponent` | 新增 `WorkpaperSyncEditorHost: 96` |
| 45 个双挂 entry | entry_id / capability / html_store / canonical_resolver **逐字不变**；`mounts[]` 变长、新增两字段 |

### 6.2 会被打红的既有判据（本 spec 只登记、不代改）

entry 数变化会让各 lane **冻结的 slice / record 产物**与 manifest 的对账再次不闭合。
设计阶段以 `live-source-before-fix` 的 138 版实测出 12 条这类红（task57 ×6 / task63 ×3 /
a_entry_connection_blockers ×2 / task46 ×1）。🔴 最终 Task 16 为回答「相对提交基线本轮引入哪些红」，
改用 `committed-artifact-before-fix` 的 HEAD 155 版做 A/B，得到 **10 条本轮引入**。两组数字的
基线不同，**不可相减或互相替代**；双口径的复现与误判复盘见 §九 T6。

🔴 **处置铁律**：这些 slice / record 与 manifest 同为 **review-gated** 审阅产物，
重生成需其 owner 复核。本 spec SHALL 逐条跑出清单、做 A/B 归因（内存/文件级，
**禁 `git stash`** —— 工作树常有并发会话在途改动）、登记到各 lane 的 tasks.md，
**SHALL NOT 代改**。

### 6.3 明确**不在**本 spec 范围

- 不改任何既有 entry 的 `capability` / `adapter_id`（那是各 lane 的 overlay override）；
- 不给 45 个双挂 entry 翻能力（§三的优先级就是为了避免这件事）；
- 不改 96 个 `.vue`（§四已说明为何不加 `sync-entry-id` 属性）；
- 不重生成任何 lane 的 slice / record；
- 不执行 `check_sync_provider_golden_digest.py --update`。

## 七、风险与对策

| 风险 | 对策 |
|---|---|
| 并发会话正在改那 17 个 A 类宿主（未提交）⇒ `sourceDigest` 持续漂 | 批准前现跑两次 discoverer 比对 digest 稳定；`review_basis` 如实披露未提交文件清单与数量 |
| 产物可能被并发会话回退（2026-09-30 已发生一次） | 四件产物全部可由生成器确定性复现（已实证 digest 逐字一致）⇒ 发现回退即重跑；**真源（overlay）的改动尽早独立落盘** |
| L2 的 `entry-id` 扫描误吃注释里的字面量 | 扫描在**模板 AST 的属性节点**上做（与 `sheet-name` 同口径），注释不进 AST；配变异证明：把声明挪进注释后该宿主须落到 L3 并 fail closed |
| L3 的 glob 规则随 d4 目录重构而失效 | 复用既有 stale-rule 门（零匹配即抛错）；并加「L1+L2+L3 == 宿主总数」闭合判据 |
| 把 `documentType: null` 当成合法取值漏到 manifest | `_REQUIRED_ENTRY_FIELDS` 校验 + 生成器显式 fail closed + 判据断言 manifest 内无 null document_type |

## 八、后续独立收口（本 spec 之后，不在本轮）

1. **给 `WorkpaperSyncEditorHost` 加必填 `sync-entry-id` 属性**，把 L2/L3 统一成 L0
   （挂点自证身份），届时 L3 的 overlay 规则可整体删除。需改 96 个 `.vue`，
   应在 A 类 17 个文件提交后单独做。
2. **各 lane 的 slice / record 重生成**（owner 复核后）。
3. `deferred_overrides` 键在 a51 移回后应整体删除（它只为本次缺口存在）。

---

## 九、实施复盘（2026-10-01，交付后补）

本轮 **4 次** 实际事故，全部如实登记。排序按「对结论正确性的危害」从大到小，不按发生时间。

### T1 🔴 最严重：我对 golden digest 漂移的归因是**错的**，且一度写进了工作记录

**我当时的结论**：`check_sync_provider_golden_digest.py` 报的
`[d4] sheet[d44-managed]: 基线=a367bf8b 现算=1fa82f83`，根因是并发会话未提交的
`backend/data/workpaper_sync_contracts/d4.revenue_detail.json`（` M`）。

**实际情况**：这个门**根本不读** `workpaper_sync_contracts/*.json`。现读脚本确认它比的是
**provider 源码现算的三段 canonical JSON** vs **基线文件 `_sync_provider_golden_digest.json`**。
契约 JSON 是 `build_contract_payload()` 的**产物**，不是它的**输入** —— 我把因果方向搞反了，
只因为「漂移的 label 是 d4」「刚好有个 d4 契约 JSON 是 ` M`」就把两件事接上了。

**真因**（三条独立证据，全部可复现）：

1. `git diff` 铁证：并发会话把 `phase5_d4_adjustment_sheet.py` 的 `FOOTER_MARKER_D44`
   从前缀 `"提示："` 改成完整 63 字文本（他们在修 `FooterAnchorDriftError` —— 引擎
   `_find_marker_row` 的判据是 `text.strip() == marker` **全等**而非 `startswith`）。
2. 现算 d44-managed sheet payload 的 sha256 前 16 位 = `1fa82f831f2f034a`，与门报的**现算值
   逐字相同**；差异点定位到 `.tables[0].footer_anchor.marker`。
3. `sys.settrace` 行级追踪：`entry_source_facts.py`（本轮我唯一改的 provider 侧文件）在 d4 的
   import 期与抽取期**零行被执行** ⇒ 本轮改动与该漂移无因果关系。

**为什么会错**：`phase5_d4_revenue_detail.py`（`PROVIDERS` 里登记的那个模块）**自身无任何
未提交改动**。我按门禁提示第 1 条「查该 provider 模块」查到「它没改」，于是转而找别的
「看起来像 d4 的未提交文件」，就撞上了那个契约 JSON。真因在它 **import 的兄弟模块**里 ——
`phase5_d4_revenue_detail.py` import 了 **26 个** `phase5_d4_*_sheet.py`，`d44-managed` 这张
sheet 的声明在其中之一。

**这是方法论铁律 ⑲ 的又一次实例**（「只扫宿主会漏 import 闭包里的真实调用」），形态换成了
「只查登记模块会漏闭包里的真实改动源」。门禁提示本身在引导这个错误，已就地补正：
`check_sync_provider_golden_digest.py` 的排查顺序改成 4 条 —— ①查整个 `workpaper_sync/`
目录而非单个登记模块，并给出按 sheet_key 反查产出模块的命令 ②明确「**别替他们 `--update`**」
③给出「用 `sys.settrace` 断言自己改的文件零行执行」这个可复现的无因果证明手段
（并写明「import 过不算 —— lazy import 会装进 `sys.modules` 造成假阳」）④才是真实回归分支。

**新增方法论（待并入 memory 铁律）**：
> **归因到「某个未提交文件」之前，先确认那个文件在被判据的因果链上**。判据读什么、不读什么，
> 要现读判据源码确认，不能按文件名的相似度推。本次的错误形态是「名字里都有 d4」就接上因果，
> 而正确的因果链是 `FOOTER_MARKER_D44 常量 → build_contract_payload() → sheet digest`，
> 契约 JSON 在链的**下游**，改它对 digest 毫无影响。
>
> 配套：**「我的改动无因果」要用执行级证据，不是文件清单级证据**。`sys.settrace` 断言零行
> 执行是可复现的；「我没改那个文件」不是 —— 你可能改了它 import 的东西。

### T2 并发会话覆盖 overlay，致本轮 14 条裁决**静默丢失**

`backend/data/workpaper_sync_entry_overlay.json` 是多 lane 共用的真源。本轮写完 14 条
override 后，并发会话按他们自己的内存状态整文件重写，我的 14 条连同两个新键一起消失，
而**没有任何判据打红**（overlay 的 digest 门只校验「声明与现算一致」，少声明不违反它）。

处置：**选择合并而非对抗** —— 以他们的 16 条为基逐字保留，加回我的 14 条与两个新键。
重建时发现丢的不只是条目，还有每条里的 `html_store` / `canonical_resolver` / `evidence_patch`
三个字段，按既有同类 override 的现算约定补齐（`checklist_responses_` + item_id 以 `__` 连接，
现算对 d2 + 9 条 H 吻合 10/14；不吻合的 4 条是约定成形前的手工标签，照实沿用不强行统一）。

**教训**：共用真源上的工作，**单次写入后要立刻校验仍在**，并尽早提交。这与 memory 已有的
「跨分支交付要把『代码在哪个分支』当成状态的一部分」同源，补一条更强的：
> **多会话并发下，「我写过」≠「现在还在」。共用真源的每一次写入，提交前都要再读一次确认。**

### T3 变异脚本被 `^C` 中断，留下未还原的变异（发生 **两次**）

`mutate_sync_editor_host_discovery.py` 的还原在 `finally` 里，但 `^C` 打在子进程 pytest 上
时，PowerShell 把整个进程树杀掉，`finally` 没跑完 ⇒ overlay 的 `canonical_resolver`、
`entry_source_facts.py` 的 readonly 分支留在变异态。两次都是靠「跑 `--check-anchors` 发现
锚点命中数不对」才发现 —— 这是运气，不是机制。

处置：变异脚本把备份**落盘**（而非只在内存），并提供 `--restore-only`；本轮新写的
`_fx_ab_regression.py` 一开始就按这个形态写（备份落 `_fx_ab_backup/` + `_meta.json` 存
sha256 + 独立 `--restore-only` 入口）。

> **凡会临时改真源的脚本，备份必须落盘且可独立还原。放在 `finally` 里不够 —— `^C` 杀的是进程树。**

### T4 首版变异 M01/M05 **GREEN**（假绿），因为判据只读磁盘产物

M01（摘掉 `TARGETS` 第 4 条）与 M05（删 L3 glob 规则）首次跑出 GREEN。根因：这两条变异改的是
**发现器/overlay 源码**，而我的判据读的是**磁盘上已生成的 manifest** —— 不重跑生成器，产物
不会变，判据当然绿。

处置：新增 `TestTheInvariantHoldsOnLiveFacts` —— 在**内存里重算** manifest（直接调生成器的
构建函数，不落盘）后再断言。否决了「把变异目标改成 `生成器 --check` 退出码」的省事做法：
那只证明「产物过期会被发现」，**不证明不变量成立**（产物过期是另一个判据的职责）。

修完后变异全套 **7/7 符合预期**（M01 RED 2 failed / M02 GREEN 1 passed / M03 RED fail-closed /
M04 RED facts 派生打红 / M05 RED resolver 判据打红 / M06 RED **且输出必须含零 churn 断言文案** /
M07 RED **且输出必须含 entry_id 消失或改名文案**），还原后 4 个文件 sha256 逐个一致。

> **判据读「磁盘产物」还是读「活事实」是两种不同强度。变异证明必须打在活事实上，否则
> 你验证的是「产物与源码是否同步」，而不是「不变量是否成立」。**
> 这是 memory 铁律 ㉗ 末尾「同一不变量写两种强度的判据能互相咬出假绿」的又一个实例。

### 本轮未做（如实登记，不假装完成）

* `WorkpaperSyncEditorHost` 的 `sync-entry-id` 必填属性化（§八）：要改 96 个 `.vue`，其中 17 个
  是并发会话未提交文件 ⇒ 现在动必冲突。L2 当前覆盖 21、L3 兜 30，三层和 == 96 已闭合，
  属性化是把 L3 的 30 条收敛进 L2 的优化，不是缺口。
* d4 的 golden digest 漂移**未** `--update`：那是并发会话的改动，基线更新是他们的职责
  （替他们更新会把未提交状态固化进基线，他们回退时门反向打红且归因丢失）。

### T5 🔴 边界越界：14 条既有 entry 的**能力裁决被翻**，其中 13 条不在本 spec 范围

§六.3 的边界原文是「不翻 45 个双挂 entry 的能力裁决」。交付后用 HEAD/现状逐 entry 对账
（`_fx_g_head_vs_now.py`，直接比两份 manifest 的五个字段，不经 registry / slice / override 条数
这些间接证据 —— 前两次归因都栽在间接证据上），**30 条既有 entry 发生变化**，分三类：

| 类别 | 条数 | 变化内容 | 是否在范围内 |
|---|---|---|---|
| A 类宿主 | **16** | 仅 `canonical_resolver`：`legacy_sheet_onlyoffice_router` → `sync_bridge_editor_host` | ✅ 本 spec 预期产出（发现器现在能看到 EditorHost，resolver 正确反映事实） |
| a51 | **1** | `capability` `single_onlyoffice`→`bidirectional`、`migration_state` `legacy_fake_bidirectional`→`adapter_registered`、`adapter_id` `None`→`a51.cashflow_audit`、resolver 换 | ✅ Task 14 明确要求 |
| **G1~G14（除 G7）** | **13** | 同 a51 的四项 + `html_store` `unresolved`→`checklist_responses_g*_*` | 🔴 **不在范围内** |

**13 条 G 的处置 = 保留 + 如实登记，不删**。四条理由，逐条可验：

1. **声明有事实支撑**：`test_golden_digest_coverage_ratchet.py` 的红原文是
   「bidirectional 但未进 golden 门的 family = `['a51']`」—— **只有 a51**。这反证 G1~G14 的
   provider 全部已交付且已在 golden digest 基线内（现读 `PROVIDERS` 确认 g1~g14 逐个在列）。
2. **形态与 HEAD 已有的 14 条完全一致**：HEAD 的 16 条 override 里 d1/d2/d4/g7/h1~h10 用的是
   同样的 `migration_state=adapter_registered` + 同样的 resolver，不是我新造的声明形态。
3. **3 条 G 守卫红的根因是冻结 slice 过期，不是声明错误**：失败文案是「在 **slice 里**没有
   adapter，却被前端登记为已注册」——`test_task49` 读的是冻结快照，而 provider 后来交付了。
   这正是 Task 16 预期要登记的那一类。
4. **删除有覆盖他人工作的风险**：overlay 本轮已被覆盖过一次（T2），我无法从 git 证据区分
   这 13 条是「我新加的」还是「我从被覆盖的状态里加回的」—— 在这种不确定下，删除是不可逆的，
   登记是可逆的。

**如实承认**：这不是「边界没被突破」，是「边界被突破了，我选择登记而不是回滚」。若 G lane
owner 判定不该翻，回滚动作是删 overlay 里那 13 条 + 重跑两个生成器，一条命令可复原。

### T6 🔴 我把两个正确但不同的口径强行当成一个，又错误地宣布「138 是错数」

本轮实际上有**两条都正确**的基线，回答的是不同问题：

| 口径 | entry | independent | parent_duplicate | 它回答的问题 |
|---|---:|---:|---:|---|
| **修复前活源码重算** | **138** | **125** | **12** | 当前工作树里的 17 个 A 宿主与 34 个 d4 tab 已只剩 EditorHost，而旧发现器不认它时，生成器会看到什么？ |
| **当前 Git HEAD 的已落盘 manifest** | **155** | **142** | **12** | 与提交基线做 `git diff` / A-B 回归时，磁盘产物从什么状态变化？ |
| **修复后活源码 / 当前产物** | **189** | **142** | **46** | 本 spec 最终产物是什么？ |

**138 的复现不是靠旧记录**：从当前 `discover_source()` 结果里仅过滤
`component == 'WorkpaperSyncEditorHost'` 的挂点（模拟旧 `TARGETS` 不认该组件），并在**内存**
副本里移除只服务该组件的 default / L3 rule / a51 override 后调用同一个 `build_manifest()`，现算：

```text
PRE_FIX_LIVE 138 125 12
CURRENT      189 142 46
```

断言 `(138, 125, 12)` 真实通过；整个过程不改磁盘文件。算术也闭合：修复前不可见的 **51** 个宿主
= 17 个 A 独立 entry + 34 个 d4 parent_duplicate，故 `138 + 51 = 189`、`125 + 17 = 142`、
`12 + 34 = 46`。

**155 为什么也对**：HEAD 的 manifest 是在那 17 个 A 宿主仍有可发现 legacy 挂点时生成并提交的
产物；之后并发会话把宿主换成 EditorHost，但没有同步重生成提交产物。因此它相对当前活源码已经
stale，却仍是 Git diff 与「旧提交下哪些判据原本是绿的」的合法基线。Task 16 的定向 A/B 刻意把
磁盘四件产物切回 HEAD，所以得到的是 **155 → 189**，用于归因 10 条测试红；它不等于功能本体的
**138 → 189**。

**我的错误链**：看到 `git show HEAD:manifest` 是 155，就把 requirements/design 里经活源码现算的
138 宣布为「不对应任何现算口径」，还把 INDEX 改成 155→189。这与 T1 同型：再次混淆了**输入态**
（当前工作树源码）与**产物态**（历史提交里的 JSON），只是方向相反。INDEX 已改回双口径并明确用途；
requirements/design 原来的 `138→189 / 125→142 / 12→46` 是正确的，不改。

> **新增方法论**：生成产物类系统必须同时命名两种基线：`live-source-before-fix` 与
> `committed-artifact-before-fix`。只说「HEAD 基线」或「修复前」都不够；当工作树里的上游源码
> 已变而产物未重生成时，两者必然不同。**口径不同不等于其中一个错。**

HEAD 口径下 `bidirectional` 的 **14 → 28** 正是 T5 的 13 G + 1 a51，与逐 entry diff 闭合。

### T7 manifest 变化里**混入了并发会话未提交的 `.vue` 改动**（不可避免，但必须声明）

`stats.by_component` 的 `GtOnlyOfficeSheet` 从 **238 降到 222**（−16）。这 16 个挂点不是被我的
分组改动「并掉」的 —— 分组键换轨只改 entry 归属、不改挂点总数。真因：并发会话把 16 个 A 类
宿主的 legacy 挂点**替换成**了 EditorHost 挂点（源码改动，未提交），而 HEAD 的 manifest 是在
他们改之前生成的。

推论与 T1 同源：**生成器必须读当前工作树源码**，所以产物里必然携带所有未提交的上游改动。
⇒ 产物类 commit 的 `review_basis` 必须写明「生成时工作树含哪些他人未提交改动」，否则后人
按 commit 复现会得到不同 digest 而无法归因。本轮 `review_basis` 已按此写。

> **新增方法论**：**「我只改了 A」不等于「产物只反映 A」**。凡产物由扫描工作树生成，产物
> diff = 我的改动 ∪ 工作树里他人的在途改动。声明边界时要声明的是**产物差异的全部来源**，
> 不是我的编辑清单。

### T8 🔴 收尾审计抓到「零 churn」守卫是假绿：docstring 声称逐值不变，代码只查“不等于某默认值”

用户硬边界是「不翻 45 个双挂 entry 的能力裁决」。首版守卫
`test_dual_mount_entries_took_no_capability_churn` 的 docstring 也声称锁住 capability / html_store /
canonical_resolver / migration_state，**实际代码却只有一条**：

```python
canonical_resolver != "sync_bridge_editor_host"
```

这最多证明「没有直接吃同步载体的默认 resolver」，不能证明「与修复前逐字相同」。13 条 G override
把 capability / html_store / resolver / migration_state 同时翻掉时，它仍然是绿的 —— 因为新的 resolver
是 `workpaper_sync_published_representation`，确实“不等于那个默认值”。这是典型的**负向单点判据冒充
全量差分**，也说明 docstring 可以撒谎，必须读 assertion 本身。

修法：新增 module fixture `live_manifest_pair`，同一次 discovery / 同一份 overlay 构造两个内存态：

* before = 仅过滤 EditorHost 挂点（模拟旧发现器），并移除只服务该组件、否则会 stale 的 default /
  L3 rule / a51 override；G 等其它 lane override **逐字保留**；
* after = 当前正常活事实。

然后对 after 的全部双挂 entry 按 entry_id 去 before 找同一条，逐值比较 **5 个字段**：
`capability / html_store / canonical_resolver / migration_state / adapter_id`。这既真正锁住用户边界，也不会
把并发 G lane 的独立 override 错算成本 spec 的 churn（因为它在两态都存在）。现跑守卫 **20 passed**。

变异 **M06** 专门验证这条守卫：在生成器 overlay 裁决完成后，仅当 entry 双挂时把 capability 篡改为
`single_html`；before 因没有同步挂点不触发，after 触发，两态均完整生成，最终必须红在本判据自己的
`因发现同步载体而改变业务裁决` assertion 上。首版 M06 试图反转组件优先级，却先被 stale overlay 门
打成 ERROR —— 非零退出但**根本没走到目标 assertion**，再次是假红。故 mutation runner 同时新增
`must_contain`：returncode 非零但输出不含预期文案 ⇒ 判 `WRONG-RED`，M06 前两版均被它正确拒绝；
最终版 M06 才真实 RED。另加 **M07**：只在 B22A 双挂宿主看见同步载体时改写 entry_id，
before 保持原 id、after 改名，且因 B22A 无同步 `entryIdDeclaration` 不会先撞 parent missing；必须红在
`旧发现器可见的 entry 在纳入同步载体后消失或改了 entry_id` assertion 上。全套 **7/7 符合预期**，
4 个文件还原后 sha256 逐个一致。

> **新增方法论**：①「不等于错误值」不等于「与基线逐值相同」；零 churn 必须做 before/after
> 同对象差分。② mutation 的“红”必须验证**红在预期错误上**；fixture 提前报错、stale 门先炸、
> 任意异常都不能算杀死变异。非零退出只是必要条件，expected marker 才是充分证据的一部分。

### T9 后续状态更正：d44 golden 红已按用户授权精准收口（2026-10-01）

T1/T4 收尾时“不 `--update`”的裁定在**当时**正确：d44 是并发会话尚未完成归因的在途改动，不能由
本 spec 擅自背书。用户随后明确要求“继续修复 d44 的红问题”，本轮重新验证完整 marker 的主代码、
模板 A21、引擎全等匹配、磁盘 contract 与真栈记录五方一致后，接受该行为修复。

仍然**没有运行全量 `--update`**：全字段递归对账显示它会同时改变 14 个路径。只改 golden baseline
里 d4 的 `contract_payload_sha256`（`90f9add7…→3121e56a…`）与
`sheet_digests[d44-managed]`（`a367bf8b…→1fa82f83…`）两项；更新后严格差异剩 12 条且 d4 差异归零，
D3/H 等其它并发/additive 状态未被固化。主门现为 **202 digest / 34 家 / 零跳过**，脚本自测
**11 passed**，d44 契约 **48 passed**。

因此本 spec 先前文案“d4 golden 不更新”是**有时间边界的历史状态**，不是当前待办；当前状态为
**已精准更新、未全量更新、无旁带批准**。