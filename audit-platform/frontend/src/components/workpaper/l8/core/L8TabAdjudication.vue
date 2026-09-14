<template>
  <div class="l8-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-1 财务费用审定表</h3>
        <el-tag type="danger" size="small">损益类·发生额</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-button size="small" @click="handleAI('adjudication')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>确认财务费用发生额的真实、完整、准确与期间归属（损益类取发生额），核查利息费用、汇兑损益及手续费的合理性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>财务费用为损益类借方科目（6603）：</strong>
        本期发生额 = 借方发生 − 贷方发生（费用为借方科目，借增贷减）。
        审定数 = 未审数 + AJE + RJE。10项费用按符号合计（+利息费用−利息资本化−利息收入+…），
        审定数变化自动回写试算表（发生额口径！）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 审定表主体（10项目行+合计+TB核对） ═══ -->
    <div class="block-section">
      <h4 class="block-title">财务费用（借方/损益类·发生额口径）</h4>
      <el-table
        :data="tableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目名称 -->
        <el-table-column prop="itemName" label="项目" min-width="180" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSummaryRow($index)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else>
              <span :class="{ 'sign-minus': row.sign === -1 }">{{ row.itemName }}</span>
            </template>
          </template>
        </el-table-column>

        <!-- B列: 本期未审数（发生额） -->
        <el-table-column label="本期未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.currentUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleUpdate($index, 'currentUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- C列: AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.currentAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleUpdate($index, 'currentAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.currentAje) }}</span>
          </template>
        </el-table-column>

        <!-- D列: RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.currentRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleUpdate($index, 'currentRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.currentRje) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 审定数（公式） -->
        <el-table-column label="审定数" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.currentAudited) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 上期发生额 -->
        <el-table-column label="上期发生额" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.priorOccurrence"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleUpdate($index, 'priorOccurrence', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.priorOccurrence) }}</span>
          </template>
        </el-table-column>

        <!-- G列: 变动额（公式） -->
        <el-table-column label="变动额" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 审定数 − 上期发生额" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'negative-value': row.changeAmount < 0 }">
              {{ fmtAmount(row.changeAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- H列: 变动率（公式） -->
        <el-table-column label="变动率" width="100" align="right">
          <template #header>
            <el-tooltip content="公式: (审定−上期)/上期×100%" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <span
              class="formula-value"
              :class="{ 'abnormal-rate': isAbnormalRow($index) }"
            >
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>

        <!-- I列: 原因分析 -->
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input
                :model-value="row.reasonAnalysis || ''"
                size="small"
                placeholder="变动原因"
                @change="(val: string) => handleReasonUpdate($index, val)"
              />
            </template>
            <span v-else>{{ row.reasonAnalysis || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- TB回写按钮 -->
      <div class="tb-writeback-bar">
        <el-button
          type="warning"
          size="small"
          :disabled="isReadonly"
          :loading="isWritingBack"
          @click="handleWritebackTB"
        >
          TB回写（发生额口径！）
        </el-button>
        <span class="tb-hint">将审定合计回写试算表科目6603（损益类发生额口径）</span>
      </div>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 利息来源联动：</span>
      <GtIndexChip value="L1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">短期借款利息</span>
      <GtIndexChip value="L3" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">长期借款利息</span>
      <GtIndexChip value="L4" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">应付债券利息</span>
      <GtIndexChip value="L5" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">未确认融资费用摊销</span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>损益类科目（6603）：</strong>本期发生额 = 借方发生 − 贷方发生（不是期末余额！）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>合计 = +利息费用总额 − 利息资本化 − 利息收入 + 未确认融资费用 − 未实现融资收益 + 承兑贴息 + 汇兑损失 − 汇兑收益 − 汇兑资本化 + 手续费及其他</li>
        <li>变动额 = 本期审定 − 上期发生额；变动率 = 变动额 / 上期 × 100%</li>
        <li>TB回写使用发生额口径，与L1~L7负债类余额口径不同！</li>
        <li>「带入调整」：可从集中登记按科目 6603 拉取调整分录，逐笔分配到各费用项目行的本期账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6603 财务费用"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabAdjudication — L8-1 财务费用审定表（损益类！发生额口径）
 *
 * Requirements: 2.1-2.7
 * - 损益类10项费用行 + 签名合计 + TB核对行
 * - 列结构：项目|本期未审|AJE|RJE|审定[公式]|上期发生额|变动额[公式]|变动率[公式]|原因分析
 * - 合计 = +B7-B8-B9+B10-B11+B12+B13-B14-B15+B16（按sign加减）
 * - TB回写: 审定数变化 → writebackTB(6603发生额口径)
 * - EventBus: publish 'substantive:adjudicated' + subscribe 'adjustment:created'
 *
 * 科目：6603 财务费用（借方/损益类！取发生额，不是余额！）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL8FormData } from '../../composables/useL8FormData'
import { useL8DualMode } from '../../composables/useL8DualMode'
import {
  useL8Adjudication,
  L8_ADJUDICATION_ITEMS,
  type L8AdjudicationRow,
} from '../../composables/useL8Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData + DualMode ─────────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const dualMode = useL8DualMode({
  wpId: computed(() => props.wpId),
})

// ─── 审定表行数据（10个费用项目行） ─────────────────────────────────────────

const rows = ref<L8AdjudicationRow[]>(
  L8_ADJUDICATION_ITEMS.map(item => ({
    key: item.key,
    itemName: item.itemName,
    sign: item.sign,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    priorOccurrence: 0,
    changeAmount: 0,
    changeRate: 0,
  }))
)

/** 原因分析（独立存储） */
const reasonAnalyses = ref<Record<string, string>>({})

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows,
  totalRow,
  abnormalChangeRows,
  updateRow,
  saveAndWriteback,
} = useL8Adjudication(formData, rows)

// ─── 从集中登记带入调整（6603 财务费用，损益借方·发生额口径；带入本期 AJE/RJE） ────
const bringInRows = computed(() =>
  computedRows.value.map((r) => ({ rowKey: r.key, name: r.itemName, aje: r.currentAje, rje: r.currentRje })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6603',
  direction: 'debit',
  subjectCode: '6603',
  wpCode: 'L8',
  subjectLabel: '财务费用(6603)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => {
    const i = rows.value.findIndex((r) => r.key === rowKey)
    if (i >= 0) handleUpdate(i, field === 'rje' ? 'currentRje' : 'currentAje', value)
  },
  totalAudited: () => totalRow.value.currentAudited,
})

// ─── 拼装表格数据（10项目行+合计行+TB核对行） ────────────────────────────────

const tableData = computed(() => {
  const projectRows = computedRows.value.map((r, i) => ({
    ...r,
    reasonAnalysis: reasonAnalyses.value[r.key] || '',
  }))
  const totalRowData = {
    key: 'total',
    itemName: '合  计',
    sign: 1 as const,
    currentUnadjusted: totalRow.value.currentUnadjusted,
    currentAje: totalRow.value.currentAje,
    currentRje: totalRow.value.currentRje,
    currentAudited: totalRow.value.currentAudited,
    priorOccurrence: totalRow.value.priorOccurrence,
    changeAmount: totalRow.value.changeAmount,
    changeRate: totalRow.value.changeRate,
    reasonAnalysis: '',
  }
  const tbRow = {
    key: 'tb-check',
    itemName: 'TB核对（发生额）',
    sign: 1 as const,
    currentUnadjusted: formData.tbOccurrence.value.net,
    currentAje: 0,
    currentRje: 0,
    currentAudited: formData.tbOccurrence.value.net,
    priorOccurrence: 0,
    changeAmount: 0,
    changeRate: 'N/A' as any,
    reasonAnalysis: '',
  }
  return [...projectRows, totalRowData, tbRow]
})

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

const PROJECT_ROW_COUNT = 10

function isEditableRow(index: number): boolean {
  return index < PROJECT_ROW_COUNT
}

function isSummaryRow(index: number): boolean {
  return index >= PROJECT_ROW_COUNT
}

function isAbnormalRow(index: number): boolean {
  return abnormalChangeRows.value.includes(index)
}

function getRowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  if (rowIndex === PROJECT_ROW_COUNT) return 'total-row'
  if (rowIndex === PROJECT_ROW_COUNT + 1) return 'tb-check-row'
  if (isAbnormalRow(rowIndex)) return 'abnormal-row'
  return ''
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const isWritingBack = ref(false)
const auditNote = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUpdate(index: number, field: string, value: number): void {
  if (!isEditableRow(index)) return
  updateRow(index, field as any, value)
}

function handleReasonUpdate(index: number, value: string): void {
  if (!isEditableRow(index)) return
  const row = rows.value[index]
  if (row) {
    reasonAnalyses.value[row.key] = value
    formData.debouncedSave(`L8-1-reason-${row.key}`, { remark: value || null })
  }
}

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
  } finally {
    isSaving.value = false
  }
}

async function handleWritebackTB() {
  isWritingBack.value = true
  try {
    await formData.writebackTB(totalRow.value.currentAudited)
  } finally {
    isWritingBack.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('L8-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l8-adjudication-${section}`,
      prompt: `请基于财务费用底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('L8-1-adjudication', '审定表')
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | 'N/A'): string {
  if (val === 'N/A') return 'N/A'
  if (val === 0) return '—'
  return val.toFixed(2) + '%'
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjustmentCreated() {
  formData.loadData()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 恢复行数据
  _restoreFromResponses()
  // 订阅调整分录事件
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
})

function _restoreFromResponses() {
  for (let i = 0; i < rows.value.length; i++) {
    const row = rows.value[i]
    const data = formData.allResponses.value.get(`L8-1-row-${row.key}-data`)
    if (data?.remark) {
      try {
        const parsed = JSON.parse(data.remark)
        row.currentUnadjusted = parsed.currentUnadjusted ?? 0
        row.currentAje = parsed.currentAje ?? 0
        row.currentRje = parsed.currentRje ?? 0
        row.priorOccurrence = parsed.priorOccurrence ?? 0
      } catch { /* ignore */ }
    }
    // 恢复原因分析
    const reason = formData.allResponses.value.get(`L8-1-reason-${row.key}`)
    if (reason?.remark) {
      reasonAnalyses.value[row.key] = reason.remark
    }
  }
  // 恢复审计说明
  const note = formData.allResponses.value.get('L8-1-auditNote')
  if (note?.remark) auditNote.value = note.remark
}
</script>

<style scoped>
.l8-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.block-section { margin-bottom: 24px; }
.block-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.negative-value { color: #f56c6c; }
.abnormal-rate { color: #e6a23c; font-weight: 700; }
.total-row-label { font-weight: 700; color: #303133; }
.sign-minus { color: #909399; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9ff !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #409eff; }
:deep(.tb-check-row) { background: #f5f7fa !important; font-style: italic; color: #909399; }
:deep(.abnormal-row) { background: #fef0e6 !important; }
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; margin-top: 12px; padding: 8px 12px; background: #fdf6ec; border-radius: 6px; }
.tb-hint { font-size: 12px; color: #e6a23c; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
