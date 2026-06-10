<!--
  WritebackConflictDialog.vue — 回填冲突三方裁决弹窗

  Spec:    deliverable-lineage-and-writeback Task 16.2
  Design:  前端设计「OnlyOffice 集成点」+ 需求 8.2/8.3
  Reqs:    8.2, 8.3

  功能：
    - 三栏对照（出品物值 / 上游值 / 基线值）
    - 单选保留方 → 收集后再次提交 resolutions
    - 全中文化 + GT 紫令牌
-->
<template>
  <el-dialog
    :model-value="visible"
    title="回填冲突裁决"
    width="80%"
    :close-on-click-modal="false"
    class="writeback-conflict-dialog"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="conflict-dialog__description">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>
          以下章节在出品物编辑后，上游附注也被独立修改过，需要您选择保留哪一方的内容。
        </template>
      </el-alert>
    </div>

    <div class="conflict-dialog__list">
      <div
        v-for="(conflict, idx) in conflicts"
        :key="conflict.section_code"
        class="conflict-dialog__item"
      >
        <div class="conflict-dialog__item-header">
          <span class="conflict-dialog__section-code">{{ conflict.section_code }}</span>
          <el-tag size="small" type="danger">冲突</el-tag>
        </div>

        <!-- 三栏对照 -->
        <div class="conflict-dialog__comparison">
          <div class="conflict-dialog__col">
            <div class="conflict-dialog__col-header">
              <el-radio
                v-model="resolutions[conflict.section_code]"
                label="deliverable"
              >
                出品物侧编辑值
              </el-radio>
            </div>
            <div class="conflict-dialog__col-content">
              {{ conflict.deliverable_value || '（空）' }}
            </div>
          </div>

          <div class="conflict-dialog__col">
            <div class="conflict-dialog__col-header">
              <el-radio
                v-model="resolutions[conflict.section_code]"
                label="upstream"
              >
                上游当前值
              </el-radio>
            </div>
            <div class="conflict-dialog__col-content">
              {{ conflict.upstream_value || '（空）' }}
            </div>
          </div>

          <div class="conflict-dialog__col conflict-dialog__col--baseline">
            <div class="conflict-dialog__col-header">
              <span class="conflict-dialog__col-label">生成时基线值（参考）</span>
            </div>
            <div class="conflict-dialog__col-content">
              {{ conflict.baseline_value || '（空）' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="conflict-dialog__footer">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button
          type="primary"
          :disabled="!allResolved"
          :loading="submitting"
          class="conflict-dialog__submit-btn"
          @click="onSubmit"
        >
          确认裁决并回填
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface WritebackConflict {
  section_code: string
  deliverable_value: string
  upstream_value: string
  baseline_value: string
}

const props = defineProps<{
  visible: boolean
  conflicts: WritebackConflict[]
  projectId: string
  wordExportTaskId: string
  year?: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'resolved', resolutions: Record<string, string>): void
}>()

const resolutions = ref<Record<string, string>>({})
const submitting = ref(false)

// 当冲突列表变化时重置 resolutions
watch(
  () => props.conflicts,
  (newConflicts) => {
    const r: Record<string, string> = {}
    for (const c of newConflicts) {
      r[c.section_code] = ''
    }
    resolutions.value = r
  },
  { immediate: true },
)

const allResolved = computed(() => {
  return props.conflicts.every(
    (c) => resolutions.value[c.section_code] && resolutions.value[c.section_code] !== '',
  )
})

async function onSubmit(): Promise<void> {
  if (!allResolved.value) {
    ElMessage.warning('请为所有冲突章节选择保留方')
    return
  }

  submitting.value = true

  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/writeback`
    await api.post(url, {
      year: props.year || new Date().getFullYear(),
      resolutions: resolutions.value,
    })

    ElMessage.success('冲突裁决已提交，回填完成')
    emit('resolved', resolutions.value)
    emit('update:visible', false)
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.error('权限不足：需要编辑权限才能执行回填')
    } else if (e?.response?.status === 409) {
      ElMessage.warning(e?.response?.data?.detail || e?.response?.data?.message || '该出品物已终态，不可回填')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '裁决提交失败')
    }
  } finally {
    submitting.value = false
  }
}

defineExpose({
  resolutions,
  allResolved,
  onSubmit,
})
</script>

<style scoped>
.conflict-dialog__description {
  margin-bottom: 16px;
}

.conflict-dialog__list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 60vh;
  overflow-y: auto;
}

.conflict-dialog__item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
}

.conflict-dialog__item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.conflict-dialog__section-code {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.conflict-dialog__comparison {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.conflict-dialog__col {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
}

.conflict-dialog__col-header {
  padding: 8px 10px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  font-weight: 600;
}

.conflict-dialog__col--baseline .conflict-dialog__col-header {
  background: var(--el-fill-color-lighter);
}

.conflict-dialog__col-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.conflict-dialog__col-content {
  padding: 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.conflict-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.conflict-dialog__submit-btn {
  --el-button-bg-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-primary, #4b2d77);
}

.conflict-dialog__submit-btn:not(.is-disabled):hover {
  --el-button-hover-bg-color: #5e3a94;
  --el-button-hover-border-color: #5e3a94;
}
</style>
