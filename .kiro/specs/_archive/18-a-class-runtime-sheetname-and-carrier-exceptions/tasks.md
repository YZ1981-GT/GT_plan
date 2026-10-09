# A 类运行时册名与载体例外车道 — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞。共同判据只引用 **AC 编号**，判据正文在 foundation。

🔴 **跨 spec 顺序硬约束**：任务 5（a3-console 补开关）须在 foundation 任务 5（载体二分判据）**之后**，且完成后须**回改 foundation 基线**（segmented 与 mode 门控 19 → 20）；任务 8（notice 接入）须在 foundation 任务 14 之后。

## 阶段 1 — 归属基线

- [x] 1. lane3 归属守卫
  - 落地 `design.md` 归属份额表全部 20 行，逐行与 foundation 算术自检表比对
  - 断言 3 条全名吻合 · BP-6/BP-8/BP-10 完整内聚 · BP 数 3×7 = **21**
  - 断言权威册 xlsx **1** + 无册 **2** · docx **0**；🔴 显式声明 AC-38 / AC-39（docx 相关）对本 spec **空分母**
  - 断言 OO 挂点 **3** · segmented **2** · mode 门控 **2** · 真库归属 **0** 行
  - 🔴 断言 AC-9/AC-40 的份额：本 spec 独占 A 域 `definedName` broken 的 **190/204 = 93%** 与 Property 22 全部 A 域站点（1/1）
  - _Requirements: 1_
  - _AC/AH-P: AC-1 · AC-13 · AC-20 · AH-P1 ~ AH-P5_

## 阶段 2 — BP-8 运行时册名（a177）

- [x] 2. 运行时 sheet 名解析建模
  - 断言 `resolution_kind` = `runtime_sheet_name_expression` · `workbook`/`workbook_format` 均 null · `sheet_name_exprs` = `["variant === 'team' ? 'A17-7' : 'A17-7A'"]`
  - 🔴 SHALL NOT 为其硬指权威册（slice `why_null` 明文「那是伪造 source_ref」）
  - 册解析推迟到运行时：由 `find_template_file_any(resolved_wp_code)` 在拿到 `variant` 后定位
  - _Requirements: 2_
  - _AC/AH-P: AC-44 · AH-P6_

- [x] 3. 变体轴显式化（契约须带 variant 维度）
  - 🔴 断言双变体 **A17-7（team）/ A17-7A（非 team）** 但 `wp_code_patterns` 只登记 **`A177I`** ⇒ 变体轴在 pattern 里丢失
  - 契约 SHALL 显式带 `variant` 维度，禁假设「一个 entry 对应一个 wp_code」
  - 断言全 slice BP-8 = **27** 条（literal 19 : runtime 27 = 46），A 域 **1** 条，其余 26 条归后续轮次
  - _Requirements: 2_
  - _AC/AH-P: AC-15 · AC-44 · AH-P7 · AH-P8_

- [x] 4. a177 门控与归档欠账
  - 🔴 断言其门控在**祖先的 v-else 链头**上（AC-13 三层嵌套形态之一），只看挂点自身会假阴
  - 登记归档欠账 `a17-7-independence-declaration` **20/21**（1 条）⇒ foundation 6 份欠账里归本 spec 的唯一 1 份（其余 5 份归 lane2）
  - 🔴 只登记不回填修改已归档 spec；扫归档区带 `errors="replace"`
  - _Requirements: 2_
  - _AC/AH-P: AC-13 · AC-25_

## 阶段 3 — BP-10 补开关（a3-console）

- [x] 5. 论证并补 segmented + mode 门控（须在 foundation 任务 5 之后）
  - 现读断言：`<el-segmented>` = **0** · mode 门控 = **0**，与 `no_carrier` / `no_switch_at_all` 吻合
  - 🔴 断言其 OO 挂点成因是 **sheet 路由兜底**而非 mode 门控 ⇒ 判据须区分两种挂点成因
  - 🔴 补开关前先落地三条论证：① `html_counterpart_verdict == 'exists'` ② `find_template_file_any('A3-3')` 返回真实路径 ③ 4 sheets / 63 公式格 ⇒ **需要双模式**；**禁以「没有开关」为由裁 `single_onlyoffice`**（AC 12.8）
  - 补开关直接用**形态 2**（`{label, value}` 分离，抄 a38 或 a112），🔴 禁新引入形态 1（中文标签作 mode 值）
  - _Requirements: 3_
  - _AC/AH-P: AC-2 · AC-41 · AH-P9 ~ AH-P11_

- [x] 6. 回改 foundation 基线（跨 spec 联动）
  - 🔴 补开关后全 A 域 segmented **19 → 20**、mode 门控 **19 → 20** ⇒ 须同步更新 foundation 的事实基线表与 AF-P13 断言
  - 🔴 两份 spec 的断言不得漂移，本任务须在同一 commit 内改两处
  - 断言 a3-console 第二形态 **`A3C` 打破规则**（按「去连字符 + 首字母」应为 `A33C`）⇒ 禁按规则推导第二形态
  - _Requirements: 3_
  - _AC/AH-P: AC-15 · AH-P12_

## 阶段 4 — BP-6 归因更正（a38）

- [x] 7. 实证并更正 BP-6 归因
  - 🔴 断言 `find_template_file_any('A3-8商誉减值测试')` → None **且 `find_template_file_any('A3-8')` → 也是 None**
  - 🔴 对照断言 `'A3-3'` / `'A5-1'` / `'A10-1'` **全部返回真实路径** ⇒ 证明解析器本身有效（变异证明）
  - 更正归因：真因是 `backend/wp_templates/A` 下**没有 `A3-8` 开头的册**，不只是 sheet 名写法问题
  - 登记 `sheet_name_literal` = **`A3-8商誉减值测试`**（码 + 中文连写）是 19 条 `literal_sheet_name` 里唯一异形
  - _Requirements: 4_
  - _AC/AH-P: AC-15 · AC-46 · AH-P13_

- [x] 8. BP-6 两步修复（顺序不可颠倒）
  - ① **先确认权威册是否存在** ⇒ 不存在则判为模板供给缺口：业务补册 **或** 显式声明该 entry 无权威册
  - ② 再改 `sheet_name_literal` 到纯码
  - 🔴 **只做 ② 解析仍返回 None** ⇒ 测试须先断言册不存在，再断言 sheet 名改动
  - 在 `design.md` 记录「补册」与「声明无册」两条路径的裁定与理由；收口后 BP-6 成员集变**全空集**（全 slice 仅 1 条）
  - _Requirements: 4_
  - _AC/AH-P: AC-46 · AH-P13_

## 阶段 5 — Property 22 与模板缺陷

- [x] 9. a38 的 Property 22 缺陷收口
  - 现读断言 `GtA38GoodwillImpairment.vue#L154`：`v-for="(_, i) in 5"`（写死 5 列）+ `key="i"`（裸下标）+ `label: \`第${i+1}年\`` ⇒ **两类缺陷同时命中**
  - 🔴 **两类同修**：① 列数改为数据驱动（预测期年数可配置，禁写死 5）② key 改为稳定 `{slot}_{seq}`（AC 6.4 原文），禁裸下标、禁可改 label
  - 🔴 登记张力：a38 在**模式层做对**（形态 2 是全域仅 2 个正面样板之一）却在**列层做错** ⇒ 证明「label/key 解耦」意识未贯穿全层
  - 修完后 A 域 Property 22 站点从 1 降至 **0**，但全 slice verdict 仍 **PARTIAL**（其余 3 条在 B 域）
  - _Requirements: 5_
  - _AC/AH-P: AC-41 · AC-48 · AH-P14 · AH-P15_

- [x] 10. `A3-3` 册缺陷台账（记录型，不改模板）
  - **T-1** AE7~AE15 恒 `#DIV/0!`（反向分母 **10 : 1**）；🔴 与 N 轮 NC-32 不同型（那里超 `max_column`，这里引空行），扫描器不可合并
  - **T-2** 首张 sheet 名码是 **`F6-10`** 而 wp_code 是 `A3-3` ⇒ 跨循环码混入，按原始字面量比对禁归一化
  - **T-3** `definedName` **261 / broken 190（73%）**，含 `_.dbf` / `_1固定资产数据库_筛选打印` / `_2其他资产_开办费除外_明细表` / `_3余额表_一级_.dbf` / `_00510` / `_1w6_` / `_13` / `_YE1` ⇒ dBase/Foxpro 残留，是 N 轮全域 4 倍
  - **T-15** 后三张 sheet 是**参考资料型**（0 公式格）⇒ 双向回写须排除
  - **T-16** `合并范围判断流程图（举例）` 幽灵行 **12**（max_row 45 vs last_value_row 33）⇒ 遍历上界取 last_value_row
  - **T-17** footer 读 raw XML：sheet1 = `第 &P 页，共 &N 页`（中文）· 其余 3 张无 `<headerFooter>` 元素
  - 🔴 本任务 SHALL NOT 修改 `A3-3` 册；交付后 sha256 须仍 match
  - _Requirements: 6_
  - _AC/AH-P: AC-9 · AC-10 · AC-21 · AC-36 · AC-40 · AC-44 · AH-P16_

## 阶段 6 — 收口

- [x] 11. BP-7 notice 接入 3 个宿主（须在 foundation 任务 14 之后）
  - 复用 foundation 已验证形态；🔴 tooltip 不算接线
  - _Requirements: 1_
  - _AC/AH-P: AC-12_

- [x] 12. 交付前自检
  - 归属份额表 20 行等式全过；AH-P1 ~ AH-P16 无缺号且每条关联 AC
  - sha256 仍 match；无 U+FFFD；「N 处」类表述与列举项数一致
  - 🔴 校验本 spec 未复述任何 AC 判据正文（只引编号）
  - 🔴 校验三处关键声明仍在：BP-6 两步顺序 · a3-console 禁裁 single 的三条论证 · foundation 基线回改（19→20）
  - _Requirements: 1, 6_
  - _AC/AH-P: AC-1 · AC-20 · AC-44_

- [x] 13.* 平台级与业务依赖欠账（登记型：欠账正确登记 + 可解部分已解）
  - **BP-1 ~ BP-5**（approved 模型 / contract / capability 裁决 / bundle 与 published / adapter 注册）：**平台层**阻塞，成员 **46/46**、status `open`，lane3 的 3 条只是子集 ⇒ 本 3-entry 车道无法单方解除，标 `[ ]*` 受阻（不标绿）
  - ~~🔴 BP-6 的第 ① 步依赖业务决策~~ → 🔴 **已解为非缺口**（Task 7/8 实证）：`A3-8` 合册一直在磁盘、解析层已修、宿主已收敛 ⇒「补册」与「声明无册」两条候选都不适用，不再是待决业务决策（见 errata E-1、design §Task 8/13）
  - `a17-7-independence-declaration` 归档 spec 的 1 条 Playwright E2E（5.2）须由对应功能 spec 负责人在真实浏览器环境补做；本 spec append-only 只登记不回填（归档仍 20/21）
  - 阻塞理由：平台层（BP-1~5）/ ~~业务决策~~已解（BP-6 step ①）/ 他人 spec 范围（a17-7 E2E）
  - 守卫：`TestTask13ExternalDebtRegistration`（8 例）；登记落地 design.md §Task 13 + errata.md E-1/E-2
  - _Requirements: 2, 4_
  - _AC/AH-P: AC-25 · AC-46_
