# 任务：冻结契约的读侧重建 + 遗留 operation 结算

> 需求 / 设计见同目录。标记纪律：`[x]` 必须有代码 + 测试通过证据；
> 外部依赖或待环境如实标 `[ ]`，并写明「代码已改但未实测」。
>
> 本 spec 预期**零迁移**（只补读路径）。若实施中发现需要迁移，先在 tasks 里登记理由。

## A. 基线

- [x] 1. 冻结开工基线
  - 在最新远端上建锁定分离头候选 worktree；记录 HEAD 与迁移最高号（三路现扫：
    磁盘 / 共享库 `schema_version` / 远端 `git ls-tree`）。
  - 只读复核 §1.2 的四项事实（definition 行 `approved` / blob `published` / 相对路径 /
    磁盘文件字节数），逐项写成可比对的断言（不是抄本文档的数字）。
  - 跑并记录将被本 spec 打红的既有判据的**开工态**：冲突 / 裁决 / merge 族、
    `test_schema_conflict_adjudication_parity.py`、`test_task14_merge_conflicts.py`。
    基线里本来就红的项逐条登记，收尾时按差集归因。

## B. 读路径：按冻结 slot 读回契约（Property 1）

- [x] 2. 提取公共 definition 读取能力（ADR-FC-002）
  - 把 `PublishedIdentityObserver._read_definition_payload` 与
    `_resolve_definition_blob` 提取成模块级公共函数（保留 `stage` / `context` 错误语义），
    observer 改为委派。
  - 守卫：提取后 observer 的全部既有用例必须仍绿；且断言「字节读取与 digest 复核
    在仓库里只有一处实现」（AST 或函数身份比对，不是文本 grep）。
  - 变异：让 observer 不再委派而是自己留一份拷贝 ⇒ 该守卫必须红。

- [x] 3. 新增 `FrozenContractReader`（ADR-FC-001）
  - 输入 `bundle_snapshot`（已含三 slot 的 `type/ref/digest`），输出 `SyncContract`：
    `slot_ref` → definition 行 → `blob_artifact_id` → artifact row → 仓储
    `resolve_relative_path()` → 读字节 → `json.loads` → `parse_contract()` →
    断言 `canonical_sha256 == slot_digest`。
  - 错误分型（R1.3）：definition 行不存在 / 非 `approved` / blob 不在盘 / digest 不符
    —— 四类必须各自可辨（不同 `error_code` + 中文原因），不得统一报「契约漂移」。
  - 🔴 只按 bundle 的 `slot_ref` 取，**禁按 `logical_id` + 最新版本**（实测同一
    `logical_id` 已有多代并存：`d4.revenue_detail` 2 行、`d2.inspection` 2 行）。

- [x] 4. Property 1 守卫
  - 对**每一个**已 approved 的 bundle，读回的 `canonical_sha256` 必须等于其
    `contract_slot_digest`（分母 = 库里的 bundle 全集，不是挑一个）。
  - 变异：把读路径改成「按 contract_id 从磁盘现取」⇒ 必须红，且红的形态是
    「取到了新契约」（核对 `canonical_sha256` 确实变成当前 registry 的 digest，
    不是别的失败）。

## C. 读侧入口改为默认取冻结契约（Property 2）

- [x] 5. `preview` / `resolve` / `retry` 的 contract 参数改可选（ADR-FC-003）
  - 省略 ⇒ 内部按 bundle 读冻结契约；显式传入 ⇒ 仍跑
    `assert_frozen_contract_matches_bundle`（**判据一个字不改**）。
  - 响应加 `contract_source`（`frozen` / `explicit`）+ `frozen_digest`
    （+ 可现取时的 `current_registry_digest`）。
  - 守卫：显式传入不匹配的 contract 仍必须 422 且 `error_code` 仍是
    `frozen_contract_digest_drift`（不得因新增默认路径而放宽）。

- [x] 6. 前端如实标注「历史契约」
  - `workpaperSyncDto.ts` 解析 `contract_source` 与两个 digest；冲突面板在
    `contract_source === 'frozen'` 时显示中文标注（说清「这是该 operation 冻结的
    契约版本，与当前模板可能不同」）。
  - 🔴 `contract_source` **只作标注**，不得用它门控任何按钮可用性（守卫断言）。
  - 守卫：DTO 不解析该字段时面板不得静默显示成「当前契约」（变异必须红）。

- [x] 7. Property 2 真库实测
  - 对遗留 operation `11809f53…`（冻结旧契约 `75fca57d…`）调冲突预览：必须 200，
    且逐项 `business_label` / `value_type` 来自**旧**契约；响应 `contract_source="frozen"`。
  - 反向对照：显式传入新契约 `645e0500…` ⇒ 必须 422 `frozen_contract_digest_drift`。

## D. 遗留 operation 结算（Property 3）

- [x] 8. 按 §5 待拍板选定的出口实现
  - 若选**正式裁决**：经既有 resolve 端点逐条裁决，落地成新 representation +
    裁决轨迹（`resolved_by` / `resolved_at` / `resolved_value` 三者齐备）。
  - 若选**显式作废**：新增 supersede/abandon 语义 —— 保留冲突行（标
    `superseded_at` + 原因 + 操作者），operation 落终态；**不物理删除冲突行**。
  - 两条路都禁止裸 SQL 改 `state`（会破坏版本链与审计链）。

- [x] 9. 结算后复核（R3.4）
  - 该 operation 终态 / 冲突行 resolved-or-superseded 状态 / 版本链指针 /
    审计轨迹逐项可查，写成可重跑的只读探针。
  - 守卫：断言「状态变了但内容没落地」这种形态不可能出现（例如终态为 applied 时
    必须有新 representation 且 revision 前进）。

  > 已交付，证据见 §R10。**该条目标记为 `[x]` 的依据**：探针 + 八条判据守卫 +
  > 5 条变异全 RED + 1 条阴性对照 GREEN，且真库跑通（101 passed / 0 skipped）。

## E. 收尾

- [x] 10. 回归与变异
  - 后端：冲突 / 裁决 / merge 全族 + 本 spec 新增守卫；与开工基线逐节点差集比对，
    新增失败必须为 0。
  - 前端：sync 目录；区域类型检查相对基线 added 0。
  - 变异逐条 RED 并核对红在预期用例（至少含：读路径回 registry、observer 留第二份拷贝、
    `contract_source` 被用作能力门控、显式传入不匹配时放宽）。

- [-] 11. 真库验收（只用【测试】项目）
  - 写入前存**全文快照**（不只存哈希），验收后逐字段复原并对账。
  - 遗留 operation 结算后，测试项目的其余数据必须零漂移。

- [~] 12. 语义审查、INDEX 登记、同步远端后单提交与版本化推送
  - 五角色复盘；只提交本 spec owned 文件；
    `git diff --check` + `check_staged_tree_self_consistency.py`；
    `push_version.py push --branch spec/disclosure-note-doc-upload-and-batch-fill`。
  - 归档后回填 `_archive/174-wp-sync-conflict-adjudication-and-d4-32-modeling/tasks.md`
    的 12.f（**已归档 spec 不回填修改正文**，勘误登记在 INDEX 速递区）。

## §待拍板（实施前必须定）

1. 遗留 operation `11809f53…` 走**正式裁决**还是**显式作废**？（design §5.1）
2. 若旧契约 payload 过不了当前 `parse_contract`，写兼容层还是如实拒绝？（design §5.2）
3. `contract_source` 的展示位置与文案。（design §5.3）

---

## 勘误与修正（2026-11-15 开工前现算；append-only，上文原结论不改）

> 本节全部结论来自代码现读 + 共享库只读现算，不引用上文数字。
> 与上文冲突时**以本节为准**。原 §待拍板 三问的答案见 §E.7。

### E.1 🔴 阻断 1：任务 8「正式裁决」出口技术上不可达（双重硬拦）

**第一拦 —— 24 条冲突全部不可按值裁决。**

```
working_paper_sync_conflict（operation 11809f53…，24 行）
  conflict_kind    = 'schema'   （24/24）
  schema_anomaly   = NULL       （24/24；V264 之前的历史行，成因已丢失）
  suggested_action = 'manual_merge'
```

`ConflictPreviewItem.adjudicable_by_value_choice`（`conflict_resolution.py:694`）在
`schema_anomaly is None` 时 fail-closed 返回 `False` → 真调 resolve 时
`apply_resolutions`（`conflicts.py:686`）抛
`StructuralConflictNotAdjudicableError`。**逐条选边在数据层就不成立**，不是前端不给选。

**第二拦 —— 即使补齐成因，apply 仍会被 fence 拦。**

`resolve` → `apply_durable_incoming` → `_fence_before_publish` →
`assert_final_authorization`（`oo_to_html.py:995`）的 `approved_bundle_identity` 判据
（`oo_to_html.py:1079`）要求 entry **当前** approved bundle 等于 application 冻结的那份：

| 项 | 值 |
| --- | --- |
| application 冻结 bundle（`1504768f`）→ 契约 | `75fca57d…` |
| entry 当前 bundle（`649af940`）→ 契约 | `645e0500…` |
| `working_paper_sync_entry_state.current_representation_id` | `a4fe664c…`（generation 5） |

必不相等 ⇒ `ApprovedBundleReplacedError`。**这不是缺陷**：契约换代后不允许用旧
bundle 产新 representation，是保护审计链的正确行为。

⇒ **§待拍板 1 的「正式裁决」选项不存在**，本 spec 只剩「显式作废」一条路。

### E.2 🔴 阻断 2：任务 5 的 `retry` 不是出口，R2.4 对 retry 不成立

实测 `retry`（`conflict_resolution.py:1299`）**不调**
`assert_frozen_contract_matches_bundle`，它直接委派
`coordinator.apply_durable_incoming`，内部走 E.1 第二拦的同一个 fence。

⇒ 读路径修好后：`preview` 能真 200（它只读冲突行、不 publish）；
`retry` 仍失败，但错误码从 `frozen_contract_digest_drift` 变成更硬的
`final_fence_approved_bundle_replaced`。

**R2.4「`frozen_contract_digest_drift` 不得再出现在用户无法继续的路径上」只对
preview 成立**，对 retry 不成立 —— 任务 5 的验收口径按此改写，不得宣称 retry 也通了。

### E.3 🔴 阻断 3：「显式作废」不能复用 `superseded_at`

冲突表已有 `superseded_at` 列，但它**只有一个写入方**：
`repository.py:3328` 的 `mark_conflicts_superseded`（观测同步，语义 =「本轮不再出现的
旧 key」），且同函数对**本轮命中**的行执行 `row.superseded_at = None` **清零**
（`repository.py:3385`）。

⇒ 拿它存「人工作废」会被下一次重观测静默抹掉，且同列两种含义 = 第二真源。

**处置**：新增 `abandoned_at` / `abandon_reason` / `abandoned_by` 三列。

**迁移号按三路现扫取号（2026-11-15，开工时）**：磁盘 `backend/migrations` 最高
**V271** / 共享库 `schema_version` 最高 **271** / 远端 `git ls-tree origin/<当前分支>`
最高 **V271** —— 三路一致。⇒ 本 spec 若确需迁移，取 **V272**（+ `R272`）。

> 勘误（本行）：初稿本处曾写 `V265`，现算发现 `V265__add_export_unit_policy_columns.sql`
> 已被占用（已于 2026-11-06 落共享库）⇒ 作废。

这与上文「本 spec 预期零迁移」冲突 —— 按本文件开头的纪律，理由在此登记：
**零迁移只对读侧（任务 2~7）成立，任务 8 必然破例**。

### E.4 事实性错误更正

| 位置 | 上文写的 | 现算实际 |
| --- | --- | --- |
| 任务 6 | 改 `workpaperSyncDto.ts` | 冲突预览解析在 **`workpaperSyncPresentation.ts`** 的 `parseConflictPreview`（`workpaperSyncDto.ts` 的 `conflictCount` 是 operation snapshot 的另一个字段） |
| 任务 6 | —— | `contract_source` / `contractSource` 全仓**零命中**，是纯新增字段 |
| 任务 5 | 「preview / resolve / retry 都跑 `assert_frozen_contract_matches_bundle`」 | 只有 **preview（L985）/ resolve（L1139）/ rollback（L1423）** 三处跑；**retry 不跑**（见 E.2） |
| 任务 4 变异 | 「改成按 contract_id 从磁盘现取 ⇒ 红」 | 磁盘上**新旧两份都在**（`75fca57d….json` 与 `645e0500….json`）。若实现成「按 slot_digest 找文件」就等价于正确实现 ⇒ 变异会**存活**。变异必须写成「按 **registry 当前 alias** 取」 |
| 任务 4 分母 | 「每一个已 approved 的 bundle」 | `state='approved'` 共 **265** 个，其中 **2** 个是 `contract:none:v1` typed null marker（`marker:contract:none:v1`，无 definition 行）。分母须先按 `slot.is_definition` 分流，否则这 2 条会被误报成「数据缺失」 |
| 任务 2 | 「observer 改为委派」 | `_read_definition_payload` 有 **3 个外部调用方**（`publish_time_structure_hash.py:201`、`scripts/fix/finalize_ready_candidate_representation_only.py:128`、observer 内 L873）+ **5 个测试文件** monkeypatch 它。提取时**必须保留同名私有方法作薄壳委派**，否则调用方与 monkeypatch 全断 |
| §2 风险段 | 「`d4.revenue_detail` 2 行 / `d2.inspection` 2 行」 | 实测 `d4.revenue_detail` **46 代**、`d2.inspection` **5 行**；全库 `kind=contract` 共 89 个 logical_id 存在多代并存。「禁止按 logical_id + 最新版本取」这条纪律的必要性比上文写的**强得多** |

### E.5 行数门余量（决定 design §3「或并入 `resolution.py`」不可行）

口径 = `check_file_size.py` 的 `len(text.splitlines())`（与白名单一致）。

| 文件 | 当前 | 白名单基线 | +5% 阈值 | 余量 |
| --- | --- | --- | --- | --- |
| `backend/app/services/workpaper_sync/conflict_resolution.py` | 1712 | 1647 | 1729 | **17 行** |
| `backend/app/services/workpaper_sync/published_identity_observer.py` | 1658 | 1658 | 1740 | 82 行 |
| `backend/app/routers/wp_sync_router.py` | 3486 | 3467 | 3640 | 154 行 |
| `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncPresentation.ts` | 1017 | — | 默认 1500 | 483 行 |

⇒ `conflict_resolution.py` 只剩 17 行余量，任务 3/5 的新增（4 类错误分型 + 可选参数
+ `contract_source` 字段）**必须抽成新模块**，并顺手把 `preview` 的契约解析段挪出去腾空间。
`check_file_size.py` 用的是 `splitlines()`，不是 `len(text.split("\n"))` —— 上一行数字
按前者算。

### E.6 范围：不是「一条遗留 op」，是平台级 17 条

`working_paper_sync_operation` 中 `state='conflict'` 共 **17** 条，
**全部**满足「冻结契约 ≠ 该 entry 当前契约」：

| 项目 | 条数 | 备注 |
| --- | --- | --- |
| 【测试】公式同步乙 | 1 | 24 条冲突（本 spec 的验收对象） |
| 【测试】OO 公式重算验收 | 1 | 3 条 |
| 【测试】在线编辑回表单验收 | 1 | 3 条 |
| **重庆和平药房连锁（真实）** | 4 | 108 / 81 / 33 … 条冲突 |
| **重药控股安徽（真实）** | 11 | 单个 entry 上冻结了 **4 代**不同契约（`9fa97e7f` / `e80dd395` / `c2f068ef` / `45dc6ac9` 系） |

⇒ 本 spec 只交付**通用读侧能力**，用【测试】那一条做 Property 2 验收。
真实项目那 14 条**是否处理必须用户明示**（写入型验收只用【测试】项目的纪律）。

### E.7 §待拍板 三问的答复（开工前裁定，用户 2026-11-15「按建议来」）

1. **遗留 operation 走哪条出口**：**显式作废**。依据 E.1 —— 「正式裁决」双重不可达，
   不存在这个选项。作废语义用 E.3 的新列，不动 `superseded_at`。
2. **是否写旧契约解析兼容层**：**不写**。已实测旧 payload
   `parse_contract()` 通过、`canonical_sha256 == 75fca57d…` 与 definition 行
   `sha256`、blob 文件名**三者逐字相等**。兼容层是零收益的额外代码。
3. **`contract_source` 展示位置**：**预览响应级一条横幅**，不逐条标注
   （24 条同属一份冻结契约，逐条标注是噪音）。

### E.8 实施顺序（本 spec 按此推进）

1. 任务 1 基线 → 任务 2~4 读路径 + Property 1 守卫（**零迁移、零行为回退风险**）。
2. 任务 5 **只改 preview**（`resolve` / `retry` 的参数保持必填，留待任务 8 拍板后统一）。
3. 任务 6 前端横幅 + 独立提交。
4. **暂停**在任务 8 前，把 E.1 / E.2 / E.3 交用户确认作废语义与迁移号，再动写侧。
5. 任务 9~12 按纪律走候选 worktree + 只写【测试】项目。

**任务 5 的验收口径按本节改写**：preview 成功 + `contract_source="frozen"` +
逐项用旧契约标签；`resolve` / `retry` **不在本 spec 的「已通」范围**。

---

## 实施记录（2026-11-15；任务 1~7 已交付，8 起等拍板）

> 本节是 append-only 的实施证据。数字全部现算，不抄上文。

### R1. 迁移号（开工时三路现扫）

| 路 | 最高号 |
| --- | --- |
| 磁盘 `backend/migrations` | V271（259 个 `V*.sql`） |
| 共享库 `schema_version` | 271 |
| 远端 `git ls-tree origin/<分支>` | V271 |

⇒ 三路一致。本 spec **读侧零迁移**；任务 8 若确需 `abandoned_*` 三列，取 **V272**。

### R2. 交付物

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `backend/app/services/workpaper_sync/frozen_definition_blob.py` | 331 | **新**：字节读取 + digest 复核的唯一实现（ADR-FC-002），四类错误分型 |
| `backend/app/services/workpaper_sync/frozen_contract_reader.py` | ~420 | **新**：按 `contract_slot_ref` 读回 `SyncContract`（ADR-FC-001），六类错误分型 |
| `backend/app/services/workpaper_sync/conflict_preview_contract.py` | 159 | **新**：「该用哪份契约」收在一处（ADR-FC-003） |
| `backend/app/services/workpaper_sync/published_identity_observer.py` | 1658 | 两个私有方法改**薄壳委派**（保留同名同签名，3 个生产调用方 + 5 个测试文件依赖） |
| `backend/app/services/workpaper_sync/conflict_resolution.py` | 1724 / 阈值 1729 | `preview` 的 `contract` 改可选；`ConflictPreview` 加 `contract_source` |
| `backend/app/routers/wp_sync_router.py` | 3587 | 预览端点不再预取 registry 契约（−2 行） |
| `audit-platform/frontend/.../workpaperSyncPresentation.ts` | 1065 | 四个 DTO 字段 + 两条横幅文案常量 |
| `audit-platform/frontend/.../WorkpaperSyncConflictDialog.vue` | 835 | 「历史契约」横幅（只作标注） |
| `backend/tests/workpaper_sync/test_frozen_contract_read_path.py` | 764 | 任务 2~4 守卫（单一实现 / 错误分型 / 不自拼布局） |
| `backend/tests/workpaper_sync/test_frozen_contract_preview_contract.py` | 382 | 任务 5~6 守卫（三分支 / DTO 必需字段 / 不只作标注但必须显示） |
| `backend/tests/workpaper_sync/test_frozen_contract_read_path_pg.py` | ~330 | **Property 1**（真库，分母 = 全部 approved bundle） |

### R3. Property 1 真库实测（分母 = 库全集）

```
approved definition-slot bundles: 263
  磁盘文件在位: 254   ← 逐项 canonical_sha256 == contract_slot_digest ✅
  磁盘文件缺失:   9   ← 如实报 frozen_contract_blob_unreadable（R1.3 可辨性）
```

🔴 **这 9 个缺失是平台级历史数据缺口，不是本 spec 引入**（现算集合已冻结成棘轮
`_KNOWN_MISSING_CONTRACT_BLOBS`，断言「新增即红 / 补齐须删行」）。其中
`661bb271…` 是 **D2 应收账款当前生效**的契约 —— 补齐它属数据修复动作，须单独走
「备份 → 重建 → 逐项对账」，不能混在读侧 spec 里顺手做。

### R4. Property 2 真库验收（遗留 operation `11809f53…`）

| 分支 | 结果 |
| --- | --- |
| ① 省略 `contract`（新默认） | ✅ `contract_source=frozen` / `frozen_digest=75fca57d…` / `conflict_count=24` / 逐项 `value_type=text` |
| ② 显式传**新**契约 `645e0500…` | ✅ 仍被拒 `frozen_contract_digest_drift`（判据一个字没放宽） |
| ③ 显式传**旧**契约 `75fca57d…` | ✅ `contract_source=explicit` / 24 条 |

### R5. 回归（与开工基线逐节点差集）

选集：`test_task27_conflict_resolution` / `test_task75_published_identity_observer` /
`test_task14_merge_conflicts` / `test_schema_conflict_adjudication_parity` /
`test_task28_sync_router`

| | 基线 | 收尾 |
| --- | --- | --- |
| testcases | 885 | **885** |
| not-passed | 20 | **20** |
| after 独有（新增红） | — | **0** |

20 条红全部是 HEAD 预存（单一根因：`test_task26_oo_to_html_pg` 的临时 schema 只跑 V151，
而 `export_surface_class` 是 V265 加的列 ⇒ `UndefinedColumnError`；另 5 条是 router
端点计数漂移，均属并发会话新增端点导致）。

补充：
* `test_frozen_contract_read_path.py` + `test_frozen_contract_preview_contract.py` = **45 passed**
* `test_frozen_contract_read_path_pg.py` = **6 passed**（带 `GT_REQUIRE_PG=1`，非 skip）
* 前端 sync 目录 = **58 文件 / 1642 用例全绿**
* 行数门（13 个改动文件）= **exit 0**

### R6. 变异证明（全部核对红的形态）

**任务 2（ADR-FC-002，5/5）**

| # | 变异 | 结果 |
| --- | --- | --- |
| M1 | observer 不再委派，自己留一份读法 | RED ✅（红在 `test_canonical_digest_check_has_exactly_one_site`） |
| M2 | 薄壳绕过 `_resolve_definition_blob` | RED ✅（红在 `test_read_payload_calls_resolve_blob`） |
| M3 | 公共模块不再做 digest 复核 | RED ✅ |
| M4 | 四类失败合并成一个 error_code | RED ✅（红在 `test_four_failure_kinds_are_distinguishable`） |
| M5 | `resolve_definition_blob_path` 自拼 `definition_store` 布局 | RED ✅（红在 `test_no_hardcoded_definition_store_layout`） |

**任务 4（Property 1，3/3）**

| # | 变异 | 结果 |
| --- | --- | --- |
| M1 | 读路径改回按 registry 当前 alias 取 | RED ✅（**208** 个 bundle 报「与冻结 slot digest 不一致」—— 形态正是「取到了新契约」） |
| M2 | 阴性对照（只加一行注释） | GREEN ✅（证明判据不是「对任何改动都红」） |
| M3 | 按 `logical_id` 取最新 definition | RED ✅（**168** 个不一致） |

**任务 5（ADR-FC-003，5/5）**

| # | 变异 | 结果 |
| --- | --- | --- |
| M1 | 省略 `contract` 时不读冻结契约 | RED ✅ |
| M2 | 显式传入不再跑原判据 | RED ✅ |
| M3 | 省略时返回 `source='explicit'`（来源撒谎） | RED ✅ |
| M4 | 读冻结失败时报成 `digest_drift`（成因碾平） | RED ✅ |
| M5 | 阴性对照（只加注释） | GREEN ✅ |

**任务 6（前端，3/3）**

| # | 变异 | 结果 |
| --- | --- | --- |
| M1 | DTO 对 `contract_source` 宽松解析（缺省成 explicit） | RED ✅ |
| M2 | 未知字面量被当成 frozen | RED ✅ |
| M3 | 横幅文案暗示「无法操作」 | RED ✅ |

### R7. 实施中修正的设计偏差（如实登记）

1. **`parse_contract` 不得传 `adapter_id`**：那是「`contract_id` 必须等于文件名」的
   双向锁（CS-2），只有**从磁盘按文件名读**的调用方才该传。本读法的身份真源是
   bundle 的 `slot_ref` + `slot_digest`。
2. **`parse_contract` 的失败要 catch `SyncDomainError`**，不能只 catch `ContractError`：
   第一段 `validate_contract_payload` 抛的是 `IdentityError`，两者是**兄弟**（都直接
   继承 `SyncDomainError`）。只 catch 后者会让「payload 缺 schema_version」冒泡成 500。
3. **observer 薄壳必须仍走 `self._resolve_definition_blob`**（只把「读字节 + decode +
   digest」委派出去）：那一层是既有测试 monkeypatch 的接缝，绕过它等于让那些用例
   改测一条不再是生产路径的分支（假绿）。
4. **Property 1 的最终 digest 对账在健康数据上是冗余的**（`read_definition_payload`
   已保证 payload ↔ definition 行 sha256，而 definition 行 sha256 恒等于 bundle slot
   digest）。它只在「definition 行与 bundle 不同步」这一数据损坏形态才有效 ——
   因此把它写成**等价变异会被判 GREEN**，任务 4 改用阴性对照。
5. **「`contract_source` 不得门控」的判据要精确到「门控的是不是控件」**：
   横幅元素自身的 `v-if="contractSource === 'frozen'"` 是**允许**的（否则无法实现
   「只在历史契约时显示」）。禁掉它等于禁掉需求本身。
6. **`conflict_resolution.py` 行数门只剩 5 行余量**（1724 / 1729）⇒ 新增逻辑
   一律抽模块（`conflict_preview_contract.py`），不得就地在 `preview` 里加。
7. **测试文件超 800 行须拆分而非加白名单**（memory 铁律）：任务 5~6 的守卫拆到
   `test_frozen_contract_preview_contract.py`（382 行），原文件 764 行。

### R8. 任务 8 起的状态（等用户拍板）

按 E.1~E.3 的现算结论：
* **正式裁决**出口双重不可达（24 条 `schema` + `schema_anomaly=NULL` ⇒
  `StructuralConflictNotAdjudicableError`；且 `ApprovedBundleReplacedError`）⇒
  只剩「显式作废」一条路；
* 作废须新起 `abandoned_at` / `abandon_reason` / `abandoned_by`（**V272**），
  不得复用 `superseded_at`（会被下一次重观测清零）；
* 平台级共 **17 条** `state='conflict'` operation（真实项目 14 条），本 spec 只交付
  通用读侧能力，真实项目那 14 条**是否处理须用户明示**。

**因此任务 8~12 未开工**，等用户对「作废语义 + 迁移号 + 是否处理真实项目」拍板。

### R9. 任务 8 实施记录（2026-11-16；出口 = 显式作废，已交付代码 + 测试）

按 §E.1 / §E.3 / §E.7 的裁定实施「显式作废」。**未实现「正式裁决」**（E.1 已证双重不可达），
**未改** `assert_frozen_contract_matches_bundle` / `load_bundle_snapshot` / definition store 布局。

#### R9.1 迁移号（实施时三路现扫 —— 与 R1 不同，登记在案）

| 路 | 最高号 | 备注 |
| --- | --- | --- |
| 磁盘 `backend/migrations`（**排除本人新增文件**） | **V272** | 开工时 V272 = `custom_template_publication_registry`（并发会话新加，落库后已入库 `9bb4ad7fe`） |
| 共享库 `schema_version` | **272** | 现查 |
| 远端 `git ls-tree origin/<分支>` | **272** | 现查 |

⇒ `max(三路) + 1 = 273` ⇒ 取 **V273**（+ `R273`）。**与 §E.3 预告的 V272 差 1**，原因是
并发会话在本任务开工后新增并推送了 V272（`9bb4ad7fe feat(server-custom-ingestion):
publication registry 落库（V272）`）。按「改未推送一侧 / 取 max+1」的纪律升号为 V273。

🔴 **V273 已应用到共享库**（`schema_version` 现 273 / 263 行）：主工作区的后端在实施期间
启动过，运行时迁移把 V273 落到了共享库。三列与 `ck_wpsc_abandon_triplet` 实测在位。这是
**只加列 + 加约束**的幂等迁移（`IF NOT EXISTS`），对既有数据零影响，无回填、无改写。

#### R9.2 交付物

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `backend/migrations/V273__sync_conflict_abandon_columns.sql` | 61 | **新**：三列（`IF NOT EXISTS`）+ `ck_wpsc_abandon_triplet`（三列同生共死 + 原因非空白） |
| `backend/migrations/R273__rollback_sync_conflict_abandon_columns.sql` | 27 | **新**：有作废行即 `RAISE EXCEPTION` 拒绝回滚，否则删约束 + 三列 |
| `backend/app/models/workpaper_sync_models.py` | 1183 | `WorkpaperSyncConflict` 加三个 `Mapped[]`（与 V273 三层一致） |
| `backend/app/services/workpaper_sync/conflict_abandon.py` | 428 | **新**：`ConflictAbandonService` + 四个异常 + 三个纯函数 + `AbandonOutcome` |
| `backend/app/routers/wp_sync_router.py` | 3640 / 阈值 3640 | `POST …/operations/{id}/abandon`；`abandon_conflicts` 登记进 `_WRITE_ACTIONS`；四个新 `error_code` 进 `_ERROR_CODE_STATUS` |
| `backend/tests/workpaper_sync/test_conflict_abandon.py` | 474 | 51 例离线：终态取值 / 原因 / 操作者 / 状态准入 / AST 结构（不裸 SQL、不删行、不碰 `superseded_at`）/ 三层一致 / 路由形态 |
| `backend/tests/workpaper_sync/test_conflict_abandon_endpoint.py` | 321 | 12 例端点级：401 / 只读 403 / 复核 放行 / 编辑 放行 / 非成员 403 / admin 放行 + 操作者不取请求体 + 缺原因 422 |
| `backend/tests/workpaper_sync/test_conflict_abandon_pg.py` | 746 | 17 例真库：三列真落库 / 不删行 / **不碰 `superseded_at`** / 幂等零写入 / 三种拒绝 / DB 两道锁 |
| `backend/tests/workpaper_sync/test_task28_sync_router.py` | 1932 | 路由清单追加 `("POST", "/operations/{op}/abandon")` |

#### R9.3 裁定与实现偏差（如实登记）

1. **终态 = `OperationState.superseded`**（不新造字面量）。现算 `conflict` 的**终态后继有两个**：
   `superseded` 与 `authorization_stale`（§E.7 与 design ADR-FC-004 均未区分这两者，只写
   「落终态」）。选前者：`authorization_stale` 的语义是「授权在裁决途中失效」（由
   `assert_final_authorization` 的 fence 触发），而作废是人工作出的业务决定；用它会让
   timeline 把作废误报成授权事件。判据 `test_the_other_terminal_successor_means_something_else`
   把这条选择理由写成可证伪断言。
2. **鉴权挂 `require_project_access("review")`**（路由级 `dependencies`）。现读确认
   `_guard`（`SyncEndpointGuard`）**不判项目成员级别** —— 它只做 scope 可见性 / workflow 锁 /
   action 词表，`WpGateVisibilityProbe` 的 `readonly` 只进 `observed` 字段、不拦写。所以只读成员
   能过词表检查。因此额外显式挂 review 门（作废是复核级动作）。**范围外登记（未改）**：
   `resolve_conflicts` / `retry_apply` / `rollback` 等既有写端点同样只靠 `_guard`，只读成员可能
   通过 —— 属平台级鉴权欠账，不在本 spec 范围。
3. **🔴 真库守卫抓到一个真迁移缺陷并已修**：`ck_wpsc_abandon_triplet` 的第一版存在性判定只查
   `pg_constraint.conname`。该目录是**整库共享**的，于是「同库另有 schema 有同名约束」时
   `IF NOT EXISTS` 判为已存在 ⇒ **静默跳过建约束** ⇒ 残缺写入（只写 `abandoned_at`）照样成功。
   PG 守卫（临时 schema + 同名表）实测抓到，改为按 `pg_class` + `pg_namespace` +
   `current_schema()` 三向限定。变异 `e1-constraint-schema-blind` 钉住这条。
4. **幂等语义**：同 operation + 同原因 ⇒ 返回既有作废事实、**零写入**（不追加 event）；
   同 operation + **不同**原因 ⇒ `conflict_not_abandonable`（同一冲突集的作废理由必须唯一）。
   后一条不是 R3.3 的字面要求，是为「审计轨迹不自相矛盾」加的（有判据钉住）。
5. **作废覆盖全部冲突行（含 `superseded_at` 非空的）**：刻意不用 `repo.load_conflicts()`
   （默认滤掉 superseded）—— 只盖当前可见集会让 superseded 行永远停在「既没裁决也没作废」，
   而它们在审计上同属这一批。

#### R9.4 验证数字

| 项 | 结果 |
| --- | --- |
| 新增三文件（离线 + 端点 + 真库） | **82 passed**（51 + 12 + 17 + 2 配对守卫），0 skipped |
| 回归选集（task28 / task27 / 读侧守卫 / 配对） | 282 passed，5 failed |
| 那 5 条 failed | **全部在干净 HEAD worktree 上同红**（`entry-identity` 路由未登记进 `_REQUIRED_ENDPOINTS` / 守卫先后的分母仍是 22）⇒ 预存失败，非本任务引入 |
| 变异 | **6 RED + 1 GREEN（阴性对照）**，逐条核对红在预期用例（见 R9.5） |
| 行数门（9 个改动文件） | **exit 0**（`wp_sync_router.py` 3640 = 阈值上限，无余量） |

#### R9.5 变异表

| # | 变异 | 结果 | 红在哪 |
| --- | --- | --- | --- |
| a1 | 作废写 `superseded_at`（复用观测同步那列） | **RED** | 真库 `test_the_abandon_columns_are_not_the_superseded_column`（预标行被改写）+ 离线 AST `test_abandon_never_touches_superseded_at` |
| b1 | 裸 SQL `UPDATE … SET state` 绕开 `append_operation_event` | **RED** | 真库 `test_the_timeline_has_exactly_one_transition_event`（timeline 零事件）+ 离线两条 AST |
| c1 | 作废时物理删除冲突行 | **RED** | 真库 `test_no_conflict_row_was_deleted` + `test_every_conflict_row_carries_all_three_columns` + 离线 AST |
| d1 | 操作者取请求体而非 `scope.user_id` | **RED** | 端点级 `test_the_actor_is_the_server_side_user_not_the_request_body` + 离线 AST `test_actor_comes_from_guarded_scope_not_from_payload` |
| n1 | **阴性对照**：只加一行注释 | **GREEN** | —（证明判据不是「对任何改动都红」） |
| e1 | V273 的约束存在性判定改回只看 `conname` | **RED** | 真库 `TestTheDatabaseGuardsAreReal` 两条（三列约束失效 ⇒ 残缺写入成功） |
| f1 | 幂等分支被短路（`if False and …`） | **RED** | 真库 `test_the_replay_does_not_append_a_second_event`（追加第二条 event）+ `test_the_replay_reports_itself_as_idempotent` |

变异器：`tmp_task8/mutate_abandon.py`（一次性，用完即删）。含 `--check-targets` 靶点命中
核对 + 逐字节恢复 + sha256 复核。

🔴 **变异器的两个新教训**（已写进脚本注释）：
* **行尾归一**：仓库 `core.autocrlf=true`，磁盘上 `wp_sync_router.py` 是 **CRLF** 而其余新文件是
  LF。脚本里的靶点写成 LF 时 `count()` 恒 0 ⇒ 变异被静默 SKIP（首轮 d1 就是这样漏跑的）。
  ⇒ 读入统一成 LF 匹配，写出前还原原行尾。
* **红的形态要核对是「哪一层」红的**：a1/b1/c1 首轮只跑离线时「RED」但 `want` 里的真库节点是
  MISS。把这三条改成 `pg=True` 后，红的形态才真的落在「内容没落地」这条判据上 ——
  否则证明的是「AST 看见了赋值」，而不是「三列没写上」。

#### R9.6 真库/环境限制（如实）

* **未做任何真实项目的数据写入**。本任务只有两处触及共享库：①V273 迁移（加列 + 加约束，
  幂等、无回填）；②`test_task10_orm_repository_contract.py` 的既有失败与 V273 无关
  （`export_surface_class` 等旧欠账，HEAD 同红）。真库写入型验收（【测试】项目作废
  `11809f53…`）**留到任务 11**，本任务**未碰**那 17 条 `state='conflict'` operation
  （真实项目 14 条 + 【测试】3 条全未动）。
* **PG 守卫全部在临时 schema**（`tmp_ca_<hex>`），结束 `DROP SCHEMA CASCADE`；真跑 V151 +
  V264 + V273 而不是手抄 DDL。
* **前端未改**（作废没有前端入口 —— 任务 8 只要求后端能力；前端按钮属后续需求，
  本 spec 未登记，如需请在任务 9~12 或新 spec 提）。

#### R9.7 范围外发现（登记，未改）

1. **`_guard` 不判项目成员级别**（见 R9.3 第 2 条）：`resolve_conflicts` / `retry_apply` /
   `rollback` / `forcesave` 等既有写端点只靠 action 词表 + `workflow_locked`，只读成员
   （`PermissionLevel.readonly`）能通过。建议另立 spec 统一挂 `require_project_access`。
2. **`test_task28_sync_router.py` 的两张清单已过期**：`_REQUIRED_ENDPOINTS` 缺
   `GET …/entry-identity`（HEAD 已加该路由但未登记），`test_every_user_handler_awaits_the_guard_first`
   的 `+7` 偏移也没跟上。本任务只补了自己的 `abandon` 一行，未代修既有欠账（那属该文件的
   作者或独立 task）。
3. **`test_task10_orm_repository_contract.py::test_orm_columns_match_ddl_bidirectionally`
   在 HEAD 上就红**（`working_paper_content_version` 的 4 列 + `working_paper_sync_conflict.schema_anomaly`
   都不在 V151 解析范围）。本任务加的三列同样不在 V151（在 V273），所以该判据对
   `abandoned_*` 也不覆盖 —— **三层一致目前由本任务自己的
   `TestMigrationOrmAndServiceAgree` 保证**，未被既有守卫覆盖。
4. **`test_repository_never_commits` 在 HEAD 上就红**（`lock_room_oo_apply` /
   `unlock_room_oo_apply` 的 `conn.commit()`，那是 advisory lock 的会话级提交，属该守卫的
   已知盲区）。

#### R9.8 需要用户拍板的残留

1. **是否处理真实项目那 14 条 `state='conflict'` operation**（和平药房 4 + 重药安徽 11 中
   的 14 条）—— 本 spec 只交付能力，未动任何真实项目数据。作废它们是**业务决定**
   （每条的冲突是否真的不再需要处理，须业务方判断），不是技术决定。
2. **前端是否需要作废入口**：当前 `POST …/abandon` 只有后端。若需要按钮，需另加前端
   （含中文文案、二次确认、原因必填输入）。
3. **`authorization_stale` 作为第二个终态后继**：本任务选 `superseded` 并写明理由。
   若用户认为作废更应表达为 `rejected`（语义「被否决」），需先确认 `ck_wpso_state`
   与 `OPERATION_EDGES` 是否要加 `conflict → rejected` 这条边 —— 那是状态机的平台级改动，
   不在本 spec 范围。

### R10. 任务 9 实施记录（2026-11-16；结算后复核 R3.4，已交付代码 + 测试 + 变异）

#### R10.1 交付物

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `backend/scripts/check/check_sync_operation_settlement.py` | 690 | **新**：只读探针的 IO + CLI 层（`SET TRANSACTION READ ONLY` + 方言检测 + 四段事实 + `--json` / `--output` / `--compare`） |
| `backend/scripts/check/sync_settlement_review.py` | 562 | **新**：八条形态判据 V1~V8 + 全部常量（纯函数，无 IO） |
| `backend/scripts/check/sync_settlement_facts.py` | 284 | **新**：值对象（四段事实）+ `summarize_conflicts`（② 段唯一口径） |
| `backend/tests/workpaper_sync/test_sync_operation_settlement_probe.py` | 676 | 只读 AST 守卫 / 报告结构 / 可重跑 / 对拍 / CLI 契约 / 行数门 |
| `backend/tests/workpaper_sync/test_sync_operation_settlement_verdicts.py` | 415 | V1~V8 **逐条**否定侧（拆分自上一个文件：合起来 982 行 > 800） |
| `backend/tests/workpaper_sync/test_sync_operation_settlement_pg.py` | 796 | 真库：三列/两列约束真拒、READ ONLY 真挡写、三跳 JOIN 真读回 |

三个脚本模块拆分的**理由不是风格**：判据要能离线逐条驱动（证明它真会红）、
「只读」要能静态断言（AST）、`check_file_size.py` 阈值 800 行。
把值对象再单独拆一个模块，是因为真库守卫要直接构造它们而不该 import 带 SQL 的模块。

#### R10.2 八条形态判据（V1~V8）与「状态变了但内容没落地」的口径

任务原文只给了一个例子（「终态为 applied 时必须有新 representation 且 revision 前进」）。
现算发现**必须按方向分型**，否则会把正确实现判成缺陷：

| 方向 | 落地证据 | 2026-11-16 现算 |
| --- | --- | --- |
| `oo_to_html` | content application → 新 representation + 新 content version | 106/106 三条判据成立 |
| `html_to_oo` | **只有** room（该方向从不产生 content application，Property 64） | **784/784** `application_id IS NULL` |

⇒ 不分型 = 784 条假红。八条判据：

| id | 断言 |
| --- | --- |
| V1 | 终态必须有落进该终态的 append-only event（`current state` 只是 timeline 投影） |
| V2 | `sequence_no` 必须从 1 起连续（断号/重号即红） |
| V3 | 作废三列同生共死（`ck_wpsc_abandon_triplet` 的读侧复核；三列全空是合法态） |
| V4 | `resolved_at`/`resolved_by` 成对**且** `resolved_value` 非空（AC 8.6 三要素） |
| V5 | 已落地终态：`oo_to_html` 必须有 application；`html_to_oo` 必须有 room |
| V6 | 已落地：有新 representation（≠ base）**且** result content revision > **base_version** revision |
| V7 | 作废终态：全部冲突行三列齐备 **且** 未产生 result representation |
| V8 | 已落地：冲突行全部已收口（resolved/abandoned/superseded 任一非空） |

#### R10.3 🔴 实施中抓到并修正的两个口径错误（如实登记）

1. **`application.current_revision` 不是「冻结基线的 revision」**。它看着像，实际是
   `working_paper.content_revision`（**另一个计数器**）在 correlation 时的快照
   （`repository.correlate_durable_incoming` 的入参就是
   `SELECT content_revision FROM working_paper`）。首版 V6 拿它当基线 ⇒ **4 条假红**
   （`0d79eaf5` 等：`result_revision` 5/7/9/11 都小于 `current_revision` 11，
   而它们的 `base_version.revision` 是 4/6/8/10，逐条严格前进）。
   **正解**：基线取 `base_version_id → working_paper_content_version.revision`。
   现算 106/106 逐条前进。
2. **`--all` 的 `_REVIEWABLE_STATES` 首版漏了 `duplicate`**（终态但
   `application_id IS NULL`，折叠到别人身上的 shell）。守卫
   `test_the_reviewable_states_cover_every_terminal_state` 逐值比对
   `TERMINAL_STATES["operation"]` 抓到 ⇒ 补齐为 8 个。

#### R10.4 已知历史缺口（棘轮，登记不修）

`sync_settlement_review.KNOWN_LEGACY_GAPS` 两条，**都早于本 spec 且与作废路径无关**：

| 缺口 id | 现算 | 说明 |
| --- | --- | --- |
| `legacy_oo_applied_unsettled_conflicts` | 1 条 operation / 108 条冲突中 54 条三列全空 | 走「带 resolutions 的 apply」路径；`record_conflicts` 只覆盖三值元数据、**不清** `resolved_*`，旧一轮观测靠 `superseded_at` 收口 |
| `legacy_oo_applied_without_entry_state` | 52 条 application（3 个 wp） | `entry_state` 是后加的 current pointer，历史 wp 从未回填；内容**确实落地了**（`result_representation_id` + revision 齐备） |

🔴 **判据不因「已登记」而降级为绿**：V8 照实判红并带 `known_gap` 标记；
探针退出码仍非 0。这是本仓棘轮纪律的形态（新增即红 / 自愈须删行）。

#### R10.5 探针用法与实测输出

```
python backend/scripts/check/check_sync_operation_settlement.py --operation <uuid>
python backend/scripts/check/check_sync_operation_settlement.py --all [--include-orphans]
python backend/scripts/check/check_sync_operation_settlement.py --all --json --output a.json
python backend/scripts/check/check_sync_operation_settlement.py --compare a.json b.json
```

`--all` 实测（共享库，只读）：**1127 条 operation / 1 条不一致**（正是上表那条历史缺口）。

已结算的正例（`886e7961…`，`refresh_required`，9 条 event，revision 1→2，gen 7）八条判据全绿，
四段事实逐项可查 —— 完整输出见本轮汇报。

🔴 **必须用 `--output` 而不是 shell 重定向**：PowerShell 的 `Out-File` / `>` 会按控制台宽度
折行，把 JSON 写坏（首轮 `--compare` 因此报 `Invalid control character`）。

#### R10.6 验证数字

| 项 | 结果 |
| --- | --- |
| 任务 9 新增三文件 | **101 passed / 0 skipped**（探针 44 + 判据 39 + 真库 18，带 `GT_REQUIRE_PG=1`） |
| 任务 8 交付物回归 | **125 passed**（abandon 离线 51 + 端点 12 + 真库 17 + 读侧 45） |
| 行数门（6 个新文件） | **exit 0**（最大 796 行） |
| 可重跑 | 两次 `--all --json` 的 `content_digest` **逐字节相同**（`--compare` 判一致） |

#### R10.7 变异表（5 RED + 1 GREEN 阴性对照）

| # | 变异 | 结果 | 红在哪（逐条核对节点 id） |
| --- | --- | --- | --- |
| m1 | 让 applied 终态允许「零新 representation」 | **RED** | `test_no_result_representation_is_red` / `test_reusing_the_base_representation_is_red` / `test_a_non_advancing_revision_is_red`（3/3 命中） |
| m2 | 让 superseded 终态允许「三列不全」 | **RED** | `test_superseded_with_partial_triplet_is_red` / `..._with_a_new_representation_is_red` / `..._with_untouched_rows_is_red`（3/3） |
| m3 | 探针读法漏掉版本链第三跳（不 JOIN representation） | **RED** | `test_the_representation_row_is_readable` / `test_a_separate_query_agrees_with_the_probe` / `test_the_revision_advances_from_base_to_result`（3/3，**真库**） |
| m4 | 探针带写 SQL（只读事务里 `UPDATE`） | **RED** | `test_every_sql_statement_is_a_select[cli]` |
| m5 | 探针调 `commit()` | **RED** | `test_no_write_call_anywhere[cli]`（与 m4 是**两条独立**判据，互不兜底） |
| n1 | **阴性对照**：只加一行注释 | **GREEN** | —（证明判据不是「对任何改动都红」） |

变异器：`tmp_task9/mutate_task9.py`（一次性，含 `--check-targets` 靶点命中核对 +
逐字节恢复 + sha256 复核）。跑完 `git status` 确认零残留。

🔴 **本轮变异的两个教训**（都已修）：

* **m3 首轮 MISS**：真库守卫当时自己另发一条 SQL 断言 `rep_row`，而那条 SQL 与探针的
  读法无关 ⇒ 把探针的第三跳短路掉，守卫照样绿（「断言的不是被测对象」）。
  **正解**：把第三跳抽成 `_load_representation_facts`，守卫直接调**探针自己的函数**。
* **m4 首轮只命中 1/2 个期望节点**：`UPDATE` 只触发 SQL 首词判据，不触发「写调用」
  判据（`execute` 不在写调用清单里，那是正确的 —— 它是通用入口）。
  **正解**：拆成 m4（写 SQL）+ m5（写调用 `commit()`）两条，各自证明一条判据真的有效。

#### R10.8 范围外发现（登记，未改）

1. **`test_sync_operation_settlement_pg.py` 的首版把 `_load_version_chain` 的第三跳内联**，
   导致该跳在「无 application」的 op 上不可达、守卫只能间接覆盖 —— 已在交付前重构，
   不属范围外，记在此仅作口径留痕。
2. **共享库里 `oo_to_html` 的 `applied` operation 有 81 条 `finished_at IS NULL`**
   （2026-09 那批 76 条 + 2026-10 的 5 条）。现读 `oo_to_html._walk_operation` 的注释
   「终态写完成时刻（与 HTML→OO 的 materialize_coordinator 同口径）。此前本路径从不写它」
   ⇒ 说明该修复是后加的，历史行未回填。**本探针不把它判红**（R3.4 只要求「两个时间戳
   可查」，不要求非空）—— 若要把「终态必须有 `finished_at`」立成判据，会一次红 81 条，
   属**数据回填债**，须单独 spec。
3. **`html_to_oo` 的 `applied` 有 453/784 条既无 `entry_state` 行也无 content version**
   （只有 room）。这是该方向的正常形态（materialize 只开 room、不发布内容），
   已由 V5 的方向分型覆盖，**不是缺陷**。记在此防止后来者误判。

#### R10.9 需要用户拍板的残留

1. **是否把「终态必须有 `finished_at`」立成第九条判据**（见 R10.8 第 2 条）：
   立则一次红 81 条历史行，须先决定「回填」还是「登记缺口棘轮」。
2. **两条已知缺口是否要修**（见 R10.4）：都属数据回填/观测语义，不在本 spec 范围。
3. **`--all` 是否默认包含 `--include-orphans`**：当前默认排除「无 application 且非
   `html_to_oo`」的 operation（实测 0 条），`html_to_oo` 仍包含。若希望默认只看
   「有 application」的，改一行即可，但会让 784 条 `html_to_oo` 不再出现在默认输出里。
