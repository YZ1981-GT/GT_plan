<template>
  <el-dialog
    :model-value="modelValue"
    title="自动识别合并范围"
    width="720px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div v-loading="loading">
      <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" />
      <p class="gt-scope-hint">
        合并范围由各项目基本信息中的企业代码、上级代码和与上级关系自动推导。保存基本信息后，系统会自动刷新本范围。
      </p>

      <el-empty v-if="!loading && !members.length" description="暂未识别到下级企业" />
      <el-alert v-if="!loading && !members.length && rootCompanyCode" type="info" :closable="false" show-icon
        :title="`请在各子公司/分公司项目的基本信息中把上级代码填为 ${rootCompanyCode}`" />

      <el-table v-if="members.length" :data="members" border size="small" max-height="420" data-testid="consol-scope-members">
        <el-table-column label="企业名称" min-width="200">
          <template #default="{ row }">{{ row.companyName || row.label || '未命名企业' }}</template>
        </el-table-column>
        <el-table-column label="企业代码" width="170" prop="companyCode" />
        <el-table-column label="与上级关系" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.relation === 'branch' ? '分公司' : '子公司' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="年度" width="90" align="center">
          <template #default="{ row }">{{ row.year || year || '未解析' }}</template>
        </el-table-column>
        <el-table-column label="项目口径" min-width="150">
          <template #default="{ row }">
            <el-tag v-if="row.consolidatedProjectId" type="primary" size="small" effect="plain">合并</el-tag>
            <el-tag v-if="row.standaloneProjectId" type="success" size="small" effect="plain">单户</el-tag>
            <span v-if="!row.consolidatedProjectId && !row.standaloneProjectId">未建对应项目</span>
          </template>
        </el-table-column>
      </el-table>

      <el-alert v-if="diagnostics.length" type="warning" :closable="false" show-icon class="gt-scope-diagnostics"
        title="企业树还有需要关注的提示">
        <ul><li v-for="(item, index) in diagnostics" :key="`${item.code}-${index}`">{{ item.message }}</li></ul>
      </el-alert>
    </div>

    <template #footer>
      <el-button type="primary" @click="emit('update:modelValue', false)">知道了</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'

interface ScopeMember {
  companyName: string
  companyCode: string
  relation: string | null
  year: number | null
  consolidatedProjectId: string | null
  standaloneProjectId: string | null
  label?: string
}
interface Diagnostic { code: string; message: string }
interface ForestNode extends ScopeMember { children?: ForestNode[] }
interface ForestTree { year?: number | null; children?: ForestNode[] }

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  attached: [count: number]
}>()
const loading = ref(false)
const loadError = ref('')
const members = ref<ScopeMember[]>([])
const diagnostics = ref<Diagnostic[]>([])
const rootCompanyCode = ref('')
const year = ref<number | null>(null)

function flatten(nodes: ForestNode[], out: ScopeMember[] = []): ScopeMember[] {
  for (const node of nodes || []) {
    if (node.relation === 'subsidiary' || node.relation === 'branch') {
      out.push({
        companyName: node.companyName || node.label || '', companyCode: node.companyCode,
        relation: node.relation, year: node.year ?? year.value,
        consolidatedProjectId: node.consolidatedProjectId || null,
        standaloneProjectId: node.standaloneProjectId || null, label: node.label,
      })
    }
    flatten(node.children || [], out)
  }
  return out
}

function findRoot(trees: ForestTree[]): ForestNode | null {
  for (const tree of trees || []) {
    const stack = [...(tree.children || [])]
    while (stack.length) {
      const node = stack.shift()!
      if (node.consolidatedProjectId === props.projectId || node.standaloneProjectId === props.projectId) return node
      stack.push(...(node.children || []))
    }
  }
  return null
}

async function handleOpen() {
  if (!props.projectId) return
  loading.value = true
  loadError.value = ''
  members.value = []
  diagnostics.value = []
  try {
    const project: any = await api.get(P_proj.detail(props.projectId))
    rootCompanyCode.value = project?.company_code || project?.companyCode || ''
    year.value = project?.audit_year || project?.audit_year_value || null
    const response: any = await api.get('/api/projects/tree', {
      params: { ...(year.value ? { year: year.value } : {}), scope: 'all' },
    })
    const trees: ForestTree[] = Array.isArray(response?.trees) ? response.trees : []
    const root = findRoot(trees)
    if (!root) {
      members.value = []
      return
    }
    members.value = flatten(root.children || [])
    diagnostics.value = (response?.diagnostics || []).filter((item: Diagnostic) => item?.message).slice(0, 10)
  } catch {
    loadError.value = '自动识别合并范围失败，请检查项目基本信息中的企业代码和上级代码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.gt-scope-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.6; margin: 0 0 12px; }
.gt-scope-diagnostics { margin-top: 12px; }
.gt-scope-diagnostics ul { margin: 4px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); }
</style>
