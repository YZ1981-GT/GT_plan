<template>
  <div class="gt-team-step">
    <div class="gt-team-header">
      <span class="gt-team-title">团队委派</span>
      <el-button type="primary" size="small" @click="showAddDialog = true">添加成员</el-button>
    </div>

    <!-- 已委派成员列表 -->
    <el-table :data="members" border stripe style="width: 100%" empty-text="暂未委派成员">
      <el-table-column prop="staff_name" label="姓名" width="120" />
      <el-table-column prop="employee_no" label="工号" width="100" />
      <el-table-column prop="staff_title" label="职级" width="100" />
      <el-table-column label="角色" width="150">
        <template #default="{ row, $index }">
          <el-select v-model="row.role" size="small" @change="onRoleChange($index)">
            <el-option label="签字合伙人" value="signing_partner" />
            <el-option label="项目经理" value="manager" />
            <el-option label="审计员" value="auditor" />
            <el-option label="质控人员" value="qc" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="审计循环" min-width="200">
        <template #default="{ row, $index }">
          <el-checkbox-group v-model="row.assigned_cycles" size="small" @change="onCycleChange($index)">
            <el-checkbox v-for="c in cycles" :key="c" :label="c">{{ c }}</el-checkbox>
          </el-checkbox-group>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeMember($index)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 添加成员弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加团队成员" width="500px">
      <el-form label-width="80px">
        <el-form-item label="搜索人员">
          <el-select v-model="selectedStaffId" filterable remote :remote-method="searchStaff"
            placeholder="输入姓名或工号搜索" style="width: 100%" :loading="searching">
            <el-option v-for="s in searchResults" :key="s.id" :label="`${s.name} (${s.employee_no || ''}) - ${s.title || ''}`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button link type="primary" @click="showQuickCreate = true">搜不到？快速创建人员</el-button>
        </el-form-item>
        <!-- 候选人负荷预览 -->
        <el-form-item v-if="selectedStaffId && selectedStaffWorkload" label="当前负荷">
          <div style="font-size: 13px; color: #666">
            参与 {{ selectedStaffWorkload.project_count }} 个项目，本周 {{ selectedStaffWorkload.week_hours }}h
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedStaffId" @click="addMember">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 快速创建人员弹窗 -->
    <el-dialog v-model="showQuickCreate" title="快速创建人员" width="450px" append-to-body>
      <el-form :model="newStaff" label-width="80px">
        <el-form-item label="姓名" required>
          <el-input v-model="newStaff.name" />
        </el-form-item>
        <el-form-item label="职级">
          <el-select v-model="newStaff.title" placeholder="选择职级" style="width: 100%">
            <el-option v-for="t in titles" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="newStaff.department" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="newStaff.phone" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showQuickCreate = false">取消</el-button>
        <el-button type="primary" @click="quickCreateStaff" :loading="creating">创建并选中</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listStaff, createStaff, listAssignments, saveAssignments, type StaffMember, type Assignment } from '@/services/staffApi'
import { useWizardStore } from '@/stores/wizard'
import http from '@/utils/http'

const props = defineProps<{ projectId?: string }>()
const wizardStore = useWizardStore()

const cycles = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
const titles = ['合伙人', '总监', '高级经理', '经理', '高级审计员', '审计员', '实习生']

interface MemberRow {
  staff_id: string
  staff_name: string
  staff_title: string
  employee_no: string
  role: string
  assigned_cycles: string[]
}

const members = ref<MemberRow[]>([])
const showAddDialog = ref(false)
const showQuickCreate = ref(false)
const selectedStaffId = ref('')
const selectedStaffWorkload = ref<any>(null)
const searchResults = ref<StaffMember[]>([])
const searching = ref(false)
const creating = ref(false)
const newStaff = ref({ name: '', title: '', department: '', phone: '' })

// 选中人员时加载负荷数据
watch(selectedStaffId, async (id) => {
  if (!id) { selectedStaffWorkload.value = null; return }
  try {
    const { data } = await http.get('/api/dashboard/staff-workload')
    const all = data.data ?? data
    selectedStaffWorkload.value = (Array.isArray(all) ? all : []).find((s: any) => s.staff_id === id) || null
  } catch { selectedStaffWorkload.value = null }
})

async function searchStaff(query: string) {
  if (!query || query.length < 1) { searchResults.value = []; return }
  searching.value = true
  try {
    const res = await listStaff({ search: query, limit: 20 })
    searchResults.value = res.items
  } finally { searching.value = false }
}

function addMember() {
  const staff = searchResults.value.find(s => s.id === selectedStaffId.value)
  if (!staff) return
  if (members.value.some(m => m.staff_id === staff.id)) {
    ElMessage.warning('该成员已在团队中')
    return
  }
  members.value.push({
    staff_id: staff.id,
    staff_name: staff.name,
    staff_title: staff.title || '',
    employee_no: staff.employee_no || '',
    role: 'auditor',
    assigned_cycles: [],
  })
  showAddDialog.value = false
  selectedStaffId.value = ''
}

function removeMember(index: number) { members.value.splice(index, 1) }
function onRoleChange(_: number) { /* auto-save handled by validate */ }
function onCycleChange(_: number) { /* auto-save handled by validate */ }

async function quickCreateStaff() {
  if (!newStaff.value.name) { ElMessage.warning('请输入姓名'); return }
  creating.value = true
  try {
    const staff = await createStaff(newStaff.value)
    selectedStaffId.value = staff.id
    searchResults.value = [staff]
    showQuickCreate.value = false
    newStaff.value = { name: '', title: '', department: '', phone: '' }
    ElMessage.success('人员创建成功')
    addMember()
  } finally { creating.value = false }
}

async function validate(): Promise<boolean> {
  // 保存到 project_assignments 表
  if (props.projectId) {
    try {
      await saveAssignments(props.projectId, members.value.map(m => ({
        staff_id: m.staff_id, role: m.role, assigned_cycles: m.assigned_cycles,
      })))
    } catch { ElMessage.error('保存委派失败'); return false }
  }
  // 保存到 wizard_state
  await wizardStore.saveStep('team_assignment', {
    members: members.value.map(m => ({ staff_id: m.staff_id, staff_name: m.staff_name, role: m.role, assigned_cycles: m.assigned_cycles })),
  })
  return true
}

defineExpose({ validate })

onMounted(async () => {
  // 恢复已有委派
  if (props.projectId) {
    try {
      const existing = await listAssignments(props.projectId)
      members.value = existing.map((a: Assignment) => ({
        staff_id: a.staff_id, staff_name: a.staff_name || '', staff_title: a.staff_title || '',
        employee_no: a.employee_no || '', role: a.role, assigned_cycles: a.assigned_cycles || [],
      }))
    } catch { /* ignore */ }
  }
  // 从 wizard_state 恢复
  const saved = wizardStore.stepData?.team_assignment as any
  if (saved?.members && members.value.length === 0) {
    members.value = saved.members
  }
})
</script>

<style scoped>
.gt-team-step { padding: var(--gt-space-2) 0; }
.gt-team-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-team-title { font-size: 16px; font-weight: 600; color: var(--gt-color-primary); }
</style>
