<!--
  GtWpRenderer.vue — 底稿 HTML 渲染器顶层路由组件

  按 componentType 分发到对应子组件（A/B/C/D/E/H/skip/univer）。
  遵循 overlay 模式：容器永远渲染，loading/error 用蒙层覆盖。
  不加顶层 v-if="loading" 守卫（避免 init 死锁）。

  锚定 spec workpaper-html-renderer Task 3.4
  Validates: Requirements 1.2（9 类路由分发）
-->
<template>
  <div class="gt-wp-renderer" :class="{ 'gt-wp-renderer--fullscreen': isWpFullscreen }" ref="containerRef">
    <!-- Loading overlay -->
    <GtLoadingOverlay
      :visible="loading"
      text="正在加载渲染配置..."
      :hint="loadingHint"
      :size="32"
    />

    <!-- Error overlay -->
    <div v-if="!loading && error" class="gt-wp-renderer__error">
      <el-result icon="error" :title="errorTitle" :sub-title="errorSubTitle">
        <template #extra>
          <el-button type="primary" @click="reload">重试</el-button>
        </template>
      </el-result>
    </div>

    <!-- Ready: dispatch by componentType -->
    <template v-if="!loading && !error && renderConfig">
      <!-- B15/合并类: 重定向到委托模块 -->
      <div v-if="renderConfig.redirect" class="gt-wp-renderer__redirect">
        <el-result icon="info" title="此底稿由独立模块承载">
          <template #sub-title>
            <span>{{ redirectHint }}</span>
          </template>
          <template #extra>
            <el-button type="primary" @click="handleRedirectNavigation">
              前往{{ redirectModuleLabel }}
            </el-button>
          </template>
        </el-result>
      </div>

      <template v-else>
      <el-alert
        v-if="schemaFallbackBanner"
        type="info"
        :closable="false"
        class="gt-wp-renderer__fallback-banner"
      >
        {{ schemaFallbackBanner }}
      </el-alert>

      <!-- 编制信息表头（workpaper 级，所有 sheet 共享）
           b-index sheet 自带等价编制信息块（GtBIndex 内置），此处跳过避免重复；
           G12/G13/G14 底稿目录 Tab 委托到循环 HTML 目录组件，需显示统一表头
           index-no-override：传当前 sheet 级索引号（如 D1A），表头右上角随 sheet 切换更新 -->
      <GtWpPreparationHeader
        v-if="showWorkpaperPreparationHeader"
        :wp-id="wpId"
        :readonly="readonly"
        :index-no-override="activeSheetIndexNo"
      />

      <!-- Sheet 选择器（多 sheet 时显示） -->
      <div v-if="visibleSheets.length > 1" class="gt-wp-renderer__sheet-tabs">
        <!-- 切换底稿：弹出本科目底稿树形结构（4 阶段），点节点跳转对应 sheet -->
        <el-popover
          v-model:visible="switchPopoverVisible"
          placement="bottom-start"
          :width="520"
          trigger="click"
          popper-class="gt-wp-renderer__switch-popover"
        >
          <template #reference>
            <el-button size="small" class="gt-wp-renderer__switch-btn">
              <el-icon class="gt-wp-renderer__switch-icon"><Switch /></el-icon>
              切换
            </el-button>
          </template>
          <div class="gt-wp-renderer__switch-tree">
            <GtBArchitectureTree
              :active-sheet="activeSheetName"
              :html-data="switchTreeHtmlData"
              @navigate="onSwitchNavigate"
            />
          </div>
        </el-popover>
        <el-tabs
          v-model="activeSheetName"
          v-tab-wheel
          type="card"
          class="gt-wp-renderer__sheet-tabs-inner"
        >
          <el-tab-pane
            v-for="sheet in tabSheets"
            :key="sheet.sheet_name"
            :name="sheet.sheet_name"
          >
            <template #label>
              <span
                v-if="sheet.sheet_name === WHOLE_EXCEL_TAB"
                class="gt-wp-renderer__tab-label gt-wp-renderer__tab-label--excel"
                title="完整 Excel（OnlyOffice 编辑整本底稿）"
              >
                <span class="gt-wp-renderer__tab-icon">📊</span>
                <span class="gt-wp-renderer__tab-name">完整Excel</span>
              </span>
              <span v-else class="gt-wp-renderer__tab-label" :title="sheet.sheet_name">
                <span class="gt-wp-renderer__tab-icon">{{ getSheetIcon(sheet.componentType) }}</span>
                <span class="gt-wp-renderer__tab-name">{{ sheet.sheet_name }}</span>
              </span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 统一功能工具栏（所有底稿类型共享，a1-dashboard 自管工具栏跳过）。
           AI 底稿复核（本页/批量）放入工具栏中间插槽，占用左右按钮之间的空档，
           全底稿统一入口覆盖 A~S 全部循环；权限门控 manager/partner/qc/admin。 -->
      <GtWpToolbar
        v-if="componentType !== 'a1-dashboard'"
        :fullscreen="isWpFullscreen"
        :wp-id="wpId"
        @export-template="onExportTemplate"
        @export-data="onExportData"
        @import-data="onImportData"
        @add-row="onAddRow"
        @toggle-fullscreen="isWpFullscreen = !isWpFullscreen"
        @open-attachments="attachmentsDrawerVisible = true"
      >
        <template v-if="activeSheetName" #center>
          <GtWpAiReviewToolbar
            :wp-id="wpId"
            :project-id="renderConfig?.project_id ?? ''"
            :wp-code-prefix="renderConfig?.wp_code ?? ''"
            :sheet-name="activeSheetName"
            :year="preparationYear"
            @navigate-sheet="onChildNavigateSheet"
          />
        </template>
      </GtWpToolbar>

      <!-- 内容区域 -->
      <div class="gt-wp-renderer__content">
      <!--
        附注联动复盘 P0-2：披露 sheet 顶部统一「附注同步状态条」。
        一处接入覆盖全部循环的披露表（判据=sheet 名含附注披露/上市/国企 或 X-note-listed/soe），
        解决"46 个 sync builder 就绪但生产零同步记录"的可见性缺口。只读，不代替页内同步按钮。
      -->
      <GtWpDisclosureSyncBar
        v-if="isDisclosureSheet"
        :project-id="renderConfig?.project_id ?? ''"
        :year="preparationYear"
        :wp-code="renderConfig?.wp_code ?? ''"
        :sheet-name="activeSheetName"
      />
      <!-- 注册表分发：HTML 类组件（A/B/C/D 5 种/E/H 共 10 种 componentType） -->
      <component
        v-if="rendererEntry"
        ref="activeComponentRef"
        :is="rendererEntry.component"
        :key="htmlRendererKey"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :readonly="readonly"
        :wp-code="renderConfig?.wp_code ?? ''"
        v-bind="extraComponentProps"
        @save="onSave"
        @subtable-toggle="onSubtableToggle"
        @standard-switch="onStandardSwitch"
        @sync-to-disclosure-notes="onSyncToDisclosureNotes"
        @jump-to-reference="onJumpToReference"
        @jump-to-section="onJumpToSection"
        @trigger-procedure-trimming-suggestion="onTrimmingSuggestion"
        @conclusion-change="onConclusionChange"
        @step-advance="onStepAdvance"
        @open-attachment="onOpenAttachment"
        @formula-saved="reload"
        @open-formula="onOpenFormula"
        @restore="reload"
        @navigate-sheet="onChildNavigateSheet"
      />

      <!-- Univer 类（F/G）有模板网格数据时只读展示；C-附注披露无 schema 时也走只读网格兜底；无注册表 renderer 但有 grid cells 时兜底 -->
      <!-- OnlyOffice 渲染（非 HTML 白名单 sheet，后端标记 onlyoffice:true） -->
      <GtOnlyOfficeSheet
        v-else-if="isOnlyOfficeSheet && !onlyOfficeFallback"
        :key="activeSheetName"
        :wp-id="wpId"
        :sheet-name="isWholeExcelTab ? wholeWorkbookSheetName : activeSheetName"
        :project-id="renderConfig?.project_id ?? ''"
        :whole-workbook="isWholeExcelTab"
        :readonly="readonly"
        @fallback="onOnlyOfficeFallback"
      />

      <!-- Grid 兜底（Univer 有网格 / C-附注无 schema / OnlyOffice 降级 / 无注册表 renderer 但有 grid cells） -->
      <template v-else-if="(componentType === 'univer' && hasGridCells) || cNoteGridFallback || noRendererGridFallback || onlyOfficeFallback">
        <div v-if="isWholeExcelTab && onlyOfficeFallback" class="gt-wp-renderer__whole-excel-fallback">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="OnlyOffice 暂不可用，已从整册 Excel 模板拉取只读网格展示"
            class="gt-wp-renderer__whole-excel-alert"
          />
          <div v-if="wholeExcelSheets.length" class="gt-wp-renderer__whole-excel-sheets">
            <el-select
              v-model="wholeExcelActiveSheet"
              size="small"
              filterable
              placeholder="选择 sheet"
              style="min-width: 240px"
              @change="(v: string) => loadWholeExcelGrid(v)"
            >
              <el-option v-for="s in wholeExcelSheets" :key="s" :label="s" :value="s" />
            </el-select>
            <el-tag v-if="wholeExcelTemplateName" size="small" type="info">{{ wholeExcelTemplateName }}</el-tag>
          </div>
          <div v-if="wholeExcelGridLoading" class="gt-wp-renderer__whole-excel-loading">
            <el-skeleton :rows="6" animated />
          </div>
          <GtGridSheet
            v-else
            :wp-id="wpId"
            :sheet-name="wholeExcelActiveSheet || activeSheetName"
            :schema="activeSheetSchema"
            :html-data="wholeExcelGridData"
            :readonly="true"
          />
        </div>
        <GtGridSheet
          v-else
          :wp-id="wpId"
          :sheet-name="activeSheetName"
          :schema="activeSheetSchema"
          :html-data="activeSheetHtmlData"
          :readonly="true"
        />
      </template>

      <!-- Univer 占位（无模板网格数据时） -->
      <div v-else-if="componentType === 'univer'" class="gt-wp-renderer__univer-placeholder">
        <el-result icon="info" title="表格底稿">
          <template #sub-title>
            <span>此底稿为表格类型，数据尚未导入。请先在项目中导入账套数据，系统将自动填充。</span>
          </template>
        </el-result>
      </div>

      <!-- Skip 占位 -->
      <SkippedSheetPlaceholder
        v-else-if="componentType === 'skip'"
        :sheet-name="activeSheetName"
      />

      <!-- 未知 componentType fallback（不应出现） -->
      <div v-else class="gt-wp-renderer__unknown-placeholder">
        <el-result icon="info" :title="`组件类型: ${componentType}`">
          <template #sub-title>
            <span>该底稿类型尚未支持渲染，将在后续版本中实现。</span>
          </template>
        </el-result>
      </div>
      </div><!-- /.gt-wp-renderer__content -->
      </template><!-- v-else (non-redirect) -->
    </template>

    <!-- 无布局 Runtime Hosts：统一承载当前底稿的真实复核对话与版本历史。 -->
    <GtWorkpaperRuntimeHosts
      :wp-id="wpId"
      :project-id="runtimeProjectId"
      @rollback-completed="reload"
    />

    <!-- 本底稿关联附件抽屉（工具栏「关联附件」打开；可编辑时支持解除关联）。 -->
    <WorkpaperAttachmentsDrawer
      v-model="attachmentsDrawerVisible"
      :wp-id="wpId"
      :project-id="renderConfig?.project_id ?? runtimeProjectId ?? ''"
      :wp-code="renderConfig?.wp_code ?? ''"
      :can-edit="!readonly"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Switch } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { useWpRenderer, type WpComponentType } from '@/composables/useWpRenderer'
import { useCellLocate, type LocateTarget } from '@/composables/useCellLocate'
import { eventBus, type WorkpaperLocateCellPayload } from '@/utils/eventBus'
import GtLoadingOverlay from '@/components/common/GtLoadingOverlay.vue'
import {
  getRendererEntry,
  getSheetIcon as registryGetSheetIcon,
  getContextPropsStrategy,
} from '@/components/workpaper/htmlRendererRegistry'
import {
  isCycleDelegatedIndexSheet,
  resolveCycleIndexComponentType,
} from '@/components/workpaper/composables/gCycleIndexRouting'

// ─── Sub-components (placeholder fallback) ───
// HTML 类型路由由 htmlRendererRegistry 管理（lazy load 自动）
// 仅 SkippedSheetPlaceholder 不在 registry 内（特殊占位）
import SkippedSheetPlaceholder from '@/components/workpaper/SkippedSheetPlaceholder.vue'
import GtGridSheet from '@/components/workpaper/GtGridSheet.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtWpToolbar from '@/components/workpaper/GtWpToolbar.vue'
import WorkpaperAttachmentsDrawer from '@/components/workpaper/WorkpaperAttachmentsDrawer.vue'
import GtWpAiReviewToolbar from './review/GtWpAiReviewToolbar.vue'
import GtWpDisclosureSyncBar from './GtWpDisclosureSyncBar.vue'
import { isDisclosureSheetName } from './composables/disclosureSyncBar'
import GtWpPreparationHeader from '@/components/workpaper/GtWpPreparationHeader.vue'
import GtWorkpaperRuntimeHosts from '@/components/workpaper/GtWorkpaperRuntimeHosts.vue'
import GtBArchitectureTree from '@/components/workpaper/GtBArchitectureTree.vue'
import { useProjectStore } from '@/stores/project'
import { subscribeInvalidation } from '@/services/acnr'
import { resolveEffectiveAuditYear } from '@/utils/resolveAuditYear'
import { normalizeSheetName, resolveSheetNameByDeepLink } from '@/utils/normalizeSheetName'
import { useWorkpaperScaffold } from '@/components/workpaper/composables/useWorkpaperScaffold'

// ─── Types ───
export interface SavePayload {
  sheet_name: string
  html_data: Record<string, any>
  schema_version?: string
}

export interface CrossRefPayload {
  source_wp_code: string
  target_wp_code: string
  cell: string
  old_value?: any
  new_value?: any
}

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  initialSheet?: string
  initialCell?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  'sheet-change': [sheetName: string]
  'cell-focus': [payload: { sheet: string; cell: string }]
  'save-success': [payload: SavePayload]
  /** 子组件自行持久化后的纯通知（无 html_data），外层仅刷新不再 POST /save */
  'saved-notify': []
  'cross-ref-update': [payload: CrossRefPayload]
  'trigger-procedure-trimming-suggestion': [payload: Record<string, any>]
  'conclusion-change': [conclusion: string]
  'step-advance': [step: number]
  'subtable-toggle': [subTableId: string]
  'standard-switch': [standard: string]
  'sync-to-disclosure-notes': [payload: Record<string, any>]
  'jump-to-reference': [refCode: string]
  'open-attachment': [payload: { wpId: string; sheetName: string; rowRef: string }]
  /** 审定表（audit-sheet）公式按钮 → 转发给上层（后续接 FormulaEditDialog） */
  'open-formula': [payload: { wpId: string; sheetName: string }]
}>()

// ─── Refs ───
const route = useRoute()
const router = useRouter()
const containerRef = ref<HTMLElement | null>(null)
const loadingHint = ref('')
// 内部维护 activeSheetName（支持 sheet 切换）
const internalActiveSheetName = ref<string>('')
// 「切换底稿」弹出树的可见状态
const switchPopoverVisible = ref(false)
// 完整 Excel 合成页签标识（OnlyOffice 整本编辑，放在底稿目录右侧）
const WHOLE_EXCEL_TAB = '__whole_excel__'
/** F1 函证程序：HTML 虚拟 sheet（无 xlsx 页，由 GtF1Prepayment 渲染） */
const F1_CONFIRM_SHEET = '函证程序F1-CONF'
// 统一工具栏状态
const isWpFullscreen = ref(false)
// 「本底稿关联附件」抽屉
const attachmentsDrawerVisible = ref(false)
// 子组件引用（用于转发工具栏操作）
const activeComponentRef = ref<any>(null)
// OnlyOffice 降级状态（当 GtOnlyOfficeSheet emit fallback 时切换到 GtGridSheet）
const onlyOfficeFallback = ref(false)
/** 完整Excel 降级：从整册模板抽取的网格 */
const wholeExcelGridLoading = ref(false)
const wholeExcelGridData = ref<Record<string, any>>({})
const wholeExcelSheets = ref<string[]>([])
const wholeExcelActiveSheet = ref('')
const wholeExcelTemplateName = ref('')

// ─── Composables ───
const wpIdRef = toRef(props, 'wpId')
const { renderConfig, loading, error, reload } = useWpRenderer(wpIdRef)

// Sprint 4 Task 10.1: schema 缺失智能提示
const schemaFallbackBanner = computed(() => {
  if (!renderConfig.value) return null
  const cls = renderConfig.value.wp_code
  if (cls && /^[A-E]/i.test(cls) && componentType.value === 'univer') {
    return '此底稿推荐使用 HTML 渲染器，当前因配置未就绪暂用表格模式'
  }
  return null
})

// ─── B15/合并类重定向 ─────────────────────────────────────────────────────
const MODULE_LABELS: Record<string, string> = {
  materiality: '重要性水平',
  consolidation_hub: '合并模块',
}
const redirectModuleLabel = computed(() => {
  const mod = renderConfig.value?.delegated_module || ''
  return MODULE_LABELS[mod] || mod || '目标模块'
})
const redirectHint = computed(() => {
  const mod = renderConfig.value?.delegated_module
  if (mod === 'materiality') return '重要性水平（B15）由独立的 Materiality 模块管理，点击下方按钮前往。'
  if (mod === 'consolidation_hub') return '此底稿由合并模块承载，请前往合并模块查看。'
  return '此底稿由其他模块承载。'
})
function handleRedirectNavigation() {
  const targetPath = renderConfig.value?.target_path
  const projectId = renderConfig.value?.project_id
  if (targetPath) {
    // target_path may already contain full route (e.g. /projects/{id}/confirmation)
    // or relative path (e.g. /materiality) needing project prefix
    if (targetPath.startsWith('/projects/')) {
      router.push(targetPath)
    } else if (projectId) {
      router.push(`/projects/${projectId}${targetPath}`)
    } else {
      router.push(targetPath)
    }
  } else {
    router.back()
  }
}

// ─── Computed ───
/** render-config sheets + 科目级 HTML 虚拟页（如 F1-CONF） */
const augmentedSheets = computed(() => {
  const sheets = [...(renderConfig.value?.sheets ?? [])]
  const rootCt = String(
    renderConfig.value?.component_type ?? renderConfig.value?.componentType ?? '',
  )
  const wpCode = String(renderConfig.value?.wp_code ?? '')
  const isF1Prepayment =
    rootCt === 'f1-prepayment'
    || sheets.some((s) => String(s.componentType ?? (s as any).component_type) === 'f1-prepayment')
    || wpCode === 'F1'
    || wpCode.startsWith('F1-')
  if (
    isF1Prepayment
    && !sheets.some((s) => /F1-CONF|函证程序/i.test(String(s.sheet_name || '')))
  ) {
    sheets.push({
      sheet_name: F1_CONFIRM_SHEET,
      componentType: 'f1-prepayment',
      schema: null,
      html_data: { virtual: true, confirmation_procedure: true },
      cross_refs: [],
    } as (typeof sheets)[number])
  }
  return sheets
})

/** 可见 sheet 列表（过滤掉 skip 类，但 skip 仍可在唯一 sheet 时显示） */
const visibleSheets = computed(() => {
  const sheets = augmentedSheets.value
  // 全部 skip 时仍展示一个；否则过滤 skip
  const nonSkip = sheets.filter(s => s.componentType !== 'skip')
  return nonSkip.length > 0 ? nonSkip : sheets
})

const activeSheetName = computed<string>({
  get() {
    const sheets = augmentedSheets.value
    if (!sheets.length) return ''
    // 优先用内部 ref（用户切换过）
    if (internalActiveSheetName.value) {
      // 完整Excel 合成页签：直接放行（不在 renderConfig.sheets 中）
      if (internalActiveSheetName.value === WHOLE_EXCEL_TAB) return WHOLE_EXCEL_TAB
      const exists = sheets.find(s => s.sheet_name === internalActiveSheetName.value)
      if (exists) return internalActiveSheetName.value
    }
    // 否则匹配 initialSheet（三级匹配的单一真源 = resolveSheetNameByDeepLink）
    if (props.initialSheet) {
      const hit = resolveSheetNameByDeepLink(
        sheets.map(s => s.sheet_name),
        props.initialSheet,
      )
      if (hit) return hit
    }
    // 兜底：第一个非 skip 的 sheet
    return visibleSheets.value[0]?.sheet_name ?? sheets[0].sheet_name
  },
  set(name: string) {
    internalActiveSheetName.value = name
    onlyOfficeFallback.value = false  // 切换 sheet 时重置 OnlyOffice 降级状态
    wholeExcelGridData.value = {}
    wholeExcelSheets.value = []
    wholeExcelActiveSheet.value = ''
    wholeExcelTemplateName.value = ''
    emit('sheet-change', name)
  },
})

const activeSheet = computed(() => {
  const sheets = augmentedSheets.value
  if (!sheets.length) return null
  return sheets.find(s => s.sheet_name === activeSheetName.value) ?? null
})

// ─── 完整 Excel 页签（OnlyOffice 整本编辑，放在底稿目录右侧）───
// 合成页签：所有多 sheet 底稿在「底稿目录」右侧注入一个「完整Excel」页签，
// 用 OnlyOffice 打开整本 xlsx 供组员直接编辑（原生显示全部 sheet tab）。
// 其余 HTML 页签保持现状，后续精细打磨。

/** 页签列表：在第一个页签（通常是底稿目录）右侧插入「完整Excel」合成页签 */
const tabSheets = computed(() => {
  const sheets = visibleSheets.value
  if (sheets.length <= 1) return sheets
  const wholeExcelTab = {
    sheet_name: WHOLE_EXCEL_TAB,
    componentType: 'onlyoffice-sheet' as WpComponentType,
    schema: null,
    html_data: { onlyoffice: true, whole_workbook: true, sheet_name: WHOLE_EXCEL_TAB },
    cross_refs: [],
  }
  // 底稿目录通常是第一个 → 插在其右侧；否则插在最前。
  // 除 b-index 外，也认 sheet 名含「底稿目录」（G 循环偶发被专属组件 override 时仍保持页签顺序）
  const first = sheets[0]
  const firstIsIndex =
    first?.componentType === 'b-index'
    || (!!first?.sheet_name && first.sheet_name.includes('底稿目录'))
  if (firstIsIndex) {
    return [sheets[0], wholeExcelTab, ...sheets.slice(1)]
  }
  return [wholeExcelTab, ...sheets]
})

/** 当前是否为「完整Excel」合成页签 */
const isWholeExcelTab = computed<boolean>(() => activeSheetName.value === WHOLE_EXCEL_TAB)

/**
 * 当前 sheet 是否为「附注披露表」（P0-2 同步状态条判据）。
 * 各循环 sheet 命名不统一：附注披露信息（上市公司）/ 附注上市 / 附注国企 /
 * F1-note-listed / G2-note-soe 等，故用宽正则；命中后由后端 registry 决定是否有映射。
 */
const isDisclosureSheet = computed<boolean>(() =>
  isDisclosureSheetName(activeSheetName.value),
)

/** 是否为底稿目录页签（b-index 或 sheet 名含「底稿目录」；对齐后端 whole-excel 优先跳过目录） */
function isIndexSheetTab(s: { sheet_name?: string; componentType?: string } | null | undefined): boolean {
  if (!s) return false
  if (s.componentType === 'b-index') return true
  return !!(s.sheet_name && s.sheet_name.includes('底稿目录'))
}

/** 完整Excel 模式下传给 config 端点的 sheet_name（用首个真实业务 sheet，仅用于满足 URL 路径，
 *  实际 OnlyOffice 打开整本 xlsx 显示全部 tab；whole_workbook=true 时后端不加 actionLink）。
 *  必须跳过「底稿目录」：G 循环目录偶发仍挂在专属 Host 上，误传会导致 OO config/WOPI 失败并降级。 */
const wholeWorkbookSheetName = computed<string>(() => {
  const real = visibleSheets.value.find(
    (s) => s.sheet_name !== WHOLE_EXCEL_TAB && !isIndexSheetTab(s),
  )
  return real?.sheet_name
    ?? visibleSheets.value.find((s) => s.sheet_name !== WHOLE_EXCEL_TAB)?.sheet_name
    ?? ''
})

const activeSheetSchema = computed(() => activeSheet.value?.schema ?? {})
const activeSheetHtmlData = computed<any>(() => activeSheet.value?.html_data ?? {})

/**
 * 当前 sheet 的索引号（sheet 级，传给编制信息表头右上角）。
 * 从 sheet_name 末尾正则提取真实索引（如「应收票据审计程序表D1A」→ D1A、
 * 「审定表D1-1」→ D1-1），与后端 _generate_b_index_data 的 sheet 级提取口径一致；
 * 提取不到时回退 workpaper 级 wp_code（renderConfig.wp_code）。
 */
const activeSheetIndexNo = computed<string>(() => {
  const name = activeSheetName.value || ''
  const m = name.match(/([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$/)
  if (m) return m[1]
  return renderConfig.value?.wp_code ?? ''
})
/** univer 类底稿：html_data 是否含可渲染网格 cells（决定走只读网格还是占位） */
const hasGridCells = computed<boolean>(() => {
  const hd = activeSheetHtmlData.value
  return !!hd && typeof hd === 'object' && hd.cells && Object.keys(hd.cells).length > 0
})
/** 当前 sheet 的 componentType（每个 sheet 独立路由） */
const componentType = computed<WpComponentType>(() => {
  if (isWholeExcelTab.value) return 'onlyoffice-sheet' as WpComponentType
  return (activeSheet.value?.componentType as WpComponentType) ?? 'skip'
})

/** G12/G13/G14 底稿目录 Tab：b-index → 循环 HTML 目录（D4TabIndex 同级） */
const isCycleDelegatedIndex = computed(() =>
  isCycleDelegatedIndexSheet(componentType.value, renderConfig.value?.wp_code ?? ''),
)

const effectiveRendererComponentType = computed<WpComponentType>(() =>
  resolveCycleIndexComponentType(componentType.value, renderConfig.value?.wp_code ?? '') as WpComponentType,
)

const showWorkpaperPreparationHeader = computed(
  () =>
    (componentType.value !== 'b-index' && componentType.value !== 'a1-dashboard')
    || isCycleDelegatedIndex.value,
)

/**
 * C-附注披露无 schema 的只读网格兜底判定。
 * GtCNoteTable 是 schema 驱动；当某附注披露 sheet 无配套 schema.sub_tables 时，
 * 后端会回退提取模板网格（html_data.cells），此时改用 GtGridSheet 只读还原模板外观，
 * 避免 GtCNoteTable 永远显示「附注披露表尚未配置」空态。
 */
const cNoteGridFallback = computed<boolean>(() => {
  if (componentType.value !== 'c-note-table') return false
  const schema = activeSheetSchema.value as any
  const hasSubTables = !!schema && Array.isArray(schema.sub_tables) && schema.sub_tables.length > 0
  return !hasSubTables && hasGridCells.value
})

/**
 * OnlyOffice sheet 判定：html_data.onlyoffice === true 时路由到 GtOnlyOfficeSheet。
 * 若 componentType 已注册 HTML 专属组件（如 d1-notes-receivable），优先结构化视图，
 * 避免历史 onlyoffice 标记或后端误判导致跳过双模式入口。
 */
const isOnlyOfficeSheet = computed<boolean>(() => {
  if (isWholeExcelTab.value) return true
  if (getRendererEntry(effectiveRendererComponentType.value)) return false
  const hd = activeSheetHtmlData.value as any
  return hd?.onlyoffice === true
})

/**
 * 有注册表组件但 html_data 是 grid 格式（非组件期望结构）时的兜底判定。
 * 后端 grid 兜底路径（多 sheet 底稿无 renderer 时从模板提取 cells）产出 grid 数据，
 * 但前端组件（如 GtDForm）期望结构化数据（rows/context 等）。
 * 当 html_data 含 cells 字段 → 直接用 GtGridSheet 渲染，跳过注册表组件。
 */
const noRendererGridFallback = computed<boolean>(() => {
  if (componentType.value === 'univer' || componentType.value === 'c-note-table') return false
  if (componentType.value === 'skip') return false
  // confirmation-* 精细组件（协作者 D0 函证模块）接收 grid cells 作为数据源，不走 grid 兜底
  if (componentType.value.startsWith('confirmation-')) return false
  // html_data 含 cells（grid 格式）→ 优先走 GtGridSheet，无论注册表有无组件
  if (hasGridCells.value) {
    const hd = activeSheetHtmlData.value as any
    // 确认是纯 grid 数据（不含组件期望的结构化字段）
    const isGridOnly = hd && hd.cells && !hd.rows && !hd.programs && !hd.audit_rows
    if (isGridOnly) return true
  }
  // 无注册表组件 → 走兜底
  const entry = getRendererEntry(effectiveRendererComponentType.value)
  if (entry) return false
  return hasGridCells.value
})

/** 注册表查找：HTML 类型 → component + emit 列表（lazy import）。
 *  C-附注披露走网格兜底时不用注册表组件（GtCNoteTable），改由 GtGridSheet 渲染。
 *  OnlyOffice sheet 不走注册表（走 GtOnlyOfficeSheet）。 */
const rendererEntry = computed(() =>
  cNoteGridFallback.value || noRendererGridFallback.value || (isOnlyOfficeSheet.value && !onlyOfficeFallback.value)
    ? undefined
    : getRendererEntry(effectiveRendererComponentType.value),
)

/**
 * HTML 渲染器 key：同 componentType 下切换 sheet（如 F2-21→F2-22 同属 f2-stocktake-bundle）
 * 必须强制重建，否则内部 activeTab 等状态会卡住，表现为「点页签没反应」。
 */
const htmlRendererKey = computed(() => {
  const ct = effectiveRendererComponentType.value
  // 同 componentType 多 sheet 需带 sheet，避免内部状态卡住 / 双层 tabs 错位 / OO 串页
  if (
    ct === 'f2-stocktake-bundle'
    || ct === 'f1-prepayment'
    || ct === 'g1-trading-financial-assets'
    || ct === 'g2-interest-receivable'
    || ct === 'd4-operating-revenue'
  ) {
    return `${ct}::${activeSheetName.value}`
  }
  // 其余 HTML 组件按类型复用即可，减少无谓重建与重复请求
  return ct
})

/** D 子模式需要 form-type prop；custom 需要项目上下文 */
const extraComponentProps = computed<Record<string, unknown>>(() => {
  const ct = effectiveRendererComponentType.value
  const strategy = getContextPropsStrategy(ct)

  switch (strategy) {
    case 'form-type':
      return { 'form-type': ct }
    case 'custom':
      return {
        'wp-generated': renderConfig.value?.is_real_workpaper ?? true,
        'project-id': renderConfig.value?.project_id ?? '',
        'wp-code': renderConfig.value?.wp_code ?? '',
        year: preparationYear.value,
      }
    case 'standard':
      return {
        'wp-id': props.wpId ?? '',
        'project-id': renderConfig.value?.project_id ?? '',
        'wp-code': renderConfig.value?.wp_code ?? '',
        year: preparationYear.value,
      }
    case 'none':
    default:
      return {}
  }
})

/** 公式校验/注册表用年度：render-config > 路由 > 项目 store > 通用兜底 */
const preparationYear = computed(() => {
  try {
    const store = useProjectStore()
    return resolveEffectiveAuditYear({
      configYear: renderConfig.value?.audit_year,
      routeYear: route.query.year,
      storeAuditYear: store.auditYear,
      storeYear: store.year,
    })
  } catch {
    return resolveEffectiveAuditYear({
      configYear: renderConfig.value?.audit_year,
      routeYear: route.query.year,
    })
  }
})

// ─── Runtime Boundary ──────────────────────────────────────────────────────────
// Scaffold 在本 Renderer 实例的 setup 中仅初始化一次；直接传入 computed/ref，
// 使 render-config 与 props 更新贯穿运行时，同时不引入额外 toolbar 或布局容器。
const runtimeProjectId = computed(() => renderConfig.value?.project_id ?? '')
const runtimeWpCode = computed(() => renderConfig.value?.wp_code ?? '')
const runtimeContextReady = computed(() => !loading.value && (!!renderConfig.value || !!error.value))
// 适用准则：后端 wp_render_config Step 9.5 在响应顶层统一注入（逐 sheet 的
// html_data.project_context 同值）。交给 scaffold provide，宿主经
// useHostApplicableStandards 取用，不再各写一份取值链。
const runtimeApplicableStandards = computed<unknown>(
  () => (renderConfig.value as any)?.applicable_standards,
)
const runtime = useWorkpaperScaffold({
  wpId: wpIdRef,
  projectId: runtimeProjectId,
  wpCode: runtimeWpCode,
  year: preparationYear,
  readonly: toRef(props, 'readonly'),
  onJumpToSection: onChildNavigateSheet,
  reloadFn: reload,
  contextReady: runtimeContextReady,
  applicableStandards: runtimeApplicableStandards,
})

// 外层编辑器的版本按钮委托给 Runtime Boundary，避免同一 HTML 底稿挂载第二个版本 Host。
defineExpose({ openVersionHistory: runtime.version.openVersionHistory })

/** componentType → 图标（sheet tab 显示），委托给 registry */
function getSheetIcon(ct: string): string {
  return registryGetSheetIcon(ct)
}

// ─── wp-locate-foundation Task 3.1: 监听 workpaper:locate-cell 事件 ───
const { locateCell } = useCellLocate()

function onLocateCell(payload: WorkpaperLocateCellPayload) {
  // 仅处理当前底稿的定位事件
  if (payload.wpId !== props.wpId) return
  // 如果渲染配置未就绪，忽略
  if (!renderConfig.value) return

  const targetSheet = payload.sheetName
  const sheets = renderConfig.value.sheets ?? []
  const sheetExists = targetSheet
    ? sheets.some(s => s.sheet_name === targetSheet)
    : false
  const needSwitchSheet = targetSheet && sheetExists && targetSheet !== activeSheetName.value

  // 构建 LocateTarget
  const target: LocateTarget = {
    wp_code: payload.wpCode || '',
    wp_id: payload.wpId,
    sheet_name: targetSheet || activeSheetName.value,
    cell_ref: payload.cellRef || null,
    component_type: payload.componentType || componentType.value || null,
    value: payload.value || null,
    label: payload.label || null,
  }

  if (needSwitchSheet) {
    // 切换 sheet，等 DOM 更新后再定位
    activeSheetName.value = targetSheet!
    nextTick(() => {
      const success = locateCell(target)
      if (!success) {
        // cell 级定位失败，但 sheet 切换已成功（sheet 级降级）
        ElMessage.info('已切换到目标 sheet，但未能精确定位到目标位置')
      }
    })
  } else if (targetSheet && !sheetExists) {
    // 目标 sheet 不存在，sheet 级也失败
    ElMessage.info('已打开底稿但未能定位到目标位置（可能已变更）')
  } else {
    // 同 sheet，直接定位
    nextTick(() => {
      const success = locateCell(target)
      if (!success) {
        // cell 级定位失败，无 sheet 切换可降级
        ElMessage.info('已打开底稿但未能定位到目标位置（可能已变更）')
      }
    })
  }
}

onMounted(() => {
  eventBus.on('workpaper:locate-cell', onLocateCell)
})

// ACNR 项目级 SSE 实时失效订阅（acnr-invalidation-overlay-hardening R1）：
// 单点订阅（workpaper 渲染外壳，每项目一连接，引用计数复用），项目切换时重订阅。
let _acnrUnsub: (() => void) | null = null

watch(
  () => renderConfig.value?.project_id,
  (pid) => {
    // ACNR SSE 订阅生命周期管理（项目变化 → 释放旧连接 + 建新连接）
    if (_acnrUnsub) {
      _acnrUnsub()
      _acnrUnsub = null
    }
    if (pid) {
      _acnrUnsub = subscribeInvalidation(pid)
    }

    if (!pid) return
    try {
      const store = useProjectStore()
      if (pid !== store.projectId) {
        void store.loadProjectContext(pid)
      }
    } catch { /* no pinia in isolated tests */ }
  },
  { immediate: true },
)

onUnmounted(() => {
  eventBus.off('workpaper:locate-cell', onLocateCell)
  if (_acnrUnsub) {
    _acnrUnsub()
    _acnrUnsub = null
  }
})

const errorTitle = computed(() => {
  if (!error.value) return ''
  return '加载渲染配置失败'
})

const errorSubTitle = computed(() => {
  if (!error.value) return ''
  return error.value.message || '请检查网络连接后重试'
})

// ─── Methods ───

// OnlyOffice 降级回调：GtOnlyOfficeSheet emit('fallback') 时切换到 GtGridSheet
function onOnlyOfficeFallback() {
  onlyOfficeFallback.value = true
  // 完整Excel：从整册模板（如 G1.xlsx）拉取网格，避免空态
  if (activeSheetName.value === WHOLE_EXCEL_TAB) {
    void loadWholeExcelGrid()
  }
}

/** 从整册 Excel 模板抽取只读网格（OO 降级兜底，对齐 D4/G1 模板拉取） */
async function loadWholeExcelGrid(sheet?: string) {
  if (!props.wpId) return
  wholeExcelGridLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (sheet) params.sheet = sheet
    const resp = await http.get(`/api/workpapers/${props.wpId}/whole-excel-grid`, {
      params,
      _silent: true,
    } as any)
    const data = resp.data?.data ?? resp.data ?? {}
    wholeExcelSheets.value = Array.isArray(data.sheets) ? data.sheets : []
    wholeExcelActiveSheet.value = data.active_sheet || sheet || ''
    wholeExcelTemplateName.value = data.template_name || ''
    wholeExcelGridData.value = data.html_data && typeof data.html_data === 'object'
      ? data.html_data
      : {}
    if (!wholeExcelGridData.value?.cells || !Object.keys(wholeExcelGridData.value.cells).length) {
      ElMessage.warning('整册 Excel 模板暂无可用网格内容，可点「导出模板」下载原文件')
    }
  } catch (e: any) {
    wholeExcelGridData.value = {}
    ElMessage.error('拉取整册 Excel 失败：' + (e?.response?.data?.detail || e?.message || '请稍后重试'))
  } finally {
    wholeExcelGridLoading.value = false
  }
}

// 统一工具栏操作
async function onExportTemplate() {
  if (!props.wpId) return
  try {
    const resp = await http.get(`/api/workpapers/${props.wpId}/export-template`, {
      responseType: 'blob',
      _silent: true,
    } as any)
    // 从 response headers 或默认文件名
    const contentDisposition = resp.headers?.['content-disposition'] || ''
    const filenameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i)
    const filename = filenameMatch
      ? decodeURIComponent(filenameMatch[1])
      : `${renderConfig.value?.wp_code || 'workpaper'}_模板.xlsx`
    // 创建下载链接
    const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error('导出模板失败：' + (e?.response?.data?.message || e?.message || '请检查网络'))
  }
}
function onExportData() {
  // 如果子组件暴露了 handleExportData 方法，委托给它
  const child = activeComponentRef.value
  if (child && typeof child.handleExportData === 'function') {
    child.handleExportData()
  } else {
    ElMessage.info('当前底稿暂不支持导出数据')
  }
}
function onImportData() {
  // 如果子组件暴露了 handleImportClick / handleImport 方法，委托给它
  const child = activeComponentRef.value
  if (child && typeof child.handleImportClick === 'function') {
    child.handleImportClick()
  } else if (child && typeof child.handleImport === 'function') {
    child.handleImport()
  } else {
    ElMessage.info('当前底稿暂不支持导入')
  }
}
function onAddRow() {
  ElMessage.info('增行功能开发中')
}

function onSave(data: Record<string, any>) {
  // 防御：部分子组件（如 WpPopupSigning）自行持久化（PUT checklist-responses），
  // 其 emit('save') 不带 payload，仅作"已保存"通知。此时 data 为 undefined/空，
  // 不应构造缺 html_data 的 save-success（否则外层 POST /save 触发 422）。
  // 仅当子组件确实传回 html_data 时才走外层 parsed_data 持久化通道。
  if (data == null || typeof data !== 'object' || Array.isArray(data)) {
    emit('saved-notify')
    return
  }
  const payload: SavePayload = {
    sheet_name: activeSheetName.value,
    html_data: data,
    schema_version: renderConfig.value?.template_version || 'v2025-R5',
  }
  emit('save-success', payload)
}

function onTrimmingSuggestion(payload: Record<string, any>) {
  emit('trigger-procedure-trimming-suggestion', payload)
}

function onConclusionChange(conclusion: string) {
  emit('conclusion-change', conclusion)
}

function onStepAdvance(step: number) {
  emit('step-advance', step)
}

function onSubtableToggle(subTableId: string) {
  emit('subtable-toggle', subTableId)
}

function onStandardSwitch(standard: string) {
  emit('standard-switch', standard)
}

function onSyncToDisclosureNotes(payload: Record<string, any>) {
  emit('sync-to-disclosure-notes', payload)
}

function onJumpToReference(refCode: string) {
  emit('jump-to-reference', refCode)
}

function onJumpToSection(sheetName: string) {
  // B-Index 架构图节点点击 → 切换到对应 sheet（同底稿内 sheet 切换）
  if (!sheetName || !renderConfig.value) return
  const hit = resolveSheetNameByDeepLink(
    (renderConfig.value.sheets ?? []).map(s => s.sheet_name),
    sheetName,
  )
  if (hit) {
    activeSheetName.value = hit
  } else {
    ElMessage.info('未找到对应底稿 sheet')
  }
}

/**
 * 「切换底稿」弹出树的数据源：从 visibleSheets 直接构造 navigation_rows
 * （排除底稿目录 b-index 自身），供 GtBArchitectureTree 按 4 阶段分组。
 * 不依赖 b-index sheet 的持久化 html_data，确保任意 sheet 下都可切换。
 */
const switchTreeHtmlData = computed(() => ({
  navigation_rows: visibleSheets.value
    .filter((s) => !isIndexSheetTab(s))
    .map((s, i) => {
      const name = s.sheet_name || ''
      const m = name.match(/([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$/)
      return {
        seq: i + 1,
        content: name,
        sheet_name: name,
        index_ref: m ? m[1] : (renderConfig.value?.wp_code ?? ''),
        component_type: s.componentType || 'skip',
        no_print: false,
      }
    }),
}))

/** 切换底稿树节点点击 → 跳转 sheet + 关闭弹窗 */
function onSwitchNavigate(sheetName: string) {
  onJumpToSection(sheetName)
  switchPopoverVisible.value = false
}

/** 子组件 emit navigate-sheet → 切换当前 active tab 到目标 sheet */
function onChildNavigateSheet(sheetName: string) {
  if (!sheetName) return
  const hit = resolveSheetNameByDeepLink(
    (renderConfig.value?.sheets ?? []).map(s => s.sheet_name),
    sheetName,
  )
  if (hit) {
    activeSheetName.value = hit
  } else {
    ElMessage.info(`未找到 sheet「${sheetName}」`)
  }
}

function onOpenAttachment(payload: { wpId: string; sheetName: string; rowRef: string }) {
  emit('open-attachment', payload)
}

/**
 * 审定表公式按钮：子组件 emit('open-formula', { sheetName }) → 补全 wpId 转发上层。
 * 后续由 WorkpaperEditor 监听打开 FormulaEditDialog（当前仅冒泡，不在本任务范围）。
 */
function onOpenFormula(payload: { sheetName: string }) {
  emit('open-formula', { wpId: props.wpId, sheetName: payload?.sheetName ?? activeSheetName.value })
}
</script>

<style scoped>
.gt-wp-renderer {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
  display: flex;
  flex-direction: column;
}
.gt-wp-renderer--fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background: #fff;
  min-height: unset;
}

.gt-wp-renderer__sheet-tabs {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-page);
  padding: 4px 12px 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.gt-wp-renderer__switch-btn {
  flex: 0 0 auto;
  margin-top: 2px;
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}

.gt-wp-renderer__switch-icon {
  margin-right: 4px;
  vertical-align: -2px;
}

.gt-wp-renderer__sheet-tabs-inner {
  flex: 1 1 auto;
  min-width: 0;
}

.gt-wp-renderer__switch-tree {
  max-height: 60vh;
  overflow-y: auto;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__nav-wrap) {
  margin-bottom: 0;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__header) {
  margin-bottom: 0;
  border-bottom: 0;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__content) {
  display: none;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__item) {
  height: 36px;
  line-height: 36px;
  font-size: var(--wp-font-size, 13px);
}

.gt-wp-renderer__tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 240px;
}

.gt-wp-renderer__tab-icon {
  flex: 0 0 auto;
}

.gt-wp-renderer__tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-wp-renderer__content {
  flex: 1 1 auto;
  position: relative;
  overflow: auto;
}

.gt-wp-renderer__error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-bg-white, #fff);
  z-index: 99;
}

.gt-wp-renderer__univer-placeholder,
.gt-wp-renderer__unknown-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.gt-wp-renderer__fallback-banner {
  margin-bottom: 8px;
}

.gt-wp-renderer__whole-excel-fallback {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 300px;
}
.gt-wp-renderer__whole-excel-alert {
  margin: 0;
}
.gt-wp-renderer__whole-excel-sheets {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.gt-wp-renderer__whole-excel-loading {
  padding: 12px;
}
</style>

<!-- Sprint 4 Task 16.4: 自动刷数 cell 全局样式（子组件需要） -->
<style>
.gt-auto-fill-cell {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f0f9ff;
  border: 1px solid #bae0ff;
  color: #0958d9;
  font-size: var(--wp-font-size, 13px);
  font-variant-numeric: tabular-nums;
  cursor: help;
  transition: all 0.2s;
}

.gt-auto-fill-cell:hover {
  background: #e6f4ff;
  border-color: #91caff;
}

.gt-auto-fill-cell--unavailable {
  background: #fff2f0;
  border: 1px dashed #ff7875;
  color: #cf1322;
}

.gt-auto-fill-cell--unavailable:hover {
  background: #fff1f0;
  border-color: #ff4d4f;
}
</style>

