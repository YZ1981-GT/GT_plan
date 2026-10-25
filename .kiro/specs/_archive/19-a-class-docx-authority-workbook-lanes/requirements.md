# A 类 docx 权威册车道 — 需求

## 引言

**上游**：`a-cycle-sync-foundation-and-first-canary`（以下简称 **foundation**）已一次性裁定共同判据 **AC-1 ~ AC-48**，本 spec **只引用编号、不复述判据正文**。术语与口径（A 域切分 / strict 四路取并 / format 分流 / footer 读 raw XML / 门控递归回溯 / 计数现算纪律）一律沿用 foundation 的「术语与口径」节。

**本 spec 的 entry 范围**（**16** 条，全部权威册为 `.docx`）：

| entry_id | wp_code | group | channel | docx tables × cells | merged% |
|---|---|---|---|---|---|
| `xlsx/gt-a101-governance-communication` | A10-1 | GRP-01 | checklist | 10 × 36 | 53% |
| `xlsx/gt-a111-subsequent-events-inquiry` | A11-1 | GRP-01 | checklist | 1 × 8 | 63% |
| `xlsx/gt-a112-dual-checklist` | **A1-12** | **GRP-03** | field_ovr | 1 × 51 | **92%** |
| `xlsx/gt-a115-disclosure-checklist` | **A1-15** | **GRP-02** | 两通道 | **3 × 3174** | **99.5%** |
| `xlsx/gt-a121-legal-confirmation` | A12-1 | GRP-01 | checklist | 5 × 13 | 38% |
| `xlsx/gt-a171-audit-summary` | A17-1 | GRP-01 | checklist | **13 × 535** | 71% |
| `xlsx/gt-a1721-kam` | A17-2-1 | GRP-01 | checklist | 5 × 194 | 85% |
| `xlsx/gt-a173-consultation-record` | A17-3 | GRP-01 | checklist | 8 × 19 | 21% |
| `xlsx/gt-a1731-consultation-execution` | A17-3-1 | GRP-01 | checklist | 1 × 36 | 86% |
| `xlsx/gt-a174-disagreement-record` | A17-4 | GRP-01 | checklist | 4 × 53 | 70% |
| `xlsx/gt-a176-closing-meeting` | A17-6 | GRP-01 | checklist | 2 × 34 | 85% |
| `xlsx/gt-a181-regulatory-submission` | A18-1 | GRP-01 | checklist | **0 × 0** | — |
| `xlsx/gt-a182-regulatory-communication` | A18-2 | GRP-01 | checklist | 2 × 2 | 0% |
| `xlsx/gt-a271-it-audit-memo` | A27-1 | GRP-01 | checklist | 5 × 42 | 64% |
| `xlsx/gt-a81-other-info-representation` | A8-1 | GRP-01 | checklist | 1 × 1 | 0% |
| `xlsx/gt-a91-deficiency-letter` | A9-1 | **GRP-10** | checklist | 2 × 2 | 0% |

**切分依据**：本 spec 恰是 **BP-9 的完整成员集**，且现算 **`BP-9 集合 == docx 集合` 为 `True`**（16 == 16）⇒ 按 docx 轴切等价于按 BP-9 轴切，横跨 **0**。**BP-11（{a91}）也完整内聚本 spec**。

**Property 前缀**：本 spec 用 **AG-P**（foundation 用 AF-P，lane3 用 AH-P）。

## 需求

### Requirement 1 — entry 范围与归属算术

**用户故事**：作为维护者，我要确认本 spec 承担的份额与 foundation 算术自检表严格对齐。

#### 验收标准

1. WHEN 现算本 spec entry THEN SHALL 恰 **16** 条，全名逐一吻合上表，且 `template_ref.workbook_format` **全为 `docx`**。
2. WHEN 现算 BP 归属 THEN SHALL 满足：BP-9 **16/16 全覆盖** · BP-11 **1** 条（a91）· 公共 BP **6** 项对 16 条全成立 ⇒ BP 数 = 15×7 + 1×8 = **113**。
3. WHEN 现算 group 归属 THEN SHALL 为 GRP-01 **13** + GRP-02 **1**（a115）+ GRP-03 **1**（a112）+ GRP-10 **1**（a91）= **16**。
4. WHEN 现算 OO 挂点与门控 THEN SHALL 为挂点 **16** · segmented **16** · mode 门控 **16**（依 AC-13 的最终口径）⇒ 本 spec 内**无 no_switch 条目**。
5. WHEN 现算真库归属 THEN SHALL 为 **1** 行（`A17-1-ch01`，属 a171，`remark` 53 B，含 `（E2E seed）` 标记）⇒ 本 spec 的真实业务载荷仍为 **0**。
6. WHEN 现算 xlsx 相关量 THEN SHALL 全为 **0**（本 spec 无 xlsx 册）⇒ 公式格 / definedName / footer / 「合计」标签（xlsx 侧）等判据对本 spec **声明空分母**（依 AC-20）。

### Requirement 2 — docx 册按 format 分流读取（BP-9 收口主线）

**用户故事**：作为实施者，我要用正确的库读 Word 权威册，并且知道哪些 Excel 类判据在这里根本不成立。

#### 验收标准

1. 🔴 WHEN 读本 spec 的 16 本权威册 THEN SHALL 用 `python-docx`，SHALL NOT 用 `openpyxl`（实测抛 `InvalidFileException`，依 AC-38）。
2. 🔴 WHEN 编写判据 THEN SHALL NOT 出现「公式格计数」「`data_only=True` 反证」「超列引用」「裸 IF」「definedName 断链」「幽灵列」「footer 形态」等 Excel 专属项 —— 这些对 docx **无意义**，须显式声明空分母而非跑出 0 后宣称通过。
3. WHEN 现算 docx 结构量 THEN SHALL 逐册吻合上表的 `tables × cells`，且 tables 范围 **0 ~ 13**、非空段落 **2 ~ 213**、cells **0 ~ 3174**。
4. WHEN 现算 sections THEN SHALL 登记 **a171 与 a81 为 2**（含分节符），其余 14 条为 **1**。
5. WHEN 现算 sha256 THEN 本 spec 16 本册 SHALL 全部 match，交付后仍 match（🔴 SHALL NOT 修改任何 `.docx`，依 AC-44）。
6. WHEN BP-9 收口 THEN SHALL 给出 docx 侧的双向回写定位模型（见 Requirement 3），收口后 BP-9 成员集 SHALL 变为空集。

### Requirement 3 — 合并单元格定位去重（docx 侧核心难点）

**用户故事**：作为双向回写的实现者，我要避免把同一个合并单元格当成多个独立位置反复写入。

#### 验收标准

1. 🔴 WHEN 现算 `merged_refs` 比例 THEN SHALL 逐册吻合上表，最高为 `a115` **3159 / 3174 = 99.5%**，另有 a112 **92%** · a1731 **86%** · a176 **85%** · a1721 **85%** · a171 **71%** · a174 **70%**。
2. 🔴 WHEN 遍历 docx 表格 THEN SHALL 以 `<w:tc>` 对象标识去重（`id(cell._tc)`），SHALL NOT 假设 `(row, col)` 与 cell 一一对应 —— 否则 a115 的 3174 个 (row,col) 位置会被当成 3174 个独立可写位置，而真实只有 **15** 个不同的 `tc`。
3. WHEN 定义定位键 THEN SHALL 基于 `tc` 标识（或等价的 grid 起止坐标），并在守卫中锁定各册的 `merged_refs` 现值，变化时显式失败。
4. 🔴 WHEN 处理 `a115` 的 934 行巨表 THEN SHALL 登记为性能风险项，遍历须一次性建立 `tc → 逻辑位置` 映射而非逐格回查。
5. WHEN 处理零合并册 THEN SHALL 容忍 `merged_refs = 0`（a182 / a81 / a91 三条），判据 SHALL NOT 要求每册都有合并单元格。

### Requirement 4 — 纯信函型 entry 的结构异形

**用户故事**：作为守卫作者，我要让判据容忍「没有表格」的 entry，避免写出必假红的断言。

#### 验收标准

1. 🔴 WHEN 现算 `a181-regulatory-submission` THEN SHALL 为 **0 tables / 0 cells / 8 段落** ⇒ 「每 entry 有表格」判据必假，SHALL 按「表格数 ≥ 0」断言。
2. WHEN 现算 `a91-deficiency-letter` THEN SHALL 为 **2 个 1×1 表 + 29 段落** ⇒ 表格存在但无实际行列结构，双向回写须走**段落级**而非表格级定位。
3. WHEN 现算 `a81-other-info-representation` THEN SHALL 为 **1 个 1×1 表 + 34 段落**，同属段落级形态。
4. WHEN 设计定位模型 THEN SHALL 同时支持**表格级**（13 条）与**段落级**（a181 / a91 / a81 三条）两种路径，SHALL NOT 只实现前者。
5. 🔴 WHEN 现算 `a173-consultation-record` 首段 THEN SHALL 为 `【参考格式，但至少包括以下四方面要素。向专业技术部咨询时，应附有项目组的处理意见、项目质量控制复核（如有）意见和各办公室…` ⇒ **指引文字占据标题位**，「首段是标题」判据必假。

### Requirement 5 — 占位符与脏字面量登记（只登记不修改）

**用户故事**：作为审计业务负责人，我要知道 Word 模板里的填空标记有五种形态，且有一处字符缺陷。

#### 验收标准

1. WHEN 现算占位符 THEN SHALL 为**五形态**：`XX`（a181 **15** 处最多）· **`××` 全角**（a101 / a91）· **`【】`**（a101 **55** 处最多 · a171 38 · a271 16 · a1731 12 · a173 10）· `□`（a121 2 处）· `N/A`（a115 1 处）。
2. 🔴 WHEN 处理占位符 THEN SHALL 按**原始字面量**匹配，SHALL NOT 归一化全角半角（`XX` 与 `××` 是不同形态）。
3. 🔴 WHEN 登记字符缺陷 THEN `a91` 的 P2 段落含 **`20l×年12月31日`** —— 小写字母 `l` 冒充数字 `1` ⇒ 记录型断言锁定现状，🔴 **本 spec SHALL NOT 修改 `.docx`**。
4. 🔴 WHEN 登记示例公司名 THEN SHALL 为**两种并存**：`XX股份有限公司`（a171 / a181）vs `ABC公司` / `ABC股份有限公司`（a111 / a81）⇒ 文案不统一，登记不修。
5. WHEN 现算 docx 内「合计/小计」THEN SHALL 为 **9** 处（a101 **1** / a115 **8**），且**全部在首列** ⇒ AC-17 对本 spec 空分母。

### Requirement 6 — BP-11：单宿主承载两个 componentType

**用户故事**：作为架构维护者，我要处理 entry 与 componentType 非双射的唯一一条 entry。

#### 验收标准

1. 🔴 WHEN 现读 BP-11 THEN SHALL 确认 `a9-1-deficiency-letter` 与 `a9-2-deficiency-letter-governance` **两个 componentType 都解析到 `GtA91DeficiencyLetter.vue`** ⇒ entry ↔ componentType **非双射**。
2. 🔴 WHEN 追溯成因 THEN SHALL 写明两者**各有独立归档 spec**（`a9-1-deficiency-letter` 28/28 与 `a9-2-deficiency-letter-governance` 18/18）但代码合并到一个宿主 ⇒ 与 M 轮 MC-25「两份归档 spec 结论不一致」**同型**（依 AC-25 · AC-45）。
3. WHEN 现算 a91 的 BP 数 THEN SHALL 为 **8**（公共 6 + BP-9 + BP-11）—— A 域最多。
4. WHEN 收口 BP-11 THEN SHALL 明确 sync 改线时**每个 componentType 各自一份 entry 契约**还是**共享一份**，并在 `design.md` 给出裁定与理由；收口后 BP-11 成员集 SHALL 变为空集。
5. 🔴 WHEN 编写判据 THEN SHALL NOT 假设 `component_types` 长度为 1 —— a91 的 `component_type_family` 是 **`multi_component_type_single_host`**，是 20 条中唯一。

### Requirement 7 — 归档 spec 欠账交叉登记

**用户故事**：作为实施者，我要知道本 spec 范围内有 5 条 entry 的功能 spec 尚未完成。

#### 验收标准

1. 🔴 WHEN 现算本 spec 范围内的归档欠账 THEN SHALL 为 **5** 份未 100%（共 **6** 条未完成任务）：`a11-1-subsequent-events-inquiry` **19/21**（2 条）· `a17-3-1-consultation-execution` **15/16** · `a17-3-consultation-record` **16/17** · `a17-4-disagreement-record` **16/17** · `a18-2-regulatory-communication` **14/15**（依 AC-25）。
2. WHEN 比对 foundation 的 6 份 THEN SHALL 说明差额：第 6 份是 `a17-7-independence-declaration` **20/21**，其 entry（a177）归 **lane3** ⇒ 两份 lane spec 各自登记自己的份额，合计 6 份 / 7 条。
3. 🔴 WHEN 处理欠账 THEN SHALL **只登记不回填修改**已归档 spec（append-only），勘误写在本 spec。
4. WHEN 扫归档区 THEN SHALL 带 `errors="replace"` 容错（依 AC-25）。

### Requirement 8 — 持久化通道与改线（三种 channel 并存）

**用户故事**：作为实施者，我要按各 entry 真实的持久化通道改线，不能一刀切。

#### 验收标准

1. WHEN 现算本 spec 的 channel 分布 THEN SHALL 为 `checklist_responses` **14** · `checklist_responses+field_overrides` **1**（a115）· `field_overrides` **1**（a112）。
2. 🔴 WHEN 复算 channel THEN SHALL 扫宿主 **import 闭包深度 3**（依 AC-42）—— 宿主内 `/checklist-responses` 现算 **0**，只扫宿主必假阴。
3. WHEN 改线 THEN 宿主内联的 `<el-segmented>` + mode 门控挂点 SHALL 改接 sync bridge，宿主只传 entryId / wpId / sheetName + flush/reload 回调（依 AC-2、删除清册 `must_rewire`）。
4. 🔴 WHEN 改线 mode 载体 THEN 本 spec 的 **15 条形态 1**（中文标签作 mode 值）SHALL 收敛到形态 2（label/value 分离），抄 **a112** 已有样板（a112 本身在本 spec 内，是就近样板）；依 AC-41。
5. WHEN 改线完成 THEN SHALL NOT 新增 `publish-to-tb` 调用（依 AC-3 的空分母裁定）。
6. WHEN 现算 docx 生成逻辑 THEN 本 spec 范围内 SHALL 占 docx/word 相关命中的主要部分（全 A 域 **70** 命中 / **8** 文件），改线须一并纳入（依 AC-38）。
