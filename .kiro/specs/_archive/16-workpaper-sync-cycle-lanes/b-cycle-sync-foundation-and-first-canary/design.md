# B 循环双向回写地基与首张 canary — 设计

## 定位

本 spec 是 B 循环（控制了解与风险评估）三份 sync spec 的**地基层**：一次性裁定 BC-1 ~ BC-60 共同判据、锁定 10 条 entry 的事实基线、落地首张 canary（`xlsx/gt-b22-a-control-matrix`）。两份 lane spec 只引用 BC 编号，不重复裁决。

## 一、拆分裁决：为什么是「载体三分」

### 1.1 A 轮方法在 B 域失效

A 域 20 条有 5 个 BP 区分项，可按 BP 归属切分。B 域 10 条的 `capability_target_blocked_by` **逐值完全相同**（`BP-1,2,3,4,5,7,8`，共 7 项）⇒ **区分项 = 0** ⇒ BP 轴无法区分任何 entry。

同样失效的还有：`resolution_kind`（10/10 同）· `workbook_format`（10/10 为 `null`）· `migration_state`（10/10 同）· `switch`（10/10 `redeemable`）· `component_type_family`（10/10 同）· `mount_count`（10/10 为 1）· `html_counterpart_verdict`（10/10 `exists`）。

### 1.2 四条候选轴穷举（现算，非推演）

| 轴 | 组数 | 组规模 | 最大/最小 | 跨组缺陷 |
|---|---|---|---|---|
| **载体三分** | 3 | 5 / 3 / 2 | **5 / 2** | 6 / 20 |
| mode 值体系 | 3 | 5 / 4 / 1 | 5 / 1 | 6 / 20 |
| sheet 表达式四形态 | 4 | 4 / 3 / 2 / 1 | 4 / 1 | 6 / 20 |
| group 二分 | 2 | 9 / 1 | **9 / 1** | 4 / 20 |

裁决理由：

- **group 二分被拒**：跨组缺陷最少（4）但规模 9:1 严重失衡，为 1 条 entry 单开一份 spec 不成立
- **sheet 表达式四形态被拒**：碎片化（4/3/2/1），且 `checklist@D1` 横跨全 **4** 组
- **mode 值体系被拒**：与载体三分近乎同构（仅 `b14` / `b23` 归组不同），但 `structured` 组只 **1** 条，失衡
- **载体三分胜出**：规模最均衡（5/3/2）+ 同时是**改线单元**（见 1.3）

### 1.3 载体三分同时是改线单元（决定性理由）

| 载体 | n | 改线后果 |
|---|---|---|
| `useWpDualMode.ts` | **3** | 🔴 **全 slice 唯一 `becomes_orphan_after_rewire = True`** —— 改线后整个文件成孤儿，须连带删除 |
| `useWorkpaperEntryDualMode.ts`（共享基类） | **5** | 26 条生产边中 B 域占 5，改线后**不**成孤儿（其他循环仍在用）⇒ 须保持向后兼容 |
| `host_inline_segmented` | **2** | 门控写在宿主内，改线只动宿主，无共享载体牵连 |

三组的改线动作根本不同（删文件 / 保兼容 / 改宿主）⇒ 切分与工程动作对齐。

### 1.4 缺陷集合重合度（Jaccard，验算切分合理性）

| 组对 | 交 / 并 | Jaccard | 共有缺陷 |
|---|---|---|---|
| host_inline ∩ 共享基类 | 5 / 18 | **0.28** | `checklist@D1` / `count` 键 / `idx` 形参 / `removeRow` / 门控假阴 |
| host_inline ∩ `useWpDualMode` | 3 / 12 | **0.25** | `E` 稳定身份 / `checklist@D1` / 门控假阴 |
| 共享基类 ∩ `useWpDualMode` | 2 / 16 | **0.12** | `checklist@D1` / 门控假阴 |

三组两两重合度均 < 0.30 ⇒ 切分合理。各组独有缺陷：共享基类 **8** · host_inline **4** · `useWpDualMode` **2**（每组都有实质独有内容）。

横跨三组的 **2** 项（`checklist@D1` 持久化闭包深度、门控假阴）正是 BC-42 / BC-13 —— 已在本 foundation 一次性裁定，不下沉 lane。

## 二、spec 三分与 entry 归属

| spec | entry | n |
|---|---|---|
| `b-cycle-sync-foundation-and-first-canary`（本份） | `xlsx/gt-b22-a-control-matrix`（canary） | **1** |
| `b-class-shared-base-carrier-lanes` | `xlsx/gt-b22-b-control-matrix` / `xlsx/gt-b22-b-deficiency-evaluation` / `xlsx/gt-b22-c-design-effectiveness` / `xlsx/gt-b50-risk-assessment` | **4** |
| `b-class-orphan-carrier-and-host-inline-lanes` | `xlsx/gt-b1-evaluation` / `xlsx/gt-b1-kaa-check` / `xlsx/gt-b1-risk-assessment` / `xlsx/gt-b14-due-diligence-report` / `xlsx/gt-b23-process-control` | **5** |

1 + 4 + 5 = **10** ✓

## 三、BC-1 ~ BC-60 共同裁决对照表

判定图例：✅ 沿用 · ⚠️ 变形（方向不变但锚点/口径须改）· ❌ 不适用（空分母） · 🔁 反转（A 轮结论在 B 被证伪） · ➕ 新增（B 独有）

| BC | 主题 | AC 基准 | 判定 | B 侧现算分母 | 归属 |
|---|---|---|---|---|---|
| BC-1 | slice 范围与 manifest 分歧 | AC-1 | ⚠️ | 同一份 abcs slice，46 切 **10** | foundation |
| BC-2 | 载体族并存 | AC-2 | 🔁 | **载体三分** 5/3/2（A 是 segmented 19 + no_carrier 1） | foundation |
| BC-3 | 端点字面量须认反引号 + 剥注释 | AC-3 | ⚠️ | publish-to-tb **0** · health **2** · checklist **2** | foundation |
| BC-4 | 确认门独立存在 | AC-4 | ✅ | confirm **12** / 5 文件 | foundation |
| BC-5 | strict 域须含小写前缀分支 | AC-5 | 🔁 | 小写 **0**（空）；须防 `^GtB` 误命中 **3** + 漏 **4** | foundation |
| BC-6 | 行身份正面样板 | AC-6 | ✅ | E 族 **11** / 3 文件 | foundation |
| BC-7 | `removeRow` 签名族 | AC-7 | 🔁 | **4** / 2 文件（A 域为 0 空分母） | foundation |
| BC-8 | 位置化族分类 | AC-8 | 🔁 | **函数参数式 38**；A 族 **0** · M 式 **0** | foundation |
| BC-9 | `definedName` 断链登记 | AC-9 | ❌ | 8 本册 **全 0** | — |
| BC-10 | sheet 名禁归一化 | AC-10 | ⚠️ | **前导空格** `' B1-5 KAA检查表-业务承接'` | foundation |
| BC-11 | 扫描口径差须登记 | AC-11 | ✅ | 门控假阴 3 / checklist 假阴 8 / slice 漏登 1 | foundation |
| BC-12 | notice 接线，tooltip 不算 | AC-12 | ✅ | B 域 **0**（同 A） | foundation |
| BC-13 | 门控判据（祖先链 × 递归 v-else 回溯） | AC-13 | ✅ | 假阴 **3**（b1-risk / b23 / b50） | foundation |
| BC-14 | `derived_total` 双正则 | AC-14 | ⚠️ | 冒号式 **0** / `.reduce(` **4** | foundation |
| BC-15 | `item_id` / wp_code 命名轴 | AC-15 | ⚠️ | pattern 与真实码 **6/10 不一致** | foundation |
| BC-16 | localStorage mode 分区 | AC-16 | ❌ | 有 localStorage（D1~D3）但**无 mode 键** | — |
| BC-17 | 「合计漏加小计」双条件 | AC-17 | ❌ | 无合计行形态 | — |
| BC-18 | canary 判据 | AC-18 | 🔁 | **收回硬标准**（第四轮态度，见 §四） | foundation |
| BC-19 | 跨循环键 + 跨 entry 污染 | AC-19 | ✅ | 污染 **0**（40/40 对齐） | foundation |
| BC-20 | 空分母纪律 + 变异证明 | AC-20 | ✅ | 结构性零 **14** 项（见 §五） | foundation |
| BC-21 | 跨册复制残留 | AC-21 | ❌ | B 域册名无跨循环码混入 | — |
| BC-22 | 科目性质四分 | AC-22 | ❌ | B 类非科目底稿，无借贷方向 | — |
| BC-23 | `SHEET_MAP` 常量映射 | AC-23 | ❌ | B 域无此形态 | — |
| BC-24 | 历史 sheet 过滤 | AC-24 | ❌ | 册名含「原底稿/历史」**0** | — |
| BC-25 | 已归档 spec 边界 | AC-25 | 🔁 | **9 份全 100%**（A 是 35 份含 6 份未完成） | foundation |
| BC-26 | 脏字面量登记 | AC-26 | ⚠️ | 占位符 `XX` + `【`；**无 `××` 全角** | foundation |
| BC-27 | 「原底稿」空格形态穷举 | AC-27 | ❌ | 空分母（同 BC-24） | — |
| BC-28 | `resolveProcedureSheetKey` 接入 | AC-28 | ✅ | 文件存在（15 引用）但 **B 分支 0**（同 A） | foundation |
| BC-29 | 行数口径 + 上游计数 | AC-29 | ✅ | 137 本 = 71 + 49 + 17 逐值吻合 AD-3 | foundation |
| BC-30 | `transport_key_resolution` | AC-30 | ❌ | abcs slice 无此节 | — |
| BC-31 | `parent_duplicate` 条件节 | AC-31 | ❌ | in-scope **0**（b60 docx-pane 已排除） | — |
| BC-32 | wp_code 与 Excel A1 引用同形 | AC-32 | ❌ | 超列引用 **0** | — |
| BC-33 | slice schema 校验器 | AC-33 | ⚠️ | 走追加节（同 A） | foundation |
| BC-34 | `conclusion` 是主载荷 | AC-34 | 🔁 | **反转：remark 强 / conclusion 弱**（17 : 1） | foundation |
| BC-35 | 超宽表 + 幽灵行列 | AC-35 | ⚠️ | 幽灵 **335 行 / 2 列**（历轮最极端） | foundation |
| BC-36 | footer 形态（禁用 openpyxl） | AC-36 | ⚠️ | 全 `&C&P/&N` 统一；**xlsm 也有 footer** | foundation |
| BC-37 | prefill 分母 | AC-37 | ✅ | **4** / 1 文件 | foundation |
| BC-38 | docx 权威册按 format 分流 | AC-38 | ❌ | `workbook_format` **10/10 为 null** | — |
| BC-39 | docx 合并单元格定位去重 | AC-39 | ✅ | merged **65% ~ 85%** | foundation |
| BC-40 | 公式行数超数据行数致除零 | AC-40 | ❌ | 公式格仅 **3**，无此形态 | — |
| BC-41 | mode 载体二分 | AC-41 | 🔁 | **三体系混用** + 第四值 `'polish'` | foundation |
| BC-42 | 持久化在 import 闭包（深度 3） | AC-42 | ✅ | 宿主内只得 2 ⇒ 假阴 **8 / 10（80%）** | foundation |
| BC-43 | entry_groups 二维分组可复算 | AC-43 | ⚠️ | GRP-04 **9** + GRP-05 **1** | foundation |
| BC-44 | 册↔entry 双射降级为单射 | AC-44 | 🔁 | **B 域 0 归属**（137 本全 excluded） | foundation |
| BC-45 | 单宿主多 componentType | AC-45 | 🔁 | **对偶形态：多 entry 共用一 wp_code**（`B22B`） | foundation |
| BC-46 | BP-6 归因更正 | AC-46 | ⚠️ | **第三种失败模式：抛 `FileNotFoundError`** | foundation |
| BC-47 | slice 自相矛盾 | AC-47 | ⚠️ | `label_as_key_sites` **漏登 1 处**（`#L1499`） | foundation |
| BC-48 | Property 22 分母 | AC-48 | ⚠️ | 站点 **5**（全正确形态）+ label-key **4** + 写死 peer | foundation |
| BC-49 | xlsm 宏层双重丢失 | — | ➕ | **17** 本全含 `vbaProject.bin`；警告影响 **16 / 66** | foundation（判据）+ lane3 |
| BC-50 | 一码多册歧义 | — | ➕ | **6 组**，`B22A` **11 本** | foundation（判据）+ lane2 |
| BC-51 | override 表把 sheet 名当 wp_code | — | ➕ | 中文名 wp_code **5 个全解析失败** | foundation |
| BC-52 | 解析失败三模式 | — | ➕ | 可解析 **11** / 不可解析 **11**（精确 50%） | foundation |
| BC-53 | 函数参数式行下标（新缺陷族） | — | ➕ | `rowIndex` **2** + `idx` **36** = **38** | foundation（判据）+ lane2 + lane3 |
| BC-54 | `count` 键与位置化行键配套 | — | ➕ | 前端 **13** / 3 文件；真库 3 种 count 键 | foundation（判据）+ lane2 |
| BC-55 | `wp_index` 一码多行 | — | ➕ | 10 码 → **26** 行（`B23`/`B50` 各 4） | foundation |
| BC-56 | 两种位置化编号基准并存 | — | ➕ | `row-0`（0-based）vs `env-def-1`（1-based） | foundation（判据）+ lane2 |
| BC-57 | strict 正则须 `^GtB\d` | — | ➕ | 误命中 **3** + 漏 **4**；域内未纳入 **14** | foundation |
| BC-58 | 载体三分即改线单元 | — | ➕ | orphan **1** 个载体 / 3 条 entry | foundation |
| BC-59 | canary 载荷是预置参考文本落库 | — | ➕ | `b22aReference.ts` 命中；空白新增行 **6** 键 | foundation |
| BC-60 | entry 级真库分母分布极不均 | — | ➕ | B22C 23 / B22A 21 / B22B 13 / B23 2 / **B50 0** | foundation |

**编号完整性（逐条数表格得出，禁凭印象）**：BC-1 ~ BC-60 连续无缺号、无重号，判定分布 **12 + 13 + 10 + 13 + 12 = 60** ✓

| 判定 | 条数 | 编号 |
|---|---|---|
| ✅ 沿用 | **12** | BC-4 / 6 / 11 / 12 / 13 / 19 / 20 / 28 / 29 / 37 / 39 / 42 |
| ⚠️ 变形 | **13** | BC-1 / 3 / 10 / 14 / 15 / 26 / 33 / 35 / 36 / 43 / 46 / 47 / 48 |
| 🔁 反转 | **10** | BC-2 / 5 / 7 / 8 / 18 / 25 / 34 / 41 / 44 / 45 |
| ❌ 不适用 | **13** | BC-9 / 16 / 17 / 21 / 22 / 23 / 24 / 27 / 30 / 31 / 32 / 38 / 40 |
| ➕ 新增 | **12** | BC-49 ~ BC-60 |

对照 A 轮（AC-1 ~ AC-48）：✅ 8 · ⚠️ 13 · 🔁 5 · ❌ 11 · ➕ 11 = 48。

🔴 **🔁 反转 10 条是历轮最多**（A 轮 5 条、N 轮更少）。10 条反转分三类根因：

1. **A 域空分母在 B 域非空**（BC-7 `removeRow` 4 处 · BC-5 strict 分支）
2. **B 域缺陷形态与 A/N 根本不同**（BC-2 载体三分 · BC-8 函数参数式 · BC-41 mode 三体系 · BC-45 多 entry 共用一码）
3. **B 域业务性质导致结论反向**（BC-34 remark 强而非 conclusion · BC-44 零册归属 · BC-25 归档全绿 · BC-18 canary 硬标准收回）

## 四、canary 选型：第四轮态度是「收回硬标准」

### 4.1 四轮态度轨迹（必须一并写明，避免后人误读为口径漂移）

| 轮次 | 硬标准（真库非空载荷）是否可用 | 实际动作 |
|---|---|---|
| K / L | 可用 | 建立硬标准 |
| M | 分母为空 | **第一次偏离**（换判据） |
| N | 分母非空 | **收回**（回到硬标准） |
| A | 唯一命中是 E2E seed | **第二次偏离** |
| **B（本轮）** | **分母非空且非 seed** | **收回（第二次收回）** |

### 4.2 B 域真库分母（现算，按 entry 细分）

| bucket | rows | remark 非空 | conclusion 非空 | wp 实例 |
|---|---|---|---|---|
| `B22C`（`gt-b22-c-design-effectiveness`） | **23** | 7 | **1** | 1 |
| `B22A`（`gt-b22-a-control-matrix`） | **21** | **9** | 0 | 1 |
| `B22B`（`gt-b22-b-control-matrix` 与 `gt-b22-b-deficiency-evaluation` 共用） | 13 | 1 | 0 | 1 |
| `B60`（pilot，已交付） | 4 | 4 | 0 | 2 |
| `B23`（`gt-b23-process-control`） | 2 | 2 | 0 | 1 |
| `B1*`（`gt-b1-*` 三条 + `gt-b14-*`） | **1** | 1 | 0 | 1 |
| `B50`（`gt-b50-risk-assessment`） | **0** | — | — | **0** |

全部载荷归属同一项目 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，每个 wp_code 各 1 个 wp 实例。

### 4.3 canary 定为 `xlsx/gt-b22-a-control-matrix`

选型依据（逐条可核）：

1. **remark 非空 9 条，全 B 域最多**（B22C 虽 23 行但 remark 仅 7）
2. **既存测试基础设施已在**：`B22A-T1-item` 在 3 个既存前端测试中出现（`b22aControlMatrix.spec.ts` / `b22aControlMatrix.property.spec.ts` / `b22bControlMatrix.spec.ts`）
3. **归档 spec `b22a-control-matrix` 47/47 全绿**（历轮最大功能 spec）⇒ 功能层完备，只缺 sync 判据
4. **落在共享基类组**（5 条中的 1 条）⇒ canary 经验可直接复用到 lane2 剩余 4 条

### 4.4 BC-59：分母非空但须区分「预置落库」与「人工录入」

🔴 溯源实测发现 `B22A-T3-item-{1..6}-point` 的中文业务文本**同时出现在** `audit-platform/frontend/src/components/workpaper/composables/b22aReference.ts` ⇒ 这些载荷是**前端预置参考文本被落库**，不是审计人员手工录入。

但 `B22A-T3-item-7-{point,desc,method,ref,conclusion,nochange}` **6 个键值全为空** ⇒ 这是「用户新增了第 7 行但未填内容」⇒ **行数增加是真人工行为**。

⇒ 判据裁定：
- **分母非空成立**（落库行为真实发生过，非 seed 脚本产物 —— seed / 测试目录对 `B22A-T3-item` 零命中）
- **变异证明须用 `B22A-T3-item-7` 的空白新增行**，不得用预置文本行（改预置文本会被 `b22aReference.ts` 覆盖，变异无效）

## 五、BC-20 空分母清册（14 项结构性零，每项附现算证据）

| # | 项 | 分母 | 现算证据 |
|---|---|---|---|
| 1 | `definedName` | **0** | 8 本可解析 xlsx 全部 0/0（A 域 A3-3 是 261/190） |
| 2 | hidden sheet | **0** | 14 sheets 全 visible（A/N 都有 `GT_Custom`） |
| 3 | `#REF!` | **0** | 8 本册全 0 |
| 4 | 超列引用 | **0** | B 码带连字符不构成合法 A1 引用 |
| 5 | `publish-to-tb` | **0** | 10 宿主 + 深度 3 闭包均 0（同 A 域） |
| 6 | `trial-balance/writeback` | **0** | 已废端点，10 宿主 0 |
| 7 | `GtEntrySyncCapabilityNotice` | **0** | 10 宿主 0（同 A 域） |
| 8 | 半角括号册名 | **0** | 137 本全角括号 45、半角 0（A 域有半角） |
| 9 | 连续两空格册名 | **0** | 137 本 0（A 域 `A17-6  总结会` 有） |
| 10 | 小写 `Gtb` 前缀 | **0** | strict 域 24 个全大写（A 域有小写分支） |
| 11 | `××` 全角占位符 | **0** | docx 只有 `XX` 与 `【`（A 域有 `××`） |
| 12 | `workbook_format` | **0** | 10/10 为 `null` ⇒ BC-38 按 format 分流不适用 |
| 13 | 册 ↔ entry 归属 | **0** | 137 本全部带 `excluded_reason`（BP-8 全覆盖） |
| 14 | `B50` 真库载荷 | **0** | `gt-b50-risk-assessment` 零行（BC-60） |

**变异证明要求**：每项空分母须配一个「人造正样本能被扫出」的变异测试，否则无法区分「真的零」与「扫描器坏了」。BC-53 是这条纪律的反面教材 —— slice 明文警告照抄 N 轮扫描器会在 B 域得 0 命中并误判为「无缺陷」。

## 六、地基组件设计

### 6.1 B 域基线守卫（新建）

`backend/tests/workpaper_sync/test_b_cycle_baseline.py`

职责：把本 spec 的事实基线冻结成可复算断言。既存守卫 `test_task57_abcs_and_shared_migration.py`（2472 行）对 B 域 10 条 entry **零逐条断言**（`gt-b1-` / `gt-b14` / `gt-b22` / `gt-b23` / `gt-b50` 全 0 命中，仅 `b60` 7 处），故本轮是 B 域首次建立逐 entry 判据。

断言面：

| 组 | 断言内容 |
|---|---|
| entry 集合 | B 域 entry 恰 **10** 条，`entry_id` 逐值匹配；BP 归属逐条为 `[BP-1,2,3,4,5,7,8]` |
| 载体归属 | `useWpDualMode` 3 / 共享基类 5 / host_inline 2，且 `useWpDualMode` 的 `becomes_orphan_after_rewire` 为真 |
| 解析三模式 | 纯码 10 个可解析；中文名 5 个返回 `None`；`' B1-5 KAA检查表-业务承接'` 抛 `FileNotFoundError` |
| 目录册对账 | `wp_templates/B` = 137 本 = docx 71 + xlsx 49 + xlsm 17 |
| 空分母 | §五 的 14 项逐项为零，且各配变异正样本 |

### 6.2 行身份扫描器（新建，BC-53 核心）

`audit-platform/frontend/src/components/workpaper/__tests__/bCycleRowIdentity.spec.ts`

🔴 设计要点：**不得照抄 N 轮扫描器**。N 轮扫的是 `${ITEM_PREFIX}-${index}` 持久化键形态，该形态在 B 域命中 **0**。B 域须扫两类：

1. **函数参数式行下标**：形参名为 `rowIndex` / `idx` 且被用于索引 JSON 数组（`rowIndex` 2 处 / `idx` 36 处 = 38）
2. **label 作渲染 key**：`:key` 绑定到可编辑文本（`row.name` / `grp.label`，4 处）

扫描器自身须带**变异测试**：人造一个 `${PREFIX}-${index}` 样本应被 N 轮口径扫出、人造一个 `idx` 形参样本应被 B 轮口径扫出，两者互不遮蔽。

### 6.3 canary 改线（`xlsx/gt-b22-a-control-matrix`）

改线动作：

1. 宿主 `GtB22AControlMatrix.vue`（2661 行）的 OO 挂点从共享基类 `useWorkpaperEntryDualMode` 取 sheet 名，改为经权威源解析
2. 🔴 BC-50 制约：`props.wpCode || 'B22A'` 的 `B22A` 在模板目录有 **11 本**候选册，实测解析到 `B22A-4-1 IT概要.xlsx`（取决于 finder 内部排序）⇒ 改线须**显式指定册**而非依赖 finder 排序
3. 🔴 BC-55 制约：`wp_index` 中 `B22A` 有 **2** 行 ⇒ 须确定用哪一行
4. 共享基类保持向后兼容（26 条生产边中 B 域仅占 5，其他循环仍在用）

### 6.4 三层一致校验（平台铁律）

canary 涉及 `capability` 字段变更时，DB 迁移 + ORM `Mapped[]` + service 方法三处须同步，缺一即伪绿。本轮 canary 不新增列（`capability` 已存在），故只需校验 service 侧读写口径一致。

## 七、Property 清单（BF-P1 ~ BF-P34）

每条为可执行断言的最小命题，「现算值」列是本轮实测分母，「判据」列关联 BC 编号。

| Property | 命题 | 现算值 | 判据 |
|---|---|---|---|
| BF-P1 | B 域 in-scope entry 恰 10 条 | 10 | BC-1 |
| BF-P2 | 10 条的 `capability_target_blocked_by` 逐值相同，区分项为 0 | 唯一组合 1 个 | BC-1 |
| BF-P3 | 该组合恰 7 项 `[BP-1,2,3,4,5,7,8]` | 7 | BC-1 |
| BF-P4 | `dual_mode_carrier.switch_verdict` 全 `redeemable`（🔴 非 `ui_toolbar_gate` 下） | 10/10 | BC-1 |
| BF-P5 | `dual_mode_carrier.kind` 二分：薄封装 8 + 宿主内联 2 | 8 / 2 | BC-2 |
| BF-P6 | 载体三分须用 `shared_carrier_module` 细分薄封装 8 → 5 + 3 | 5 / 3 / 2 | BC-2 |
| BF-P7 | `useWpDualMode.ts` 全域边 3 == B 域边 3（成孤儿充要条件） | 3 == 3 | BC-58 |
| BF-P8 | `useWorkpaperEntryDualMode.ts` 全域边 26，B 域占 5 | 26 / 5 | BC-58 |
| BF-P9 | 另两个共享载体 B 域边均为 0 | 0 / 0 | BC-2 |
| BF-P10 | `group_id` 分布 GRP-04 9 + GRP-05 1 | 9 / 1 | BC-43 |
| BF-P11 | `host_path` 唯一数 10（无共宿主） | 10 | BC-45 |
| BF-P12 | `workbook_format` 全 `null` ⇒ 按 format 分流空分母 | 10/10 | BC-38 |
| BF-P13 | 目录册 137 = docx 71 + xlsx 49 + xlsm 17 | 137 | BC-29 |
| BF-P14 | 册 ↔ entry 归属为 0（全部带 `excluded_reason`） | 0 | BC-44 |
| BF-P15 | 一码多册 6 组，`B22A` 11 本 | 6 / 11 | BC-50 |
| BF-P16 | 纯码 10 个全部可解析 | 10/10 | BC-52 |
| BF-P17 | 中文名 wp_code 5 个全部返回 `None` | 5/5 | BC-51 |
| BF-P18 | manifest 的 6 个 pattern 全部返回 `None` | 6/6 | BC-15 |
| BF-P19 | 前导空格 sheet 名抛 `FileNotFoundError`（第三种失败模式） | 1 | BC-46 |
| BF-P20 | 可解析 11 / 不可解析 11（精确 50%） | 11 : 11 | BC-52 |
| BF-P21 | `wp_index` 10 码全存在且全 n ≥ 2，合计 26 行 | 26 | BC-55 |
| BF-P22 | OO 挂点 10 · segmented 11 · mode 门控 10 · radio 0 | 10/11/10/0 | BC-13 |
| BF-P23 | 独立 DOM 扫描与 slice `ui_toolbar_gate` 站点数三项逐值一致 | 3/3 中 | BC-13 |
| BF-P24 | 仅自身口径门控假阴 3 条 | 3 | BC-13 |
| BF-P25 | `/checklist-responses` 深度 3 闭包命中 10，仅宿主命中 2（假阴 80%） | 10 / 2 | BC-42 |
| BF-P26 | mode 值三体系 + 第四值：中文 4 · `onlyoffice` 6 次 · `structured` 1 · `polish` 1 | 4/6/1/1 | BC-41 |
| BF-P27 | 仅 b14 在宿主内声明 `modeOptions`（3 处） | 1 / 3 | BC-41 |
| BF-P28 | 函数参数式行下标 38 处（`rowIndex` 2 + `idx` 36） | 38 | BC-53 |
| BF-P29 | N 轮形态（`${PREFIX}-${index}` / `row-${n}`）B 域命中 0，且该 0 不判为无缺陷 | 0 | BC-53 |
| BF-P30 | label 作渲染 key 4 处（slice 只登记 3，漏 `#L1499`） | 4 vs 3 | BC-47 |
| BF-P31 | remark 非空 17 > conclusion 非空 1（与 N / A 反转） | 17 : 1 | BC-34 |
| BF-P32 | B60 pilot 同样 conclusion 0（反转是全域性质） | 0 | BC-34 |
| BF-P33 | entry 级真库分母极不均，`B50` 为 0 | 23/21/13/2/1/0 | BC-60 |
| BF-P34 | 跨 entry 污染 0（item_id 前缀与 wp_code 全对齐） | 0 | BC-19 |

**编号完整性**：BF-P1 ~ BF-P34 连续 **34** 条，无缺号无重号，每条关联至少一个 BC 编号。

## 八、守卫测试类映射

| 测试类 | Property | 备注 |
|---|---|---|
| `TestBDomainSliceSplit` | BF-P1 ~ BF-P4 | B 域切分与全域同构性 |
| `TestCarrierTripartition` | BF-P5 ~ BF-P9 | 🔴 B 独有（载体三分须两字段联合现算） |
| `TestGroupAndHostMapping` | BF-P10 ~ BF-P12 | — |
| `TestTemplateDirectoryCensus` | BF-P13 ~ BF-P15 | 目录普查替代逐 entry 冻结（BP-8 全覆盖） |
| `TestResolutionThreeFailureModes` | BF-P16 ~ BF-P20 | 🔴 B 独有（须容忍 `None` 与异常两种失败） |
| `TestWpIndexMultiRow` | BF-P21 | 🔴 B 独有 |
| `TestModeGateAncestorChain` | BF-P22 ~ BF-P24 | 沿用 A 轮 AC-13 口径 + 与 slice 双向对账 |
| `TestPersistenceImportClosure` | BF-P25 | 沿用 A 轮 AC-42 口径 |
| `TestModeValueSystems` | BF-P26 ~ BF-P27 | 🔴 B 独有（三体系混用） |
| `TestRowIdentityFunctionParam` | BF-P28 ~ BF-P30 | 🔴 B 独有，须带双向变异测试 |
| `TestPayloadColumnReversal` | BF-P31 ~ BF-P33 | 🔴 反转 A / N 结论 |
| `TestCrossEntryIsolation` | BF-P34 | 对齐既存守卫同名类 |
