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
 * - Tab kind 分发：chapter-editor / hour-budget（B60-1 受管，接统一桥）/ docx-inline
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
// ── B60-1 工时表接统一桥（原 `usePilotBridgeAdapter` 是零 API 空壳，见 syncBridge 注释）──
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../sync/workpaperSyncApi'
import { capabilityForEntry } from '../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../sync/WorkpaperSyncEditorHost.vue'
import { B60_STRUCTURED_CODES } from './constants/subSheetSchemas'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from '../composables/useWorkpaperReviewProvide'

// ─── Lazy-loaded sub-components ───
const GtB60MainDoc = defineAsyncComponent(() => import('./GtB60MainDoc.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))
const GtB60DocxPane = defineAsyncComponent(() => import('./GtB60DocxPane.vue'))
const GtB60SubSheetForm = defineAsyncComponent(() => import('./GtB60SubSheetForm.vue'))
const GtB60HourBudgetPanel = defineAsyncComponent(() => import('./GtB60HourBudgetPanel.vue'))
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
  /**
   * `hour-budget` = B60-1 工时表，**本 entry 唯一的受管 sheet**（契约
   * `b60.hour_budget.json` 只声明一张 `b601-managed`）⇒ 走统一桥的真双模式。
   * 原 kind 是 `navigate-sheet`：Tab 里只有一个「打开工时表 →」按钮，把用户 emit 去
   * 主页面切 sheet，受管 sheet 在 bundle 内**根本不渲染** ⇒ 桥无处可接。
   */
  kind: 'chapter-editor' | 'hour-budget' | 'docx-inline'
}

const B60_TABS: B60TabDef[] = [
  { id: 'B60', label: 'B60 审计策略', wpCode: 'B60', kind: 'chapter-editor' },
  { id: 'B60-1', label: 'B60-1 工时表', wpCode: 'B60-1', kind: 'hour-budget' },
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

// ═══ 主 B60 章节 Tab：**非受管**册的 legacy OO 视图（不接桥）═══════════════════
//
// 🔴 为什么主册不接桥：契约 `b60.hour_budget.json` 的 `sheets` 只声明**一张**
//    `b601-managed`（`B60-1工时预算与控制表`），`review.reviewed_basis` 也逐字写明权威
//    模板是 `B/B60-1 审计项目工时预算与控制表.xlsx`。主 B60 那册没有受管 sheet ——
//    拿 B60-1 的 adapter 去 materialize 主册会打开错的文档。同 G7 的「非受管 sheet 走
//    本地 legacy ref」范式。
//
// 🔴 这里原来挂的是 `usePilotBridgeAdapter`：它自称「委派给 sync bridge」，实现里
//    `switchMode()` 只置 `currentMode` + 写 localStorage（**零 API 调用**）、
//    `isOoAvailable` 硬编码 `ref(true)`、`ooConfig` 恒 `null`。所以那面「OnlyOffice
//    拉取成功」的绿 tag 是**无条件**显示的，不代表任何探测结果。
const mainLegacyOoMode = ref(false)
const mainSwitching = ref(false)
const mainMode = computed<'html' | 'onlyoffice'>(() =>
  mainLegacyOoMode.value ? 'onlyoffice' : 'html',
)
const mainModeOptions = [
  { label: '章节编辑', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const },
]
const mainOoStatus = computed(() =>
  mainSwitching.value
    ? { type: 'info' as const, text: '切换中…' }
    : { type: 'info' as const, text: '在线编辑独立于章节数据（主册无受管 sheet）' },
)

/** 主册切换：切走前 await 章节编辑落库，切回时重载（章节编辑器自带防抖）。 */
async function switchMainMode(target: 'html' | 'onlyoffice'): Promise<void> {
  if (target === mainMode.value || mainSwitching.value) return
  mainSwitching.value = true
  try {
    if (target === 'onlyoffice') {
      await chapterEditorRef.value?.flushPendingSaves?.()
      mainLegacyOoMode.value = true
    } else {
      mainLegacyOoMode.value = false
      await reloadChapterData()
    }
  } finally {
    mainSwitching.value = false
  }
}

// ═══ B60-1 工时表：统一桥（G4-1 `simple_checklist` canary）═════════════════════
//
// 🔴 `WorkpaperSyncEditorHost` **自己不触发 materialize** —— 它只在
//    `descriptor !== null && bridge.mode === 'oo'` 时创建 DocEditor，而 descriptor 只能由
//    `bridge.switchToOnlyOffice()` 产出。「挂了宿主」≠「接了桥」，必须真调那个方法
//    （基线由 `sync/__tests__/bridgeMaterializeDriven.spec.ts` 钉住）。
//
// ✅ 两个方向都已接通（2026-09-27）：
//    · HTML→OO：`flushHtml` 先 await 面板落库再读投影 → materialize；
//    · OO→HTML：后端 `oo_to_html` 按 `store_item_registry` 的 plan 取
//      `pilot_simple_checklist.merge_projection_into_store_rows` 把受管格合并回
//      `B60-1-hour-budget-rows`，`reloadHtml` 重读面板即可见。
//    此前 `b60.hour_budget` 是 `NON_STORE_BACKED_ADAPTERS` 的唯一成员（契约无
//    `html_store` ⇒ 回方向被提前跳过）—— 那条归类描述的是「前端还没有 HTML 面」
//    这个时点事实，`GtB60HourBudgetPanel` 落地后已随契约一并改正。

/** entry id（manifest 冻结值，与 `pilot_simple_checklist.PILOT_ENTRY_ID` 逐字一致）。 */
const B60_SYNC_ENTRY_ID = 'xlsx/b60/gt-b60-bundle'
/** 受管 sheet 的契约键（`b60.hour_budget.json` → `sheets[0].sheet_key`）。 */
const B601_SHEET_KEY = 'b601-managed'

/**
 * 🔴 桥绑的是 **B60-1 子底稿自己的 wp_id**，不是宿主 `props.wpId`（那是主 B60 册）。
 * `projection_target_resolution` 对 B60 解析到的也是 `B60-1`（3 个候选底稿里只有它
 * 全有文件）。绑错 wpId 会打开错的 OO 文档。
 */
const b601WpId = computed(() => wpIdMap.value['B60-1'] ?? '')
const hourBudgetPanelRef = ref<{
  flushPendingSave: () => Promise<void>
  reload: () => Promise<void>
} | null>(null)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(B60_SYNC_ENTRY_ID),
  wpId: b601WpId,
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(B601_SHEET_KEY),
  capability: capabilityForEntry(B60_SYNC_ENTRY_ID),
  flushHtml: async () => {
    // 🔴 先 await 面板落库再读投影：工时面板防抖 600ms，不等它 materialize 出的 xlsx
    //    会少掉最后那批编辑且无任何提示。
    await hourBudgetPanelRef.value?.flushPendingSave()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: b601WpId.value,
      entryId: B60_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: async () => {
    await hourBudgetPanelRef.value?.reload()
  },
})

const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(() =>
  (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncSwitching = ref(false)
/** B60-1 的渲染模式以**桥**为真源（不再有第二份本地 mode ref）。 */
const b601Mode = computed<'html' | 'onlyoffice'>(() =>
  syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html',
)
const b601ModeOptions = [
  { label: '结构化视图', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const },
]

/**
 * 四分支保存协议（照 D3/F3/G2/G7 同构）。
 *
 * 🔴 切换器**不带 `:disabled`**：健康检查是异步的，disabled 在未就绪时会把「在线编辑」
 *    锁死、点击被彻底吞掉（D4 已实证的 bug ③）。门禁在本函数里 await 兜底。
 */
async function switchB601Mode(target: 'html' | 'onlyoffice'): Promise<void> {
  if (target === b601Mode.value || syncSwitching.value) return
  syncSwitching.value = true
  try {
    if (target === 'onlyoffice') {
      // ① HTML → OO：桥内部先 flushHtml（await 面板落库）→ pending → materialize
      await syncBridge.switchToOnlyOffice()
      return
    }
    if (syncBridge.mode.value !== 'oo') return
    if (String(syncBridge.state.value) === 'applied') {
      // ② 改动已落库 ⇒ 只重载，不再发保存 ⇒ 秒切
      await syncBridge.reloadAfterApplied()
    } else if (!syncBridge.dirty.value) {
      // ③ 未改动 ⇒ clean close，不发强制保存 ⇒ 丝滑
      await syncBridge.leaveWithoutSaving()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      // ④ 有改动 ⇒ 强制保存（慢是允许的，用户没先保存）
      await syncEditorHostRef.value.forceSave()
    } else {
      await syncBridge.switchToHtml()
    }
  } catch {
    // 失败保持当前视图；错误已由桥写入 lastError / feedback（fail visible）
  } finally {
    syncSwitching.value = false
  }
}

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
    // hour-budget (B60-1 工时表) is always visible —— 未生成时 Tab 内显示占位
    if (tab.kind === 'hour-budget') return true
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
function handleTabClick(_tab: any): void {
  // 🔴 原实现：点 B60-1 Tab 就 `emit('navigate-sheet','B60-1')` 把用户弹去主页面 ——
  //    受管 sheet 在 bundle 内根本不渲染，桥无处可接。现在 B60-1 在 Tab 内直接双模式，
  //    跳转改为 Tab 里的显式按钮（用户主动点才走）。
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
                :model-value="mainMode"
                :options="mainModeOptions"
                @change="(v: any) => switchMainMode(v as 'html' | 'onlyoffice')"
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
            <ErrorBoundary v-if="mainMode === 'html'">
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

          <!-- ─── hour-budget kind (B60-1 工时表 · 本 entry 唯一受管 sheet) ─── -->
          <template v-else-if="tab.kind === 'hour-budget'">
            <div v-if="!b601WpId" class="gt-b60-bundle__pending">
              B60-1 工时表尚未生成（生成后即可在此双模式编辑）
            </div>
            <template v-else>
              <div class="gt-b60-bundle__mode-bar">
                <!--
                  🔴 不带 `:disabled`：健康检查异步，disabled 会在未就绪时把「在线编辑」
                  锁死且点击被彻底吞掉（D4 已实证）。门禁在 switchB601Mode 里 await 兜底。
                -->
                <el-segmented
                  :model-value="b601Mode"
                  :options="b601ModeOptions"
                  :disabled="syncBusy || syncSwitching"
                  size="small"
                  @change="(v: any) => switchB601Mode(v as 'html' | 'onlyoffice')"
                />
                <el-tag v-if="syncSwitching" type="info" size="small" effect="light">切换中…</el-tag>
                <el-button size="small" @click="emit('navigate-sheet', 'B60-1')">
                  在主页面打开 →
                </el-button>
              </div>

              <ErrorBoundary v-if="b601Mode === 'html'">
                <GtB60HourBudgetPanel
                  ref="hourBudgetPanelRef"
                  :wp-id="b601WpId"
                  :project-id="props.projectId"
                  :readonly="props.readonly"
                />
              </ErrorBoundary>

              <!-- 在线编辑：descriptor 由 switchB601Mode → bridge.switchToOnlyOffice() 产出 -->
              <div v-else class="oo-container">
                <WorkpaperSyncEditorHost
                  v-if="syncOoDescriptor"
                  ref="syncEditorHostRef"
                  :descriptor="syncOoDescriptor"
                  :bridge="syncBridge"
                />
                <div v-else class="oo-loading">正在打开 B60-1 同步编辑器…</div>
              </div>
            </template>
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

/* ─── B60-1 在线编辑容器 ─── */
/* 🔴 必须带**视口相关的确定高度**：`WorkpaperSyncEditorHost` 根元素是 height:100% + flex 列，
   只给 min-height 时编辑区会被压到接近下限，OnlyOffice 在页面上只剩一条（2026-09-22 实测）。 */
.oo-container {
  min-height: 600px;
  height: calc(100vh - 320px);
  overflow: hidden;
  border-radius: 8px;
}

.oo-loading {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}

/* ─── Pending / Empty ─── */
.gt-b60-bundle__pending {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}
</style>
