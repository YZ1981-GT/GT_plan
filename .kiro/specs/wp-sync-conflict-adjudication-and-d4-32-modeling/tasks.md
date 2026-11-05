# 任务：同步冲突可裁决化 + D4-32 资金流水建模修正

> 需求 / 设计见同目录。标记纪律：`[x]` 必须有代码 + 测试通过证据；
> 外部依赖或待环境如实标 `[ ]*`，并写明「代码已改但未实测」。

## A. 基线

- [x] 1. 冻结开工基线
  - 在最新远端上建锁定分离头候选 worktree；记录 HEAD、迁移最高号（三路现扫：磁盘 /
    共享库 `schema_version` / 远端 `git ls-tree`）、`d4.revenue_detail.json` 的 digest。
  - 跑并记录将被本 spec 打红的既有判据的**开工态**：冲突域测试、D4 契约族、单趟等价族、
    `test_dedicated_store_merge_is_non_destructive`。基线里本来就红的项逐条登记，
    收尾时按差集归因，不把预存红算进本轮。

## B. 缺陷一：schema 冲突成因持久化与单一判据

- [x] 2. 迁移 + 写入侧持久化 `schema_anomaly`
  - 新增 `V<取号>__*.sql` / `R<同号>__*.sql` 配对给 `working_paper_sync_conflict` 加可空
    `schema_anomaly` 列（`CREATE/ALTER` 必 `IF NOT EXISTS`）；迁移号按
    `max(磁盘含未跟踪, 共享库已应用) + 1` 取，提交前再核一次。
  - ORM 加 `Mapped[]` 字段；落 conflict 行的写入路径把 `ConflictRecord.schema_anomaly`
    写进去（三层一致：迁移 + ORM + service）。
- [x] 3. 读侧删掉第二份判据（ADR-CA-001）
  - 删 `conflict_resolution.py` 的 `adjudicable_by_value_choice` 自算实现，改为按行上成因
    重建 `SchemaAnomalyKind` 后委派 `conflicts.ConflictRecord` 的同名属性。
  - 成因为 NULL 的历史行 fail closed 判不可裁决，且读侧 payload 要能区分
    「成因未知」与「成因不可裁决」（R1.4）。
  - preview payload 暴露 `schema_anomaly`，使 `suggested_action` 与
    `adjudicable_by_value_choice` 不再可能自相矛盾（R1.5）。
- [x] 4. resolve 入口贯通 + 对拍守卫
  - 可裁决 schema 冲突接受 `keep_current` / `take_incoming` / `manual`；行身份类仍拒绝。
  - 守卫（Property 1）：对 `SchemaAnomalyKind` **每个**成员，断言读侧与域内结论相同；
    分母 = 枚举成员全集（加新成员即打红）。
  - 变异：把读侧改回 `return self.kind is not ConflictKind.schema` ⇒ 对拍必须红，
    且核对红在对拍用例上而不是别处。

## C. 缺陷一：界面可完成裁决

- [x] 5. 冲突面板补齐 fence 八项（ADR-CA-002）
  - 面板提交前读 `GET /operations/{id}` 取 `room_latest_durable_application_id` /
    `room_latest_durable_sequence`，与 preview 的其余六项组满八项；桥仍不编任何一项。
  - 删掉 `useWorkpaperSyncBridge.resolveConflicts` 里「没有任何读取面」的过期注释，
    改为指向真实读取面；保留缺项 fail visible 的中文拒绝。
  - 前端测试：八项齐 ⇒ 调用成功；任一项取不到 ⇒ 可见中文错误且不发请求。

## D. 缺陷二：D4-32 建模

- [x] 6. A 列移出受管字段集（ADR-D432-001）
  - 删 `group_label` 字段声明，受管面 B..I 八列；补注释写明 A 列是模板序号、
    三面缺陷各自的机理与 openpyxl 实测依据。
  - 守卫：逐字段断言 `header_text` 与权威模板同行同列文字逐字相等（分母 = 受管字段数），
    这条同时防止将来再出现「契约说分组、模板写序号」。
- [x] 7. 六段分组载荷双向映射（ADR-D432-002）
  - `_rows()` 按组声明序展平成逐行 `(id, row)`；`merge_projection_into_store` 对称地按 `id`
    在原分组内原地更新，保留分组结构 / 未知组 `groupLabel` / 行内未受管字段。
  - 守卫（Property 3 主体）：含空组、未知组、未受管字段的往返逐项不变；
    并断言「手写基线的键等于 merge 自己产出的键」防夹具漂移。
- [x] 8. 骨架行分流与未映射分组（ADR-D432-003）
  - 接 `template_skeleton_baseline.carries_user_content`：模板原值骨架行跳过；
    带用户内容的未知身份行落 `__unknown__` 组。
  - 守卫：①`B19='主要客户'` 这类组标题行**不得**进 store；②在模板空行填值的骨架行**必须**
    进 store 且落未映射组。两条形态各一个用例（单向用例会把其中一种判反）。

## E. 连带基线与产物

- [x] 9. 契约 / golden digest / definition 链同步（R5.1）
  - `generate_phase5_d4_contract.py --apply` 重生成契约；golden digest 经其自身工具刷新
    （禁手改 JSON）；`fix_task76_provision_projection_definitions.py --check` 后 `--apply`。
- [x] 10. 失效常数重新实测与补偿退役（R5.2 / R5.3）
  - `EXTRACTED_FIELD_COUNT` 重新实测后更新。
  - 🔴 `TEXT_VICTIM` / `TEXT_VICTIM_CHANGED_FIELDS`：该 victim 当初被选中的理由是
    「模板里那些格存的是数字」，A 列移出后**理由消失** ⇒ 重选 victim 或改写反证叙述，
    并保留「反读判据能看见、字节判据也能看见」的两类对照；不得只改数字留下矛盾注释。
  - `d4_materialize_harness._text_safe` 退役；退役后 D4 物化族判据须仍绿。

## F. 回归、变异与真库验收

- [x] 11. 回归与变异
  - 后端：冲突 / 裁决 / merge / D4 契约 / 单趟等价 / dedicated merge 全族；与开工基线
    逐节点差集比对，新增失败必须为 0。
  - 前端：sync 目录 + D4 相关；区域类型检查相对基线 added 0。
  - 变异逐条 RED 并核对红在预期用例（至少含：读侧判据回退、成因不持久化、分组 merge 压平、
    骨架行一律新建 / 一律跳过、A 列回到受管集）。
- [ ]* 12. 真库端到端（只用【测试】项目）　← 真库 UAT 未执行（见 §实施记录 2）
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

## §实施记录（2026-11-04，如实）

### 1. 已完成并有证据（任务 1~11）

| 面 | 改动 | 证据 |
| --- | --- | --- |
| 成因持久化 | V264/R264 + ORM `schema_anomaly` + `ConflictRecord.to_row()` 补键（根因本体） | `test_task14_merge_conflicts.py` 的 `AC81_COLUMNS` 扩入该列，同时是「列必须在 ORM 上存在」的守卫 |
| 读侧委派 | `ConflictPreviewItem` 加 `schema_anomaly` / `schema_anomaly_known`；`adjudicable_by_value_choice` 改为委派域内；`_schema_anomaly_of` 对脏值 fail closed；`_preview_item` 真传 | 新守卫 `test_schema_conflict_adjudication_parity.py` 31 例（分母 = `SchemaAnomalyKind` 全集逐成员对拍 + AST 断言读侧不自维护名单 + 生产路径回传 + `to_row` 键集闭合于 ORM 列） |
| fence 读取面 | 前端 DTO 解析 `room_latest_durable_*`；新增唯一投影点 `roomDurableFenceFromOperation()`；面板 prop 缺省时从 `bridge.operation` 投影；`WP_SYNC_TRACE_GAPS` 删两条过期登记并改为**反向判据** | 前端 `src/components/workpaper/sync` 57 files / 1631 passed；新增 `roomDurableFenceReadPath.spec.ts` 13 例 + 面板 4 例 |
| D4-32 建模 | A 列移出受管集（ADR-D432-001）；`_d4_32_rows` 按六段分组展平；`_merge_d4_32` 对称回写 + 骨架行按 `pure_template_skeleton_rows` 分流 + 未归属行落 `__unknown__`（ADR-D432-002/003） | 契约重生成 digest `75fca57d…` → `645e0500…`，D4-32 受管面 9 → 8 字段（B..I，无 A 列） |
| 连带基线 | `EXTRACTED_FIELD_COUNT` 218 → 189；**重选** `TEXT_VICTIM`（见下）；`_text_safe` 退役（含 5 个调用方文件 11 处） | 后端定向回归 **432 passed / 2 failed**，2 failed 与干净 HEAD 基线逐条一致 ⇒ 新增失败 **0** |

**变异验证**：后端 5 组（读侧一刀切 / `_preview_item` 漏传 / `to_row` 漏列 / 脏值炸 / 阴性对照）、
前端 5 组（DTO 不解析 / 投影编造 / 面板不回退 / 过期登记复活 / 阴性对照）全部红在预期用例，
阴性对照全绿，恢复后 sha256 校验通过。其中两条值得记：
* 后端 M2（`_preview_item` 漏传）只红生产路径两条而 DTO 对拍组保持绿 —— 两层判据各管一段，
  正是「被调函数全绿 ≠ 调用方接上了」的实证；
* 前端 MT5-2（投影编造）连带打红既有的「缺 fence 可见失败」两条 —— 证明编造会破坏 fail-visible 语义。

**`TEXT_VICTIM` 为什么是重选而不是改数字**：它原来是 `d4_32_groups`，选中理由是「34 处全是
`inline_text`，且模板里那些格存的是数字 ⇒ 漏写后反读回 int」—— 而那个「存数字的 text 格」
**就是**被错声明成 text 的 A 列序号。A 列移出后 `d4_32_groups` 漏写的反读差异现算为 **0**
（它变成 silent 型），这条反证失去对象。逐 binding 实测 46 个里只剩 `undisclosed_rp_rows`
满足「漏写后反读会变」（4 处、字节差异恰落 `sheet35.xml`、单趟、extract 总数仍 189），
机理同型（模板存 `1`、`boolean` 归一成 `True`）。

### 2. 未执行：任务 12 真库 UAT

真库 UAT（结算 operation `11809f53-a34e-44fc-8182-efc5bc68e019`、D4-32 六组各填一行走完整
OO↔HTML 往返）**本轮未执行**，连带 definition re-provision 也未做。原因是会话预算用尽，
不是判定它不必要。**未执行就不标完成** —— 当前只能说「代码与离线判据到位」，不能说
「真栈跑通」。执行前置：
1. `backend/scripts/fix/fix_task76_provision_projection_definitions.py --apply --entry "xlsx/gt-d4-operating-revenue" --project-id "e8c40d30-de96-440d-a880-fafcf41f32f3"`
   —— 契约 digest 变了，冻结的 definition 必须重发布，否则在线编辑会报「冻结身份与生产契约脱钩」；
2. 只用【测试】项目（公式同步乙 `e8c40d30…` / wp `d7fa0522…`），写入前存**全文**快照、验收后逐值复原对账。

### 3. 预存失败（非本轮引入，未吸收）

`test_single_pass_artifact_equivalence.py` 两条在干净 HEAD 检出上同样红，本轮不动它们：
* `test_both_artifacts_really_came_from_different_code_paths`：binding 实际 40 vs 常量 39；
* `test_artifact_zip_entries_are_byte_identical_ignoring_timestamps`：zip entry 实际 144 vs 常量 142。

两者方向都与本轮改动相反（删字段不会让 binding 与 entry 增加），且已用「把本会话改过的
6 个后端文件换回 `git show HEAD:` 版」实测取证。归属应是阶段 0 或并发会话的 definition
provision 产物，留给迁移/发布负责人处置。

### 4. 本轮事故与已落地的防护

换版跑基线的脚本（`tmp_stage0/baseline_backend.py`）被共享终端的 Ctrl+C 打断过两次，
`finally` 来不及恢复 ⇒ 文件停在 HEAD 版；随后同一脚本再运行，把 HEAD 版当成「当前版本」
备份并"恢复"回去 ⇒ **Task 2/3/6/7/8 的六个文件改动被静默擦除**，而 `git status` 仍显示 `M`
（只是行尾 churn）几乎掩盖了这件事，直到新守卫 26 条全红才暴露。已在脚本里加硬门：
备份前逐字节比对 HEAD，**凡当前内容等于 HEAD 就拒绝运行**并点名文件。
