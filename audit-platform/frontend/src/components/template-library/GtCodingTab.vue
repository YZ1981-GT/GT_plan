<!--
  GtCodingTab.vue — 致同编码体系 Tab [template-library-coordination Sprint 4.3]

  需求 11.1-11.5：
  - 表格展示全部编码（code_prefix / code_range / cycle_name / wp_type / description / sort_order）
  - 按 wp_type 分组（preliminary / risk_assessment / control_test / substantive / specific / general）
  - 每个编码旁显示模板数量（按 cycle_name 与 wp-templates list 关联计数）
  - admin/partner 可编辑（v-permission），其他角色只读
  - 顶部统计：总编码数 + 各 wp_type 数量

  数据源：GET /api/gt-coding（动态从 API 取，不硬编码 48）
  D7 ADR：gt_wp_coding 是 DB-table editable，admin/partner 可编辑
-->
<template>
  <div class="gt-gtc">
    <!-- 顶部统计 + 工具栏（合一） -->
    <div class="gt-gtc-toolbar">
      <span class="gt-gtc-stats-item">
        总编码：<span class="gt-amt">{{ codings.length }}</span>
      </span>
      <span
        v-for="t in typeStats"
        :key="t.wp_type"
        class="gt-gtc-stats-tag"
      >
        <el-tag
          size="small"
          :class="`gt-gtc-type--${t.wp_type}`"
          effect="light"
          round
        >
          {{ typeLabel(t.wp_type) }}
          <span class="gt-amt gt-gtc-stats-tag-num">{{ t.count }}</span>
        </el-tag>
      </span>

      <div class="gt-gtc-spacer" />

      <el-input
        v-model="searchInput"
        size="small"
        placeholder="搜索 code_prefix / cycle_name / description"
        clearable
        class="gt-gtc-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="filterType"
        size="small"
        placeholder="按类型筛选"
        clearable
        class="gt-gtc-select"
      >
        <el-option label="全部" value="" />
        <el-option
          v-for="t in typeOptions"
          :key="t.value"
          :label="t.label"
          :value="t.value"
        />
      </el-select>

      <el-button
        v-if="canEdit"
        size="small"
        type="primary"
        @click="onAddNew"
      >
        <el-icon style="margin-right: 4px"><Plus /></el-icon>新增编码
      </el-button>
    </div>

    <!-- 分组列表 -->
    <div v-loading="loading" class="gt-gtc-body">
      <el-empty
        v-if="!loading && filteredCodings.length === 0"
        :description="codings.length === 0 ? '暂无编码数据，请通过 reseed 加载' : '未匹配到任何编码'"
      />
      <div
        v-for="g in groupedFiltered"
        :key="g.wp_type"
        class="gt-gtc-group"
      >
        <div class="gt-gtc-group-header" :class="`gt-gtc-group--${g.wp_type}`">
          <span class="gt-gtc-group-title">{{ typeLabel(g.wp_type) }}</span>
          <span class="gt-gtc-group-count gt-amt">{{ g.items.length }}</span>
        </div>
        <el-table
          :data="g.items"
          size="small"
          :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
          class="gt-gtc-table"
        >
          <el-table-column prop="code_prefix" label="编码" width="80" align="center">
            <template #default="{ row }">
              <span class="gt-amt gt-gtc-prefix">{{ row.code_prefix }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="code_range" label="范围" width="140">
            <template #default="{ row }">
              <code class="gt-gtc-range">{{ row.code_range }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="cycle_name" label="循环名称" min-width="180" />
          <el-table-column prop="description" label="说明" min-width="280" show-overflow-tooltip />
          <el-table-column prop="parent_cycle" label="父循环" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.parent_cycle" size="small" effect="plain">
                {{ row.parent_cycle }}
              </el-tag>
              <span v-else class="gt-gtc-em">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="sort_order" label="排序" width="80" align="right">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.sort_order ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="模板数" width="100" align="right">
            <template #default="{ row }">
              <span v-if="templateCountMap[row.code_range] !== undefined" class="gt-amt gt-gtc-tmpl-count">
                {{ templateCountMap[row.code_range] || 0 }}
              </span>
              <span v-else class="gt-gtc-em">—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.is_active === false ? 'info' : 'success'"
                size="small"
                effect="plain"
                round
              >
                {{ row.is_active === false ? '禁用' : '启用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="canEdit" label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                link
                type="primary"
                @click="onEdit(row)"
              >编辑</el-button>
              <el-button
                size="small"
                link
                type="danger"
                @click="onDelete(row)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 编辑/新增对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editDialogTitle"
      width="540px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="editForm"
        label-width="100px"
        size="small"
        :rules="formRules"
      >
        <el-form-item label="编码前缀" prop="code_prefix">
          <el-input v-model="editForm.code_prefix" placeholder="如 A / B / D" />
        </el-form-item>
        <el-form-item label="编码范围" prop="code_range">
          <el-input v-model="editForm.code_range" placeholder="如 D1-D7" />
        </el-form-item>
        <el-form-item label="循环名称" prop="cycle_name">
          <el-input v-model="editForm.cycle_name" placeholder="如 销售循环" />
        </el-form-item>
        <el-form-item label="底稿类型" prop="wp_type">
          <el-select v-model="editForm.wp_type" placeholder="选择底稿类型" style="width: 100%">
            <el-option
              v-for="t in typeOptions"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="说明" prop="description">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="父循环">
          <el-input v-model="editForm.parent_cycle" placeholder="可选，如 D" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="editForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item v-if="editingId" label="启用">
          <el-switch v-model="editForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import { api } from '@/services/apiProxy'
import { gtCoding as P_gt, workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'

interface Props {
  projectId?: string
}
const props = defineProps<Props>()

interface GtCoding {
  id?: string
  code_prefix: string
  code_range: string
  cycle_name: string
  wp_type: string
  description?: string
  parent_cycle?: string | null
  sort_order?: number | null
  is_active?: boolean
}

// ─── State ────────────────────────────────────────────────────────────────
const loading = ref(false)
const codings = ref<GtCoding[]>([])
const templateCountMap = ref<Record<string, number>>({})

const searchInput = ref('')
const searchText = ref('')
let searchDebouncer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (v) => {
  if (searchDebouncer) clearTimeout(searchDebouncer)
  searchDebouncer = setTimeout(() => { searchText.value = (v || '').trim() }, 250)
})
const filterType = ref('')

const editDialogVisible = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const formRef = ref<any>(null)
const editForm = ref<GtCoding>({
  code_prefix: '',
  code_range: '',
  cycle_name: '',
  wp_type: 'substantive',
  description: '',
  parent_cycle: '',
  sort_order: 999,
  is_active: true,
})

const formRules = {
  code_prefix: [{ required: true, message: '请输入编码前缀', trigger: 'blur' }],
  code_range: [{ required: true, message: '请输入编码范围', trigger: 'blur' }],
  cycle_name: [{ required: true, message: '请输入循环名称', trigger: 'blur' }],
  wp_type: [{ required: true, message: '请选择底稿类型', trigger: 'change' }],
}

// ─── 权限（D7 ADR）─────────────────────────────────────────────────────────
const authStore = useAuthStore()
const canEdit = computed(() => {
  const role = authStore.user?.role || ''
  return role === 'admin' || role === 'partner'
})

// ─── 类型映射 ─────────────────────────────────────────────────────────────
const typeOptions = [
  { value: 'preliminary', label: '初步业务（B1-B5）' },
  { value: 'risk_assessment', label: '风险评估（B10-B60）' },
  { value: 'control_test', label: '控制测试（C）' },
  { value: 'substantive', label: '实质性程序（D-N）' },
  { value: 'completion', label: '完成阶段（A）' },
  { value: 'specific', label: '特定项目（S）' },
  { value: 'general', label: '通用' },
] as const

function typeLabel(code: string): string {
  return typeOptions.find(t => t.value === code)?.label || code
}

const typeOrder = typeOptions.map(t => t.value)

// ─── 数据加载 ─────────────────────────────────────────────────────────────
async function loadCodings() {
  loading.value = true
  try {
    const data = await api.get(P_gt.list)
    codings.value = (Array.isArray(data) ? data : (data?.items || [])) as GtCoding[]
  } catch (e: any) {
    handleApiError(e, '加载编码体系')
    codings.value = []
  } finally {
    loading.value = false
  }
}

async function loadTemplateCounts() {
  // 模板数量统计：基于 wp-templates list（按 cycle 字段聚合到 code_range）
  if (!props.projectId) {
    templateCountMap.value = {}
    return
  }
  try {
    const data = await api.get(P_wp.templateList(props.projectId))
    const list = Array.isArray(data) ? data : (data?.items || [])
    const map: Record<string, number> = {}
    for (const t of list as Array<{ cycle?: string }>) {
      const k = t.cycle || ''
      if (!k) continue
      map[k] = (map[k] || 0) + 1
    }
    templateCountMap.value = map
  } catch {
    templateCountMap.value = {}
  }
}

onMounted(async () => {
  await Promise.all([loadCodings(), loadTemplateCounts()])
})

watch(() => props.projectId, () => {
  loadTemplateCounts()
})

// ─── 计算属性 ─────────────────────────────────────────────────────────────
const typeStats = computed(() => {
  const map = new Map<string, number>()
  for (const c of codings.value) {
    map.set(c.wp_type, (map.get(c.wp_type) || 0) + 1)
  }
  // 按 typeOrder 顺序输出
  return typeOrder
    .filter(t => map.has(t))
    .map(t => ({ wp_type: t, count: map.get(t) || 0 }))
})

const filteredCodings = computed<GtCoding[]>(() => {
  const q = searchText.value.toLowerCase()
  return codings.value.filter(c => {
    if (filterType.value && c.wp_type !== filterType.value) return false
    if (q) {
      const hay = [
        c.code_prefix,
        c.code_range,
        c.cycle_name,
        c.description || '',
      ].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

interface Group {
  wp_type: string
  items: GtCoding[]
}

const groupedFiltered = computed<Group[]>(() => {
  const groups = new Map<string, GtCoding[]>()
  for (const c of filteredCodings.value) {
    if (!groups.has(c.wp_type)) groups.set(c.wp_type, [])
    groups.get(c.wp_type)!.push(c)
  }
  // 每组内按 sort_order 升序
  for (const arr of groups.values()) {
    arr.sort((a, b) => (a.sort_order ?? 999999) - (b.sort_order ?? 999999))
  }
  // 按 typeOrder 排列
  const result: Group[] = []
  for (const t of typeOrder) {
    if (groups.has(t)) {
      result.push({ wp_type: t, items: groups.get(t)! })
      groups.delete(t)
    }
  }
  // 未在 typeOrder 中的兜底
  for (const [t, items] of groups) {
    result.push({ wp_type: t, items })
  }
  return result
})

const editDialogTitle = computed(() => editingId.value ? '编辑编码' : '新增编码')

// ─── CRUD ────────────────────────────────────────────────────────────────
function resetForm() {
  editForm.value = {
    code_prefix: '',
    code_range: '',
    cycle_name: '',
    wp_type: 'substantive',
    description: '',
    parent_cycle: '',
    sort_order: 999,
    is_active: true,
  }
  editingId.value = null
}

function onAddNew() {
  resetForm()
  editDialogVisible.value = true
}

function onEdit(row: GtCoding) {
  editForm.value = {
    code_prefix: row.code_prefix,
    code_range: row.code_range,
    cycle_name: row.cycle_name,
    wp_type: row.wp_type,
    description: row.description || '',
    parent_cycle: row.parent_cycle || '',
    sort_order: row.sort_order ?? 999,
    is_active: row.is_active !== false,
  }
  editingId.value = row.id || null
  editDialogVisible.value = true
}

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    saving.value = true
    try {
      const payload = { ...editForm.value }
      if (editingId.value) {
        // PUT /api/gt-coding/{id}
        await api.put(`/api/gt-coding/${editingId.value}`, payload)
        ElMessage.success('编码已更新')
      } else {
        await api.post(P_gt.list, payload)
        ElMessage.success('编码已新增')
      }
      editDialogVisible.value = false
      await loadCodings()
    } catch (e: any) {
      handleApiError(e, '保存编码')
    } finally {
      saving.value = false
    }
  })
}

async function onDelete(row: GtCoding) {
  if (!row.id) return
  try {
    await confirmDangerous(
      `确认删除编码 "${row.code_prefix} ${row.code_range} ${row.cycle_name}"？`,
      '删除编码',
    )
  } catch {
    return  // 用户取消
  }
  try {
    await api.delete(`/api/gt-coding/${row.id}`)
    ElMessage.success('编码已删除')
    await loadCodings()
  } catch (e: any) {
    handleApiError(e, '删除编码')
  }
}
</script>

<style scoped>
.gt-gtc {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* ─── 顶部统计 + 工具栏 ─── */
.gt-gtc-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  border-left: 3px solid var(--gt-color-primary);
  flex-shrink: 0;
}
.gt-gtc-stats-item {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  margin-right: 8px;
}
.gt-gtc-stats-tag-num {
  margin-left: 4px;
  font-weight: 700;
}
.gt-gtc-spacer { flex: 1; min-width: 8px; }
.gt-gtc-search { width: 240px; }
.gt-gtc-select { width: 180px; }

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

/* 类型标签颜色 */
.gt-gtc-type--preliminary { background: var(--gt-bg-info); color: var(--gt-color-teal); border-color: var(--gt-color-border-info); }
.gt-gtc-type--risk_assessment { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); border-color: var(--gt-color-border-warning); }
.gt-gtc-type--control_test { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); border-color: var(--gt-color-border-warning); }
.gt-gtc-type--substantive { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); border-color: var(--gt-color-border-purple-light); }
.gt-gtc-type--completion { background: var(--gt-color-success-light); color: var(--gt-color-success); border-color: var(--gt-color-border-success); }
.gt-gtc-type--specific { background: var(--gt-color-coral-light); color: var(--gt-color-coral); border-color: var(--gt-color-border-danger); }
.gt-gtc-type--general { background: var(--gt-color-bg); color: var(--gt-color-text-regular); border-color: var(--gt-color-border-light); }

/* ─── 主体 ─── */
.gt-gtc-body {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.gt-gtc-group {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.gt-gtc-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--gt-color-primary-bg);
  border-bottom: 1px solid var(--gt-color-border-lighter);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-gtc-group-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.gt-gtc-group-count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
  background: var(--gt-color-bg-white);
  padding: 1px 8px;
  border-radius: 10px;
  border: 1px solid var(--gt-color-border-purple-light);
}

.gt-gtc-table :deep(.el-table__row:hover > td) {
  background-color: rgba(75, 45, 119, 0.06) !important;
}

.gt-gtc-prefix {
  display: inline-block;
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: var(--gt-font-size-xs);
}
.gt-gtc-range {
  font-family: 'Consolas', 'Courier New', monospace;
  background: var(--gt-color-bg);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
}
.gt-gtc-em {
  color: var(--gt-color-text-placeholder);
  font-size: var(--gt-font-size-xs);
}
.gt-gtc-tmpl-count {
  color: var(--gt-color-primary);
}
</style>
