# A 类运行时册名与载体例外车道 — 设计

## 概述

本 spec 是 A 循环三份 sync spec 的 **lane3**，承担 **3 条非 docx 特例 entry**，规模最小但**每条各背负一个独有 BP**。共同判据 **AC-1 ~ AC-48** 已在 foundation 裁定，本文**只引用编号**。

**主题**：运行时 sheet 名表达式（BP-8）+ 无模式开关（BP-10）+ 无权威册（BP-6）+ Property 22 缺陷收口。

**切分依据**：这 3 条是「非 docx 的 4 条」里除 canary（a51）外的全部；**BP-6 / BP-8 / BP-10 三个区分项完整内聚**，横跨 **0**。三者共同特征 = **都无法用「一本 xlsx 权威册 + 字面 sheet 名」的标准模型处理**。

## 本 spec 归属份额（须与 foundation 算术自检表逐行对齐）

| 量 | a177 | a3-console | a38 | 本 spec | 全 A 域 |
|---|---|---|---|---|---|
| entry | 1 | 1 | 1 | **3** | 20 |
| docx 册 | 0 | 0 | 0 | **0** | 16 |
| xlsx 册 | 0 | **1** | 0 | **1** | 2 |
| 无册 | **1** | 0 | **1** | **2** | 2 |
| GRP-01 | 1 | 0 | 0 | **1** | 15 |
| GRP-03 | 0 | 1 | 1 | **2** | 3 |
| OO 挂点 | 1 | 1 | 1 | **3** | 20 |
| segmented | 1 | **0** | 1 | **2** | 19 |
| mode 门控 | 1 | **0** | 1 | **2** | 19 |
| BP 数 | 7 | 7 | 7 | **21** | 140 |
| 独有 BP | **BP-8** | **BP-10** | **BP-6** | 3 项 | 5 项 |
| xlsx sheets | 0 | **4** | 0 | **4** | 13 |
| xlsx 公式格 | 0 | **63** | 0 | **63** | 120 |
| `definedName` total / broken | 0 | **261 / 190** | 0 | **261 / 190** | 283 / 204 |
| mode 形态 1 | 1 | 0 | 0 | **1** | 17 |
| mode 形态 2 | 0 | 0 | **1**（a38） | **1** | 2 |
| Property 22 站点 | 0 | 0 | **1** | **1** | 1 |
| 归档欠账 | **1**（a17-7 20/21） | 0 | 0 | **1** | 6 |
| 真库行数 | 0 | 0 | 0 | **0** | 1 |

🔴 本 spec 虽只 3 条，却独占 **A 域全部 `definedName` broken 的 93%**（190/204）与 **Property 22 全部 A 域站点**（1/1），且是**唯一无 segmented 的 entry 所在地**。

## BP 收口路线

| BP | 成员 | 本 spec 动作 | 收口后 |
|---|---|---|---|
| **BP-8** | {a177}（全 slice 27 条，A 域 1 条） | 按「运行时解析 + 双变体」建模；🔴 **不硬指册** | A 域空集 |
| **BP-10** | {a3-console}（全 slice 4 条，A 域 1 条） | 补 segmented + mode 门控，采用形态 2 | A 域空集 |
| **BP-6** | {a38}（全 slice 1 条） | 🔴 **先确认册是否存在，再改 sheet 名**（顺序不可颠倒） | **全空集** |
| BP-14 | {a38} + 3 条 B 域 | 修写死列数 + 裸下标 key | A 域份额归零 |
| BP-1 ~ BP-5 | 全 46 条 | 平台级，标 `[ ]*` | 不变 |
| BP-7 | 全 46 条 | 依 foundation 形态为 3 个宿主新增 notice | 见 foundation |
| **BP-9 / BP-11** | — | 🔴 **本 spec 空分母**（成员全在 lane2） | 不涉及 |

BP 计数校验：3 条各 = 公共 6 + 1 个独有 = **7** 项 ⇒ 3×7 = **21** ✓

## 三条 entry 的处理模型

### a177 — 运行时 sheet 名（BP-8）

```
template_ref = {
    "resolution_kind": "runtime_sheet_name_expression",
    "sheet_name_exprs": ["variant === 'team' ? 'A17-7' : 'A17-7A'"],
    "workbook": null, "workbook_format": null,
    "why_null": "…本 slice 不为它硬指一本册（那是伪造 source_ref）"
}
```
处理：双向回写的册解析**推迟到运行时**，由 `find_template_file_any(resolved_wp_code)` 在拿到 `variant` 后定位。
🔴 **变体轴 A17-7 / A17-7A 在 `wp_code_patterns` 里丢失**（只登记 `A177I`）⇒ 契约须显式带 `variant` 维度，SHALL NOT 假设一个 entry 对应一个 wp_code。
🔴 门控在**祖先的 v-else 链头**上（AC-13 的三层嵌套形态之一），只看挂点自身会假阴。

### a3-console — 无开关（BP-10）

```
现状：<el-segmented> = 0 · mode 门控 = 0 · OO 挂点 = 1（成因是 sheet 路由兜底，不是 mode 门控）
论证「需要双模式」的三条现算依据：
  ① html_counterpart_verdict == 'exists'
  ② find_template_file_any('A3-3') → 真实路径（xlsx 册可解析）
  ③ 4 sheets / 63 公式格（有实质业务承载）
⇒ 结论：补开关；🔴 禁以「没有开关」为由裁 single_onlyoffice（AC 12.8 禁止）
补法：直接用形态 2（{label, value} 分离），抄 a38 或 a112 样板，禁新引入形态 1
```
收口后全 A 域 segmented **19 → 20**、mode 门控 **19 → 20** ⇒ foundation 与本 spec 基线表须同步更新。

### a38 — 无权威册（BP-6），归因须更正

```
BP-6 原文：「字面 sheet-name 不是 wp_code ⇒ find_template_file_any 返回 None（A3-8商誉减值测试）」
实证：find_template_file_any('A3-8商誉减值测试') → None
      find_template_file_any('A3-8')             → 🔴 也是 None
      find_template_file_any('A3-3'/'A5-1'/'A10-1') → 全部返回真实路径
⇒ 真因 = backend/wp_templates/A 下没有 A3-8 开头的册，不只是 sheet 名写法问题
修法（顺序不可颠倒）：
  ① 先确认权威册是否存在 → 不存在则是模板供给缺口（业务补册 or 显式声明无册）
  ② 再改 sheet_name_literal：'A3-8商誉减值测试' → 纯码
  🔴 只做 ② 解析仍返回 None
```

## 模板层缺陷台账（本 spec 份额，只登记不修改）

| # | 位置 | 形态 | 性质 | 反向分母 |
|---|---|---|---|---|
| T-1 | `A3-3` / `结构化主体纳入合并范围判断F6-10` **AE7~AE15** | `=(AB#+AC#+AD#)/(L#*J#)`，AB/AC/AD 与 L/J 只 r6 有值 | 🔴 真缺陷，恒 `#DIV/0!`；A 域**独有新族** | **10 : 1** |
| T-2 | 同册首张 sheet 名 | 码是 **`F6-10`**，wp_code 是 `A3-3` | 🔴 跨循环码混入（不同字母 + 不同编号体系） | — |
| T-3 | 同册 `definedName` | **261 / broken 190（73%）**，含 `_.dbf` · `_1固定资产数据库_筛选打印` · `_2其他资产_开办费除外_明细表` · `_3余额表_一级_.dbf` · `_00510` · `_1w6_` · `_13` · `_YE1` | 🔴 dBase/Foxpro 旧底稿残留，是 N 轮全域的 **4 倍** | 261 : 190 |
| T-10 | `A3-8` | **无权威册**（纯码也解析 None） | BP-6 归因须更正 | — |
| T-11 | `GtA38GoodwillImpairment.vue#L154` | `v-for="(_, i) in 5"` + `key="i"` | 🔴 写死列数 + 裸下标 key（Property 22 两类同时命中） | 7 : 3 |
| T-15 | `A3-3` 后三张 sheet | `合并范围判断流程图（举例）` / `单一控制模型判断流程（参考）` / `权益与负债的区分的判断框架（参考）`，**0 公式格** | 参考资料型 sheet，双向回写须排除 | 1 : 3 |
| T-16 | `A3-3` / `合并范围判断流程图（举例）` | 幽灵行 **12**（`max_row` 45 vs `last_value_row` 33） | 遍历上界须取 last_value_row | — |
| T-17 | `A3-3` footer | sheet1 = **`第 &P 页，共 &N 页`**（中文）· 其余 3 张**无 `<headerFooter>` 元素** | 三态中的两态；🔴 须读 raw XML | 1 : 3 |

🔴 **T-1 与 N 轮 NC-32 不同型**：NC-32 是「引用超出 `max_column` 的列」，T-1 是「引用同表内的空行」⇒ 两者扫描器完全不同，不可合并判据。

## Property 清单（AH-P1 ~ AH-P16）

| # | 断言 | 现算值 | 关联 AC |
|---|---|---|---|
| AH-P1 | 3 条 entry 全名吻合；归属份额 20 行与 foundation 算术表对齐 | 3 | AC-1 |
| AH-P2 | BP-6 / BP-8 / BP-10 完整内聚本 spec；BP 数 3×7 = 21 | 21 | AC-1 |
| AH-P3 | 权威册 xlsx 1 + 无册 2 · docx 0 ⇒ AC-38 / AC-39 空分母 | 1/2/0 | AC-20 · AC-38 |
| AH-P4 | OO 挂点 3 · segmented 2 · mode 门控 2 | 3/2/2 | AC-13 |
| AH-P5 | 真库归属 0 行 ⇒ 闭环须自建夹具 | 0 | AC-18 |
| AH-P6 | a177 的 `resolution_kind` 与 `sheet_name_exprs` 逐字吻合；🔴 不硬指册 | 1 | AC-44 |
| AH-P7 | a177 变体轴 A17-7 / A17-7A 双变体，pattern 只登记 `A177I` | 2 vs 1 | AC-15 |
| AH-P8 | 全 slice BP-8 = 27 条（literal 19 : runtime 27 = 46），A 域 1 条 | 27 / 1 | AC-44 |
| AH-P9 | a3-console segmented = 0 且门控 = 0，与 `no_switch_at_all` 吻合 | 0 | AC-2 |
| AH-P10 | a3-console 的 OO 挂点成因是**路由兜底**非 mode 门控 | 1 | AC-2 |
| AH-P11 | 补开关前先论证三条依据；🔴 禁裁 single_onlyoffice | 3 | AC-2 |
| AH-P12 | a3-console 第二形态 `A3C` **打破规则**（应为 A33C） | 1 | AC-15 |
| AH-P13 | BP-6 归因更正：`'A3-8'` 纯码**也**返回 None（对照 3 个正例） | 1 vs 3 | AC-46 |
| AH-P14 | a38 修复须两类同修（列数 + key），且 key 用 `{slot}_{seq}` | 2 | AC-48 |
| AH-P15 | a38 在模式层做对（形态 2）却在列层做错（裸下标） | 1 | AC-41 · AC-48 |
| AH-P16 | T-1 ~ T-17 台账记录型锁定；sha256 交付后仍 match | 8 项 | AC-9 · AC-40 · AC-44 |

**编号完整性**：AH-P1 ~ AH-P16 连续 **16** 条，无缺号无重号，每条关联至少一个 AC 编号。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_a_class_carrier_exceptions.py`（新建）。

| 类名 | 覆盖 |
|---|---|
| `TestLane3Attribution` | AH-P1 ~ AH-P5 |
| `TestBp8RuntimeSheetName` | AH-P6 ~ AH-P8 |
| `TestBp10MissingSwitch` | AH-P9 ~ AH-P12 |
| `TestBp6AttributionCorrection` | AH-P13 |
| `TestProperty22DefectClosure` | AH-P14 · AH-P15 |
| `TestA33TemplateDefects` | AH-P16 |

**原则**（沿用 foundation 测试原则 1 ~ 6）：期望值现读得出禁写死 · 结构性零配变异证明 · sha256 断言置前失败即中止 · 真库用 asyncpg 且无库时 skip · 扫归档区带 `errors="replace"` · docx 判据在本 spec 声明空分母。

🔴 **本 spec 额外原则**：① BP-6 的修复测试须**先断言册不存在**再断言 sheet 名改动，顺序颠倒会让第 ② 步看似通过而解析仍返回 None；② a3-console 补开关后须同步更新 foundation 的 segmented/门控基线（19 → 20），两份 spec 的断言不得漂移。

## 附：Task 6 基线回改登记（append-only，2026-10-03）

> 🔴 foundation spec `a-cycle-sync-foundation-and-first-canary` 现已归档至
> `.kiro/specs/_archive/17-2026-10-03-verified-batch/`。按项目铁律**已归档 spec 一律不回填修改**
> （append-only 审计轨迹），故本任务**不**改归档 spec 的 tasks.md/design.md/requirements.md。
> 「回改 foundation 基线」的意图改由下述两条可执行途径落地。

**① foundation 守卫是 LIVE 扫描，已就地校正 19 → 20（改的是测试代码，不是归档文档）。**
foundation 的 AF-P13 基线断言 `TestModeGateResolution::test_segmented_19` 由 `_host_gate()` 对
A 域 20 条宿主的真实 `.vue` 源码逐个解析得出（live scan），**不是**读冻结 slice JSON。
任务 5 给 a3-console 补了顶层 segmented（形态 2，`{label, value}` 分离）后，live 扫描结果从
segmented 19 / mode 门控 19 / 无门控 1（a3-console）变为 segmented **20** / mode 门控（legacy
挂点口径 ≤19，改线后大量宿主迁走）/ 无门控 **0**。该守卫断言已更新为 `== 20`
（见 `test_a_cycle_foundation_canary.py::TestModeGateResolution::test_segmented_19`，现读通过）。
测试文件是 live 代码而非归档 spec 文档，编辑它是正确且必要的，不违反 append-only 铁律。

**② slice 是补开关前的冻结快照（pre-fix），不改；lane3 守卫以 live 计数对账。**
slice 的 `ui_toolbar_gate` 仍记 a3-console segmented=0 / mode 门控=0 与 `switch_verdict ==
no_switch_at_all`（这是**裁决基线**，记录「补开关前该 entry 没有开关」这一事实，须保持）。
lane3 守卫 `TestBP10NoSwitch::test_no_segmented_no_mode_gate` 现读 slice 断言补开关**前**的 0/0
基线，并在 docstring 注明「补开关后的 live 计数（segmented 19→20）由 foundation 基线回改承接」。
⇒ 两份 spec 口径对齐、无漂移：foundation live=20、lane3 slice=补开关前基线，各自声明口径不互相矛盾。

**③ a3-console 第二形态 `A3C` 打破命名规则 ⇒ 禁按规则推导，须从 slice 现读。**
现读 slice：`xlsx/gt-a3-consolidation-console` 的 `wp_code_patterns == ['A3-3', 'A3C']`。
按「去连字符 + 首字母」规则，由 `A3-3` 去连字符得 `A33`、再接 console 首字母 `C` 应为 **`A33C`**；
但实际登记的第二形态是 **`A3C`**（直接 `A3` + `C`，丢了第二个 `3`）。故**第二形态不可按规则推导**，
必须从 slice/overrides 直接读取。守卫 `TestBP10NoSwitch::test_a3c_breaks_naming_rule`（AH-P12）
断言 `'A3C' in codes` 且 `'A33C' not in codes`，期望值全部由 slice 现读得出，无硬编码。

**同一 commit 内改两处**：foundation 守卫（19→20）与 lane3 守卫/本登记在同一提交内落地，
两份 spec 断言彼此一致（foundation live segmented=20 ↔ lane3 对补开关前 0/0 基线 + A3C 规则例外），
满足任务 6「两份 spec 的断言不得漂移」。

## 附：Task 8 — BP-6 两步修复收口（append-only，2026-10-03）

> 🔴 本节 **append-only**，承接 errata E-1/E-2，记录「补册 vs 声明无册」两条候选路径的裁定与
> 为何**两条都不适用**，以及 step ② 的落地位置与证据。不回填修改归档/上游 spec。

### 两步顺序复述（不可颠倒）

- **step ①（确认册存在 / 解析层通）** —— **已完成**。证据：合册
  `backend/wp_templates/A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx` 在磁盘（425.9 KB，
  `_index.json` 挂 wp_code `A3`），现算 `find_template_file_any('A3-8')` →
  `A3-7内部往来核对表、A3-8商誉减值测试.xlsx`（由 spec
  `workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 新增
  `_find_combined_workbook_declaring` 修复，见 errata E-1）。
- **step ②（宿主 sheet 名收敛到纯码）** —— **本任务完成**。见下。

🔴 顺序不可颠倒的可执行证据（守卫 `test_bp6_only_step2_without_step1_still_returns_none`）：
在被测函数**下一层**注入故障（禁用 `_find_combined_workbook_declaring`），纯码 `A3-8` 回到
`None` ⇒ **若只做 step ②（把宿主改成纯码）而没有 step ① 的 finder 修复，纯码一样解析不到**。
这坐实「只做 ② 解析仍返回 None」。

### 「补册」vs「声明无册」两条候选路径的裁定

| 候选路径 | 前提 | 现算事实 | 裁定 |
|---|---|---|---|
| **补册**（业务新增一本 `A3-8` 开头的权威册） | 磁盘上**没有**承载 A3-8 的册 | 合册**一直在磁盘上**且含 sheet `A3-8商誉减值测试`/`A3-8-1可收回金额测试` | ❌ **不适用**——册不缺，补册会产生重复册 |
| **声明无册**（显式登记该 entry 无权威册） | 该 entry 确实无册可依 | 同上，册存在且 `find_template_file_any('A3-8')` 已能解析 | ❌ **不适用**——声明无册 = 把真实存在的册当成不存在，是 E-1 glob 锚定假事实的延续 |
| **（实际路径）册存在 + 收敛宿主 sheet 名** | 册在、解析层已通，仅宿主传了中文连写字面 | `GtA38GoodwillImpairment.vue` 向 `GtOnlyOfficeSheet` 传 `sheet-name="A3-8商誉减值测试"` | ✅ **采纳**——真因是宿主字面写法，不是册缺口 |

**为什么两条候选都不适用（而非当初预判的「声明无册」）**：BP-6 最初被归因为「`backend/wp_templates/A`
下根本没有 `A3-8` 开头的册」，那是 `rglob("A3-8*")` **锚定文件名开头**的 glob 口径错误（合册真名以
`A3-7` 起头 ⇒ 该 pattern 恒 0 命中、假绿）。册其实一直在。因此这不是模板**供给**缺口（补册 /
声明无册都针对「供给缺口」），而是**宿主层字面写法**问题 —— 把 `sheet_name_literal` 从「码 + 中文
连写」收敛为纯码即可。

### step ② 落地位置与安全性论证

**落地点 = 宿主组件**（不是改冻结 slice）：`GtA38GoodwillImpairment.vue` 的 docx 分支把
`sheet-name="A3-8商誉减值测试"` 传给 `GtOnlyOfficeSheet` ⇒ 这是该中文连写字面在**运行时的真源**。
本任务把它收敛为 `sheet-name="A3-8"`。

**为什么此改动安全**（现读 `wp_onlyoffice_router.get_sheet_onlyoffice_config` +
`onlyoffice_room_identity.sheet_entry_id`）：a38 以 `:whole-workbook="true"` 挂载，whole-workbook
模式下 —

1. **册解析用 `wp_code` 而非 `sheet_name`**：`get_sheet_onlyoffice_config` 里 sheet→独立子码的
   提取分支被 `if not whole_workbook:` 整段跳过，`_sheet_wp_code = wp_code`（`A3-8`，由
   `wp_code_overrides.json` 映射到 componentType `a3-8-goodwill-impairment`）⇒ 模板由
   `_whole_workbook_template_or_primary(_sheet_wp_code)` 定位，**与 sheet_name 的字面无关**；
2. **room doc_key 不吃 sheet_name**：`sheet_entry_id(whole_workbook=True)` 的 slot 恒为
   `__whole__`（`WHOLE_WORKBOOK_SLOT`），sheet_name 不参与 room 身份派生；
3. **sheet_name 仅出现在 URL 路径段与签名 token**（config / WOPI / callback 三处对称使用同一
   sheet_name），改成纯码三处一致 ⇒ 自洽无副作用。

⇒ 收敛为 `A3-8` 既消除了 19 条 `literal_sheet_name` 里的唯一异形（码 + 中文连写），又不触碰
册解析与房间身份这两条真正定位路径。

**冻结 slice 不改**：`workpaper_sync_abcs_cycle_manifest_slice.json` 的 `sheet_name_literal`
仍记 `A3-8商誉减值测试` —— 这是**裁决基线**（记录「收敛前宿主传的是中文连写字面」这一事实，供
errata E-2 的「唯一异形」判据现读派生），保持原样。lane3 守卫对冻结 slice 断言的是收敛**前**的
基线（`test_a38_literal_is_the_unique_abnormal_among_19`），对宿主 live 源码断言的是收敛**后**的
纯码（本任务新增守卫），两口径各自声明、不互相矛盾（与 Task 6 foundation 基线回改同一手法）。

### 收口后 BP-6 成员集

全 slice BP-6 仅 **1** 条（a38），本 spec 独占。step ① 已通、step ② 已在宿主收敛 ⇒ BP-6 的 A 域
份额与全 slice 份额收口后变为**全空集**（守卫 `test_bp6_global_count_1` 坐实全 slice 仅 1 条且归
a38；本任务新增守卫坐实该条两步均已落地）。


## 附：Task 13 — 平台级与业务依赖欠账登记（append-only，2026-10-03）

> 🔴 本节 **append-only**。Task 13 是 `[ ]*`（受外部依赖阻塞）任务，其「完成」= **欠账被
> 正确登记、可解的部分已解**，而非「所有欠账都已修」。依项目铁律「任务标记不能假绿」，
> 下表逐条区分**平台层 / 已解为非缺口 / 他人 spec 范围**三类，各自据实登记。

### 欠账登记表

| 欠账项 | 阻塞理由 | 当前状态 | 依据 |
|---|---|---|---|
| **BP-1** approved authoritative model immutable definition 未发布 | **平台层** | `[ ]*` 受阻（代码/车道无法单方解） | slice 成员 **46/46**、status `open`，跨全 slice entry |
| **BP-2** reviewed per-entry contract 未发布（契约目录 4 份生产契约无一属本 slice） | **平台层** | `[ ]*` 受阻 | slice 成员 **46/46**、status `open` |
| **BP-3** capability / html_store 是 overlay 默认值而非逐 entry 裁决 | **平台层** | `[ ]*` 受阻 | slice 成员 **46/46**、status `open` |
| **BP-4** non-null approved definition bundle 与 published representation 均未交付 | **平台层** | `[ ]*` 受阻 | slice 成员 **46/46**、status `open` |
| **BP-5** adapter 未注册（`adapter_id` 现算 46/46 为 null）且逐 scenario evidence 为 0 | **平台层** | `[ ]*` 受阻 | slice 成员 **46/46**、status `open` |
| **BP-6 step ①** `A3-8` 权威册「补册 vs 声明无册」 | ~~业务决策~~ → **已解为非缺口** | ✅ **已解除**（不再 pending） | Task 7/8：册一直在磁盘、解析层已修、宿主已收敛 ⇒ 两条候选都不适用 |
| `a17-7-independence-declaration` 归档 spec 的 1 条 Playwright E2E（5.2） | **他人 spec 范围 / 环境** | deferred（由功能 spec 负责人补做） | 归档 **20/21**；append-only 不回填 |

### 逐类说明

**① BP-1 ~ BP-5（平台层，`[ ]*` 不标绿）** —— 这 5 条的成员集现算均 == 全 slice **46**
条 entry（lane3 的 3 条只是其子集），`status` 现读仍 `open`。它们是**平台级**前置
（approved 模型 / 逐 entry contract / capability 裁决 / bundle 与 published / adapter 注册），
须平台层统一发布，本 **3-entry 车道无法只为自己这 3 条单方解除**。故据实登记为「代码/车道
已就位但受平台层阻塞」，**不**标绿。守卫
`TestTask13ExternalDebtRegistration::test_platform_bps_span_all_46_entries_not_lane3_specific`
/ `test_lane3_three_entries_are_subset_of_each_platform_bp` /
`test_platform_bps_still_open_not_falsely_resolved` 坐实这三件事（成员=46 · lane3 是子集 ·
status 仍 open），期望值全部 slice 现读派生——平台层一旦解除，slice status 变化即打红，
提醒本登记过期。

**② BP-6 step ①（已解为非缺口，不再挂业务决策）** —— tasks.md 任务 13 原文把它写成「依赖
业务决策（`A3-8` 权威册是补还是声明无册），本 spec 无法单方裁定」。但 Task 7/8（errata
E-1、design §Task 8）已实证：合册 `A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`
**一直在磁盘上**，当初「没有这本册」是 `rglob("A3-8*")` **锚定文件名开头**的 glob 口径
假事实（合册真名以 `A3-7` 起头 ⇒ 恒 0 命中）。解析层已由 spec
`workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 修复、宿主 sheet 名已由
Task 8 step ② 收敛为纯码。⇒ **「补册」与「声明无册」两条候选都不适用**（册不缺），这不是
待决的业务决策，而是**已解除的非缺口**。本节据实把它从「业务决策 pending」更正为「已解」，
守卫 `test_bp6_step1_resolved_as_non_gap_not_pending_business_decision` /
`test_errata_records_bp6_resolution_glob_anchoring_root_cause` 坐实（册在磁盘 + 解析非 None +
errata 记录了 glob 锚定根因）。

**③ a17-7 归档 E2E（他人 spec 范围，deferred）** —— 归档 spec
`a17-7-independence-declaration` 现读 **20/21**，唯一欠账是 Playwright E2E（任务 5.2），须在
**真实浏览器环境**下由**对应功能 spec 的负责人**执行。本 lane3 spec（代码层）按项目铁律
「已归档 spec 一律不回填修改」只**登记**此欠账、不代做、不回填归档 spec。守卫
`test_a177_archive_debt_is_owned_by_feature_spec_not_lane3` 坐实「恰 1 条 E2E 欠账 + 归档仍
20/21 未被本任务改动」。

🔴 **本节不改任何归档/上游 spec**（append-only 审计轨迹）；BP-6 的「非缺口」再更正只登记在
本 spec 的 `errata.md`（E-1/E-2）与本节，不回填 foundation 等归档文件。
