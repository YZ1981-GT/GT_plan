<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="500px"
    append-to-body
    :close-on-click-modal="false"
    @close="onClose"
  >
    <div class="gt-staff-select">
      <el-table
        :data="candidates"
        size="small"
        max-height="300"
        highlight-current-row
        @current-change="onCurrentChange"
        :loading="loading"
        empty-text="暂无候选人"
      >
        <el-table-column prop="staff_name" label="姓名" min-width="120" />
        <el-table-column prop="role" label="角色" min-width="100">
          <template #default="{ row }">
            {{ roleLabel(row.role) }}
          </template>
        </el-table-column>
        <el-table-column prop="staff_title" label="职级" min-width="100" />
      </el-table>
      <div v-if="selectedStaff" class="gt-staff-select-info">
        <el-tag type="success" size="small">
          已选：{{ selectedStaff.staff_name }}（{{ roleLabel(selectedStaff.role) }}）
        </el-tag>
      </div>
    </div>

    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedStaff"
        :loading="submitting"
        @click="onConfirm"
      >
        确认
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { listAssignments, type Assignment } from '@/services/staffApi'

interface Props {
  modelValue: boolean
  projectId: string
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '选择人员',
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'confirm', staff: { user_id: string; staff_name: string; role: string }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

interface CandidateItem {
  user_id: string
  staff_id: string
  staff_name: string
  role: string
  staff_title?: string
}

const loading = ref(false)
const submitting = ref(false)
const candidates = ref<CandidateItem[]>([])
const selectedStaff = ref<CandidateItem | null>(null)

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

async function loadCandidates() {
  loading.value = true
  try {
    const assignments: Assignment[] = await listAssignments(props.projectId)
    const validRoles = new Set(['auditor', 'senior_auditor', 'manager'])
    candidates.value = assignments
      .filter(a => validRoles.has(a.role))
      .map(a => ({
        user_id: a.staff_id,
        staff_id: a.staff_id,
        staff_name: a.staff_name || a.employee_no || a.staff_id,
        role: a.role,
        staff_title: a.staff_title,
      }))
  } catch {
    candidates.value = []
  } finally {
    loading.value = false
  }
}

function onCurrentChange(row: CandidateItem | null) {
  selectedStaff.value = row
}

function onConfirm() {
  if (selectedStaff.value) {
    emit('confirm', {
      user_id: selectedStaff.value.user_id,
      staff_name: selectedStaff.value.staff_name,
      role: selectedStaff.value.role,
    })
    onClose()
  }
}

function onClose() {
  visible.value = false
  selectedStaff.value = null
}

watch(visible, (val) => {
  if (val) {
    loadCandidates()
  }
})
</script>

<style scoped>
.gt-staff-select {
  min-height: 200px;
}

.gt-staff-select-info {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--gt-color-border-light);
}
</style>
