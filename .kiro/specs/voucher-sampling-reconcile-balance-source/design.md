# 抽凭总体完整性核对接入科目余额表 + 预览内就地放行 — 设计

## 1. 根因链

三个先后落地、各自看起来合理的决策叠加成「恒阻断」：

1. voucher-sampling-hardening Req2：独立账面取试算表（资产负债类取期末余额 / 损益类取发生额）。
2. 同 spec 的 P1 口径守卫发现「期末余额 vs 发生额总体」是范畴错误 ⇒ 资产负债类直接返回 `(None, None)`。
   前提是「试算表没有发生额列」—— 但科目余额表 `tb_balance` 有（`debit_amount` / `credit_amount`）。
3. sampling-evaluation R5：核对不可用 / 不符即阻断回填。

再加上损益类比对口径本身错（GREATEST 绝对值合计 vs 审定净额），结果是几乎所有科目都过不了。

**第四层根因（2026-10-21 补充）**：即使改用余额表发生额，抽凭传入的是标准科目编码（如 `1122`），
而 `tb_balance`/`tb_ledger` 存的是企业原始编码。当企业编码与标准编码不一致时，前缀匹配查不到数据，
核对依然退化成噪声。平台已有 `account_mapping` 表维护 `original → standard` 映射，但抽凭路径完全绕过。

## 2. 核对口径

| 项 | 取值 |
|----|------|
| 科目码解析 | **优先映射**：`account_mapping` 中 `standard_account_code LIKE '{标准码}%'` 且 `is_deleted=false` 的所有 `original_account_code`；**无映射退回**：直接用标准码做前缀匹配（向后兼容） |
| 序时账侧 | `tb_ledger`：项目 + 年度 + 抽样框数据集（与总体同一 `dataset_id`）+ `is_deleted=false` + 凭证日期在该年 1/1~12/31 + **解析后的科目码集合**做前缀匹配；`SUM(debit_amount)`、`SUM(credit_amount)`，**带符号** |
| 账面侧 | `tb_balance`：同项目 / 年度 / 数据集 + **解析后的科目码集合**做前缀匹配；取**最高层行**（范围内不存在「是其前缀的另一行」）的 `debit_amount`、`credit_amount` 合计 |
| 判定 | 借方、贷方分别 `|序时账 − 账面| ≤ |账面| × 可容忍比例`，两者都满足才算一致 |
| 手工录入 | 与序时账「借+贷」合计比对（`|差| ≤ |手工值| × 比例`） |

**为什么带符号**：红字冲销在序时账里是负数，余额表发生额是净额；取绝对值会把冲销重复计入（安徽 1122.01 带符号借方 10.01 亿，绝对值 21.84 亿）。
平台导入期已有同口径规则 `import_engine.validation.LedgerBalanceReconcileRule`（逐科目比带符号借贷合计）。

**为什么取最高层行而不是叶子**：真库全量比对两种取法只有 2 处不一致（和平物流 1601 / 2651，余额表自身父≠子之和），
其中 2651 贷方是最高层行与序时账相等。最高层行就是总账口径的「账面」。

**为什么不受抽样筛选影响**：完整性核对验证的是抽样框来源（序时账）相对账面是否完整；按金额、期间、摘要等筛选是总体界定，
若对筛选后的子集比对，任何筛选都会「不符」，门禁又退化成噪声。首次回填后默认 `exclude_extracted=true` 的二次抽样同理。

**为什么用凭证日期年度窗口**：与总体默认窗口一致；真库 8 个项目序时账无一条落在年度外，若将来出现会以差异暴露。

**为什么优先用映射反查**：企业科目编码体系不一定与标准编码前缀兼容（如 `SA1122` 或 `100201` 等自定义编码），
直接用标准码做前缀匹配会命中 0 行。映射表是审计师人工确认过的「企业码 → 标准码」对应关系，
反查后得到的原始码集合覆盖了企业实际使用的全部该标准科目的编码变体。

## 3. 科目映射反查设计

### 3.1 新增纯函数 `resolve_effective_codes`

放在 `sampling_population_reconcile.py` 内（不引入新模块，核对与映射反查是同一流程）：

```python
async def resolve_effective_codes(
    db: AsyncSession,
    project_id: UUID,
    standard_codes: list[str],
) -> tuple[list[str], bool]:
    """将标准科目编码通过映射表反查为企业原始编码。

    Returns:
        (effective_codes, mapping_used)
        - mapping_used=True: 返回的是映射表中的原始编码集合
        - mapping_used=False: 映射表中无匹配，退回标准编码原样（向后兼容）
    """
```

逻辑：
1. 查 `account_mapping` 表：`project_id = ? AND is_deleted = false AND standard_account_code LIKE ANY(standard_codes 的前缀)`
2. 取所有命中行的 `original_account_code` 去重
3. 若结果非空 → 返回 `(original_codes, True)`
4. 若结果为空 → 返回 `(standard_codes, False)` —— 向后兼容，保持原有前缀匹配行为

### 3.2 接入核对主函数

`resolve_population_reconcile` 在构建过滤条件前先调用 `resolve_effective_codes`，
用返回的 `effective_codes` 替换 `account_codes` 做后续查询。
结果 `PopulationReconcileFacts` 新增字段 `mapping_used: bool`（`to_stats()` 输出到 API）。

### 3.3 接入抽凭查询（LedgerSamplingService）

`voucher_sampling.py` 在调用 `LedgerSamplingService.build_ledger_query` 前，
先调用 `resolve_effective_codes` 解析 `filters.account_codes`，
将解析后的编码传入 `LedgerQueryFilters.account_codes`。
这使得**抽凭总体查询本身也能命中企业自定义编码的序时账**——
否则即使核对用了映射、总体却查不到数据，前后不一致。

### 3.4 不可用原因增强

当 `mapping_used=false` 且余额表查不到行时，`unavailable_reason` 追加
「建议先在『科目映射』中确认映射关系」，引导审计师完成映射。

## 4. 后端

### 4.1 模块 `backend/app/services/sampling_population_reconcile.py`

- `PopulationReconcileFacts`（frozen dataclass）：`available` / `basis`（`tb_balance_movement`）/ `ledger_debit` / `ledger_credit` /
  `book_debit` / `book_credit` / `unavailable_reason` / **`mapping_used`**（bool，默认 False）；`to_stats()` 输出 API 扁平字段。
- `select_top_level_rows(rows)`：纯函数，按科目码前缀关系取最高层行。
- `resolve_effective_codes(db, project_id, standard_codes)`：映射反查纯函数，返回 `(codes, mapping_used)`。
- `resolve_population_reconcile(db, project_id, year, account_codes, dataset_id)`：
  - 先调 `resolve_effective_codes` 解析编码
  - 过滤条件用 `dataset_query.get_filter_with_dataset_id`（有数据集）/ `sync_active_filter`（无数据集，镜像 `get_active_filter` 的降级），
    **不再调用** `get_active_filter`（其失败分支会 `db.rollback()` 整个会话）。
  - 两条只读查询包在 `db.begin_nested()` 里；任何异常记 WARNING、返回不可用（原因「取数失败」），不污染外层事务。
  - 不可用原因：未指定科目 / 科目余额表中无所选科目的行（未导入或科目编码不一致，若未用映射则追加映射建议）/ 取数失败。

### 4.2 路由 `voucher_sampling.py`

- 删除 `_resolve_independent_book_amount` 与仅为它导入的 `TrialBalance`。
- 在 `filters` 解析出 `account_codes` 后先调 `resolve_effective_codes` 得到 `(effective_codes, mapping_used)`。
- `effective_codes` 传入 `LedgerQueryFilters.account_codes`（抽凭总体查询也用映射后的编码）。
- `effective_codes` 传入 `resolve_population_reconcile`（核对也用同一组编码）。
- `stats` 保留 `book_amount`（= 余额表借+贷）/ `reconcile_available` / `reconcile_basis`，
  新增 `reconcile_ledger_debit` / `reconcile_ledger_credit` / `reconcile_book_debit` / `reconcile_book_credit` / `reconcile_unavailable_reason` / **`reconcile_mapping_used`**。
- 性能：映射反查是小表单次查（`account_mapping` 通常百行级），序时账侧多一次聚合扫描。真库最大科目（和平药房 2024 / 1122，47 万行）冷缓存 2.5 s、热缓存 0.66 s；
  抽凭是低频操作，接受。不做「筛选为空时复用总体统计」的优化（等价判定易错，错了会静默给出错误核对）。

## 5. 前端

### 5.1 新模块 `composables/samplingPopulationReconcile.ts`

- `parseReconcileInfo(stats)`：响应 → `PopulationReconcileInfo`（含逐方向金额 + 不可用原因 + **`mappingUsed`** + 向后兼容旧响应）。
- `resolvePopulationReconcile({ info, manualBook, populationAmount, thresholdPct })`：手工优先 → 自动逐方向 → 都没有返回 `null`；
  旧响应（无逐方向字段）回落「序时账合计或总体金额 vs book_amount」单值比对。阈值一律取账面绝对值（修 `reconcilePopulation` 账面为负时恒判不符）。
- `describeReconcileIssue(result, info, pct)`：生成 R5 门控原因文案（不可用带原因 / 不符带逐方向差异 / 一致返回 `null`）。若 `mappingUsed=false` 且不可用，文案追加映射建议。
- `reconcilePresetsFor(result)`：仅「未执行核对」时返回预置理由。
- `formatMovementPair(debit, credit)`：「借 x / 贷 y 元」展示。

### 5.2 `useVoucherSampling.ts`

- `reconcileInfo` 改由 `parseReconcileInfo` 产出（类型扩展，旧字段保留）。
- 新增 `conclusionBlockedSource`：`'unchecked' | 'deviation' | 'reconcile' | 'other' | null`，首句 `if (!conclusionBlockedReason.value) return null`
  保证与原因同为空；判定顺序与 `conclusionBlockedReason` 同链，未知新门控落 `'other'`（走保守提示）。

### 5.3 `GtVoucherSamplingEngine.vue`

- `populationReconcile` / `reconcileIssue` 改调新模块；卡片增「序时账发生额（所选科目·全年）」行，账面来源标签按 basis 显示「科目余额表发生额」，
  差异按逐方向显示；**映射状态标签**：`mappingUsed=true` 显示「已通过科目映射」/ `false` 显示「直接匹配（未使用映射）」。
- `confirmBlockedReason`：来源为 `reconcile` 时后缀改为「可直接在本窗口下方『总体完整性校验』处填写说明」。
- 预览组件传入 `reconcile-issue` / `v-model:reconcile-override-reason` / `reconcile-presets`。

### 5.4 `SamplingPreviewDialog.vue`

- 新 props `reconcileIssue`（缺省 `null` = 不显示，旧调用点零变化）/ `reconcileOverrideReason` / `reconcilePresets`，emit `update:reconcileOverrideReason`。
- 底部操作区上方渲染「总体完整性校验」块：原因 + 文本框（≤500 字、字数统计）+ 预置理由 + 「还需 N 字 / 已填写」状态。

## 6. 测试

| 层 | 文件 | 覆盖 |
|----|------|------|
| 后端纯函数 + SQLite 真行 | `test_sampling_population_reconcile.py`（新） | 最高层行、前缀、数据集过滤、年度窗口、三类不可用原因、取数失败降级、**映射反查（有映射/无映射/部分映射/映射后最高层行选取）** |
| 后端端点契约 | `test_voucher_sampling_reconcile.py`（重写） | 新字段（含 `reconcile_mapping_used`）、资产类不再恒不可用、不自身比对、**映射后抽凭总体也用原始编码** |
| 后端回归 | `test_voucher_sampling_unit.py` | patch 目标改名 |
| 前端纯函数 | `samplingPopulationReconcile.spec.ts`（新） | 逐方向判定、负数账面、手工口径、旧响应回落、文案、预置理由、**映射状态文案** |
| 前端接线 | `samplingReconcilePreviewOverride.spec.ts`（新） | composable 门控来源、预览就地放行（挂载）、引擎传参 |

## 7. 不在本 spec 范围（待用户裁决）

- **R3/R4 门控也挡回填**：未检查样本（`checkResult` 为空）必须先选处置才能「确认填充」。抽出的样本默认全为空，
  审计师要么在预览里先填核查结果、要么批量填「Y」才能把样本写进底稿 —— 后者等于未检查先记「已核查无异常」。
  sampling-evaluation R3.4 写的是「阻止确认抽样结论」，实现把它挂在了回填上。是否改为「只挡结论确认 / A13 推送、不挡回填」需用户拍板。
- 自动核对结果（口径、逐方向差异、阈值、结论）尚未写入回填留痕 `extraction_criteria`；仅放行理由随评价落库。
