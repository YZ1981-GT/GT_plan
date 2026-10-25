# C22 ITGC 无开关与域码 sheet 名通道 — 设计

## 定位

本 spec 是 C 循环两份 sync spec 的 **lane**，承担 `xlsx/gt-c22-itgc-bundle` 一条 entry。

共同判据一律引用 `c-cycle-sync-foundation-and-first-canary` 的 **CC-1 ~ CC-68**，本文件不重复裁决，只写本条特有的落地设计。

## 一、宿主结构现算

### 1.1 tab 四分（`#L199`）

`kind: 'matrix' | 'group' | 'c21' | 'c21-1'`

| kind | 含义 | 有 `wpCode` | 出现在 OO 挂点 |
|---|---|---|---|
| `matrix` | ITGC 控制矩阵总览（`#L211`） | 否 | 否 |
| `group` | ITGC 分组（`ItgcGroupKey`，`#L214`） | 否 | 否 |
| `c21` | C21 IT 专业成员（`#L218`） | **是** | **是** |
| `c21-1` | C21-1 IT 发现汇总（`#L221`） | **是** | **是** |

### 1.2 OO 挂点的实际条件（`#L269-274`、`#L686-690`）

```
activeDocTab = visibleTabs.find(t => t.id === active && (t.kind === 'c21' || t.kind === 'c21-1'))
模板：v-if="activeDocTab && subWpId(activeDocTab)"
      :sheet-name="activeDocTab.wpCode || ''"
```

⇒ OO 挂点**只在 c21 / c21-1 两个 tab 上渲染**；`matrix` / `group` tab 上 `activeDocTab` 为 `undefined`，挂点不渲染。

### 1.3 CC-63 / CC-64：sheet 名命中 0 / 3（决定性事实）

| 传入 sheet 名 | 加载的册 | 册内真实 sheet 名 | 命中 |
|---|---|---|---|
| `'C21'` | `C21 具有信息技术专业技能的项目组成员.xlsx` | `C21 具有信息技术专业技能的项目组成员` + `GT_Custom`（2 个） | ❌ |
| `'C21-1'` | `C21-1  IT审计发现汇总表.xlsx` | `IT 审计发现汇总表`（**1 个**） | ❌ |
| `'C22'` | `C22 IT一般控制测试.xlsx` | `C22 IT一般控制测试` + 33 个 ITGC 域码（34 个） | ❌ |

三项均不命中。两条机理：

1. **前缀不等于全名**：`'C21'` 是 `'C21 具有信息技术专业技能的项目组成员'` 的前缀，但 sheet 名匹配要求全等
2. 🔴 **`C21-1` 册的 sheet 名与册名完全脱钩**：册名是 `C21-1  IT审计发现汇总表`（两个连续空格），sheet 名是 `IT 审计发现汇总表`（单空格且**无 `C21-1` 前缀**）

### 1.4 权威册归属错误（CC-64）

本 entry 的 `wp_codes_via_component_type` = `['C22']`，对应册 `C22 IT一般控制测试.xlsx`。但 OO 挂点实际加载 `C21` / `C21-1` 两本册 —— 这两本在 foundation 的**排除册清单**（7 本）内。

⇒ **`C22 IT一般控制测试.xlsx`（34 sheets / 公式格 61 / 带 fx sheet 31 / `#REF!` 2）从未被 OO 侧加载过**，它在双向回写链路上完全缺席。

## 二、补开关设计（需求 1）

### 2.1 现状（CC-41）

| 项 | 现算值 |
|---|---|
| `el-segmented` | **0** |
| mode 门控 OO 挂点 | **0** |
| mode 比较字面量 | **0** |
| `ref<泛型>` | **0** |
| 宿主内 `modeOptions` | **未声明** |

⇒ 完全无 mode 概念，与 slice `switch_verdict = no_switch_at_all` 逐值吻合。

### 2.2 三条前置论证（抄 A 轮 lane3 对 `gt-a3-consolidation-console` 的处理路径）

BP-10 的 `must_fix_before` = 「任何 entry 从待裁决态改裁 bidirectional 之前」，且 A 轮已对同 BP 的另一条 entry 落地过论证路径，本条可直接沿用：

1. `html_counterpart_verdict` 现算为 **`exists`** ⇒ HTML 侧存在，不是「只有 OO」
2. 权威册可解析：`find_template_file_any('C22')` → `C22 IT一般控制测试.xlsx` ✅
3. 册内非空：**34** sheets / 公式格 **61** / 带 fx sheet **31**（全 C 域最多）

⇒ 结论是**需要补开关**，禁以「没有开关」为由裁 `single_onlyoffice`。

### 2.3 补法

采用 `{label, value}` 分离形态，禁引入中文标签直接作 mode 值（A 域 17 条踩过该坑）。mode 值取 `'structured'` 与 canary 侧的 `'online-edit'` 保持一致（CC-41 的第四体系已在 C 域出现，不再引入第五种）。

### 2.4 补完须回改 foundation 基线

foundation 基线断言「C 域 segmented **1** / mode 门控 **1**」（现算值）。补开关后变为 **2 / 2** ⇒ 🔴 **须与 foundation 基线在同一 commit 内同步修改**，否则基线守卫假红。

## 三、sheet 名解析设计（需求 2、3）

### 3.1 两种可选方案（须裁决）

| 方案 | 做法 | 代价 |
|---|---|---|
| **A** | 保持 OO 挂点加载 C21 / C21-1，但传入真实 sheet 名 | 简单；但 C22 册仍缺席链路，本 entry 的权威册名不副实 |
| **B** | 让 OO 挂点也能加载 C22 册（34 sheets） | 须为 `matrix` / `group` tab 定义 sheet 映射；须裁定 C21 / C21-1 是否另立 entry |

🔴 本 spec 不预设结论，把裁决作为独立任务（见 tasks.md 任务 7），要求裁决时给出「C22 册 34 个 sheet 各由哪个 tab 承载」的映射表或显式声明「不承载」。

### 3.2 解析层要求（两方案共用）

1. sheet 名按**原始字面量**匹配，禁 `strip()`、禁全角半角归一化（`C21-1` 册的 sheet 名 `IT 审计发现汇总表` 含单空格，册名含双空格）
2. 匹配失败须给可诊断信息，区分「册不存在」「sheet 名不存在」「传入值是 wp_code 而非 sheet 名」三种
3. 🔴 禁用「前缀匹配」兜底 —— `'C21'` 前缀能匹配到 `'C21 具有信息技术专业技能的项目组成员'`，但这会掩盖传入值语义错误的根本问题

## 四、命名空间共享边界（需求 4）

### 4.1 现状（CC-15）

| 组件 | 是否本轮 entry | `item_id` 构造 | 证据 |
|---|---|---|---|
| `GtC22ItgcBundle.vue` | **是** | `itgcItemId(controlId, field)` | `#L323`；`#L312` 注释「item_id = C22.{controlId}.{field}」 |
| `GtC22ControlSheet.vue` | 否（排除组件） | `itgcItemId(controlId.value, field)` | `#L265`；`#L16` 注释指向 `useC22BundleState.itgcItemId`；`#L191` `prefix = \`C22.${controlId.value}.\`` |

两者**共用同一函数与同一命名空间**，注释明写「与子页保持一致」⇒ **有意共享，不是冲突**。

### 4.2 改动纪律

1. 改 `itgcItemId()` 须同时回归两个组件
2. `GtC22ControlSheet.vue` 虽在 foundation 的排除清单（因 OO 挂点 **0**），但它**不是无关组件** —— 它是本 entry 的子页
3. 🔴 排除理由须精确表述为「无 OO 挂点故不构成独立 sync entry」，**不可**表述为「与本 entry 无关」

### 4.3 零分母验证

真库该命名空间 **0** 行 ⇒ 验证须造人工数据（至少 2 个 controlId × 2 个 field 以暴露键构造错误），并在测试中显式声明「本 entry 真库分母为 0，验证基于人造数据」。

## 五、Property 清单（CG-P1 ~ CG-P16）

| Property | 命题 | 现算值 | 判据 |
|---|---|---|---|
| CG-P1 | 本 entry `switch_verdict` 为 `no_switch_at_all` | 1 | CC-2 |
| CG-P2 | `dual_mode_carrier.kind` 为 `no_carrier` | 1 | CC-2 |
| CG-P3 | BP 数为 8 且含 BP-10 | 8 | CC-43 |
| CG-P4 | BP-10 全 slice 仅 4 条，本条是其一 | 4 | CC-43 |
| CG-P5 | segmented / mode 门控 / mode 字面量 / ref 泛型 全为 0 | 0×4 | CC-41 |
| CG-P6 | 宿主内未声明 `modeOptions` | 0 | CC-41 |
| CG-P7 | tab 四分 `matrix`/`group`/`c21`/`c21-1` | 4 | CC-64 |
| CG-P8 | OO 挂点只在 c21 / c21-1 两个 tab 渲染 | 2 / 4 | CC-64 |
| CG-P9 | 传入 sheet 名命中册内 sheet 名 0 / 3 | 0 | CC-63 |
| CG-P10 | `C21-1` 册 sheet 名与册名完全脱钩 | 1 | CC-63 / CC-10 |
| CG-P11 | 本 entry 权威册 `C22 IT一般控制测试.xlsx` 从未被 OO 加载 | 0 | CC-64 |
| CG-P12 | 该册 34 sheets / 公式格 61 / 带 fx sheet 31 / `#REF!` 2 | 34 | CC-9 / CC-32 |
| CG-P13 | `item_id` 用点号 `C22.{controlId}.{field}` | 1 | CC-15 |
| CG-P14 | 与 `GtC22ControlSheet.vue` 共用同一命名空间（有意共享） | 2 | CC-15 |
| CG-P15 | 持久化在 D0（宿主内直调），闭包 8 册 | D0 / 8 | CC-42 |
| CG-P16 | 真库 0 行 ⇒ 验证须人造数据并声明前提 | 0 | CC-60 / CC-20 |

**编号完整性**：CG-P1 ~ CG-P16 连续 **16** 条，无缺号无重号。
