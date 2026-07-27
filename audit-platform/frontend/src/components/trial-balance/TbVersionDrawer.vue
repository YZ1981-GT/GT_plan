<template>
  <el-drawer :model-value="visible" title="⏱ 试算表版本历史" size="520" :append-to-body="true" @close="$emit('close')" @update:model-value="!$event && $emit('close')">
    <!-- 版本时间线 -->
    <div v-if="loading" v-loading="true" style="height:200px"></div>
    <el-empty v-else-if="!versions.length" description="暂无版本快照（重算或保存后自动生成）" />
    <el-timeline v-else>
      <el-timeline-item
        v-for="v in versions" :key="v.version_no"
        :timestamp="formatTime(v.created_at)"
        placement="top"
        :type="v.trigger === 'restore' ? 'danger' : v.trigger === 'recalc' ? 'primary' : 'info'"
      >
        <div class="gt-tb-ver-item" :class="{ 'gt-tb-ver-item--active': selectedVersion === v.version_no }" @click="selectVersion(v.version_no)">
          <div class="gt-tb-ver-item__header">
            <span class="gt-tb-ver-item__trigger">{{ triggerLabel(v.trigger) }}</span>
            <el-tag size="small" type="info">v{{ v.version_no }}</el-tag>
            <span v-if="v.row_count" class="gt-tb-ver-item__meta">{{ v.row_count }} 行</span>
          </div>
          <div class="gt-tb-ver-item__hash" :title="v.content_hash">{{ v.content_hash?.slice(0, 8) }}</div>
        </div>
      </el-timeline-item>
    </el-timeline>

    <!-- 版本详情 -->
    <template v-if="detail">
      <el-divider>版本 v{{ detail.version_no }} 详情</el-divider>
      <el-table :data="detailTableRows" size="small" border height="360" style="width:100%" class="gt-tb-ver-table">
        <el-table-column prop="row_code" label="行次" width="80" v-if="detailIsSummaryMode" />
        <el-table-column prop="standard_account_code" label="科目" width="100" v-else />
        <el-table-column prop="row_name" label="项目" min-width="140" v-if="detailIsSummaryMode" />
        <el-table-column prop="account_name" label="科目名称" min-width="140" v-else />
        <el-table-column label="审定数" width="140" align="right">
          <template #default="{ row }">
            <span class="gt-tb-ver-amt">{{ fmtAmt(row.audited || row.audited_amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:12px;text-align:right">
        <el-button size="small" @click="detail = null">关闭详情</el-button>
        <el-popconfirm title="恢复此版本将创建当前状态的快照后覆盖，确定？" @confirm="doRestore(detail.version_no)">
          <template #reference>
            <el-button size="small" type="warning">恢复此版本</el-button>
          </template>
        </el-popconfirm>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{ projectId: string; year: number; visible: boolean }>()
const emit = defineEmits<{ close: []; restored: [] }>()

const displayPrefs = useDisplayPrefsStore()
const fmtAmt = (v: any) => displayPrefs.fmtAmount(v)

// 版本详情表格数据：优先 summary_rows（有长度），否则 detail_rows；过滤零/空+按科目码排序
const detailTableRows = computed(() => {
  const snap = detail.value?.snapshot_data
  if (!snap) return []
  const summary = snap.summary_rows
  if (Array.isArray(summary) && summary.length > 0) return summary
  const rows = snap.detail_rows || []
  return rows
    .filter((r: any) => {
      const amt = Number(r.audited_amount ?? r.audited ?? 0)
      return amt !== 0 && r.standard_account_code
    })
    .sort((a: any, b: any) => (a.standard_account_code || '').localeCompare(b.standard_account_code || ''))
})
const detailIsSummaryMode = computed(() => {
  const snap = detail.value?.snapshot_data
  return Array.isArray(snap?.summary_rows) && snap.summary_rows.length > 0
})

const loading = ref(false)
const versions = ref<any[]>([])
const selectedVersion = ref<number | null>(null)
const detail = ref<any>(null)

watch(() => props.visible, async (v) => {
  if (v) await loadVersions()
})

async function loadVersions() {
  loading.value = true
  try {
    const { data } = await http.get(`/api/projects/${props.projectId}/trial-balance/snapshots`, { params: { year: props.year } })
    versions.value = Array.isArray(data) ? data : []
  } catch { versions.value = [] }
  finally { loading.value = false }
}

async function selectVersion(vno: number) {
  selectedVersion.value = vno
  try {
    const { data } = await http.get(`/api/projects/${props.projectId}/trial-balance/snapshots/${vno}`, { params: { year: props.year } })
    detail.value = data?.data || data
  } catch { detail.value = null }
}

async function doRestore(vno: number) {
  try {
    await http.post(`/api/projects/${props.projectId}/trial-balance/snapshots/${vno}/restore`, null, { params: { year: props.year } })
    ElMessage.success('已恢复到 v' + vno + '，当前状态已保存为新快照')
    emit('restored')
    await loadVersions()
    detail.value = null
  } catch { ElMessage.error('恢复失败') }
}

function triggerLabel(t: string) {
  const map: Record<string, string> = { recalc: '🔄 重算', manual_save: '💾 保存', import: '📥 导入', adjustment_approved: '✅ 调整批准', restore: '⏪ 恢复' }
  return map[t] || t
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.gt-tb-ver-item { padding: 6px 10px; border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.gt-tb-ver-item:hover { background: #f5f7fa; }
.gt-tb-ver-item--active { background: #ecf5ff; border: 1px solid #b3d8ff; }
.gt-tb-ver-item__header { display: flex; align-items: center; gap: 8px; }
.gt-tb-ver-item__trigger { font-weight: 600; font-size: 13px; }
.gt-tb-ver-item__meta { font-size: 11px; color: #909399; }
.gt-tb-ver-item__hash { font-size: 10px; color: #c0c4cc; font-family: monospace; margin-top: 2px; }
.gt-tb-ver-table { font-size: 12px; }
.gt-tb-ver-table :deep(.el-table__header th .cell),
.gt-tb-ver-table :deep(.el-table__body td .cell) { font-size: 12px; padding: 2px 8px; line-height: 16px; }
.gt-tb-ver-table :deep(.el-table__body td) { height: 20px; padding: 0; }
.gt-tb-ver-amt { font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
