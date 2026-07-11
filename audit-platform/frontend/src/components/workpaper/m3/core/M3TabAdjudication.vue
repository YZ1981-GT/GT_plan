<template>
  <div class="m3-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M3-1 库存股审定表</h3>
        <el-tag type="warning" effect="dark" size="small" class="contra-equity-badge">
          权益备抵·借方余额
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

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective-alert">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        确认库存股（4002）的<strong>存在性</strong>（回购交易真实发生）、
        <strong>计价准确性</strong>（按回购成本法核算，注销/再售会计处理正确）、
        <strong>完整性</strong>、<strong>列报恰当性</strong>（作为所有者权益备减项列示）。
      </div>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景）─── 借方方向说明 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>库存股（4002）为权益备抵类借方科目：</strong>
        期末余额 = 期初 + 借方（回购增加） − 贷方（注销/再售减少）。
        审定数 = 未审数 + AJE + RJE。
        回购股份增加库存股记借方，注销或再出售减少库存股记贷方，
        与其他M权益类科目方向<strong>完全相反</strong>。按回购批次分类列示，
        审定数变化自动回写试算表（4002）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 库存股审定区块（权益备抵借方，按回购批次分类） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">库存股（借方/权益备抵，按回购批次分类）</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow"
        >
          + 新增回购批次
        </el-button>
      </div>

      <el-table
        :data="computedTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目（回购批次名） -->
        <el-table-column prop="batchName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow($index) || isTotalRow($index)">
              <span class="total-row-label">{{ row.batchName }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input
                :model-value="row.batchName"
                size="small"
                placeholder="回购批次名称"
                @change="(val: string) => updateRow($index, 'batchName', val)"
              />
            </template>
            <template v-else>
              {{ row.batchName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- B列: 期初余额（借方） -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginning"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginning', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 借方发生额（回购增加） -->
        <el-table-column label="借方发生（回购）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 贷方发生额（注销/再售减少） -->
        <el-table-column label="贷方发生（注销/再售）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期末余额（公式=期初+借方-贷方，权益备抵借方！） -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 借方(回购) − 贷方(注销/再售)【权益备抵借方】" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 未审数 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'unadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.aje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'aje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.rje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'rje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 审定数（公式=未审+AJE+RJE） -->
        <el-table-column label="审定" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列（非只读时） -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ $index }">
            <el-button
              v-if="isEditableRow($index)"
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

      <!-- 权益备抵期末校验 + TB回写状态 -->
      <div class="adjudication-footer">
        <el-tag type="warning" size="small" effect="plain">
          TB回写: 科目4002 库存股（借方/权益备抵）
        </el-tag>
        <el-tag
          :type="contraEquityCheck.isMatch ? 'success' : 'danger'"
          size="small"
          effect="plain"
        >
          期末校验: 期末{{ fmtAmount(contraEquityCheck.actual) }}
          {{ contraEquityCheck.isMatch ? '=' : '≠' }}
          期初+借方−贷方{{ fmtAmount(contraEquityCheck.expected) }}
          <template v-if="!contraEquityCheck.isMatch">
            （差异: {{ fmtAmount(contraEquityCheck.diff) }}）
          </template>
        </el-tag>
      </div>
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
        placeholder="请填写库存股审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>库存股（4002）为权益备抵类借方科目：期末 = 期初 + 借方（回购） − 贷方（注销/再售）</li>
        <li>方向相反：回购增加库存股记<strong>借方</strong>，注销/再售减少记<strong>贷方</strong>（与M2/M4/M5/M6权益类方向相反）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>按回购批次分类填列：逐一列示各回购批次的库存股变动</li>
        <li>小计行按批次分类自动汇总，合计行汇总全部批次</li>
        <li>审定数变化自动回写 TB（科目 4002）并通知附注组件</li>
        <li>期末校验：期末审定 应等于 期初 + 借方(回购) − 贷方(注销/再售)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabAdjudication — M3-1 库存股审定表（权益备抵借方！）
 *
 * Requirements: 2.1-2.7
 * - 单区块：库存股(借方/权益备抵) — 按回购批次分类 + 小计 + 合计
 * - 列结构（33×12）：
 *   A:项目(回购批次) | B:期初 | C:借方发生(回购) | D:贷方发生(注销/再售)
 *   | E:期末[公式=期初+借方-贷方] | F:未审 | G:AJE | H:RJE | I:审定[公式=未审+AJE+RJE]
 * - 公式列: 虚线下划线 + cursor:help + tooltip showing formula source
 * - 权益备抵校验: 期末=期初+借方-贷方（借方余额！）
 * - TB回写: 审定数变化 → writebackTB(4002)
 * - EventBus: publish 'substantive:adjudicated' on save
 * - el-segmented 双模式(HTML/OO) at top using useM3DualMode
 * - 复核按钮 (inject openReviewDialog)
 * - AI辅助 section title right-aligned button
 * - Table font-size 13px
 * - Uses useM3FormData + useM3Adjudication composables
 * - Props: wpId, projectId, isReadonly
 *
 * 科目：4002 库存股（**借方/权益备抵类！期末=期初+借方-贷方**）
 * 回购股份在借方增加库存股，注销/再售在贷方减少库存股（与其他M权益类方向相反！）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM3FormData } from '../../composables/useM3FormData'
import { useM3DualMode } from '../../composables/useM3DualMode'
import {
  useM3Adjudication,
  type M3AdjudicationRow,
} from '../../composables/useM3Adjudication'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'save'): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useM3DualMode({
  wpId: computed(() => props.wpId),
})

// ─── 审定表行数据（动态按回购批次分类行） ────────────────────────────────────────

const rows = ref<M3AdjudicationRow[]>([])

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows: rawComputedRows,
  totalRow,
  categorySubtotals,
  contraEquityCheck,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
} = useM3Adjudication(formData, rows)

// ─── 表格数据：数据行 + 小计行 + 合计行 ─────────────────────────────────────

interface TableRow extends M3AdjudicationRow {
  _rowType?: 'data' | 'subtotal' | 'total'
}

/** 全部表格行 = 按 category 分组 + 小计行 + 合计行 */
const computedTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []
  const grouped = new Map<string, M3AdjudicationRow[]>()

  // 按 category 分组
  for (const row of rawComputedRows.value) {
    const cat = row.category || '未分类'
    if (!grouped.has(cat)) grouped.set(cat, [])
    grouped.get(cat)!.push(row)
  }

  // 每组数据行 + 小计
  for (const [cat, catRows] of grouped.entries()) {
    for (const row of catRows) {
      result.push({ ...row, _rowType: 'data' })
    }
    // 小计行（仅多分类时显示）
    if (grouped.size > 1) {
      const sub = categorySubtotals.value.get(cat)
      if (sub) {
        result.push({
          key: `subtotal-${cat}`,
          batchName: `小计（${cat}）`,
          beginning: sub.beginning,
          debitAmount: sub.debitAmount,
          creditAmount: sub.creditAmount,
          endBalance: sub.endBalance,
          unadjusted: sub.unadjusted,
          aje: sub.aje,
          rje: sub.rje,
          audited: sub.audited,
          category: cat,
          _rowType: 'subtotal',
        })
      }
    }
  }

  // 合计行
  const total = totalRow.value
  result.push({
    key: 'grand-total',
    batchName: '合  计',
    beginning: total.beginning,
    debitAmount: total.debitAmount,
    creditAmount: total.creditAmount,
    endBalance: total.endBalance,
    unadjusted: total.unadjusted,
    aje: total.aje,
    rje: total.rje,
    audited: total.audited,
    category: '',
    _rowType: 'total',
  })

  return result
})

// ─── 原始数据行索引映射（tableRow index → rawRows index） ─────────────────

/** 获取 tableRow 对应的原始 rows index（-1 表示非数据行） */
function getRawIndex(tableIndex: number): number {
  const row = computedTableRows.value[tableIndex]
  if (!row || row._rowType !== 'data') return -1
  return rawComputedRows.value.findIndex(r => r.key === row.key)
}

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

function isEditableRow(index: number): boolean {
  const row = computedTableRows.value[index]
  return row?._rowType === 'data'
}

function isSubtotalRow(index: number): boolean {
  const row = computedTableRows.value[index]
  return row?._rowType === 'subtotal'
}

function isTotalRow(index: number): boolean {
  const row = computedTableRows.value[index]
  return row?._rowType === 'total'
}

function getRowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  const row = computedTableRows.value[rowIndex]
  if (row?._rowType === 'total') return 'total-row'
  if (row?._rowType === 'subtotal') return 'subtotal-row'
  return ''
}

// ─── 行操作代理 ──────────────────────────────────────────────────────────────

function updateRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getRawIndex(tableIndex)
  if (rawIdx < 0) return
  composableUpdateRow(rawIdx, field as any, value)
}

/** 新增回购批次行（先弹 ElMessageBox.prompt 输入名称） */
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入回购批次名称', '新增回购批次', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：2024年第一次回购、2023年Q3回购',
      inputValidator: (v: string) => (v && v.trim() ? true : '回购批次名称不能为空'),
    })
    if (value && value.trim()) {
      // 第二步：输入分类（category）
      let category = ''
      try {
        const catResult = await ElMessageBox.prompt(
          '请输入所属分类（可选，用于小计分组）',
          '分类',
          {
            confirmButtonText: '确定',
            cancelButtonText: '跳过',
            inputPlaceholder: '如：首次回购、二次回购',
          },
        )
        category = catResult.value?.trim() || ''
      } catch {
        // 用户跳过分类
      }
      addRow(value.trim(), category)
    }
  } catch {
    // 用户取消
  }
}

/** 删除行 */
function handleRemoveRow(tableIndex: number): void {
  const rawIdx = getRawIndex(tableIndex)
  if (rawIdx < 0) return
  removeRow(rawIdx)
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('M3-M3-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) {
  // AI辅助钩子（集成时实现）
}

function handleReview() {
  openReviewDialog?.('M3-1-adjudication', '库存股审定表')
}

// ─── EventBus: subscribe 'adjustment:created' 刷新AJE/RJE ────────────────────

function handleAdjustmentCreated() {
  formData.loadData()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 从 checklist_responses 恢复已存储的行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) {
      rows.value = restored
    }
  }
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M3-M3-1-auditNote')
  if (noteResp?.remark) {
    auditNote.value = noteResp.remark
  }
  // 订阅调整分录创建事件
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.on('substantive:adjudicated' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.off('substantive:adjudicated' as any, handleAdjustmentCreated)
})

// ─── 行数据恢复（从 checklist_responses） ───────────────────────────────────

function _restoreRows(): M3AdjudicationRow[] {
  const restored: M3AdjudicationRow[] = []
  const prefix = 'M3-M3-1-row-'
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data') && resp.remark) {
      try {
        const data = JSON.parse(resp.remark)
        restored.push({
          key: data.key || `m3-adj-restored-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          batchName: data.batchName || '',
          beginning: Number(data.beginning) || 0,
          debitAmount: Number(data.debitAmount) || 0,
          creditAmount: Number(data.creditAmount) || 0,
          endBalance: 0,
          unadjusted: Number(data.unadjusted) || 0,
          aje: Number(data.aje) || 0,
          rje: Number(data.rje) || 0,
          audited: 0,
          category: data.category || '',
        })
      } catch {
        // 解析失败跳过
      }
    }
  }
  return restored
}
</script>

<style scoped>
.m3-tab-adjudication {
  padding: 12px;
  font-size: 13px;
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

.contra-equity-badge {
  font-weight: 600;
}

.audit-objective-alert {
  margin-bottom: 16px;
}

.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

.block-section {
  margin-bottom: 24px;
}

.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.block-title {
  margin: 0;
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

.total-row-label {
  font-weight: 700;
  color: #303133;
}

:deep(.el-table) {
  font-size: 13px;
}

:deep(.total-row) {
  background: #fef0e6 !important;
  font-weight: 600;
}

:deep(.total-row td) {
  border-top: 2px solid #e6a23c;
}

:deep(.subtotal-row) {
  background: #fafafa !important;
  font-weight: 500;
}

:deep(.subtotal-row td) {
  border-top: 1px solid #dcdfe6;
}

.adjudication-footer {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.m3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
