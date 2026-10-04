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
