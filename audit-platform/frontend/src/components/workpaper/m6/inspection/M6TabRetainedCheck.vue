<template>
  <div class="m6-tab-retained-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M6-4 未分配利润检查表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>检查表目的：</strong>
        验证未分配利润期末余额的正确性，通过逐项核对利润分配结转链条（期初→+净利润→-盈余公积→-股利→=期末），
        并交叉验证M5盈余公积计提、M1应付股利宣告的一致性，确保M6作为利润分配结转枢纽的完整性与勾稽性。
        科目4104利润分配-未分配利润为<strong>权益类贷方科目</strong>（期末=期初+贷方-借方）。
      </div>
    </div>

    <!-- ═══ 进度摘要条 ═══ -->
    <div class="progress-summary-bar">
      <div class="progress-info">
        <span class="progress-label">核对进度：</span>
        <span class="progress-stats">
          <el-tag type="success" size="small" effect="plain">通过 {{ checkSummary.passed }}</el-tag>
          <el-tag v-if="checkSummary.failed > 0" type="danger" size="small" effect="plain">不通过 {{ checkSummary.failed }}</el-tag>
          <el-tag v-if="checkSummary.pending > 0" type="info" size="small" effect="plain">待核 {{ checkSummary.pending }}</el-tag>
          <span class="progress-total">/ {{ checkSummary.total }} 项</span>
        </span>
      </div>
      <el-progress
        :percentage="Math.round(checkSummary.passRate * 100)"
        :stroke-width="8"
        :color="progressColor"
        class="progress-bar"
      />
    </div>

    <!-- ═══ Section 1: 核对清单表格 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>核对清单</span>
          <div class="card-header-right">
            <el-button size="small" :loading="aiLoading === 'checklist'" :disabled="isReadonly" @click="handleAI('checklist')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="computedCheckItems"
        border
        size="small"
        class="check-table"
        row-class-name="check-table-row"
      >
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">
            {{ row.order }}
          </template>
        </el-table-column>

        <el-table-column label="检查项描述" min-width="260">
          <template #default="{ row }">
            <span class="check-description">{{ row.description }}</span>
            <el-tag
              v-if="row.category === 'cross-check'"
              type="warning"
              size="small"
              effect="plain"
              class="category-tag"
            >联动核对</el-tag>
            <el-tag
              v-else-if="row.category === 'tb-reconciliation'"
              type="primary"
              size="small"
              effect="plain"
              class="category-tag"
            >TB对账</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="M6值" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.m6Value !== null" class="amount-cell">{{ formatAmount(row.m6Value) }}</span>
            <span v-else class="no-value">—</span>
          </template>
        </el-table-column>

        <el-table-column label="来源值" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.sourceValue !== null" class="amount-cell">{{ formatAmount(row.sourceValue) }}</span>
            <span v-else class="no-value">—</span>
          </template>
        </el-table-column>

        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span
              v-if="row.diff !== null"
              :class="['diff-cell', { 'diff-danger': Math.abs(row.diff) >= 0.01 }]"
            >{{ formatAmount(row.diff) }}</span>
            <span v-else class="no-value">—</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              :type="statusTagType(row.status)"
              size="small"
              effect="dark"
            >{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="核对备注..."
              @change="(val: string) => updateCheckRemark(row.id, val)"
            />
            <span v-else class="remark-text">{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="来源" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip :value="row.sourceRef" :context-project-id="projectId" />
          </template>
        </el-table-column>
      </el-table>

      <!-- 手动核对项（非自动状态的项） -->
      <div v-if="manualCheckItems.length > 0 && !isReadonly" class="manual-check-section">
        <el-divider content-position="left">手动核对（非自动联动项）</el-divider>
        <div v-for="item in manualCheckItems" :key="item.id" class="manual-check-item">
          <span class="manual-check-label">{{ item.order }}. {{ item.description }}</span>
          <el-radio-group
            :model-value="item.status"
            size="small"
            @change="(val: string) => updateCheckStatus(item.id, val as any)"
          >
            <el-radio-button value="pass">通过</el-radio-button>
            <el-radio-button value="fail">不通过</el-radio-button>
            <el-radio-button value="pending">待核</el-radio-button>
          </el-radio-group>
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 2: 审计说明 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <div class="card-header-right">
            <el-button size="small" :loading="aiLoading === 'explanation'" :disabled="isReadonly" @click="handleAI('explanation')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-input
        :model-value="auditExplanation"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明利润分配结转核对过程、关注事项、不一致原因分析等..."
        @change="(val: string) => setAuditExplanation(val)"
      />
    </el-card>

    <!-- ═══ Section 3: 审计结论 ═══ -->
    <el-card shadow="never" class="check-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <div class="card-header-right">
            <el-button size="small" :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-section">
        <div class="conclusion-type-row">
          <span class="conclusion-type-label">结论类型：</span>
          <el-radio-group
            :model-value="conclusion.conclusionType"
            :disabled="isReadonly"
            size="small"
            @change="(val: string) => updateConclusion('conclusionType', val)"
          >
            <el-radio-button value="no-exception">无异常</el-radio-button>
            <el-radio-button value="exception-found">发现异常</el-radio-button>
            <el-radio-button value="pending">待定</el-radio-button>
          </el-radio-group>
          <el-tag
            v-if="isAllPassed && conclusion.conclusionType === 'pending'"
            type="success"
            size="small"
            effect="plain"
            class="recommend-tag"
          >推荐：无异常</el-tag>
        </div>

        <el-input
          :model-value="conclusion.conclusionText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :disabled="isReadonly"
          :placeholder="recommendedConclusion"
          @change="(val: string) => updateConclusion('conclusionText', val)"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>未分配利润（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（净利润转入） − 借方（分配减少）</li>
        <li><strong>利润分配结转核心公式链</strong>：期末未分配利润 = 期初 + 本年净利润 − 提取盈余公积 − 应付股利</li>
        <li><strong>M5联动</strong>：提取盈余公积金额应与M5实际计提数一致</li>
        <li><strong>M1联动</strong>：分配股利金额应与M1实际宣告数一致</li>
        <li><strong>结转公式链验证</strong>：期末=期初+净利润-盈余公积-股利 需逐项勾稽</li>
        <li><strong>TB对账</strong>：审定数应与试算表科目4104一致（回写）</li>
        <li>审定表(M6-1)期末应与明细表(M6-2)结转后期末相互验证</li>
        <li>如有前期差错更正/会计政策变更，需调整年初未分配利润</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabRetainedCheck — M6-4 未分配利润检查表
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 4.4
 * Requirements: 4.1-4.7, 5.1-5.2
 *
 * 功能：
 * - 核对清单表格：7项检查（分配结转链/跨底稿核对/TB对账）
 * - 每项：序号 | 检查项描述 | M6值 | 来源值 | 差异 | 状态(pass/fail/pending) | 备注 | 来源(GtIndexChip)
 * - Auto-status from useM6CrossSheet (surplusVsM5, dividendVsM1, adjudicationVsDetail)
 * - 进度摘要条 (passed/total)
 * - 审计说明 section (el-card, autosize textarea + AI button)
 * - 审计结论 section (el-card, conclusion type selector + text)
 * - AI辅助按钮在每个section标题行右侧
 * - inject openReviewDialog for section review
 * - 方法论上下文（琥珀色左边线）
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM6FormData } from '../../composables/useM6FormData'
import { useM6CrossSheet } from '../../composables/useM6CrossSheet'
import { useM6RetainedCheck, type CheckStatus } from '../../composables/useM6RetainedCheck'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>(
  'openReviewDialog',
  null,
)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData + CrossSheet ───────────────────────────────────────────────────

const formData = useM6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const crossSheet = useM6CrossSheet(formData.allResponses)

// ─── CrossCheck results ref (bridging to useM6RetainedCheck) ─────────────────

const crossCheckResults = computed(() => ({
  surplusVsM5: crossSheet.surplusVsM5.value,
  dividendVsM1: crossSheet.dividendVsM1.value,
  adjudicationVsDetail: crossSheet.adjudicationVsDetail.value,
}))

// ─── RetainedCheck composable ────────────────────────────────────────────────
// useM6RetainedCheck expects Ref<M6CrossCheckResults>; use computed as ref (ComputedRef is Ref)

const {
  computedCheckItems,
  checkSummary,
  isAllPassed,
  conclusion,
  recommendedConclusion,
  updateCheckStatus,
  updateCheckRemark,
  updateConclusion,
  loadFromResponses,
} = useM6RetainedCheck(formData, crossCheckResults as any)

// ─── 审计说明 ────────────────────────────────────────────────────────────────

const auditExplanation = ref('')

function setAuditExplanation(val: string) {
  auditExplanation.value = val
  formData.debouncedSave('M6-4-explanation', { remark: val || null })
}

// ─── Manual check items (non-auto items that need user radio input) ──────────

const manualCheckItems = computed(() =>
  computedCheckItems.value.filter(item =>
    !['chk-03', 'chk-04', 'chk-07'].includes(item.id),
  ),
)

// ─── Progress color ──────────────────────────────────────────────────────────

const progressColor = computed(() => {
  const rate = checkSummary.value.passRate
  if (rate >= 1) return '#67c23a'
  if (rate >= 0.7) return '#e6a23c'
  return '#909399'
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function formatAmount(value: number): string {
  if (value == null) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(status: CheckStatus): string {
  switch (status) {
    case 'pass': return 'success'
    case 'fail': return 'danger'
    case 'pending': return 'info'
    case 'not-applicable': return 'warning'
    default: return 'info'
  }
}

function statusLabel(status: CheckStatus): string {
  switch (status) {
    case 'pass': return '通过'
    case 'fail': return '不通过'
    case 'pending': return '待核'
    case 'not-applicable': return 'N/A'
    default: return '待核'
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const s = checkSummary.value
    const context: Record<string, string> = {
      科目: '4104 利润分配-未分配利润 / 检查表（M6-4）',
      核对项总数: String(s.total),
      通过: String(s.passed),
      不通过: String(s.failed),
      待核: String(s.pending),
      通过率: (s.passRate * 100).toFixed(1) + '%',
      结论类型: conclusion.value.conclusionType,
    }
    if (section === 'explanation') {
      const text = await generateAiText({ section: 'm6-check-explanation', context, existingContent: auditExplanation.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      setAuditExplanation(text)
      return
    }
    if (section === 'conclusion') {
      const text = await generateAiText({ section: 'm6-check-conclusion', context, existingContent: conclusion.value.conclusionText })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      updateConclusion('conclusionText', text)
      return
    }
    // checklist 无对应文本区 → 弹窗展示建议
    const text = await generateAiText({ section: `m6-check-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M6-4-retained-check', '未分配利润检查表')
}

// ─── Restore ─────────────────────────────────────────────────────────────────

function _restoreData() {
  // 从 allResponses 恢复检查表数据
  loadFromResponses(formData.allResponses.value)

  // 恢复审计说明
  const explanationResp = formData.allResponses.value.get('M6-4-explanation')
  if (explanationResp?.remark) auditExplanation.value = explanationResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
})
</script>

<style scoped>
.m6-tab-retained-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 标题栏 ──── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
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

.equity-badge {
  font-weight: 600;
}

/* ─── 方法论上下文（琥珀色左边线） ──── */
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

/* ─── 进度摘要条 ──── */
.progress-summary-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 16px;
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.progress-label {
  font-weight: 500;
  color: #303133;
}

.progress-stats {
  display: flex;
  align-items: center;
  gap: 6px;
}

.progress-total {
  color: #909399;
  font-size: 12px;
}

.progress-bar {
  flex: 1;
  min-width: 120px;
}

/* ─── Card 共用 ──── */
.check-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #303133;
}

.card-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 核对清单表格 ──── */
.check-table {
  font-size: var(--wp-font-size, 13px);
}

.check-table :deep(.el-table__header th) {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

.check-description {
  color: #303133;
  line-height: 1.5;
}

.category-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.amount-cell {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 12px;
  color: #303133;
}

.no-value {
  color: #c0c4cc;
}

.diff-cell {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 12px;
  color: #67c23a;
}

.diff-danger {
  color: #f56c6c;
  font-weight: 600;
}

.remark-text {
  color: #606266;
  font-size: 12px;
}

/* ─── 手动核对区 ──── */
.manual-check-section {
  margin-top: 16px;
}

.manual-check-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f2f6fc;
}

.manual-check-item:last-child {
  border-bottom: none;
}

.manual-check-label {
  flex: 1;
  color: #606266;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.5;
}

/* ─── 审计结论 ──── */
.conclusion-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conclusion-type-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.conclusion-type-label {
  font-weight: 500;
  color: #303133;
  flex-shrink: 0;
}

.recommend-tag {
  margin-left: 8px;
}

/* ─── 编制提示 ──── */
.m6-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
