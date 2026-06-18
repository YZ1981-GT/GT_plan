<!--
  WorkpaperWordEditor.vue — Word 模板底稿编辑器（A16 声明书等）

  布局：
  ┌─ 主声明书（A16-1~6 互斥 radio，推荐项置顶 + badge）──┐
  │  [OnlyOffice] [下载] [上传]  签回: pending/sent/signed │
  ├─ A13 错报 alert ─────────────────────────────────────┤
  ├─ 补充声明 A16-7 [toggle] ────────────────────────────┤
  │  （启用后）独立编辑/签回，scope word_template:A16:A16-7 │
  └─ 编制信息（占位符预览）──────────────────────────────┘
-->
<template>
  <div class="gt-wp-word-editor">
    <!-- ═══ 主声明书区 A16-1~6 ═══ -->
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
          </el-radio-button>
        </el-radio-group>
      </div>

      <!-- 主版本操作栏 -->
      <div class="gt-wp-word-editor__toolbar">
        <el-button type="primary" size="small" @click="openEditor('main')" :loading="loading">
          {{ onlyofficeAvailable ? '📝 在线编辑' : '📝 编辑（降级）' }}
        </el-button>
        <el-button size="small" @click="downloadTemplate('main')">⬇️ 下载模板</el-button>
        <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true; uploadTarget = 'main'">⬆️ 上传</el-button>
        <el-divider direction="vertical" />
        <el-button-group>
          <el-button size="small" :type="signStatus === 'sent' ? 'warning' : 'default'" @click="updateSignStatus('sent')" :disabled="signStatus === 'signed'">
            📤 标记已发送
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

        <!-- A16-7 独立操作栏 -->
        <div class="gt-wp-word-editor__toolbar">
          <el-button type="primary" size="small" @click="openEditor('supplement')" :loading="supplementLoading">
            {{ onlyofficeAvailable ? '📝 编辑 A16-7' : '📝 编辑（降级）' }}
          </el-button>
          <el-button size="small" @click="downloadTemplate('supplement')">⬇️ 下载 A16-7</el-button>
          <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true; uploadTarget = 'supplement'">⬆️ 上传</el-button>
          <el-divider direction="vertical" />
          <el-button-group>
            <el-button size="small" :type="supplementSignStatus === 'sent' ? 'warning' : 'default'" @click="updateSupplementSignStatus('sent')" :disabled="supplementSignStatus === 'signed'">
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

    <!-- ═══ 编制信息（占位符预览）═══ -->
    <div class="gt-wp-word-editor__info">
      <el-descriptions :column="2" border size="small" title="编制信息（自动预填占位符）">
        <el-descriptions-item label="客户名称">{{ placeholders.client_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="审计期间">{{ placeholders.audit_period || '—' }}</el-descriptions-item>
        <el-descriptions-item label="签字合伙人">{{ placeholders.partner_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="选用版本">{{ selectedVersionLabel }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- OnlyOffice 编辑弹窗 -->
    <OnlyOfficeEditor
      v-if="editorVisible"
      v-model:visible="editorVisible"
      :document-url="documentUrl"
      :document-key="documentKey"
      :title="editorTitle"
      :mode="readonly ? 'view' : 'edit'"
      @saved="onSaved"
    />

    <!-- 降级提示 -->
    <div v-if="!onlyofficeAvailable" class="gt-wp-word-editor__degraded">
      <el-alert type="info" :closable="false" show-icon>
        OnlyOffice 不可用，请下载模板到本地编辑后上传。
      </el-alert>
    </div>

    <!-- ═══ 签署日期对话框（CW-76：A16 主版本 signed 必填） ═══ -->
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
          <p>拖拽或点击上传编辑完成的声明书文件（.docx）</p>
        </div>
      </el-upload>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'

const props = defineProps<{
  wpId: string
  sheetName?: string
  htmlData?: any
  schema?: any
  readonly?: boolean
}>()

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

// ─── State ───
const loading = ref(false)
const supplementLoading = ref(false)
const editorVisible = ref(false)
const showUpload = ref(false)
const uploadTarget = ref<'main' | 'supplement'>('main')
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')
const editorTitle = ref('管理层声明书')
const signStatus = ref<string>('pending')
const supplementSignStatus = ref<string>('pending')
const supplementEnabled = ref(false)
const misstatementSummary = ref('')
const misstatementLoaded = ref(false)
const selectedVersion = ref('A16-1')
// CW-76: cached dates for sign_date default
const cachedReportDate = ref<string>('')
const cachedAuditPeriodEnd = ref<string>('')

const SUPPLEMENT_CODE = 'A16-7'

// ─── CW-76: sign date dialog state ───
const showSignDateDialog = ref(false)
const signDateValue = ref<string>('')
const pendingSignTarget = ref<'main' | 'supplement'>('main')

const placeholders = reactive({
  client_name: '',
  audit_period: '',
  partner_name: '',
  uncorrected_misstatements: '',
})

// ─── Template Versions (A16-1~6 only, A16-7 is separate) ───
interface TemplateVersion {
  code: string
  label: string
  recommended: boolean
}

const mainTemplateVersions = ref<TemplateVersion[]>([
  { code: 'A16-1', label: '一般财报', recommended: false },
  { code: 'A16-2', label: '整合审计', recommended: false },
  { code: 'A16-3', label: 'IPO申报', recommended: false },
  { code: 'A16-4', label: 'IPO季度', recommended: false },
  { code: 'A16-5', label: '新三板', recommended: false },
  { code: 'A16-6', label: '企业债', recommended: false },
])

// Sorted: recommended version on top, then original order
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

// ─── Sign status computed ───
const mainSignStatusLabel = computed(() => {
  const m: Record<string, string> = { pending: '待编辑', sent: '已发送', signed: '已签回' }
  return m[signStatus.value] || '待编辑'
})

const mainSignStatusType = computed(() => {
  if (signStatus.value === 'signed') return 'success'
  if (signStatus.value === 'sent') return 'warning'
  return 'info'
})

const supplementSignLabel = computed(() => {
  const m: Record<string, string> = { pending: '待编辑', sent: '已发送', signed: '已签回' }
  return m[supplementSignStatus.value] || '待编辑'
})

const supplementSignStatusType = computed(() => {
  if (supplementSignStatus.value === 'signed') return 'success'
  if (supplementSignStatus.value === 'sent') return 'warning'
  return 'info'
})

const uploadHeaders = computed(() => {
  const token = sessionStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

// ─── Methods ───
async function loadProjectInfo() {
  try {
    const info = await api.get<any>(`/api/projects/${projectId.value}`)
    const d = info?.data || info
    placeholders.client_name = d?.client_name || d?.name || ''
    placeholders.audit_period = d?.audit_period_end ? `${d.audit_year || ''}年度` : ''
    placeholders.partner_name = d?.partner_name || ''

    // CW-76: cache audit_period_end for sign_date default
    if (d?.audit_period_end) {
      cachedAuditPeriodEnd.value = typeof d.audit_period_end === 'string'
        ? d.audit_period_end.slice(0, 10)
        : ''
    }

    // CW-76: try to get audit_report.report_date as preferred default
    try {
      const year = getAuditYear()
      const report = await api.get<any>(`/api/audit-report?project_id=${projectId.value}&year=${year}`)
      const rd = report?.report_date || report?.data?.report_date
      if (rd) {
        cachedReportDate.value = typeof rd === 'string' ? rd.slice(0, 10) : ''
      }
    } catch { /* audit_report may not exist yet */ }

    // ─── Version resolution priority: URL query > persisted > recommendation > default A16-1 ───
    let resolvedVersion: string | null = null

    // 1. URL query override (highest priority)
    const qv = route.query.version as string
    if (qv && mainTemplateVersions.value.some(v => v.code === qv)) {
      resolvedVersion = qv
    }

    // 2. Persisted field_override (second priority)
    if (!resolvedVersion) {
      const persisted = await loadPersistedVersion()
      if (persisted) {
        resolvedVersion = persisted
      }
    }

    // 3. API recommendation (third priority)
    try {
      const rec = await api.get<any>(`/api/projects/${projectId.value}/a16/recommended-version`)
      const mainCode = rec?.main?.code
      if (mainCode) {
        for (const v of mainTemplateVersions.value) {
          v.recommended = v.code === mainCode
        }
        // Only use recommendation if no higher-priority source resolved
        if (!resolvedVersion) {
          resolvedVersion = mainCode
        }
      }
      // A16-7 supplement recommendation
      if (rec?.supplement) {
        supplementEnabled.value = true
      }
    } catch { /* fallback: no recommendation available */ }

    // 4. Apply resolved version (or keep default A16-1)
    if (resolvedVersion) {
      selectedVersion.value = resolvedVersion
    }

    // If URL query was used, also persist it for consistency
    if (qv && qv === resolvedVersion) {
      persistSelectedVersion(qv)
    }
  } catch { /* ignore */ }
}

async function loadMisstatementSummary() {
  try {
    const year = getAuditYear()
    const r = await api.get<any>(
      `/api/projects/${projectId.value}/misstatements/for-letter`,
      { params: { year } },
    )
    const text = r?.summary || r?.data?.summary || ''
    misstatementSummary.value = (text === '无未更正错报。') ? '' : text
    misstatementLoaded.value = true
    placeholders.uncorrected_misstatements = misstatementSummary.value || '无'
  } catch {
    misstatementLoaded.value = true
  }
}

async function checkHealth() {
  try {
    const r = await api.get<{ available: boolean }>('/api/deliverables/onlyoffice/health')
    onlyofficeAvailable.value = r?.available ?? false
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function loadSignStatus() {
  try {
    const info = await api.get<any>(
      `/api/workpapers/${props.wpId}/file-info?version=${encodeURIComponent(selectedVersion.value)}`,
    )
    signStatus.value = info?.sign_status || 'pending'
  } catch { /* ignore */ }
}

async function loadSupplementSignStatus() {
  if (!supplementEnabled.value) return
  try {
    const info = await api.get<any>(
      `/api/workpapers/${props.wpId}/file-info?version=${encodeURIComponent(SUPPLEMENT_CODE)}`,
    )
    supplementSignStatus.value = info?.sign_status || 'pending'
  } catch { /* ignore */ }
}

async function updateSignStatus(status: string) {
  // CW-76: 主版本签回时必须弹窗获取签署日期
  if (status === 'signed') {
    pendingSignTarget.value = 'main'
    // Pre-fill sign_date with audit report date or audit_period_end
    signDateValue.value = getDefaultSignDate()
    showSignDateDialog.value = true
    return
  }
  await _doUpdateSignStatus(status)
}

/** 实际执行签回状态更新（可能带 sign_date） */
async function _doUpdateSignStatus(status: string, signDate?: string) {
  try {
    const payload: Record<string, any> = {
      status,
      version: selectedVersion.value,
    }
    if (signDate) {
      payload.sign_date = signDate
    }
    await api.post(`/api/workpapers/${props.wpId}/sign-status`, payload)
    signStatus.value = status
    ElMessage.success(status === 'signed' ? '已标记签回' : '已标记发送')
  } catch {
    // Fallback: field_overrides
    try {
      const year = getAuditYear()
      await api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year,
        scope: `word_template:A16:${selectedVersion.value}`,
        item_key: 'sign_status',
        field: 'value',
        value: status,
      })
      signStatus.value = status
      ElMessage.success(status === 'signed' ? '已标记签回' : '已标记发送')
    } catch {
      ElMessage.error('更新状态失败')
    }
  }
}

/** CW-76: 确认签署日期后执行签回 */
async function confirmSignDate() {
  showSignDateDialog.value = false
  if (pendingSignTarget.value === 'main') {
    await _doUpdateSignStatus('signed', signDateValue.value)
  } else {
    await _doUpdateSupplementSignStatus('signed', signDateValue.value)
  }
}

/** 获取默认签署日期：优先审计报告日期，降级审计期间截止日 */
function getDefaultSignDate(): string {
  // 从 placeholders 中获取审计报告日期（如果已从 project info / audit_report 取得）
  if (cachedReportDate.value) {
    return cachedReportDate.value
  }
  if (cachedAuditPeriodEnd.value) {
    return cachedAuditPeriodEnd.value
  }
  // 降级：当天
  return new Date().toISOString().slice(0, 10)
}

async function updateSupplementSignStatus(status: string) {
  // A16-7 签回: sign_date 可选，不 push 到审计报告
  if (status === 'signed') {
    // 直接签回不弹日期框（A16-7 不需要）
    await _doUpdateSupplementSignStatus(status)
    return
  }
  await _doUpdateSupplementSignStatus(status)
}

async function _doUpdateSupplementSignStatus(status: string, _signDate?: string) {
  try {
    const payload: Record<string, any> = {
      status,
      version: SUPPLEMENT_CODE,
    }
    // A16-7 不传 sign_date（不 push 到审计报告）
    await api.post(`/api/workpapers/${props.wpId}/sign-status`, payload)
    supplementSignStatus.value = status
    ElMessage.success(status === 'signed' ? 'A16-7 已签回' : 'A16-7 已发送')
  } catch {
    // Fallback: field_overrides
    try {
      const year = getAuditYear()
      await api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year,
        scope: `word_template:A16:${SUPPLEMENT_CODE}`,
        item_key: 'sign_status',
        field: 'value',
        value: status,
      })
      supplementSignStatus.value = status
      ElMessage.success(status === 'signed' ? 'A16-7 已签回' : 'A16-7 已发送')
    } catch {
      ElMessage.error('更新 A16-7 状态失败')
    }
  }
}

async function onSupplementToggle(enabled: boolean | string | number) {
  // Persist the enabled state via field_overrides
  try {
    const year = getAuditYear()
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value,
      year,
      scope: `word_template:A16:${SUPPLEMENT_CODE}`,
      item_key: 'enabled',
      field: 'value',
      value: String(!!enabled),
    })
    if (enabled) {
      loadSupplementSignStatus()
    }
  } catch { /* non-critical */ }
}

async function onVersionChange(code: string) {
  selectedVersion.value = code
  editorTitle.value = `管理层声明书 (${selectedVersionLabel.value})`
  // Persist selected_version via field_overrides
  persistSelectedVersion(code)
  // Load sign_status for the new version (independent per version)
  await loadSignStatus()
}

/**
 * 持久化 selected_version 到 field_overrides (scope=word_template:A16)
 * 切换版本时调用，刷新后可恢复选择。
 */
async function persistSelectedVersion(code: string) {
  try {
    const year = getAuditYear()
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value,
      year,
      scope: 'word_template:A16',
      item_key: 'selected_version',
      field: 'value',
      value: code,
    })
  } catch { /* 非关键路径，静默失败 */ }
}

/**
 * 从 field_overrides 读取已持久化的 selected_version
 * 返回 null 表示无持久化记录。
 */
async function loadPersistedVersion(): Promise<string | null> {
  try {
    const year = getAuditYear()
    const overrides = await api.get<Record<string, Record<string, any>>>(
      '/api/workpapers/field-overrides',
      { params: { project_id: projectId.value, year, scope: 'word_template:A16' } },
    )
    const val = overrides?.selected_version?.value
    if (val && mainTemplateVersions.value.some(v => v.code === val)) {
      return val
    }
  } catch { /* ignore */ }
  return null
}

/** 获取审计年度（优先 route query，否则当前年份） */
function getAuditYear(): number {
  return parseInt(route.query.year as string) || new Date().getFullYear()
}

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
    })
    documentUrl.value = config.document_url || ''
    documentKey.value = config.document_key || `wp-${props.wpId}-${version}-${Date.now()}`
    editorTitle.value = target === 'supplement'
      ? '关联交易声明书 (A16-7)'
      : `声明书 (${selectedVersionLabel.value})`
    editorVisible.value = true
  } catch (e: any) {
    ElMessage.error('打开编辑器失败：' + (e?.message || '未知错误'))
  } finally {
    loadingRef.value = false
  }
}

async function downloadTemplate(target: 'main' | 'supplement') {
  const version = target === 'supplement' ? SUPPLEMENT_CODE : selectedVersion.value
  const label = target === 'supplement' ? 'A16-7 关联交易声明书' : `${selectedVersion.value} 管理层声明书`
  try {
    const url = `/api/projects/${projectId.value}/wp-templates/${version}/prefilled-download`
    const token = sessionStorage.getItem('token') || ''
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error('下载失败')
    const blob = await r.blob()
    const obj = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = obj
    a.download = `${label}.docx`
    a.click()
    URL.revokeObjectURL(obj)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

function onSaved() {
  ElMessage.success('文件已保存')
  loadSignStatus()
  if (supplementEnabled.value) loadSupplementSignStatus()
}

function onUploadSuccess() {
  showUpload.value = false
  ElMessage.success('上传成功')
  if (uploadTarget.value === 'supplement') {
    loadSupplementSignStatus()
  } else {
    loadSignStatus()
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  checkHealth()
  await loadProjectInfo()
  loadMisstatementSummary()
  await loadSignStatus()
  if (supplementEnabled.value) loadSupplementSignStatus()
})
</script>

<style scoped>
.gt-wp-word-editor {
  padding: 16px;
}

/* Section styling */
.gt-wp-word-editor__main-section,
.gt-wp-word-editor__supplement-section {
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

/* Recommended version highlight */
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

.gt-wp-word-editor__degraded {
  margin-bottom: 12px;
}
.gt-wp-word-editor__info {
  margin-top: 16px;
}
</style>
