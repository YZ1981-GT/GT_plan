<template>
  <div class="m8-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M8-1 一般风险准备审定表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额·4104
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" :disabled="isReadonly" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-button size="small" :loading="aiLoading === 'adjudication'" @click="handleAI('adjudication')">
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

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>一般风险准备（4104）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（计提增加） − 借方（转回/使用减少）。
        审定数 = 未审数 + AJE + RJE。
        金融企业从净利润中计提一般风险准备（贷方增加），原则上不低于风险资产期末余额的1.5%；
        弥补损失或经批准转回时借方减少。
        本表数据从明细表M8-2自动引用，审定数变化自动回写试算表（4104）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 单区块：一般风险准备审定 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">一般风险准备（4104 贷方/权益类）</h4>
      </div>

      <el-table
        :data="tableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目名称 -->
        <el-table-column prop="itemName" label="项目名称" min-width="150" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._rowType === 'total', 'diff-row-label': row._rowType === 'diff' }">
              {{ row.itemName || '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- B列: 期初未审 -->
        <el-table-column label="期初未审" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'beginUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 期初AJE -->
        <el-table-column label="期初AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'beginAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 期初RJE -->
        <el-table-column label="期初RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'beginRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期初审定（公式列） -->
        <el-table-column label="期初审定" width="120" align="right">
          <template #header>
            <el-tooltip content="期初审定 = 期初未审 + 期初AJE + 期初RJE" placement="top">
              <span class="formula-col-header">期初审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 期末未审 -->
        <el-table-column label="期末未审" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.endUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'endUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: 期末AJE -->
        <el-table-column label="期末AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.endAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'endAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: 期末RJE -->
        <el-table-column label="期末RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.endRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'endRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 期末审定（公式列） -->
        <el-table-column label="期末审定" width="120" align="right">
          <template #header>
            <el-tooltip content="期末审定 = 期末未审 + 期末AJE + 期末RJE" placement="top">
              <span class="formula-col-header">期末审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAudited) }}</span>
          </template>
        </el-table-column>

        <!-- J列: 变动额（公式列） -->
        <el-table-column label="变动额" width="120" align="right">
          <template #header>
            <el-tooltip content="变动额 = 期末审定 − 期初审定" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': Math.abs(row.changeAmount) > 0.01 && row._rowType !== 'prior' }]">
              {{ fmtAmount(row.changeAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- K列: 变动率（公式列） -->
        <el-table-column label="变动率" width="90" align="right">
          <template #header>
            <el-tooltip content="IF(期初审定=0且变动额=0, 0; 期初审定=0, 100%; 否则 变动额/期初审定)" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- L列: 原因分析 -->
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input
                :model-value="row.reason"
                size="small"
                placeholder="变动原因..."
                @change="(val: string) => handleUpdateRow($index, 'reason', val)"
              />
            </template>
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计 + TB回写状态 + 交叉验证 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">
        期末审定合计: {{ fmtAmount(adjudication.totalRow.value.endAudited) }}
      </el-tag>
      <el-tag type="success" size="small" effect="plain">
        TB回写: 科目4104 一般风险准备（贷方/权益类）
      </el-tag>
      <el-tag
        :type="crossValidation.isMatch ? 'success' : 'danger'"
        size="small"
        effect="plain"
      >
        M8-2交叉验证:
        {{ crossValidation.isMatch ? '一致 ✓' : `差异 ${fmtAmount(crossValidation.diff)}` }}
      </el-tag>
      <el-tag
        v-if="adjudication.totalRow.value.changeRate !== 0"
        :type="Math.abs(adjudication.totalRow.value.changeRate) > 0.2 ? 'warning' : 'info'"
        size="small"
        effect="plain"
      >
        变动率: {{ (adjudication.totalRow.value.changeRate * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
          <el-button size="small" :loading="aiLoading === 'conclusion'" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写一般风险准备审定表审计结论..."
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>一般风险准备（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提） − 借方（转回/使用）</li>
        <li><strong>金融企业专属</strong>：仅银行/证券/保险/金融企业适用</li>
        <li>计提：从净利润中计提，原则上不低于风险资产期末余额的1.5%</li>
        <li>转回/使用：弥补尚未识别的可能性损失或经批准转回</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>变动额 = 期末审定 − 期初审定；变动率 = 变动额 / 期初审定</li>
        <li>本表数据从M8-2明细表自动引用（Row 7-12），合计行SUM(B7:B12)</li>
        <li>Row 14: 上期审定数；Row 15: 差异 = 合计 − 上期审定数</li>
        <li>审定数变化自动回写 TB（科目 4104）并通知附注组件</li>
        <li>「带入调整」：从集中登记按科目 4104 拉取调整分录，逐笔分配到各明细行的期末 AJE/RJE，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="4104 一般风险准备"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabAdjudication — M8-1 一般风险准备审定表（权益类贷方！）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 权益类单区块（4104 一般风险准备, 贷方权益类, 金融企业专属）
 * xlsx结构：25×12 (A:L), 84公式
 * Columns: 项目名称 | 期初未审 | 期初AJE | 期初RJE | 期初审定 | 期末未审 | 期末AJE | 期末RJE | 期末审定 | 变动额 | 变动率 | 原因分析
 * Rows 7-12: Detail (引用M8-2), Row 13: 合计SUM, Row 14: 上期审定, Row 15: 差异
 *
 * - useM8FormData + useM8Adjudication composable
 * - Font 13px, formula columns with dashed underline + cursor:help + tooltip
 * - TB回写(4104) on 审定数变化
 * - EventBus 'substantive:adjudicated' publish
 * - 双模式 (HTML/OO) 由主入口 GtM8GeneralRiskReserve 统一承载（本 tab 仅结构化）
 * - 方法论上下文琥珀色块 (权益类贷方方向说明)
 * - el-card for 审计结论区
 * - Section标题行右侧AI辅助按钮 + 复核对话按钮
 * - 编制提示details折叠底部
 * - Version trail integration (useVersionTrail)
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import { useM8FormData } from '../../composables/useM8FormData'
import {
  useM8Adjudication,
  type M8AdjudicationRow,
} from '../../composables/useM8Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useVersionTrail } from '../../composables/useVersionTrail'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 + AI ─────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const rows = ref<M8AdjudicationRow[]>([])

const adjudication = useM8Adjudication(formData, rows)

// ─── 从集中登记带入调整（4104 一般风险准备，权益贷方；双列 endAje/endRje，固定明细行） ───
const bringInRows = computed(() =>
  adjudication.computedRows.value.map((r) => ({
    rowKey: r.key,
    name: r.itemName || '一般风险准备项目',
    aje: r.endAje ?? 0,
    rje: r.endRje ?? 0,
  })),
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
  subjectPrefix: '4104',
  direction: 'credit',
  subjectCode: '4104',
  wpCode: 'M8',
  subjectLabel: '一般风险准备(4104)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => {
    const idx = rows.value.findIndex((r) => r.key === rowKey)
    if (idx < 0) return
    adjudication.updateRow(idx, field === 'aje' ? 'endAje' : 'endRje', value)
  },
  totalAudited: () => adjudication.totalRow.value.endAudited,
})

// Version trail (autoSnapshot on save)
const versionTrail = useVersionTrail({
  projectId: computed(() => props.projectId),
  workpaperId: computed(() => props.wpId),
})

// ─── 上期审定数 + 差异行 ─────────────────────────────────────────────────────
const priorAudited = ref({ beginAudited: 0, endAudited: 0 })

// ─── 交叉验证（与M8-2明细表比较） ────────────────────────────────────────────
const crossValidation = computed(() => {
  // 默认一致（M8-2数据由crossSheet或loadData注入）
  const detailTotal = Number(formData.getField('2', 'total-endAudited')) || 0
  return adjudication.crossValidateWithDetail(detailTotal)
})

// ─── 表格行构建（data rows + 合计 + 上期审定 + 差异） ─────────────────────────
interface TableRow extends M8AdjudicationRow {
  _rowType?: 'data' | 'total' | 'prior' | 'diff'
}

const tableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []

  // 明细行（rows 7-12）
  adjudication.computedRows.value.forEach(r => {
    result.push({ ...r, _rowType: 'data' })
  })

  // Row 13: 合计行
  const t = adjudication.totalRow.value
  result.push({
    key: 'total',
    itemName: '合 计',
    beginUnadjusted: t.beginUnadjusted,
    beginAje: t.beginAje,
    beginRje: t.beginRje,
    beginAudited: t.beginAudited,
    endUnadjusted: t.endUnadjusted,
    endAje: t.endAje,
    endRje: t.endRje,
    endAudited: t.endAudited,
    changeAmount: t.changeAmount,
    changeRate: t.changeRate,
    reason: '',
    _rowType: 'total',
  })

  // Row 14: 上期审定数
  result.push({
    key: 'prior',
    itemName: '上期审定数',
    beginUnadjusted: 0,
    beginAje: 0,
    beginRje: 0,
    beginAudited: priorAudited.value.beginAudited,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: priorAudited.value.endAudited,
    changeAmount: 0,
    changeRate: 0,
    reason: '',
    _rowType: 'prior',
  })

  // Row 15: 差异 = 合计 − 上期审定
  const diffBegin = t.beginAudited - priorAudited.value.beginAudited
  const diffEnd = t.endAudited - priorAudited.value.endAudited
  result.push({
    key: 'diff',
    itemName: '差 异',
    beginUnadjusted: 0,
    beginAje: 0,
    beginRje: 0,
    beginAudited: diffBegin,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: diffEnd,
    changeAmount: 0,
    changeRate: 0,
    reason: '',
    _rowType: 'diff',
  })

  return result
})

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'total') return 'total-row'
  if (row._rowType === 'prior') return 'prior-row'
  if (row._rowType === 'diff') return 'diff-row'
  return ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdateRow(
  tableIndex: number,
  field: 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'endUnadjusted' | 'endAje' | 'endRje' | 'reason',
  value: string | number,
): void {
  // tableIndex → 原始 rows 索引（排除合计/上期/差异行）
  const dataRows = tableRows.value.filter(r => r._rowType === 'data')
  const tableRow = tableRows.value[tableIndex]
  if (!tableRow || tableRow._rowType !== 'data') return
  const rawIdx = dataRows.findIndex(r => r.key === tableRow.key)
  if (rawIdx >= 0) {
    adjudication.updateRow(rawIdx, field as any, value)
  }
}

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditConclusion = ref('')

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    await adjudication.saveAndWriteback()
    await versionTrail.createSnapshot('M8-1 审定表保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditConclusion(): void {
  formData.debouncedSave('M8-1-auditConclusion', { remark: auditConclusion.value || null })
}

async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const t = adjudication.totalRow.value
    const context: Record<string, string> = {
      科目: '4104 一般风险准备（权益类/贷方）',
      底稿: 'M8-1 一般风险准备审定表',
      期初审定合计: fmtAmount(t.beginAudited),
      期末审定合计: fmtAmount(t.endAudited),
      变动额: fmtAmount(t.changeAmount),
      变动率: t.changeRate !== 0 ? (t.changeRate * 100).toFixed(1) + '%' : '0%',
      'M8-2交叉验证': crossValidation.value.isMatch ? '一致' : `差异${fmtAmount(crossValidation.value.diff)}`,
    }
    const text = await generateAiText({ section: `m8-adjudication-${section}`, context, existingContent: auditConclusion.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    auditConclusion.value = text
    saveAuditConclusion()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview(): void {
  openReviewDialog?.('M8-1-adjudication', '一般风险准备审定表')
}

// ─── EventBus + Lifecycle ────────────────────────────────────────────────────
function handleAdjustmentCreated(): void { formData.loadData() }
let unsubAdjudicated: (() => void) | null = null
let unsubDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()

  // 恢复行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) {
      rows.value = restored
    } else {
      // 默认6行明细（对应xlsx rows 7-12）
      rows.value = _defaultRows()
    }
  }

  // 恢复上期审定数
  const priorBegin = formData.allResponses.value.get('M8-1-prior-beginAudited')
  const priorEnd = formData.allResponses.value.get('M8-1-prior-endAudited')
  if (priorBegin?.remark) priorAudited.value.beginAudited = Number(priorBegin.remark) || 0
  if (priorEnd?.remark) priorAudited.value.endAudited = Number(priorEnd.remark) || 0

  // 恢复审计结论
  const noteResp = formData.allResponses.value.get('M8-1-auditConclusion')
  if (noteResp?.remark) auditConclusion.value = noteResp.remark

  // EventBus subscriptions
  eventBus.on('adjustment:created', handleAdjustmentCreated)
  unsubAdjudicated = adjudication.subscribeAdjudicated(() => { formData.loadData() })
  unsubDisclosure = adjudication.subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created', handleAdjustmentCreated)
  if (unsubAdjudicated) { unsubAdjudicated(); unsubAdjudicated = null }
  if (unsubDisclosure) { unsubDisclosure(); unsubDisclosure = null }
})

// ─── 从 checklist_responses 恢复行数据 ───────────────────────────────────────
function _restoreRows(): M8AdjudicationRow[] {
  const restored: M8AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M8-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m8-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          beginUnadjusted: Number(d.beginUnadjusted) || 0,
          beginAje: Number(d.beginAje) || 0,
          beginRje: Number(d.beginRje) || 0,
          beginAudited: 0,
          endUnadjusted: Number(d.endUnadjusted) || 0,
          endAje: Number(d.endAje) || 0,
          endRje: Number(d.endRje) || 0,
          endAudited: 0,
          changeAmount: 0,
          changeRate: 0,
          reason: d.reason || '',
        })
      } catch { /* skip corrupt data */ }
    }
  }
  return restored
}

/** 默认6行明细（对应xlsx rows 7-12，从M8-2引用） */
function _defaultRows(): M8AdjudicationRow[] {
  const labels = [
    '一般风险准备—信贷资产',
    '一般风险准备—投资资产',
    '一般风险准备—表外资产',
    '一般风险准备—其他资产',
    '',
    '',
  ]
  return labels.map((name, i) => ({
    key: `m8-adj-default-${i + 1}`,
    itemName: name,
    beginUnadjusted: 0,
    beginAje: 0,
    beginRje: 0,
    beginAudited: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    changeAmount: 0,
    changeRate: 0,
    reason: '',
  }))
}
</script>

<style scoped>
.m8-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* ─── 区块 ─── */
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 公式列虚线下划线 + cursor:help ─── */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.diff-warning { color: #f56c6c; font-weight: 600; }
.high-change { color: #e6a23c; font-weight: 600; }

/* ─── 行样式 ─── */
.total-row-label { font-weight: 700; color: #303133; }
.diff-row-label { font-weight: 600; color: #f56c6c; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #ecf5ff !important; font-weight: 700; }
:deep(.total-row td) { border-top: 2px solid #409eff; }
:deep(.prior-row) { background: #f5f7fa !important; color: #909399; }
:deep(.diff-row) { background: #fef0f0 !important; font-weight: 600; }
:deep(.diff-row td) { border-top: 1px dashed #f56c6c; }

/* ─── Footer ─── */
.adjudication-footer {
  margin-top: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* ─── 审计结论卡片 ─── */
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 编制提示折叠 ─── */
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
