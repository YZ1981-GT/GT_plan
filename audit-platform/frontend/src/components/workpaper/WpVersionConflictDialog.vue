<!--
  WpVersionConflictDialog.vue — 底稿保存版本冲突弹窗

  当保存时服务端返回 409 data_version_conflict，弹出此对话框
  让用户选择：覆盖 / 刷新合并 / 取消

  Requirements: 6.3
-->
<template>
  <el-dialog
    v-model="visible"
    title="版本冲突"
    width="460px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    append-to-body
  >
    <div class="wp-version-conflict">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          <span>数据已被其他用户修改</span>
        </template>
      </el-alert>

      <div class="wp-version-conflict__info">
        <p>
          您的版本：<strong>v{{ clientVersion }}</strong>
        </p>
        <p>
          服务端版本：<strong>v{{ serverVersion }}</strong>
        </p>
        <p v-if="lastModifiedBy">
          最后修改者：<strong>{{ lastModifiedBy }}</strong>
        </p>
        <p v-if="lastModifiedAt">
          修改时间：<strong>{{ formatTime(lastModifiedAt) }}</strong>
        </p>
      </div>

      <div class="wp-version-conflict__hint">
        <p>请选择处理方式：</p>
      </div>
    </div>

    <template #footer>
      <div class="wp-version-conflict__actions">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="warning" @click="handleOverwrite">
          覆盖服务端
        </el-button>
        <el-button type="primary" @click="handleRefresh">
          刷新并合并
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface VersionConflictInfo {
  serverVersion: number
  clientVersion: number
  lastModifiedBy?: string
  lastModifiedAt?: string
}

const props = defineProps<{
  modelValue: boolean
  conflict: VersionConflictInfo | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  overwrite: []
  refresh: []
  cancel: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const serverVersion = computed(() => props.conflict?.serverVersion ?? 0)
const clientVersion = computed(() => props.conflict?.clientVersion ?? 0)
const lastModifiedBy = computed(() => props.conflict?.lastModifiedBy)
const lastModifiedAt = computed(() => props.conflict?.lastModifiedAt)

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

function handleOverwrite() {
  emit('overwrite')
  visible.value = false
}

function handleRefresh() {
  emit('refresh')
  visible.value = false
}

function handleCancel() {
  emit('cancel')
  visible.value = false
}
</script>

<style scoped>
.wp-version-conflict {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wp-version-conflict__info {
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.8;
}

.wp-version-conflict__info p {
  margin: 0;
}

.wp-version-conflict__hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.wp-version-conflict__hint p {
  margin: 0;
}

.wp-version-conflict__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
