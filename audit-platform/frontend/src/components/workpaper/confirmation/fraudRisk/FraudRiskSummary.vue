<template>
  <div class="fraud-risk-summary">
    <div class="fraud-risk-summary__header">
      <h4 class="fraud-risk-summary__title">舞弊风险汇总评价</h4>
      <el-button
        v-if="!readonly"
        type="primary"
        size="small"
        plain
        :loading="aiLoading"
        @click="handleAiFill"
      >
        AI 智能填充
      </el-button>
    </div>

    <!-- 财务报表层次 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">财务报表层次舞弊风险评价</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.statement_level_risk"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请评价财务报表层次的舞弊风险（如：是否存在管理层凌驾内控之上的系统性风险）"
        @change="(val: string) => $emit('update', 'statement_level_risk', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.statement_level_risk || '—' }}
      </p>
    </div>

    <!-- 认定层次 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">认定层次舞弊风险评价</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.assertion_level_risk"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请评价认定层次的舞弊风险（如：收入确认认定中是否存在通过虚构交易高估收入的风险）"
        @change="(val: string) => $emit('update', 'assertion_level_risk', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.assertion_level_risk || '—' }}
      </p>
    </div>

    <!-- 初步应对 -->
    <div class="fraud-risk-summary__section">
      <label class="fraud-risk-summary__label">初步应对措施</label>
      <el-input
        v-if="!readonly"
        :model-value="summary.initial_response"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请描述初步应对措施（如：扩大函证范围/追加实质性程序/与治理层沟通等）"
        @change="(val: string) => $emit('update', 'initial_response', val)"
      />
      <p v-else class="fraud-risk-summary__text">
        {{ summary.initial_response || '—' }}
      </p>
    </div>

    <!-- B50 跳转 -->
    <div class="fraud-risk-summary__section fraud-risk-summary__jump">
      <el-button type="primary" text @click="$emit('jump-b50')">
        → 跳转 B50 风险评估底稿
      </el-button>
      <span class="fraud-risk-summary__hint">
        （舞弊风险评价结果应同步更新至 B50 整体风险评估）
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FraudRiskSummary, FraudRiskMetrics } from './fraudRiskTypes'

const props = defineProps<{
  summary: FraudRiskSummary
  readonly: boolean
  /** 从父组件传入的看板指标 */
  metrics?: FraudRiskMetrics
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: string): void
  (e: 'jump-b50'): void
}>()

const aiLoading = ref(false)

function handleAiFill() {
  aiLoading.value = true
  try {
    const m = props.metrics
    const total = m?.total_count ?? 0
    const existCount = m?.exist_count ?? 0
    const withMeasure = m?.with_measure_count ?? 0
    const withoutMeasure = m?.without_measure_count ?? 0

    // 财务报表层次
    let statementRisk = ''
    if (existCount === 0) {
      statementRisk = '经对函证程序全过程中的 19 项舞弊风险迹象逐项评估，未发现与财务报表层次舞弊相关的风险因素。管理层未表现出凌驾内部控制之上的迹象，函证程序执行过程中未受到不当干预。'
    } else if (existCount <= 3) {
      statementRisk = `经评估，共识别 ${existCount} 项舞弊风险迹象。目前尚未发现系统性的财务报表层次舞弊风险，已识别的迹象主要集中于个别交易或认定层次，需通过追加实质性程序予以应对。`
    } else {
      statementRisk = `经评估，共识别 ${existCount} 项舞弊风险迹象，数量较多。需警惕是否存在财务报表层次的系统性舞弊风险（如管理层串通、内控整体失效）。建议与合伙人沟通并考虑修改整体审计策略。`
    }

    // 认定层次
    let assertionRisk = ''
    if (existCount === 0) {
      assertionRisk = '函证程序未揭示认定层次的舞弊风险。收入确认、应收/应付款项的存在性和完整性认定未发现异常。'
    } else {
      assertionRisk = `已识别的 ${existCount} 项风险迹象可能影响以下认定：收入确认的发生认定（虚构交易风险）、应收账款的存在性认定（虚假客户/空转贸易）。已对 ${withMeasure} 项制定了应对措施。`
    }

    // 初步应对
    let response = ''
    if (existCount === 0) {
      response = '维持原有审计计划和样本量，无需追加程序。'
    } else if (withoutMeasure > 0) {
      response = `尚有 ${withoutMeasure} 项已识别风险未制定应对措施，请补充完善。初步建议：扩大函证范围或追加替代程序、与治理层/管理层沟通已识别的风险迹象、评估是否需要修改审计报告意见类型。`
    } else {
      response = `已对全部 ${existCount} 项风险迹象制定应对措施。主要措施包括：扩大检查范围、追加实质性分析程序、与管理层沟通确认相关事项。建议将评价结果同步更新至 B50 风险评估底稿。`
    }

    // 仅填充空白字段
    if (!props.summary.statement_level_risk) emit('update', 'statement_level_risk', statementRisk)
    if (!props.summary.assertion_level_risk) emit('update', 'assertion_level_risk', assertionRisk)
    if (!props.summary.initial_response) emit('update', 'initial_response', response)

    ElMessage.success('已根据检查清单统计数据生成汇总评价（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.fraud-risk-summary {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 16px;
  margin-top: 12px;
}

.fraud-risk-summary__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.fraud-risk-summary__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.fraud-risk-summary__section {
  margin-bottom: 12px;
}

.fraud-risk-summary__section:last-child {
  margin-bottom: 0;
}

.fraud-risk-summary__label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.fraud-risk-summary__text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
  padding: 4px 0;
}

.fraud-risk-summary__jump {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.fraud-risk-summary__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
