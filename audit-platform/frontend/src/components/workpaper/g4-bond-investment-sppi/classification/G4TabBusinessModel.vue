<template>
  <div class="g4-tab-business-model">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认管理债权投资的业务模式判断恰当（以收取合同现金流量为目标），作为金融资产分类计量的基础。"
      style="margin-bottom: 12px"
    />
    <!-- Section标题 + 复核按钮 -->
    <div class="section-header">
      <h3 class="section-title">G4-5 业务模式分析</h3>
      <div class="section-actions">
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-5业务模式分析')">复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p>确定管理债权投资的业务模式，以此为基础对债权投资进行分类。根据《企业会计准则第22号——金融工具确认和计量》（CAS22），企业应当在金融资产组合层次上确定管理金融资产的业务模式。</p>
    </div>

    <!-- ═══ (一) 以单一业务模式管理所有债权投资 ═══ -->
    <el-divider content-position="left">
      <span class="divider-title">(一) 以单一业务模式管理所有债权投资</span>
    </el-divider>

    <!-- 5道问卷 -->
    <div class="questionnaire-list">
      <div
        v-for="item in bm.questionnaire.value"
        :key="item.id"
        class="questionnaire-item"
      >
        <div class="question-row">
          <span class="question-seq">{{ item.seq }}.</span>
          <span class="question-text">{{ item.question }}</span>
          <el-radio-group
            :model-value="item.answer"
            :disabled="props.isReadonly"
            size="small"
            class="question-radio"
            @update:model-value="(val: boolean | null) => bm.setAnswer(item.id, val as boolean | null)"
          >
            <el-radio :value="true">是</el-radio>
            <el-radio :value="false">否</el-radio>
          </el-radio-group>
        </div>
        <div class="explanation-row">
          <el-input
            :model-value="item.explanation"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明（选填）"
            :disabled="props.isReadonly"
            @update:model-value="(val: string) => bm.setExplanation(item.id, val)"
          />
        </div>
      </div>
    </div>

    <!-- 审计评价 -->
    <div class="audit-evaluation">
      <label class="field-label">审计评价</label>
      <el-input
        :model-value="bm.auditEvaluation.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计评价..."
        :disabled="props.isReadonly"
        @update:model-value="bm.setAuditEvaluation"
      />
    </div>

    <!-- 结论chip区域 -->
    <div class="conclusion-area">
      <span class="conclusion-label">结论：</span>
      <el-tag
        :color="bm.conclusionChip.value.color"
        :type="bm.conclusionChip.value.type"
        size="large"
        effect="dark"
        round
      >
        {{ bm.conclusionChip.value.label }}
      </el-tag>
    </div>

    <!-- 跨组校验警告 -->
    <el-alert
      v-if="bm.crossCheckWarning.value"
      :title="bm.crossCheckWarning.value"
      type="warning"
      show-icon
      :closable="false"
      class="cross-check-warning"
    />

    <!-- ═══ (二) 将债权投资分拆为次级组合分别确定业务模式 ═══ -->
    <el-divider content-position="left">
      <span class="divider-title">(二) 将债权投资分拆为次级组合分别确定业务模式</span>
    </el-divider>

    <div class="sub-portfolio-toggle">
      <span class="field-label">适用性：</span>
      <el-radio-group
        :model-value="bm.hasSubPortfolios.value"
        :disabled="props.isReadonly"
        size="small"
        @update:model-value="(val: boolean) => bm.setHasSubPortfolios(val)"
      >
        <el-radio :value="true">是，需分拆为次级组合</el-radio>
        <el-radio :value="false">否，单一业务模式适用</el-radio>
      </el-radio-group>
    </div>

    <!-- 次级组合编辑区 -->
    <div v-if="bm.hasSubPortfolios.value" class="sub-portfolios-section">
      <div
        v-for="sp in bm.subPortfolios.value"
        :key="sp.id"
        class="sub-portfolio-card"
      >
        <el-card shadow="hover">
          <template #header>
            <div class="sp-card-header">
              <span class="sp-name">次级组合：{{ sp.name }}</span>
              <el-button
                v-if="!props.isReadonly"
                type="danger"
                size="small"
                text
                @click="bm.removeSubPortfolio(sp.id)"
              >
                删除
              </el-button>
            </div>
          </template>
          <!-- 重复5道问题 -->
          <div class="questionnaire-list">
            <div
              v-for="item in sp.questionnaire"
              :key="item.id"
              class="questionnaire-item"
            >
              <div class="question-row">
                <span class="question-seq">{{ item.seq }}.</span>
                <span class="question-text">{{ item.question }}</span>
                <el-radio-group
                  :model-value="item.answer"
                  :disabled="props.isReadonly"
                  size="small"
                  class="question-radio"
                  @update:model-value="(val: boolean | null) => bm.setSubAnswer(sp.id, item.id, val as boolean | null)"
                >
                  <el-radio :value="true">是</el-radio>
                  <el-radio :value="false">否</el-radio>
                </el-radio-group>
              </div>
              <div class="explanation-row">
                <el-input
                  :model-value="item.explanation"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="说明（选填）"
                  :disabled="props.isReadonly"
                  @update:model-value="(val: string) => bm.setSubExplanation(sp.id, item.id, val)"
                />
              </div>
            </div>
          </div>
          <!-- 次级组合结论chip -->
          <div class="conclusion-area sub-conclusion">
            <span class="conclusion-label">结论：</span>
            <el-tag
              :color="getChipStyle(sp.conclusion).color"
              :type="getChipStyle(sp.conclusion).type"
              size="default"
              effect="dark"
              round
            >
              {{ getChipStyle(sp.conclusion).label }}
            </el-tag>
          </div>
        </el-card>
      </div>

      <!-- 新增次级组合按钮 -->
      <el-button
        v-if="!props.isReadonly"
        type="primary"
        plain
        size="small"
        @click="bm.addSubPortfolio()"
      >
        + 新增次级组合
      </el-button>
    </div>

    <!-- ═══ 审计结论 ═══ -->
    <el-divider />
    <el-card shadow="never" class="audit-conclusion-card">
      <div class="section-header">
        <span class="field-label">审计结论</span>
        <div class="section-actions">
          <el-button size="small" type="primary" text>
            AI辅助
          </el-button>
        </div>
      </div>
      <el-input
        :model-value="bm.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入审计结论..."
        :disabled="props.isReadonly"
        @update:model-value="bm.setAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="preparation-tips">
      <summary>编制提示</summary>
      <div class="tips-content">
        <p>1. 根据CAS22第十七条，企业应在金融资产组合层次上确定管理金融资产的业务模式。</p>
        <p>2. 业务模式不取决于管理层对单项金融资产的意图，而应当以更高层次的角度确定。</p>
        <p>3. 评估业务模式时应考虑：历史出售频率/金额/原因/未来预期/绩效评价方式/组合管理方式。</p>
        <p>4. 当组合内存在不同业务模式管理的投资时，应将组合拆分为次级组合分别确定业务模式。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabBusinessModel.vue — G4-5 业务模式分析（完整实现）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 5.2
 * Requirements: 2.1~2.9, 9.1~9.6, 9.11
 *
 * 方法论上下文(琥珀色左边线+浅黄背景) + 5道问卷(是/否radio + 说明textarea autosize)
 * + 审计评价 + 结论chip(动态变色) + 次级组合(ElMessageBox.prompt新增)
 * + 审计结论textarea(AI按钮) + 编制提示details折叠
 */
import { inject, computed } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { useG4SppiBusinessModel, CONCLUSION_CHIP_MAP, type ConclusionChipStyle } from '@/composables/useG4SppiBusinessModel'
import type { BusinessModelResult } from '@/composables/useG4SppiFormulaEngine'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')

function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

// ─── 数据层 ─────────────────────────────────────────────────────────────────
const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// 加载数据
formData.loadAll()

// ─── 业务模式composable ─────────────────────────────────────────────────────
const bm = useG4SppiBusinessModel({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

// ─── chip样式helper ─────────────────────────────────────────────────────────
function getChipStyle(conclusion: BusinessModelResult): ConclusionChipStyle {
  return CONCLUSION_CHIP_MAP[conclusion]
}
</script>

<style scoped>
.g4-tab-business-model {
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.section-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* 方法论上下文：琥珀色左边线+浅黄背景 */
.methodology-context {
  border-left: 4px solid #E6A23C;
  background: #fdf6ec;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #856404;
}

.methodology-context p {
  margin: 0;
}

.divider-title {
  font-weight: 600;
  font-size: 14px;
}

/* 问卷列表 */
.questionnaire-list {
  margin-bottom: 16px;
}

.questionnaire-item {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.question-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.question-seq {
  font-weight: 600;
  color: #606266;
  min-width: 20px;
}

.question-text {
  flex: 1;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.question-radio {
  flex-shrink: 0;
}

.explanation-row {
  padding-left: 28px;
}

/* 审计评价 */
.audit-evaluation {
  margin-bottom: 16px;
}

.field-label {
  display: inline-block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* 结论区域 */
.conclusion-area {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}

.conclusion-area.sub-conclusion {
  margin-top: 12px;
  background: #f8f9fa;
}

.conclusion-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* 跨组校验警告 */
.cross-check-warning {
  margin-bottom: 16px;
}

/* 次级组合 */
.sub-portfolio-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.sub-portfolios-section {
  margin-bottom: 16px;
}

.sub-portfolio-card {
  margin-bottom: 12px;
}

.sp-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sp-name {
  font-weight: 600;
  font-size: 14px;
}

/* 审计结论 card */
.audit-conclusion-card {
  margin-bottom: 16px;
}

/* 编制提示 */
.preparation-tips {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #909399;
}

.preparation-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}

.tips-content {
  margin-top: 8px;
  line-height: 1.8;
}

.tips-content p {
  margin: 0;
}
</style>
