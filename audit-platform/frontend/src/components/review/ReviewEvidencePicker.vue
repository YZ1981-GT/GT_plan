<script setup lang="ts">
/**
 * P1-1.2: 复核意见关联证据选择器
 *
 * 支持关联底稿单元格、附件、报告段落、附注表格
 */
import { ref, computed } from 'vue'
import type { EvidenceRef, EvidenceType } from '@/types/evidenceRef'

interface Props {
  modelValue: EvidenceRef[]
  projectId: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: EvidenceRef[]]
}>()

const showDialog = ref(false)
const selectedType = ref<EvidenceType>('attachment')
const evidenceId = ref('')
const evidenceLabel = ref('')

const evidenceTypes: { value: EvidenceType; label: string }[] = [
  { value: 'workpaper_cell', label: '底稿单元格' },
  { value: 'attachment', label: '附件' },
  { value: 'report_paragraph', label: '报告段落' },
  { value: 'note_table', label: '附注表格' },
]

const linkedRefs = computed(() => props.modelValue)

function openDialog() {
  if (props.disabled) return
  showDialog.value = true
  evidenceId.value = ''
  evidenceLabel.value = ''
}

function addEvidence() {
  if (!evidenceId.value.trim()) return
  const newRef: EvidenceRef = {
    evidence_type: selectedType.value,
    evidence_id: evidenceId.value.trim(),
    project_id: props.projectId,
    label: evidenceLabel.value || undefined,
  }
  emit('update:modelValue', [...props.modelValue, newRef])
  showDialog.value = false
}

function removeEvidence(index: number) {
  if (props.disabled) return
  const updated = [...props.modelValue]
  updated.splice(index, 1)
  emit('update:modelValue', updated)
}

function getTypeLabel(type: EvidenceType): string {
  const found = evidenceTypes.find((t) => t.value === type)
  return found?.label ?? type
}
</script>

<template>
  <div class="review-evidence-picker">
    <div class="evidence-list">
      <el-tag
        v-for="(ref, idx) in linkedRefs"
        :key="`${ref.evidence_type}-${ref.evidence_id}-${idx}`"
        :closable="!disabled"
        type="info"
        class="evidence-tag"
        @close="removeEvidence(idx)"
      >
        {{ getTypeLabel(ref.evidence_type) }}：{{ ref.label || ref.evidence_id }}
      </el-tag>
    </div>
    <el-button
      v-if="!disabled"
      size="small"
      type="primary"
      plain
      @click="openDialog"
    >
      关联证据
    </el-button>

    <el-dialog
      v-model="showDialog"
      title="关联证据"
      width="480px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="证据类型">
          <el-select v-model="selectedType" placeholder="选择证据类型">
            <el-option
              v-for="t in evidenceTypes"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="证据 ID">
          <el-input
            v-model="evidenceId"
            placeholder="输入证据标识"
          />
        </el-form-item>
        <el-form-item label="展示名称">
          <el-input
            v-model="evidenceLabel"
            placeholder="可选：便于识别的名称"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="addEvidence">确认关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.review-evidence-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.evidence-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.evidence-tag {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
