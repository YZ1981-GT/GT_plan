<!--
  WorkpaperWordEditor.vue — Word 模板底稿编辑器（通用 + A16 专用双模式）

  模式判定：
  - 通用模式（非 A16 wp_code）：直接加载 OnlyOffice editor，无版本选择 UI
  - A16 模式（wp_code === 'A16'）：保留版本选择面板 + 推荐提示 + 补充声明

  统一工具栏：
  - 文档标题（wp_code + 模板名称）
  - sign_status 颜色编码 badge (draft=灰, pending=橙, signed=绿)
  - 保存状态指示器（已保存/保存中/未保存）
  - 导出按钮
-->
<template>
  <div class="gt-wp-word-editor">
    <!-- ═══ 网络断连警告 ═══ -->
    <el-alert
      v-if="networkOffline"
      type="warning"
      :closable="false"
      show-icon
      class="gt-wp-word-editor__network-warning"
    >
      <template #title>网络连接已断开</template>
      <span>正在尝试重新连接…编辑内容将在恢复连接后自动保存。</span>
    </el-alert>

    <!-- ═══ 统一工具栏 ═══ -->
    <div class="gt-wp-word-editor__unified-toolbar">
      <div class="gt-wp-word-editor__toolbar-left">
        <span class="gt-wp-word-editor__doc-title">{{ documentTitle }}</span>
        <el-tag :type="signStatusTagType" size="small" effect="plain">
          {{ signStatusLabel }}
        </el-tag>
      </div>
      <div class="gt-wp-word-editor__toolbar-right">
        <span class="gt-wp-word-editor__save-status" :class="saveStatusClass">
          {{ saveStatusText }}
        </span>
        <el-button size="small" @click="onExportDocx" :disabled="!canExport">
          ⬇️ 导出
        </el-button>
      </div>
    </div>

    <!-- ═══ A16 模式：版本选择面板 ═══ -->
    <template v-if="isA16Mode">
      <section class="gt-wp-word-editor__main-section">
        <div class="gt-wp-word-editor__section-header">
          <h4 class="gt-wp-word-editor__section-title">主声明书版本</h4>
          <el-tag :type="mainSignStatusType" size="small">{{ mainSignStatusLabel }}</el-tag>
        </div>

        <!-- 版本选择器：推荐版本置顶 -->
        <div class="gt-wp-word-editor__version-select">
          <el-radio-group v-model="selectedVersion" size="small" @change="onVersionChange">
            <el-radio-button
              v-for="v in sortedMainVersions"
              :key="v.code"
              :value="v.code"
              :class="{ 'is-recommended': v.recommended }"
            >
              {{ v.label }}
              <el-tag v-if="v.recommended" type="success" size="small" effect="plain" style="margin-left: 4px">推荐</el-tag>
              <el-tag v-if="!v.exists_in_project" type="info" size="small" effect="plain" style="margin-left: 4px">未创建</el-tag>
            </el-radio-button>
          </el-radio-group>
        </div>

        <!-- 推荐版本一键创建提示 -->
        <el-alert
          v-if="recommendedNotCreated"
          type="info"
          :closable="true"
          show-icon
          style="margin-bottom: 12px"
        >
          <template #title>
            推荐使用「{{ recommendedVersionLabel }}」，该版本尚未在项目中创建。
          </template>
          <el-button size="small" type="primary" @click="createRecommendedVersion">
            一键创建
          </el-button>
        </el-alert>

        <!-- 主版本操作栏 -->
        <div class="gt-wp-word-editor__toolbar">
          <el-button type="primary" size="small" @click="openEditor('main')" :loading="loading">
            {{ onlyofficeAvailable ? '📝 在线编辑' : '📝 编辑（降级）' }}
          </el-button>
          <el-button size="small" @click="downloadTemplate('main')">⬇️ 下载模板</el-button>
          <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true; uploadTarget = 'main'">⬆️ 上传</el-button>
          <el-divider direction="vertical" />
          <el-button-group>
            <el-button size="small" :type="signStatus === 'pending' ? 'warning' : 'default'" @click="updateSignStatus('pending')" :disabled="signStatus === 'signed'">
              📤 标记待签署
            </el-button>
            <el-button size="small" :type="signStatus === 'signed' ? 'success' : 'default'" @click="updateSignStatus('signed')">
              ✅ 标记已签回
            </el-button>
          </el-button-group>
        </div>
      </section>

      <!-- ═══ A13 未更正错报联动提示 ═══ -->
      <el-alert
        v-if="misstatementSummary"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>声明书"未更正错报"段落内容（自动引用 A13）</template>
        <p style="margin: 4px 0 0; font-size: 12px; white-space: pre-wrap">{{ misstatementSummary }}</p>
      </el-alert>
      <el-alert
        v-else-if="misstatementLoaded"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        :title="`无未更正错报，声明书中\u201C未更正错报\u201D段落可填写\u201C无\u201D`"
      />

      <!-- ═══ 补充声明区 A16-7 ═══ -->
      <section class="gt-wp-word-editor__supplement-section">
        <div class="gt-wp-word-editor__section-header">
          <h4 class="gt-wp-word-editor__section-title">补充声明（A16-7 关联交易声明书）</h4>
          <el-switch
            v-model="supplementEnabled"
            active-text="需编制关联交易声明书"
            @change="onSupplementToggle"
          />
        </div>

        <template v-if="supplementEnabled">
          <div class="gt-wp-word-editor__supplement-status">
            <el-tag :type="supplementSignStatusType" size="small">签回：{{ supplementSignLabel }}</el-tag>
          </div>

          <div class="gt-wp-word-editor__toolbar">
            <el-button type="primary" size="small" @click="openEditor('supplement')" :loading="supplementLoading">
              {{ onlyofficeAvailable ? '📝 编辑 A16-7' : '📝 编辑（降级）' }}
            </el-button>
            <el-button size="small" @click="downloadTemplate('supplement')">⬇️ 下载 A16-7</el-button>
            <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true; uploadTarget = 'supplement'">⬆️ 上传</el-button>
            <el-divider direction="vertical" />
            <el-button-group>
              <el-button size="small" :type="supplementSignStatus === 'pending' ? 'warning' : 'default'" @click="updateSupplementSignStatus('pending')" :disabled="supplementSignStatus === 'signed'">
                📤 已发送
              </el-button>
              <el-button size="small" :type="supplementSignStatus === 'signed' ? 'success' : 'default'" @click="updateSupplementSignStatus('signed')">
                ✅ 已签回
              </el-button>
            </el-button-group>
          </div>
        </template>

        <p v-else class="gt-wp-word-editor__supplement-hint">
          如有关联交易，请启用此项独立编制并签回。
        </p>
      </section>

      <!-- 编制信息 -->
      <div class="gt-wp-word-editor__info">
        <el-descriptions :column="2" border size="small" title="编制信息（自动预填占位符）">
          <el-descriptions-item label="客户名称">{{ placeholders.client_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审计期间">{{ placeholders.audit_period || '—' }}</el-descriptions-item>
          <el-descriptions-item label="签字合伙人">{{ placeholders.partner_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="选用版本">{{ selectedVersionLabel }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </template>

    <!-- ═══ 通用模式：直接加载 OnlyOffice editor ═══ -->
    <template v-else>
      <section class="gt-wp-word-editor__generic-section">
        <!-- 双模式切换 (Task 5.1 + 5.4: tooltip when OO unavailable) -->
        <div class="gt-wp-word-editor__mode-switch">
          <el-tooltip
            :content="'OnlyOffice 不可用'"
            :disabled="onlyofficeAvailable"
            placement="top"
          >
            <el-segmented
              v-model="genericViewMode"
              :options="genericModeOptions"
              size="small"
              @change="onModeSwitch"
            />
          </el-tooltip>
          <span class="gt-wp-word-editor__save-indicator" :class="`save-status--${structuredSaveStatus}`">
            {{ structuredSaveStatus === 'saved' ? '✓ 已保存' : structuredSaveStatus === 'saving' ? '保存中…' : '● 未保存' }}
          </span>
        </div>

        <!-- 结构化视图 -->
        <div v-if="genericViewMode === '结构化视图'" class="gt-wp-word-editor__structured-area">
          <!-- 导出/导入工具栏 (Task 8.1, 8.2, 8.3) -->
          <div class="gt-wp-word-editor__structured-toolbar">
            <el-button size="small" :icon="Download" @click="onExportWord" :loading="exportingWord">
              导出 Word
            </el-button>
            <el-button size="small" :icon="Document" @click="onExportTemplate" :loading="exportingTemplate">
              导出模板
            </el-button>
            <el-button size="small" :icon="Upload" @click="showImportDialog = true">
              导入数据
            </el-button>
          </div>

          <el-skeleton v-if="structuredLoading" :rows="8" animated />
          <GtWordTemplateStructuredView
            v-else-if="structuredTemplateStructure"
            :template-structure="structuredTemplateStructure"
            :field-values="structuredFieldValues"
            :readonly="readonly"
            @update:field="onStructuredFieldUpdate"
            @ai-fill="onAiFill"
          />
          <el-empty v-else description="模板解析失败，请使用在线编辑模式" />
        </div>

        <!-- 在线编辑 -->
        <div v-else class="gt-wp-word-editor__editor-area">
          <template v-if="onlyofficeAvailable">
            <div class="gt-wp-word-editor__oo-toolbar">
              <el-button size="small" @click="toggleFullscreen">
                {{ isFullscreen ? '退出全屏' : '全屏编辑' }}
              </el-button>
            </div>
            <div ref="ooContainerRef" :id="editorContainerId" class="gt-wp-word-editor__oo-container" :class="{ 'is-fullscreen': isFullscreen }" />
          </template>
          <div v-else class="gt-wp-word-editor__degraded-generic">
            <el-alert type="warning" :closable="false" show-icon>
              <template #title>OnlyOffice 不可用，已降级为只读模式</template>
              <span>请使用「结构化视图」编辑字段，或下载模板到本地编辑后上传。</span>
            </el-alert>
            <div class="gt-wp-word-editor__toolbar" style="margin-top: 12px">
              <el-button size="small" @click="downloadTemplate('main')">⬇️ 下载模板</el-button>
              <el-button size="small" @click="showUpload = true; uploadTarget = 'main'">⬆️ 上传</el-button>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- OnlyOffice 编辑弹窗（A16 模式） -->
    <OnlyOfficeWordDialog
      v-if="editorVisible"
      v-model:visible="editorVisible"
      :document-url="documentUrl"
      :document-key="documentKey"
      :title="editorTitle"
      :mode="readonly ? 'view' : 'edit'"
      :callback-url="callbackUrl"
      @saved="onDocumentSaved"
    />

    <!-- 签署日期对话框 -->
    <el-dialog v-model="showSignDateDialog" title="确认签署日期" width="400px" :close-on-click-modal="false">
      <p style="margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 13px">
        请确认管理层声明书签署日期。该日期将同步到审计报告。
      </p>
      <el-date-picker
        v-model="signDateValue"
        type="date"
        placeholder="选择签署日期"
        value-format="YYYY-MM-DD"
        style="width: 100%"
      />
      <template #footer>
        <el-button @click="showSignDateDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!signDateValue" @click="confirmSignDate">确认签回</el-button>
      </template>
    </el-dialog>

    <!-- 上传弹窗 -->
    <el-dialog v-model="showUpload" title="上传编辑后文件" width="480px">
      <el-upload
        :action="`/api/workpapers/${wpId}/upload-offline`"
        :headers="uploadHeaders"
        :on-success="onUploadSuccess"
        accept=".docx,.doc"
        :limit="1"
        drag
      >
        <div style="padding: 20px; text-align: center">
          <p>拖拽或点击上传编辑完成的文件（.docx）</p>
        </div>
      </el-upload>
    </el-dialog>

    <!-- 导入数据弹窗 (Task 8.3) -->
    <el-dialog v-model="showImportDialog" title="导入数据" width="480px" :close-on-click-modal="false">
      <p style="margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 13px">
        上传离线填写的 .docx 文件，系统将自动解析并导入字段数据。
      </p>
      <el-upload
        ref="importUploadRef"
        :auto-upload="false"
        accept=".docx"
        :limit="1"
        drag
        :on-change="onImportFileChange"
        :on-remove="onImportFileRemove"
      >
        <div style="padding: 20px; text-align: center">
          <p>拖拽或点击选择 .docx 文件</p>
        </div>
      </el-upload>
      <template #footer>
        <el-button @click="showImportDialog = false" :disabled="importing">取消</el-button>
        <el-button type="primary" @click="onImportData" :loading="importing" :disabled="!importFile">
          开始导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Document, Upload } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import OnlyOfficeWordDialog from './OnlyOfficeWordDialog.vue'
import GtWordTemplateStructuredView from './GtWordTemplateStructuredView.vue'
import { useWordTemplateStructured } from './composables/useWordTemplateStructured'

const props = defineProps<{
  wpId: string
  sheetName?: string
  htmlData?: any
  schema?: any
  readonly?: boolean
  // extraComponentProps via 'standard' strategy (Vue auto-converts kebab to camelCase)
  wpCode?: string
  projectId?: string
  year?: number
}>()

const route = useRoute()
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')
const wpCode = computed(() => props.wpCode || '')

// ─── Mode Detection ───
const isA16Mode = computed(() => wpCode.value === 'A16')

// ─── Generic Mode: Dual-mode switch (Task 5.1) ───
const genericViewMode = ref<'结构化视图' | '在线编辑'>('结构化视图')
const genericModeOptions = ['结构化视图', '在线编辑']

// ─── Structured View (useWordTemplateStructured composable) ───
const {
  templateStructure: structuredTemplateStructure,
  fieldValues: structuredFieldValues,
  loading: structuredLoading,
  saveStatus: structuredSaveStatus,
  loadStructure: loadStructuredData,
  updateField: structuredUpdateField,
  flushPendingSaves: structuredFlush,
  exportDocx: structuredExportDocx,
  exportTemplate: structuredExportTemplate,
  triggerAiFill: structuredAiFill,
} = useWordTemplateStructured({
  wpId: computed(() => props.wpId),
  wpCode: wpCode,
  projectId: projectId,
})

function onStructuredFieldUpdate(fieldId: string, value: string) {
  structuredUpdateField(fieldId, value)
}

function onAiFill(fieldId: string) {
  structuredAiFill(fieldId)
}

// ─── Export/Import Toolbar (Task 8.1, 8.2, 8.3) ───
const exportingWord = ref(false)
const exportingTemplate = ref(false)
const showImportDialog = ref(false)
const importing = ref(false)
const importFile = ref<File | null>(null)
const importUploadRef = ref<any>(null)

/** Task 8.1: Export Word with responses merged */
async function onExportWord() {
  exportingWord.value = true
  try {
    await structuredExportDocx()
  } finally {
    exportingWord.value = false
  }
}

/** Task 8.2: Export template with guidance */
async function onExportTemplate() {
  exportingTemplate.value = true
  try {
    await structuredExportTemplate()
  } finally {
    exportingTemplate.value = false
  }
}

/** Task 8.3: Import file change handler */
function onImportFileChange(file: any) {
  importFile.value = file?.raw || null
}

function onImportFileRemove() {
  importFile.value = null
}

/** Task 8.3: Import structured data from uploaded docx */
async function onImportData() {
  if (!importFile.value) return
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const r = await fetch(`/api/workpapers/${props.wpId}/import-structured`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err?.detail || err?.message || '导入失败')
    }
    const data = await r.json()
    // ResponseWrapperMiddleware: actual payload in data.data
    const result = data?.data || data
    const importedCount = result?.imported_count ?? 0
    showImportDialog.value = false
    importFile.value = null
    ElMessage.success(`已导入 ${importedCount} 个字段`)
    // Refresh structured view
    await loadStructuredData()
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败，请重试')
  } finally {
    importing.value = false
  }
}

// ─── Mode Switch Logic (Task 5.3 + 5.4) ───
async function onModeSwitch(newMode: string) {
  if (newMode === '在线编辑') {
    // Task 5.4: Guard — prevent switching when OnlyOffice unavailable
    if (!onlyofficeAvailable.value) {
      genericViewMode.value = '结构化视图'
      ElMessage.warning('OnlyOffice 不可用')
      return
    }
    // Structured→Online: flush pending saves then init OnlyOffice
    await structuredFlush()
    await initGenericEditor()
  } else {
    // Online→Structured: reload template-structure API for latest responses
    await loadStructuredData()
  }
}

// ─── Fullscreen toggle (generic online edit) ───
const isFullscreen = ref(false)
const ooContainerRef = ref<HTMLElement | null>(null)

function toggleFullscreen() {
  if (!isFullscreen.value) {
    const el = ooContainerRef.value
    if (el?.requestFullscreen) {
      el.requestFullscreen().catch(() => { /* fallback to CSS */ })
    } else if ((el as any)?.webkitRequestFullscreen) {
      (el as any).webkitRequestFullscreen()
    }
    isFullscreen.value = true
    document.addEventListener('fullscreenchange', _onFsChange)
  } else {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
    }
    isFullscreen.value = false
    document.removeEventListener('fullscreenchange', _onFsChange)
  }
}

function _onFsChange() {
  if (!document.fullscreenElement && isFullscreen.value) {
    isFullscreen.value = false
    document.removeEventListener('fullscreenchange', _onFsChange)
  }
}

// ─── Common State ───
const loading = ref(false)
const supplementLoading = ref(false)
const editorVisible = ref(false)
const showUpload = ref(false)
const uploadTarget = ref<'main' | 'supplement'>('main')
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')
const editorTitle = ref('')
const callbackUrl = ref('')
const signStatus = ref<'draft' | 'pending' | 'signed'>('draft')
const supplementSignStatus = ref<'draft' | 'pending' | 'signed'>('draft')
const supplementEnabled = ref(false)
const misstatementSummary = ref('')
const misstatementLoaded = ref(false)
const selectedVersion = ref('A16-1')

// ─── Save Status ───
type SaveState = 'saved' | 'saving' | 'unsaved'
const saveState = ref<SaveState>('saved')

// ─── Network Status ───
const networkOffline = ref(false)
let reconnectTimer: ReturnType<typeof setInterval> | null = null

// ─── Sign Date Dialog ───
const showSignDateDialog = ref(false)
const signDateValue = ref<string>('')
const pendingSignTarget = ref<'main' | 'supplement'>('main')
const cachedReportDate = ref<string>('')
const cachedAuditPeriodEnd = ref<string>('')

// ─── OnlyOffice inline editor (generic mode) ───
const editorContainerId = `oo-wp-editor-${Date.now()}`
let ooEditorInstance: any = null

const SUPPLEMENT_CODE = 'A16-7'

const placeholders = reactive({
  client_name: '',
  audit_period: '',
  partner_name: '',
  entity_name: '',
  period_end: '',
})

// ─── A16 Template Versions ───
interface TemplateVersion {
  code: string
  label: string
  recommended: boolean
  exists_in_project: boolean
}

const mainTemplateVersions = ref<TemplateVersion[]>([
  { code: 'A16-1', label: '一般财报', recommended: false, exists_in_project: true },
  { code: 'A16-2', label: '整合审计', recommended: false, exists_in_project: true },
  { code: 'A16-3', label: 'IPO申报', recommended: false, exists_in_project: true },
  { code: 'A16-4', label: 'IPO季度', recommended: false, exists_in_project: true },
  { code: 'A16-5', label: '新三板', recommended: false, exists_in_project: true },
  { code: 'A16-6', label: '企业债', recommended: false, exists_in_project: true },
])

const sortedMainVersions = computed(() => {
  const versions = [...mainTemplateVersions.value]
  versions.sort((a, b) => {
    if (a.recommended && !b.recommended) return -1
    if (!a.recommended && b.recommended) return 1
    return 0
  })
  return versions
})

const selectedVersionLabel = computed(() =>
  mainTemplateVersions.value.find(v => v.code === selectedVersion.value)?.label || selectedVersion.value
)

// ─── Recommended version (Task 8.1) ───
const recommendedCode = ref<string>('')
const recommendedNotCreated = computed(() => {
  if (!recommendedCode.value) return false
  const v = mainTemplateVersions.value.find(t => t.code === recommendedCode.value)
  return v ? !v.exists_in_project : false
})
const recommendedVersionLabel = computed(() =>
  mainTemplateVersions.value.find(v => v.code === recommendedCode.value)?.label || recommendedCode.value
)

// ─── Unified Toolbar Computed (Task 7.2) ───
const documentTitle = computed(() => {
  if (isA16Mode.value) {
    return `${wpCode.value} 管理层声明书`
  }
  // Generic mode: wp_code + template name from htmlData or schema
  const templateName = props.htmlData?.template_name || props.schema?.template_name || ''
  return templateName ? `${wpCode.value} ${templateName}` : wpCode.value || 'Word 模板'
})

const signStatusTagType = computed(() => {
  if (signStatus.value === 'signed') return 'success'
  if (signStatus.value === 'pending') return 'warning'
  return 'info' // draft = gray
})

const signStatusLabel = computed(() => {
  const m: Record<string, string> = { draft: '草稿', pending: '待签署', signed: '已签署' }
  return m[signStatus.value] || '草稿'
})

const saveStatusText = computed(() => {
  const m: Record<SaveState, string> = { saved: '已保存', saving: '保存中…', unsaved: '未保存' }
  return m[saveState.value]
})

const saveStatusClass = computed(() => `save-status--${saveState.value}`)

const canExport = computed(() => onlyofficeAvailable.value || true) // always allow export attempt

// A16 specific sign status display
const mainSignStatusLabel = computed(() => {
  const m: Record<string, string> = { draft: '草稿', pending: '待签署', signed: '已签回' }
  return m[signStatus.value] || '草稿'
})
const mainSignStatusType = computed(() => {
  if (signStatus.value === 'signed') return 'success'
  if (signStatus.value === 'pending') return 'warning'
  return 'info'
})
const supplementSignLabel = computed(() => {
  const m: Record<string, string> = { draft: '草稿', pending: '待签署', signed: '已签回' }
  return m[supplementSignStatus.value] || '草稿'
})
const supplementSignStatusType = computed(() => {
  if (supplementSignStatus.value === 'signed') return 'success'
  if (supplementSignStatus.value === 'pending') return 'warning'
  return 'info'
})

const uploadHeaders = computed(() => {
  const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

// ─── Export filename helper (Task 7.2 / Property 12) ───
function buildExportFilename(): string {
  const code = wpCode.value || 'workpaper'
  const entity = sanitizeFilename(placeholders.entity_name || placeholders.client_name || '')
  const period = placeholders.period_end || ''
  if (entity && period) return `${code}_${entity}_${period}.docx`
  if (entity) return `${code}_${entity}.docx`
  return `${code}.docx`
}

/** 清理文件名中不安全的字符 */
function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim()
}

// ─── Network disconnection detection (Task 7.3) ───
function onOnline() {
  networkOffline.value = false
  if (reconnectTimer) {
    clearInterval(reconnectTimer)
    reconnectTimer = null
  }
  ElMessage.success('网络已恢复连接')
}

function onOffline() {
  networkOffline.value = true
  // Auto-reconnect attempt every 10s
  if (!reconnectTimer) {
    reconnectTimer = setInterval(() => {
      if (navigator.onLine) {
        onOnline()
      }
    }, 10000)
  }
}

// ─── Methods ───
async function loadProjectInfo() {
  if (!projectId.value) return
  try {
    const info = await api.get<any>(`/api/projects/${projectId.value}`, { _silent: true } as any)
    const d = info?.data || info
    placeholders.client_name = d?.client_name || d?.name || ''
    placeholders.entity_name = d?.client_name || d?.name || ''
    placeholders.audit_period = d?.audit_period_end ? `${d.audit_year || ''}年度` : ''
    placeholders.partner_name = d?.partner_name || ''
    placeholders.period_end = d?.audit_period_end
      ? (typeof d.audit_period_end === 'string' ? d.audit_period_end.slice(0, 10) : '')
      : ''

    if (d?.audit_period_end) {
      cachedAuditPeriodEnd.value = typeof d.audit_period_end === 'string'
        ? d.audit_period_end.slice(0, 10) : ''
    }

    // Try to get audit report date for sign_date default
    try {
      const year = getAuditYear()
      const report = await api.get<any>(`/api/audit-report?project_id=${projectId.value}&year=${year}`, { _silent: true } as any)
      const rd = report?.report_date || report?.data?.report_date
      if (rd) cachedReportDate.value = typeof rd === 'string' ? rd.slice(0, 10) : ''
    } catch { /* audit_report may not exist yet */ }
  } catch { /* ignore */ }
}

/** Task 8.1: Load recommended version from API */
async function loadRecommendedVersion() {
  if (!isA16Mode.value) return
  try {
    const rec = await api.get<any>(`/api/projects/${projectId.value}/a16/recommended-version`)
    const data = rec?.data || rec
    // Support both API formats:
    // Format 1 (design doc): { recommended_code, all_versions, always_required }
    // Format 2 (legacy): { main: { code, label }, supplement: { code } }
    const recCode = data?.recommended_code || data?.main?.code
    if (recCode) {
      recommendedCode.value = recCode
      // Update version labels and exists_in_project from API response
      if (data.all_versions && Array.isArray(data.all_versions)) {
        for (const apiVer of data.all_versions) {
          const local = mainTemplateVersions.value.find(v => v.code === apiVer.code)
          if (local) {
            if (apiVer.label) local.label = apiVer.label
            local.exists_in_project = apiVer.exists_in_project !== false
          }
        }
      }
      // Mark recommended
      for (const v of mainTemplateVersions.value) {
        v.recommended = v.code === recCode
      }
    }
    // Supplement: check if A16-7 should be enabled
    if (data?.supplement || (data?.always_required && data.always_required.includes('A16-7'))) {
      supplementEnabled.value = true
    }
  } catch { /* fallback: no recommendation available */ }
}

/** A16 version resolution (URL query > persisted > recommendation > default) */
async function resolveA16Version() {
  let resolvedVersion: string | null = null

  // 1. URL query override
  const qv = route.query.version as string
  if (qv && mainTemplateVersions.value.some(v => v.code === qv)) {
    resolvedVersion = qv
  }

  // 2. Persisted field_override
  if (!resolvedVersion) {
    const persisted = await loadPersistedVersion()
    if (persisted) resolvedVersion = persisted
  }

  // 3. Recommendation fallback
  if (!resolvedVersion && recommendedCode.value) {
    resolvedVersion = recommendedCode.value
  }

  // 4. Apply
  if (resolvedVersion) selectedVersion.value = resolvedVersion
  if (qv && qv === resolvedVersion) persistSelectedVersion(qv)
}

/** Create recommended version workpaper (Task 8.1) */
async function createRecommendedVersion() {
  if (!recommendedCode.value) return
  try {
    await api.post(`/api/projects/${projectId.value}/workpapers/create-from-template`, {
      wp_code: recommendedCode.value,
    })
    ElMessage.success(`已创建 ${recommendedVersionLabel.value}`)
    // Refresh versions
    const v = mainTemplateVersions.value.find(t => t.code === recommendedCode.value)
    if (v) v.exists_in_project = true
    selectedVersion.value = recommendedCode.value
    persistSelectedVersion(recommendedCode.value)
  } catch (e: any) {
    ElMessage.error('创建失败：' + (e?.message || '请重试'))
  }
}

async function loadMisstatementSummary() {
  if (!isA16Mode.value) return
  try {
    const year = getAuditYear()
    const r = await api.get<any>(
      `/api/projects/${projectId.value}/misstatements/for-letter`,
      { params: { year } },
    )
    const text = r?.summary || r?.data?.summary || ''
    misstatementSummary.value = (text === '无未更正错报。') ? '' : text
    misstatementLoaded.value = true
  } catch {
    misstatementLoaded.value = true
  }
}

async function checkHealth() {
  try {
    const r = await api.get<{ healthy: boolean }>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    onlyofficeAvailable.value = r?.healthy ?? false
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function loadSignStatus() {
  // For generic mode, sign_status comes from render-config (htmlData)
  if (!isA16Mode.value) {
    // Try from htmlData (injected by render-config step 9)
    const fromHtml = props.htmlData?.sign_status
    if (fromHtml && ['draft', 'pending', 'signed'].includes(fromHtml)) {
      signStatus.value = fromHtml
      return
    }
    // Fallback: query field_overrides
    try {
      const year = getAuditYear()
      const scope = `word_template:${wpCode.value}`
      const overrides = await api.get<any>('/api/workpapers/field-overrides', {
        params: { project_id: projectId.value, year, scope },
        _silent: true,
      } as any)
      signStatus.value = overrides?.sign_status?.value || 'draft'
    } catch { signStatus.value = 'draft' }
    return
  }
  // A16 mode
  try {
    const info = await api.get<any>(
      `/api/projects/${projectId.value}/working-papers/${props.wpId}/file-info?version=${encodeURIComponent(selectedVersion.value)}`,
      { _silent: true } as any,
    )
    signStatus.value = info?.sign_status || 'draft'
  } catch { signStatus.value = 'draft' }
}

async function loadSupplementSignStatus() {
  if (!supplementEnabled.value) return
  try {
    const info = await api.get<any>(
      `/api/projects/${projectId.value}/working-papers/${props.wpId}/file-info?version=${encodeURIComponent(SUPPLEMENT_CODE)}`,
      { _silent: true } as any,
    )
    supplementSignStatus.value = info?.sign_status || 'draft'
  } catch { /* ignore */ }
}

// ─── Sign status update ───
async function updateSignStatus(status: string) {
  if (isA16Mode.value && status === 'signed') {
    pendingSignTarget.value = 'main'
    signDateValue.value = getDefaultSignDate()
    showSignDateDialog.value = true
    return
  }
  await _doUpdateSignStatus(status)
}

async function _doUpdateSignStatus(status: string, signDate?: string) {
  try {
    const payload: Record<string, any> = { status }
    if (isA16Mode.value) payload.version = selectedVersion.value
    if (signDate) payload.sign_date = signDate
    await api.post(`/api/workpapers/${props.wpId}/sign-status`, payload)
    signStatus.value = status as any
    ElMessage.success(status === 'signed' ? '已标记签回' : status === 'pending' ? '已标记待签署' : '已更新状态')
  } catch {
    // Fallback: field_overrides
    try {
      const year = getAuditYear()
      const scope = isA16Mode.value
        ? `word_template:A16:${selectedVersion.value}`
        : `word_template:${wpCode.value}`
      await api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value, year, scope,
        item_key: 'sign_status', field: 'value', value: status,
      })
      signStatus.value = status as any
      ElMessage.success('状态已更新')
    } catch {
      ElMessage.error('更新状态失败')
    }
  }
}

async function confirmSignDate() {
  showSignDateDialog.value = false
  if (pendingSignTarget.value === 'main') {
    await _doUpdateSignStatus('signed', signDateValue.value)
  } else {
    await _doUpdateSupplementSignStatus('signed', signDateValue.value)
  }
}

function getDefaultSignDate(): string {
  if (cachedReportDate.value) return cachedReportDate.value
  if (cachedAuditPeriodEnd.value) return cachedAuditPeriodEnd.value
  return new Date().toISOString().slice(0, 10)
}

async function updateSupplementSignStatus(status: string) {
  if (status === 'signed') {
    await _doUpdateSupplementSignStatus(status)
    return
  }
  await _doUpdateSupplementSignStatus(status)
}

async function _doUpdateSupplementSignStatus(status: string, _signDate?: string) {
  try {
    const payload: Record<string, any> = { status, version: SUPPLEMENT_CODE }
    await api.post(`/api/workpapers/${props.wpId}/sign-status`, payload)
    supplementSignStatus.value = status as any
    ElMessage.success(status === 'signed' ? 'A16-7 已签回' : 'A16-7 已标记待签署')
  } catch {
    try {
      const year = getAuditYear()
      await api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value, year,
        scope: `word_template:A16:${SUPPLEMENT_CODE}`,
        item_key: 'sign_status', field: 'value', value: status,
      })
      supplementSignStatus.value = status as any
      ElMessage.success(status === 'signed' ? 'A16-7 已签回' : 'A16-7 已标记待签署')
    } catch {
      ElMessage.error('更新 A16-7 状态失败')
    }
  }
}

async function onSupplementToggle(enabled: boolean | string | number) {
  try {
    const year = getAuditYear()
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value, year,
      scope: `word_template:A16:${SUPPLEMENT_CODE}`,
      item_key: 'enabled', field: 'value', value: String(!!enabled),
    })
    if (enabled) loadSupplementSignStatus()
  } catch { /* non-critical */ }
}

// ─── Version selection (A16) ───
async function onVersionChange(code: string) {
  selectedVersion.value = code
  persistSelectedVersion(code)
  await loadSignStatus()
}

async function persistSelectedVersion(code: string) {
  try {
    const year = getAuditYear()
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value, year,
      scope: 'word_template:A16',
      item_key: 'selected_version', field: 'value', value: code,
    })
  } catch { /* non-critical */ }
}

async function loadPersistedVersion(): Promise<string | null> {
  try {
    const year = getAuditYear()
    const overrides = await api.get<Record<string, Record<string, any>>>(
      '/api/workpapers/field-overrides',
      { params: { project_id: projectId.value, year, scope: 'word_template:A16' } },
    )
    const val = overrides?.selected_version?.value
    if (val && mainTemplateVersions.value.some(v => v.code === val)) return val
  } catch { /* ignore */ }
  return null
}

function getAuditYear(): number {
  return props.year || parseInt(route.query.year as string) || new Date().getFullYear()
}

// ─── OnlyOffice editor actions ───
async function openEditor(target: 'main' | 'supplement') {
  const version = target === 'supplement' ? SUPPLEMENT_CODE : selectedVersion.value
  const loadingRef = target === 'supplement' ? supplementLoading : loading

  if (!onlyofficeAvailable.value) {
    ElMessage.info('OnlyOffice 不可用，请使用下载编辑方式')
    return
  }
  loadingRef.value = true
  try {
    const config = await api.get<any>(`/api/workpapers/${props.wpId}/onlyoffice-config`, {
      params: { version },
      _silent: true,
    } as any)
    documentUrl.value = config.document_url || ''
    documentKey.value = config.document_key || `wp-${props.wpId}-${version}-${Date.now()}`
    callbackUrl.value = config.callback_url || ''
    editorTitle.value = target === 'supplement'
      ? '关联交易声明书 (A16-7)'
      : isA16Mode.value
        ? `声明书 (${selectedVersionLabel.value})`
        : documentTitle.value
    editorVisible.value = true
  } catch (e: any) {
    ElMessage.error('打开编辑器失败：' + (e?.message || '未知错误'))
  } finally {
    loadingRef.value = false
  }
}

async function downloadTemplate(target: 'main' | 'supplement') {
  const version = target === 'supplement' ? SUPPLEMENT_CODE : (isA16Mode.value ? selectedVersion.value : wpCode.value)
  try {
    const url = `/api/projects/${projectId.value}/wp-templates/${version}/prefilled-download`
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error('下载失败')
    const blob = await r.blob()
    const obj = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = obj
    a.download = target === 'supplement' ? 'A16-7_关联交易声明书.docx' : buildExportFilename()
    a.click()
    URL.revokeObjectURL(obj)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

// ─── Export (Task 7.2) ───
async function onExportDocx() {
  try {
    const version = isA16Mode.value ? selectedVersion.value : wpCode.value
    const url = `/api/projects/${projectId.value}/wp-templates/${version}/prefilled-download`
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error('导出失败')
    const blob = await r.blob()
    const obj = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = obj
    a.download = buildExportFilename()
    a.click()
    URL.revokeObjectURL(obj)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

// ─── OnlyOffice save callback (Task 7.3) ───
function onDocumentSaved() {
  saveState.value = 'saved'
  ElMessage.success('文件已保存')
  loadSignStatus()
  if (isA16Mode.value && supplementEnabled.value) loadSupplementSignStatus()
}

/** Initialize OnlyOffice inline editor for generic mode */
async function initGenericEditor() {
  if (isA16Mode.value || !onlyofficeAvailable.value) return

  // word-template 底稿使用 GtOnlyOfficeSheet 相同的端点格式：
  // /api/workpapers/{wpId}/sheets/{sheetName}/onlyoffice-config
  const sheetName = props.sheetName || props.htmlData?.sheet_name || wpCode.value || 'Sheet1'
  try {
    const resp = await api.get<any>(
      `/api/workpapers/${props.wpId}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`,
      { params: { project_id: projectId.value }, _silent: true } as any,
    )
    if (!resp?.config?.document?.url) return

    // Load OnlyOffice JS API
    const base = resp.onlyoffice_url || (import.meta as any).env?.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
    await loadOnlyOfficeScript(base)
    await nextTick()

    const DocsAPI = (window as any).DocsAPI
    if (!DocsAPI) {
      onlyofficeAvailable.value = false
      return
    }

    // 使用后端返回的完整 config + token
    const editorConfig: any = {
      ...resp.config,
      ...(resp.token ? { token: resp.token } : {}),
      events: {
        onDocumentStateChange(event: any) {
          if (event?.data) {
            saveState.value = 'unsaved'
          }
        },
        onSave() {
          saveState.value = 'saving'
        },
        onDocumentReady() {
          saveState.value = 'saved'
        },
      },
    }

    ooEditorInstance = new DocsAPI.DocEditor(editorContainerId, editorConfig)
  } catch (e: any) {
    console.warn('[WorkpaperWordEditor] OnlyOffice init failed:', e)
    onlyofficeAvailable.value = false
  }
}

function loadOnlyOfficeScript(baseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).DocsAPI) { resolve(); return }
    const script = document.createElement('script')
    script.src = `${baseUrl}/web-apps/apps/api/documents/api.js`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load OnlyOffice API script'))
    document.head.appendChild(script)
  })
}

function onUploadSuccess() {
  showUpload.value = false
  ElMessage.success('上传成功')
  saveState.value = 'saved'
  if (uploadTarget.value === 'supplement') {
    loadSupplementSignStatus()
  } else {
    loadSignStatus()
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  // Network listeners (Task 7.3)
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  networkOffline.value = !navigator.onLine

  await checkHealth()
  await loadProjectInfo()

  if (isA16Mode.value) {
    // A16 mode: load recommended version first, then resolve selection
    await loadRecommendedVersion()
    await resolveA16Version()
    loadMisstatementSummary()
  }

  await loadSignStatus()

  if (isA16Mode.value && supplementEnabled.value) {
    loadSupplementSignStatus()
  }

  // Generic mode: init inline editor + load structured data
  if (!isA16Mode.value) {
    await nextTick()
    loadStructuredData()
    initGenericEditor()
  }
})

onUnmounted(() => {
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  if (reconnectTimer) { clearInterval(reconnectTimer); reconnectTimer = null }
  if (ooEditorInstance) {
    try { ooEditorInstance.destroyEditor() } catch { /* ignore */ }
    ooEditorInstance = null
  }
})
</script>

<style scoped>
.gt-wp-word-editor {
  padding: 16px;
}

/* Network warning */
.gt-wp-word-editor__network-warning {
  margin-bottom: 12px;
}

/* Unified toolbar (Task 7.2) */
.gt-wp-word-editor__unified-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 6px;
  background: var(--el-bg-color, #fff);
}
.gt-wp-word-editor__toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gt-wp-word-editor__toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-wp-word-editor__doc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-wp-word-editor__save-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}
.gt-wp-word-editor__save-status.save-status--saved {
  color: var(--el-color-success, #67c23a);
}
.gt-wp-word-editor__save-status.save-status--saving {
  color: var(--el-color-warning, #e6a23c);
}
.gt-wp-word-editor__save-status.save-status--unsaved {
  color: var(--el-color-danger, #f56c6c);
}

/* Section styling */
.gt-wp-word-editor__main-section,
.gt-wp-word-editor__supplement-section,
.gt-wp-word-editor__generic-section {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--el-bg-color, #fff);
}
.gt-wp-word-editor__main-section {
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.gt-wp-word-editor__supplement-section {
  border-left: 3px solid var(--el-color-info, #909399);
}
.gt-wp-word-editor__generic-section {
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
  min-height: 500px;
}

.gt-wp-word-editor__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-wp-word-editor__section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-wp-word-editor__version-select {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gt-wp-word-editor__version-select :deep(.is-recommended .el-radio-button__inner) {
  border-color: var(--gt-color-primary, #4b2d77);
  color: var(--gt-color-primary, #4b2d77);
}

.gt-wp-word-editor__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.gt-wp-word-editor__supplement-status {
  margin-bottom: 8px;
}
.gt-wp-word-editor__supplement-hint {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
  margin: 0;
}

.gt-wp-word-editor__info {
  margin-top: 16px;
}

/* Generic mode editor area */
.gt-wp-word-editor__editor-area {
  width: 100%;
  height: 600px;
}
.gt-wp-word-editor__oo-container {
  width: 100%;
  height: 100%;
}
.gt-wp-word-editor__degraded-generic {
  padding: 24px;
  text-align: center;
}

/* Mode switch (Task 5.1) */
.gt-wp-word-editor__mode-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.gt-wp-word-editor__save-indicator {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}
.gt-wp-word-editor__save-indicator.save-status--saved {
  color: var(--el-color-success, #67c23a);
}
.gt-wp-word-editor__save-indicator.save-status--saving {
  color: var(--el-color-warning, #e6a23c);
}
.gt-wp-word-editor__save-indicator.save-status--unsaved {
  color: var(--el-color-danger, #f56c6c);
}
.gt-wp-word-editor__structured-area {
  min-height: 400px;
}
.gt-wp-word-editor__structured-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 6px;
  background: var(--el-fill-color-lighter, #f5f7fa);
}
.gt-wp-word-editor__oo-toolbar {
  margin-bottom: 8px;
}
.gt-wp-word-editor__oo-container.is-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  height: 100vh !important;
}
</style>
