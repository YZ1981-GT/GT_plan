<!--
  GtB1KaaCheck.vue — B1-5 KAA检查程序表

  一、确定是否达到KAA标准（12 判定项，item7/12 含子项）→ 任一"是"即达到标准
  二、完成KAA审批或报备流程（3 项）
  自动结论（达到/未达到 KAA 标准）+ 可手工覆盖；达到时高亮提示需执行审批/报备。
-->
<template>
  <div class="gt-b1kaa">
    <div class="gt-b1kaa__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <el-tag type="info" effect="plain" size="small">KAA 关键业务承接检查</el-tag>
      <span class="gt-b1kaa__spacer" />
      <span class="gt-b1kaa__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else>○ 未保存</template>
      </span>
    </div>

    <template v-if="mode === '结构化视图'">
    <el-alert type="info" :closable="false" show-icon class="gt-b1kaa__intro">
      <template #title><strong>KAA（关键业务承接）政策</strong></template>
      <p class="gt-b1kaa__intro-text">
        GTIL 的关键业务承接（KAA）政策旨在识别和评估某些鉴证任务可能对致同品牌、GTIL 及其成员所带来的重大风险。
        下列"一、KAA标准"中<strong>任一判定为"是"</strong>即达到 KAA 标准，须执行"二、审批或报备流程"。
      </p>
    </el-alert>

    <!-- 头部信息 -->
    <el-card shadow="never" class="gt-b1kaa__header-card">
      <div class="gt-b1kaa__header-grid">
        <div v-for="hf in headerFields" :key="hf.field" class="gt-b1kaa__header-item">
          <label>{{ hf.label }}</label>
          <el-input :model-value="header[hf.field] || ''" size="small" placeholder="请输入"
            @update:model-value="(v: string) => updateHeader(hf.field, v)" />
        </div>
      </div>
    </el-card>

    <!-- 结论横幅 -->
    <el-alert
      :type="effectiveReached ? 'warning' : 'success'"
      :closable="false"
      show-icon
      class="gt-b1kaa__conclusion-banner"
    >
      <template #title>
        <span v-if="effectiveReached">⚠️ 已达到 KAA 标准 — 须完成下方"二、审批或报备流程"（向 GTI 提交审批表或向办公室提交报备表）</span>
        <span v-else>✓ 未达到 KAA 标准 — 一节全部判定为"否/N/A"</span>
      </template>
    </el-alert>

    <!-- 各章节 -->
    <el-card v-for="sec in sections" :key="sec.key" shadow="never" class="gt-b1kaa__section-card">
      <template #header><span class="gt-b1kaa__section-title">{{ sec.title }}</span></template>
      <div v-for="it in sec.items" :key="it.seq" class="gt-b1kaa__item">
        <div class="gt-b1kaa__item-row">
          <span class="gt-b1kaa__seq">{{ it.seq }}</span>
          <span class="gt-b1kaa__text" :class="{ 'is-group': it.kind === 'group' }">{{ it.text }}</span>
          <el-select
            v-if="it.kind === 'judge'"
            :model-value="it.answer"
            size="small"
            placeholder="判定"
            clearable
            class="gt-b1kaa__judge"
            :class="{ 'is-hit': it.answer === '是' && sec.key === 'standard' }"
            @update:model-value="(v: string) => updateAnswer(sec.key, it.seq, v)"
          >
            <el-option v-for="o in choiceOptions" :key="o" :label="o" :value="o" />
          </el-select>
        </div>
        <!-- 子项 -->
        <div v-for="sub in it.sub_items" :key="sub.seq" class="gt-b1kaa__sub-row">
          <span class="gt-b1kaa__sub-seq">{{ sub.seq }}</span>
          <span class="gt-b1kaa__sub-text">{{ sub.text }}</span>
          <el-select
            :model-value="sub.answer"
            size="small"
            placeholder="判定"
            clearable
            class="gt-b1kaa__judge"
            :class="{ 'is-hit': sub.answer === '是' && sec.key === 'standard' }"
            @update:model-value="(v: string) => updateSubAnswer(sec.key, it.seq, sub.seq, v)"
          >
            <el-option v-for="o in choiceOptions" :key="o" :label="o" :value="o" />
          </el-select>
        </div>
        <!-- 执行情况说明（仅判定项）-->
        <div v-if="it.kind === 'judge'" class="gt-b1kaa__note-row">
          <el-input
            :model-value="it.note"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            placeholder="执行情况说明 / 索引号"
            @update:model-value="(v: string) => updateNote(sec.key, it.seq, v)"
          />
        </div>
      </div>
    </el-card>

    <!-- 最终结论（可覆盖）-->
    <el-card shadow="never" class="gt-b1kaa__final-card">
      <template #header>
        <span class="gt-b1kaa__section-title">KAA 检查结论</span>
        <GtReviewTrigger section-id="b1kaa-conclusion" label="💬 复核" />
      </template>
      <div class="gt-b1kaa__final-row">
        <label>系统自动判断</label>
        <el-tag :type="liveAutoReached ? 'warning' : 'success'" effect="dark" size="small">
          {{ liveAutoReached ? '达到 KAA 标准' : '未达到 KAA 标准' }}
        </el-tag>
      </div>
      <div v-if="hitItems.length" class="gt-b1kaa__hits">
        <span class="gt-b1kaa__hits-label">命中的 KAA 标准项（{{ hitItems.length }}）：</span>
        <ul class="gt-b1kaa__hits-list">
          <li v-for="(h, i) in hitItems" :key="i">{{ h }}</li>
        </ul>
      </div>
      <el-alert v-if="approvalIncomplete" type="error" :closable="false" show-icon class="gt-b1kaa__approval-warn">
        <template #title>⚠️ 已达到 KAA 标准但"二、审批或报备流程"尚有未完成项，请先完成审批/报备判定</template>
      </el-alert>
      <div class="gt-b1kaa__final-row">
        <label>最终结论（可覆盖）</label>
        <el-select
          :model-value="manualConclusion"
          size="small"
          placeholder="默认采用系统自动判断"
          clearable
          @update:model-value="updateManualConclusion"
        >
          <el-option label="达到 KAA 标准（需审批/报备）" value="reached" />
          <el-option label="未达到 KAA 标准" value="not_reached" />
        </el-select>
      </div>
      <div class="gt-b1kaa__note-head">
        <label>结论说明</label>
        <el-button size="small" text type="primary" :loading="aiBusy" class="gt-b1kaa__ai-btn"
          @click="aiConclusionNote">🤖 AI 辅助说明</el-button>
      </div>
      <el-input :model-value="conclusionNote" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="说明 KAA 判定依据（命中的标准项）及后续审批/报备安排"
        @update:model-value="updateConclusionNote" />
    </el-card>
    </template>

    <!-- 在线编辑（OnlyOffice 降级） -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="wpId"
      :sheet-name="sourceSheet || ' B1-5 KAA检查表-业务承接'"
      :project-id="projectId"
      class="gt-b1kaa__oo"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, provide, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { useB1KaaCheck, KAA_CHOICE_OPTIONS, type KaaRenderData } from './composables/useB1KaaCheck'
import { useWpDualMode } from './composables/useWpDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import GtReviewTrigger from './GtReviewTrigger.vue'

// 版本快照由 Runtime Boundary(GtWpRenderer) 提供的运行时上下文承载；复核对话由 GtReviewTrigger 自行 inject
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = () => runtime?.version?.scheduleAutoSnapshot?.()

defineOptions({ name: 'GtB1KaaCheck' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: KaaRenderData | null
}>(), { projectId: '', htmlData: null })

const {
  saveStatus, sourceSheet, sections, headerFields, header, manualConclusion, conclusionNote,
  computeReached, updateAnswer, updateNote, updateSubAnswer, updateHeader,
  updateManualConclusion, updateConclusionNote, flushPendingSaves, loadData,
} = useB1KaaCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
  onAfterSave: () => scheduleAutoSnapshot?.(),
})

// 双模式：健康检查 + 切换前 flush（对齐 D4/GtB14 gold 范式）
const { mode, modeOptions, checkOOHealth } = useWpDualMode({ flush: flushPendingSaves })

// 复核线程蓝/红点（供后代 GtReviewTrigger/GtReviewDot inject）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId') as any)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const choiceOptions = KAA_CHOICE_OPTIONS

// 实时"达到"判断（一节任一"是"，客户端即时重算，不依赖 render 时快照）
const liveAutoReached = computed(() => computeReached())
// 最终"达到"判断（手工覆盖优先）
const effectiveReached = computed(() => {
  if (manualConclusion.value) return manualConclusion.value === 'reached'
  return liveAutoReached.value
})
// 命中的 KAA 标准项（供 UI 直接展示，与 AI 上下文同源）
const hitItems = computed<string[]>(() => collectHitItems())

// ─── 改进4：达标时二节审批/报备强制完成校验 ───
const approvalIncomplete = computed<boolean>(() => {
  if (!effectiveReached.value) return false
  const approval = sections.value.find((s) => s.key === 'approval')
  if (!approval) return false
  // 检查二节所有 judge 类判定项是否全部已填
  return approval.items.some((it) => it.kind === 'judge' && !it.answer)
})

// ─── AI 辅助结论说明 ───
const aiBusy = ref(false)
function collectHitItems(): string[] {
  const hits: string[] = []
  const std = sections.value.find((s) => s.key === 'standard')
  if (!std) return hits
  for (const it of std.items) {
    if (it.answer === '是') hits.push(`${it.seq}. ${it.text}`)
    for (const sub of it.sub_items) {
      if (sub.answer === '是') hits.push(`${it.seq}(${sub.seq}) ${sub.text}`)
    }
  }
  return hits
}
async function aiConclusionNote() {
  aiBusy.value = true
  try {
    const hits = collectHitItems()
    const ctx: Record<string, string> = {
      被审计单位: header.value.audited_entity || '',
      是否达到KAA标准: effectiveReached.value ? '是' : '否',
      命中标准项: hits.length ? hits.join('；') : '无',
      命中项数: String(hits.length),
    }
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'b1-5-kaa-conclusion',
      prompt: '根据 KAA 检查命中的标准项，撰写 KAA 检查结论说明，概述判定依据及后续审批（GTI 审批表）或报备（办公室报备表）安排',
      existingContent: conclusionNote.value || '',
      context: ctx,
    })
    const text = res?.content || res?.data?.content || res?.text || ''
    if (text) { updateConclusionNote(text); ElMessage.success('AI 已生成结论说明') }
    else ElMessage.warning('AI 未返回内容')
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiBusy.value = false }
}

onMounted(async () => { checkOOHealth(); if (!props.htmlData) await loadData() })
onBeforeUnmount(() => { flushPendingSaves() })
</script>

<style scoped>
/* ── 统一字号 13px + 视觉语言 ── */
.gt-b1kaa { display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: var(--el-text-color-primary); }
.gt-b1kaa :deep(.el-input__inner),
.gt-b1kaa :deep(.el-textarea__inner),
.gt-b1kaa :deep(.el-select__placeholder) { font-size: 13px; }
.gt-b1kaa__toolbar { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.gt-b1kaa__spacer { flex: 1; }
.gt-b1kaa__save-status { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-b1kaa__intro :deep(.el-alert__content) { padding: 2px 0; }
.gt-b1kaa__intro-text { margin: 4px 0 0; font-size: 13px; line-height: 1.7; }

/* ── 卡片统一：primary 左强调条 + 渐变标题栏 ── */
.gt-b1kaa :deep(.el-card) { border-radius: 8px; border-color: var(--el-border-color-lighter); }
.gt-b1kaa :deep(.el-card__header) {
  padding: 9px 14px;
  background: linear-gradient(90deg, var(--el-color-primary-light-9), transparent 70%);
  border-left: 3px solid var(--el-color-primary);
  display: flex; align-items: center; justify-content: space-between;
}
.gt-b1kaa :deep(.el-card__body) { padding: 14px; }
.gt-b1kaa__header-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 20px; }
.gt-b1kaa__header-item { display: flex; align-items: center; gap: 8px; }
.gt-b1kaa__header-item label { flex: 0 0 140px; font-size: 13px; color: var(--el-text-color-regular); text-align: right; }
.gt-b1kaa__conclusion-banner :deep(.el-alert__title) { font-size: 13px; }
.gt-b1kaa__section-title { font-weight: 600; font-size: 13px; }
.gt-b1kaa__item { padding: 8px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.gt-b1kaa__item:last-child { border-bottom: none; }
.gt-b1kaa__item-row { display: flex; align-items: flex-start; gap: 8px; }
.gt-b1kaa__seq { flex: 0 0 28px; font-weight: 600; font-size: 13px; color: var(--el-color-primary); }
.gt-b1kaa__text { flex: 1; font-size: 13px; line-height: 1.6; }
.gt-b1kaa__text.is-group { font-weight: 600; }
.gt-b1kaa__judge { flex: 0 0 104px; }
.gt-b1kaa__judge.is-hit :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px var(--el-color-warning) inset; }
.gt-b1kaa__sub-row { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0 5px 28px; }
.gt-b1kaa__sub-seq { flex: 0 0 32px; font-size: 13px; color: var(--el-text-color-secondary); }
.gt-b1kaa__sub-text { flex: 1; font-size: 13px; line-height: 1.6; color: var(--el-text-color-regular); }
.gt-b1kaa__note-row { padding: 4px 0 0 28px; }
.gt-b1kaa__final-card :deep(.el-card__body) { display: flex; flex-direction: column; gap: 10px; }
.gt-b1kaa__final-row { display: flex; align-items: center; gap: 10px; }
.gt-b1kaa__final-row > label { flex: 0 0 140px; font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1kaa__note-head { display: flex; align-items: center; justify-content: space-between; }
.gt-b1kaa__note-head > label { font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1kaa__ai-btn { padding: 2px 6px; }
.gt-b1kaa__hits { background: var(--el-color-warning-light-9); border-left: 3px solid var(--el-color-warning); border-radius: 4px; padding: 8px 12px; }
.gt-b1kaa__hits-label { font-size: 13px; font-weight: 600; color: var(--el-color-warning-dark-2); }
.gt-b1kaa__hits-list { margin: 6px 0 0; padding-left: 20px; line-height: 1.7; font-size: 13px; color: var(--el-text-color-regular); }
.gt-b1kaa__approval-warn { margin-top: 8px; }
.gt-b1kaa__approval-warn :deep(.el-alert__title) { font-size: 13px; font-weight: 500; }
.gt-b1kaa__oo { min-height: 600px; }
</style>
