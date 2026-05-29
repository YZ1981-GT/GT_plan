# 底稿编辑器瘦身与跨模块联动 — 设计文档

> 起草日期：2026-05-28 | 修订：2026-05-29（基于 2602 sheet 完整分析数据）
> 对应需求：requirements.md（7 个 US + 5 个 PBT 属性）
> 数据源：workpaper_template_analysis.md（4817 行逐 sheet 分析）+ workpaper_template_analysis.json（机器读）
> 状态：📐 design 阶段

---

## 一、整体架构变更

### 1.1 WorkpaperEditor 瘦身后结构

```
WorkpaperEditor.vue (≤1200 行)
├── [顶层路由] v-if="useHtmlRenderer" → GtWpRenderer
├── [顶层路由] v-else-if="componentType !== 'univer'" → 子编辑器
├── [默认] Univer 编辑器
│   ├── 工具栏（保留）
│   ├── SheetNav（保留）
│   ├── UniverContainer（保留）
│   └── <CycleDialogSlot />  ← 新：配置驱动，替代 12 trigger + 15 dialog
└── 侧面板（保留）
```

### 1.2 跨模块联动数据流

```
底稿保存 (HTML/Univer)
  │
  ├─→ [1] POST /api/workpapers/{id}/save
  │       └─→ 后端 service:
  │            ├─ 写 parsed_data
  │            ├─ cross_ref_service.detect_changes → SSE cross_ref.updated
  │            ├─ report_stale_service.mark_if_mapped(wp_code) → SSE report.stale  [US-2]
  │            └─ if C类: disclosure_sync_service.sync(wp_id) → SSE note.synced    [US-3]
  │
  ├─→ [2] 前端 eventBus
  │       ├─ ReportView 订阅 report.stale → 黄色横幅
  │       ├─ DisclosureEditor 订阅 note.synced → 刷新树
  │       └─ useStaleImpact 订阅 cross_ref.updated → 影响范围
  │
  └─→ [3] 附件/LLM（用户主动触发）
          ├─ 📎 按钮 → AttachmentDropZone → POST /api/wp-storage/upload
          └─ 🤖 按钮 → POST /api/wp-ai/{id}/suggest → 建议文本
```

---

## 二、US-1 详细设计：CycleDialogSlot 配置驱动

### 2.1 配置文件结构

```typescript
// audit-platform/frontend/src/config/cycleDialogRegistry.ts
import type { Component } from 'vue'

export interface CycleDialogConfig {
  id: string                    // 唯一标识
  cycle: string                 // 循环代号 F/G/H/I/K/L/M/N
  wpCodePattern: RegExp         // wp_code 匹配正则
  component: () => Promise<Component>  // 异步加载 dialog 组件
  triggerLabel: string          // 按钮文字
  triggerIcon: string           // emoji/icon
  triggerType: 'primary' | 'warning'   // el-button type
  requiresSheet?: boolean       // 是否需要 activeSheetId
}

export const cycleDialogRegistry: CycleDialogConfig[] = [
  {
    id: 'f-stocktake',
    cycle: 'F',
    wpCodePattern: /^F2-(2[1-6])/i,
    component: () => import('@/components/workpaper/InventoryStocktakeDialog.vue'),
    triggerLabel: '开始监盘',
    triggerIcon: '📦',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'f-impairment',
    cycle: 'F',
    wpCodePattern: /^F2-(4[7-9]|5[0-2])/i,
    component: () => import('@/components/workpaper/InventoryImpairmentDialog.vue'),
    triggerLabel: 'AI 分析跌价',
    triggerIcon: '🤖',
    triggerType: 'warning',
  },
  // ... 其余 13 个 dialog 配置
]
```

### 2.2 CycleDialogSlot 组件

```typescript
// <CycleDialogSlot> props
interface Props {
  wpDetail: WorkpaperDetail
  projectId: string
  wpId: string
  activeSheetId: string
  cycleType: ReturnType<typeof useCycleType>
}

// 内部逻辑：
// 1. computed matchedConfigs = registry.filter(c => c.wpCodePattern.test(wpDetail.wp_code))
// 2. 对每个 matched config 渲染 trigger 按钮
// 3. 点击后 defineAsyncComponent 加载 dialog + 传入标准 props
// 4. dialog emit saved/applied → 向上 emit onChildSaved
```

### 2.3 从 WorkpaperEditor 移除的代码

| 移除项 | 行数估算 |
|--------|---------|
| 12 个 trigger div（含 v-if 正则） | ~180 行 |
| 15 个 dialog 组件实例 | ~240 行 |
| 15 个 dialog import | ~30 行 |
| 15 个 visible ref + applied handler | ~90 行 |
| 循环特定 computed（showXTrigger 等） | ~60 行 |
| **合计** | **~600 行** |

---

## 三、US-2 详细设计：报表 stale 联动

### 3.1 后端

```python
# backend/app/services/report_stale_service.py (新建)
class ReportStaleService:
    async def mark_if_mapped(self, wp_code: str, project_id: UUID) -> list[str]:
        """检查 wp_code 是否在 report_line_mapping 中有映射，有则标记 stale"""
        rows = await self.db.execute(
            select(ReportLineMapping.row_code)
            .where(ReportLineMapping.source_wp_code == wp_code,
                   ReportLineMapping.project_id == project_id)
        )
        affected = [r.row_code for r in rows.scalars()]
        if affected:
            await self.db.execute(
                update(ReportSnapshot)
                .where(ReportSnapshot.row_code.in_(affected))
                .values(is_stale=True)
            )
            # 发 SSE
            await sse_manager.broadcast(project_id, 'report.stale', {'rows': affected})
        return affected
```

### 3.2 前端

```typescript
// ReportView.vue 新增订阅
eventBus.on('sse:sync-event', (evt) => {
  if (evt.event_type === 'report.stale') {
    staleRows.value = evt.data.rows
    showStaleBanner.value = true
  }
})
```

---

## 四、US-3 详细设计：C 类底稿 → 附注同步

### 4.1 触发时机

GtCNoteTable emit `save` → GtWpRenderer emit `save-success` → WorkpaperEditor 检测 componentType 为 `c-note-table` → 调用 disclosure_sync。

### 4.2 后端 service 扩展

```python
# backend/app/services/wp_disclosure_sync_service.py (已有，扩展)
class WpDisclosureSyncService:
    async def sync_from_html(self, wp_id: UUID, sheet_name: str, sub_table_data: dict):
        """从 HTML 渲染器的 C 类底稿同步到 disclosure_notes"""
        # 1. 查 wp_code → 映射到 disclosure_notes.section_id
        mapping = await self._get_section_mapping(wp_id, sheet_name)
        if not mapping:
            return  # 无映射则跳过

        # 2. 读 disclosure_notes 当前值
        note = await self._get_note(mapping.section_id)

        # 3. 冲突检测
        if note.updated_at > mapping.last_sync_at:
            raise ConflictError(note_id=note.id, note_updated=note.updated_at)

        # 4. 写入
        note.table_data = sub_table_data
        note.is_stale = False
        note.last_sync_at = func.now()

        # 5. 审计日志
        await audit_trail.log('disclosure_sync', wp_id=wp_id, section_id=mapping.section_id)

        # 6. SSE 通知
        await sse_manager.broadcast(note.project_id, 'note.synced', {
            'section_id': mapping.section_id
        })
```

### 4.3 前端冲突处理

```typescript
// WorkpaperEditor.vue onSaveSuccess handler
if (componentType === 'c-note-table') {
  try {
    await api.post(`/api/wp-disclosure-sync/${wpId}/sync-html`, payload)
  } catch (e) {
    if (e.status === 409) {
      // 冲突弹窗
      const choice = await ElMessageBox.confirm(
        '附注模块有更新的手动编辑，如何处理？',
        { distinguishCancelAndClose: true, confirmButtonText: '覆盖', cancelButtonText: '保留附注版本' }
      )
      if (choice === 'confirm') {
        await api.post(`/api/wp-disclosure-sync/${wpId}/sync-html?force=true`, payload)
      }
    }
  }
}
```

---

## 五、US-4 详细设计：附件联动

### 5.1 组件集成

在 GtAProgramConsole 的每行操作列增加附件按钮：

```vue
<el-table-column label="证据" width="70" align="center">
  <template #default="{ row }">
    <el-badge :value="row.attachment_count" :hidden="!row.attachment_count" :max="9">
      <el-button text size="small" @click="openAttachment(row)">📎</el-button>
    </el-badge>
  </template>
</el-table-column>
```

点击后弹出已有 `AttachmentDropZone` 组件，绑定参数：
- `resource_type = 'workpaper_row'`
- `resource_id = ${wp_id}:${sheet_name}:${row.program_no}`

### 5.2 后端存储

复用已有 `workpaper_attachment` 表 + `wp_storage` router，新增 `row_ref` 字段：

```sql
ALTER TABLE workpaper_attachment ADD COLUMN IF NOT EXISTS row_ref VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_wpa_row_ref ON workpaper_attachment(working_paper_id, row_ref);
```

---

## 六、US-5 详细设计：LLM 辅助填写

### 6.1 前端入口

GtDFormParagraph 的 textarea 右上角增加浮动按钮：

```vue
<div class="gt-ai-suggest-trigger" v-if="aiEnabled">
  <el-button text size="small" :loading="aiLoading" @click="onAiSuggest">🤖 AI 建议</el-button>
</div>
```

### 6.2 后端端点扩展

```python
# backend/app/routers/wp_ai.py 已有，新增 suggest 端点
@router.post("/{wp_id}/suggest")
async def suggest_fill(wp_id: UUID, body: SuggestRequest, db=Depends(get_db)):
    if not settings.WP_AI_SERVICE_ENABLED:
        raise HTTPException(403, "AI service disabled")
    result = await wp_ai_service.suggest(
        wp_id=wp_id,
        sheet_name=body.sheet_name,
        field_name=body.field_name,
        context=body.existing_content,
    )
    return {"suggestion": result.text[:2000], "confidence": result.confidence}
```

### 6.3 审计轨迹

采纳建议后前端在保存 payload 中标记：

```json
{
  "html_data": { ... },
  "ai_assisted_fields": ["field_name_1", "field_name_2"]
}
```

后端保存时写入 `wp_audit_trail`：`action='ai_suggest_adopted'`。

---

## 七、US-6 详细设计：router_registry 聚合

### 7.1 分组方案

| 聚合组 | 包含的现有 router | prefix |
|--------|------------------|--------|
| wp_template | wp_template / wp_template_metadata / wp_template_files / wp_template_download / wp_template_version | /api/wp-templates |
| wp_lifecycle | working_paper / workpaper_batch_status / wp_batch_ops / wp_progress / wp_prerequisite_status / wp_procedure_status | /api/workpapers |
| wp_review | wp_review / wp_review_status / wp_cell_annotations / review_records_global / wp_eqcr_evaluation | /api/wp-review |
| wp_render | wp_render_config / wp_classification / wp_html_save / wp_xlsx_export / wp_index_resolve / wp_trace | /api/wp-render |
| wp_data | formula / wp_mapping / wp_data_rules / wp_prefill_context / wp_prefill_preview / wp_user_formulas / wp_cross_check / wp_dependencies / sampling / sampling_enhanced / aging_analysis / data_fetch_custom | /api/wp-data |
| wp_search | wp_search / wp_version_search / global_search / wp_health_dashboard | /api/wp-search |

### 7.2 实施方式

不改各 router 文件内部的 `prefix`，仅在 registry 层用注释分组 + 循环注册：

```python
def register_workpaper_routers(app: FastAPI) -> None:
    groups = {
        "模板管理": [wp_template, wp_template_metadata, ...],
        "生命周期": [working_paper, workpaper_batch_status, ...],
        ...
    }
    for tag, routers in groups.items():
        for r in routers:
            app.include_router(r, tags=[tag])
```

---

## 八、US-7 详细设计：render_schema 全覆盖

### 8.1 根因修复

`generate_wp_render_schema.py` 的 `extract_wp_code_from_filename` 函数中 `.split("-")[0]` 将子序号截断（如 `D2-1至D2-4` → `D2`），导致同一主 wp_code 下多个子模板只生成 1 个 yaml。

修复方案：
```python
# 修复前（错误）
def extract_wp_code_from_filename(filename: str) -> str | None:
    m = _WP_CODE_PATTERN.match(filename)
    if m:
        return m.group(1).split("-")[0]  # ← BUG: 截断子序号
    return None

# 修复后（正确）
def extract_wp_code_from_filename(filename: str) -> str | None:
    """从模板文件名提取完整 wp_code（保留子序号）"""
    m = _WP_CODE_PATTERN.match(filename)
    if m:
        return m.group(1)  # 保留完整 wp_code 如 A1-11, D2-1
    return None
```

同时修复 `iter_template_files` 的去重逻辑：
```python
def iter_template_files(template_dir: Path, wp_code_filter: str | None) -> list[tuple[str, Path]]:
    """枚举 (wp_code, xlsx_path) 列表 — 不再去重，每个 xlsx 独立生成 yaml"""
    results = []
    for xlsx_path in sorted(template_dir.rglob("*.xlsx")):
        if xlsx_path.name.startswith("~$") or xlsx_path.name.startswith("."):
            continue
        wp_code = extract_wp_code_from_filename(xlsx_path.name)
        if not wp_code:
            continue
        if wp_code_filter and not wp_code.startswith(wp_code_filter):
            continue
        results.append((wp_code, xlsx_path))
    return results
```

### 8.2 生成策略（基于 2602 sheet 分析数据）

利用 `workpaper_template_analysis.json` 作为权威数据源，生成时交叉验证：

```python
# 新增：从 JSON 分析数据加载预期 componentType
def load_analysis_data(json_path: Path) -> dict[str, dict]:
    """加载 workpaper_template_analysis.json 作为 ground truth"""
    data = json.loads(json_path.read_text(encoding='utf-8'))
    result = {}
    for cycle_data in data['cycles'].values():
        for template in cycle_data['templates']:
            filename = template['filename']
            wp_code = extract_wp_code_from_filename(filename)
            if wp_code:
                result[wp_code] = {
                    'sheets': {s['name']: s for s in template['sheets']},
                    'filename': filename,
                }
    return result
```

### 8.3 组件映射规则（完整 15 类 → 9 组件）

基于 2602 sheet 分析确认的映射关系：

| 渲染策略 | componentType | Vue 组件 | sheet 数 |
|---------|--------------|----------|---------|
| HTML 中控台 | a-program-console | GtAProgramConsole | 278 |
| HTML 表单（编制信息+索引导航） | b-index | GtBIndex | 149 |
| HTML 嵌套表（多级子表） | c-note-table | GtCNoteTable | 166 |
| HTML 表单（表格型检查） | d-form-table | GtDForm | 305 |
| HTML 表单（专属子组件） | d-form-confirmation | GtDForm | 109 |
| HTML 表单（电子签） | d-form-review | GtDForm | 27 |
| HTML 段落型 | d-form-paragraph | GtDForm | 19 |
| HTML 是否问答型 | d-form-qa | GtDForm | 9 |
| HTML 表单 | e-control-test | GtEControlTest | 292 |
| HTML stepper | e-control-test | GtEControlTest | 29 |
| 静态展示 | h-static-doc | GtHStaticDoc | 104 |
| 保留 Univer | univer | UniverContainer | 706 |
| 保留 Univer（测算） | univer | UniverContainer | 158 |
| 跳过渲染 | skip | (不渲染) | 244 |
| PENDING-待人工归类 | pending | (人工决策) | 7 |

### 8.4 CI 断言

```python
# backend/tests/test_render_schema_coverage.py
def test_all_templates_have_schema():
    """断言每个模板 xlsx 都有对应的 render_schema yaml"""
    templates = list(Path("backend/wp_templates").rglob("*.xlsx"))
    templates = [t for t in templates if not t.name.startswith("~$")]
    schema_dir = Path("backend/data/wp_render_schema")
    schema_codes = set()
    for yaml_path in schema_dir.rglob("*.yaml"):
        schema_codes.add(yaml_path.stem)

    missing = []
    for t in templates:
        wp_code = extract_wp_code(t.name)
        if wp_code and wp_code not in schema_codes:
            missing.append(wp_code)

    assert not missing, f"Missing schemas for {len(missing)} templates: {missing[:10]}"


def test_schema_sheets_match_xlsx():
    """断言 yaml 中的 sheets 与 xlsx 实际 sheet 名一致"""
    # 抽样验证 20 个 yaml
    ...


def test_component_type_matches_analysis():
    """断言 yaml 中的 componentType 与 JSON 分析数据一致"""
    analysis = json.loads(Path("workpaper_template_analysis.json").read_text())
    ...
```

### 8.5 执行命令

```bash
# 修复后重跑全量生成
python backend/scripts/generate_wp_render_schema.py --overwrite

# 验证覆盖率
python -m pytest backend/tests/test_render_schema_coverage.py -v
```

---

## 九、风险与缓解

| 风险 | 缓解 |
|------|------|
| CycleDialogSlot 异步加载闪烁 | defineAsyncComponent + Suspense fallback |
| 报表 stale 高频触发 | debounce 2s + 批量合并 affected rows |
| 附注同步冲突频繁 | 默认"底稿优先" + 仅 C 类触发 |
| LLM 响应慢 | stub 模式 + 超时 5s 自动取消 |
| router 合并后 OpenAPI tag 变化 | 保持 URL 不变，仅 tag 重组 |
| render_schema 生成后 componentType 不匹配 | 以 JSON 分析数据为 ground truth 交叉验证 |

---

## 十、数据引用

本 spec 依赖以下分析数据文件（同目录）：

| 文件 | 用途 | 行数/大小 |
|------|------|----------|
| `workpaper_template_analysis.md` | 人读：逐 sheet 分析表（含类别/行列/合并/公式/推荐渲染） | 4817 行 |
| `workpaper_template_analysis.json` | 机读：完整结构化数据（implementation 阶段消费） | 349 模板 / 2602 sheet |

### 10.1 关键统计摘要

- **总模板**：349 个 xlsx（15 循环 A~N + S + _reference）
- **总 sheet**：2602 个
- **HTML 渲染**：1487 sheet（57.1%）→ 需要 render_schema yaml 正确路由
- **保留 Univer**：864 sheet（33.2%）→ F/G 类不动
- **跳过渲染**：244 sheet（9.4%）→ I 类占位 / GT_Custom
- **PENDING**：7 sheet（0.3%）→ 需人工归类
- **自动归类健康度**：99.7%（2595/2602）

### 10.2 per-cycle 分布

| 循环 | 模板数 | sheet 数 | HTML | Univer | Skip |
|------|--------|---------|------|--------|------|
| A | 65 | 607 | 233 | 324 | 46 |
| B | 49 | 262 | 227 | 11 | 21 |
| C | 36 | 164 | 125 | 8 | 31 |
| D | 17 | 155 | 92 | 56 | 7 |
| E | 5 | 56 | 39 | 17 | 0 |
| F | 15 | 151 | 74 | 62 | 15 |
| G | 15 | 197 | 113 | 84 | 0 |
| H | 11 | 187 | 111 | 74 | 2 |
| I | 6 | 86 | 41 | 39 | 6 |
| J | 3 | 38 | 23 | 9 | 6 |
| K | 14 | 152 | 90 | 54 | 8 |
| L | 9 | 100 | 62 | 34 | 4 |
| M | 10 | 102 | 54 | 37 | 11 |
| N | 5 | 59 | 29 | 25 | 5 |
| S | 86 | 267 | 167 | 18 | 82 |



---

## 十一、用户体验增强设计（P2 迭代）

> 以下设计在 Sprint 1~3 核心功能完成后实施，按成本/收益排序。

### 11.1 US-8：底稿填写完成度可视化

```typescript
// composable: useWpCompletionRate(schema, htmlData)
interface CompletionRate {
  filled: number       // 已填必填字段数
  total: number        // 总必填字段数
  percentage: number   // 0~100
  category: 'empty' | 'partial' | 'complete'
}

// 计算逻辑按组件类型分化：
// A 类：已决策程序数 / 总程序数（status !== 'pending'）
// D 类：已回答问题数 / 总问题数（value !== null && value !== ''）
// E 类：已完成步骤 / 总步骤（step.completed === true）
// B 类：已填编制信息字段 / 总必填字段
// C 类：已填子表行数 / schema 定义最小行数
```

前端展示：
- 底稿编辑器顶部：`<el-progress type="circle" :percentage="rate.percentage" :width="36" />`
- 底稿列表页每行：`<el-progress type="circle" :percentage="rate.percentage" :width="24" />`

### 11.2 US-9：底稿间导航增强

```typescript
// composable: useWpNavigationHistory()
const MAX_HISTORY = 5

interface NavHistoryItem {
  wpId: string
  wpCode: string
  sheetName: string
  rowRef?: string      // 如 "第 3 行"
  timestamp: number
}

// sessionStorage key: 'gt_wp_nav_history'
// 跳转时 push → 目标底稿顶部显示面包屑
// Backspace 键 → pop 返回上一个
```

面包屑组件：
```vue
<div v-if="navHistory.length > 0" class="gt-wp-breadcrumb-return">
  <el-button text size="small" @click="goBack">
    ← 返回 {{ lastItem.wpCode }} {{ lastItem.rowRef }}
  </el-button>
</div>
```

### 11.3 US-10：schema 缺失智能提示

在 `useWpRenderer.ts` 中增加 fallback 检测：

```typescript
const schemaFallbackBanner = computed(() => {
  if (!renderConfig.value) return null
  // 如果 classification 表中 class_code 是 A/B/C/D/E 类
  // 但 componentType 返回 'univer'（因 schema 缺失 fallback）
  // → 显示 info banner
  const cls = renderConfig.value.classification?.class_code
  if (cls && /^[A-E]-/.test(cls) && componentType.value === 'univer') {
    return '此底稿推荐使用 HTML 渲染器，当前因配置未就绪暂用表格模式'
  }
  return null
})
```

### 11.4 US-11：渲染模式手动切换

```typescript
// WorkpaperEditor 工具栏
<el-button
  v-if="canSwitchRenderer"
  size="small"
  @click="toggleRendererMode"
>
  {{ useHtmlRenderer ? '切换为表格模式' : '切换为 HTML 模式' }}
</el-button>

// 切换后写入 project_workpaper_sheet_override
async function toggleRendererMode() {
  const newMode = useHtmlRenderer.value ? 'univer' : htmlComponentType.value
  await api.post(`/api/wp-classifications/override`, {
    project_id: projectId,
    wp_code: wpDetail.wp_code,
    renderer_override: newMode,
  })
  reload()
}
```

### 11.5 US-12：离线暂存

```typescript
// composable: useWpOfflineCache(wpId, sheetName)
const STORAGE_KEY_PREFIX = 'gt_wp_offline_'
const MAX_OFFLINE_SIZE = 50 * 1024 * 1024  // 50MB

function saveToOffline(data: Record<string, any>) {
  const key = `${STORAGE_KEY_PREFIX}${wpId}_${sheetName}`
  try {
    localStorage.setItem(key, JSON.stringify({ data, timestamp: Date.now() }))
  } catch (e) {
    // QuotaExceededError → 提示用户手动导出
    ElMessage.warning('本地存储已满，请手动导出底稿数据')
  }
}

function loadFromOffline(): { data: any; timestamp: number } | null {
  const key = `${STORAGE_KEY_PREFIX}${wpId}_${sheetName}`
  const raw = localStorage.getItem(key)
  return raw ? JSON.parse(raw) : null
}

// auto-save 失败时自动调用 saveToOffline
// 恢复网络后 → 检测 offline cache → 冲突比对 → 用户选择
```

### 11.6 US-13：首次使用引导

使用 el-tour 组件（Element Plus 内置）：

```vue
<el-tour v-model="showGuide" :steps="guideSteps" />

const guideSteps = [
  { target: '.gt-a-program-console__progress', title: '程序表中控台', description: '这里显示整体完成进度' },
  { target: '.gt-a-program-console__table .el-table__expand-icon', title: '展开查看详情', description: '点击展开查看完整程序描述和历史决策' },
  { target: '.gt-a-program-console__actions', title: '批量裁剪', description: '选中多条程序后可一次性裁剪并填写理由' },
]

// localStorage 记录
const GUIDE_KEY = 'gt_wp_guide_shown'
const showGuide = ref(!localStorage.getItem(GUIDE_KEY))
watch(showGuide, (v) => { if (!v) localStorage.setItem(GUIDE_KEY, '1') })
```


### 11.7 US-14：底稿模板导出 → 线下填写 → 导入

> 复用附注模块 D15 离线分发的架构模式（`note_offline_export_service.py` / `note_offline_import_service.py`），适配底稿场景。

#### 11.7.1 导出 xlsx 结构

```
导出文件: {wp_code}_{project_name}_{date}_填写模板.xlsx
├── [Sheet 1] 注意事项
│   ├── 一、填写说明（本底稿用途 + 填写范围）
│   ├── 二、字段颜色语义（黄=可填 / 灰=公式锁定 / 红=禁改 / 绿=必填）
│   ├── 三、填写注意事项（不要删行/不要改列顺序/不要修改隐藏 sheet）
│   ├── 四、截止日期（请于 YYYY-MM-DD 前返回）
│   ├── 五、联系人（项目经理 + 电话 + 邮箱）
│   ├── 六、版本信息（导出时间 + schema_version + 系统版本）
│   └── 七、数据安全提示（如加密则说明解密方式）
├── [Sheet 2~N] 底稿内容（按原模板结构）
│   ├── 可填 cell: 黄色底色 + 无保护
│   ├── 公式 cell: 灰色底色 + sheet 保护锁定
│   ├── 必填 cell: 绿色边框 + DataValidation 提示
│   └── 禁改 cell: 红色底色 + sheet 保护锁定
└── [Hidden] _meta_
    └── A1: base64(gzip(JSON))
        {
          "wp_id": "uuid",
          "wp_code": "D2A",
          "project_id": "uuid",
          "schema_version": "v2025-R5",
          "exported_at": "ISO8601",
          "exported_by": "user_id",
          "sheet_bindings": {
            "应收账款实质性程序表D2A": {
              "fields": { "B7": "program_desc", "D7": "assertion.existence", ... },
              "row_range": [7, 26],
              "dynamic_rows": true
            }
          },
          "checksum": "sha256_of_bindings"
        }
```

#### 11.7.2 后端 service

```python
# backend/app/services/wp_offline_export_service.py (新建)
class WpOfflineExportService:
    async def export_template(
        self,
        wp_id: UUID,
        project_id: UUID,
        sheet_names: list[str] | None = None,  # None = 全部
        encrypt_password: str | None = None,
    ) -> BytesIO:
        """导出底稿填写模板 xlsx"""
        # 1. 加载 render_schema + 致同模板 xlsx
        # 2. 复制模板到 BytesIO
        # 3. 插入"注意事项" sheet（第 1 位）
        # 4. 按 schema 标记 cell 颜色（黄/灰/红/绿）+ sheet 保护
        # 5. 生成 _meta_ sheet（hidden + base64+gzip）
        # 6. 可选 AES 加密（Fernet）
        # 7. 归档到 storage/projects/{pid}/workpapers/offline_exports/
        ...

# backend/app/services/wp_offline_import_service.py (新建)
class WpOfflineImportService:
    async def validate_and_diff(
        self,
        wp_id: UUID,
        uploaded_file: BytesIO,
        decrypt_password: str | None = None,
    ) -> ImportDiffResult:
        """验证导入文件 + 生成 diff"""
        # 1. 解密（如需要）
        # 2. 解析 _meta_ sheet → 校验 wp_id / schema_version / checksum
        # 3. 逐 sheet 逐 cell 对比：导入值 vs 系统当前值
        # 4. 分类：value_changed / row_added / row_deleted / unchanged
        # 5. 返回 diff 结果（不写入 DB）
        ...

    async def apply_import(
        self,
        wp_id: UUID,
        diff: ImportDiffResult,
        conflict_resolution: str,  # 'overwrite' | 'keep_system' | 'merge'
        selected_fields: list[str] | None = None,  # merge 模式下用户选择的字段
    ) -> None:
        """应用导入（写入 parsed_data + 审计日志）"""
        # 1. 按 conflict_resolution 策略合并
        # 2. 写入 working_paper.parsed_data['html_data']
        # 3. 触发 cross_ref_service.detect_changes
        # 4. 写入 wp_audit_trail: action='offline_import'
        ...
```

#### 11.7.3 后端端点

```python
# backend/app/routers/wp_offline.py (新建)
@router.post("/{wp_id}/export-template")
async def export_template(wp_id: UUID, body: ExportTemplateRequest):
    """导出底稿填写模板"""
    ...

@router.post("/{wp_id}/import-preview")
async def import_preview(wp_id: UUID, file: UploadFile):
    """上传填写完成的 xlsx → 返回 diff 预览"""
    ...

@router.post("/{wp_id}/import-apply")
async def import_apply(wp_id: UUID, body: ImportApplyRequest):
    """确认导入（应用 diff）"""
    ...
```

#### 11.7.4 前端组件

```vue
<!-- WpOfflineExportDialog.vue -->
<!-- 导出弹窗：选择 sheet 范围 + 可选加密 + 截止日期 + 联系人 -->

<!-- WpOfflineImportDialog.vue -->
<!-- 导入弹窗：4 步流程 -->
<!-- Step 1: 上传文件（拖拽 / 点击） -->
<!-- Step 2: 验证结果（_meta_ 校验 + schema_version 匹配） -->
<!-- Step 3: Diff 预览表格（变化字段高亮，逐条勾选） -->
<!-- Step 4: 冲突处理（覆盖/保留/合并）+ 确认导入 -->
```

#### 11.7.5 注意事项 sheet 内容模板

| 节 | 内容 |
|---|------|
| 一、填写说明 | 本底稿为「{wp_name}」，请在黄色区域填写相关数据 |
| 二、颜色语义 | 🟡黄色=可填写 / ⬜灰色=公式自动计算（勿改）/ 🟢绿色边框=必填 / 🔴红色=禁止修改 |
| 三、注意事项 | ①不要删除/插入行列 ②不要修改隐藏 sheet ③不要更改文件名中的编码 ④如有疑问联系项目组 |
| 四、截止日期 | 请于 {deadline} 前将填写完成的文件发回 |
| 五、联系人 | {manager_name} / {phone} / {email} |
| 六、版本信息 | 导出时间：{exported_at} / 系统版本：{app_version} |
| 七、安全提示 | 本文件含审计工作底稿数据，请妥善保管，不要转发给无关人员 |


### 11.8 US-15：HTML 底稿自动刷数

#### 数据流

```
底稿打开 / 保存后刷新
  → useWpRenderer.load() 拉 render-config
  → 后端遍历 schema.sheets[*].cross_refs[]
  → 批量调用 query_workpaper(wp_code, sheet, cell) 取值
  → 返回 html_data 中已填充最新值
  → 前端渲染时 cell 带 tooltip 显示来源
```

#### 后端批量取数

```python
# 在 GET /api/workpapers/{wp_id}/render-config 中增强
async def _resolve_auto_fill_values(schema: dict, project_id: UUID) -> dict:
    """批量解析 schema 中 source 标记的 cell，从 TB/WP/REPORT 取值"""
    fill_results = {}
    for sheet_name, sheet_schema in schema.get('sheets', {}).items():
        cross_refs = sheet_schema.get('cross_refs', [])
        for ref in cross_refs:
            # ref: { "cell": "B7", "source": "TB:1122:期末", "label": "应收账款期末余额" }
            value = await _fetch_source_value(ref['source'], project_id)
            fill_results[f"{sheet_name}!{ref['cell']}"] = {
                'value': value,
                'source': ref['source'],
                'label': ref.get('label', ''),
                'status': 'ok' if value is not None else 'unavailable',
            }
    return fill_results
```

#### 前端展示

```vue
<!-- 自动刷数 cell 渲染 -->
<el-tooltip
  v-if="cell.autoFill"
  :content="`来自 ${cell.autoFill.source}${cell.autoFill.label ? ' — ' + cell.autoFill.label : ''}`"
  placement="top"
>
  <span :class="['gt-auto-fill-cell', { 'gt-auto-fill-cell--unavailable': cell.autoFill.status === 'unavailable' }]">
    {{ cell.autoFill.status === 'ok' ? formatAmount(cell.autoFill.value) : '—' }}
  </span>
</el-tooltip>
```

### 11.9 US-16：程序表流程导航图

#### 数据结构

```typescript
interface AuditFlowGraph {
  objectives: AuditObjective[]      // 5 项认定
  risks: IdentifiedRisk[]           // 从风险评估关联
  procedures: ProcedureNode[]       // 当前底稿程序
  workpapers: LinkedWorkpaper[]     // 关联底稿
  edges: FlowEdge[]                 // 连线关系
}

interface AuditObjective {
  id: string
  name: string  // '存在' | '完整性' | '权利义务' | '准确性' | '列报'
}

interface IdentifiedRisk {
  id: string
  description: string
  level: 'significant' | 'normal' | 'low'
  sourceWpCode: string  // 风险评估底稿 wp_code（可跳转）
}

interface ProcedureNode {
  id: string
  programNo: number
  category: string      // '常规★' | 'IPO 加项' | '备选' | '舞弊应对'
  status: string        // 'completed' | 'in_progress' | 'not_applicable' | 'pending'
  assertions: string[]  // 关联的认定
}

interface LinkedWorkpaper {
  wpCode: string
  wpName: string
  status: string
  exists: boolean       // 是否已生成
}

interface FlowEdge {
  from: string  // node id
  to: string    // node id
  type: 'objective-risk' | 'risk-procedure' | 'procedure-workpaper'
}
```

#### 组件设计

```vue
<!-- GtAuditFlowGraph.vue — 审计逻辑流程图 -->
<template>
  <div class="gt-audit-flow-graph" v-show="expanded">
    <!-- 4 层横向布局 -->
    <div class="gt-flow-layer gt-flow-layer--objectives">
      <div class="gt-flow-layer__title">审计目标</div>
      <div
        v-for="obj in graph.objectives"
        :key="obj.id"
        class="gt-flow-node gt-flow-node--objective"
      >
        {{ obj.name }}
      </div>
    </div>

    <div class="gt-flow-layer gt-flow-layer--risks">
      <div class="gt-flow-layer__title">识别风险</div>
      <div
        v-for="risk in graph.risks"
        :key="risk.id"
        class="gt-flow-node gt-flow-node--risk"
        :class="`gt-flow-node--${risk.level}`"
        @click="jumpToRisk(risk)"
      >
        {{ risk.description }}
      </div>
    </div>

    <div class="gt-flow-layer gt-flow-layer--procedures">
      <div class="gt-flow-layer__title">应对程序</div>
      <div
        v-for="proc in graph.procedures"
        :key="proc.id"
        class="gt-flow-node gt-flow-node--procedure"
        :class="`gt-flow-node--${proc.status}`"
        @click="scrollToProgram(proc.programNo)"
      >
        {{ proc.programNo }}. {{ proc.category }}
      </div>
    </div>

    <div class="gt-flow-layer gt-flow-layer--workpapers">
      <div class="gt-flow-layer__title">关联底稿</div>
      <GtIndexChip
        v-for="wp in graph.workpapers"
        :key="wp.wpCode"
        :value="wp.wpCode"
        @click="jumpToWorkpaper(wp.wpCode)"
      />
    </div>

    <!-- SVG 连线层 -->
    <svg class="gt-flow-edges" :viewBox="edgesViewBox">
      <path
        v-for="edge in computedEdges"
        :key="`${edge.from}-${edge.to}`"
        :d="edge.path"
        class="gt-flow-edge"
        :class="`gt-flow-edge--${edge.type}`"
      />
    </svg>
  </div>
</template>
```

#### B 类目录架构图

```vue
<!-- GtBArchitectureTree.vue — 底稿架构树 -->
<template>
  <div class="gt-b-architecture-tree" v-show="expanded">
    <el-tree
      :data="treeData"
      :props="{ label: 'name', children: 'children' }"
      default-expand-all
      :expand-on-click-node="false"
      @node-click="onNodeClick"
    >
      <template #default="{ node, data }">
        <span class="gt-b-tree-node">
          <GtIndexChip :value="data.wpCode" :validate="false" />
          <span class="gt-b-tree-node__name">{{ data.name }}</span>
          <el-tag v-if="data.status" :type="statusType(data.status)" size="small">
            {{ statusLabel(data.status) }}
          </el-tag>
        </span>
      </template>
    </el-tree>
  </div>
</template>
```

#### 后端数据源

```python
# GET /api/workpapers/{wp_id}/audit-flow-graph
# 从以下数据源组装流程图：
# 1. schema.assertions → 审计目标层
# 2. risk_assessment（B 循环风险评估底稿）→ 风险层
# 3. html_data.programs → 程序层（含 status/category/assertions）
# 4. html_data.programs[*].linked_workpapers → 底稿层
# 5. edges 由 assertions ↔ risks ↔ programs ↔ workpapers 的关联关系自动生成
```
