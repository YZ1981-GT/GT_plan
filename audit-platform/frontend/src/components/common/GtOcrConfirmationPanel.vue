<script setup lang="ts">
/**
 * GtOcrConfirmationPanel — OCR 差异确认面板（Task 5.5, Wave 4）
 *
 * 显示原始值与确认值的差异，提供 accept/correct/reject 操作按钮。
 */
import { ref, computed } from 'vue'

export interface FieldConfirmation {
  id?: string
  field_name: string
  original_value: string | null
  confirmed_value: string | null
  decision: 'accepted' | 'corrected' | 'rejected' | null
  actor_type?: string
  created_at?: string
}

const props = defineProps<{
  fields: FieldConfirmation[]
  readonly?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm', payload: { field_name: string; decision: string; confirmed_value?: string }): void
}>()

const editingField = ref<string | null>(null)
const correctedValue = ref('')

function startCorrect(field: FieldConfirmation) {
  editingField.value = field.field_name
  correctedValue.value = field.original_value || ''
}

function cancelEdit() {
  editingField.value = null
  correctedValue.value = ''
}

function submitDecision(fieldName: string, decision: string, value?: string) {
  emit('confirm', {
    field_name: fieldName,
    decision,
    confirmed_value: value,
  })
  editingField.value = null
  correctedValue.value = ''
}

function decisionTag(decision: string | null): { type: string; label: string } {
  switch (decision) {
    case 'accepted':
      return { type: 'success', label: '采纳' }
    case 'corrected':
      return { type: 'warning', label: '修正' }
    case 'rejected':
      return { type: 'danger', label: '拒绝' }
    default:
      return { type: 'info', label: '待决定' }
  }
}

const decidedCount = computed(() => props.fields.filter(f => f.decision).length)
const totalCount = computed(() => props.fields.length)
</script>

<template>
  <div class="ocr-confirmation-panel">
    <div class="panel-header">
      <span class="title">字段确认</span>
      <el-tag size="small" :type="decidedCount === totalCount ? 'success' : 'warning'">
        {{ decidedCount }}/{{ totalCount }} 已决定
      </el-tag>
    </div>

    <el-skeleton v-if="loading" :rows="4" animated />

    <el-table v-else :data="fields" size="small" stripe border>
      <el-table-column prop="field_name" label="字段名" width="140" />
      <el-table-column label="原始值" min-width="120">
        <template #default="{ row }">
          <span class="original-value">{{ row.original_value || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="确认值" min-width="120">
        <template #default="{ row }">
          <template v-if="editingField === row.field_name">
            <el-input
              v-model="correctedValue"
              size="small"
              placeholder="输入修正值"
              @keyup.enter="submitDecision(row.field_name, 'corrected', correctedValue)"
            />
          </template>
          <template v-else>
            <span v-if="row.confirmed_value" class="confirmed-value">
              {{ row.confirmed_value }}
            </span>
            <span v-else class="no-value">—</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="decisionTag(row.decision).type" size="small">
            {{ decisionTag(row.decision).label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center" v-if="!readonly">
        <template #default="{ row }">
          <template v-if="editingField === row.field_name">
            <el-button size="small" type="primary" @click="submitDecision(row.field_name, 'corrected', correctedValue)">
              确认修正
            </el-button>
            <el-button size="small" @click="cancelEdit">取消</el-button>
          </template>
          <template v-else>
            <el-button
              size="small"
              type="success"
              plain
              @click="submitDecision(row.field_name, 'accepted', row.original_value)"
            >
              采纳
            </el-button>
            <el-button size="small" type="warning" plain @click="startCorrect(row)">
              修正
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              @click="submitDecision(row.field_name, 'rejected')"
            >
              拒绝
            </el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.ocr-confirmation-panel {
  padding: 12px 0;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.title {
  font-size: 14px;
  font-weight: 500;
}
.original-value {
  color: var(--el-text-color-regular);
}
.confirmed-value {
  color: var(--el-color-success);
  font-weight: 500;
}
.no-value {
  color: var(--el-text-color-placeholder);
}
</style>
