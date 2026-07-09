<!--
  K1TabPolicyCheck.vue — K1-6 信用减值损失会计政策检查

  段落型检查: ECL模型选择/账龄组合划分/预期损失率确定依据/前瞻性调整
  AI辅助 per-section + 琥珀色方法论

  Spec: .kiro/specs/k1-other-receivables/ Task 4.6
  Requirements: 9.1-9.2
-->
<template>
  <div class="k1-tab-policy-check">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-6检查企业信用减值损失会计政策是否符合CAS 22要求。重点关注：①ECL模型选择是否恰当
        ②账龄组合划分是否合理 ③预期损失率确定依据是否充分 ④是否考虑前瞻性信息调整。
        各section逐项检查并记录审计证据。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-6 信用减值损失会计政策检查</h3>
      <div class="head-actions">
        <el-button size="small" @click="handleReview('K1-6-policy')">💬 复核</el-button>
      </div>
    </div>

    <!-- 各检查段落 -->
    <div v-for="section in policySections" :key="section.id" class="policy-section">
      <div class="policy-section-head">
        <h4 class="policy-section-title">{{ section.label }}</h4>
        <el-button size="small" type="primary" link @click="handleAiGenerate(section.id)">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
      </div>
      <p class="policy-section-desc">{{ section.description }}</p>

      <el-input
        v-if="!isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :model-value="getSectionContent(section.id)"
        :placeholder="section.placeholder"
        @change="(v: string) => handleSectionChange(section.id, v)"
      />
      <div v-else class="readonly-content">
        {{ getSectionContent(section.id) || '（未填写）' }}
      </div>
    </div>

    <!-- 综合政策结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span class="conclusion-title">政策检查结论</span>
      </template>
      <el-input
        v-if="!isReadonly"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :model-value="conclusion"
        placeholder="请填写会计政策检查综合结论"
        @change="handleConclusionChange"
      />
      <div v-else class="readonly-content">{{ conclusion || '（未填写）' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>ECL模型选择：一般模型(三阶段) or 简化模型(始终按整个存续期ECL)</li>
        <li>账龄组合：检查是否以账龄为唯一分组因素，是否考虑其他信用风险特征</li>
        <li>损失率：确定依据应基于历史违约数据+前瞻性信息+个别评估</li>
        <li>前瞻性调整：宏观经济、行业趋势、债务人信用变化等因素是否纳入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabPolicyCheck.vue — K1-6 信用减值损失会计政策检查
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6
 * Requirements: 9.1-9.2
 */
import { ref, inject, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Section 配置 ────────────────────────────────────────────────────────────

const policySections = [
  {
    id: 'K1-6-ecl-model',
    label: '一、ECL模型选择',
    description: '检查企业采用的预期信用损失模型类型（一般模型/简化模型）是否恰当。',
    placeholder: '说明企业采用的ECL模型类型及其合理性分析...',
  },
  {
    id: 'K1-6-aging-group',
    label: '二、账龄组合划分',
    description: '检查企业按账龄组合划分的合理性，是否考虑了其他信用风险特征。',
    placeholder: '说明账龄组合划分方式及合理性...',
  },
  {
    id: 'K1-6-loss-rate',
    label: '三、预期损失率确定依据',
    description: '检查预期损失率的确定方法，历史违约数据是否充分、方法论是否合理。',
    placeholder: '说明预期损失率的确定方法及数据来源...',
  },
  {
    id: 'K1-6-forward-adj',
    label: '四、前瞻性调整',
    description: '检查是否考虑前瞻性信息对预期信用损失的影响（宏观经济、行业趋势等）。',
    placeholder: '说明前瞻性信息调整情况及合理性...',
  },
]

// ─── State ───────────────────────────────────────────────────────────────────

const sectionContents = ref<Record<string, string>>({})
const conclusion = ref<string>('')

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => { loadData() })

function loadData() {
  for (const section of policySections) {
    const raw = props.allResponses.get(section.id)?.remark
    sectionContents.value[section.id] = raw || ''
  }
  conclusion.value = props.allResponses.get('K1-6-conclusion')?.remark || ''
}

// ─── 数据操作 ────────────────────────────────────────────────────────────────

function getSectionContent(id: string): string {
  return sectionContents.value[id] || ''
}

function handleSectionChange(id: string, value: string) {
  sectionContents.value[id] = value
  const payload = { item_id: id, conclusion: null, remark: value }
  props.allResponses.set(id, payload)
  emit('save', id, { remark: value })
}

function handleConclusionChange(value: string) {
  conclusion.value = value
  const itemId = 'K1-6-conclusion'
  const payload = { item_id: itemId, conclusion: value, remark: value }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { conclusion: value, remark: value })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAiGenerate(section: string) { console.log('[K1-6] AI generate:', section) }
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-policy-check { padding: 16px; font-size: 13px; }

.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.section-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;
}
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }

.policy-section {
  margin-bottom: 20px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.policy-section-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
}
.policy-section-title { font-size: 14px; font-weight: 600; margin: 0; }
.policy-section-desc {
  font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 10px;
}

.readonly-content {
  padding: 8px 12px; background: var(--el-fill-color-lighter);
  border-radius: 4px; min-height: 60px; white-space: pre-wrap; line-height: 1.6;
}

.conclusion-card { margin-top: 20px; }
.conclusion-title { font-weight: 600; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
