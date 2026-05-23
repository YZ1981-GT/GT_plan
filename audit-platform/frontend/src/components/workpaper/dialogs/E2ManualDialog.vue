<template>
  <el-dialog
    v-model="visible"
    :title="title"
    :fullscreen="true"
    :close-on-press-escape="false"
    :close-on-click-modal="false"
    @close="onCloseAttempt"
    class="gt-fullscreen-dialog"
  >
    <AuditContextHeader
      :procedure-code="procedureCode"
      :assertions="assertions"
      :risk-level="riskLevel"
    />

    <div class="gt-e2-toolbar">
      <el-button size="small" type="primary" plain @click="addItem">+ 增加行</el-button>
    </div>

    <el-table :data="form.items" stripe height="450">
      <el-table-column label="#" type="index" width="50" />
      <el-table-column
        v-for="col in columns"
        :key="col.field"
        :label="col.label"
        :width="col.width"
      >
        <template #default="{ row }">
          <el-input v-if="col.type !== 'number'" v-model="row[col.field]" size="small" />
          <el-input-number
            v-else
            v-model="row[col.field]"
            size="small"
            :precision="2"
            :controls="false"
          />
        </template>
      </el-table-column>
      <el-table-column label="批注" width="180">
        <template #default="{ $index }">
          <ItemAnnotation v-model="form.items[$index].annotations" />
        </template>
      </el-table-column>
      <el-table-column label="附件" width="160">
        <template #default="{ $index }">
          <ItemAttachment
            :project-id="projectId"
            :wp-id="wpId"
            :sheet-key="sheetKey"
            :item-index="$index"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ $index }">
          <el-button text type="danger" size="small" @click="removeItem($index)">×</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="gt-e2-conclusion">
      <span class="gt-e2-conclusion-label">结论：</span>
      <el-input
        v-model="form.conclusion"
        type="textarea"
        :rows="3"
        placeholder="请填写结论"
      />
      <AiConclusionButton
        :wp-id="wpId"
        scenario="audit_conclusion"
        :sheet-key="sheetKey"
        :context="{ items: form.items }"
        @apply="(t) => (form.conclusion = t)"
      />
    </div>

    <template #footer>
      <div class="gt-fullscreen-dialog-footer">
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * E2ManualDialog — E2 类人工检查弹窗（Sprint 2 Task 2.11）
 *
 * 适用 sheet：E1-20 利息收入测算 等需要手工录入的人工检查类
 */
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './AuditContextHeader.vue'
import ItemAnnotation from '../ItemAnnotation.vue'
import ItemAttachment from '../ItemAttachment.vue'
import AiConclusionButton from '../AiConclusionButton.vue'
import { confirmLeave } from '@/utils/confirm'

interface ColumnDef {
  field: string
  label: string
  type?: 'string' | 'number'
  width?: number
}

interface Props {
  modelValue: boolean
  projectId: string
  wpId: string
  sheetKey: string
  title?: string
  procedureCode?: string
  assertions?: string[]
  riskLevel?: string
  /** 自定义列结构 */
  columns?: ColumnDef[]
}
const props = withDefaults(defineProps<Props>(), {
  title: 'E2 人工检查',
  procedureCode: '',
  assertions: () => [],
  riskLevel: '',
  columns: () => [
    { field: 'bank', label: '银行/对象', type: 'string', width: 160 },
    { field: 'description', label: '说明', type: 'string', width: 240 },
    { field: 'amount', label: '金额', type: 'number', width: 130 },
  ],
})
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [] }>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => (visible.value = v))
watch(visible, (v) => emit('update:modelValue', v))

const form = ref({
  items: [] as any[],
  conclusion: '',
})
const saving = ref(false)

async function loadData() {
  try {
    const detail: any = await api.get(`/api/projects/${props.projectId}/working-papers/${props.wpId}`)
    const sheet = detail?.parsed_data?.[props.sheetKey] || {}
    form.value = {
      items: Array.isArray(sheet.items) ? sheet.items : [],
      conclusion: sheet.conclusion || '',
    }
  } catch {
    /* 静默 */
  }
}
watch(visible, (v) => { if (v) loadData() })

function addItem() {
  const newRow: any = { annotations: [] }
  for (const c of props.columns) {
    newRow[c.field] = c.type === 'number' ? 0 : ''
  }
  form.value.items.push(newRow)
}
function removeItem(idx: number) {
  form.value.items.splice(idx, 1)
}

async function onSave() {
  saving.value = true
  try {
    await api.patch(`/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`, {
      sheet_key: props.sheetKey,
      data: {
        items: form.value.items,
        conclusion: form.value.conclusion,
      },
    })
    ElMessage.success('已保存')
    eventBus.emit('manual-refresh', { projectId: props.projectId, wpId: props.wpId })
    emit('saved')
    visible.value = false
  } catch (err: any) {
    ElMessage.error('保存失败：' + (err?.message || '请稍后重试'))
  } finally {
    saving.value = false
  }
}

async function onCancel() {
  try {
    await confirmLeave('E2 人工检查')
    visible.value = false
  } catch {
    /* user cancelled */
  }
}

function onCloseAttempt() {
  onCancel()
}
</script>

<style scoped>
.gt-e2-toolbar {
  padding: 6px 12px;
  margin-bottom: 8px;
}
.gt-e2-conclusion {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 12px;
  margin-top: 8px;
}
.gt-e2-conclusion-label {
  white-space: nowrap;
  padding-top: 6px;
  color: var(--gt-color-text-secondary);
}
.gt-e2-conclusion :deep(.el-textarea) {
  flex: 1;
}
.gt-fullscreen-dialog :deep(.el-dialog__body) {
  padding: 8px 16px;
  height: calc(100vh - 110px);
  overflow-y: auto;
}
.gt-fullscreen-dialog-footer {
  position: sticky;
  bottom: 0;
  background: var(--gt-color-bg-white, #fff);
  padding: 8px 0;
  border-top: 1px solid var(--gt-color-border-lighter, #ebeef5);
  text-align: right;
}
</style>
