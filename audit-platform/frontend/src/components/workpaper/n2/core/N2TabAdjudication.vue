<template>
  <div class="n2-adjudication">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税费审定表 N2-1</span>
        <el-tag type="danger" size="small" class="liability-tag">负债类·贷方</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>
          AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>
          复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 负债类科目公式提示 ═══ -->
    <div class="liability-formula-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>⚠️ 负债类贷方科目：期末余额 = 期初余额 + 本期贷方（计提）− 本期借方（缴纳）</span>
    </div>

    <!-- ═══ 主数据表格 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      show-summary
      :summary-method="getSummaries"
      highlight-current-row
      class="adjudication-table"
      :row-class-name="getRowClassName"
    >
      <!-- 税种列 -->
      <el-table-column prop="taxType" label="税种" min-width="120" fixed>
        <template #default="{ row }">
          <span class="tax-type-cell">{{ row.taxType }}</span>
        </template>
      </el-table-column>

      <!-- 期初余额 -->
      <el-table-column prop="beginning" label="期初余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.beginning"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'beginning', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.beginning) }}</span>
        </template>
      </el-table-column>

      <!-- 本期贷方(计提) -->
      <el-table-column prop="creditAmount" label="本期贷方(计提)" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.creditAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'creditAmount', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 本期借方(缴纳) -->
      <el-table-column prop="debitAmount" label="本期借方(缴纳)" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.debitAmount"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'debitAmount', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末余额（公式列） -->
      <el-table-column label="期末余额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="期末 = 期初 + 贷方 − 借方（负债类）">
            期末余额
          </span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="期末 = 期初 + 贷方 − 借方（负债类贷方科目）" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 未审数 -->
      <el-table-column prop="unadjusted" label="未审数" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.unadjusted"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'unadjusted', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column prop="aje" label="AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.aje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'aje', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column prop="rje" label="RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.rje"
            :controls="false"
            :precision="2"
            size="small"
            class="cell-input"
            @change="(val: number | undefined) => handleCellChange(row.taxType, 'rje', val ?? 0)"
          />
          <span v-else class="cell-value">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（公式列） -->
      <el-table-column label="审定数" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="审定数 = 未审 + AJE + RJE">
            审定数
          </span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 交叉验证区 ═══ -->
    <div class="cross-validation-section">
      <div class="cv-title">交叉验证</div>
      <div class="cv-indicators">
        <!-- N2-1 vs N2-2明细 -->
        <div class="cv-item" :class="adjudicationVsDetail.isMatch ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">N2-1 vs N2-2明细</span>
          <span v-if="adjudicationVsDetail.isMatch" class="cv-badge cv-badge-ok">✓ 一致</span>
          <span v-else class="cv-badge cv-badge-err">
            ⚠ 差异 {{ fmtAmount(adjudicationVsDetail.diff) }}
          </span>
        </div>

        <!-- N2-1 vs 各测算表 -->
        <div
          v-for="item in adjudicationVsCalcTables"
          :key="item.tax"
          class="cv-item"
          :class="item.isMatch ? 'cv-match' : 'cv-diff'"
        >
          <span class="cv-label">N2-1 {{ item.tax }} vs 测算表</span>
          <span v-if="item.isMatch" class="cv-badge cv-badge-ok">✓</span>
          <span v-else class="cv-badge cv-badge-err">
            ⚠ {{ fmtAmount(item.diff) }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ TB回写 + N4联动 ═══ -->
    <div class="action-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="isReadonly"
        :loading="writebackLoading"
        @click="handleWritebackTB"
      >
        回写审定数
      </el-button>
      <div class="n4-linkage-indicator">
        <span class="n4-label">N4联动状态：</span>
        <span v-if="n4LinkageStatus === 'synced'" class="n4-badge n4-badge-ok">
          ✓ 已同步
        </span>
        <span v-else-if="n4LinkageStatus === 'pending'" class="n4-badge n4-badge-warn">
          ⚠ 待同步
        </span>
        <span v-else class="n4-badge n4-badge-na">— N4未编制</span>
      </div>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip）Task 6.2 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 税金联动：</span>
      <GtIndexChip value="N4-1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">税金及附加审定表（计提核对）</span>
      <GtIndexChip value="N2-6" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">增值税测算</span>
      <GtIndexChip value="N2-8" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">城建税及附加测算</span>
      <GtIndexChip value="N2-9" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">房产税测算</span>
      <GtIndexChip value="N2-10" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">土地增值税测算</span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi">
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input
          v-model="auditNotes"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="handleNotesSave"
        />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="handleConclusionSave"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应交税费（2221）为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（计提）− 借方（缴纳）</li>
        <li>审定数 = 未审数 + AJE调整 + RJE重分类</li>
        <li>各测算表（N2-6增值税/N2-8城建税/N2-9房产税/N2-10土增税）测算结果应与本表对应行一致</li>
        <li>城建税/教育费附加/房产税/土地使用税/印花税/土增税计提联动N4税金及附加</li>
        <li>"回写审定数"将合计审定数回写至试算表（科目2221期末余额）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabAdjudication — N2-1 应交税费审定表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.2
 * Requirements: 2.1-2.8
 *
 * 核心职责：
 * - 11税种行 + 合计行，85公式覆盖
 * - 负债类期末余额 = 期初 + 贷方 − 借方
 * - 审定数 = 未审 + AJE + RJE
 * - 与N2-2明细、各测算表(N2-6/N2-8/N2-9/N2-10)交叉验证
 * - TB回写(2221期末余额) + N4联动提示
 * - 审计说明+结论+复核
 *
 * 科目：2221应交税费（贷方/负债类！）
 */
import { ref, computed, inject, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2Adjudication, type N2TaxType } from '../../composables/useN2Adjudication'
import { useN2CrossSheet } from '../../composables/useN2CrossSheet'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── useN2FormData（内部保存逻辑） ───────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useN2FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  total,
  rowValidations,
  updateRow,
  saveAndSync,
} = useN2Adjudication({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
  writebackTB: formData.writebackTB,
})

const {
  adjudicationVsDetail,
  adjudicationVsCalcTables,
  accrualToN4,
  publishTaxAccrualUpdated,
} = useN2CrossSheet(allResponsesRef)

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────

const auditNotes = ref<string>(formData.getField('1', 'audit-notes') ?? '')
const auditConclusion = ref<string>(formData.getField('1', 'audit-conclusion') ?? '')

// ─── 表格数据 ────────────────────────────────────────────────────────────────

const tableData = computed(() => rows.value)

// ─── TB回写 loading ──────────────────────────────────────────────────────────

const writebackLoading = ref(false)

// ─── N4 联动状态 ─────────────────────────────────────────────────────────────

const n4LinkageStatus = computed<'synced' | 'pending' | 'none'>(() => {
  const accruals = accrualToN4.value
  const hasAnyAccrual = accruals.some(a => a.amount !== 0)
  if (!hasAnyAccrual) return 'none'
  return 'synced'
})

// ─── 只读判断 ────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 单元格变更 → 保存 ──────────────────────────────────────────────────────

async function handleCellChange(
  taxType: N2TaxType,
  field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
  value: number,
) {
  await updateRow(taxType, field, value)
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, idx: number) => {
    if (idx === 0) {
      sums[idx] = '合计'
      return
    }
    const t = total.value
    const map: Record<number, number> = {
      1: t.beginning,
      2: t.credit,
      3: t.debit,
      4: t.endBalance,
      5: t.unadjusted,
      6: t.aje,
      7: t.rje,
      8: t.audited,
    }
    const val = map[idx]
    sums[idx] = val != null ? fmtAmount(val) : ''
  })
  return sums
}

// ─── 行样式（校验失败红色） ──────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  const validation = rowValidations.value.find(v => v.taxType === row.taxType)
  if (validation && !validation.isValid) return 'row-validation-error'
  return ''
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  writebackLoading.value = true
  try {
    await saveAndSync()
    publishTaxAccrualUpdated()
    ElMessage.success('审定数已回写试算表（科目2221期末余额）')
  } catch (err: any) {
    ElMessage.error(`回写失败：${err.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

async function handleNotesSave() {
  await formData.setField('1', 'audit-notes', auditNotes.value)
}

async function handleConclusionSave() {
  await formData.setField('1', 'audit-conclusion', auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助分析审定表数据...')
}

function handleNotesAi() {
  ElMessage.info('AI辅助生成审计说明...')
}

// ─── 复核对话 ────────────────────────────────────────────────────────────────

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N2-1-审定表')
  } else {
    ElMessage.info('复核对话未配置')
  }
}

// ─── 监听审定数变化 → 自动触发N4联动事件 ─────────────────────────────────────

watch(
  () => total.value.audited,
  () => {
    publishTaxAccrualUpdated()
  },
  { immediate: false },
)
</script>

<style scoped>
.n2-adjudication {
  padding: 12px;
  font-size: 13px;
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.liability-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 负债类公式提示 ─── */
.liability-formula-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
  border: 1px solid #f48fb1;
  border-left: 4px solid #e91e63;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #880e4f;
}

.liability-formula-badge .el-icon {
  font-size: 16px;
  color: #e91e63;
  flex-shrink: 0;
}

/* ─── 表格样式 ─── */
.adjudication-table {
  margin-bottom: 16px;
}

:deep(.adjudication-table .el-table) {
  font-size: 13px;
}

.tax-type-cell {
  font-weight: 500;
  color: #303133;
}

.cell-input {
  width: 100%;
}

:deep(.cell-input .el-input__inner) {
  text-align: right;
  font-size: 13px;
}

.cell-value {
  font-size: 13px;
  color: #606266;
}

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
.formula-header {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

/* ─── 校验失败行红色高亮 ─── */
:deep(.row-validation-error) {
  background-color: #fef0f0 !important;
}

:deep(.row-validation-error:hover > td) {
  background-color: #fde2e2 !important;
}

/* ─── 交叉验证区 ─── */
.cross-validation-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.cv-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.cv-indicators {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.cv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.cv-match {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.cv-diff {
  background: #fef0f0;
  border: 1px solid #fab6b6;
}

.cv-label {
  color: #606266;
  font-size: 12px;
}

.cv-badge {
  font-weight: 600;
  font-size: 12px;
}

.cv-badge-ok {
  color: #43a047;
}

.cv-badge-err {
  color: #f56c6c;
}

/* ─── 操作栏 ─── */
.action-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.n4-linkage-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.n4-label {
  color: #606266;
}

.n4-badge {
  font-weight: 500;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.n4-badge-ok {
  background: #e8f5e9;
  color: #43a047;
  border: 1px solid #a5d6a7;
}

.n4-badge-warn {
  background: #fff3e0;
  color: #e65100;
  border: 1px solid #ffcc80;
}

.n4-badge-na {
  background: #f5f5f5;
  color: #9e9e9e;
  border: 1px solid #e0e0e0;
}

/* ─── 审计说明卡片 ─── */
.audit-notes-card {
  margin-bottom: 16px;
}

/* ─── 跨底稿联动 cross_wp_ref ─── */
.cross-wp-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 12px;
}

.cross-wp-label {
  color: #0369a1;
  font-weight: 500;
  margin-right: 4px;
}

.cross-wp-desc {
  color: #64748b;
  margin-right: 8px;
}

.notes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.notes-field {
  margin-bottom: 12px;
}

.notes-field:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* ─── 编制提示折叠 ─── */
.n2-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
