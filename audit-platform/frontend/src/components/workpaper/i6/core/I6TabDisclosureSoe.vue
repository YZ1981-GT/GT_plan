<template>
  <div class="i6-disclosure-soe">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 研发费用按类型汇总（国企版16行×6列）</div>
        <div class="guide-step"><span class="step-num">②</span> 费用化/资本化总额说明</div>
        <div class="guide-step"><span class="step-num">③</span> AI辅助生成文字描述</div>
      </div>
    </div>
    <div class="methodology-block">
      <div class="methodology-title">附注披露（国有企业版）</div>
      <div class="methodology-content">
        国有企业应披露研发费用的分类明细及发生额变动情况。本表16行×6列。
        科目6602研发费用（损益类/借方），取发生额非余额。
      </div>
    </div>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">研发费用分类明细（国企版）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('category')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" type="default" link @click="handleReview('category')">💬</el-button>
          </div>
        </div>
      </template>
      <el-table :data="categoryRows" border stripe size="small" class="matrix-table">
        <el-table-column prop="item" label="费用类别" min-width="140" fixed />
        <el-table-column prop="currentAmount" label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" :controls="false" size="small" @change="(v: number) => onEdit(row.rowId, 'currentAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" :controls="false" size="small" @change="(v: number) => onEdit(row.rowId, 'priorAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="= 本期 - 上期">{{ fmtAmt(row.currentAmount - row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }"><span class="formula-cell" :class="{ 'rate-warn': isHighRate(row) }">{{ fmtPct(row.currentAmount, row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @blur="(e: FocusEvent) => onEdit(row.rowId, 'remark', (e.target as HTMLInputElement).value)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="totals-row">
        <span class="totals-label">合计</span>
        <span class="totals-value">本期: {{ fmtAmt(totalCurrent) }}</span>
        <span class="totals-value">上期: {{ fmtAmt(totalPrior) }}</span>
      </div>
    </el-card>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">补充说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('supplement')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" type="default" link @click="handleReview('supplement')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="supplementNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="费用化与资本化划分说明、重大项目概况..." @blur="onNoteBlur" />
    </el-card>

    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>国企版：16行×6列（费用类别/本期/上期/变动额/变动率/说明）</li>
      <li>EventBus: publish 'disclosure:note-text-updated'</li>
    </ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

interface CategoryRow { rowId: string; item: string; currentAmount: number; priorAmount: number; remark: string }

const ITEM_ID = 'I6-disc-S-categories'
const DEFAULT_CATEGORIES = ['人工费', '材料费', '折旧费', '无形资产摊销', '设计费', '装备调试费', '委外研发费', '其他费用']

const categoryRows = ref<CategoryRow[]>([])
const supplementNote = ref('')

const totalCurrent = computed(() => categoryRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0))
const totalPrior = computed(() => categoryRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))

function _load(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) { categoryRows.value = p; _loadNote(); return } } catch { /* */ } }
  categoryRows.value = DEFAULT_CATEGORIES.map((name) => ({ rowId: `row-${Math.random().toString(36).slice(2, 10)}`, item: name, currentAmount: 0, priorAmount: 0, remark: '' }))
  _loadNote()
}
function _loadNote(): void { supplementNote.value = _str('I6-disc-S-supplement') }
function _str(id: string): string { const item = props.allResponses.get(id); return (item?.remark ?? (typeof item === 'string' ? item : '')) as string }
watch(() => props.allResponses, () => _load(), { immediate: true })

function _persist(): void { emit('save', ITEM_ID, JSON.stringify(categoryRows.value)) }
function onEdit(rowId: string, field: string, value: any): void { const row = categoryRows.value.find((r) => r.rowId === rowId); if (row) { (row as any)[field] = value; _persist() } }
function onNoteBlur(): void { emit('save', 'I6-disc-S-supplement', supplementNote.value); window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', { detail: { wpCode: 'I6-附注国企' } })) }

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section, prompt: `I6研发费用附注国企-${section}`, context: { wpCode: 'I6-附注国企', totalCurrent: totalCurrent.value } })
    if (res.data?.data?.content && section === 'supplement') { supplementNote.value = res.data.data.content; onNoteBlur() }
  } catch { /* */ }
}
function handleReview(section: string): void { openReviewDialog(`I6 附注国企-${section}`) }
function isHighRate(row: CategoryRow): boolean { if (!row.priorAmount) return false; return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > 0.3 }
function fmtAmt(v: number | null | undefined): string { if (v == null || Math.abs(v) < 0.005) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPct(current: number, prior: number): string { if (!prior) return '-'; return ((current - prior) / Math.abs(prior) * 100).toFixed(1) + '%' }
</script>

<style scoped>
.i6-disclosure-soe { padding: 16px; font-size: 13px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7; }
.methodology-title { font-weight: 600; color: #78350f; margin-bottom: 4px; }
.disclosure-card { margin-bottom: 16px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 14px; font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 4px; }
.matrix-table { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.amount-cell { font-variant-numeric: tabular-nums; }
.rate-warn { color: #d97706; font-weight: 600; background: #fefce8; padding: 1px 4px; border-radius: 2px; }
.totals-row { display: flex; align-items: center; gap: 16px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 12px; margin-top: 4px; }
.totals-label { font-weight: 600; min-width: 40px; }
.totals-value { font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
