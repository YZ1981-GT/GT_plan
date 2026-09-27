# C22 ITGC 无开关与域码 sheet 名通道 — 任务

> 判据一律引用 `c-cycle-sync-foundation-and-first-canary` 的 CC 编号，本文件不重复裁决。
> 🔴 补开关（任务 2~5）是 BP-10 的前置硬约束，须在改裁 `bidirectional` 之前完成。

## 阶段 1：事实基线

- [ ] 1. 冻结本 entry 事实基线
  - 断言 `entry_id` = `xlsx/gt-c22-itgc-bundle`、宿主 922 行、`group_id` = GRP-06、family = `c_class_bundle`
  - 断言 `switch_verdict` = **`no_switch_at_all`**、`dual_mode_carrier.kind` = **`no_carrier`**
  - 断言 BP 数 **8** 且含 **BP-10**（全 slice 仅 4 条，本条是其一）
  - 断言 `wp_code_patterns` = `['C22I']` 但解析为 **`None`**；`wp_codes_via_component_type` = `['C22']`
  - 断言真库 **0** 行、import 闭包 **8** 册（全 C 域最小）、持久化在 **D0**
  - _判据：CC-2、CC-43、CC-42、CC-46、CC-60_

- [ ] 2. 补开关前置三条论证（禁跳过）
  - 论证一：`html_counterpart_verdict` 现算为 **`exists`**
  - 论证二：`find_template_file_any('C22')` → `C22 IT一般控制测试.xlsx` 可解析
  - 论证三：册内非空 —— **34** sheets / 公式格 **61** / 带 fx sheet **31**（全 C 域最多）/ `#REF!` **2**（全域仅此）
  - 🔴 结论须是「需要补开关」，禁以「没有开关」为由裁 `single_onlyoffice`
  - _判据：CC-41、CC-9、CC-32_

## 阶段 2：补模式开关（BP-10）

- [ ] 3. 补开关现状断言
  - 断言 `el-segmented` **0** · mode 门控 OO 挂点 **0** · mode 比较字面量 **0** · `ref<泛型>` **0** · 宿主内 `modeOptions` **未声明**
  - 断言与 slice `switch_verdict = no_switch_at_all` 逐值吻合
  - _判据：CC-41_

- [ ] 4. 补入开关（采用正确形态）
  - 采用 `{label, value}` 分离形态，🔴 **禁**引入中文标签直接作 mode 值（A 域 17 条踩过该坑）
  - mode 值用 `'structured'` 与 canary 侧的 `'online-edit'` 保持一致，🔴 **禁引入第五种体系**
  - OO 挂点须被 mode 门控（补完后祖先链或自身须含 mode 条件）
  - _判据：CC-41、CC-13_

- [ ] 5. 补完后回改 foundation 基线（🔴 同一 commit）
  - foundation 现算基线为「C 域 segmented **1** / mode 门控 **1**」，补完后变为 **2 / 2**
  - 🔴 须与 foundation 基线守卫**在同一 commit 内同步修改**，否则基线假红
  - 重新执行与 slice `ui_toolbar_gate` 四项的双向对账
  - _判据：CC-13、CC-11_

## 阶段 3：sheet 名解析

- [ ] 6. 命中 0 / 3 事实冻结
  - 断言传入 `'C21'` 对册 `C21 具有信息技术专业技能的项目组成员.xlsx`（sheet 名 `C21 具有信息技术专业技能的项目组成员` + `GT_Custom`）**不命中**
  - 断言传入 `'C21-1'` 对册 `C21-1  IT审计发现汇总表.xlsx`（sheet 名仅 **1** 个 `IT 审计发现汇总表`）**不命中**
  - 断言传入 `'C22'` 对册 `C22 IT一般控制测试.xlsx`（34 sheets）**不命中**
  - 🔴 断言两条机理：① 前缀不等于全名 ② **`C21-1` 册的 sheet 名与册名完全脱钩**（册名双空格、sheet 名单空格且无 `C21-1` 前缀）
  - _判据：CC-63、CC-10_

- [ ] 7. 🔴 裁决：方案 A 还是方案 B（须显式裁决，禁默认）
  - 方案 A：保持 OO 挂点加载 C21 / C21-1，只把传入值改为真实 sheet 名 —— 代价是 C22 册仍缺席链路
  - 方案 B：让 OO 挂点也能加载 C22 册 —— 须为 `matrix` / `group` tab 定义 sheet 映射，并裁定 C21 / C21-1 是否另立 entry
  - 🔴 裁决须产出「C22 册 **34** 个 sheet 各由哪个 tab 承载」的映射表，或显式声明「不承载」及理由
  - _判据：CC-63、CC-64_

- [ ] 8. 解析层实现（两方案共用）
  - sheet 名按**原始字面量**匹配，禁 `strip()`、禁全角半角归一化
  - 匹配失败给可诊断信息，区分「册不存在」「sheet 名不存在」「传入值是 wp_code 而非 sheet 名」三种
  - 🔴 **禁用前缀匹配兜底** —— `'C21'` 能前缀匹配到全名，但会掩盖传入值语义错误的根本问题
  - _判据：CC-63、CC-10、CC-52_

- [ ] 9. 权威册归属纠正登记（CC-64）
  - 断言 `activeDocTab` 只匹配 `kind === 'c21' || kind === 'c21-1'`（`#L269-274`）
  - 断言 OO 挂点只在 **2 / 4** 个 tab 上渲染（`matrix` / `group` 上 `activeDocTab` 为 `undefined`）
  - 🔴 断言 C21 / C21-1 两本册属 foundation 排除册清单（7 本之一）
  - 🔴 断言本 entry 权威册 `C22 IT一般控制测试.xlsx` **从未被 OO 侧加载过**
  - _判据：CC-64、CC-44_

## 阶段 4：命名空间与验证

- [ ] 10. 点号命名空间与共享边界（CC-15）
  - 断言 `item_id` 形态为 **`C22.{controlId}.{field}`**（点号分隔，与 canary 那条的连字符三段式不同）
  - 断言构造函数是 `itgcItemId()`，`GtC22ItgcBundle.vue#L323` 与 `GtC22ControlSheet.vue#L265` **共用**
  - 断言 `GtC22ControlSheet.vue#L191` 的 `prefix` 为 `` `C22.${controlId.value}.` ``
  - 🔴 断言这是**有意共享**（`#L312` 注释明写「与子页保持一致」），不是命名冲突
  - 🔴 断言排除理由须精确表述为「无 OO 挂点故不构成独立 sync entry」，**不可**表述为「与本 entry 无关」
  - _判据：CC-15_

- [ ] 11. 零分母人造数据验证（CC-60、CC-20）
  - 造人工数据：至少 **2** 个 controlId × **2** 个 field，以暴露键构造错误
  - 测试中显式声明「本 entry 真库分母为 0，验证基于人造数据」
  - 🔴 不得因分母为 0 而跳过验证
  - _判据：CC-60、CC-20_

- [ ] 12. 行身份空分母声明（CC-53、CC-6）
  - 断言本 entry 在 slice `dynamic_row_identity.tables` 中**无条目**（空分母）
  - 断言稳定身份 **4** 处全在本宿主：`:key="r.tab.id"`（`#L497`）/ `tab.id`（`#L642`）/ `activeControlTab.id`（`#L661`）/ `activeDocTab.id`（`#L687`）⇒ tab 级正面样板
  - 断言 `idx` 形参 / N 族 / M 式 / `rowIndex` / `$index` / 熵键 / label 作 key / removeRow / count 键 在本宿主全为 **0**
  - 配变异证明
  - _判据：CC-53、CC-6、CC-20_

- [ ] 13. 双向读写一致性
  - 结构化视图与 OO 视图读同一权威源
  - OO 侧写入后切回结构化视图能反映写入结果
  - 断言 tab 切换不丢失已填内容（tab 级身份是 `.id`，稳定）
  - _判据：CC-2、CC-6_

- [ ] 14. 回滚路径
  - `capability` 可从 `bidirectional` 退回 `null` 且不留脏数据
  - 🔴 补开关可独立回滚（与 capability 改裁解耦）
  - 回滚后 foundation 基线的 segmented / mode 门控数须同步回退
  - _判据：CC-2、CC-13_

## 外部依赖（本轮不可标 completed）

- [ ]* 15. BP-1 ~ BP-5、BP-7、BP-8 七项共有阻塞 —— 见 foundation tasks 29 ~ 35
- [ ]* 16. 本 entry 真实数据 UAT —— 真库 **0** 行，待真实项目数据
- [ ]* 17. 任务 7 的方案裁决若选 B —— 须业务侧确认 C21 / C21-1 与 C22 的底稿边界（跨 entry 归属调整）
