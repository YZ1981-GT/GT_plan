<script setup lang="ts">

/** G 循环程序表 — 截止测试自动提取面板（对标 D4/F2 GtCutoffAutoSampling） */

import { computed } from 'vue'

import { ElMessage } from 'element-plus'

import GtCutoffAutoSampling from '../cutoff/GtCutoffAutoSampling.vue'

import { dispatchGCycleCutoffFilled } from '../composables/gCycleCutoffFill'

import type { ExtractedVoucher, FillMode } from '../composables/useCutoffAutoSampling'



const props = withDefaults(defineProps<{

  wpId: string

  projectId: string

  accountCode: string

  cycle: 'g8' | 'g9' | 'g11' | 'g12' | 'g13' | 'g14'

  isReadonly?: boolean

  year?: number

  /** 截止样本回填目标说明 */

  fillTargetHint?: string

}>(), {

  fillTargetHint: '',

})



const emit = defineEmits<{

  filled: [payload: { samples: ExtractedVoucher[]; fillMode: FillMode }]

}>()



const auditYear = computed(() => props.year ?? new Date().getFullYear())



const defaultFillHint: Record<'g8' | 'g9' | 'g11' | 'g12' | 'g13' | 'g14', string> = {

  g8: '样本将回填至 G8-3 调整分录与 G8-6 凭证检查表',

  g9: '样本将回填至 G9-3 调整分录与 G9-6 凭证检查表',

  g11: '样本将回填至 G11-5 投资收益凭证检查表',

  g12: '样本将回填至 G12-6 凭证检查表',

  g13: '样本将回填至 G13-3 调整分录汇总',

  g14: '样本将回填至 G14-3 调整分录汇总',

}



const fillHint = computed(() => props.fillTargetHint || defaultFillHint[props.cycle])



function onFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {

  const n = payload.samples?.length ?? 0

  dispatchGCycleCutoffFilled(props.cycle, payload)

  emit('filled', payload)

  ElMessage.success(`截止样本已提取 ${n} 笔（${payload.fillMode}）→ ${fillHint.value}`)

}

</script>



<template>

  <div v-if="!isReadonly && wpId && projectId" class="g-cycle-cutoff-panel" data-testid="g-cycle-cutoff-panel">

    <el-collapse>

      <el-collapse-item title="⚡ 截止测试自动提取" name="cutoff">

        <p class="fill-hint">{{ fillHint }}</p>

        <GtCutoffAutoSampling

          :account-code="accountCode"

          cutoff-direction="window"

          :workpaper-id="wpId"

          :project-id="projectId"

          :year="auditYear"

          :default-conditions="{ daysBefore: 5, daysAfter: 10 }"

          @filled="onFilled"

        />

      </el-collapse-item>

    </el-collapse>

  </div>

</template>



<style scoped>

.g-cycle-cutoff-panel { margin-bottom: 12px; }

.fill-hint { margin: 0 0 8px; font-size: 12px; color: #606266; }

</style>

