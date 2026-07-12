<template>
  <div class="i6-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>研发费用审定原理：</strong>科目6602（损益类/借方科目）。取发生额非余额！</p>
      <p>审定数=未审数+AJE+RJE。上期审定=B+C+D，本期审定=F+G+H，变动额=I-E，变动率=(I-E)/E。</p>
      <p>I6↔I2联动：费用化(I6)+资本化(I2)=研发总额(VR-I6-01)。变动率超±30%黄色高亮。</p>
    </div>

    <!-- VR-I6-01 校验警告 -->
    <el-alert
      v-if="vrStatus && !vrStatus.isBalanced"
      type="error"
      :title="`VR-I6-01不平：费用化(${fmtAmount(vrStatus.expense)}) + 资本化(${fmtAmount(vrStatus.capitalized)}) ≠ 研发总额，差额 ${fmtAmount(vrStatus.difference)}`"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <!-- 主审定表（27行×11列） -->
    <div class="table-section">
      <div class="block-header">
        <span class="block-title">研发费用审定表（I6-1）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" text @click="handleAiGenerate('adjudication')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview">复核</el-button>
        </div>
      </div>

      <el-table
        :data="rows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        max-height="560"
        scrollbar-always-on
      >
        <!-- 1. 项目 -->
        <el-table-column prop="项目" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.项目 }}</span>
          </template>
        </el-table-column>
        <!-- 2. 上期未审B -->
        <el-table-column prop="上期未审" label="上期未审(B)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.上期未审" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.上期未审) }}</span>
          </template>
        </el-table-column>
        <!-- 3. 上期AJE(C) -->
        <el-table-column prop="上期AJE" label="上期AJE(C)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.上期AJE" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.上期AJE) }}</span>
          </template>
        </el-table-column>
        <!-- 4. 上期RJE(D) -->
        <el-table-column prop="上期RJE" label="上期RJE(D)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.上期RJE" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.上期RJE) }}</span>
          </template>
        </el-table-column>
        <!-- 5. 上期审定(E)=B+C+D 公式列 -->
        <el-table-column label="上期审定(E)" min-width="110" align="right">
          <template #header>
            <el-tooltip content="上期审定 = B + C + D" placement="top">
              <span class="formula-col-header">上期审定(E)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-value">{{ fmtAmount(row.上期审定) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 6. 本期未审(F) -->
        <el-table-column prop="本期未审" label="本期未审(F)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.本期未审" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.本期未审) }}</span>
          </template>
        </el-table-column>
        <!-- 7. 本期AJE(G) -->
        <el-table-column prop="本期AJE" label="本期AJE(G)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.本期AJE" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.本期AJE) }}</span>
          </template>
        </el-table-column>
        <!-- 8. 本期RJE(H) -->
        <el-table-column prop="本期RJE" label="本期RJE(H)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.本期RJE" size="small" :controls="false" @change="onCellChange(row)" />
            <span v-else>{{ fmtAmount(row.本期RJE) }}</span>
          </template>
        </el-table-column>
        <!-- 9. 本期审定(I)=F+G+H 公式列 -->
        <el-table-column label="本期审定(I)" min-width="110" align="right">
          <template #header>
            <el-tooltip content="本期审定 = F + G + H" placement="top">
              <span class="formula-col-header">本期审定(I)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 本期未审 + 本期AJE + 本期RJE" placement="top">
              <span class="formula-value">{{ fmtAmount(row.本期审定) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 10. 变动额(J)=I-E 公式列 -->
        <el-table-column label="变动额(J)" min-width="110" align="right">
          <template #header>
            <el-tooltip content="变动额 = 本期审定(I) - 上期审定(E)" placement="top">
              <span class="formula-col-header">变动额(J)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 本期审定 - 上期审定" placement="top">
              <span class="formula-value">{{ fmtAmount(row.变动额) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 11. 变动率 公式列 -->
        <el-table-column label="变动率" min-width="90" align="right">
          <template #header>
            <el-tooltip content="变动率 = (I - E) / E" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 变动额 / 上期审定" placement="top">
              <span class="formula-value" :class="{ 'rate-warn': isHighChangeRate(row.变动率) }">
                {{ fmtRate(row.变动率) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- I2联动面板 -->
    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="card-header">
          <span>I6↔I2 联动面板（VR-I6-01）</span>
          <el-button size="small" type="success" @click="handleWritebackTB" :disabled="isReadonly">
            回写TB(6602发生额)
          </el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="费用化(I6)">{{ fmtAmount(linkageData.expense) }}</el-descriptions-item>
        <el-descriptions-item label="资本化(I2)">{{ fmtAmount(linkageData.capitalized) }}</el-descriptions-item>
        <el-descriptions-item label="研发总额">{{ fmtAmount(linkageData.total) }}</el-descriptions-item>
        <el-descriptions-item label="VR-I6-01">
          <el-tag :type="vrStatus?.isBalanced ? 'success' : 'danger'" size="small">
            {{ vrStatus?.isBalanced ? '✓ 平衡' : '✗ 不平衡' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div class="cross-ref-bar">
        <span class="cross-ref-label">跨底稿联动：</span>
        <GtIndexChip value="I2" @click="navigateTo('I2')" />
        <GtIndexChip value="I6-2" @click="navigateTo('I6-2')" />
        <GtIndexChip value="I6-3" @click="navigateTo('I6-3')" />
        <GtIndexChip value="A13" @click="navigateTo('A13')" />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计说明（研发费用归集完整性、与I2划分一致性等）..."
        :disabled="isReadonly" @blur="onNoteBlur" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-select v-model="auditConclusion" placeholder="请选择审计结论" :disabled="isReadonly" class="conclusion-select" @change="onConclusionChange">
        <el-option value="研发费用发生额列报恰当，费用化与资本化划分正确" label="研发费用发生额列报恰当，费用化与资本化划分正确" />
        <el-option value="经审计调整后，研发费用列报恰当" label="经审计调整后，研发费用列报恰当" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>6602研发费用（损益类/借方科目）：取发生额非余额</li>
        <li>公式列：上期审定=B+C+D，本期审定=F+G+H，变动额=I-E，变动率=(I-E)/E</li>
        <li>变动率超±30%黄色高亮需补充原因说明</li>
        <li>"回写TB"将审定发生额回写6602</li>
        <li>VR-I6-01：费用化(I6)+资本化(I2)必须等于研发总额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I6TabAdjudication.vue — I6-1 研发费用审定表（27行×11列，损益类发生额）
 *
 * 列结构（11列）：
 *   项目 | 上期未审(B) | 上期AJE(C) | 上期RJE(D) | 上期审定(E=B+C+D)
 *        | 本期未审(F) | 本期AJE(G) | 本期RJE(H) | 本期审定(I=F+G+H)
 *        | 变动额(J=I-E) | 变动率
 *
 * I2联动面板：费用化(I6)|资本化(I2)|合计|VR-I6-01校验
 * TB回写：writebackTB发生额(6602)
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 4.2
 */
import { ref, reactive, computed, watch, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import {
  calcAuditedAmount,
  calcChangeRate,
} from '../../composables/useI6FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6602: number; audited6602: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────
interface AdjRow {
  rowId: string
  项目: string
  上期未审: number; 上期AJE: number; 上期RJE: number; 上期审定: number
  本期未审: number; 本期AJE: number; 本期RJE: number; 本期审定: number
  变动额: number; 变动率: number | null
  isSubtotal: boolean; isEditable: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────
const ITEM_ID = 'I6-1-rows'
const rows = ref<AdjRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

const linkageData = reactive({ expense: 0, capitalized: 0, total: 0 })

// ─── VR-I6-01 ────────────────────────────────────────────────────────────────
const vrStatus = computed(() => {
  const diff = linkageData.expense + linkageData.capitalized - linkageData.total
  return {
    expense: linkageData.expense,
    capitalized: linkageData.capitalized,
    total: linkageData.total,
    difference: diff,
    isBalanced: Math.abs(diff) < 0.01,
  }
})

// ─── Default rows ────────────────────────────────────────────────────────────
const DEFAULT_ITEMS = [
  '人工费', '材料费', '折旧费', '无形资产摊销', '设计费',
  '装备调试费', '委外研发费', '其他费用', '小计',
]

function _makeRow(name: string, isSubtotal = false): AdjRow {
  return {
    rowId: `row-${Math.random().toString(36).slice(2, 10)}`,
    项目: name, 上期未审: 0, 上期AJE: 0, 上期RJE: 0, 上期审定: 0,
    本期未审: 0, 本期AJE: 0, 本期RJE: 0, 本期审定: 0,
    变动额: 0, 变动率: null,
    isSubtotal, isEditable: !isSubtotal,
  }
}

function _recalcFormulas(): void {
  for (const row of rows.value) {
    row.上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
    row.本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
    row.变动额 = row.本期审定 - row.上期审定
    row.变动率 = calcChangeRate(row.本期审定, row.上期审定)
  }
  // Update subtotal rows
  const editableRows = rows.value.filter((r) => r.isEditable)
  const subtotalRow = rows.value.find((r) => r.项目 === '小计')
  if (subtotalRow) {
    subtotalRow.上期未审 = editableRows.reduce((s, r) => s + r.上期未审, 0)
    subtotalRow.上期AJE = editableRows.reduce((s, r) => s + r.上期AJE, 0)
    subtotalRow.上期RJE = editableRows.reduce((s, r) => s + r.上期RJE, 0)
    subtotalRow.上期审定 = calcAuditedAmount(subtotalRow.上期未审, subtotalRow.上期AJE, subtotalRow.上期RJE)
    subtotalRow.本期未审 = editableRows.reduce((s, r) => s + r.本期未审, 0)
    subtotalRow.本期AJE = editableRows.reduce((s, r) => s + r.本期AJE, 0)
    subtotalRow.本期RJE = editableRows.reduce((s, r) => s + r.本期RJE, 0)
    subtotalRow.本期审定 = calcAuditedAmount(subtotalRow.本期未审, subtotalRow.本期AJE, subtotalRow.本期RJE)
    subtotalRow.变动额 = subtotalRow.本期审定 - subtotalRow.上期审定
    subtotalRow.变动率 = calcChangeRate(subtotalRow.本期审定, subtotalRow.上期审定)
  }
  // Linkage
  linkageData.expense = subtotalRow?.本期审定 ?? 0
}

// ─── Load / Save ─────────────────────────────────────────────────────────────
function _load(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) { rows.value = parsed; _recalcFormulas(); return }
    } catch { /* ignore */ }
  }
  rows.value = DEFAULT_ITEMS.map((n) => _makeRow(n, n === '小计'))
  _recalcFormulas()
  // Load note/conclusion
  auditNote.value = _getString('I6-1-note')
  auditConclusion.value = _getString('I6-1-conclusion')
  // Load I2 capitalized from allResponses (cross-sheet)
  const i2Cap = props.allResponses.get('I2-capitalized-total')
  linkageData.capitalized = Number(typeof i2Cap === 'string' ? i2Cap : i2Cap?.remark ?? 0) || 0
  linkageData.total = linkageData.expense + linkageData.capitalized
}

function _getString(id: string): string {
  const item = props.allResponses.get(id)
  return (item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')) as string
}

watch(() => props.allResponses, () => _load(), { immediate: true })

function _persist(): void {
  emit('save', ITEM_ID, JSON.stringify(rows.value))
}

function onCellChange(_row: AdjRow): void {
  _recalcFormulas()
  _persist()
}

function onNoteBlur(): void { emit('save', 'I6-1-note', auditNote.value) }
function onConclusionChange(val: string): void { emit('save', 'I6-1-conclusion', val) }

// ─── Row styling ─────────────────────────────────────────────────────────────
function getRowClassName({ row }: { row: AdjRow }): string {
  if (row.isSubtotal) return 'row-subtotal'
  return ''
}

function isHighChangeRate(rate: number | null | undefined): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 30  // calcChangeRate returns percentage (e.g. 50 = 50%)
}

// ─── Writeback TB(6602) ──────────────────────────────────────────────────────
async function handleWritebackTB(): Promise<void> {
  try {
    const subtotal = rows.value.find((r) => r.项目 === '小计')
    await http.put(`/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '6602', audited_amount: subtotal?.本期审定 ?? 0,
      source_wp_code: 'I6-1', type: 'income_statement',
    })
    // Publish EventBus
    window.dispatchEvent(new CustomEvent('research:expense-updated', {
      detail: { wpCode: 'I6-1', expense: subtotal?.本期审定 ?? 0 },
    }))
    ElMessage.success('已回写TB(6602发生额)')
  } catch { ElMessage.error('TB回写失败') }
}

// ─── AI / Review / Navigation ────────────────────────────────────────────────
async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section, prompt: `I6研发费用审定表${section}`,
      context: { wpCode: 'I6-1', rule: '6602损益类借方,取发生额', auditedTotal: linkageData.expense },
    })
    if (res.data?.data?.content) {
      if (section === 'note') { auditNote.value = res.data.data.content; onNoteBlur() }
      else if (section === 'conclusion') { auditConclusion.value = res.data.data.content; onConclusionChange(auditConclusion.value) }
    }
  } catch { /* ignore */ }
}

function handleReview(): void { openReviewDialog('I6-1 审定表') }
function navigateTo(code: string): void { emit('navigate-sheet', code) }

// ─── Formatters ──────────────────────────────────────────────────────────────
function fmtAmount(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(rate: number | null | undefined): string {
  if (rate == null) return '-'
  return rate.toFixed(1) + '%'  // calcChangeRate already returns percentage
}
</script>

<style scoped>
.i6-adjudication { font-size: var(--wp-font-size, 13px); padding: 16px; }
.methodology-context { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.8; }
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }
.adj-warning { margin-bottom: 12px; }
.table-section { margin-bottom: 20px; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; font-weight: 600; font-size: 14px; }
.block-actions { display: flex; align-items: center; gap: 4px; }
.block-title { font-size: 14px; }
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; color: #303133; font-weight: 500; }
.adjudication-table :deep(.row-subtotal td) { font-weight: 600; background: #f0f9ff !important; }
.subtotal-text { font-weight: 600; }
.rate-warn { color: #d97706; font-weight: 600; background: #fefce8; padding: 1px 4px; border-radius: 2px; }
.linkage-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.cross-ref-bar { display: flex; align-items: center; gap: 8px; padding: 12px 0; flex-wrap: wrap; }
.cross-ref-label { color: #606266; font-size: var(--wp-font-size, 13px); }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.conclusion-select { width: 100%; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
