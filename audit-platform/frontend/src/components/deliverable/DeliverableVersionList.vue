<template>
  <el-card shadow="never">
    <template #header>版本链（按时间倒序）</template>
    <el-timeline>
      <el-timeline-item
        v-for="v in versions"
        :key="v.id"
        :timestamp="v.created_at || ''"
        placement="top"
      >
        <div class="version-row">
          <span>v{{ v.version_no }}</span>
          <span v-if="v.file_size">{{ formatSize(v.file_size) }}</span>
          <span v-if="v.created_via">{{ v.created_via }}</span>
          <el-button
            link
            type="primary"
            :href="downloadUrl(v.version_no)"
            target="_blank"
          >下载</el-button>
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup lang="ts">
import { deliverableDownloadUrl } from '@/services/deliverableApi'
import type { DeliverableVersion } from '@/services/deliverableApi'

const props = defineProps<{
  versions: DeliverableVersion[]
  projectId: string
}>()

function downloadUrl(versionNo: number) {
  const taskId = props.versions[0]?.word_export_task_id
  if (!taskId) return '#'
  return deliverableDownloadUrl(props.projectId, taskId, versionNo)
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}
</script>

<style scoped>
.version-row {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>
