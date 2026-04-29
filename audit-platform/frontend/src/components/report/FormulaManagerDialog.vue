<template>
  <el-dialog
    v-model="visible"
    title="公式管理"
    width="900px"
    append-to-body
    destroy-on-close
  >
    <!-- 分类 Tab -->
    <el-tabs v-model="activeCategory">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane name="auto_calc">
        <template #label>
          <span>⚡ 自动运算 <el-badge :value="categoryCounts.auto_calc" type="primary" /></span>
        </template>
      </el-tab-pane>
      <el-tab-pane name="logic_check">
        <template #label>
          <span>🔍 逻辑审核 <el-badge :value="categoryCounts.logic_check" type="warning" /></span>
        </template>
      </el-tab-pane>
      <el-tab-pane name="reasonability">
        <template #label>
          <span>💡 提示合理性 <el-badge :value="categoryCounts.reasonability" type="info" /></span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 公式列表 -->
    <el-table :data="filteredRows" size="small" border max-height="450" style="width: 100%">
      <el-table-column prop="row_code" label="行次" width="80" />
      <el-table-column prop="row_name" label="项目" width="180" show-overflow-tooltip />
      <el-table-column label="公式" min-width="280">
        <template #default="{ row }">
          <el-input
            v-if="editingId === row.id"
            v-model="editFormula"
            size="small"
            placeholder="如 TB('1001','期末余额')"
          />
          <code v-else style="font-size: 11px; color: #555; word-break: break-all">
            {{ row.formula || '—' }}
          </code>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="editingId === row.id"
            v-model="editCategory"
            size="small"
            style="width: 90px"
          >
            <el-option label="自动运算" value="auto_calc" />
            <el-option label="逻辑审核" value="logic_check" />
            <el-option label="合理性" value="reasonability" />
          </el-select>
          <el-tag v-else :type="categoryTagType(row.formula_category)" size="small">
            {{ categoryLabel(row.formula_category) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="说明" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input v-if="editingId === row.id" v-model="editDescription" size="small" />
          <span v-else style="font-size: 12px; color: #888">{{ row.formula_description || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="100">
        <template #default="{ row }">
          <span style="font-size: 11px; color: #aaa">{{ row.formula_source || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button v-if="editingId !== row.id" size="small" link type="primary" @click="startEdit(row)">编辑</el-button>
          <el-button v-else size="small" link type="success" @click="saveEdit(row)">保存</el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <span style="font-size: 12px; color: #999; float: left; line-height: 32px">
        共 {{ allFormulaRows.length }} 个公式行
      </span>
      <el-button type="primary" @click="onApplyFormulas" :loading="applying">
        应用自动运算
      </el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  modelValue: boolean
  rows: any[]
  projectId?: string
  year?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'saved': []
  'applied': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeCategory = ref('all')
const editingId = ref<string | null>(null)
const editFormula = ref('')
const editCategory = ref('auto_calc')
const editDescription = ref('')
const applying = ref(false)

const allFormulaRows = computed(() => props.rows.filter(r => r.formula))

const filteredRows = computed(() => {
  if (activeCategory.value === 'all') return allFormulaRows.value
  return allFormulaRows.value.filter(r => r.formula_category === activeCategory.value)
})

const categoryCounts = computed(() => ({
  auto_calc: allFormulaRows.value.filter(r => r.formula_category === 'auto_calc').length,
  logic_check: allFormulaRows.value.filter(r => r.formula_category === 'logic_check').length,
  reasonability: allFormulaRows.value.filter(r => r.formula_category === 'reasonability').length,
}))

function categoryTagType(cat: string | null) {
  if (cat === 'auto_calc') return 'primary'
  if (cat === 'logic_check') return 'warning'
  if (cat === 'reasonability') return 'info'
  return ''
}

function categoryLabel(cat: string | null) {
  if (cat === 'auto_calc') return '自动运算'
  if (cat === 'logic_check') return '逻辑审核'
  if (cat === 'reasonability') return '合理性'
  return '未分类'
}

function startEdit(row: any) {
  editingId.value = row.id
  editFormula.value = row.formula || ''
  editCategory.value = row.formula_category || 'auto_calc'
  editDescription.value = row.formula_description || ''
}

async function saveEdit(row: any) {
  if (!row.id) return
  try {
    await http.put(`/api/report-config/${row.id}`, {
      formula: editFormula.value || null,
      formula_category: editCategory.value,
      formula_description: editDescription.value,
    })
    // 更新本地数据
    row.formula = editFormula.value
    row.formula_category = editCategory.value
    row.formula_description = editDescription.value
    editingId.value = null
    ElMessage.success('公式已保存')
    emit('saved')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function onApplyFormulas() {
  if (!props.projectId || !props.year) {
    ElMessage.warning('缺少项目信息，无法应用公式')
    return
  }
  applying.value = true
  try {
    // 调用后端重新生成报表（执行所有自动运算公式）
    await http.post('/api/reports/generate', {
      project_id: props.projectId,
      year: props.year,
    })
    ElMessage.success('自动运算公式已应用，报表数据已刷新')
    emit('applied')
  } catch (e: any) {
    ElMessage.error('应用失败: ' + (e?.message || '请稍后重试'))
  } finally {
    applying.value = false
  }
}
</script>
