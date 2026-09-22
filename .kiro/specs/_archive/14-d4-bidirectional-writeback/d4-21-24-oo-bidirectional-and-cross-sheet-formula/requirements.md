# D4-21~24 需求

## 范围
D4-21 关联方销售及价格分析、D4-22A 程序表、D4-22 重要指标、D4-23 发票比较、D4-24 第三方回款。目标是接入 HTML/OnlyOffice 内容表征同步、跨底稿公式治理和 D4-21/24 导入导出。模板 finder/index 核定前不预设同册、sheet、行数、UUID 列或双向档位。

## 统一约束
- HTML/Excel/快照统一走 `ContentMutationService` 版本校验、三方合并和 durable callback，禁止 Excel 优先、last-write-wins 和 fail-open。
- 公式统一走 F-SHELL 与 `wp_formula` effective definition，表达式、规范化 refs、参数、版本/hash 一体化；不使用 field_overrides/remark。
- OO 内部公式保留在 OOXML；FORMULA_MASK 仅防普通值投影写入，授权公式修改仍需解析提交。
- D4-21~24 业务取数复用 four_table scope/叶子聚合，缺码拒绝或人工；D4-22 同业横向列用 `{slot}_{seq}` 动态 key。D4-22A 无金额/公式/行身份时可判不适用。
- 业务导航 refs 是用户导航关系，不要求与公式 refs 相等，但必须各自可追溯。

## Acceptance Criteria
### Requirement 1: 模板裁决
1. WHEN 实施前置核 THEN 必须直接读取运行时权威模板并记录真实 tab、范围、表头、数据区、footer、公式格、行身份、O列保留值和映射 digest。
2. WHEN 某表无可稳定合并的行身份或存在不可接受排版/专用链冲突 THEN 必须判 `single_html` 或 `limited_bidirectional`，书面记录依据，不得代码扩展假双向。
3. WHEN D4-21 插桩 THEN UUID 不得使用 O 列，且 O 列枚举原值逐字保持；D4-23 的 D/I/J、D4-21 的 I/K 等 OO 公式必须进入 mask。

### Requirement 2: 内容同步
1. WHEN 受管表同步 THEN 统一走 ContentMutationService/bridge，版本冲突可见可恢复，失败不 markSynced。
2. WHEN HTML→OO THEN 先 flush 待保存内容，只投影受管字段，不写 mask；WHEN OO→HTML THEN 按行身份合并并保留非受管字段和公式字节。
3. WHEN D4-22-data 含 `{rows, peers, transportExpense}` THEN 分槽合并；同行列动态展开，不写死公司数量。
4. WHEN D4-22A 或裁决为 single_html THEN 保持结构化视图，记录理由，不伪造在线编辑能力。

### Requirement 3: 跨底稿公式
1. WHEN 预设、custom、恢复默认或 Excel 公式编辑 THEN 都经 F-SHELL 写入 versioned `wp_formula` effective definition，refs 使用 addr_id/formula_ref，参数纳入 hash。
2. WHEN 公式执行失败 THEN 仅失败公式及依赖项为 failed/blocked，不 ApplyValue、不把 null 转零；无依赖公式可继续。
3. WHEN D4-21 取 D4-1 审定数 THEN 使用 ACNR canonical 坐标与 D4-1 快照，不读取旧 `D4-1-adj-tb-6001` 键；业务导航 refs 不必等于公式 refs。
4. WHEN 模板已有内部算术 THEN 保留 OOXML 公式并由 mask 保护；不得在 wp_formula 重复声明同一物理公式。
5. WHEN 用户改定义 THEN version/hash 递增，custom 派生自 preset，依赖方经 outbox 标记 stale；参数覆盖走同一 effective definition。

### Requirement 4: 各表字段与导入导出
1. WHEN D4-21/D4-24 导入 THEN 专用 parser 按列头映射；模板-only 列显式登记，不静默丢弃；导出按 camel 字段映射中文列头。
2. WHEN 派生列导入 THEN 不采信文件值，按公式重算；D4-21/24 与已有 D4-22/23 均有 round-trip 测试。
3. WHEN D4-21 行身份重复、D4-24 枚举不合法或 scope 缺失 THEN 拒绝或人工，不猜测。

### Requirement 5: 溯源与验证
1. WHEN GtIndexChip 展示关系 THEN 从 cross_wp_references 单一导航真源读取并可跳转；既有关系只补不删，D4-24 的 D2 引用先做语义裁决。
2. WHEN A13 推送 THEN 只接受 formula logic_check 的 IssueItem，复用既有共享件，科目固定 6001/营业收入，不能复制判据。
3. WHEN 交付 THEN 必须有模板真读、投影真跑、DB formula 快照、stale outbox、浏览器四表实测，并完成 AC/Property/task/DAG 自查。

## Correctness Properties
### Property 1
**Validates: Requirements 1.1, 1.2, 1.3**
模板裁决、行身份、公式 mask 与 digest 一致；不可合并表不会被伪接入。
### Property 2
**Validates: Requirements 2.1, 2.2, 2.3**
并发同步三方合并，受管字段 round-trip，非受管字段和 OO 公式保持不变，复合 store 不丢槽。
### Property 3
**Validates: Requirements 3.1, 3.2, 3.5**
同一 effective definition 的 refs/params/hash/version 可追溯，失败隔离，依赖 stale 可见。
### Property 4
**Validates: Requirements 3.3, 4.1, 4.2**
D4-21 使用 D4-1 canonical snapshot，专用 import/export 逐字段 round-trip，派生列重算。
### Property 5
**Validates: Requirements 5.1, 5.2**
导航、公式和 A13 来源分别可追溯，IssueItem 是唯一推送判据且科目正确。
