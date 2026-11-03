<template>
  <span class="gt-diff-row-ev">
    <RowEvidenceEye :wp-id="wpId" :project-id="projectId" :sheet-key="sheetKey" :cell-ref="cellRef" />
    <el-popover v-if="!readonly" placement="left" trigger="click" :width="360">
      <template #reference>
        <el-button
          link
          size="small"
          class="gt-diff-row-ev__clip"
          title="上传 / 移除本行调节依据"
          aria-label="管理本行调节依据附件"
          data-testid="diff-row-attach"
        >📎</el-button>
      </template>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        :sheet-key="sheetKey"
        :cell-ref="cellRef"
        evidence-type="support"
      />
    </el-popover>
  </span>
</template>

<script setup lang="ts">
/**
 * 差异调节表行内的调节依据附件（spec attachment-confirmation-evidence-loop 需求 4）
 *
 * 小眼睛任何状态下都显示本行附件；编辑态「📎」弹出本行附件清单（上传 / 预览 / 只移除本行链接）。
 * 位置：表页 = 本循环差异调节表编码（如 `D0-4`），单元格 = `row:{行 id}`。
 */
import { computed } from 'vue'
import RowEvidenceEye from '@/components/attachment/RowEvidenceEye.vue'
import { rowEvidenceCell } from '@/components/attachment/rowEvidence'
import ItemAttachment from '../../ItemAttachment.vue'

const props = withDefaults(
  defineProps<{
    wpId: string
    projectId: string
    sheetKey: string
    rowId: string
    readonly?: boolean
  }>(),
  { readonly: false },
)

const cellRef = computed(() => rowEvidenceCell(props.rowId))
</script>

<style scoped>
.gt-diff-row-ev {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.el-button.gt-diff-row-ev__clip {
  padding: 0 2px;
  min-height: auto;
}
</style>
