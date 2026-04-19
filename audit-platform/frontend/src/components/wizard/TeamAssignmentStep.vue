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

    <!-- 添加成员弹窗：勾选模式 -->
    <el-dialog append-to-body v-model="showAddDialog" width="700px" :close-on-click-modal="false">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; color: var(--gt-color-primary)">
          <el-icon><User /></el-icon> 从人员库选择成员
        </div>
      </template>

      <!-- 搜索栏 -->
      <div style="display: flex; gap: 10px; margin-bottom: 12px">
        <el-input v-model="staffSearch" placeholder="搜索姓名/工号" clearable style="flex: 1" @input="debouncedLoadStaffList" />
        <el-select v-model="staffDeptFilter" placeholder="部门" clearable style="width: 150px" @change="loadStaffList">
          <el-option label="审计一部" value="审计一部" />
          <el-option label="审计二部" value="审计二部" />
          <el-option label="审计三部" value="审计三部" />
        </el-select>
      </div>

      <!-- 人员列表（勾选） -->
      <el-table
        ref="staffTableRef"
        :data="staffListForSelect"
        v-loading="staffListLoading"
        size="small"
        max-height="360"
        @selection-change="onStaffSelectionChange"
        row-key="id"
      >
        <el-table-column type="selection" width="45" :selectable="isSelectable" />
        <el-table-column prop="name" label="姓名" width="100">
          <template #default="{ row }">
            <span style="font-weight: 600">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="employee_no" label="工号" width="90" />
        <el-table-column prop="department" label="部门" width="100" />
        <el-table-column prop="title" label="职级" width="90" />
        <el-table-column prop="partner_name" label="所属合伙人" width="110" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="isAlreadyAdded(row.id)" type="info" size="small">已添加</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 8px; font-size: 13px; color: #888">
        已选 <span style="color: var(--gt-color-primary); font-weight: 600">{{ selectedStaffIds.length }}</span> 人
        <el-button link type="primary" size="small" @click="showQuickCreate = true" style="margin-left: 16px">搜不到？快速创建</el-button>
      </div>

      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :disabled="selectedStaffIds.length === 0" @click="addSelectedMembers">
          添加 {{ selectedStaffIds.length }} 人
        </el-button>
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
import { User } from '@element-plus/icons-vue'
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
const creating = ref(false)
const newStaff = ref({ name: '', title: '', department: '', phone: '' })

// 勾选模式相关
const staffSearch = ref('')
const staffDeptFilter = ref('')
const staffListForSelect = ref<StaffMember[]>([])
const staffListLoading = ref(false)
const selectedStaffIds = ref<string[]>([])
const staffTableRef = ref<any>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function debouncedLoadStaffList() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadStaffList, 300)
}

async function loadStaffList() {
  staffListLoading.value = true
  try {
    const res = await listStaff({
      search: staffSearch.value || undefined,
      department: staffDeptFilter.value || undefined,
      limit: 50,
    })
    staffListForSelect.value = res.items || []
  } catch { staffListForSelect.value = [] }
  finally { staffListLoading.value = false }
}

function isAlreadyAdded(id: string): boolean {
  return members.value.some(m => m.staff_id === id)
}

function isSelectable(row: StaffMember): boolean {
  return !isAlreadyAdded(row.id)
}

function onStaffSelectionChange(selection: StaffMember[]) {
  selectedStaffIds.value = selection.map(s => s.id)
}

function addSelectedMembers() {
  for (const id of selectedStaffIds.value) {
    if (isAlreadyAdded(id)) continue
    const staff = staffListForSelect.value.find(s => s.id === id)
    if (!staff) continue
    members.value.push({
      staff_id: staff.id,
      staff_name: staff.name,
      staff_title: staff.title || '',
      employee_no: staff.employee_no || '',
      role: 'auditor',
      assigned_cycles: [],
    })
  }
  ElMessage.success(`已添加 ${selectedStaffIds.value.length} 名成员`)
  showAddDialog.value = false
  selectedStaffIds.value = []
}

// 打开弹窗时加载人员列表
watch(showAddDialog, (v) => {
  if (v) {
    staffSearch.value = ''
    staffDeptFilter.value = ''
    selectedStaffIds.value = []
    loadStaffList()
  }
})

function removeMember(index: number) { members.value.splice(index, 1) }
function onRoleChange(_: number) { /* auto-save handled by validate */ }
function onCycleChange(_: number) { /* auto-save handled by validate */ }

async function quickCreateStaff() {
  if (!newStaff.value.name) { ElMessage.warning('请输入姓名'); return }
  creating.value = true
  try {
    const staff = await createStaff({ ...newStaff.value, source: 'custom' })
    showQuickCreate.value = false
    newStaff.value = { name: '', title: '', department: '', phone: '' }
    ElMessage.success('人员创建成功')
    // 刷新列表并自动添加
    await loadStaffList()
    if (!isAlreadyAdded(staff.id)) {
      members.value.push({
        staff_id: staff.id,
        staff_name: staff.name,
        staff_title: staff.title || '',
        employee_no: staff.employee_no || '',
        role: 'auditor',
        assigned_cycles: [],
      })
    }
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
