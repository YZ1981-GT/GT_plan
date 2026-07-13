<script setup lang="ts">
/** F2TabPolicy — F2-16 会计政策 | Task 17.1 */
import { ref, toRef, onMounted, type Ref } from 'vue'
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

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────
const NOTE_KEY = 'F2-policy-audit-note'
const CONCLUSION_KEY = 'F2-policy-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

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
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项核查存货相关会计政策（发出计价方法、跌价准备、成本核算等），变更项须说明原因并评价。</p>
        <p>2. 依《企业会计准则第 1 号——存货》，发出存货计价方法（先进先出/加权平均/个别计价）一经确定不得随意变更。</p>
        <p>3. 期末按成本与可变现净值孰低计量，跌价准备计提方法及依据应保持前后一贯。</p>
        <p>4. 政策变更须评价是否符合准则、是否影响可比性，并在结论中说明。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：评价存货计价与跌价准备会计政策的适当性及前后期一贯性。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag v-if="changedCount > 0" type="warning" size="small">{{ changedCount }} 项政策有变更</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ sections.length }} 项</el-tag>
      </div>
    </div>

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

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">政策评价结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generatePolicyConclusion">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-16-conclusion" />
          </div>
        </div>
      </template>
      <el-input v-model="policyConclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="总体政策评价结论..." />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述存货计价与跌价准备会计政策的核查程序、适当性与前后期一贯性的测试情况与结果，以及政策变更的核查与拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-tab-policy { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-tab-policy :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-tab-policy :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.policy-card { margin: 12px 0; }
.card-title { font-weight: 600; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
