<template>
  <div class="h3-tab-policy-check">
    <!-- 整体进度条 -->
    <el-progress :percentage="progressPct" :stroke-width="8" class="progress-bar" />

    <!-- CAS3 五段落卡片 -->
    <el-card v-for="(para, idx) in paragraphs" :key="para.key" shadow="never" class="policy-card">
      <template #header>
        <div class="section-title">
          <span>{{ `(${idx + 1}) ${para.title}` }}</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI(para.key)">AI</el-button>
            <el-button size="small" circle @click="openReview(para.key)">💬</el-button>
          </span>
        </div>
      </template>

      <!-- 计量模式突出显示（仅第2段） -->
      <div v-if="para.key === 'measurement'" class="mode-highlight">
        <el-tag :type="measurementModel === 'cost' ? 'info' : 'warning'" size="large">
          当前项目采用：{{ measurementModel === 'cost' ? '成本模式' : '公允价值模式' }}
        </el-tag>
      </div>

      <!-- 准则条款引用（折叠） -->
      <details class="standard-ref">
        <summary>准则条款引用</summary>
        <p class="ref-text">{{ para.standardRef }}</p>
      </details>

      <!-- 实际政策 -->
      <div class="field-group">
        <label class="field-label">实际政策：</label>
        <el-input
          v-model="policyTexts[para.key]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请描述企业实际采用的政策..."
          :disabled="isReadonly"
          @change="onTextChange(para.key, 'policy')"
        />
      </div>

      <!-- 审计师评价 -->
      <div class="field-group">
        <label class="field-label">审计师评价：</label>
        <el-input
          v-model="evaluationTexts[para.key]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计评价..."
          :disabled="isReadonly"
          @change="onTextChange(para.key, 'evaluation')"
        />
      </div>

      <!-- 段落结论 -->
      <div class="conclusion-row">
        <span class="conclusion-label">结论：</span>
        <el-radio-group v-model="conclusions[para.key]" :disabled="isReadonly" @change="onConclusionChange(para.key)">
          <el-radio-button value="Y">Y（适当）</el-radio-button>
          <el-radio-button value="N">N（不适当）</el-radio-button>
          <el-radio-button value="NA">N/A</el-radio-button>
        </el-radio-group>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabPolicyCheck.vue — H3-4 会计政策检查
 * CAS3五段落卡片+计量模式突出+进度条+AI+💬复核
 */
import { ref, reactive, computed, inject, toRef } from 'vue'
import { useH3PolicyCheck } from '../../composables/useH3PolicyCheck'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: toRef(props, 'measurementModel') as any,
})

const {
  policyTexts, evaluationTexts, conclusions, progressPct,
  updatePolicyText, updateEvaluationText, updateConclusion,
} = useH3PolicyCheck({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
  measurementModel: toRef(props, 'measurementModel') as any,
})

interface Paragraph {
  key: string
  title: string
  standardRef: string
}

const paragraphs: Paragraph[] = [
  { key: 'recognition', title: '投资性房地产确认条件', standardRef: 'CAS3第3条：投资性房地产是指为赚取租金或资本增值，或两者兼有而持有的房地产。包括已出租的土地使用权、持有并准备增值后转让的土地使用权、已出租的建筑物。' },
  { key: 'measurement', title: '计量模式选择（成本/公允价值）', standardRef: 'CAS3第10-11条：企业应当在成本模式和公允价值模式之间进行选择。采用公允价值模式的，应当同时满足：(1)有活跃房地产交易市场；(2)能够从该市场取得同类或类似房地产价格及相关信息，从而对公允价值作出合理估计。' },
  { key: 'subsequent', title: '后续计量政策', standardRef: 'CAS3第12-14条：成本模式下按固定资产/无形资产准则计提折旧/摊销及减值；公允价值模式下不计提折旧/摊销，以资产负债表日公允价值为基础调整账面价值，变动计入当期损益。' },
  { key: 'conversion', title: '转换政策', standardRef: 'CAS3第15-18条：投资性房地产与自用房地产/存货之间的转换，应当在用途发生改变时转换。转换日为租赁期开始日/自用开始日/资本化条件满足日。' },
  { key: 'disposal', title: '处置政策', standardRef: 'CAS3第19-20条：投资性房地产被处置或永久退出使用且预计不能从其处置中取得经济利益时，应当终止确认。处置收入扣除其账面价值和相关税费后的差额计入当期损益。' },
]

function onTextChange(key: string, type: 'policy' | 'evaluation') {
  if (type === 'policy') updatePolicyText(key, policyTexts[key])
  else updateEvaluationText(key, evaluationTexts[key])
}
function onConclusionChange(key: string) {
  updateConclusion(key, conclusions[key])
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section: `H3-4-${section}`, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(`H3-4-${section}`) }
</script>

<style scoped>
.h3-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.progress-bar { margin-bottom: 16px; }
.policy-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.mode-highlight { margin-bottom: 12px; }
.standard-ref { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.standard-ref summary { cursor: pointer; font-weight: 500; }
.ref-text { margin-top: 6px; padding: 8px; background: var(--el-fill-color-lighter); border-radius: 4px; line-height: 1.6; }
.field-group { margin-bottom: 12px; }
.field-label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-row { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.conclusion-label { font-weight: 500; }
</style>
