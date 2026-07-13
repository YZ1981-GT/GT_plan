<template>
  <div class="m1-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M1-1 应付股利审定表</h3>
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
        确认应付股利（2232）的<strong>完整性</strong>（所有已宣告分配的股利均已入账）、
        <strong>计价准确性</strong>（金额及外币折算正确）、
        <strong>列报恰当性</strong>（作为流动负债列示，关联方股利充分披露）。
      </div>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>应付股利为负债类贷方科目（2232）：</strong>
        期末审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）。
        负债类期末余额 = 期初 + 贷方（宣告分配） − 借方（实际支付）。
        变动额 = 期末审定 − 期初审定。按股东分类列示，审定数变化自动回写试算表并通知附注组件。
      </div>
    </div>

    <!-- ═══ 应付股利审定区块（负债类单区块，按股东分类） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">应付股利（贷方/负债类，按股东分类）</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow"
        >
          + 新增股东
        </el-button>
      </div>

      <el-table
        :data="computedTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目（股东名称） -->
        <el-table-column prop="shareholderName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isTotalRow($index) || isTbCheckRow($index)">
              <span class="total-row-label">{{ row.shareholderName }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input
                :model-value="row.shareholderName"
                size="small"
                placeholder="股东名称"
                @change="(val: string) => updateRow($index, 'shareholderName', val)"
              />
            </template>
            <template v-else>
              {{ row.shareholderName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- B列: 期初未审数 -->
        <el-table-column label="期初未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 期初AJE -->
        <el-table-column label="期初AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 期初RJE -->
        <el-table-column label="期初RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.beginRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期初审定数（公式） -->
        <el-table-column label="期初审定" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期初未审 + 期初AJE + 期初RJE" placement="top">
              <span class="formula-col-header">期初审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 期末未审数 -->
        <el-table-column label="期末未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endUnadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: 期末AJE -->
        <el-table-column label="期末AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: 期末RJE -->
        <el-table-column label="期末RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isEditableRow($index) && !isReadonly">
              <el-input-number
                :model-value="row.endRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'endRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 期末审定数（公式） -->
        <el-table-column label="期末审定" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期末未审 + 期末AJE + 期末RJE" placement="top">
              <span class="formula-col-header">期末审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAudited) }}</span>
          </template>
        </el-table-column>

        <!-- J列: 变动额（公式） -->
        <el-table-column label="变动额" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 期末审定 − 期初审定" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'negative-value': row.varianceAmount < 0 }">
              {{ fmtAmount(row.varianceAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- K列: 变动率（公式） -->
        <el-table-column label="变动率" width="100" align="right">
          <template #header>
            <el-tooltip content="公式: 变动额 / 期初审定" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row.varianceRate) }}</span>
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

      <!-- TB回写状态 + 余额异常 -->
      <div class="adjudication-footer">
        <el-tag type="info" size="small" effect="plain">
          TB回写: 科目2232 应付股利
        </el-tag>
        <el-alert
          v-if="totalRow.endAudited < 0"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 8px"
        >
          余额异常：应付股利期末审定数为负，请核查数据
        </el-alert>
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
        placeholder="请填写审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应付股利为负债类贷方科目（2232）：期末 = 期初 + 贷方（宣告） − 借方（支付）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>变动额 = 期末审定 − 期初审定；变动率 = 变动额 / 期初审定</li>
        <li>按股东分类填列：逐一列示各股东应付股利</li>
        <li>小计行自动汇总各股东行数据</li>
        <li>审定数变化自动回写 TB（科目 2232）并通知附注组件</li>
        <li>宣告分配→贷方增加；实际支付→借方减少</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabAdjudication — M1-1 应付股利审定表
 *
 * Requirements: 2.1-2.7
 * - 负债类单区块：按股东分类行(动态) + 小计行
 * - 列结构（xlsx 56×12, B~L列）：
 *   A:项目(股东) | B-E:期初(未审/AJE/RJE/审定[公式]) | F-I:期末(未审/AJE/RJE/审定[公式]) | J:变动额[公式] | K:变动率[公式]
 * - 公式列: 虚线下划线 + cursor:help + tooltip showing formula source
 * - TB回写: 审定数变化 → writebackTB(2232)
 * - EventBus: subscribe 'adjustment:created' → refresh AJE/RJE columns
 * - el-segmented 双模式(HTML/OO) at top using useM1DualMode
 * - 复核按钮 (inject openReviewDialog)
 * - AI辅助 section title right-aligned button
 * - Table font-size 13px
 * - Uses useM1FormData + useM1Adjudication composables
 * - Props: wpId, projectId, isReadonly
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 * 宣告分配在贷方增加，实际支付在借方减少
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM1FormData } from '../../composables/useM1FormData'
import { useM1DualMode } from '../../composables/useM1DualMode'
import {
  useM1Adjudication,
  type M1AdjudicationRow,
} from '../../composables/useM1Adjudication'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useM1DualMode({
  wpId: computed(() => props.wpId),
})

// ─── 审定表行数据（动态按股东分类行） ────────────────────────────────────────

const rows = ref<M1AdjudicationRow[]>([])

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows: rawComputedRows,
  totalRow,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
} = useM1Adjudication(formData, rows)

// ─── 合计行 + TB核对行 → 拼装为表格数据 ────────────────────────────────────────

interface TableRow extends M1AdjudicationRow {
  _rowType?: 'data' | 'total' | 'tb-check'
}

/** 全部表格行 = 动态股东行 + 小计行 + TB核对行 */
const computedTableRows = computed<TableRow[]>(() => {
  const projectRows: TableRow[] = rawComputedRows.value.map(r => ({
    ...r,
    _rowType: 'data' as const,
  }))
  const total = totalRow.value
  const totalRowData: TableRow = {
    key: 'total',
    shareholderName: '小  计',
    beginUnadjusted: total.beginUnadjusted,
    beginAje: total.beginAje,
    beginRje: total.beginRje,
    beginAudited: total.beginAudited,
    endUnadjusted: total.endUnadjusted,
    endAje: total.endAje,
    endRje: total.endRje,
    endAudited: total.endAudited,
    varianceAmount: total.varianceAmount,
    varianceRate: total.varianceRate,
    _rowType: 'total',
  }
  const tbRow: TableRow = {
    key: 'tb-check',
    shareholderName: 'TB核对',
    beginUnadjusted: 0,
    beginAje: 0,
    beginRje: 0,
    beginAudited: 0,
    endUnadjusted: 0,
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    varianceAmount: 0,
    varianceRate: 0,
    _rowType: 'tb-check',
  }
  return [...projectRows, totalRowData, tbRow]
})

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

function isEditableRow(index: number): boolean {
  return index < rows.value.length
}

function isTotalRow(index: number): boolean {
  return index === rows.value.length
}

function isTbCheckRow(index: number): boolean {
  return index === rows.value.length + 1
}

function getRowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  if (isTotalRow(rowIndex)) return 'total-row'
  if (isTbCheckRow(rowIndex)) return 'tb-check-row'
  return ''
}

// ─── 行操作代理 ──────────────────────────────────────────────────────────────

function updateRow(index: number, field: string, value: string | number): void {
  if (!isEditableRow(index)) return
  composableUpdateRow(index, field as any, value)
}

/** 新增股东行（先弹 ElMessageBox.prompt 输入名称） */
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入股东名称', '新增股东行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：张三、某某公司',
      inputValidator: (v: string) => (v && v.trim() ? true : '股东名称不能为空'),
    })
    if (value && value.trim()) {
      addRow(value.trim())
    }
  } catch {
    // 用户取消
  }
}

/** 删除行 */
function handleRemoveRow(index: number): void {
  if (!isEditableRow(index)) return
  removeRow(index)
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('M1-M1-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `m1-adjudication-${section}`,
      prompt: `请基于应付股利底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('M1-1-adjudication', '审定表')
}

// ─── EventBus: subscribe 'adjustment:created' 刷新AJE/RJE ────────────────────

function handleAdjustmentCreated() {
  formData.loadData()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 如果没有行数据，预置一个空行引导用户
  if (rows.value.length === 0) {
    // 从 allResponses 恢复已存储的行数据
    const restored = _restoreRows()
    if (restored.length > 0) {
      rows.value = restored
    }
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

function _restoreRows(): M1AdjudicationRow[] {
  const restored: M1AdjudicationRow[] = []
  const prefix = 'M1-M1-1-row-'
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data') && resp.remark) {
      try {
        const data = JSON.parse(resp.remark)
        restored.push({
          key: data.key || `m1-adj-restored-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          shareholderName: data.shareholderName || '',
          beginUnadjusted: Number(data.beginUnadjusted) || 0,
          beginAje: Number(data.beginAje) || 0,
          beginRje: Number(data.beginRje) || 0,
          beginAudited: 0,
          endUnadjusted: Number(data.endUnadjusted) || 0,
          endAje: Number(data.endAje) || 0,
          endRje: Number(data.endRje) || 0,
          endAudited: 0,
          varianceAmount: 0,
          varianceRate: 0,
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
.m1-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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

.audit-objective-alert {
  margin-bottom: 16px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
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

.negative-value {
  color: #f56c6c;
}

.total-row-label {
  font-weight: 700;
  color: #303133;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.total-row) {
  background: #f0f9ff !important;
  font-weight: 600;
}

:deep(.total-row td) {
  border-top: 2px solid #409eff;
}

:deep(.tb-check-row) {
  background: #f5f7fa !important;
  font-style: italic;
  color: #909399;
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

.m1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
