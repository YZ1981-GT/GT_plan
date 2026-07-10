<template>
<div class="d3-detail">
  <!-- 搜索 + 工具栏 -->
  <div class="detail-toolbar">
    <el-input
      v-model="searchQuery"
      size="small"
      placeholder="搜索客户名称..."
      clearable
      style="width: 240px"
    />
    <div class="toolbar-actions">
      <el-button-group size="small">
        <el-button @click="exportTemplate('F1-2')">导出模板</el-button>
        <el-button @click="exportData('F1-2')">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :disabled="isReadonly || importing"
          :before-upload="(file: any) => handleImport(file, 'F1-2')"
        >
          <el-button>导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加客户</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
    </div>
  </div>

  <!-- 27列宽表 -->
  <el-table
    :data="displayRows"
    size="small"
    border
    stripe
    :height="tableHeight"
    style="width: 100%"
    :row-class-name="rowClassName"
  >
    <!-- A: 对方单位名称 -->
    <el-table-column prop="customerName" label="对方单位名称" width="140" fixed>
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__' || row.rowId === '__verification__'">
          <span class="subtotal-label">{{ row.customerName }}</span>
        </template>
        <el-input v-else v-model="row.customerName" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'customerName', val)" />
      </template>
    </el-table-column>
    <!-- B: 公司代码 -->
    <el-table-column prop="companyCode" label="公司代码" width="90" fixed>
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__' && row.rowId !== '__verification__'"
          v-model="row.companyCode" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'companyCode', val)" />
      </template>
    </el-table-column>
    <!-- C: 款项性质 -->
    <el-table-column label="款项性质" width="160">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.nature" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'nature', val)">
          <el-option value="预收销售固定资产款" />
          <el-option value="预收销售土地使用权款" />
          <el-option value="合同不成立时已收取的对价" />
          <el-option value="其他" />
        </el-select>
      </template>
    </el-table-column>
    <!-- D: 关联方类型 -->
    <el-table-column label="关联方类型" width="120">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.relationType" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'relationType', val)">
          <el-option value="非关联方" />
          <el-option value="母公司" />
          <el-option value="子公司" />
          <el-option value="联营企业" />
          <el-option value="合营企业" />
          <el-option value="其他关联方" />
        </el-select>
      </template>
    </el-table-column>
    <!-- E: 期初未审 -->
    <el-table-column label="期初未审(E)" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorUnadjusted" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorUnadjusted', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorUnadjusted) }}</span>
      </template>
    </el-table-column>
    <!-- F: 期初账项调整 -->
    <el-table-column label="期初调整(F)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorAdjustment" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorAdjustment', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorAdjustment) }}</span>
      </template>
    </el-table-column>
    <!-- G: 期初重分类 -->
    <el-table-column label="期初重分(G)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorReclass', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorReclass) }}</span>
      </template>
    </el-table-column>
    <!-- H: 期初审定(自动) -->
    <el-table-column label="期初审定(H)" width="110" align="right">
      <template #default="{ row }"><span class="auto-calc amt">{{ fmtAmount(row.priorAudited) }}</span></template>
    </el-table-column>
    <!-- 期初账龄（动态） -->
    <el-table-column v-for="band in bands" :key="'prior-' + band.key" :label="`${band.label}(期初)`" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.agingPrior[band.key]" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, `agingPrior.${band.key}`, val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.agingPrior?.[band.key]) }}</span>
      </template>
    </el-table-column>
    <!-- M: 借方发生 -->
    <el-table-column label="借方(M)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.debit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'debit', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.debit) }}</span>
      </template>
    </el-table-column>
    <!-- N: 贷方发生 -->
    <el-table-column label="贷方(N)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.credit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'credit', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.credit) }}</span>
      </template>
    </el-table-column>
    <!-- O: 期末余额(自动) -->
    <el-table-column label="期末余额(O)" width="110" align="right">
      <template #default="{ row }"><span class="auto-calc amt">{{ fmtAmount(row.endBalance) }}</span></template>
    </el-table-column>
    <!-- P: 重分类调整 -->
    <el-table-column label="重分类(P)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.entityReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'entityReclass', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.entityReclass) }}</span>
      </template>
    </el-table-column>
    <!-- Q: 期末未审(自动) -->
    <el-table-column label="期末未审(Q)" width="110" align="right">
      <template #default="{ row }"><span class="auto-calc amt">{{ fmtAmount(row.endUnadjusted) }}</span></template>
    </el-table-column>
    <!-- R: 期末AJE -->
    <el-table-column label="期末AJE(R)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endAje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endAje', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.endAje) }}</span>
      </template>
    </el-table-column>
    <!-- S: 期末RJE -->
    <el-table-column label="期末RJE(S)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endRje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endRje', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.endRje) }}</span>
      </template>
    </el-table-column>
    <!-- T: 期末审定(自动) -->
    <el-table-column label="期末审定(T)" width="110" align="right">
      <template #default="{ row }"><span class="auto-calc amt">{{ fmtAmount(row.endAudited) }}</span></template>
    </el-table-column>
    <!-- 审定账龄（动态） -->
    <el-table-column v-for="band in bands" :key="'audited-' + band.key" :label="`${band.label}(期末审定)`" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.agingAudited[band.key]" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, `agingAudited.${band.key}`, val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.agingAudited?.[band.key]) }}</span>
      </template>
    </el-table-column>
    <!-- Y: 是否发函 -->
    <el-table-column label="发函(Y)" width="70" align="center">
      <template #default="{ row }">{{ row.isConfirmed || '-' }}</template>
    </el-table-column>
    <!-- Z: 期后结转 -->
    <el-table-column label="期后结转(Z)" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.postPeriodSettlement" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'postPeriodSettlement', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.postPeriodSettlement) }}</span>
      </template>
    </el-table-column>
    <!-- AA: 备注 -->
    <el-table-column label="备注" min-width="120">
      <template #default="{ row }">
        <el-input v-if="isDataRow(row)" v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <!-- 操作列 -->
    <el-table-column label="操作" width="60" fixed="right" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm v-if="isDataRow(row)" title="确认删除此行？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <!-- F1-7期后结转联动提示 -->
  <el-alert
    v-if="postPeriodLinkageWarning"
    :title="postPeriodLinkageWarning"
    type="warning"
    :closable="false"
    show-icon
    style="margin: 12px 0"
  />

  <!-- 审计说明 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <div class="note-block">
      <div class="note-label">(1) 变动分析</div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="说明预付账款明细变动情况..."
        :model-value="auditNote1" @update:model-value="auditNote1 = $event" />
    </div>
    <div class="note-block">
      <div class="note-label">(2) 合同履约分析 <el-button size="small" :disabled="true">🤖AI</el-button></div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="分析合同履约情况..."
        :model-value="auditNote2" @update:model-value="auditNote2 = $event" />
    </div>
    <div class="note-block">
      <div class="note-label">(3) 超期未结转说明</div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="超期未结转的原因和处理计划..."
        :model-value="auditNote3" @update:model-value="auditNote3 = $event" />
    </div>
    <div class="conclusion-actions">
      <el-button size="small" @click="openReview">💬 复核</el-button>
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabDetail.vue — F1-2 明细表
 * 27列宽表 + 款项性质/关联方下拉 + 公式链自动计算 + 搜索 + 导入
 */
import { computed, inject, ref, type Ref } from 'vue'
import { useF1Detail } from '../composables/useF1Detail'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const relatedParties = ref<string[]>([])
const auditNote1 = ref('')
const auditNote2 = ref('')
const auditNote3 = ref('')

const {
  rows,
  filteredRows,
  subtotalRow,
  verificationRow,
  searchQuery,
  bands,
  addRow,
  removeRow,
  updateCell,
  importFromAuxBalance,
} = useF1Detail({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  relatedParties,
})

// ─── F1-7 期后结转联动 ──────────────────────────────────────────────────────
import { useF1CrossSheet } from '../composables/useF1CrossSheet'

const crossSheet = useF1CrossSheet({ allResponses: props.allResponses })

/** 当 F1-7 有期后结转金额但 F1-2 Z列为空时，显示黄色提示 */
const postPeriodLinkageWarning = computed(() => {
  const sync = crossSheet.postPeriodSettlementSync.value
  if (sync.total === 0) return ''
  // 检查是否有 F1-7 有金额但 F1-2 Z列为空的行
  const mismatched: string[] = []
  for (const [customer, d7Amount] of Object.entries(sync.byCustomer)) {
    if (d7Amount <= 0) continue
    const detailRow = rows.value.find(r => r.customerName === customer)
    if (detailRow && (!detailRow.postPeriodSettlement || detailRow.postPeriodSettlement === 0)) {
      mismatched.push(customer)
    }
  }
  if (mismatched.length === 0) return ''
  return `F1-7期后结转检查中发现 ${mismatched.length} 个客户有贷方金额（合计 ${sync.total.toLocaleString()} 元），但F1-2期后结转列（Z列）为空：${mismatched.slice(0, 3).join('、')}${mismatched.length > 3 ? '等' : ''}`
})

// 虚拟滚动: 超30行启用固定高度
const tableHeight = computed(() => filteredRows.value.length > 30 ? '600px' : undefined)

// 显示行 = filteredRows + 合计行 + 核对行
const displayRows = computed(() => [...filteredRows.value, subtotalRow.value, verificationRow.value])

function isDataRow(row: any): boolean {
  return row.rowId !== '__subtotal__' && row.rowId !== '__verification__'
}

function rowClassName({ row }: { row: any }): string {
  if (row.rowId === '__subtotal__') return 'subtotal-row'
  if (row.rowId === '__verification__') return 'verification-row'
  if (row.relationType && row.relationType !== '非关联方') return 'related-party-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function openReview() {
  openReviewDialog('F1-det-notes')
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: props.wpId })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-detail { padding: 16px; }
.detail-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-actions { display: flex; gap: 8px; }
.subtotal-label { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto-calc { background: #f5f7fa; padding: 2px 4px; border-radius: 2px; }
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; margin-bottom: 12px; }
.note-block { margin-bottom: 12px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; color: #606266; }
.conclusion-actions { margin-top: 8px; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.verification-row) { background-color: #fff8e1 !important; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }
</style>
