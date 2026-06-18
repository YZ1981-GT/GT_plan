# 完成阶段公共基础设施（A7–A18 共用）

## 背景

A7–A15、A16、A17、A18 四个 spec 共用同一套底稿运行时能力。本文档为 **唯一权威** 定义；各模块 spec 只写增量，须引用本节。

**消费方 spec**：

| Spec | 依赖 PRE |
|------|----------|
| [a7-a15-completion-workpapers](../a7-a15-completion-workpapers/requirements.md) | PRE-1~4（lite/core/plus） |
| [a13-misstatement-workpaper](../a13-misstatement-workpaper/requirements.md) | —（持久化见 persistence） |
| [a14-control-deficiency](../a14-control-deficiency/requirements.md) | PRE-4 阶段 3~4 |
| [a16-representation-letter](../a16-representation-letter/requirements.md) | PRE-1、PRE-3（**不**依赖 PRE-2） |
| [a17-summary-workpaper](../a17-summary-workpaper/requirements.md) | PRE-1~3、PRE-2、PRE-4-0~2 |
| [a18-regulatory-communication](../a18-regulatory-communication/requirements.md) | PRE-1~3、PRE-2（core+） |

跨模块联动与摘要 API 见 [linkage.md](./linkage.md)。  
持久化 / item_id / 别名见 [persistence.md](./persistence.md)。  
组件与 docx 清单见 [design.md](./design.md)。  
E2E 见 [e2e-matrix.md](./e2e-matrix.md)。  
索引：[completion-phase-README.md](../completion-phase-README.md)。

---

## PRE-1：docx 子码 prefilled-download

### 问题

`_index.json` 中多个子文件 `wp_code` 挂父码（如 A16、A17），或物理文件名与子码不一致（如 `A9-1向…` **无空格**），导致 `GET /api/wp-templates/{wp_code}/prefilled-download` 404。

### 要求

1. **精确匹配**：`wp_code` 查 `_index.json` 与子目录 ✅（代码已有）
2. **前缀 fallback**：精确失败时，按 `wp_templates/A/` 下文件名前缀 `{wp_code}` 匹配（含无空格变体）✅（`_match_filename_prefix`/`_find_docx_by_index_or_disk` 已落地；子码 docx 禁回退父 xlsx）
3. **占位符预填（现状以代码为准）**：
   - 已实现：client_name（××公司/ABC公司/XX公司）、audit_year（202X）、上年度（201X）
   - **未实现**：合伙人 / 签字注册会计师 — 现有代码 `XX、XX` **保留不替换**（手动填写）。若要预填须新增取数（`staff_members.name` JOIN `project_assignments.staff_id`，见 #conventions），属 PRE-1 增量任务，**不要默认它已具备**

### 验收（smoke 五件套，PRE-1 标绿须全部通过）

| wp_code | 消费 spec | 验证点 |
|---------|-----------|--------|
| A8-1 | A7–A15 | 标准路径 |
| A9-1 | A7–A15 | 无空格文件名 |
| A16-1 | A16 | 虚拟子码模板 |
| A17-3 | A17 | 子码挂父码 |
| A18-1 | A18 | 监管小结弹窗 |

---

## PRE-2：docx_template_filler.py（Word 导出引擎）

### 范围

结构化 HTML → Word 导出；**不阻塞** docx 弹窗 prefilled-download / OnlyOffice 编辑。

### 消费方

| 消费方 | 用途 |
|--------|------|
| A17-1 / A17-2-1 | 章节 / KAM 组装 export-word |
| A18-2 | 监管沟通函 export-word |
| A7–A15 plus | A8-1/2 等弹窗 docx export-word（optional） |

### **不消费** PRE-2

- **A16** 全系列：OnlyOffice + prefilled-download，不走 structured export
- **A7–A15 lite**：7 个 docx 弹窗仅下载编辑

### 颜色语义（致同模板通用）

| 类型 | 识别 | export 行为 |
|------|------|-------------|
| 红 | 公司名/年度/XX/201X | 替换为项目数据 |
| 蓝 + 【】 | 编制提示 | **删除** |
| 黑 | 固定正文 | 保留 |
| 注释表 | 模板末尾参考表 | **删除** |

### export-word 统一端点

```
GET /api/projects/{pid}/working-papers/{wp_id}/export-word
GET /api/projects/{pid}/working-papers/{wp_id}/export-word/check-incomplete
```

后端按 `wp_code` 或 `component_type` 分发到各 spec 编排服务（`a17_word_exporter`、`regulatory_letter_service` 等），**禁止**在编排层重复实现颜色语义。

---

## PRE-3：弹窗三处同步

单一数据源：`audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigs.ts`

须与以下两处保持一致：

1. `INLINE_POPUP_WP_CODES`（chip 弹窗 + preventNavigate）
2. `procedure_table_templates.json` 各程序表步骤 `ref_index`

**适用性联动**（全 spec 统一）：

- 步骤 `applicable=false` → chip **灰显**，不弹窗
- `applicable=true` 且无 OnlyOffice 实例 → 弹窗内 prefilled-download
- 已有实例 → 弹窗内在线编辑

---

## PRE-4：checklist_xlsx_parser.py

### 要求

- **新建**独立模块；**不可**扩展 `checklist_docx_parser.py`
- 输入：xlsx 模板 + 列映射（权威：`a7_a15_xlsx_audit.json` 或各 spec audit 产出）
- 输出：`{ sections, toc, stats }`，兼容 `GtChecklistTable.vue`
- 缓存：mtime 缓存（同 docx parser）

### 实施顺序（定案）

| 阶段 | 范围 | 理由 |
|------|------|------|
| 1 | **A17-5-1** 首版 | 验证 parser 接口 + GtChecklistTable 集成 |
| 2 | A17-5-2~5-5 | 同 parser，770 行扩展 |
| 3 | A15-1、A14-1 | A7–A15 core；列映射来自 audit JSON |
| 4 | A11-2、A11-3 | A7–A15 core |

维护：从 audit JSON **半自动生成**列配置；CI 跑 `audit_*_xlsx.py --diff-only` 防 drift。

---

## checkCompletion 契约（程序表 chip badge）

| 底稿类型 | 完成条件 | 负责 spec |
|----------|----------|-----------|
| A16-1~7 弹窗 | `field_overrides` scope=`word_template:A16:{code}` → `sign_status=signed` | A16 |
| docx 弹窗（A7–A15、A17、A18-1） | lite：**none**（不伪绿）；plus：export check-incomplete 通过或 OnlyOffice 有保存实例 | 各 spec plus |
| checklist-table | 必填项 conclusion 已填 / stats 100% | 各 spec core |
| structured HTML（A17-1、A18-2） | 必填章节/议题 `conclusion=done` | A17/A18 core |
| a-program-console 步骤 | 步骤 status + 关联子底稿 completion | 已有逻辑 |

**禁止**无 sign_status / 无保存即显示 completed badge。

### checkCompletion 扩展约定（防多 spec 并行覆盖）

`GtAProgramConsole.vue` 的 `checkCompletion(wpCode, responses)` 是**单点 switch**，现有 case：`A1-17 / A1-12 / A1-11 / A1-18`，`default` 返回 `'none'`（符合「lite 不伪绿」）。a16 #9、a17 core、a18 core 三个 spec 都要改**同一函数**，存在并行 PR 互相覆盖风险。约定：

1. 各 spec **只新增 case，不改 default、不动他 spec 的 case**；case 段顶部注释标注归属 spec（如 `// A16 — a16-representation-letter`）。
2. A16 的 sign_status 判定数据源是 `field_overrides`（非 `checklist_responses`），与现有基于 responses 的 case 不同源 → A16 case 须单独取数，**不要塞进** `loadPopupCompletionStatus` 的 responses 循环。
3. 若 case 超过 ~8 个，重构为「按 component_type 分发的判定注册表」（infra 统一发起，不在消费 spec 内擅自重构）。

---

## issue_tickets 取数映射（舞弊/违规）

当前 `issue_tickets.category` **无** `fraud` / `legal` 枚举。

| 监管语义 | P1 映射策略 |
|----------|-------------|
| 舞弊相关 | `severity IN ('major','blocker')` AND (`title ILIKE '%舞弊%'` OR `reason_code='fraud'`) |
| 重大违法 | `severity IN ('blocker','major')` AND (`reason_code='legal_compliance'` OR 标题关键词) |

**禁止** `WHERE category='fraud'`。

**召回率约定（实施前必确认）**：`IssueTicket` 真实 schema = `category String(64)`（自由文本，非枚举，注释 `data_mismatch/evidence_missing/...`）、`severity` 枚举 `blocker/major/minor/suggestion`、`reason_code String(64)` 可空。映射策略依赖 `reason_code='fraud'/'legal_compliance'`，但**当前无任何写入端确证会写这两个 reason_code**。INFRA-1 实施第一步须 grep 写入端：

- 若有写入端写 `reason_code` → 按上表 OR 策略；
- 若无 → 策略退化为**纯标题关键词启发式**，必须在 API 响应与 guidance UI 标注「召回不完备，仅供提示」，且 P1 **不**作为判定依据。

P1 仅返回 **计数 + 标题列表** 供 guidance 提示；**不自动写入** Word/HTML 正文（A17 拉取、A18 issue_hints、A7–A15 plus 均遵守）。

---

## 适用性统一口径

```python
# 唯一入口：ProcedureTableService._check_applicable
# 数据源：procedure_table_templates.json → applicable_categories
# 项目：business_category → get_category_prefix() → "A"|"B"|"C"
# 禁止：template_type == 'listed' 用于 A 类/A17 适用性
```

| Spec | 典型 applicable_categories |
|------|---------------------------|
| A7–A15 | `["A","B"]`（步骤级差异见各 spec） |
| A16 | 全类适用；子码版本按 matrix 推荐 |
| A17 | `["A"]` 为主 |
| A18 | `["A","B"]` |

---

## 现状与差距（公共层）

| 能力 | 目标 | 代码现状 |
|------|------|----------|
| PRE-1 fallback（代码） | 子码 + 前缀匹配 | ✅ 已落地（`_match_filename_prefix`） |
| PRE-1 E2E | smoke 五件套 | ⚠️ 未标绿（依赖 FIX 夹具） |
| PRE-1 合伙人预填 | 签字会计师占位符 | ❌ 现状保留不替换（可选） |
| PRE-2 filler | export-word 颜色语义引擎 | ✅ `docx_template_filler.py` 已建（红替换转黑/蓝删/注释表删） |
| PRE-3 弹窗配置 | 三处同步 | ✅ `wpPopupDocxConfigs.ts` 已配置 |
| PRE-4 xlsx parser | A17-5-1~5 + A15-1 + A14-1 + A11-2/3 | ✅ `checklist_xlsx_parser.py`（4 阶段全完） |
| export-word 端点 | 统一路由 + check-incomplete | ✅ 骨架已建（dispatch→501，各 spec 注册 handler 后激活） |
| INFRA-1 issue_hints | 舞弊/违规计数 | ✅ 纯标题关键词启发式（`heuristic_only=True`） |
| INFRA-2 摘要 API | workpaper-summaries/{key} | ✅ 5 key；misstatement/related_party/going_concern/control_deficiency/governance 已实现 |
| INFRA-3 CI drift | `--diff-only` 门禁 | ✅ CI job `audit-xlsx-drift` 已加 |
| checkCompletion A16 | sign_status（field_overrides） | ✅ `GtAProgramConsole.checkCompletion` A16-x case |
| E2E FIX-A 夹具 | A 类种子项目 | ⚠️ spec 已写（`a16/a17/a18` e2e）；需 `RUN_FULL_E2E=1` + `TEST_PROJECT_ID` |
