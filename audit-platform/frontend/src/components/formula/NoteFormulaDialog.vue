<template>
  <el-dialog
    v-model="visible"
    title="附注公式管理"
    width="800px"
    append-to-body
    destroy-on-close
  >
    <div v-if="!currentNote" class="gt-nf-empty">
      请先选择一个附注章节
    </div>
    <template v-else>
      <div class="gt-nf-header">
        <span>{{ currentNote.note_section }} {{ currentNote.section_title }}</span>
        <el-tag size="small" type="info">{{ currentNote.content_type }}</el-tag>
      </div>

      <!-- 分类 Tab -->
      <el-tabs v-model="activeCategory" style="margin-top: 12px">
        <el-tab-pane label="⚡ 自动运算" name="auto_calc" />
        <el-tab-pane label="🔍 逻辑审核" name="logic_check" />
        <el-tab-pane label="💡 合理性" name="reasonability" />
      </el-tabs>

      <!-- 公式列表 -->
      <el-table :data="filteredFormulas" size="small" border max-height="350">
        <el-table-column prop="target" label="目标单元格" width="120" />
        <el-table-column label="公式" min-width="250">
          <template #default="{ row }">
            <el-input v-if="row._editing" v-model="row.formula" size="small">
              <template #append>
                <el-button size="small" @click="openRefPicker(row)">引用</el-button>
              </template>
            </el-input>
            <code v-else style="font-size: 11px">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="说明" width="160">
          <template #default="{ row }">
            <el-input v-if="row._editing" v-model="row.description" size="small" />
            <span v-else style="font-size: 12px; color: #888">{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <span style="font-size: 11px; color: #aaa">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
            <el-button v-else size="small" link type="success" @click="row._editing = false">完成</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button size="small" @click="addFormula">新增公式</el-button>
      </div>
    </template>

    <template #footer>
      <el-button type="primary" @click="onApply" :loading="applying">应用自动运算</el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 引用选择器 -->
    <FormulaRefPicker
      v-model="showRefPicker"
      :report-rows="refPickerData.reportRows"
      :tb-rows="refPickerData.tbRows"
      :note-rows="refPickerData.noteRows"
      @insert="onInsertRef"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import FormulaRefPicker from './FormulaRefPicker.vue'

const props = defineProps<{
  modelValue: boolean
  currentNote: any
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'applied': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeCategory = ref('auto_calc')
const applying = ref(false)
const showRefPicker = ref(false)
const editingRow = ref<any>(null)

// 引用选择器数据（懒加载）
const refPickerData = ref<{ reportRows: any[], tbRows: any[], noteRows: any[] }>({
  reportRows: [], tbRows: [], noteRows: [],
})

async function openRefPicker(row: any) {
  editingRow.value = row
  // 加载引用数据
  try {
    if (!refPickerData.value.reportRows.length) {
      const [reportData, tbData] = await Promise.all([
        api.get(`/api/reports/${props.projectId}/${props.year}/balance_sheet`).catch(() => []),
        api.get(`/api/trial-balance/`, { params: { project_id: props.projectId, year: props.year } }).catch(() => []),
      ])
      refPickerData.value.reportRows = Array.isArray(reportData) ? reportData : (reportData || [])
      refPickerData.value.tbRows = Array.isArray(tbData) ? tbData : (tbData || [])
    }
  } catch { /* 静默 */ }
  showRefPicker.value = true
}

function onInsertRef(formula: string, _label: string) {
  if (editingRow.value) {
    editingRow.value.formula = (editingRow.value.formula || '') + formula
  }
}

// 附注公式列表（从 currentNote.table_data 推断）
const formulas = ref<any[]>([])

// 当 currentNote 变化时，从表格结构推断默认公式
const filteredFormulas = computed(() => {
  return formulas.value.filter(f => f.category === activeCategory.value)
})

function addFormula() {
  formulas.value.push({
    target: '合计行',
    formula: 'SUM(上方明细行)',
    category: activeCategory.value,
    description: '纵向求和',
    source: '表格结构',
    _editing: true,
  })
}

async function onApply() {
  if (!props.projectId || !props.year || !props.currentNote) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  applying.value = true
  try {
    // 调用后端执行附注公式（从 check_presets 自动生成并计算）
    const noteSection = props.currentNote.note_section
    const data = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${noteSection}/apply-formulas`
    )
    const result = data
    ElMessage.success(`公式已应用：执行 ${result?.executed || 0} 个，更新 ${result?.updated || 0} 个单元格`)
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '应用失败')
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.gt-nf-empty { text-align: center; padding: 40px; color: #999; }
.gt-nf-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }
</style>
