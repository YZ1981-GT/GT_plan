# N4 税金及附加 真双向改线 —— 验证证据

> spec: `n-cycle-sync-foundation-and-first-canary` · N4 canary
> 实施：照 L1 playbook 逐环，仅 N4（不动 N1/N2/N3/N5）。所有命令在 Windows/PowerShell +
> `d:\GT_plan\.venv\Scripts\python.exe` 下跑；判成败一律**查数据不看退出码**。
> 本证据供复核阅读，不必重跑。

## 0. 几何现算（Task 1，净化后复算）

权威模板 `backend/wp_templates/N/N4 税金及附加.xlsx`（净化后）：
- size **46325**、sha256 **`2005eada32506e9e2b1b6f68c704ca4f6626b8a78e9e2a3a221ca00602cad638`**
- 9 sheet；definedName 0；Excel Table 0
- 受管 sheet `税金及附加明细表N4-2`：单级表头 r8、11 列 A..K、数据区 r9~r18
  （r9~r16 预印 8 税种名 消费税/城市维护建设税/教育费附加/资源税/房产税/土地使用税/
  车船使用税/印花税，r17/r18 空）、footer **A19「合计」**、UUID 列 **L**（max_col+1）
- 公式列恰 **E/I/K**：E=B+C+D（本期审定数）/ I=F+G+H（上期审定数）/ K=E-J（与应交税费贷方差异）
- footer SUM 列 B..K；合并单元格仅 A1:K1 / A2:K2（数据区不跨合并）
- 整册裸 IF **20 格全在派生表 `税金及附加审定表N4-1`**（K/M 列变动率），受管表零命中
- 🔴 模板既知缺陷（记录型锁定，**不改模板**）：`E9='=B9+C9+N4'`（第三加数误写列引用，NC-32 A1 族）、
  `D19='=SUM(D4:N18)'`（footer SUM 越界）

## 1. OOXML 净化（Task 7a，照 L4/I/J/D）

脚本 `backend/scripts/fix/sanitize_n4_template_external_links.py`（复用 I 循环 `sanitize_bytes` 内核）。
`--apply` 结果（判成败查数据）：
- gate **before = REJECT external_relationships** → **after = PASS**
- stats = dropped_parts **4**（externalLink{1,2}.xml + 各自 _rels）、neutralized_formulas **5**
  （全在**隐藏**册 `税金及附加审计程序表O2A（原底稿）`，引用 `[1]底稿目录!`/`[2]底稿目录!` 的死外链）、
  dropped_defined_names 0、dropped_hyperlinks 0、dropped_ole_objects 0
- 受管 sheet `税金及附加明细表N4-2`：净化前后 **77→77 格，逐格 0 diff，merge 不变**
- `.preclean.bak` 保留为门负例（仍 REJECT）；`vmlDrawing{1,2}.vml` 是批注/控件 VML、不触发门、保留；
  `printerSettings*.bin` 是打印设置、非 OLE、门不拒
- 净化后 formula_cells 236→**231**（5 外部引用公式中性化）、sheets_with_formula 7→**6**；sheet_count 9 不变

## 7c/7d. 五环发布（真 PG，查数据不看退出码）

- wp_code 裁决 `fix_n_cycle_wp_code_adjudication.py --apply`：N4→`['N4']`（真底稿 5 份、file_path 全非空；
  `N4T` 幻影码 wp_index 零命中）。裁决表 53→54 条，digest `e8401d74…`。
- `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-n4-taxes-and-surcharges`：
  `created_total=5`、`errors=[]`；真库 `working_paper_sync_definition_artifact` 138→**142**、
  `working_paper_sync_definition_bundle` 42→**43**（approved bundle 就位）。
- `fix_projection_first_publication.py --apply --entry …`：10 阶段全跑通；真库
  `working_paper_content_version` 18→**19**、`working_paper_content_representation` 18→**19**；
  `working_paper_sync_entry_state` 新增 N4 行 current_representation_id=`22a3e9bd-…`、
  representation_generation=**1**；content_version_id=`753bb589-…`。
- 真库 `N4-2-detail-rows` 现算 **0 行** —— 五环照常发布，store 载荷分母**如实声明为空**
  （空 projection + instrumented 载体是合法首版）。

SQL 快照（evidence 现查）：
```
entry_state: [('xlsx/gt-n4-taxes-and-surcharges', '22a3e9bd-bad9-4cdd-ab65-6ff26e648c4b', 1)]
current representation: generation=1, artifact_sha256 len=64
N4-2-detail-rows live rows (honest empty denom): 0
```

## 8. manifest / overlay 翻转（仅 N4）

- overlay `overrides` **末尾追加**一条 N4（`GtN4TaxesAndSurcharges.vue` / `GtOnlyOfficeSheet` /
  `html_store=checklist_responses_n4_detail_rows` / `canonical_resolver=workpaper_sync_published_representation` /
  `adapter_id=n4.taxes_and_surcharges` / `capability=bidirectional` / `migration_state=adapter_registered` /
  `evidence_patch.legacy_reasons=[]`）—— 与 D1/L1/K 既有翻转同形，纯追加。
- manifest N4 条目翻转 6 字段（adapter_id/canonical_resolver/capability/migration_state/html_store/evidence），
  `stats.capability_counts` 同步，`overlay_digest`/`manifest_digest` 用生成器**同一算法**重算
  （`_sha256_bytes`/`_stable_json`）。
- 🔴 **未走 generator --apply**：①干净 HEAD worktree 跑它要 node_modules（mount discovery），worktree 无；
  ②live 树 overlay 已被并发 K/L 会话改脏，且 overlay 的 `l3.long_term_loans` override 尚未反映进
  manifest（跑生成器会把 L3 翻转一并烘进本次改动）。故**只改 N4 一条**、重算 digest，其余 185 条
  entry 逐字节不动。consistency 现查：overlay bidi == manifest adapter_registered；
  `source_digest==approved_source_digest`；overlay_digest / manifest_digest 均重算匹配。
- ⚠️ 并发注记：实施期间并发 L 会话把 L3 在 live manifest 翻成 adapter_registered（非本轮改动，
  已**保留**不覆盖）；本轮 N4 翻转与之叠加，manifest 内部 digest 自洽。

## 10. 真 OnlyOffice 9.4 往返（`verify_n4_oo94_roundtrip.py`，exit 0）

对真 `audit-onlyoffice`（localhost:8080，healthy）：
- ⑤ **OO ConvertService xlsx→xlsx 真重存 OK，percent=100**（50650 B）
- ⑥ extract 54 values，G1 等值门 OK
- ⑦ 我的 2 行合成载荷（固定 UUID rowKey）逐字段相等 + **8 条预印具名税种行以 `GTROW-N42-0009..0016`
  身份保留**（消费税…印花税），无错配身份
- ⑧a 受管行 E/I/K 往返后**仍是公式**（formula_mask 生效）
- ⑧b `税金及附加审定表N4-1` R7~R15×A..M 117 格：**OO 引擎改写 0 格**；materialize 只中性化
  18 个裸 IF（K7~K15 / M7~M15 变动率，GC-2 挂载预期）
- ⑨ store 0 行快照 digest 不变（脚本不写库）
- 🔴 **反向变异证明**：把 FORMULA_COLS 掺入文本列 A，脚本在 ⑧ 打红
  `受管行非公式格={'A19':'往返验证税种一',...}` 并 exit 1 —— ⑧ 判据非空转。
- 🔴 **J1 行翻倍防护（Task 7b）—— 已在后端/instrumentation 层证实**：N4-2 模板预印**具名**税种行，
  instrumentation 铸 `GTROW-N42-0009..0016`。真 OO 往返（⑦）实测这 8 行以模板身份保留、我的 2 行
  以自带 rowKey 保留、无身份错配、无行翻倍 —— 对齐机制在 substrate/instrumentation 侧已工作。
  🔴 **未新建前端 `n4DetailRowIdentity.ts`**：它若落在 `composables/` 会被 orphan 扫描器
  （`_n_composables`）判为无消费方的孤儿，而让 `useN4Detail.ts` 消费它必然移动该文件行号、
  连锁打红 slice 冻结的 `n4_detail_rows.row_identity.source_ref`（`#Lnn`）与多处 Property 23
  位置化计数（slice 把 useN4Detail 冻结为 untouched）。前端 HTML 侧让预印行采用 `GTROW-N42-*`
  身份属 useN4Detail 的一次独立、谨慎的改线（会动 slice 冻结锚点），留给后续批次；本轮 canary 的
  真双向闭环由后端往返证实已足够（预印行身份一致、不翻倍）。与 L1 的差异（L1 预印行只有序号、
  taxType 空、被 ghost anchor 过滤）如实登记。

## 9. 门与回归（相关子集全绿）

- `check_sync_provider_golden_digest.py`：含 N4，**无 SKIP**。🔴 N4 仅追加一条进基线
  （digest_count 143→146、families 24→25），d4/d5/d6/d7 等既存条目**逐字节不动**——那几家相对
  committed baseline 的既存漂移（并发会话改了 provider/contract 代码但未更新基线）**非本轮引入**，
  不随 N4 `--update` 烘入。N4 contract digest `e44e3a7c…` / sheet `n42-managed d68acdfd…` /
  projection `e8a06104…` / instr `08455bf9…`。
- `check_sheet_specs_fully_registered.py`：N4 adapter 已注册，分母 +1，通过。
- `test_n4_adapter_registration.py`：**33 passed, 1 skipped**（skip = `_resolve_oo_crash_neutralization_fn`
  非公开符号，graceful）。
- `test_task56_n_cycle_migration.py`：**123 passed**（N4-only 翻转后，用 `n_cycle_facts` post-slice
  模式仅为 N4 开豁免 —— 不删判据、不翻 N1/N2/N3/N5）。
- `test_n_cycle_foundation_canary.py`：**90 passed**（同 N4-only 豁免）。
- `import app.main`：OK。

## 交付物清单（本轮新建/编辑，仅 N4 范围）

| 文件 | 作用 |
|---|---|
| `backend/app/services/workpaper_sync/phase5_n4_sheets.py` | sheets 常量层（身份/几何/字段/SPEC_N42） |
| `backend/app/services/workpaper_sync/phase5_n4_taxes_and_surcharges.py` | provider（委派 L 公共骨架 + 三别名） |
| `backend/data/workpaper_sync_contracts/n4.taxes_and_surcharges.json` | reviewed 契约 |
| `backend/scripts/gen/generate_phase5_n_contracts.py` | 契约生成器（--check/--apply） |
| `backend/scripts/fix/sanitize_n4_template_external_links.py` | OOXML 净化 |
| `backend/scripts/fix/fix_n_cycle_wp_code_adjudication.py` | wp_code 裁决 |
| `backend/scripts/e2e/verify_n4_oo94_roundtrip.py` | 真 OO 往返守卫 |
| `backend/tests/workpaper_sync/test_n4_adapter_registration.py` | N4 守卫 |
| 追加 N4 一条：`delivered_contracts_ledger.py` / `store_item_registry.py` / `registry.py`（白名单） / `_sync_provider_golden_digest.json` / `workpaper_sync_entry_overlay.json` / `workpaper_sync_entry_manifest.json`（N4 条目翻转） / `workpaper_sync_entry_wp_code_adjudication.json` | registry/门接线 |
| `n_cycle_facts.py` / `test_task56_n_cycle_migration.py` / `test_n_cycle_foundation_canary.py` | N4-only 翻转豁免（不删判据） |
