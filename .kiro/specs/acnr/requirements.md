# Requirements Document

## Introduction

ACNR（Address Coordinate & Naming Registry，地址坐标名称注册中心）是审计平台的**平台级单一真源（Single Source of Truth）**，用于统一底稿/报表/附注/试算表/辅助余额的**名称、坐标、URI、跳转、依赖锚点**。

本需求文档不重新推导设计，而是把架构蓝图 `docs/proposals/address-coordinate-name-registry-architecture.md`（v1.10）的**验收门（附录 A：G1–G8 + MVD-1..8，及 §17.7：G9–G13）**转写为 EARS 格式的可验证需求，作为 spec 三件套的第一件（对应 G8 阻塞项）。

平台现状痛点（架构文档 §一/§〇·二 实证）：
- 存在**至少四套并行寻址体系**——五域 URI + `WP()` 公式、V1 运行时目录、V2 静态语义图、索引命名空间（11 命名空间 + Layer），互不解析。
- 坐标种子（473 个）仅服务测试，**运行时未接入**；公式选址器搜不到。
- `WP()`/`PREV()` 存在 2 参与 3 参分裂；`[A-I]\d` 与 `[A-S]\d` 标准码判定已跨文件裂开。
- 前端 30+ 份披露 composable 逐字节重复；`*SheetLabels.ts` 14 份与 DB 漂移。

**核心命题**：四大消费库（公式管理库 / 高级查询库 / 索引库 / 附注库）共用一个 `resolve()`，四套语法收敛为一张映射表，一格一 `addr_id`。

**架构原则（五层模型）**：上层只通过 `addr_id` 或 URI 引用下层，**禁止消费者拼接 `wp_code + sheet + cell` 字符串**。

- **L0 Grammar**：URI、addr_id、`WP()/TB()` 语法、索引命名空间语法（`grammar_v1`）。
- **L1 GlobalCatalog**：标准底稿全量 sheet + 坐标种子（首期**仅 wp 域**静态 JSON）。
- **L2 ProjectOverlay**：wp_id、CUST、项目别名、ProjectBinding。
- **L3 RuntimeIndex**：parsed_data、当前值缓存、自定义格。
- **L4 DependencyGraph**：引用/公式/stale 边，端点必须是 addr_id。

**里程碑范围**：M0（catalog JSON + 只读 lookup/resolve + CI）、M1（运行时接线 + 语法 + resolve_instance + orchestrator 失效收口）、M2（bulk 试点 + 消费者切换 + 披露工厂）、M3（扩展 + CCR normalize）。每条需求标注对应里程碑。

**首期明确范围**：L1 静态 catalog **仅 wp 域**；tb/report/note/aux 仍走现网 V1 动态 build，但**经同一 `resolve()` 出口**对外。

## Glossary

- **ACNR**: Address Coordinate & Naming Registry，地址坐标名称注册中心；平台级寻址目录真源，提供可版本化、可治理、可解析的命名/坐标/URI/跳转服务。
- **addr_id**: ACNR 稳定主键，格式 `{parent}/{sheet_code}[/{coordinate_key}]`（如 `D2/D2-2/E100`），**不因 sheet 改名而变**；改名走 aliases，不改主键（§13.4）。
- **canonical_addr_id**: 某物理格唯一权威 addr_id；有 A1 单元格时以 `{parent}/{sheet_code}/{cell_address}` 为准（§5.1.1）。
- **SheetCatalogEntry**: L1 主条目，Tab/sheet 粒度；addr_id 无坐标后缀（如 `D2/D2-2`）；含 sheet_name、component_type、import_export、jump_route_template 等。
- **CellCatalogEntry**: L1 坐标子条目，单元格或语义锚点粒度；含 cell_address、semantic_label、formula_ref、uri，FK 指向 SheetCatalogEntry。
- **RuntimeCellEntry**: L2/L3 项目实例格；addr_id 前缀 `runtime/{project_id}/{wp_id}/...`；服务 CUST、parsed_data 提取；`runtime_only=true` 不进全局 L1 种子。
- **resolve**: ACNR 统一解析方法；输入接受四种语法（五域 URI / `WP()` 公式 / 索引 `ns:target` / 裸 wp+sheet+cell），输出 canonical addr_id + 物理格 + jump_route。
- **resolve_instance**: `resolve_instance(project_id, parent_wp_code, sheet_code)`，经 ProjectBinding 返回项目内 `wp_id`；是唯一的 wp_id 解析出口。
- **ProjectBinding**: L2 绑定层，把 `(project_id, parent_wp_code, sheet_code)` 映射到 WorkingPaper 实例 `wp_id`；全局 catalog 不含 project_id/wp_id。
- **grammar_v1**: L0 冻结的语法定义文件（`grammar_v1.json`），收录五域 URI profile（standard + custom_flat）、`WP()/PREV()` 元数、索引命名空间↔addr_id/URI 映射表、`STANDARD_WP_CODE_RE` 常量。
- **ACNR_Generator**: catalog 生成器（`generate_catalog.py`），合并 classification + I/E manifest + seeds + labels→aliases 产出 `global_catalog.json`。
- **ACNR_Resolver**: 执行 resolve 决策树（§6.1.1）的服务组件。
- **ACNR_CI**: ACNR 相关 CI 守卫集合（drift / addr-id-unique / ie-catalog-sync / ccr-resolve 等）。
- **URI_Profile**: URI 形态类别，standard（`wp://{parent}/{sheet_name}#{cell}`）或 custom_flat（`wp://{wp_code}/{cell}`）。
- **CCR**: 跨底稿交叉引用（cross_wp_references），415 条 `WP()` 规则。
- **STANDARD_WP_CODE_RE**: 标准底稿码判定的单一正则常量 `^[A-S]\d`，由 `wp_render_config.py` 与 `wp_index_resolve.py` 共同 import。
- **registry_version**: catalog 版本号；归档项目创建时记录，解析时按项目锁定版本。
- **jump_route**: ACNR 返回的跳转路由（模板 + 已解析 wp_id）；消费者禁止自拼路由。

## Requirements

---

### Requirement 1: 全局目录生成（G1）

**User Story:** 作为平台架构组 DRI，我想通过生成器一键产出可版本化的 `global_catalog.json`，以便所有消费者从单一目录取名称与坐标，而不是各自维护副本。

#### Acceptance Criteria

1. WHEN ACNR_Generator 执行完成, THE ACNR_Generator SHALL 产出包含 `workpaper_sheet_classification` 全量 sheet 骨架的 `global_catalog.json`（覆盖率达到 classification 记录的 100%）。
2. WHEN ACNR_Generator 处理 D 循环（D1–D7）, THE ACNR_Generator SHALL 在 `global_catalog.json` 中为每个 D 循环 sheet 填充 import_export 段与坐标种子条目。
3. THE ACNR_Generator SHALL 将 classification、I/E manifest、坐标种子、labels 别名合并为 SheetCatalogEntry 与 CellCatalogEntry 两类条目。
4. IF 任一 sheet 存在 `skip_reason`, THEN THE ACNR_Generator SHALL 在对应 SheetCatalogEntry 中写入 `skip_reason` 并完全阻止本次 bulk manifest 生成（而非仅跳过该 sheet）。
5. THE ACNR_Generator SHALL 为 `global_catalog.json` 写入 `registry_version` 字段。

---

### Requirement 2: sheet_code 正向解析（G2）

**User Story:** 作为公式管理库开发者，我想用 sheet_code 查到唯一的 sheet 名称与路由信息，以便公式选址器与 bulk manifest 有权威来源。

#### Acceptance Criteria

1. WHEN 消费者以合法 sheet_code（如 `D1-2`）调用 `GET /api/acnr/lookup`, THE ACNR_Resolver SHALL 返回唯一的 sheet_name、parent_wp_code、api_prefix 与 item_id。
2. WHEN lookup 命中, THE ACNR_Resolver SHALL 在响应中返回 `found: true`、`addr_id` 与 `entry_type`。
3. IF 提供的 sheet_code 在 catalog 中不存在, THEN THE ACNR_Resolver SHALL 返回 `found: false` 并附带最多 5 条 `candidates`（含 addr_id、display_label、score）。
4. IF 同一 sheet_code 在 catalog 中命中多个条目, THEN THE ACNR_Resolver SHALL 返回 `found: false`、`error: "ambiguous"` 且在 `candidates` 中返回全部命中条目。

---

### Requirement 3: 别名反查（G3）

**User Story:** 作为审计助理，我想用现场临时叫法或历史 sheet 名反查到规范 sheet_code，以便命名漂移不会导致寻址失败。

#### Acceptance Criteria

1. WHEN 消费者以已登记的 `sheet_name_alias` 发起解析, THE ACNR_Resolver SHALL 返回唯一对应的 sheet_code。
2. THE ACNR_Generator SHALL 把 14 份 `*SheetLabels.ts` 与 classification 中的展示名 ingest 为 SheetCatalogEntry 的 `sheet_name_aliases`。
3. IF 一个别名映射到多个 sheet_code, THEN THE ACNR_CI SHALL 在合并前将该冲突标为缺口并阻断该别名进入 catalog。
4. WHERE 别名触发命名模式或保留字等冲突之外的附加规则, THE ACNR_CI SHALL 阻断该别名进入 catalog。
5. IF 别名阻断成功但缺口标记失败, THEN THE ACNR_CI SHALL 保持该别名处于阻断状态（优先保障 catalog 完整性）。

---

### Requirement 4: 坐标种子汇入运行时（G4）

**User Story:** 作为公式管理库开发者，我想让测试种子里的坐标真正进入运行时选址器，以便"测过"等于"能用"，消除种子与运行时脱节。

#### Acceptance Criteria

1. WHEN ACNR_Generator 执行（M0）, THE ACNR_Generator SHALL 把 13 个种子文件中的 473 个坐标登记为 CellCatalogEntry。
2. WHEN `build_workpaper_entries()` 构建运行时条目（M1）, THE L3_RuntimeIndex SHALL 合并来自 catalog 的 Cell 条目，使 D 循环种子坐标在公式选址器中可被搜索到。
3. THE CellCatalogEntry SHALL 为每个坐标保存 `cell_address`、`semantic_label`（可选）与 `formula_ref`。
4. WHERE 某 CellCatalogEntry 尚无可靠 A1 坐标且 `semantic_only=true`, THE ACNR_CI SHALL 在覆盖度报表中标记该条目需尽快补 A1。
5. WHEN CellCatalogEntry 完成登记, THE ACNR SHALL 使该坐标立即可被搜索，而不依赖 `build_workpaper_entries()` 的执行状态。
6. WHERE 某 CellCatalogEntry 为 `semantic_only=true`, THE ACNR_CI SHALL 在覆盖度报表中标记该条目需补 A1，无论对应 A1 坐标是否已存在。

---

### Requirement 5: 统一 resolve API 与决策树（MVD-4 / MVD-8）

**User Story:** 作为任一消费库，我想只调用一个 `resolve()` 就能把任意寻址输入解析为 canonical addr_id 与物理格，以便四库不再各自解析。

#### Acceptance Criteria

1. WHEN `resolve()` 收到 `formula_ref` 或 `uri` 或 `addr_id` 或 `lookup{parent,sheet,cell_desc}` 之一, THE ACNR_Resolver SHALL 先按 grammar_v1 的 URI profile 规范化输入，再依决策树（L2 overlay → L1 Cell 精确 → L1 Sheet+aliases → semantic_label 包含 → L3 Runtime → 非 wp 域委托 V1）执行解析。
2. WHERE 调用带 `project_id`, THE ACNR_Resolver SHALL 在 L1 命中前先应用 L2 ProjectOverlay 补丁。
3. WHEN 解析命中一个 Cell, THE ACNR_Resolver SHALL 返回 `found: true`、`addr_id`、`entry_type`、`cell_address`、`semantic_label`、`formula_ref`、`uri` 与 `jump_route`。
4. WHEN 调用传入 `project_id` 且解析命中, THE ACNR_Resolver SHALL 在响应中附带已解析的 `wp_id`。
5. IF 解析在同一 sheet 下命中多个候选, THEN THE ACNR_Resolver SHALL 返回 `found: false`、`error: "ambiguous"` 与候选列表（disambiguation）。
6. IF 解析未命中, THEN THE ACNR_Resolver SHALL 返回 `found: false`、最多 5 条相近项 `candidates` 并记录 miss 指标。
7. WHEN 消费者对 tb/report/note/aux 非 wp 域发起 `resolve()`, THE ACNR_Resolver SHALL 委托 V1 动态 build 完成解析并以统一响应契约返回成功结果（MVD-8）。
8. WHERE 调用带 `project_id` 且解析最终以 `ambiguous` 失败, THE ACNR_Resolver SHALL 仍先应用 L2 ProjectOverlay 补丁。

---

### Requirement 6: 项目实例解析 ProjectBinding（MVD-7）

**User Story:** 作为 jump_route 与 bulk manifest 的消费者，我想用 `resolve_instance` 拿到项目内 wp_id，以便跳转与导出定位到具体底稿实例。

#### Acceptance Criteria

1. WHEN 消费者调用 `resolve_instance(project_id, parent_wp_code, sheet_code)`, THE ACNR_Resolver SHALL 经 ProjectBinding 返回正确的 `wp_id`。
2. THE ACNR_Resolver SHALL 返回 jump_route 模板与已填充 `wp_id` 的路由。
3. IF 同项目下同 `(parent_wp_code, sheet_code)` 存在多个实例, THEN THE ACNR_Resolver SHALL 返回 disambiguation 错误，除非调用显式传入 `wp_id`。
4. THE global_catalog SHALL NOT 包含 `project_id` 或 `wp_id` 字段（项目上下文仅存在于 L2/L3）。

---

### Requirement 7: 五层引用铁律（结构性约束）

**User Story:** 作为平台架构组，我想强制所有消费者只通过 addr_id 或 URI 引用坐标，以便重命名 sheet 时依赖不断裂。

#### Acceptance Criteria

1. THE L4_DependencyGraph SHALL 使用 addr_id 作为所有边端点身份。
2. WHEN 上层模块引用下层坐标, THE 上层模块 SHALL 通过 addr_id 或 URI 引用，而非拼接 `wp_code + sheet + cell` 字符串。
3. WHERE 消费者需要跳转, THE 消费者 SHALL 使用 `resolve()` 返回的 jump_route，而非自行拼接路由。

---

### Requirement 8: 三实体模型与 canonical addr_id（MVD-2）

**User Story:** 作为设计评审人，我想把 Sheet/Cell/Runtime 三类实体与 canonical addr_id 规则冻结在需求中，以便实现避免同一物理格出现双主键。

#### Acceptance Criteria

1. THE ACNR SHALL 区分 SheetCatalogEntry、CellCatalogEntry、RuntimeCellEntry 三类实体，各自 addr_id 模式分别为 `{parent}/{sheet_code}`、`{parent}/{sheet_code}/{coordinate_key}`、`runtime/{project_id}/{wp_id}/{sheet_or_code}/{cell}`。
2. WHERE 某坐标有 `cell_address`, THE ACNR SHALL 以 `{parent}/{sheet_code}/{cell_address}` 作为 canonical addr_id。
3. THE ACNR SHALL 把 `semantic_label` 写入 CellCatalogEntry 且不为其单独分配 addr_id，除非 `semantic_only=true` 且无 A1。
4. WHERE `semantic_only=true`, THE ACNR SHALL 以 `{parent}/{sheet_code}/{slug(semantic_label)}` 作为 addr_id。
5. THE ACNR SHALL NOT 为同一物理格分配两个 canonical addr_id。
6. THE SheetCatalogEntry SHALL 以 `parent_wp_code`（如 `D2`）作为 `WP()` 第一参，而非 `sheet_code`（如 `D2-2`）。

---

### Requirement 9: URI Profile 冻结（standard / custom_flat）

**User Story:** 作为公式引擎开发者，我想让标准多 Tab 底稿与自定义单 sheet 底稿有明确的 URI 形态，以便解析规则无歧义。

#### Acceptance Criteria

1. THE grammar_v1 SHALL 收录 standard profile（`wp://{parent}/{sheet_name}#{cell}`，对应 `WP(parent, sheet_name, cell|semantic)` 三参）。
2. THE grammar_v1 SHALL 收录 custom_flat profile（`wp://{wp_code}/{cell}`，对应 `WP(wp_code, cell)` 二参）。
3. WHERE 域为 tb/report/note/aux, THE grammar_v1 SHALL 保持既有五域语法（`TB()` / `ROW()` / `NOTE()` / `AUX()`）不变。
4. WHEN RuntimeCellEntry 为自定义格, THE ACNR SHALL 使用 custom_flat profile 记录其 uri 与 formula_ref。
5. WHERE 条目需要, THE ACNR SHALL 允许任一 entry_type 采用 custom_flat profile，且 profile 选择可覆盖格式类型（自定义格亦允许采用 standard profile）。

---

### Requirement 10: WP()/PREV() 语法冻结与无损往返（G6 / R-WP）

**User Story:** 作为公式校验与联动图的共同维护者，我想让 `WP()`/`PREV()` 的 2 参与 3 参并存且可无损互转，以便"联动图能建"和"校验能过"不再互相打脸。

#### Acceptance Criteria

1. THE grammar_v1 SHALL 定义 `WP()` 与 `PREV()` 的 2 参与 3 参形态并存及互转规则（冻结于 M0）。
2. WHEN `formula_grammar.py` 在 M1 实现语法, THE Formula_Grammar SHALL 同时支持 `WP()`/`PREV()` 的 2 参与 3 参解析。
3. FOR ALL 合法 formula_ref, `formula_ref_to_uri()` 转换后再转回 formula_ref SHALL 产生等价结果（无损往返）。
4. THE grammar_v1 SHALL 与 bulk §8.6 命名规则一致，并同时收录 standard 与 custom_flat profile。
5. WHILE `formula_grammar.py` 尚不能实际解析 `WP()`/`PREV()`, THE Formula_Grammar SHALL 视为未完成（须具备实际解析能力方可标记完成）。

---

### Requirement 11: 索引命名空间语法收敛（G9 / D9）

**User Story:** 作为 GtIndexChip 的使用者，我想让索引命名空间（11 ns + Layer）与五域 URI/公式/addr_id 双向映射，以便索引跳转与公式选址指向同一目标。

#### Acceptance Criteria

1. THE grammar_v1 SHALL 收录恰好 11 个索引命名空间（`wp/sheet/cell/Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm`）与 Layer 1-4 到 addr_id/五域 URI 的双向映射表，且该映射表 SHALL 仅限这 11 个命名空间。
2. WHEN 消费者以索引语法 `TB:1001` 与公式语法 `TB('1001','审定数')` 分别调用 `resolve()`, THE ACNR_Resolver SHALL 将两者解析到同一目标。
3. WHEN `resolve()` 收到 `cell:D2-2!E100`, THE ACNR_Resolver SHALL 解析为 addr_id `D2/D2-2/E100` 与 uri `wp://D2/明细表D2-2#E100`。
4. WHERE 命名空间为 `Adj/Att/EQCR/Calc/Sample/Confirm` 等外部模块, THE ACNR_Resolver SHALL 返回 `exists=true` 且首期只登记不解析物理格。
5. WHERE 命名空间为 `wp/sheet/cell` 等内部命名空间, THE ACNR_Resolver SHALL 使用区别于外部模块的状态指示符（仅外部模块设置 `exists=true`）。

---

### Requirement 12: 标准码判定单一常量（G10 / D11）

**User Story:** 作为渲染配置与索引解析的维护者，我想让 `[A-S]\d` 标准码判定收敛为单一常量，以便 J~S 底稿不再被误判为自建底稿。

#### Acceptance Criteria

1. THE grammar_v1 SHALL 定义单一常量 `STANDARD_WP_CODE_RE = ^[A-S]\d`。
2. THE `wp_render_config.py` 与 `wp_index_resolve.py` SHALL 均从 grammar_v1 import `STANDARD_WP_CODE_RE`。
3. THE ACNR_CI SHALL 阻断代码中新增 `[A-I]\d` 或 `[A-S]\d` 的重复副本。
4. WHEN 以码 `J1` 或 `S3` 判定标准码, THE Standard_Code_Check SHALL 判定为标准底稿。
5. IF 标准码判定逻辑执行失败, THEN THE Standard_Code_Check SHALL 确保标准码（如 `J1`/`S3`）不被误判为自建底稿。
6. WHERE 校验结果已由预校验或缓存提供, THE Standard_Code_Check SHALL 允许在无显式校验调用的情况下存在校验结果。

---

### Requirement 13: 索引解析端点统一（G11 / D10）

**User Story:** 作为前端索引跳转的维护者，我想把三个 index-resolve 端点统一到 `resolve_instance`，以便 wp_id 解析只有一个出口。

#### Acceptance Criteria

1. THE `resolve_instance` SHALL 作为唯一的 wp_id 解析出口。
2. WHEN 消费者调用旧端点 `/api/wp-index-resolve`、`/api/workpapers/render-registry/{wp_code}`、`/api/workpapers/index-resolve/{wpCode}`, THE ACNR SHALL 将请求转发至统一 resolve 出口。
3. WHEN GtIndexChip 需要解析索引, THE 前端导航层 SHALL 调用 `resolve(ns:target)` 获取 addr_id 与 jump_route，而非自行 parse。
4. WHEN 解析索引引用, THE ACNR_Resolver SHALL 一次查询返回 `exists`、`trimmed` 与 `reason`。
5. IF 旧端点调用转发失败, THEN THE ACNR SHALL 返回错误，而不回退到旧解析逻辑。

---

### Requirement 14: 公式管理库消费统一 resolve（消费者契约 §7.1）

**User Story:** 作为公式管理库，我想只从 ACNR 读取选址树并在存库前校验引用，以便非法引用在编译期失败。

#### Acceptance Criteria

1. THE 公式选址器 SHALL 以 `list_sheets` + `list_cells` 按 domain 分组构建下拉树。
2. WHEN 用户保存 formula_ref, THE 公式管理库 SHALL 先调用 `resolve()` 校验，IF 引用非法 THEN THE 公式管理库 SHALL 总是在编译期返回失败。
3. THE FormulaReverseIndex 边端点 SHALL 使用 addr_id，使重命名 sheet 时边不断裂。
4. WHEN `WP()` 第三参为语义名, THE ACNR_Resolver SHALL 将其内部解析到 A1 坐标。

---

### Requirement 15: 高级查询库回写身份升级为 addr_id（G13 / D6）

**User Story:** 作为高级查询库，我想把回写身份从裸坐标升级为 addr_id，以便回写值与公式引用是同一格单一身份，stale chip 对齐。

#### Acceptance Criteria

1. WHEN `snapshot_writer` 回写快照（M2）, THE 高级查询库 SHALL 存储 `addr_id` 而非裸 `(wp_id, sheet_name, cell_ref)`。
2. THE 快照列元数据 SHALL 挂载 `addr_id`，使 chip 可下钻到具体单元格。
3. THE 查询构建器"选字段" SHALL 复用 `list_sheets` / `list_cells`（与公式选址同一棵树）。
4. WHEN 高级查询回写解析 addr_id, THE ACNR_Resolver SHALL 携带 project context 进行解析。

---

### Requirement 16: 附注库披露工厂与 note 子域坐标（G12 / D12）

**User Story:** 作为附注编制开发者，我想用一个披露工厂替代 30+ 份逐字节重复的 composable，并把披露行坐标登记进 catalog，以便新增循环不再 copy。

#### Acceptance Criteria

1. WHEN `useDisclosureSection(cycle, options)` 工厂上线（M2）, THE 附注库 SHALL 支持至少 3 个循环切换到该工厂。
2. THE ACNR_Generator SHALL 把 note 域坐标（子节/合计/披露行）登记进 catalog 的 note 子域，addr_id 形态为 `note/{note_code}/{row_key}`。
3. WHEN 循环发布 `disclosure:note-text-updated` 事件, THE 附注库 SHALL 在 payload 中携带 `addr_id`，订阅方按 addr_id 精准刷新。
4. WHEN 附注引用审定表/明细表数据, THE 附注库 SHALL 经 `resolve()` 获取物理格（附注引用即公式引用）。
5. THE 附注库 SHALL 支持通过 `disclosure:note-text-updated` 事件之外的多种机制实现按 addr_id 的精准刷新。

---

### Requirement 17: CCR 自检与 blocking 迁移（G5 / MVD-6）

**User Story:** 作为跨底稿引用的维护者，我想让 415 条 CCR 规则都能被 resolve 自检，以便"联动坏了"不再靠猜。

#### Acceptance Criteria

1. WHEN CI 运行 `check-ccr-resolve`（M1 报告模式）, THE ACNR_CI SHALL 校验每条 CCR source 可 resolve 或已标 `semantic_only`，并产出缺口清单而不阻断 PR。
2. THE L4_DependencyGraph SHALL 将 CCR 边的 source/target 端点 normalize 为 addr_id。
3. WHEN CI 在 M3 转为 blocking 模式, THE ACNR_CI SHALL 要求 blocking 级 CCR 规则 100% resolve，IF 存在未 resolve 的 blocking 规则 THEN THE ACNR_CI SHALL 阻断 PR。

---

### Requirement 18: 治理入口铁律与 CI 守卫（MVD-5 / R-ENTRY / R-ROUTE）

**User Story:** 作为平台架构组 DRI，我想强制目录只能经生成器或 overrides 双入口写入并由 CI 守卫，以便杜绝第四套手写副本导致的漂移。

#### Acceptance Criteria

1. THE ACNR SHALL 仅允许通过 ACNR_Generator 或 overrides 文件两个入口新增/修改 sheet 条目。
2. THE CONTRIBUTING 文档 SHALL 记录生成器/override 双入口流程（M0 创建）。
3. WHEN CI 运行 `check-acnr-catalog-drift`, THE ACNR_CI SHALL 校验生成器产出与已提交的 `global_catalog.json` 一致，IF 不一致 THEN THE ACNR_CI SHALL 阻断 PR。
4. WHEN CI 运行 `check-addr-id-unique`, THE ACNR_CI SHALL 校验全局 addr_id 无重复，IF 存在重复 THEN THE ACNR_CI SHALL 阻断 PR。
5. WHEN CI 运行 `check-ie-catalog-sync`, THE ACNR_CI SHALL 校验 `*_cycle_ie_manifest.yaml` 与 catalog 的 `import_export` 段一致（首期先 D 循环）。
6. THE I/E 路由 SHALL 只认 catalog 的 `api_prefix` 与 `item_id`（R-ROUTE）。

---

### Requirement 19: addr_id 不可变政策与版本锁定（R-ADDR / §13.4）

**User Story:** 作为归档合规负责人，我想让 addr_id 不可变并按项目锁定 registry_version，以便历史项目能复现当时引用的具体单元格。

#### Acceptance Criteria

1. THE ACNR SHALL NOT 允许修改已存在的 `addr_id`（改 addr_id 视为破坏性变更，须新 addr + 迁移映射表）。
2. WHEN sheet 权威名变更, THE ACNR SHALL 把旧名写入 `sheet_name_aliases` 而非修改 addr_id。
3. WHERE 坐标被弃用, THE ACNR SHALL 标记 `deprecated: true` 并保留至少一个 `registry_version`。
4. WHEN 归档项目创建, THE ACNR SHALL 记录该项目的 `registry_version`。
5. WHEN 解析归档项目引用, THE ACNR_Resolver SHALL 按该项目锁定的 `registry_version` 解析。

---

### Requirement 20: 规则冻结（MVD-1 / G7）

**User Story:** 作为评审会决策人，我想在 M0 冻结六条核心规则并归档决议，以便后续实现有统一依据、不越做越乱。

#### Acceptance Criteria

1. THE spec SHALL 冻结六条规则：R-URI（五域 URI 语法不变）、R-ADDR（addr_id 格式与不可变政策）、R-WP（WP() 2+3 参并存互转）、R-NAME（sheet_name 权威源=classification）、R-ROUTE（I/E 路由只认 api_prefix+item_id）、R-ENTRY（只许生成器或 overrides 入口）。
2. WHERE sheet_name 存在冲突, THE ACNR SHALL 以 `workpaper_sheet_classification` 为权威源（R-NAME）。
3. THE 规则拍板 SHALL 包含 bulk §8.6、A-Q 与 N-Q 决议签字归档（G7）。

---

### Requirement 21: ACNR spec 三件套（G8）

**User Story:** 作为 M0 开工门禁的把关人，我想让 ACNR spec 三件套评审通过，以便解除开工阻塞项。

#### Acceptance Criteria

1. THE ACNR spec SHALL 在 `.kiro/specs/acnr/` 下包含 requirements.md、design.md、tasks.md 三个文件。
2. THE requirements.md SHALL 把 G1–G13 与 MVD-1..8 转为可追溯的 Requirement ID。
3. WHEN 三件套评审通过且满足 G8 合规标准, THE spec SHALL 在同时具备评审批准与 G8 合规两项条件后解锁 M0 编码。

---

### Requirement 22: 首期范围与统一出口（L1 wp 域 only）

**User Story:** 作为项目排期负责人，我想把首期 L1 静态 catalog 限定在 wp 域，以便控制范围膨胀同时保持对外接口统一。

#### Acceptance Criteria

1. WHERE 域为 wp, THE global_catalog SHALL 在 M0–M1 纳入静态 JSON（全循环骨架 + D 详情）。
2. WHERE 域为 tb/report/note/aux, THE ACNR SHALL 不写入 global_catalog 而继续由 V1 动态 build 提供运行时数据。
3. WHEN 消费者经 `resolve()` 或 `/api/acnr/*` 访问任一域, THE ACNR SHALL 使消费者无需区分数据来自 L1 JSON 还是 V1 动态 build。
4. THE `workpaper_render_registry` 的 `upstream/downstream` SHALL 作为第 6 个 L4 边源纳入生成器输入，端点 normalize 为 addr_id。
5. WHEN 消费者经 `resolve()` 或 `/api/acnr/*` 访问任一域, THE ACNR SHALL 保证功能等价（无论数据来源均返回相同数据格式与行为）。

---

### Requirement 23: 缓存失效收口（D5 / §1.6）

**User Story:** 作为保存链路维护者，我想让 WP 域地址缓存失效在 orchestrator 统一触发，以便消除分散调用导致的漏失效或重复失效。

#### Acceptance Criteria

1. WHEN `WorkpaperSaveOrchestrator.after_save` 触发（M1）, THE Save_Orchestrator SHALL 统一调用 ACNR `invalidate`（可按 `trigger` / `extra.sheets` 增量）。
2. WHEN `after_save` 统一失效上线, THE 平台 SHALL 删除各 router 级重复的 `touch_wp_registry` 调用。
3. WHEN 底稿保存后 parsed_data 提交, THE ACNR SHALL 经 `register_custom()` 登记 RuntimeCellEntry。
4. IF catalog 加载失败, THEN THE ACNR SHALL 只读缓存上一版并向管理端告警，而不静默退回各模块分散 JSON。
5. IF catalog 加载失败且不存在可用的上一版缓存, THEN THE ACNR SHALL 使该操作整体失败并要求人工介入。

---

### Requirement 24: 安全与多租户隔离（§13.7）

**User Story:** 作为安全负责人，我想让自定义写入与 overlay 校验项目归属，以便防止越权访问（IDOR）。

#### Acceptance Criteria

1. WHEN 调用 `register_custom` 或写入 overlay, THE ACNR SHALL 校验 `project_id` 与 wp 归属。
2. THE 自定义底稿 addr_id SHALL 仅存在于 L2/L3，且不得写入全局 L1 种子。
3. WHEN 高级查询按 addr_id 回写, THE ACNR_Resolver SHALL 携带 project context 进行解析。
4. THE ACNR SHALL 在 L1 禁止全部 addr_id（含历史遗留 addr_id）。
