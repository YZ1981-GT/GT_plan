# C 循环双向回写地基与首张 canary — 设计

## 定位

本 spec 是 C 循环（控制测试）两份 sync spec 的**地基层**：一次性裁定 CC-1 ~ CC-68 共同判据、锁定 2 条 entry 的事实基线、落地首张 canary（`xlsx/gt-c-control-test`）。lane spec 只引用 CC 编号。

## 一、拆分裁决：为什么是 2 份而不是 1 份或 3 份

### 1.1 两条 entry 的形态对照（现算，非推演）

| 维度 | `xlsx/gt-c-control-test` | `xlsx/gt-c22-itgc-bundle` | 是否相反 |
|---|---|---|---|
| `wp_code_patterns` | **空数组**（pattern_less） | `['C22I']` | ✅ |
| 真实 wp_code 数 | **28** | **1** | ✅ |
| `component_type_family` | `control_test_router` | `c_class_bundle` | ✅ |
| `group_id` | GRP-07 | GRP-06 | ✅ |
| `dual_mode_carrier.kind` | `host_inline_segmented` | **`no_carrier`** | ✅ |
| `switch_verdict` | `redeemable` | **`no_switch_at_all`** | ✅ |
| BP 数 | 7 | **8**（多 **BP-10**） | ✅ |
| segmented 站点 | 1 | **0** | ✅ |
| mode 门控 OO 挂点 | 1 | **0** | ✅ |
| mode 值体系 | `'structured'` / `'online-edit'` | **完全无 mode 概念** | ✅ |
| 真库行数 | **136**（4 循环 × 34） | **0** | ✅ |
| `checklist` 通道深度 | D1（`useCControlTestData.ts`） | **D0**（宿主内直调） | ✅ |
| import 闭包规模 | **35** 册 | **8** 册 | ✅ |
| `item_id` 分隔符 | **连字符** `C{n}-{层}-{序号}-{字段}` | **点号** `C22.{controlId}.{field}` | ✅ |
| 行身份 | `step.num` 业务键（**CLEAN**） | 该节**无条目**（空分母） | ✅ |
| OCR 通道 | **75** 处 | 0 | ✅ |
| 权威册归属 | 29 本明确 | 🔴 **加载的是被排除的 C21/C21-1 册** | ✅ |

**14 / 14 个维度全部相反**，无任何共同缺陷可共享改线动作。

### 1.2 为什么不是 1 份

两条 entry 的改线**前置条件根本不同**：

- `gt-c22-itgc-bundle` 背负 **BP-10**（`no_switch_at_all`），slice 明文 `must_fix_before` = 「任何 entry 从待裁决态改裁 bidirectional 之前」⇒ **必须先补模式开关**才能谈双向
- `gt-c-control-test` 是 `redeemable`（开关已存在且已被 mode 门控）⇒ 直接进入回写改造

合成一份会让「补开关」与「改回写」两条不同性质的工作混在同一任务序列里，且 C22 的阻塞会拖住 canary。

### 1.3 为什么不是 3 份

C 域只有 **2** 条 in-scope entry，第 3 份无 entry 可分。`pattern_less` 另 4 条经 override 反查已裁归其他轮次（见 requirements.md 排除边界 A），不可为凑份数硬塞。

### 1.4 分配

| spec | entry | n |
|---|---|---|
| `c-cycle-sync-foundation-and-first-canary`（本份） | `xlsx/gt-c-control-test`（canary） | **1** |
| `c22-itgc-no-switch-and-domain-code-sheet-lane` | `xlsx/gt-c22-itgc-bundle` | **1** |

1 + 1 = **2** ✓

## 二、CC-1 ~ CC-68 共同裁决对照表

判定图例：✅ 沿用 · ⚠️ 变形（方向不变但锚点/口径须改）· ❌ 不适用（空分母）· 🔁 反转（B 轮结论在 C 被证伪）· ➕ 新增（C 独有）

| CC | 主题 | BC 基准 | 判定 | C 侧现算分母 | 归属 |
|---|---|---|---|---|---|
| CC-1 | slice 范围与域切分 | BC-1 | 🔁 | **首字母切域会漏主体** —— pattern_less 含 28 码 router | foundation |
| CC-2 | 载体族并存 | BC-2 | 🔁 | **载体二分且各 1 条**：`host_inline` 1 + **`no_carrier`** 1 | foundation |
| CC-3 | 端点字面量须认反引号 + 剥注释 | BC-3 | ⚠️ | checklist **1** · health **0** · publish-to-tb **0** | foundation |
| CC-4 | 确认门独立存在 | BC-4 | ❌ | `ElMessageBox.confirm` **0**（B 域 12） | — |
| CC-5 | strict 域须含小写前缀分支 | BC-5 | ❌ | 小写 `Gtc` **0**（B 域亦 0，连续两轮空分母） | — |
| CC-6 | 行身份正面样板 | BC-6 | ⚠️ | 稳定身份 **4** 处全在 C22（tab 级 `.id`） | foundation |
| CC-7 | `removeRow` 签名族 | BC-7 | ❌ | **0**（B 域 4） | — |
| CC-8 | 位置化族分类 | BC-8 | ❌ | A 族 0 · M 式 0 · `rowIndex` 形参 0 · `$index` 0 | — |
| CC-9 | `definedName` 断链登记 | BC-9 | 🔁 | **3514 / broken 2727 = 77.6%**，历轮最高（B 域空分母） | foundation |
| CC-10 | sheet 名禁归一化 | BC-10 | ⚠️ | 全角半角**同名内混用**（`选项清单列表（不归档） (2)`） | foundation |
| CC-11 | 扫描口径差须登记 | BC-11 | ✅ | 门控假阴 1 · `idx` 假阳 14 · step5 falsy 丢失 | foundation |
| CC-12 | notice 接线，tooltip 不算 | BC-12 | ✅ | **0**（同 A、B） | foundation |
| CC-13 | 门控判据（祖先链 × 递归回溯） | BC-13 | ✅ | 假阴 **1**；与 slice 四项**逐值全中** | foundation |
| CC-14 | `derived_total` 双正则 | BC-14 | ❌ | 冒号式 0 · `.reduce(` 0 | — |
| CC-15 | `item_id` / wp_code 命名轴 | BC-15 | 🔁 | **两条分隔符不同**：连字符 vs **点号** | foundation |
| CC-16 | localStorage mode 分区 | BC-16 | ❌ | 有 localStorage（D2/D3 auth）但**无 mode 键** | — |
| CC-17 | 「合计漏加小计」双条件 | BC-17 | ❌ | 无合计行形态 | — |
| CC-18 | canary 判据 | BC-18 | ✅ | **第三次收回硬标准**（真库 136 行） | foundation |
| CC-19 | 跨循环键 + 跨 entry 污染 | BC-19 | ✅ | 污染 **0**（7 组前缀与 wp_code 全对齐） | foundation |
| CC-20 | 空分母纪律 + 变异证明 | BC-20 | ✅ | 结构性零 **17** 项（见 §五） | foundation |
| CC-21 | 跨册复制残留 | BC-21 | 🔁 | **14 对 `-2` 册逐值一致** ⇒ 同模板复制 14 份 | foundation |
| CC-22 | 科目性质四分 | BC-22 | ❌ | C 类非科目底稿，无借贷方向 | — |
| CC-23 | `SHEET_MAP` 常量映射 | BC-23 | ❌ | C 域无此形态 | — |
| CC-24 | 历史 sheet 过滤 | BC-24 | ❌ | 册名与 sheet 名含「原底稿/历史」均 **0** | — |
| CC-25 | 已归档 spec 边界 | BC-25 | 🔁 | **7 份中 1 份欠 28 条**（`c-control-test-component` 25/53） | foundation |
| CC-26 | 脏字面量登记 | BC-26 | ⚠️ | 册名连续空格 **1** · sheet 名括号混用 **1** | foundation |
| CC-27 | 「原底稿」空格形态穷举 | BC-27 | ❌ | 空分母（同 CC-24） | — |
| CC-28 | `resolveProcedureSheetKey` 接入 | BC-28 | ✅ | 宿主内 **0**（同 A、B 三轮同态） | foundation |
| CC-29 | 行数口径 + 上游计数 | BC-29 | ✅ | 36 本 = xlsx 36 逐值吻合 AD-3 | foundation |
| CC-30 | `transport_key_resolution` | BC-30 | ❌ | abcs slice 无此节 | — |
| CC-31 | `parent_duplicate` 条件节 | BC-31 | ❌ | in-scope **0** | — |
| CC-32 | wp_code 与 Excel A1 引用同形 | BC-32 | 🔁 | 超列引用 **113**（B 域 0），须分族核验 | foundation |
| CC-33 | slice schema 校验器 | BC-33 | ⚠️ | 走追加节（同 A、B） | foundation |
| CC-34 | `conclusion` 是主载荷 | BC-34 | 🔁 | **双列均衡第三态**：conclusion 10 : remark 8 | foundation |
| CC-35 | 超宽表 + 幽灵行列 | BC-35 | ⚠️ | 本轮册最大 ghost **22 行**；域内 C24 达 **10141** | foundation |
| CC-36 | footer 形态（禁用 openpyxl） | BC-36 | ✅ | 三态 84 + 72 + 8 = 164；内容**只 1 种** `&C&P/&N` | foundation |
| CC-37 | prefill 分母 | BC-37 | ❌ | **0**（B 域 4） | — |
| CC-38 | docx 权威册按 format 分流 | BC-38 | ❌ | 36 本 **100% xlsx**（唯一纯 xlsx 域） | — |
| CC-39 | docx 合并单元格去重 | BC-39 | ❌ | 无 docx | — |
| CC-40 | 公式行数超数据行数致除零 | BC-40 | ❌ | 无此形态 | — |
| CC-41 | mode 载体体系 | BC-41 | 🔁 | **第四体系 `'online-edit'`**；另一条**完全无 mode** | foundation |
| CC-42 | 持久化在 import 闭包（深度 3） | BC-42 | ✅ | D0 **1** + D1 **1**；闭包 8 与 35 册 | foundation |
| CC-43 | entry_groups 二维分组可复算 | BC-43 | ⚠️ | GRP-06 **1** + GRP-07 **1**（各 1 条） | foundation |
| CC-44 | 册 ↔ entry 双射降级为单射 | BC-44 | 🔁 | 本轮 **29 本可归属**（B 域 0） | foundation |
| CC-45 | 单宿主多 componentType | BC-45 | 🔁 | **对偶再翻转：一 componentType 覆盖 28 码** | foundation |
| CC-46 | BP-6 归因更正 | BC-46 | ❌ | 解析 **29/29 全中**，无失败 | — |
| CC-47 | slice 自相矛盾 / 漏登 | BC-47 | ⚠️ | AD-9 与 override 反查**逐值吻合**（28/32/1/1/0） | foundation |
| CC-48 | Property 22 分母 | BC-48 | ❌ | C 域无动态列站点、无 label 作 key | — |
| CC-49 | xlsm 宏层双重丢失 | BC-49 | ❌ | xlsm **0** 本；数据验证警告 **0 / 36** | — |
| CC-50 | 一码多册歧义 | BC-50 | ❌ | **0** 组（B 域 6 组、B22A 11 本） | — |
| CC-51 | override 表把 sheet 名当 wp_code | BC-51 | ❌ | 29 码全是纯码，无中文名项 | — |
| CC-52 | 解析失败三模式 | BC-52 | ❌ | 29/29 全中；唯一失败是 manifest pattern `C22I` | — |
| CC-53 | 函数参数式行下标 | BC-53 | 🔁 | **须再分两类防假阳**：`idx` 14 处全属 UI 局部 | foundation |
| CC-54 | `count` 键与位置化行键配套 | BC-54 | ❌ | `count` 键 **0** | — |
| CC-55 | `wp_index` 一码多行 | BC-55 | ⚠️ | 29 码**全存在且全 n = 4**（B 域 2~4 不等） | foundation |
| CC-56 | 两种位置化编号基准并存 | BC-56 | ❌ | 无位置化行键（序号是业务控制点号） | — |
| CC-57 | strict 正则形态 | BC-57 | 🔁 | **`^GtC\d` 漏主体** ⇒ 须扩 `^GtC\d` ∪ `^GtC[A-Z]` | foundation |
| CC-58 | 载体轴即改线单元 | BC-58 | ❌ | 无共享载体（四个载体命中全 0） | — |
| CC-59 | canary 载荷须分预置落库与人工录入 | BC-59 | ⚠️ | 4 循环各 **34** 行，内容是真实审计文本 | foundation |
| CC-60 | entry 级真库分母极不均 | BC-60 | ⚠️ | 136 : **0**；且 28 码中 **10 个循环全 0** | foundation |
| CC-61 | 一 componentType 覆盖 N 个 wp_code | — | ➕ | **28** 码（AD-9 明文警告会漏 27 个） | foundation |
| CC-62 | 成对册缺陷完全不对称 | — | ➕ | 主册裸 IF **0**/dn **0** ｜ `-2` 册裸 IF **20**/dn **232-181** | foundation |
| CC-63 | 传入 sheet 名与册内 sheet 名零交集 | — | ➕ | 命中 **0 / 3**（`C21` / `C21-1` / `C22` 全不中） | foundation（判据）+ lane |
| CC-64 | OO 挂点加载的册不是本 entry 的册 | — | ➕ | C22 挂点实际加载 **C21 / C21-1**（均属排除册） | foundation（判据）+ lane |
| CC-65 | boolean falsy 值持久化丢失 | — | ➕ | `step5: boolean` 默认 `false` ⇒ 真库 **6 步只见 5 步** | foundation |
| CC-66 | 域内单册体量极端离群 | — | ➕ | `C24` 真库 **1,033,309 行 = 全库 99.87%** | foundation |
| CC-67 | 参考型 sheet 须排除 | — | ➕ | 3 种 × 14/14/12 次 = **40** sheets | foundation |
| CC-68 | `pattern_less` 归属须 override 反查 | — | ➕ | 反查 5 条得 28 / 1 / 32 / 1 / 0 码 | foundation |

**编号完整性（脚本逐条数表格得出，禁凭印象）**：CC-1 ~ CC-68 连续无缺号、无重号；**BC-1 ~ BC-60 全部被逐条重裁，零遗漏**；判定分布 **10 + 11 + 13 + 26 + 8 = 68** ✓

| 判定 | 条数 | 编号 |
|---|---|---|
| ✅ 沿用 | **10** | CC-11 / 12 / 13 / 18 / 19 / 20 / 28 / 29 / 36 / 42 |
| ⚠️ 变形 | **11** | CC-3 / 6 / 10 / 26 / 33 / 35 / 43 / 47 / 55 / 59 / 60 |
| 🔁 反转 | **13** | CC-1 / 2 / 9 / 15 / 21 / 25 / 32 / 34 / 41 / 44 / 45 / 53 / 57 |
| ❌ 不适用 | **26** | CC-4 / 5 / 7 / 8 / 14 / 16 / 17 / 22 / 23 / 24 / 27 / 30 / 31 / 37 / 38 / 39 / 40 / 46 / 48 / 49 / 50 / 51 / 52 / 54 / 56 / 58 |
| ➕ 新增 | **8** | CC-61 ~ CC-68 |

历轮对照：A 轮 ✅8 ⚠️13 🔁5 ❌11 ➕11 = 48 · B 轮 ✅12 ⚠️13 🔁10 ❌13 ➕12 = 60。

🔴🔴 **❌ 26 条与 🔁 13 条双双创历轮新高**（❌ 轨迹 N 1 → M 5 → A 11 → B 13 → **C 26**）。两项根因不同：

- **❌ 激增的根因是 C 域形态极简**：36 本册 **100% xlsx**（无 docx / 无 xlsm）⇒ 一次性排掉 CC-38/39/49；`removeRow` / `count` 键 / label 作 key / `prefill` / `confirm` / `derived_total` / 位置化行键**全为 0** ⇒ 再排 7 条；解析 **29/29 全中** ⇒ 排掉 BC 的整个「解析失败」族（CC-46/50/51/52）。这不是判据质量下降，而是**C 域本身干净**。
- **🔁 激增的根因是 C 域在多个维度上与 B 域恰好相反**：B 域空分母处 C 域非空（`definedName` 2727 / 超列 113 / 册可归属 29 本），B 域非空处 C 域空（xlsm / 一码多册 / 三失败模式）。

## 三、13 条反转逐条说明（🔁 必须显式声明）

| CC | B 轮结论 | C 轮证伪证据 |
|---|---|---|
| CC-1 | 按 slice 域切分即可 | **首字母切域漏主体** —— `gt-c-control-test` 的 `wp_code_patterns` 为空数组却覆盖 28 个 C 码 |
| CC-2 | 载体三分（5/3/2） | **载体二分且各 1 条**，其中一条是 `no_carrier`（B 域无此形态） |
| CC-9 | `definedName` 空分母 | **3514 / broken 2727 = 77.6%**，历轮最高 |
| CC-15 | 命名轴用连字符 | **两条 entry 分隔符不同**：`C{n}-{层}-{序号}-{字段}` vs **`C22.{controlId}.{field}`** |
| CC-21 | 跨册复制残留 1 处 | **14 对 `-2` 册数值逐值一致** ⇒ 整族同模板复制 |
| CC-25 | 归档 spec 9 份全 100% | **7 份中 1 份欠 28 条**（`c-control-test-component` 25/53，历轮最大单份欠账） |
| CC-32 | 超列引用 0 | **113 处**（其中 99 处在域内 `C24`，本轮册内 14 处） |
| CC-34 | remark 强 conclusion 弱（17:1） | **双列均衡第三态**（conclusion 10 : remark 8） |
| CC-41 | mode 值三体系 | **第四体系 `'online-edit'`**；且另一条**完全无 mode 概念** |
| CC-44 | 册 ↔ entry 归属 0 本 | **29 本可归属**（BP-8 在 C 域不构成阻塞） |
| CC-45 | 多 entry 共用一 wp_code | **对偶再翻转：一 componentType 覆盖 28 个 wp_code** |
| CC-53 | `idx` 形参即缺陷 | **须再分两类防假阳**：14 处全属内存与 UI 局部，`item_id` 模板串含 `idx` 为 **0** |
| CC-57 | strict 正则须 `^GtB\d` | **`^GtC\d` 会漏主体** —— `GtCControlTest.vue` 不带数字 |

## 四、canary 选型：第五轮态度是「第三次收回硬标准」

### 4.1 五轮态度轨迹（必须一并写明，避免后人误读为口径漂移）

| 轮次 | 硬标准（真库非空载荷）是否可用 | 实际动作 |
|---|---|---|
| K / L | 可用 | 建立硬标准 |
| M | 分母为空 | **第一次偏离** |
| N | 分母非空 | **第一次收回** |
| A | 唯一命中是 E2E seed | **第二次偏离** |
| B | 分母非空且非 seed | **第二次收回** |
| **C（本轮）** | **分母非空 136 行** | **第三次收回** |

### 4.2 C 域真库分母（现算，按 wp_code 分组）

| 分组 | rows | remark 非空 | conclusion 非空 | wp 实例 | 归属 |
|---|---|---|---|---|---|
| `C14` | 34 | 3 | 2 | 1 | 本轮（`gt-c-control-test`） |
| `C2` | 34 | 2 | 2 | 1 | 本轮 |
| `C15` | 34 | 1 | 2 | 1 | 本轮 |
| `C10` | 34 | 2 | 4 | 1 | 本轮 |
| **`C22`** | **0** | — | — | **0** | 本轮（lane 承担） |
| `C24` | **1,033,309** | 11 | 6 | 1 | 排除册 |
| `C23` | 266 | 4 | 6 | 1 | 排除册 |
| `C1` | 10 | 2 | 0 | 1 | 排除册 |

本轮 entry 合计 **136** 行（4 × 34），remark 非空 **8** / conclusion 非空 **10**。

🔴 28 码中只有 **4 个循环**（C2 / C10 / C14 / C15）有载荷，其余 **10 个循环**（C3~C9 / C11 / C12 / C13）与全部 14 个 `-2` 码真库为 **0** ⇒ CC-60 的「分母极不均」在 C 域是**码级**而非 entry 级。

### 4.3 canary 定为 `xlsx/gt-c-control-test`

选型依据（逐条可核）：

1. **真库 136 行，硬标准成立**（另一条 C22 为 0 行）
2. **载荷是真实审计业务文本**（CC-59）：`C14-dev-1-exceptionDesc` 为 118 B 中文实录（「控制点 C14 于 2023 年 Q3 期间出现例外，具体表现为 15 笔采购订单金额超过审批权限且未获补充授权……」），非预置参考文本、非 seed 标记
3. **行身份已是 CLEAN**（`step.num` 业务键）⇒ 闭环不必先做身份改造，比 B 轮 canary 门槛更低
4. **`switch_verdict` 是 `redeemable`**（另一条是 `no_switch_at_all`，须先补开关）⇒ 不被 BP-10 阻塞
5. **归档 spec 提供功能基础**（`c-control-test-component` 已完成 25 条 + 另 3 份 C 域 spec 100% 完成）

### 4.4 与 B 轮 canary 的判据差异

B 轮 BC-59 要求「变异证明须用空白新增行，因载荷是预置参考文本落库」。C 轮**不需要该绕道**：真库载荷已是人工录入的业务文本（依据见 4.3 第 2 点），可直接对现有行做变异。

## 五、CC-20 空分母清册（17 项结构性零，每项附现算证据）

| # | 项 | 分母 | 现算证据 |
|---|---|---|---|
| 1 | docx 册 | **0** | 36 本 100% `.xlsx`（唯一纯 xlsx 域） |
| 2 | xlsm 册 | **0** | 同上 |
| 3 | 数据验证扩展警告 | **0** | 0 / 36 本（B 域 16 / 66） |
| 4 | 一码多册 | **0** 组 | 36 本码前缀全 n = 1（B 域 6 组） |
| 5 | 解析失败 | **0** | 29 / 29 全中；唯一失败是 manifest pattern `C22I` |
| 6 | `ElMessageBox.confirm` | **0** | 2 宿主（B 域 12） |
| 7 | `prefill` | **0** | 2 宿主（B 域 4） |
| 8 | `publish-to-tb` | **0** | 2 宿主 + 深度 3 闭包（A、B 同为 0） |
| 9 | `GtEntrySyncCapabilityNotice` | **0** | 2 宿主（A、B 同为 0） |
| 10 | `onlyoffice/health` | **0** | 2 宿主（B 域 2） |
| 11 | `resolveProcedureSheetKey` | **0** | 2 宿主（A、B 三轮同态） |
| 12 | 四个共享载体 | **0** | `useWpDualMode` / `useWorkpaperEntryDualMode` / `useCycleHtmlOoDualMode` / `createDualMode` 全 0 |
| 13 | `removeRow` 家族 | **0** | 2 宿主（B 域 4） |
| 14 | `count` 键 | **0** | 2 宿主（B 域 13） |
| 15 | label 作渲染 key | **0** | 2 宿主（B 域 4） |
| 16 | 小写 `Gtc` 前缀 | **0** | strict 域内（B 域亦 0，连续两轮） |
| 17 | `C22` 真库载荷 | **0** | `checklist_responses` 零行 |

**变异证明要求**：每项须配「人造正样本能被扫出」的变异测试。🔴 CC-53 是反面教材的镜像 —— B 轮扫描器在 C 域会扫出 14 处 `idx` 但全是**假阳**，故扫描器须同时通过「B 域样本命中」与「C 域样本不命中」双向测试。

## 六、地基组件设计

### 6.1 C 域基线守卫（新建）

`backend/tests/workpaper_sync/test_c_cycle_baseline.py`

既存守卫 `test_task57_abcs_and_shared_migration.py`（2471 行 / 17 类 / 130 test）对 C 域覆盖极不均：`gt-c22` / `c22-itgc` / `C22I` / `itgc` / `GRP-06` / `GRP-07` / `control_test_router` **全 0 命中**（C22 零断言），`gt-c-control-test` 1 处 / `c-control-test` 7 处。本轮为 C22 首次建立断言。

断言面：

| 组 | 断言内容 |
|---|---|
| entry 集合 | C 域 in-scope 恰 **2** 条；`pattern_less` 另 4 条按 override 反查裁归其他轮次 |
| 一对多归属 | override 反查 `c-control-test` 得 **28** 码、`c22-itgc-bundle` 得 **1** 码 |
| 形态对照 | design.md §1.1 的 14 个维度逐项相反 |
| 模板册 | 36 本 = xlsx 36；本轮覆盖 **29** 本；排除 **7** 本各带理由 |
| 成对册 | 主册 14 本与 `-2` 册 14 本的六项指标逐值一致（同模板复制） |
| sheet 名命中 | 传入 `C21` / `C21-1` / `C22` 对册内 sheet 名命中 **0 / 3** |
| 空分母 | §五 的 **17** 项逐项为零，各配变异正样本 |

### 6.2 行身份扫描器（CC-53 核心，须双向变异）

`audit-platform/frontend/src/components/workpaper/__tests__/cCycleRowIdentity.spec.ts`

🔴 设计要点：**不得照抄 B 轮扫描器**。B 轮口径「存在 `idx` 形参即缺陷」在 C 域会命中 14 处**假阳**。C 域须按两类判定：

1. **类 A（缺陷）**：`idx` 出现在 `item_id` 构造或持久化键模板串中
2. **类 B（非缺陷）**：`idx` 仅作内存数组索引、`splice` 参数、弹窗打开参数、Dialog 标题插值

判定依据（现算证据）：`item_id` 模板串含 `idx` = **0** · `item_id` 赋值处含 `idx` = **0** · 持久化模块 `useCControlTestData.ts`（168 行）内 `idx`/`index` = **0**。

扫描器须同时通过双向变异：B 域样本（`idx` 进键）应命中、C 域样本（`idx` 仅 UI）应不命中。

### 6.3 boolean falsy 持久化（CC-65）

`DecisionTreeState`（`useDeviationDecisionTree.ts`，299 行）的 6 个 step 字段类型不一致：

| 字段 | 类型 | 默认值 |
|---|---|---|
| `step1` / `step4` / `step6` | `'是' \| '否' \| null` | `null` |
| `step2` | `'系统性偏差' \| '人为偏差' \| '随机性偏差' \| null` | `null` |
| `step3` | `'扩大样本量' \| '直接认定为偏差' \| null` | `null` |
| 🔴 **`step5`** | **`boolean`** | **`false`** |

真库现算只见 `step1` ~ `step4` 与 `step6`（**5 个**），`step5` 缺席。根因是 `false` 被按空值跳过 ⇒ **用户显式选「否」与「未填」不可区分**。

修复方向：持久化层区分 `undefined`（未填）与 `false`（显式否），或把 `step5` 改为与其他字段一致的三态字符串枚举。

### 6.4 canary 改线（`xlsx/gt-c-control-test`）

1. 宿主 `GtCControlTest.vue`（1719 行）的 OO 挂点 sheet 名表达式为 `sheetName || ''`，须经权威源解析而非裸变量
2. 🔴 CC-61 制约：一次改线须覆盖 **28** 个 wp_code，判据按主册族（14）与 `-2` 册族（14）分别断言
3. 🔴 CC-62 制约：`-2` 册族的 `definedName` broken 181 / 232（78%）与裸 IF 20 / 20（100%）是改线时的已知污染，只登记不在本轮修
4. 保留 `step.num` 业务键行身份（CC-53）
5. 🔴 OCR 通道 **75** 处是 C 域最大通道，改线不得破坏 OCR 文本与附件的行关联

## 七、Property 清单（CF-P1 ~ CF-P30）

| Property | 命题 | 现算值 | 判据 |
|---|---|---|---|
| CF-P1 | C 域 in-scope entry 恰 2 条 | 2 | CC-1 |
| CF-P2 | 按首字母切域只得 1 条，会漏主体 | 1 vs 2 | CC-1 |
| CF-P3 | override 反查 `c-control-test` 得 28 码 | 28 | CC-61 |
| CF-P4 | override 反查 `c22-itgc-bundle` 得 1 码 | 1 | CC-61 |
| CF-P5 | `pattern_less` 5 条反查得 28 / 1 / 32 / 1 / 0 | 5 | CC-68 |
| CF-P6 | `cash-flow-verification` 反查得 `A5` ⇒ 属 A 域 | 1 | CC-68 |
| CF-P7 | 两条 entry 的 14 个维度逐项相反 | 14 / 14 | CC-2 |
| CF-P8 | 载体二分各 1 条，其一为 `no_carrier` | 1 + 1 | CC-2 |
| CF-P9 | C22 的 BP 为 8 项且含 BP-10 | 8 | CC-43 |
| CF-P10 | 目录册 36 本 100% xlsx | 36 | CC-38 |
| CF-P11 | 本轮覆盖 29 本，排除 7 本各带理由 | 29 + 7 | CC-44 |
| CF-P12 | 解析 29 / 29 全中 | 29 | CC-52 |
| CF-P13 | manifest pattern `C22I` 解析为 None | 1 | CC-46 |
| CF-P14 | 成对册六项指标逐值一致（同模板复制 14 份） | 14 对 | CC-21 / CC-62 |
| CF-P15 | 主册裸 IF 0 / dn 0；`-2` 册裸 IF 20 / dn 232-181 | 对照 | CC-62 |
| CF-P16 | `definedName` 3514 / broken 2727 = 77.6% | 2727 | CC-9 |
| CF-P17 | broken 验算闭合：181×14 + 14 + 15 + 164 = 2727 | ✓ | CC-9 |
| CF-P18 | footer 三态 84 + 72 + 8 = 164，内容只 1 种 | 164 | CC-36 |
| CF-P19 | 参考型 sheet 3 种共 40 sheets 须排除 | 40 | CC-67 |
| CF-P20 | sheet 名全角半角同名内混用 1 处 | 1 | CC-10 |
| CF-P21 | 门控两条与 slice 四项逐值全中 | 4 / 4 | CC-13 |
| CF-P22 | 仅自身口径门控假阴 1 条 | 1 | CC-13 |
| CF-P23 | mode 第四体系 `'online-edit'`；另一条无 mode | 1 + 0 | CC-41 |
| CF-P24 | OCR 通道 75 处是 C 域最大通道 | 75 | CC-3 |
| CF-P25 | `idx` 形参 14 处全属类 B（非缺陷） | 14 | CC-53 |
| CF-P26 | `item_id` 模板串含 `idx` 为 0（三项证据） | 0 / 0 / 0 | CC-53 |
| CF-P27 | 两条 entry 的 `item_id` 分隔符不同 | `-` vs `.` | CC-15 |
| CF-P28 | 传入 sheet 名命中册内 sheet 名 0 / 3 | 0 | CC-63 / CC-64 |
| CF-P29 | `step5` 为 boolean 默认 false ⇒ 真库 6 步只见 5 步 | 5 / 6 | CC-65 |
| CF-P30 | 真库 136 : 0；28 码中 10 个循环全 0 | 136 / 0 | CC-60 |

**编号完整性**：CF-P1 ~ CF-P30 连续 **30** 条，无缺号无重号，每条关联至少一个 CC 编号。
