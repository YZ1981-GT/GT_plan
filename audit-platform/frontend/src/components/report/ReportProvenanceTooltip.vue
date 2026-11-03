<template>
  <el-tooltip
    placement="bottom"
    :show-after="350"
    :hide-after="0"
    popper-class="gt-report-provenance-tooltip__popper"
    @before-show="loadProvenance"
  >
    <template #content>
      <div class="gt-report-provenance">
        <div v-if="loading" class="gt-report-provenance__state">正在读取来源……</div>
        <div v-else-if="errorMessage" class="gt-report-provenance__state gt-report-provenance__state--warning">{{ errorMessage }}</div>
        <template v-else-if="payload">
          <div v-if="formulaText" class="gt-report-provenance__row">
            <span class="gt-report-provenance__label">公式</span>
            <span class="gt-report-provenance__formula">{{ formulaText }}</span>
          </div>
          <div class="gt-report-provenance__row">
            <span class="gt-report-provenance__label">最终状态</span>
            <span>{{ valueStateLabel }}</span>
          </div>
          <div class="gt-report-provenance__row">
            <span class="gt-report-provenance__label">当前值</span>
            <span>{{ payload.value == null ? '空' : payload.value }}</span>
          </div>
          <div v-if="payload.legacy" class="gt-report-provenance__state gt-report-provenance__state--warning">历史存量行，尚无来源信封</div>
          <template v-if="payload.envelope">
            <div class="gt-report-provenance__row">
              <span class="gt-report-provenance__label">定义</span>
              <span>{{ definitionText }}</span>
            </div>
            <div class="gt-report-provenance__row">
              <span class="gt-report-provenance__label">最近计算</span>
              <span>{{ calculationText }}</span>
            </div>
            <div class="gt-report-provenance__row">
              <span class="gt-report-provenance__label">输入摘要</span>
              <span>{{ inputText }}</span>
            </div>
            <div v-if="payload.inputs_redacted" class="gt-report-provenance__state gt-report-provenance__state--warning">部分跨项目输入因权限已脱敏</div>
          </template>
          <div v-if="payload.stale" class="gt-report-provenance__state gt-report-provenance__state--warning">当前定义或计算版本已变化，结果已过期</div>
        </template>
        <div v-else class="gt-report-provenance__state">暂无来源信封</div>
      </div>
    </template>
    <span class="gt-report-provenance__trigger"><slot /></span>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/services/apiProxy'
import { fmtDateTime } from '@/utils/formatters'

interface ProvenanceAttempt {
  calculation_status?: string
  calculated_value?: unknown
  computed_at?: string | null
  definition_ref?: { kind?: string; id?: string }
  definition_version?: number
  definition_layer?: string
  input_count?: number
  inputs_truncated?: boolean
  input_digest?: string
}

interface ProvenancePayload {
  value?: string | number | null
  envelope?: {
    value_state?: string
    calculation_applied?: boolean
    applied_attempt?: ProvenanceAttempt | null
    last_calculation?: ProvenanceAttempt | null
  } | null
  stale?: boolean
  legacy?: boolean
  computed_by_label?: string | null
  inputs_redacted?: boolean
}

const props = defineProps<{
  projectId: string
  year: number | null
  reportType: string
  rowCode: string
  attemptId?: string | null
  formula?: string | null
}>()

const cache = new Map<string, ProvenancePayload>()
const pending = new Map<string, Promise<ProvenancePayload>>()
const payload = ref<ProvenancePayload | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const key = computed(() => `${props.projectId}|${props.year ?? ''}|${props.reportType}|${props.rowCode}|${props.attemptId || 'legacy'}`)
const formulaText = computed(() => (props.formula || '').trim())

const stateLabels: Record<string, string> = {
  auto: '自动计算并已采用',
  manual: '人工填写',
  locked: '已锁定',
  kept: '保留旧值',
  pending_confirm: '等待确认，尚未采用',
  failed: '计算失败，保留旧值',
}

const valueStateLabel = computed(() => {
  const state = payload.value?.envelope?.value_state
  return stateLabels[state || ''] || (payload.value?.legacy ? '历史值' : '暂无状态')
})

const lastAttempt = computed(() => payload.value?.envelope?.last_calculation || null)
const definitionText = computed(() => {
  const attempt = lastAttempt.value
  if (!attempt) return '暂无'
  const ref = attempt.definition_ref
  const refText = ref?.id ? `${ref.kind || '定义'} · ${ref.id}` : '未记录定义引用'
  return `${refText} · v${attempt.definition_version ?? '—'} · ${attempt.definition_layer || '—'}`
})

const CALCULATION_SUCCEEDED = 'succeeded'
const CALCULATION_FAILED = 'failed'

const calculationText = computed(() => {
  const attempt = lastAttempt.value
  if (!attempt) return '暂无计算记录'
  const status = attempt.calculation_status === CALCULATION_SUCCEEDED ? '成功' : attempt.calculation_status === CALCULATION_FAILED ? '失败' : '跳过'
  const time = attempt.computed_at ? fmtDateTime(attempt.computed_at) : '时间未知'
  const actor = payload.value?.computed_by_label ? ` · ${payload.value.computed_by_label}` : ''
  return `${status} · ${time}${actor}`
})

const inputText = computed(() => {
  const attempt = lastAttempt.value
  if (!attempt) return '暂无'
  const count = attempt.input_count ?? 0
  return `${count} 项${attempt.inputs_truncated ? '，展示已截断' : ''} · 摘要 ${attempt.input_digest ? attempt.input_digest.slice(0, 12) : '—'}`
})

async function loadProvenance() {
  if (!props.projectId || props.year == null || !props.rowCode) return
  const cacheKey = key.value
  errorMessage.value = ''
  if (cache.has(cacheKey)) {
    payload.value = cache.get(cacheKey) || null
    return
  }
  let request = pending.get(cacheKey)
  if (!request) {
    request = api.get(
      `/api/reports/${encodeURIComponent(props.projectId)}/${props.year}/${encodeURIComponent(props.reportType)}/rows/${encodeURIComponent(props.rowCode)}/provenance`,
      { _silent: true } as any,
    ) as Promise<ProvenancePayload>
    pending.set(cacheKey, request)
  }
  loading.value = true
  try {
    const result = await request
    cache.set(cacheKey, result)
    payload.value = result
  } catch (error: any) {
    const status = error?.response?.status
    errorMessage.value = status === 403 ? '无权查看该来源' : '来源暂时无法读取'
    payload.value = null
  } finally {
    pending.delete(cacheKey)
    loading.value = false
  }
}
</script>

<style scoped>
.gt-report-provenance__trigger {
  display: inline-flex;
  align-items: center;
  border-bottom: 1px dashed var(--el-color-primary);
  cursor: help;
}
.gt-report-provenance {
  min-width: 280px;
  max-width: 390px;
  font-size: 12px;
  line-height: 1.7;
}
.gt-report-provenance__row {
  display: flex;
  gap: 8px;
}
.gt-report-provenance__label {
  flex: 0 0 64px;
  color: #a3c8ff;
  white-space: nowrap;
}
.gt-report-provenance__formula {
  max-width: 290px;
  word-break: break-all;
  font-family: 'Consolas', 'Courier New', monospace;
}
.gt-report-provenance__state--warning {
  color: #e6a23c;
}
</style>
