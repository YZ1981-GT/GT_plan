<template>
  <div class="m7-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M7-1 专项储备审定表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额·4201
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
        <strong>专项储备（4201）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（计提增加） − 借方（使用减少）。
        审定数 = 未审数 + AJE + RJE。
        安全生产费计提在贷方增加（借:生产成本/管理费用 贷:专项储备）；
        费用性支出直接冲减专项储备（借方减少）；
        资本性支出形成固定资产同时全额计提折旧冲减专项储备。
        本表按安全生产费/维简费/其他专项储备分类小计。
        审定数变化自动回写试算表（4201）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 单区块：专项储备（按类别分组+小计） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">专项储备明细（4201 贷方/权益类）</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="tableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 项目列 -->
        <el-table-column prop="itemName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="isTotalRow(row)">
              <span class="grand-total-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => handleUpdateRow($index, 'itemName', val)"
              />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方发生（计提） -->
        <el-table-column label="贷方发生（计提）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'creditAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 借方发生（使用） -->
        <el-table-column label="借方发生（使用）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'debitAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列） -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(计提) − 借方(使用)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 未审 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定（公式列） -->
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

        <!-- TB数 -->
        <el-table-column label="TB数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.tbBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow($index, 'tbBalance', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.tbBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 差异（公式列） -->
        <el-table-column label="差异" width="110" align="right">
          <template #header>
            <el-tooltip content="差异 = 审定 − TB数" placement="top">
              <span class="formula-col-header">差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': Math.abs(row.tbDiff) > 0.01 }]">
              {{ fmtAmount(row.tbDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动率 -->
        <el-table-column label="变动率" width="90" align="right">
          <template #header>
            <el-tooltip content="变动率: IF(期初=0且期末=0,0; 期初=0,100%; 否则期末/期初)" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计 + 期末校验 + TB回写状态 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">合计审定: {{ fmtAmount(totalRow.audited) }}</el-tag>
      <el-tag type="success" size="small" effect="plain">TB回写: 科目4201 专项储备（贷方/权益类）</el-tag>
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

    <!-- ═══ 分类小计摘要 ═══ -->
    <div class="category-summary">
      <el-tag type="info" size="small" effect="plain">安全生产费小计: {{ fmtAmount(safetyProductionSubtotal.audited) }}</el-tag>
      <el-tag type="info" size="small" effect="plain">维简费小计: {{ fmtAmount(maintenanceSubtotal.audited) }}</el-tag>
      <el-tag type="info" size="small" effect="plain">其他专项储备小计: {{ fmtAmount(otherSubtotal.audited) }}</el-tag>
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写专项储备审定表审计结论..."
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>专项储备（4201）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提） − 借方（使用）</li>
        <li>安全生产费：高危行业按产量或营业收入分档计提，贷方增加</li>
        <li>费用性支出：直接冲减专项储备（借方减少）</li>
        <li>资本性支出：形成固定资产 + 同时全额折旧冲减专项储备（联动H1）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>审定数变化自动回写 TB（科目 4201）并通知附注组件</li>
        <li>合计行应与M7-2明细表合计一致（交叉验证）</li>
        <li>分类：安全生产费 / 维简费 / 其他专项储备</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabAdjudication — M7-1 专项储备审定表（权益类贷方！）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 权益类单区块（4201 专项储备, 贷方权益类）
 * Columns: 项目 | 期初 | 贷方发生(计提) | 借方发生(使用) | 期末 | 未审 | AJE | RJE | 审定 | TB数 | 差异 | 变动率
 * - useM7FormData + useM7Adjudication composable
 * - Font 13px, formula columns with dashed underline + cursor:help + tooltip
 * - TB回写(4201) on 审定数变化
 * - EventBus 'substantive:adjudicated' publish
 * - el-segmented 双模式 (HTML/OO) via useM7DualMode
 * - 方法论上下文琥珀色块 (权益类贷方方向说明)
 * - el-card for 审计结论区
 * - Section标题行右侧AI辅助按钮 + 复核对话按钮
 * - 编制提示details折叠底部
 * - Version trail integration (useVersionTrail)
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM7FormData } from '../../composables/useM7FormData'
import { useM7DualMode } from '../../composables/useM7DualMode'
import {
  useM7Adjudication,
  type M7AdjudicationRow,
  type M7RowCategory,
} from '../../composables/useM7Adjudication'
import { useVersionTrail } from '../../composables/useVersionTrail'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM7FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM7DualMode({ wpId: computed(() => props.wpId) })
const rows = ref<M7AdjudicationRow[]>([])

const {
  computedRows,
  safetyProductionSubtotal,
  maintenanceSubtotal,
  otherSubtotal,
  totalRow,
  totalChangeRate,
  equityEndCheck,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
  subscribeAdjudicated,
  subscribeDisclosure,
} = useM7Adjudication(formData, rows)

// Version trail (autoSnapshot on save)
const versionTrail = useVersionTrail({ projectId: computed(() => props.projectId), workpaperId: computed(() => props.wpId) })

// ─── 表格数据构建（data rows + 分类小计 + 合计） ─────────────────────────────
interface TableRow extends M7AdjudicationRow { _rowType?: 'data' | 'subtotal' | 'total' }

const tableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []

  // 安全生产费行
  const safetyRows = computedRows.value.filter(r => r.category === 'safety-production')
  safetyRows.forEach(r => result.push({ ...r, _rowType: 'data' }))
  if (safetyRows.length > 0) {
    result.push(_buildSubtotalRow('safety-production', '安全生产费小计', safetyProductionSubtotal.value))
  }

  // 维简费行
  const maintenanceRows = computedRows.value.filter(r => r.category === 'maintenance')
  maintenanceRows.forEach(r => result.push({ ...r, _rowType: 'data' }))
  if (maintenanceRows.length > 0) {
    result.push(_buildSubtotalRow('maintenance', '维简费小计', maintenanceSubtotal.value))
  }

  // 其他专项储备行
  const otherRows = computedRows.value.filter(r => r.category === 'other')
  otherRows.forEach(r => result.push({ ...r, _rowType: 'data' }))
  if (otherRows.length > 0) {
    result.push(_buildSubtotalRow('other', '其他专项储备小计', otherSubtotal.value))
  }

  // 合计行
  result.push(_buildTotalRow())

  return result
})

function _buildSubtotalRow(category: M7RowCategory, label: string, subtotal: any): TableRow {
  return {
    key: `${category}-subtotal`,
    itemName: label,
    category,
    beginning: subtotal.beginning,
    creditAmount: subtotal.creditAmount,
    debitAmount: subtotal.debitAmount,
    endBalance: subtotal.endBalance,
    unadjusted: subtotal.unadjusted,
    aje: subtotal.aje,
    rje: subtotal.rje,
    audited: subtotal.audited,
    tbBalance: subtotal.tbBalance,
    tbDiff: subtotal.tbDiff,
    changeRate: 0,
    _rowType: 'subtotal',
  }
}

function _buildTotalRow(): TableRow {
  const t = totalRow.value
  return {
    key: 'grand-total',
    itemName: '合 计',
    category: 'safety-production',
    beginning: t.beginning,
    creditAmount: t.creditAmount,
    debitAmount: t.debitAmount,
    endBalance: t.endBalance,
    unadjusted: t.unadjusted,
    aje: t.aje,
    rje: t.rje,
    audited: t.audited,
    tbBalance: t.tbBalance,
    tbDiff: t.tbDiff,
    changeRate: 0,
    _rowType: 'total',
  }
}

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }
function isTotalRow(row: TableRow): boolean { return row._rowType === 'total' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'subtotal') return 'subtotal-row'
  if (row._rowType === 'total') return 'total-row'
  return ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function getRawIndex(tableIndex: number): number {
  // tableIndex对应tableRows中的位置，需要找到对应的原始rows索引
  const tableRow = tableRows.value[tableIndex]
  if (!tableRow || tableRow._rowType !== 'data') return -1
  return rows.value.findIndex(r => r.key === tableRow.key)
}

function handleUpdateRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getRawIndex(tableIndex)
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as any, value)
}

function handleRemoveRow(tableIndex: number): void {
  const rawIdx = getRawIndex(tableIndex)
  if (rawIdx >= 0) removeRow(rawIdx)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入专项储备项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：安全生产费-煤矿开采',
      inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
    })
    if (!name || !name.trim()) return

    // 选择分类
    const { value: cat } = await ElMessageBox.prompt(
      '请选择分类（输入编号）：\n1. 安全生产费\n2. 维简费\n3. 其他专项储备',
      '选择分类',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '1/2/3',
        inputValidator: (v: string) => (['1', '2', '3'].includes(v?.trim()) ? true : '请输入1/2/3'),
      },
    )
    const categoryMap: Record<string, M7RowCategory> = { '1': 'safety-production', '2': 'maintenance', '3': 'other' }
    const category = categoryMap[cat?.trim() || '1'] || 'safety-production'
    addRow(name.trim(), category)
  } catch { /* 用户取消 */ }
}

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditConclusion = ref('')

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    await saveAndWriteback()
    // autoSnapshot via version trail
    await versionTrail.createSnapshot('M7-1 审定表保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditConclusion(): void {
  formData.debouncedSave('M7-1-auditConclusion', { remark: auditConclusion.value || null })
}

function handleAI(_section: string): void { /* AI辅助钩子：后续集成 */ }
function handleReview(): void { openReviewDialog?.('M7-1-adjudication', '专项储备审定表') }

// ─── EventBus + Lifecycle ────────────────────────────────────────────────────
function handleAdjustmentCreated(): void { formData.loadData() }
let unsubAdjudicated: (() => void) | null = null
let unsubDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()
  // 恢复行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) rows.value = restored
  }
  // 恢复审计结论
  const noteResp = formData.allResponses.value.get('M7-1-auditConclusion')
  if (noteResp?.remark) auditConclusion.value = noteResp.remark

  // EventBus subscriptions
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  unsubAdjudicated = subscribeAdjudicated(() => { formData.loadData() })
  unsubDisclosure = subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  if (unsubAdjudicated) { unsubAdjudicated(); unsubAdjudicated = null }
  if (unsubDisclosure) { unsubDisclosure(); unsubDisclosure = null }
})

// ─── 从 checklist_responses 恢复行数据 ───────────────────────────────────────
function _restoreRows(): M7AdjudicationRow[] {
  const restored: M7AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M7-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m7-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          category: d.category || 'safety-production',
          beginning: Number(d.beginning) || 0,
          creditAmount: Number(d.creditAmount) || 0,
          debitAmount: Number(d.debitAmount) || 0,
          endBalance: 0,
          unadjusted: Number(d.unadjusted) || 0,
          aje: Number(d.aje) || 0,
          rje: Number(d.rje) || 0,
          audited: 0,
          tbBalance: Number(d.tbBalance) || 0,
          tbDiff: 0,
          changeRate: 0,
        })
      } catch { /* skip corrupt data */ }
    }
  }
  return restored
}
</script>

<style scoped>
.m7-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

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

/* ─── 行样式 ─── */
.total-row-label { font-weight: 700; color: #303133; }
.grand-total-label { font-weight: 700; color: #303133; font-size: var(--wp-font-size, 13px); }
.high-change { color: #e6a23c; font-weight: 600; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }
:deep(.total-row) { background: #ecf5ff !important; font-weight: 700; }
:deep(.total-row td) { border-top: 2px solid #409eff; }

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

/* ─── 分类小计摘要 ─── */
.category-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

/* ─── 审计结论卡片 ─── */
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 编制提示折叠 ─── */
.m7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m7-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m7-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m7-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
