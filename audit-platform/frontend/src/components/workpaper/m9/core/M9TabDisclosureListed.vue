<template>
  <div class="m9-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-listed'" :disabled="isReadonly" @click="handleAI('disclosure-listed')">
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
        <strong>上市公司其他综合收益披露：</strong>
        资产负债表与利润表口径分别保存。每张表按不能重分类与将重分类两类，列示期初余额、
        税前发生额、转入损益、所得税、税后归属及期末余额。
      </div>
    </div>

    <!-- ═══ Section 1: 不能重分类进损益的OCI ═══ -->
    <div class="statement-switch">
      <el-radio-group v-model="activeStatement" size="small">
        <el-radio-button value="balanceSheet">资产负债表口径</el-radio-button>
        <el-radio-button value="incomeStatement">利润表口径</el-radio-button>
      </el-radio-group>
      <span>两张披露表独立保存，切换不会互相覆盖。</span>
    </div>
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、不能重分类进损益的其他综合收益</span>
          <el-button size="small" :loading="aiLoading === 'section-non-reclass'" :disabled="isReadonly" @click="handleAI('section-non-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="nonReclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorYearAmount"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'priorYearAmount', val)" />
            <span v-else>{{ fmtAmount(row.priorYearAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期所得税前发生额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.preTaxAmount"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'preTaxAmount', val)" />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减：前期转入损益" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.transferToPl"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'transferToPl', val)" />
            <span v-else>{{ fmtAmount(row.transferToPl) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减：所得税费用" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.taxEffect"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'taxEffect', val)" />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后归属于母公司" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.preTaxAmount - row.transferToPl - row.taxEffect - row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后归属于少数股东" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.afterTaxMinority"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'afterTaxMinority', val)" />
            <span v-else>{{ fmtAmount(row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.priorYearAmount + row.preTaxAmount - row.transferToPl - row.taxEffect - row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 能重分类进损益的OCI ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、将重分类进损益的其他综合收益</span>
          <el-button size="small" :loading="aiLoading === 'section-reclass'" :disabled="isReadonly" @click="handleAI('section-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="reclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorYearAmount"
              @update:model-value="(val: number) => updateReclassRow($index, 'priorYearAmount', val)" />
            <span v-else>{{ fmtAmount(row.priorYearAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期所得税前发生额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.preTaxAmount"
              @update:model-value="(val: number) => updateReclassRow($index, 'preTaxAmount', val)" />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减：前期转入损益" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.transferToPl"
              @update:model-value="(val: number) => updateReclassRow($index, 'transferToPl', val)" />
            <span v-else>{{ fmtAmount(row.transferToPl) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减：所得税费用" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.taxEffect"
              @update:model-value="(val: number) => updateReclassRow($index, 'taxEffect', val)" />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后归属于母公司" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.preTaxAmount - row.transferToPl - row.taxEffect - row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后归属于少数股东" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.afterTaxMinority"
              @update:model-value="(val: number) => updateReclassRow($index, 'afterTaxMinority', val)" />
            <span v-else>{{ fmtAmount(row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.priorYearAmount + row.preTaxAmount - row.transferToPl - row.taxEffect - row.afterTaxMinority) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 3: OCI合计 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、其他综合收益合计</span>
          <el-button size="small" :loading="aiLoading === 'section-total'" :disabled="isReadonly" @click="handleAI('section-total')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="不可重分类税后净额合计">{{ fmtAmount(nonReclassTotalNet) }}</el-descriptions-item>
        <el-descriptions-item label="可重分类税后净额合计">{{ fmtAmount(reclassTotalNet) }}</el-descriptions-item>
        <el-descriptions-item label="OCI税后净额合计">{{ fmtAmount(totalNet) }}</el-descriptions-item>
        <el-descriptions-item label="期初余额合计">{{ fmtAmount(totalPriorYear) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══ Section 4: 其他综合收益补充说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、其他综合收益相关说明</span>
          <el-button size="small" :loading="aiLoading === 'section-remark'" :disabled="isReadonly" @click="handleAI('section-remark')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="ociRemarkNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明各项其他综合收益的具体组成、变动原因及对所有者权益的影响..."
        @change="handleOciRemarkChange"
      />
    </el-card>

    <!-- ═══ Section 5: 转出至留存收益说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、OCI转出至留存收益说明</span>
          <el-button size="small" :loading="aiLoading === 'section-transfer'" :disabled="isReadonly" @click="handleAI('section-transfer')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="transferNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本期从其他综合收益转入留存收益的项目及金额（如处置其他权益工具投资转回等）..."
        @change="handleTransferNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M9-1审定表和M9-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司按CAS30分两大类披露：不可重分类+可重分类</li>
        <li>每项列示：税前发生额-所得税影响=税后净额</li>
        <li>格式：30行×18列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M9TabDisclosureListed — 附注披露信息（上市公司）30×18
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.5
 * Requirements: 5.2, 5.3, 5.4
 *
 * 功能：
 * - 上市公司附注模板（30×18）
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - 两大类OCI分别列示（不可重分类/可重分类）
 * - 税前-所得税=税后净额公式列
 * - AI辅助按钮 each section
 * - autosize textarea for 文本段
 */
import { computed, inject, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM9FormData } from '../../composables/useM9FormData'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  buildM9DisclosurePayload,
  createM9ListedRows,
  m9NoteText,
  restoreM9ListedRows,
  type M9Group,
  type M9ListedUiRow,
  type M9Statement,
} from '../../composables/m9DisclosureForm'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM9FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 同步链路 ───────────────────────────────────────────────────────────────

const activeStatement = ref<M9Statement>('balanceSheet')
const balanceSheetNonRows = ref<M9ListedUiRow[]>(createM9ListedRows('nonReclass'))
const balanceSheetReclassRows = ref<M9ListedUiRow[]>(createM9ListedRows('reclass'))
const incomeStatementNonRows = ref<M9ListedUiRow[]>(createM9ListedRows('nonReclass'))
const incomeStatementReclassRows = ref<M9ListedUiRow[]>(createM9ListedRows('reclass'))
const nonReclassRows = computed(() => activeStatement.value === 'balanceSheet'
  ? balanceSheetNonRows.value
  : incomeStatementNonRows.value)
const reclassRows = computed(() => activeStatement.value === 'balanceSheet'
  ? balanceSheetReclassRows.value
  : incomeStatementReclassRows.value)

async function syncToDisclosureNotes(): Promise<void> {
  const payload = buildM9DisclosurePayload({
    variant: 'listed',
    wpId: props.wpId,
    bsNon: balanceSheetNonRows.value,
    bsReclass: balanceSheetReclassRows.value,
    plNon: incomeStatementNonRows.value,
    plReclass: incomeStatementReclassRows.value,
    noteText: m9NoteText(formData.allResponses.value, 'listed'),
  })
  if (!payload || props.isReadonly) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── State: 不可重分类OCI行 ─────────────────────────────────────────────────



// ─── State: 可重分类OCI行 ───────────────────────────────────────────────────


// ─── State: 文本区 ──────────────────────────────────────────────────────────

const ociRemarkNote = ref('')
const transferNote = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

const listedNet = (row: M9ListedUiRow) => row.preTaxAmount - row.transferToPl - row.taxEffect
const nonReclassTotalNet = computed(() => nonReclassRows.value.reduce((sum, row) => sum + listedNet(row), 0))

const reclassTotalNet = computed(() => reclassRows.value.reduce((sum, row) => sum + listedNet(row), 0))

const totalNet = computed(() => nonReclassTotalNet.value + reclassTotalNet.value)

const totalPriorYear = computed(() => {
  return [...nonReclassRows.value, ...reclassRows.value]
    .reduce((sum, row) => sum + row.priorYearAmount, 0)
})

// ─── Handlers ────────────────────────────────────────────────────────────────

type M9ListedNumericField = Exclude<keyof M9ListedUiRow, 'key' | 'item'>
function updateListedRow(group: M9Group, index: number, field: M9ListedNumericField, val: number): void {
  if (props.isReadonly) return
  const rows = group === 'nonReclass' ? nonReclassRows.value : reclassRows.value
  const row = rows[index]
  if (!row) return
  row[field] = Number(val) || 0
  formData.debouncedSave(
    `M9-disclosure-listed-${activeStatement.value}-${group}-${row.key}-${field}`,
    { remark: String(val) },
  )
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}
function updateNonReclassRow(index: number, field: M9ListedNumericField, val: number) {
  updateListedRow('nonReclass', index, field, val)
}

function updateReclassRow(index: number, field: M9ListedNumericField, val: number) {
  updateListedRow('reclass', index, field, val)
}

function handleOciRemarkChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M9-disclosure-listed-remark', { remark: ociRemarkNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleTransferNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M9-disclosure-listed-transfer', { remark: transferNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const LISTED_NOTE_TARGETS: Record<string, { get: () => string; set: (v: string) => void; save: () => void }> = {
  'section-remark': { get: () => ociRemarkNote.value, set: (v) => { ociRemarkNote.value = v }, save: handleOciRemarkChange },
  'section-transfer': { get: () => transferNote.value, set: (v) => { transferNote.value = v }, save: handleTransferNoteChange },
}

async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4003 其他综合收益 / 附注披露（上市公司，30×18）',
      不可重分类税后合计: fmtAmount(nonReclassTotalNet.value),
      可重分类税后合计: fmtAmount(reclassTotalNet.value),
      OCI税后净额合计: fmtAmount(totalNet.value),
      期初余额合计: fmtAmount(totalPriorYear.value),
    }
    const target = LISTED_NOTE_TARGETS[section]
    const text = await generateAiText({ section: `m9-disclosure-listed-${section}`, context, existingContent: target ? target.get() : '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target) { target.set(text); target.save() }
    else { ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {}) }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M9-disclosure-listed', '附注披露（上市）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function restoreData(): void {
  const responses = formData.allResponses.value
  balanceSheetNonRows.value = restoreM9ListedRows(responses, 'balanceSheet', 'nonReclass')
  balanceSheetReclassRows.value = restoreM9ListedRows(responses, 'balanceSheet', 'reclass')
  incomeStatementNonRows.value = restoreM9ListedRows(responses, 'incomeStatement', 'nonReclass')
  incomeStatementReclassRows.value = restoreM9ListedRows(responses, 'incomeStatement', 'reclass')
  ociRemarkNote.value = responses.get('M9-disclosure-listed-remark')?.remark || ''
  transferNote.value = responses.get('M9-disclosure-listed-transfer')?.remark || ''
}
async function onAdjudicatedRefresh(): Promise<void> {
  await formData.loadData()
  restoreData()
}

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.m9-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.statement-switch { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; color: #606266; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #409eff; border-bottom: 1px dashed #409eff; cursor: help; }
.m9-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
