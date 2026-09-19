# Requirements Document

## Introduction

函证枢纽底稿（D0/E0/F0/G0/H0/K0/L0）在平台上此前点「编辑」会被整体重定向到函证管理中心台账，源模板里的多 sheet 编制界面（底稿目录 / X0A 程序表 / X0-1 函证结果汇总 / X0-2 核实被函证单位 / X0-3 跟函过程控制 / X0-4 差异调节 / X0-5·X0-6 替代程序 / X0-7 回函可靠性 / X0-8 舞弊风险）一张都到不了。

本 spec 的目标是把「底稿层编制」与「中心层台账」做成**两层并存且双向联动**的完整闭环：审计师在底稿编辑器里按源模板逐 sheet 编制，编制结果汇聚到项目级函证台账（发函/回函/差异状态），台账的回函结果又回流到底稿（X0-1 汇总状态、各科目明细「已函证」标记、未回函自动带入替代程序）。

**P0 已完成（本 spec 的基线，需锁定零回归）**：`confirmation-hub` 已加入 `HTML_RENDERER_ROUTE_SET`（只进路由集合、不进 registry，对齐 `skip` placeholder 模式），`WorkpaperEditor` 已移除整体重定向并在标题栏提供「函证管理中心」入口按钮。F0 实测呈现 12 个 tab、8 张逐一验证专属组件真实挂载、0 相关 console error。

**已实证的现状基线（Requirements 以此为准，不得假设）**：

- **后端 render-config 已完备**：F0（`wp_code='F0'`，11 行 `workpaper_sheet_classification`）返回 11 个 sheet，每个 sheet 的 componentType 均正确派生（`b-index` / `a-program-console` / `confirmation-summary` / `confirmation-entity-verify` / `confirmation-followup` / `confirmation-diff-reconcile` / `confirmation-diff-checklist` / `confirmation-alternative-f05` / `confirmation-alternative-f06` / `confirmation-reliability` / `confirmation-fraud-risk`）。**本 spec 不需要后端 render 改动。**
- **`GtWpRenderer` 按 per-sheet componentType 分发**，workbook 级类型仅用于「走 HTML 渲染器而非 Univer」的判定。
- **底稿→台账同步已接线**：`GtConfirmationSummary` 有「同步到函证中心」按钮（`v-if="!readonly"`，无数据量门控）+ 保存后 `_autoSyncAfterSave()` 自动同步 + `emitConfirmationCompletedFromSummary()` 批量回写科目明细。**空态时该 toolbar 被"开始编制函证底稿"引导视图替换，故按钮不可见——这是空态呈现问题，不是接线缺失。**
- **台账→底稿回流已有基础**：`ConfirmationHub.executeTransition` 在 returned/matched/discrepancy 三终态 emit `confirmation:received`；后端 `transition_confirmation` 终态调 `apply_confirmation_result` 发 `CONFIRMATION_RECEIVED`，`_on_confirmation_received` 触发下游 stale。
- **未回函→替代程序带入现状不一致（真缺口）**：D0-5 / H0-5 / K0-6 / L0-5 已真实实现；**D0-6 / F0-5 / F0-6 是 STUB 桩**（`ElMessage.info('从 X0-1 带入功能待跨底稿引用 API 接入后启用')`）；K0-5 无带入入口。共用能力 `coordination/importFromSummary.ts` 已存在。

**范围边界**：不改后端 render 策略与 sheet 分类；不改函证台账数据模型（`confirmation` 表）与状态机；不改 OCR / 附件证据链（归 `confirmation-attachment-ocr-linkage`）；不改替代程序各自的区块列结构（`blockColumnConfigs*`）。

## Glossary

| 术语 | 含义 |
|------|------|
| Hub_Workbook | 函证枢纽底稿（D0/E0/F0/G0/H0/K0/L0），workbook 级 componentType = `confirmation-hub` 的多 sheet 工作簿 |
| Hub_Sheet | Hub_Workbook 内的单张 sheet（底稿目录 / X0A / X0-1 ~ X0-8），各自有已注册的专属 componentType |
| Confirmation_Center | 项目级函证管理中心台账页面（路由 `ConfirmationHub`，读写 `confirmation` 表） |
| Summary_Sheet | X0-1 函证结果汇总表（`confirmation-summary`），confirmation-v1 编制真源 |
| Alternative_Sheet | X0-5 / X0-6 替代程序底稿（`confirmation-alternative-*`） |
| Sync_To_Center | Summary_Sheet → Confirmation_Center 的 upsert 同步（`syncHubFromSummary`） |
| Reply_Backflow | Confirmation_Center 回函结果 → 底稿的回流（Summary_Sheet 状态 + 科目明细 `isConfirmed`） |
| Unreplied_Pull | 未回函项目从 Summary_Sheet 带入 Alternative_Sheet（`importFromSummary`） |
| Center_Entry | 底稿编辑器标题栏的「函证管理中心」入口按钮 |
| Linkage_Matrix | 7 个枢纽 × 各项联动能力（Sync_To_Center / Reply_Backflow / Unreplied_Pull / Center_Entry）的覆盖矩阵 |
| Sheet_Code_Tail | `wp_render_config._SHEET_CODE_RE` 从 sheet_name **尾部**提取的 sheet 级编码（如「合同负债及销售替代程序D0-5」→ `D0-5`），编码不在尾部时提取失败 |
| Program_Template_Code | 程序表渲染时用于查 `procedure_table_templates.json` 的 key（`_a_program.py` 从 sheet_name 正则提取，提取不到回退父 wp_code） |
| Index_Code_Map | sheet_name ↔ 该 sheet 在源模板内真实索引号 的对照表（用于纠正跨枢纽复制造成的编码污染显示） |

## Requirements

### Requirement 1: Hub_Workbook 底稿多 sheet 可达（P0 基线锁定）

**User Story:** 作为审计助理，我要在底稿编辑器里按源模板逐 sheet 编制函证底稿，而不是被弹到台账页面。

#### Acceptance Criteria

1. WHEN 打开任一 Hub_Workbook 底稿 THEN 系统 SHALL 在底稿编辑器内渲染其全部 Hub_Sheet 作为页签，且页签集合与该底稿在 `workpaper_sheet_classification` 中的 sheet 集合一致
2. WHEN 打开任一 Hub_Workbook 底稿 THEN 系统 SHALL NOT 重定向到 Confirmation_Center
3. WHEN 切换到任一 Hub_Sheet 页签 THEN 系统 SHALL 挂载该 sheet componentType 对应的已注册专属组件，且 SHALL NOT 显示「尚未支持渲染」占位或「加载底稿失败」
4. WHERE workbook 级 componentType 为 `confirmation-hub` THE 系统 SHALL 将其纳入走 HTML 渲染器的判定集合，且 SHALL NOT 为其在渲染注册表中注册组件（分发按 per-sheet componentType）
5. WHEN 底稿深链带 `?sheet=` 参数指向某 Hub_Sheet THEN 系统 SHALL 初始激活该页签

### Requirement 2: 底稿与 Confirmation_Center 双向导航

**User Story:** 作为审计助理，我在底稿里编制时要能一键去台账看发函/回函全貌，在台账里也要能回到对应底稿继续编制。

#### Acceptance Criteria

1. WHEN 打开 Hub_Workbook 底稿 THEN 系统 SHALL 在标题栏显示 Center_Entry 入口
2. WHEN 点击 Center_Entry THEN 系统 SHALL 导航到当前项目的 Confirmation_Center
3. WHERE 底稿非 Hub_Workbook THE 系统 SHALL NOT 显示 Center_Entry
4. WHEN 在 Confirmation_Center 查看某条函证记录且该记录有来源底稿标识 THEN 系统 SHALL 提供跳回该 Hub_Workbook 的 Summary_Sheet 的入口
5. IF 跳转目标底稿在本项目未实例化 THEN 系统 SHALL 给出明确提示而非静默失败或跳到底稿目录

### Requirement 3: Summary_Sheet → Confirmation_Center 同步（Sync_To_Center）

**User Story:** 作为现场经理，我要底稿里编制的函证明细自动汇到项目台账，这样覆盖率与发函进度才有单一口径。

#### Acceptance Criteria

1. WHEN Summary_Sheet 保存 THEN 系统 SHALL 自动执行 Sync_To_Center，把「已进入函证程序」的行 upsert 到台账并按状态机推进
2. WHEN 用户在 Summary_Sheet 点击「同步到函证中心」THEN 系统 SHALL 执行同步并以明确文案回报结果（新建/更新/推进的条数，或「暂无需同步的行」）
3. WHERE Summary_Sheet 处于空态（尚无函证行）THE 系统 SHALL 仍保持 Sync_To_Center 入口可达（空态引导视图不得吞掉该入口）
4. WHEN 同步成功且台账返回记录标识 THEN 系统 SHALL 把该标识回写并持久化到底稿行，使重复同步幂等而非重复建单
5. IF 同步失败（网络/权限/校验）THEN 系统 SHALL 给出失败原因提示且 SHALL NOT 丢失底稿已编制内容
6. WHERE 当前用户为只读或 EQCR 视图 THE 系统 SHALL 隐藏或禁用 Sync_To_Center 入口

### Requirement 4: Confirmation_Center 回函 → 底稿回流（Reply_Backflow）

**User Story:** 作为审计助理，台账里登记的回函结果要自动回到底稿，不要在两处重复录。

#### Acceptance Criteria

1. WHEN 台账中某条函证被推进到回函终态（已回函/相符/差异）THEN 系统 SHALL 通知当前打开的 Summary_Sheet 刷新对应行的回函状态与回函金额
2. WHEN 回函结果为「差异」THEN 系统 SHALL 使该差异可被 X0-4 差异调节表消费（带入或提示存在未调节差异）
3. WHEN 回函完成 THEN 系统 SHALL 批量回写各科目明细底稿的「已函证」标记
4. WHERE 底稿行已被审计师手工修改过对应字段 THE 系统 SHALL NOT 静默覆盖手工值（手工优先或给出冲突提示）
5. IF 回流目标底稿未打开 THEN 系统 SHALL 保证下次打开时能从持久化数据读到回函结果（不依赖同会话事件）

### Requirement 5: 未回函 → 替代程序带入（Unreplied_Pull）

**User Story:** 作为审计助理，对未回函的单位我要一键把清单带进替代程序底稿，而不是手工重抄。

#### Acceptance Criteria

1. WHEN 在 Alternative_Sheet 点击「从 X0-1 带入」THEN 系统 SHALL 从同项目 Summary_Sheet 读取未回函项目并生成待检查清单行
2. WHERE Alternative_Sheet 当前为 STUB 桩实现（D0-6 / F0-5 / F0-6）THE 系统 SHALL 改为真实带入，且 SHALL NOT 再返回「待接入后启用」类提示
3. WHERE 枢纽的替代程序缺少带入入口（K0-5）THE 系统 SHALL 补齐入口
4. WHEN 带入的项目在 Alternative_Sheet 已存在 THEN 系统 SHALL 去重而非重复追加
5. WHEN 带入完成 THEN 系统 SHALL 报告带入条数；WHEN 无未回函项目 THEN 系统 SHALL 明确提示「无未回函项目」
6. WHERE Summary_Sheet 未编制或不可读 THE 系统 SHALL 给出可理解提示且 SHALL NOT 抛未捕获异常

### Requirement 6: 七枢纽一致性（Linkage_Matrix）

**User Story:** 作为业务合伙人，我不希望同一能力在应收函证有、在应付函证没有，各循环行为要一致可预期。

#### Acceptance Criteria

1. WHEN 实施开始前 THEN 系统 SHALL 产出 D0/E0/F0/G0/H0/K0/L0 七个枢纽的 Linkage_Matrix（每枢纽的 sheet 集合、各项联动能力现状：已实现 / STUB / 缺失）
2. WHERE 某项联动能力在任一枢纽已实现 THE 系统 SHALL 使其在全部具备对应 sheet 的枢纽上行为一致
3. WHERE 某枢纽源模板确实没有对应 sheet THE 系统 SHALL 在 Linkage_Matrix 中登记为「不适用」并说明依据，且 SHALL NOT 臆造该 sheet
4. WHEN 联动能力实现为共用能力 THEN 系统 SHALL 复用既有共用模块（`importFromSummary` / `syncHubFromSummary` / `emitConfirmationCompleted`）而 SHALL NOT 新造并行的第二套实现
5. WHEN Linkage_Matrix 中的项目落地后 THEN 系统 SHALL 有守卫（契约测试或检查脚本）防止某枢纽被漏接后静默漂移

### Requirement 7: 联动可追溯

**User Story:** 作为质量控制复核合伙人，我要能看清底稿里的函证数字从哪来、同步到哪去。

#### Acceptance Criteria

1. WHEN Summary_Sheet 的行已同步到台账 THEN 系统 SHALL 在底稿上可见其同步状态（已同步/未同步）
2. WHEN 某底稿数据来自另一 Hub_Sheet 或台账 THEN 系统 SHALL 标注来源（索引芯片或来源说明）
3. WHEN Alternative_Sheet 的行由 Unreplied_Pull 带入 THEN 系统 SHALL 标注其来源为 X0-1 带入
4. WHERE 联动动作改变了底稿数据 THE 系统 SHALL 使该变更可经版本链回溯

### Requirement 8: 零回归与增量可回退

**User Story:** 作为平台维护者，函证中心与七个枢纽是生产在用的，任何改动不能破坏既有能力。

#### Acceptance Criteria

1. WHEN 本 spec 改动落地 THEN Confirmation_Center 既有能力（台账 CRUD、状态机推进、从底稿导入、批量同步、覆盖率统计）SHALL 逐字保持
2. WHEN 本 spec 改动落地 THEN 既有函证域前端测试（当前 39 文件 / 710 例）与渲染注册表契约测试 SHALL 全部通过
3. WHEN 本 spec 改动落地 THEN 非 Hub_Workbook 底稿的编辑器路由行为 SHALL 逐字不变
4. WHERE 某项联动按枢纽分批实施 THE 每批 SHALL 独立可发布且可单独回退
5. WHEN 后端存在既有缺陷（如 `confirmations/match-queue` 500）THEN 本 spec SHALL 不将其纳入范围，但 SHALL 不因其失败而阻断底稿层能力

### Requirement 9: 属性化可测

**User Story:** 作为平台维护者，我要联动规则以可测属性表达，避免回归靠人工点检。

#### Acceptance Criteria

1. WHEN 定义 Sync_To_Center THEN 系统 SHALL 具备幂等属性测试（同一批行重复同步不产生重复台账记录）
2. WHEN 定义 Unreplied_Pull THEN 系统 SHALL 具备去重属性测试（重复带入不产生重复行）
3. WHEN 定义 Reply_Backflow THEN 系统 SHALL 具备手工优先属性测试（已手工修改的字段不被覆盖）
4. WHEN 定义 Linkage_Matrix THEN 系统 SHALL 具备覆盖守卫测试（七枢纽应实现项无遗漏）
5. WHEN 定义 Requirement 1 的 sheet 可达性 THEN 系统 SHALL 具备契约测试（workbook 级类型在路由集合内且不在渲染注册表内）

### Requirement 10: 路由解析与索引编码治理（P0 阻断修复）

**User Story:** 作为审计助理，我要每张函证 sheet 都渲染成它自己该有的那张表、程序表加载该循环自己的程序清单、索引号显示自己的编码，而不是被别的循环的编码劫持。

**背景（已实证，非假设）**：`wp_render_config._SHEET_CODE_RE = ([A-Z]\d+(?:-\d+)*[A-Z]?)(?:-新增)?\s*$` 要求编码在 sheet_name **尾部**；`_sheet_ovr` 解析顺序为「尾码 override → sheet_name 精确 override → `{wp_code}-{sheet_name}` override」（`wp_render_config.py` 已具备 sheet_name 精确 fallback，故本需求的修法不需改解析器）。`_a_program.py` 的 Program_Template_Code 由 sheet_name 正则提取，不校验其循环前缀是否等于父 wp_code。

#### Acceptance Criteria

1. WHERE 某 Hub_Sheet 的 Sheet_Code_Tail 提取失败（编码不在尾部，如「函证差异核对表G0-3（证券投资）」「函证差异核对表G0-4(非证券投资)」）THE 系统 SHALL 经 sheet_name 精确 override 命中其应有 componentType，且 SHALL NOT 落 `confirmation-hub` / `onlyoffice-sheet` 兜底
2. WHEN G0 的证券投资差异核对表被渲染 THEN 系统 SHALL 挂载 `confirmation-diff-securities` 组件（该组件在此修复前为全平台零渲染）
3. WHERE `wp_code_overrides.json` 中存在 sheet_name 里不存在的编码 key（如 `G0-3S`）THE 系统 SHALL 将其标注为死配置或移除，且 SHALL NOT 依赖其生效
4. WHEN 渲染任一 Hub_Workbook 的程序表 sheet THEN 系统 SHALL 使用**所属循环**的 Program_Template_Code（L0 的「函证程序表F0A」SHALL 命中 `L0A` 模板而非 `F0A`），使该循环已存在的程序表 JSON 模板（含 `risk_for_cycle` / `control_test_result_for_cycle` 等 auto_data_source 联动）生效
5. WHERE 某 sheet 的 Program_Template_Code 循环前缀与父 wp_code 循环不一致 THE 系统 SHALL 优先按父 wp_code 推导模板 key，且 IF 该 key 无模板 THEN 系统 SHALL 回退到既有 xlsx 提取行为（不得因治理而丢失原有程序行）
6. WHEN 治理落地 THEN 系统 SHALL 产出 Index_Code_Map（各 Hub_Sheet 的 sheet_name、Sheet_Code_Tail、源模板内真实索引号、偏差原因），并在底稿内索引号显示与 sheet_name 尾码不一致时以 Index_Code_Map 为准或明示为已知偏差
7. WHEN 治理落地 THEN 系统 SHALL 具备契约守卫：每个 Hub_Workbook 的每张未 skip 的 sheet 都能解析到**非兜底**的 componentType（不得为 `confirmation-hub` / `skip`），新增或改名 sheet 漏配时 SHALL 使守卫失败
8. WHERE 源模板自身存在编码污染（D0-6/D0-7/D0-8 内部索引写 F0-*、K0-1 调节索引写 K1-12、L0-1 调节索引写 F0-4）THE 系统 SHALL NOT 修改源 xlsx，而 SHALL 在 Index_Code_Map 中登记偏差并保证跨底稿引用芯片指向正确目标
9. WHEN 治理落地 THEN 非 Hub_Workbook 底稿的 sheet componentType 解析结果 SHALL 逐字不变
