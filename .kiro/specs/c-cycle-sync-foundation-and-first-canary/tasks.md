# C 循环双向回写地基与首张 canary — 任务

> 判据引用规则：本文件裁定 CC-1 ~ CC-68，lane spec 只引用编号。
> `[ ]*` = 外部依赖阻塞，不可在本轮标 completed。

## 阶段 1：域切分与归属基线

- [ ] 1. 建 C 域基线守卫 `backend/tests/workpaper_sync/test_c_cycle_baseline.py`
  - 断言 C 域 in-scope entry 恰 **2** 条：`xlsx/gt-c-control-test` 与 `xlsx/gt-c22-itgc-bundle`
  - 🔴 断言按 `wp_code_patterns` 首字母切域只得 **1** 条，会漏主体（CC-1 反转证据）
  - 断言两条 `migration_state` 均为 `legacy_fake_bidirectional`、`capability` 均为 `null`
  - _判据：CC-1、CC-43_

- [ ] 2. `pattern_less` 归属裁决落成断言（CC-68）
  - 用 override 表（`backend/app/data/wp_code_overrides.json`，**1526** 条）反查 componentType
  - 断言 5 条反查结果：`c-control-test` **28** · `c22-itgc-bundle` **1** · `a-program-console` **32** · `cf-verification` **1** · `custom` **0**
  - 🔴 断言 `xlsx/cash-flow-verification` 反查得 **`A5`** ⇒ 属 A 域，**A 轮遗漏**（只登记缺口不在本轮修）
  - 断言另 3 条（`gt-custom-wp-editor` / `gt-wp-renderer` / `shared/cycle-standalone-procedure-shell`）留独立一轮，各带排除理由
  - 🔴 断言这是 B 轮 BC-45「多 entry 共用一 wp_code」的**对偶再翻转**：C 域是**一 componentType 覆盖 28 个 wp_code**（CC-45）
  - _判据：CC-68、CC-61、CC-45_

- [ ] 3. 两条 entry 形态对照断言（CC-2）
  - 断言 design.md §1.1 的 **14** 个维度逐项相反
  - 断言载体二分各 1 条，其一为 `no_carrier` + `no_switch_at_all`
  - 断言 C22 的 BP 为 **8** 项且含 **BP-10**；另一条 **7** 项
  - _判据：CC-2、CC-43_

- [ ] 4. strict 域口径（CC-57、CC-5）
  - 🔴 断言 `^GtC\d` 得 **8** 个但只含本轮 **1** 条 ⇒ **会漏主体**
  - 断言 `^GtC` 后非数字得 **32** 个，含本轮主体 `GtCControlTest.vue`
  - 断言正则须扩为 `^GtC\d` ∪ `^GtC[A-Z]`
  - 断言小写 `Gtc` 为 **0**（空分母，配变异证明）
  - 断言非 Gt 前缀含 C 码 **10** 个（`C23*` / `C24*` 子表组件）属排除
  - 断言 `^GtC\d` 域内未纳入本轮 **7** 个各带排除理由
  - _判据：CC-57、CC-5、CC-20_

- [ ] 5. 空分母清册 + 变异证明（CC-20，覆盖全部 ❌ 判定条）
  - 逐项断言 design.md §五 的 **17** 项结构性零，每项配人造正样本变异测试
  - 逐条落断言：confirm 0（CC-4）· 小写前缀 0（CC-5）· removeRow 0（CC-7）· 位置化族 0（CC-8）· `derived_total` 0（CC-14）· localStorage 无 mode 键（CC-16）· 无合计行（CC-17）· 无借贷方向（CC-22）· 无 `SHEET_MAP`（CC-23）· 无「原底稿/历史」（CC-24 / CC-27）· slice 无 `transport_key_resolution`（CC-30）· `parent_duplicate` 0（CC-31）· prefill 0（CC-37）· 无 docx（CC-38 / CC-39）· 无除零形态（CC-40）· 解析零失败（CC-46 / CC-50 / CC-51 / CC-52）· Property 22 零站点（CC-48）· 无 xlsm（CC-49）· count 键 0（CC-54）· 无位置化编号基准（CC-56）· 无共享载体（CC-58）
  - 另断言两项 ✅ 沿用的零分母：`GtEntrySyncCapabilityNotice` **0**（CC-12，tooltip 不计作 notice 接线）· `resolveProcedureSheetKey` 宿主内 **0**（CC-28，A / B / C 三轮同态）
  - _判据：CC-20、CC-4、CC-5、CC-7、CC-8、CC-12、CC-14、CC-16、CC-17、CC-22、CC-23、CC-24、CC-27、CC-28、CC-30、CC-31、CC-37、CC-38、CC-39、CC-40、CC-46、CC-48、CC-49、CC-50、CC-51、CC-52、CC-54、CC-56、CC-58_

## 阶段 2：模板层判据

- [ ] 6. 目录册对账与归属（CC-29、CC-44）
  - 断言 `backend/wp_templates/C` = **36** 本，**100% `.xlsx`**（唯一纯 xlsx 域），锁文件 0，无子目录
  - 断言与 AD-3 声明 `{"C": {"xlsx": 36}}` 逐值吻合
  - 断言本轮 entry 覆盖 **29** 本；排除 **7** 本各带理由（`C1` / `C21` / `C21-1` / `C23` / `C24` / `C25` / `C26`）
  - 🔴 断言 `C25 利用内审工作.xlsx` 有 `definedName` **219 / broken 164** 但公式格 **0**（有断链无公式）
  - _判据：CC-29、CC-44_

- [ ] 7. 成对册缺陷不对称（CC-21、CC-62）
  - 断言主册 `C{n}`（14 本）：公式格 12 · 裸 IF **0** · `definedName` **0 / 0** · 超列 0 · max_col 18
  - 断言 `-2` 册（14 本）：公式格 20 · 裸 IF **20（100%）** · `definedName` **232 / broken 181（78%）** · 超列 1 · max_col 9（`C6-2`/`C7-2` 为 6）
  - 🔴 断言 14 本 `-2` 册六项指标**逐值一致** ⇒ 同模板复制 14 份
  - _判据：CC-21、CC-62_

- [ ] 8. `definedName` 断链登记（CC-9）
  - 断言全域 **3514 / broken 2727 = 77.6%**（历轮最高，A 轮 A3-3 为 261/190 = 73%）
  - 🔴 断言验算闭合：`-2` 册 181 × 14 = 2534 + `C21` 14 + `C24` 15 + `C25` 164 = **2727** ✓
  - _判据：CC-9_

- [ ] 9. 超列引用分族核验（CC-32）
  - 断言全域 **113** 处；其中 `C24`（排除册）**99** 处、本轮 `-2` 册族 **14** 处（每本 1 处）
  - 🔴 口径须先剔引号段与中文 sheet 名 `!` 段（承 N 轮 NC-32 教训）
  - _判据：CC-32_

- [ ] 10. 幽灵行与遍历上界（CC-35）
  - 断言本轮册最大 ghost **22 行**（`C1` 册，属排除册）；本轮 29 本内最大 ghost **16 行**
  - 🔴 断言域内 `C24`（排除册）ghost 达 **10141 行** ⇒ 遍历上界必须取 `last_value_row`
  - 断言 hidden sheet 全域 **5** 个，含 `GT_Custom` **4** 与 `2025假期清单` 1（年份硬编码）
  - _判据：CC-35_

- [ ] 11. footer 与 sheet 名脏形态（CC-36、CC-10、CC-26、CC-67）
  - footer 读 raw XML（禁用 openpyxl）：三态 = 无容器 **84** + 有内容 **72** + 有容器无 `oddFooter` **8** = **164** ✓ 与 sheets 总数吻合
  - 断言内容形态**只 1 种** `&C&P/&N`（与 B 域一致，与 A 域中英双语并存不同）
  - 断言 164 sheets / **121** 个不同名
  - 🔴 断言参考型 sheet **3** 种共 **40** sheets 须排除：`选项清单列表（不归档）` 14 · `示例-评价控制偏差（不打印）` 14 · `选项清单列表（不归档） (2)` 12
  - 🔴 断言 `选项清单列表（不归档） (2)` **同一名内全角与半角括号混用** ⇒ 禁归一化
  - 断言册名脏形态唯一 1 处：`C21-1  IT审计发现汇总表.xlsx` 两个连续空格
  - 断言 sheet 名前导/尾随空格 **0** · 跨循环码 **0** · 「原底稿/历史」**0**（各配变异证明）
  - _判据：CC-36、CC-10、CC-26、CC-67、CC-20_

- [ ] 12. 一码一册与解析全中（CC-50、CC-52、CC-46）
  - 断言一码多册 **0** 组（B 域 6 组、B22A 11 本 ⇒ C 域空分母）
  - 断言 29 码解析 **29 / 29 全中**（权威 finder = `backend/app/services/wp_template_finder.py`）
  - 断言唯一解析失败是 manifest pattern **`C22I` → None**
  - 断言数据验证扩展警告 **0 / 36** 本（B 域 16 / 66）
  - _判据：CC-50、CC-52、CC-46、CC-49_

## 阶段 3：口径判据落地

- [ ] 13. 门控扫描器与 slice 双向对账（CC-13、CC-11）
  - 实现祖先链 × 递归 v-if/v-else 链头回溯口径
  - 断言 `gt-c-control-test` seg **1** / oo **1** / gated **1** / radio **0**
  - 断言 `gt-c22-itgc-bundle` seg **0** / oo **1** / gated **0** / radio **0**（印证 `no_switch_at_all`）
  - 🔴 断言仅自身口径 gated 得 **0** ⇒ 假阴 **1**
  - 🔴 双向对账：独立 DOM 扫描须与 slice `ui_toolbar_gate.{segmented_sites, oo_mount_sites, mode_gated_oo_mount_sites, mode_radio_sites}` **四项逐值一致**（本轮已验证全中）
  - _判据：CC-13、CC-11_

- [ ] 14. 行身份扫描器（CC-53，🔴 禁照抄 B 轮）
  - 新建 `audit-platform/frontend/src/components/workpaper/__tests__/cCycleRowIdentity.spec.ts`
  - 实现两类判定：类 A（`idx` 进 `item_id` 构造或持久化键）= 缺陷 · 类 B（`idx` 仅内存数组 / `splice` / 弹窗参数 / Dialog 标题插值）= 非缺陷
  - 断言 C 域 `idx` 形参 **14** 处**全属类 B**
  - 🔴 断言三项证据全为 0：`item_id` 模板串含 `idx` **0** · `item_id` 赋值含 `idx` **0** · `useCControlTestData.ts`（168 行）内 `idx`/`index` **0**
  - 断言 slice 判 `c_control_test_step_rows` 为 **CLEAN** 且 `identity_field` = `num`、`registered_as` = `[]`
  - 🔴 双向变异测试：B 域样本（`idx` 进键）应命中、C 域样本（`idx` 仅 UI）应不命中
  - 断言 N 族 / M 式 / `rowIndex` 形参 / `$index` / 熵键 / label 作 key 全为 **0**（各配变异证明）
  - _判据：CC-53、CC-8、CC-6、CC-11_

- [ ] 15. `item_id` 命名轴双体系（CC-15、CC-27 边界）
  - 断言 `gt-c-control-test` 用**连字符**三段式：`C{n}-{ctrl|sum|dev}-{序号}-{字段}` + `C{n}-cycle-conclusion`
  - 断言 `ctrl` 层 **11** 字段 · `dev` 层真库可见 **5** 步（step1~4 + step6）
  - 🔴 断言 `gt-c22-itgc-bundle` 用**点号**：`C22.{controlId}.{field}`（由 `itgcItemId()` 构造）
  - 🔴 断言 `GtC22ControlSheet.vue`（排除组件）与本轮 C22 **共用同一命名空间**（注释明写「与子页保持一致」）⇒ 不是冲突而是有意共享
  - 断言序号是 **1-based 业务控制点号**，非数组下标
  - _判据：CC-15、CC-53_

- [ ] 16. boolean falsy 持久化（CC-65）
  - 断言 `DecisionTreeState`（`useDeviationDecisionTree.ts`，299 行）6 个 step 字段类型不一致
  - 🔴 断言 `step5` 类型为 **`boolean`** 且 `createEmptyState()` 默认 **`false`**，其余 5 个为字符串枚举 + `null`
  - 🔴 断言真库只见 5 步（`step5` 缺席）⇒ 根因是 `false` 被按空值跳过，**非断号缺陷**
  - 判据：修复后须能区分 `undefined`（未填）与 `false`（显式否）
  - _判据：CC-65_

- [ ] 17. mode 值体系与 OCR 通道（CC-41、CC-3）
  - 🔴 断言 `gt-c-control-test` 出现**第四体系** `'online-edit'`（`ref<'structured' | 'online-edit'>(`）
  - 断言 `gt-c22-itgc-bundle` 的 mode 比较字面量 **0** + `ref<泛型>` **0** ⇒ 完全无 mode 概念
  - 断言两条**都未在宿主内声明 `modeOptions`**
  - 🔴 断言 OCR 通道 **CODE 75 / CMT 26**（`GtCControlTest.vue`）是 C 域最大通道，与 `attachment_and_ocr` family 吻合
  - 断言 `/checklist-responses` CODE **1**（C22 宿主内直调）· `docx|word` 2
  - _判据：CC-41、CC-3_

- [ ] 18. 持久化闭包深度 3（CC-42）
  - 断言 `gt-c-control-test` 闭包 **35** 册，`checklist-responses` 在 **D1**（`useCControlTestData.ts`）
  - 断言 `gt-c22-itgc-bundle` 闭包 **8** 册，`checklist-responses` 在 **D0**（宿主内直调）
  - 断言 `field-overrides` / `custom-cells` / `publish-to-tb` 在深度 3 内两条全 **0**
  - 断言 localStorage 在 D2 / D3（`auth.ts`），无 mode 分区键
  - _判据：CC-42、CC-16_

- [ ] 19. 真库分母与双列均衡（CC-34、CC-60、CC-19）
  - 断言本轮 4 组各 **34** 行，合计 **136**；remark 非空 **8** / conclusion 非空 **10**
  - 🔴 断言这是**双列均衡第三态**（轨迹：N/A 悬殊 conclusion 主 23:4 / 24:4 → B 反转 remark 强 17:1 → **C 均衡 10:8**）⇒ 契约**两列都必须映射**
  - 🔴 断言 28 码中只 **4 个循环**有载荷，其余 **10 个循环**与全部 14 个 `-2` 码真库为 **0**
  - 断言 `C22` 真库 **0** 行
  - 断言跨 entry 污染 **0**（7 组 item_id 前缀与 wp_code 全对齐）
  - 断言 `wp_index` 中 29 码**全存在且全 n = 4**
  - _判据：CC-34、CC-60、CC-19、CC-55_

- [ ] 20. 域内单册体量离群登记（CC-66）
  - 🔴 断言 `C24`（排除册）真库 **1,033,309** 行 = 全表 `checklist_responses`（**1,034,702**）的 **99.87%**
  - 断言该事实是「JOIN `checklist_responses` 查询超时」的根因 ⇒ 后续查询须避免全表 JOIN 或加 `wp_id` 过滤
  - 断言本轮 entry 只占 **136** 行 ⇒ 本轮判据不受该离群册影响
  - _判据：CC-66_

## 阶段 4：首张 canary

- [ ] 21. canary 事实锁定（`xlsx/gt-c-control-test`）
  - 断言真库 136 行 / 4 个 wp 实例 / remark 8 / conclusion 10
  - 🔴 断言载荷是**真实审计业务文本**（`C14-dev-1-exceptionDesc` 为 118 B 中文实录）⇒ 非预置参考文本、非 seed
  - 断言与 B 轮 BC-59 的差异：C 轮**不需要**「用空白新增行做变异」的绕道
  - 断言这是**第三次收回硬标准**（五轮轨迹须一并写明）
  - _判据：CC-18、CC-59_

- [ ] 22. canary 改线：28 码全覆盖（CC-61）
  - 🔴 一次改线须覆盖 **28** 个 wp_code，不得只处理 1 个（AD-9 明文警告会漏 27 个）
  - 判据按主册族（14）与 `-2` 册族（14）**分别断言**
  - sheet 名表达式 `sheetName || ''` 改为经权威源解析
  - _判据：CC-61、CC-62_

- [ ] 23. canary 双向读写一致性
  - 结构化视图与 OO 视图读同一权威源
  - OO 侧写入后切回结构化视图能反映写入结果（非缓存快照）
  - 🔴 保留 `step.num` 业务键行身份，不得改为下标
  - 🔴 不得破坏 OCR 文本与附件的行关联（OCR 是 C 域最大通道）
  - 变异证明直接对现有真实业务行做（依据 CC-59）
  - _判据：CC-18、CC-53、CC-3_

- [ ] 24. canary 回滚路径
  - `capability` 可从 `bidirectional` 退回 `null` 且不留脏数据
  - 断言既存守卫中 `gt-c-control-test` 1 处 / `c-control-test` 7 处断言保持通过
  - _判据：CC-2_

## 阶段 5：边界与缺口登记

- [ ] 25. 归档 spec 边界与欠账（CC-25）
  - 断言真 C 域归档 **7** 份，其中 **6** 份 100%（`c-control-test-popup-enhance` 14/14 · `c-control-test-refresh` 8/8 · `c1-entity-level-control` 7/7 · `c22-itgc-bundle` 8/8 · `c23-c24-journal-entry-testing` 8/8 · `c25-c26-internal-audit-info-control` 7/7）
  - 🔴 断言 **`c-control-test-component` 25 / 53（欠 28 条）= 历轮最大单份欠账**
  - 🔴 已归档 spec **一律不回填修改**（append-only），勘误只登记在本 spec
  - _判据：CC-25_

- [ ] 26. slice 一致性核验（CC-47、CC-33）
  - 断言 AD-9 声明值与 override 反查**逐值吻合**（`c-control-test` 28 · `a-program-console` 32）
  - 断言 AD-1 明文警告「照抄单字母规则会漏这 5 条」已被本轮采纳
  - 断言 `a-program-console` 的 32 码横跨 **B / F / G / H / K / L / S** 七个字母 + **2 个中文码**（`函证程序表E0A` / `函证程序表F0A`）
  - slice schema 校验器走追加节（同 A、B 两轮处置）
  - _判据：CC-47、CC-33、CC-68_

- [ ] 27. 既存守卫覆盖缺口登记（CC-2）
  - 断言 `test_task57_abcs_and_shared_migration.py`（2471 行 / 17 类 / 130 test）对 C 域覆盖极不均
  - 🔴 断言 `gt-c22` / `c22-itgc` / `C22I` / `itgc` / `GRP-06` / `GRP-07` / `control_test_router` **全 0 命中** ⇒ **C22 零断言**
  - 断言 `gt-c-control-test` **1** 处 / `c-control-test` **7** 处
  - _判据：CC-2、CC-43_

- [ ] 28. A 轮遗漏缺口登记（CC-68）
  - 🔴 断言 `xlsx/cash-flow-verification` 经 override 反查得 **`A5`** ⇒ 属 A 域但 A 轮三份 spec 未收
  - 断言该 entry 同时背负 **BP-10**（`no_switch_at_all`，全 slice 仅 4 条之一）
  - 只登记不在本轮修（跨轮次缺口，须由 A 轮补章或独立一轮承接）
  - _判据：CC-68、CC-1_

## 外部依赖（本轮不可标 completed）

- [ ]* 29. BP-1 approved 模型落地 —— C 域两条 entry 共有阻塞
- [ ]* 30. BP-2 contract 定义 —— 同上
- [ ]* 31. BP-3 capability 裁决流程 —— 同上
- [ ]* 32. BP-4 bundle + published representation —— 同上
- [ ]* 33. BP-5 adapter 注册 —— 同上
- [ ]* 34. BP-7 sync 能力接线 —— 同上
- [ ]* 35. BP-8 运行时 sheet 名表达式收口 —— 同上（但 C 域 29 本册可静态归属，不构成实质阻塞）
- [ ]* 36. `-2` 册族 `definedName` broken 181 / 232 的模板层修复 —— 须业务侧重做模板，本轮只登记
- [ ]* 37. C22 真实数据 UAT —— 真库 0 行，待真实项目数据
