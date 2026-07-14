<template>
<div class="d6-tab-policy-check">
  <!-- 审计目标（源模板：一、审计目标） -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <span class="ao-title">审计目标</span>
    </template>
    <template #default>
      <ol class="ao-list">
        <li>资产负债表中记录的合同资产是存在的；</li>
        <li>合同资产以恰当的金额包括在财务报表中，与之相关的计价调整已恰当记录。</li>
      </ol>
    </template>
  </el-alert>

  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示（CAS22 金融工具减值准则）</summary>
    <div class="guidance-content">
      <p>1. 逐段评价被审计单位合同资产坏账准备会计政策及 ECL 模型的合理性，对照 CAS22 金融工具减值准则要求。</p>
      <p>2. 每段评价应关注政策合规性、历史损失率预测、前瞻性信息调整及同行业可比性。</p>
      <p>3. 评价结论应与 D6-8 减值测算的损失率参数选取相互印证。</p>
      <p>4. 发现政策不当或参数不合理时，应评估对减值准备计提充分性的影响并考虑调整。</p>
      <p>5. CAS22第63条：对于不含重大融资成分的应收账款和合同资产，企业应当始终按照整个存续期的预期信用损失计量其损失准备。</p>
    </div>
  </details>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-tag size="small" type="info">二、审计过程</el-tag>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:D6-8" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
    </div>
  </div>

  <!-- 四段审计评价 -->
  <div v-for="item in policyEvalItems" :key="item.id" class="eval-card">
    <div class="eval-header">
      <span class="eval-title">{{ item.title }}</span>
      <div class="eval-actions">
        <el-button size="small" type="primary" plain @click="aiGenerate(item)">🤖 AI辅助</el-button>
        <el-button size="small" @click="openReview(item.itemId)">💬</el-button>
      </div>
    </div>

    <!-- 源模板方法论上下文（琥珀块） -->
    <div class="amber-context">
      <span class="amber-icon">📌</span>
      <span class="amber-text">{{ item.guidance }}</span>
    </div>

    <el-input
      :model-value="evaluations[item.id]"
      type="textarea"
      :autosize="{ minRows: 5, maxRows: 16 }"
      :disabled="isReadonly"
      :placeholder="getPlaceholder(item.id)"
      @change="(v: string) => updateEvaluation(item.id, v)"
    />

    <!-- 第(四)节：内嵌上市公司参考 -->
    <template v-if="item.id === 4">
      <details class="ref-details">
        <summary>📘 上市公司合同资产减值准备会计政策披露示例（点击展开，可一键套用）</summary>
        <div class="ref-grid">
          <div v-for="ref in industryPolicyRefs" :key="ref.company" class="ref-item">
            <div class="ref-item-header">
              <span class="ref-company">{{ ref.company }}</span>
              <el-button size="small" type="success" plain @click="applyIndustryRef(ref)">套用</el-button>
            </div>
            <div class="ref-policy">{{ ref.policy }}</div>
          </div>
        </div>
      </details>
    </template>
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-8" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <!-- 三、审计说明 -->
    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">三、审计说明</span>
        <div class="opinion-actions">
          <el-button size="small" type="primary" plain @click="aiGenerateNote('explanation')">🤖 AI辅助</el-button>
          <el-button size="small" @click="openReview('D6-7-note-explanation')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :disabled="isReadonly" placeholder="说明政策检查过程中的重要发现、与管理层的讨论要点、对ECL模型参数的验证过程等..." />
    </div>

    <!-- 四、审计结论 -->
    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">四、审计结论</span>
        <div class="opinion-actions">
          <el-select
            v-model="selectedTemplate"
            placeholder="快速选择结论模板"
            size="small"
            clearable
            style="width: 200px; margin-right: 8px"
            @change="onTemplateSelect"
          >
            <el-option v-for="t in conclusionTemplates" :key="t.label" :label="t.label" :value="t.value" />
          </el-select>
          <el-button size="small" type="primary" plain @click="aiGenerateNote('conclusion')">🤖 AI辅助</el-button>
          <el-button size="small" @click="openReview('D6-7-note-conclusion')">💬</el-button>
        </div>
      </div>
      <!-- 源模板结论参考（琥珀块） -->
      <div class="amber-context amber-conclusion">
        <span class="amber-icon">📌</span>
        <span class="amber-text">被审计单位对能维护的计提准备金的会计政策与会计估计准则和企业会计准则的规定一致，实现了预期的一整个合同周期的减值准备的合理一致，且同行业公司的做法亦为合适者标准，日常会计政策调整符合一致性原则。</span>
      </div>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }" :disabled="isReadonly" placeholder="综合评价政策合理性结论..." />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabPolicyCheck.vue — 合同资产减值准备会计政策检查 D6-7
 *
 * 对齐源模板结构：审计目标(2条认定) → 审计过程(四段评价) → 审计说明 → 审计结论
 * 增强：每段AI辅助 + 方法论琥珀块 + 上市公司参考一键套用 + 结论模板select
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useD6PolicyCheck } from '../composables/useD6PolicyCheck'
import type { PolicyEvalItem } from '../composables/useD6PolicyCheck'
import type { ChecklistResponse } from '../composables/useD6FormData'
import http from '@/utils/http'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const {
  evaluations, updateEvaluation, auditObjective, auditNotes, policyEvalItems,
  industryPolicyRefs, conclusionTemplates, applyConclusion, applyIndustryRef,
} = useD6PolicyCheck({
  allResponses: allResponsesRef,
  debouncedSave: props.debouncedSave,
})

const selectedTemplate = ref('')

function onTemplateSelect(val: string) {
  if (val) {
    applyConclusion(val)
    selectedTemplate.value = ''
  }
}

// ─── AI 辅助生成 ────────────────────────────────────────────────────────────
function getPlaceholder(id: number): string {
  const map: Record<number, string> = {
    1: '描述被审计单位合同资产减值准备计提会计政策：信用风险组合划分依据、ECL模型选用（简化法/一般法）、损失率确定方法...',
    2: '说明历史坏账损失率数据来源、核实程序、是否考虑货币时间价值、数据年限是否充分...',
    3: '说明前瞻性信息来源（内部模型/第三方/外部专家）、宏观经济指标选取、调整幅度及依据...',
    4: '列示同行业上市公司合同资产减值准备会计政策，对比分析被审计单位政策的合理性...',
  }
  return map[id] || '请输入审计评价...'
}

async function aiGenerate(item: PolicyEvalItem) {
  try {
    const context: Record<string, string> = {
      '底稿编号': 'D6-7',
      '评价段落': item.title,
      '方法论要求': item.guidance,
    }
    // 附加已填其他段落作为上下文
    for (const p of policyEvalItems) {
      if (p.id !== item.id && evaluations.value[p.id]) {
        context[p.title] = evaluations.value[p.id]
      }
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: item.aiSection,
      prompt: `请根据CAS22金融工具减值准则要求，生成合同资产减值准备会计政策检查中"${item.title}"段落的审计评价。要求：专业、具体、有逻辑层次，包含需关注的关键点。`,
      context,
      existingContent: evaluations.value[item.id] || '',
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      updateEvaluation(item.id, text)
    }
  } catch {
    // silent - vLLM可能不可用
  }
}

async function aiGenerateNote(section: 'explanation' | 'conclusion') {
  try {
    const context: Record<string, string> = { '底稿编号': 'D6-7' }
    for (const p of policyEvalItems) {
      if (evaluations.value[p.id]) {
        context[p.title] = evaluations.value[p.id]
      }
    }
    if (section === 'conclusion' && auditNotes.value.explanation) {
      context['审计说明'] = auditNotes.value.explanation
    }
    const promptMap = {
      explanation: '根据以上四段政策评价内容，生成审计说明，概括性描述政策检查过程、重要发现和与管理层的讨论结论。',
      conclusion: '根据以上审计过程和审计说明，生成审计结论。结论应明确判断被审计单位合同资产减值准备会计政策是否符合企业会计准则规定，是否与同行业保持一致，是否保持一贯性。',
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `d6-7-${section}`,
      prompt: promptMap[section],
      context,
      existingContent: section === 'explanation' ? auditNotes.value.explanation : auditNotes.value.conclusion,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (section === 'explanation') {
        auditNotes.value = { ...auditNotes.value, explanation: text }
      } else {
        auditNotes.value = { ...auditNotes.value, conclusion: text }
      }
    }
  } catch {
    // silent
  }
}
</script>

<style scoped>
.d6-tab-policy-check { padding: 16px; }

/* 审计目标 */
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

/* 编制提示 */
.guidance-details {
  margin-bottom: 14px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 13px;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 评价卡片 */
.eval-card {
  margin-bottom: 18px;
  padding: 14px 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}
.eval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.eval-title { font-size: 14px; font-weight: 600; color: #303133; }
.eval-actions { display: flex; gap: 6px; align-items: center; }

/* 方法论琥珀块 */
.amber-context {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.55;
  color: #8a6d3b;
  display: flex;
  gap: 6px;
}
.amber-icon { flex-shrink: 0; }
.amber-text { flex: 1; }
.amber-conclusion { margin-bottom: 10px; }

/* 上市公司参考 */
.ref-details {
  margin-top: 12px;
  border: 1px dashed #d9ecff;
  border-radius: 6px;
  padding: 8px 12px;
  background: #f5faff;
}
.ref-details summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}
.ref-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.ref-item {
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
}
.ref-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.ref-company {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}
.ref-policy {
  color: #606266;
  line-height: 1.5;
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
}

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
</style>
