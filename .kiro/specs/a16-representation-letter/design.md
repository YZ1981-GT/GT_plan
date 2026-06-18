# A16 管理层声明书 — 设计文档

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-1、PRE-3）。**不含 PRE-2**。

---

## 架构总览

```
程序表 A16
  ├─ seq1 版本推荐 ──→ a16_version_service → auto_data summary
  ├─ seq2 主版本 chip ──→ [推荐] + [其他版本▼] → 弹窗
  │       └─「完整编辑」→ 跳转页 ?version=A16-x
  ├─ seq3 A16-7 chip ──→ 弹窗（补充）
  └─ seq4 获取签署 ──→ 跳转页（主版本 + A16-7 分区签回）

索引 A16 ──→ 跳转页
索引 A16-x（虚拟码）──→ 302/路由重定向 → A16 + ?version=A16-x
```

### 弹窗 vs 跳转

| 场景 | 行为 |
|------|------|
| 程序表 ref_index chip | **弹窗** |
| 索引 A16 / seq4 / 「完整编辑」 | **跳转页** |
| 索引 A16-1~7 | **重定向**跳转页 + version query |
| A16 父码 | 不在 `INLINE_POPUP_WP_CODES`，正常跳转 |

### 虚拟子码渲染

```python
# wp_render / 路由层（A16-lite）
if wp_code.startswith("A16-") and wp_code != "A16":
    redirect_to_parent("A16", query={"version": wp_code})
# 不创建独立 WorkingPaper；不注册 _WP_CODE_OVERRIDE
```

---

## 版本推荐

### 配置文件

`backend/data/a16_version_matrix.json`（lite task 3 新建）：

```json
{
  "main_versions": [
    {"code": "A16-3", "label": "IPO申报", "match": {"business_category": ["A2"]}, "confidence": "high"},
    {"code": "A16-5", "label": "新三板", "match": {"business_category": ["B1"]}, "confidence": "high"},
    {"code": "A16-6", "label": "企业债", "match": {"business_category": ["B2"]}, "confidence": "high"},
    {"code": "A16-2", "label": "整合审计", "match": {"signals": ["integrated_audit"]}, "confidence": "medium"},
    {"code": "A16-4", "label": "IPO季度审阅", "match": {"signals": ["ipo_quarterly_review"]}, "confidence": "low"},
    {"code": "A16-1", "label": "一般财报", "match": {"default": true}, "confidence": "high"}
  ],
  "supplement": {
    "code": "A16-7",
    "match": {"related_party_txn_count_gt": 0}
  }
}
```

### 服务

`backend/app/services/a16_version_service.py`

```python
async def recommend_main_version(db, project_id) -> dict:
    """
    1. 读 project.business_category → 匹配 matrix 子码规则
    2. integrated_audit 信号（lite 半自动）：
       - B60 程序表存在且 applicable != na，或
       - review_workflow audit_type 含 internal_control
    3. ipo_quarterly_review：仅 wizard_state / field_overrides 手动标记
    4. 多规则命中 → 取 confidence 最高；同级 → matrix 声明顺序
    返回 { code, label, reason, confidence }
    """
```

前端 `WorkpaperWordEditor` 与 `procedure_table_auto_service.a16_template_recommend` **共用此服务**。

⚠️ **禁止**引用不存在的 Project 字段（`integrated_audit`、`ipo_application` 等）。

---

## 组件设计

### WorkpaperWordEditor.vue（须改造）

> ⚠️ **文件路径歧义**：仓库存在两个同名文件 —
> - `components/workpaper/WorkpaperWordEditor.vue` ← **改造目标**（`htmlRendererRegistry` 的 `word-template` 指向此文件）
> - `views/WorkpaperWordEditor.vue`（Univer/TipTap 独立编辑视图，**非**本 spec 目标）
>
> 实施时只改 `components/workpaper/` 版本，勿误改 views 版。

**布局**：

```
┌─ 主声明书（A16-1~6 互斥 radio，推荐项置顶 + badge）──┐
│  [OnlyOffice] [下载] [上传]  签回: pending/sent/signed │
├─ A13 错报 alert ─────────────────────────────────────┤
├─ 补充声明 A16-7 [toggle] ────────────────────────────┤
│  （启用后）独立编辑/签回，scope word_template:A16:A16-7 │
└─ 编制信息（占位符预览）──────────────────────────────┘
```

**OnlyOffice document_key**：`{project_id}:A16:{selected_version}:{file_version}`

**版本切换**：切换主版本时加载对应模板文件（`prefilled-download?wp_code=A16-x`），签回读 `word_template:A16:{x}`。

### WpPopupDocxEditor

- 配置：`wpPopupDocxConfigs.ts` 7 项
- 下载：`GET /api/wp-templates/{wp_code}/prefilled-download`（PRE-1 后）
- `relatedLinks` + 「完整编辑」→ `/workpapers/A16?version=A16-x`

### GtAProgramConsole — seq2 chip 折叠

```typescript
// seq2 ref_index 仍配置全量 A16-1~6（JSON 源）
// 渲染层：
const recommended = await fetchRecommendedVersion()
const visibleChips = expanded ? allMainVersions : [recommended, ...othersCollapsed]
// 非推荐版本：不禁用，仅默认折叠
```

### checkCompletion（须新增）

```typescript
function checkCompletion(wpCode: string, ...): ... {
  // ...
  if (wpCode.match(/^A16-[1-7]$/)) {
    // 读 field_overrides sign_status for scope word_template:A16:{wpCode}
    // signed → 'completed'; sent → 'in_progress'; else 'none'
  }
}
```

lite 可先读 `checklist_responses` 缓存字段；core 接 field_overrides API。

---

## 后端 API

### 已有（E2E 验证，非新建）

| 端点 | 用途 |
|------|------|
| `GET /api/projects/{pid}/working-papers/{wp_id}/file-info` | 文件 + sign_status |
| `POST /api/projects/{pid}/working-papers/{wp_id}/sign-status` | 更新签回 |
| `GET /api/wp-templates/{wp_code}/prefilled-download` | docx 预填充 |
| `GET /api/projects/{pid}/misstatements/for-letter?year=` | A13 错报摘要 |

### 新建（A16-lite）

| 端点 | 用途 |
|------|------|
| `GET /api/projects/{pid}/a16/recommended-version` | 版本推荐 |

### sign-status scope 扩展（A16-core）

现有端点写 `word_template:{wp_code}`；A16 扩展为 **`word_template:A16:{version}`**，后端 `update_sign_status` 接受 optional `version` query/body。

---

## 占位符与预填

| 来源 | 用途 |
|------|------|
| `docx_placeholder_registry.json` | A16-1/2 已扫描占位符；core task 验证覆盖 |
| `MisstatementSummaryService.get_for_representation_letter` | alert +（可选）docx 写入 |
| 项目信息 | 客户名、期间、合伙人 |

core 可选增强：按 registry URI 写入错报段落（非 lite 阻塞）。

---

## _WP_CODE_OVERRIDE

```python
"A16": "word-template",
# A16-1~7：无 override；虚拟码走路由重定向
```

---

## 审计报告联动（A16-plus）

CW-76：`A16.sign_date → audit_report.representation_letter_date`

```
用户标记 signed
  → 弹窗必填 sign_date（默认 project.audit_report_date 或 audit_period_end）
  → AuditReportService.update(representation_letter_date=sign_date)
```

---

## 程序表：简化 4 步 vs xlsx 7 行

| 层 | 内容 |
|----|------|
| JSON 4 步（lite） | 版本确定 → 编制主声明 → 编制 A16-7 → 获取签署 |
| xlsx 7 行（模板实物） | 草拟/通用/特定/日期/签署人/获取/归档 |
| plus 可选 | 从 xlsx 提取步骤对齐 JSON，不阻塞 lite/core |

---

## 与 A17/A18 差异

| 项 | A16 | A17/A18 |
|----|-----|---------|
| 交付 | OnlyOffice + prefilled-download | 结构化 HTML + Word 导出 |
| PRE-2 | 不依赖 | 依赖 |
| 子码 | 虚拟码 + 7 模板互斥 | 多种 componentType |
| 完成态 | field_overrides sign_status | checklist_responses / 导出 |

---

## 不做

- 结构化 HTML 章节编辑器（不走 A17-1 模式）
- A16-1~6 同时 signed（互斥）
- 非推荐主版本 chip 灰显禁用
- 从 docx 元数据读签署日期
- 伪造 completion / sign_status 标绿
