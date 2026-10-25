# Requirements Document

## Introduction

本需求由 `design.md` 推导。目标是解除一个没有 owner 的平台级瓶颈：平台从未在生产调用路径上为任何 manifest entry 产出过 published representation，而上游 spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 7 个任务（61 / 63 / 71 / 72 / 74 / 75 / 76）全部收敛到这一点。

本需求覆盖两件交付物与其连带回归判据：

1. projection lane 首版 published representation 的**生产调用点**（服务层 + 唯一幂等宿主），破环点是 `ExcelEntryDefinitionLoader` 这条不依赖 representation 的 `FrozenEntryDefinitions` 生产路径；
2. **projection lane vs opaque lane 的选路裁决**，把「已 provision projection bundle」与「representation 真按 projection contract 发布」拆成互相独立、可分别 falsify 的判据。

明确不覆盖：Task 74 的 writer 迁移、Task 71 的 `multi_resolver` 归零、任何 Word adapter、放宽 OOXML 安全策略、给供给门加 project/wp scope、合并 opaque lane 内部 entry_id 命名空间分叉、新增数据库迁移。

## Glossary

- **Lane_Registry**：`backend/app/services/workpaper_sync/projection_lane_registry.py`。lane 裁决的单一真源，提供 `adjudicate_lane` / `assert_projection_lane` / `observe_lane_supply` / `describe_supply_gap` 及与既有真源的双向锁断言。
- **Supply_Observer**：Lane_Registry 中负责观测 `LaneSupplyFacts` 四条判据的部分（`observe_lane_supply`）。
- **First_Publication_Service**：`backend/app/services/workpaper_sync/projection_first_publication.py` 的 `ProjectionFirstPublicationService`。projection lane 首版 published representation 的唯一生产出口。
- **Substrate_Stager**：First_Publication_Service 的 `stage_instrumented_substrate` 方法。纯文件侧，把权威模板 instrument 成 staged substrate 并现算运行时实测入参。
- **Publication_Host**：`backend/scripts/fix/fix_projection_first_publication.py`。First_Publication_Service 的唯一消费宿主，提供 `--check` / `--apply` / `--json`。
- **Lane_Guard**：`backend/scripts/check/check_projection_lane_adjudication.py`。lane 裁决与首版落成的回归门。
- **Mutation_Runner**：`backend/scripts/diagnose/mutate_projection_first_publication_guards.py`。变异检验脚本，支持 `--check-anchors`。
- **LaneVerdict**：封闭三值枚举 `{projection, opaque, undecided}`。
- **LaneSupplyFacts**：承载四条独立供给判据的冻结数据类，字段为 `projection_bundle_provisioned`（判据 A）、`published_representation_current`（判据 B）、`representation_follows_projection_contract`（判据 C）、`representation_contract_digest_matches`（判据 D）。
- **判据 A / B / C / D**：见 LaneSupplyFacts。四条取数来源两两不同（definition 表 / entry pointer 表 / representation→bundle 反查 / 磁盘契约↔bundle slot digest）。
- **首版**：某 (wp_id, entry_id) 的第一个 published representation，对应第一个 content version、`generation = 1`。
- **代际提升**：同一 content version 的新 representation generation，由 Task 36 / 77 的 finalize gate 产出，`content_revision` 不变。
- **Frozen_Definitions**：`FrozenEntryDefinitions`。有两个互不依赖的生产者：`PublishedIdentityObserver.observe()`（需 representation）与 `ExcelEntryDefinitionLoader.load()`（不需 representation）。
- **供给门**：`adapters/registry._describe_entry_supply`。要求 entry current pointer 存在、representation row 存在、绑定 definition bundle 三条。
- **capability 门**：各 pilot `attach_pilot_adapters()` 首部的 `if not manifest_capability_enabled(): return ()`，其真值由 source-backed manifest 的 entry capability 决定。
- **注册门**：`WorkpaperSyncAdapterRegistry.register()` 的 RG-1~RG-19。
- **伪造供给五形态**：自造 uuid 或 digest；在 `projection_contract` 的 contract slot 用版本化 typed null marker 冒充 contract；写空串或全零 hash；slot omission 或 SQL NULL；把 generator 候选当已人工审核的 per-entry contract 发布。
- **变异四态**：RED（打红且正是预期那条测试）、GREEN（守卫缺陷）、ANCHOR-MISS（脚本缺陷，锚点未命中或命中多于一处）、WRONG-TEST（打红但不是预期项）。
- **既有门禁三门**：`check_task44_oo94_excel_pilot_gate.py`（R1）、Lane_Guard 加 PG 现读（R2）、`check_task61_oo94_word_pilot_gate.py`（R3）。

## Requirements

### Requirement 1: lane 裁决的单一真源

**User Story:** 作为平台架构维护者，我需要一个 lane 裁决的单一真源，以便任何调用方都能对同一 entry 得到相同、可测、三值封闭的选路结论，而不是各处按形态自行猜测。

#### Acceptance Criteria

1. THE Lane_Registry SHALL 为任一 entry_id 返回落在封闭枚举 `{projection, opaque, undecided}` 内的 LaneVerdict。
2. WHEN 同一 entry_id 与同一 manifest 快照被重复裁决，THE Lane_Registry SHALL 返回相同的 LaneVerdict。
3. THE Lane_Registry SHALL 按固定顺序 L1（opaque entry_id 形态）→ L2（manifest 归属）→ L3（per-entry 契约登记）→ L4（independent_entry 与 capability 非 unreachable）→ L5（磁盘契约 review_status 为 reviewed）求值。
4. WHEN entry_id 命中 `OPAQUE_AUTHORITY_LANES` 任一 lane 声明的 `entry_id_source` 形态，THE Lane_Registry SHALL 返回 `opaque` 并终止后续判据求值。
5. IF L2 至 L5 中任一判据不成立，THEN THE Lane_Registry SHALL 返回 `undecided`，并在诊断中给出首个不成立判据的编号与该判据的真源文件路径。
6. WHEN L1 至 L5 全部成立，THE Lane_Registry SHALL 返回 `projection`。
7. WHEN 调用 `assert_projection_lane` 且裁决结果不是 `projection`，THE Lane_Registry SHALL 抛出携带 `error_code` 的异常，`opaque` 结果用 `lane_is_opaque`，`undecided` 结果用 `lane_undecided`。
8. THE Lane_Registry SHALL 把 L1 的 entry_id 形态表与 `opaque_entry_gate.OPAQUE_AUTHORITY_LANES` 逐项交叉锁死，两侧任一新增或修改一条 lane 时使 `assert_registry_covers_opaque_lanes` 失败。
9. THE Lane_Registry SHALL 提供 `assert_no_second_lane_decision_site`，以抽象语法树扫描 `backend/app/**` 与 `backend/scripts/**`，把按 authority model 取值或 `opaque-` 前缀自行判定 lane 且未调用 Lane_Registry 的语法位置报为违规，并返回合规调用点清册。

### Requirement 2: 供给四条独立判据

**User Story:** 作为审计平台的质量负责人，我需要「已 provision projection bundle」与「representation 真按 projection contract 发布」各有独立判据，以便任一侧被短路时守卫都会打红，而不是两条互相遮蔽。

#### Acceptance Criteria

1. THE Supply_Observer SHALL 为一个 (project_id, wp_id, entry_id) 三元组产出携带判据 A、判据 B、判据 C、判据 D 四个布尔值的 LaneSupplyFacts。
2. THE Supply_Observer SHALL 以 definition bundle 与 definition artifact 表取判据 A、以 entry pointer 表取判据 B、以 representation 到 bundle 的反查取判据 C、以磁盘契约 canonical digest 与 bundle contract slot digest 的比对取判据 D。
3. THE LaneSupplyFacts SHALL 仅在判据 A、B、C、D 四者同时为真时报告供给成立。
4. WHEN 判据 A、B、C、D 中至少一条为假，THE Lane_Registry SHALL 由 `describe_supply_gap` 返回非空诊断文本，并在文本中点名首个为假的判据。
5. WHILE 判据 A 为真且判据 B 为假，THE Lane_Registry SHALL 在诊断文本中同时点明判据 A 已满足与判据 B 未满足。
6. IF Supply_Observer 的任一取数抛出异常，THEN THE Supply_Observer SHALL 抛出携带 `error_code=lane_supply_observation_failed` 的异常并记为 ERROR 级，而不返回一个四条判据皆为假的 LaneSupplyFacts。
7. THE Supply_Observer SHALL 在判据 A 的查询中要求 authority model 类型为 `projection_contract`、definition 与 bundle 两侧 state 均为 approved、且三个 typed slot 均为 definition 形态。
8. THE Supply_Observer SHALL 在判据 C 中把 current representation 绑定的 bundle 的 authority model 类型与 `projection_contract` 比对，使绑定 opaque bundle 的 representation 无法满足判据 C。

### Requirement 3: 首版发布的准入

**User Story:** 作为审计平台的开发者，我需要首版发布入口在写任何一行之前跑完全部准入判据，以便失败时数据库一行不动、且诊断能指出具体卡在哪一条。

#### Acceptance Criteria

1. THE First_Publication_Service SHALL 按固定顺序求值五条准入：lane 必须裁决为 `projection`、判据 A 必须为真、判据 B 必须为假、bundle 三个 typed slot 逐项校验通过、磁盘 per-entry 契约的 review_status 为 reviewed。
2. WHEN 五条准入全部成立，THE First_Publication_Service SHALL 返回携带 project_id、wp_id、entry_id、authority model 逻辑标识、frozen bundle 标识与 frozen bundle digest 的冻结发布计划。
3. THE First_Publication_Service SHALL 从 `DELIVERED_PER_ENTRY_CONTRACTS` 现取 authority model 逻辑标识，而不在本模块写死该字面量。
4. IF 该 (wp_id, entry_id) 已有 current published representation，THEN THE First_Publication_Service SHALL 抛出携带 `error_code=first_publication_already_done` 的异常。
5. IF 判据 A 为假，THEN THE First_Publication_Service SHALL 抛出携带 `error_code=projection_bundle_not_provisioned` 的异常，并在诊断中指向 Task 76 的 provision 宿主脚本。
6. IF 磁盘 per-entry 契约的 review_status 不是 reviewed，THEN THE First_Publication_Service SHALL 抛出携带 `error_code=contract_not_reviewed` 的异常。
7. THE First_Publication_Service SHALL 把 bundle typed slot 与 digest 的深度校验委派既有 `load_bundle_snapshot` 与 `ExcelEntryDefinitionLoader`，而不在本模块重写同一判据。
8. WHEN 任一准入判据不成立，THE First_Publication_Service SHALL 使 `working_paper_content_version`、`working_paper_content_representation`、`working_paper_sync_entry_state` 与 `working_paper.content_revision` 四处相对调用前逐行不变。
9. THE 冻结发布计划 SHALL 在构造后不可变，且不持有 session、repository 或 outbox 等写入能力面。

### Requirement 4: instrumented substrate 的暂存与安全门

**User Story:** 作为审计平台的开发者，我需要 substrate 暂存阶段在纯文件侧跑完 OOXML 安全门，以便被策略拒绝的权威模板在发布前显式失败，而不是在事务中途炸出看不出来源的错误。

#### Acceptance Criteria

1. THE Substrate_Stager SHALL 以权威模板字节经 `instrument_workbook_bytes` 注入 identity 载体，并现算 identity inventory、observed structure、observed business sheets 与 observed dynamic columns 四项运行时实测入参。
2. THE Substrate_Stager SHALL 在暂存期间不执行任何数据库读写。
3. THE Substrate_Stager SHALL 在产出 staged substrate 之前对字节调用既有 `validate_ooxml_artifact`。
4. IF 权威模板字节被 OOXML 安全策略拒绝，THEN THE Substrate_Stager SHALL 抛出携带 `error_code=ooxml_security_rejected` 与被拒 gate 名称的异常，且不产生任何 staged artifact。
5. THE Substrate_Stager SHALL 使 `xl/externalLinks/` 部件、`xl/vbaProject.bin` 部件与嵌入对象三类各自触发第 4 条的拒绝。
6. THE Substrate_Stager SHALL 把动态列的稳定键由 `dynamic_column_stable_keys` 现算，并只把 label 放入 observed 侧，不用 label 充当键。

### Requirement 5: 首版 published representation 的发布

**User Story:** 作为审计平台的开发者，我需要首版发布走 `ExcelEntryDefinitionLoader` → `build_excel_adapter` → `ContentMutationService.commit` 这条链，以便在不放宽任何既有判据的前提下打破 representation 与 adapter 的循环依赖。

#### Acceptance Criteria

1. THE First_Publication_Service SHALL 以 `ExcelEntryDefinitionLoader.load` 产出 Frozen_Definitions，其入参全部来自 approved projection bundle 与 Substrate_Stager 现算的实测值。
2. THE First_Publication_Service SHALL 以 `build_excel_adapter` 并以 `direction="html_to_oo"` 构造 adapter。
3. THE First_Publication_Service SHALL 把该 adapter 作为 `adapter` 实参传入 `ContentMutationService.commit`。
4. WHEN 首版发布成功，THE First_Publication_Service SHALL 使落库 representation 的 definition bundle 标识、definition bundle digest、authority model definition 标识、adapter 标识、adapter build digest、structure hash 与 identity inventory digest 七个字段，与冻结发布计划及 Substrate_Stager 现算实测值逐项相等。
5. WHEN 首版发布成功，THE First_Publication_Service SHALL 使 `content_revision` 由 `expected_revision` 变为 `expected_revision + 1`，并产生恰好一个 content version、一个 generation 为 1 的 representation 与一条 entry pointer。
6. WHEN 首版发布成功，THE First_Publication_Service SHALL 使该笔业务事务的 commit 次数为一次。
7. IF 发布过程中任一阶段失败，THEN THE First_Publication_Service SHALL 使第 3 项需求第 8 条列举的四处相对失败前逐行不变。
8. THE First_Publication_Service SHALL 不修改 `PublishedIdentityObserver` 的任何判据，也不为绕过 `_assert_authority_shape` 而以 `adapter=None` 调用 `ContentMutationService.commit`。

### Requirement 6: 唯一幂等宿主

**User Story:** 作为现场经理，我需要一个只读预演加真发布的幂等宿主，以便在动库之前先看到逐 entry 的结算，并在重跑时不产生第二份供给。

#### Acceptance Criteria

1. THE Publication_Host SHALL 提供 `--check`、`--apply` 与 `--json` 三个入口。
2. WHILE 运行 `--check`，THE Publication_Host SHALL 裁决 lane、观测四条供给判据、在临时目录内 instrument 权威模板并跑完 OOXML 安全门、`ExcelEntryDefinitionLoader` 全部校验步骤与 `build_excel_adapter`，且不写入数据库任何一行。
3. THE Publication_Host SHALL 把每个目标 entry 的结算取值限定在封闭词表 `{ready_to_publish, blocked_missing_approved_bundle, blocked_ooxml_gate, blocked_contract_not_reviewed, blocked_lane_undecided, already_published}` 内。
4. THE Publication_Host SHALL 以 `DELIVERED_PER_ENTRY_CONTRACTS` 与真实 `working_paper` 现算目标清单，而不写第二份 entry 清单。
5. THE Publication_Host SHALL 以 `wi.wp_code, wp.created_at, wp.id` 的全序为每个 entry 选取唯一目标底稿，使 `--check` 与 `--apply` 对同一库状态选出相同的 (project_id, wp_id)。
6. WHILE 运行 `--apply`，THE Publication_Host SHALL 为每个 (wp_id, entry_id) 使用独立事务。
7. IF `--apply` 处理某一 entry 时失败，THEN THE Publication_Host SHALL 只回滚该 entry 的事务、继续处理后续 entry，并以非零退出码报告 ERROR。
8. WHEN 对已发布首版的 entry 重跑 `--apply`，THE Publication_Host SHALL 把它结算为 `already_published`，并使该 entry 的 representation、content version 与 entry pointer 三者的行数与 digest 逐项不变。
9. THE Publication_Host SHALL 对 `xlsx/b60/gt-b60-bundle` 结算为 `blocked_ooxml_gate`，并在诊断中写明解除条件属 OOXML 安全策略裁决。
10. THE Publication_Host SHALL 对 `xlsx/gt-g7-long-term-equity-main` 结算为 `blocked_missing_approved_bundle`，并在诊断中指向 Task 76 的 provision 宿主脚本。
11. IF 任一失败使诊断无法给出具体原因，THEN THE Publication_Host SHALL 以非零退出码失败，而不输出「本项目无此数据」一类降级文案。

### Requirement 7: 禁止伪造供给与禁止放宽判据

**User Story:** 作为质量控制复核合伙人，我需要伪造供给的每一种形态各有一条独立打红判据，以便注册数与发布数的增长只可能来自真实供给。

#### Acceptance Criteria

1. THE First_Publication_Service SHALL 使伪造供给五形态各以互不相同的 `error_code` 被拒绝，并在诊断中指出首个非法 slot。
2. THE First_Publication_Service SHALL 不放宽 `WorkpaperSyncAdapterRegistry.register` 的 RG-1 至 RG-19 任一判据。
3. THE First_Publication_Service SHALL 不使用占位 adapter 标识，包含全零 digest、空字符串与自造 uuid 三种形态。
4. THE Lane_Registry SHALL 不把 `PublishedIdentityObserver` 改为返回空值或空 identity。
5. THE First_Publication_Service SHALL 不在 `projection_contract` 的 contract slot 接受版本化 typed null marker。
6. THE First_Publication_Service SHALL 不接受 slot 缺项或 SQL 空值形态的 bundle。
7. THE First_Publication_Service SHALL 不把 generator 候选契约当作已人工审核的 per-entry 契约发布。
8. WHERE manifest capability 需要由 `single_onlyoffice` 改为 `bidirectional`，THE 变更 SHALL 经 reviewed overlay 裁决并重生成 manifest，且不绕过 `approved_source_digest` 复核门。
9. WHILE `PENDING_ENGINE_ADAPTERS` 仍禁止 `app/services/workpaper_sync/adapters/word.py` 路径，THE 本需求范围 SHALL 不落地任何 Word adapter。
10. THE 本需求范围内的一切数据库写入 SHALL 经服务层或幂等宿主脚本执行，且 PostgreSQL MCP 保持 restricted 只读。

### Requirement 8: 连带回归判据

**User Story:** 作为项目质量控制复核人，我需要连带解除的三条回归判据全部复用既有门禁读数，以便新旧基线可直接比对而不引入第二份读数。

#### Acceptance Criteria

1. THE Lane_Guard SHALL 复用 `check_task44_oo94_excel_pilot_gate.py` 的读数作为 adapter 注册状态的判据，而不另造第二份读数。
2. WHEN 某 entry 已落成首版且其 manifest capability 已裁决为 `bidirectional`，THE 供给门 SHALL 对该 entry 返回空值表示供给成立，且 `register_from_manifest` 的已注册 adapter 标识集合 SHALL 包含该 entry 的契约标识。
3. THE `register_from_manifest` SHALL 在任何供给状态下满足已注册 entry 数与未注册 entry 数之和等于计划 entry 总数。
4. WHEN 首版落成，THE Lane_Guard SHALL 证明至少一条 representation 绑定的 bundle 的 authority model 类型为 `projection_contract`。
5. THE Lane_Guard SHALL 把「representation upgrade candidate 表可能有行」表述为首版落成之后的结果，而不作为首版落成的前置条件。
6. THE `check_task61_oo94_word_pilot_gate.py` 的 BP-61-1 判据 SHALL 由「entry state 表全表行数为零」改为「是否存在某个 manifest entry 的 current published representation」。
7. THE BP-61-1 的绑定约束先后关系 SHALL 继续由该门既有的 arm_a、arm_b、arm_c 三臂实测得出，而不由写死字面量得出。
8. WHEN Lane_Guard 与既有三门重跑完成，THE 新基线 SHALL 被记录，且既有门禁的 failed 计数 SHALL 不因本需求的交付而增加。

### Requirement 9: 过期登记的更正

**User Story:** 作为平台架构维护者，我需要把已被实测推翻的登记读数更正到位，以便后续复盘不再基于过期事实做判断。

#### Acceptance Criteria

1. WHEN 首版落成后重跑核对，THE `opaque_entry_gate.ENTRY_ID_NAMESPACE_SPLIT_NOTE` 的实测迁移成本读数 SHALL 与真实库当前行数一致。
2. THE `ENTRY_ID_NAMESPACE_SPLIT_NOTE` 的裁决归属 SHALL 继续指向 Task 67，且本需求范围 SHALL 不合并 opaque lane 内部的 entry_id 命名空间分叉。
3. THE Lane_Guard SHALL 把「upgrade candidate 的 source representation 标识为非空外键」记为 candidate 路径无法产出首版的结构依据。
4. THE 本需求范围 SHALL 不新增数据库迁移文件。

### Requirement 10: 守卫质量与变异检验

**User Story:** 作为审计平台的开发者，我需要每条守卫都经过变异检验并按四态判读，以便「守卫全绿」真的意味着行为正确而不是判据缺陷。

#### Acceptance Criteria

1. THE Mutation_Runner SHALL 为每条守卫声明至少一个变异锚点，并记录该变异所守的假绿形态。
2. THE Mutation_Runner SHALL 把每次变异结果判读为 RED、GREEN、ANCHOR-MISS 或 WRONG-TEST 之一，而不以退出码代替判读。
3. IF 某锚点在源码中命中次数不等于一，THEN THE Mutation_Runner SHALL 判为 ANCHOR-MISS 并报告实际命中次数。
4. THE Mutation_Runner SHALL 提供 `--check-anchors` 只读入口，用于核对全部锚点在当前源码上仍恰好命中一次。
5. THE Mutation_Runner SHALL 覆盖以下变异：把 L1 判据移到 L2 之后、把供给成立判定改为只读判据 A、把 Supply_Observer 的异常改为返回假值、把首版准入第三条的期望值取反、删除 OOXML 安全门调用、把 `commit` 的 adapter 实参改为空值、新增第二处 lane 判定位置、把每 entry 独立事务改为共用一个事务边界、把宿主对发布方法的调用改为只取引用不调用。
6. THE 本需求范围内的一切判据 SHALL 落在行为、结构或真实执行上，而不落在字符串是否存在上。
7. THE 守卫脚本 SHALL 在截取函数体时以括号配对并先跳过参数列表，且不以固定字符窗口截断。
8. THE 守卫脚本 SHALL 不以注释剥离逻辑处理内嵌 SQL 文本块。

### Requirement 11: 真实环境验证与数据复原

**User Story:** 作为现场经理，我需要首版发布在真实 PostgreSQL 上验证且测试数据可完整复原，以便验证结论可信且不污染库。

#### Acceptance Criteria

1. THE 首版发布验证 SHALL 在真实 PostgreSQL 上执行，并在临时 schema 内完成后丢弃该 schema。
2. THE 验证 SHALL 以数据库中的数据判定成败，而不以进程退出码判定成败。
3. WHEN 回写带时区时间戳字段，THE 验证夹具 SHALL 在 Python 侧转为 datetime 对象，而不依赖 SQL 层类型转换。
4. THE 复原流程 SHALL 使每一步使用独立事务边界，使某一步失败不撤销先前已成功的步骤。
5. THE 连库守卫 SHALL 在单次事件循环内取得全部快照，而不为每条测试各自建立事件循环。
6. THE 测试执行 SHALL 从仓库根目录调用 pytest，并按对本需求交付物的实际引用关系确定辐射面，而不执行全量后端测试目录。
7. WHEN 验证结束，THE 临时诊断产物 SHALL 被清理。

### Requirement 12: 范围边界

**User Story:** 作为业务合伙人，我需要范围边界写进需求并各自说明理由，以便后续不因失焦把独立劳动量并进来。

#### Acceptance Criteria

1. THE 本需求范围 SHALL 不包含 Task 74 的 writer 迁移七条准则归零。
2. THE 本需求范围 SHALL 不包含 Task 71 的 `multi_resolver` 归零。
3. THE 本需求范围 SHALL 不放宽 OOXML 安全策略的外部关系许可。
4. THE 本需求范围 SHALL 不为供给门或 pilot attach 入口增加 project 或 wp 维度作用域。
5. THE 本需求范围 SHALL 记录首版目标的可行域，其中 `xlsx/gt-h1-fixed-assets` 与 `xlsx/gt-d2-accounts-receivable` 为可发布目标，`xlsx/b60/gt-b60-bundle` 因 OOXML 安全门受阻，`xlsx/gt-g7-long-term-equity-main` 因缺 approved bundle 受阻。
6. WHERE manifest 无法在不解除 Task 67 的 BP-67-1 的前提下重生成，THE adapter 注册目标 SHALL 拆为两阶段，第一阶段只证明供给门放行，capability 翻转另行处理。
7. WHERE overlay 的现有覆盖粒度不支持逐 entry 的 capability 覆盖，THE schema 扩展 SHALL 由 manifest generator 域承接，而不在本需求范围内自行增加字段。
