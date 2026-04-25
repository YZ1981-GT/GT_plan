<template>
  <div class="gt-project-team">
    <div class="team-header">
      <h3>项目团队</h3>
      <el-button type="primary" @click="showInvite = true">邀请成员</el-button>
    </div>

    <el-table :data="teamMembers" stripe>
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="display_name" label="姓名" />
      <el-table-column prop="role" label="角色" />
      <el-table-column prop="project_role" label="项目角色" />
      <el-table-column prop="assigned_cycles" label="审计期间" />
      <el-table-column label="操作" width="160">
        <template #default="{ row: _row }">
          <el-button size="small" @click="editRole(_row)">修改角色</el-button>
          <el-button size="small" type="danger" @click="removeMember(_row)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog append-to-body v-model="showInvite" title="邀请成员" width="500px">
      <el-form :model="inviteForm" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="inviteForm.username" />
        </el-form-item>
        <el-form-item label="项目角色">
          <el-select v-model="inviteForm.project_role">
            <el-option label="项目经理" value="manager" />
            <el-option label="审计员" value="auditor" />
            <el-option label="QC审核员" value="qc_reviewer" />
            <el-option label="只读" value="readonly" />
          </el-select>
        </el-form-item>
        <el-form-item label="分配期间">
          <el-select v-model="inviteForm.assigned_cycles" multiple placeholder="选择审计期间">
            <el-option label="2024年度" value="2024" />
            <el-option label="2025年度" value="2025" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showInvite = false">取消</el-button>
        <el-button type="primary" @click="invite">确认邀请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { userApi } from '@/services/collaborationApi'

const teamMembers = ref<any[]>([])
const showInvite = ref(false)
const inviteForm = ref({ username: '', project_role: 'auditor', assigned_cycles: [] as string[] })

onMounted(async () => {
  try {
    const { data } = await userApi.list()
    teamMembers.value = data
  } catch (e) {
    console.error(e)
  }
})

async function invite() {
  try {
    // await userApi.invite(projectId, inviteForm.value)
    ElMessage.success('邀请已发送')
    showInvite.value = false
  } catch (e) {
    ElMessage.error('邀请失败')
  }
}

async function removeMember(row: any) {
  // await userApi.remove(projectId, row.id)
  teamMembers.value = teamMembers.value.filter(m => m.id !== row.id)
}

function editRole(_row: any) {
  // implement role edit dialog
}
</script>

<style scoped>
.gt-project-team {}
.team-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
