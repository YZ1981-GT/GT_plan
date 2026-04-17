<template>
  <div class="gt-procedure gt-fade-in">
    <div class="gt-proc-header">
      <h2 class="gt-page-title">审计程序裁剪</h2>
      <div class="gt-proc-actions">
        <el-button size="small" @click="showRefDialog = true">参照其他单位</el-button>
        <el-button size="small" @click="saveTrim" :loading="saving">保存裁剪</el-button>
      </div>
    </div>

    <!-- 审计循环 Tab -->
    <el-tabs v-model="activeCycle" @tab-change="loadProcedures">
      <el-tab-pane v-for="c in cycles" :key="c.code" :label="c.label" :name="c.code" />
    </el-tabs>

    <!-- 程序列表 -->
    <el-table :data="procedures" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="procedure_code" label="编号" width="120" />
      <el-table-column prop="procedure_name" label="程序名称" min-width="250" />
      <el-table-column label="状态" width="200">
        <template #default="{ row }">
          <el-radio-group v-model="row.status" size="small">
            <el-radio-button value="execute">执行</el-radio-button>
            <el-radio-button value="skip">跳过</el-radio-button>
            <el-radio-button value="not_applicable">不适用</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="裁剪理由" min-width="200">
        <template #default="{ row }">
          <el-input v-if="row.status !== 'execute'" v-model="row.skip_reason"
            placeholder="请填写理由" size="small" />
          <span v-else class="gt-text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="wp_code" label="关联底稿" width="100" />
      <el-table-column label="执行状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="execTagType(row.execution_status)" size="small">
            {{ execLabel(row.execution_status) }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-button style="margin-top: 12px" @click="addCustom">+ 新增自定义程序</el-button>

    <!-- 参照弹窗 -->
    <el-dialog v-model="showRefDialog" title="参照其他单位程序" width="450px">
      <el-form label-width="80px">
        <el-form-item label="参照项目">
          <el-input v-model="refProjectId" placeholder="输入项目ID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRefDialog = false">取消</el-button>
        <el-button type="primary" @click="applyRef">应用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const cycles = [
  { code: 'B', label: 'B 初步业务' }, { code: 'C', label: 'C 控制测试' },
  { code: 'D', label: 'D 收入' }, { code: 'E', label: 'E 货币资金' },
  { code: 'F', label: 'F 存货' }, { code: 'G', label: 'G 投资' },
  { code: 'H', label: 'H 固定资产' }, { code: 'I', label: 'I 无形资产' },
  { code: 'J', label: 'J 职工薪酬' }, { code: 'K', label: 'K 管理' },
  { code: 'L', label: 'L 债务' }, { code: 'M', label: 'M 权益' },
  { code: 'N', label: 'N 税金' }, { code: 'A', label: 'A 完成阶段' },
]

const activeCycle = ref('D')
const procedures = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const showRefDialog = ref(false)
const refProjectId = ref('')

function execTagType(s: string) {
  return { not_started: 'info', in_progress: 'warning', completed: 'success', reviewed: '' }[s] || 'info'
}
function execLabel(s: string) {
  return { not_started: '未开始', in_progress: '进行中', completed: '已完成', reviewed: '已复核' }[s] || s
}

async function loadProcedures() {
  loading.value = true
  try {
    // 先尝试获取，没有则初始化
    let { data } = await http.get(`/api/projects/${projectId.value}/procedures/${activeCycle.value}`)
    let procs = data.data ?? data
    if (!procs || procs.length === 0) {
      const initRes = await http.post(`/api/projects/${projectId.value}/procedures/${activeCycle.value}/init`)
      procs = (initRes.data.data ?? initRes.data).procedures || []
    }
    procedures.value = procs
  } finally { loading.value = false }
}

async function saveTrim() {
  saving.value = true
  try {
    await http.put(`/api/projects/${projectId.value}/procedures/${activeCycle.value}/trim`, {
      items: procedures.value.map(p => ({ id: p.id, status: p.status, skip_reason: p.skip_reason })),
    })
    ElMessage.success('裁剪已保存')
  } finally { saving.value = false }
}

async function addCustom() {
  const name = prompt('请输入自定义程序名称')
  if (!name) return
  const { data } = await http.post(`/api/projects/${projectId.value}/procedures/${activeCycle.value}/custom`, {
    procedure_name: name,
  })
  procedures.value.push(data.data ?? data)
}

async function applyRef() {
  if (!refProjectId.value) return
  try {
    await http.post(`/api/projects/${projectId.value}/procedures/${activeCycle.value}/apply-scheme`, null, {
      params: { source_project_id: refProjectId.value },
    })
    ElMessage.success('已应用参照方案')
    showRefDialog.value = false
    await loadProcedures()
  } catch { ElMessage.error('应用失败') }
}

onMounted(loadProcedures)
</script>

<style scoped>
.gt-procedure { padding: var(--gt-space-4); }
.gt-proc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-proc-actions { display: flex; gap: var(--gt-space-2); }
.gt-text-muted { color: #ccc; }
</style>
