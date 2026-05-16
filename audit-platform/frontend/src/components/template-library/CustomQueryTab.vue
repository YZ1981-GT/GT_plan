<!--
  CustomQueryTab.vue — 自定义查询 Tab [template-library-coordination Sprint 6 Tasks 6.4-6.6]

  需求 22.1-22.9：
  - 可视化查询构建器：数据源选择 + 多条件筛选 + 字段选择
  - 8+ 数据源（底稿/试算表/调整分录/科目余额/序时账/附注/报表行次/工时）
  - 条件类型：等于/包含/大于/小于/范围/为空/不为空
  - 多条件 AND/OR 组合
  - 结果 el-table 展示 + Excel 导出（前端 xlsx）
  - 模板保存/加载（私有 + 全局共享）

  依赖：
  - GET /api/custom-query/indicators       数据源指标库
  - POST /api/custom-query/execute         执行查询
  - GET /api/custom-query/templates        列出模板
  - POST /api/custom-query/templates       保存模板
  - DELETE /api/custom-query/templates/:id 删除模板
-->
<template>
  <div class="gt-cqt">
    <!-- 顶部：项目年度选择 + 模板管理 -->
    <div class="gt-cqt-top">
      <el-form :model="formCtx" inline size="small" class="gt-cqt-ctx-form">
        <el-form-item label="项目">
          <el-select
            v-model="formCtx.project_id"
            filterable
            placeholder="选择项目"
            style="width: 240px"
          >
            <el-option
              v-for="p in projectList"
              :key="p.id"
              :label="`${p.code || ''} ${p.name || p.id}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="年度">
          <el-input-number
            v-model="formCtx.year"
            :min="2000"
            :max="2100"
            :step="1"
            controls-position="right"
            style="width: 120px"
          />
        </el-form-item>
        <el-form-item label="数据源">
          <el-select
            v-model="formCtx.source"
            filterable
            placeholder="选择数据源"
            style="width: 220px"
            @change="onSourceChange"
          >
            <el-option-group
              v-for="grp in indicatorTree"
              :key="grp.key"
              :label="grp.label"
            >
              <el-option
                v-for="child in grp.children"
                :key="child.key"
                :label="child.label"
                :value="child.key"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>

      <div class="gt-cqt-top-actions">
        <el-button size="small" @click="loadTemplates" :loading="loadingTemplates">
          <el-icon style="margin-right: 4px"><Folder /></el-icon>
          我的模板 ({{ templates.length }})
        </el-button>
        <el-button size="small" type="primary" plain @click="onSaveTemplate">
          <el-icon style="margin-right: 4px"><DocumentAdd /></el-icon>
          保存为模板
        </el-button>
      </div>
    </div>

    <!-- 主体：左侧条件筛选 + 字段选择，右侧结果 -->
    <el-row :gutter="12" class="gt-cqt-main">
      <!-- 左侧：查询构建器 -->
      <el-col :span="8" class="gt-cqt-left">
        <div class="gt-cqt-panel">
          <div class="gt-cqt-panel-header">
            <span>条件筛选</span>
            <el-radio-group v-model="formCtx.condition_logic" size="small">
              <el-radio-button label="AND">全部满足 (AND)</el-radio-button>
              <el-radio-button label="OR">任一满足 (OR)</el-radio-button>
            </el-radio-group>
          </div>
          <div class="gt-cqt-conditions">
            <div
              v-for="(cond, idx) in conditions"
              :key="idx"
              class="gt-cqt-cond-row"
            >
              <el-select
                v-model="cond.field"
                size="small"
                placeholder="字段"
                style="width: 150px"
              >
                <el-option
                  v-for="f in availableColumns"
                  :key="f"
                  :label="f"
                  :value="f"
                />
              </el-select>
              <el-select
                v-model="cond.operator"
                size="small"
                placeholder="操作符"
                style="width: 110px"
              >
                <el-option
                  v-for="op in operatorOptions"
                  :key="op.value"
                  :label="op.label"
                  :value="op.value"
                />
              </el-select>
              <el-input
                v-if="!['is_null', 'is_not_null'].includes(cond.operator)"
                v-model="cond.value"
                size="small"
                :placeholder="cond.operator === 'between' ? '起,止' : '值'"
                style="flex: 1; min-width: 0"
              />
              <el-button
                size="small"
                link
                type="danger"
                @click="onRemoveCondition(idx)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-button
              size="small"
              link
              type="primary"
              @click="onAddCondition"
            >
              <el-icon style="margin-right: 4px"><Plus /></el-icon>
              添加条件
            </el-button>
          </div>
        </div>

        <div class="gt-cqt-panel" style="margin-top: 12px">
          <div class="gt-cqt-panel-header">
            <span>字段选择 ({{ selectedColumns.length }} / {{ availableColumns.length }})</span>
            <el-button size="small" link @click="toggleAllColumns">
              {{ selectedColumns.length === availableColumns.length ? '取消全选' : '全选' }}
            </el-button>
          </div>
          <el-checkbox-group v-model="selectedColumns" class="gt-cqt-fields">
            <el-checkbox
              v-for="col in availableColumns"
              :key="col"
              :label="col"
              :value="col"
              size="small"
            >
              {{ col }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="gt-cqt-panel-actions">
          <el-button
            type="primary"
            :loading="executing"
            @click="onExecute"
            :disabled="!formCtx.source || !formCtx.project_id"
            style="width: 100%"
          >
            <el-icon style="margin-right: 4px"><Search /></el-icon>
            执行查询
          </el-button>
        </div>
      </el-col>

      <!-- 右侧：结果展示 -->
      <el-col :span="16" class="gt-cqt-right">
        <div class="gt-cqt-result-header">
          <span class="gt-cqt-result-title">
            查询结果
            <el-tag
              v-if="result.rows.length > 0"
              size="small"
              type="success"
              effect="plain"
              round
              style="margin-left: 8px"
            >
              {{ result.rows.length }} 条
            </el-tag>
          </span>
          <div class="gt-cqt-result-actions">
            <el-button
              size="small"
              :disabled="result.rows.length === 0"
              @click="onExportExcel"
            >
              <el-icon style="margin-right: 4px"><Download /></el-icon>
              导出 Excel
            </el-button>
          </div>
        </div>

        <div class="gt-cqt-result-body">
          <el-empty
            v-if="!executing && result.rows.length === 0 && !result.error"
            description="点击 [执行查询] 开始检索"
          />
          <el-alert
            v-if="result.error"
            type="error"
            :closable="false"
            show-icon
          >
            <template #title>查询失败</template>
            <template #default>
              <pre class="gt-cqt-error">{{ result.error }}</pre>
            </template>
          </el-alert>
          <el-table
            v-if="result.rows.length > 0"
            v-loading="executing"
            :data="result.rows"
            size="small"
            border
            stripe
            max-height="600"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            class="gt-cqt-table"
          >
            <el-table-column
              v-for="col in displayColumns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span :class="{ 'gt-amt': isNumericValue(row[col]) }">
                  {{ formatCellValue(row[col]) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <!-- 模板列表对话框 -->
    <el-dialog
      v-model="templatesDialogVisible"
      title="查询模板"
      width="720px"
    >
      <el-table :data="templates" size="small" border>
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="data_source" label="数据源" width="140" />
        <el-table-column label="可见范围" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.scope === 'global' ? 'warning' : 'info'"
              size="small"
              effect="plain"
              round
            >
              {{ row.scope === 'global' ? '全局共享' : '私有' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="160">
          <template #default="{ row }">
            <span class="gt-cqt-em">
              {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="onLoadTemplate(row)">
              加载
            </el-button>
            <el-button
              v-if="row.is_owner"
              size="small"
              link
              type="danger"
              @click="onDeleteTemplate(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 保存模板对话框 -->
    <el-dialog v-model="saveDialogVisible" title="保存查询模板" width="480px">
      <el-form
        ref="saveFormRef"
        :model="saveForm"
        label-width="80px"
        size="small"
      >
        <el-form-item label="名称" required>
          <el-input v-model="saveForm.name" placeholder="如 应收账款明细查询" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="saveForm.description"
            type="textarea"
            :rows="2"
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="saveForm.scope">
            <el-radio label="private">仅我可见</el-radio>
            <el-radio label="global">全局共享</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDialogVisible = false" size="small">取消</el-button>
        <el-button
          type="primary"
          size="small"
          :loading="savingTemplate"
          :disabled="!saveForm.name.trim()"
          @click="onConfirmSaveTemplate"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Plus, Delete, Download, Folder, DocumentAdd } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { customQuery as P_cq, projects as P_proj } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface IndicatorChild {
  key: string
  label: string
  columns: string[]
}
interface IndicatorGroup {
  key: string
  label: string
  icon?: string
  children: IndicatorChild[]
}
interface QueryCondition {
  field: string
  operator: 'eq' | 'contains' | 'gt' | 'lt' | 'between' | 'is_null' | 'is_not_null'
  value: string
}
interface QueryResult {
  rows: any[]
  columns: string[]
  total: number
  error?: string
}
interface ProjectItem {
  id: string
  code?: string
  name?: string
}
interface TemplateItem {
  id: string
  name: string
  description?: string | null
  data_source: string
  config: any
  scope: 'private' | 'global'
  created_by: string
  is_owner: boolean
  created_at: string
  updated_at: string
}

// ─── 状态 ───
const indicatorTree = ref<IndicatorGroup[]>([])
const projectList = ref<ProjectItem[]>([])
const formCtx = ref({
  project_id: '',
  year: new Date().getFullYear(),
  source: '',
  condition_logic: 'AND' as 'AND' | 'OR',
})
const conditions = ref<QueryCondition[]>([])
const selectedColumns = ref<string[]>([])
const availableColumns = ref<string[]>([])
const result = ref<QueryResult>({ rows: [], columns: [], total: 0 })
const executing = ref(false)

// 模板
const templates = ref<TemplateItem[]>([])
const templatesDialogVisible = ref(false)
const saveDialogVisible = ref(false)
const loadingTemplates = ref(false)
const savingTemplate = ref(false)
const saveForm = ref({
  name: '',
  description: '',
  scope: 'private' as 'private' | 'global',
})

const operatorOptions = [
  { label: '等于 (=)', value: 'eq' },
  { label: '包含 (LIKE)', value: 'contains' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '范围 (BETWEEN)', value: 'between' },
  { label: '为空 (IS NULL)', value: 'is_null' },
  { label: '不为空 (IS NOT NULL)', value: 'is_not_null' },
]

// 当前已展示列（结果优先用 result.columns，回退到用户选择）
const displayColumns = computed(() => {
  if (result.value.columns && result.value.columns.length > 0) {
    return selectedColumns.value.length > 0
      ? result.value.columns.filter((c) => selectedColumns.value.includes(c))
      : result.value.columns
  }
  return selectedColumns.value
})

function isNumericValue(v: any): boolean {
  if (typeof v === 'number') return true
  if (typeof v === 'string' && v.length > 0) {
    return /^-?\d+(\.\d+)?$/.test(v.trim())
  }
  return false
}

function formatCellValue(v: any): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString()
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ─── 数据加载 ───
async function loadIndicators() {
  try {
    const data = await api.get<IndicatorGroup[]>(P_cq.indicators)
    if (Array.isArray(data)) {
      indicatorTree.value = data
    }
  } catch (e: any) {
    handleApiError(e, '加载查询指标库')
  }
}

async function loadProjects() {
  try {
    const data = await api.get<any>(P_proj.list)
    const list = Array.isArray(data) ? data : (data?.items || [])
    projectList.value = list.map((p: any) => ({
      id: p.id,
      code: p.code || p.project_code,
      name: p.name || p.project_name,
    }))
  } catch (e: any) {
    handleApiError(e, '加载项目列表')
  }
}

function onSourceChange() {
  // 切换数据源时重置条件和字段
  conditions.value = []
  for (const grp of indicatorTree.value) {
    const child = grp.children.find((c) => c.key === formCtx.value.source)
    if (child) {
      availableColumns.value = [...child.columns]
      selectedColumns.value = [...child.columns]
      return
    }
  }
  availableColumns.value = []
  selectedColumns.value = []
}

function toggleAllColumns() {
  if (selectedColumns.value.length === availableColumns.value.length) {
    selectedColumns.value = []
  } else {
    selectedColumns.value = [...availableColumns.value]
  }
}

function onAddCondition() {
  conditions.value.push({
    field: availableColumns.value[0] || '',
    operator: 'eq',
    value: '',
  })
}

function onRemoveCondition(idx: number) {
  conditions.value.splice(idx, 1)
}

// ─── 执行查询 ───
function buildFilters(): Record<string, any> {
  // 条件转换为后端 filters 格式（简化为字段→值映射，兼容当前后端按字段名识别）
  const out: Record<string, any> = {}
  for (const c of conditions.value) {
    if (!c.field) continue
    if (c.operator === 'is_null') {
      out[`${c.field}__is_null`] = true
    } else if (c.operator === 'is_not_null') {
      out[`${c.field}__is_not_null`] = true
    } else if (c.operator === 'between') {
      const parts = (c.value || '').split(/[,，]/).map((s) => s.trim())
      if (parts.length === 2) {
        out[`${c.field}_from`] = parts[0]
        out[`${c.field}_to`] = parts[1]
      }
    } else if (c.operator === 'contains') {
      out[c.field] = c.value
    } else if (c.operator === 'gt') {
      out[`${c.field}_min`] = c.value
    } else if (c.operator === 'lt') {
      out[`${c.field}_max`] = c.value
    } else {
      out[c.field] = c.value
    }
  }
  // 后端期望的常用字段
  if (formCtx.value.source === 'report' || formCtx.value.source.startsWith('report_')) {
    if (formCtx.value.source.startsWith('report_')) {
      out.report_type = formCtx.value.source.replace('report_', '')
    }
  }
  return out
}

async function onExecute() {
  if (!formCtx.value.source) {
    ElMessage.warning('请先选择数据源')
    return
  }
  if (!formCtx.value.project_id) {
    ElMessage.warning('请先选择项目')
    return
  }
  executing.value = true
  result.value = { rows: [], columns: [], total: 0 }
  try {
    const data = await api.post<QueryResult>(P_cq.execute, {
      project_id: formCtx.value.project_id,
      year: formCtx.value.year,
      source: formCtx.value.source,
      filters: buildFilters(),
      columns: selectedColumns.value,
      limit: 500,
      offset: 0,
    })
    if (data) {
      result.value = data
      if (data.error) {
        ElMessage.warning('查询执行返回错误')
      } else {
        ElMessage.success(`查询完成，返回 ${data.rows?.length || 0} 条记录`)
      }
    }
  } catch (e: any) {
    handleApiError(e, '执行查询')
    result.value = { rows: [], columns: [], total: 0, error: String(e?.message || e) }
  } finally {
    executing.value = false
  }
}

// ─── 导出 Excel（前端 xlsx） ───
async function onExportExcel() {
  if (result.value.rows.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const XLSX: any = await import('xlsx')
    const cols = displayColumns.value
    // 构造 [[header...], [row1...], [row2...]] 二维数组
    const aoa: any[][] = [cols]
    for (const row of result.value.rows) {
      aoa.push(cols.map((c) => row[c] ?? ''))
    }
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '查询结果')
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const fname = `自定义查询_${formCtx.value.source}_${ts}.xlsx`
    XLSX.writeFile(wb, fname)
    ElMessage.success(`已导出 ${fname}`)
  } catch (e: any) {
    handleApiError(e, '导出 Excel')
  }
}

// ─── 模板管理 ───
async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const data = await api.get<{ templates: TemplateItem[]; total: number }>(P_cq.templates)
    templates.value = data?.templates || []
    templatesDialogVisible.value = true
  } catch (e: any) {
    handleApiError(e, '加载查询模板列表')
  } finally {
    loadingTemplates.value = false
  }
}

function onSaveTemplate() {
  if (!formCtx.value.source) {
    ElMessage.warning('请先选择数据源后再保存')
    return
  }
  saveForm.value.name = ''
  saveForm.value.description = ''
  saveForm.value.scope = 'private'
  saveDialogVisible.value = true
}

async function onConfirmSaveTemplate() {
  if (!saveForm.value.name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  savingTemplate.value = true
  try {
    await api.post(P_cq.templates, {
      name: saveForm.value.name.trim(),
      description: saveForm.value.description?.trim() || null,
      data_source: formCtx.value.source,
      config: {
        project_id: formCtx.value.project_id,
        year: formCtx.value.year,
        condition_logic: formCtx.value.condition_logic,
        conditions: conditions.value,
        selected_columns: selectedColumns.value,
        available_columns: availableColumns.value,
      },
      scope: saveForm.value.scope,
    })
    ElMessage.success('模板已保存')
    saveDialogVisible.value = false
  } catch (e: any) {
    handleApiError(e, '保存查询模板')
  } finally {
    savingTemplate.value = false
  }
}

function onLoadTemplate(tpl: TemplateItem) {
  const cfg = tpl.config || {}
  formCtx.value.source = tpl.data_source
  if (cfg.year) formCtx.value.year = cfg.year
  if (cfg.condition_logic) formCtx.value.condition_logic = cfg.condition_logic
  if (Array.isArray(cfg.available_columns)) {
    availableColumns.value = cfg.available_columns
  } else {
    onSourceChange()
  }
  if (Array.isArray(cfg.selected_columns)) {
    selectedColumns.value = cfg.selected_columns
  }
  if (Array.isArray(cfg.conditions)) {
    conditions.value = cfg.conditions
  }
  templatesDialogVisible.value = false
  ElMessage.success(`已加载模板：${tpl.name}`)
}

async function onDeleteTemplate(tpl: TemplateItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除模板「${tpl.name}」？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await api.delete(P_cq.templateDetail(tpl.id))
    ElMessage.success('已删除')
    await loadTemplates()
  } catch (e: any) {
    handleApiError(e, '删除查询模板')
  }
}

// 项目变化时清除结果
watch(() => formCtx.value.project_id, () => {
  result.value = { rows: [], columns: [], total: 0 }
})

onMounted(() => {
  loadIndicators()
  loadProjects()
})
</script>

<style scoped>
.gt-cqt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.gt-cqt-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.gt-cqt-ctx-form { margin-bottom: 0; flex: 1; }
.gt-cqt-ctx-form :deep(.el-form-item) { margin-bottom: 0; margin-right: 12px; }
.gt-cqt-top-actions { display: flex; gap: 8px; flex-shrink: 0; }
.gt-cqt-em { color: #909399; font-size: 12px; }

.gt-cqt-main {
  flex: 1;
  margin: 0 !important;
  min-height: 0;
}
.gt-cqt-left,
.gt-cqt-right {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.gt-cqt-panel {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
}
.gt-cqt-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.gt-cqt-conditions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gt-cqt-cond-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.gt-cqt-fields {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px 12px;
  max-height: 220px;
  overflow: auto;
  padding: 4px 0;
}
.gt-cqt-fields :deep(.el-checkbox) {
  margin-right: 0;
  height: 24px;
}

.gt-cqt-panel-actions {
  margin-top: 8px;
}

.gt-cqt-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.gt-cqt-result-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.gt-cqt-result-actions { display: flex; gap: 8px; }
.gt-cqt-result-body {
  flex: 1;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  min-height: 0;
  overflow: auto;
}
.gt-cqt-table { font-size: 12px; }
.gt-cqt-error {
  margin: 0;
  font-size: 12px;
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  white-space: pre-wrap;
  color: #f56c6c;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
