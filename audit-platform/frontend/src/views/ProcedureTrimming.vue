<template>
  <div class="gt-procedure gt-fade-in">
    <div class="gt-proc-header">
      <GtPageHeader title="审计程序裁剪" :show-back="false">
        <template #actions>
          <el-button size="small" @click="showRefDialog = true">参照其他单位</el-button>
          <el-button size="small" @click="saveTrim" :loading="saving">保存裁剪</el-button>
        </template>
      </GtPageHeader>
    </div>

    <!-- 程序执行进度可视化 -->
    <div class="gt-proc-progress">
      <div class="gt-proc-progress-stats">
        <span>总计 <b>{{ progressStats.total }}</b></span>
        <span style="color: #67c23a">已完成 <b>{{ progressStats.completed }}</b></span>
        <span style="color: #e6a23c">进行中 <b>{{ progressStats.in_progress }}</b></span>
        <span style="color: #909399">未开始 <b>{{ progressStats.pending }}</b></span>
        <span style="color: #f56c6c">跳过 <b>{{ progressStats.skipped }}</b></span>
      </div>
      <el-progress
        :percentage="progressStats.total > 0 ? Math.round(progressStats.completed / progressStats.total * 100) : 0"
        :stroke-width="12"
        :color="[
          { color: '#909399', percentage: 20 },
          { color: '#e6a23c', percentage: 60 },
          { color: '#67c23a', percentage: 100 },
        ]"
        style="margin-top: 8px"
      />
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
          <el-tag :type="(execTagType(row.execution_status)) || undefined" size="small">
            {{ execLabel(row.execution_status) }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-button style="margin-top: 12px" @click="addCustom">+ 新增自定义程序</el-button>

    <!-- 参照弹窗 -->
    <el-dialog append-to-body v-model="showRefDialog" title="参照其他单位程序" width="450px">
      <el-form label-width="80px">
        <el-form-item label="参照项目">
          <el-select
            v-model="refProjectId"
            filterable
            placeholder="选择参照项目"
            style="width: 100%"
          >
            <el-option
              v-for="p in projectOptions"
              :key="p.id"
              :label="p.name || p.client_name || p.id"
              :value="p.id"
            />
          </el-select>
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
import {
  getProcedures, updateProcedureTrim, initProcedures,
  addCustomProcedure, applyProcedureScheme, listProjects,
} from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

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
const projectOptions = ref<any[]>([])

const progressStats = computed(() => {
  const procs = procedures.value
  const total = procs.length
  const completed = procs.filter(p => p.execution_status === 'completed' || p.execution_status === 'reviewed').length
  const in_progress = procs.filter(p => p.execution_status === 'in_progress').length
  const skipped = procs.filter(p => p.status === 'skip' || p.status === 'not_applicable').length
  const pending = total - completed - in_progress - skipped
  return { total, completed, in_progress, skipped, pending }
})

function execTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return ({ not_started: 'info', in_progress: 'warning', completed: 'success', reviewed: '' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s] || 'info'
}
function execLabel(s: string) {
  return { not_started: '未开始', in_progress: '进行中', completed: '已完成', reviewed: '已复核' }[s] || s
}

async function loadProcedures() {
  loading.value = true
  try {
    let procs = await getProcedures(projectId.value, activeCycle.value)
    if (!procs || procs.length === 0) {
      procs = await initProcedures(projectId.value, activeCycle.value)
    }
    procedures.value = procs
  } finally { loading.value = false }
}

async function saveTrim() {
  saving.value = true
  try {
    await updateProcedureTrim(projectId.value, activeCycle.value,
      procedures.value.map(p => ({ id: p.id, status: p.status, skip_reason: p.skip_reason })))
    ElMessage.success('裁剪已保存')
  } finally { saving.value = false }
}

async function addCustom() {
  const name = prompt('请输入自定义程序名称')
  if (!name) return
  const newProc = await addCustomProcedure(projectId.value, activeCycle.value, { procedure_name: name })
  procedures.value.push(newProc)
}

async function applyRef() {
  if (!refProjectId.value) return
  try {
    await applyProcedureScheme(projectId.value, activeCycle.value, refProjectId.value)
    ElMessage.success('已应用参照方案')
    showRefDialog.value = false
    await loadProcedures()
  } catch (e: any) { handleApiError(e, '应用') }
}

onMounted(async () => {
  await loadProcedures()
  // 需求 37.1：加载项目列表供"参照其他单位"下拉选择
  try {
    const list = await listProjects()
    projectOptions.value = Array.isArray(list) ? list : []
  } catch { /* 静默处理，下拉为空但不影响主流程 */ }
})
</script>

<style scoped>
.gt-procedure { padding: var(--gt-space-4); }
.gt-proc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-proc-actions { display: flex; gap: var(--gt-space-2); }
.gt-proc-progress {
  margin-bottom: var(--gt-space-3); padding: 12px 16px;
  background: #f8f5fc; border-radius: var(--gt-radius-md, 8px);
  border: 1px solid #e0d4f0;
}
.gt-proc-progress-stats { display: flex; gap: 16px; font-size: 13px; color: #666; }
.gt-proc-progress-stats b { font-size: 15px; }
.gt-text-muted { color: #ccc; }
</style>
