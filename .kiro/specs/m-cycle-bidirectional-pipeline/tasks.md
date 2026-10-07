# M 循环双向回写管线 · 任务

> **实施纪律**
> - 🔴 contract JSON 的每个字段必须 openpyxl 现算确认（mode=formula 当且仅当该单元格有 `=` 开头的公式）
> - 🔴 M1 是负债类（2232），TB 回写口径与 M5/M8/M9 分开处理
> - 🔴 M9 无模式切换开关（orphan 已删），contract 不声明 mode switch 相关结构
> - 🔴 adapter 注册必须在 `backend/app/services/workpaper_sync/adapters/registry.py` 中完成
> - 🔴 OO 探针需要真实 OO 9.4 环境，不可用时标 `[ ]*`
> - 🔴 本 spec 期间冻结四本权威模板（sha256 校验），不改模板

---

## Phase 1：Contract 撰写（Task 0 ~ 7）

- [x] 0. openpyxl 精读 M5 审定表 M5-1 结构（canary sheet）
  - 审定表 48r×12c / 59 公式：两级表头 R5-R6，数据区 R7-R10（法定/任意/利润归还/其他），R11 合计 SUM
  - **B~K 列全是公式**（引用明细表 M5-2），只有 A 列（项目名称）和 L 列（原因分析）是 editable
  - R12=试算平衡表数（editable），R13=差异（formula），R14~R26 审计说明/结论文本区
  - 产出 field 清单：12 个字段（2 editable + 10 formula）

- [x] 1. openpyxl 精读 M5 明细表 M5-2 结构
  - 明细表 38r×17c / 41 公式：三级合并表头 R9-R11，数据区 R12-R15（4 行固定科目），R16 合计公式
  - Editable 列 12 个（A/B/C/D/E/F/H/I/J/K/L/M），公式列 5 个（G/N/O/P/Q）
  - 行身份方案：template_row_key（4 行固定科目，不是动态增删行）
  - 产出 field 清单：17 个字段（12 editable + 5 formula）

- [x] 2. 撰写 M5 contract JSON（canary contract）
  - `backend/data/workpaper_sync_contracts/m5.surplus_reserve.json` 已创建
  - review_status = "candidate"（待 Phase 2 发布 template definition 后升级为 reviewed）
  - 覆盖审定表（12 字段）+ 明细表（17 字段）= 29 字段
  - 🔴 `parse_contract()` 需要 `template_definition_sha256`（DAG 发布后产物），Phase 2 回填

- [x] 3. 撰写 M1 contract JSON
  - `backend/data/workpaper_sync_contracts/m1.dividends_payable.json`（33 字段：审定表 12 + 明细表 21）
  - 🔴 M1 是负债类（2232），明细表多出股东信息列（B/C/R/S/T/U）
  - 🔴 M1 审定表 A 列也是公式（=底稿目录!A9），只有 L 列 editable（1e/11f）

- [x] 4. 撰写 M8 contract JSON
  - `backend/data/workpaper_sync_contracts/m8.general_risk_reserve.json`（30 字段：审定表 12 + 明细表 18）
  - 🔴 M8 有「针对性测试M8-5-删除」和 Q8A 修订前，都不在受管范围

- [x] 5. 撰写 M9 contract JSON
  - `backend/data/workpaper_sync_contracts/m9.other_comprehensive_income.json`（32 字段：审定表 12 + 明细表 20）
  - 🔴 M9 明细表是 30 列宽表，公式列 17 个（含分组 SUM），editable 仅 3 个（大部分是中间计算列）

- [ ] 6. contract 强校验通过 + 守卫
  - 🔴 `parse_contract()` 需要 `template_definition_sha256`（DAG 发布后产物），Phase 2 回填后执行
  - 对四份 contract 运行 `parse_contract()` 断言全部通过
  - 断言 field 的 mode 与 openpyxl 现算一致（公式格 = formula，非公式 = editable）
  - 断言 `review.html_store.item_id` 前缀与 FormData ITEM_PREFIX 一致

- [ ] 7. contract sha256 冻结基线
  - 🔴 待 Phase 2 回填 template_definition_sha256 后冻结（当前 contract 处于 candidate 状态）
  - 计算四份 contract JSON 的 sha256，写入守卫
  - 计算四本权威模板的 sha256，与 slice 中 `template_ref.sha256` 等值校验

---

## Phase 2：Adapter 注册 + Definition DAG（Task 8 ~ 12）

- [x] 8. 为四条 entry 创建 provider + 共享内核
  - M 循环共享内核 `phase5_m_cycle_common.py`（~340 行）：MEntryConfig / MFieldSpec / MSheetConfig / build_m_provider / flat_key_value store 映射 / publish_m_definitions
  - `phase5_m1_dividends_payable.py`：33 字段（1e+11f / 16e+5f），🔴 负债类 2232，A 列也是公式
  - `phase5_m5_surplus_reserve.py`：29 字段（2e+10f / 12e+5f），canary provider
  - `phase5_m8_general_risk_reserve.py`：30 字段（1e+11f / 13e+5f），不覆盖「删除」和 Q8A 修订前 sheet
  - `phase5_m9_other_comprehensive_income.py`：32 字段（2e+10f / 3e+17f），🔴 宽表 30 列大部分公式
  - 四个 provider 全部 import + build_contract_payload 验证通过
  - 🔴 `delivered_contracts_ledger.py` 注册待后续步骤完成

- [ ] 9.* 发布 template definition × 4
  - 🔴 白名单已加（`_ALLOWED_PROVIDER_MODULES` 含四条 M 循环 provider）
  - 🔴 task76 `--check` 报 unresolved：真库无 M 循环底稿 working_paper 记录 ⇒ 无法 resolve target
  - 🔴 阻塞点不是代码而是**真库数据**：需要至少一个项目有 M5/M1/M8/M9 底稿才能 DAG 发布
  - 标 `[ ]*`：待真库有 M 循环底稿后执行 `task76 --apply --entry xlsx/gt-m5-surplus-reserve`

- [ ] 10.* 发布 instrumentation definition × 4
  - 🔴 需要运行时环境，标 `[ ]*`
  - 为每条 entry 声明行身份方案（instrumented stable identity）
  - `DefinitionPublisher.publish_definition(kind="instrumentation", ...)` × 4

- [ ] 11.* 发布 contract definition × 4
  - 🔴 需要运行时环境，标 `[ ]*`
  - 将 contract JSON 作为 definition 发布，回填 template_definition_sha256
  - `DefinitionPublisher.publish_definition(kind="contract", ...)` × 4
  - 回填后 review_status 从 candidate 升级为 reviewed

- [ ] 12.* 发布 definition bundle × 4
  - 🔴 需要运行时环境，标 `[ ]*`
  - 三个 slot（template + instrumentation + contract）全部 approved 后发布 bundle
  - `DefinitionPublisher.publish_bundle(authority_model="projection_contract", ...)` × 4
  - 断言 `authority_model` / `definition_bundle` 不再为 null

---

## Phase 3：Finalize + Published Representation（Task 13 ~ 15）

- [ ] 13. 为四条 entry 生成 staged candidate
  - instrumentation 标记 → 产出 instrumented xlsx + equivalence report
  - 断言 roundtrip 等值（instrumented 字节 sha256 == evidence 记录）

- [ ] 14. 调用 `ExcelEntryFinalizeGate.finalize_candidate()` × 4
  - 校验全部前置（bundle 存在 / evidence 一致 / structure hash）
  - 产出 `ExcelEntryFinalizeOutcome` × 4
  - 断言 `instrumentation_candidate` / `published_representation` 不再为 null

- [ ] 15. finalize 守卫
  - 断言 BP-2 的 4 个前提字段全部非 null
  - 断言 `migration_state` 仍为 `legacy_fake_bidirectional`（BP-3 未解除前不变）

---

## Phase 4：OO 探针验证（Task 16 ~ 18）

- [ ]* 16. 搭建 OO 9.4 探针环境
  - 确认 `audit-vllm-embed` / OnlyOffice 容器可用
  - 🔴 OO 不可用时标 `[ ]*`

- [ ]* 17. 执行 OO 探针 × 4
  - 对每条 entry 的 required scenario set 逐条执行
  - 收集 `EvidenceVerdict`：0 defect + 0 stale + run 存在 → verified
  - 🔴 OO 不可用时标 `[ ]*`

- [ ]* 18. evidence 守卫
  - 断言四条 entry 的 `verification_state == "VERIFIED"`
  - 断言 `sync_test_run_id` / `required_scenario_set_digest` 非 null
  - 🔴 OO 不可用时标 `[ ]*`

---

## Phase 5：端到端闭环（Task 19 ~ 22）

- [ ] 19. HTML → OO 方向验证
  - 在 HTML 侧通过 `setField` 修改明细表字段
  - 触发 materialize → OO 侧加载 → 验证同一字段值一致

- [ ] 20. OO → HTML 方向验证
  - 在 OO 侧修改 editable 字段 → 保存
  - 触发 extract → HTML 侧 `loadResponses` → 验证同一字段值一致
  - 🔴 formula 字段 OO 侧修改后 extract 应忽略（不回写 HTML）

- [ ] 21. TB 回写闭环
  - M1 回写到 trial_balance 2232（负债类）
  - M5 回写到 4101 / M8 回写到 4104 / M9 回写到 4103（权益类）
  - 验证 `writebackTB` 调用后 `trial_balance.audited_amount` 更新

- [ ] 22. 更新 slice + migration_state
  - 四条 entry 的 `migration_state` 从 `legacy_fake_bidirectional` 改为 `bidirectional`
  - 更新 `capability` 从 null 改为 `bidirectional`
  - 更新 `capability_target_blocked_by` 为空数组
  - 更新既存守卫断言

---

## Phase 6：收尾（Task 23 ~ 24）

- [ ] 23. 更新上游 spec 的 `[ ]*` 标记
  - `m1-m5-m8-m9-mode-value-and-carrier-exceptions` 的 Task 3/18/25 的 `[ ]*` 理由更新
  - INDEX.md 登记本 spec

- [ ] 24. 自检
  - 断言四份 contract 的 sha256 不变
  - 断言四本权威模板的 sha256 不变
  - 断言 adapter 注册数量正确
  - 断言无 U+FFFD
