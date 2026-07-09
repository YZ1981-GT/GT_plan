<template>
  <div class="i1-tab-policy-check">
    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 逐项检查摊销方法/使用寿命/残值率/减值迹象/测试频率</div>
        <div class="guide-step"><span class="step-num">②</span> 对照CAS6+CAS8准则条款判断政策适当性</div>
        <div class="guide-step"><span class="step-num">③</span> 每项勾选结论：是/否/不适用</div>
        <div class="guide-step"><span class="step-num">④</span> 结论为"否"时必须填写原因及影响评估</div>
      </div>
    </div>

    <!-- ═══ 琥珀色方法论上下文（CAS6+CAS8） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>CAS6无形资产 关键条款：</strong>
        使用寿命有限的无形资产，应当在使用寿命内系统合理摊销（§17）；
        摊销方法包括直线法、产量法等，无法可靠确定消耗方式的应采用直线法（§19）；
        残值通常为零，除非有第三方承诺购买或存在活跃市场（§16）。
        <br />
        <strong>CAS8资产减值 关键条款：</strong>
        资产存在减值迹象时应进行减值测试（§4）；
        使用寿命不确定的无形资产，无论是否存在减值迹象，至少每年进行减值测试（§6）；
        可收回金额为公允价值减处置费用与预计未来现金流量现值两者之间的较高者（§8）。
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <el-progress :percentage="completionPct" :stroke-width="10" :format="() => `${completedCount}/${totalCount}`" />
    </div>

    <!-- ═══ 检查项卡片列表 ═══ -->
    <el-card
      v-for="(item, idx) in checkItems"
      :key="item.key"
      shadow="never"
      class="check-card"
      :class="{ 'check-card-done': item.conclusion === '是' || item.conclusion === '不适用' }"
    >
      <template #header>
        <div class="section-title">
          <span class="check-title">{{ idx + 1 }}. {{ item.label }}</span>
          <div class="title-actions">
            <el-tag v-if="item.conclusion" :type="getConclusionTagType(item.conclusion)" size="small">
              {{ item.conclusion }}
            </el-tag>
            <el-button size="small" type="primary" link @click="handleAiGenerate(item.key)" :disabled="isReadonly">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview(`I1-4-${item.key}`)">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 准则条款引用 -->
      <div class="cas-reference">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ item.casRef }}</span>
      </div>

      <!-- 被审计单位实际政策 -->
      <div class="field-group">
        <label>被审计单位实际政策：</label>
        <el-input
          v-model="item.actualPolicy"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="描述被审计单位就此方面的实际会计政策..."
          @blur="handleItemSave(item)"
        />
      </div>

      <!-- 审计师评价 -->
      <div class="field-group">
        <label>审计师评价：</label>
        <el-input
          v-model="item.evaluation"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="评价该政策是否符合准则要求..."
          @blur="handleItemSave(item)"
        />
      </div>

      <!-- 勾选结论 -->
      <div class="field-group conclusion-group">
        <label>结论：</label>
        <el-radio-group v-model="item.conclusion" :disabled="isReadonly" @change="handleItemSave(item)">
          <el-radio value="是">是</el-radio>
          <el-radio value="否">否</el-radio>
          <el-radio value="不适用">不适用</el-radio>
        </el-radio-group>
      </div>

      <!-- 否时强制说明 -->
      <div v-if="item.conclusion === '否'" class="field-group n-explanation">
        <label>不符合原因及影响：</label>
        <el-input
          v-model="item.explanationIfNo"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="必须说明不符合准则的具体原因和对审计的潜在影响..."
          @blur="handleItemSave(item)"
        />
        <el-alert v-if="!item.explanationIfNo" type="error" :closable="false" show-icon>
          结论为"否"时必须填写原因说明
        </el-alert>
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>政策检查总体结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('overall-conclusion')" :disabled="isReadonly">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="无形资产摊销减值政策检查总体结论..."
        @blur="handleConclusionSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS6第17条：使用寿命有限的无形资产自达到预定用途之日起摊销</li>
        <li>CAS6第19条：摊销方法应反映经济利益预期消耗方式，无法可靠确定时用直线法</li>
        <li>CAS6第16条：残值通常为零，有第三方购买承诺或活跃市场除外</li>
        <li>CAS8第4条：每年末评估是否存在减值迹象（技术陈旧/市场变化/法律限制等）</li>
        <li>CAS8第6条：使用寿命不确定的无形资产每年必须做减值测试</li>
        <li>关注前后期摊销政策一致性；政策变更须按CAS28处理</li>
        <li>结论为"否"时须评估对报表的影响并考虑调整分录</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabPolicyCheck.vue — I1-4 无形资产摊销减值政策检查表
 *
 * 段落型检查组件（非表格主导）。逐项对照CAS6/CAS8检查摊销+减值政策适当性。
 * 每个检查项包含：准则引用 → 被审计单位政策 → 审计师评价 → 结论(是/否/不适用)。
 *
 * Storage: "I1-4-{checkItem}" item_ids in checklist_responses
 * Requirements: Req 5.1~5.4
 */
import { ref, reactive, computed, watch, inject, onMounted } from 'vue'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Props & Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'save': [itemId: string, value: any]
}>()

// ─── Inject ───────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Check Items Definition ───────────────────────────────────────────────────

interface CheckItem {
  key: string
  label: string
  casRef: string
  actualPolicy: string
  evaluation: string
  conclusion: string
  explanationIfNo: string
}

const CHECK_ITEM_DEFS: Omit<CheckItem, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfNo'>[] = [
  {
    key: 'amort-method',
    label: '摊销方法',
    casRef: 'CAS6§19：摊销方法应反映与该项无形资产有关的经济利益预期消耗方式。无法可靠确定预期消耗方式的，应当采用直线法。'
  },
  {
    key: 'useful-life',
    label: '使用寿命确定',
    casRef: 'CAS6§11-15：企业应判断无形资产使用寿命是有限还是不确定。寿命有限的，估计期限或构成寿命的产量等类似计量单位数量；寿命不确定的，每期末复核。'
  },
  {
    key: 'salvage-rate',
    label: '残值率确定',
    casRef: 'CAS6§16：残值通常为零，除非有第三方承诺在使用寿命结束时购买该项无形资产，或可从活跃市场获得残值信息且该市场在寿命结束时很可能存在。'
  },
  {
    key: 'impairment-indication',
    label: '减值迹象判断',
    casRef: 'CAS8§4-5：企业每年末应判断是否存在减值迹象（含技术陈旧/市场变化/经济环境变化/法律限制/净现金流持续恶化/内部报告显示经济绩效低于预期等）。'
  },
  {
    key: 'impairment-test-frequency',
    label: '减值测试频率',
    casRef: 'CAS8§6：使用寿命不确定的无形资产和尚未达到可使用状态的无形资产，无论是否存在减值迹象，每年至少进行一次减值测试。'
  },
  {
    key: 'amort-start-date',
    label: '摊销起始时点',
    casRef: 'CAS6§17：无形资产自达到预定用途之日起开始摊销。处置当月不再摊销。如系月中达到预定用途，按天数/整月不同企业可选择一致性方法。'
  },
  {
    key: 'amort-period-review',
    label: '摊销期限/方法复核',
    casRef: 'CAS6§21-22：企业至少每年末复核无形资产使用寿命和摊销方法。寿命及方法与以前估计不同的，应调整摊销期限和方法（会计估计变更，未来适用法）。'
  },
]

// ─── Reactive State ───────────────────────────────────────────────────────────

const checkItems = reactive<CheckItem[]>(
  CHECK_ITEM_DEFS.map(def => ({
    ...def,
    actualPolicy: '',
    evaluation: '',
    conclusion: '',
    explanationIfNo: '',
  }))
)

const overallConclusion = ref('')

// ─── Computed ─────────────────────────────────────────────────────────────────

const totalCount = computed(() => checkItems.length)
const completedCount = computed(() => checkItems.filter(item => !!item.conclusion).length)
const completionPct = computed(() => totalCount.value === 0 ? 0 : Math.round((completedCount.value / totalCount.value) * 100))

// ─── Data Load ────────────────────────────────────────────────────────────────

function loadFromResponses() {
  const responses = props.allResponses
  if (!responses || responses.size === 0) return

  for (const item of checkItems) {
    const prefix = `I1-4-${item.key}`
    const saved = responses.get(prefix)
    if (saved) {
      try {
        const data = typeof saved === 'string' ? JSON.parse(saved) : saved
        item.actualPolicy = data.actualPolicy || ''
        item.evaluation = data.evaluation || ''
        item.conclusion = data.conclusion || ''
        item.explanationIfNo = data.explanationIfNo || ''
      } catch { /* ignore parse errors */ }
    }
  }

  const conclusionData = responses.get('I1-4-overall-conclusion')
  if (conclusionData) {
    overallConclusion.value = typeof conclusionData === 'string' ? conclusionData : (conclusionData?.text || '')
  }
}

watch(() => props.allResponses, loadFromResponses, { immediate: true })

// ─── Save Handlers ────────────────────────────────────────────────────────────

function handleItemSave(item: CheckItem) {
  const itemId = `I1-4-${item.key}`
  const value = {
    actualPolicy: item.actualPolicy,
    evaluation: item.evaluation,
    conclusion: item.conclusion,
    explanationIfNo: item.explanationIfNo,
  }
  emit('save', itemId, JSON.stringify(value))
}

function handleConclusionSave() {
  emit('save', 'I1-4-overall-conclusion', overallConclusion.value)
}

// ─── AI Generate ──────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string) {
  try {
    const context = section === 'overall-conclusion'
      ? `政策检查项完成情况: ${completedCount.value}/${totalCount.value}, 各项结论: ${checkItems.map(i => `${i.label}=${i.conclusion || '未填'}`).join('; ')}`
      : `检查项: ${checkItems.find(i => i.key === section)?.label || section}`

    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: section === 'overall-conclusion'
        ? '根据各项政策检查结论，生成摊销减值政策检查的总体审计结论。'
        : `根据CAS6/CAS8准则，对无形资产"${checkItems.find(i => i.key === section)?.label}"进行评价。`,
      context,
      section: `I1-4-${section}`,
    })

    if (res.data?.data?.content) {
      if (section === 'overall-conclusion') {
        overallConclusion.value = res.data.data.content
        handleConclusionSave()
      } else {
        const item = checkItems.find(i => i.key === section)
        if (item) {
          item.evaluation = res.data.data.content
          handleItemSave(item)
        }
      }
      ElMessage.success('AI生成完成')
    }
  } catch {
    ElMessage.warning('AI生成暂不可用')
  }
}

// ─── Review Dialog ────────────────────────────────────────────────────────────

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getConclusionTagType(conclusion: string): 'success' | 'danger' | 'info' {
  if (conclusion === '是') return 'success'
  if (conclusion === '否') return 'danger'
  return 'info'
}
</script>

<style scoped>
.i1-tab-policy-check { padding: 16px; font-size: 13px; }

/* ─── 蓝色渐变引导区 ─── */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 0 6px 6px 0;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.methodology-text {
  font-size: 12px;
  color: #7d5b1e;
  line-height: 1.6;
}
.methodology-text strong {
  display: inline-block;
  margin-top: 4px;
}

/* ─── 进度条 ─── */
.progress-section { margin-bottom: 16px; }

/* ─── 检查项卡片 ─── */
.check-card { margin-bottom: 12px; }
.check-card-done { border-left: 3px solid var(--el-color-success); }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.check-title { font-weight: 500; }
.title-actions { display: flex; align-items: center; gap: 8px; }

/* ─── 准则引用 ─── */
.cas-reference {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

/* ─── 字段组 ─── */
.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; }
.n-explanation {
  border-left: 3px solid var(--el-color-danger);
  padding-left: 12px;
}

/* ─── 结论卡片 ─── */
.conclusion-card { margin-bottom: 12px; }

/* ─── 编制提示 ─── */
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
