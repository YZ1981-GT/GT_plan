# Implementation Plan: published-representation-production-path-and-lane-adjudication

## Overview

实现语言 **Python 3.12**（设计文档全程使用 Python，无需再选）。交付顺序遵循 design.md §Rollout：裁决先行 → 只读预演 → 首版落成 → 第二个 entry → capability 裁决 → 回归门更新 → 收口。

**不新增数据库迁移**（磁盘最高 V153，本 spec 不加 V154）。一切写库经服务层或幂等宿主脚本，PG MCP 全程 restricted 只读。

新增/改动文件：

| 记号 | 路径 | 性质 |
|---|---|---|
| F1 | `backend/app/services/workpaper_sync/projection_lane_registry.py` | 新增 |
| F2 | `backend/app/services/workpaper_sync/projection_first_publication.py` | 新增 |
| F3 | `backend/scripts/fix/fix_projection_first_publication.py` | 新增（唯一宿主） |
| F4 | `backend/scripts/check/check_projection_lane_adjudication.py` | 新增（回归门） |
| F5 | `backend/scripts/diagnose/mutate_projection_first_publication_guards.py` | 新增（变异） |
| F6 | `backend/tests/workpaper_sync/test_projection_lane_registry.py` | 新增 |
| F7 | `backend/tests/workpaper_sync/test_projection_first_publication.py` | 新增 |
| F8 | `backend/tests/workpaper_sync/test_projection_first_publication_pg.py` | 新增（真实 PG） |
| F9 | `backend/tests/workpaper_sync/test_projection_lane_regression_gate.py` | 新增 |
| F10 | `backend/app/services/workpaper_sync/opaque_entry_gate.py` | 改（更正过期读数） |
| F11 | `backend/scripts/check/check_task61_oo94_word_pilot_gate.py` | 改（BP-61-1 判据） |
| F12 | `.github/workflows/governance-checks.yml` | 追加 job（只加不动） |

命令一律 Windows PowerShell、仓库根、`;` 分隔、`cwd` 参数代替 `cd`；pytest 从仓库根跑，**不跑全量** `backend/tests`。

## Tasks

- [ ] 1. 建 lane 裁决单一真源
  - [ ] 1.1 建 `LaneVerdict` 枚举、`LaneSupplyFacts` 数据类与 L1~L5 裁决 (F1)
    - 定义封闭三值枚举 `LaneVerdict{projection, opaque, undecided}` 与 frozen dataclass `LaneSupplyFacts`（四个布尔字段 + `entry_id` + `verdict`）
    - 实现 `adjudicate_lane(entry_id, *, manifest=None)`：L1 opaque entry_id 形态 → L2 manifest 归属 → L3 `DELIVERED_PER_ENTRY_CONTRACTS` 登记 → L4 `independent_entry` 且 capability 非 `unreachable` → L5 磁盘契约 `review_status == reviewed`
    - L1 **必须**排第一并在命中时立即 `return opaque`：反过来排会让 opaque entry_id 先撞 L2 的 `undecided`，L1 变成不可达分支
    - 实现 `assert_projection_lane(entry_id)`：`opaque` → `error_code=lane_is_opaque`（附命中的 `lane_id`）；`undecided` → `error_code=lane_undecided`（附首个不成立判据编号 + 该判据的真源文件路径）
    - 各真源一律现读，本模块不抄第二份：opaque 形态取自 `opaque_entry_gate.OPAQUE_AUTHORITY_LANES`、manifest 取自 `manifest_entries_by_id(load_entry_manifest())`、契约登记取自 `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS`、契约解析走 `contracts.load_contract`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 1.2 属性测试：裁决的封闭性、确定性与两条终止分支 (F6)
    - **Property 1: lane 裁决三值封闭且确定**
    - **Validates: Requirements 1.1, 1.2, 1.6**
    - **Property 2: opaque 命名空间的 entry_id 恒判 opaque 且不受后续判据影响**
    - **Validates: Requirements 1.3, 1.4, 1.7**
    - **Property 3: 判据不足恒判 undecided 并点名首个不足判据与其真源**
    - **Validates: Requirements 1.5, 1.7**
    - 生成器覆盖三类 entry_id：由每条 opaque lane 的 `entry_id_source` 形态现造的、manifest 里真实存在的、两者皆不在的任意字符串
    - Property 2 的关键构造：固定一个 opaque 形态 entry_id，**同时**扰动 L2~L5 的输入（抽掉 manifest 项 / 抽掉契约登记 / 把契约 `review_status` 改非 reviewed），结论必须恒为 `opaque`
    - `hypothesis` 每条 ≥100 例

  - [ ] 1.3 建与既有真源的双向锁及无第二真源守卫 (F1)
    - 实现 `assert_registry_covers_opaque_lanes()`：L1 形态表与 `OPAQUE_AUTHORITY_LANES` 逐项（`lane_id` + `entry_id_source`）交叉锁死，不一致时指出具体 `lane_id`
    - 实现 `assert_no_second_lane_decision_site()`：以 `ast` 扫 `backend/app/**` 与 `backend/scripts/**`，把「比较 authority model 取值」与「判 `opaque-` 前缀」两类语法位置报为违规（除非该位置调用本模块），返回按模块归组的合规调用点清册供 evidence 现读
    - AST 扫描**不得**用 `strip_comments` 预处理（会连带剥掉 `sa.text("""…SQL…""")`）；节点定位一律走语法树而非字符窗口
    - import 期即跑 `assert_registry_covers_opaque_lanes()`（坏表不许被加载，与 `assert_lane_self_consistent()` 同款）
    - _Requirements: 1.8, 1.9_

  - [ ]* 1.4 属性测试：双向锁、无第二真源与顺序门不可交换 (F6)
    - **Property 4: L1 形态表与 opaque lane 登记双向锁**
    - **Validates: Requirements 1.8**
    - **Property 5: lane 判定没有第二真源**
    - **Validates: Requirements 1.9**
    - **Property 17: L1 的顺序门不可交换**
    - **Validates: Requirements 1.3**
    - Property 4 的构造：对两侧任一做单条增/删/改（monkeypatch 内存副本），断言 `assert_registry_covers_opaque_lanes` 失败且消息含被改动的 `lane_id`
    - Property 5 的反向自检：临时在扫描根内写一处 `entry_id.startswith("opaque-")`，断言被报违规；删掉后恢复合规（**不得**只断言当前源码合规 —— 那是空分母）
    - Property 17 的判据必须落在「打红的恰是 Property 2 那条测试」而非「有测试打红」

- [ ] 2. 建供给四条独立判据
  - [ ] 2.1 实现 `observe_lane_supply` 与 `describe_supply_gap` (F1)
    - 四条判据各自独立取数，来源两两不同：
      - A `projection_bundle_provisioned` ← `working_paper_sync_definition_bundle` JOIN `working_paper_sync_definition_artifact`，要求 `authority_model_type='projection_contract'` ∧ 两侧 `state='approved'` ∧ 三 slot 均 `is_definition` ∧ `logical_id` 等于该 entry 的 authority model key
      - B `published_representation_current` ← `working_paper_sync_entry_state` 按 **(wp_id, entry_id)** 取（本模块带 scope，不复制供给门那条全局 `.first()`）
      - C `representation_follows_projection_contract` ← representation `definition_bundle_id` 反查 bundle 的 `authority_model_type`
      - D `representation_contract_digest_matches` ← 磁盘契约 `canonical_sha256` 与 bundle contract slot digest 比对（跨来源，非自我比对）
    - `supply_satisfied` = A ∧ B ∧ C ∧ D，**四条全部必需**
    - `describe_supply_gap(facts)`：供给成立返回 `None`；否则返回点名首个为假判据的文本。A 真 B 假时文本**同时**点明「判据 A 已满足」与「判据 B 未满足」
    - 取数异常一律 `raise` 携 `error_code=lane_supply_observation_failed` 并记 ERROR 级 —— **禁止** `except Exception: return False`（fail-open 掩盖接线错误是本仓库最贵的一类缺陷）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8_

  - [ ]* 2.2 属性测试：四条判据的合成语义与取数语义 (F6)
    - **Property 6: 供给成立当且仅当四条判据全为真**
    - **Validates: Requirements 2.1, 2.3, 2.4**
    - **Property 7: 「已 provision bundle」不蕴含「供给成立」**
    - **Validates: Requirements 2.5**
    - **Property 8: 判据 A 与判据 C 的取数语义互不重叠**
    - **Validates: Requirements 2.2, 2.7, 2.8**
    - Property 6 穷举 16 种布尔组合（不用随机 —— 分母有限时穷举比抽样强），断言 15 种为假的组合各自返回非空文本且点名首个为假者
    - Property 8 的判据 C 构造：造一条绑定 opaque bundle 的 current representation，断言 C 为假（这是 D2 那类情形的直接落点）

  - [ ]* 2.3 属性测试：观测异常不降级为假值 (F6)
    - **Property 9: 供给观测的异常不被降级为假值**
    - **Validates: Requirements 2.6**
    - 三种致错情形各一例：表缺失、外键悬挂、session 抛错。断言抛出 `error_code=lane_supply_observation_failed` 且**不**返回四条皆假的 `LaneSupplyFacts`
    - 反向自检：把实现改成 `return False` 后本条必须打红

- [ ] 3. Checkpoint - 裁决层完成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时一行库都不写。用 `--check` 之前的临时探针确认：B60/D2/G7/H1 四个 entry 的 `adjudicate_lane` 全部返回 `projection`，`opaque-<uuid>` 形态返回 `opaque`。

- [ ] 4. 建首版发布服务层
  - [ ] 4.1 建 `FirstPublicationPlan` 与 `resolve_plan` 五条准入 (F2)
    - `FirstPublicationPlan` 为 frozen dataclass，`__post_init__` 调 `assert_no_mutation_surface`（不持 session / repository / outbox，与 `ContentCommitPlan` 同款）
    - `resolve_plan` 按固定顺序求值：① `assert_projection_lane` ② 判据 A 必须为真 ③ 判据 B 必须为 **False**（首版专用）④ bundle 三 typed slot 逐项校验 ⑤ 磁盘契约 `review_status == reviewed`
    - 每条不成立各有独立 `error_code`：`lane_undecided` / `lane_is_opaque` / `projection_bundle_not_provisioned`（诊断指向 `fix_task76_provision_projection_definitions.py`）/ `first_publication_already_done` / `contract_not_reviewed`
    - `authority_model_logical_id` 从 `DELIVERED_PER_ENTRY_CONTRACTS` **现取**，本模块不写死该字面量
    - 第 ④ 条**委派** `resolution.load_bundle_snapshot` + `ExcelEntryDefinitionLoader`，本模块不重写同一判据（重写一份的后果不是更安全，而是任一侧被短路都不改变行为 ⇒ 变异判 GREEN）
    - 任一准入不过时不写任何库行
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 4.2 属性测试：准入顺序、首版专用与拒绝码互不相同 (F7)
    - **Property 10: 首版准入按固定顺序求值并返回无写入面的冻结计划**
    - **Validates: Requirements 3.1, 3.2, 3.9**
    - **Property 11: 首版入口拒绝已有 current representation 的 entry**
    - **Validates: Requirements 3.4**
    - **Property 12: 一切拒绝形态的 error_code 两两不同并指出首个不符项**
    - **Validates: Requirements 3.5, 3.6, 7.1, 7.3, 7.5, 7.6, 7.7**
    - Property 10 的顺序判据：逐一构造「使第 k 条不成立」的输入，断言抛出的 `error_code` 恒为第 k 条那一个（不被后续判据遮蔽）—— 这条才能让顺序不可交换
    - Property 12 收集全部拒绝形态的 `error_code` 做两两不等断言（伪造供给五形态 + 占位 adapter 标识三形态 + 缺 bundle + 契约未 reviewed），并断言诊断指出首个非法 slot
    - 补单元测试：`assert_no_mutation_surface` 对塞了 session 的 plan 必须抛；`authority_model_logical_id` 与 `DELIVERED_PER_ENTRY_CONTRACTS` 现算值相等（改登记表即失败）

  - [ ] 4.3 实现 `stage_instrumented_substrate` (F2)
    - 纯文件侧：权威模板字节 → `instrument_workbook_bytes(spec, gate=…)` → `validate_ooxml_artifact(path, document_type="xlsx", limits=load_limits())` → 现算 `identity_inventory` / `observed_structure` / `observed_business_sheets` / `observed_dynamic_columns`
    - **暂存期零数据库读写**（失败时库一行没动，调用方可直接报错）
    - OOXML 安全门排在产出 staged artifact **之前**：B60 的 `external_relationships` 必须在发布前以 `error_code=ooxml_security_rejected` + `gate` 名显式拒绝，而不是让 `commit` 在事务中途炸出看不出来源的错误
    - 动态列键一律 `dynamic_column_stable_keys(slot, count)`，label 只进 observed 侧、不充当键（label 撞键是本仓库已踩过的坑）
    - 临时目录跑完即删
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.4 属性测试：暂存的实测入参、零 DB 与安全门 (F7)
    - **Property 14: substrate 暂存现算四项实测入参且动态列键不由 label 充当**
    - **Validates: Requirements 4.1, 4.6**
    - **Property 15: substrate 暂存期零数据库读写**
    - **Validates: Requirements 4.2**
    - **Property 16: 被策略拒绝的 OOXML 部件在发布前失败且不留 staged artifact**
    - **Validates: Requirements 4.3, 4.4, 4.5**
    - Property 16 三类部件各一例：注入 `xl/externalLinks/`、注入 `xl/vbaProject.bin`、注入嵌入对象。断言 `error_code=ooxml_security_rejected` + 携带 `gate` 名 + staged 目录为空
    - Property 16 必须包含 **B60 权威模板的真实字节**作为已知负例（实测 `gate=external_relationships`）
    - Property 14 的 label 判据：扰动任一表头 label，断言全部动态列键逐项不变
    - Property 15 用不可用 session 构造（`stage_*` 签名里根本不该有 session ⇒ 判据落在签名 + 行为双侧）

  - [ ] 4.5 实现 `publish_first_generation`（loader → adapter → commit）(F2)
    - 链路：`ExcelEntryDefinitionLoader.load(entry_id, frozen_bundle_id, frozen_bundle_sha256, adapter_build, identity_inventory, observed_*)` → `build_excel_adapter(definitions=…, binding=…, direction="html_to_oo")` → `ContentMutationService.commit(plan=…, mutation=…, adapter=<该 adapter>)`
    - 本方法**不**降级任何判据：`commit` 的 `_assert_authority_shape` 仍要求 projection + contract + adapter 三者齐备；bundle 仍必须 approved；typed slot 仍不得是 marker
    - 本方法不 commit、不选目标底稿、不发布 definition（事务边界与目标选取属宿主脚本，与 `word_entry_gate` / `OpaqueAuthorityProvisioner.resolve` 的既有约定一致）
    - 结构守卫（在 4.6 落判据）：函数体内 `registry.register` / `PENDING_ENGINE_ADAPTERS` / `adapters/word` 零引用；不出现 `adapter=None`；不改写 `PublishedIdentityObserver`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 7.2, 7.9, 7.10_

  - [ ]* 4.6 属性测试：破环点与空 adapter 必被拒 (F7)
    - **Property 18: Frozen_Definitions 的生产入参零 representation 依赖**
    - **Validates: Requirements 5.1**
    - **Property 21: 以空 adapter 提交 projection 必被拒**
    - **Validates: Requirements 5.8, 7.4**
    - Property 18 是本 spec 的**核心判据**：在库中不存在该 (wp, entry) 任何 representation 时，产出 `FrozenEntryDefinitions` 的调用仍成功；并以 AST 断言该调用的入参集合不含任何 representation 标识
    - Property 21 双侧：`commit(adapter=None)` 必抛 `ContractRequiredError`；`PublishedIdentityObserver.observe(representation=None)` 必抛 `RepresentationShapeError`（不返回 `None`、不返回空 identity）
    - 补结构守卫：`publish_first_generation` 的 `direction` 实参恒为 `"html_to_oo"`；函数体内 Word 相关路径零引用

- [ ] 5. Checkpoint - 服务层完成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时仍未在真实库写入任何行。

- [ ] 6. 建唯一幂等宿主
  - [ ] 6.1 建 `--check` 只读预演与封闭结算词表 (F3)
    - `--check` 逐 entry 跑完：`adjudicate_lane` → `observe_lane_supply` 四条判据 → 临时目录 instrument → OOXML 安全门 → loader 全部校验步骤 → `build_excel_adapter`。**一行库都不写**
    - 结算词表为封闭集 `CHECK_ENTRY_STATES = ("ready_to_publish", "blocked_missing_approved_bundle", "blocked_ooxml_gate", "blocked_contract_not_reviewed", "blocked_lane_undecided", "already_published")` —— 自由文本会让守卫只能比字符串
    - 目标清单从 `DELIVERED_PER_ENTRY_CONTRACTS` × 真实 `working_paper` **现算**，不写第二份 entry 清单
    - `TARGET_ORDER_SQL = "wi.wp_code, wp.created_at, wp.id"` 全序为每个 entry 选唯一目标底稿（与 `fix_task77_finalize_word_entry_representation.py` 同款；这解决设计文档 C8 的取值确定性）
    - 已知负例必须落对格：`xlsx/b60/gt-b60-bundle` → `blocked_ooxml_gate`（诊断写明解除条件属安全策略裁决）；`xlsx/gt-g7-long-term-equity-main` → `blocked_missing_approved_bundle`（诊断指向 Task 76 宿主）
    - 提供 `--json` 把结算快照落盘（脚本内 `Path.write_text(encoding="utf-8")`，**不**用 PowerShell 重定向 —— 会把中文腌成乱码）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9, 6.10_

  - [ ]* 6.2 属性测试：只读性、封闭词表与目标选取确定性 (F7)
    - **Property 22: `--check` 只读且跑完全链**
    - **Validates: Requirements 6.2**
    - **Property 23: 逐 entry 结算落在封闭词表内**
    - **Validates: Requirements 6.3**
    - **Property 24: 目标选取在固定库状态下确定**
    - **Validates: Requirements 6.5**
    - Property 22 判据落在「执行前后逐表快照逐行相等」+「六个链路阶段各留下一条真实执行痕迹」双侧 —— 只断言只读会让「什么都没跑」也通过
    - Property 24 的构造：以不同插入顺序造出等价的目标行集合，断言选出的 (project_id, wp_id) 相同
    - 补结构守卫：`--check` 的 AST 里对写入面（`session.add` / `INSERT` / `UPDATE` / `repository.register_*`）零引用

  - [ ] 6.3 建 `--apply` 逐 entry 独立事务 (F3)
    - `--apply` 只对 `--check` 结算为 `ready_to_publish` 的 entry 发布首版；逐 (wp_id, entry_id) **独立事务**
    - 单 entry 失败只回滚它自己、继续后续 entry，最终以非零退出码报 ERROR —— **不**降级成「本项目无此数据」
    - 幂等：对已发布首版的 entry 结算为 `already_published`，不产生第二份供给
    - 事务边界**不得**共用一个 `engine.begin()`（一处失败全部回滚是本仓库已踩过的坑）
    - 破坏性运行前设 `$env:PYTHONIOENCODING='utf-8'`；判成败一律查数据不看退出码（被 `^C` 中断的运行可能已提交部分变更）
    - _Requirements: 6.6, 6.7, 6.8, 6.11_

  - [ ]* 6.4 属性测试：事务隔离与幂等 (F7)
    - **Property 25: 每 entry 独立事务，单点失败只回滚自身并以非零退出码报错**
    - **Validates: Requirements 6.6, 6.7, 6.11**
    - **Property 26: 重跑 `--apply` 幂等，不产生第二份供给**
    - **Validates: Requirements 6.8**
    - Property 25 的构造：对 N 个目标注入第 k 个失败，断言前 k-1 个的落库结果不变、后 N-k 个仍被处理、退出码非零
    - Property 26 判据落在「行数与 digest 逐项不变」而非「没报错」

- [ ] 7. 真实 PG 上的首版落成验证
  - [ ] 7.1 建真实 PG 临时 schema 夹具 (F8)
    - 真实 PostgreSQL 上 `CREATE SCHEMA` → 跑迁移 → 发布 → 断言 → `DROP SCHEMA`；DB 非 PostgreSQL 时**不 skip**，直接 fail（判据是「真库上真的成了」）
    - 三坑逐条落实：① timestamptz 一律在 **Python 侧**转 `datetime`（SQL 层 `CAST(:x AS timestamptz)` 无效，asyncpg 发送前就按目标类型编码）② 复原每步用独立事务边界（不共用一个 `engine.begin()`）③ 判成败查数据不看退出码
    - 连库快照用**一次** `asyncio.run` 取全部（每测试各自 async 会污染共享连接池，第二个起 `NoneType has no attribute send`）
    - 目标顺序按 design.md §首版目标选取：先 `xlsx/gt-h1-fixed-assets`（最干净），再 `xlsx/gt-d2-accounts-receivable`（判据 C 的活证人 —— 该 wp 已有 opaque representation）
    - 若 H1 卡在 loader 某一步而 D2 通得过，对调顺序并把实测原因记入 evidence（design.md §Open Gates 第 3 项）
    - _Requirements: 11.1, 11.5, 11.6_

  - [ ]* 7.2 属性测试：落库字段一致、事务形状与失败无残留 (F8)
    - **Property 13: 任一阶段失败时数据库四处逐行不变**
    - **Validates: Requirements 3.8, 5.7**
    - **Property 19: 落库 representation 的七个冻结字段与计划及实测值逐项相等**
    - **Validates: Requirements 5.4**
    - **Property 20: 首版发布恰好一次 revision 推进、一组单行产出与一次 commit**
    - **Validates: Requirements 5.5, 5.6**
    - Property 19 的七字段：`definition_bundle_id` / `definition_bundle_sha256` / `authority_model_definition_id` / `adapter_id` / `adapter_build_digest` / `structure_hash` / `identity_inventory_sha256`。期望值从 plan 与 staged 实测**现取**，不写死字面量
    - Property 20 的 commit 计数取自 `_CommitLatch` 的既有见证，不另装计数器
    - Property 13 在三个阶段各注入一次失败，逐表快照比对

  - [ ]* 7.3 属性测试：判定取自数据、时间戳往返与复原事务边界 (F8)
    - **Property 33: 成败判定取自数据库数据而非进程退出码**
    - **Validates: Requirements 11.2**
    - **Property 34: 带时区时间戳在 Python 侧编码后可往返**
    - **Validates: Requirements 11.3**
    - **Property 35: 复原流程每步独立事务，先前成功步骤不被撤销**
    - **Validates: Requirements 11.4**
    - Property 33 构造两种不一致：「已提交但退出码非零」与「未提交但退出码为零」，断言判定由数据库最终状态唯一决定
    - Property 34 用 `hypothesis` 的 `datetimes(timezones=…)` 生成器，往返后比时间点相等（不比字符串表示）
    - Property 35 在多步复原序列中注入失败，断言先前成功步骤的写入保留

- [ ] 8. Checkpoint - 首版已在真实库落成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时应能用 PG 只读查到：至少一条 representation 绑定的 bundle 的 `authority_model_type='projection_contract'`，且其 `entry_id` 是 manifest entry（非 `opaque-` 命名空间）。

- [ ] 9. 回归判据接线与过期登记更正
  - [ ] 9.1 建 `check_projection_lane_adjudication.py` 回归门 (F4)
    - 复用既有门读数，**不另造**：R1 直接消费 `check_task44_oo94_excel_pilot_gate.py` 的输出（`adapter_registered` / `capability_enabled` / 四态分布），R2 走 PG 只读现查
    - R2 的判据：至少一条 representation 绑定 `projection_contract` bundle；并把「upgrade candidate 表可能有行」表述为首版落成**之后**的结果，**不**作为前置条件
    - 落 candidate 结构依据：断言 `working_paper_representation_upgrade_candidate.source_representation_id` 为 NOT NULL 外键 —— 这是「candidate 路径产不出首版」的结构证据（design.md C1）
    - 落范围边界的结构缺席判据：本 spec 交付物中不含 Task 74 的 writer 迁移改动、不含 `multi_resolver` 改动、不含 `allow_external_relationships` 变更、不含供给门/pilot attach 的 scope 参数、不含新增 `backend/migrations/V*.sql`
    - 落 capability 变更纪律判据：若 manifest capability 出现 `bidirectional`，则 overlay 必须已 reviewed 且 `approved_source_digest` 复核门未被绕过
    - `--json` 落盘新基线并记录与旧基线的差集（`failed` 计数不得因本 spec 交付而增加）
    - _Requirements: 8.1, 8.4, 8.5, 8.8, 9.3, 9.4, 12.1, 12.2, 12.3, 12.4, 12.5, 7.8_

  - [ ]* 9.2 属性测试：供给门放行与注册会计恒等式 (F9)
    - **Property 27: 首版落成且 capability 裁决后供给门放行且注册集合含该 entry**
    - **Validates: Requirements 8.2**
    - **Property 28: 注册会计恒等式在任何供给状态下成立**
    - **Validates: Requirements 8.3**
    - Property 27 是**非空跑证明**（避免「供给为 0 所以注册 0」的重言式）：在临时 schema 上落成首版 + 以内存 manifest 把该 entry 的 capability 置为 `bidirectional`（`build_production_registry(manifest=…)` 本就支持传入 manifest），断言 `_describe_entry_supply` 返回 `None` 且 `register_from_manifest` 的 `registered_adapter_ids` 含该 entry 的 `contract_id`
    - 注册必须由**生产** `attach_pilot_adapters` 完成（其返回值就是证据），不得由测试自己组装后再数 registry
    - Property 28 穷举多种供给状态（0 供给 / 1 供给 / 供给但 capability 未开），断言 `len(registered_entry_ids) + unregistered_entry_count == planned_entry_count`

  - [ ] 9.3 更正 BP-61-1 判据字面量 (F11)
    - 把 `BINDING_CONSTRAINTS` 中 `BP-61-1.what` 的「`working_paper_sync_entry_state` 全表 0 行」改为「不存在任何 **manifest entry** 的 current published representation」—— 实测该表现有 1 行但那 1 行是 `opaque-…` 命名空间，旧字面量已成假话
    - 判据实现改为按 manifest entry_id 集合过滤 entry pointer，而不是数全表行数
    - `owner_task` 与 `unblocks` 字段随之更新：owner 指向本 spec，`unblocks` 保持「Task 61 正文第一句的准入条件」
    - **不动** arm_a / arm_b / arm_c 三臂度量逻辑：绑定约束的先后关系继续由实测得出，而不由写死字面量得出（该门自己已写明「arm_b 原因不再逐字相等时拒绝沿用旧裁决」）
    - 只改本 spec 归属的字节区间；同文件其他 constraint 一律不动（归因型验收，不用全局等值型 —— 并发会话可能同时改同一文件）
    - _Requirements: 8.6, 8.7_

  - [ ]* 9.4 属性测试：绑定约束由三臂实测得出 (F9)
    - **Property 29: BP-61-1 的绑定约束先后由三臂实测得出**
    - **Validates: Requirements 8.7**
    - 构造两种供给状态（无 manifest entry representation / 有），断言 `binding_constraint_facts(arms)` 的 `binding_constraint_id` 随实测改变而改变
    - 反向自检：把三臂之一改成恒定返回后本条必须打红
    - 归因型验收：断言本次改动只落在 `BP-61-1` 的字节区间内，`BP-61-2` / `BP-61-3` 的取值逐字不变

  - [ ] 9.5 更正 `ENTRY_ID_NAMESPACE_SPLIT_NOTE` 过期读数 (F10)
    - `measured_migration_cost_at_task65` 现记三表均 0 行，实测为 `working_paper_content_version=1` / `working_paper_content_representation=1` / `working_paper_content_application=0` —— 更正为实测值并加注更正时点
    - `adjudication_owner_task` 保持 `"67"`，**不**合并 opaque lane 内部的 entry_id 命名空间分叉（那是 Task 67 的范围）
    - 加一条注解说明本登记表裁决的是 opaque lane **内部**的 `wp_code` / `wp_id` / `wp_code_with_sheet` 三种口径，**不涉及** projection vs opaque（后者归本 spec 的 Lane_Registry）
    - _Requirements: 9.1, 9.2_

  - [ ]* 9.6 属性测试：登记读数与真库双向一致 (F9)
    - **Property 30: 登记读数与真实库行数双向一致**
    - **Validates: Requirements 9.1**
    - 判据两侧：登记表读数 == 真库现查行数。任一侧改变而另一侧未更新时打红
    - 反向自检：把登记读数改回 0 后本条必须打红（**不得**把错值当基线锁死 —— 那是假绿第③源）

- [ ] 10. 变异检验
  - [ ] 10.1 建 `mutate_projection_first_publication_guards.py` (F5)
    - 九条变异各带 `id` / `path` / `anchor` / `new` / `want`（预期打红的**具体测试**）/ `why`（它守的假绿形态）：
      1. `adjudicate_lane` 的 L1 分支移到 L2 之后 → 守「opaque entry 恒 undecided」的顺序门
      2. `supply_satisfied` 改成只读判据 A → 守「四条判据合成一条」
      3. `observe_lane_supply` 的 `raise` 改成 `return False` → 守 fail-open 掩盖接线错误
      4. `resolve_plan` 第 ③ 条的期望值取反 → 守「首版入口被拿去覆盖既有 representation」
      5. 删掉 `validate_ooxml_artifact` 调用 → 守 B60 的 `external_relationships` 静默通过
      6. `commit(adapter=<adapter>)` 改成 `adapter=None` → 守绕开 `_assert_authority_shape`
      7. 新写一处 `entry_id.startswith("opaque-")` 判定 → 守第二真源
      8. `--apply` 的每 entry 独立事务改成共用一个 `engine.begin()` → 守「一处失败全部回滚」
      9. 宿主里 `await service.publish_first_generation(...)` 改成只取引用不调用 → 守 additive 死代码（假绿第①源）
    - 四态判读 RED / GREEN / ANCHOR-MISS / WRONG-TEST，**不以退出码代替判读**；WRONG-TEST 需比对失败测试名差集而非只看有无失败
    - 锚点命中次数必须恰为 1（≠1 即 ANCHOR-MISS 并报告实际次数）；锚点不含 `\n`（CRLF 下跨行锚点必 MISS）；CRLF 归一后再匹配；还原后 sha256 自证
    - 提供 `--check-anchors` 只读入口（秒级，用于核对「已归档 spec 是否还可复现」）
    - 加「passed < N 即中止」自检；测试调用走 `subprocess.run([...])` **不经 shell**（`-k "a or b"` 经 shell 会被拆成多个位置参数）
    - _Requirements: 10.1, 10.4, 10.5, 10.6_

  - [ ]* 10.2 属性测试：四态判读与函数体截取 (F9)
    - **Property 31: 变异结果按四态判读，锚点命中数不等于一即 ANCHOR-MISS**
    - **Validates: Requirements 10.2, 10.3**
    - **Property 32: 守卫脚本对任意签名与内嵌 SQL 均正确截取函数体**
    - **Validates: Requirements 10.7, 10.8**
    - Property 31 的构造：喂入命中 0 次 / 1 次 / 2 次的锚点各一例，断言判读分别为 ANCHOR-MISS / 可判 / ANCHOR-MISS
    - Property 32 生成器覆盖：多行签名、带 `-> Mapping[str, Any]` 返回注解、体内含三引号 SQL 文本块。断言截取起止与 `ast` 给出的一致，且 SQL 块不被注释剥离逻辑移除

  - [ ] 10.3 执行全部变异并把非 RED 判读修到 RED (F5 与各守卫)
    - 逐条执行九条变异，记录四态判读结果
    - GREEN → 守卫有缺陷，补强守卫（**不是**代码没问题）
    - ANCHOR-MISS → 脚本缺陷，重指锚点
    - WRONG-TEST → 锚点错行或污染残留，定位并修正
    - 全部收敛为 RED 后把结果落 `--json`，作为收口证据
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [ ] 11. CI 接线与收口
  - [ ] 11.1 把回归门与锚点自检挂进 CI (F12)
    - 在 `.github/workflows/governance-checks.yml` **追加**（`fs_append`，不改既有 job）两个 job：`check_projection_lane_adjudication.py` 与 `mutate_projection_first_publication_guards.py --check-anchors`
    - 验收用**归因型**判据（变动是否落在本 spec 追加的字节区间内），**不用**全局等值型（「其他 job 一个都没变」在并发多会话下必假红）
    - 挂 job 前先 `git status --porcelain` 确认被引用的脚本已入库 —— 干净 checkout 下文件不存在会让 job 必挂
    - _Requirements: 8.1, 8.8_

  - [ ] 11.2 逐产物核对 git 跟踪状态并清理临时产物
    - 对 F1~F12 逐个 `git status --porcelain -- <path>`，见到 `??` 即 `git add`（「spec 全绿 ≠ 产物已入库」是本仓库反复出现的问题；本 spec 目录自身也必须入库，否则丢工作树即全部蒸发）
    - 清理本次会话产生的 `tmp_*` 与 `_wip_*` 诊断产物（`.gitignore` 已收这两类前缀；按 mtime 判归属，并发会话在用的不动）
    - 记录三门新基线（R1/R2/R3）与九条变异判读结果，供后续复盘现读
    - _Requirements: 11.7, 12.6, 12.7_

- [ ] 12. Final checkpoint - 全部判据收敛
  - Ensure all tests pass, ask the user if questions arise.
  - 收口核对：① 至少一个 manifest entry 有 current published representation 且其 bundle 为 `projection_contract` ② `--check` 对 B60/G7 落在对应 blocked 格（负例证明判据在跑）③ 九条变异全 RED ④ 三门新基线已记录且 `failed` 未增 ⑤ F1~F12 全部已入库。

## Notes

- 标 `*` 的子任务为测试任务，可为快速 MVP 跳过；顶层任务不标 `*`。
- 每条属性测试用 `hypothesis`，`max_examples` ≥100，并以 `**Feature: published-representation-production-path-and-lane-adjudication, Property N: <标题>**` 标签回指 design.md。
- **每写完一条守卫必做变异检验**（改一字看是否变红）。没打红 = 守卫有缺陷，不是代码没问题。
- 判据一律落在行为 / 结构 / 真实执行，**不得**落在「字符串是否存在」。
- 判磁盘一律 `python -c "open(p,encoding='utf-8').read()"`（读文件工具对刚改的文件可能返回陈旧版本）。
- 命令用 `;` 分隔、`cwd` 参数代替 `cd`；pytest 从仓库根跑，按对本 spec 交付物的实际引用关系确定辐射面，**不跑全量** `backend/tests`（1522 个文件）。
- design.md §Open Gates 的三项在实施中确认：manifest 能否重生成（BP-67-1）、overlay 是否支持逐 entry capability 覆盖、H1 的 instrumented 字节能否通过 loader 全部步骤。任一不成立即按该节的应对调整，**不绕开**。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1"] },
    { "id": 4, "tasks": ["2.3", "4.3"] },
    { "id": 5, "tasks": ["4.2", "4.5"] },
    { "id": 6, "tasks": ["4.4", "6.1"] },
    { "id": 7, "tasks": ["4.6", "6.3"] },
    { "id": 8, "tasks": ["6.2", "7.1", "9.1", "9.3", "9.5"] },
    { "id": 9, "tasks": ["6.4", "7.2", "9.2"] },
    { "id": 10, "tasks": ["7.3", "9.4"] },
    { "id": 11, "tasks": ["9.6", "10.1"] },
    { "id": 12, "tasks": ["10.2", "11.1"] },
    { "id": 13, "tasks": ["10.3"] },
    { "id": 14, "tasks": ["11.2"] }
  ]
}
```
