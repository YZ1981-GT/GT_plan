<template>
  <div class="gt-legal-hub" data-testid="legal-hub-card">
    <span class="gt-legal-hub__label">函证中心</span>
    <span v-if="loading" class="gt-legal-hub__muted">加载中…</span>
    <template v-else-if="hub">
      <el-tag size="small" :type="statusTag" data-testid="legal-hub-status">{{ confirmationStatusLabel(hub.status) }}</el-tag>
      <el-button link type="primary" size="small" data-testid="legal-hub-attachments" @click="drawerOpen = true">
        发函件 {{ hub.outbound_count ?? 0 }} 份 · 回函件 {{ hub.inbound_count ?? 0 }} 份
      </el-button>
      <el-button
        v-if="!readonly && firm && firm !== hub.counterparty"
        link
        size="small"
        :loading="saving"
        data-testid="legal-hub-rename"
        @click="rename"
      >函证对象更新为「{{ firm }}」</el-button>
    </template>
    <template v-else>
      <span class="gt-legal-hub__muted">未登记</span>
      <el-tooltip v-if="!readonly" :disabled="!!firm" content="请先在收件人里填写律师事务所" placement="top">
        <span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="!firm"
            :loading="saving"
            data-testid="legal-hub-register"
            @click="register"
          >登记到函证中心</el-button>
        </span>
      </el-tooltip>
    </template>
    <ConfirmationAttachmentDrawer
      v-if="hub && pid"
      v-model:visible="drawerOpen"
      :confirmation-id="hub.id"
      :project-id="pid"
      :counterparty-name="hub.counterparty"
      :readonly="readonly"
      @updated="load"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * A12-1 律师询证函 ↔ 函证中心（spec attachment-confirmation-evidence-loop 需求 5.2，ADR-ACE-06）
 *
 * 一张 A12-1 底稿 = 一封给一家律师事务所的函 ⇒ 对应函证中心里 `wp_id = 本底稿` 且类型为律师的那一笔。
 * 未登记时可一键登记（函证对象 = 收件人律师事务所）；事务所名称改了可一键更新；件数与状态取函证中心列表；
 * 发函件 / 回函件用与函证中心同一个附件抽屉。只读时只显示。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { routeProjectId } from '@/components/attachment/rowEvidence'
import ConfirmationAttachmentDrawer from './ConfirmationAttachmentDrawer.vue'
import { confirmationStatusLabel } from './coordination/confirmationTypeLabels'

interface HubItem {
  id: string
  confirm_type: string
  counterparty: string
  status: string
  wp_id: string | null
  outbound_count?: number
  inbound_count?: number
}

const props = withDefaults(
  defineProps<{ wpId: string; projectId?: string | null; firmName?: string | null; readonly?: boolean }>(),
  { projectId: null, firmName: null, readonly: false },
)

const routePid = routeProjectId()
const pid = computed(() => props.projectId || routePid)
const firm = computed(() => (props.firmName || '').trim())

const hub = ref<HubItem | null>(null)
const loading = ref(false)
const saving = ref(false)
const drawerOpen = ref(false)

const STATUS_TAGS: Record<string, 'info' | 'warning' | 'primary' | 'success' | 'danger'> = {
  pending: 'info', sent: 'warning', returned: 'primary', matched: 'success', discrepancy: 'danger',
}
const statusTag = computed(() => STATUS_TAGS[hub.value?.status ?? ''] ?? 'info')

async function load(): Promise<void> {
  if (!pid.value || !props.wpId) return
  loading.value = true
  try {
    const res = await api.get<{ items?: HubItem[] }>(`/api/projects/${pid.value}/confirmations`, { _silent: true } as any)
    hub.value = (res?.items ?? []).find((it) => it.wp_id === props.wpId && it.confirm_type === 'legal') ?? null
  } catch {
    hub.value = null // 函证中心读不到不影响编制
  } finally {
    loading.value = false
  }
}

async function register(): Promise<void> {
  if (!firm.value || !pid.value) return
  saving.value = true
  try {
    await api.post(`/api/projects/${pid.value}/confirmations`,
      { confirm_type: 'legal', counterparty: firm.value, wp_id: props.wpId }, { _silent: true } as any)
    ElMessage.success('已登记到函证中心')
    await load()
  } catch (e) {
    handleApiError(e, '登记到函证中心')
  } finally {
    saving.value = false
  }
}

async function rename(): Promise<void> {
  if (!hub.value || !firm.value || !pid.value) return
  saving.value = true
  try {
    await api.put(`/api/projects/${pid.value}/confirmations/${hub.value.id}`, { counterparty: firm.value }, { _silent: true } as any)
    ElMessage.success('函证对象已更新')
    await load()
  } catch (e) {
    handleApiError(e, '更新函证对象')
  } finally {
    saving.value = false
  }
}

onMounted(load)
watch(() => [pid.value, props.wpId], () => { void load() })
</script>

<style scoped>
.gt-legal-hub {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
}
.gt-legal-hub__label {
  color: var(--gt-color-text-secondary, #606266);
}
.gt-legal-hub__muted {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
