<template>
  <div class="m8-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-listed'" @click="handleAI('disclosure-listed')">
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
        <strong>上市公司一般风险准备附注披露（11×14）：</strong>
        按企业会计准则要求，金融企业应在附注中披露一般风险准备的期初余额、本期增减变动及期末余额。
        数据从M8-2明细表自动拉取（期初余额 = M8-2!L10跨sheet引用），subscribe 'substantive:adjudicated' 事件自动刷新。
        期末余额 = 期初余额 + 本期增加 − 本期减少（<strong>权益类贷方</strong>方向）。
      </div>
    </div>

    <!-- ═══ 一般风险准备变动表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一般风险准备变动表</span>
          <el-button size="small" :loading="aiLoading === 'section-movement'" @click="handleAI('section-movement')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <el-table :data="tableRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <!-- A列: 项目 -->
        <el-table-column prop="item" label="项目" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._rowType === 'total' }">{{ row.item }}</span>
          </template>
        </el-table-column>

        <!-- B列: 期初余额 -->
        <el-table-column label="期初余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期初余额引用M8-2明细表合计（跨sheet）" placement="top">
              <span class="formula-col-header">期初余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="row._rowType === 'data' && !isReadonly">
              <WpAmountInput
                :model-value="row.beginBalance"
                @update:model-value="(val: number) => updateDataRow($index, 'beginBalance', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._rowType === 'total' }">
              {{ fmtAmount(row.beginBalance) }}
            </span>
          </template>
        </el-table-column>

        <!-- C列: 本期增加 -->
        <el-table-column label="本期增加" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="row._rowType === 'data' && !isReadonly">
              <WpAmountInput
                :model-value="row.currentIncrease"
                @update:model-value="(val: number) => updateDataRow($index, 'currentIncrease', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._rowType === 'total' }">
              {{ fmtAmount(row.currentIncrease) }}
            </span>
          </template>
        </el-table-column>

        <!-- D列: 本期减少 -->
        <el-table-column label="本期减少" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="row._rowType === 'data' && !isReadonly">
              <WpAmountInput
                :model-value="row.currentDecrease"
                @update:model-value="(val: number) => updateDataRow($index, 'currentDecrease', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._rowType === 'total' }">
              {{ fmtAmount(row.currentDecrease) }}
            </span>
          </template>
        </el-table-column>

        <!-- E列: 期末余额（公式列） -->
        <el-table-column label="期末余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期末余额 = 期初余额 + 本期增加 − 本期减少（权益类贷方！）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注说明文本区 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>附注说明</span>
          <el-button size="small" :loading="aiLoading === 'section-note'" @click="handleAI('section-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="disclosureNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明一般风险准备计提政策、计提比例、变动原因等..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司应披露一般风险准备的变动情况（期初+增加-减少=期末）</li>
        <li>期初余额 B7 引用 M8-2明细表!L10（跨sheet reference）</li>
        <li>权益类贷方方向：<strong>期末 = 期初 + 本期增加（计提） − 本期减少（转回/使用）</strong></li>
        <li>Formulas: E=B+C-D; B10=SUM(B7:B9); C10=SUM(C7:C9); D10=SUM(D7:D9); E10=SUM(E7:E9)</li>
        <li>数据从审定表/明细表自动拉取（subscribe 'substantive:adjudicated' 刷新）</li>
        <li>3 data rows + 1 total row (合计SUM)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabDisclosureListed — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 4.5
 * Requirements: 4.2-4.4
 *
 * xlsx结构：11×14, 16 formulas
 * Columns: 项目(A) | 期初余额(B) | 本期增加(C) | 本期减少(D) | 期末余额(E=B+C-D, 权益类贷方!)
 * 3 data rows + 1 total row (SUM)
 * Formulas: E=B+C-D, B10=SUM(B7:B9), C10=SUM(C7:C9), D10=SUM(D7:D9), E10=SUM(E7:E9)
 * 期初余额 B7 = 明细表M8-2!L10 (cross-sheet reference)
 * Subscribe to EventBus 'substantive:adjudicated' to refresh data
 *
 * Composables: useM8FormData + useVersionTrail（双模式由主入口统一承载）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM8FormData } from '../../composables/useM8FormData'
import { useVersionTrail } from '../../composables/useVersionTrail'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'
import { calcEquityEndBalance, calcSubtotal } from '../../composables/useM8FormulaEngine'
import WpAmountInput from '../../shared/WpAmountInput.vue'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ─── Inject复核对话 + AI ─────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── 同步链路 ───────────────────────────────────────────────────────────────
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildM8SyncPayload, type M8DisclosureRow } from '../../composables/m8NoteSectionMap'
import http from '@/utils/http'

async function syncToDisclosureNotes(): Promise<void> {
  const rows: M8DisclosureRow[] = dataRows.value.map((r: any) => ({
    label: r.item || r.label || '',
    begin: Number(r.beginAmount) || 0,
    increase: Number(r.increaseAmount) || 0,
    decrease: Number(r.decreaseAmount) || 0,
  }))
  const payload = buildM8SyncPayload(props.wpId, 'listed', rows, disclosureNote.value)
  if (!payload) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const { scheduleAutoSync } = useDisclosureAutoSync(syncToDisclosureNotes)

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const versionTrail = useVersionTrail({
  projectId: computed(() => props.projectId),
  workpaperId: computed(() => props.wpId),
})

// ─── Data Rows (3 data rows corresponding to xlsx rows 7-9) ─────────────────
interface DisclosureDataRow {
  item: string
  beginBalance: number
  currentIncrease: number
  currentDecrease: number
}

const dataRows = ref<DisclosureDataRow[]>([
  { item: '一般风险准备—信贷资产', beginBalance: 0, currentIncrease: 0, currentDecrease: 0 },
  { item: '一般风险准备—投资资产', beginBalance: 0, currentIncrease: 0, currentDecrease: 0 },
  { item: '一般风险准备—其他', beginBalance: 0, currentIncrease: 0, currentDecrease: 0 },
])

// ─── Computed: table rows with total ─────────────────────────────────────────
interface TableRow {
  item: string
  beginBalance: number
  currentIncrease: number
  currentDecrease: number
  endBalance: number
  _rowType: 'data' | 'total'
}

const tableRows = computed<TableRow[]>(() => {
  const rows: TableRow[] = dataRows.value.map(r => ({
    item: r.item,
    beginBalance: r.beginBalance,
    currentIncrease: r.currentIncrease,
    currentDecrease: r.currentDecrease,
    // E=B+C-D (权益类贷方！)
    endBalance: calcEquityEndBalance(r.beginBalance, r.currentIncrease, r.currentDecrease),
    _rowType: 'data' as const,
  }))

  // Total row (SUM)
  const totalBegin = calcSubtotal(dataRows.value.map(r => r.beginBalance))
  const totalIncrease = calcSubtotal(dataRows.value.map(r => r.currentIncrease))
  const totalDecrease = calcSubtotal(dataRows.value.map(r => r.currentDecrease))
  rows.push({
    item: '合 计',
    beginBalance: totalBegin,
    currentIncrease: totalIncrease,
    currentDecrease: totalDecrease,
    endBalance: calcEquityEndBalance(totalBegin, totalIncrease, totalDecrease),
    _rowType: 'total',
  })

  return rows
})

// ─── State: 附注说明 ─────────────────────────────────────────────────────────
const disclosureNote = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function updateDataRow(tableIndex: number, field: keyof DisclosureDataRow, val: number): void {
  // tableIndex maps directly to dataRows for data rows only
  if (tableIndex >= 0 && tableIndex < dataRows.value.length) {
    (dataRows.value[tableIndex] as any)[field] = val
    formData.debouncedSave(`M8-disclosure-listed-row-${tableIndex}-${field}`, { remark: String(val) })
    scheduleAutoSync()
  }
}

function handleNoteChange(): void {
  formData.debouncedSave('M8-disclosure-listed-note', { remark: disclosureNote.value || null })
  scheduleAutoSync()
}

async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const total = tableRows.value.find(r => r._rowType === 'total')
    const context: Record<string, string> = {
      科目: '4104 一般风险准备（权益类/贷方）',
      底稿: 'M8 附注披露信息（上市公司）',
      期初余额合计: fmtAmount(total?.beginBalance ?? 0),
      本期增加合计: fmtAmount(total?.currentIncrease ?? 0),
      本期减少合计: fmtAmount(total?.currentDecrease ?? 0),
      期末余额合计: fmtAmount(total?.endBalance ?? 0),
    }
    const text = await generateAiText({ section: `m8-disclosure-listed-${section}`, context, existingContent: disclosureNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    disclosureNote.value = text
    handleNoteChange()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview(): void { openReviewDialog?.('M8-disclosure-listed', '附注披露（上市）') }

function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'total') return 'total-row'
  return ''
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh(payload: { accountCode: string; auditedAmount: number; wpCode: string; timestamp: number }): void {
  if (payload?.wpCode === 'M8' || payload?.accountCode === '4104') {
    formData.loadData().then(() => _restoreData())
  }
}

onMounted(async () => {
  await formData.loadData()
  _restoreData()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
})

/** 从 checklist_responses 恢复数据 */
function _restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    const fields: (keyof DisclosureDataRow)[] = ['beginBalance', 'currentIncrease', 'currentDecrease']
    for (const field of fields) {
      const resp = formData.allResponses.value.get(`M8-disclosure-listed-row-${i}-${field}`)
      if (resp?.remark) {
        (dataRows.value[i] as any)[field] = Number(resp.remark) || 0
      }
    }
  }

  // Cross-sheet reference: 期初余额 B7 from M8-2 detail total
  const detailBeginTotal = formData.getField('2', 'total-beginBalance')
  if (detailBeginTotal !== null && detailBeginTotal !== undefined) {
    // Distribute to first row if available
    const numVal = Number(detailBeginTotal)
    if (!isNaN(numVal) && numVal !== 0 && dataRows.value[0].beginBalance === 0) {
      dataRows.value[0].beginBalance = numVal
    }
  }

  // 恢复附注说明
  const noteResp = formData.allResponses.value.get('M8-disclosure-listed-note')
  if (noteResp?.remark) disclosureNote.value = noteResp.remark
}
</script>

<style scoped>
.m8-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* ─── Card ─── */
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

/* ─── Formula columns ─── */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

/* ─── Row styles ─── */
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #ecf5ff !important; font-weight: 700; }
:deep(.total-row td) { border-top: 2px solid #409eff; }

/* ─── 编制提示 ─── */
.m8-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m8-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m8-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m8-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
