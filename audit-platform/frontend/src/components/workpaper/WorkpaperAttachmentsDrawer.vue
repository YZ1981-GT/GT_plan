<script setup lang="ts">
/**
 * WorkpaperAttachmentsDrawer — 底稿「本底稿关联附件」面板（双向可见）
 *
 * 复用反查端点 GET /api/working-papers/{wpId}/attachments（见 attachments.py），
 * 列出关联到本底稿的证据附件：名称/类型/关联类型/来源/大小/时间 + 预览/下载 +
 * 「在附件管理中查看」+ 可编辑时「解除关联」。
 *
 * Wave 2：来源 tag；Wave 3：解除关联（canEdit 门控）；Wave 4：证据类型声明 / 缺证据提示。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'
import { downloadFile } from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { View, Download, TopRight, Link } from '@element-plus/icons-vue'
import AttachmentPreview from '@/components/extension/AttachmentPreview.vue'
import { SOURCE_LABEL, resolveSourceKeys, canUnlinkSources } from './workpaperAttachmentSources'
import { uploadAndAssociateToWorkpaper } from './composables/ocrAttachmentLinkage'

type EvidenceRequirement = { type: string; label: string; satisfied: boolean }

type StaleInfo = {
  has_stale: boolean
  level?: 'definite' | 'conservative' | null
  items?: Array<{ kind?: string; id?: string; reason?: string; label?: string }>
  project_id?: string | null
}

const props = defineProps<{
  modelValue: boolean
  wpId: string
  projectId: string
  wpCode?: string
  /** 有底稿编辑权时显示解除关联；默认 false（只读） */
  canEdit?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const router = useRouter()
const loading = ref(false)
const unlinkingId = ref<string | null>(null)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const rows = ref<any[]>([])
const evidenceRequirements = ref<EvidenceRequirement[]>([])
const staleInfo = ref<StaleInfo | null>(null)

const missingEvidence = computed(() =>
  evidenceRequirements.value.filter((r) => !r.satisfied),
)

const showStaleTip = computed(() => !!staleInfo.value?.has_stale)

const hasConfirmationOnly = computed(() =>
  rows.value.some((row) => {
    const keys = resolveSourceKeys(row)
    return keys.includes('confirmation') && !canUnlinkSources(keys)
  }),
)

const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const previewType = ref('')

const ASSOC_LABEL: Record<string, string> = {
  evidence: '审计证据',
  support: '支持文件',
  confirmation: '函证回函',
  contract: '合同',
  bank_statement: '银行对账单',
}

async function load() {
  if (!props.wpId) {
    rows.value = []
    evidenceRequirements.value = []
    staleInfo.value = null
    return
  }
  loading.value = true
  try {
    const data: any = await api.get(`/api/working-papers/${props.wpId}/attachments`)
    const envelope = Array.isArray(data) ? { items: data } : (data || {})
    rows.value = envelope.items ?? []
    evidenceRequirements.value = Array.isArray(envelope.evidence_requirements)
      ? envelope.evidence_requirements
      : []
    staleInfo.value = envelope.stale_info && typeof envelope.stale_info === 'object'
      ? envelope.stale_info
      : null
  } catch {
    rows.value = []
    evidenceRequirements.value = []
    staleInfo.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (open) => { if (open) load() }, { immediate: true })

function preview(row: any) {
  previewUrl.value = P_att.preview(row.id)
  previewName.value = row.file_name
  previewType.value = row.file_type || ''
  previewVisible.value = true
}

async function download(row: any) {
  try { await downloadFile(P_att.download(row.id)) }
  catch (e: any) { handleApiError(e, '下载') }
}

/** 跳到附件管理页并高亮定位该附件（消费 AttachmentManagement 的 ?id=） */
function viewInHub(row: any) {
  emit('update:modelValue', false)
  router.push({ path: `/projects/${props.projectId}/attachments`, query: { id: row.id } })
}

function goHub() {
  emit('update:modelValue', false)
  router.push({ path: `/projects/${props.projectId}/attachments` })
}

function goGovernance() {
  const pid = staleInfo.value?.project_id || props.projectId
  if (!pid) return
  emit('update:modelValue', false)
  router.push({ name: 'EvidenceGovernanceCenter', params: { projectId: pid } })
}

function showUnlink(row: any): boolean {
  return !!props.canEdit && canUnlinkSources(resolveSourceKeys(row))
}

async function unlink(row: any) {
  if (!props.canEdit || !props.wpId || !row?.id) return
  try {
    await ElMessageBox.confirm(
      `确定解除「${row.file_name || '该附件'}」与本底稿的关联？不会删除附件文件本身。`,
      '解除关联',
      { type: 'warning', confirmButtonText: '解除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  unlinkingId.value = row.id
  try {
    await api.delete(`/api/working-papers/${props.wpId}/attachments/${row.id}/link`)
    ElMessage.success('已解除关联')
    await load()
  } catch (e: any) {
    handleApiError(e, '解除关联')
  } finally {
    unlinkingId.value = null
  }
}

function pickUploadFile() {
  fileInputRef.value?.click()
}

async function onUploadSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.canEdit || !props.wpId || !props.projectId) return
  uploading.value = true
  try {
    await uploadAndAssociateToWorkpaper(props.projectId, props.wpId, file)
    ElMessage.success('已上传并关联到本底稿')
    await load()
  } catch (e: any) {
    handleApiError(e, '上传并关联')
  } finally {
    uploading.value = false
  }
}

function fileEmoji(type: string): string {
  const t = (type || '').toLowerCase()
  if (t.includes('pdf')) return '📕'
  if (t.includes('doc') || t.includes('word')) return '📘'
  if (t.includes('xls') || t.includes('excel')) return '📗'
  if (t.includes('ppt')) return '📙'
  if (/png|jpg|jpeg|gif|bmp|webp|tif|heic|image/.test(t)) return '🖼️'
  if (/zip|rar|7z|archive/.test(t)) return '📦'
  if (/eml|msg|email/.test(t)) return '✉️'
  if (/ofd|dwg/.test(t)) return '📐'
  return '📄'
}
function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
function formatDate(d: string): string {
  if (!d) return '-'
  const date = new Date(d)
  return `${date.getMonth() + 1}月${date.getDate()}日`
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="`本底稿关联附件${wpCode ? '（' + wpCode + '）' : ''}`"
    size="480px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="wp-att-drawer">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="wp-att-tip"
        :title="canEdit
          ? '可查看本底稿关联证据；错误关联可在此解除（不删文件）。检查项级证据请在检查项页查看（本面板不收录）。'
          : '此处仅展示已关联到本底稿的证据附件。检查项级证据请在检查项页查看。'"
      />
      <div v-if="canEdit" class="wp-att-actions-bar">
        <el-button type="primary" size="small" :loading="uploading" @click="pickUploadFile">
          上传并关联到本底稿
        </el-button>
        <el-button size="small" @click="goHub">打开附件管理</el-button>
        <input
          ref="fileInputRef"
          type="file"
          class="wp-att-file-input"
          @change="onUploadSelected"
        >
      </div>

      <el-alert
        v-if="hasConfirmationOnly"
        type="warning"
        :closable="false"
        show-icon
        class="wp-att-tip"
        data-testid="confirmation-unlink-tip"
        title="纯函证来源的附件请在函证模块调整关联；本面板不提供解除（不改函证编制链路）。"
      />

      <el-alert
        v-if="showStaleTip"
        :type="staleInfo?.level === 'definite' ? 'error' : 'warning'"
        :closable="false"
        show-icon
        class="wp-att-stale"
        data-testid="stale-info"
      >
        <template #title>
          <span v-if="staleInfo?.level === 'definite'">
            存在明确失效的证据引用（{{ staleInfo?.items?.length || 0 }} 条）
          </span>
          <span v-else>关联证据/依赖可能已过期（保守提示）</span>
        </template>
        <div class="wp-att-stale__body">
          <p v-if="staleInfo?.level === 'definite' && staleInfo?.items?.length">
            {{ staleInfo.items[0].label || '证据引用已失效' }}
            <span v-if="(staleInfo.items?.length || 0) > 1">
              等 {{ staleInfo.items.length }} 项
            </span>
          </p>
          <p v-else>底稿预填或上游依赖已标脏，请在治理中心核对后再采信关联证据。</p>
          <el-button type="primary" link size="small" @click="goGovernance">
            前往证据链治理中心查看详情
          </el-button>
        </div>
      </el-alert>

      <div
        v-if="evidenceRequirements.length"
        class="wp-att-evidence-req"
        data-testid="evidence-requirements"
      >
        <div class="wp-att-evidence-req__title">应收集证据</div>
        <ul class="wp-att-evidence-req__list">
          <li
            v-for="req in evidenceRequirements"
            :key="req.type"
            class="wp-att-evidence-req__item"
            :data-satisfied="req.satisfied ? '1' : '0'"
          >
            <span v-if="req.satisfied" class="wp-att-evidence-req__ok">✓ {{ req.label }}</span>
            <span v-else class="wp-att-evidence-req__miss">⚠ 缺「{{ req.label }}」证据</span>
          </li>
        </ul>
        <el-alert
          v-if="missingEvidence.length"
          type="warning"
          :closable="false"
          show-icon
          class="wp-att-evidence-req__alert"
          :title="`尚缺 ${missingEvidence.length} 类证据（不阻断编制，请尽快补齐）`"
        />
      </div>

      <el-empty v-if="!loading && rows.length === 0" description="本底稿暂无关联附件">
        <el-button type="primary" @click="goHub">前往附件管理上传并关联</el-button>
      </el-empty>

      <div v-else class="wp-att-list">
        <div v-for="row in rows" :key="row.id" class="wp-att-item">
          <div class="wp-att-item__icon">{{ fileEmoji(row.file_type) }}</div>
          <div class="wp-att-item__info">
            <div class="wp-att-item__name" :title="row.file_name" @click="preview(row)">{{ row.file_name }}</div>
            <div class="wp-att-item__meta">
              <el-tag
                v-for="src in resolveSourceKeys(row)"
                :key="src"
                size="small"
                effect="plain"
                round
                class="wp-att-source-tag"
                :type="SOURCE_LABEL[src]?.type || 'info'"
                :data-source="src"
              >{{ SOURCE_LABEL[src]?.label || src }}</el-tag>
              <el-tag v-if="row.association_type" size="small" effect="plain" round>
                {{ ASSOC_LABEL[row.association_type] || row.association_type }}
              </el-tag>
              <span>{{ row.file_type || '-' }}</span>
              <span>{{ formatSize(row.file_size) }}</span>
              <span>{{ formatDate(row.created_at) }}</span>
            </div>
          </div>
          <div class="wp-att-item__actions">
            <el-tooltip content="预览" placement="top">
              <el-button circle size="small" @click="preview(row)"><el-icon><View /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip content="下载" placement="top">
              <el-button circle size="small" @click="download(row)"><el-icon><Download /></el-icon></el-button>
            </el-tooltip>
            <el-tooltip v-if="showUnlink(row)" content="解除关联" placement="top">
              <el-button
                circle
                size="small"
                type="danger"
                class="wp-att-unlink-btn"
                :loading="unlinkingId === row.id"
                @click="unlink(row)"
              >
                <el-icon><Link /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="在附件管理中查看" placement="top">
              <el-button circle size="small" @click="viewInHub(row)"><el-icon><TopRight /></el-icon></el-button>
            </el-tooltip>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="goHub">前往附件管理</el-button>
      <el-button type="primary" @click="emit('update:modelValue', false)">关闭</el-button>
    </template>

    <AttachmentPreview
      v-model="previewVisible"
      :file-url="previewUrl"
      :file-name="previewName"
      :file-type="previewType"
      @close="previewVisible = false"
    />
  </el-drawer>
</template>

<script lang="ts">
import { View, Download, TopRight, Link } from '@element-plus/icons-vue'
export default { components: { View, Download, TopRight, Link } }
</script>

<style scoped>
.wp-att-tip { margin-bottom: 12px; }
.wp-att-actions-bar { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.wp-att-file-input { display: none; }
.wp-att-stale { margin-bottom: 12px; }
.wp-att-stale__body { font-size: 12px; line-height: 1.6; }
.wp-att-stale__body p { margin: 0 0 4px; }
.wp-att-evidence-req {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 8px;
  background: var(--gt-color-fill-blank, #fafafa);
}
.wp-att-evidence-req__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin-bottom: 6px;
}
.wp-att-evidence-req__list {
  margin: 0;
  padding-left: 1.1em;
  font-size: 12px;
  line-height: 1.7;
  color: var(--gt-color-text-regular, #606266);
}
.wp-att-evidence-req__ok { color: var(--el-color-success, #67c23a); }
.wp-att-evidence-req__miss { color: var(--el-color-warning, #e6a23c); font-weight: 600; }
.wp-att-evidence-req__alert { margin-top: 8px; }
.wp-att-list { display: flex; flex-direction: column; gap: 8px; }
.wp-att-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border: 1px solid var(--gt-color-border-light, #eee); border-radius: 8px;
  transition: all 0.2s;
}
.wp-att-item:hover { border-color: var(--gt-purple-light, #d8b8ee); box-shadow: 0 2px 10px rgba(75,45,119,0.08); }
.wp-att-item__icon { font-size: 24px; flex-shrink: 0; }
.wp-att-item__info { flex: 1; min-width: 0; }
.wp-att-item__name {
  font-size: 13px; font-weight: 600; color: var(--gt-color-primary, #4b2d77); cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.wp-att-item__name:hover { text-decoration: underline; }
.wp-att-item__meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--gt-color-text-tertiary, #909399); flex-wrap: wrap; }
.wp-att-item__actions { display: flex; gap: 4px; flex-shrink: 0; }
</style>
