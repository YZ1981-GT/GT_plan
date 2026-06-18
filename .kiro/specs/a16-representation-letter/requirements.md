# A16 管理层声明书底稿

## 背景

A16 是完成阶段**所有项目必做**的底稿——获取经管理层签署的管理层声明书是审计报告签发的前置条件（ISA 580 / 中国注册会计师审计准则第 1321 号）。

底稿结构（见 `backend/wp_templates/A/`）：

| 底稿 | 格式 | 模式 |
|------|------|------|
| A16 管理层声明书程序表 | xlsx | 程序表控制台（`a-program-console`，已有） |
| A16-1 财务报表审计（企业会计准则） | docx | 主声明书版本之一 |
| A16-2 整合审计 | docx | 主声明书版本之一 |
| A16-3 IPO 申报报表审计 | docx | 主声明书版本之一 |
| A16-4 IPO 季度财务报表审阅 | docx | 主声明书版本之一 |
| A16-5 新三板申报报表审计 | docx | 主声明书版本之一 |
| A16-6 企业债（企业会计准则） | docx | 主声明书版本之一 |
| A16-7 管理层关联交易声明书 | docx | **补充声明**（可与主声明书并行） |

**核心交互原则：按类型弹窗或跳转**

- **A16 程序表 / 索引 A16** → **跳转页**（`word-template` → `WorkpaperWordEditor.vue`）
- **A16-1~7 程序表 chip** → **弹窗**（`WpPopupDocxEditor`）：说明 + 预填充下载 + 在线编辑
- **索引 A16-1~7（虚拟码）** → **重定向**至 A16 跳转页 + `?version=A16-x`（不单独建 WorkingPaper 实例）

## 索引与子码实例模型

| 问题 | 决策 |
|------|------|
| 是否生成 7 个子底稿实例？ | **否** — 每项目仅 **1 个** A16 WorkingPaper 实例 |
| A16-1~7 在索引中的角色 | **虚拟 wp_code**（`wp_account_mapping` 保留元数据，渲染层重定向） |
| 文件存储 | 主版本 docx 按 `selected_version` 切换模板源；A16-7 可独立上传/编辑 |

## 前置依赖（阻塞项）

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-1、PRE-3）。  
> **本 spec 不依赖 PRE-2**（OnlyOffice + prefilled-download，非 structured export）。  
> 占位符清单：`backend/data/docx_placeholder_registry.json`

| 依赖 | 阻塞范围 |
|------|----------|
| PRE-1 | A16-1~7 弹窗 prefilled-download |
| PRE-3 | 程序表 ref_index + INLINE_POPUP 三处同步 |

## 适用条件

- **A16 程序表**：A/B/C 类**全部适用**
- **子码版本**：按 `business_category` **子码** + 半自动信号推荐（见 design §版本矩阵），**非推荐版本仍可手动选用**
- ⚠️ 不使用 `template_type == 'listed'` 判定版本适用性

### 版本推荐矩阵（权威配置：`backend/data/a16_version_matrix.json`）

| 子码 | 名称 | 自动推荐条件 | 置信度 | 与主声明书关系 |
|------|------|-------------|--------|----------------|
| A16-1 | 企业会计准则 | 默认（以上均未命中） | 高 | 主声明书（互斥选一） |
| A16-2 | 整合审计 | B60 内控程序表已启用 **或** 项目 `audit_type` 含整合信号 | 中（须用户确认） | 主声明书 |
| A16-3 | IPO 申报 | `business_category` = **A2** | 高 | 主声明书 |
| A16-4 | IPO 季度审阅 | 无可靠自动字段；wizard/手动标记 `ipo_quarterly_review` | 低（lite 手动选） | 主声明书 |
| A16-5 | 新三板 | `business_category` = **B1** | 高 | 主声明书 |
| A16-6 | 企业债 | `business_category` = **B2** | 高 | 主声明书 |
| A16-7 | 关联交易声明书 | A7 关联交易计数 > 0 | 中 | **补充**，独立签回 |

A16-1~6 **互斥**；A16-7 **可选叠加**，UI 与签回状态均与主版本**分离**。

## 模板颜色语义（致同通用，与 A17/A18 一致）

- **红色文字** = 需根据项目填写/选择
- **蓝色文字** = 编制提示，正式文件中**必须删除**
- **黑色文字** = 固定正文
- **注释表格** = 编制参考，交付前删除

## 交付分期

| 分期 | 范围 | DoD |
|------|------|-----|
| **A16-lite** | PRE-1 + 版本矩阵 + 程序表 + 弹窗 E2E + 完成态 | 推荐 chip→弹窗→下载 docx；chip 完成 badge 正确 |
| **A16-core** | 跳转页主/补分离 + 按版本签回 + A13 联动 | 切版本签回独立；刷新后状态仍在 |
| **A16-plus** | 签署日期→报告 + QC 对齐 + 分期 E2E | CW-76 可用 |

---

## 需求

### 1. A16 程序表

- 组件：`GtAProgramConsole`（已有）
- **步骤策略**：`procedure_table_templates.json` 采用 **4 步简化版**（lite 先行）；xlsx 模板实际有 7 行（`sheet_mapping_rules.json`：草拟声明书→归档），**plus 阶段**可选从 xlsx 提取对齐，lite 不阻塞

| seq | 内容 | ref_index | auto_data_source |
|-----|------|-----------|------------------|
| 1 | 确定声明书版本 | — | `a16_template_recommend` |
| 2 | 编制管理层声明书（主版本） | 见下「chip 展示规则」 | — |
| 3 | 编制关联交易声明书（如适用） | `A16-7` | `related_party_transaction_count` |
| 4 | 获取管理层签署 | `A16`（跳转页签回） | — |

**seq2 chip 展示规则（避免 6 chip 堆叠）**：
- 默认展示：**推荐版本 chip**（带「推荐」badge）+「其他版本 ▼」折叠展开 A16-1~6 其余项
- 展开后所有主版本 chip **均可点击**（非推荐不禁用，仅排序靠后）
- seq3：`applicable_default: "no"`；A7 有交易时 auto 建议适用，用户可手动改

**步骤适用性**：步骤 `applicable=false`（如 seq3 裁剪）→ chip 灰显；**非推荐主版本不禁灰**

### 2. A16-1~7 — 弹窗模式

- 配置源：`wpPopupDocxConfigs.ts`（已在 `DOCX_POPUP_WP_CODES`）
- 程序表 chip → 弹窗 + `preventNavigate`
- 弹窗内「完整编辑」→ 跳转页 + 同步 `?version=`
- **端到端验收**：`prefilled-download` 返回有效 docx（依赖 PRE-1）

**弹窗完成态判定**（程序表 chip badge，`GtAProgramConsole.checkCompletion` 须新增 case）：

| wp_code | 完成条件 |
|---------|----------|
| A16-1~6 | `field_overrides` scope=`word_template:A16:{code}` sign_status=`signed` |
| A16-7 | scope=`word_template:A16:A16-7` sign_status=`signed` |

未完成时 badge 不亮绿（禁止伪绿）。

### 3. A16 — 跳转页模式

- `_WP_CODE_OVERRIDE["A16"] = "word-template"`（已有，须 E2E 验证）
- 组件：`WorkpaperWordEditor.vue`（已有骨架，**须改造**）

**UI 分区（主版本 / 补充声明分离）**：

1. **主声明书区**（A16-1~6）：互斥 radio + 推荐 badge
2. **补充声明区**（A16-7）：独立 toggle「需编制关联交易声明书」+ 独立操作栏
3. 占位符预填、OnlyOffice、降级下载/上传
4. A13 错报摘要 alert（见 API 路径）
5. **按版本签回**：pending → sent → signed，scope **含版本号**

**field_overrides 契约**：

| scope | field | 值 |
|-------|-------|-----|
| `word_template:A16` | `selected_version` | `A16-1`~`A16-6`（主版本，不含 A16-7） |
| `word_template:A16:{version}` | `sign_status` | `pending`/`sent`/`signed`（**每主版本独立**） |
| `word_template:A16:A16-7` | `sign_status` | 补充声明独立签回 |
| `word_template:A16:A16-7` | `enabled` | `true`/`false` |

切换主版本时，签回状态读取对应 scope，**不继承**其他版本的 signed。

**API（已有，路径以代码为准）**：
- A13 错报：`GET /api/projects/{pid}/misstatements/for-letter?year=`
- 签回：`GET/POST .../working-papers/{wp_id}/file-info` / `sign-status`

### 4. 版本智能推荐（A16-lite）

- 新建 `backend/data/a16_version_matrix.json` + `a16_version_service.py`
- 替换 `a16_template_recommend` 桩
- 输出：`{ code, label, reason, confidence: high|medium|low }`
- 中/低置信度时 seq1 摘要追加「请项目组确认」

### 5. 签回与审计报告联动（A16-plus）

- **CW-76**：签回时用户**必填**签署日期（默认审计报告日，可改），push 至 `audit_report.representation_letter_date`
- 禁止从 docx 元数据自动推断签署日期（不可靠）
- QC 仪表盘 wizard_state「管理层声明」与主版本 `sign_status=signed` 对齐

## 关联模块

| 模块 | 关系 |
|------|------|
| A1 seq 9 | `ref_index: A16` → A16 程序表；plus：主版本 signed 时可 auto 建议 completed |
| A13 | 未更正错报 alert +（core 可选）docx 占位符写入 |
| A7 | A16-7 适用性 + 推荐 |
| A8-1 | 可整合进主声明书（relatedLinks 已有；plus 可选提示） |
| 审计报告 | CW-76 签署日期（A16-plus） |

联动详情：[linkage.md](../completion-phase-infra/linkage.md)

## 现状与差距（A16 特有）

> 公共 PRE 状态见 [infra §现状](../completion-phase-infra/requirements.md#现状与差距公共层)。

| 能力 | 目标 | 代码现状 | 分期 |
|------|------|----------|------|
| A16 程序表 | 4 步 + chip 折叠 | ⚠️ ref_index、completion | lite |
| wpPopupDocxConfigs | 7 项配置 | ✅ | lite E2E **E8** |
| WorkpaperWordEditor | 主/补分离 + 按版本签回 | ⚠️ 骨架（`components/workpaper/` 版，非 views/）；A16-7 混 radio | core |
| checkCompletion A16 | sign_status case | ❌ | lite |
| a16_version_service | 版本推荐 | ❌ 桩 | lite |
| 虚拟子码重定向 | A16-x → A16?version= | ❌ | core |
| CW-76 | sign_date → 报告 | ❌ | plus **E16** |
