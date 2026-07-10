# ACNR 六条规则冻结（Rules Freeze v1）

- **状态**：M0 冻结（`MVD-1 / G7`）
- **日期**：2026-07-10
- **DRI**：平台架构组
- **对应需求**：`requirements.md` Requirement 20（20.1 / 20.2 / 20.3）
- **上游真源**：
  - 架构蓝图 `docs/proposals/address-coordinate-name-registry-architecture.md`（v1.10，附录 A / §十 A-Q）
  - 命名规则 normative 真源 `docs/proposals/workpaper-bulk-tab-import-export-requirements.md` §8.6（含 §8.6.7 N-Q）

> **本文用途**：把 ACNR 六条核心规则与 bulk §8.6、A-Q、N-Q 评审决议**冻结归档**，作为 M0 开工门禁（G7）的可追溯依据。冻结后的规则为后续实现（生成器、resolver、CI、消费者切换）的统一裁决基准；**任何变更须走评审并升 registry_version**（见 R-ADDR 不可变政策）。
>
> 本文只**归档**规则，不重复推导命名规则全文——命名规则 normative 真源仍在 bulk §8.6，本文引用其结论。

---

## 一、六条核心规则（冻结）

以下六条规则于 M0 冻结，是 ACNR「四套并行寻址语法收敛为一张映射表、一格一 `addr_id`」核心命题的规则地基。

### R-URI — 五域 URI 语法不变

| 项 | 内容 |
|----|------|
| **规则** | 保持既有五域 URI 语法：`{domain}://{source}/{path}#{cell}`，域 `domain ∈ {wp, tb, report, note, aux}`；ACNR 不改动 tb/report/note/aux 四域的既有语法（`TB()` / `ROW()` / `NOTE()` / `AUX()`）。 |
| **wp 域 profile** | 冻结两个 wp 域 URI profile：<br>· **standard**：`wp://{parent}/{sheet_name}#{cell}`，对应 `WP(parent, sheet_name, cell\|semantic)` 三参。<br>· **custom_flat**：`wp://{wp_code}/{cell}`，对应 `WP(wp_code, cell)` 二参。 |
| **理据** | 平台已有五域 URI + `WP()` 公式体系与 `cross_wp_references` / `formula_reverse_index` 深度耦合；推倒重来成本与风险不可控。ACNR 采用 Strangler-fig 策略，**语法保持向后兼容**，仅新增收敛出口。 |
| **冻结点** | `grammar_v1.json` 的 `uri_profiles`（standard / custom_flat + tb/report/note/aux）。profile 选择可覆盖格式类型（任一 entry_type 允许 custom_flat，自定义格亦允许 standard）。 |
| **追溯** | Requirement 9；bulk §8.6.1 统一 URI；架构蓝图 §5.5。 |

### R-ADDR — addr_id 格式与不可变政策

| 项 | 内容 |
|----|------|
| **格式** | `addr_id = {parent}/{sheet_code}[/{coordinate_key}]`；三实体分别为：<br>· SheetCatalogEntry：`{parent}/{sheet_code}`（如 `D2/D2-2`，无坐标后缀）。<br>· CellCatalogEntry：`{parent}/{sheet_code}/{coordinate_key}`（如 `D2/D2-2/E100`）。<br>· RuntimeCellEntry：`runtime/{project_id}/{wp_id}/{sheet_or_code}/{cell}`。 |
| **canonical 规则** | 有 A1 单元格时以 `{parent}/{sheet_code}/{cell_address}` 为 canonical addr_id；无可靠 A1 且 `semantic_only=true` 时用 `{parent}/{sheet_code}/{slug(semantic_label)}`。**同一物理格不得有两个 canonical addr_id。** |
| **coordinate_key** | `cell_address`（A1）优先；无 A1 时用 `semantic_label` 的 slug。 |
| **不可变政策** | **不允许修改已存在的 `addr_id`**（改 addr_id 视为破坏性变更，须新 addr + 迁移映射表）。sheet 权威名变更走 `sheet_name_aliases`，不改主键。坐标弃用标 `deprecated:true` 并保留 ≥1 个 `registry_version`。 |
| **版本锁定** | 归档项目创建时记录 `registry_version`；解析归档项目引用时按该项目锁定的版本解析（历史可复现）。 |
| **项目上下文隔离** | 全局 catalog（L1）**不含** `project_id` / `wp_id`；项目上下文仅存在于 L2/L3。 |
| **理据** | `addr_id` 是「不因 sheet 改名而变」的稳定身份键，是公式引用、CCR 边、高级查询回写、QC 下钻的统一锚点。可变身份会导致重命名断链、归档不可复现。 |
| **冻结点** | `global_catalog.schema.json` addr_id pattern + `not.required:[project_id,wp_id]`；生成器 canonical 构造逻辑。 |
| **追溯** | Requirement 8、Requirement 19（§13.4）；bulk §8.6.1 库内稳定主键；架构蓝图 §5.1 / §5.1.1。 |

### R-WP — `WP()` 2 参 + 3 参并存互转

| 项 | 内容 |
|----|------|
| **规则** | `WP()` 与 `PREV()` 的 **2 参与 3 参形态并存**；第三参为 `semantic_label` 或 `cell`；两形态可**无损互转**（`roundtrip:true`）。 |
| **无损往返铁律** | FOR ALL 合法 `formula_ref`：`formula_ref_to_uri()` 转换后再转回 `formula_ref` 产生等价结果。第三参（语义名）**不得丢弃**——现网 `formula_ref_to_uri()` 只取前两参的缺陷须在 M1 修复。 |
| **第一参约定** | `WP()` 第一参为**父码** `parent_wp_code`（如 `D2`），而非 `sheet_code`（如 `D2-2`）。 |
| **实现门槛** | M0 只冻结语法元数（`arities:[2,3]`、`third_arg`、`roundtrip:true`）；M1 在 `formula_grammar.py` 实现，**具备实际解析能力方可标记完成**（不能空实现）。 |
| **理据** | 历史上联动图/CCR 按 3 参 `WP()` 建设，公式校验按 2 参，「能力叠上去了，真源没立住」，两者互相打脸。冻结并存 + 无损互转，让「联动图能建」与「校验能过」不再冲突。 |
| **冻结点** | `grammar_v1.json` 的 `functions.WP` / `functions.PREV`。与 bulk §8.6 命名规则一致，同时收录 standard 与 custom_flat profile。 |
| **追溯** | Requirement 10（G6）；A-Q6；架构蓝图 §17.3。 |

### R-NAME — sheet_name 权威源 = classification

| 项 | 内容 |
|----|------|
| **规则** | sheet_name 存在冲突时，以 `workpaper_sheet_classification.sheet_name`（xlsx Tab 真名）为**唯一权威源**。 |
| **权威源优先级** | `workpaper_sheet_classification.sheet_name` > xlsx 模板 Tab 名 > 前端 `*SheetLabels.ts` label（后者仅作 `sheet_name_aliases` 别名 ingest）。 |
| **别名收敛** | 14 份 `*SheetLabels.ts` 与 classification 展示名 ingest 为 `sheet_name_aliases`；一别名映射多 sheet_code 时 CI 在合并前标缺口并**阻断该别名进入 catalog**（阻断优先于缺口标记）。 |
| **自定义例外** | 自定义底稿 `sheet_name` 默认 = `wp_code`（与 `parsed_data.html_data` 的 key 一致），见 bulk §8.6.3。 |
| **理据** | 现状同一 sheet 多处中文名不一致，前端 14 份 label 与 DB 漂移，导致 bulk manifest、跳转、导入列头匹配失败。定权威源终结「多套展示名各自为政」。 |
| **冻结点** | 生成器 `from_classification.py`（骨架主源）+ `from_frontend_labels.py`（仅 ingest 别名）。 |
| **追溯** | Requirement 20.2、Requirement 3；bulk §8.6.2 权威源优先级；架构蓝图 §5.2。 |

### R-ROUTE — I/E 路由只认 api_prefix + item_id

| 项 | 内容 |
|----|------|
| **规则** | 导入导出（I/E）路由**只认** catalog 的 `api_prefix` 与 `item_id`；消费者禁止自行拼接 I/E 路由或猜测 item_id。 |
| **跳转扩展** | 一般跳转须使用 `resolve()` 返回的 `jump_route`（模板 + 已解析 wp_id），禁止消费者自拼路由。`resolve_instance` 是唯一 wp_id 解析出口。 |
| **同步守卫** | `{cycle}_cycle_ie_manifest.yaml` 与 catalog 的 `import_export` 段须一致，由 CI `check-ie-catalog-sync` 校验（首期先 D 循环）。 |
| **理据** | I/E 逻辑分散在 71 个 `_*_import_export.py`，manifest 无权威 `sheet_code → item_id → api_prefix` 单一 join，做 bulk ZIP = 硬编码路径、每扩循环重写。收口到 catalog 才能一次登记、处处复用。 |
| **冻结点** | SheetCatalogEntry.`import_export` = `{enabled, api_prefix, item_id, storage_field, import_order, depends_on_sheets}`；`d_cycle_ie_manifest.yaml` 手维清单。 |
| **追溯** | Requirement 18.6、Requirement 7.3；bulk §8.6.6 manifest 映射；架构蓝图 §8.3。 |

### R-ENTRY — 只许生成器或 overrides 入口

| 项 | 内容 |
|----|------|
| **规则** | 新增/修改 sheet 条目**只允许两条入口**：<br>1. 改 catalog 源数据（classification / manifest / seeds / labels）+ 跑 `generate_catalog.py`；<br>2. 在 `global_catalog.overrides.json` 打补丁并注明 `reason` + `owner`（建议 `expires_at`）。 |
| **禁止** | 禁止任何模块私自新建第四套手写命名副本（如再造 `*SheetLabels.ts` / 各自维护命名表）。 |
| **CI 守卫** | `check-acnr-catalog-drift`（生成器产出 = committed `global_catalog.json`）、`check-addr-id-unique`（全局 addr_id 无重复）、`check-standard-wp-code-re-single`（grep-ban 阻断新增 `[A-I]\d`/`[A-S]\d` 副本）。 |
| **override 边界** | overrides 仅放别名、补充坐标、临时 skip；**不覆盖**标准 wp_code 主记录；CI 合并时 override 优先级高于自动生成。 |
| **理据** | 目录只有单一写入面才能防漂移。双入口 + CI drift 检查保证「同输入 → 字节一致输出」，杜绝手改导致的目录腐化。 |
| **冻结点** | `generate_catalog.py` 唯一生成入口 + `global_catalog.overrides.json` + `docs/acnr/CONTRIBUTING.md` 双入口流程。 |
| **追溯** | Requirement 18（MVD-5）；bulk §8.6.4 扩展流程；架构蓝图 §13.5。 |

---

## 二、bulk §8.6 命名规则决议（归档）

命名规则 normative 真源为 bulk 需求文档 §8.6（v1.0 草案，随 ACNR v1.7 对齐）。本文归档其**已拍板结论**，细节以 §8.6 为准。

### 8.6.1 三层寻址模型（冻结）

| 层 | 字段 | 作用 | 示例 |
|----|------|------|------|
| **L1 底稿** | `wp_code` | 底稿类型/实例编码 | `D1`、`D2`、`CUST-99` |
| **L2 表页** | `sheet_code` + `sheet_name` | Tab 级定位（bulk 文件名、manifest 路由） | `D1-2` / `明细表D2-2` |
| **L3 坐标** | `cell_address` 或 `semantic_label` | 单元格或语义锚点 | `E100` / `合计行-期末余额` |

- 库内稳定主键 `addr_id = {parent_wp_code}/{sheet_code}/{coordinate_key}`；sheet 级为 `D2/D2-2`（无坐标后缀）；`WP()` 第一参为父码 `D2`（v1.7 对齐）。

### 8.6.2 标准底稿（冻结要点）

- **wp_code**：循环+序号 `^[A-S]\d+`；带 Tab 后缀 `^{Cycle}\d+-\d+([A-Z])?$`；程序表 `^{Cycle}A$`；Bundle 子码 `^S\d+-\d+-\d+$`。
- **标准码判定**：`_looks_like_standard_wp_code` 由 `^[A-I]\d` **扩为 `^[A-S]\d`**（消除 J~S 误判为自定义），收敛为单一常量 `STANDARD_WP_CODE_RE`（见 N-Q3、Requirement 12）。
- **sheet_code**：从 `sheet_name` 尾部提取 `([A-S]\d+-\d+[A-Z]?|[A-S]\d+A)\s*$`，须与 API `?sheet=` 及前端 label key 一致。
- **sheet_name 权威写法**：`{中文功能名}{sheet_code}`（审定表`审定表{code}` / 明细表`明细表{code}` / 程序表`…程序表{code}` / 底稿目录无后缀）。
- **purpose 枚举（只允许追加）**：`balance_verification | conclusion | aging_analysis | ratio_analysis | formula_anchor | import_export_total | other`。

### 8.6.3 自定义底稿（冻结要点）

- **wp_code 分配**：`CUST-{项目内序号}`（如 `CUST-01`），格式 `^CUST-\d{2,}$` 或 `^custom-\d+$`；禁止与标准 wp_code 冲突。
- **sheet_name**：默认 = `wp_code`（与 `html_data` key 一致）。
- **sheet_code**：单 sheet 自定义 = `wp_code`；多 sheet 为 `{wp_code}@{tab_slug}`（如 `CUST-01@sheet1`），URI 仍用 `/`（见 N-Q2）。
- **坐标注册**：保存后 `extract_custom_cells(parsed_data)` 自动写入 WP 域（L3），关键格可追加 `semantic_label`。
- **class_code**：固定 `CUSTOM`；bulk 一期可 `skip_reason=custom_univer_only`。
- **隔离**：自定义 addr_id 仅存 L2/L3，**不写入全局 L1 种子**（防越权 / IDOR）。

### 8.6.4 扩展与新增底稿流程（冻结）

```
1. 申请 wp_code（或 CUST-xx）→ 2. 登记 sheet_name + sheet_code
→ 3. 登记 item_id / api_prefix（若有 I/E）→ 4. 登记坐标（可选）
→ 5. CI 校验 addr_id 唯一 + 命名符合 §8.6
```

> 与 R-ENTRY 一致：新增底稿必须走登记流程，否则不得接入 bulk ZIP / `WP()` / 跨底稿引用。

---

## 三、A-Q 架构级决议（评审签字归档，G7）

来源：架构蓝图 §十「待拍板（架构级）」。评审会须对 **A-Q1–A-Q3、A-Q5–A-Q8 签字归档**（G7）；未决项不得开工 M0 编码。

| # | 问题 | 决议 | 状态 |
|---|------|------|------|
| A-Q1 | 模块代号：ACNR 还是沿用 `address_registry`？ | 对内 **ACNR**；HTTP `/api/acnr`；旧路径转发 | ✅ 采纳（G7） |
| A-Q2 | L1 存 JSON 还是 DB？ | **M0 JSON 生成物**；M2+ 可选 DB 索引表加速 | ✅ 采纳（G7） |
| A-Q3 | addr_id 是否含 project_id？ | **全局不含**；项目用 `project_id + addr_id` | ✅ 采纳（G7） |
| A-Q4 | MCP 集成？ | `acnr_lookup` / `acnr_resolve` | ⏳ 可选（M3） |
| A-Q5 | DRI？ | **平台架构组**，非单循环 feature 组 | ✅ 采纳（G7） |
| A-Q6 | `WP()` arity？ | **2 参与 3 参并存**；3 参第三项为 semantic_label 或 cell | ✅ 采纳（G7，→ R-WP） |
| A-Q7 | 种子何时进运行时？ | **M0** 进 catalog；**M1** 进 `build_workpaper_entries` | ✅ 采纳（G7） |
| A-Q8 | bulk ZIP 何时启动？ | **M1 Gate 通过** → bulk spec；**M2** 写 API | ✅ 采纳（G7） |

---

## 四、N-Q 命名规则决议（评审签字归档，G7）

来源：bulk §8.6.7「待确认（命名规则专用）」。

| # | 问题 | 决议 | 状态 |
|---|------|------|------|
| N-Q1 | 自定义 wp_code 前缀统一为 `CUST-` 还是允许用户中文名？ | **仅 `CUST-{nn}` 机器码**，中文放 `wp_name` | ✅ 采纳（G7） |
| N-Q2 | 多 sheet 自定义的 `sheet_code` 用 `@` 还是 `/`？ | `CUST-01@Tab名slug`，**URI 仍用 `/`** | ✅ 采纳（G7） |
| N-Q3 | `_looks_like_standard_wp_code` 是否扩到 `[A-S]\d`？ | **是**，避免 J/K 误判 custom（→ R-NAME / `STANDARD_WP_CODE_RE`） | ✅ 采纳（G7） |
| N-Q4 | 语义坐标是否强制绑定 A1？ | **尽量双写**；仅有语义时 formula 用 label、bulk 用 item_id 行 JSON（`semantic_only=true` 由 CI 标记需补 A1） | ✅ 采纳（G7） |
| N-Q5 | 全局库 vs 项目库？ | **全局种子 + 项目实例 overlay**（含 CUST 与 wp_id），全局不含项目上下文 | ✅ 采纳（G7） |

---

## 五、规则 ↔ 需求 ↔ 上游真源 追溯矩阵

| 规则 | Requirement | 上游真源 | grammar/schema 冻结点 |
|------|-------------|----------|------------------------|
| R-URI | R9、R20.1 | 架构 §5.5；bulk §8.6.1 | `grammar_v1.json.uri_profiles` |
| R-ADDR | R8、R19、R20.1 | 架构 §5.1 / §5.1.1；bulk §8.6.1 | `global_catalog.schema.json` addr_id pattern |
| R-WP | R10、A-Q6 | 架构 §17.3 | `grammar_v1.json.functions.WP/PREV` |
| R-NAME | R20.2、R3、N-Q3 | 架构 §5.2；bulk §8.6.2 | `from_classification.py` / `from_frontend_labels.py` |
| R-ROUTE | R18.6、R7.3 | 架构 §8.3；bulk §8.6.6 | SheetCatalogEntry.import_export；`d_cycle_ie_manifest.yaml` |
| R-ENTRY | R18、R20.1 | 架构 §13.5；bulk §8.6.4 | `generate_catalog.py` + overrides + CONTRIBUTING |

---

## 六、冻结声明

本六条规则与 bulk §8.6 / A-Q / N-Q 决议自 M0 起冻结。冻结后：

1. 规则为生成器、resolver、CI、消费者切换的统一裁决基准。
2. **不得**绕过评审修改任一规则；任何变更须走评审并升 `registry_version`（addr_id 变更另须迁移映射表，见 R-ADDR）。
3. 本文归档满足 Requirement 20.1（冻结六条规则）、20.2（sheet_name 权威源 = classification）、20.3（bulk §8.6、A-Q、N-Q 决议签字归档），构成 M0 开工门禁（G7）证据链。
