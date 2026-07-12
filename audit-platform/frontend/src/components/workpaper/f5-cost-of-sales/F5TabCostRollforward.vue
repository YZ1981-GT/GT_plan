<template>
  <div class="f5-rollforward">
    <!-- 蓝色渐变引导区 -->
    <div class="f5-guide">
      <div class="f5-guide-title">成本倒轧逻辑（4步骤结构化验证）</div>
      <div class="f5-guide-steps">
        <span class="f5-guide-step"><b>①</b> 材料流转</span>
        <span class="f5-guide-arrow">→</span>
        <span class="f5-guide-step"><b>②</b> 成本构成</span>
        <span class="f5-guide-arrow">→</span>
        <span class="f5-guide-step"><b>③</b> 成本结转</span>
        <span class="f5-guide-arrow">→</span>
        <span class="f5-guide-step"><b>④</b> 营业成本</span>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过成本倒轧（材料→成本构成→成本结转→营业成本）验证营业成本结转的完整与准确，将倒轧结果与 F5-1 审定营业成本核对，差异超重要性水平须查明。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-hint">科目6401 · 4区结构化倒轧验证</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" /></span>
      </div>
    </div>

    <!-- ① 材料流转区 -->
    <el-card class="f5-zone" shadow="never">
      <template #header><span class="f5-zone-title">① 材料流转区</span></template>
      <div class="f5-line"><span>期初原材料（TB取数）</span><span class="f5-tb">{{ fmt(d.openingMaterial) }}</span></div>
      <div class="f5-line"><span>+ 本期购入</span>{{ editable('purchase') }}</div>
      <div class="f5-line"><span>− 期末原材料（TB取数）</span><span class="f5-tb">{{ fmt(d.closingMaterial) }}</span></div>
      <div class="f5-line"><span>− 其他发出</span>{{ editable('otherIssue1') }}</div>
      <div class="f5-line f5-result"><span>= 投入生产</span>
        <span class="f5-formula" title="期初原材料+购入-期末原材料-其他发出">{{ fmt(d.materialInput) }}</span>
      </div>
    </el-card>

    <!-- ② 成本构成区 -->
    <el-card class="f5-zone" shadow="never">
      <template #header><span class="f5-zone-title">② 成本构成区</span></template>
      <div class="f5-line"><span>投入生产（来自①）</span><span class="f5-tb">{{ fmt(d.materialInput) }}</span></div>
      <div class="f5-line"><span>+ 直接人工</span>{{ editable('directLabor') }}</div>
      <div class="f5-line"><span>+ 制造费用</span>{{ editable('overhead') }}</div>
      <div class="f5-line f5-result"><span>= 产品总成本</span>
        <span class="f5-formula" title="投入生产+直接人工+制造费用">{{ fmt(d.totalProductionCost) }}</span>
      </div>
    </el-card>

    <!-- ③ 成本结转区 -->
    <el-card class="f5-zone" shadow="never">
      <template #header><span class="f5-zone-title">③ 成本结转区</span></template>
      <div class="f5-line"><span>期初在产品（TB取数）</span><span class="f5-tb">{{ fmt(d.openingWIP) }}</span></div>
      <div class="f5-line"><span>+ 产品总成本（来自②）</span><span class="f5-tb">{{ fmt(d.totalProductionCost) }}</span></div>
      <div class="f5-line"><span>− 期末在产品（TB取数）</span><span class="f5-tb">{{ fmt(d.closingWIP) }}</span></div>
      <div class="f5-line f5-result"><span>= 完工产品成本</span>
        <span class="f5-formula" title="期初在产品+产品总成本-期末在产品">{{ fmt(d.finishedGoodsCost) }}</span>
      </div>
    </el-card>

    <!-- ④ 营业成本区 -->
    <el-card class="f5-zone" shadow="never">
      <template #header><span class="f5-zone-title">④ 营业成本区</span></template>
      <div class="f5-line"><span>期初产成品（TB取数）</span><span class="f5-tb">{{ fmt(d.openingFG) }}</span></div>
      <div class="f5-line"><span>+ 完工产品成本（来自③）</span><span class="f5-tb">{{ fmt(d.finishedGoodsCost) }}</span></div>
      <div class="f5-line"><span>− 期末产成品（TB取数）</span><span class="f5-tb">{{ fmt(d.closingFG) }}</span></div>
      <div class="f5-line"><span>− 其他发出</span>{{ editable('otherIssue2') }}</div>
      <div class="f5-line f5-result f5-cogs"><span>= 本期营业成本</span>
        <span class="f5-formula" title="期初产成品+完工产品成本-期末产成品-其他发出">{{ fmt(d.cogs) }}</span>
      </div>
    </el-card>

    <!-- 校验区 -->
    <el-card class="f5-verify" shadow="never" :class="{ 'is-error': roll.varianceExceedsMateriality.value }">
      <template #header><span class="f5-zone-title">校验区</span></template>
      <div class="f5-verify-grid">
        <div><span>审定表营业成本（F5-1取）</span><b>{{ fmt(d.adjudicatedCOGS) }}</b></div>
        <div><span>倒轧营业成本</span><b>{{ fmt(d.cogs) }}</b></div>
        <div><span>与倒轧差异</span>
          <b :class="roll.varianceExceedsMateriality.value ? 'danger' : 'ok'">{{ fmt(d.rollforwardVariance) }}</b>
        </div>
        <div><span>结论</span>
          <el-tag :type="roll.varianceExceedsMateriality.value ? 'danger' : 'success'" size="small">
            {{ roll.varianceExceedsMateriality.value ? '差异超重要性水平，需查明' : '倒轧一致，通过' }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="roll.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="成本倒轧审计结论..." @change="saveConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details guidance-bottom">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 期初/期末原材料(1401)、在产品(1404)、产成品(1405)由试算表自动取数（灰底只读），确保存货口径与 F2 存货底稿一致。</p>
        <p>2. 可编辑字段：本期购入、直接人工、制造费用、其他发出；各区结果按公式自动倒轧（公式列虚线，悬停查看来源）。</p>
        <p>3. 倒轧营业成本 = 期初产成品 + 完工产品成本 − 期末产成品 − 其他发出，逐区串联验证成本结转链条。</p>
        <p>4. 校验区从 F5-1 审定表获取审定营业成本，与倒轧结果差异超重要性水平以红色标记，须查明原因。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabCostRollforward.vue — F5-7 成本倒轧表（4区结构化验证）
 * 蓝色引导区 + 4区el-card(公式行虚线+tooltip) + TB取数只读/可编辑高亮 + 校验区(绿/红) + 审计结论(AI) + 编制提示折叠
 */
import { computed, inject, toRef, watch, h, type Ref, type VNode } from 'vue'
import { ElInput } from 'element-plus'
import { useF5CostRollforward } from '../composables/useF5CostRollforward'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  materiality?: number
  adjudicatedCOGS?: number
  /** TB 自动取数（1401/1404/1405 期初期末），来自 render 策略 */
  tbData?: Record<string, number>
}>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const CONCLUSION_KEY = 'F5-7-conclusion'
const ROLL_KEY = 'F5-7-cost-rollforward'

const roll = useF5CostRollforward({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  materiality: computed(() => props.materiality ?? 0) as unknown as Ref<number>,
  adjudicatedCOGS: computed(() => props.adjudicatedCOGS ?? 0) as unknown as Ref<number>,
})

/** 倒轧数据（computed ref，模板自动解包 → d.xxx） */
const d = computed(() => roll.data.value)

/** TB 自动取数写入只读字段（1401/1404/1405 期初期末） */
const TB_KEYS = ['openingMaterial', 'closingMaterial', 'openingWIP', 'closingWIP', 'openingFG', 'closingFG'] as const
function seedTb(tb?: Record<string, number>): void {
  if (props.isReadonly || !tb) return
  const patch: Record<string, number> = {}
  for (const k of TB_KEYS) {
    if (tb[k] != null && Number.isFinite(Number(tb[k]))) patch[k] = Number(tb[k])
  }
  if (Object.keys(patch).length) {
    roll.setTbValues(patch as any)
    window.dispatchEvent(new CustomEvent('f5:save-items', {
      detail: { items: [allResponsesRef.value.get(ROLL_KEY)].filter(Boolean) },
    }))
  }
}
watch(() => props.tbData, (tb) => seedTb(tb), { immediate: true })

/** 可编辑字段渲染函数（返回 el-input 或只读 span） */
function editable(field: string): VNode {
  if (props.isReadonly) {
    return h('span', { class: 'f5-edit-ro' }, fmt((roll.data.value as any)[field]))
  }
  return h(ElInput, {
    modelValue: (roll.data.value as any)[field],
    size: 'small',
    class: 'f5-edit-input',
    'onUpdate:modelValue': (v: any) => roll.updateField(field, v),
    onChange: (v: any) => {
      roll.updateField(field, v)
      window.dispatchEvent(new CustomEvent('f5:save-items', {
        detail: { items: [allResponsesRef.value.get(ROLL_KEY)].filter(Boolean) },
      }))
    },
  })
}

function saveConclusion() {
  window.dispatchEvent(new CustomEvent('f5:save-items', {
    detail: { items: [allResponsesRef.value.get(CONCLUSION_KEY)].filter(Boolean) },
  }))
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function openReview() { openReviewDialog('F5-7-conclusion') }
</script>

<style scoped>
.f5-rollforward { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-guide { background: linear-gradient(135deg, #409eff, #66b1ff); color: #fff; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px; }
.f5-guide-title { font-weight: 700; margin-bottom: 6px; }
.f5-guide-steps { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.f5-guide-step b { font-size: 16px; margin-right: 4px; }
.f5-guide-arrow { opacity: 0.8; }
.f5-zone { margin-bottom: 10px; }
.f5-zone-title { font-weight: 600; }
.f5-line { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; border-bottom: 1px dotted #ebeef5; }
.f5-line > span:first-child { color: #606266; }
.f5-tb { background: #f5f7fa; padding: 2px 8px; border-radius: 3px; color: #909399; }
.f5-result { font-weight: 700; border-top: 1px solid #dcdfe6; margin-top: 4px; }
.f5-cogs { color: #409eff; font-size: 15px; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.f5-edit-input) { width: 160px; }
.f5-verify { margin-top: 12px; border: 1px solid #67c23a; }
.f5-verify.is-error { border-color: #f56c6c; }
.f5-verify-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.f5-verify-grid > div { display: flex; flex-direction: column; gap: 4px; }
.f5-verify-grid .danger { color: #f56c6c; }
.f5-verify-grid .ok { color: #67c23a; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }

/* 审计目标 */
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.toolbar-hint { font-size: var(--wp-font-size, 13px); color: #909399; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计意见卡片 */
.opinion-card { margin-top: 12px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }

/* 编制提示 */
.guidance-details { margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
