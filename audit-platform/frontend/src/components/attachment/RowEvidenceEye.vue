<template>
  <!-- 外层恒为 span：多份时的按钮若直接挨着宿主的按钮，会吃到 `.el-button + .el-button` 的 12px 间距、在窄列里换行 -->
  <span v-if="rows.length" class="gt-row-eye" data-testid="row-evidence-eye">
    <AttachmentEyeButton
      v-if="rows.length === 1"
      :attachment-id="rows[0].attachment_id"
      :file-name="rows[0].attachment.file_name"
      :file-type="rows[0].attachment.file_type"
      :ocr-status="rows[0].attachment.ocr_status"
    />
    <el-popover
      v-else
      placement="bottom"
      trigger="click"
      :width="280"
    >
      <template #reference>
        <el-button
          class="gt-row-eye__multi"
          link
          type="primary"
          size="small"
          :aria-label="`本行附件 ${rows.length} 份，点开逐个预览`"
          @click.stop
        >
          <el-icon><View /></el-icon>
          <span class="gt-row-eye__count">{{ rows.length }}</span>
        </el-button>
      </template>
      <ul class="gt-row-eye__list">
        <li v-for="row in rows" :key="row.id" class="gt-row-eye__item">
          <span class="gt-row-eye__name" :title="row.attachment.file_name">{{ row.attachment.file_name }}</span>
          <AttachmentEyeButton
            :attachment-id="row.attachment_id"
            :file-name="row.attachment.file_name"
            :file-type="row.attachment.file_type"
            :ocr-status="row.attachment.ocr_status"
          />
        </li>
      </ul>
    </el-popover>
  </span>
</template>

<script setup lang="ts">
/**
 * RowEvidenceEye — 行内附件的小眼睛（spec attachment-inline-preview ADR-AIP-03）
 *
 * 按位置（表页 + 行槽位）从本底稿共享链接仓取本行附件：0 份不显示，1 份显示小眼睛，多份显示「👁 n」点开列表。
 * 同一底稿上所有实例共用一次列表请求（useWpEvidenceLinks 单飞）。项目 id 缺省取路由参数。
 */
import { computed } from 'vue'
import { View } from '@element-plus/icons-vue'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
import { routeProjectId } from '@/components/attachment/rowEvidence'
import { useWpEvidenceLinks } from '@/composables/useWpEvidenceLinks'

const props = withDefaults(
  defineProps<{
    wpId: string
    sheetKey: string
    /** 行槽位（`row:{id}` / `item:{n}`）；不传 = 表页级（只按表页匹配单元格为空的链接） */
    cellRef?: string | null
    projectId?: string | null
  }>(),
  { cellRef: null, projectId: null },
)

const fallbackProjectId = routeProjectId()
const store = useWpEvidenceLinks(() => props.projectId || fallbackProjectId, () => props.wpId)
const rows = computed(() => (props.sheetKey ? store.linksAt(props.sheetKey, props.cellRef || null) : []))
</script>

<style scoped>
.gt-row-eye {
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
  margin-left: 2px;
}
.el-button.gt-row-eye__multi {
  padding: 0 2px;
  min-height: auto;
}
/* 盖掉 Element Plus 按钮里「图标 + 文字」的 6px 间距，份数紧贴图标，窄列里不换行 */
.gt-row-eye__multi .gt-row-eye__count {
  margin-left: 1px;
  font-size: 11px;
}
.gt-row-eye__list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
}
.gt-row-eye__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 12px;
}
.gt-row-eye__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
