<script setup lang="ts">
/** F2TabPolicy — F2-16 会计政策 | Task 17.1 */
import { toRef, type Ref } from 'vue'
import { useF2Policy } from '../../composables/useF2Policy'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const { sections, policyConclusion, changedCount, updateSection } = useF2Policy({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generatePolicyConclusion() {
  const text = await generateAndConfirm(
    'policy-evaluation',
    policyConclusion.value,
    { changedCount: changedCount.value },
    'AI 生成 · 会计政策评价',
  )
  if (text) policyConclusion.value = text
}
</script>

<template>
  <div class="f2-tab-policy">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>核查存货五类会计政策，变更项需说明原因并评价。</p></details>
    <el-tag v-if="changedCount > 0" type="warning" size="small">{{ changedCount }} 项政策有变更</el-tag>

    <el-card v-for="sec in sections" :key="sec.key" class="policy-card" shadow="never">
      <template #header>
        <span class="card-title">{{ sec.title }}</span>
        <GtIndexChip v-if="sec.indexRef" :value="sec.indexRef" :context-project-id="projectId" />
      </template>

      <el-form label-width="100px" size="small">
        <el-form-item label="政策描述">
          <el-input :model-value="sec.policyDesc" type="textarea" :rows="3" :disabled="isReadonly"
            @change="(v: string) => updateSection(sec.key, 'policyDesc', v)" />
        </el-form-item>
        <el-form-item label="是否变更">
          <el-select :model-value="sec.isChanged" :disabled="isReadonly" style="width:120px"
            @change="(v: string) => updateSection(sec.key, 'isChanged', v)">
            <el-option label="否" value="否" /><el-option label="是" value="是" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="sec.isChanged === '是'" label="变更原因">
          <el-input :model-value="sec.changeReason" type="textarea" :rows="2" :disabled="isReadonly"
            @change="(v: string) => updateSection(sec.key, 'changeReason', v)" />
        </el-form-item>
        <el-form-item label="审计评价">
          <el-input :model-value="sec.auditEval" type="textarea" :rows="2" :disabled="isReadonly"
            @change="(v: string) => updateSection(sec.key, 'auditEval', v)" />
        </el-form-item>
        <el-form-item label="索引">
          <el-input :model-value="sec.indexRef" :disabled="isReadonly" style="max-width:200px"
            @change="(v: string) => updateSection(sec.key, 'indexRef', v)" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">政策评价结论</span>
          <div class="header-actions">
            <F2ReviewChip section-id="F2-16-conclusion" />
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generatePolicyConclusion">AI 生成</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="policyConclusion" type="textarea" :rows="4" :disabled="isReadonly" placeholder="总体政策评价结论..." />
    </el-card>
  </div>
</template>

<style scoped>
.f2-tab-policy { padding: 12px; font-size: 13px; }
.policy-card { margin: 12px 0; }
.card-title { font-weight: 600; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
</style>
