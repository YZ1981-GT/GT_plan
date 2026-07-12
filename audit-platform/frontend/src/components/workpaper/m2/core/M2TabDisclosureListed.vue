<template>
  <div class="m2-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市·万股</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司股本附注披露要求（15×19，41公式）：</strong>
        按股份性质列示股本变动情况（单位：万股）。披露期初/本期增/本期减/期末股数及占比。
        数据自动从审定表/明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 股本变动明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>股本变动明细（单位：万股）</span>
          <el-button size="small" @click="handleAI('section-capital-change')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="capitalChangeRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="股份性质" min-width="160" />
        <el-table-column label="期初数（万股）" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'beginShares', val ?? 0)"
            />
            <span v-else>{{ fmtShares(row.beginShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加（万股）" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increaseShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'increaseShares', val ?? 0)"
            />
            <span v-else>{{ fmtShares(row.increaseShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少（万股）" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decreaseShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'decreaseShares', val ?? 0)"
            />
            <span v-else>{{ fmtShares(row.decreaseShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数（万股）" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 本期增加 − 本期减少" placement="top">
              <span class="formula-col-header">期末数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtShares(row.endShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="90" align="center">
          <template #default="{ row }">
            <span>{{ row.ratio ? `${(row.ratio * 100).toFixed(2)}%` : '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 限售股说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>限售股份说明</span>
          <el-button size="small" @click="handleAI('section-restricted')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="restrictedNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="列明限售股份的类型、数量、限售原因、可上市流通时间..."
        @change="handleNoteChange('restricted', restrictedNote)"
      />
    </el-card>

    <!-- ═══ Section 3: 股本变动原因说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>股本变动原因说明</span>
          <el-button size="small" @click="handleAI('section-reason')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="changeReasonNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本期股本变动的原因：IPO/增发/配股/转增/回购注销等..."
        @change="handleNoteChange('change-reason', changeReasonNote)"
      />
    </el-card>

    <!-- ═══ Section 4: 每股收益相关 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>与每股收益计算相关说明</span>
          <el-button size="small" @click="handleAI('section-eps')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="epsNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="期末股本总额（基本EPS计算基数）、稀释性潜在普通股..."
        @change="handleNoteChange('eps', epsNote)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司股本单位：万股（注意与非上市公司"元"的区别）</li>
        <li>数据优先从M2-1审定表和M2-2明细表(上市版)自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>需额外披露限售股份、变动原因、EPS相关基数</li>
        <li>格式：15行×19列（含合计行和比例计算列）</li>
        <li>期末数 = 期初 + 本期增加 − 本期减少（权益类方向）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabDisclosureListed — 附注披露信息（上市公司）15×19, 41公式
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 4.6
 * Requirements: 6.2-6.3
 *
 * 功能：
 * - 上市公司版附注（股份单位：万股）
 * - Subscribe EventBus 'substantive:adjudicated' refresh
 * - 股本变动明细表 + 期末公式计算
 * - 限售股/变动原因/EPS相关 textarea sections
 * - AI辅助 per section
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM2FormData } from '../../composables/useM2FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

interface CapitalRow {
  item: string
  beginShares: number
  increaseShares: number
  decreaseShares: number
  endShares: number
  ratio: number
}

const capitalChangeRows = ref<CapitalRow[]>([
  { item: '一、有限售条件股份', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  1.国家持股', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  2.国有法人持股', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  3.其他内资持股', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  4.外资持股', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '二、无限售条件股份', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  1.人民币普通股（A股）', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  2.境内上市外资股（B股）', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  3.境外上市外资股（H股）', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '  4.其他', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
  { item: '三、股份总数', beginShares: 0, increaseShares: 0, decreaseShares: 0, endShares: 0, ratio: 0 },
])

const restrictedNote = ref('')
const changeReasonNote = ref('')
const epsNote = ref('')

// ─── Computed: 期末数 = 期初+增-减, 占比 ─────────────────────────────────────

function recalcEndAndRatio(): void {
  const totalEnd = capitalChangeRows.value.reduce((sum, row) => {
    const end = row.beginShares + row.increaseShares - row.decreaseShares
    return sum + end
  }, 0)

  capitalChangeRows.value.forEach(row => {
    row.endShares = row.beginShares + row.increaseShares - row.decreaseShares
    row.ratio = totalEnd > 0 ? row.endShares / totalEnd : 0
  })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateCapitalRow(index: number, field: 'beginShares' | 'increaseShares' | 'decreaseShares', val: number) {
  if (index >= 0 && index < capitalChangeRows.value.length) {
    capitalChangeRows.value[index][field] = val
    recalcEndAndRatio()
    formData.debouncedSave('M2-disclosure-listed-capital-rows', {
      remark: JSON.stringify(capitalChangeRows.value),
    })
  }
}

function handleNoteChange(section: string, value: string) {
  formData.debouncedSave(`M2-disclosure-listed-${section}`, { remark: value || null })
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('M2-disclosure-listed', '附注披露（上市）') }

function fmtShares(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore state ──────────────────────────────────────────────────────────

function _restoreFromResponses(): void {
  const rowData = formData.allResponses.value.get('M2-disclosure-listed-capital-rows')
  if (rowData?.remark) {
    try {
      const parsed = JSON.parse(rowData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        capitalChangeRows.value = parsed
        recalcEndAndRatio()
      }
    } catch { /* ignore */ }
  }

  const restricted = formData.allResponses.value.get('M2-disclosure-listed-restricted')
  if (restricted?.remark) restrictedNote.value = restricted.remark

  const reason = formData.allResponses.value.get('M2-disclosure-listed-change-reason')
  if (reason?.remark) changeReasonNote.value = reason.remark

  const eps = formData.allResponses.value.get('M2-disclosure-listed-eps')
  if (eps?.remark) epsNote.value = eps.remark
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(_restoreFromResponses)
}

onMounted(async () => {
  await formData.loadData()
  _restoreFromResponses()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m2-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.m2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
