<template>
  <div class="wp-version-history">
    <div class="wp-version-history__header">
      <h4 class="wp-version-history__title">版本历史</h4>
      <el-button
        size="small"
        :icon="Refresh"
        :loading="loadingVersions"
        @click="fetchVersions"
      >
        刷新
      </el-button>
    </div>

    <el-table
      v-loading="loadingVersions"
      :data="versions"
      size="small"
      stripe
      border
      empty-text="暂无版本记录"
      class="wp-version-history__table"
    >
      <el-table-column prop="version_no" label="版本号" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">v{{ row.version_no }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="sourceTagType(row.source)" size="small">
            {{ sourceLabel(row.source) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="100">
        <template #default="{ row }">
          {{ row.created_by || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="file_retained" label="文件" width="70" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.file_retained" color="var(--el-color-success)"><Check /></el-icon>
          <el-icon v-else color="var(--el-text-color-disabled)"><Close /></el-icon>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * WpVersionHistoryPanel — 版本历史面板
 *
 * 底稿详情区域展示版本列表。
 * 显示版本号、来源、创建时间、创建人。
 *
 * Requirements: 6.1, 6.2
 */
import { ref, onMounted, watch } from 'vue'
import { Refresh, Check, Close } from '@element-plus/icons-vue'
import { useWpExportImport } from '@/composables/useWpExportImport'
import type { VersionArchiveItem } from '@/composables/useWpExportImport'

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const { getVersionHistory } = useWpExportImport()

const versions = ref<VersionArchiveItem[]>([])
const loadingVersions = ref(false)

async function fetchVersions() {
  loadingVersions.value = true
  try {
    versions.value = await getVersionHistory(props.projectId, props.wpId)
  } catch {
    versions.value = []
  } finally {
    loadingVersions.value = false
  }
}

function sourceTagType(source: string) {
  switch (source) {
    case 'import': return 'primary'
    case 'upload': return 'success'
    case 'edit': return 'info'
    case 'template': return 'warning'
    default: return 'info'
  }
}

function sourceLabel(source: string) {
  switch (source) {
    case 'import': return '导入'
    case 'upload': return '上传'
    case 'edit': return '编辑'
    case 'template': return '模板'
    default: return source
  }
}

function formatTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

onMounted(fetchVersions)

watch(() => props.wpId, fetchVersions)
</script>

<style scoped>
.wp-version-history {
  padding: 12px 0;
}

.wp-version-history__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.wp-version-history__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.wp-version-history__table {
  width: 100%;
}
</style>
