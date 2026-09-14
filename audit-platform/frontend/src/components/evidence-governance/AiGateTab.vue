<script setup lang="ts">
/**
 * AiGateTab — AI 内容门禁 + FormalOutput preflight/finalize（useAiEvidenceGate）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R8/R9/R11)
 */
import { ref, computed, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useAiEvidenceGate,
  type AiGenerationStatus,
  type AiEligibilityResult,
  type FormalOutputEvaluation,
} from '@/composables/useAiEvidenceGate'

const props = defineProps<{ projectId: string; year: number; role: string }>()
const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const roleRef = toRef(props, 'role') as any
const gate = useAiEvidenceGate(projectIdRef, yearRef, roleRef)

const contentId = ref('')
const status = ref<AiGenerationStatus | null>(null)
const eligibility = ref<AiEligibilityResult | null>(null)

// formal output
const targetId = ref('')
const targetType = ref('workpaper_conclusion')
const preflightResult = ref<FormalOutputEvaluation | null>(null)
const finalizeResult = ref<FormalOutputEvaluation | null>(null)

/** preflight + finalize 合并为一个渲染列表，避免重复模板 */
const gateEvaluations = computed(() =>
  [
    { title: 'Preflight', ev: preflightResult.value },
    { title: 'Finalize', ev: finalizeResult.value },
  ].filter((x) => x.ev) as Array<{ title: string; ev: FormalOutputEvaluation }>,
)

async function loadStatus() {
  if (!contentId.value) return
  status.value = await gate.getGeneration(contentId.value)
  eligibility.value = await gate.checkEligibility(contentId.value)
  if (gate.error.value) ElMessage.error(gate.error.value)
}

async function confirm() {
  const res = await gate.confirmGeneration(contentId.value)
  if (res) { ElMessage.success('已人工确认'); await loadStatus() }
  else if (gate.error.value) ElMessage.error(gate.error.value)
}

async function revise() {
  try {
    const { value } = await ElMessageBox.prompt('输入修订后的内容', '修订 AI 内容', { inputType: 'textarea' })
    if (!value) return
    const res = await gate.reviseGeneration(contentId.value, value)
    if (res) { ElMessage.success('已修订（生成新版本）'); await loadStatus() }
    else if (gate.error.value) ElMessage.error(gate.error.value)
  } catch { /* cancelled */ }
}

async function reject() {
  try {
    const { value } = await ElMessageBox.prompt('输入拒绝原因', '拒绝 AI 内容', {})
    if (!value) return
    const res = await gate.rejectGeneration(contentId.value, value)
    if (res) { ElMessage.success('已拒绝'); await loadStatus() }
    else if (gate.error.value) ElMessage.error(gate.error.value)
  } catch { /* cancelled */ }
}

async function preflight() {
  if (!targetId.value) { ElMessage.warning('请填写目标 ID'); return }
  finalizeResult.value = null
  preflightResult.value = await gate.formalOutputPreflight({ target_id: targetId.value, target_type: targetType.value })
  if (gate.error.value) ElMessage.error(gate.error.value)
}

async function finalize() {
  if (!preflightResult.value?.watermark) { ElMessage.warning('请先执行 Preflight 获取 watermark'); return }
  finalizeResult.value = await gate.formalOutputFinalize({
    target_id: targetId.value,
    target_type: targetType.value,
    preflight_watermark: preflightResult.value.watermark,
  })
  if (gate.error.value) ElMessage.error(gate.error.value)
}

const lcType = (s?: string) =>
  s === 'confirmed' ? 'success' : s === 'rejected' ? 'danger' : s === 'revised' ? 'info' : 'warning'
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="AI 全入口硬门禁：未人工确认、内容哈希变化或依据 stale 的 AI 内容不得进入底稿结论/附注/报告/归档等正式输出。"
      style="margin-bottom: 12px"
    />

    <el-card shadow="never" header="AI 内容状态与人工确认" style="margin-bottom: 16px">
      <el-form :inline="true" size="default">
        <el-form-item label="内容 ID">
          <el-input v-model="contentId" placeholder="ai content_id" style="width: 280px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="gate.loading.value" @click="loadStatus">查询状态</el-button>
          <el-button type="success" :disabled="!status || !gate.canConfirmAi.value" @click="confirm">确认</el-button>
          <el-button :disabled="!status || !gate.canConfirmAi.value" @click="revise">修订</el-button>
          <el-button type="danger" plain :disabled="!status || !gate.canConfirmAi.value" @click="reject">拒绝</el-button>
        </el-form-item>
      </el-form>
      <el-text v-if="!gate.canConfirmAi.value" type="warning" size="small">当前角色无人工确认权限（仅展示）</el-text>

      <el-descriptions v-if="status" :column="3" border size="small" style="margin-top: 8px">
        <el-descriptions-item label="入口">{{ status.entry_point }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ status.model_name }}</el-descriptions-item>
        <el-descriptions-item label="服务状态">{{ status.service_status }}</el-descriptions-item>
        <el-descriptions-item label="生命周期">
          <el-tag size="small" :type="lcType(status.lifecycle_status)">{{ status.lifecycle_status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="版本">v{{ status.content_version }}</el-descriptions-item>
        <el-descriptions-item label="输出 Hash">
          <span class="mono">{{ status.output_hash?.slice(0, 12) }}…</span>
        </el-descriptions-item>
      </el-descriptions>

      <template v-if="eligibility">
        <el-divider content-position="left">FormalOutput 资格</el-divider>
        <el-tag :type="eligibility.eligible ? 'success' : 'danger'">
          {{ eligibility.eligible ? '可进入正式输出' : '被门禁阻断' }}
        </el-tag>
        <ul v-if="eligibility.reasons.length" class="reasons">
          <li v-for="(r, i) in eligibility.reasons" :key="i">
            <el-tag size="small" type="danger">{{ r.code }}</el-tag> {{ r.description }}
          </li>
        </ul>
      </template>
    </el-card>

    <el-card shadow="never" header="FormalOutput 门禁（preflight / finalize）">
      <el-form :inline="true" size="default">
        <el-form-item label="目标类型">
          <el-select v-model="targetType" style="width: 200px">
            <el-option label="底稿结论" value="workpaper_conclusion" />
            <el-option label="附注" value="note" />
            <el-option label="报告段落" value="report_section" />
            <el-option label="交付件" value="deliverable" />
            <el-option label="归档包" value="archive" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标 ID">
          <el-input v-model="targetId" placeholder="target_id" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="gate.loading.value" @click="preflight">Preflight</el-button>
          <el-button :disabled="!preflightResult?.watermark" @click="finalize">Finalize</el-button>
        </el-form-item>
      </el-form>

      <div v-for="g in gateEvaluations" :key="g.title" class="gate-result">
        <div class="gate-title">
          {{ g.title }}：
          <el-tag size="small" :type="g.ev.passed ? 'success' : 'danger'">
            {{ g.ev.passed ? '通过' : `阻断(${g.ev.verdict})` }}
          </el-tag>
          <el-tag v-if="g.ev.degraded" size="small" type="warning" style="margin-left: 6px">依赖降级</el-tag>
        </div>
        <div class="gate-meta">证据数 {{ g.ev.evidence_count }} · watermark {{ g.ev.watermark ?? '-' }}</div>
        <ul v-if="g.ev.blocking_reasons.length" class="reasons danger">
          <li v-for="(r, i) in g.ev.blocking_reasons" :key="i">{{ r.code }}: {{ r.description }}</li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
.reasons { margin: 8px 0 0; padding-left: 18px; font-size: 13px; }
.reasons li { margin-bottom: 4px; }
.reasons.danger { color: #f56c6c; }
.gate-result { margin-top: 12px; }
.gate-title { font-weight: 500; margin-bottom: 6px; }
.gate-meta { font-size: 12px; color: #606266; }
</style>
