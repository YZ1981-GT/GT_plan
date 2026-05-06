<template>
  <el-dialog
    v-model="visible"
    title="批量委派底稿"
    width="900px"
    append-to-body
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 步骤 1：选择策略 + 候选人 -->
    <div v-if="step === 1" class="gt-batch-assign-step1">
      <el-form label-width="100px" :model="form">
        <el-form-item label="分配策略">
          <el-radio-group v-model="form.strategy">
            <el-radio value="manual">手动（统一分配给同一人）</el-radio>
            <el-radio value="round_robin">轮询（均匀分配）</el-radio>
            <el-radio value="by_level">按职级（按底稿复杂度匹配）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="候选人">
          <div class="gt-batch-candidates">
            <el-table
              :data="filteredCandidates"
              size="small"
              max-height="200"
              @selection-change="onCandidateSelectionChange"
              ref="candidateTableRef"
              row-key="user_id"
            >
              <el-table-column type="selection" width="40" reserve-selection />
              <el-table-column prop="staff_name" label="姓名" min-width="120" />
              <el-table-column prop="role" label="角色" min-width="100">
                <template #default="{ row }">
                  {{ roleLabel(row.role) }}
                </template>
              </el-table-column>
              <el-table-column prop="staff_title" label="职级" min-width="100" />
            </el-table>
            <div v-if="!candidates.length" class="gt-batch-no-candidates">
              暂无候选人（需项目中有 auditor/senior_auditor/manager 角色成员）
            </div>
          </div>
        </el-form-item>

        <el-form-item label="复核人">
          <el-select
            v-model="form.reviewer_id"
            placeholder="可选，统一指定复核人"
            clearable
            style="width: 300px"
          >
            <el-option
              v-for="c in candidates"
              :key="c.user_id"
              :label="`${c.staff_name} (${roleLabel(c.role)})`"
              :value="c.user_id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <div class="gt-batch-step1-info">
        <el-tag type="info" size="small">已选底稿：{{ wpIds.length }} 张</el-tag>
        <el-tag v-if="selectedCandidates.length" type="success" size="small">
          已选候选人：{{ selectedCandidates.length }} 人
        </el-tag>
      </div>
    </div>

    <!-- 步骤 2：预览分配结果 -->
    <div v-if="step === 2" class="gt-batch-assign-step2">
      <div class="gt-batch-preview-header">
        <span>分配预览（可逐行修改编制人）</span>
        <el-tag type="info" size="small">策略：{{ strategyLabel }}</el-tag>
      </div>
      <el-table
        :data="previewAssignments"
        size="small"
        max-height="400"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="wp_code" label="底稿编号" min-width="120" />
        <el-table-column prop="wp_name" label="底稿名称" min-width="180" />
        <el-table-column label="编制人" min-width="180">
          <template #default="{ row }">
            <el-select
              v-model="row.user_id"
              size="small"
              style="width: 100%"
            >
              <el-option
                v-for="c in selectedCandidates"
                :key="c.user_id"
                :label="`${c.staff_name} (${roleLabel(c.role)})`"
                :value="c.user_id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="form.reviewer_id" label="复核人" min-width="120">
          <template #default>
            {{ reviewerName }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <div class="gt-batch-footer">
        <el-button @click="onClose">取消</el-button>
        <template v-if="step === 1">
          <el-button
            type="primary"
            :disabled="!canPreview"
            @click="onPreview"
          >
            预览分配
          </el-button>
        </template>
        <template v-else>
          <el-button @click="step = 1">← 返回修改</el-button>
          <el-button
            type="primary"
            :loading="submitting"
            @click="onSubmit"
          >
            确认提交
          </el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { listAssignments, type Assignment } from '@/services/staffApi'

// ── Props & Emits ──

interface Props {
  modelValue: boolean
  projectId: string
  wpIds: string[]
  wpList: Array<{ id: string; wp_code?: string; wp_name?: string; audit_cycle?: string }>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'assigned', result: { updated: number; notifications_sent: number; message: string }): void
}>()

// ── State ──

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const step = ref(1)
const submitting = ref(false)
const candidates = ref<CandidateItem[]>([])
const selectedCandidates = ref<CandidateItem[]>([])
const candidateTableRef = ref<any>(null)

interface CandidateItem {
  user_id: string
  staff_id: string
  staff_name: string
  role: string
  staff_title?: string
}

const form = ref({
  strategy: 'round_robin' as 'manual' | 'round_robin' | 'by_level',
  reviewer_id: null as string | null,
})

interface PreviewItem {
  wp_id: string
  wp_code: string
  wp_name: string
  user_id: string
}

const previewAssignments = ref<PreviewItem[]>([])

// ── Computed ──

const filteredCandidates = computed(() => candidates.value)

const canPreview = computed(() => {
  if (form.value.strategy === 'manual') {
    return selectedCandidates.value.length === 1
  }
  return selectedCandidates.value.length >= 1
})

const strategyLabel = computed(() => {
  const map: Record<string, string> = {
    manual: '手动',
    round_robin: '轮询',
    by_level: '按职级',
  }
  return map[form.value.strategy] || form.value.strategy
})

const reviewerName = computed(() => {
  if (!form.value.reviewer_id) return '-'
  const c = candidates.value.find(c => c.user_id === form.value.reviewer_id)
  return c ? c.staff_name : '未知'
})

// ── Role label helper ──

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    auditor: '审计员',
    senior_auditor: '高级审计员',
    manager: '经理',
    signing_partner: '签字合伙人',
    qc: '质控',
  }
  return map[role] || role
}

// ── Load candidates ──

async function loadCandidates() {
  try {
    const assignments: Assignment[] = await listAssignments(props.projectId)
    // 只保留 auditor / senior_auditor / manager 角色
    const validRoles = new Set(['auditor', 'senior_auditor', 'manager'])
    const roleOrder: Record<string, number> = { manager: 0, senior_auditor: 1, auditor: 2 }
    candidates.value = assignments
      .filter(a => validRoles.has(a.role))
      .map(a => ({
        user_id: a.staff_id,
        staff_id: a.staff_id,
        staff_name: a.staff_name || a.employee_no || a.staff_id,
        role: a.role,
        staff_title: a.staff_title,
      }))
      .sort((a, b) => (roleOrder[a.role] ?? 9) - (roleOrder[b.role] ?? 9) || a.staff_name.localeCompare(b.staff_name))
  } catch {
    candidates.value = []
  }
}

// ── Candidate selection ──

function onCandidateSelectionChange(selection: CandidateItem[]) {
  selectedCandidates.value = selection
}

// ── Preview logic (client-side strategy computation) ──

function computePreview(): PreviewItem[] {
  const wpItems = props.wpList.filter(w => props.wpIds.includes(w.id))
  const cands = selectedCandidates.value

  if (!cands.length || !wpItems.length) return []

  if (form.value.strategy === 'manual') {
    // All assigned to the single selected candidate
    const userId = cands[0].user_id
    return wpItems.map(w => ({
      wp_id: w.id,
      wp_code: w.wp_code || '',
      wp_name: w.wp_name || '',
      user_id: userId,
    }))
  }

  if (form.value.strategy === 'round_robin') {
    // Round-robin distribution
    return wpItems.map((w, idx) => ({
      wp_id: w.id,
      wp_code: w.wp_code || '',
      wp_name: w.wp_name || '',
      user_id: cands[idx % cands.length].user_id,
    }))
  }

  if (form.value.strategy === 'by_level') {
    // TODO [Batch 3]: by_level 策略的前端预览逻辑应改为调用后端 preview endpoint
    // （POST /api/workpapers/batch-assign-enhanced/preview），避免前端 CYCLE_COMPLEXITY_MAP
    // 与后端 batch_assign_strategy.py 的映射漂移。当前为客户端本地计算，仅作临时方案。
    // By level: complex cycles (D,K,N) → manager/senior, simple → auditor
    const complexCycles = new Set(['D', 'K', 'N', 'G', 'H', 'I'])
    const seniors = cands.filter(c => c.role === 'manager' || c.role === 'senior_auditor')
    const juniors = cands.filter(c => c.role === 'auditor')
    // Fallback: if no seniors or juniors, use all candidates
    const seniorPool = seniors.length ? seniors : cands
    const juniorPool = juniors.length ? juniors : cands

    let seniorIdx = 0
    let juniorIdx = 0

    return wpItems.map(w => {
      const cycle = (w.audit_cycle || w.wp_code?.charAt(0) || '').toUpperCase()
      const isComplex = complexCycles.has(cycle)
      let userId: string
      if (isComplex) {
        userId = seniorPool[seniorIdx % seniorPool.length].user_id
        seniorIdx++
      } else {
        userId = juniorPool[juniorIdx % juniorPool.length].user_id
        juniorIdx++
      }
      return {
        wp_id: w.id,
        wp_code: w.wp_code || '',
        wp_name: w.wp_name || '',
        user_id: userId,
      }
    })
  }

  return []
}

function onPreview() {
  previewAssignments.value = computePreview()
  step.value = 2
}

// ── Submit ──

async function onSubmit() {
  submitting.value = true
  try {
    // Build override_assignments from preview (user may have modified)
    const overrides = previewAssignments.value.map(p => ({
      wp_id: p.wp_id,
      user_id: p.user_id,
    }))

    const payload = {
      wp_ids: props.wpIds,
      strategy: form.value.strategy,
      candidates: selectedCandidates.value.map(c => c.user_id),
      reviewer_id: form.value.reviewer_id || undefined,
      override_assignments: overrides,
    }

    const { data } = await http.post('/api/workpapers/batch-assign-enhanced', payload)

    const result = {
      updated: data.updated ?? 0,
      notifications_sent: data.notifications_sent ?? 0,
      message: data.message ?? '',
    }

    ElMessage.success(`已分配 ${result.updated} 张，${result.notifications_sent} 人收到通知`)
    emit('assigned', result)
    onClose()
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    ElMessage.error(detail || '批量委派失败，请重试')
  } finally {
    submitting.value = false
  }
}

// ── Close / Reset ──

function onClose() {
  visible.value = false
  step.value = 1
  form.value = { strategy: 'round_robin', reviewer_id: null }
  selectedCandidates.value = []
  previewAssignments.value = []
}

// ── Watch for dialog open ──

watch(visible, (val) => {
  if (val) {
    step.value = 1
    loadCandidates()
  }
})
</script>

<style scoped>
.gt-batch-assign-step1 {
  min-height: 300px;
}

.gt-batch-candidates {
  width: 100%;
}

.gt-batch-no-candidates {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.gt-batch-step1-info {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.gt-batch-assign-step2 {
  min-height: 300px;
}

.gt-batch-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.gt-batch-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
