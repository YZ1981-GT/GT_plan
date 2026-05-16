<template>
  <!-- 路由分发：非 univer 类型使用对应子编辑器 -->
  <component
    v-if="componentType && componentType !== 'univer'"
    :is="editorComponent"
    :project-id="projectId"
    :wp-id="wpId"
    :wp-detail="wpDetail"
    @show-versions="onShowVersions"
    @toggle-panel="showSidePanel = !showSidePanel"
    @saved="onChildSaved"
  />

  <!-- 默认 Univer 编辑器（component_type='univer' 或未配置时） -->
  <div v-else class="gt-wp-editor gt-fade-in">
    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <!-- 顶部工具栏 -->
    <div class="gt-wp-editor-toolbar">
      <div class="gt-wp-editor-toolbar-left">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="(statusTagType(wpDetail.status)) || undefined" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
        <el-tag type="success" size="small" style="margin-left: 8px">Univer</el-tag>
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <span v-if="dirty" class="gt-dirty-indicator">● 有未保存的变更</span>
        <el-button size="small" @click="onSave" :loading="saving">💾 保存</el-button>
        <el-tooltip
          v-if="wpDetail && wpDetail.status === WP_STATUS.DRAFT && fineCheckFailCount > 0"
          placement="bottom"
          :content="`当前有 ${fineCheckFailCount} 项自检未通过，建议处理后再提交`"
        >
          <el-button
            size="small"
            type="warning"
            @click="onSubmitForReview"
            :loading="submitting"
            :disabled="dirty"
          >⚠️ 提交复核（{{ fineCheckFailCount }} 项待处理）</el-button>
        </el-tooltip>
        <el-button
          v-else-if="wpDetail && wpDetail.status === WP_STATUS.DRAFT"
          size="small"
          type="primary"
          @click="onSubmitForReview"
          :loading="submitting"
          :disabled="dirty"
        >📨 提交复核</el-button>
        <el-button size="small" @click="onSyncStructure" :loading="syncLoading">🔄 同步公式</el-button>
        <el-button size="small" @click="onRefreshPrefill" :loading="prefillLoading" title="从试算表重新取数填入底稿">📊 刷新取数</el-button>
        <el-button size="small" @click="onShowVersions">📋 版本历史</el-button>
        <el-button size="small" @click="onDownload">📥 下载</el-button>
        <el-button size="small" @click="onExportPdf" :loading="exportingPdf" v-permission="'workpaper:export'">📄 导出 PDF</el-button>
        <el-button size="small" @click="onUpload">📤 上传</el-button>
        <el-badge :value="fineCheckFailCount" :max="99" :hidden="fineCheckFailCount === 0" type="danger">
          <el-button size="small" @click="showSidePanel = !showSidePanel">📋 面板</el-button>
        </el-badge>
      </div>
    </div>

    <!-- 版本历史抽屉（任务 8.19.1） -->
    <el-drawer
      v-model="showVersionDrawer"
      title="版本历史"
      direction="rtl"
      size="360px"
    >
      <div v-loading="versionLoading">
        <el-empty v-if="!versionLoading && versionList.length === 0" description="暂无历史版本" />
        <el-timeline v-else>
          <el-timeline-item
            v-for="v in versionList"
            :key="v.version || v.id"
            :timestamp="v.created_at ? v.created_at.slice(0, 19) : ''"
            placement="top"
          >
            <div style="font-weight: 600">v{{ v.version ?? v.file_version ?? '—' }}</div>
            <div v-if="v.note || v.description" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-top: 4px">
              {{ v.note || v.description }}
            </div>
            <div v-if="v.created_by_name || v.created_by" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px">
              {{ v.created_by_name || v.created_by }}
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>

    <!-- Univer 编辑区 -->
    <div class="gt-wp-editor-main">
      <div v-if="loading" class="gt-wp-editor-loading">
        <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
        <p>正在加载底稿...</p>
      </div>
      <div v-show="!loading" ref="univerContainer" class="gt-wp-editor-univer"></div>
    </div>

    <!-- 底部状态栏 -->
    <div class="gt-wp-editor-statusbar" v-if="wpDetail">
      <span>编制人: {{ resolveUserName(wpDetail.assigned_to) }}</span>
      <span>复核人: {{ resolveUserName(wpDetail.reviewer) }}</span>
      <span>版本: v{{ wpDetail.file_version || 1 }}</span>
      <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
      <span v-if="autoSaveMsg" style="color: var(--gt-color-success)">✓ {{ autoSaveMsg }}</span>
      <span v-if="dirty" style="color: var(--gt-color-wheat)">● 未保存</span>
      <span v-if="smartTip" class="gt-wp-smart-tip" @click="showSmartTipDetail = !showSmartTipDetail">
        💡 {{ smartTip.summary }}
      </span>
    </div>

    <!-- 智能提示详情 -->
    <div v-if="showSmartTipDetail && smartTip" class="gt-wp-smart-tip-detail">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;font-size: var(--gt-font-size-sm)">💡 审计关注点</span>
        <el-button size="small" text @click="showSmartTipDetail = false">收起</el-button>
      </div>
      <div v-if="smartTip.warnings?.length" style="margin-bottom:6px">
        <div v-for="(w, i) in smartTip.warnings" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); padding: 2px 0">⚠️ {{ w }}</div>
      </div>
      <div v-if="smartTip.tips?.length">
        <div v-for="(t, i) in smartTip.tips" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); padding: 1px 0">• {{ t }}</div>
      </div>
    </div>

    <!-- R7-S3-05 Task 25：底稿右栏面板（抽屉模式） -->
    <el-drawer
      v-model="showSidePanel"
      direction="rtl"
      size="400px"
      :with-header="false"
      :modal="false"
      append-to-body
    >
      <WorkpaperSidePanel
        :project-id="projectId"
        :wp-id="wpId"
        :wp-code="wpDetail?.wp_code"
        @finecheck-update="fineCheckFailCount = $event"
      />
    </el-drawer>
  </div>

  <!-- 非 Univer 编辑器的侧面板（共享） -->
  <el-drawer
    v-if="componentType && componentType !== 'univer'"
    v-model="showSidePanel"
    direction="rtl"
    size="400px"
    :with-header="false"
    :modal="false"
    append-to-body
  >
    <WorkpaperSidePanel
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail?.wp_code"
      @finecheck-update="fineCheckFailCount = $event"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmSubmitReview, confirmLeave, confirmVersionConflict } from '@/utils/confirm'
import { Loading } from '@element-plus/icons-vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
// @ts-ignore - locale file has no type declarations
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import {
  downloadWorkpaper,
  getWorkpaper,
  type WorkpaperDetail,
} from '@/services/workpaperApi'
import { rebuildWorkpaperStructure, listUsers } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { useWorkpaperReviewMarkers, type ReviewMarkerTicket } from '@/composables/useWorkpaperReviewMarkers'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import WorkpaperSidePanel from '@/components/workpaper/WorkpaperSidePanel.vue'
import { WP_STATUS } from '@/constants/statusEnum'
import { handleApiError } from '@/utils/errorHandler'

// ─── 动态编辑器组件（按 component_type 路由分发） ───────────────────────────

const WorkpaperFormEditor = defineAsyncComponent(() => import('./WorkpaperFormEditor.vue'))
const WorkpaperWordEditor = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))
const WorkpaperTableEditor = defineAsyncComponent(() => import('./WorkpaperTableEditor.vue'))
const WorkpaperHybridEditor = defineAsyncComponent(() => import('./WorkpaperHybridEditor.vue'))

const EDITOR_MAP: Record<string, any> = {
  form: WorkpaperFormEditor,
  word: WorkpaperWordEditor,
  table: WorkpaperTableEditor,
  hybrid: WorkpaperHybridEditor,
}
// ─────────────────────────────────────────────────────────────────────────────

const DIRTY_COMMAND_PATTERNS = [
  'set-range-values', 'set-cell',
  'set-formula', 'formula.', 'array-formula',
  'set-style', 'set-border', 'set-number-format', 'set-font',
  'clear-selection', 'delete-range',
  'insert-row', 'insert-col', 'remove-row', 'remove-col',
  'merge-cells', 'unmerge-cells',
]

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

// ─── component_type 路由逻辑 ─────────────────────────────────────────────────
const componentType = ref<string>('univer')
const editorComponent = computed(() => EDITOR_MAP[componentType.value] || null)

/** 从后端获取 component_type（wp_template_metadata 或底稿详情） */
async function fetchComponentType() {
  try {
    const detail = await httpApi.get(P_wp.detail(projectId.value, wpId.value))
    // component_type 可能来自 detail 本身或 template_metadata
    const ct = detail?.component_type || detail?.template_metadata?.component_type || 'univer'
    componentType.value = ct
    // 同时缓存 wpDetail 供子编辑器使用
    if (detail) wpDetail.value = detail
  } catch {
    componentType.value = 'univer'
  }
}

/** 子编辑器保存后的回调 */
function onChildSaved() {
  eventBus.emit('workpaper:saved', {
    projectId: projectId.value,
    wpId: wpId.value,
  } as WorkpaperSavedPayload)
}
// ─────────────────────────────────────────────────────────────────────────────

const editLock = useEditingLock({
  resourceId: computed(() => wpId.value || ''),
  // WorkpaperEditor 天然编辑模式，mount 时即 acquire
})

// R7-S2-05：统一自动保存（60s 间隔，合并原 30s UI 反馈 + 120s 后端保存）
const autoSave = useWorkpaperAutoSave(async () => {
  const ok = await onSave()
  if (!ok) {
    ElMessage.warning({ message: '自动保存失败，请手动保存', duration: 5000 })
  }
}, 60_000)

// UI 反馈：绑定 autoSave 状态
const autoSaveMsg = computed(() => {
  if (autoSave.saving.value) return '保存中...'
  if (autoSave.lastSavedAt.value) {
    const sec = Math.round((Date.now() - autoSave.lastSavedAt.value.getTime()) / 1000)
    if (sec < 5) return '已自动保存'
  }
  return ''
})

// R1 需求 2：底稿复核红点（任务 5）
const reviewMarkers = useWorkpaperReviewMarkers({
  projectId: () => projectId.value,
  wpId: () => wpId.value,
  onJumpToIssue: (ticket: ReviewMarkerTicket) => {
    // 跳转到项目问题单列表，高亮该工单
    router.push({
      name: 'IssueTicketList',
      params: { projectId: projectId.value },
      query: { highlight_id: ticket.id },
    })
  },
})

const wpDetail = ref<WorkpaperDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const submitting = ref(false)
const syncLoading = ref(false)
const prefillLoading = ref(false)
const dirty = ref(false)
const showSidePanel = ref(false)
// R8-S2-02：自检未通过项数（由 WorkpaperSidePanel @finecheck-update 同步）
const fineCheckFailCount = ref(0)
const univerContainer = ref<HTMLElement | null>(null)

// 任务 8.18.1：用户名映射（UUID → 显示名）
const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}

async function loadUserMap() {
  try {
    const users = await listUsers()
    userNameMap.value = new Map(
      (users || []).map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默：状态栏降级显示 UUID */ }
}

// 任务 8.19.1：版本历史
const showVersionDrawer = ref(false)
const versionList = ref<any[]>([])
const versionLoading = ref(false)

async function onShowVersions() {
  showVersionDrawer.value = true
  versionLoading.value = true
  try {
    const data = await httpApi.get(P_wp.versions(wpId.value), {
      validateStatus: (s: number) => s < 600,
    })
    versionList.value = Array.isArray(data) ? data : (data?.versions || data?.items || [])
  } catch (e: any) {
    versionList.value = []
    handleApiError(e, '加载版本历史')
  } finally {
    versionLoading.value = false
  }
}

// （旧 30s 自动保存已合并到 useWorkpaperAutoSave 60s 统一方案）

let univerInstance: any = null
let univerAPI: any = null

// 智能提示
const smartTip = ref<any>(null)
const showSmartTipDetail = ref(false)

// P0-2/P0-3: Track whether workpaper was loaded from xlsx (component scope for onSave access)
let loadedFromXlsx = false
// P2-2: 记录文件打开时间戳（用于 xlsx 保存冲突检测）
let fileOpenedAt = 0

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success', archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', archived: '已归档',
  }
  return m[s] || s
}

function goBack() {
  if (dirty.value) {
    if (!confirm('有未保存的修改，确定离开？')) return
  }
  router.push({ name: 'WorkpaperList', params: { projectId: projectId.value } })
}

async function initUniver() {
  if (!univerContainer.value) return

  // 1. 加载底稿详情
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch (e: any) {
    handleApiError(e, '底稿不存在')
    goBack()
    return
  }

  // 2. 优先尝试从 xlsx 模板文件加载（致同 2025 模板）
  let workbookData: any = null
  loadedFromXlsx = false
  try {
    const xlsxResp = await fetch(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file`,
      { headers: { Authorization: `Bearer ${sessionStorage.getItem('token') || localStorage.getItem('token') || ''}` } },
    )
    if (xlsxResp.ok && xlsxResp.headers.get('content-type')?.includes('spreadsheet')) {
      const blob = await xlsxResp.blob()
      if (blob.size > 100) {
        // 有 xlsx 模板文件，使用 importXLSX 加载
        loadedFromXlsx = true
        fileOpenedAt = Date.now() / 1000  // P2-2: 记录打开时间（秒级 Unix 时间戳）
        // Univer 需要先初始化再导入，标记后续处理
        workbookData = { _xlsxBlob: blob }
      }
    }
  } catch {
    // xlsx 端点不可用，降级到 JSON 模式
  }

  // 2b. 降级：从后端加载 Univer JSON 数据
  if (!loadedFromXlsx) {
    try {
      const data = await httpApi.get(
        P_wp.univerData(projectId.value, wpId.value),
        { validateStatus: (s: number) => s < 600 },
      )
      workbookData = data
    } catch {
      workbookData = null
    }
  }

  if (!workbookData || !workbookData.sheets) {
    // 兜底：创建空白工作簿
    workbookData = {
      id: wpDetail.value.wp_code || 'wp',
      name: `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}`,
      sheetOrder: ['sheet0'],
      sheets: {
        sheet0: {
          id: 'sheet0',
          name: wpDetail.value.wp_name || 'Sheet1',
          rowCount: 100,
          columnCount: 20,
          cellData: {},
        },
      },
    }
  }

  // 3. 初始化 Univer
  // Advanced Preset 需要 Univer Server（:3010），当前未部署，跳过
  // 如需启用：部署 Univer Server 后取消下方注释
  const extraPresets: any[] = []
  // try {
  //   const { UniverSheetsDrawingPreset } = await import('@univerjs/preset-sheets-drawing')
  //   const { UniverSheetsAdvancedPreset } = await import('@univerjs/preset-sheets-advanced')
  //   extraPresets.push(UniverSheetsDrawingPreset())
  //   extraPresets.push(UniverSheetsAdvancedPreset({
  //     universerEndpoint: window.location.origin.replace(/:\d+$/, ':3010'),
  //   }))
  // } catch { /* Advanced Preset 不可用 */ }

  const { univerAPI: api, univer } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: mergeLocales(UniverPresetSheetsCoreZhCN),
    },
    presets: [
      UniverSheetsCorePreset({
        container: univerContainer.value,
      }),
      ...extraPresets,
    ],
  })

  univerInstance = univer
  univerAPI = api

  // 4. 创建工作簿（支持 xlsx 导入或 JSON 创建）
  if (loadedFromXlsx && workbookData?._xlsxBlob) {
    // P0-2: Try Univer native xlsx import (requires @univerjs/preset-sheets-advanced)
    const blob = workbookData._xlsxBlob
    let imported = false

    // Strategy 1: importXLSXToSnapshotAsync (Univer 0.21.x with advanced preset)
    if (typeof univerAPI.importXLSXToSnapshotAsync === 'function') {
      try {
        const file = new File([blob], 'workpaper.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
        const snapshot = await univerAPI.importXLSXToSnapshotAsync(file)
        univerAPI.createWorkbook(snapshot)
        imported = true
      } catch (e: any) {
        console.warn('importXLSXToSnapshotAsync failed:', e)
      }
    }

    // Strategy 2: importXLSXToWorkbook (alternative API name)
    if (!imported && typeof univerAPI.importXLSXToWorkbook === 'function') {
      try {
        await univerAPI.importXLSXToWorkbook(blob)
        imported = true
      } catch (e: any) {
        console.warn('importXLSXToWorkbook failed:', e)
      }
    }

    // Strategy 3: Fallback - request backend to convert xlsx to Univer JSON
    if (!imported) {
      try {
        const formData = new FormData()
        formData.append('file', blob, 'workpaper.xlsx')
        const jsonData = await httpApi.post(
          `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/to-json`,
          formData,
        )
        if (jsonData && jsonData.sheets) {
          univerAPI.createWorkbook(jsonData)
          imported = true
        }
      } catch (e: any) {
        console.warn('Backend xlsx-to-json fallback failed:', e)
      }
    }

    // Final fallback: empty workbook
    if (!imported) {
      univerAPI.createWorkbook({
        id: wpDetail.value.wp_code || 'wp',
        name: `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}`,
        sheetOrder: ['sheet0'],
        sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 100, columnCount: 20, cellData: {} } },
      })
    }
  } else {
    univerAPI.createWorkbook(workbookData)
  }

  // 5. 监听数据变化
  univerAPI.onCommandExecuted((command: any) => {
    if (DIRTY_COMMAND_PATTERNS.some(p => command.id?.includes(p))) {
      dirty.value = true
      autoSave.markDirty()
    }
  })

  loading.value = false

  // 6. 非阻塞加载智能提示和用户名映射
  loadSmartTips()
  loadUserMap()

  // ─── Sprint 6 Task 6.4: Univer 右键菜单证据链入口 ─────────────────────────
  // TODO: 完整 Univer 右键菜单集成需要 @univerjs/ui 的 IMenuService
  // 注册位置：在 univerAPI 就绪后，通过 IMenuService.addMenuItem 注册以下三项：
  //   1. "引用附件" — 打开附件选择器，选中后调用 useEvidenceLink.createLink
  //   2. "上传并引用" — 打开上传对话框，上传完成后自动建立 link
  //   3. "查看引用的附件" — 读取当前单元格 cellRef，展示该单元格所有 evidence links
  // 当前为占位注释，完整集成在 Univer 插件体系稳定后实施。
  // ──────────────────────────────────────────────────────────────────────────

  // 7. R1 需求 2：加载复核意见红点（失败不阻断底稿）
  loadReviewMarkers()
}

/**
 * R1 需求 2：拉取 ReviewRecord 并在 Univer 单元格挂红点。
 * - 任何错误都被 composable 内部吞掉，不影响底稿编辑；
 * - 路由 query.cell 或 query.review_id 存在时，红点挂载完成后滚动到对应单元格。
 */
async function loadReviewMarkers() {
  try {
    await reviewMarkers.loadData()
    // Univer API 已在 initUniver 中就绪（univerAPI 变量）
    reviewMarkers.attachMarkers(univerAPI)

    // 路由跳转支持：?cell=B5 直接定位；?review_id=<uuid> 查出 cell 再定位
    const q = route.query
    let targetCell: string | null = null
    if (typeof q.cell === 'string' && q.cell.trim()) {
      targetCell = q.cell.trim()
    } else if (typeof q.review_id === 'string' && q.review_id.trim()) {
      targetCell = reviewMarkers.findCellRefByReviewId(q.review_id.trim())
    }
    if (targetCell) {
      // 下一帧滚动，避免 Univer 内部异步布局未完成
      requestAnimationFrame(() => {
        reviewMarkers.scrollToCell(univerAPI, targetCell as string)
      })
    }
  } catch {
    /* ignore — 红点仅为辅助功能 */
  }
}

async function onSave(): Promise<boolean> {
  if (!univerAPI || !wpDetail.value) return false
  saving.value = true
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')

    const snapshot = workbook.getSnapshot()

    // 如果底稿从 xlsx 模板加载，同时导出 xlsx 回写到后端
    if (loadedFromXlsx) {
      try {
        let xlsxBlob: Blob | null = null

        // P0-3: Try exportXLSXBySnapshotAsync (Univer 0.21.x with advanced preset)
        if (typeof univerAPI.exportXLSXBySnapshotAsync === 'function') {
          xlsxBlob = await univerAPI.exportXLSXBySnapshotAsync(snapshot)
        }
        // Fallback: try exportWorkbookToXLSX
        else if (typeof univerAPI.exportWorkbookToXLSX === 'function') {
          xlsxBlob = await univerAPI.exportWorkbookToXLSX()
        }

        if (xlsxBlob && xlsxBlob.size > 0) {
          const formData = new FormData()
          formData.append('file', xlsxBlob, `${wpId.value}.xlsx`)
          await fetch(
            `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/upload-xlsx`,
            {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
                'X-File-Opened-At': String(fileOpenedAt),
              },
              body: formData,
            },
          )
        }
        // If no export API available, just save the JSON snapshot (existing behavior below)
      } catch (e) {
        console.warn('xlsx export failed (non-blocking):', e)
      }
    }

    // 调用完整保存 API（xlsx 回写 + structure.json + 审计留痕 + 事件发布）
    // 需求 45.1：携带 expected_version 触发后端并发冲突检测
    const data = await httpApi.post(
      P_wp.univerSave(projectId.value, wpId.value),
      { snapshot, expected_version: wpDetail.value.file_version },
      { validateStatus: (s: number) => s < 600 },
    )

    // 需求 45.2：处理 409 版本冲突（axios 在 validateStatus 放行后，409 不会抛错，需手动判断）
    if (data?.detail?.error_code === 'VERSION_CONFLICT' || data?.error_code === 'VERSION_CONFLICT') {
      const detail = data.detail || data
      try {
        await confirmVersionConflict(detail.server_version, detail.expected_version)
        // 刷新放弃：重新加载最新数据
        await initUniver()
        return false
      } catch (action) {
        if (action === 'cancel') {
          // 强制覆盖：不带 expected_version 重发
          const retryData = await httpApi.post(
            P_wp.univerSave(projectId.value, wpId.value),
            { snapshot },
          )
          dirty.value = false
          autoSave.clearDirty()
          ElMessage.success(retryData?.message || '已强制覆盖保存')
          eventBus.emit('workpaper:saved', {
            projectId: projectId.value,
            wpId: wpId.value,
          } as WorkpaperSavedPayload)
          wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
          return true
        }
        return false
      }
    }

    const result = data
    dirty.value = false
    autoSave.clearDirty()
    ElMessage.success(result?.message || '保存成功')

    // 发布底稿保存事件，触发附注自动同步
    eventBus.emit('workpaper:saved', {
      projectId: projectId.value,
      wpId: wpId.value,
    } as WorkpaperSavedPayload)

    // 刷新版本信息
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    return true
  } catch (err: any) {
    handleApiError(err, '保存底稿')
    return false
  } finally {
    saving.value = false
  }
}

async function onSubmitForReview() {
  if (!wpDetail.value) return
  if (dirty.value) {
    ElMessage.warning('请先保存当前修改')
    return
  }
  try {
    await confirmSubmitReview(wpDetail.value?.wp_code || '', wpDetail.value?.wp_name || '')
  } catch { return }

  submitting.value = true
  try {
    await httpApi.put(
      P_wp.status(projectId.value, wpId.value),
      { status: 'pending_review' },
    )
    ElMessage.success('已提交复核，等待复核人审阅')
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch (err: any) {
    handleApiError(err, '提交复核')
  } finally {
    submitting.value = false
  }
}

async function onSyncStructure() {
  syncLoading.value = true
  try {
    // 先保存当前数据
    if (dirty.value) {
      const saveOk = await onSave()
      if (!saveOk) return
    }
    // 重建 structure
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    ElMessage.success('公式坐标已同步')
  } catch (e: any) {
    handleApiError(e, '同步')
  } finally {
    syncLoading.value = false
  }
}

async function onRefreshPrefill() {
  prefillLoading.value = true
  try {
    // 先保存当前编辑
    if (dirty.value) {
      const saveOk = await onSave()
      if (!saveOk) return
    }
    // 调用后端重新初始化（强制从模板复制+prefill）
    await httpApi.post(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/init`,
    )
    // 重新加载 Univer
    if (univerInstance) {
      try { univerInstance.dispose() } catch { /* ignore */ }
      univerInstance = null
      univerAPI = null
    }
    loading.value = true
    await initUniver()
    ElMessage.success('取数刷新完成，已从试算表重新填入最新数据')
  } catch (e: any) {
    handleApiError(e, '刷新取数')
  } finally {
    prefillLoading.value = false
  }
}

async function onDownload() {
  try {
    await downloadWorkpaper(projectId.value, wpId.value)
  } catch (e: any) {
    handleApiError(e, '下载')
  }
}

// 任务 10.6.2：导出 PDF
const exportingPdf = ref(false)
async function onExportPdf() {
  if (!wpDetail.value) return
  exportingPdf.value = true
  try {
    // 使用 axios http 客户端直接获取 blob（apiProxy.api 会 unwrap data 不适合 blob）
    const http = (await import('@/utils/http')).default
    const response = await http.get(
      P_wp.exportPdf(projectId.value, wpId.value),
      { responseType: 'blob', validateStatus: (s: number) => s < 600 },
    )
    const blob: Blob = response.data
    // 后端出错时返回 JSON（blob），需检测
    if (blob.type && blob.type.includes('application/json')) {
      const txt = await blob.text()
      let msg = 'PDF 导出失败'
      try { msg = JSON.parse(txt)?.detail || msg } catch { /* ignore */ }
      handleApiError({ response: { status: 500, data: { detail: msg } } }, 'PDF 导出')
      return
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${wpDetail.value.wp_code || 'workpaper'}_${wpDetail.value.wp_name || ''}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (err: any) {
    handleApiError(err, 'PDF 导出')
  } finally {
    exportingPdf.value = false
  }
}

function onUpload() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

async function loadSmartTips() {
  if (!wpDetail.value) return
  try {
    const wpName = wpDetail.value.wp_name || ''
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) return

    const data = await httpApi.get(
      P_wp.wpMappingTsj(projectId.value, accountName),
      { validateStatus: (s: number) => s < 600 },
    )
    if (data?.tips?.length || data?.risk_areas?.length) {
      smartTip.value = {
        summary: data.risk_areas?.find((a: string) => a.includes('高风险')) || data.tips?.[0]?.slice(0, 30) || '查看审计关注点',
        warnings: (data.risk_areas || []).filter((a: string) => a.includes('高风险')),
        tips: (data.tips || []).slice(0, 3),
      }
    }
  } catch { /* ignore */ }
}

onBeforeRouteLeave(async (_to, _from, next) => {
  if (!dirty.value) { next(); return }
  try {
    await confirmLeave('底稿')
    next()
  } catch {
    next(false)
  }
})

onMounted(() => {
  // 先获取 component_type 决定路由，再初始化对应编辑器
  fetchComponentType().then(() => {
    if (componentType.value === 'univer' || !componentType.value) {
      initUniver()
    }
  })
  // R8-S2-02：订阅 workpaper:locate-cell 事件，定位到 Univer 单元格
  eventBus.on('workpaper:locate-cell', onLocateCell)
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)

  // [R9 F9 Task 30] 确认 Univer Ctrl+Z/Y 不被 shortcutManager 拦截
  // shortcutManager 已在 R9 Task 31 中移除 Ctrl+Z 和 Ctrl+Shift+Z 的注册
  // Univer 内置 UndoCommand/RedoCommand 原生处理撤销/重做，无需额外绑定
})

onUnmounted(() => {
  eventBus.off('workpaper:locate-cell', onLocateCell)
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (univerInstance) {
    try { univerInstance.dispose() } catch { /* ignore */ }
    univerInstance = null
    univerAPI = null
  }
})

/** R8-S2-14：浏览器关闭/刷新前警告（仅在 dirty 时阻止） */
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

/**
 * R8-S2-02：响应 workpaper:locate-cell 事件，通过 Univer API 定位到指定单元格
 * - 事件来源：WorkpaperSidePanel 自检 Tab 的"定位"按钮
 * - 仅处理属于当前底稿的事件（wpId 匹配）
 */
function onLocateCell(payload: { wpId: string; sheetName?: string; cellRef: string }) {
  if (!univerAPI || payload.wpId !== wpId.value) return
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    // 如果指定 sheetName，先切到对应 sheet
    if (payload.sheetName) {
      const sheet = workbook.getSheetByName?.(payload.sheetName)
      if (sheet) workbook.setActiveSheet?.(sheet)
    }
    // cellRef 支持 "B5" 或 "Sheet1!B5" 两种格式
    const cellRef = payload.cellRef.includes('!') ? payload.cellRef.split('!')[1] : payload.cellRef
    const activeSheet = workbook.getActiveSheet?.()
    if (!activeSheet) return
    // 解析 A1 格式为 row/col
    const m = cellRef.match(/^([A-Z]+)(\d+)$/i)
    if (!m) return
    const colStr = m[1].toUpperCase()
    const row = parseInt(m[2], 10) - 1
    let col = 0
    for (const ch of colStr) col = col * 26 + (ch.charCodeAt(0) - 64)
    col -= 1
    const range = activeSheet.getRange?.(row, col)
    if (range) {
      activeSheet.setActiveRange?.(range)
      // 滚动到目标单元格
      try { range.activate?.() } catch { /* ignore */ }
    }
    // 切回编辑区焦点
    showSidePanel.value = false
  } catch {
    /* Univer API 不稳定时静默忽略 */
  }
}
</script>

<style scoped>
.gt-wp-editor {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--gt-color-bg);
}
.gt-wp-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-bg-white); box-shadow: var(--gt-shadow-sm); z-index: 10;
}
.gt-wp-editor-toolbar-left { display: flex; align-items: center; gap: 10px; }
.gt-wp-editor-toolbar-right { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-editor-code { font-weight: 600; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); }
.gt-wp-editor-name { color: var(--gt-color-text); font-size: var(--gt-font-size-md); }
.gt-wp-editor-main { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.gt-wp-editor-univer { width: 100%; height: 100%; }
.gt-wp-editor-loading {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: var(--gt-color-text-tertiary);
}
.gt-wp-editor-statusbar {
  display: flex; gap: var(--gt-space-5); padding: 6px var(--gt-space-4);
  background: var(--gt-color-primary-dark); color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}
.gt-wp-smart-tip {
  margin-left: auto; cursor: pointer; color: var(--gt-color-wheat); font-weight: 500;
}
.gt-wp-smart-tip-detail {
  position: absolute; bottom: 30px; right: 12px; left: 12px;
  background: var(--gt-color-bg-white); border: 1px solid #e8e4f0; border-radius: 8px;
  padding: 12px 16px; box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
  z-index: 20; max-height: 300px; overflow-y: auto;
}
.gt-dirty-indicator {
  color: var(--gt-color-wheat);
  font-size: var(--gt-font-size-xs);
  font-weight: 500;
}
</style>

<!-- R1 需求 2：复核红点样式需全局生效（Univer overlay 在 Vue scope 外渲染） -->
<style>
.gt-review-marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--gt-color-coral);
  box-shadow: 0 0 0 2px rgba(230, 68, 62, 0.18), 0 1px 3px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  transition: transform 0.15s ease;
}
.gt-review-marker-dot:hover {
  transform: scale(1.2);
}
.gt-review-marker-popover {
  padding: 12px !important;
}
</style>
