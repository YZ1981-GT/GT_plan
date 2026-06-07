<template>
  <!--
    LinkageTraceDrawer — 统一穿透面板（P1-2）
    =============================================================================
    以 el-drawer 展示 LinkageContract 列表：来源、口径、金额、状态、影响范围。
    支持跳转目标页面和复制引用信息。
    Requirements: 2.1, 2.2, 2.3
  -->
  <el-drawer
    :model-value="modelValue"
    title="数据穿透追溯"
    direction="rtl"
    size="420px"
    :destroy-on-close="true"
    class="gt-linkage-trace-drawer"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <!-- Loading -->
    <div v-if="loading" class="gt-trace-drawer__loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载联动数据...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="!contracts.length" class="gt-trace-drawer__empty">
      <el-empty description="暂无联动关系" :image-size="80" />
    </div>

    <!-- Contract list -->
    <div v-else class="gt-trace-drawer__list">
      <div
        v-for="(contract, idx) in contracts"
        :key="idx"
        class="gt-trace-card"
      >
        <!-- Header: source → target -->
        <div class="gt-trace-card__header">
          <el-tag size="small" :type="getSourceTagType(contract.source_type)">
            {{ getTypeLabel(contract.source_type) }}
          </el-tag>
          <span class="gt-trace-card__arrow">→</span>
          <el-tag size="small" :type="getSourceTagType(contract.target_type)">
            {{ getTypeLabel(contract.target_type) }}
          </el-tag>
          <!-- Status badge -->
          <el-tag
            v-if="contract.status !== 'current'"
            size="small"
            :type="getStatusTagType(contract.status)"
            class="gt-trace-card__status"
            effect="dark"
          >
            {{ getStatusLabel(contract.status) }}
          </el-tag>
          <!-- Conflict badge (P1-3.2) -->
          <el-tag
            v-if="contract.conflict_id"
            size="small"
            type="danger"
            effect="dark"
            class="gt-trace-card__conflict"
            @click="handleConflictClick(contract.conflict_id)"
          >
            冲突
          </el-tag>
        </div>

        <!-- Body: 口径 + 金额 -->
        <div class="gt-trace-card__body">
          <div v-if="contract.basis" class="gt-trace-card__row">
            <span class="gt-trace-card__label">口径</span>
            <span class="gt-trace-card__value">{{ contract.basis }}</span>
          </div>
          <div v-if="contract.amount" class="gt-trace-card__row">
            <span class="gt-trace-card__label">金额</span>
            <span class="gt-trace-card__value gt-amt">{{ formatAmount(contract.amount) }}</span>
          </div>
          <div class="gt-trace-card__row">
            <span class="gt-trace-card__label">置信度</span>
            <span class="gt-trace-card__value">{{ getConfidenceLabel(contract.confidence) }}</span>
          </div>
        </div>

        <!-- Footer: actions -->
        <div class="gt-trace-card__footer">
          <el-button
            type="primary"
            text
            size="small"
            :disabled="!contract.route"
            @click="handleJump(contract)"
          >
            跳转查看
          </el-button>
          <el-button
            text
            size="small"
            @click="handleCopy(contract)"
          >
            复制引用
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import type { LinkageContract, LinkageStatus } from '@/types/linkageContract'

export interface LinkageTraceDrawerProps {
  modelValue: boolean
  projectId: string
  sourceType?: string
  sourceId?: string
  cell?: string | null
  year?: number | null
}

const props = withDefaults(defineProps<LinkageTraceDrawerProps>(), {
  sourceType: '',
  sourceId: '',
  cell: null,
  year: null,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'open-conflict': [conflictId: string]
  'resolved': []
}>()

const router = useRouter()
const loading = ref(false)
const contracts = ref<LinkageContract[]>([])

// 当 drawer 打开且有 sourceType/sourceId 时自动查询
watch(
  () => props.modelValue,
  async (visible) => {
    if (visible && props.sourceType && props.sourceId) {
      await fetchTrace()
    }
    if (!visible) {
      contracts.value = []
    }
  },
  { immediate: true },
)

async function fetchTrace() {
  loading.value = true
  try {
    const params: Record<string, string> = {
      source_type: props.sourceType,
      source_id: props.sourceId,
    }
    if (props.cell) params.cell = props.cell
    if (props.year) params.year = String(props.year)

    const data: any = await api.get(
      `/api/projects/${props.projectId}/linkage/trace`,
      { params },
    )
    contracts.value = data?.contracts || []
  } catch (e) {
    contracts.value = []
  } finally {
    loading.value = false
  }
}

// ─── Type / status label helpers ───────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  trial_balance: '试算表',
  ledger: '序时账',
  audit_sheet: '审定表',
  workpaper: '底稿',
  adjustment: '调整分录',
  report: '报表',
  note: '附注',
  attachment: '附件',
  ai: 'AI 内容',
}

const STATUS_LABELS: Record<string, string> = {
  current: '最新',
  stale: '过期',
  conflict: '冲突',
  manual_override: '人工覆盖',
}

const CONFIDENCE_LABELS: Record<string, string> = {
  system: '系统计算',
  manual: '人工确认',
  ai_confirmed: 'AI 已确认',
  ai_suggested: 'AI 建议',
}

function getTypeLabel(type: string): string {
  return TYPE_LABELS[type] || type
}

function getStatusLabel(status: string): string {
  return STATUS_LABELS[status] || status
}

function getConfidenceLabel(confidence: string): string {
  return CONFIDENCE_LABELS[confidence] || confidence
}

function getSourceTagType(type: string): '' | 'success' | 'info' | 'warning' | 'danger' {
  const map: Record<string, '' | 'success' | 'info' | 'warning' | 'danger'> = {
    trial_balance: '',
    workpaper: 'success',
    note: 'info',
    report: 'warning',
    adjustment: 'danger',
  }
  return map[type] ?? 'info'
}

function getStatusTagType(status: string): '' | 'success' | 'info' | 'warning' | 'danger' {
  const map: Record<string, '' | 'success' | 'info' | 'warning' | 'danger'> = {
    stale: 'warning',
    conflict: 'danger',
    manual_override: 'info',
  }
  return map[status] ?? 'info'
}

function formatAmount(value: string | null | undefined): string {
  if (!value) return '—'
  const num = parseFloat(value)
  if (isNaN(num)) return value
  return `¥${num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// ─── Actions ───────────────────────────────────────────────────────────

function handleJump(contract: LinkageContract) {
  if (!contract.route) return
  emit('update:modelValue', false)
  router.push(contract.route)
}

function handleCopy(contract: LinkageContract) {
  const text = [
    `来源: ${getTypeLabel(contract.source_type)} [${contract.source_id}]`,
    `目标: ${getTypeLabel(contract.target_type)} [${contract.target_id}]`,
    contract.amount ? `金额: ${contract.amount}` : '',
    contract.basis ? `口径: ${contract.basis}` : '',
    `状态: ${getStatusLabel(contract.status)}`,
  ].filter(Boolean).join('\n')

  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('引用信息已复制')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}

// P1-3.3: 跳转冲突调解
function handleConflictClick(conflictId: string | null | undefined) {
  if (!conflictId) return
  emit('open-conflict', conflictId)
}
</script>

<style scoped>
.gt-trace-drawer__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px 16px;
  color: var(--gt-text-secondary, #999);
}

.gt-trace-drawer__loading .is-loading {
  animation: rotating 1.5s linear infinite;
}

.gt-trace-drawer__empty {
  padding: 40px 16px;
  text-align: center;
}

.gt-trace-drawer__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 4px;
}

.gt-trace-card {
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  transition: box-shadow 0.2s;
}

.gt-trace-card:hover {
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.1);
}

.gt-trace-card__header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.gt-trace-card__arrow {
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
}

.gt-trace-card__status {
  margin-left: auto;
}

.gt-trace-card__conflict {
  cursor: pointer;
}

.gt-trace-card__body {
  margin-bottom: 10px;
}

.gt-trace-card__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  font-size: 13px;
}

.gt-trace-card__label {
  flex-shrink: 0;
  width: 48px;
  color: var(--gt-text-secondary, #999);
  font-size: 12px;
}

.gt-trace-card__value {
  flex: 1;
  color: var(--gt-text-primary, #1a1a1a);
  word-break: break-all;
}

.gt-trace-card__footer {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}

.gt-amt {
  font-variant-numeric: tabular-nums;
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
