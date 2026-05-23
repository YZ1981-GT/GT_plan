<script setup lang="ts">
/**
 * AdjustmentImpactPreview — 调整分录影响实时预览面板
 *
 * 嵌入调整分录编辑弹窗，实时显示当前正在编辑的 line_items 对报表/底稿的影响。
 * 监听 `lineItems` 深度变化，debounce 500ms 调用 `POST .../adjustments/preview-impact`。
 *
 * 后端响应：
 *   {
 *     affected_report_rows: [{ report_type, row_code, row_name, field, delta(string) }],
 *     affected_workpapers:  ["D2", "K8", ...],
 *     unmapped_accounts:    ["9999", ...]
 *   }
 *
 * Validates: proposal-remaining-18 §二 L-2，design.md ADR-2，task 2.2
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { adjustments as P_ADJ } from '@/services/apiPaths/accounting'
import { fmtAmount } from '@/utils/formatters'

interface LineItem {
  account_code?: string
  /** 兼容旧字段：等同 account_code */
  standard_account_code?: string
  debit?: number | string | null
  credit?: number | string | null
  /** 兼容旧字段：等同 debit / credit */
  debit_amount?: number | string | null
  credit_amount?: number | string | null
}

interface AffectedReportRow {
  report_type: string
  row_code: string
  row_name?: string
  field: string
  delta: string
}

interface PreviewResult {
  affected_report_rows: AffectedReportRow[]
  affected_workpapers: string[]
  unmapped_accounts: string[]
}

const props = withDefaults(
  defineProps<{
    projectId: string
    lineItems: LineItem[]
    year?: number | null
    /** debounce 间隔（毫秒），默认 500，便于测试覆写 */
    debounceMs?: number
  }>(),
  { year: null, debounceMs: 500 },
)

const result = ref<PreviewResult | null>(null)
const loading = ref(false)
const errorMsg = ref<string>('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null
let requestSeq = 0

/** 判断 line_items 是否有"可计算"的内容（含 account_code 且金额 != 0） */
const hasCalculableItems = computed(() => {
  if (!Array.isArray(props.lineItems) || props.lineItems.length === 0) return false
  return props.lineItems.some((li) => {
    const code = (li.account_code || li.standard_account_code || '').toString().trim()
    if (!code) return false
    const dr = Number(li.debit ?? li.debit_amount ?? 0) || 0
    const cr = Number(li.credit ?? li.credit_amount ?? 0) || 0
    return dr !== 0 || cr !== 0
  })
})

function clearDebounce() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
}

async function fetchPreview() {
  if (!props.projectId) return
  if (!hasCalculableItems.value) {
    result.value = null
    errorMsg.value = ''
    loading.value = false
    return
  }
  const seq = ++requestSeq
  loading.value = true
  errorMsg.value = ''
  try {
    const payload = {
      year: props.year ?? null,
      line_items: props.lineItems
        .filter((li) => (li.account_code || li.standard_account_code || '').toString().trim())
        .map((li) => ({
          account_code: li.account_code || li.standard_account_code,
          debit: Number(li.debit ?? li.debit_amount ?? 0) || 0,
          credit: Number(li.credit ?? li.credit_amount ?? 0) || 0,
        })),
    }
    const data = await api.post<PreviewResult>(P_ADJ.previewImpact(props.projectId), payload)
    // 防止旧请求覆盖新响应
    if (seq !== requestSeq) return
    result.value = {
      affected_report_rows: data?.affected_report_rows || [],
      affected_workpapers: data?.affected_workpapers || [],
      unmapped_accounts: data?.unmapped_accounts || [],
    }
  } catch (e: any) {
    if (seq !== requestSeq) return
    errorMsg.value = e?.response?.data?.detail || e?.message || '预览失败'
    result.value = null
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

/** 防抖触发：500ms 内连续修改只调一次 API */
function scheduleFetch() {
  clearDebounce()
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    void fetchPreview()
  }, props.debounceMs)
}

watch(
  () => [props.lineItems, props.year, props.projectId] as const,
  () => {
    // 立即清空旧错误，避免视觉残留
    errorMsg.value = ''
    scheduleFetch()
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  clearDebounce()
})

/** delta 数字解析（后端返回 string，保留精度） */
function parseDelta(delta: string): number {
  const n = Number(delta)
  return Number.isFinite(n) ? n : 0
}

function deltaClass(delta: string): string {
  const n = parseDelta(delta)
  if (n > 0) return 'gt-aip-delta-pos'
  if (n < 0) return 'gt-aip-delta-neg'
  return ''
}

function fmtDelta(delta: string): string {
  const n = parseDelta(delta)
  if (n === 0) return '-'
  // 正数加 "+" 前缀，负数 fmtAmount 自带负号
  const formatted = fmtAmount(Math.abs(n))
  return n > 0 ? `+${formatted}` : `-${formatted}`
}

const isEmpty = computed(
  () =>
    !loading.value &&
    !errorMsg.value &&
    (!result.value ||
      ((result.value.affected_report_rows?.length || 0) === 0 &&
        (result.value.affected_workpapers?.length || 0) === 0 &&
        (result.value.unmapped_accounts?.length || 0) === 0)),
)

defineExpose({
  /** 测试用：强制立即刷新，绕过 debounce */
  flush: fetchPreview,
})
</script>

<template>
  <div class="gt-aip-panel">
    <div class="gt-aip-header">
      <span class="gt-aip-title">影响预览</span>
      <span v-if="loading" class="gt-aip-status">计算中…</span>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      :title="errorMsg"
      style="margin-bottom: 8px"
    />

    <!-- 空态 -->
    <div v-else-if="!hasCalculableItems" class="gt-aip-empty">
      录入科目和金额后自动预览影响范围
    </div>
    <div v-else-if="isEmpty" class="gt-aip-empty">未发现受影响的报表行或底稿</div>

    <template v-else-if="result">
      <!-- 受影响报表行 -->
      <div class="gt-aip-section">
        <div class="gt-aip-section-title">
          受影响报表行
          <span class="gt-aip-count">({{ result.affected_report_rows.length }})</span>
        </div>
        <div v-if="result.affected_report_rows.length === 0" class="gt-aip-empty-sm">
          无受影响报表行
        </div>
        <table v-else class="gt-aip-table">
          <thead>
            <tr>
              <th>报表</th>
              <th>行</th>
              <th>字段</th>
              <th class="gt-aip-th-num">变动</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in result.affected_report_rows" :key="`${row.report_type}-${row.row_code}-${row.field}-${idx}`">
              <td>
                <el-tag size="small" type="info" effect="plain">{{ row.report_type }}</el-tag>
              </td>
              <td>
                <span class="gt-aip-row-code">{{ row.row_code }}</span>
                <span v-if="row.row_name" class="gt-aip-row-name">{{ row.row_name }}</span>
              </td>
              <td>{{ row.field }}</td>
              <td class="gt-aip-td-num gt-amt" :class="deltaClass(row.delta)">
                {{ fmtDelta(row.delta) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 受影响底稿 -->
      <div class="gt-aip-section">
        <div class="gt-aip-section-title">
          受影响底稿
          <span class="gt-aip-count">({{ result.affected_workpapers.length }})</span>
        </div>
        <div v-if="result.affected_workpapers.length === 0" class="gt-aip-empty-sm">无受影响底稿</div>
        <div v-else class="gt-aip-tags">
          <el-tag
            v-for="wp in result.affected_workpapers"
            :key="wp"
            size="small"
            effect="plain"
            type="primary"
          >
            {{ wp }}
          </el-tag>
        </div>
      </div>

      <!-- 未映射科目警告 -->
      <el-alert
        v-if="result.unmapped_accounts.length > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 8px"
      >
        <template #title>
          <span>
            未映射科目（{{ result.unmapped_accounts.length }}）：
            <span v-for="(c, i) in result.unmapped_accounts" :key="c">
              <span class="gt-aip-row-code">{{ c }}</span>
              <span v-if="i < result.unmapped_accounts.length - 1">、</span>
            </span>
          </span>
        </template>
        <span class="gt-aip-warn-hint">
          这些科目暂无报表行映射，影响测算将不计入。请前往"报表行映射"补全。
        </span>
      </el-alert>
    </template>
  </div>
</template>

<style scoped>
.gt-aip-panel {
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--gt-color-bg-soft, #fafafa);
  font-size: var(--gt-font-size-sm);
}
.gt-aip-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
}
.gt-aip-title {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-aip-status {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.gt-aip-empty,
.gt-aip-empty-sm {
  text-align: center;
  padding: 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-placeholder);
}
.gt-aip-empty-sm {
  padding: 6px 0;
}
.gt-aip-section {
  margin-bottom: 10px;
}
.gt-aip-section:last-child {
  margin-bottom: 0;
}
.gt-aip-section-title {
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  margin-bottom: 6px;
}
.gt-aip-count {
  font-weight: 400;
  color: var(--gt-color-text-tertiary);
  margin-left: 4px;
}
.gt-aip-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--gt-font-size-xs);
}
.gt-aip-table th,
.gt-aip-table td {
  border-bottom: 1px solid var(--gt-color-border-lighter);
  padding: 4px 6px;
  text-align: left;
  vertical-align: middle;
}
.gt-aip-th-num,
.gt-aip-td-num {
  text-align: right;
  white-space: nowrap;
}
.gt-aip-row-code {
  font-family: 'Arial Narrow', Arial, sans-serif;
  color: var(--gt-color-teal);
  margin-right: 4px;
}
.gt-aip-row-name {
  color: var(--gt-color-text-regular);
}
.gt-aip-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gt-aip-delta-pos {
  color: #2e7d32; /* 绿色 = 增加 */
  font-weight: 600;
}
.gt-aip-delta-neg {
  color: #c62828; /* 红色 = 减少 */
  font-weight: 600;
}
.gt-aip-warn-hint {
  display: block;
  margin-top: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
