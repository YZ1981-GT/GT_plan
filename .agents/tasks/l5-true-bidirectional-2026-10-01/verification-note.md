# L5 长期应付款「真双向」改线 — 验证记录

spec: `l5-true-bidirectional-2026-10-01`。本轮为**第一次迭代**（无 review.json）。
基点 HEAD `55bd1d1d4009929a71ca3f7f58eaf9f2e605ba3b`。工作树脏（并发 K/J/N/I ~数百项未提交改动）——
正常，全程只逐文件 add 本任务产物，绝不 `git add -A/.`。

---

## T1 判定（读 `t1-architecture-gate.md`，严格据此执行）

✅ **候选 C（三区同键）成立**，无需退候选 B，无需退候选 A。
- 受管表 `明细表L5-2`、科目 2701、`amount_kind=balance`（负债期末=期初+贷-借）。
- 三区 `RowTableSheetSpec`：售后租回 R11:15（footer 16）/ 分期付款 R18:22（footer 23）/ 「…」R24:24（footer 25=合计）。
- 共享 `store_item_id='L5-L5-2-rows'`，`row_section_field='section'`，values `saleLeaseback`/`installment`/`other`。
- 三区 UUID 列最终选位 **AD / AE / AF**（R11~R25 全空坐实；AD 是物理 max_col=30 最后一列、数据区已空）。
- 公式列 `("E","L","M","N","O","R","S")` 全 11 输入行同形，无跨行派生异形、无裸 IF（bare_IF=0）。
- 账龄 `AgingLayout.flat` 单组 5 桶 T~X；叶子标签用模板全角字符（`１～2年` 的 `～` 全角、`２～3年` 的 `２` 全角）。
- 小计 R16/R23 + 合计 R25（`=SUM(B16,B23,B24)` 非连续枚举 SUM）+ 标题 A10/A17 作静态骨架（`is_template_skeleton_identity`）。
- L5-3 的 A 列 `='明细表L5-2'!A{n}` 镜像引用须在真 OO 往返专门断言不被打坏。

**架构落地选择**：L5 provider 的 identity/契约/发布/attach 委派 `phase5_l_cycle_common`（照 L7），
但 store 投影/合并/迭代走 **G9 式三区门面**（照 `phase5_g9_store_facade`），契约 `html_store` 的
`row_section_field`/`row_section_values` 经 `extra_review` 带出（`l_cycle_common` 的单 item_id 形态保留）。

---

## 本轮改动文件清单（随实施更新）

（见文件末尾「提交」节的 commit --stat）

## 验证结果

### T2 前端行身份 + HTML 列（方案 b）✅
- `useL5Detail.ts`：`key` 生成器换 `newRowIdentity('l52det')`（addRow 走 `createL5DetailRow`、hydrate 补铸缺 key/缺 section）；
  `L5DetailRow` 加 roll-forward 受管字段（B..S + 账龄 T~X 5 桶）+ `section` 字段；
  融资属性列 + HTML 旧标量 13 键导出为 `L5_HTML_ONLY_KEYS`；导出 `createL5DetailRow`/`L5_SECTION_SALE_LEASEBACK`。
- **vitest** `useL5Detail.rowIdentity.spec.ts` **6 passed**（key 前缀/唯一 + 新字段默认值全 0 + section 归属 +
  删中间行身份不漂 + hydrate 补铸/保留/落默认区 + html_only 键清单）。
- **限定范围 vue-tsc**（`tsconfig._l5-dual-mode.json`）：我改的 `useL5Detail.ts` 无类型错；
  **变异证明**注入 `const _mutationProbe: number = 'string'` → `useL5Detail.ts(143,7): error TS2322`（检查生效），已移除。
- 残留两条错在 `GtL5LongTermPayables.vue`（L47 `:schema` on GtAProgramConsole、L125 `:sheet-name=props.sheetName`）
  —— 均**预存**（原 L5 host 逐字已有，L7/L8 host 同形），非本轮引入；我新增的 OO 块用 `props.sheetName || 'L5A'`（string）无错。

### T3 host 双模式切换器 ✅
- `GtL5LongTermPayables.vue`：L5A 程序表加 `isProcedureSheet`(currentSheet==='L5A') + `procedureDualMode`
  (`useCycleHtmlOoDualMode`，storagePrefix `'l5-proc:'`) + el-segmented 工具栏 + `GtEntrySyncCapabilityNotice
  entry-id="xlsx/gt-l5-long-term-payables"` + OO不可用 tag + OO 挂载块（`v-if isProcedureSheet &&
  currentMode==='onlyoffice'`，sheet-name `props.sheetName||'L5A'`）+ `.l5-procedure-toolbar` CSS；
  原 L5TabIndex `v-if` → `v-else-if`；GtAProgramConsole HTML 分支保留；v-else 兜底保留。
- v-if/v-else 链核：OO 块(`v-if`) → L5TabIndex(`v-else-if 'L5'`) → L5A(`v-else-if 'L5A'`) → …子表 → `v-else` 兜底，链不断。
- dev server 未起 ⇒ 浏览器实测**未做（如实标：未实测）**。

### T4 provider + 三处注册 + 裁决表 + 测试 ✅
- 新建 `phase5_l5_sheets.py`（三区 RowTableSheetSpec R11:15/R18:22/R24:24，共享 store_item_id L5-L5-2-rows，
  uuid AD/AE/AF + template_id L52R1/R2/R3 + footer 16/23/25 + section saleLeaseback/installment/other，
  formula_columns E/L/M/N/O/R/S，aging_layout flat + AGING_GROUPS_L52 5 桶，header 8/9）+
  `phase5_l5_long_term_payables.py`（委派 phase5_l_cycle_common；SPECS=三区；derived_readonly_sheet 审定表L5-1；
  extra_review 登记 row_sections + 静态骨架 + flat 账龄 + L5-3 镜像依赖；attach_adapters 覆盖补区②③ sibling binding）+
  `phase5_l5_store_facade.py`（三区门面 build/merge/iter/split）。
- 契约 `l5.long_term_payables.json` 由 provider 生成（canonical_digest `143dfb02…`），`--check` 报 `[check] OK`（disk==source）。
- 三处注册（registry 白名单第八条 / delivered_contracts_ledger L 第八条 / store_item_registry L5 条，均 L 块末尾追加）
  + 裁决表（fix_l_cycle_wp_code_adjudication.py 加 L5 条 wp_codes=["L5"]，--apply 后 57 条、digest `9c0322f5…`）
  + 生成器 `_PROVIDERS` 加 `_l5`。
- **pytest** `test_l5_adapter_registration.py` + `test_l7_adapter_registration.py` + `test_l_cycle_common.py` **56 passed**
  （三区几何 + 三 UUID 空 + 7 公式列同形含 R24 单格 + flat 账龄 5 桶全角标签 + 受管表 0 裸 IF/整册 12 +
  三区门面 iter/split/projection + 契约 3 tables/1 sheet + html_store 单 item + section 声明 + 配对不变式 L 域 8==8 +
  裁决表 wp_codes=["L5"] + HTML 对齐 + 真库命名空间）。L7/l_cycle_common **未回归**。

### 🔴 用户裁决 A（2026-10-02）：三区 → 两区（R24 其他段作模板静态骨架）

现查坐实 R24「其他」段是模板预留占位续行、非业务行：
1. **真库**：`L5-L5-2-rows` 0 行，`remark` 全库无 `section`/`saleLeaseback`/`installment` 任何痕迹（0 命中）；
   L5-% 的 7 行是 canary 夹具（L5-adj/note/conclusion），无 detail-rows。
2. **HTML 侧**：`L5TabDetail`/`useL5Detail` 的展示 segment 是列分组（未审/调整/审定），**无用户可填的「其他」第三数据分组**；
   addRow 新增行落默认区 saleLeaseback。A24='…' 在 HTML 不呈现为可编辑行。
3. **Excel R24**：A24='…'(U+2026) + roll-forward 公式骨架在（E24=B24-C24+D24 … S24），但 B24/C24/D24 输入格全空。
⇒ 典型中文审计「其他……」续行占位。平台 typography 门 BP-21（比幽灵行更硬）对纯省略号占位行 fail-closed。
**走两区（零能力损失）**：受管区 = 区①R11:15 + 区②R18:22（共 10 输入行）；R24 连同小计/合计/标题作模板静态骨架。
不选 B（改模板字节，sanitize 不该改内容）/ C（放宽平台 BP-21 有意防护，禁）。

provider 从三区改两区：删区③ SPEC；保留 R1/R2（uuid AD/AE、template_id L52R1/R2、footer 16/23）；
AF 不用；section 枚举去 other（前端 `L5DetailSection` 类型保留 other 但无行用它）。
T1/report「三区」结论**勘误**为「两区 + R24 占位静态」（登记在 provider docstring + verification-note；
历史档案 append-only，不回填改写 T1 文件本体）。契约重生成（digest `143dfb02…`→`8a9e89f2…`）、测试改两区断言、
provision 的 inert 三区产物由两区版重新 provision 覆盖。

### T5 五环发布（真库 Docker up）✅

Docker 已 up（audit-postgres / audit-onlyoffice healthy / audit-redis healthy，无需启 Docker Desktop）。
- 🔴 不带 `--entry` 的全量 `--check` 会撞**预存**空壳 provider `e1-monetary-fund`（缺 publish_pilot_definitions）崩溃，
  与 L5 无关；全程用 `--entry xlsx/gt-l5-long-term-payables` 过滤绕开。
- **接线两处 provider 常量补全（多区 provider 必需，首版发布链实测暴露）**：
  ① `UUID_COL='AD'`（主区）—— `_observe_identity_inventory` 的 fallback 读 `provider.UUID_COL`（因
     `getattr(spec,'uuid_column',None)` 恒 None，字段名是 uuid_col），缺它 identity inventory 的
     uuid_column_letter 落 None、`resolved_sheet_by` 恒 None（照 L7 的 UUID_COL）。
  ② `ROWS_TABLE_KEY='long_term_payable_rows_r1'`（主表）—— `_row_identity_table_key` 对多表 candidates
     要求 provider 声明主表，其余走 sibling_bindings。
  两者都是 provider 常量、**不进契约 payload**（digest `8a9e89f2…` 不变）。
- **task76 provision（两区版）** `--apply`：definition_artifact 166→168、definition_bundle 50→51、created 3、errors=[]。
- **first publication** `--check`：**state=ready_to_publish、stages 10/10 全过**（adapter_built / projection_composed /
  materialized / roundtrip_verified / unmanaged_regions_verified 全通过），projection row_keys 覆盖两区
  r1/r2、空 projection 首版合法。`--apply`：revision=1、representation_generation=1。
- **DB 确认（不看退出码）**：
  - entry_state：L5 generation=1、wp_id `4b3ec8ff`、adapter_id `l5.long_term_payables`、
    definition_bundle_id `d4d480d6`。
  - content_version_id `123f8f28`、representation_id `651e97b3`、artifact_sha `9b5b0a0f…`、projection_sha `44a69a27…`。
  - 物化日志 `single_pass binding=2`（两区 binding 均活）。
  - L5 载荷：`L5-L5-2-rows` 0 行、L5-% 7 行不变（发布不写载荷）。

### T6 overlay + 干净 worktree 翻 manifest ✅
- 主树 overlay 追加 1 条 L5 override（GtL5LongTermPayables.vue→l5.long_term_payables、bidirectional/
  adapter_registered、html_store=L5-L5-2-rows）；git diff 仅该条新增（14 insert / 1 delete，无并发条目触碰）。
- 干净 worktree `.worktrees/l5-flip`（临时分支 `work/2026-10-02-l5-flip`，基于 55bd1d1d4 只叠加 L5 host+overlay，
  node_modules 经 junction 指向主树供 discover-mounts 用）：approved_source_digest `f85f682e…`→`b165847f…`。
- **mount-diff 零能力损失复核**：entry 155→155、**唯一翻转=L5**（single_onlyoffice→bidirectional /
  legacy_fake_bidirectional→adapter_registered / adapter_id None→l5.long_term_payables / mount 1→2）、changed=1、
  byComponent 仅 GtOnlyOfficeSheet 243→244、capability bidirectional 19→20 / single_onlyoffice 130→129、
  mount_count 249→250、host_count 154 不变。无预期外翻转。
- **legacy baseline diff**：唯一变化=L5（missing_adapter true→false / mode_switch_visible false→true /
  migration_state 翻 / evidence 记 3 条 dual-mode 证据）+ 顶层 digest/missing_adapter_count 123→122。其它 entry 零改动。
- worktree 内 `test_task73_entry_profile_manifest.py` **46 passed**。回拷主树后 `L5.manifest_capability_enabled()==True`、
  `assert_manifest_capability_enabled()` 不抛。详见 `l5-flip-diff.md`。
- 清理：worktree + 临时分支 + node_modules junction 已删（主树 node_modules 完好）。

### 🔴 平台 observer 根因修复（用户裁决 A + 方案 (i)，2026-10-02）

L5 两区同键首次真实翻 manifest 并走到 `observe_published_frozen_definitions` → `_build_identity_binding`，
暴露平台 observer 对「同一 sheet_key 多张 row_identity 表」只用 sheet_key 消歧、无法选主表的缺口
（G9 范式 `manifest_capability_enabled()==False`、从未翻、此路径从未被运行过）。按用户裁决修**平台 observer**：
- 改 `published_identity_observer.PublishedIdentityObserver._build_identity_binding`：新增 `elif len(matched)>1`
  分支，用冻结 `anchors['table_name']`（sheet_anchors[0]=主区 Excel Table 名）对齐 **provider
  `managed_row_table_specs()`**（方案 (i)，不动契约解析器/零 golden digest 风险，沿用 H attach 侧既有的
  observer→provider 依赖模式）选主区 table_key，其余走 sibling（observer 本就只返主 binding）。
- 新增 `_primary_table_key_by_frozen_table_name`（table_name 对齐 + fail-closed：命中≠1 则抛）+
  `_resolve_provider_for_contract`（按 contract_id 经 STORE_MERGE_REGISTRY.provider_module 解析，不读 registry alias）。
- 🔴 **单表 / 多 sheet 既有分支一字不动**；只在同 sheet_key matched>1 时走新消歧；消歧后仍不唯一照旧 fail-closed。
- **变异证明**（`test_l5_adapter_registration.TestObserverSameSheetKeyDisambiguation` 6 例）：
  主区 R1 正确选中 + 冻结锚点换 R2 则选 R2（非写死第一张）+ table_name 对不上任何一张 fail-closed（match「消歧命中 0 张」）+
  冻结 table_name 空 fail-closed（match「anchors['table_name']」）+ provider 解析映射正确。
- **G9 回归确认**：G9 `manifest_capability_enabled()==False`、真库无 entry_state、不走 observer 路径 ⇒ 不受影响
  （将来翻 manifest 直接受益）。全仓同 sheet_key 多区 entry 当前真实命中仅 L5（G9 未翻不算）。
- 🔴 **observer 是平台级共享文件（非 L5 专属）**：本次改了 `_build_identity_binding` 消歧，受影响面见上，
  review 须专门核这条（与 L5 产物同 commit，是 L5 真实命中逼出的根因修复）。

### T7 真 OO 往返 + 回归归因 + 提交 ✅

写了 `verify_l5_oo94_roundtrip.py`（两区 + key + section + 账龄 + 静态骨架 + L5-3 镜像 + 不写库）。
真 OO 往返 **9 步 + 3 专项断言全绿（退出码 0）**：
- `[①]` attach=('l5.long_term_payables',)（observer 消歧修复后通）
- `[②]` generation=1 substrate `9b5b0a0f`
- `[③]` projection values=34 rows=2（两区各 1 行）
- `[④]` materialize（两区新身份作 orphan 插入，静态骨架合法下移、footer SUM 按插行重归一化）
- `[⑤]` OO ConvertService xlsx→xlsx percent=100
- `[⑥]` extract + G1 等值门 OK
- `[⑦]` L5-L5-2-rows 往返逐字段相等（2 行，两区 section 对齐，key 稳定，无幽灵行）
- `[⑧]` 受管行 [16,24] 七列公式 E/L/M/N/O/R/S 14 格全是公式
- `[⑧a]` 静态骨架幸存（标题 R10/R18 + 小计 R[17,25] + 合计 R27 + R26『…』占位续行；SUM/roll-forward 公式形态原样，
  随插行合法重归一化——按标签/形态定位，不假设固定行号）
- `[⑧b]` 账龄桶 T~X editable 往返正确（R16 的 5 桶值回写）
- `[⑧c]` 🔴 L5-3 的 A 列 `='明细表L5-2'!A{n}` 镜像引用未被打坏（12 格仍是原样跨 sheet 引用公式——
  L5-2 materialize 不损坏 L5-3 既有镜像公式；L5-3 全链路对齐是后续 spec）
- `[⑨]` L5 载荷 7 行不变（不写库）

**回归归因（git stash 分预存红 vs 本任务红）**：
- `test_l5_adapter_registration.py`（含 6 例 observer 消歧变异证明）**32 passed**。
- 观测器修复零回归：`test_task75_published_identity_observer.py` **本任务改动在场 vs 临时移除两种状态下 54 failed 逐一
  完全相同**（with=54failed/357passed，without=54failed/330passed，Compare-Object 判 FAILED 集合 IDENTICAL）⇒ 这 54 条是
  并发 J/N/K 会话 + 预存 e1 空壳的预存红，本 observer 改动**引入零新失败**（反而让 27 条额外通过）。
- `test_task73_entry_profile_manifest.py` 主树 8 failed：git stash 掉本任务 host+manifest+overlay 后**同样 8 failed**
  （J1 provenance `GtJ1EmployeeCompensation.vue#L17` + sourceDigest 漂移 `f85f682e vs c4eda55e`）⇒ 并发 J1/N4 未提交 host 编辑所致，
  非本任务。本任务的 manifest/overlay 在**干净 worktree（HEAD+仅 L5）task73 46 passed** 已证正确。
- L5/L7/l_cycle_common/row_table_sheet 相关套件：95 passed（除 task73 的 8 条并发红）。

写了 `verify_l5_oo94_roundtrip.py`（两区 + key + section + 账龄 + 静态骨架 + L5-3 镜像 + 不写库）。真 OO 往返链路在
**步骤 ① attach** 即停：`FrozenChildUnusableError: 契约声明了 2 张带 row_identity 的表
['long_term_payable_rows_r1','long_term_payable_rows_r2']，但一 sheet 锚点 'l52-managed' 未能唯一对齐
（匹配 ['long_term_payable_rows_r1','long_term_payable_rows_r2']）—— 不得随手挑第一张`。

**根因（现算坐实）**：`published_identity_observer._build_identity_binding` 对「同一 sheet_key 下多张
row_identity 表」只用 **sheet_key 对齐**选主表（`matched=[t for s,t in row_tables if s==primary_sheet]`）。
两区共享 `sheet_key='l52-managed'` ⇒ `matched` 恒为 2 张 ⇒ fail-closed「不得随手挑第一张」。
`anchors = sheet_anchors[0]` 已是主区 R1（table_name `GT_L52_..._R1`、uuid AD），但该函数**不用 table_name/uuid
去消歧**，只用 sheet_key。

🔴🔴 **这是 L5 首次真实触达的未被运行过的引擎路径**：现查 **G9（唯一同键三区范式）`manifest_capability_enabled()==False`、
真库无 entry_state** —— G9 provider/契约层建了同键多区，但**从未翻 manifest、从未经 attach 的 observer 路径**
（`attach_pilot_adapters` 因 capability 非 bidirectional 早退返 `()`）。所以 `_build_identity_binding` 的
「同 sheet_key 多表消歧」从未被真实行使过。L5 是**第一条真正翻 manifest 并走到 observe_published_frozen_definitions
的同键多区 entry**，暴露了这个平台级 observer 的 sheet_key 消歧不足。

**这不是 L5 provider 的接线问题**（first publication 已 10/10 全过、provision/manifest 翻转全成立）；
`attach` 侧我已照 H 范式补了区②的 sibling_bindings；缺的是 observer **选主表** 这一步在同 sheet_key 下无法消歧。

**拟修（平台 observer，blast radius = 所有同键多区 entry，但当前仅 L5 一条真实命中）**：
`_build_identity_binding` 当 `matched`（按 sheet_key）>1 时，用冻结锚点 `anchors['table_name']`（主区 Excel Table 名
= `GT_<TID>_<TABLE_KEY_R1>`）与各 row_table 的 provider spec 的 `table_name` 精确对齐选主表，其余走 sibling
（observer 只返主 binding，sibling 由 attach 另传，机制已在）。等价于把「D4-2+D4-3 多 **sheet** 用 sheet_key 消歧」
扩展到「同 sheet 多 **区** 用 table_name 消歧」。纯增量：单表 / 多 sheet 既有分支不变，只给「同 sheet_key 多表」
加一条按 table_name 的消歧，并保「仍不唯一就 fail-closed」。

因该修改触碰**跨 entry 共享的平台 observer**（高 blast radius），已 `send_message severity=warning` 报用户裁决：
修平台 observer（推荐，根因修复）vs 其它路径。未裁决前不改 observer、不提交、不 push。
T2/T3/T4/T5/T6 全部成立且已验证（见上）；仅 T7 真 OO 往返卡在此 observer 消歧。

### T6 overlay + 干净 worktree 翻 manifest
- [ ] 翻转范围（只 L5）+ mount-diff 零能力损失 + baseline diff

### T7 真 OO 往返 + 回归归因 + 提交
- [ ] 9 步 + 专项断言（三区 section / 账龄 / 公式幸存 / 小计标题骨架 / L5-3 镜像）
- [ ] 回归归因（预存红 vs 本任务红）+ commit hash
