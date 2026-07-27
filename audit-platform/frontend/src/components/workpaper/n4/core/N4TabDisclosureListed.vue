<template>
  <div class="n4-disclosure-listed" data-testid="n4-disclosure-listed">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>附注披露（上市公司）</strong>：按证监会格式披露税金及附加各税种的本期与上期发生额明细，分析变动原因。数据自动从N4-1审定表同步。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>税金及附加附注（上市公司） — 18×12</span>
        <el-tag type="success" size="small">证监会格式</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :loading="aiLoading" :disabled="props.isReadonly" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI变动说明
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审定数同步提示 ═══ -->
    <el-alert v-if="adjudicatedTotal != null" type="success" :closable="false" class="sync-hint">
      已同步N4-1审定发生额合计：{{ fmtAmount(adjudicatedTotal) }}
      <el-button link size="small" @click="pullFromAdjudication">刷新</el-button>
    </el-alert>

    <!-- ═══ 主数据表格（10税种+其他+合计 = 12行） ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      class="disclosure-table"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="label" label="税种" min-width="160" fixed />

      <el-table-column label="本期发生额" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.currentAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => updateField(row.rowKey, 'currentAmount', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.currentAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="上期发生额" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.priorAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => updateField(row.rowKey, 'priorAmount', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.priorAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="变动额" min-width="110" align="right">
        <template #header>
          <el-tooltip content="变动额 = 本期发生额 − 上期发生额" placement="top">
            <span class="formula-header">变动额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="变动率" min-width="90" align="right">
        <template #header>
          <el-tooltip content="变动率 = (本期 − 上期) / |上期|" placement="top">
            <span class="formula-header">变动率</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-cell', yoyClass(row.changeRate)]">{{ fmtPercent(row.changeRate) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="变动原因说明" min-width="200">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly && !row.isTotal"
            :model-value="row.remark"
            size="small"
            placeholder="变动说明..."
            @update:model-value="(val: string) => updateField(row.rowKey, 'remark', val)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 附注文本（自由文本，autosize） ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-header">
          <span>附注说明文本</span>
          <el-button size="small" :loading="aiLoading" :disabled="props.isReadonly" @click="handleAiNoteText">
            <el-icon><MagicStick /></el-icon>AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="props.isReadonly"
        placeholder="税金及附加附注披露说明（各税种变动情况分析...）"
        @input="onNoteTextChange"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabDisclosureListed.vue — 附注披露信息（上市公司），18×12
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 4.5
 * Requirements: 5.2-5.4
 *
 * 功能：
 * - 10个税种行 + 其他 + 合计行 = 12行显示
 * - 列：税种 | 本期发生额 | 上期发生额 | 变动额 | 变动率 | 变动原因说明
 * - Subscribe 'substantive:adjudicated' 自动从N4-1拉取审定数据
 * - Publish 'disclosure:note-text-updated' 当文本变化时
 * - AI按钮生成变动说明文本
 * - allResponses持久化，item_id: "N4-disclosure-listed-*"
 *
 * 证监会格式：各税种本期/上期发生额明细+变动分析
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { calcSubtotal, calcYoyChange, parseNum } from '../../composables/useN4FormulaEngine'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | null
  remark: string
  isTotal?: boolean
}

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  isReadonly?: boolean
}>()

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'N4-disclosure-listed'
const NOTE_ITEM_ID = 'N4-disclosure-listed-note'
const ACCOUNT_CODE = '6403'

/** 上市公司附注税种行定义（证监会格式） */
const TAX_ROW_DEFS = [
  { rowKey: 'consumption-tax', label: '消费税' },
  { rowKey: 'urban-construction', label: '城市维护建设税' },
  { rowKey: 'education-surcharge', label: '教育费附加' },
  { rowKey: 'local-education', label: '地方教育附加' },
  { rowKey: 'property-tax', label: '房产税' },
  { rowKey: 'land-use-tax', label: '城镇土地使用税' },
  { rowKey: 'vehicle-vessel', label: '车船税' },
  { rowKey: 'stamp-tax', label: '印花税' },
  { rowKey: 'resource-tax', label: '资源税' },
  { rowKey: 'environmental-tax', label: '环境保护税' },
  { rowKey: 'other', label: '其他' },
]

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<DisclosureRow[]>(defaultRows())
const noteText = ref('')
const adjudicatedTotal = ref<number | null>(null)
const aiLoading = ref(false)

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function defaultRows(): DisclosureRow[] {
  return TAX_ROW_DEFS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentAmount: 0,
    priorAmount: 0,
    changeAmount: 0,
    changeRate: null,
    remark: '',
  }))
}

function enrichRow(raw: Partial<DisclosureRow> & { rowKey: string }): DisclosureRow {
  const def = TAX_ROW_DEFS.find((d) => d.rowKey === raw.rowKey)
  const currentAmount = parseNum(raw.currentAmount)
  const priorAmount = parseNum(raw.priorAmount)
  const changeAmount = currentAmount - priorAmount
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    currentAmount,
    priorAmount,
    changeAmount,
    changeRate: calcYoyChange(currentAmount, priorAmount),
    remark: raw.remark ?? '',
  }
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number | null): string {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

function yoyClass(v: number | null): string {
  if (v == null) return ''
  if (v > 0.3) return 'yoy-up'
  if (v < -0.3) return 'yoy-down'
  return ''
}

function getRowClassName({ row }: { row: DisclosureRow }): string {
  return row.isTotal ? 'total-row' : ''
}

// ─── Computed ────────────────────────────────────────────────────────────────

const displayRows = computed<DisclosureRow[]>(() => {
  const data = rows.value
  const totalCurrent = calcSubtotal(data.map((r) => r.currentAmount))
  const totalPrior = calcSubtotal(data.map((r) => r.priorAmount))
  const totalChange = totalCurrent - totalPrior
  const total: DisclosureRow = {
    rowKey: 'total',
    label: '合  计',
    currentAmount: totalCurrent,
    priorAmount: totalPrior,
    changeAmount: totalChange,
    changeRate: calcYoyChange(totalCurrent, totalPrior),
    remark: '',
    isTotal: true,
  }
  return [...data, total]
})

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadFromStore(): void {
  const raw = props.allResponses.get(ITEM_ID)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
        rows.value = TAX_ROW_DEFS.map((def) =>
          enrichRow({ ...def, ...byKey.get(def.rowKey) }),
        )
      }
    } catch { /* ignore */ }
  }
  noteText.value = props.allResponses.get(NOTE_ITEM_ID)?.conclusion ?? props.allResponses.get(NOTE_ITEM_ID)?.remark ?? ''
  // 从N4-1审定总额同步
  const adj = props.allResponses.get('N4-1-adjudicated-amount')?.conclusion ?? props.allResponses.get('N4-1-adjudicated-amount')?.remark
  if (adj != null && adj !== '') adjudicatedTotal.value = parseNum(adj)
}

watch(() => props.allResponses, loadFromStore, { deep: true, immediate: true })

// ─── Persistence ─────────────────────────────────────────────────────────────

function persist(): void {
  if (!props.wpId) return
  const data = rows.value.map(({ rowKey, currentAmount, priorAmount, remark }) => ({
    rowKey, currentAmount, priorAmount, remark,
  }))
  const item = {
    item_id: ITEM_ID,
    remark: JSON.stringify(data),
    conclusion: null,
  }
  props.allResponses.set(ITEM_ID, item)
  void saveSingle(ITEM_ID, item)
}

function persistNote(): void {
  if (!props.wpId) return
  const item = { item_id: NOTE_ITEM_ID, conclusion: noteText.value, remark: null }
  props.allResponses.set(NOTE_ITEM_ID, item)
  void saveSingle(NOTE_ITEM_ID, item)
}

async function saveSingle(itemId: string, data: any): Promise<void> {
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      items: [{
        item_id: itemId,
        conclusion: data.conclusion || null,
        remark: data.remark || null,
      }],
    })
  } catch { /* silent */ }
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function updateField(rowKey: string, field: 'currentAmount' | 'priorAmount' | 'remark', value: unknown): void {
  if (props.isReadonly || rowKey === 'total') return
  rows.value = rows.value.map((r) => {
    if (r.rowKey !== rowKey) return r
    const patch = { ...r, [field]: field === 'remark' ? String(value ?? '') : parseNum(value) }
    return enrichRow(patch)
  })
  persist()
  publishNoteDebounced()
}

function onNoteTextChange(): void {
  if (props.isReadonly) return
  persistNote()
  publishNoteDebounced()
}

// ─── EventBus: publish disclosure:note-text-updated ──────────────────────────

let noteTimer: ReturnType<typeof setTimeout> | null = null
function publishNoteDebounced(): void {
  if (noteTimer) clearTimeout(noteTimer)
  noteTimer = setTimeout(() => {
    noteTimer = null
    eventBus.emit('disclosure:note-text-updated', {
      accountCode: ACCOUNT_CODE,
      wpCode: 'N4',
      variant: 'listed',
      text: noteText.value,
      timestamp: Date.now(),
    })
  }, 2000)
}

// ─── EventBus: subscribe substantive:adjudicated ─────────────────────────────

function handleAdjudicated(payload: any): void {
  if (payload?.accountCode === ACCOUNT_CODE || payload?.wpCode === 'N4') {
    adjudicatedTotal.value = parseNum(payload.auditedAmount)
    pullFromAdjudication()
  }
}

function pullFromAdjudication(): void {
  // 从 allResponses 中拉取N4-1审定数据（各税种行）
  const adj = props.allResponses.get('N4-1-adjudicated-amount')?.conclusion ?? props.allResponses.get('N4-1-adjudicated-amount')?.remark
  if (adj != null) adjudicatedTotal.value = parseNum(adj)

  // 尝试从N4-1审定行数据同步各税种审定额
  const adjData = props.allResponses.get('N4-1-rows')?.remark
  if (adjData) {
    try {
      const adjRows = JSON.parse(adjData)
      if (Array.isArray(adjRows)) {
        rows.value = rows.value.map((row) => {
          const matchRow = adjRows.find((ar: any) => ar.rowKey === row.rowKey)
          if (matchRow) {
            return enrichRow({
              ...row,
              currentAmount: parseNum(matchRow.audited ?? matchRow.currentAmount),
            })
          }
          return row
        })
        persist()
      }
    } catch { /* ignore */ }
  }
}

// ─── AI Assist ───────────────────────────────────────────────────────────────

async function handleAiAssist(): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请为上市公司税金及附加附注各税种的变动生成简要说明',
      // 后端 context 为 dict[str,str]：包一层 dict + 值转 JSON 字符串（直接传字符串会 422）
      context: { 各税种变动: JSON.stringify(rows.value.map((r) => ({
        tax: r.label, current: r.currentAmount, prior: r.priorAmount, change: r.changeAmount,
      }))) },
      section: 'n4-disclosure-listed-remark',
    }, { _silent: true } as any)
    const text = res?.data?.content ?? res?.content ?? ''
    if (text) {
      // 解析AI返回的各行备注分发到对应行
      const lines = text.split('\n').filter((l: string) => l.trim())
      rows.value = rows.value.map((row, idx) => {
        if (lines[idx] && !row.remark) {
          return enrichRow({ ...row, remark: lines[idx].replace(/^[^:：]+[:：]\s*/, '') })
        }
        return row
      })
      persist()
    }
  } catch { /* AI is optional */ }
  finally { aiLoading.value = false }
}

async function handleAiNoteText(): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请为上市公司税金及附加附注披露生成完整说明文本（证监会格式）',
      // 后端 context 为 dict[str,str]：包一层 dict + 值转 JSON 字符串（直接传字符串会 422）
      context: { 披露数据: JSON.stringify(displayRows.value.map((r) => ({
        tax: r.label, current: r.currentAmount, prior: r.priorAmount, changeRate: r.changeRate,
      }))) },
      existingContent: noteText.value,
      section: 'n4-disclosure-listed-note',
    }, { _silent: true } as any)
    const text = res?.data?.content ?? res?.content ?? ''
    if (text) {
      noteText.value = text
      persistNote()
    }
  } catch { /* AI is optional */ }
  finally { aiLoading.value = false }
}

function handleReview(): void {
  openReviewDialog('N4-disclosure-listed')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  pullFromAdjudication()
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  if (noteTimer) clearTimeout(noteTimer)
})
</script>

<style scoped>
.n4-disclosure-listed { font-size: var(--wp-font-size, 13px); padding: 8px 0; }
.methodology-context {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 2px;
  font-size: 12px;
  color: #666;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
}
.section-actions { display: flex; gap: 6px; }
.sync-hint { margin-bottom: 8px; }
.disclosure-table { margin-bottom: 12px; }
.cell-input { width: 100%; }
.cell-value { font-variant-numeric: tabular-nums; }
.formula-header { border-bottom: 1px dashed #999; cursor: help; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; font-variant-numeric: tabular-nums; }
.yoy-up { color: #f56c6c; }
.yoy-down { color: #67c23a; }
.note-card { margin-top: 12px; }
.note-header { display: flex; justify-content: space-between; align-items: center; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa !important; }
</style>
