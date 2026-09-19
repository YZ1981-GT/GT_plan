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
          <span class="version-row__no">v{{ v.version_no }}</span>

          <el-tag size="small" type="info">{{ createdViaLabel(v.created_via) }}</el-tag>

          <!-- 试算表快照短标识：判「这一版按哪份数据生成」的唯一线索 -->
          <el-tooltip
            v-if="shortHash(v.bound_tb_hash)"
            :content="`绑定试算表快照 tb_hash：${v.bound_tb_hash}`"
            placement="top"
          >
            <span class="version-row__hash">快照 {{ shortHash(v.bound_tb_hash) }}</span>
          </el-tooltip>
          <span v-else class="version-row__muted">快照未记录</span>

          <!-- stale 三态：未知不显示徽标（显示"最新"会骗人） -->
          <el-tag v-if="v.is_stale === true" size="small" type="warning">上游已变更</el-tag>
          <el-tag v-else-if="v.is_stale === false" size="small" type="success">与上游一致</el-tag>

          <el-tag v-if="v.drift_blocked" size="small" type="danger">
            {{ v.drift_report?.unavailable ? '差异检测不可用' : '数字与重算不一致' }}
          </el-tag>

          <!--
            编辑时间与版本落库时间（时间轴上的 created_at）通常相近但并非同一事实：
            前者是 OnlyOffice 侧的编辑时刻，后者是回调落库时刻。放 tooltip 里既
            保留这条留痕、又不让行变长（否则 `edited_at` 就是个下发了却没人看的死字段）。
          -->
          <el-tooltip
            v-if="editorText(v)"
            :content="editorTooltip(v)"
            placement="top"
            :show-after="200"
          >
            <span class="version-row__editor">{{ editorText(v) }}</span>
          </el-tooltip>

          <span v-if="v.file_size" class="version-row__muted">{{ formatSize(v.file_size) }}</span>

          <el-button link type="primary" @click="download(v.version_no)">下载</el-button>
        </div>

        <p v-if="v.drift_reason" class="version-row__drift">{{ v.drift_reason }}</p>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup lang="ts">
import { deliverableDownloadUrl } from '@/services/deliverableApi'
import type { DeliverableVersion } from '@/services/deliverableApi'
import { downloadFile } from '@/utils/http'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { createdViaLabel, shortHash } from './deliverableLineageLabels'

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

/**
 * 编辑人展示（需求 11.2）。
 * 🔴 只读 `edited_by_name` —— OO 路径下 `created_by` 只是回调处理占位（NOT NULL 列
 * 无法表达"未知"），拿它当编辑人会让所有在线编辑版本都显示成交付物创建人。
 * 解析不出编辑人时如实显示"编辑人未知"，不回退创建人。
 */
function editorText(v: DeliverableVersion): string {
  if (v.created_via !== 'onlyoffice_edit') return ''
  return v.edited_by_name ? `编辑人 ${v.edited_by_name}` : '编辑人未知'
}

/** 编辑人 tooltip：补上编辑时间；解析不出编辑人时说明为什么是「未知」。 */
function editorTooltip(v: DeliverableVersion): string {
  const who = v.edited_by_name
    ? `编辑人 ${v.edited_by_name}`
    : '回调未携带可识别的编辑人，如实记为未知（不回退交付物创建人）'
  const when = v.edited_at ? `编辑时间 ${formatTime(v.edited_at)}` : '编辑时间未记录'
  return `${who}；${when}`
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
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.version-row__no {
  font-weight: 600;
}

.version-row__hash {
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: help;
  border-bottom: 1px dashed var(--el-border-color);
}

.version-row__editor {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.version-row__muted {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.version-row__drift {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-color-danger);
}
</style>
