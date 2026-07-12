<template>
  <div class="i4-tab-policy-check">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 确认摊销方法是否适当（直线法/工作量法）</div>
        <div class="guide-step"><span class="step-num">②</span> 评估受益期限估计的合理性</div>
        <div class="guide-step"><span class="step-num">③</span> 检查会计估计变更是否恰当处理</div>
      </div>
    </div>

    <!-- Section 1: 摊销方法 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">一、摊销方法适当性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('amortization-method')">
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
        <p><strong>方法论：</strong>长期待摊费用摊销方法应与费用受益模式一致。</p>
        <p>直线法：受益均匀分布（如装修费、开办费按月平均分摊）。</p>
        <p>工作量法：受益与产出相关（如模具费按产量分摊）。</p>
        <p>选择依据：CAS 第十三号"或有事项"相关解释 + 公司会计政策。</p>
      </div>

      <el-input
        v-model="sections.amortizationMethod"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 被审计单位采用的摊销方法（直线法/工作量法/混合）&#10;2. 摊销方法是否与费用受益模式一致&#10;3. 与同行业惯例比较&#10;4. 对财务报表的影响"
        @blur="onSectionBlur('amortizationMethod')"
      />
    </el-card>

    <!-- Section 2: 受益期估计 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">二、受益期限估计合理性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('benefit-period')">
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
        <p><strong>方法论：</strong>受益期限应有充分依据，不得随意缩短或延长。</p>
        <p>装修费：不超过租赁期/使用年限孰短。开办费：不超过5年（按规定最短3年）。</p>
        <p>其他：根据合同约定/预计受益年限确定。若无约定按不超过10年摊销。</p>
        <p>关注：期限估计是否经管理层审批？是否有书面记录？</p>
      </div>

      <el-input
        v-model="sections.benefitPeriod"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 各项目受益期限确定依据&#10;2. 是否与合同期限/资产使用寿命一致&#10;3. 估计变更情况及合理性&#10;4. 管理层审批记录"
        @blur="onSectionBlur('benefitPeriod')"
      />
    </el-card>

    <!-- Section 3: 变更处理 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、会计估计变更处理</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('change-treatment')">
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
        <p><strong>方法论：</strong>CAS 28号"会计政策、会计估计变更和差错更正"。</p>
        <p>摊销方法变更：属于会计政策变更，需追溯调整（除非不可行）。</p>
        <p>受益期限变更：属于会计估计变更，采用未来适用法。</p>
        <p>差错更正：前期差错须追溯重述。</p>
        <p>关注：变更是否有合理理由？是否已在附注充分披露？</p>
      </div>

      <el-input
        v-model="sections.changeTreatment"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="请填写：&#10;1. 本期是否存在摊销政策/估计变更&#10;2. 变更原因及合理性分析&#10;3. 会计处理是否符合CAS 28号&#10;4. 附注披露是否充分"
        @blur="onSectionBlur('changeTreatment')"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
        </div>
      </template>
      <el-select
        v-model="conclusion"
        placeholder="请选择审计结论"
        :disabled="isReadonly"
        class="conclusion-select"
        @change="onConclusionChange"
      >
        <el-option value="摊销政策适当，估计合理，无需调整" label="摊销政策适当，估计合理，无需调整" />
        <el-option value="摊销政策适当，但受益期限估计需关注" label="摊销政策适当，但受益期限估计需关注" />
        <el-option value="存在会计估计变更，已恰当处理" label="存在会计估计变更，已恰当处理" />
        <el-option value="摊销政策不适当，需建议调整" label="摊销政策不适当，需建议调整" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>本表为段落型检查，主要通过文字描述记录审计判断</li>
        <li>每个section均可使用AI辅助生成初稿，审计师需复核修改</li>
        <li>结论应与审定表I4-1结果一致</li>
        <li>会计估计变更需特别关注：是否有合理理由+附注是否充分披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabPolicyCheck.vue — I4-4 摊销政策检查表
 *
 * 段落型检查：摊销方法适当性 / 受益期限估计 / 会计估计变更处理
 * - 琥珀色方法论区（每个section独立）
 * - AI按钮 per section
 * - Autosize textarea
 * - Conclusion dropdown
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.5
 * Requirements: 4.1-4.2
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

const PREFIX = 'I4-4'

const sections = reactive({
  amortizationMethod: '',
  benefitPeriod: '',
  changeTreatment: '',
})

const conclusion = ref('')

// ─── Load from allResponses ──────────────────────────────────────────────────

function _load(): void {
  sections.amortizationMethod = _getString(`${PREFIX}-amortization-method`)
  sections.benefitPeriod = _getString(`${PREFIX}-benefit-period`)
  sections.changeTreatment = _getString(`${PREFIX}-change-treatment`)
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
    amortizationMethod: `${PREFIX}-amortization-method`,
    benefitPeriod: `${PREFIX}-benefit-period`,
    changeTreatment: `${PREFIX}-change-treatment`,
  }
  emit('save', mapping[field], sections[field])
}

function onConclusionChange(val: string): void {
  emit('save', `${PREFIX}-conclusion`, val)
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I4摊销政策检查-${section}`,
      context: {
        wpCode: 'I4-4',
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
    'amortization-method': 'amortizationMethod',
    'benefit-period': 'benefitPeriod',
    'change-treatment': 'changeTreatment',
  }
  return map[key] ?? key
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('I4-4 摊销政策检查')
}
</script>

<style scoped>
.i4-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* Section卡片 */
.check-section { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
}
.section-title { font-size: 14px; font-weight: 600; }
.section-actions { display: flex; align-items: center; gap: 4px; }

/* 方法论琥珀色区（每个section内） */
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

/* 结论卡片 */
.conclusion-card { margin-bottom: 16px; }
.conclusion-select { width: 100%; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
