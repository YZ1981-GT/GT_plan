<template>
  <div class="m10-classification-check" data-testid="m10-classification-check">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <strong>CAS37核心判定：</strong>发行方是否存在交付现金/其他金融资产的合同义务。
      无合同义务→权益工具(4003)；有合同义务→金融负债(负债科目)。
    </div>

    <!-- ═══ 引导步骤（蓝色渐变引导区） ═══ -->
    <div class="guide-steps">
      <div class="guide-step">
        <span class="step-num">1</span>
        <span class="step-text">选择待判定工具</span>
      </div>
      <span class="step-arrow">→</span>
      <div class="guide-step">
        <span class="step-num">2</span>
        <span class="step-text">逐维度判定</span>
      </div>
      <span class="step-arrow">→</span>
      <div class="guide-step">
        <span class="step-num">3</span>
        <span class="step-text">确认分类结论</span>
      </div>
      <span class="step-arrow">→</span>
      <div class="guide-step">
        <span class="step-num">4</span>
        <span class="step-text">金额拆分(如需)</span>
      </div>
    </div>

    <!-- ═══ 标题栏 + 工具按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">M10-4 负债与权益区分检查表（CAS37核心）</h3>
        <el-tag type="warning" effect="dark" size="small">
          {{ cc.computedJudgments.value.length }} 项工具
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :disabled="isReadonly" @click="handleAI('overall')">
          🤖 AI辅助
        </el-button>
        <GtReviewTrigger section-id="M10-4-classification" />
      </div>
    </div>

    <!-- ═══ 负债警告卡片 ═══ -->
    <el-alert
      v-for="warn in cc.liabilityWarnings.value"
      :key="warn.instrumentKey"
      type="warning"
      :closable="false"
      show-icon
      class="liability-alert"
    >
      <template #title>⚠️ 应计入负债科目而非权益</template>
      <span>{{ warn.message }}</span>
    </el-alert>

    <!-- ═══ 金额不守恒警告 ═══ -->
    <el-alert
      v-for="item in cc.inconsistentItems.value"
      :key="'inconsist-' + item.instrumentKey"
      type="error"
      :closable="false"
      show-icon
      class="inconsistent-alert"
    >
      <template #title>❌ 权益+负债≠总额</template>
      <span>"{{ item.instrumentName }}" 权益部分({{ fmtAmount(item.equityAmount) }}) + 负债部分({{ fmtAmount(item.liabilityAmount) }}) ≠ 总额({{ fmtAmount(item.totalAmount) }})</span>
    </el-alert>

    <!-- ═══ 逐工具判定区域 ═══ -->
    <div v-if="cc.computedJudgments.value.length === 0" class="empty-hint">
      <el-empty description="暂无待判定工具，请先在M10-2明细表中录入工具信息" />
    </div>

    <el-collapse v-else v-model="expandedInstruments" class="instrument-collapse">
      <el-collapse-item
        v-for="instrument in cc.computedJudgments.value"
        :key="instrument.instrumentKey"
        :name="instrument.instrumentKey"
      >
        <template #title>
          <div class="instrument-title">
            <span class="instrument-name">{{ instrument.instrumentName || '未命名工具' }}</span>
            <el-tag
              v-if="instrument.classification === 'equity'"
              type="success" size="small" effect="plain"
            >权益</el-tag>
            <el-tag
              v-else-if="instrument.classification === 'liability'"
              type="danger" size="small" effect="plain"
            >负债</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">待判定</el-tag>
            <span class="instrument-amount">总额: {{ fmtAmount(instrument.totalAmount) }}</span>
            <el-icon v-if="!instrument.isConsistent" color="#F56C6C"><WarningFilled /></el-icon>
          </div>
        </template>

        <!-- 7维度判定表 -->
        <div class="dimension-section">
          <div
            v-for="dim in JUDGMENT_DIMENSIONS_DISPLAY"
            :key="dim.key"
            class="dimension-row"
          >
            <div class="dimension-header">
              <span class="dimension-label">{{ dim.label }}</span>
              <el-button
                size="small" text :disabled="isReadonly"
                @click="handleAI(dim.key + '-' + instrument.instrumentKey)"
              >🤖</el-button>
            </div>
            <div class="dimension-body">
              <el-radio-group
                :model-value="instrument.dimensions[dim.key] || ''"
                :disabled="isReadonly"
                size="small"
                @change="(val: any) => cc.updateDimension(instrument.instrumentKey, dim.key, val)"
              >
                <el-radio-button value="yes">是</el-radio-button>
                <el-radio-button value="no">否</el-radio-button>
                <el-radio-button value="na">不适用</el-radio-button>
              </el-radio-group>
              <el-input
                :model-value="getDimensionNote(instrument.instrumentKey, dim.key)"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                placeholder="审计师说明..."
                size="small"
                :disabled="isReadonly"
                class="dimension-note"
                @change="(val: string) => handleDimensionNote(instrument.instrumentKey, dim.key, val)"
              />
            </div>
          </div>
        </div>

        <!-- 自动推导分类结论 -->
        <div class="auto-classification">
          <div class="classification-result">
            <span class="classification-label">自动推导分类：</span>
            <el-tag
              v-if="instrument.classification === 'equity'"
              type="success" effect="dark" size="default"
            >权益工具 → 计入4003其他权益工具</el-tag>
            <el-tag
              v-else-if="instrument.classification === 'liability'"
              type="danger" effect="dark" size="default"
            >金融负债 → 应计入负债科目</el-tag>
            <el-tag v-else type="info" effect="plain" size="default">
              待完成判定维度
            </el-tag>
          </div>
          <div class="classification-rule">
            <el-text type="info" size="small">
              规则：本金义务=是 OR (利息义务=是 AND 递延权利≠是) → 金融负债；否则 → 权益工具
            </el-text>
          </div>
        </div>

        <!-- 金额拆分（复合工具） -->
        <div class="amount-split-section">
          <h4 class="split-title">金额拆分</h4>
          <div class="split-grid">
            <div class="split-item">
              <span class="split-label">工具总额</span>
              <span class="split-value">{{ fmtAmount(instrument.totalAmount) }}</span>
            </div>
            <div class="split-item">
              <span class="split-label">权益部分</span>
              <el-input-number
                v-if="!isReadonly && instrument.classification !== 'equity' && instrument.classification !== 'liability'"
                :model-value="instrument.equityAmount"
                :controls="false"
                :min="0"
                :max="instrument.totalAmount"
                size="small"
                style="width: 160px"
                @change="(val: number | undefined) => cc.updateEquityAmount(instrument.instrumentKey, val ?? 0)"
              />
              <span v-else class="split-value">{{ fmtAmount(instrument.equityAmount) }}</span>
            </div>
            <div class="split-item">
              <span class="split-label">负债部分</span>
              <span class="split-value">{{ fmtAmount(instrument.liabilityAmount) }}</span>
            </div>
            <div class="split-item consistency-indicator">
              <span class="split-label">守恒校验</span>
              <el-tag
                :type="instrument.isConsistent ? 'success' : 'danger'"
                size="small"
                effect="plain"
              >
                <el-icon v-if="instrument.isConsistent"><CircleCheck /></el-icon>
                <el-icon v-else><CircleClose /></el-icon>
                {{ instrument.isConsistent ? '一致' : '不一致' }}
              </el-tag>
            </div>
          </div>
        </div>

        <!-- 结论区 -->
        <el-card shadow="never" class="conclusion-card">
          <template #header>
            <div class="conclusion-head">
              <span>审计结论</span>
              <el-button
                size="small" :disabled="isReadonly"
                @click="handleAI('conclusion-' + instrument.instrumentKey)"
              >🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            :model-value="instrument.conclusion"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="填写该工具的分类审计结论..."
            :disabled="isReadonly"
            @change="(val: string) => cc.updateConclusion(instrument.instrumentKey, val)"
          />
        </el-card>

      </el-collapse-item>
    </el-collapse>

    <!-- ═══ 汇总仪表板 ═══ -->
    <el-card shadow="never" class="summary-dashboard" data-testid="m10-4-summary">
      <template #header>
        <div class="summary-head">
          <span>分类汇总</span>
          <el-tag
            :type="cc.summary.value.allConsistent ? 'success' : 'danger'"
            size="small" effect="dark"
          >
            {{ cc.summary.value.allConsistent ? '✓ 全部守恒' : '✗ 存在不一致' }}
          </el-tag>
        </div>
      </template>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">工具总数</span>
          <span class="summary-value">{{ cc.summary.value.totalInstruments }}</span>
        </div>
        <div class="summary-item equity-item">
          <span class="summary-label">权益工具</span>
          <span class="summary-value">{{ cc.summary.value.equityCount }} 项</span>
          <span class="summary-amount">{{ fmtAmount(cc.summary.value.totalEquityAmount) }}</span>
        </div>
        <div class="summary-item liability-item">
          <span class="summary-label">金融负债</span>
          <span class="summary-value">{{ cc.summary.value.liabilityCount }} 项</span>
          <span class="summary-amount">{{ fmtAmount(cc.summary.value.totalLiabilityAmount) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">待判定</span>
          <span class="summary-value">{{ cc.summary.value.pendingCount }} 项</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">合计</span>
          <span class="summary-amount">{{ fmtAmount(cc.summary.value.totalAmount) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">守恒状态</span>
          <el-icon v-if="cc.summary.value.allConsistent" color="#67C23A"><CircleCheck /></el-icon>
          <el-icon v-else color="#F56C6C"><CircleClose /></el-icon>
        </div>
      </div>
    </el-card>

    <!-- ═══ 综合审计结论 ═══ -->
    <el-card shadow="never" class="overall-conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>M10-4 综合审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAI('overall-conclusion')">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="综合CAS37负债权益区分结论..."
        :disabled="isReadonly"
        @change="handleOverallConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐项判定CAS37各维度：本金义务、利息义务、递延权利、或有结算、转股特征、清算优先、结算方式</li>
        <li>核心规则：有交付现金/金融资产的合同义务→金融负债，无→权益工具</li>
        <li>复合金融工具需手动拆分权益/负债部分金额，确保权益+负债=总额（金额守恒）</li>
        <li>判定为负债的工具应从M10(4003)转出至负债科目，并在明细表中标注</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabClassificationCheck.vue — M10-4 负债与权益区分检查表（CAS37核心！）
 *
 * 本组件是 M10 其他权益工具底稿中最重要的sheet。
 * 职责：逐工具 CAS37 七维度判定 → 自动推导分类（权益/负债）→ 金额拆分 → 守恒校验
 *
 * 功能：
 * - 逐工具7维度判定（radio: 是/否/不适用 + 审计师说明 textarea）
 * - 自动推导分类结论：principal=yes OR (interest=yes AND deferral≠yes) → liability
 * - 复合工具手动金额拆分（权益/负债部分）
 * - 金额守恒校验（green/red indicator）
 * - 负债警告卡片（黄色alert）
 * - 汇总仪表板（权益/负债数量+金额+守恒状态）
 * - AI辅助按钮（每个维度section + 结论）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.4
 * Requirements: 4.1-4.5
 */
import { ref, computed, onMounted, toRef } from 'vue'
import { CircleCheck, CircleClose, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import { useM10FormData } from '../../composables/useM10FormData'
import { useM10ClassificationCheck, M10_JUDGMENT_DIMENSIONS } from '../../composables/useM10ClassificationCheck'
import type { M10JudgmentDimension } from '../../composables/useM10ClassificationCheck'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const isReadonly = computed(() => !!props.isReadonly)

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM10FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetName: 'M10-4',
})

const cc = useM10ClassificationCheck(formData)

// ─── State ───────────────────────────────────────────────────────────────────

const expandedInstruments = ref<string[]>([])
const overallConclusion = ref('')
const dimensionNotes = ref<Map<string, string>>(new Map())

// ─── Constants ───────────────────────────────────────────────────────────────

/** 7判定维度（不含finalConclusion，它由自动推导） */
const JUDGMENT_DIMENSIONS_DISPLAY = M10_JUDGMENT_DIMENSIONS.filter(
  d => d.key !== 'finalConclusion',
)

// ─── Dimension notes ─────────────────────────────────────────────────────────

function getDimensionNote(instrumentKey: string, dimension: string): string {
  return dimensionNotes.value.get(`${instrumentKey}::${dimension}`) || ''
}

function handleDimensionNote(instrumentKey: string, dimension: string, val: string): void {
  const noteKey = `${instrumentKey}::${dimension}`
  dimensionNotes.value.set(noteKey, val)
  formData.debouncedSave(`M10-4-note-${instrumentKey}-${dimension}`, { remark: val })
}

// ─── Overall conclusion ──────────────────────────────────────────────────────

function handleOverallConclusionChange(val: string): void {
  overallConclusion.value = val
  formData.debouncedSave('M10-4-overall-conclusion', { remark: val })
}

// ─── AI assist (placeholder) ─────────────────────────────────────────────────

function handleAI(sectionId: string): void {
  ElMessage.info(`AI辅助分析：${sectionId}（功能开发中）`)
}

// ─── Load data ───────────────────────────────────────────────────────────────

async function loadData(): Promise<void> {
  await formData.loadData()

  // 恢复 overall conclusion
  const saved = formData.allResponses.value.get('M10-4-overall-conclusion')
  if (saved?.remark) {
    overallConclusion.value = saved.remark
  }

  // 恢复 dimension notes
  for (const [key, resp] of formData.allResponses.value) {
    if (key.startsWith('M10-4-note-') && resp.remark) {
      const noteKey = key.replace('M10-4-note-', '').replace('-', '::')
      dimensionNotes.value.set(noteKey, resp.remark)
    }
  }

  // 如果还没有工具，默认展开提示
  if (cc.computedJudgments.value.length > 0) {
    expandedInstruments.value = [cc.computedJudgments.value[0].instrumentKey]
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.m10-classification-check {
  font-size: var(--wp-font-size, 13px);
  padding: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.6;
}

/* ─── 引导步骤 ─── */
.guide-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%);
  border-radius: 6px;
  flex-wrap: wrap;
}
.guide-step {
  display: flex;
  align-items: center;
  gap: 6px;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.step-arrow {
  color: #909399;
  font-size: 14px;
}

/* ─── Section header ─── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
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
  gap: 6px;
}
.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

/* ─── Alerts ─── */
.liability-alert,
.inconsistent-alert {
  margin-bottom: 8px;
}

/* ─── Instrument collapse ─── */
.instrument-collapse {
  margin-bottom: 12px;
}
.instrument-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.instrument-name {
  font-weight: 600;
  font-size: 14px;
}
.instrument-amount {
  margin-left: auto;
  color: #606266;
  font-size: 12px;
}

/* ─── Dimension section ─── */
.dimension-section {
  padding: 8px 0;
}
.dimension-row {
  border-bottom: 1px solid #ebeef5;
  padding: 8px 0;
}
.dimension-row:last-child {
  border-bottom: none;
}
.dimension-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.dimension-label {
  font-weight: 500;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.dimension-body {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.dimension-note {
  flex: 1;
  min-width: 200px;
}

/* ─── Auto classification ─── */
.auto-classification {
  margin: 12px 0;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 4px;
}
.classification-result {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.classification-label {
  font-weight: 500;
}
.classification-rule {
  margin-top: 4px;
}

/* ─── Amount split ─── */
.amount-split-section {
  margin: 12px 0;
  padding: 10px 14px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.split-title {
  margin: 0 0 8px 0;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.split-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.split-label {
  font-size: 12px;
  color: #909399;
}
.split-value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.consistency-indicator {
  align-items: flex-start;
}

/* ─── Conclusion card ─── */
.conclusion-card {
  margin-top: 12px;
}
.conclusion-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.overall-conclusion-card {
  margin-top: 14px;
}

/* ─── Summary dashboard ─── */
.summary-dashboard {
  margin-top: 14px;
}
.summary-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 4px;
  background: #f5f7fa;
}
.summary-item.equity-item {
  background: #f0f9eb;
}
.summary-item.liability-item {
  background: #fef0f0;
}
.summary-label {
  font-size: 12px;
  color: #909399;
}
.summary-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.summary-amount {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

/* ─── Guidance ─── */
.guidance-details {
  margin-top: 12px;
  font-size: 12px;
  color: #606266;
}
.guidance-details ul {
  margin: 6px 0;
  padding-left: 18px;
}
.guidance-details li {
  margin-bottom: 4px;
}

/* ─── Empty hint ─── */
.empty-hint {
  padding: 32px 0;
}
</style>
