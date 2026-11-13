<template>
  <div class="gt-mapping-page gt-fade-in">
    <GtPageHeader title="科目映射" @back="$router.push(`/projects/${projectId}/trial-balance`)">
      <template #actions>
        <el-button type="primary" :loading="autoMatchLoading" @click="onAutoMatch">
          🔄 自动匹配
        </el-button>
        <el-button
          :disabled="inheritCandidates.length === 0"
          :loading="inheritLoading"
          @click="onInheritFromParent"
        >
          按上级补全下级（{{ inheritCandidates.length }}）
        </el-button>
        <el-button @click="fetchData" :loading="loading">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- 完成率进度条 -->
    <div class="gt-mapping-summary">
      <div class="gt-mapping-summary__rate">
        <span class="gt-mapping-summary__label">映射完成率</span>
        <el-progress
          :percentage="completionRate"
          :stroke-width="16"
          :format="(pct: number) => `${pct.toFixed(1)}%`"
          :color="completionRate >= 80 ? '#67c23a' : completionRate >= 50 ? '#e6a23c' : '#f56c6c'"
          style="width: 300px; display: inline-flex; margin: 0 16px"
        />
        <span class="gt-mapping-summary__stats">
          已映射 {{ mappedCount }} / {{ totalCount }} 个科目
        </span>
        <el-radio-group v-model="viewFilter" size="small" style="margin-left: 16px">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="unmapped">未映射有余额（{{ unmappedRows.length }}）</el-radio-button>
          <el-radio-button value="mapped">已映射</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 映射列表 -->
    <el-table
      :data="filteredMappings"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
      max-height="calc(100vh - 260px)"
      :default-sort="{ prop: 'original_account_code', order: 'ascending' }"
    >
      <el-table-column prop="original_account_code" label="客户科目编码" width="160" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ row.original_account_code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="original_account_name" label="客户科目名称" min-width="180" />
      <el-table-column prop="standard_account_code" label="标准科目编码" width="160" sortable>
        <template #default="{ row }">
          <span class="gt-amt">{{ row.standard_account_code || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="standard_account_name" label="标准科目名称" min-width="180">
        <template #default="{ row }">
          {{ row.standard_account_name || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="mapping_type" label="映射方式" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="mappingTypeTag(row.mapping_type)" size="small">
            {{ mappingTypeLabel(row.mapping_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 手动编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑科目映射" width="500px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="120px">
        <el-form-item label="客户科目编码">
          <el-input :model-value="editForm.original_account_code" disabled />
        </el-form-item>
        <el-form-item label="客户科目名称">
          <el-input :model-value="editForm.original_account_name" disabled />
        </el-form-item>
        <el-form-item label="标准科目编码" prop="standard_account_code">
          <el-input v-model="editForm.standard_account_code" placeholder="输入标准科目编码" />
        </el-form-item>
        <el-form-item v-if="editDescendants.length > 0" label="下级科目">
          <el-checkbox v-model="applyToDescendants">
            同时映射 {{ editDescendants.length }} 个未映射的下级科目
          </el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { accountMapping } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { rules } from '@/utils/formRules'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string || route.params.id as string)

const loading = ref(false)
const autoMatchLoading = ref(false)
const saveLoading = ref(false)
const mappings = ref<any[]>([])
const unmappedRows = ref<any[]>([])
const viewFilter = ref<'all' | 'unmapped' | 'mapped'>('all')
const completionRate = ref(0)
const totalCount = ref(0)
const mappedCount = ref(0)

const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = ref({
  id: '',
  original_account_code: '',
  original_account_name: '',
  standard_account_code: '',
})
const editRules: FormRules = {
  standard_account_code: [rules.required('标准科目编码')],
}

const filteredMappings = computed(() => {
  if (viewFilter.value === 'unmapped') return unmappedRows.value
  if (viewFilter.value === 'mapped') return mappings.value
  return [...unmappedRows.value, ...mappings.value]
})

/** child 是否为 parent 的下级科目（「1613.02」是「1613」的下级；不带点的编码按前缀判断） */
function isDescendant(child: string, parent: string): boolean {
  if (!child || !parent || child === parent) return false
  if (child.startsWith(parent + '.')) return true
  return !parent.includes('.') && !child.includes('.') && child.length > parent.length && child.startsWith(parent)
}

/** 未映射科目中，有已映射上级的：取最近一级已映射上级的标准科目 */
const inheritCandidates = computed(() => {
  const out: { original_account_code: string; original_account_name: string; standard_account_code: string }[] = []
  for (const row of unmappedRows.value) {
    let best: any = null
    for (const m of mappings.value) {
      if (isDescendant(row.original_account_code, m.original_account_code)
        && (!best || m.original_account_code.length > best.original_account_code.length)) {
        best = m
      }
    }
    if (best) {
      out.push({
        original_account_code: row.original_account_code,
        original_account_name: row.original_account_name,
        standard_account_code: best.standard_account_code,
      })
    }
  }
  return out
})

/** 编辑中的科目的未映射下级（编辑时可一并映射） */
const editDescendants = computed(() =>
  unmappedRows.value.filter(r => isDescendant(r.original_account_code, editForm.value.original_account_code)),
)
const applyToDescendants = ref(true)
const inheritLoading = ref(false)

async function onInheritFromParent() {
  const items = inheritCandidates.value
  if (!items.length) return
  try {
    await ElMessageBox.confirm(
      `将为 ${items.length} 个未映射科目套用其上级科目的标准科目，保存后试算表会重算。是否继续？`,
      '按上级补全下级',
      { confirmButtonText: '补全', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  inheritLoading.value = true
  try {
    await api.post(accountMapping.batchConfirm(projectId.value), items)
    ElMessage.success(`已补全 ${items.length} 个科目`)
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '按上级补全失败')
  } finally {
    inheritLoading.value = false
  }
}

const MAPPING_TYPE_LABELS: Record<string, string> = {
  auto_exact: '自动（精确）',
  auto_fuzzy: '自动（模糊）',
  manual: '手动',
}
function mappingTypeLabel(t: string | null | undefined) {
  return (t && MAPPING_TYPE_LABELS[t]) || '未映射'
}
function mappingTypeTag(t: string | null | undefined) {
  if (t === 'auto_exact') return 'success'
  if (t === 'auto_fuzzy') return 'primary'
  if (t === 'manual') return 'warning'
  return 'danger'
}

/** 有余额但还没映射的客户科目（completion-rate 接口返回；同一科目可能有多行余额，按编码去重） */
function toUnmappedRows(items: any[]): any[] {
  const seen = new Set<string>()
  const out: any[] = []
  for (const it of items || []) {
    const code = it?.account_code
    if (!code || seen.has(code)) continue
    seen.add(code)
    out.push({
      id: '',
      original_account_code: code,
      original_account_name: it.account_name || '',
      standard_account_code: '',
      standard_account_name: '',
      mapping_type: null,
    })
  }
  return out.sort((a, b) => a.original_account_code.localeCompare(b.original_account_code))
}

async function fetchData() {
  loading.value = true
  try {
    const [listData, rateData] = await Promise.all([
      api.get(accountMapping.list(projectId.value)),
      api.get(accountMapping.completionRate(projectId.value)),
    ])

    // Process list
    const list = Array.isArray(listData) ? listData : (listData?.data || listData?.items || [])
    mappings.value = list

    // Process completion rate
    const rate = rateData?.data || rateData
    if (rate) {
      completionRate.value = typeof rate.completion_rate === 'number'
        ? rate.completion_rate
        : typeof rate.rate === 'number'
          ? rate.rate
          : 0
      totalCount.value = typeof rate.total_count === 'number' ? rate.total_count : list.length
      mappedCount.value = typeof rate.mapped_count === 'number' ? rate.mapped_count : list.length
      unmappedRows.value = toUnmappedRows(rate.unmapped_with_balance)
    }
  } catch (e: any) {
    handleApiError(e, '获取映射数据失败')
  } finally {
    loading.value = false
  }
}

async function onAutoMatch() {
  autoMatchLoading.value = true
  try {
    const result = await api.post(accountMapping.autoMatch(projectId.value))
    const data = result?.data || result
    ElMessage.success(`自动匹配完成：已匹配 ${data?.saved || data?.matched || 0} 个科目`)
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '自动匹配失败')
  } finally {
    autoMatchLoading.value = false
  }
}

function onEdit(row: any) {
  editForm.value = {
    id: row.id || '',
    original_account_code: row.original_account_code || '',
    original_account_name: row.original_account_name || '',
    standard_account_code: row.standard_account_code || '',
  }
  applyToDescendants.value = true
  editDialogVisible.value = true
}

async function onSaveEdit() {
  if (!editForm.value.standard_account_code) {
    ElMessage.warning('请输入标准科目编码')
    return
  }
  saveLoading.value = true
  try {
    const stdCode = editForm.value.standard_account_code.trim()
    const descendants = applyToDescendants.value ? editDescendants.value : []
    if (editForm.value.id) {
      // Update existing mapping
      await api.put(accountMapping.detail(projectId.value, editForm.value.id), {
        standard_account_code: stdCode,
      })
      if (descendants.length) {
        await api.post(accountMapping.batchConfirm(projectId.value), descendants.map(d => ({
          original_account_code: d.original_account_code,
          original_account_name: d.original_account_name || undefined,
          standard_account_code: stdCode,
        })))
      }
    } else {
      // 新建映射；勾选了下级时与下级一次批量保存（只触发一次试算表重算）
      await api.post(accountMapping.batchConfirm(projectId.value), [editForm.value, ...descendants].map(d => ({
        original_account_code: d.original_account_code,
        original_account_name: d.original_account_name || undefined,
        standard_account_code: stdCode,
      })))
    }
    ElMessage.success(descendants.length ? `映射保存成功（含 ${descendants.length} 个下级科目）` : '映射保存成功')
    editDialogVisible.value = false
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '保存映射失败')
  } finally {
    saveLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.gt-mapping-page {
  padding: 0 16px 16px;
}

.gt-mapping-summary {
  margin: 12px 0;
  padding: 12px 16px;
  background: var(--gt-color-bg);
  border-radius: 8px;
  display: flex;
  align-items: center;
}

.gt-mapping-summary__rate {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-mapping-summary__label {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  white-space: nowrap;
}

.gt-mapping-summary__stats {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}
</style>
