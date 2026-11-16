# 设计：同步冲突可裁决化 + D4-32 资金流水建模修正

## §0 结论先行

两个缺陷各自独立、叠加后使 `xlsx/gt-d4-operating-revenue` 的 OO→HTML 回写完全不可用：
D4-32 **必然**制造 schema 冲突，而 schema 冲突**必然**无法裁决。本 spec 一起修。

修完后的目标态：D4-32 的 A 列不再受管、六段分组载荷双向保真；任何 entry 的
`type_normalization_failure` / `multi_location_divergence` 冲突都能在界面上裁决掉。

## §1 缺陷一（平台级）：schema 冲突一律无法人工裁决

### 1.1 实测（候选 3032，经真实前端 `workpaperSyncApi.getOperationConflicts`）

同一条冲突 item 上两个字段自相矛盾，且成因字段根本不在 payload 里：

```
stable_field_key : d4_32_groups/GTROW-D432-0013/group_label
kind             : schema
suggested_action : manual_merge          ← 建议人工合并
adjudicable_by_value_choice : false      ← 又说不可按值裁决
value_type       : text
base/current/incoming : {value:1, present:true} ×3   ← 三侧同值
（payload 里没有 schema_anomaly 字段）
```

### 1.2 三处合成死路

| # | 位置 | 事实 |
|---|---|---|
| ① | `working_paper_sync_conflict` 表 | **无 `schema_anomaly` 列**（现查列清单 25 列，无此项）⇒ merge 判定的成因落库即丢 |
| ② | `conflict_resolution.py:680` | `return self.kind is not ConflictKind.schema` —— 读侧 DTO 自己算，**所有** schema 冲突一律判不可裁决 |
| ③ | `conflicts.py:165` | 域内 `ConflictRecord.adjudicable_by_value_choice` 按 `schema_anomaly` 分两类，`type_normalization_failure` / `multi_location_divergence` 在 `_VALUE_ADJUDICABLE_ANOMALIES` 里 |

②③ 是同一判据的两份实现，口径分叉；① 让 ② 即便想按成因判也拿不到成因。

后果链：前端 `bulkScopeTargets` 把不可裁决项从所有批量范围排除（含 `all_unresolved`）⇒
单条也不给选边 ⇒ 真调 resolve 会撞 `conflicts.py` 的 `StructuralConflictNotAdjudicableError`。
**与 D4-32 无关，对任何 entry 的任何 schema 冲突都成立。**

### 1.3 ADR-CA-001：成因持久化 + 读侧删掉第二份实现

* **选**：给冲突表加 `schema_anomaly` 列并在落库时写入；读侧 DTO **删掉**自算属性，改为按行上
  成因重建 `SchemaAnomalyKind` 后委派域内判据。
* **拒**：在读侧 DTO 里照抄域内的两类名单 —— 那是把一份分叉换成两份同步维护的清单，下次加
  anomaly 成员时同样会漂。
* **拒**：把 `type_normalization_failure` 从 schema 冲突改成 value 冲突绕开 —— 它确实是结构性
  成因（声明类型与载荷类型不符），改类别会让「要先修契约」这个信息消失。
* 历史行（迁移前落的）成因为 NULL：按 R1.4 fail closed 判不可裁决，但读侧要能把
  「成因未知」与「成因不可裁决」区分开，否则本缺陷修完也看不出修没修。

### 1.4 ADR-CA-002：fence 八项从正式读取面取，不由桥编造

`useWorkpaperSyncBridge.resolveConflicts` 现在显式拒绝替调用方编
`room_latest_durable_application_id` / `room_latest_durable_sequence`，理由写的是
「当前 16 条用户路由里没有任何读取面」。**该注释已过期**：`GET /operations/{id}` 自 Task 32 的
`_fold_observability_facts` 起就返回这两项（现读 `wp_sync_router.py` 确认）。

* **选**：冲突面板在提交前读 `GET /operations/{id}` 取这两项，连同 preview 给的
  `conflict_set_digest` / `room_generation` / `current_revision` / `canonical_application_id`
  / `client_edit_epoch` 组满八项；桥仍然**不编**任何一项（R2.1 / R2.2 的 fail visible 保留）。
* **拒**：放宽后端 `RESOLVE_FENCE_REQUIRED_FIELDS` —— 少比一项 fence 在功能测试里完全看不
  出来，而它守的正是「客户端断言自己看到的就是当前值」。

## §2 缺陷二：D4-32 建模三面皆错

### 2.1 权威模板实测（openpyxl 逐格直读）

```
A11 = '序号'                              ← 契约却声明 header_text='分组'
B11..I11 = 单位名称/姓名 · 本期交易金额 · 占同类交易比例 · 开户银行 · 账号 ·
           资金流水获取途径 · 是否发现异常交易 · 索引号     ← 与其余 8 字段逐字一致
A13..A46：整数 24 格 + '……' 5 格 + 空 5 格（空格就是组标题行）
分组标题在 B 列：B12/B19/B26/B30/B34/B41 = 主要供应商/主要客户/控股股东/
                 实际控制人/关键管理人员/其他关联方
```

24 个整数 = 6 组数据槽 5/5/2/2/5/5，与实测的 24 条冲突**逐一对应**，算术闭合。

### 2.2 三个面

* **面 A（OO→HTML 恒冲突）**：`phase5_d4_ipo_interview_sheets._SHEETS['D4-32'].fields` 把 A 列
  声明为 `("group_label", "A", "editable", "text", "groupLabel", "分组")`。那 24 个整数在
  `value_type=text` 下 `merge.normalize_value` 抛 `ValueNormalizationError` ⇒ 每次保存恒产 24 条
  `type_normalization_failure`，而三侧同值本该判 `kept_current`。
* **面 B（HTML→OO 清空序号）**：六组业务行的 store 无 `groupLabel` 键（前端 `FlowRow` 只有
  id/name/amount/ratio/bank/account/method/hasAnomaly/indexRef）⇒ 投影恒 `None` ⇒ materialize
  把 A 列序号写空。
* **面 C（一有数据就打挂整个 entry）**：真实 store 是 `[{key, rows}]` 六段分组，而 `_rows()` 按
  扁平行数组解析 ⇒ 实测抛 `ValueError: D4-32 缺稳定身份` ⇒ store-projection 422 ⇒ 整个 D4 entry
  进不了在线编辑；回写侧 `merge_projection_into_store` 又返回扁平数组，前端
  `D4TabFundFlow.loadData` 的 `!Array.isArray(group.rows)` 会把六组全判空 ⇒ 镜像一次清空 D4-32。
  **当前未炸只因测试底稿的 D4-32 是空表。**

### 2.3 ADR-D432-001：A 列移出受管字段集（不是改类型）

* **选**：删掉 `group_label` 字段声明，受管面变成 B..I 八列。依据：A11 逐字是「序号」，
  A 列内容是模板自增序号与「……」排版占位，不是业务字段；store 侧也没有对应的业务键。
  与 D4-34 两区「A 序号(模板自增,不入契约)」同一处置，有先例。
* **拒**：改成 `value_type=integer` —— 那会让「模板序号」成为可回写业务字段，面 B 的清空问题
  变成「用户可改序号」，而 store 里本来就没有承载它的键。
* **拒**：对 `text` 放宽数值转换 —— 会让「不得把数字与其字符串形态判等」这条平台口径在所有
  entry 上失效，掩盖的是契约与模板不一致这个真问题。

### 2.4 ADR-D432-002：分组载荷按行身份双向映射，Excel 侧不表达分组

* **选**：`_rows()` 增加 D4-32 分支，按六组声明序（+ 未知组）把各组 `rows` 展平成逐行
  `(id, row)`；`merge_projection_into_store` 增加对称分支，按 `id` 在**原分组内**原地更新字段，
  保留分组结构、未知组 `groupLabel` 与行内未受管字段。
* **已知限制（本 spec 不解决，显式登记）**：Excel 侧六组数据落在同一个连续受管区
  （13..46 单 table），分组归属**不在 Excel 侧表达**。这是既有几何，要彻底解决需把 D4-32 拆成
  6 个 table（各自 first/last/footer/UUID 列），属更大改造。本 spec 的口径是「行身份驱动、
  不丢数据、不靠位置」，分组归属由 HTML store 的结构保持。
* **拒**：本 spec 内顺手做 6-table 重建 —— 它会改 instrumentation 声明数量、
  `_align_specs_to_sibling_tables` 的双射、UUID 列分配，风险与工作量都另一个量级。

### 2.5 ADR-D432-003：骨架行按模板基线分流，未归属行落未映射分组

OO 侧 extract 必然带回模板骨架行（`GTROW-D432-00xx`）。两条简单路都错：

* 一律新建 ⇒ `B19='主要客户'` 这类**组标题**被当业务行写进 store，且骨架行永不收敛、删了还来；
* 一律跳过 ⇒ 用户在 OO 模板空行里填的数据**静默丢失**。

* **选**：复用 `template_skeleton_baseline`（R12 已有）的 `carries_user_content` 判据 ——
  比不了就当用户内容（保守方向）。不带用户内容 ⇒ 跳过；带用户内容 ⇒ 进 store 并落
  `__unknown__` 组，由前端既有 `mapUnknownGroup` 人工认定。
* 这与 D4-32 自己的既定裁决一致（上游 `d4-ipo-fraud-writeback-formula-io` R1.5 / R5.2：
  未知组别不自动归「其他关联方」，落未映射供人工认定），不是本 spec 新发明的语义。

## §3 连带基线（会被 §2 改动打红，必须重新实测）

| 对象 | 现值 | 处置 |
|---|---|---|
| `d4.revenue_detail.json` 契约 | digest `75fca57d…` | 经 `generate_phase5_d4_contract.py --apply` 重生成 |
| `_sync_provider_golden_digest.json` | d4 `contract_payload_sha256` + per-sheet digest | 经其自身工具刷新，禁手改 |
| `test_single_pass_artifact_equivalence.EXTRACTED_FIELD_COUNT` | 218 | 重新实测（A 列移出后减少） |
| 同文件 `TEXT_VICTIM` / `TEXT_VICTIM_CHANGED_FIELDS` | `d4_32_groups` / 24 | 🔴 该 victim 被选中的**理由**正是「模板里那些格存的是数字」，A 列移出后理由消失 ⇒ 必须重选 victim 或改写反证叙述，不能只改数字 |
| `d4_materialize_harness._text_safe` | 为 `d4_32_groups/*/group_label` 的 int 做补偿 | 退役（R5.3）；退役后 D4 物化判据须仍绿 |
| definition 链 + representation | 测试底稿指向 bundle `0efcba0f…` | 经 `fix_task76_provision_projection_definitions.py --apply` 重 provision 后重发布 |

## §4 影响面与数据层风险

现算（共享库只读）：`working_paper_sync_entry_state` 里 entry `xlsx/gt-d4-operating-revenue`
**只有 1 行**，就是测试底稿 `d7fa0522…`；真实业务项目**0** 条已发布 representation。
⇒ 改 D4-32 契约身份在数据层只需重发布这一张，不触及真实项目。

缺陷一是平台级读写路径改动，影响所有 entry 的冲突读侧 ⇒ 回归面取「冲突 / 裁决 / merge」
相关全部既有测试，并与干净 HEAD 基线逐节点比对。

## §5 现场遗留（本 spec 开工前的真实状态）

* operation `11809f53-a34e-44fc-8182-efc5bc68e019`：`state=conflict` / `conflict_count=24`，
  **按决策不裸改**（裸 SQL 结算会破坏版本链与审计链），留作缺陷证据。缺陷一修完后，它应当
  成为第一个「可被正式裁决掉」的真实样本 —— 本 spec 用它做端到端验收。
* 测试底稿 D4-8 的业务值已复原为全 0；D4-32 仍是空表。
* 候选环境：worktree `D:/GT_plan/tmp_stage0/wt`，前端 3032 / 后端 9981（`--lifespan off`
  + `GT_BOOTSTRAP_DONE=1`，避免启动 worker 对共享库额外写入）。

## §6 验收口径

* 缺陷一：Property 1 / 2 —— 含「把读侧改回 `kind is not schema` 即被证伪」的变异。
* 缺陷二：Property 3 —— 六段分组往返逐项不变，骨架行两种形态分流正确。
* 连带：Property 4 —— 契约双向锁死、常数现算一致、补偿退役后仍绿。
* 真库 UAT 只用【测试】项目，写入前存**全文快照**（不只存哈希 —— 上游 6.6 就因只存哈希
  而无法定位复原差异），验收后逐字段复原并对账。
