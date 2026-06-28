<template>
  <el-card shadow="never">
    <template #header>版本链（按时间倒序）</template>
    <el-timeline>
      <el-timeline-item
        v-for="v in versions"
        :key="v.id"
        :timestamp="formatTime(v.created_at)"
        placement="top"
      >
        <div class="version-row">
          <span>v{{ v.version_no }}</span>
          <span v-if="v.file_size">{{ formatSize(v.file_size) }}</span>
          <span v-if="v.created_via">{{ v.created_via }}</span>
          <el-button
            link
            type="primary"
            @click="download(v.version_no)"
          >下载</el-button>
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup lang="ts">
import { deliverableDownloadUrl } from '@/services/deliverableApi'
import type { DeliverableVersion } from '@/services/deliverableApi'
import { downloadFile } from '@/utils/http'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  versions: DeliverableVersion[]
  projectId: string
}>()

const displayPrefs = useDisplayPrefsStore()

/**
 * 格式化版本创建时间。
 * 后端 created_at 由 PG func.now() 生成，是 naive UTC（无时区标记），
 * 浏览器会误当本地时间解析。这里补 'Z' 标记为 UTC，再交给统一格式化器
 * 转换为本地时区（中国 UTC+8）显示。
 */
function formatTime(v: string | null | undefined): string {
  if (!v) return '-'
  // 已带时区标记（Z 或 ±HH:MM）则不动；否则视为 UTC 补 'Z'
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)
  const iso = hasTz ? v : `${v}Z`
  return displayPrefs.fmtDateTime(iso)
}

function download(versionNo: number) {
  const taskId = props.versions[0]?.word_export_task_id
  if (!taskId) return
  const v = props.versions.find((x) => x.version_no === versionNo)
  const url = deliverableDownloadUrl(props.projectId, taskId, versionNo)
  downloadFile(url, { fileName: v?.file_path?.split(/[/\\]/).pop() || `deliverable_v${versionNo}` })
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
