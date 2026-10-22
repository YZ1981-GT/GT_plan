<template>
  <el-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)"
    title="合并附注明细模板编辑器" width="720px" append-to-body destroy-on-close>
    <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <el-input v-model="templateName" placeholder="模板名称（如：管理费用明细）" size="small" style="width:240px" />
      <el-tag size="small" type="info">v{{ currentVersion }}</el-tag>
      <span style="flex:1" />
      <el-button size="small" @click="handleSuggest" :loading="suggesting">💡 从来源建议</el-button>
    </div>

    <el-table :data="editRows" border size="small" max-height="400" row-key="target_row_id">
      <el-table-column label="↕" width="50" align="center">
        <template #default="{ $index }">
          <span class="gt-drag-handle" draggable="true"
            @dragstart="onDragStart($index, $event)"
            @dragover.prevent="onDragOver($index)"
            @drop="onDrop($index)"
            style="cursor:grab;user-select:none">☰</span>
        </template>
      </el-table-column>
      <el-table-column label="序号" width="50" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="规范名称" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.canonical_name" size="small" placeholder="必填" />
        </template>
      </el-table-column>
      <el-table-column label="别名（逗号分隔）" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row._aliases_text" size="small" placeholder="工资及奖金, 管理人员薪酬" />
        </template>
      </el-table-column>
      <el-table-column label="行类型" width="110">
        <template #default="{ row }">
          <el-select v-model="row.row_type" size="small" style="width:90px">
            <el-option label="数据" value="data" />
            <el-option label="合计" value="total" />
            <el-option label="小计" value="subtotal" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ $index }">
          <el-button size="small" text :disabled="$index === 0" @click="moveRow($index, -1)">↑</el-button>
          <el-button size="small" text :disabled="$index === editRows.length - 1" @click="moveRow($index, 1)">↓</el-button>
          <el-button size="small" type="danger" text @click="removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div style="margin-top:8px;display:flex;gap:8px">
      <el-button size="small" @click="addRow">+ 新增行</el-button>
      <span style="flex:1" />
      <span style="font-size:12px;color:var(--gt-color-text-tertiary)">共 {{ editRows.length }} 行</span>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">保存为新版本</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { DetailTemplateRow, DetailTemplate } from '@/services/consolidationApi'
import {
  createDetailTemplate,
  addDetailTemplateVersion,
  checkRowDeletion,
  suggestDetailTemplate,
} from '@/services/consolidationApi'

interface EditRow {
  target_row_id: string
  canonical_name: string
  _aliases_text: string
  row_type: 'data' | 'total' | 'subtotal'
  sort_order: number
}

const props = defineProps<{
  visible: boolean
  projectId: string
  sectionId: string
  year: number
  templateType: 'soe' | 'listed'
  /** 已有模板（编辑模式）；为 null 时是新建 */
  template: DetailTemplate | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', tmpl: DetailTemplate): void
}>()

const templateName = ref('')
const currentVersion = ref(1)
const editRows = ref<EditRow[]>([])
const saving = ref(false)
const suggesting = ref(false)

watch(() => props.visible, (v) => {
  if (!v) return
  if (props.template?.latest_version) {
    templateName.value = props.template.name || ''
    currentVersion.value = props.template.latest_version.version_number
    editRows.value = props.template.latest_version.rows.map(toEditRow)
  } else {
    templateName.value = ''
    currentVersion.value = 1
    editRows.value = [emptyRow()]
  }
})

function toEditRow(r: DetailTemplateRow): EditRow {
  return {
    target_row_id: r.target_row_id,
    canonical_name: r.canonical_name,
    _aliases_text: (r.aliases || []).join(', '),
    row_type: r.row_type || 'data',
    sort_order: r.sort_order || 0,
  }
}

function emptyRow(): EditRow {
  return { target_row_id: '', canonical_name: '', _aliases_text: '', row_type: 'data', sort_order: editRows.value.length * 10 }
}

function addRow() {
  editRows.value.push(emptyRow())
}

// ── 拖拽排序（HTML5 Drag & Drop） ──
let dragFromIndex = -1

function onDragStart(index: number, event: DragEvent) {
  dragFromIndex = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

function onDragOver(index: number) {
  // prevent default 已在模板 @dragover.prevent 处理
}

function onDrop(toIndex: number) {
  if (dragFromIndex < 0 || dragFromIndex === toIndex) return
  const rows = editRows.value
  const [moved] = rows.splice(dragFromIndex, 1)
  rows.splice(toIndex, 0, moved)
  dragFromIndex = -1
}

function moveRow(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= editRows.value.length) return
  const rows = editRows.value
  const temp = rows[index]
  rows[index] = rows[target]
  rows[target] = temp
}

async function removeRow(idx: number) {
  const row = editRows.value[idx]
  if (row.target_row_id && props.template) {
    try {
      const impact = await checkRowDeletion(props.template.id, [row.target_row_id])
      if (impact.affected_rule_count > 0) {
        await ElMessageBox.confirm(
          `该行被 ${impact.affected_rule_count} 条映射规则引用，涉及 ${impact.affected_entity_count} 家企业。确认删除？`,
          '删除确认', { type: 'warning' },
        )
      }
    } catch (err: any) {
      // 用户取消 ElMessageBox 也走这里——cancelled 不应阻止后续逻辑
      if (err === 'cancel' || err?.toString?.()?.includes('cancel')) return
      // 网络错误时仍允许删除（前端编辑，保存时后端再校验）
    }
  }
  editRows.value.splice(idx, 1)
}

function toApiRows(): Array<Partial<DetailTemplateRow>> {
  return editRows.value.map((r, i) => ({
    target_row_id: r.target_row_id || undefined,
    canonical_name: r.canonical_name.trim(),
    aliases: r._aliases_text.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    sort_order: i * 10,
    row_type: r.row_type,
  }))
}

async function handleSave() {
  const rows = toApiRows()
  if (rows.some(r => !r.canonical_name)) {
    ElMessage.warning('所有行的规范名称不能为空')
    return
  }
  saving.value = true
  try {
    let result: DetailTemplate
    if (props.template) {
      const ver = await addDetailTemplateVersion(props.template.id, {
        rows, change_note: `v${currentVersion.value + 1}`,
      })
      result = { ...props.template, latest_version: ver }
    } else {
      result = await createDetailTemplate({
        template_type: props.templateType,
        section_id: props.sectionId,
        name: templateName.value.trim() || props.sectionId,
        rows,
      })
    }
    ElMessage.success('模板已保存')
    emit('saved', result)
    emit('update:visible', false)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail?.message || err?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSuggest() {
  suggesting.value = true
  try {
    const result = await suggestDetailTemplate(props.projectId, props.sectionId, props.year)
    if (!result.suggested_rows?.length) {
      ElMessage.info('当前来源没有可建议的行')
      return
    }
    // 建议以合并附注模板该表的行（顺序 / 行类型）为骨架，别名是子企业来源里的不同写法
    editRows.value = result.suggested_rows.map((r: any) => ({
      target_row_id: '',
      canonical_name: r.canonical_name,
      _aliases_text: (r.aliases || []).join(', '),
      row_type: r.row_type || 'data',
      sort_order: r.sort_order || 0,
    }))
    ElMessage.success(`已导入 ${result.suggested_rows.length} 行建议`)
  } catch (err: any) {
    ElMessage.error('获取建议失败')
  } finally {
    suggesting.value = false
  }
}
</script>
