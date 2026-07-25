<template>
  <div class="i2-adjudication" data-testid="i2-adjudication">
    <div class="section-header">
      <span class="section-title">I2-1 开发支出审定表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标</template>
      核查开发支出(1717)期初/期末余额的真实性与完整性；审定数＝未审数＋账项调整；与 TB 勾稽一致后回写试算并驱动附注披露。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（对齐源表）：</b>
        期初/期末各列「未审数 → 账项调整 → 审定数」；变动额＝期末审定−期初审定；变动率分母为 0 时显示 N/A。
        合计与 TB 数据差异须为 0。项目明细优先自 I2-2 带入，期末调整可自 I2-3 分摊。
        保存后发布 substantive:adjudicated，供附注自动刷新。
      </p>
    </div>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:I2-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:I2-2" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:I2-3" :context-project-id="props.projectId" />
      <el-tag size="small" type="info">项目 {{ rows.length }}</el-tag>
      <el-tag size="small" type="success">期末审定 {{ fmtAmount(summary.endAudited) }}</el-tag>
      <el-tag v-if="hasTbDiff" size="small" type="danger">与TB差异 {{ fmtAmount(tbDiff) }}</el-tag>
      <el-tag v-else size="small" type="success">✓ TB一致</el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'I2-2')">I2-2 →</el-button>
      <el-button size="small" @click="emit('navigate-sheet', '附注上市')">附注 →</el-button>
    </div>

    <div class="tb-display">
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="TB未审(1717)">{{ fmtAmount(tbData.unadjusted1717) }}</el-descriptions-item>
        <el-descriptions-item label="TB审定(1717)">{{ fmtAmount(tbData.audited1717) }}</el-descriptions-item>
        <el-descriptions-item label="AJE">{{ fmtAmount(tbData.aje1717) }}</el-descriptions-item>
        <el-descriptions-item label="RJE">{{ fmtAmount(tbData.rje1717) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="action-bar">
      <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <el-button size="small" plain :disabled="isReadonly" :loading="isLoadingTb" data-testid="i2-1-load-tb" @click="handleLoadTb()">从 TB 带入</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" data-testid="i2-1-seed-i22" @click="handleSeedI22">从 I2-2 带入</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="handleSyncI23">从 I2-3 同步调整</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="handleApplyTb">TB写入汇总行</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增项目</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" data-testid="i2-1-save" @click="handleSave">保存并回写</el-button>
      <el-dropdown v-if="!isReadonly" size="small" :disabled="ieBusy" @command="handleIeCommand">
        <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <el-alert
      v-if="hasAjeApprox"
      type="warning"
      :closable="false"
      show-icon
      class="aje-approx-alert"
      title="系统近似分摊：部分期末调整按期末未审占比分摊自 I2-3，请按项目人工复核后改数（改后自动清除「近似」标记）"
    />

    <el-table :data="displayRows" border size="small" class="adjudication-table" :row-class-name="rowClassName" max-height="520">
      <el-table-column prop="projectName" label="项目" min-width="130" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!row._footer && !isReadonly"
            :model-value="row.projectName"
            size="small"
            @change="(v: string) => updateRow(row.rowId, 'projectName', v)"
          />
          <span v-else :class="{ 'footer-text': row._footer }">{{ row.projectName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row._footer && !isReadonly"
              :model-value="row.beginUnadj"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="(v: number) => updateRow(row.rowId, 'beginUnadj', v ?? 0)"
            />
            <span v-else :class="{ 'footer-text': row._footer }">{{ fmtAmount(row.beginUnadj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row._footer && !isReadonly"
              :model-value="row.beginAdj"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="(v: number) => updateRow(row.rowId, 'beginAdj', v ?? 0)"
            />
            <span v-else :class="{ 'footer-text': row._footer }">{{ fmtAmount(row.beginAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row._footer && !isReadonly"
              :model-value="row.endUnadj"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="(v: number) => updateRow(row.rowId, 'endUnadj', v ?? 0)"
            />
            <span v-else :class="{ 'footer-text': row._footer, 'warn-diff': row.projectName === '差异' && hasTbDiff }">
              {{ row.projectName === '差异' ? fmtAmount(summary.endUnadj - (tbData.unadjusted1717 || 0)) : fmtAmount(row.endUnadj) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="130" align="right">
          <template #default="{ row }">
            <div v-if="!row._footer && !isReadonly" class="adj-cell">
              <el-input-number
                :model-value="row.endAdj"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                @change="(v: number) => updateRow(row.rowId, 'endAdj', v ?? 0)"
              />
              <el-tag v-if="row.ajeApprox" size="small" type="warning" effect="plain">近似</el-tag>
            </div>
            <template v-else>
              <span :class="{ 'footer-text': row._footer }">{{ fmtAmount(row.endAdj) }}</span>
              <el-tag v-if="row.ajeApprox" size="small" type="warning" effect="plain">近似</el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{ 'warn-diff': row.projectName === '差异' && hasTbDiff }"
            >
              {{ row.projectName === '差异' ? fmtAmount(tbDiff) : fmtAmount(row.endAudited) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期审定与上期比较" align="center">
        <el-table-column label="变动额" width="110" align="right">
          <template #header>
            <el-tooltip content="变动额 = 期末审定 − 期初审定" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #header>
            <el-tooltip content="变动率 = 变动额 ÷ 期初审定（期初为0时 N/A）" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ formatChangeRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!row._footer && !isReadonly"
            :model-value="row.reasonAnalysis"
            size="small"
            placeholder="重大变动原因…"
            @change="(v: string) => updateRow(row.rowId, 'reasonAnalysis', v)"
          />
          <span v-else>{{ row.reasonAnalysis || '' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="52" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="!row._footer" size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>1、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录重大事项、特别风险、调整分录索引（CAS 1131）…"
        @change="(v: string) => saveAuditField('note', v)"
      />
      <details class="tips">
        <summary>提示（编制审计说明时可参考）</summary>
        <ul>
          <li>记录识别的特别风险、重大异常交易、关联方及会计估计相关事项；</li>
          <li>逐项列示审计调整并交叉索引至 I2-3 / 支持性底稿；</li>
          <li>说明与 TB、明细表、附注披露的勾稽结果。</li>
          <li>「带入调整」：从集中登记按科目 1717 拉取调整分录，逐笔分配到各项目的账项调整列，带入后审定数自动更新并联动附注。</li>
        </ul>
      </details>
    </el-card>

    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>2、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="开发支出在重大方面是否公允反映…"
        @change="(v: string) => saveAuditField('conclusion', v)"
      />
    </el-card>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1717 开发支出"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Adjudication, formatChangeRate } from '../../composables/useI2Adjudication'
import { fetchI2TbData, persistI2TbData, type I2TbData } from '../../composables/useI2FormData'
import { useI2ImportExport } from '../../composables/useI2ImportExport'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { Download } from '@element-plus/icons-vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import http from '@/utils/http'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string]; imported: [] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const tbData = computed<I2TbData>(() => {
  const raw = props.allResponses.get('I2-tb-data')
  if (raw && typeof raw === 'object') {
    const o = typeof (raw as any).remark === 'string'
      ? (() => { try { return JSON.parse((raw as any).remark) } catch { return raw } })()
      : raw
    return {
      unadjusted1717: Number((o as any).unadjusted1717) || 0,
      audited1717: Number((o as any).audited1717) || 0,
      aje1717: Number((o as any).aje1717) || 0,
      rje1717: Number((o as any).rje1717) || 0,
    }
  }
  return { unadjusted1717: 0, audited1717: 0, aje1717: 0, rje1717: 0 }
})

const allResponsesRef = computed(() => props.allResponses)
const tbDataRef = computed(() => tbData.value)

// ─── TB 带入（I2-tb-data）：科目1717未审/审定/AJE/RJE，供上方 el-descriptions 展示与差异校验 ──
const isLoadingTb = ref(false)
async function handleLoadTb(silent = false): Promise<void> {
  if (!props.projectId) return
  isLoadingTb.value = true
  try {
    const tb: I2TbData = await fetchI2TbData(http, props.projectId)
    await persistI2TbData(props.saveResponse, tb)
    if (!silent) ElMessage.success('已从 TB 带入科目1717数据')
  } finally {
    isLoadingTb.value = false
  }
}

async function writebackTb(auditedAmount: number) {
  if (!props.wpId || !props.projectId) return
  try {
    await http.post(`/workpapers/${props.wpId}/writeback-trial-balance`, {
      project_id: props.projectId,
      account_code: '1717',
      audited_amount: auditedAmount,
    })
  } catch {
    // 部分环境无此接口：静默，仍保留本地审定事件
  }
}

const {
  rows, auditNote, auditConclusion, summary,
  totalRow, tbRow, diffRow, tbDiff, hasTbDiff, hasAjeApprox,
  addRow, removeRow, updateRow,
  seedFromDetail, syncAjeFromI23, applyTbToUnadj,
  save, saveAuditField,
} = useI2Adjudication({
  allResponses: allResponsesRef,
  tbData: tbDataRef,
  saveResponses: props.saveResponse,
  onAfterSave: async (s) => { await writebackTb(s.endAudited) },
})

const displayRows = computed(() => [
  ...rows.value.map((r) => ({ ...r, _footer: false })),
  { ...totalRow.value, _footer: true },
  { ...tbRow.value, _footer: true },
  { ...diffRow.value, _footer: true },
])

// ─── 从集中登记带入调整（1717 开发支出，资产借方；单一「账项调整」列 endAdj，读实时值增量累加） ───
const bringInRows = computed(() =>
  rows.value.map((r) => ({ rowKey: r.rowId, name: r.projectName, aje: 0, rje: 0 })),
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
  subjectPrefix: '1717',
  direction: 'debit',
  subjectCode: '1717',
  wpCode: 'I2',
  subjectLabel: '开发支出(1717)',
  rows: bringInRows,
  // 单一「账项调整」列：aje/rje 净额均累加至 endAdj（读取实时值做增量累加）
  updateCell: (rowKey: string, _field: any, value: number) => {
    const row = rows.value.find((r) => r.rowId === rowKey)
    const live = Number(row?.endAdj) || 0
    updateRow(rowKey, 'endAdj', Math.round((live + value) * 100) / 100)
  },
  totalAudited: () => summary.value.endAudited,
})

function rowClassName({ row }: { row: any }) {
  if (row.projectName === '合计') return 'total-row'
  if (row.projectName === 'TB数据') return 'tb-row'
  if (row.projectName === '差异') return hasTbDiff.value ? 'diff-row-error' : 'diff-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：课题1 / 数据资源',
    })
    if (value?.trim()) {
      addRow(value.trim())
      ElMessage.success('已添加项目')
    }
  } catch { /* cancelled */ }
}

function handleSeedI22() {
  const r = seedFromDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

function handleSyncI23() {
  const r = syncAjeFromI23()
  if (r.ok) {
    if (r.approx) ElMessage.warning(r.message)
    else ElMessage.success(r.message)
  } else {
    ElMessage.info(r.message)
  }
}

function handleApplyTb() {
  const r = applyTbToUnadj()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

async function handleSave() {
  await save()
  emit('save')
  ElMessage.success('审定表已保存，已尝试回写 TB 并通知附注')
}

function handleReview() { openReviewDialog('I2-1-审定表') }

// ─── 导入导出（I2-1 审定表） ────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const { isImporting, isExporting, exportTemplate, exportData, importData } = useI2ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => emit('imported'),
})
const ieBusy = computed(() => isImporting.value || isExporting.value)

async function handleIeCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('I2-1')
  else if (cmd === 'export-data') await exportData('I2-1')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (file) await importData(file, 'I2-1')
}

onMounted(() => {
  if (!(props.allResponses.get('I2-tb-data'))) void handleLoadTb(true)
})

function fmtAmount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (Math.abs(value) < 0.005) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-adjudication { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.objective-alert { margin-bottom: 10px; }
.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7;
}
.tab-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
.tb-display { margin-bottom: 10px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.aje-approx-alert { margin-bottom: 10px; }
.adj-cell { display: flex; flex-direction: column; gap: 2px; align-items: stretch; }
.adjudication-table { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; border-bottom: 1px dashed #c0c4cc; }
.footer-text { font-weight: 600; }
.warn-diff { color: #dc2626; font-weight: 700; }
.audit-note-card, .audit-conclusion-card { margin-top: 14px; }
.tips { margin-top: 8px; font-size: 12px; color: #1d4ed8; }
.tips ul { margin: 4px 0 0; padding-left: 18px; }
:deep(.total-row) { background: #f5f7fa !important; }
:deep(.tb-row) { background: #eff6ff !important; }
:deep(.diff-row) { background: #f0fdf4 !important; }
:deep(.diff-row-error) { background: #fef2f2 !important; }
</style>
