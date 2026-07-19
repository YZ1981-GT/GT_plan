<template>
  <div class="i4-tab-targeted-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：针对长期待摊费用中大额新增项目的真实性与资本化判断、受益期变更的合理性、以及提前终止摊销的恰当处理进行专项核查。" class="objective-alert" />

    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 核查大额新增长期待摊费用的真实性和完整性</div>
        <div class="guide-step"><span class="step-num">②</span> 评估受益期变更的合理性及会计处理</div>
        <div class="guide-step"><span class="step-num">③</span> 检查提前终止摊销的原因及剩余价值处理</div>
      </div>
    </div>

    <!-- Section 1: 大额新增核查 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">一、大额新增核查</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('major-addition')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" text @click="handleReview">
              复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 方法论琥珀区 -->
      <div class="methodology-block">
        <p><strong>方法论：</strong>大额新增长期待摊费用应当关注以下事项：</p>
        <p>1. 支出的真实性：是否有合同、发票、验收单等支撑。</p>
        <p>2. 资本化判断：是否满足资产确认条件（未来经济利益很可能流入+金额能可靠计量）。</p>
        <p>3. 金额重大性：单笔超过重要性水平的应逐笔检查原始凭证。</p>
        <p>4. 受益期确定：新增项目的摊销起点和受益期限是否合理。</p>
      </div>

      <el-input
        v-model="sections.majorAddition"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 本期大额新增项目清单（项目名称/金额/新增日期）&#10;2. 逐笔核查原始凭证结果&#10;3. 资本化/费用化判断依据&#10;4. 摊销起点和受益期限确定依据"
        @blur="onSectionBlur('majorAddition')"
      />

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-select
          v-model="sectionConclusions.majorAddition"
          placeholder="请选择"
          :disabled="isReadonly"
          size="small"
          @change="onSectionConclusionChange('majorAddition')"
        >
          <el-option value="大额新增真实完整，资本化判断恰当" label="大额新增真实完整，资本化判断恰当" />
          <el-option value="大额新增存在疑点，需进一步核实" label="大额新增存在疑点，需进一步核实" />
          <el-option value="存在不应资本化的支出" label="存在不应资本化的支出" />
          <el-option value="本期无大额新增" label="本期无大额新增" />
        </el-select>
      </div>
    </el-card>

    <!-- Section 2: 受益期变更 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">二、受益期变更</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('benefit-change')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" text @click="handleReview">
              复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 方法论琥珀区 -->
      <div class="methodology-block">
        <p><strong>方法论：</strong>受益期变更属于会计估计变更，适用CAS 28号。</p>
        <p>1. 变更原因：合同续期/提前解除、经营环境变化、技术进步等。</p>
        <p>2. 处理方法：未来适用法（变更当期及以后各期调整摊销额）。</p>
        <p>3. 披露要求：变更内容/原因/对当期和未来的影响金额。</p>
        <p>4. 重点关注：是否存在通过延长受益期减少当期费用的利润操纵。</p>
      </div>

      <el-input
        v-model="sections.benefitChange"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 本期是否存在受益期变更&#10;2. 变更项目清单（原期限→新期限/变更原因）&#10;3. 变更对当期及未来摊销的影响金额&#10;4. 是否有合理商业理由支持变更"
        @blur="onSectionBlur('benefitChange')"
      />

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-select
          v-model="sectionConclusions.benefitChange"
          placeholder="请选择"
          :disabled="isReadonly"
          size="small"
          @change="onSectionConclusionChange('benefitChange')"
        >
          <el-option value="受益期估计合理，本期无变更" label="受益期估计合理，本期无变更" />
          <el-option value="存在合理变更，已恰当处理并披露" label="存在合理变更，已恰当处理并披露" />
          <el-option value="存在变更但披露不充分" label="存在变更但披露不充分" />
          <el-option value="变更缺乏合理理由，可能存在利润操纵" label="变更缺乏合理理由，可能存在利润操纵" />
        </el-select>
      </div>
    </el-card>

    <!-- Section 3: 提前终止处理 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、提前终止处理</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('early-termination')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" text @click="handleReview">
              复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 方法论琥珀区 -->
      <div class="methodology-block">
        <p><strong>方法论：</strong>长期待摊费用提前终止的情形及处理：</p>
        <p>1. 租赁提前终止：装修费/改良支出剩余未摊余额一次性转入当期损益。</p>
        <p>2. 经营终止：相关待摊费用不再受益，应一次性转出。</p>
        <p>3. 减值迹象：有减值迹象时，按可收回金额与账面价值孰低计量。</p>
        <p>4. 关注：是否存在应终止但未终止的项目（虚增资产）。</p>
      </div>

      <el-input
        v-model="sections.earlyTermination"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 本期是否存在提前终止摊销的项目&#10;2. 终止原因及处理方式&#10;3. 剩余未摊余额的转出金额及去向&#10;4. 是否存在应终止但未终止的情况"
        @blur="onSectionBlur('earlyTermination')"
      />

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-select
          v-model="sectionConclusions.earlyTermination"
          placeholder="请选择"
          :disabled="isReadonly"
          size="small"
          @change="onSectionConclusionChange('earlyTermination')"
        >
          <el-option value="本期无提前终止项目" label="本期无提前终止项目" />
          <el-option value="提前终止处理恰当" label="提前终止处理恰当" />
          <el-option value="存在应终止但未终止的项目" label="存在应终止但未终止的项目" />
          <el-option value="终止处理不当，需建议调整" label="终止处理不当，需建议调整" />
        </el-select>
      </div>
    </el-card>

    <!-- 总体审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">总体审计结论</span>
        </div>
      </template>
      <el-select
        v-model="conclusion"
        placeholder="请选择审计结论"
        :disabled="isReadonly"
        class="conclusion-select"
        @change="onConclusionChange"
      >
        <el-option value="针对性检查未发现异常，长期待摊费用列报恰当" label="针对性检查未发现异常，长期待摊费用列报恰当" />
        <el-option value="存在需关注事项，但不影响整体合理性" label="存在需关注事项，但不影响整体合理性" />
        <el-option value="发现需调整事项，已提出审计调整建议" label="发现需调整事项，已提出审计调整建议" />
        <el-option value="存在重大错报风险，需进一步审计程序" label="存在重大错报风险，需进一步审计程序" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><strong>CAS依据：</strong>《企业会计准则第6号——无形资产》应用指南、CAS 28号"会计政策、会计估计变更和差错更正"。</p>
        <p><strong>编制要点：</strong></p>
        <ul>
          <li>I4-5针对性检查为段落型，每个section独立结论+AI辅助</li>
          <li>大额新增核查关注：超过重要性水平的单笔新增应逐项抽凭</li>
          <li>受益期变更按CAS 28号未来适用法处理</li>
          <li>提前终止项目剩余价值一次性计入当期损益</li>
          <li>总体结论应与审定表I4-1结果一致</li>
        </ul>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabTargetedCheck.vue — I4-5 针对性检查表
 *
 * 段落型：大额新增核查 / 受益期变更 / 提前终止处理
 * - 逐项结论（dropdown per section）
 * - 琥珀色方法论区 per section
 * - AI button per section
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.6
 * Requirements: 5.1-5.2
 */
import { ref, reactive, watch, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── State ───────────────────────────────────────────────────────────────────

const PREFIX = 'I4-5'

const sections = reactive({
  majorAddition: '',
  benefitChange: '',
  earlyTermination: '',
})

const sectionConclusions = reactive({
  majorAddition: '',
  benefitChange: '',
  earlyTermination: '',
})

const conclusion = ref('')

// ─── Load from allResponses ──────────────────────────────────────────────────

function _load(): void {
  sections.majorAddition = _getString(`${PREFIX}-major-addition`)
  sections.benefitChange = _getString(`${PREFIX}-benefit-change`)
  sections.earlyTermination = _getString(`${PREFIX}-early-termination`)
  sectionConclusions.majorAddition = _getString(`${PREFIX}-major-addition-conclusion`)
  sectionConclusions.benefitChange = _getString(`${PREFIX}-benefit-change-conclusion`)
  sectionConclusions.earlyTermination = _getString(`${PREFIX}-early-termination-conclusion`)
  conclusion.value = _getString(`${PREFIX}-conclusion`)
}

function _getString(itemId: string): string {
  const item = props.allResponses.get(itemId)
  return (item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')) as string
}

watch(() => props.allResponses, () => _load(), { immediate: true })

// ─── Save ────────────────────────────────────────────────────────────────────

function onSectionBlur(field: keyof typeof sections): void {
  const mapping: Record<string, string> = {
    majorAddition: `${PREFIX}-major-addition`,
    benefitChange: `${PREFIX}-benefit-change`,
    earlyTermination: `${PREFIX}-early-termination`,
  }
  emit('save', mapping[field], sections[field])
}

function onSectionConclusionChange(field: keyof typeof sectionConclusions): void {
  const mapping: Record<string, string> = {
    majorAddition: `${PREFIX}-major-addition-conclusion`,
    benefitChange: `${PREFIX}-benefit-change-conclusion`,
    earlyTermination: `${PREFIX}-early-termination-conclusion`,
  }
  emit('save', mapping[field], sectionConclusions[field])
}

function onConclusionChange(val: string): void {
  emit('save', `${PREFIX}-conclusion`, val)
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I4针对性检查-${section}`,
      context: {
        wpCode: 'I4-5',
        topic: section,
        existing: (sections as any)[_sectionFieldFromKey(section)] || '',
      },
    })
    if (res.data?.data?.content) {
      const field = _sectionFieldFromKey(section)
      ;(sections as any)[field] = res.data.data.content
      onSectionBlur(field as keyof typeof sections)
    }
  } catch { /* ignore */ }
}

function _sectionFieldFromKey(key: string): string {
  const map: Record<string, string> = {
    'major-addition': 'majorAddition',
    'benefit-change': 'benefitChange',
    'early-termination': 'earlyTermination',
  }
  return map[key] ?? key
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('I4-5 针对性检查')
}
</script>

<style scoped>
.i4-tab-targeted-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 审计目标 */
.objective-alert { margin-bottom: 14px; }
.i4-tab-targeted-check :deep(.objective-alert .el-alert__content) { padding: 2px 0; }

/* 编制提示 (guidance-details) */
.guidance-details { margin-top: 16px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.guidance-details summary { cursor: pointer; font-weight: 500; font-size: 13px; }
.guidance-content { padding: 8px 0 0 8px; line-height: 1.7; }
.guidance-content ul { padding-left: 18px; margin-top: 4px; }
.guidance-content li { margin-bottom: 3px; }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* Section卡片 */
.check-section { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
}
.section-title { font-size: 14px; font-weight: 600; }
.section-actions { display: flex; align-items: center; gap: 4px; }

/* 方法论琥珀色区 */
.methodology-block {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-block p { margin: 0 0 2px; }
.methodology-block strong { color: #78350f; }

/* 逐项结论 */
.section-conclusion {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.conclusion-label { font-size: 12px; color: var(--el-text-color-regular); white-space: nowrap; }

/* 总体结论卡片 */
.conclusion-card { margin-bottom: 16px; }
.conclusion-select { width: 100%; }
</style>
