<!--
  GtB1Evaluation.vue — B1-3 业务评价表（适用全部项目立项，含简化立项程序）

  一、业务基本信息 / 二、对客户的评价（诚信·经营·财务 + 高中低）/ 三、审计前提条件 /
  四、项目组独立性及胜任能力（方法论 + 是/否）/ 五、预计费用及可收回比率 /
  六、业务评价结论（关键要素 + 承接承做意见 可以承接/可以保持 + 签名）
-->
<template>
  <div class="gt-b1eval">
    <div class="gt-b1eval__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <el-tag type="success" effect="plain" size="small">业务评价表（立项）</el-tag>
      <span class="gt-b1eval__spacer" />
      <span class="gt-b1eval__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else>○ 未保存</template>
      </span>
    </div>

    <template v-if="mode === '结构化视图'">
    <el-alert v-if="riskAlert" type="warning" :closable="false" show-icon class="gt-b1eval__risk-alert">
      <template #title>{{ riskAlert }}</template>
    </el-alert>

    <template v-for="sec in sections" :key="sec.key">
      <!-- 一、基本信息 -->
      <el-card v-if="sec.key === 'basic'" shadow="never" class="gt-b1eval__card">
        <template #header><span class="gt-b1eval__title">{{ sec.title }}</span></template>
        <div class="gt-b1eval__basic-grid">
          <div v-for="f in sec.fields" :key="f.field" class="gt-b1eval__basic-item"
            :class="{ 'is-wide': f.type === 'textarea' }">
            <label>{{ f.label }}</label>
            <el-select v-if="f.type === 'choice'" :model-value="getVal('basic-' + f.field)" size="small"
              placeholder="选择" clearable @update:model-value="(v: string) => updateBasic(f.field, v)">
              <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
            </el-select>
            <el-input v-else-if="f.type === 'textarea'" :model-value="getVal('basic-' + f.field)" type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }" size="small" placeholder="请输入"
              @update:model-value="(v: string) => updateBasic(f.field, v)" />
            <el-input v-else :model-value="getVal('basic-' + f.field)" size="small" placeholder="请输入"
              @update:model-value="(v: string) => updateBasic(f.field, v)" />
          </div>
        </div>
      </el-card>

      <!-- 二、对客户的评价 -->
      <el-card v-else-if="sec.key === 'client_eval'" shadow="never" class="gt-b1eval__card">
        <template #header><span class="gt-b1eval__title">{{ sec.title }}</span></template>
        <div v-for="r in sec.rows" :key="r.id" class="gt-b1eval__client-row">
          <div class="gt-b1eval__row-head">
            <label>{{ r.label }}</label>
            <el-button v-if="r.type === 'textarea'" size="small" text type="primary"
              :loading="aiBusy === 'client-' + r.id" class="gt-b1eval__ai-btn"
              @click="aiClientDesc(r.id, r.label)">🤖 AI 辅助</el-button>
          </div>
          <el-input v-if="r.type === 'textarea'" :model-value="getVal('client-' + r.id)" type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }" size="small" placeholder="填写情况描述"
            @update:model-value="(v: string) => updateClientText(r.id, v)" />
          <div v-else class="gt-b1eval__risk-select">
            <el-radio-group :model-value="getVal('client-' + r.id)"
              @update:model-value="(v: string) => updateClientRisk(r.id, v)">
              <el-radio-button v-for="o in riskOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
            </el-radio-group>
            <el-tag v-if="getVal('client-' + r.id)" :type="riskTagType(getVal('client-' + r.id))" effect="dark" size="small">
              {{ riskLabel(getVal('client-' + r.id)) }}风险
            </el-tag>
            <el-tag
              v-if="r.id === 'overall_client_risk' && riskConsistency"
              :type="riskConsistency.mismatch ? 'warning' : 'success'"
              effect="plain"
              size="small"
            >
              {{ riskConsistency.mismatch
                ? `⚠️ 与 B1-1/B1-2 总体结论（${riskConsistency.raLabel}）不一致`
                : `✓ 与 B1-1/B1-2 总体结论一致` }}
            </el-tag>
            <el-tag
              v-if="r.id === 'overall_client_risk' && suggestedOverallRisk && !getVal('client-overall_client_risk')"
              type="info" effect="plain" size="small"
            >
              💡 建议：{{ suggestedOverallRisk === 'high' ? '高' : suggestedOverallRisk === 'medium' ? '中' : '低' }}风险（取三项最高档）
            </el-tag>
          </div>
        </div>
      </el-card>

      <!-- 三、前提条件 / 四、独立性（是否判断表）-->
      <el-card v-else-if="sec.key === 'precondition' || sec.key === 'independence'" shadow="never" class="gt-b1eval__card">
        <template #header><span class="gt-b1eval__title">{{ sec.title }}</span></template>
        <div v-if="sec.methodology" class="gt-b1eval__methodology">{{ sec.methodology }}</div>
        <div v-for="it in sec.items" :key="it.id" class="gt-b1eval__judge-row">
          <span class="gt-b1eval__judge-label">{{ it.label }}</span>
          <el-select
            :model-value="getVal((sec.key === 'precondition' ? 'pre-' : 'indep-') + it.id)"
            size="small" placeholder="判断" clearable class="gt-b1eval__judge-sel"
            :class="{ 'is-warn': isIndepIssue(sec.key, it.id) }"
            @update:model-value="(v: string) => (sec.key === 'precondition' ? updatePre(it.id, v) : updateIndep(it.id, v))"
          >
            <el-option v-for="o in judgeOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <el-input
            :model-value="getNote((sec.key === 'precondition' ? 'pre-' : 'indep-') + it.id)"
            size="small" placeholder="说明（可选）" class="gt-b1eval__judge-note"
            @update:model-value="(v: string) => (sec.key === 'precondition' ? updatePreNote(it.id, v) : updateIndepNote(it.id, v))"
          />
        </div>
      </el-card>

      <!-- 五、费用 -->
      <el-card v-else-if="sec.key === 'fee'" shadow="never" class="gt-b1eval__card">
        <template #header>
          <span class="gt-b1eval__title">{{ sec.title }}</span>
          <el-button size="small" text type="primary" :loading="aiBusy === 'fee'"
            class="gt-b1eval__ai-btn gt-b1eval__ai-header" @click="aiFee">🤖 AI 辅助</el-button>
        </template>
        <p v-if="sec.note" class="gt-b1eval__note-hint">{{ sec.note }}</p>
        <!-- 结构化费用字段 -->
        <div class="gt-b1eval__fee-grid">
          <div class="gt-b1eval__fee-item">
            <label>预计审计收费（万元）</label>
            <el-input-number :model-value="Number(feeStructured.estimatedFee) || undefined" size="small"
              :precision="2" :min="0" placeholder="收费"
              @update:model-value="(v: number | undefined) => updateFeeField('estimated_fee', String(v ?? ''))" />
          </div>
          <div class="gt-b1eval__fee-item">
            <label>预计成本（万元）</label>
            <el-input-number :model-value="Number(feeStructured.estimatedCost) || undefined" size="small"
              :precision="2" :min="0" placeholder="成本"
              @update:model-value="(v: number | undefined) => updateFeeField('estimated_cost', String(v ?? ''))" />
          </div>
          <div class="gt-b1eval__fee-item">
            <label>可收回比率（%）</label>
            <el-input-number :model-value="Number(feeStructured.recoverRate) || undefined" size="small"
              :precision="1" :min="0" :max="100" placeholder="比率"
              @update:model-value="(v: number | undefined) => updateFeeField('recover_rate', String(v ?? ''))" />
            <el-tag v-if="Number(feeStructured.recoverRate) > 0 && Number(feeStructured.recoverRate) < 70"
              type="warning" effect="plain" size="small">⚠️ 可收回比率偏低</el-tag>
          </div>
        </div>
        <el-divider content-position="left">详细说明</el-divider>
        <el-input :model-value="getVal('fee')" type="textarea" :autosize="{ minRows: 3 }"
          placeholder="说明预计审计收费、预计成本（含计算过程）、可收回比率等" @update:model-value="updateFee" />
      </el-card>

      <!-- 独立性预警（出现在结论卡之前，独立于 section 循环） -->

      <!-- 六、结论 -->
      <el-card v-else-if="sec.key === 'conclusion'" shadow="never" class="gt-b1eval__card">
        <template #header>
          <span class="gt-b1eval__title">{{ sec.title }}</span>
          <GtReviewTrigger section-id="b1eval-conclusion" label="💬 复核" />
        </template>
        <!-- 独立性预警 -->
        <el-alert
          v-if="independenceWarning"
          type="error"
          :closable="false"
          show-icon
          class="gt-b1eval__indep-warn"
        >
          <template #title>{{ independenceWarning }}</template>
        </el-alert>
        <div class="gt-b1eval__elem-label">（一）通过开展初步业务活动，对以下关键要素得出结论：</div>
        <div v-for="el in sec.key_elements" :key="el.id" class="gt-b1eval__elem-row">
          <div class="gt-b1eval__row-head">
            <label>{{ el.label }}</label>
            <el-button size="small" text type="primary" :loading="aiBusy === 'elem-' + el.id"
              class="gt-b1eval__ai-btn" @click="aiElem(el.id, el.label)">🤖 AI 辅助</el-button>
          </div>
          <el-input :model-value="getVal('elem-' + el.id)" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
            size="small" placeholder="结论" @update:model-value="(v: string) => updateElem(el.id, v)" />
        </div>
        <div class="gt-b1eval__elem-label">（二）承接承做意见</div>
        <div class="gt-b1eval__opinion-row">
          <el-radio-group :model-value="opinion" @update:model-value="updateOpinion">
            <el-radio-button v-for="o in opinionOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
          </el-radio-group>
          <el-tag v-if="currentOpinion" :type="currentOpinion.class as any" effect="dark" size="small">
            {{ currentOpinion.label }}
          </el-tag>
        </div>
        <div class="gt-b1eval__opinion-note-head">
          <span class="gt-b1eval__elem-label">承接承做意见说明</span>
          <el-button size="small" text type="primary" :loading="aiBusy === 'opinion-note'"
            class="gt-b1eval__ai-btn" @click="aiOpinionNote">🤖 AI 辅助</el-button>
        </div>
        <el-input :model-value="opinionNote" type="textarea" :autosize="{ minRows: 2 }"
          placeholder="承接承做意见说明" class="gt-b1eval__opinion-note" @update:model-value="updateOpinionNote" />
        <div class="gt-b1eval__sign-row">
          <div class="gt-b1eval__sign-item">
            <label>项目合伙人签名</label>
            <el-input :model-value="signPartner" size="small" placeholder="签名"
              @update:model-value="(v: string) => updateSign('partner', v)" />
          </div>
          <div class="gt-b1eval__sign-item">
            <label>日期</label>
            <el-date-picker :model-value="signDate" type="date" size="small" value-format="YYYY-MM-DD"
              placeholder="选择日期" @update:model-value="(v: string) => updateSign('date', v || '')" />
          </div>
        </div>
      </el-card>
    </template>
    </template>

    <!-- 在线编辑（OnlyOffice 降级） -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="wpId"
      :sheet-name="sourceSheet || '业务评价表B1-3'"
      :project-id="projectId"
      class="gt-b1eval__oo"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, provide, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { useB1Evaluation, EVAL_JUDGE_OPTIONS, type EvalRenderData } from './composables/useB1Evaluation'
import { useWpDualMode } from './composables/useWpDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import GtReviewTrigger from './GtReviewTrigger.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// 版本快照由 Runtime Boundary(GtWpRenderer) 提供的运行时上下文承载；复核对话由 GtReviewTrigger 自行 inject
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = () => runtime?.version?.scheduleAutoSnapshot?.()

defineOptions({ name: 'GtB1Evaluation' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: EvalRenderData | null
}>(), { projectId: '', htmlData: null })

const {
  saveStatus, sections, opinionOptions, riskOptions, opinion, opinionNote,
  signPartner, signDate, riskAlert, projectContext, riskAssessmentConclusion, getVal, getNote,
  updateBasic, updateClientText, updateClientRisk, updatePre, updatePreNote,
  updateIndep, updateIndepNote, updateFee, updateElem, updateOpinion,
  updateOpinionNote, updateSign, flushPendingSaves, loadData,
  suggestedOverallRisk, independenceWarning, feeStructured, updateFeeField,
  sourceSheet,
} = useB1Evaluation({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
  onAfterSave: () => scheduleAutoSnapshot?.(),
})

// 双模式：健康检查 + 切换前 flush（对齐 D4/GtB14 gold 范式）
const { mode, modeOptions, checkOOHealth } = useWpDualMode({ flush: flushPendingSaves })

const judgeOptions = EVAL_JUDGE_OPTIONS

// 复核线程蓝/红点（供后代 GtReviewTrigger/GtReviewDot inject）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId') as any)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const currentOpinion = computed(() => opinionOptions.value.find((o) => o.value === opinion.value))

// 综合客户风险 ↔ B1-1/B1-2 总体风险结论 一致性（两者都填时提示）
const riskConsistency = computed(() => {
  const ra = riskAssessmentConclusion.value
  const evalRisk = getVal('client-overall_client_risk')
  if (!ra || !evalRisk) return null
  const raLevel = ra.replace('_risk', '')
  const raCn: Record<string, string> = { low_risk: '低风险', medium_risk: '中风险', high_risk: '高风险' }
  return { mismatch: raLevel !== evalRisk, raLabel: raCn[ra] || ra }
})

// ─── AI 辅助 ───
const aiBusy = ref('')
async function callAi(section: string, prompt: string, existing: string, ctx: Record<string, string>): Promise<string> {
  const res = await api.post<any>(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    section, prompt, existingContent: existing || '', context: ctx,
  })
  return res?.content || res?.data?.content || res?.text || ''
}
function baseCtx(): Record<string, string> {
  return {
    客户名称: getVal('basic-client_name') || projectContext.value.client_name || '',
    所属行业: getVal('basic-industry') || projectContext.value.industry || '',
    业务分类: getVal('basic-business_class') || '',
  }
}
async function aiClientDesc(rowId: string, label: string) {
  aiBusy.value = 'client-' + rowId
  try {
    const text = await callAi(
      'b1-3-client-eval',
      `撰写业务承接阶段对客户的"${label}"，简述客户情况并为后续高/中/低风险评价提供依据`,
      getVal('client-' + rowId),
      baseCtx(),
    )
    if (text) { updateClientText(rowId, text); ElMessage.success('AI 已生成') }
    else ElMessage.warning('AI 未返回内容')
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiBusy.value = '' }
}
async function aiFee() {
  aiBusy.value = 'fee'
  try {
    const text = await callAi(
      'b1-3-fee',
      '撰写预计审计收费、预计成本（含人力投入计算过程）及可收回比率的说明',
      getVal('fee'),
      { ...baseCtx(), 初步商谈收费: getVal('basic-prelim_fee') || '' },
    )
    if (text) { updateFee(text); ElMessage.success('AI 已生成') }
    else ElMessage.warning('AI 未返回内容')
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiBusy.value = '' }
}
async function aiElem(elemId: string, label: string) {
  aiBusy.value = 'elem-' + elemId
  try {
    const ctx: Record<string, string> = {
      ...baseCtx(),
      结论要素: label,
      客户综合风险: riskLabel(getVal('client-overall_client_risk')),
      独立性存在问题: getVal('indep-has_independence_issue') || '未填',
    }
    const text = await callAi(
      'b1-3-key-element',
      `针对业务评价关键要素"${label}"，结合客户风险评价与前提条件，撰写简明结论`,
      getVal('elem-' + elemId),
      ctx,
    )
    if (text) { updateElem(elemId, text); ElMessage.success('AI 已生成') }
    else ElMessage.warning('AI 未返回内容')
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiBusy.value = '' }
}
async function aiOpinionNote() {
  aiBusy.value = 'opinion-note'
  try {
    const ctx: Record<string, string> = {
      ...baseCtx(),
      客户诚信风险: riskLabel(getVal('client-integrity_risk')),
      客户经营风险: riskLabel(getVal('client-operation_risk')),
      客户财务风险: riskLabel(getVal('client-financial_risk')),
      综合风险: riskLabel(getVal('client-overall_client_risk')),
      独立性存在问题: getVal('indep-has_independence_issue') || '未填',
      承接承做意见: currentOpinion.value?.label || '未选择',
    }
    const text = await callAi(
      'b1-3-opinion',
      '综合客户风险评价、审计前提条件、独立性与专业胜任能力，撰写承接承做意见说明',
      opinionNote.value,
      ctx,
    )
    if (text) { updateOpinionNote(text); ElMessage.success('AI 已生成') }
    else ElMessage.warning('AI 未返回内容')
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiBusy.value = '' }
}

function riskTagType(v: string): string {
  return v === 'high' ? 'danger' : v === 'medium' ? 'warning' : 'success'
}
function riskLabel(v: string): string {
  return v === 'high' ? '高' : v === 'medium' ? '中' : '低'
}
function isIndepIssue(sk: string, itemId: string): boolean {
  return sk === 'independence' && itemId === 'has_independence_issue' && getVal('indep-' + itemId) === '是'
}

onMounted(async () => { checkOOHealth(); if (!props.htmlData) await loadData() })
onBeforeUnmount(() => { flushPendingSaves() })
</script>

<style scoped>
/* ── 统一字号 13px + 视觉语言 ── */
.gt-b1eval { display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: var(--el-text-color-primary); }
.gt-b1eval :deep(.el-input__inner),
.gt-b1eval :deep(.el-textarea__inner),
.gt-b1eval :deep(.el-radio-button__inner),
.gt-b1eval :deep(.el-table) { font-size: 13px; }
.gt-b1eval__toolbar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.gt-b1eval__spacer { flex: 1; }
.gt-b1eval__save-status { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1eval__risk-alert :deep(.el-alert__title) { font-size: 13px; }

/* ── 卡片统一：primary 左强调条 + 渐变标题栏 ── */
.gt-b1eval :deep(.el-card) { border-radius: 8px; border-color: var(--el-border-color-lighter); }
.gt-b1eval__card :deep(.el-card__header) {
  padding: 9px 14px;
  background: linear-gradient(90deg, var(--el-color-primary-light-9), transparent 70%);
  border-left: 3px solid var(--el-color-primary);
  display: flex; align-items: center; justify-content: space-between;
}
.gt-b1eval__card :deep(.el-card__body) { padding: 14px; }
.gt-b1eval__title { font-weight: 600; font-size: 13px; }
.gt-b1eval__basic-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 20px; }
.gt-b1eval__basic-item { display: flex; flex-direction: column; gap: 4px; }
.gt-b1eval__basic-item.is-wide { grid-column: 1 / -1; }
.gt-b1eval__basic-item label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1eval__client-row { display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.gt-b1eval__client-row:last-child { border-bottom: none; }
.gt-b1eval__client-row > label { font-size: 13px; font-weight: 500; }
.gt-b1eval__row-head { display: flex; align-items: center; justify-content: space-between; }
.gt-b1eval__row-head > label { font-size: 13px; font-weight: 500; }
.gt-b1eval__ai-btn { padding: 2px 6px; }
.gt-b1eval__ai-header { margin-left: auto; }
.gt-b1eval__opinion-note-head { display: flex; align-items: center; justify-content: space-between; }
.gt-b1eval__risk-select { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-b1eval__methodology { font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); background: var(--el-color-warning-light-9); border-left: 3px solid var(--el-color-warning); padding: 9px 12px; border-radius: 4px; margin-bottom: 10px; }
.gt-b1eval__judge-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.gt-b1eval__judge-row:last-child { border-bottom: none; }
.gt-b1eval__judge-label { flex: 1; font-size: 13px; line-height: 1.6; }
.gt-b1eval__judge-sel { flex: 0 0 104px; }
.gt-b1eval__judge-sel.is-warn :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px var(--el-color-danger) inset; }
.gt-b1eval__judge-note { flex: 0 0 220px; }
.gt-b1eval__note-hint { margin: 0 0 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1eval__elem-label { font-size: 13px; font-weight: 600; margin: 10px 0 6px; color: var(--el-color-primary); }
.gt-b1eval__elem-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.gt-b1eval__elem-row > label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1eval__opinion-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.gt-b1eval__opinion-note { margin-bottom: 10px; }
.gt-b1eval__sign-row { display: flex; gap: 24px; flex-wrap: wrap; padding-top: 6px; border-top: 1px solid var(--el-border-color-lighter); }
.gt-b1eval__sign-item { display: flex; align-items: center; gap: 8px; }
.gt-b1eval__sign-item label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1eval__fee-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 16px; margin-bottom: 10px; }
.gt-b1eval__fee-item { display: flex; flex-direction: column; gap: 4px; }
.gt-b1eval__fee-item label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1eval__indep-warn { margin-bottom: 10px; }
.gt-b1eval__indep-warn :deep(.el-alert__title) { font-size: 13px; font-weight: 500; }
.gt-b1eval__oo { min-height: 600px; }
</style>
