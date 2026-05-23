<!--
  EnumDictManager.vue — 枚举字典管理 [proposal-remaining-18 / DT-3 / 任务 1.5]

  目标：
  - 在 SystemSettings 新增"枚举管理"Tab，提供枚举字典 CRUD UI
  - el-table 显示 dict_key / value / label / color / 排序 / 引用计数
  - 新增/编辑/删除按钮调用 /api/system/dicts 端点（POST/PUT/DELETE）
  - 仅 admin 可见（外层 v-if="isAdmin"）

  当前后端约束（D13 ADR）：
  - 写操作（POST/PUT/DELETE）端点返回 405 + ENUM_DICT_HARDCODED hint
  - 提交后 toast 显示 hint，告知用户当前枚举字典需修改源码
  - 一旦未来后端切到 DB-backed，本组件 UI 自动生效（提交即写库）

  与 EnumDictTab.vue（模板库）的差异：
  - EnumDictTab 仅展示+按钮 disabled+tooltip 提示
  - EnumDictManager 按钮可点 → 真实调 CRUD endpoint → 失败时展示 hint，
    保留"前端界面就绪、后端切换无前端改动"的演进路径
-->
<template>
  <div class="gt-edm">
    <!-- 顶部工具栏 -->
    <div class="gt-edm-toolbar">
      <span class="gt-edm-stats">
        总字典：<span class="gt-amt">{{ dictKeys.length }}</span>
      </span>
      <span class="gt-edm-stats">
        总枚举值：<span class="gt-amt">{{ totalEntries }}</span>
      </span>
      <div class="gt-edm-spacer" />
      <el-input
        v-model="searchInput"
        size="small"
        placeholder="搜索字典名 / value / label"
        clearable
        class="gt-edm-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button
        size="small"
        :loading="loading"
        @click="refreshAll"
        round
      >
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>
        刷新
      </el-button>
      <el-button
        size="small"
        type="primary"
        round
        @click="onCreate"
      >
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新增枚举项
      </el-button>
    </div>

    <!-- 字典分组 + el-table CRUD -->
    <div v-loading="loading" class="gt-edm-body">
      <el-empty
        v-if="!loading && filteredDicts.length === 0"
        :description="dictKeys.length === 0 ? '暂无字典数据' : '未匹配到字典'"
      />

      <div
        v-for="dictKey in filteredDicts"
        :key="dictKey"
        class="gt-edm-group"
      >
        <div class="gt-edm-group-header">
          <el-icon><CollectionTag /></el-icon>
          <code class="gt-edm-dict-key">{{ dictKey }}</code>
          <span class="gt-edm-dict-label">{{ dictLabels[dictKey] || dictKey }}</span>
          <el-tag size="small" type="info" effect="plain" round>
            {{ dictData[dictKey]?.length || 0 }} 项
          </el-tag>
          <el-button
            v-if="!usageCountsLoaded[dictKey]"
            size="small"
            link
            :loading="loadingUsage[dictKey]"
            @click="loadUsageCount(dictKey)"
          >
            加载引用计数
          </el-button>
        </div>

        <el-table
          :data="filteredEntries(dictKey)"
          size="small"
          :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
          class="gt-edm-table"
        >
          <el-table-column label="排序" width="70" align="right">
            <template #default="{ $index }">
              <span class="gt-amt">{{ $index + 1 }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="value" label="value" min-width="180">
            <template #default="{ row }">
              <code class="gt-edm-value">{{ row.value }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="label" label="label" min-width="160" />
          <el-table-column label="预览" width="120" align="center">
            <template #default="{ row }">
              <el-tag
                :type="(row.color || 'info') as any"
                size="small"
                effect="light"
                round
              >
                {{ row.label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="color" label="color" width="160" align="center">
            <template #default="{ row }">
              <code class="gt-edm-color">{{ row.color || '(empty)' }}</code>
            </template>
          </el-table-column>
          <el-table-column label="引用计数" width="100" align="right">
            <template #default="{ row }">
              <template v-if="usageCountsLoaded[dictKey]">
                <el-tag
                  v-if="(usageCountMap[dictKey]?.[row.value] || 0) > 0"
                  type="warning"
                  size="small"
                  effect="plain"
                  round
                  class="gt-amt"
                >
                  {{ usageCountMap[dictKey]?.[row.value] || 0 }}
                </el-tag>
                <span v-else class="gt-amt gt-edm-em">0</span>
              </template>
              <span v-else class="gt-edm-em">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                link
                type="primary"
                @click="onEdit(dictKey, row)"
              >编辑</el-button>
              <el-button
                size="small"
                link
                type="danger"
                :disabled="(usageCountMap[dictKey]?.[row.value] || 0) > 0"
                @click="onDelete(dictKey, row)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingMode === 'create' ? '新增枚举项' : '编辑枚举项'"
      width="520px"
      append-to-body
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formState"
        :rules="formRules"
        label-width="100px"
        size="small"
      >
        <el-form-item label="字典 key" prop="dict_key">
          <el-select
            v-model="formState.dict_key"
            :disabled="editingMode === 'edit'"
            placeholder="选择字典"
            style="width: 100%"
          >
            <el-option
              v-for="k in dictKeys"
              :key="k"
              :label="`${dictLabels[k] || k} (${k})`"
              :value="k"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="value" prop="value">
          <el-input
            v-model="formState.value"
            :disabled="editingMode === 'edit'"
            placeholder="枚举值，如 draft / approved"
          />
        </el-form-item>
        <el-form-item label="label" prop="label">
          <el-input v-model="formState.label" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="color">
          <el-select v-model="formState.color" clearable style="width: 100%">
            <el-option label="(default)" value="" />
            <el-option label="success" value="success" />
            <el-option label="warning" value="warning" />
            <el-option label="danger" value="danger" />
            <el-option label="info" value="info" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number
            v-model="formState.sort_order"
            :min="0"
            :step="1"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="onSubmit"
        >提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Search, Refresh, Plus, CollectionTag } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { systemDicts as P_dicts } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface DictEntry {
  value: string
  label: string
  color: string
}
interface UsageCountItem {
  value: string
  count: number
}
interface FormState {
  dict_key: string
  value: string
  label: string
  color: string
  sort_order: number
}

// ─── 状态 ───
const loading = ref(false)
const submitting = ref(false)
const dictData = ref<Record<string, DictEntry[]>>({})
const usageCountMap = ref<Record<string, Record<string, number>>>({})
const usageCountsLoaded = ref<Record<string, boolean>>({})
const loadingUsage = ref<Record<string, boolean>>({})
const searchInput = ref('')

// 弹窗状态
const dialogVisible = ref(false)
const editingMode = ref<'create' | 'edit'>('create')
const formRef = ref<FormInstance | null>(null)
const formState = reactive<FormState>({
  dict_key: '',
  value: '',
  label: '',
  color: '',
  sort_order: 0,
})

const formRules: FormRules = {
  dict_key: [{ required: true, message: '请选择字典', trigger: 'change' }],
  value: [{ required: true, message: '请输入 value', trigger: 'blur' }],
  label: [{ required: true, message: '请输入 label', trigger: 'blur' }],
}

// 字典中文标签（与后端 _DICTS 同步维护）
const dictLabels: Record<string, string> = {
  wp_status: '底稿状态',
  wp_review_status: '底稿复核状态',
  adjustment_status: '调整分录状态',
  report_status: '审计报告状态',
  template_status: '模板状态',
  project_status: '项目状态',
  issue_status: '工单状态',
  pdf_task_status: 'PDF 任务状态',
  workhour_status: '工时状态',
}

const dictKeys = computed(() => Object.keys(dictData.value).sort())
const totalEntries = computed(() =>
  Object.values(dictData.value).reduce((sum, list) => sum + list.length, 0),
)

const filteredDicts = computed(() => {
  const kw = searchInput.value.trim().toLowerCase()
  if (!kw) return dictKeys.value
  return dictKeys.value.filter(
    (k) =>
      k.toLowerCase().includes(kw) ||
      (dictLabels[k] || '').toLowerCase().includes(kw) ||
      (dictData.value[k] || []).some(
        (e) =>
          e.value.toLowerCase().includes(kw) ||
          (e.label || '').toLowerCase().includes(kw),
      ),
  )
})

function filteredEntries(dictKey: string): DictEntry[] {
  const kw = searchInput.value.trim().toLowerCase()
  const entries = dictData.value[dictKey] || []
  if (!kw) return entries
  if (
    dictKey.toLowerCase().includes(kw) ||
    (dictLabels[dictKey] || '').toLowerCase().includes(kw)
  ) {
    return entries
  }
  return entries.filter(
    (e) =>
      e.value.toLowerCase().includes(kw) || (e.label || '').toLowerCase().includes(kw),
  )
}

// ─── 数据加载 ───
async function loadDicts() {
  loading.value = true
  try {
    const data = await api.get<Record<string, DictEntry[]>>(P_dicts.list)
    if (data && typeof data === 'object') {
      dictData.value = data
    }
  } catch (e: any) {
    handleApiError(e, '加载枚举字典')
  } finally {
    loading.value = false
  }
}

async function loadUsageCount(dictKey: string) {
  if (loadingUsage.value[dictKey] || usageCountsLoaded.value[dictKey]) return
  loadingUsage.value[dictKey] = true
  try {
    const list = await api.get<UsageCountItem[]>(P_dicts.usageCount(dictKey))
    const map: Record<string, number> = {}
    if (Array.isArray(list)) {
      for (const item of list) {
        map[item.value] = item.count
      }
    }
    usageCountMap.value[dictKey] = map
    usageCountsLoaded.value[dictKey] = true
  } catch (e: any) {
    handleApiError(e, `加载 ${dictKey} 引用计数`)
  } finally {
    loadingUsage.value[dictKey] = false
  }
}

async function refreshAll() {
  usageCountsLoaded.value = {}
  usageCountMap.value = {}
  await loadDicts()
}

// ─── CRUD 操作 ───
function resetForm() {
  formState.dict_key = ''
  formState.value = ''
  formState.label = ''
  formState.color = ''
  formState.sort_order = 0
}

function onCreate() {
  editingMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

function onEdit(dictKey: string, row: DictEntry) {
  editingMode.value = 'edit'
  formState.dict_key = dictKey
  formState.value = row.value
  formState.label = row.label
  formState.color = row.color || ''
  const idx = (dictData.value[dictKey] || []).findIndex((e) => e.value === row.value)
  formState.sort_order = idx >= 0 ? idx : 0
  dialogVisible.value = true
}

/** 解析后端 405 ENUM_DICT_HARDCODED 响应 → 友好提示 */
function extractHardcodedHint(e: any): string | null {
  const status = e?.response?.status || e?.status || 0
  if (status !== 405) return null
  const detail = e?.response?.data?.detail || e?.data?.detail
  if (detail && typeof detail === 'object' && detail.error_code === 'ENUM_DICT_HARDCODED') {
    return detail.hint || '枚举字典硬编码在后端，需修改源码后重启服务。'
  }
  return null
}

async function onSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (editingMode.value === 'create') {
      await api.post(P_dicts.items(formState.dict_key), {
        value: formState.value,
        label: formState.label,
        color: formState.color,
        sort_order: formState.sort_order,
      })
    } else {
      await api.put(P_dicts.itemDetail(formState.dict_key, formState.value), {
        label: formState.label,
        color: formState.color,
        sort_order: formState.sort_order,
      })
    }
    ElMessage.success(editingMode.value === 'create' ? '新增成功' : '更新成功')
    dialogVisible.value = false
    await refreshAll()
  } catch (e: any) {
    const hint = extractHardcodedHint(e)
    if (hint) {
      ElMessageBox.alert(hint, '当前为代码定义字典', {
        confirmButtonText: '我知道了',
        type: 'info',
      }).catch(() => { /* 忽略关闭 */ })
    } else {
      handleApiError(e, editingMode.value === 'create' ? '新增枚举项' : '更新枚举项')
    }
  } finally {
    submitting.value = false
  }
}

async function onDelete(dictKey: string, row: DictEntry) {
  try {
    await ElMessageBox.confirm(
      `确认删除字典 ${dictKey} 中的枚举项 ${row.value}（${row.label}）？`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }

  try {
    await api.delete(P_dicts.itemDetail(dictKey, row.value))
    ElMessage.success('删除成功')
    await refreshAll()
  } catch (e: any) {
    const hint = extractHardcodedHint(e)
    if (hint) {
      ElMessageBox.alert(hint, '当前为代码定义字典', {
        confirmButtonText: '我知道了',
        type: 'info',
      }).catch(() => { /* 忽略关闭 */ })
    } else {
      handleApiError(e, '删除枚举项')
    }
  }
}

onMounted(() => {
  loadDicts()
})

// 暴露给单元测试
defineExpose({
  dictData,
  formState,
  editingMode,
  dialogVisible,
  loadDicts,
  onCreate,
  onEdit,
  onDelete,
  onSubmit,
  extractHardcodedHint,
  filteredEntries,
  filteredDicts,
})
</script>

<style scoped>
.gt-edm {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.gt-edm-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border-radius: 6px;
  border: 1px solid var(--gt-color-border-lighter);
}
.gt-edm-stats { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); }
.gt-edm-spacer { flex: 1; }
.gt-edm-search { width: 280px; }
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  font-weight: 600;
}
.gt-edm-em { color: var(--gt-color-text-placeholder); font-weight: 400; }

.gt-edm-body { display: flex; flex-direction: column; gap: 16px; }
.gt-edm-group {
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  overflow: hidden;
  background: var(--gt-color-bg-white);
}
.gt-edm-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--gt-color-bg);
  border-bottom: 1px solid var(--gt-color-border-lighter);
  font-size: var(--gt-font-size-sm);
}
.gt-edm-dict-key {
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  background: var(--gt-color-primary-bg);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--gt-color-primary);
  font-weight: 600;
}
.gt-edm-dict-label { color: var(--gt-color-text-primary); }

.gt-edm-table { margin: 0; }
.gt-edm-value,
.gt-edm-color {
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-primary);
}
.gt-edm-color { color: var(--gt-color-info); }
</style>
