<template>
  <div class="m5-tab-detail">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M5-2 盈余公积明细表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('detail')">
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
        <strong>盈余公积明细（4101）为权益类贷方科目：</strong>
        期末余额 = 期初 + 本期计提（贷方增加） − 本期转增资本（借方减少） − 本期弥补亏损（借方减少）。
        法定盈余公积按净利润（弥补以前年度亏损后）10%计提，累计达注册资本50%可不再计提。
        任意盈余公积由股东大会决议自主计提。
        明细表分两区段展示，合计应与M5-1审定表一致。
        支持动态新增明细行 + 导入导出。
      </div>
    </div>

    <!-- ═══ 区段一：法定盈余公积明细 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">法定盈余公积明细</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow('statutory')">
          + 新增明细
        </el-button>
      </div>

      <el-table :data="statutoryTableRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="sourceName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)"><span class="total-row-label">{{ row.sourceName }}</span></template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input :model-value="row.sourceName" size="small" placeholder="来源项目" @change="(val: string) => updateStatutoryRow($index, 'sourceName', val)" />
            </template>
            <template v-else>{{ row.sourceName || '—' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.accrual" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'accrual', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.accrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转增资本" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.capitalConversion" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'capitalConversion', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.capitalConversion) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期弥补亏损" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.lossOffset" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'lossOffset', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.lossOffset) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="130" align="right">
          <template #header>
            <el-tooltip content="权益类贷方: 期初 + 本期计提 − 本期转增 − 本期弥补" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveStatutoryRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">法定盈余公积小计期末: {{ fmtAmount(statutorySubtotal.endBalance) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 区段二：任意盈余公积明细 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">任意盈余公积明细</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow('discretionary')">
          + 新增明细
        </el-button>
      </div>

      <el-table :data="discretionaryTableRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="sourceName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)"><span class="total-row-label">{{ row.sourceName }}</span></template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input :model-value="row.sourceName" size="small" placeholder="来源项目" @change="(val: string) => updateDiscretionaryRow($index, 'sourceName', val)" />
            </template>
            <template v-else>{{ row.sourceName || '—' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.accrual" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'accrual', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.accrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转增资本" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.capitalConversion" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'capitalConversion', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.capitalConversion) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期弥补亏损" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.lossOffset" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'lossOffset', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.lossOffset) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="130" align="right">
          <template #header>
            <el-tooltip content="权益类贷方: 期初 + 本期计提 − 本期转增 − 本期弥补" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveDiscretionaryRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">任意盈余公积小计期末: {{ fmtAmount(discretionarySubtotal.endBalance) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 合计 + 交叉验证状态 ═══ -->
    <div class="detail-footer">
      <el-tag type="primary" size="small" effect="dark">合计期末: {{ fmtAmount(grandTotal.endBalance) }}</el-tag>
      <el-tag :type="crossValidation.isMatch ? 'success' : 'danger'" size="small" effect="plain">
        与M5-1交叉验证:
        {{ crossValidation.isMatch ? '一致 ✓' : `差异 ${fmtAmount(crossValidation.statutoryDiff + crossValidation.discretionaryDiff)}` }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        法定小计: {{ fmtAmount(statutorySubtotal.endBalance) }} | 任意小计: {{ fmtAmount(discretionarySubtotal.endBalance) }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">明细表审计说明</span>
          <el-button size="small" @click="handleAI('detailNote')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写盈余公积明细表审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>盈余公积（4101）为<strong>权益类贷方科目</strong>：期末 = 期初 + 本期计提 − 本期转增资本 − 本期弥补亏损</li>
        <li>法定盈余公积：按净利润（弥补以前年度亏损后）<strong>10%</strong>计提，累计达注册资本<strong>50%</strong>可不再计提</li>
        <li>任意盈余公积：股东大会决议自主计提（无比例限制）</li>
        <li>明细表分两区段：法定盈余公积明细 + 任意盈余公积明细</li>
        <li>明细表合计应与 M5-1 审定表对应区块小计一致（交叉验证）</li>
        <li>支持动态行新增：点击"+ 新增明细"后输入来源项目名称</li>
        <li>支持导入导出：通过"导入导出"下拉菜单操作（导出模板/导出数据/导入数据）</li>
        <li>12公式实时计算：每行期末自动 = 期初 + 计提 − 转增 − 弥补</li>
      </ul>
    </details>

    <!-- ═══ 隐藏文件上传input ═══ -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabDetail — M5-2 盈余公积明细表（法定+任意两区段）
 * Requirements: 3.1-3.5
 * 两区段: 法定盈余公积明细 + 任意盈余公积明细
 * 列: 项目 | 期初 | 本期计提 | 本期转增资本 | 本期弥补亏损 | 期末
 * 公式: 期末=期初+本期计提-本期转增-本期弥补（权益类贷方）
 * 12公式实时计算 + 动态行新增 + 导入导出
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { useM5FormData } from '../../composables/useM5FormData'
import { useM5DualMode } from '../../composables/useM5DualMode'
import { useM5ImportExport } from '../../composables/useM5ImportExport'
import {
  useM5Detail,
  type M5DetailRow,
  type M5DetailSegment,
} from '../../composables/useM5Detail'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM5FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM5DualMode({ wpId: computed(() => props.wpId) })
const importExport = useM5ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

const detailRows = ref<M5DetailRow[]>([])

const {
  computedRows,
  statutorySubtotal,
  discretionarySubtotal,
  grandTotal,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  crossValidateWithAdjudication,
} = useM5Detail(formData, detailRows)

// ─── 表格数据：按区段拆分 + 小计行 ──────────────────────────────────────────
interface TableRow extends M5DetailRow { _rowType?: 'data' | 'subtotal' }

const statutoryTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = computedRows.value
    .filter(r => r.segment === 'statutory')
    .map(r => ({ ...r, _rowType: 'data' as const }))
  result.push({
    key: 'statutory-subtotal', segment: 'statutory', sourceName: '法定盈余公积小计',
    beginning: statutorySubtotal.value.beginning, accrual: statutorySubtotal.value.accrual,
    capitalConversion: statutorySubtotal.value.capitalConversion, lossOffset: statutorySubtotal.value.lossOffset,
    endBalance: statutorySubtotal.value.endBalance, unadjBeginning: 0, unadjAccrual: 0,
    unadjConversion: 0, unadjLossOffset: 0, unadjEnd: 0, ajeAmount: 0, rjeAmount: 0,
    auditedEnd: statutorySubtotal.value.auditedEnd, remark: '', _rowType: 'subtotal',
  })
  return result
})

const discretionaryTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = computedRows.value
    .filter(r => r.segment === 'discretionary')
    .map(r => ({ ...r, _rowType: 'data' as const }))
  result.push({
    key: 'discretionary-subtotal', segment: 'discretionary', sourceName: '任意盈余公积小计',
    beginning: discretionarySubtotal.value.beginning, accrual: discretionarySubtotal.value.accrual,
    capitalConversion: discretionarySubtotal.value.capitalConversion, lossOffset: discretionarySubtotal.value.lossOffset,
    endBalance: discretionarySubtotal.value.endBalance, unadjBeginning: 0, unadjAccrual: 0,
    unadjConversion: 0, unadjLossOffset: 0, unadjEnd: 0, ajeAmount: 0, rjeAmount: 0,
    auditedEnd: discretionarySubtotal.value.auditedEnd, remark: '', _rowType: 'subtotal',
  })
  return result
})

function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  return row._rowType === 'subtotal' ? 'subtotal-row' : ''
}

// ─── 行操作代理（表格索引→detailRows原始索引） ───────────────────────────────
function getSegmentRawIndex(tableIndex: number, segment: M5DetailSegment): number {
  const segmentRows = computedRows.value.filter(r => r.segment === segment)
  if (tableIndex < 0 || tableIndex >= segmentRows.length) return -1
  const targetKey = segmentRows[tableIndex].key
  return detailRows.value.findIndex(r => r.key === targetKey)
}

function updateStatutoryRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getSegmentRawIndex(tableIndex, 'statutory')
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as keyof M5DetailRow, value)
}
function updateDiscretionaryRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getSegmentRawIndex(tableIndex, 'discretionary')
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as keyof M5DetailRow, value)
}
function handleRemoveStatutoryRow(tableIndex: number): void {
  const rawIdx = getSegmentRawIndex(tableIndex, 'statutory')
  if (rawIdx >= 0) removeRow(rawIdx)
}
function handleRemoveDiscretionaryRow(tableIndex: number): void {
  const rawIdx = getSegmentRawIndex(tableIndex, 'discretionary')
  if (rawIdx >= 0) removeRow(rawIdx)
}

async function handleAddRow(segment: M5DetailSegment): Promise<void> {
  await addRow(segment)
}

// ─── 交叉验证（从formData恢复M5-1审定表合计） ────────────────────────────────
const crossValidation = computed(() => {
  const adjStatutoryResp = formData.allResponses.value.get('M5-1-statutory-audited-total')
  const adjDiscretionaryResp = formData.allResponses.value.get('M5-1-discretionary-audited-total')
  const adjStatutoryTotal = Number(adjStatutoryResp?.remark) || 0
  const adjDiscretionaryTotal = Number(adjDiscretionaryResp?.remark) || 0
  return crossValidateWithAdjudication(adjStatutoryTotal, adjDiscretionaryTotal)
})

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave() {
  isSaving.value = true
  try {
    for (let i = 0; i < detailRows.value.length; i++) {
      const row = detailRows.value[i]
      formData.debouncedSave(`M5-2-row-${i + 1}-data`, {
        remark: JSON.stringify({
          key: row.key, segment: row.segment, sourceName: row.sourceName,
          beginning: row.beginning, accrual: row.accrual,
          capitalConversion: row.capitalConversion, lossOffset: row.lossOffset,
          unadjBeginning: row.unadjBeginning, unadjAccrual: row.unadjAccrual,
          unadjConversion: row.unadjConversion, unadjLossOffset: row.unadjLossOffset,
          ajeAmount: row.ajeAmount, rjeAmount: row.rjeAmount, remark: row.remark,
        }),
      })
    }
    // 保存合计（供M5-1交叉验证读取）
    formData.debouncedSave('M5-M5-2-total-end-amount', { remark: String(grandTotal.value.endBalance) })
    ElMessage.success('明细表已保存')
    emit('save')
  } finally { isSaving.value = false }
}

function saveAuditNote() {
  formData.debouncedSave('M5-2-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) { /* AI辅助钩子 */ }
function handleReview() { openReviewDialog?.('M5-2-detail', '盈余公积明细表') }

// ─── 导入导出 ────────────────────────────────────────────────────────────────
function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('M5-2')
      break
    case 'exportData':
      importExport.exportData('M5-2')
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const result = await importExport.importData('M5-2', file)
  if (result?.success) {
    // 重新加载数据
    await formData.loadData()
    _restoreRows()
  }
  // 清除文件选择，允许重复导入同一文件
  input.value = ''
}

// ─── selfLoad + 数据恢复 ─────────────────────────────────────────────────────
function _restoreRows(): void {
  const restored: M5DetailRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M5-2-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m5-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          segment: d.segment || 'statutory',
          sourceName: d.sourceName || '',
          beginning: Number(d.beginning) || 0,
          accrual: Number(d.accrual) || 0,
          capitalConversion: Number(d.capitalConversion) || 0,
          lossOffset: Number(d.lossOffset) || 0,
          endBalance: 0,
          unadjBeginning: Number(d.unadjBeginning) || 0,
          unadjAccrual: Number(d.unadjAccrual) || 0,
          unadjConversion: Number(d.unadjConversion) || 0,
          unadjLossOffset: Number(d.unadjLossOffset) || 0,
          unadjEnd: 0,
          ajeAmount: Number(d.ajeAmount) || 0,
          rjeAmount: Number(d.rjeAmount) || 0,
          auditedEnd: 0,
          remark: d.remark || '',
        })
      } catch { /* skip malformed */ }
    }
  }
  if (restored.length > 0) detailRows.value = restored
}

// ─── EventBus ────────────────────────────────────────────────────────────────
function handleAdjustmentCreated() { formData.loadData() }

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M5-2-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
})
</script>

<style scoped>
.m5-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.block-subtotal { margin-top: 8px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }
.detail-footer { margin-top: 8px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.m5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m5-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m5-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m5-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
