<template>
  <div class="wp-conflict-panel">
    <el-alert type="warning" :closable="false" show-icon>
      <template #title>检测到版本冲突</template>
      <p>该底稿在您导出后已被其他人修改，请选择处理方式。</p>
    </el-alert>

    <el-descriptions :column="1" border class="wp-conflict-panel__details">
      <el-descriptions-item label="服务器版本">
        v{{ conflict.server_version }}
      </el-descriptions-item>
      <el-descriptions-item label="导入文件版本">
        v{{ conflict.imported_version }}
      </el-descriptions-item>
      <el-descriptions-item label="最后修改人">
        {{ conflict.last_modifier || '未知' }}
      </el-descriptions-item>
      <el-descriptions-item label="最后修改时间">
        {{ formatTime(conflict.last_modified_at) }}
      </el-descriptions-item>
      <el-descriptions-item label="冲突类型">
        <el-tag :type="conflict.is_substantive ? 'danger' : 'info'" size="small">
          {{ conflictTypeLabel }}
        </el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <div class="wp-conflict-panel__actions">
      <el-button
        type="danger"
        :loading="loading"
        @click="$emit('resolve', 'force_overwrite')"
      >
        强制覆盖
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="$emit('resolve', 'parallel_version')"
      >
        创建并行版本
      </el-button>
      <el-button
        :loading="loading"
        @click="$emit('resolve', 'cancel')"
      >
        取消导入
      </el-button>
    </div>

    <div class="wp-conflict-panel__hint">
      <el-text type="info" size="small">
        <strong>强制覆盖</strong>：用当前导入文件替换服务器版本（操作不可逆，将写入审计日志）<br>
        <strong>创建并行版本</strong>：保留服务器版本，同时创建新版本<br>
        <strong>取消导入</strong>：放弃本次导入
      </el-text>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * WpConflictPanel — 冲突处理面板
 *
 * 409 时弹出冲突详情（版本号、最后修改人、时间）。
 * 三选项按钮: 强制覆盖 / 创建并行版本 / 取消导入。
 * 调用 import/resolve 端点。
 *
 * Requirements: 4.3, 4.4
 */
import { computed } from 'vue'
import type { ConflictResult } from '@/composables/useWpExportImport'

const props = defineProps<{
  conflict: ConflictResult
  loading?: boolean
}>()

defineEmits<{
  (e: 'resolve', resolution: 'force_overwrite' | 'parallel_version' | 'cancel'): void
}>()

const conflictTypeLabel = computed(() => {
  if (props.conflict.is_substantive) return '实质冲突（内容已变更）'
  return '版本冲突（内容未实质变更）'
})

function formatTime(iso?: string): string {
  if (!iso) return '未知'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
</script>

<style scoped>
.wp-conflict-panel__details {
  margin-top: 16px;
}

.wp-conflict-panel__actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
  justify-content: center;
}

.wp-conflict-panel__hint {
  margin-top: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
</style>
