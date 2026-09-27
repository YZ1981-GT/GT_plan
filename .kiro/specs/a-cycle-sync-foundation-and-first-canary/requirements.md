# A 循环双向回写地基与首张 canary — 需求

## 引言

**上游**：umbrella Task 57 的 abcs slice（`backend/data/workpaper_sync_abcs_cycle_manifest_slice.json`，**750,744 B**，冻结 2026-08-31）+ 删除清册（27,566 B）+ 既存守卫 `backend/tests/workpaper_sync/test_task57_abcs_and_shared_migration.py`（**2472 行 / 17 类 / 130 test**）+ 前十轮共同裁决 FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / KC-1~24 / LC-1~26 / MC-1~29 / **NC-1~37**。

🔴 **本轮与前十一轮的第一个根本不同：slice 不是单循环的**。`slice_scope.cycle` 现读为 **`"A/B/C/S + cross_cycle_shared"`**（复合值），slice 自身明文警告「任何『cycle 必须是单个大写字母』的判据在本轮必假红」。全 slice **46 条独立 entry**，本系列只做 **A 域 20 条**；B 10 / C 1 / S 10 / pattern_less 5 由后续 B、C、S 轮承接。

**本 spec 的 entry 范围**：`xlsx/gt-a51-cashflow-audit`（**1** 条，canary 所在 entry，沿用 H/I/J/K/L/M/N 七轮既定形态）。

**承接策略**：以 **NC-1~37 为基准逐条重裁**，得 **AC-1 ~ AC-48**（NC 对位 37 条 + A 独有新增 11 条）。判定分布在 `design.md` **逐条数表格得出**，禁凭印象。🔴 本轮 **❌ 不适用 11 条**、**🔁 反转 5 条**，两类**都必须显式声明**。

**既存守卫的边界**：`test_task57_abcs_and_shared_migration.py` 锁「现状诚实记录」，本 spec 锁「改线后目标态」。🔴 **测试类名禁照抄 N**：A 有 **5 个 N 没有的类**（`TestEntryGroupsAreRecomputable` / `TestAc16ConfirmationAdapterReuse` / `TestProperty22DynamicColumnIdentity` / `TestDualModeCarrierInventory` / `TestBusinessModelProjection`）+ **1 个非 Test 前缀的辅助类 `_VueTemplateParser`**；而 **N 有而 A 无** `TestTransportKeyResolution` / `TestOrphanInventory` / `TestSheetGranularityAndRouter`；`TestNCycleFormDifferences` 在 A 改名为 **`TestFormDifferences`**。

🔴 **A 循环另有 35 份已归档 spec**（底稿功能方向，与本系列的 sync 方向正交）：

| 归档区 | spec 数 | 说明 |
|---|---|---|
| `_archive/10-A~S-workpaper-all-cycles-complete/` | **13**（A00 ~ A12） | 合计 **159/159**，但 🔴 **4 份是 0/0**（A00-completion-infra / A02-misstatement-a13 / A03-control-deficiency-a14 —— 有 `tasks.md` 但零编号任务） |
| `_archive/13-2026-06-29-batch/` | **20** | 逐 wp_code 一份；🔴 **6 份未 100% 完成**（见下） |
| `_archive/12-2026-06-23-batch/` | 2 | a13-misstatement-aggregation 35/35 · a17-summary-enhancement 33/33 |

🔴🔴 **与 N 轮（16 份全部 100% done）反转**：A 有 **6 份归档 spec 未完成**，共 **7 条未完成任务**，且这些 entry 正是本轮 A 域的 entry —— `a11-1-subsequent-events-inquiry` **19/21** · `a17-3-1-consultation-execution` **15/16** · `a17-3-consultation-record` **16/17** · `a17-4-disagreement-record` **16/17** · `a17-7-independence-declaration` **20/21** · `a18-2-regulatory-communication` **14/15**。

🔴 另抓到一处平台级编码缺陷：`_archive/07-workpaper-slimdown/report-view-slimdown/tasks.md` **不是 UTF-8**（`read_text(encoding="utf-8")` 抛 `UnicodeDecodeError`）⇒ 任何全归档区扫描须带 `errors="replace"` 容错并登记。

## 术语与口径（先立规矩，后面 Req 直接引用）

- **A 域**：`independent_entries` 中 `wp_code_patterns[0]` 以 `A` 开头的 entry，现算恰 **20** 条。🔴 **禁按 entry_id 里的字母猜域** —— `xlsx/gt-c-control-test` 名字带 `c-control-test` 却因 `wp_code_patterns` 为空数组而归 `pattern_less` 桶。
- **strict 域文件集**：前端 `audit-platform/frontend/src/` 下，路径含 `/a{n}/` 或 `/a{n}-{m}/` 目录段、**或**文件名匹配 `^(?:use|Gt)?A\d`、**或**匹配 `^a\d`（小写）、**或**匹配 `^a\d+-`（componentType 式）——四路取并现算 **148**（生产 **79** / 测试 69）。🔴 **仅用大写分支会漏 34 个**。
- **format 分流**：A 域权威册 **docx 16 / xlsx 2 / 无册 2**。🔴 **对 docx 册禁跑 openpyxl**（实测抛 `InvalidFileException`），须用 `python-docx`；公式格计数对 docx **无意义**。
- **footer 口径**：🔴 **禁用 `ws.oddFooter`** —— openpyxl 对 A 域两本 xlsx 均报 `Cannot parse header or footer so it will be ignored` 并静默返回空。一律读 raw XML（`zipfile` + `xl/worksheets/sheet*.xml` 的 `<oddFooter>`）。
- **mode 门控口径**：🔴 判「OO 挂点有 mode 门控」须 **祖先链 × 递归 v-if/v-else 链头回溯**（详见 Requirement 4）。只看挂点自身属性会假阴 **5** 处。
- **计数现算**：所有数字一律从源现算并与 `design.md` 等值比对。禁写死。
- **判据锚点**：用常量名 / 端点字面量 / 形态特征。🔴 **禁写死行号**。
- **canary**：entry `xlsx/gt-a51-cashflow-audit`，权威册 `A/A5-1 现金流量表审计.xlsx`，wp_code `A5-1`（第二 pattern `A51C`）。

## 需求

### Requirement 1 — entry 边界：四循环合一 slice 里切出 A 域

**用户故事**：作为维护者，我要一眼看清本轮到底做哪 20 条、slice 的 46 条如何分域、以及 slice 自身哪些数字是错的，避免基于错误基数展开。

#### 验收标准

1. WHEN 现算 `independent_entries` THEN 总数 SHALL 为 **46**，按 `wp_code_patterns[0]` 首字母分域 SHALL 为 A **20** / B **10** / C **1** / S **10** / `pattern_less` **5**。
2. WHEN 校验 A 域 20 条 THEN 全名 SHALL 逐一吻合：`xlsx/gt-a101-governance-communication` · `xlsx/gt-a111-subsequent-events-inquiry` · `xlsx/gt-a112-dual-checklist` · `xlsx/gt-a115-disclosure-checklist` · `xlsx/gt-a121-legal-confirmation` · `xlsx/gt-a171-audit-summary` · `xlsx/gt-a1721-kam` · `xlsx/gt-a173-consultation-record` · `xlsx/gt-a1731-consultation-execution` · `xlsx/gt-a174-disagreement-record` · `xlsx/gt-a176-closing-meeting` · `xlsx/gt-a177-independence-declaration` · `xlsx/gt-a181-regulatory-submission` · `xlsx/gt-a182-regulatory-communication` · `xlsx/gt-a271-it-audit-memo` · `xlsx/gt-a3-consolidation-console` · `xlsx/gt-a38-goodwill-impairment` · **`xlsx/gt-a51-cashflow-audit`** · `xlsx/gt-a81-other-info-representation` · `xlsx/gt-a91-deficiency-letter`。
3. 🔴 WHEN 比对 slice 自述 THEN SHALL 登记 **4 处自相矛盾**（两个来源都有错）：`slice_scope.letter_bucket_counts` 说 B **11**（未扣 pilot B60）· `description` 说 C **2** 与跨循环共享 **4**（现算 1 与 5）· `description` 说「5 个持久化通道」而 `entry_groups.counters.channels` = **4**（现算 4 对）· `dual_mode_carrier_inventory` 正文说全域 `*DualMode*.ts` **115** 个而同节字段 `all_dual_mode_modules_in_repo` = **114**。
4. 🔴 WHEN 判定域归属 THEN SHALL 按 `wp_code_patterns` 现算，SHALL NOT 按 entry_id 猜 —— `xlsx/gt-c-control-test` 归 `pattern_less`（其 `wp_code_patterns` 是空数组，`wp_code_pattern_absent_because` 明文写「不得为凑字段编一个码」）。
5. WHEN 现算 pilot 排除 THEN `excluded_pilot_entry_count` SHALL 为 **1**（`xlsx/b60/gt-b60-bundle`），🔴 这是**前十一轮里首次非 0**。
6. WHEN 现算 `in_scope_parent_duplicate_count` THEN SHALL 为 **0** ⇒ `parent_duplicate_summary` 条件节**不触发**（与 K/L/M 同形、🔴 **与 N 轮相反** —— N 那轮触发并写了完整节，照抄必假红）。全量 manifest 的 43 条 parent_duplicate 由各自父 entry 所属 slice 负责。
7. 🔴 IF slice 的 `excluded_from_slice` 显式否决过某条捷径 THEN 本 spec SHALL NOT 重新引入，且 SHALL 在 `design.md` 引用其否决理由原文（含「不为它硬指一本册（那是伪造 source_ref）」与「不得为凑字段编一个码」两条）。

### Requirement 2 — AC-1 ~ AC-48 只在本 spec 裁定一次

**用户故事**：作为三份 A spec 的共同上游，我要把跨 entry 复用的判据集中裁定，让 lane spec 只引用编号。

#### 验收标准

1. WHEN 编写 `design.md` THEN SHALL 给出 **AC-1 ~ AC-48** 完整对照表，每条含「NC 基准编号 / 在 A 的判定（✅沿用 · ⚠️变形 · ❌不适用 · 🔁反转 · 新增）/ A 侧现算分母 / 归属 spec」四列。
2. WHEN lane2 / lane3 spec 引用共同裁决 THEN SHALL 仅写编号（如「依 AC-38」），SHALL NOT 复述判据正文。
3. 🔴 WHEN 某条判 ❌ 不适用 THEN SHALL 显式写出「空分母」及其现算证据。本轮 ❌ 共 **11** 条，是历轮最多（N 轮仅 1 条）。
4. 🔴 WHEN 某条判 🔁 反转 THEN SHALL 同时写出「N 轮结论」与「A 轮反证数据」。本轮 🔁 共 **5** 条：AC-13（门控口径）· AC-18（canary 判据）· AC-25（归档 spec 完成度）· AC-28（路由接入状态）· AC-36（footer 读取方式）。
5. WHEN AC 编号落地 THEN SHALL 无缺号、无重号，且每条至少被本 spec 或某 lane spec 的 tasks 引用一次（引用闭合性在 Task 6 复盘校验）。
6. 🔴 WHEN 统计判定分布 THEN SHALL **逐条数表格**得出并给出五类计数与编号清单，SHALL NOT 凭印象写总数（N 轮在此犯过错，本轮明确要求列编号）。

### Requirement 3 — 写路径与持久化通道（TB 发布门在 A 域空分母）

**用户故事**：作为质控，我要知道 A 类底稿根本不回写试算表，避免照抄前十一轮的发布门判据后得到恒空结果并误判为「已合规」。

#### 验收标准

1. 🔴 WHEN 现算端点 `audit-determination/publish-to-tb` 在 A 域 20 个宿主内的命中 THEN SHALL 为 **0** ⇒ **前十一轮来首次为 0**。该判据在 A 域 SHALL 声明**空分母**，SHALL NOT 写「已验证发布门唯一」。
2. WHEN 现算已废端点 `trial-balance/writeback` THEN SHALL 为 **0** —— 平台铁律未被 A 域违反（本项仍为有效反向断言）。
3. 🔴 WHEN 现算 `/checklist-responses` 在宿主内的命中 THEN SHALL 为 **0**，但 `entry_groups` 声明 GRP-01 的 channel 就是 `checklist_responses` ⇒ **持久化在宿主 import 闭包里，不在宿主文件内** ⇒ 判据 SHALL 按 slice 的 `grouping_recipe` 扫 **import 闭包（深度 3）**，只扫宿主必假阴。
4. WHEN 现算持久化通道 THEN SHALL 恰 **4** 种：`checklist_responses` · `checklist_responses+field_overrides` · `field_overrides` · `custom_cells`；A 域只涉及前 **3** 种（`custom_cells` 属 `xlsx/gt-custom-wp-editor`，不在 A 域）。
5. WHEN 现算 `field-overrides` 在 A 域宿主内 THEN SHALL 为 **4** 命中 / **2** 文件，与 GRP-02 + GRP-03 的 channel 声明吻合。
6. WHEN 现算确认门 THEN `ElMessageBox.confirm` SHALL 为 **7** 命中 / **3** 文件，且与发布门**无交集**（发布门分母为 0，交集恒空）⇒ 判据 SHALL 表述为「确认门独立存在」而非「与发布门分居」。
7. WHEN 新增 sync 写路径 THEN SHALL NOT 引入任何 publish-to-tb 调用点（A 类底稿无此语义），也 SHALL NOT 在 watch / onMounted / debounce 回调内触发持久化。

### Requirement 4 — 模式门控判据：祖先链 × 递归 v-else 链头回溯

**用户故事**：作为扫描器作者，我要一个在 A 域真实成立的门控判据，避免照抄 N 轮口径后把 5 个 entry 误判为「无开关」。

#### 验收标准

1. WHEN 现算 OO 挂点 THEN SHALL 为 **20**（每 entry 恰 1 个，`mount_count` 全 **1**）；`<el-segmented>` SHALL 为 **19**；有 mode 门控的挂点 SHALL 为 **19**。
2. 🔴 WHEN 判定 mode 门控 THEN 判据 SHALL 为：对 OO 挂点**及其全部祖先**，逐节点检查「自身 `v-*`/`:` 绑定含 mode token」**或**「该节点是 `v-else`/`v-else-if` 且其同层兄弟链头的 `v-if` 含 mode token」。mode token 正则 SHALL 为 `\b\w*[Mm]ode\b`（覆盖 `mode` / `renderMode` / `activeMode` / `dualMode` / `editorMode`）。
3. 🔴 WHEN 登记门控三形态 THEN SHALL 为：**`v-else` 兄弟链 14** · **祖先元素 3**（a112 / a115 / a38）· **三层嵌套 2**（a171 / a177 —— 外层 `<div v-else>` 承 mode 门控，OO 挂点自身是 `v-else-if="ooReady"` **不含 mode**，须对**祖先的 v-else 再回溯其兄弟链头**）。
4. 🔴 WHEN 用 N 轮口径（只看挂点自身属性）THEN SHALL 只得 **14** ⇒ **假阴 5 处**；用「挂点自身 + 自身链头」中间口径 SHALL 只得 **3 处祖先命中** ⇒ 两个中间版本**都不可照抄**，本 spec SHALL 在 `design.md` 保留两次口径迭代的对照作为变异证明。
5. WHEN 现算无门控的 entry THEN SHALL 恰 **1** 条：`xlsx/gt-a3-consolidation-console`（segmented = 0 且 mode 门控 = 0），与 slice 的 `no_carrier` / `no_switch_at_all` 声明吻合。
6. WHEN 现算开关裁决分布 THEN 全 slice SHALL 为 **42 redeemable + 0 inert + 4 no_switch_at_all**；A 域 SHALL 为 **19 redeemable + 1 no_switch** ⇒ 🔴 **inert 在 A 域为 0**（N 轮有 2 条 inert），照抄 N 的「inert 是宿主内联空回调」判据在本轮**恒空跑**。

### Requirement 5 — mode 载体二分：中文标签作值 vs label/value 分离

**用户故事**：作为实施者，我要知道 A 域有 17 个 entry 把中文界面文案直接当作 mode 的逻辑值，改文案就会破坏逻辑。

#### 验收标准

1. 🔴 WHEN 现算形态 1 THEN SHALL 为 **17** 条 entry：`modeOptions = ref(['结构化视图', '在线编辑'])`（**字符串数组**），mode 值**就是中文标签**，`mode === '结构化视图'` 比较现算 **18** 处 ⇒ **改中文文案即破坏逻辑**，与 BP-14「不得使用可改 label 作 identity」**同型**。
2. 🔴 WHEN 现算形态 2 THEN SHALL 为 **2** 条 entry（`xlsx/gt-a112-dual-checklist` / `xlsx/gt-a38-goodwill-impairment`）：`modeOptions = [{ label: '结构化视图', value: 'html' }, { label: 'Word编辑', value: 'docx' }]`（**对象数组**）+ 变量名 **`activeMode`** + 类型 `ref<'html' | 'docx'>` ⇒ **label/value 分离的正面样板**，改造 SHALL 抄此形态。
3. 🔴 WHEN 扫 `modeOptions` THEN SHALL 区分字符串数组与对象数组两种结构 —— 把对象数组的 label 与 value 一并当成「并列选项」会得出「4 值混排」的错误结论（本轮实测踩过此坑，已现读源码更正）。
4. 🔴 WHEN 扫 OO 模式字面量 THEN `'onlyoffice'` 在 A 域现算 SHALL 为 **0** 次（形态 2 里 OO 值是 **`'docx'`**）⇒ 任何以 `'onlyoffice'` 为锚点的判据在 A 域恒空。
5. WHEN 现算英文 mode 值 THEN SHALL 登记 `mode === 'structured'` **1** 处与中文值混用。
6. WHEN 现算 localStorage THEN A 域宿主内 SHALL 只有 `'token'` **1** 处，**无 mode 分区键** ⇒ mode **不持久化**，该判据在 A 域声明空分母（N 轮有 `n1-dual-mode` 按 wp 分区）。

### Requirement 6 — canary 判据第二次偏离硬标准（三轮态度须一并写明）

**用户故事**：作为决策记录的读者，我要看到 canary 判据在 M→N→A 三轮的完整轨迹，确认每轮都现查了分母，而不是随意放宽。

#### 验收标准

1. 🔴 WHEN 陈述 canary 判据 THEN SHALL 完整写出三轮轨迹：**M 轮偏离**（M 域真库仅 6 行、唯一非空 `remark` 是 AI 会话 ⇒ 硬标准无解，改用五条替代判据）→ **N 轮收回**（N 域 `N4-1-rows` 真库 **1665 B** 且 `rowKey` 是稳定语义键 ⇒ 硬标准可用，显式声明「M 轮换判据是 M 特有」）→ **A 轮再偏离**（见第 2 条）。SHALL NOT 只说「沿用 M 轮做法」。
2. 🔴 WHEN 校验 A 域真库分母 THEN `item_id ~ '^A[0-9]'` 现算 SHALL 为 **28** 行，但其宿主 wp_code 为 `A1-11` / `A15-1` / `A17-1` / `A17-5-1` / `A1` / `A21-1`，与本轮 20 条 entry 的 wp_code **交集仅 `A17-1` 一条**（`A17-1-ch01`，`remark` **53 B**），且该行内容明文含 **`（E2E seed）`** ⇒ **不是真实业务载荷** ⇒ 硬标准在 A 域**无解**。
3. WHEN 选定 canary THEN SHALL 为 `xlsx/gt-a51-cashflow-audit`，替代判据 **五项全中且全域唯一**：① **零区分项**（`capability_target_blocked_by` 仅公共 6 项，20 条中唯一）② **xlsx 权威册**（2 条之一，可跑既有 openpyxl 全套判据）③ **主组 GRP-01**（15 条之一，代表性最强）④ **redeemable**（19 条之一）⑤ **`literal_sheet_name`**（19 条之一）。
4. WHEN 登记加分项 THEN SHALL 写明：sha256 + size 对账通过 · **9 sheets / 公式格 57**（中等规模）· channel 单一 `checklist_responses` · `mount_count` 1。
5. WHEN 记录排除理由 THEN SHALL 逐条写明：`a3-consolidation-console`（虽也是 xlsx，但**无 segmented + 无 mode 门控** ⇒ 「双向」的「双」不存在，结构上不能做 canary）· `a177-independence-declaration`（`resolution_kind` 是 `runtime_sheet_name_expression`，**静态无唯一权威册**）· `a38-goodwill-impairment`（**无权威册** + 背负 BP-14 的 Property 22 缺陷）。
6. 🔴 WHEN 登记 canary 短板 THEN SHALL 写明：`A5-1` 册的 `definedName` **22 / broken 14**（形态与 N 域同源）· 真库该 entry **0 行**（`A5-1` 前缀在 28 行里不存在）⇒ 闭环验证须**自建夹具**，SHALL NOT 依赖既有真库数据，且该依赖须标 `[ ]*`。
7. 🔴 WHEN 登记 AI 会话行 THEN `A1-review-session-20260725074949`（**261 B**）SHALL 被按白名单排除 —— 与 M1 / N1 / N2 / N5 **同型同批次**（**第三轮出现**），判据 SHALL 沉淀为跨循环通用排除规则而非每轮重写。

### Requirement 7 — 模板层只登记不修改，且判据按 format 分流

**用户故事**：作为审计业务负责人，我要确保 sync 改线不动权威模板，且扫描器不会对 docx 册跑出异常或无意义的数字。

#### 验收标准

1. 🔴 WHEN 本 spec 任何 task 执行 THEN SHALL NOT 修改 `backend/wp_templates/A` 下任何文件 —— A 域 18 本有册 entry 的 **sha256 + size 现算 18/18 match**，交付后须仍 match。删除清册的 `must_not_delete_templates` 明文 `AP-2：不得为满足数字修改或删除权威模板`（`file_count` 367，覆盖 A/B/C/S 四个根）。
2. 🔴 WHEN 扫描权威册 THEN SHALL 先读 `template_ref.workbook_format` 分流：**docx 16 条走 `python-docx`** · **xlsx 2 条走 `openpyxl`** · **无册 2 条声明空分母**。对 docx 跑 openpyxl SHALL 抛 `InvalidFileException`（已实证），该反证 SHALL 保留在守卫中。
3. WHEN 现算 A 目录全册 THEN SHALL 为 **97 本 = xlsx 65 + docx 32**，与 slice 的 `AD-3.value` 的 `{"A": {"xlsx": 65, "docx": 32}}` **逐值吻合**。
4. WHEN 现算册↔entry 归属 THEN 只 **18** 本能归属 ⇒ **未引用 79 本**（97 − 18）⇒ 🔴 **双射判据 SHALL 降级为单射**，未归属册须写 `excluded_reason`（SR-8）。
5. WHEN 断言 xlsx 侧公式格 THEN SHALL 为 **120**（A3-3 **63** + A5-1 **57**），带公式 sheet **7**，口径 `data_only=False` + `isinstance(v, str)` + `startswith('=')` + `len > 1`；`data_only=True` 反证 SHALL 为 **0**。
6. 🔴 WHEN 读 footer THEN SHALL 用 raw XML，SHALL NOT 用 `ws.oddFooter` —— openpyxl 对两本册均报 `Cannot parse header or footer so it will be ignored` 并静默返回空。raw XML 现算 13 sheet 呈**三态**：**2 有内容**（`A3-3` sheet1 = **`第 &P 页，共 &N 页`** 中文 · `A5-1` sheet8 = **`Page &P`** 英文且无 `&N`）+ **7 有 `<headerFooter>` 容器但无 `oddFooter` 子元素** + **4 无容器**。
7. WHEN 发现模板层缺陷 THEN SHALL 以「登记 + **记录型**测试锁定现状」处理，使未来修复时测试显式失败提醒同步更新。

### Requirement 8 — 结构性零必须配变异证明（A 域空分母项为历轮最多）

**用户故事**：作为复盘者，我要能区分「扫描器写错导致 0」与「事实就是 0」，尤其在 A 域有 11 条判据整体不适用的情况下。

#### 验收标准

1. WHEN 断言某项为 0 THEN SHALL 同时提供**变异证明**：同一扫描器在非空场景（其他循环 / A 域其他形态 / 故意造的反例串）上 SHALL 命中非零。
2. 🔴 WHEN 登记「我自己踩过的坑」THEN SHALL 写明 **footer 案例**：第一轮用 `ws.oddFooter` 读出「全 None/空」，若直接写成「A 域 footer 空分母」即为假绿；raw XML 对账推翻后才得到真三态 ⇒ **解析失败与事实为空必须分开**。
3. WHEN 登记本轮结构性零 THEN 清单 SHALL 为：`trial-balance/writeback` 0 · `#REF!` 死公式 0 · 超列引用 0 · 裸 IF 0 · `'onlyoffice'` 字面量 0 · `removeRow` 0 · A 族持久化键 0 · M 式 `row-${n}` 0 · `GtEntrySyncCapabilityNotice` 0 · `useChecklistPersistence` 0 · `contract-ocr` 0 · `onlyoffice-config` 0 · `useAdjustmentCentralSync` 0 · `http.put` 0 · `api.put` 0 · `useWpDualMode` 与 `useWorkpaperEntryDualMode` 在 A 域各 0 · `publish-to-tb` 0 · `/checklist-responses`（宿主内）0 · A 域 per-entry dual-mode composable 0 · A 域「原底稿/历史」册 0 · 跨 entry 污染 0 · in-scope parent_duplicate 0 · A 域 orphan dual-mode 模块 0。
4. 🔴 WHEN 某项分母为空 THEN SHALL 写「本轮空分母，判据保留待后续循环」，SHALL NOT 写「已验证无此问题」。
5. 🔴 WHEN 断言「A 域 per-entry dual-mode composable = 0」THEN SHALL 用**变异证明**：同一正则在全域跑出 `*DualMode*.ts` **114** 个模块（无一属 A/B/C/S），证明正则本身有效。
6. WHEN 断言「跨 entry 污染 = 0」THEN SHALL 附现算依据：A 域 28 行真库记录的 `item_id` 前缀与宿主 `wp_code` **28/28 完全对齐**；变异证明 = 同一查询在 L / N 域跑出 G8 污染（L 1 条 / N 4 条）。

### Requirement 9 — docx 权威册（BP-9）是 A 域最大区分项

**用户故事**：作为实施者，我要知道 16/20 条 entry 的权威册是 Word 文档而非 Excel，双向回写的「表格定位」模型在这里不成立。

#### 验收标准

1. WHEN 现算 BP-9 成员 THEN SHALL 为 **16** 条，且 🔴 **BP-9 集合 == docx 集合**（现算 `True`，16 == 16）⇒ **两者是同一分界**，切分依据即此。
2. WHEN 现算 docx 结构 THEN tables 范围 SHALL 为 **0 ~ 13**、非空段落 **2 ~ 213**、表格单元格 **0 ~ 3174**。
3. 🔴 WHEN 登记极端册 THEN `a115-disclosure-checklist` 的 3 个表格几何 SHALL 为 `25x9` / `49x3` / **`934x3`** ⇒ **934 行巨表**，cells **3174**，`merged_refs` **3159（99.5%）**。
4. 🔴 WHEN 现算合并单元格 THEN SHALL 登记 `merged_refs` 普遍极高：a115 **99.5%** · a112 **92%** · a1731 **86%** · a176 **85%** · a171 **71%** · a174 **70%** ⇒ **按 (row, col) 遍历会重复命中同一 `<w:tc>`** ⇒ 定位模型 SHALL 以 `tc` 对象标识去重，SHALL NOT 假设 (row, col) 与 cell 一一对应。
5. 🔴 WHEN 处理纯信函型 entry THEN SHALL 容忍 **0 表格**：`a181-regulatory-submission` 现算 **0 tables / 8 段落**、`a91-deficiency-letter` 现算 2 个 `1x1` 表 + 29 段 ⇒ 「每 entry 有表格」判据必假。
6. WHEN 现算占位符 THEN SHALL 为**五形态**：`XX`（a181 15 处最多）· **`××` 全角**（a101 / a91）· **`【】`**（a101 **55** 处最多 · a171 38 · a271 16）· `□`（a121）· `N/A`（a115）⇒ `【` 是主要填空/指引标记。
7. WHEN 现算 sections THEN SHALL 登记 **a171 与 a81 为 2**（含分节符），其余为 1。
8. 🔴 WHEN 登记 docx 层脏数据 THEN SHALL 含：示例公司名**两种**（`XX股份有限公司` vs `ABC公司`/`ABC股份有限公司`）· `a173` **首段是指引文字**（`【参考格式，但至少包括以下四方面要素…`）而非标题 · **`a91` 的 `20l×年12月31日`**（🔴 小写字母 `l` 冒充数字 `1`）。
9. WHEN 现算 docx 内「合计/小计」THEN SHALL 为 **9** 处（a101 1 / a115 8），与 xlsx 侧 **4** 处合计 **13** 处；🔴 **全部在首列** ⇒ NC-17 的「首个非空列」改进在 A 域**空分母**（判据保留）。

### Requirement 10 — 契约字段映射：`conclusion` 仍是主载荷

**用户故事**：作为契约实现者，我要确认 N 轮发现的「`conclusion` 是主载荷」在 A 域继续成立，不要退回「只映 remark」。

#### 验收标准

1. 🔴 WHEN 现算 A 域真库字段非空 THEN `conclusion` 非空 SHALL 为 **24**、`remark` 非空 SHALL 为 **4** ⇒ **NC-34 在 A 域继续成立**（连续第二轮），契约字段映射 SHALL 覆盖 `conclusion`。
2. WHEN 现算分布 THEN SHALL 为 `A21` **19 行**（全部 conclusion 非空）· `A1` 5 行（remark 3 / conclusion 2）· `A17` 3 行（remark 1 / conclusion 2）· `A15` 1 行（conclusion 1）。
3. WHEN 现算全域对照 THEN `checklist_responses` SHALL 为 **1,034,702** 行 / **155** wp / `remark` 非空 **680** / **`conclusion` 非空 130** ⇒ A21 的 19 行占全域 conclusion 的 **14.6%**。
4. WHEN 处理 `*-review-session-*` THEN SHALL 按白名单排除（依 Requirement 6 第 7 条）。
5. 🔴 WHEN 设计映射 THEN SHALL 沿用 N 轮裁定的「**实际非空列优先于后缀规则**」，SHALL NOT 仅按 `item_id` 后缀猜列。
6. WHEN 现算契约目录归属 THEN 生产契约 **4** 份（`b60.hour_budget` / `d2.*` / `g7.*` / `h1.*`），**无一属 A 域** ⇒ BP-2 成立；🔴 第 5 个文件 `_example.candidate.json` 的 `review.entry_id` 为 **null**，是反例分母，守卫 SHALL NOT 要求它非空。

### Requirement 11 — 已归档 spec 边界：35 份且 6 份未完成（与 N 轮反转）

**用户故事**：作为实施者，我要知道 A 循环的功能 spec 有未完成的欠账，且其中一处正是 BP-11 的成因。

#### 验收标准

1. WHEN 执行铁律⑬ THEN SHALL 用**宽关键词**扫 `_archive/`（`a1x` / `a3` / `a5` / `a8` / `a9` / `report` / `adjust` / `cashflow` / `goodwill` / `consolidat` / `kam` / `governance` / `checklist` / `deficiency`），现算命中 **35** 份 A 循环相关 spec。
2. 🔴 WHEN 现算完成度 THEN SHALL 登记 **6 份未 100%**（共 **7** 条未完成任务）：`a11-1-subsequent-events-inquiry` 19/21 · `a17-3-1-consultation-execution` 15/16 · `a17-3-consultation-record` 16/17 · `a17-4-disagreement-record` 16/17 · `a17-7-independence-declaration` 20/21 · `a18-2-regulatory-communication` 14/15 ⇒ **与 N 轮（16 份全 100%）反转**。这些 entry 正是本轮 A 域 entry，欠账须在 lane2 / lane3 交叉登记。
3. 🔴 WHEN 现算 0/0 spec THEN SHALL 登记 **4 份**（`A00-completion-infra` / `A02-misstatement-a13` / `A03-control-deficiency-a14` 等）—— 有 `tasks.md` 但**零编号任务** ⇒ 「159/159 全绿」的表述 SHALL 附此说明，避免读者误以为 13 份都有实质任务。
4. 🔴 WHEN 追溯 BP-11 成因 THEN SHALL 写明：`a9-1-deficiency-letter`（28/28）与 `a9-2-deficiency-letter-governance`（18/18）**各有独立归档 spec**，但两个 componentType **共用宿主 `GtA91DeficiencyLetter.vue`** ⇒ entry↔componentType 非双射 ⇒ 与 M 轮 MC-25「两份归档 spec 结论不一致」**同型**。
5. 🔴 WHEN 处理 a177 的变体轴 THEN SHALL 写明归档 spec 名是 **`a17-7`** 而 entry 的 `wp_code_patterns` 只有 **`A177I`** 一个，其 `sheet_name_exprs` 是 `variant === 'team' ? 'A17-7' : 'A17-7A'` ⇒ **A17-7 / A17-7A 双变体在 pattern 里丢失**。
6. 🔴 WHEN 扫描归档区 THEN SHALL 带 `errors="replace"` 容错 —— `_archive/07-workpaper-slimdown/report-view-slimdown/tasks.md` **不是 UTF-8**，直接 `read_text(encoding="utf-8")` 会抛 `UnicodeDecodeError` 中断整轮扫描。
7. WHEN 本 spec 交付 THEN SHALL NOT 回填修改任何已归档 spec（append-only），勘误登记在本 spec。

### Requirement 12 — entry_groups 二维分组与既存守卫可复算性

**用户故事**：作为守卫维护者，我要能从源现算出 13 组分组键，而不是照抄 slice 里的数字。

#### 验收标准

1. WHEN 现算分组 THEN SHALL 为 **13 组 / 9 个 componentType 家族 / 4 个持久化通道**，`groups_with_more_than_one_entry` **4** / `singleton_groups` **9**。
2. WHEN 现算 A 域分组归属 THEN SHALL 为 **GRP-01 15**（`a_class_single_sheet_host` + `checklist_responses`）· **GRP-02 1**（+ `field_overrides`）· **GRP-03 3**（`field_overrides`）· **GRP-10 1**（`multi_component_type_single_host`）= **20** ✓，且这 4 组**只含 A 域 entry**（不与 B/C/S 混）。
3. 🔴 WHEN 复算第一维（componentType 家族）THEN SHALL 按 slice 的 `grouping_recipe`：从 `htmlRendererRegistry.ts` 的 `REGISTRY_LIST` 按**模块边**匹配（把每条 `componentType:` 与紧随的 `component:` 解析成磁盘路径，再与 entry 的 `host_path` 比对），**SHALL NOT 按符号名 grep** —— registry 有提升的 `const` 与内联 `defineAsyncComponent` 两种写法，只认一种会漏 **94/211** 条（slice 首版实测）。
4. WHEN 复算第二维（持久化通道）THEN SHALL 现读宿主 **import 闭包（深度 3）**里的真实 HTTP 站点，三个通道键为 `/checklist-responses` · `/api/workpapers/field-overrides` · `/custom-cells`；命中多个按固定顺序拼接。**SHALL NOT 按 wp_code 字母硬分组**。
5. WHEN 现算 registry 规模 THEN `htmlRendererRegistry.ts` 的 `componentType:` 行数 SHALL 为 **211**（删除清册 `must_not_delete` 明文：删改会让分组恒空）。
6. WHEN 现算 `component_type_family` 分布 THEN A 域 SHALL 为 `a_class_single_sheet_host` **19** + `multi_component_type_single_host` **1**。

### Requirement 13 — BP 收口范围与平台级欠账

**用户故事**：作为实施者，我要明确 canary entry 要闭合哪些 blocked_by，哪些属平台级不在本轮闭合。

#### 验收标准

1. WHEN 现算 A 域公共 BP THEN SHALL 恰 **6** 项（BP-1 / BP-2 / BP-3 / BP-4 / BP-5 / BP-7），20 条无一例外。
2. WHEN 现算区分项成员集 THEN SHALL 为 BP-6 = {a38}（1）· BP-8 = {a177}（1）· **BP-9 = 16 条 docx** · BP-10 = {a3-console}（1）· BP-11 = {a91}（1）。
3. WHEN 现算 canary 的 `capability_target_blocked_by` THEN SHALL 恰 **6** 项（仅公共，零区分项）—— 20 条中唯一。
4. WHEN 现算逐 entry BP 数分布 THEN SHALL 为 **6 项 1 条**（a51）· **7 项 18 条** · **8 项 1 条**（a91，兼 BP-9 + BP-11）。
5. 🔴 WHEN 处理 BP-1 / BP-2 / BP-3 / BP-4 / BP-5 THEN SHALL 标 `[ ]*`（平台级：approved 权威模型未发布 · 逐 entry contract 未发布 · manifest 的 capability 是 overlay 默认值非逐 entry 裁决 · definition bundle 与 published representation 未交付 · adapter 未注册且 `adapter_id` 现算 **46/46 为 null**），SHALL NOT 在本 spec 声称闭合。
6. WHEN 收口 BP-7 THEN `GtEntrySyncCapabilityNotice` 在 A 域现算 SHALL 为 **0** 挂载（该组件全域现算 **41** 条非本 slice 宿主在用）⇒ A 域须**新增**挂载而非删除；🔴 tooltip 不算接线。
7. 🔴 WHEN 处理 BP-14 THEN SHALL 注意它**不进任何 entry 的 `blocked_by`**（登记型 BP）⇒ 「登记型 BP」与「阻塞型 BP」两种语义 SHALL NOT 混判。

### Requirement 14 — 删除清册：本轮无立即删除对象，主线是 46 宿主改线

**用户故事**：作为维护者，我要知道前十一轮的「删 orphan」主线在 A 轮空分母，本轮真正的主线是宿主改线。

#### 验收标准

1. 🔴 WHEN 现算删除清册 THEN `delete_files` SHALL 为 **0**（空数组），且 `delete_files_is_empty_because` 明文给出三条实算依据：① `composables/` 下匹配 `^use[ABCS]\d.*DualMode\.ts$` 的文件 **0** 个 ② 46 条 entry 的宿主里没有一个 import per-entry dual-mode composable ③ 四个共享载体**此刻都还有生产消费方**。
2. 🔴 WHEN 编写守卫 THEN SHALL 断言「现算 orphan dual-mode 模块数 == 0」**且**「`delete_after_rewire` 非空」，SHALL NOT 断言「删除清单非空」（清册明文要求此口径）。
3. WHEN 现算 `delete_after_rewire` THEN SHALL 为 **1**（`composables/useWpDualMode.ts`，3 条生产边全在本 slice 内 —— `GtB1Evaluation.vue` / `GtB1KaaCheck.vue` / `GtB1RiskAssessment.vue`，🔴 **全在 B 域**，A 域不涉及）。
4. WHEN 现算 `latent_orphan_after_rewire` THEN SHALL 为 **1**（`composables/factories/createDualMode.ts`，改线后只剩 **barrel** 入边）⇒ 🔴 **不擅自删**；barrel 入边 SHALL 按**路径解析**口径识别（**禁 stem 相等**）。
5. WHEN 现算 `must_rewire` THEN SHALL 为 **46** 条（每 entry 一个宿主），A 域占 **20** 条；改线目标 = 宿主内联的 `<el-segmented>` + mode 门控 `GtOnlyOfficeSheet` 挂点改接 sync bridge，宿主只传 entryId / wpId / sheetName + flush/reload 回调。
6. WHEN 现算 `must_not_delete` THEN SHALL 为 **5** 项（`useWorkpaperEntryDualMode.ts` 共享基类 · `useCycleHtmlOoDualMode.ts` · `GtEntrySyncCapabilityNotice.vue` · `workpaperEntrySyncNotice.ts` · `htmlRendererRegistry.ts`）。
7. 🔴 WHEN 现算共享基类边 THEN SHALL 为 **26 生产 + 1 测试**，本 slice 只贡献 **5** 条（全在 B 域）⇒ A 域贡献 **0** ⇒ 该判据对 A 域空分母；且清册明文「每轮现算不得照抄（M=29 / N=27 / 本轮=26+1）」。
8. WHEN 现算载体分布 THEN SHALL 为 `entries_host_inline` **32** · `entries_on_shared_carrier` **10** · `entries_with_no_carrier` **4** · `shared_dual_mode_carriers` **4** · `orphan_dual_mode_modules` **0** · `per_entry_dual_mode_composables` **0**。

### Requirement 15 — Property 22 首次拿到非空分母（结论 PARTIAL）

**用户故事**：作为质控，我要知道「动态列 key 与 label 解耦」这条 Property 在本轮首次有真实分母，且结论不是通过。

#### 验收标准

1. 🔴 WHEN 现算 Property 22 分母 THEN `dynamic_column_site_count` SHALL 为 **7**、`label_as_key_site_count` SHALL 为 **3**、`verdict` SHALL 为 **PARTIAL** ⇒ 前六轮（I/J/K/L/M/N）均以「分母为空、不宣称通过」收场，**本轮首次非空**。
2. WHEN 现算 A 域份额 THEN SHALL 为 **1** 条 entry（`xlsx/gt-a38-goodwill-impairment`）：站点 `GtA38GoodwillImpairment.vue#L154`，`v-for="(_, i) in 5"` ⇒ **写死 5 列**（`column_count_hardcoded`）+ `key_binding: "i"` ⇒ **裸下标作 key**（`key_is_bare_index`）+ `label: \`第${i + 1}年\`` ⇒ **两类缺陷同时命中**。
3. WHEN 现算 BP-14 成员 THEN SHALL 为 **4** 条（a38 / b14-due-diligence-report / b23-process-control / b50-risk-assessment），A 域只 **1** 条 ⇒ 其余 3 条归后续 B 轮。
4. WHEN 复算 Property 22 THEN SHALL 按 slice 的 `recompute_recipe`：扫描面 = 46 条 entry 的宿主 + 宿主所在子目录下全部 `.vue`（剥注释保留行号）；动态列站点 = `<el-table-column … v-for="…" …>` 整标签（跨行 `re.S`）；三类缺陷判据 = `key_equals_label` / `key_is_bare_index` / `column_count_hardcoded`；另反扫「用 `.label`/`.name`/`.title` 作 `:key`」。
5. 🔴 WHEN 陈述结论 THEN SHALL 写 **PARTIAL** 并列出三处缺陷，SHALL NOT 写「通过」。
6. 🔴 WHEN 关联 mode 载体 THEN SHALL 指出 Requirement 5 形态 1（中文标签直接作 mode 值，17 条）与 Property 22 的「label 作 identity」是**同一类问题在不同层面的体现** —— 前者是模式层、后者是列层，判据分开但根因同源。

### Requirement 16 — 行数口径与上游计数纪律

**用户故事**：作为复盘者，我要知道哪些上游数字必须现算、哪些已被证伪。

#### 验收标准

1. WHEN 统一行数口径 THEN SHALL 用 `len(text.split("\n"))`，并在 `design.md` 写明与 slice / 清册 `splitlines()` 的差异（末行无换行时相差 1）。
2. 🔴 WHEN 引用 slice 数字 THEN SHALL 逐项现算校验，且 SHALL 登记 Requirement 1 第 3 条的 **4 处自相矛盾**。
3. 🔴 WHEN 引用 `_should_skip_historical_sheet` 消费方数 THEN SHALL 现算（本轮 **3** 个文件：`wp_template_init_service.py` / `wp_template_finder.py` / `chain_orchestrator.py`），SHALL NOT 照抄 M 轮记录的「只 2 处」。
4. WHEN 现算 `resolveProcedureSheetKey.ts` THEN SHALL 为 **91** 行且 🔴 **完全无 A 分支** ⇒ A 循环**未接入该路由**。三轮三态 SHALL 一并登记：**M 缺 4 条（M1/M3/M7/M8）· N 完备 5/5 · A 整段缺失**。
5. WHEN 现算 `derived_total` 双正则 THEN A 域宿主 SHALL 为 TAIL **4** : MID **2** / 3 文件（全域 764 : 268 / 431 文件）⇒ 分母小但非空，判据保留。
6. WHEN 现算 `prefill` THEN A 域宿主 SHALL 为 **11** 命中 / **2** 文件 ⇒ 分母非空（同 N 轮结论）。
7. WHEN 现算 docx 生成逻辑 THEN SHALL 为 **70** 命中 / **8** 文件 ⇒ 🔴 A 域独有（前十一轮全无），该逻辑与 BP-9 同源，改线时须一并纳入。
