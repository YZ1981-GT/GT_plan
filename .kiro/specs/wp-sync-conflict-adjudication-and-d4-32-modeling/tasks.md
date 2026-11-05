# 任务：同步冲突可裁决化 + D4-32 资金流水建模修正

> 需求 / 设计见同目录。标记纪律：`[x]` 必须有代码 + 测试通过证据；
> 外部依赖或待环境如实标 `[ ]*`，并写明「代码已改但未实测」。

## A. 基线

- [ ] 1. 冻结开工基线
  - 在最新远端上建锁定分离头候选 worktree；记录 HEAD、迁移最高号（三路现扫：磁盘 /
    共享库 `schema_version` / 远端 `git ls-tree`）、`d4.revenue_detail.json` 的 digest。
  - 跑并记录将被本 spec 打红的既有判据的**开工态**：冲突域测试、D4 契约族、单趟等价族、
    `test_dedicated_store_merge_is_non_destructive`。基线里本来就红的项逐条登记，
    收尾时按差集归因，不把预存红算进本轮。

## B. 缺陷一：schema 冲突成因持久化与单一判据

- [ ] 2. 迁移 + 写入侧持久化 `schema_anomaly`
  - 新增 `V<取号>__*.sql` / `R<同号>__*.sql` 配对给 `working_paper_sync_conflict` 加可空
    `schema_anomaly` 列（`CREATE/ALTER` 必 `IF NOT EXISTS`）；迁移号按
    `max(磁盘含未跟踪, 共享库已应用) + 1` 取，提交前再核一次。
  - ORM 加 `Mapped[]` 字段；落 conflict 行的写入路径把 `ConflictRecord.schema_anomaly`
    写进去（三层一致：迁移 + ORM + service）。
- [ ] 3. 读侧删掉第二份判据（ADR-CA-001）
  - 删 `conflict_resolution.py` 的 `adjudicable_by_value_choice` 自算实现，改为按行上成因
    重建 `SchemaAnomalyKind` 后委派 `conflicts.ConflictRecord` 的同名属性。
  - 成因为 NULL 的历史行 fail closed 判不可裁决，且读侧 payload 要能区分
    「成因未知」与「成因不可裁决」（R1.4）。
  - preview payload 暴露 `schema_anomaly`，使 `suggested_action` 与
    `adjudicable_by_value_choice` 不再可能自相矛盾（R1.5）。
- [ ] 4. resolve 入口贯通 + 对拍守卫
  - 可裁决 schema 冲突接受 `keep_current` / `take_incoming` / `manual`；行身份类仍拒绝。
  - 守卫（Property 1）：对 `SchemaAnomalyKind` **每个**成员，断言读侧与域内结论相同；
    分母 = 枚举成员全集（加新成员即打红）。
  - 变异：把读侧改回 `return self.kind is not ConflictKind.schema` ⇒ 对拍必须红，
    且核对红在对拍用例上而不是别处。

## C. 缺陷一：界面可完成裁决

- [ ] 5. 冲突面板补齐 fence 八项（ADR-CA-002）
  - 面板提交前读 `GET /operations/{id}` 取 `room_latest_durable_application_id` /
    `room_latest_durable_sequence`，与 preview 的其余六项组满八项；桥仍不编任何一项。
  - 删掉 `useWorkpaperSyncBridge.resolveConflicts` 里「没有任何读取面」的过期注释，
    改为指向真实读取面；保留缺项 fail visible 的中文拒绝。
  - 前端测试：八项齐 ⇒ 调用成功；任一项取不到 ⇒ 可见中文错误且不发请求。

## D. 缺陷二：D4-32 建模

- [ ] 6. A 列移出受管字段集（ADR-D432-001）
  - 删 `group_label` 字段声明，受管面 B..I 八列；补注释写明 A 列是模板序号、
    三面缺陷各自的机理与 openpyxl 实测依据。
  - 守卫：逐字段断言 `header_text` 与权威模板同行同列文字逐字相等（分母 = 受管字段数），
    这条同时防止将来再出现「契约说分组、模板写序号」。
- [ ] 7. 六段分组载荷双向映射（ADR-D432-002）
  - `_rows()` 按组声明序展平成逐行 `(id, row)`；`merge_projection_into_store` 对称地按 `id`
    在原分组内原地更新，保留分组结构 / 未知组 `groupLabel` / 行内未受管字段。
  - 守卫（Property 3 主体）：含空组、未知组、未受管字段的往返逐项不变；
    并断言「手写基线的键等于 merge 自己产出的键」防夹具漂移。
- [ ] 8. 骨架行分流与未映射分组（ADR-D432-003）
  - 接 `template_skeleton_baseline.carries_user_content`：模板原值骨架行跳过；
    带用户内容的未知身份行落 `__unknown__` 组。
  - 守卫：①`B19='主要客户'` 这类组标题行**不得**进 store；②在模板空行填值的骨架行**必须**
    进 store 且落未映射组。两条形态各一个用例（单向用例会把其中一种判反）。

## E. 连带基线与产物

- [ ] 9. 契约 / golden digest / definition 链同步（R5.1）
  - `generate_phase5_d4_contract.py --apply` 重生成契约；golden digest 经其自身工具刷新
    （禁手改 JSON）；`fix_task76_provision_projection_definitions.py --check` 后 `--apply`。
- [ ] 10. 失效常数重新实测与补偿退役（R5.2 / R5.3）
  - `EXTRACTED_FIELD_COUNT` 重新实测后更新。
  - 🔴 `TEXT_VICTIM` / `TEXT_VICTIM_CHANGED_FIELDS`：该 victim 当初被选中的理由是
    「模板里那些格存的是数字」，A 列移出后**理由消失** ⇒ 重选 victim 或改写反证叙述，
    并保留「反读判据能看见、字节判据也能看见」的两类对照；不得只改数字留下矛盾注释。
  - `d4_materialize_harness._text_safe` 退役；退役后 D4 物化族判据须仍绿。

## F. 回归、变异与真库验收

- [ ] 11. 回归与变异
  - 后端：冲突 / 裁决 / merge / D4 契约 / 单趟等价 / dedicated merge 全族；与开工基线
    逐节点差集比对，新增失败必须为 0。
  - 前端：sync 目录 + D4 相关；区域类型检查相对基线 added 0。
  - 变异逐条 RED 并核对红在预期用例（至少含：读侧判据回退、成因不持久化、分组 merge 压平、
    骨架行一律新建 / 一律跳过、A 列回到受管集）。
- [ ] 12. 真库端到端（只用【测试】项目）
  - 重发布测试底稿 representation 后，先把遗留 operation
    `11809f53-a34e-44fc-8182-efc5bc68e019` 经**正式裁决端点**结算掉（它是缺陷一的真实样本）。
  - D4-32 六组各填一行 → 切在线编辑 → OO 内改值 → forcesave → 回表单刷新 →
    HTML / API / 已发布 representation 三方一致；分组归属与模板序号列逐项核对。
  - 🔴 写入前存**全文快照**（不只存哈希 —— 上游 6.6 就因只存哈希而无法定位复原差异），
    验收后逐字段复原并对账。
- [ ] 13. 上游 spec 回填
  - 把 `workpaper-writeback-data-loss-and-mirror-consistency-closure` 的 6.3 / 6.4 / 6.5
    由阻断改为实测结论，并在 6.6 / 6.7 标注本 spec 的交付结果。

## G. 收尾

- [ ] 14. 语义审查、INDEX 登记、同步远端后单提交与版本化推送
  - 五角色复盘；只提交本 spec owned 文件（生成文件如 `components.d.ts` 不并集）；
    `git diff --check` + `check_staged_tree_self_consistency.py`；
    `push_version.py push --branch spec/disclosure-note-doc-upload-and-batch-fill`。
