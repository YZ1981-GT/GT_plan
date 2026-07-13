<template>
<div class="d3-detail">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表按对方单位逐户列示预付账款（科目1123）明细，填列期初/发生额/期末及账龄分布。</p>
      <p>2. 灰色底纹列为自动计算列（期初审定H/期末余额O/期末未审Q/期末审定T），不可手工编辑。</p>
      <p>3. 账龄超过1年的长期挂账应转入 F1-5 检查，关联方预付款需在 F1-6 单独列示并关注商业实质。</p>
      <p>4. 关注预付款能否形成资产及可收回性，存在无法收回迹象的应评估减值并考虑重分类。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实预付账款期末余额的存在与准确，确认账龄划分与款项性质恰当，识别长期挂账、关联方预付及减值迹象。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-input v-model="searchQuery" size="small" placeholder="搜索客户名称..." clearable style="width: 220px" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加客户</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-2')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-2')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-2')"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
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
    <el-table-column label="期初审定(H)" width="110" align="right" class-name="auto-calc-col">
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
    <el-table-column label="期末余额(O)" width="110" align="right" class-name="auto-calc-col">
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
    <el-table-column label="期末未审(Q)" width="110" align="right" class-name="auto-calc-col">
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
    <el-table-column label="期末审定(T)" width="110" align="right" class-name="auto-calc-col">
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

  <!-- 审计说明区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-5" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-6" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(1) 变动分析</span>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="说明预付账款明细变动情况..."
        :model-value="auditNote1" @update:model-value="auditNote1 = $event" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(2) 合同履约分析</span>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="分析合同履约情况..."
        :model-value="auditNote2" @update:model-value="auditNote2 = $event" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(3) 超期未结转说明</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="超期未结转的原因和处理计划..."
        :model-value="auditNote3" @update:model-value="auditNote3 = $event" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计结论</span>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        :model-value="auditConclusion" @change="saveAuditConclusion" />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabDetail.vue — F1-2 明细表
 * 27列宽表 + 款项性质/关联方下拉 + 公式链自动计算 + 搜索 + 导入
 */
import { computed, inject, onMounted, ref, toRef, type Ref } from 'vue'
import { useF1Detail } from '../composables/useF1Detail'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const relatedParties = ref<string[]>([])
const auditNote1 = ref('')
const auditNote2 = ref('')
const auditNote3 = ref('')

// ─── 审计结论 ──────────────────────────────────────────────────────────────
const CONCLUSION_KEY = 'F1-detail-audit-conclusion'
const auditConclusion = ref('')

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  allResponsesRef.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void props.saveImmediate(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const c = allResponsesRef.value.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

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
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  relatedParties,
})

// ─── F1-7 期后结转联动 ──────────────────────────────────────────────────────
import { useF1CrossSheet } from '../composables/useF1CrossSheet'

const crossSheet = useF1CrossSheet({ allResponses: allResponsesRef })

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
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: toRef(props, 'wpId') as Ref<string> })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-detail { padding: 16px; }
.d3-detail :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.d3-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.subtotal-label { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto-calc { color: #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.verification-row) { background-color: #fff8e1 !important; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
