<!--
  ProjectAuditPhaseSection — 项目设置「年度准则」页的「审计阶段」区块
  （spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1）

  当前审计阶段（预审 / 年审）+ 预审截止日。抽凭、挂凭、从序时账挂入生成的凭证检查行按当前阶段标记。
  只有项目经理、合伙人（含签字合伙人）与管理员能改（后端判，接口回 can_edit）；改动写审计日志。
-->
<template>
  <section class="audit-phase-section" aria-labelledby="audit-phase-section-title">
    <h4 id="audit-phase-section-title" class="audit-phase-section__title">审计阶段</h4>
    <p class="audit-phase-section__desc">{{ DESC }}</p>
    <el-form label-width="100px" :disabled="!editable" @submit.prevent>
      <el-form-item label="当前阶段">
        <el-radio-group v-model="form.phase" aria-label="当前审计阶段">
          <el-radio value="preliminary">预审</el-radio>
          <el-radio value="final">年审</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="预审截止日">
        <el-date-picker
          v-model="form.cutoff"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          clearable
          :disabled-date="outsidePeriod"
          aria-label="预审截止日"
        />
        <span class="audit-phase-section__hint">{{ periodHint }}</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="ap.saving.value" :disabled="!dirty" @click="onSave">
          保存审计阶段
        </el-button>
      </el-form-item>
    </el-form>
    <p v-if="ap.state.value && !ap.canEdit.value" class="audit-phase-section__hint" role="note">
      只有项目经理、合伙人（含签字合伙人）可以修改审计阶段
    </p>
    <p v-else-if="ap.error.value" class="audit-phase-section__hint" role="alert">{{ ap.error.value }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  auditPhaseSaveFailureReason,
  useProjectAuditPhase,
  type AuditPhase,
} from '@/composables/useProjectAuditPhase'

defineOptions({ name: 'ProjectAuditPhaseSection' })

const props = defineProps<{ projectId: string; readonly?: boolean }>()

const DESC = '抽凭、挂凭和从序时账挂入生成的凭证检查行按当前阶段标记。年审阶段预审行只读；'
  + '年审抽凭时可选「只抽剩余期间」或「全年扣除预审已抽」。'

const ap = useProjectAuditPhase(() => props.projectId)
const form = reactive<{ phase: AuditPhase; cutoff: string | null }>({ phase: 'final', cutoff: null })

const editable = computed(() => ap.canEdit.value && !props.readonly)
const dirty = computed(() => {
  const s = ap.state.value
  return !!s && (form.phase !== s.phase || (form.cutoff || null) !== s.interimCutoffDate)
})

const periodHint = computed(() => {
  const s = ap.state.value
  if (s?.auditPeriodStart && s.auditPeriodEnd) {
    return `须在审计期间 ${s.auditPeriodStart} 至 ${s.auditPeriodEnd} 内，且早于期末`
  }
  return '须早于审计期末；年审「只抽剩余期间」从截止日次日起算'
})

function outsidePeriod(day: Date): boolean {
  const s = ap.state.value
  const ymd = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
  if (s?.auditPeriodStart && ymd < s.auditPeriodStart) return true
  if (s?.auditPeriodEnd && ymd >= s.auditPeriodEnd) return true
  return false
}

function syncFormFromState() {
  const s = ap.state.value
  if (!s) return
  form.phase = s.phase
  form.cutoff = s.interimCutoffDate
}

watch(() => ap.state.value, syncFormFromState)

async function onSave() {
  try {
    const changed = await ap.save({ phase: form.phase, interimCutoffDate: form.cutoff || null })
    ElMessage.success(changed ? '审计阶段已保存' : '审计阶段没有变化')
  } catch (err) {
    ElMessage.error(auditPhaseSaveFailureReason(err))
    syncFormFromState()
  }
}

onMounted(async () => {
  await ap.load(true)
  syncFormFromState()
})
</script>

<style scoped>
.audit-phase-section {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--gt-color-border, #e4e7ed);
}

.audit-phase-section__title {
  font-size: var(--gt-font-size-base, 14px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin: 0 0 8px 0;
}

.audit-phase-section__desc,
.audit-phase-section__hint {
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--gt-font-size-sm, 13px);
  line-height: 1.6;
}

.audit-phase-section__desc {
  margin: 0 0 12px 0;
}

.audit-phase-section__hint {
  margin-left: 12px;
}
</style>
