# Design Document: C2~C15 控制测试弹窗增强

## Overview

为 C2~C15 控制测试底稿的 L1 Dialog 和 Cx-2 偏差评价弹窗增加两项功能：编制提示琥珀块（Guidance JSON → render-config → 前端 `<details>` 渲染）和附件 OCR 上下文选择器（OcrAttachmentPicker.vue 子组件 + useOcrAttachmentCache composable）。

## Architecture

本增强在现有 GtCControlTest.vue / CControlTestSubPage.vue / `_c_control_test.py` 基础上，新增两个功能模块：

1. **编制提示琥珀块**：通过 render-config 机制将 Guidance JSON 下发前端，在 L1 Dialog 和 Cx-2 偏差评价区域顶部以琥珀色 `<details>` 块展示。
2. **附件 OCR 上下文选择器**：独立子组件 `OcrAttachmentPicker.vue`，在 AI 生成前弹出附件选择面板，将选中附件的 OCR 文本作为 AI context 补充。

### 数据流概览

```
┌─────────────────────────────────────────────────────────────────────┐
│  Backend                                                            │
│                                                                     │
│  wp_guidance/C{n}.json ──→ _c_control_test.py render()              │
│                            ↓ html_data.guidance                     │
│                                                                     │
│  /d4/contract-ocr ←── OcrAttachmentPicker (选中附件 file POST)      │
│                            ↓ extracted_fields.full_text             │
│                                                                     │
│  /ai/generate-text ←── context["参考资料（OCR识别）"] = ocrText      │
└─────────────────────────────────────────────────────────────────────┘
         ↑ render-config GET                ↑ POST
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend                                                           │
│                                                                     │
│  GtCControlTest.vue                                                 │
│    ├── L1 Dialog (controlDialogVisible)                             │
│    │     ├── AmberGuidanceBlock (guidance from html_data)           │
│    │     └── CControlTestSubPage.vue                                │
│    │           └── AI Button → OcrAttachmentPicker                  │
│    └── L2 Dialog / Standalone (deviationDialogVisible)              │
│          ├── AmberGuidanceBlock (guidance from C{n}-2.json)         │
│          └── AI Button → OcrAttachmentPicker                        │
│                                                                     │
│  useOcrAttachmentCache (composable)                                 │
│    ├── attachmentListCache (per dialog session)                     │
│    └── ocrResultCache (per attachment_id, component lifecycle)      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. Guidance JSON 文件（静态数据）

**路径**: `backend/data/wp_guidance/C{n}.json` (n=2~15) + `C{n}-2.json` (偏差评价)

**Schema**:
```typescript
interface GuidanceJSON {
  wp_code: string       // "C2" | "C3" | ... | "C15" | "C2-2" | ...
  title: string         // 人类可读标题
  sections: Array<{
    heading: string     // 章节标题（加粗显示）
    content: string     // 章节正文（支持换行符 \n）
  }>
  source: "static_json" // 固定值
}
```

文件命名约定：
- L1 Dialog 用：`C2.json`, `C3.json`, ..., `C15.json`（14 个）
- Cx-2 偏差评价用：`C2-2.json`, `C3-2.json`, ..., `C15-2.json`（14 个）

### 2. 后端 Render 策略增强 (`_c_control_test.py`)

在现有 `render()` 函数中新增 guidance 加载逻辑：

```python
import json
from pathlib import Path

GUIDANCE_DIR = Path(__file__).resolve().parents[3] / "data" / "wp_guidance"

def _load_guidance(wp_code: str) -> dict | None:
    """加载 guidance JSON，缺失或解析失败返回 None。"""
    filename = f"{wp_code}.json"
    filepath = GUIDANCE_DIR / filename
    if not filepath.exists():
        return None
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "sections" in data:
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None

async def render(ctx: RenderContext) -> dict | None:
    # ... 现有逻辑 ...
    
    # 新增：加载 L1 guidance + Cx-2 guidance
    guidance_l1 = _load_guidance(wp_code)           # e.g. C5.json
    guidance_cx2 = _load_guidance(f"{wp_code}-2")   # e.g. C5-2.json
    
    return {
        "component_type": "c-control-test",
        "wp_code": wp_code,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        # 新增字段
        "guidance": guidance_l1,         # L1 Dialog 编制提示
        "guidance_cx2": guidance_cx2,    # Cx-2 偏差评价编制提示
    }
```

### 3. 琥珀块 UI 渲染（内联模板，非独立组件）

复用已有全局 `<details>` + amber 样式模式（项目中多处使用 `cct-compilation-tips` 类似模式），在 GtCControlTest.vue 的 L1 Dialog 和 Cx-2 区域内联渲染：

```vue
<!-- L1 Dialog 内，内容区顶部 -->
<details v-if="guidanceL1?.sections?.length" class="amber-context">
  <summary>编制提示</summary>
  <div class="amber-context__body">
    <div v-for="(sec, i) in guidanceL1.sections" :key="i" class="amber-context__section">
      <strong>{{ sec.heading }}</strong>
      <p style="white-space: pre-wrap;">{{ sec.content }}</p>
    </div>
  </div>
</details>
```

**CSS 规范**（全局或 scoped）:
```css
.amber-context {
  margin-bottom: 12px;
  border-left: 4px solid #d97706;   /* amber-600 */
  background: #fffbeb;              /* amber-50 */
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
}
.amber-context > summary {
  padding: 8px 12px;
  font-weight: 600;
  cursor: pointer;
  color: #92400e;                   /* amber-800 */
}
.amber-context__body {
  padding: 0 12px 10px;
}
.amber-context__section {
  margin-bottom: 8px;
}
.amber-context__section strong {
  display: block;
  margin-bottom: 2px;
  color: #78350f;                   /* amber-900 */
}
.amber-context__section p {
  margin: 0;
  color: #451a03;                   /* amber-950 */
}
```

### 4. OcrAttachmentPicker.vue（独立子组件）

**路径**: `audit-platform/frontend/src/components/workpaper/cControlTest/OcrAttachmentPicker.vue`

**Props**:
```typescript
interface OcrAttachmentPickerProps {
  wpId: string
  projectId: string
  visible: boolean        // v-model 控制显隐
  /** 已缓存的 OCR 结果（attachment_id → text），由父组件通过 composable 维护 */
  ocrCache: Map<string, string>
}
```

**Emits**:
```typescript
interface OcrAttachmentPickerEmits {
  (e: 'update:visible', val: boolean): void
  (e: 'confirm', payload: { ocrText: string; failedIds: string[] }): void
  (e: 'cancel'): void
}
```

**行为**:
1. `visible=true` 时，调用 `GET /api/attachments?wp_id={wpId}` 获取附件列表（session cache）
2. 渲染 checkbox 列表：文件名 + OCR 可识别标记（`.pdf/.png/.jpg/.jpeg/.tiff/.bmp`）
3. 用户勾选 → 确认 → 对未缓存的附件逐个调用 `POST /api/workpapers/{wpId}/d4/contract-ocr`
4. 拼接所有成功 OCR 文本，截断到 3000 字符，emit `confirm`
5. 失败的附件收集 ID 一并返回，供父组件 toast 警告

### 5. useOcrAttachmentCache Composable

**路径**: `audit-platform/frontend/src/composables/useOcrAttachmentCache.ts`

```typescript
interface UseOcrAttachmentCacheReturn {
  /** OCR 结果缓存 (attachment_id → extracted full_text) */
  ocrCache: Ref<Map<string, string>>
  /** 附件列表缓存（dialog session 内有效） */
  attachmentList: Ref<AttachmentItem[]>
  attachmentListLoaded: Ref<boolean>
  /** 加载附件列表（已加载则跳过） */
  loadAttachments: (wpId: string) => Promise<void>
  /** 执行 OCR 并缓存（已缓存则跳过） */
  runOcr: (wpId: string, attachmentId: string, file: File | Blob) => Promise<string>
  /** 清除缓存（dialog 关闭时调用） */
  resetListCache: () => void
}
```

**缓存策略**:
- `ocrCache`：组件生命周期内持久，key = attachment_id，value = full_text 字符串
- `attachmentList`：dialog session 内缓存，关闭 dialog 时 resetListCache()
- 新附件上传事件（EventBus `attachment:uploaded`）触发 `attachmentListLoaded = false` 强制下次刷新

### 6. AI 生成集成修改

在 CControlTestSubPage.vue 和偏差评价区域的 AI 按钮点击处理中：

```typescript
async function handleAiGenerate(section: string, existingContent: string) {
  // 1. 弹出 OcrAttachmentPicker
  ocrPickerVisible.value = true
  
  // 2. 等待用户确认（通过 emit callback 或 Promise 模式）
  // ...

  // 3. 构建 context
  const context: Record<string, string> = {
    '控制点名称': page.controlName,
    '控制描述': page.description,
    '相关认定': page.assertion?.join('、') || '',
    // ... 其他表单字段
  }
  
  // 4. 如有 OCR 文本，追加到 context
  if (ocrText) {
    context['参考资料（OCR识别）'] = ocrText
  }
  
  // 5. 调用通用端点
  const res = await api.post(`/api/workpapers/${wpId}/ai/generate-text`, {
    prompt: `请为"${section}"生成内容`,
    context,
    existingContent,
    section,
  })
}
```

### 7. OCR 文本截断规则

```typescript
const MAX_OCR_CONTEXT_LENGTH = 3000

function truncateOcrText(texts: string[]): string {
  const joined = texts.join('\n---\n')
  if (joined.length <= MAX_OCR_CONTEXT_LENGTH) return joined
  return joined.slice(0, MAX_OCR_CONTEXT_LENGTH) + '…（已截断）'
}
```

---

## Data Models

### Guidance JSON Schema (TypeScript)

```typescript
interface GuidanceSection {
  heading: string
  content: string
}

interface GuidanceData {
  wp_code: string
  title: string
  sections: GuidanceSection[]
  source: 'static_json'
}
```

### Attachment Item (前端)

```typescript
interface AttachmentItem {
  id: string               // attachment_id
  file_name: string
  file_type: string        // MIME type
  file_size: number
  created_at: string
  ocrEligible: boolean     // 前端根据 file_name 后缀计算
}
```

### OCR Response (from `/d4/contract-ocr`)

```typescript
interface OcrResponse {
  extracted_fields: {
    full_text?: string
    [key: string]: any
  }
}
```

---

## Error Handling

| 场景 | 处理方式 |
|------|----------|
| Guidance JSON 文件不存在 | render 策略返回 `guidance: null`，前端 `v-if` 隐藏琥珀块 |
| Guidance JSON 格式错误 | render 策略 catch 解析异常，返回 `null`，logger.warning |
| 附件列表获取失败 | OcrAttachmentPicker 显示"暂无附件"空状态，不阻塞 AI 生成 |
| 单个附件 OCR 失败 | 跳过该附件，收集失败 ID，emit 后由父组件 ElMessage.warning |
| 全部 OCR 失败 | ocrText 为空，等同"未选择附件"，继续 AI 生成（仅表单 context） |
| OCR 文本超长 | 截断到 3000 字符 + 尾部"…（已截断）"标记 |
| 附件无 OCR 可识别格式 | 在列表中禁用 checkbox，tooltip 提示"仅支持 PDF/图片" |

---

## Interfaces

### 后端新增返回字段（render-config）

`GET /api/workpapers/{wp_id}/render-config` 响应中 `sheets[].html_data` 新增：

```json
{
  "component_type": "c-control-test",
  "wp_code": "C5",
  "guidance": {
    "wp_code": "C5",
    "title": "C5 采购与付款循环控制测试 — 编制提示",
    "sections": [{"heading": "...", "content": "..."}],
    "source": "static_json"
  },
  "guidance_cx2": {
    "wp_code": "C5-2",
    "title": "C5-2 偏差评价 — 编制提示",
    "sections": [...],
    "source": "static_json"
  },
  "project_context": {...},
  "responses_snapshot": {...}
}
```

### AI Generate Text 端点（无结构变更，仅 context 新增 key）

`POST /api/workpapers/{wp_id}/ai/generate-text`

Request body 中 `context` dict 可包含新 key：
```json
{
  "prompt": "...",
  "context": {
    "控制点名称": "...",
    "参考资料（OCR识别）": "OCR识别文本内容（最大3000字符）"
  },
  "existingContent": "...",
  "section": "testProcedure"
}
```

---

## OCR Eligibility Detection

```typescript
const OCR_EXTENSIONS = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'])

function isOcrEligible(fileName: string): boolean {
  const ext = '.' + fileName.split('.').pop()?.toLowerCase()
  return OCR_EXTENSIONS.has(ext)
}
```

---

## Testing Strategy

- **单元测试**：`_load_guidance()` 纯函数（文件存在/缺失/格式错误）、`isOcrEligible()` 分类、`truncateOcrText()` 截断逻辑
- **Property 测试**：OCR 缓存行为、OCR 文本截断一致性、Guidance 加载全覆盖 [2,15]
- **集成测试**：render-config 端点返回 guidance 字段、AI generate-text 端点接收 OCR context
- **Playwright E2E**：L1 Dialog 打开显示琥珀块、AI 按钮弹出附件选择器

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Guidance 加载 — 有效循环编号返回正确 guidance

*For any* cycle number `n` in the range [2, 15], the render strategy SHALL return a non-null `guidance` field containing a valid GuidanceData object with `wp_code` matching `C{n}` and a non-empty `sections` array; similarly `guidance_cx2` SHALL contain `wp_code` matching `C{n}-2`.

**Validates: Requirements 2.1, 3.1, 7.1, 7.2**

### Property 2: Guidance section 完整渲染

*For any* GuidanceData object with N sections (N ≥ 1), the rendered amber block SHALL contain exactly N heading-content pairs, where each heading text matches the corresponding section's `heading` field and each content text matches the section's `content` field.

**Validates: Requirements 2.3**

### Property 3: OCR 可识别性分类

*For any* file name string, `isOcrEligible` SHALL return `true` if and only if the file extension (case-insensitive) is one of `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, or `.gif`.

**Validates: Requirements 4.2**

### Property 4: OCR 缓存避免重复调用

*For any* attachment ID that has been previously OCR-processed and cached, subsequent OCR requests for the same attachment ID SHALL return the cached text without making an additional HTTP call to the OCR endpoint.

**Validates: Requirements 4.3, 6.3**

### Property 5: OCR 文本拼接与截断

*For any* collection of OCR text strings with total concatenated length L:
- If L ≤ 3000: the result SHALL be the full concatenation joined by `\n---\n`
- If L > 3000: the result SHALL be the first 3000 characters of the concatenation followed by `…（已截断）`

Additionally, the resulting text SHALL be placed in the AI context under key `"参考资料（OCR识别）"`.

**Validates: Requirements 4.4, 5.3**

### Property 6: OCR 部分失败容错

*For any* set of N selected attachments where K attachments fail OCR (0 ≤ K < N), the system SHALL:
1. Include OCR text from all (N - K) successful attachments in the AI context
2. Return the K failed attachment IDs for warning display
3. NOT block AI generation due to partial OCR failures

**Validates: Requirements 4.6**

### Property 7: Guidance 缺失 — 安全降级

*For any* wp_code where the corresponding Guidance JSON file does not exist or is malformed, the render strategy SHALL return `null` for the guidance field, and the frontend SHALL hide the amber block without displaying any error message to the user.

**Validates: Requirements 2.6, 3.4, 7.3**
