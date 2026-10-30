<!--
  GenerationPlanDialog — 按粗裁结果生成底稿（spec trim-generation-plan-linkage R2）

  底稿列表页与程序裁剪页共用。只读后端生成计划（与生成接口同一判定）：按循环汇总粗裁状态与
  将生成 / 已生成 / 在回收站 / 已裁剪 / 业务分类不生成；只能按循环勾选，逐个底稿的排除走程序裁剪页。
  「去程序裁剪」只 emit navigate-cycle，由宿主决定怎么跳（裁剪页要先过未保存修改确认）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="生成底稿"
    width="min(900px, 96vw)"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!generating"
    :show-close="!generating"
    @update:model-value="requestClose($event)"
  >
    <div v-loading="loading" class="gt-gen-plan">
      <div class="gt-gen-plan__head">
        <span class="gt-gen-plan__label">模板集</span>
        <el-select v-model="templateSetId" size="small" style="width: 200px" :disabled="loading || generating"
                   placeholder="选择模板集" @change="loadPlan">
          <el-option v-for="s in templateSets" :key="s.id" :label="s.set_name" :value="s.id" />
        </el-select>
        <span v-if="plan" class="gt-gen-plan__meta">业务分类：{{ categoryText }}</span>
        <span class="gt-gen-plan__meta">审计年度：{{ year ?? '未设置' }}</span>
      </div>

      <el-alert v-if="canSubmit === false" type="info" :title="disabledReason || '当前项目状态已变化，不能生成底稿'"
                :closable="false" show-icon class="gt-gen-plan__alert" />
      <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="gt-gen-plan__alert" />
      <template v-else-if="plan">
        <el-alert v-if="pending.length" type="warning" :closable="false" show-icon class="gt-gen-plan__alert">
          <template #title>
            {{ pending.length }} 个循环的程序裁剪还没保存过，这些循环先按业务分类默认生成；建议先去程序裁剪确认
          </template>
          <div class="gt-gen-plan__pending">
            <el-button v-for="c in pending" :key="c.cycle" size="small" link type="primary"
                       :disabled="generating" :aria-label="`前往${cycleLabel(c.cycle)}程序裁剪`" @click="goTrim(c.cycle)">
              {{ cycleLabel(c.cycle) }}（{{ trimStateText(c) }}）→
            </el-button>
          </div>
        </el-alert>

        <div class="gt-gen-plan__toolbar">
          <el-checkbox :model-value="allSelected" :indeterminate="someSelected" :disabled="!selectable.length || generating"
                       @change="toggleAll">全选可生成的循环</el-checkbox>
          <span class="gt-gen-plan__hint">只能按循环选择；某个底稿不需要，请到程序裁剪页带理由裁掉</span>
        </div>

        <div class="gt-gen-plan__list">
          <div class="gt-gen-plan__row gt-gen-plan__row--head">
            <span /><span>循环</span><span>粗裁</span><span>程序 保留 / 裁掉</span><span>将生成</span>
            <span>已生成</span><span>在回收站</span><span>已裁剪</span><span>业务分类不生成</span><span />
          </div>
          <template v-for="c in cycles" :key="c.cycle">
            <div class="gt-gen-plan__row" :class="{ 'is-disabled': !isCycleSelectable(c) }">
              <el-checkbox :model-value="selected.has(c.cycle)" :disabled="!isCycleSelectable(c) || generating"
                           :aria-label="`选择${cycleLabel(c.cycle)}循环`"
                           @change="toggleCycle(c.cycle, !!$event)" />
              <span class="gt-gen-plan__cycle">{{ cycleLabel(c.cycle) }}</span>
              <span><el-tag size="small" :type="c.trim_state === 'confirmed' ? 'success' : 'warning'" effect="plain">
                {{ trimStateText(c) }}</el-tag></span>
              <span>{{ programCounts(c).kept }} / {{ programCounts(c).cut }}</span>
              <span class="is-create">{{ c.counts.to_create }}</span>
              <span>{{ c.counts.existing }}</span>
              <span>{{ c.counts.in_recycle }}</span>
              <span>{{ c.counts.trimmed }}</span>
              <span>{{ c.counts.category_excluded }}</span>
              <span class="gt-gen-plan__ops">
                <el-button link size="small" :aria-label="`${expanded.has(c.cycle) ? '收起' : '展开'}${cycleLabel(c.cycle)}明细`"
                           :aria-expanded="expanded.has(c.cycle)" @click="toggleExpand(c.cycle)">{{ expanded.has(c.cycle) ? '收起' : '明细' }}</el-button>
                <el-button link type="primary" size="small" :disabled="generating"
                           :aria-label="`前往${cycleLabel(c.cycle)}程序裁剪`" @click="goTrim(c.cycle)">去程序裁剪</el-button>
              </span>
            </div>
            <div v-if="expanded.has(c.cycle)" class="gt-gen-plan__detail">
              <div v-if="conflictCount(c)" class="gt-gen-plan__conflict">
                {{ conflictCount(c) }} 个底稿按业务分类不适用，但程序裁剪保存为执行，会照常生成
              </div>
              <div v-for="g in groupItemsByProgram(c)" :key="g.key" class="gt-gen-plan__group">
                <div class="gt-gen-plan__group-title">
                  {{ g.label }}
                  <el-tag v-if="g.status" size="small" :type="g.status === 'execute' ? 'success' : 'danger'" effect="plain">
                    {{ g.status === 'execute' ? '执行' : '已裁剪' }}</el-tag>
                </div>
                <div class="gt-gen-plan__items">
                  <el-tooltip v-for="it in g.items" :key="it.wp_code" :content="itemTip(it)" placement="top">
                    <el-tag size="small" :type="ITEM_STATE_META[it.state].tag" effect="plain" class="gt-gen-plan__item">
                      {{ it.wp_code }} {{ it.wp_name }} · {{ ITEM_STATE_META[it.state].text }}
                    </el-tag>
                  </el-tooltip>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </div>

    <template #footer>
      <span class="gt-gen-plan__summary">已选 {{ summary.cycles }} 个循环，将生成 {{ summary.codes }} 个底稿</span>
      <el-button :disabled="generating" @click="requestClose(false)">取消</el-button>
      <el-button type="primary" :loading="generating" :disabled="!canGenerate" @click="onGenerate">
        生成 {{ summary.codes }} 个底稿
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { TemplateSetItem } from '@/services/workpaperApi'
import {
  getGenerationOperation, getGenerationPlan, listGenerationTemplateSets, operationReceipt,
  planErrorText, runGenerationOperation,
  type GenerationPlan, type PlanCycle, type PlanItem,
} from '@/services/generationPlanApi'
import {
  clearGenerationOperation,
  generationRequestKey,
  loadGenerationOperation,
  newGenerationOperationId,
  rememberGenerationOperation,
} from '@/services/generationOperationStore'
import { handleApiError } from '@/utils/errorHandler'
import { summarizeWorkpaperGenerateResult, type WorkpaperGenerateResult } from '@/utils/workpaperGenerateResult'
import {
  ITEM_STATE_META, codesToGenerate, cycleLabel, defaultSelectedCycles, groupItemsByProgram, isCycleSelectable,
  orderCycles, pendingTrimCycles, selectedSummary, trimStateText,
} from './generationPlanModel'

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: string
  year: number | null
  /** 打开后权限 / 归档状态变化时由宿主实时禁用提交。 */
  canSubmit?: boolean
  disabledReason?: string
  /** 只默认勾这个循环（程序裁剪页传当前循环） */
  initialCycle?: string | null
}>(), {
  canSubmit: true,
  disabledReason: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  generated: [result: WorkpaperGenerateResult]
  'navigate-cycle': [cycle: string]
}>()

const templateSets = ref<TemplateSetItem[]>([])
const templateSetId = ref('')
const plan = ref<GenerationPlan | null>(null)
const error = ref('')
const loading = ref(false)
const generating = ref(false)
const selected = ref(new Set<string>())
const expanded = ref(new Set<string>())
let seq = 0
let openEpoch = 0

const cycles = computed(() => orderCycles(plan.value?.cycles ?? []))
const selectable = computed(() => cycles.value.filter(isCycleSelectable).map((c) => c.cycle))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every((c) => selected.value.has(c)))
const someSelected = computed(() => !allSelected.value && selectable.value.some((c) => selected.value.has(c)))
const pending = computed(() => orderCycles(pendingTrimCycles(plan.value)))
const summary = computed(() => selectedSummary(plan.value, selected.value))
const canGenerate = computed(() => props.canSubmit !== false && !!plan.value && !error.value && !loading.value && !generating.value && summary.value.codes > 0)
const categoryText = computed(() => {
  const bc = plan.value?.business_category
  if (!bc) return ''
  return `${bc.code} 类${bc.defaulted ? '（项目未填写 A / B / C 业务分类，按 C 类判断）' : ''}`
})

function programCounts(c: PlanCycle): { kept: number; cut: number } {
  const cut = c.programs.filter((p) => p.status === 'not_applicable' || p.status === 'skip').length
  return { kept: c.programs.length - cut, cut }
}

function conflictCount(c: PlanCycle): number {
  return c.items.filter((it) => it.category_conflict).length
}

function itemTip(it: PlanItem): string {
  const parts = [it.decided_by ? `决定它的程序：${it.decided_by}` : '尚无程序行覆盖']
  if (it.follows_children) parts.push('科目审定表：本科目程序全部裁掉才不生成')
  if (it.category_reason) parts.push(`业务分类：${it.category_reason}`)
  return parts.join('；')
}

function toggleCycle(cycle: string, on: boolean) {
  const next = new Set(selected.value)
  if (on) next.add(cycle)
  else next.delete(cycle)
  selected.value = next
}

function toggleAll(on: unknown) {
  selected.value = new Set(on ? selectable.value : [])
}

function toggleExpand(cycle: string) {
  expanded.value = expanded.value.has(cycle) ? new Set() : new Set([cycle])
}

function isCanceled(e: any): boolean {
  return e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError'
}

function isOpenSession(epoch: number): boolean {
  return epoch === openEpoch && props.modelValue
}

function requestClose(value: boolean) {
  if (!value && generating.value) return
  emit('update:modelValue', value)
}

async function loadPlan(epoch = openEpoch) {
  const mine = ++seq
  const projectId = props.projectId
  const selectedTemplateSet = templateSetId.value || null
  loading.value = true
  error.value = ''
  try {
    const data = await getGenerationPlan(projectId, selectedTemplateSet)
    if (mine !== seq || !isOpenSession(epoch) || props.projectId !== projectId) return
    plan.value = data
    selected.value = new Set(defaultSelectedCycles(data, props.initialCycle))
    expanded.value = new Set()
  } catch (e: any) {
    if (mine !== seq || !isOpenSession(epoch) || isCanceled(e)) return
    plan.value = null
    selected.value = new Set()
    error.value = `生成计划读取失败：${planErrorText(e)}`
  } finally {
    if (mine === seq && isOpenSession(epoch)) loading.value = false
  }
}

async function recoverRememberedOperation(epoch: number) {
  const remembered = loadGenerationOperation(props.projectId)
  if (!remembered) return
  try {
    const status = await getGenerationOperation(remembered.projectId, remembered.operationId)
    if (!isOpenSession(epoch) || props.projectId !== remembered.projectId) return
    const receipt = operationReceipt(status)
    if (!receipt) {
      ElMessage.info(status.resumable ? '上次底稿生成已中断，点击生成可继续原操作' : '上次底稿仍在生成，点击生成可查看进度')
      return
    }
    clearGenerationOperation(remembered.projectId, remembered.operationId)
    const notice = summarizeWorkpaperGenerateResult(receipt)
    ElMessage[notice.level]({ message: notice.message, duration: 5000, showClose: notice.level === 'warning' })
    emit('generated', receipt)
    await loadPlan(epoch)
  } catch {
    // operation 可能尚未完成 Phase A 或已被清理；保留 sessionStorage，用户点击时仍以同 id 重试。
  }
}

async function onOpen(epoch: number) {
  loading.value = true
  error.value = ''
  plan.value = null
  selected.value = new Set()
  expanded.value = new Set()
  try {
    const sets = await listGenerationTemplateSets()
    if (!isOpenSession(epoch)) return
    templateSets.value = sets
  } catch (e: any) {
    if (!isOpenSession(epoch) || isCanceled(e)) return
    templateSets.value = []
    error.value = `模板集读取失败：${planErrorText(e)}`
    loading.value = false
    return
  }
  if (!templateSets.value.some((s) => s.id === templateSetId.value)) {
    templateSetId.value = templateSets.value[0]?.id ?? ''
  }
  if (!templateSetId.value) {
    plan.value = null
    error.value = '暂无可用模板集，请在「模板库」中创建'
    loading.value = false
    return
  }
  await loadPlan(epoch)
  if (isOpenSession(epoch)) await recoverRememberedOperation(epoch)
}

// 每次打开 / 关闭都是独立 epoch：旧打开流程、旧计划响应与旧生成回执都不能接管后来重开的弹窗。
watch(() => [props.modelValue, props.projectId] as const, ([open]) => {
  const epoch = ++openEpoch
  ++seq
  if (open) void onOpen(epoch)
  else loading.value = false
}, { immediate: true })
onBeforeUnmount(() => { ++openEpoch; ++seq })

function goTrim(cycle: string) {
  if (generating.value) return
  emit('update:modelValue', false)
  emit('navigate-cycle', cycle)
}

async function onGenerate() {
  if (generating.value) return
  if (props.canSubmit === false) {
    ElMessage.warning(props.disabledReason || '当前项目状态已变化，不能生成底稿')
    return
  }
  if (props.year == null) {
    ElMessage.warning('未设置审计年度，请先在项目基本信息中填写')
    return
  }
  const codes = codesToGenerate(plan.value, selected.value)
  if (!codes.length) return
  const submissionEpoch = openEpoch
  const projectId = props.projectId
  const templateId = templateSetId.value
  const year = props.year
  const requestKey = generationRequestKey({ projectId, templateSetId: templateId, year, codes })
  const previous = loadGenerationOperation(projectId)
  const remembered = loadGenerationOperation(projectId, requestKey)
  const operationId = remembered?.operationId ?? previous?.operationId ?? newGenerationOperationId()
  const operationRequest = remembered ?? previous ?? {
    projectId, operationId, requestKey, templateSetId: templateId, year, codes, savedAt: Date.now(),
  }
  if (previous && !remembered) ElMessage.info('正在恢复上次未完成的底稿生成，完成后可再按当前计划生成')
  rememberGenerationOperation(operationRequest)
  generating.value = true
  try {
    const result = await runGenerationOperation(projectId, {
      templateSetId: operationRequest.templateSetId,
      year: operationRequest.year,
      codes: operationRequest.codes,
      operationId,
    })
    if (!isOpenSession(submissionEpoch) || props.projectId !== projectId) return
    clearGenerationOperation(projectId, operationId)
    const notice = summarizeWorkpaperGenerateResult(result)
    ElMessage[notice.level]({
      message: notice.message,
      duration: notice.level === 'warning' ? 10000 : 3000,
      showClose: notice.level === 'warning',
    })
    emit('generated', result)
    emit('update:modelValue', false)
  } catch (e: any) {
    if (isOpenSession(submissionEpoch)) handleApiError(e, '生成底稿')
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.gt-gen-plan { min-height: 160px; }
.gt-gen-plan__head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.gt-gen-plan__label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-gen-plan__meta { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-gen-plan__alert { margin-bottom: 10px; }
.gt-gen-plan__pending { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; }
.gt-gen-plan__toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.gt-gen-plan__hint { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-gen-plan__list { max-height: 52vh; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.gt-gen-plan__row {
  display: grid; align-items: center; gap: 6px; padding: 6px 10px; font-size: 13px;
  grid-template-columns: 28px 110px 150px 100px 56px 56px 64px 56px 96px 1fr;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.gt-gen-plan__row--head {
  position: sticky; top: 0; z-index: 1; font-size: 12px; color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}
.gt-gen-plan__row.is-disabled { color: var(--el-text-color-placeholder); }
.gt-gen-plan__cycle { font-weight: 600; }
.gt-gen-plan__row .is-create { color: var(--el-color-success); font-weight: 600; }
.gt-gen-plan__ops { text-align: right; white-space: nowrap; }
.gt-gen-plan__detail { padding: 6px 16px 10px 44px; background: var(--el-fill-color-lighter); }
.gt-gen-plan__conflict { font-size: 12px; color: var(--el-color-warning); margin-bottom: 6px; }
.gt-gen-plan__group { margin-bottom: 6px; }
.gt-gen-plan__group-title { font-size: 12px; color: var(--el-text-color-regular); margin-bottom: 4px; }
.gt-gen-plan__items { display: flex; flex-wrap: wrap; gap: 4px; }
.gt-gen-plan__item { max-width: 320px; overflow: hidden; text-overflow: ellipsis; }
.gt-gen-plan__summary { margin-right: 12px; font-size: 13px; color: var(--el-text-color-regular); }
</style>
