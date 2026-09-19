<script setup lang="ts">
/**
 * GtB60Bundle — B60 总体审计策略聚合组件
 *
 * 顶层 Bundle 通过 el-tabs 管理 B60 系列全部子底稿。
 * 参照 GtA17Bundle 架构：固定顺序 Tab + wpIdMap 动态可见性 + defineAsyncComponent 懒加载。
 *
 * 职责：
 * - 通过 GET /api/workpapers/{wpId}/wp-index 构建 wpIdMap（wp_code → wp_id）
 * - 渲染适用性矩阵面板（8 个子底稿勾选）
 * - 管理 10 个固定顺序 Tab（B60 恒可见，其余由 wpIdMap + 适用性联合推导可见性）
 * - Tab kind 分发：chapter-editor / navigate-sheet / docx-inline
 * - 提供 el-segmented 模式切换（章节编辑 / 在线编辑）
 * - 空状态占位"B60 系列子底稿尚未生成"
 * - ErrorBoundary 隔离子底稿渲染失败
 *
 * Spec: .kiro/specs/b60-dedicated-component/
 * Requirements: 1.1, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 12.1, 12.4
 */
import { ref, computed, toRef, onMounted, defineAsyncComponent, provide } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useB60Applicability, B60_SUB_WP_CODES } from './composables/useB60Applicability'
import { DEFAULT_CHAPTER_DEFINITIONS } from './constants/defaultChapterDefinitions'
// Task 45: legacy useB60DualMode deleted — pilot host now delegates to sync bridge.
import { usePilotBridgeAdapter } from '../sync/usePilotBridgeAdapter'
import { B60_STRUCTURED_CODES } from './constants/subSheetSchemas'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from '../composables/useWorkpaperReviewProvide'

// ─── Lazy-loaded sub-components ───
const GtB60MainDoc = defineAsyncComponent(() => import('./GtB60MainDoc.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))
const GtB60DocxPane = defineAsyncComponent(() => import('./GtB60DocxPane.vue'))
const GtB60SubSheetForm = defineAsyncComponent(() => import('./GtB60SubSheetForm.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('../GtWpReviewDialogHost.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
  year?: number
  /** 由父级（GtBIndex）从 cycle_workpapers 派生的 B60-* 子底稿 wp_id 映射 */
  subWpIdMap?: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Version Trail ───
const { versionTrailRef, scheduleAutoSnapshot, openVersionHistory } = useWorkpaperVersionToolbar({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── Review Dialog ───
useWorkpaperReviewProvide({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// provide scheduleAutoSnapshot for child components (GtB60MainDoc uses it after save)
provide('scheduleAutoSnapshot', scheduleAutoSnapshot)

// ─── Tab Definitions (fixed order) ───
interface B60TabDef {
  id: string
  label: string
  wpCode: string
  kind: 'chapter-editor' | 'navigate-sheet' | 'docx-inline'
}

const B60_TABS: B60TabDef[] = [
  { id: 'B60', label: 'B60 审计策略', wpCode: 'B60', kind: 'chapter-editor' },
  { id: 'B60-1', label: 'B60-1 工时表', wpCode: 'B60-1', kind: 'navigate-sheet' },
  { id: 'B60-2-1', label: 'B60-2-1 IT复杂性判断表', wpCode: 'B60-2-1', kind: 'docx-inline' },
  { id: 'B60-2-2', label: 'B60-2-2 IT审计进场前通知表', wpCode: 'B60-2-2', kind: 'docx-inline' },
  { id: 'B60-2-3', label: 'B60-2-3 IT审计计划备忘录', wpCode: 'B60-2-3', kind: 'docx-inline' },
  { id: 'B60-3', label: 'B60-3 评估专家工作计划', wpCode: 'B60-3', kind: 'docx-inline' },
  { id: 'B60A', label: 'B60A 内控审计特殊考虑', wpCode: 'B60A', kind: 'docx-inline' },
  { id: 'B60B', label: 'B60B IPO审计特殊考虑', wpCode: 'B60B', kind: 'docx-inline' },
  { id: 'B60C', label: 'B60C 国企审计特殊考虑', wpCode: 'B60C', kind: 'docx-inline' },
  { id: 'B60D', label: 'B60D 监管机构报送', wpCode: 'B60D', kind: 'docx-inline' },
]

// 适用性矩阵描述文本（只读）
const APPLICABILITY_DESCRIPTIONS: Record<string, string> = {
  'B60-2-1': '项目涉及 IT 系统审计时适用',
  'B60-2-2': '项目涉及 IT 系统审计时适用',
  'B60-2-3': '项目涉及 IT 系统审计时适用',
  'B60-3': '项目需要利用评估专家工作时适用',
  'B60A': '同时执行内部控制审计时适用',
  'B60B': 'IPO 申报财务报表审计时适用',
  'B60C': '国有企业年度财务报表审计时适用',
  'B60D': '需向监管机构报送策略和计划时适用',
}

// ─── State ───
const loading = ref(false)
const activeTab = ref('B60')
const wpIdMap = ref<Record<string, string>>({})
const responsesSnapshot = ref<Record<string, { conclusion: string | null; remark: string | null }>>({})
const chapterDefinitions = ref<any[]>([])
const projectContext = ref<Record<string, string>>({})
const chapterEditorRef = ref<{ flushPendingSaves?: () => Promise<void> } | null>(null)

// ─── Main doc dual-mode — Task 45: bridge adapter replaces legacy useB60DualMode ───
const mainDual = usePilotBridgeAdapter({
  entryId: 'xlsx/b60/gt-b60-bundle',
  wpId: toRef(props, 'wpId'),
  sheetName: computed(() => 'B60'),
  flushBeforeOo: async () => {
    if (chapterEditorRef.value?.flushPendingSaves) {
      await chapterEditorRef.value.flushPendingSaves()
    }
  },
  reloadHtml: async () => {
    await reloadChapterData()
  },
})
const mainModeOptions = computed(() => [
  { label: '章节编辑', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const, disabled: !mainDual.isOoAvailable.value },
])
const mainOoStatus = computed(() => {
  if (mainDual.switching.value) return { type: 'info' as const, text: '切换中…' }
  if (mainDual.isOoAvailable.value) return { type: 'success' as const, text: 'OnlyOffice 拉取成功' }
  return { type: 'warning' as const, text: 'OnlyOffice 不可用（在线编辑已禁用）' }
})

// ─── Applicability composable ───
const wpIdRef = computed(() => props.wpId)
const applicability = useB60Applicability({
  wpId: wpIdRef,
  responsesSnapshot,
})
const { applicabilityMap, toggleApplicability, isApplicable } = applicability

// ─── wpIdMap construction ───
// 优先用父级传入的 subWpIdMap（来自 cycle_workpapers，已含各子底稿 wp_id）；
// 无则回退旧 wp-index 端点（部分部署可能提供）。
async function loadWpIndex(): Promise<void> {
  if (props.subWpIdMap && Object.keys(props.subWpIdMap).length > 0) {
    wpIdMap.value = { ...props.subWpIdMap }
    return
  }
  if (!props.wpId) return
  try {
    const { data } = await http.get(`/api/workpapers/${props.wpId}/wp-index`, { _silent: true } as any)
    const items: any[] = Array.isArray(data) ? data : (data?.data || [])
    const map: Record<string, string> = {}
    for (const item of items) {
      const code = item.wp_code || ''
      if (code.startsWith('B60-') || /^B60[A-D]$/.test(code)) {
        if (item.wp_id) map[code] = item.wp_id
      }
    }
    wpIdMap.value = map
  } catch {
    wpIdMap.value = {}
  }
}

// ─── Load render-config data ───
async function loadRenderData(): Promise<void> {
  if (!props.wpId) return
  try {
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`)
    const sheets = data?.sheets || data?.data?.sheets || []
    const sheet = sheets[0] || {}
    const htmlData = sheet.html_data || {}
    responsesSnapshot.value = htmlData.responses_snapshot || {}
    projectContext.value = htmlData.project_context || {}
    // chapter_definitions 已通过独立 API 加载（含 10s 超时降级），
    // 但如果 render-config 有数据且独立 API 尚未返回，也可作为候选源
    if (!chapterDefinitions.value.length && htmlData.chapter_definitions?.length) {
      chapterDefinitions.value = htmlData.chapter_definitions
    }
  } catch {
    responsesSnapshot.value = {}
    projectContext.value = {}
  }
}

// ─── Load chapter definitions from API with 10s timeout + fallback ───
const chapterDefFallbackUsed = ref(false)

async function loadChapterDefinitions(): Promise<void> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)
    const { data } = await http.get('/api/b60/chapter-definitions', {
      signal: controller.signal,
    })
    clearTimeout(timeout)
    const defs = Array.isArray(data) ? data : (data?.data || [])
    if (defs.length > 0) {
      chapterDefinitions.value = defs
      chapterDefFallbackUsed.value = false
    } else {
      // Empty response — use default
      chapterDefinitions.value = DEFAULT_CHAPTER_DEFINITIONS
      chapterDefFallbackUsed.value = true
      ElMessage.warning('章节定义加载失败，当前使用默认配置')
    }
  } catch {
    // Timeout or non-2xx — fallback to built-in defaults
    chapterDefinitions.value = DEFAULT_CHAPTER_DEFINITIONS
    chapterDefFallbackUsed.value = true
    ElMessage.warning('章节定义加载失败，当前使用默认配置')
  }
}

// ─── Reload latest chapter data (for mode switch back to 章节编辑) ───
async function reloadChapterData(): Promise<void> {
  if (!props.wpId) return
  try {
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`)
    const sheets = data?.sheets || data?.data?.sheets || []
    const sheet = sheets[0] || {}
    const htmlData = sheet.html_data || {}
    responsesSnapshot.value = htmlData.responses_snapshot || {}
    projectContext.value = htmlData.project_context || {}
  } catch {
    // silent — keep existing data on failure
  }
}

// ─── Tab visibility logic ───
const visibleTabs = computed(() =>
  B60_TABS.filter(tab => {
    // chapter-editor (B60 main) is always visible
    if (tab.kind === 'chapter-editor') return true
    // navigate-sheet (工时表) is always visible
    if (tab.kind === 'navigate-sheet') return true
    // If marked not applicable → hidden
    if (!isApplicable(tab.wpCode)) return false
    // 有结构化 schema → 始终显示（结构化数据持久化到主 B60 wp_id，不依赖子底稿 wp 记录）
    if (B60_STRUCTURED_CODES.includes(tab.wpCode)) return true
    // 无结构化 schema（B60-2-2/B60-2-3）→ 仅在有子底稿 wp 记录时可在线编辑
    if (wpIdMap.value[tab.wpCode]) return true
    return false
  }),
)

// Tabs marked applicable but not yet generated (show placeholder)
function isTabPendingGeneration(tab: B60TabDef): boolean {
  if (tab.kind !== 'docx-inline') return false
  if (B60_STRUCTURED_CODES.includes(tab.wpCode)) return false
  return isApplicable(tab.wpCode) && !wpIdMap.value[tab.wpCode]
}

// ─── Empty state detection ───
// 主底稿章节编辑器 + 结构化子底稿（持久化到主 B60 wp_id）恒可用，故 bundle 永不为空
const showEmptyState = computed(() => false)

// ─── Tab click handler ───
function handleTabClick(tab: any): void {
  const tabDef = B60_TABS.find(t => t.id === tab.paneName)
  if (tabDef?.kind === 'navigate-sheet') {
    // Emit navigate-sheet event for B60-1 工时表
    emit('navigate-sheet', 'B60-1')
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      loadWpIndex(),
      loadRenderData(),
      loadChapterDefinitions(),
    ])
    // 🔴 这里曾调 `mainDual.checkOOHealth()` —— usePilotBridgeAdapter 没有该方法
    // （OO 健康探测已收归 bridge 的 materialize 协议，适配器刻意不做）。
    // 结果是 onMounted 抛 `mainDual.checkOOHealth is not a function`
    // ⇒ B60 整页崩成「页面渲染出错」（finally 不吞异常）。
    // 在线编辑门控现在读 `mainDual.isOoAvailable`，不需要宿主自行探测。
  } finally {
    loading.value = false
  }
})

// ─── Provide for child components ───
// openReviewDialog is provided by useWorkpaperReviewProvide above.
// scheduleAutoSnapshot is provided above for child composables to call after save.
</script>

<template>
  <div class="gt-b60-bundle" v-loading="loading">
    <!-- Empty state when no sub-workpapers generated -->
    <el-empty
      v-if="!loading && showEmptyState"
      description="B60 系列子底稿尚未生成"
      :image-size="120"
    />

    <template v-else>
      <!-- ─── Version Trail (版本历史抽屉) ─── -->
      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />

      <!-- ─── Review Dialog Host (复核对话) ─── -->
      <GtWpReviewDialogHost />

      <!-- ─── Applicability Matrix Panel ─── -->
      <el-card shadow="never" class="gt-b60-bundle__applicability">
        <template #header>
          <span class="applicability-title">适用性矩阵</span>
        </template>
        <el-table
          :data="B60_SUB_WP_CODES.map(code => ({ code, label: B60_TABS.find(t => t.wpCode === code)?.label || code, description: APPLICABILITY_DESCRIPTIONS[code] || '', applicable: applicabilityMap[code] ?? true }))"
          size="small"
          :border="false"
          class="applicability-table"
        >
          <el-table-column prop="code" label="编码" width="100" />
          <el-table-column prop="label" label="子底稿名称" min-width="200" />
          <el-table-column prop="description" label="适用条件" min-width="240">
            <template #default="{ row }">
              <span class="applicability-desc">{{ row.description }}</span>
            </template>
          </el-table-column>
          <el-table-column label="适用性" width="80" align="center">
            <template #default="{ row }">
              <el-checkbox
                :model-value="row.applicable"
                :disabled="props.readonly"
                @change="(val: boolean) => toggleApplicability(row.code, val)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- ─── Tab Navigation ─── -->
      <el-tabs v-model="activeTab" @tab-click="handleTabClick" class="gt-b60-bundle__tabs">
        <el-tab-pane
          v-for="tab in visibleTabs"
          :key="tab.id"
          :label="tab.label"
          :name="tab.id"
          lazy
        >
          <!-- ─── chapter-editor kind (B60 main) ─── -->
          <template v-if="tab.kind === 'chapter-editor'">
            <!-- Mode switcher（切在线编辑前预拉 config「拉取成功」才切换） -->
            <div class="gt-b60-bundle__mode-bar">
              <el-segmented
                :model-value="mainDual.currentMode.value"
                :options="mainModeOptions"
                @change="mainDual.onModeChange"
              />
              <el-tag :type="mainOoStatus.type" size="small" effect="light">
                {{ mainOoStatus.text }}
              </el-tag>
              <!-- Fallback warning when using default chapter definitions -->
              <el-tag
                v-if="chapterDefFallbackUsed"
                type="warning"
                size="small"
                class="gt-b60-bundle__fallback-tag"
              >
                使用默认章节配置
              </el-tag>
            </div>

            <!-- 结构化主底稿（15 章 / 38 表 + SCOT+ 接 B50） -->
            <ErrorBoundary v-if="mainDual.currentMode.value === 'html'">
              <GtB60MainDoc
                ref="chapterEditorRef"
                :wp-id="props.wpId"
                :project-id="props.projectId"
                :readonly="props.readonly"
              />
            </ErrorBoundary>

            <!-- OnlyOffice mode（拉取成功后才渲染） -->
            <ErrorBoundary v-else>
              <GtOnlyOfficeSheet
                :wp-id="props.wpId"
                sheet-name="B60"
                :project-id="props.projectId"
              />
            </ErrorBoundary>
          </template>

          <!-- ─── navigate-sheet kind (B60-1 工时表) ─── -->
          <template v-else-if="tab.kind === 'navigate-sheet'">
            <div class="gt-b60-bundle__navigate-hint">
              <el-button type="primary" @click="emit('navigate-sheet', 'B60-1')">
                打开工时表 →
              </el-button>
              <p class="navigate-desc">B60-1 工时表通过主页面 sheet 切换打开（复用 xlsx 渲染）</p>
            </div>
          </template>

          <!-- ─── docx-inline kind（双模式：结构化视图 / 在线编辑，OnlyOffice 拉取成功才显示） ─── -->
          <template v-else-if="tab.kind === 'docx-inline'">
            <ErrorBoundary>
              <!-- 有结构化 schema：结构化视图持久化到主 B60 wp_id；在线编辑需子底稿 wp 记录 -->
              <GtB60DocxPane
                v-if="B60_STRUCTURED_CODES.includes(tab.wpCode)"
                :wp-id="wpIdMap[tab.wpCode] || ''"
                :project-id="props.projectId"
                :sheet-name="tab.wpCode"
                :has-structured="true"
                :readonly="props.readonly"
              >
                <GtB60SubSheetForm
                  :wp-id="props.wpId"
                  :code="tab.wpCode"
                  :readonly="props.readonly"
                />
              </GtB60DocxPane>
              <!-- 无结构化 schema：需子底稿 wp 记录走 OnlyOffice -->
              <GtB60DocxPane
                v-else-if="wpIdMap[tab.wpCode]"
                :wp-id="wpIdMap[tab.wpCode]"
                :project-id="props.projectId"
                :sheet-name="tab.wpCode"
                :has-structured="false"
                :readonly="props.readonly"
              />
              <div v-else-if="isTabPendingGeneration(tab)" class="gt-b60-bundle__pending">
                该子底稿尚未生成（结构复杂，暂仅支持在线编辑，需先生成底稿）
              </div>
            </ErrorBoundary>
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.gt-b60-bundle {
  padding: 16px;
}

/* ─── Applicability Matrix ─── */
.gt-b60-bundle__applicability {
  margin-bottom: 16px;
}

.applicability-title {
  font-size: 14px;
  font-weight: 600;
}

.applicability-table {
  font-size: 13px;
}

.applicability-desc {
  color: #909399;
  font-size: 12px;
}

/* ─── Tabs ─── */
.gt-b60-bundle__tabs {
  margin-top: 8px;
}

/* ─── Mode bar ─── */
.gt-b60-bundle__mode-bar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.gt-b60-bundle__fallback-tag {
  flex-shrink: 0;
}

/* ─── Navigate sheet hint ─── */
.gt-b60-bundle__navigate-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 12px;
}

.navigate-desc {
  color: #909399;
  font-size: 13px;
  margin: 0;
}

/* ─── Pending / Empty ─── */
.gt-b60-bundle__pending {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}
</style>
