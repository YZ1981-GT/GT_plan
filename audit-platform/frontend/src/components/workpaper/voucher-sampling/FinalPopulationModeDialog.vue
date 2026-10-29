<template>
  <el-dialog
    v-model="visible"
    title="年审抽凭口径"
    width="560px"
    :close-on-click-modal="false"
    append-to-body
    data-testid="final-population-mode-dialog"
    @closed="settle(false)"
  >
    <p class="fpm-summary" data-testid="final-population-mode-summary">{{ summaryText }}</p>
    <el-radio-group v-model="selected" class="fpm-options">
      <el-radio value="full_minus_interim" class="fpm-option" data-testid="final-population-mode-b">
        <span class="fpm-option__title">b 全年扣除预审已检样本（推荐）</span>
        <span class="fpm-option__desc">
          从全年分录里抽，扣除本底稿预审抽到的分录和预审手工挂凭的分录。全年错报 = 预审样本查出的实际错报 + 本次推断错报。
        </span>
      </el-radio>
      <el-radio value="remaining" class="fpm-option" :disabled="!remainingAvailable" data-testid="final-population-mode-a">
        <span class="fpm-option__title">a 只抽剩余期间</span>
        <span class="fpm-option__desc">{{ remainingDesc }}</span>
      </el-radio>
    </el-radio-group>
    <p v-if="ctx?.lastMode" class="fpm-hint" data-testid="final-population-mode-last">
      上次选择：{{ FINAL_POPULATION_MODE_LABELS[ctx.lastMode] }}
    </p>
    <template #footer>
      <el-button @click="close(false)">取消</el-button>
      <el-button type="primary" data-testid="final-population-mode-confirm" @click="close(selected)">按此口径抽凭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 年审抽凭口径弹窗（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1，ADR-VK-10）。
 *
 * 由抽凭引擎经 `open(ctx)` 打开，返回所选口径或 false（取消）。缺省选上次口径，首次选 b；
 * 口径 a 需要截止日：项目没设、预审批次也没有期间信息时不可选。
 */
import { computed, ref } from 'vue'
import {
  FINAL_POPULATION_MODE_LABELS,
  type FinalPopulationMode,
  type SamplingPhaseContext,
} from '../composables/useFinalPopulationMode'

const visible = ref(false)
const ctx = ref<SamplingPhaseContext | null>(null)
const selected = ref<FinalPopulationMode>('full_minus_interim')
let resolver: ((v: FinalPopulationMode | false) => void) | null = null

const remainingAvailable = computed(() => Boolean(ctx.value?.effectiveCutoffDate))

const summaryText = computed(() => {
  const c = ctx.value
  if (!c) return ''
  const cutoff = c.interimCutoffDate
    ? `预审截止日 ${c.interimCutoffDate}`
    : c.effectiveCutoffDate
      ? `项目未设预审截止日，按预审批次期间上限 ${c.effectiveCutoffDate} 计`
      : '项目未设预审截止日'
  return `本底稿预审已抽凭 ${c.interimBatchCount} 批、样本 ${c.interimSampleCount} 条，`
    + `预审手工挂凭 ${c.interimAttachCount} 张；${cutoff}。`
})

const remainingDesc = computed(() => {
  const c = ctx.value
  if (!remainingAvailable.value) {
    return '项目没有设置预审截止日，预审批次也没有期间信息，暂不能选；请先在项目设置「审计阶段」里填写预审截止日。'
  }
  const end = c?.auditPeriodEnd ? `审计期末 ${c.auditPeriodEnd}` : '审计期末'
  return `只从预审截止日 ${c?.effectiveCutoffDate} 之后至${end} 的分录里抽。`
    + '全年错报 = 预审各批推断错报 + 本次推断错报（两段总体不重叠）。'
})

function settle(value: FinalPopulationMode | false): void {
  const done = resolver
  resolver = null
  done?.(value)
}

function close(value: FinalPopulationMode | false): void {
  visible.value = false
  settle(value)
}

/** 打开弹窗；关闭（含右上角关闭、取消）返回 false */
function open(context: SamplingPhaseContext): Promise<FinalPopulationMode | false> {
  settle(false)
  ctx.value = context
  const preferred = context.lastMode ?? context.defaultMode
  selected.value = preferred === 'remaining' && !context.effectiveCutoffDate ? 'full_minus_interim' : preferred
  visible.value = true
  return new Promise((resolve) => { resolver = resolve })
}

defineExpose({ open })
</script>

<style scoped>
.fpm-summary {
  margin: 0 0 12px;
  color: var(--gt-color-text-regular);
  font-size: var(--gt-font-size-sm);
  line-height: 1.6;
}
.fpm-options {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
.fpm-option {
  height: auto;
  margin-right: 0;
  align-items: flex-start;
  white-space: normal;
}
.fpm-option__title {
  display: block;
  font-weight: 600;
}
.fpm-option__desc {
  display: block;
  margin-top: 4px;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
  line-height: 1.6;
}
.fpm-hint {
  margin: 12px 0 0;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
}
</style>
