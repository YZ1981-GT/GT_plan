<template>
  <div class="i6-disclosure-listed">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 研发费用明细按类型汇总（SUMIF从审定表/明细表取数）</div>
        <div class="guide-step"><span class="step-num">②</span> 费用化/资本化划分说明（联动I2开发支出）</div>
        <div class="guide-step"><span class="step-num">③</span> 重大研发项目进展说明（AI辅助生成）</div>
        <div class="guide-step"><span class="step-num">④</span> 上市公司版 19行×7列</div>
      </div>
    </div>
    <div class="methodology-block">
      <div class="methodology-title">CAS 附注披露要求（上市公司版）</div>
      <div class="methodology-content">
        按信息披露编报规则：上市公司应披露研发费用的分类明细（人工费/材料费/折旧/设计等）、
        本期发生额和上期对比。本表19行×7列。损益类科目6602（借方），取发生额非余额。
      </div>
    </div>

    <!-- 分类汇总表 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">研发费用分类明细</span>
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
            <el-input-number v-if="!isReadonly && !row.isAutoFilled" :model-value="row.currentAmount" :controls="false" size="small" @change="(v: number) => onCategoryEdit(row.rowId, 'currentAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentAmount) }}<el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag></span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" :controls="false" size="small" @change="(v: number) => onCategoryEdit(row.rowId, 'priorAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="= 本期 - 上期">{{ fmtAmt(row.currentAmount - row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }"><span class="formula-cell" title="= (本期 - 上期) / 上期" :class="{ 'rate-warn': isHighRate(row) }">{{ fmtPercent2(row.currentAmount, row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @blur="(e: FocusEvent) => onCategoryEdit(row.rowId, 'remark', (e.target as HTMLInputElement).value)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPctOfTotal(row.currentAmount) }}</span></template>
        </el-table-column>
      </el-table>
      <div class="totals-row">
        <span class="totals-label">合计</span>
        <span class="totals-value">本期: {{ fmtAmt(totalCurrent) }}</span>
        <span class="totals-value">上期: {{ fmtAmt(totalPrior) }}</span>
      </div>
    </el-card>

    <!-- 费用化/资本化说明 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">费用化与资本化说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('capitalization')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" type="default" link @click="handleReview('capitalization')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="capitalizationNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="费用化金额(I6)、资本化金额(I2)及其占比说明..." @blur="onNoteBlur('capitalization')" />
    </el-card>

    <!-- 重大项目说明 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">重大研发项目进展</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('projects')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" type="default" link @click="handleReview('projects')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="projectsNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="列示重大研发项目名称、投入金额、完成进度..." @blur="onNoteBlur('projects')" />
    </el-card>

    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>上市公司版：19行×7列（费用类别/本期/上期/变动额/变动率/说明/占比）</li>
      <li>数据从审定表I6-1/明细表I6-2自动汇总(SUMIF)</li>
      <li>EventBus: subscribe 'substantive:adjudicated' 刷新, publish 'disclosure:note-text-updated'</li>
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

interface CategoryRow { rowId: string; item: string; currentAmount: number; priorAmount: number; remark: string; isAutoFilled: boolean }

const ITEM_ID = 'I6-disc-L-categories'
const DEFAULT_CATEGORIES = ['人工费', '材料费', '折旧费', '无形资产摊销', '设计费', '装备调试费', '委外研发费', '其他费用']

const categoryRows = ref<CategoryRow[]>([])
const capitalizationNote = ref('')
const projectsNote = ref('')

const totalCurrent = computed(() => categoryRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0))
const totalPrior = computed(() => categoryRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))

function _load(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) { categoryRows.value = p; _loadNotes(); return } } catch { /* */ } }
  categoryRows.value = DEFAULT_CATEGORIES.map((name) => ({ rowId: `row-${Math.random().toString(36).slice(2, 10)}`, item: name, currentAmount: 0, priorAmount: 0, remark: '', isAutoFilled: false }))
  _loadNotes()
}
function _loadNotes(): void {
  capitalizationNote.value = _str('I6-disc-L-capitalization')
  projectsNote.value = _str('I6-disc-L-projects')
}
function _str(id: string): string { const item = props.allResponses.get(id); return (item?.remark ?? (typeof item === 'string' ? item : '')) as string }
watch(() => props.allResponses, () => _load(), { immediate: true })

function _persist(): void { emit('save', ITEM_ID, JSON.stringify(categoryRows.value)) }

function onCategoryEdit(rowId: string, field: string, value: any): void {
  const row = categoryRows.value.find((r) => r.rowId === rowId)
  if (row) { (row as any)[field] = value; _persist() }
}

function onNoteBlur(section: string): void {
  if (section === 'capitalization') emit('save', 'I6-disc-L-capitalization', capitalizationNote.value)
  else if (section === 'projects') emit('save', 'I6-disc-L-projects', projectsNote.value)
  // Publish EventBus
  window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', { detail: { wpCode: 'I6-附注上市', section } }))
}

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section, prompt: `I6研发费用附注上市-${section}`, context: { wpCode: 'I6-附注上市', totalCurrent: totalCurrent.value } })
    if (res.data?.data?.content) {
      if (section === 'capitalization') { capitalizationNote.value = res.data.data.content; onNoteBlur('capitalization') }
      else if (section === 'projects') { projectsNote.value = res.data.data.content; onNoteBlur('projects') }
    }
  } catch { /* */ }
}

function handleReview(section: string): void { openReviewDialog(`I6 附注上市-${section}`) }

function isHighRate(row: CategoryRow): boolean { if (!row.priorAmount) return false; return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > 0.3 }
function fmtAmt(v: number | null | undefined): string { if (v == null || Math.abs(v) < 0.005) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPercent2(current: number, prior: number): string { if (!prior) return '-'; return ((current - prior) / Math.abs(prior) * 100).toFixed(1) + '%' }
function fmtPctOfTotal(val: number): string { if (!totalCurrent.value || !val) return '-'; return ((val / totalCurrent.value) * 100).toFixed(1) + '%' }
</script>

<style scoped>
.i6-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
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
.auto-badge { margin-left: 4px; }
.rate-warn { color: #d97706; font-weight: 600; background: #fefce8; padding: 1px 4px; border-radius: 2px; }
.totals-row { display: flex; align-items: center; gap: 16px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 12px; margin-top: 4px; }
.totals-label { font-weight: 600; min-width: 40px; }
.totals-value { font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
