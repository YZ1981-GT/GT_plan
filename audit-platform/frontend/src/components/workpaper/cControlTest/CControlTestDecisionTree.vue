<!--
  CControlTestDecisionTree.vue — Cx-2 偏差评价决策树（6步IF驱动）

  职责：
  - 6 步决策树 UI：每步卡片 + 问题 + 单选选项
  - 点选自动推进（isStepVisible 控制显隐）
  - 步骤五显示 GtIndexChip → A14
  - 最终评价结论 badge 展示
  - 数据绑定：deviationStates[index] + updateDeviationStep

  Spec: .kiro/specs/c-control-test-refresh/
  Task: 4.3
  Requirements: 5.4, 5.5
-->
<template>
  <div class="cct-decision-tree">
    <!-- 视图头部 -->
    <div class="cct-view-header">
      <el-button text @click="$emit('navigate', 'directory')">
        <el-icon><ArrowLeft /></el-icon>
        返回目录
      </el-button>
      <span class="cct-view-title">{{ wpCode }}-2 评价控制偏差</span>
      <span class="cct-dev-subtitle" v-if="controlName">
        — 控制点 {{ devIndex + 1 }}：{{ controlName }}
      </span>
    </div>

    <!-- 控制点选择（如果有多个） -->
    <div v-if="controlCount > 1" class="cct-dev-selector">
      <span class="cct-dev-selector-label">选择控制点：</span>
      <el-select
        :model-value="devIndex"
        size="small"
        @change="(v: number) => $emit('change-dev-index', v)"
      >
        <el-option
          v-for="(name, i) in controlNames"
          :key="i"
          :label="`${i + 1}. ${name || '控制点' + (i + 1)}`"
          :value="i"
        />
      </el-select>
    </div>

    <!-- 控制例外情况描述（顶部） -->
    <div class="cct-exception-desc">
      <div class="cct-exception-desc-label">
        <span class="cct-exception-desc-title">控制例外情况描述</span>
        <el-tooltip content="描述控制测试中发现的例外情况具体表现、涉及金额、影响范围等" placement="top" :show-after="300">
          <el-icon class="cct-step-info"><InfoFilled /></el-icon>
        </el-tooltip>
        <el-button
          size="small"
          type="primary"
          plain
          class="cct-exception-ai-btn"
          :loading="aiGeneratingException"
          :disabled="readonly"
          @click="handleAiGenerateException"
        >
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
      </div>
      <el-input
        v-model="exceptionDescription"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="readonly"
        placeholder="描述控制测试中发现的例外情况，包括具体表现、涉及金额、时间区间、影响范围等"
        @blur="handleExceptionDescBlur"
      />
    </div>

    <!-- 六步决策树 -->
    <div class="cct-steps-container">
      <!-- 步骤一 -->
      <div
        v-if="isVisible(1)"
        id="cct-step-1"
        class="cct-step-card"
        :class="{ 'is-active': isCurrentStep(1) }"
      >
        <div class="cct-step-header">
          <span class="cct-step-num">1</span>
          <span class="cct-step-question">{{ getQuestion(1) }}</span>
          <el-tooltip
            :content="getStepTooltip(1)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <el-radio-group
            :model-value="devState.step1"
            :disabled="readonly"
            @update:model-value="(v: string) => onStepChange('step1', v)"
          >
            <el-radio
              v-for="opt in getOptions(1)"
              :key="opt.value"
              :value="opt.value"
              class="cct-step-radio"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <!-- 注释说明 -->
          <div class="cct-step-annotation">
            <span class="cct-annotation-tag">注1</span>
            <span>控制偏差是指控制未按设计运行，或执行控制的人员不具备有效执行控制所必需的授权或胜任能力。控制例外不一定构成控制偏差，例如合理的人为判断差异、系统维护期间的计划内例外等。</span>
          </div>
          <!-- 指引文案 -->
          <div v-if="devState.step1" class="cct-step-guidance">
            <el-icon><Right /></el-icon>
            <span>{{ getGuidanceAfterStep(1) }}</span>
          </div>
        </div>
      </div>

      <!-- 步骤二 -->
      <div
        v-if="isVisible(2)"
        id="cct-step-2"
        class="cct-step-card"
        :class="{ 'is-active': isCurrentStep(2) }"
      >
        <div class="cct-step-header">
          <span class="cct-step-num">2</span>
          <span class="cct-step-question">{{ getQuestion(2) }}</span>
          <el-tooltip
            :content="getStepTooltip(2)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <el-radio-group
            :model-value="devState.step2"
            :disabled="readonly"
            @update:model-value="(v: string) => onStepChange('step2', v)"
          >
            <el-radio
              v-for="opt in getOptions(2)"
              :key="opt.value"
              :value="opt.value"
              class="cct-step-radio"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <!-- 注释说明 -->
          <div class="cct-step-annotation">
            <span class="cct-annotation-tag">注2</span>
            <span><b>系统性偏差</b>：因控制设计缺陷或系统性因素导致一类交易中反复出现的偏差（如系统参数配置错误导致所有同类交易异常）。<b>人为偏差</b>：由特定人员有意规避或忽略控制而导致（如管理层凌驾、审批人越权）。<b>随机性偏差</b>：偶发性的人为疏忽或操作失误，非蓄意行为（如个别交易漏审批）。</span>
          </div>
          <!-- 指引文案 -->
          <div v-if="devState.step2" class="cct-step-guidance">
            <el-icon><Right /></el-icon>
            <span>{{ getGuidanceAfterStep(2) }}</span>
          </div>
        </div>
      </div>

      <!-- 步骤三 -->
      <div
        v-if="isVisible(3)"
        id="cct-step-3"
        class="cct-step-card"
        :class="{ 'is-active': isCurrentStep(3) }"
      >
        <div class="cct-step-header">
          <span class="cct-step-num">3</span>
          <span class="cct-step-question">{{ getQuestion(3) }}</span>
          <el-tooltip
            :content="getStepTooltip(3)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <el-radio-group
            :model-value="devState.step3"
            :disabled="readonly"
            @update:model-value="(v: string) => onStepChange('step3', v)"
          >
            <el-radio
              v-for="opt in getOptions(3)"
              :key="opt.value"
              :value="opt.value"
              class="cct-step-radio"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <!-- 注释说明 -->
          <div class="cct-step-annotation">
            <span class="cct-annotation-tag">注3</span>
            <span>扩大样本量时应从原始总体中重新选取额外样本（通常扩大至原样本量的2倍），并对新样本进行同等程序的测试。若直接认定为偏差，则无需扩大样本量，直接进入缺陷评价环节。注意：扩大样本量仅适用于随机性偏差，系统性和人为偏差不应通过扩大样本来解决。</span>
          </div>
          <!-- 指引文案 -->
          <div v-if="devState.step3" class="cct-step-guidance">
            <el-icon><Right /></el-icon>
            <span>{{ getGuidanceAfterStep(3) }}</span>
          </div>
        </div>
      </div>

      <!-- 步骤四 -->
      <div
        v-if="isVisible(4)"
        id="cct-step-4"
        class="cct-step-card"
        :class="{ 'is-active': isCurrentStep(4) }"
      >
        <div class="cct-step-header">
          <span class="cct-step-num">4</span>
          <span class="cct-step-question">{{ getQuestion(4) }}</span>
          <el-tooltip
            :content="getStepTooltip(4)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <el-radio-group
            :model-value="devState.step4"
            :disabled="readonly"
            @update:model-value="(v: string) => onStepChange('step4', v)"
          >
            <el-radio
              v-for="opt in getOptions(4)"
              :key="opt.value"
              :value="opt.value"
              class="cct-step-radio"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <!-- 注释说明 -->
          <div class="cct-step-annotation">
            <span class="cct-annotation-tag">注4</span>
            <span>扩大样本后如未发现新偏差，注册会计师可据此合理判断原始偏差为孤立事件，控制整体有效运行。若发现新偏差，则表明原始偏差并非孤立事件，需重新评估控制的运行有效性，并进入缺陷评价程序。</span>
          </div>
          <!-- 指引文案 -->
          <div v-if="devState.step4" class="cct-step-guidance">
            <el-icon><Right /></el-icon>
            <span>{{ getGuidanceAfterStep(4) }}</span>
          </div>
        </div>
      </div>

      <!-- 步骤五（自动推导，无选项，显示 GtIndexChip → A14） -->
      <div v-if="isVisible(5)" id="cct-step-5" class="cct-step-card cct-step-five">
        <div class="cct-step-header">
          <span class="cct-step-num cct-step-num-warning">5</span>
          <span class="cct-step-question">{{ getQuestion(5) }}</span>
          <el-tooltip
            :content="getStepTooltip(5)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <div class="cct-step-five-content">
            <el-icon class="cct-warning-icon"><WarningFilled /></el-icon>
            <span>请进入A14内控缺陷评价底稿，评价控制缺陷等级</span>
            <GtIndexChip value="A14" :context="defectContext || `控制点：${controlName}`" class="cct-a14-chip" />
          </div>
          <!-- 注释说明 -->
          <div class="cct-step-annotation cct-step-annotation-warning">
            <span class="cct-annotation-tag">注5</span>
            <span>控制缺陷的严重程度分为三级：<b>一般缺陷</b>（内控虽有偏差但尚不足以影响财务报表整体公允性）、<b>重要缺陷</b>（一项或多项控制缺陷的组合，严重程度低于重大缺陷但足以引起管理层关注）、<b>重大缺陷</b>（一项或多项控制缺陷的组合，可能导致不能及时防止或发现并纠正财务报表中的重大错报）。评价时应考虑定量标准（涉及金额占重要性水平的比例）与定性标准（是否涉及舞弊、影响范围等）。</span>
          </div>
        </div>
      </div>

      <!-- 步骤六 -->
      <div
        v-if="isVisible(6)"
        id="cct-step-6"
        class="cct-step-card"
        :class="{ 'is-active': isCurrentStep(6) }"
      >
        <div class="cct-step-header">
          <span class="cct-step-num">6</span>
          <span class="cct-step-question">{{ getQuestion(6) }}</span>
          <el-tooltip
            :content="getStepTooltip(6)"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <el-icon class="cct-step-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <div class="cct-step-body">
          <el-radio-group
            :model-value="devState.step6"
            :disabled="readonly"
            @update:model-value="(v: string) => onStepChange('step6', v)"
          >
            <el-radio
              v-for="opt in getOptions(6)"
              :key="opt.value"
              :value="opt.value"
              class="cct-step-radio"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <!-- 注释说明 -->
          <div class="cct-step-annotation">
            <span class="cct-annotation-tag">注6</span>
            <span>设计缺陷是指某项控制缺失、或虽存在但即使按设计运行也无法有效防止/发现重大错报。与运行缺陷不同，设计缺陷意味着控制本身的逻辑或覆盖范围存在根本性不足。发现设计缺陷应通知管理层并建议完善控制设计。</span>
          </div>
          <!-- 指引文案 -->
          <div v-if="devState.step6" class="cct-step-guidance">
            <el-icon><Right /></el-icon>
            <span>{{ getGuidanceAfterStep(6) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 评价结论汇总区 -->
    <div v-if="treeResult.conclusion" class="cct-conclusion-area">
      <el-card shadow="never" class="cct-conclusion-card">
        <template #header>
          <div class="cct-conclusion-card-header">
            <span class="cct-conclusion-card-title">评价结论</span>
            <el-button size="small" text type="primary" @click="showExampleDrawer = true">
              <el-icon><Document /></el-icon> 查看示例参考
            </el-button>
          </div>
        </template>
        <div class="cct-conclusion-summary">
          <div class="cct-conclusion-row">
            <span class="cct-conclusion-label">控制点：</span>
            <span class="cct-conclusion-value">{{ controlName || `控制点${devIndex + 1}` }}</span>
          </div>
          <div class="cct-conclusion-row">
            <span class="cct-conclusion-label">例外描述：</span>
            <span class="cct-conclusion-value">{{ exceptionDescription || '（未填写）' }}</span>
          </div>
          <div class="cct-conclusion-row">
            <span class="cct-conclusion-label">决策路径：</span>
            <span class="cct-conclusion-value cct-path-badge">路径{{ treeResult.path }}</span>
          </div>
          <div class="cct-conclusion-row">
            <span class="cct-conclusion-label">评价结论：</span>
            <el-tag
              :type="conclusionTagType"
              size="large"
              effect="dark"
              class="cct-conclusion-badge"
            >
              {{ treeResult.conclusion }}
            </el-tag>
          </div>
          <div v-if="treeResult.goToA14" class="cct-conclusion-action">
            <el-icon><WarningFilled /></el-icon>
            <span>需进入内控缺陷评价底稿：</span>
            <GtIndexChip value="A14" :context="defectContext || `控制点：${controlName}`" />
          </div>
        </div>
      </el-card>
    </div>

    <!-- 底部导航 -->
    <div class="cct-decision-footer">
      <el-button @click="$emit('navigate', 'summary')">返回汇总表</el-button>
    </div>

    <!-- 编制提示（底部折叠） -->
    <details class="cct-compilation-tips">
      <summary>编制提示 — 偏差评价决策树</summary>
      <div class="cct-tips-content">
        <p>• 本决策树复刻源模板 Cx-2「评价控制偏差」的 6 步 IF 公式链。</p>
        <p>• 步骤一判断控制例外是否属于控制偏差——「否」进入步骤六评估设计缺陷。</p>
        <p>• 系统性/人为有意偏差直接进入步骤五（A14 内控缺陷评价）。</p>
        <p>• 随机性偏差→步骤三（扩大样本量 or 直接认定），扩大后无新偏差=控制有效。</p>
        <p>• 步骤五触发 A14 联动——通过索引芯片跳转缺陷评价底稿。</p>
        <p>• 步骤六「是」表明存在设计缺陷，回到步骤五处理。</p>
      </div>
    </details>

    <!-- ═══ 示例参考 Drawer ═══ -->
    <el-drawer
      v-model="showExampleDrawer"
      title="示例 — 评价控制偏差"
      direction="rtl"
      size="45%"
      :append-to-body="true"
    >
      <div class="cct-example-drawer-content">
        <div class="cct-example-section">
          <h4>示例一：采购订单审批控制偏差（随机性→扩大样本→控制有效）</h4>
          <div class="cct-example-flow">
            <div class="cct-example-step"><b>控制例外情况描述：</b>在25笔采购样本中，发现1笔金额为12,500元的采购订单缺少部门经理签字审批。经核实，该审批人当日因病请假，代理审批人已口头确认但未补签。</div>
            <div class="cct-example-step"><b>步骤一：</b>是（属于控制偏差—未按既定审批流程执行）</div>
            <div class="cct-example-step"><b>步骤二：</b>随机性偏差（偶发性人为疏忽，非蓄意行为）</div>
            <div class="cct-example-step"><b>步骤三：</b>扩大样本量（从原总体中重新选取25笔额外样本）</div>
            <div class="cct-example-step"><b>步骤四：</b>否（扩大后25笔均有完整审批签字）</div>
            <div class="cct-example-step"><b>结论：</b>控制有效（路径E）——原始偏差为孤立事件</div>
          </div>
        </div>

        <el-divider />

        <div class="cct-example-section">
          <h4>示例二：付款授权控制偏差（系统性→控制缺陷）</h4>
          <div class="cct-example-flow">
            <div class="cct-example-step"><b>控制例外情况描述：</b>在30笔付款样本中，发现8笔大额付款（单笔≥50万元）仅有财务经理一人签字，缺少财务总监的复核签字。经调查发现系ERP系统5月升级后，付款审批流程中50万以上复核节点被误删除。</div>
            <div class="cct-example-step"><b>步骤一：</b>是（属于控制偏差—复核控制未执行）</div>
            <div class="cct-example-step"><b>步骤二：</b>系统性偏差（因系统参数错误导致一类交易反复出现偏差）</div>
            <div class="cct-example-step"><b>步骤五：</b>进入A14内控缺陷评价（评估为重要缺陷，影响5~8月所有大额付款）</div>
            <div class="cct-example-step"><b>结论：</b>属于控制缺陷，进入内控缺陷评价（路径C）</div>
          </div>
        </div>

        <el-divider />

        <div class="cct-example-section">
          <h4>示例三：控制例外非偏差（不构成缺陷）</h4>
          <div class="cct-example-flow">
            <div class="cct-example-step"><b>控制例外情况描述：</b>发现3笔销售退货单据的审批日期晚于退货入库日期2天。经调查为年末集中退货期间，审批人按时完成了实质性审核，系统中记录的审批日期为补录日期，实际审批凭纸质签字簿确认已在入库前完成。</div>
            <div class="cct-example-step"><b>步骤一：</b>否（不属于控制偏差—控制实质上已运行，仅系统记录时间差异）</div>
            <div class="cct-example-step"><b>步骤六：</b>否（不表明设计缺陷—控制设计合理，仅存在记录时点差异）</div>
            <div class="cct-example-step"><b>结论：</b>不构成偏差或缺陷，控制有效（路径A）</div>
          </div>
        </div>

        <el-divider />

        <div class="cct-example-section">
          <h4>示例四：设计缺陷（非偏差→设计问题）</h4>
          <div class="cct-example-flow">
            <div class="cct-example-step"><b>控制例外情况描述：</b>检查应收账款账龄分析报告生成控制时发现，系统仅按发票日期计算账龄，未考虑信用期调整。对账龄90天以上的应收款，有15%实际尚在信用期内被错误标记为逾期。</div>
            <div class="cct-example-step"><b>步骤一：</b>否（不属于运行偏差—系统按设计运行，是设计本身的问题）</div>
            <div class="cct-example-step"><b>步骤六：</b>是（表明设计缺陷—账龄计算逻辑未纳入信用期调整，可能导致减值准备计提不准确）</div>
            <div class="cct-example-step"><b>步骤五：</b>进入A14评价（评估为一般缺陷或重要缺陷，取决于对坏账准备的影响金额）</div>
            <div class="cct-example-step"><b>结论：</b>存在设计缺陷，进入内控缺陷评价（路径B）</div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ArrowLeft, WarningFilled, InfoFilled, Right, Document, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import http from '@/utils/http'
import {
  evaluateDecisionTree,
  getStepOptions,
  getStepQuestion,
  isStepVisible,
  type DecisionTreeState,
} from '@/composables/useDeviationDecisionTree'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpCode: string
  wpId?: string
  devIndex: number
  devState: DecisionTreeState
  controlName: string
  controlNames: string[]
  controlCount: number
  readonly: boolean
  updateDeviationStep: (devIndex: number, step: string, value: string | null) => void
  /** 缺陷回填汇总表 (Req 11.3) */
  writebackDefect?: (devIndex: number, defectSummary: string) => void
  /** 构造缺陷摘要 (Req 11.3) */
  buildDefectSummary?: (devIndex: number, conclusion: string) => string
  /** 控制例外描述 (持久化字段) */
  exceptionDesc?: string
  /** 例外描述变更回调 */
  updateExceptionDesc?: (devIndex: number, desc: string) => void
}>()

const emit = defineEmits<{
  (e: 'navigate', view: string): void
  (e: 'change-dev-index', index: number): void
}>()

// ─── 控制例外情况描述 ────────────────────────────────────────────────────────

const exceptionDescription = ref(props.exceptionDesc || '')

// 同步 prop 变化
watch(() => props.exceptionDesc, (v) => {
  if (v !== undefined) exceptionDescription.value = v
})

function handleExceptionDescBlur() {
  if (props.updateExceptionDesc) {
    props.updateExceptionDesc(props.devIndex, exceptionDescription.value)
  }
}

// ─── 示例参考 Drawer ─────────────────────────────────────────────────────────

const showExampleDrawer = ref(false)

// ─── AI 辅助生成例外情况描述 ─────────────────────────────────────────────────

const aiGeneratingException = ref(false)

async function handleAiGenerateException(): Promise<void> {
  if (props.readonly || aiGeneratingException.value) return
  aiGeneratingException.value = true
  try {
    const context: Record<string, string> = {}
    if (props.controlName) context['控制点名称'] = props.controlName
    if (props.wpCode) context['循环编码'] = props.wpCode
    if (exceptionDescription.value) context['现有描述'] = exceptionDescription.value

    const systemHint = '请根据以下控制点信息，生成一段专业的控制例外情况描述（80~150字），需包含：例外具体表现、涉及的交易金额或笔数、发生时间区间、影响范围。使用审计专业用语。'

    const wpId = props.wpId
    if (!wpId) {
      ElMessage.warning('AI服务暂不可用（缺少底稿ID）')
      return
    }

    const res = await http.post(
      `/api/workpapers/${wpId}/ai/generate-text`,
      {
        prompt: systemHint,
        context,
        existingContent: exceptionDescription.value || '',
        section: 'control-exception-description',
      },
      { _silent: true } as any,
    )
    const generated = res?.data?.data?.content || res?.data?.content || res?.data?.text || ''
    if (generated) {
      exceptionDescription.value = generated
      handleExceptionDescBlur() // 持久化
      ElMessage.success('AI已生成例外情况描述')
    } else {
      ElMessage.info('AI未返回内容，请手动填写')
    }
  } catch {
    ElMessage.warning('AI服务暂不可用，请手动填写')
  } finally {
    aiGeneratingException.value = false
  }
}
// ─── 决策树推导结果 ──────────────────────────────────────────────────────────

const treeResult = computed(() => evaluateDecisionTree(props.devState))

// ─── 缺陷摘要 (Req 11.3): GtIndexChip A14 context + 回填汇总表 ──────────────

/** 缺陷摘要：控制名称 + 偏差性质 + 结论 */
const defectContext = computed(() => {
  if (!treeResult.value.goToA14 || !treeResult.value.conclusion) return ''
  if (props.buildDefectSummary) {
    return props.buildDefectSummary(props.devIndex, treeResult.value.conclusion)
  }
  return `控制点：${props.controlName} — ${treeResult.value.conclusion}`
})

// 当推导至缺陷时自动回填汇总表
watch(
  () => treeResult.value.goToA14,
  (goToA14) => {
    if (goToA14 && treeResult.value.conclusion && props.writebackDefect) {
      const summary = defectContext.value || treeResult.value.conclusion
      props.writebackDefect(props.devIndex, summary)
    }
  },
  { immediate: true },
)

// ─── 步骤可见性 & 当前步骤判断 ───────────────────────────────────────────────

function isVisible(step: number): boolean {
  return isStepVisible(props.devState, step)
}

function isCurrentStep(step: number): boolean {
  return treeResult.value.currentStep === step && !treeResult.value.conclusion
}

function getQuestion(step: number): string {
  return getStepQuestion(step)
}

function getOptions(step: number) {
  return getStepOptions(step)
}

// ─── 步骤 tooltip（显示当前步骤 IF 逻辑来源）────────────────────────────────

/** 每步 tooltip：hover 显示源模板 IF 逻辑来源 */
function getStepTooltip(step: number): string {
  const tooltips: Record<number, string> = {
    1: 'IF 控制例外=偏差 → 步骤二（确定性质）；否 → 步骤六（设计缺陷评估）',
    2: 'IF 系统性/人为 → 步骤五（缺陷）；随机性 → 步骤三（扩大/认定）',
    3: 'IF 扩大样本量 → 步骤四；IF 直接认定 → 步骤五（缺陷）',
    4: 'IF 扩大后无新偏差 → 控制有效；有新偏差 → 步骤五（缺陷）',
    5: '决策树推导至控制缺陷，需进入A14内控缺陷评价底稿评估等级',
    6: 'IF 设计缺陷=是 → 回步骤五（缺陷）；否 → 不构成偏差或缺陷',
  }
  return tooltips[step] || ''
}

/** 选择后显示的指引文案 */
function getGuidanceAfterStep(step: number): string {
  const result = treeResult.value
  if (step === 1) {
    if (props.devState.step1 === '是') return '→ 请在步骤二确定偏差性质'
    if (props.devState.step1 === '否') return '→ 请在步骤六判断是否存在设计缺陷'
  }
  if (step === 2) {
    if (props.devState.step2 === '系统性偏差' || props.devState.step2 === '人为偏差') {
      return '→ 属于控制缺陷，进入步骤五评价'
    }
    if (props.devState.step2 === '随机性偏差') return '→ 请在步骤三选择应对措施'
  }
  if (step === 3) {
    if (props.devState.step3 === '直接认定为偏差') return '→ 直接认定缺陷，进入步骤五'
    if (props.devState.step3 === '扩大样本量') return '→ 请在步骤四判断扩大后结果'
  }
  if (step === 4) {
    if (props.devState.step4 === '否') return '→ 扩大后未发现新偏差，控制有效'
    if (props.devState.step4 === '是') return '→ 发现新偏差，控制无效，进入步骤五'
  }
  if (step === 6) {
    if (props.devState.step6 === '否') return '→ 不构成偏差或缺陷，控制有效'
    if (props.devState.step6 === '是') return '→ 存在设计缺陷，进入步骤五评价'
  }
  return result.nextStepHint || ''
}

// ─── 步骤选择变更 ────────────────────────────────────────────────────────────

function onStepChange(step: 'step1' | 'step2' | 'step3' | 'step4' | 'step6', value: string) {
  props.updateDeviationStep(props.devIndex, step, value)

  // 选择步骤一时，如果改变方向需要清空后续步骤
  if (step === 'step1') {
    if (value === '否') {
      // 清空 step2/3/4（保留 step6）
      props.updateDeviationStep(props.devIndex, 'step2', null)
      props.updateDeviationStep(props.devIndex, 'step3', null)
      props.updateDeviationStep(props.devIndex, 'step4', null)
    } else {
      // 清空 step6（保留 step2/3/4）
      props.updateDeviationStep(props.devIndex, 'step6', null)
    }
  }

  if (step === 'step2') {
    // 如果改为非随机性偏差，清空 step3/4
    if (value !== '随机性偏差') {
      props.updateDeviationStep(props.devIndex, 'step3', null)
      props.updateDeviationStep(props.devIndex, 'step4', null)
    }
  }

  if (step === 'step3') {
    // 如果改为直接认定，清空 step4
    if (value !== '扩大样本量') {
      props.updateDeviationStep(props.devIndex, 'step4', null)
    }
  }
}

// ─── 结论 badge 颜色 ─────────────────────────────────────────────────────────

const conclusionTagType = computed(() => {
  const conclusion = treeResult.value.conclusion || ''
  if (conclusion.includes('有效') || conclusion.includes('不构成')) return 'success'
  if (conclusion.includes('缺陷') || conclusion.includes('无效')) return 'danger'
  return 'warning'
})

function scrollToStep(step: number) {
  const el = document.getElementById(`cct-step-${step}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

defineExpose({ scrollToStep })
</script>

<style scoped>
.cct-decision-tree {
  font-size: 13px;
}

.cct-view-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.cct-view-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.cct-dev-subtitle {
  font-size: 14px;
  color: #6b7280;
}

/* ─── Selector ─── */
.cct-dev-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.cct-dev-selector-label {
  font-size: 13px;
  color: #6b7280;
}

/* ─── Steps Container ─── */
.cct-steps-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

/* ─── Step Card ─── */
.cct-step-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.cct-step-card.is-active {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.cct-step-card.cct-step-five {
  border-color: #e6a23c;
  background: #fdf6ec;
}

.cct-step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #f3f4f6;
}

.cct-step-five .cct-step-header {
  background: #fef0e0;
}

.cct-step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.cct-step-num-warning {
  background: #e6a23c;
}

.cct-step-question {
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
}

.cct-step-body {
  padding: 12px 16px 16px;
}

.cct-step-radio {
  display: block;
  margin-bottom: 8px;
}

.cct-step-radio:last-child {
  margin-bottom: 0;
}

/* ─── Step Guidance (after selection) ─── */
.cct-step-guidance {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 8px 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 4px;
  font-size: 12px;
  color: #0369a1;
}

.cct-step-guidance .el-icon {
  color: #0ea5e9;
  flex-shrink: 0;
}

/* ─── Step Info Tooltip Icon ─── */
.cct-step-info {
  color: #9ca3af;
  cursor: help;
  margin-left: auto;
  flex-shrink: 0;
  font-size: 14px;
  transition: color 0.15s;
}

.cct-step-info:hover {
  color: #6b7280;
}

/* ─── Step Five Content ─── */
.cct-step-five-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #92400e;
}

.cct-warning-icon {
  color: #e6a23c;
  font-size: 18px;
}

.cct-a14-chip {
  flex-shrink: 0;
}

/* ─── Conclusion Area ─── */
.cct-conclusion-area {
  margin-bottom: 20px;
}

.cct-conclusion-card {
  border-color: #d1d5db;
}

.cct-conclusion-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.cct-conclusion-content {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.cct-conclusion-label {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.cct-conclusion-badge {
  font-size: 13px;
}

.cct-conclusion-action {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #6b7280;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5e7eb;
}

/* ─── Footer ─── */
.cct-decision-footer {
  display: flex;
  justify-content: flex-start;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

/* ─── 编制提示 details 折叠 ─── */
.cct-compilation-tips {
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}

.cct-compilation-tips summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: #f9fafb;
  cursor: pointer;
  user-select: none;
}

.cct-compilation-tips summary:hover {
  background: #f3f4f6;
}

.cct-compilation-tips[open] summary {
  border-bottom: 1px solid #e5e7eb;
}

.cct-tips-content {
  padding: 12px 16px;
  font-size: 12px;
  color: #4b5563;
  line-height: 1.8;
}

.cct-tips-content p {
  margin: 0 0 4px;
}

/* ─── 控制例外描述区 ─── */
.cct-exception-desc {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.cct-exception-desc-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.cct-exception-desc-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.cct-exception-ai-btn {
  margin-left: auto;
}

/* ─── 步骤注释说明 ─── */
.cct-step-annotation {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  font-size: 12px;
  color: #475569;
  line-height: 1.7;
}

.cct-step-annotation-warning {
  background: #fffbeb;
  border-color: #fde68a;
  color: #78350f;
}

.cct-annotation-tag {
  display: inline-block;
  background: #e2e8f0;
  color: #334155;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  margin-right: 6px;
  vertical-align: middle;
}

.cct-step-annotation-warning .cct-annotation-tag {
  background: #fde68a;
  color: #78350f;
}

/* ─── 结论汇总卡片 ─── */
.cct-conclusion-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cct-conclusion-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.cct-conclusion-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cct-conclusion-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.cct-conclusion-row .cct-conclusion-label {
  font-weight: 500;
  color: #6b7280;
  min-width: 80px;
  flex-shrink: 0;
}

.cct-conclusion-row .cct-conclusion-value {
  color: #1f2937;
}

.cct-path-badge {
  display: inline-block;
  background: #e0e7ff;
  color: #3730a3;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

/* ─── 示例 Drawer ─── */
.cct-example-drawer-content {
  padding: 0 4px;
}

.cct-example-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 12px;
}

.cct-example-flow {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cct-example-step {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
  padding: 6px 10px;
  background: #f9fafb;
  border-left: 3px solid #93c5fd;
  border-radius: 0 4px 4px 0;
}

.cct-example-step b {
  color: #1e40af;
}
</style>
