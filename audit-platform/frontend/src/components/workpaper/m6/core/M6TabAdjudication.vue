<template>
  <div class="m6-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M6-1 未分配利润审定表</h3>
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
        <strong>利润分配-未分配利润（4104）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（净利润转入） − 借方（分配：提取盈余公积 + 宣告股利）。
        审定数 = 未审数 + AJE + RJE。
        核心公式链：期末未分配利润 = 期初 + 本年净利润 − 提取盈余公积(M5) − 应付股利(M1)。
        审定数变化自动回写试算表（4104）并通知M5/M1联动组件。
      </div>
    </div>

    <!-- ═══ 单区块：利润分配-未分配利润 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">利润分配-未分配利润</h4>
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
        <!-- 项目名称 -->
        <el-table-column prop="itemName" label="项目" min-width="180" fixed>
          <template #default="{ row, $index }">
            <template v-if="isTotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
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
              <el-input-number
                :model-value="row.beginning"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'beginning', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方发生(净利润转入) -->
        <el-table-column label="贷方发生(净利润转入)" width="170" align="right">
          <template #header>
            <el-tooltip content="贷方增加：本年净利润结转转入" placement="top">
              <span class="formula-col-header">贷方发生(净利润转入)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 借方发生(分配) -->
        <el-table-column label="借方发生(分配)" width="140" align="right">
          <template #header>
            <el-tooltip content="借方减少：提取盈余公积+宣告股利" placement="top">
              <span class="formula-col-header">借方发生(分配)</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 期末 (公式列) -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(净利润转入) − 借方(分配)" placement="top">
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
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'unadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.aje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'aje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.rje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdateRow($index, 'rje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定 (公式列) -->
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

        <!-- 差异 -->
        <el-table-column label="差异" width="100" align="right">
          <template #header>
            <el-tooltip content="差异 = 审定数 − 试算平衡表数" placement="top">
              <span class="formula-col-header">差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'diff-warning': Math.abs(row.tbDiff) > 0.01 }">
              {{ row.tbDiff !== 0 ? fmtAmount(row.tbDiff) : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动率 -->
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 删除 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button
              v-if="isDataRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemoveRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计 + 期末校验 + TB回写状态 + M6-2交叉验证 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">
        合计审定: {{ fmtAmount(totalRow.audited) }}
      </el-tag>
      <el-tag type="success" size="small" effect="plain">
        TB回写: 科目4104 利润分配-未分配利润（贷方/权益类）
      </el-tag>
      <el-tag
        :type="equityEndCheck.isMatch ? 'success' : 'danger'"
        size="small"
        effect="plain"
      >
        期末校验: {{ fmtAmount(equityEndCheck.actual) }}
        {{ equityEndCheck.isMatch ? '=' : '≠' }}
        期初+贷方−借方{{ fmtAmount(equityEndCheck.expected) }}
        <template v-if="!equityEndCheck.isMatch">
          （差异: {{ fmtAmount(equityEndCheck.diff) }}）
        </template>
      </el-tag>
      <el-tag
        v-if="totalChangeRate !== 0"
        :type="Math.abs(totalChangeRate) > 0.2 ? 'warning' : 'info'"
        size="small"
        effect="plain"
      >
        变动率: {{ (totalChangeRate * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 关联底稿：</span>
      <GtIndexChip value="M6-2" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">明细表（期末交叉验证）</span>
      <GtIndexChip value="M5" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">盈余公积计提</span>
      <GtIndexChip value="M1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">应付股利宣告</span>
      <GtIndexChip value="A" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">本年利润（结转来源）</span>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">原因分析及审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写未分配利润审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>利润分配-未分配利润（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（净利润转入） − 借方（分配）</li>
        <li>核心公式链：期末未分配利润 = 期初 + 本年净利润 − 提取盈余公积(M5) − 应付股利(M1)</li>
        <li>本年净利润转入：<strong>贷方增加</strong>（借:本年利润 贷:利润分配-未分配利润）</li>
        <li>提取盈余公积：<strong>借方减少</strong>（借:利润分配-未分配利润 贷:盈余公积）</li>
        <li>宣告分配股利：<strong>借方减少</strong>（借:利润分配-未分配利润 贷:应付股利）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>审定数变化自动回写 TB（科目 4104）并通知 M5/M1 联动组件</li>
        <li>合计行应与明细表 M6-2 的期末未分配利润一致（交叉验证）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabAdjudication — M6-1 未分配利润审定表（权益类贷方！）
 * Requirements: 2.1-2.7
 *
 * 单区块：利润分配-未分配利润（贷方/权益类！）
 * 列：项目 | 期初 | 贷方发生(净利润转入) | 借方发生(分配) | 期末 | 未审 | AJE | RJE | 审定 | 差异 | 变动率
 * 公式列虚线下划线+cursor:help+tooltip
 * 审定数变化 → writebackTB(4104) + EventBus
 * 与M6-2明细交叉验证
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM6FormData } from '../../composables/useM6FormData'
import { useM6DualMode } from '../../composables/useM6DualMode'
import {
  useM6Adjudication,
  type M6AdjudicationRow,
} from '../../composables/useM6Adjudication'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

const formData = useM6FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM6DualMode({ wpId: computed(() => props.wpId) })
const rows = ref<M6AdjudicationRow[]>([])

const {
  computedRows, totalRow, totalChangeRate, equityEndCheck,
  addRow, removeRow, updateRow: composableUpdateRow, saveAndWriteback,
  subscribeDisclosure,
} = useM6Adjudication(formData, rows)

// ─── 表格数据：数据行 + 合计行 ──────────────────────────────────────────────
interface TableRow extends M6AdjudicationRow { _rowType?: 'data' | 'total' }

const tableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = computedRows.value.map(r => ({ ...r, _rowType: 'data' as const }))
  // 合计行
  result.push({
    key: 'total-row',
    itemName: '合计',
    category: 'other',
    beginning: totalRow.value.beginning,
    creditAmount: totalRow.value.creditAmount,
    debitAmount: totalRow.value.debitAmount,
    endBalance: totalRow.value.endBalance,
    unadjusted: totalRow.value.unadjusted,
    aje: totalRow.value.aje,
    rje: totalRow.value.rje,
    audited: totalRow.value.audited,
    tbBalance: totalRow.value.tbBalance,
    tbDiff: totalRow.value.tbDiff,
    changeRate: 0,
    _rowType: 'total',
  })
  return result
})

function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isTotalRow(row: TableRow): boolean { return row._rowType === 'total' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  return row._rowType === 'total' ? 'total-row' : ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdateRow(tableIndex: number, field: string, value: string | number): void {
  if (tableIndex < 0 || tableIndex >= computedRows.value.length) return
  composableUpdateRow(tableIndex, field as any, value)
}

function handleRemoveRow(tableIndex: number): void {
  if (tableIndex < 0 || tableIndex >= computedRows.value.length) return
  removeRow(tableIndex)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入项目名称', '新增利润分配项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：本年净利润转入 / 提取法定盈余公积 / 应付普通股股利',
      inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
    })
    if (value && value.trim()) addRow(value.trim())
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

function saveAuditNote() {
  formData.debouncedSave('M6-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) { /* AI钩子 */ }
function handleReview() { openReviewDialog?.('M6-1-adjudication', '未分配利润审定表') }

// ─── EventBus ────────────────────────────────────────────────────────────────
function handleAdjustmentCreated() { formData.loadData() }
let unsubscribeDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()
  // 恢复已有行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) rows.value = restored
  }
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M6-1-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark

  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  unsubscribeDisclosure = subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  if (unsubscribeDisclosure) { unsubscribeDisclosure(); unsubscribeDisclosure = null }
})

/**
 * 从 checklist_responses 恢复已保存的行数据
 */
function _restoreRows(): M6AdjudicationRow[] {
  const restored: M6AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M6-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m6-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          category: d.category || 'other',
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
      } catch { /* skip corrupted */ }
    }
  }
  return restored
}
</script>

<style scoped>
.m6-tab-adjudication { padding: 12px; font-size: 13px; }
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

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
.high-change { color: #e6a23c; font-weight: 600; }
.diff-warning { color: #f56c6c; font-weight: 600; }

:deep(.el-table) { font-size: 13px; }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }

.adjudication-footer { margin-top: 8px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }

/* 跨底稿联动 */
.cross-wp-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 16px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
}
.cross-wp-label {
  font-weight: 600;
  color: #303133;
  flex-shrink: 0;
}
.cross-wp-desc {
  color: #606266;
  font-size: 12px;
  margin-right: 8px;
}

.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.m6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m6-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m6-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m6-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
