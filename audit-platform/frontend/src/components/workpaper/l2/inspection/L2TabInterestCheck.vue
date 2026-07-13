<template>
  <div class="l2-tab-interest-check">
    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>检查表目标：</strong>
        系统性核对应付利息计提的准确性与完整性。核对L1短期借款/L3长期借款利息测算与账面计提差异，
        逐项确认检查结果并记录审计说明。完成全部检查后撰写审计结论。
      </div>
    </div>

    <!-- ═══ 跨底稿引用导航（GtIndexChip） ═══ -->
    <div class="cross-wp-references">
      <span class="cross-wp-label">关联底稿：</span>
      <GtIndexChip
        v-for="ref in crossWpRefs"
        :key="ref.targetWpCode"
        :value="ref.targetWpCode"
        :context="ref.label"
        class="cross-wp-chip"
      />
    </div>

    <!-- ═══ 计提核对摘要指标 ═══ -->
    <div class="accrual-summary-bar">
      <div class="summary-indicator">
        <span class="indicator-label">L1/L3测算 vs L2账面计提：</span>
        <el-tag :type="accrualSummary.statusType" size="small" effect="plain">
          {{ accrualSummary.statusText }}
        </el-tag>
      </div>
      <div class="completion-progress">
        <span class="progress-label">完成进度：</span>
        <el-progress
          :percentage="completionStats.rate"
          :stroke-width="16"
          :format="() => `${completionStats.completed}/${completionStats.total}`"
          style="width: 140px"
        />
      </div>
    </div>

    <!-- ═══ 各section核对清单 ═══ -->
    <template v-for="sectionKey in sectionKeys" :key="sectionKey">
      <div class="check-section">
        <!-- Section标题行 + AI按钮 -->
        <div class="section-header">
          <h4 class="section-title">{{ sectionLabels[sectionKey] }}</h4>
          <el-button
            v-if="!isReadonly && sectionHasAi(sectionKey)"
            size="small"
            type="warning"
            plain
            @click="handleSectionAi(sectionKey)"
          >
            AI 辅助
          </el-button>
        </div>

        <!-- 检查项列表 -->
        <div
          v-for="item in sections[sectionKey]"
          :key="item.key"
          class="check-item"
        >
          <div class="check-item-header">
            <span class="check-title">{{ item.title }}</span>
            <el-select
              v-if="!isReadonly"
              :model-value="item.conclusion"
              size="small"
              placeholder="选择结论"
              style="width: 110px"
              @change="(val: string) => handleConclusionChange(item.key, val)"
            >
              <el-option label="通过" value="通过" />
              <el-option label="不通过" value="不通过" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <span v-else :class="getConclusionClass(item.conclusion)">
              {{ item.conclusion || '-' }}
            </span>
          </div>
          <el-input
            v-if="!isReadonly"
            :model-value="item.remark"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            size="small"
            placeholder="审计说明..."
            @input="(val: string) => handleRemarkInput(item.key, val)"
          />
          <span v-else class="remark-readonly">{{ item.remark || '' }}</span>
        </div>
      </div>
    </template>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-header-title">审计结论</span>
          <div class="conclusion-header-actions">
            <el-button
              v-if="openReviewDialog && !isReadonly"
              size="small"
              type="primary"
              plain
              @click="openReviewDialog('L2-4')"
            >
              复核
            </el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-body">
        <div class="conclusion-select-row">
          <span class="field-label">总体结论：</span>
          <el-select
            v-if="!isReadonly"
            :model-value="overallConclusion"
            size="small"
            placeholder="选择总体结论"
            style="width: 160px"
            @change="handleOverallConclusionChange"
          >
            <el-option label="通过" value="通过" />
            <el-option label="不通过" value="不通过" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <span v-else :class="getConclusionClass(overallConclusion)">
            {{ overallConclusion || '-' }}
          </span>
        </div>

        <el-input
          v-if="!isReadonly"
          :model-value="conclusionRemark"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="根据上述检查结果，对应付利息审计结论如下..."
          @input="handleConclusionRemarkInput"
        />
        <div v-else class="remark-readonly conclusion-remark-text">
          {{ conclusionRemark || '' }}
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>计提核对</strong>：核对L1短期借款/L3长期借款利息测算与账面计提差异，差异应在合理范围内</li>
        <li><strong>逾期分析</strong>：识别逾期未付利息，评估可收回性</li>
        <li><strong>完整性</strong>：确认所有借款合同的应付利息均已完整记录，截止日正确</li>
        <li><strong>准确性</strong>：验证利息公式（本金×利率×天数/365）和余额变动合理性</li>
        <li><strong>结论选项</strong>：通过/不通过/不适用</li>
        <li><strong>关联底稿</strong>：L1短期借款、L3长期借款、L8财务费用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabInterestCheck.vue — L2-4 应付利息检查表
 *
 * 计提核对清单（4 sections × 10 items）+ 审计结论区 + AI辅助
 * 与 useL2CrossSheet 联动显示 L1/L3 vs L2 计提一致性
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 4.4
 * Requirements: 5.1-5.2
 */
import { computed, inject, onMounted, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2CrossSheet } from '../../composables/useL2CrossSheet'
import { useL2InterestCheck, type CheckSection } from '../../composables/useL2InterestCheck'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sheetCode: string) => void) | null>('openReviewDialog', null)

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetName: 'L2-4',
})

const crossSheet = useL2CrossSheet(formData.allResponses)

/** 跨底稿引用（L1/L3/L8）— 用于 GtIndexChip 导航 */
const crossWpRefs = crossSheet.cross_wp_references

const {
  sections,
  sectionLabels,
  overallConclusion,
  conclusionRemark,
  accrualSummary,
  completionStats,
  updateConclusion,
  updateRemark,
  saveOverallConclusion,
  updateConclusionRemark,
} = useL2InterestCheck({
  allResponses: formData.allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  saveField: formData.saveField,
  debouncedSave: formData.debouncedSave,
  accrualVsL1L3: crossSheet.accrualVsL1L3,
  isInterestDataReady: crossSheet.isInterestDataReady,
})

// ─── Section keys (不含conclusion) ───────────────────────────────────────────

const sectionKeys = computed<CheckSection[]>(() => [
  'accrual-verification',
  'overdue-analysis',
  'completeness',
  'accuracy',
])

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 判断 section 是否包含 AI 辅助项 */
function sectionHasAi(sectionKey: CheckSection): boolean {
  const items = sections.value[sectionKey]
  return items?.some(item => item.hasAiAssist) ?? false
}

/** 结论文字样式 */
function getConclusionClass(conclusion: string): string {
  switch (conclusion) {
    case '通过': return 'conclusion-pass'
    case '不通过': return 'conclusion-fail'
    case '不适用': return 'conclusion-na'
    default: return 'conclusion-empty'
  }
}

// ─── Event Handlers ──────────────────────────────────────────────────────────

function handleConclusionChange(key: string, val: string): void {
  updateConclusion(key, val as any)
}

function handleRemarkInput(key: string, val: string): void {
  updateRemark(key, val)
}

function handleOverallConclusionChange(val: string): void {
  saveOverallConclusion(val)
}

function handleConclusionRemarkInput(val: string): void {
  updateConclusionRemark(val)
}

function handleSectionAi(sectionKey: CheckSection): void {
  const label = sectionLabels[sectionKey] || sectionKey
  import('@/utils/http').then(({ default: http }) => {
    http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l2-check-${sectionKey}`,
      prompt: `请基于"${label}"检查区的各项检查结果，给出审计分析建议`,
      context: {
        sectionKey,
        items: sections.value[sectionKey]?.map(i => ({ title: i.title, conclusion: i.conclusion, remark: i.remark })) || [],
        accrualStatus: accrualSummary.value.statusText,
      },
    }).then(res => {
      const content = res.data?.data?.content
      if (content) {
        // 填入该section第一个空remark项
        const emptyItem = sections.value[sectionKey]?.find(i => !i.remark)
        if (emptyItem) {
          updateRemark(emptyItem.key, content)
        }
        ElMessage.success(`${label} AI建议已生成`)
      }
    }).catch(() => {
      ElMessage.info(`${label} AI辅助暂不可用`)
    })
  })
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  formData.loadData()
})
</script>

<style scoped>
.l2-tab-interest-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 跨底稿引用导航 ─── */
.cross-wp-references {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #f0f5ff;
  border: 1px solid #d6e4ff;
  border-radius: 6px;
  margin-bottom: 14px;
}

.cross-wp-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.cross-wp-chip {
  margin-right: 4px;
}

/* ─── 计提核对摘要指标 ─── */
.accrual-summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 16px;
}

.summary-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.indicator-label {
  font-weight: 500;
  color: #606266;
}

.completion-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-label {
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

/* ─── Section ─── */
.check-section {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── Check item ─── */
.check-item {
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #fafbfc;
  border: 1px solid #f0f2f5;
  border-radius: 6px;
}

.check-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  gap: 12px;
}

.check-title {
  flex: 1;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  line-height: 1.5;
}

.remark-readonly {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

/* ─── Conclusion styles ─── */
.conclusion-pass {
  color: #67c23a;
  font-weight: 600;
}

.conclusion-fail {
  color: #f56c6c;
  font-weight: 600;
}

.conclusion-na {
  color: #909399;
}

.conclusion-empty {
  color: #c0c4cc;
}

/* ─── 审计结论卡片 ─── */
.conclusion-card {
  margin-top: 20px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.conclusion-header-title {
  font-weight: 600;
  font-size: 14px;
}

.conclusion-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.conclusion-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conclusion-select-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.field-label {
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.conclusion-remark-text {
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  line-height: 1.7;
  min-height: 60px;
}

/* ─── 编制提示折叠 ─── */
.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
