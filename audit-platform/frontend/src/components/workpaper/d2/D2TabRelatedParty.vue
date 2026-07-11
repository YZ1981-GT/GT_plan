<script setup lang="ts">
/**
 * D2TabRelatedParty — 关联方及交易检查 D2-6
 *
 * 打磨基准：D1 检查型底稿（审计目标 / 全字段可编辑 / 行级复核+索引 /
 *           合计行 / 审计说明+结论+AI / 编制提示）
 */
import { inject, toRef, ref, computed, type Ref } from 'vue'
import { useD2RelatedParty } from '../composables/useD2RelatedParty'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-6',
)

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onReview(sectionId: string): void {
  if (openReviewDialog) openReviewDialog(sectionId)
}

const {
  rows,
  totalRow,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  importFromDetail,
  saveAuditNote,
  saveAuditConclusion,
} = useD2RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const ARMS_LENGTH_OPTIONS = ['是', '否', '待核实']

// ─── AI ─────────────────────────────────────────────────────────────────
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, generateAndConfirm } = useD2AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildAiContext(extra = ''): Record<string, unknown> {
  return {
    sheet: 'D2-6',
    rowCount: rows.value.length,
    endTotal: totalRow.value.endBalance,
    bookValueTotal: totalRow.value.bookValue,
    guidance: extra,
  }
}

async function generateNoteAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm('related-party-note', auditNote.value,
      buildAiContext('关注关联方识别完整性、交易定价公允性、期末余额合理性。'), 'AI · 审计说明')
    if (text) saveAuditNote(text)
  } finally { aiLoadingNote.value = false }
}

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm('related-party-note', auditConclusion.value,
      buildAiContext('生成关联方应收账款检查审计结论。'), 'AI · 审计结论')
    if (text) saveAuditConclusion(text)
  } finally { aiLoadingConclusion.value = false }
}

async function handleImport(file: File): Promise<boolean> {
  await onImportFile(file)
  return false
}

// ─── 虚拟速览 ──────────────────────────────────────────────────────────────
const browseRows = computed(() =>
  rows.value.map(r => ({
    debtorName: r.debtorName,
    relationType: r.relationType,
    endBalance: r.endBalance,
    bookValue: r.bookValue,
  })),
)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('debtorName', '关联方名称', 140),
  virtualTextCol('relationType', '关联关系', 120),
  virtualNumCol('endBalance', '期末余额', 110, (v) => displayPrefs.fmtAmount(Number(v) || 0)),
  virtualNumCol('bookValue', '账面价值', 110, (v) => displayPrefs.fmtAmount(Number(v) || 0)),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 900,
})

const GUIDANCE_TEXTS = [
  '关联方识别：应结合股权结构、董监高任职、资金往来、异常交易等线索，评价关联方清单的完整性（CAS 1323）。',
  '关联交易公允性：关注定价是否公允、是否存在通过关联方调节利润或转移资金的迹象。',
  '期末余额核对：关联方应收账款期末余额应与函证/往来对账单核对，账龄异常长的应评估回收风险。',
  '披露完整性：重大关联方交易及余额应在附注充分披露（关系、类型、金额、占比、结算方式）。',
]
</script>

<template>
  <div class="d2-tab-related-party">
    <!-- ─── 标题行 ─── -->
    <div class="tab-header">
      <h4>关联方及交易检查 D2-6</h4>
      <GtIndexChip value="wp:D2-6" />
      <GtReviewTrigger section-id="D2-relatedparty-header" />
    </div>

    <!-- ─── 审计目标 ─── -->
    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>识别并核实应收账款关联方及交易，评价关联方清单完整性、交易定价公允性及披露充分性（CAS 1323）。</p>
      </template>
    </el-alert>

    <!-- ─── 工具栏 ─── -->
    <div class="tab-toolbar">
      <el-dropdown trigger="click" size="small">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="onExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="onExportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="handleImport" style="width:100%">
                <span style="display:block;width:100%">导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromDetail">从 D2-2 明细导入关联方</el-button>
      <el-tag size="small" type="info" effect="plain" class="row-count-tag">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- ─── 虚拟速览 ─── -->
    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRows.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>
    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
    />

    <!-- ─── 主表格 ─── -->
    <el-table
      v-if="!useVirtualScroll || !browseMode"
      :data="rows"
      border
      size="small"
      max-height="500"
      style="width: 100%"
      class="rp-table"
    >
      <el-table-column label="关联方名称" min-width="140" fixed="left">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" placeholder="关联方名称" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
          <span v-else>{{ row.debtorName || '-' }}</span>
          <GtReviewDot row-prefix="D2-relatedparty" :row-key="row.rowId" />
        </template>
      </el-table-column>
      <el-table-column label="关联关系" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relationType" size="small" placeholder="如控股股东" @change="(v: string) => updateCell(row.rowId, 'relationType', v)" />
          <span v-else>{{ row.relationType || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="交易类型" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.transactionType" size="small" placeholder="如销售商品" @change="(v: string) => updateCell(row.rowId, 'transactionType', v)" />
          <span v-else>{{ row.transactionType || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.priorBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorBalance', v || 0)" />
          <span v-else>{{ displayPrefs.fmtAmount(row.priorBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期借方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v || 0)" />
          <span v-else>{{ displayPrefs.fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v || 0)" />
          <span v-else>{{ displayPrefs.fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="= 期初 + 借方 - 贷方（自动计算）" placement="top">
            <span class="formula-cell">{{ displayPrefs.fmtAmount(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="坏账准备" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.badDebtProvision" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'badDebtProvision', v || 0)" />
          <span v-else>{{ displayPrefs.fmtAmount(row.badDebtProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面价值" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="= 期末余额 - 坏账准备（自动计算）" placement="top">
            <span class="formula-cell">{{ displayPrefs.fmtAmount(row.bookValue) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="公允交易" width="110" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isArmsLength" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'isArmsLength', v || '')">
            <el-option v-for="o in ARMS_LENGTH_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.isArmsLength || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>暂无关联方记录，点击"+ 添加关联方"或"从 D2-2 明细导入"</template>
    </el-table>

    <!-- ─── 合计行 ─── -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <el-tag size="small" effect="plain">期初 {{ displayPrefs.fmtAmount(totalRow.priorBalance) }}</el-tag>
      <el-tag size="small" effect="plain" type="warning">期末 {{ displayPrefs.fmtAmount(totalRow.endBalance) }}</el-tag>
      <el-tag size="small" effect="plain" type="danger">坏账 {{ displayPrefs.fmtAmount(totalRow.badDebtProvision) }}</el-tag>
      <el-tag size="small" effect="plain" type="success">账面价值 {{ displayPrefs.fmtAmount(totalRow.bookValue) }}</el-tag>
    </div>

    <!-- ─── 审计意见区 ─── -->
    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计说明' : 'AI 服务暂不可用'" placement="top">
              <el-button type="primary" plain size="small" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNoteAI">🤖 AI</el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-relatedparty-note')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" placeholder="请输入审计说明..." :disabled="isReadonly" @change="(v: string) => saveAuditNote(v || '')" />
    </el-card>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计结论' : 'AI 服务暂不可用'" placement="top">
              <el-button type="primary" plain size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusionAI">🤖 AI</el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-relatedparty-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditConclusion" placeholder="请输入审计结论..." :disabled="isReadonly" @change="(v: string) => saveAuditConclusion(v || '')" />
    </el-card>

    <!-- ─── 编制提示 ─── -->
    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-related-party { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; align-items: center; margin-bottom: 12px; gap: 12px; flex-wrap: wrap; }
.row-count-tag { margin-left: auto; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }

/* ─── 表格 13px + 紧凑 ─── */
.rp-table { font-size: 13px; }
.rp-table :deep(.el-table__cell) { padding: 4px 3px; }

/* ─── 公式列：灰底 + 虚线下划线 + help 光标 ─── */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
  font-variant-numeric: tabular-nums;
}

/* ─── 合计栏 ─── */
.total-bar {
  display: flex; gap: 12px; align-items: center; padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; margin-right: 4px; }

/* ─── 审计意见卡片 ─── */
.audit-opinion-card { margin-top: 16px; margin-bottom: 0; }
.audit-opinion-card + .audit-opinion-card { margin-top: 12px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }

/* ─── 编制提示 ─── */
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
</style>
