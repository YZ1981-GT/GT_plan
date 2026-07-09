<template>
  <div class="i5-tab-targeted-check">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 核查其他非流动资产分类是否正确（应否归入其他科目）</div>
        <div class="guide-step"><span class="step-num">②</span> 评估期限适当性（距到期＜12个月应重分类为流动资产）</div>
        <div class="guide-step"><span class="step-num">③</span> 评估可回收性（是否存在减值迹象）</div>
      </div>
    </div>

    <!-- Section 1: 分类正确性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">一、分类正确性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('classification')">
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
        <p><strong>方法论：</strong>其他非流动资产的分类正确性关注以下方面：</p>
        <p>1. 是否存在应归入长期待摊费用（1801）的项目（如装修费、改良支出）。</p>
        <p>2. 是否存在应归入无形资产（1701）的项目（如软件使用权、特许经营权）。</p>
        <p>3. 是否存在应归入预付账款或其他流动资产的项目。</p>
        <p>4. 是否存在与经营活动无关的资产应做剔除或重分类。</p>
      </div>

      <!-- 检查项 -->
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">是否存在应重分类到长期待摊费用的项目：</span>
          <el-radio-group
            v-model="checkItems.classToLtpa"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('classToLtpa')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在应重分类到无形资产的项目：</span>
          <el-radio-group
            v-model="checkItems.classToIntangible"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('classToIntangible')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在应归入流动资产科目的项目：</span>
          <el-radio-group
            v-model="checkItems.classToCurrent"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('classToCurrent')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input
          v-model="sectionConclusions.classification"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="请填写分类正确性检查结论..."
          @blur="onSectionConclusionBlur('classification')"
        />
      </div>
    </el-card>

    <!-- Section 2: 期限适当性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">二、期限适当性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('maturity')">
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
        <p><strong>方法论：</strong>其他非流动资产的期限适当性判断标准：</p>
        <p>1. CAS 30号规定：资产负债表日起一年内到期的非流动资产应转列为流动资产。</p>
        <p>2. 逐笔核实到期日，对距资产负债表日不足12个月的项目标记。</p>
        <p>3. 需重分类到"其他流动资产"或"一年内到期的非流动资产"。</p>
        <p>4. 关注有无延长到期日的情形（实质判断是否仍满足非流动条件）。</p>
      </div>

      <!-- 检查项 -->
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">是否存在距到期日＜12个月的项目未重分类：</span>
          <el-radio-group
            v-model="checkItems.maturityReclass"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('maturityReclass')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">到期日信息是否完整可验证：</span>
          <el-radio-group
            v-model="checkItems.maturityVerifiable"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('maturityVerifiable')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在期限延长但未重新评估的情况：</span>
          <el-radio-group
            v-model="checkItems.maturityExtended"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('maturityExtended')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input
          v-model="sectionConclusions.maturity"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="请填写期限适当性检查结论..."
          @blur="onSectionConclusionBlur('maturity')"
        />
      </div>
    </el-card>

    <!-- Section 3: 可回收性评估 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、可回收性评估</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('recoverability')">
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
        <p><strong>方法论：</strong>其他非流动资产可回收性评估要点：</p>
        <p>1. CAS 8号规定：资产存在减值迹象时应估计其可收回金额。</p>
        <p>2. 减值迹象包括：对方财务恶化、合同违约、市场变化、资产闲置等。</p>
        <p>3. 逐项评估是否存在回收风险，关注长期挂账、对方信用恶化项目。</p>
        <p>4. 有减值迹象的应测算可收回金额，账面＞可收回的差额计提减值。</p>
      </div>

      <!-- 检查项 -->
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">是否存在对方信用恶化/违约的资产：</span>
          <el-radio-group
            v-model="checkItems.recoverCredit"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('recoverCredit')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在长期挂账未清理的资产：</span>
          <el-radio-group
            v-model="checkItems.recoverLongPending"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('recoverLongPending')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">已识别减值迹象是否已恰当计提减值：</span>
          <el-radio-group
            v-model="checkItems.recoverImpairment"
            :disabled="isReadonly"
            size="small"
            @change="onCheckItemChange('recoverImpairment')"
          >
            <el-radio-button value="正常">正常</el-radio-button>
            <el-radio-button value="异常">异常</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- 逐项结论 -->
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input
          v-model="sectionConclusions.recoverability"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="请填写可回收性评估结论..."
          @blur="onSectionConclusionBlur('recoverability')"
        />
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
        <el-option value="针对性检查未发现异常，其他非流动资产分类与列报恰当" label="针对性检查未发现异常，其他非流动资产分类与列报恰当" />
        <el-option value="存在需关注事项，但不影响整体合理性" label="存在需关注事项，但不影响整体合理性" />
        <el-option value="发现需调整事项，已提出审计调整建议" label="发现需调整事项，已提出审计调整建议" />
        <el-option value="存在重大错报风险，需进一步审计程序" label="存在重大错报风险，需进一步审计程序" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>I5-4针对性检查关注三个维度：分类正确性、期限适当性、可回收性</li>
        <li>分类正确性：关注是否应重分类到长期待摊费用(1801)/无形资产(1701)等科目</li>
        <li>期限适当性：距资产负债表日不足12个月的应转入流动资产</li>
        <li>可回收性：关注对方信用恶化、长期挂账、合同违约等减值迹象</li>
        <li>总体结论应与审定表I5-1结果一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabTargetedCheck.vue — I5-4 针对性检查表
 *
 * 段落型：分类正确性 / 期限适当性 / 可回收性评估
 * - 逐项检查（radio正常/异常/不适用 per item）
 * - 逐项结论（textarea per section）
 * - 琥珀色方法论区 per section
 * - AI button per section
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
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

const PREFIX = 'I5-4'

const checkItems = reactive({
  // 分类正确性
  classToLtpa: '',
  classToIntangible: '',
  classToCurrent: '',
  // 期限适当性
  maturityReclass: '',
  maturityVerifiable: '',
  maturityExtended: '',
  // 可回收性
  recoverCredit: '',
  recoverLongPending: '',
  recoverImpairment: '',
})

const sectionConclusions = reactive({
  classification: '',
  maturity: '',
  recoverability: '',
})

const conclusion = ref('')

// ─── Load from allResponses ──────────────────────────────────────────────────

function _load(): void {
  // Check items
  checkItems.classToLtpa = _getString(`${PREFIX}-class-to-ltpa`)
  checkItems.classToIntangible = _getString(`${PREFIX}-class-to-intangible`)
  checkItems.classToCurrent = _getString(`${PREFIX}-class-to-current`)
  checkItems.maturityReclass = _getString(`${PREFIX}-maturity-reclass`)
  checkItems.maturityVerifiable = _getString(`${PREFIX}-maturity-verifiable`)
  checkItems.maturityExtended = _getString(`${PREFIX}-maturity-extended`)
  checkItems.recoverCredit = _getString(`${PREFIX}-recover-credit`)
  checkItems.recoverLongPending = _getString(`${PREFIX}-recover-long-pending`)
  checkItems.recoverImpairment = _getString(`${PREFIX}-recover-impairment`)
  // Section conclusions
  sectionConclusions.classification = _getString(`${PREFIX}-classification-conclusion`)
  sectionConclusions.maturity = _getString(`${PREFIX}-maturity-conclusion`)
  sectionConclusions.recoverability = _getString(`${PREFIX}-recoverability-conclusion`)
  // Overall
  conclusion.value = _getString(`${PREFIX}-conclusion`)
}

function _getString(itemId: string): string {
  const item = props.allResponses.get(itemId)
  return (item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')) as string
}

watch(() => props.allResponses, () => _load(), { immediate: true })

// ─── Save ────────────────────────────────────────────────────────────────────

const CHECK_ITEM_MAP: Record<string, string> = {
  classToLtpa: `${PREFIX}-class-to-ltpa`,
  classToIntangible: `${PREFIX}-class-to-intangible`,
  classToCurrent: `${PREFIX}-class-to-current`,
  maturityReclass: `${PREFIX}-maturity-reclass`,
  maturityVerifiable: `${PREFIX}-maturity-verifiable`,
  maturityExtended: `${PREFIX}-maturity-extended`,
  recoverCredit: `${PREFIX}-recover-credit`,
  recoverLongPending: `${PREFIX}-recover-long-pending`,
  recoverImpairment: `${PREFIX}-recover-impairment`,
}

function onCheckItemChange(field: keyof typeof checkItems): void {
  emit('save', CHECK_ITEM_MAP[field], checkItems[field])
}

function onSectionConclusionBlur(field: keyof typeof sectionConclusions): void {
  const mapping: Record<string, string> = {
    classification: `${PREFIX}-classification-conclusion`,
    maturity: `${PREFIX}-maturity-conclusion`,
    recoverability: `${PREFIX}-recoverability-conclusion`,
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
      prompt: `I5针对性检查-${section}`,
      context: {
        wpCode: 'I5-4',
        topic: section,
        existing: sectionConclusions[_sectionFieldFromKey(section) as keyof typeof sectionConclusions] || '',
      },
    })
    if (res.data?.data?.content) {
      const field = _sectionFieldFromKey(section) as keyof typeof sectionConclusions
      sectionConclusions[field] = res.data.data.content
      onSectionConclusionBlur(field)
    }
  } catch { /* ignore */ }
}

function _sectionFieldFromKey(key: string): string {
  const map: Record<string, string> = {
    classification: 'classification',
    maturity: 'maturity',
    recoverability: 'recoverability',
  }
  return map[key] ?? key
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('I5-4 针对性检查')
}
</script>

<style scoped>
.i5-tab-targeted-check { padding: 16px; font-size: 13px; }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
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

/* 检查项区块 */
.check-items { margin-bottom: 12px; }
.check-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.check-item:last-child { border-bottom: none; }
.check-label { font-size: 13px; color: var(--el-text-color-regular); flex: 1; }

/* 逐项结论 */
.section-conclusion {
  margin-top: 12px; padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.conclusion-label { font-size: 12px; color: var(--el-text-color-regular); display: block; margin-bottom: 6px; }

/* 总体结论卡片 */
.conclusion-card { margin-bottom: 16px; }
.conclusion-select { width: 100%; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
