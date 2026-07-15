<script setup lang="ts">
/**
 * GtOcrWritebackDialog — OCR 写回对话框（Task 5.5, Wave 4）
 *
 * 显示映射预览、冲突警告，确认后执行写回。
 */
import { ref, computed, watch } from 'vue'

export interface MappingField {
  field_name: string
  confirmed_value: string
}

const props = defineProps<{
  visible: boolean
  mapping: Record<string, string> | null
  allDecided: boolean
  readyForWriteback: boolean
  conflictWarning?: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirm-writeback'): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

const mappingEntries = computed<MappingField[]>(() => {
  if (!props.mapping) return []
  return Object.entries(props.mapping).map(([field_name, confirmed_value]) => ({
    field_name,
    confirmed_value,
  }))
})

const hasConflict = computed(() => !!props.conflictWarning)

function handleConfirm() {
  emit('confirm-writeback')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="OCR 写回确认"
    width="580px"
    :close-on-click-modal="false"
  >
    <!-- 冲突警告 -->
    <el-alert
      v-if="hasConflict"
      type="error"
      :title="conflictWarning || '版本冲突'"
      description="目标对象版本已变化，无法执行写回。请刷新后重试。"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <!-- 未完成决定警告 -->
    <el-alert
      v-if="!allDecided"
      type="warning"
      title="部分字段尚未决定"
      description="所有 required 字段需先作出 accepted/corrected/rejected 决定后才可写回。"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <!-- 映射预览 -->
    <div class="mapping-section">
      <div class="section-title">写回字段预览</div>
      <el-table v-if="mappingEntries.length > 0" :data="mappingEntries" size="small" stripe border>
        <el-table-column prop="field_name" label="目标字段" min-width="140" />
        <el-table-column prop="confirmed_value" label="写入值" min-width="160">
          <template #default="{ row }">
            <span class="write-value">{{ row.confirmed_value }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无可写回的字段（rejected 字段已排除）" />
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!readyForWriteback || hasConflict"
        :loading="loading"
        @click="handleConfirm"
      >
        确认写回
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mapping-section {
  margin-top: 8px;
}
.section-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--el-text-color-regular);
}
.write-value {
  color: var(--el-color-primary);
  font-weight: 500;
}
</style>
