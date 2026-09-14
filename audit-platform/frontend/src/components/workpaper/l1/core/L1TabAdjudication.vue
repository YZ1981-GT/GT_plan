<template>
  <div class="l1-tab-adjudication">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="adj-header">
      <el-button text size="small" @click="$emit('navigate', '底稿目录')">
        ← 返回目录
      </el-button>
      <h3 class="adj-title">L1-1 短期借款审定表</h3>
      <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="warning"
        plain
        @click="handleImportFromDetail"
      >从 L1-2 明细带入</el-button>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        <span class="ao-title">审计目标</span>
      </template>
      <ol class="ao-list">
        <li>资产负债表中记录的短期借款是存在的，且已记录在恰当的账户中（存在/完整性）；</li>
        <li>所有应记录的短期借款均已记录（完整性）；</li>
        <li>短期借款以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录（计价）；</li>
        <li>短期借款已被恰当地汇总或分解且表述清楚，相关披露符合企业会计准则（列报）。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>双期审定结构：</strong>
        期初数、期末数各按「未审数 → 账项调整 → 重分类调整 → 审定数」列示，
        审定数 = 未审数 + 账项调整 + 重分类调整。变动额/率反映本期相对期初的变化，比例超 30% 需在原因分析栏说明。
        期末未审合计应与明细表 L1-2 各行期末余额合计勾稽一致。
      </div>
    </div>

    <!-- ═══ 审定表主体（双期结构，分组表头） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <!-- 项目列 -->
      <el-table-column prop="label" label="项目" min-width="110" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.isTotal }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 期初数 -->
      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.beginUnadjusted" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'beginUnadjusted', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.beginAje" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'beginAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.beginRje" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'beginRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right">
          <template #header>
            <el-tooltip content="期初审定数 = 期初未审 + 账项调整 + 重分类调整" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 期末数 -->
      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.endUnadjusted" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'endUnadjusted', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.endAje" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'endAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.endRje" :controls="false" size="small" style="width: 100%"
              @change="(v: number | undefined) => handleCellChange(row.index, 'endRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right">
          <template #header>
            <el-tooltip content="期末审定数 = 期末未审 + 账项调整 + 重分类调整（回写 TB 2001）" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.endAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 本期未审 vs 期初 -->
      <el-table-column label="本期未审较期初" align="center">
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="changeClass(row.unadjChange)">{{ fmtAmount(row.unadjChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-warning': Math.abs(row.unadjRate) > 0.3 }">{{ fmtRate(row.unadjRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 本期审定 vs 期初 -->
      <el-table-column label="本期审定较期初" align="center">
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="changeClass(row.auditedChange)">{{ fmtAmount(row.auditedChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-warning': Math.abs(row.auditedRate) > 0.3 }">{{ fmtRate(row.auditedRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 原因分析 -->
      <el-table-column label="原因分析" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable && !isReadonly"
            :model-value="row.reason" size="small" placeholder="变动率超30%需说明"
            @input="(v: string) => handleReasonChange(row.index, v)"
          />
          <span v-else>{{ row.reason || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 勾稽校验状态（与明细表对比） ═══ -->
    <div class="cross-check-section">
      <div class="cross-check-row">
        <span class="cross-check-label">审定表期末未审合计 vs 明细表 L1-2 期末合计：</span>
        <span :class="crossCheckClass">
          <template v-if="crossCheckResult.isMatch">✓ 匹配</template>
          <template v-else>✗ 差额 {{ fmtAmount(crossCheckResult.diff) }}</template>
        </span>
      </div>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计说明</span>
          <el-button
            v-if="!isReadonly" size="small" type="primary" plain
            :loading="aiNoteLoading" @click="handleAiNote"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="note" type="textarea" :autosize="{ minRows: 5 }"
        :disabled="isReadonly" :placeholder="NOTE_PLACEHOLDER" @input="onNoteInput"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计结论</span>
          <el-button
            v-if="!isReadonly" size="small" type="primary" plain
            :loading="aiConclusionLoading" @click="handleAiConclusion"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="参考：A.未见异常。 B.除上述重大不符事项应作为调整事项予以调整外，其余未见异常。 C.由于存在重大未调整事项（或审计范围受限无法获取充分适当证据），不可确认。"
        @input="onConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>双期结构</strong>：期初数/期末数各含未审数、账项调整、重分类调整、审定数；审定数 = 未审 + 账项调整 + 重分类调整</li>
        <li><strong>分类</strong>：按信用/抵押/保证/质押四种借款类型分类汇总（对齐源模板顺序）</li>
        <li><strong>带入</strong>：可从明细表 L1-2 按借款种类 SUMIF 聚合带入期初/期末未审数</li>
        <li><strong>变动分析</strong>：变动率超 30% 需在原因分析栏说明</li>
        <li><strong>勾稽</strong>：审定表期末未审合计应与明细表 L1-2 各行期末余额合计一致</li>
        <li><strong>TB回写</strong>：期末审定合计自动回写试算平衡表科目 2001</li>
        <li><strong>审计说明四要点</strong>：①期末较期初增减原因（比例超30%需说明）②已到期未偿还情况（贷款单位/金额/利率/用途/未偿原因/预计还款期/期后是否偿还/展期条件）③抵押质押财产情况④关联方保证抵押质押情况</li>
        <li><strong>带入调整</strong>：可从集中登记按科目 2001 拉取调整分录，逐笔分配到各分类行期末账项调整/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2001 短期借款"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabAdjudication — L1-1 短期借款审定表（双期结构，2026-07 复盘重建）
 *
 * 对齐致同源模板「审定表L1-1」：期初数/期末数各(未审/账项调整/重分类/审定)
 * + 本期未审较期初(变动额/率) + 本期审定较期初(变动额/率) + 原因分析。
 * - 审定数 = 未审 + 账项调整 + 重分类调整（公式列虚线下划线+tooltip）
 * - TB回写：期末审定合计变化 → writebackTB(2001) + EventBus 'substantive:adjudicated'
 * - 从 L1-2 明细带入 + 与 L1-2 期末合计交叉验证
 */
import { computed, inject, onMounted, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import type { useL1FormData } from '@/composables/useL1FormData'
import { useL1Adjudication } from '@/composables/useL1Adjudication'
import { useL1AiNote } from '@/composables/useL1AiNote'
import type { AdjudicationVsDetailResult } from '@/composables/useL1CrossSheet'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Composable ──────────────────────────────────────────────────────────────

const { computedCategories, total, updateCategory, updateReason, importFromDetail } =
  useL1Adjudication(formData)

// ─── 从集中登记带入调整（2001 短期借款，负债贷方；双列 endAje/endRje） ───
const bringInRows = computed(() =>
  computedCategories.value.map((c, idx) => ({
    rowKey: String(idx),
    name: c.name,
    aje: c.endAje ?? 0,
    rje: c.endRje ?? 0,
  })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2001',
  direction: 'credit',
  subjectCode: '2001',
  wpCode: 'L1',
  subjectLabel: '短期借款(2001)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => {
    const idx = Number(rowKey)
    updateCategory(idx, field === 'aje' ? 'endAje' : 'endRje', value)
  },
  totalAudited: () => total.value.endAudited,
})

// ─── 从明细带入 ──────────────────────────────────────────────────────────────

async function handleImportFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将按借款种类从明细表 L1-2 聚合期初/期末未审数带入审定表，覆盖对应分类的未审数（账项调整/重分类调整保留）。是否继续？',
      '从 L1-2 明细带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
    const count = importFromDetail()
    if (count > 0) ElMessage.success(`已带入 ${count} 个分类`)
    else ElMessage.info('明细表暂无数据可带入')
  } catch { /* 取消 */ }
}

// ─── 审计说明 + 审计结论（AI 辅助） ─────────────────────────────────────────

const NOTE_PLACEHOLDER =
  '（1）短期借款期末余额较期初余额增加（负数为减少）：___，主要原因（比例超过30%的）：___\n' +
  '（2）已到期未偿还的短期借款情况说明（贷款单位、金额、利率、资金用途、未按期偿还原因及预计还款期，并在期后事项中反映报表日后是否已偿还；如获展期，说明展期条件、新到期日）。\n' +
  '（3）公司用于抵押、质押的财产情况说明。\n' +
  '（4）关联方保证、抵押或质押情况说明。'

const isReadonlyRef = toRef(props, 'isReadonly')
const {
  note, conclusion, aiNoteLoading, aiConclusionLoading,
  load: loadNote, onNoteInput, onConclusionInput, generateNote, generateConclusion,
} = useL1AiNote(formData, toRef(props, 'wpId'), 'adj', isReadonlyRef)

function _aiContext() {
  return {
    期末审定合计: total.value.endAudited,
    期初审定合计: total.value.beginAudited,
    变动额: total.value.auditedChange,
    变动率百分比: (total.value.auditedRate * 100).toFixed(2),
    分类明细: computedCategories.value.map(c => `${c.name}:期末审定${c.endAudited}`).join('；'),
  }
}

function handleAiNote() {
  generateNote(
    '请基于短期借款审定表数据，撰写审计说明，覆盖：①期末较期初增减及原因（比例超30%需重点说明）②已到期未偿还情况③抵押质押财产④关联方担保情况。',
    _aiContext(),
  )
}

function handleAiConclusion() {
  generateConclusion(
    '请基于短期借款审定情况生成审计结论，明确是否存在需调整事项及总体判断。',
    _aiContext(),
  )
}

onMounted(() => {
  loadNote()
})

// ─── Inject 勾稽校验 ─────────────────────────────────────────────────────────

const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

// ─── Table Data ──────────────────────────────────────────────────────────────

interface TableRow {
  label: string
  index: number
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  unadjChange: number
  unadjRate: number
  auditedChange: number
  auditedRate: number
  reason: string
  isEditable: boolean
  isTotal: boolean
}

const tableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = []
  computedCategories.value.forEach((cat, idx) => {
    rows.push({ ...cat, label: cat.name, index: idx, isEditable: true, isTotal: false })
  })
  const t = total.value
  rows.push({
    label: '合  计', index: -1,
    beginUnadjusted: t.beginUnadjusted, beginAje: t.beginAje, beginRje: t.beginRje, beginAudited: t.beginAudited,
    endUnadjusted: t.endUnadjusted, endAje: t.endAje, endRje: t.endRje, endAudited: t.endAudited,
    unadjChange: t.unadjChange, unadjRate: t.unadjRate, auditedChange: t.auditedChange, auditedRate: t.auditedRate,
    reason: '', isEditable: false, isTotal: true,
  })
  return rows
})

// ─── 勾稽校验结果 ────────────────────────────────────────────────────────────

const crossCheckResult = computed<AdjudicationVsDetailResult>(() => adjudicationVsDetail.value)
const crossCheckClass = computed(() => ({
  'cross-check-match': crossCheckResult.value.isMatch,
  'cross-check-diff': !crossCheckResult.value.isMatch,
}))

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: TableRow }): string {
  return row.isTotal ? 'total-row' : ''
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

type EditableField = 'beginUnadjusted' | 'beginAje' | 'beginRje'
  | 'endUnadjusted' | 'endAje' | 'endRje'

function handleCellChange(index: number, field: EditableField, value: number): void {
  if (index < 0) return
  updateCategory(index, field, value)
}

function handleReasonChange(index: number, value: string): void {
  if (index < 0) return
  updateReason(index, value)
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return `${(val * 100).toFixed(2)}%`
}

function changeClass(val: number): Record<string, boolean> {
  return { 'text-danger': val < 0, 'text-success': val > 0 }
}
</script>

<style scoped>
.l1-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.adj-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 审计目标 ─── */
.audit-objective {
  margin-bottom: 14px;
}

.ao-title {
  font-weight: 600;
}

.audit-objective :deep(.el-alert__content) {
  padding: 2px 0;
}

.ao-list {
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
  margin: 4px 0 0;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b45309;
}

/* ─── 公式列 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

.row-bold {
  font-weight: 700;
}

:deep(.total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 勾稽校验区 ─── */
.cross-check-section {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.cross-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.cross-check-label {
  color: #606266;
}

.cross-check-match {
  color: #67c23a;
  font-weight: 600;
}

.cross-check-diff {
  color: #f56c6c;
  font-weight: 600;
}

.text-danger { color: #f56c6c; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; font-weight: 600; }

/* ─── 审计说明/结论卡片 ─── */
.opinion-card {
  margin-top: 16px;
}

.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}

.opinion-card :deep(.el-textarea__inner) {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
