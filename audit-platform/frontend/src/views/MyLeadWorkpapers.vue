<template>
  <div class="gt-my-lead">
    <!-- External_Not_Found 统一占位（Req 12.7）：不显示内部原因、不闪现缓存名称 -->
    <GtEmpty
      v-if="list.hasNotFound.value"
      preset="no-data"
      :title="list.notFoundMessage.value"
      description="请确认底稿仍在你的委派范围内，或联系项目经理"
    />

    <template v-else>
      <!-- 状态统计（服务端 stats，非客户端聚合；Req 11.4/12.4/12.5） -->
      <div class="gt-my-lead__stats" v-if="list.total.value">
        <span class="gt-my-lead__stat">主编底稿 <b>{{ list.total.value }}</b></span>
        <span v-for="(cnt, key) in list.stats.value.by_file_status" :key="key" class="gt-my-lead__stat">
          {{ fileStatusLabel(key) }} <b>{{ cnt }}</b>
        </span>
      </div>

      <GtEmpty
        v-if="list.isEmpty.value"
        preset="no-data"
        title="暂无你主编的底稿"
        description="你被指定为底稿主编后将在此显示"
      />

      <el-table v-else :data="list.items.value" v-loading="list.loading.value" border size="small" stripe>
        <el-table-column prop="wp_code" label="编码" width="100" />
        <el-table-column prop="wp_name" label="底稿名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="audit_cycle" label="循环" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.audit_cycle || '—' }}</el-tag>
          </template>
        </el-table-column>
        <!-- 状态拆分：索引层 / 文件层分列（Req 12.4/12.5） -->
        <el-table-column label="索引状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">{{ indexStatusLabel(row.index_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.wp_generated" size="small" :type="fileStatusType(row.file_status)">
              {{ fileStatusLabel(row.file_status) }}
            </el-tag>
            <!-- nullable wp：底稿尚未生成（Req 12.8） -->
            <el-tag v-else size="small" type="info" effect="plain">{{ list.NOT_GENERATED_LABEL }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <!-- wp_generated 才允许打开/下载（Req 12.9：禁用依赖具体底稿资源的动作） -->
            <template v-if="list.canOpen(row)">
              <el-button link type="primary" size="small" @click="openWorkpaper(row)">打开</el-button>
              <el-button link type="primary" size="small" @click="download(row)">下载</el-button>
            </template>
            <el-tooltip v-else content="底稿尚未生成，生成后可打开与下载" placement="top">
              <span class="gt-my-lead__disabled">{{ list.NOT_GENERATED_LABEL }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="list.total.value > list.pageSize.value"
        layout="prev, pager, next, total"
        :total="list.total.value"
        :page-size="list.pageSize.value"
        :current-page="list.page.value"
        style="margin-top: 16px; justify-content: flex-end"
        @current-change="list.goToPage"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * MyLeadWorkpapers — 我的主编底稿（Req 11.12/11.13）
 *
 * Feature: procedure-delegation-visibility-isolation · Task 12（组件 C16）。
 * 与「我的程序任务」（assignee/reviewer）为两个独立身份视图（Req 11.11：不合成主编项）。
 * 仅消费服务端分页 envelope（listMyLeadWorkpapers）；状态拆分 index/file；
 * nullable wp 显示「底稿尚未生成」并禁用文件动作；404 统一占位不闪现缓存。
 */
import { watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtEmpty from '@/components/common/GtEmpty.vue'
import { listMyLeadWorkpapers, downloadWorkpaper, type VisibilityWpItem } from '@/services/workpaperApi'
import { useVisibilityWorkpaperList } from '@/composables/useVisibilityWorkpaperList'
import { isExternalNotFound, EXTERNAL_NOT_FOUND_MESSAGE } from '@/utils/visibilityAccess'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{ projectId: string }>()
const router = useRouter()

const list = useVisibilityWorkpaperList(listMyLeadWorkpapers, () => props.projectId, { pageSize: 20, sort: 'wp_code' })

// 索引层状态标签（WpIndex.status）
const INDEX_STATUS_LABELS: Record<string, string> = {
  not_started: '未开始', in_progress: '进行中', completed: '已完成', archived: '已归档',
}
function indexStatusLabel(s: string | null): string {
  if (!s) return '—'
  return INDEX_STATUS_LABELS[s] || s
}

// 文件层状态标签（WorkingPaper.status）
const FILE_STATUS_LABELS: Record<string, string> = {
  draft: '待编', in_progress: '编制中', edit_complete: '已完成',
  pending_review: '待复核', reviewed: '已复核', approved: '已通过',
  review_passed: '复核通过', archived: '已归档', not_generated: '尚未生成',
}
function fileStatusLabel(s: string | null): string {
  if (!s) return '—'
  return FILE_STATUS_LABELS[s] || s
}
function fileStatusType(s: string | null): string {
  switch (s) {
    case 'reviewed': case 'approved': case 'review_passed': return 'success'
    case 'pending_review': return 'warning'
    case 'edit_complete': return 'primary'
    default: return 'info'
  }
}

function openWorkpaper(row: VisibilityWpItem) {
  // 深链只定位；服务端 gate 独立判定，前端不授权（Req 12.9）
  if (!list.canOpen(row)) return
  router.push({
    path: `/projects/${row.project_id}/workpapers/${row.wp_id}/edit`,
  })
}

async function download(row: VisibilityWpItem) {
  if (!list.canOpen(row) || !row.wp_id) return
  try {
    await downloadWorkpaper(row.project_id, row.wp_id)
  } catch (e: any) {
    // 拒绝：统一占位（不透出内部原因），并刷新可见集清理缓存
    if (isExternalNotFound(e)) {
      ElMessage.warning(EXTERNAL_NOT_FOUND_MESSAGE)
      list.reload()
    } else {
      handleApiError(e, '下载底稿')
    }
  }
}

async function safeLoad() {
  try {
    await list.load()
  } catch (e: any) {
    handleApiError(e, '加载主编底稿')
  }
}

watch(() => props.projectId, () => { if (props.projectId) safeLoad() })
onMounted(() => { if (props.projectId) safeLoad() })

defineExpose({ list, reload: () => list.reload() })
</script>

<style scoped>
.gt-my-lead { padding: 0; }
.gt-my-lead__stats {
  display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px;
  font-size: 13px; color: var(--gt-color-text-secondary);
}
.gt-my-lead__stat b { color: var(--gt-color-primary); margin-left: 2px; }
.gt-my-lead__disabled { color: var(--gt-color-text-placeholder); font-size: 12px; }
</style>
