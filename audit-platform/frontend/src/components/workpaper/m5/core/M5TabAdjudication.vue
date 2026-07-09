<template>
  <div class="m5-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M5-1 盈余公积审定表</h3>
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

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>盈余公积（4101）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（计提增加） − 借方（转增/弥补减少）。
        审定数 = 未审数 + AJE + RJE。
        法定盈余公积按净利润（弥补亏损后）10%计提，累计达注册资本50%可不再计提。
        任意盈余公积由股东大会决议自主计提。
        双区块：法定盈余公积 + 任意盈余公积。
        审定数变化自动回写试算表（4101）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 区块一：法定盈余公积 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">法定盈余公积</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('statutory')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="statutoryTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <el-table-column prop="itemName" label="项目" min-width="150" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => updateStatutoryRow($index, 'itemName', val)"
              />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
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

        <el-table-column label="贷方发生（计提）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'creditAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借方发生（转增/弥补）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'debitAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(计提) − 借方(转增/弥补)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateStatutoryRow($index, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审定" width="120" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveStatutoryRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">法定盈余公积小计审定: {{ fmtAmount(statutorySubtotal.audited) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 区块二：任意盈余公积 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">任意盈余公积</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow('discretionary')">+ 新增项目</el-button>
      </div>

      <el-table :data="discretionaryTableRows" border size="small" style="width:100%" :row-class-name="getRowClassName">
        <el-table-column prop="itemName" label="项目" min-width="150" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)"><span class="total-row-label">{{ row.itemName }}</span></template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input :model-value="row.itemName" size="small" placeholder="项目名称" @change="(val: string) => updateDiscretionaryRow($index, 'itemName', val)" />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'beginning', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方发生（计提）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'creditAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方发生（转增/弥补）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'debitAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="120" align="right">
          <template #header><el-tooltip content="权益类贷方: 期初+贷方−借方" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'unadjusted', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'aje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateDiscretionaryRow($index, 'rje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #header><el-tooltip content="审定=未审+AJE+RJE" placement="top"><span class="formula-col-header">审定</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">{{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveDiscretionaryRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">任意盈余公积小计审定: {{ fmtAmount(discretionarySubtotal.audited) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 合计 + 期末校验 + TB回写状态 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">合计审定: {{ fmtAmount(totalRow.audited) }}</el-tag>
      <el-tag type="success" size="small" effect="plain">TB回写: 科目4101 盈余公积（贷方/权益类）</el-tag>
      <el-tag :type="equityEndCheck.isMatch ? 'success' : 'danger'" size="small" effect="plain">
        期末校验: {{ fmtAmount(equityEndCheck.actual) }}
        {{ equityEndCheck.isMatch ? '=' : '≠' }}
        期初+贷方−借方{{ fmtAmount(equityEndCheck.expected) }}
        <template v-if="!equityEndCheck.isMatch">（差异: {{ fmtAmount(equityEndCheck.diff) }}）</template>
      </el-tag>
      <el-tag v-if="totalChangeRate !== 0" :type="Math.abs(totalChangeRate) > 0.2 ? 'warning' : 'info'" size="small" effect="plain">
        变动率: {{ (totalChangeRate * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">原因分析及审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写盈余公积审定表审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>盈余公积（4101）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提） − 借方（转增/弥补）</li>
        <li>法定盈余公积：按净利润（弥补以前年度亏损后）<strong>10%</strong>计提，累计达注册资本<strong>50%</strong>可不再计提</li>
        <li>任意盈余公积：股东大会决议自主计提（无比例限制）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>双区块展示：法定盈余公积 + 任意盈余公积</li>
        <li>审定数变化自动回写 TB（科目 4101）并通知附注组件</li>
        <li>合计行应与明细表M5-2的合计一致（交叉验证）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabAdjudication — M5-1 盈余公积审定表（权益类贷方！）
 * Requirements: 2.1-2.7
 * 双区块(法定+任意) + 合计行 + 试算平衡表数行 + 差异行
 * 公式列虚线下划线+cursor:help+tooltip
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM5FormData } from '../../composables/useM5FormData'
import { useM5DualMode } from '../../composables/useM5DualMode'
import {
  useM5Adjudication,
  type M5AdjudicationRow,
  type M5AdjudicationBlock,
} from '../../composables/useM5Adjudication'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

const formData = useM5FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM5DualMode({ wpId: computed(() => props.wpId) })
const rows = ref<M5AdjudicationRow[]>([])

const {
  computedRows, statutorySubtotal, discretionarySubtotal, totalRow,
  totalChangeRate, equityEndCheck, addRow, removeRow,
  updateRow: composableUpdateRow, saveAndWriteback, subscribeDisclosure,
} = useM5Adjudication(formData, rows)

// ─── 表格数据：按区块拆分 + 小计行 ──────────────────────────────────────────
interface TableRow extends M5AdjudicationRow { _rowType?: 'data' | 'subtotal' }

const statutoryTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = computedRows.value
    .filter(r => r.block === 'statutory')
    .map(r => ({ ...r, _rowType: 'data' as const }))
  result.push({
    key: 'statutory-subtotal', itemName: '法定盈余公积小计', block: 'statutory', category: 'statutory',
    beginning: statutorySubtotal.value.beginning, creditAmount: statutorySubtotal.value.creditAmount,
    debitAmount: statutorySubtotal.value.debitAmount, endBalance: statutorySubtotal.value.endBalance,
    unadjusted: statutorySubtotal.value.unadjusted, aje: statutorySubtotal.value.aje,
    rje: statutorySubtotal.value.rje, audited: statutorySubtotal.value.audited,
    tbBalance: statutorySubtotal.value.tbBalance, tbDiff: statutorySubtotal.value.tbDiff, changeRate: 0,
    _rowType: 'subtotal',
  })
  return result
})

const discretionaryTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = computedRows.value
    .filter(r => r.block === 'discretionary')
    .map(r => ({ ...r, _rowType: 'data' as const }))
  result.push({
    key: 'discretionary-subtotal', itemName: '任意盈余公积小计', block: 'discretionary', category: 'discretionary',
    beginning: discretionarySubtotal.value.beginning, creditAmount: discretionarySubtotal.value.creditAmount,
    debitAmount: discretionarySubtotal.value.debitAmount, endBalance: discretionarySubtotal.value.endBalance,
    unadjusted: discretionarySubtotal.value.unadjusted, aje: discretionarySubtotal.value.aje,
    rje: discretionarySubtotal.value.rje, audited: discretionarySubtotal.value.audited,
    tbBalance: discretionarySubtotal.value.tbBalance, tbDiff: discretionarySubtotal.value.tbDiff, changeRate: 0,
    _rowType: 'subtotal',
  })
  return result
})

function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  return row._rowType === 'subtotal' ? 'subtotal-row' : ''
}

// ─── 行操作代理 ──────────────────────────────────────────────────────────────
function getBlockRawIndex(tableIndex: number, block: M5AdjudicationBlock): number {
  const blockRows = computedRows.value.filter(r => r.block === block)
  if (tableIndex < 0 || tableIndex >= blockRows.length) return -1
  const targetKey = blockRows[tableIndex].key
  return rows.value.findIndex(r => r.key === targetKey)
}

function updateStatutoryRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getBlockRawIndex(tableIndex, 'statutory')
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as any, value)
}
function updateDiscretionaryRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getBlockRawIndex(tableIndex, 'discretionary')
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as any, value)
}
function handleRemoveStatutoryRow(tableIndex: number): void {
  const rawIdx = getBlockRawIndex(tableIndex, 'statutory')
  if (rawIdx >= 0) removeRow(rawIdx)
}
function handleRemoveDiscretionaryRow(tableIndex: number): void {
  const rawIdx = getBlockRawIndex(tableIndex, 'discretionary')
  if (rawIdx >= 0) removeRow(rawIdx)
}

async function handleAddRow(block: M5AdjudicationBlock): Promise<void> {
  const label = block === 'statutory' ? '法定盈余公积' : '任意盈余公积'
  try {
    const { value } = await ElMessageBox.prompt(`请输入${label}项目名称`, `新增${label}项目`, {
      confirmButtonText: '确定', cancelButtonText: '取消',
      inputPlaceholder: block === 'statutory' ? '如：按净利润10%提取法定盈余公积' : '如：股东会决议提取任意盈余公积',
      inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
    })
    if (value && value.trim()) addRow(value.trim(), block)
  } catch { /* 用户取消 */ }
}

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditNote = ref('')

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave() {
  isSaving.value = true
  try { await saveAndWriteback(); emit('save') } finally { isSaving.value = false }
}
function saveAuditNote() { formData.debouncedSave('M5-1-auditNote', { remark: auditNote.value || null }) }
function handleAI(_section: string) { /* AI钩子 */ }
function handleReview() { openReviewDialog?.('M5-1-adjudication', '盈余公积审定表') }

// ─── EventBus ────────────────────────────────────────────────────────────────
function handleAdjustmentCreated() { formData.loadData() }
let unsubscribeDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) rows.value = restored
  }
  const noteResp = formData.allResponses.value.get('M5-1-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  unsubscribeDisclosure = subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  if (unsubscribeDisclosure) { unsubscribeDisclosure(); unsubscribeDisclosure = null }
})

function _restoreRows(): M5AdjudicationRow[] {
  const restored: M5AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M5-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m5-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '', block: d.block || 'statutory', category: d.category || 'statutory',
          beginning: Number(d.beginning) || 0, creditAmount: Number(d.creditAmount) || 0,
          debitAmount: Number(d.debitAmount) || 0, endBalance: 0, unadjusted: Number(d.unadjusted) || 0,
          aje: Number(d.aje) || 0, rje: Number(d.rje) || 0, audited: 0,
          tbBalance: Number(d.tbBalance) || 0, tbDiff: 0, changeRate: 0,
        })
      } catch { /* skip */ }
    }
  }
  return restored
}
</script>

<style scoped>
.m5-tab-adjudication { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.block-subtotal { margin-top: 8px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
.high-change { color: #e6a23c; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }
.adjudication-footer { margin-top: 8px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.m5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m5-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m5-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m5-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
