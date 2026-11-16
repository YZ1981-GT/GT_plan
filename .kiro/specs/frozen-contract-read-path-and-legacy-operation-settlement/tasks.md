# 任务：冻结契约的读侧重建 + 遗留 operation 结算

> 需求 / 设计见同目录。标记纪律：`[x]` 必须有代码 + 测试通过证据；
> 外部依赖或待环境如实标 `[ ]*`，并写明「代码已改但未实测」。
>
> 本 spec 预期**零迁移**（只补读路径）。若实施中发现需要迁移，先在 tasks 里登记理由。

## A. 基线

- [ ] 1. 冻结开工基线
  - 在最新远端上建锁定分离头候选 worktree；记录 HEAD 与迁移最高号（三路现扫：
    磁盘 / 共享库 `schema_version` / 远端 `git ls-tree`）。
  - 只读复核 §1.2 的四项事实（definition 行 `approved` / blob `published` / 相对路径 /
    磁盘文件字节数），逐项写成可比对的断言（不是抄本文档的数字）。
  - 跑并记录将被本 spec 打红的既有判据的**开工态**：冲突 / 裁决 / merge 族、
    `test_schema_conflict_adjudication_parity.py`、`test_task14_merge_conflicts.py`。
    基线里本来就红的项逐条登记，收尾时按差集归因。

## B. 读路径：按冻结 slot 读回契约（Property 1）

- [ ] 2. 提取公共 definition 读取能力（ADR-FC-002）
  - 把 `PublishedIdentityObserver._read_definition_payload` 与
    `_resolve_definition_blob` 提取成模块级公共函数（保留 `stage` / `context` 错误语义），
    observer 改为委派。
  - 守卫：提取后 observer 的全部既有用例必须仍绿；且断言「字节读取与 digest 复核
    在仓库里只有一处实现」（AST 或函数身份比对，不是文本 grep）。
  - 变异：让 observer 不再委派而是自己留一份拷贝 ⇒ 该守卫必须红。

- [ ] 3. 新增 `FrozenContractReader`（ADR-FC-001）
  - 输入 `bundle_snapshot`（已含三 slot 的 `type/ref/digest`），输出 `SyncContract`：
    `slot_ref` → definition 行 → `blob_artifact_id` → artifact row → 仓储
    `resolve_relative_path()` → 读字节 → `json.loads` → `parse_contract()` →
    断言 `canonical_sha256 == slot_digest`。
  - 错误分型（R1.3）：definition 行不存在 / 非 `approved` / blob 不在盘 / digest 不符
    —— 四类必须各自可辨（不同 `error_code` + 中文原因），不得统一报「契约漂移」。
  - 🔴 只按 bundle 的 `slot_ref` 取，**禁按 `logical_id` + 最新版本**（实测同一
    `logical_id` 已有多代并存：`d4.revenue_detail` 2 行、`d2.inspection` 2 行）。

- [ ] 4. Property 1 守卫
  - 对**每一个**已 approved 的 bundle，读回的 `canonical_sha256` 必须等于其
    `contract_slot_digest`（分母 = 库里的 bundle 全集，不是挑一个）。
  - 变异：把读路径改成「按 contract_id 从磁盘现取」⇒ 必须红，且红的形态是
    「取到了新契约」（核对 `canonical_sha256` 确实变成当前 registry 的 digest，
    不是别的失败）。

## C. 读侧入口改为默认取冻结契约（Property 2）

- [ ] 5. `preview` / `resolve` / `retry` 的 contract 参数改可选（ADR-FC-003）
  - 省略 ⇒ 内部按 bundle 读冻结契约；显式传入 ⇒ 仍跑
    `assert_frozen_contract_matches_bundle`（**判据一个字不改**）。
  - 响应加 `contract_source`（`frozen` / `explicit`）+ `frozen_digest`
    （+ 可现取时的 `current_registry_digest`）。
  - 守卫：显式传入不匹配的 contract 仍必须 422 且 `error_code` 仍是
    `frozen_contract_digest_drift`（不得因新增默认路径而放宽）。

- [ ] 6. 前端如实标注「历史契约」
  - `workpaperSyncDto.ts` 解析 `contract_source` 与两个 digest；冲突面板在
    `contract_source === 'frozen'` 时显示中文标注（说清「这是该 operation 冻结的
    契约版本，与当前模板可能不同」）。
  - 🔴 `contract_source` **只作标注**，不得用它门控任何按钮可用性（守卫断言）。
  - 守卫：DTO 不解析该字段时面板不得静默显示成「当前契约」（变异必须红）。

- [ ] 7. Property 2 真库实测
  - 对遗留 operation `11809f53…`（冻结旧契约 `75fca57d…`）调冲突预览：必须 200，
    且逐项 `business_label` / `value_type` 来自**旧**契约；响应 `contract_source="frozen"`。
  - 反向对照：显式传入新契约 `645e0500…` ⇒ 必须 422 `frozen_contract_digest_drift`。

## D. 遗留 operation 结算（Property 3）

- [ ] 8. 按 §5 待拍板选定的出口实现
  - 若选**正式裁决**：经既有 resolve 端点逐条裁决，落地成新 representation +
    裁决轨迹（`resolved_by` / `resolved_at` / `resolved_value` 三者齐备）。
  - 若选**显式作废**：新增 supersede/abandon 语义 —— 保留冲突行（标
    `superseded_at` + 原因 + 操作者），operation 落终态；**不物理删除冲突行**。
  - 两条路都禁止裸 SQL 改 `state`（会破坏版本链与审计链）。

- [ ] 9. 结算后复核（R3.4）
  - 该 operation 终态 / 冲突行 resolved-or-superseded 状态 / 版本链指针 /
    审计轨迹逐项可查，写成可重跑的只读探针。
  - 守卫：断言「状态变了但内容没落地」这种形态不可能出现（例如终态为 applied 时
    必须有新 representation 且 revision 前进）。

## E. 收尾

- [ ] 10. 回归与变异
  - 后端：冲突 / 裁决 / merge 全族 + 本 spec 新增守卫；与开工基线逐节点差集比对，
    新增失败必须为 0。
  - 前端：sync 目录；区域类型检查相对基线 added 0。
  - 变异逐条 RED 并核对红在预期用例（至少含：读路径回 registry、observer 留第二份拷贝、
    `contract_source` 被用作能力门控、显式传入不匹配时放宽）。

- [ ] 11. 真库验收（只用【测试】项目）
  - 写入前存**全文快照**（不只存哈希），验收后逐字段复原并对账。
  - 遗留 operation 结算后，测试项目的其余数据必须零漂移。

- [ ] 12. 语义审查、INDEX 登记、同步远端后单提交与版本化推送
  - 五角色复盘；只提交本 spec owned 文件；
    `git diff --check` + `check_staged_tree_self_consistency.py`；
    `push_version.py push --branch spec/disclosure-note-doc-upload-and-batch-fill`。
  - 归档后回填 `_archive/174-wp-sync-conflict-adjudication-and-d4-32-modeling/tasks.md`
    的 12.f（**已归档 spec 不回填修改正文**，勘误登记在 INDEX 速递区）。

## §待拍板（实施前必须定）

1. 遗留 operation `11809f53…` 走**正式裁决**还是**显式作废**？（design §5.1）
2. 若旧契约 payload 过不了当前 `parse_contract`，写兼容层还是如实拒绝？（design §5.2）
3. `contract_source` 的展示位置与文案。（design §5.3）
