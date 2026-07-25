<template>
  <div class="l7-tab-adjudication">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L7-1 其他非流动负债审定表</h3>
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
        <strong>审计目标：</strong>确认其他非流动负债余额的存在、完整、准确与列报，核查项目分类（递延收益/保证金/押金等）的恰当性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他非流动负债为负债类贷方科目（2801）：</strong>
        期末审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）。
        变动额 = 期末审定 − 期初审定。按项目分类列示，包括递延收益（非流动）、保证金、押金等。
        审定数变化自动回写试算表并通知附注组件。
      </div>
    </div>

    <!-- ═══ 其他非流动负债审定区块（单区块） ═══ -->
    <div class="block-section">
      <h4 class="block-title">其他非流动负债（贷方/负债类）</h4>
      <el-table
        :data="computedRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目名称 -->
        <el-table-column prop="itemName" label="项目名称" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isTotalRow($index) || isTbCheckRow($index)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => updateRow($index, 'itemName', val)"
              />
            </template>
            <template v-else>
              {{ row.itemName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- B列: 期初未审数 -->
        <el-table-column label="期初未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 期初AJE -->
        <el-table-column label="期初AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 期初RJE -->
        <el-table-column label="期初RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期初审定数（公式） -->
        <el-table-column label="期初审定" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期初未审 + 期初AJE + 期初RJE" placement="top">
              <span class="formula-col-header">期初审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 期末未审数 -->
        <el-table-column label="期末未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: 期末AJE -->
        <el-table-column label="期末AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: 期末RJE -->
        <el-table-column label="期末RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 期末审定数（公式） -->
        <el-table-column label="期末审定" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期末未审 + 期末AJE + 期末RJE" placement="top">
              <span class="formula-col-header">期末审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAudited) }}</span>
          </template>
        </el-table-column>

        <!-- J列: 变动额（公式） -->
        <el-table-column label="变动额" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期末审定 − 期初审定" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'negative-value': row.variance < 0 }">
              {{ fmtAmount(row.variance) }}
            </span>
          </template>
        </el-table-column>

        <!-- K列: 变动率（公式） -->
        <el-table-column label="变动率" width="100" align="right">
          <template #header>
            <el-tooltip content="公式: 变动额 / 期初审定" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row.varianceRate) }}</span>
          </template>
        </el-table-column>

        <!-- 交叉引用 -->
        <el-table-column label="索引" width="80" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.refIndex" :value="row.refIndex" />
          </template>
        </el-table-column>
      </el-table>

      <!-- 期末异常提示 -->
      <el-alert
        v-if="totalRow.endAudited < 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 8px"
      >
        余额异常：其他非流动负债期末审定数为负，请核查数据
      </el-alert>
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

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他非流动负债为负债类贷方科目（2801）：期末 = 期初 + 贷方 − 借方</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>变动额 = 期末审定 − 期初审定；变动率 = 变动额 / 期初审定</li>
        <li>按项目分类填列：递延收益（非流动）、保证金、押金、其他等</li>
        <li>合计行自动汇总各项目行数据</li>
        <li>TB核对行自动从试算表取数，用于校验录入正确性</li>
        <li>审定数变化自动回写 TB（科目 2801）并通知附注组件</li>
        <li>「带入调整」：可从集中登记按科目 2801 拉取调整分录，逐笔分配到各项目行的期末账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2801 其他非流动负债"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabAdjudication — L7-1 其他非流动负债审定表
 *
 * Requirements: 2.1-2.7
 * - 负债类单区块：5个项目行 + 合计行 + TB核对行
 * - 12列结构（xlsx B~K）：
 *   A:项目名称 | B-E:期初(未审/AJE/RJE/审定[公式]) | F-I:期末(未审/AJE/RJE/审定[公式]) | J:变动额[公式] | K:变动率[公式]
 * - 公式列: 虚线下划线 + cursor:help + tooltip showing formula source
 * - TB回写: 审定数变化 → writebackTB(2801)
 * - EventBus: subscribe 'adjustment:created' → refresh AJE/RJE columns
 * - el-segmented 双模式(HTML/OO) at top using useL7DualMode
 * - GtIndexChip for cross-references
 * - Font 13px, formula columns with dashed-underline style
 * - 方法论上下文: amber left-border block
 * - Props: wpId, projectId, isReadonly
 * - inject 'openReviewDialog' for review button
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, inject, onMounted, onUnmounted, reactive, ref } from 'vue'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL7FormData } from '../../composables/useL7FormData'
import { useL7DualMode } from '../../composables/useL7DualMode'
import {
  useL7Adjudication,
  type L7AdjudicationRow,
} from '../../composables/useL7Adjudication'
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

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useL7DualMode({
  wpId: computed(() => props.wpId),
})

// ─── 审定表行数据（5个项目行，对应xlsx row7~row11） ──────────────────────────

const rows = ref<L7AdjudicationRow[]>([
  { key: 'r1', itemName: '递延收益（非流动）', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'r2', itemName: '保证金及押金', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'r3', itemName: '长期应付款（非流动）', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'r4', itemName: '专项应付款', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'r5', itemName: '其他', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
])

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows: rawComputedRows,
  totalRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
} = useL7Adjudication(formData, rows)

// ─── 合计行 + TB核对行 → 拼装为表格数据 ────────────────────────────────────────

/** TB核对行（从试算表自动取数用于校验） */
const tbCheckRow = reactive<L7AdjudicationRow>({
  key: 'tb-check',
  itemName: 'TB核对',
  beginUnadjusted: 0,
  beginAje: 0,
  beginRje: 0,
  beginAudited: 0,
  endUnadjusted: 0,
  endAje: 0,
  endRje: 0,
  endAudited: 0,
  variance: 0,
  varianceRate: 0,
})

/** 全部表格行 = 5项目行 + 合计行 + TB核对行 */
const computedRows = computed(() => {
  const projectRows = rawComputedRows.value.map(r => ({ ...r, refIndex: '' }))
  const total = totalRow.value
  const totalRowData: L7AdjudicationRow & { refIndex: string } = {
    key: 'total',
    itemName: '合  计',
    beginUnadjusted: total.beginUnadjusted,
    beginAje: total.beginAje,
    beginRje: total.beginRje,
    beginAudited: total.beginAudited,
    endUnadjusted: total.endUnadjusted,
    endAje: total.endAje,
    endRje: total.endRje,
    endAudited: total.endAudited,
    variance: total.variance,
    varianceRate: total.varianceRate,
    refIndex: '',
  }
  const tbRow: L7AdjudicationRow & { refIndex: string } = {
    ...tbCheckRow,
    refIndex: 'TB',
  }
  return [...projectRows, totalRowData, tbRow]
})

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

const PROJECT_ROW_COUNT = 5

function isEditableRow(index: number): boolean {
  return index < PROJECT_ROW_COUNT
}

function isTotalRow(index: number): boolean {
  return index === PROJECT_ROW_COUNT
}

function isTbCheckRow(index: number): boolean {
  return index === PROJECT_ROW_COUNT + 1
}

function getRowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  if (isTotalRow(rowIndex)) return 'total-row'
  if (isTbCheckRow(rowIndex)) return 'tb-check-row'
  return ''
}

// ─── 行操作代理 ──────────────────────────────────────────────────────────────

function updateRow(index: number, field: string, value: string | number): void {
  if (!isEditableRow(index)) return
  composableUpdateRow(index, field as any, value)
}

// ─── 从集中登记带入调整（2801 其他非流动负债，负债贷方；带入期末 AJE/RJE） ─────────
const bringInRows = computed(() =>
  rawComputedRows.value.map((r) => ({ rowKey: r.key, name: r.itemName || '(未命名项目)', aje: r.endAje, rje: r.endRje })),
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
  subjectPrefix: '2801',
  direction: 'credit',
  subjectCode: '2801',
  wpCode: 'L7',
  subjectLabel: '其他非流动负债(2801)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => {
    const i = rows.value.findIndex((r) => r.key === rowKey)
    if (i >= 0) updateRow(i, field === 'rje' ? 'endRje' : 'endAje', value)
  },
  totalAudited: () => totalRow.value.endAudited,
})

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('L7-L7-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l7-adjudication-${section}`,
      prompt: `请基于其他非流动负债底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('L7-1-adjudication', '审定表')
}

// ─── EventBus: subscribe 'adjustment:created' 刷新AJE/RJE ────────────────────

function handleAdjustmentCreated() {
  // 重新加载数据以获取最新AJE/RJE
  formData.loadData()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 恢复审计说明（此前保存但从不回读）
  const note = formData.allResponses.value.get('L7-L7-1-auditNote')?.remark
  if (note != null) auditNote.value = note
  // 订阅调整分录创建事件
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.on('substantive:adjudicated' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.off('substantive:adjudicated' as any, handleAdjustmentCreated)
})
</script>

<style scoped>
.l7-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.block-section {
  margin-bottom: 24px;
}

.block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.negative-value {
  color: #f56c6c;
}

.total-row-label {
  font-weight: 700;
  color: #303133;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.total-row) {
  background: #f0f9ff !important;
  font-weight: 600;
}

:deep(.total-row td) {
  border-top: 2px solid #409eff;
}

:deep(.tb-check-row) {
  background: #f5f7fa !important;
  font-style: italic;
  color: #909399;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.l7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l7-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.l7-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
