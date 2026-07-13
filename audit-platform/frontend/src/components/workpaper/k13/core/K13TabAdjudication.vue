<template>
  <div class="k13-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的营业外支出（罚没支出/捐赠/非流动资产毁损报废损失等）确已发生；</li>
        <li><b>完整性：</b>所有应确认的营业外支出均已记录，不存在漏记或跨期；</li>
        <li><b>准确性：</b>营业外支出金额计算准确、与支持性文件一致；</li>
        <li><b>分类与列报：</b>分类恰当、列报披露充分，关注税前扣除性（捐赠/罚款等）。</li>
      </ol>
    </el-alert>

    <!-- ═══ 跨底稿引用（GtIndexChip：K13-1 → TB） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-3" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="k13-methodology-ctx">
      <p><strong>营业外支出(6711)</strong>：与日常经营活动无关的各项损失，包括非流动资产处置损失、债务重组损失、资产盘亏损失、捐赠支出、罚款滞纳金等。损益类借方科目，取发生额非余额。</p>
      <p>审定数 = 未审数 + AJE + RJE。同比变动率 = (本期审定 − 上期审定) ÷ |上期审定|。</p>
    </div>

    <!-- ═══ 损益类科目公式提示 ═══ -->
    <div class="k13-formula-badge">
      <span>⚠️ 损益类借方科目6711：发生额 = 借方发生（支出增加）− 贷方发生（冲回）</span>
    </div>

    <!-- ═══ 审定表 section ═══ -->
    <el-card shadow="never" class="k13-section-card">
      <template #header>
        <div class="section-header">
          <div class="section-title-group">
            <span class="section-title">营业外支出审定表 K13-1</span>
            <el-tag type="warning" size="small" class="expense-tag">损益类·借方·发生额</el-tag>
            <!-- 交叉验证badge -->
            <el-tag
              v-if="!adjudication.detailCrossValidation.value.isBalanced"
              type="danger"
              size="small"
              effect="dark"
              class="cv-badge"
            >
              ⚠ K13-1 vs K13-2 差异 {{ fmtAmt(adjudication.detailCrossValidation.value.diff) }}
            </el-tag>
            <el-tag
              v-else
              type="success"
              size="small"
              class="cv-badge"
            >
              ✓ K13-1 = K13-2
            </el-tag>
          </div>
          <div class="section-actions">
            <el-button size="small" @click="handleAI('adjudication')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="handleReview">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="adjudication.rows.value"
        border
        size="small"
        show-summary
        :summary-method="getSummaries"
        style="width: 100%"
        highlight-current-row
        class="adjudication-table"
      >
        <!-- 项目名称 -->
        <el-table-column prop="name" label="项目（去向）" min-width="140" fixed>
          <template #default="{ row }">
            <span class="category-cell">{{ row.name }}</span>
          </template>
        </el-table-column>

        <!-- 本期未审 -->
        <el-table-column prop="unadjusted" label="本期未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.unadjusted"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'unadjusted', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.unadjusted < 0 }]">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column prop="aje" label="AJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.aje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'aje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.aje < 0 }]">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column prop="rje" label="RJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.rje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'rje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.rje < 0 }]">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数（公式列） -->
        <el-table-column prop="audited" label="审定数" min-width="115" align="right">
          <template #header>
            <el-tooltip content="公式：审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="审定数 = 本期未审 + AJE + RJE" placement="top">
              <span class="formula-value">{{ fmtAmt(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 上期未审 -->
        <el-table-column prop="priorUnadj" label="上期未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorUnadj"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorUnadj', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorUnadj < 0 }]">{{ fmtAmt(row.priorUnadj) }}</span>
          </template>
        </el-table-column>

        <!-- 上期AJE -->
        <el-table-column prop="priorAje" label="上期AJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorAje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorAje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorAje < 0 }]">{{ fmtAmt(row.priorAje) }}</span>
          </template>
        </el-table-column>

        <!-- 上期RJE -->
        <el-table-column prop="priorRje" label="上期RJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorRje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorRje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorRje < 0 }]">{{ fmtAmt(row.priorRje) }}</span>
          </template>
        </el-table-column>

        <!-- 上期审定（公式列） -->
        <el-table-column prop="priorAudited" label="上期审定" min-width="115" align="right">
          <template #header>
            <el-tooltip content="公式：上期审定 = 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-col">上期审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="上期审定 = 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-value">{{ fmtAmt(row.priorAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 同比变动（公式列） -->
        <el-table-column prop="yoyChange" label="同比变动" min-width="90" align="right">
          <template #header>
            <el-tooltip content="公式：同比变动 = (本期审定 − 上期审定) ÷ |上期审定|" placement="top">
              <span class="formula-col">同比变动</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="(本期审定 − 上期审定) ÷ |上期审定|" placement="top">
              <span :class="['formula-value', { negative: row.yoyChange != null && row.yoyChange < 0 }]">
                {{ fmtPercent(row.yoyChange) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly && row.isEditable"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
              @change="adjudication.updateCell(row.rowKey, 'remark', row.remark)"
            />
            <span v-else class="cell-value">{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ TB回写操作栏 ═══ -->
    <div class="k13-action-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="props.isReadonly"
        :loading="writebackLoading"
        @click="handleWritebackTB"
      >
        回写审定数 → TB(6711发生额)
      </el-button>
      <span class="tb-info">
        TB未审发生额：{{ fmtAmt(props.tbData.unadjusted6711) }}　|　
        TB审定发生额：{{ fmtAmt(props.tbData.audited6711) }}
      </span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="k13-section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计说明</span>
          <div class="section-actions">
            <el-button size="small" link type="primary" @click="handleAI('note')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请输入审计说明（变动原因分析、特殊事项说明等）..."
        :disabled="props.isReadonly"
        @blur="handleNoteSave"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="k13-section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button size="small" link type="primary" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计结论..."
        :disabled="props.isReadonly"
        @blur="handleConclusionSave"
      />
    </el-card>

    <!-- ═══ 编制提示（details折叠） ═══ -->
    <details class="k13-tips-details">
      <summary>编制提示</summary>
      <ul class="tips-list">
        <li>营业外支出为损益类借方科目(6711)，取发生额（借方-贷方），非期末余额</li>
        <li>审定数 = 未审数 + AJE + RJE，同比变动 = (本期-上期)/|上期|</li>
        <li>K13-1审定合计应与K13-2明细合计一致，差异时显示红色告警badge</li>
        <li>回写操作将审定发生额写入试算表科目6711</li>
        <li>注意核查税前扣除性：捐赠支出(12%限额)、罚款滞纳金(不可扣除)等</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabAdjudication.vue — K13-1 营业外支出审定表
 *
 * 损益类！取发生额非余额（6711借方科目）
 * 按去向分行：非流动资产处置损失/债务重组损失/资产盘亏损失/捐赠支出/罚款滞纳金/其他
 * GtIndexChip跨底稿引用：K13-1 → TB(试算表) / K13-2(明细) / K13-3(调整)
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 4.2
 * Requirements: 2.1-2.7
 */
import { ref, inject, defineAsyncComponent, watch, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useK13Adjudication } from '../../composables/useK13Adjudication'
import { eventBus } from '@/utils/eventBus'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6711: number; audited6711: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = ref(props.allResponses)

// 监听 props 变化（shallow）
watch(() => props.allResponses, (val) => { allResponsesRef.value = val }, { immediate: true })

const adjudication = useK13Adjudication({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as any,
  wpId: toRef(props, 'wpId') as any,
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId: string, value: any) => emit('save', itemId, value),
  writebackTB: handleWritebackTBInternal,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackLoading = ref(false)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined | null): string {
  if (val == null || isNaN(val as number) || val === 0) return '—'
  return (val as number).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: any) {
  const sums: string[] = []
  const t = adjudication.totalRow.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合  计'; return }
    const map: Record<string, number | null> = {
      unadjusted: t.unadjusted,
      aje: t.aje,
      rje: t.rje,
      audited: t.audited,
      priorUnadj: t.priorUnadj,
      priorAje: t.priorAje,
      priorRje: t.priorRje,
      priorAudited: t.priorAudited,
      yoyChange: t.yoyChange,
    }
    const prop = col.property
    if (prop === 'yoyChange') {
      sums[i] = fmtPercent(t.yoyChange)
    } else if (prop && map[prop] !== undefined) {
      sums[i] = fmtAmt(map[prop] as number)
    } else {
      sums[i] = ''
    }
  })
  return sums
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────

async function handleWritebackTBInternal(auditedAmount: number): Promise<void> {
  // 发布 EventBus 'substantive:adjudicated'
  eventBus.emit('substantive:adjudicated', {
    accountCode: '6711',
    auditedAmount,
    wpCode: 'K13',
    type: 'occurrence_amount', // 标识：发生额回写（损益类）
    timestamp: Date.now(),
  })
  ElMessage.success('审定数已回写试算表（科目6711发生额）')
}

async function handleWritebackTB(): Promise<void> {
  writebackLoading.value = true
  try {
    await adjudication.writeback()
  } catch (err: any) {
    ElMessage.error(`回写失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

function handleNoteSave(): void {
  adjudication.saveNote(adjudication.auditNote.value)
}

function handleConclusionSave(): void {
  adjudication.saveConclusion(adjudication.auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAI(section: string): void {
  ElMessage.info(`AI辅助分析营业外支出${section}数据...`)
}

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog?.('K13-1-adjudication', '营业外支出审定表')
}
</script>

<style scoped>
.k13-tab-adjudication {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ─── 跨底稿引用栏 ─── */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.cross-refs-label {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.k13-methodology-ctx {
  padding: 10px 14px;
  background: #fffbe6;
  border-left: 4px solid #e6a23c;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.7;
}
.k13-methodology-ctx p {
  margin: 0 0 4px;
}
.k13-methodology-ctx p:last-child {
  margin-bottom: 0;
}

/* ─── 公式提示badge ─── */
.k13-formula-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  font-size: 12px;
  color: #e6a23c;
}

/* ─── Section card ─── */
.k13-section-card {
  margin: 0;
}
.k13-section-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: #fafbfc;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.expense-tag {
  font-size: 11px;
}
.cv-badge {
  font-size: 11px;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ─── 审定表样式 ─── */
.adjudication-table {
  font-size: var(--wp-font-size, 13px);
}
.adjudication-table :deep(.el-table__header th) {
  font-size: 12px;
  background: #f8f9fb;
}
.adjudication-table :deep(.el-table__footer td) {
  font-weight: 600;
  background: #f0f4ff;
}

/* 公式列样式：虚线下划线 + cursor:help + tooltip */
.formula-col {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #409eff;
  font-weight: 500;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #303133;
  display: inline-block;
  padding: 0 2px;
}

.category-cell {
  font-weight: 500;
  color: #303133;
}

.cell-input {
  width: 100%;
}
.cell-input :deep(.el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-value {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.cell-value.negative,
.formula-value.negative {
  color: #f56c6c;
}

/* ─── 操作栏 ─── */
.k13-action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 6px;
  border: 1px solid #d9ecff;
}
.tb-info {
  font-size: 12px;
  color: #909399;
}

/* ─── 编制提示 ─── */
.k13-tips-details {
  font-size: 12px;
  color: #909399;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}
.k13-tips-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
  margin-bottom: 4px;
}
.tips-list {
  margin: 6px 0 0 16px;
  padding: 0;
  line-height: 1.8;
}
.tips-list li {
  margin: 2px 0;
}
</style>
