<template>
  <span class="gt-alt-row-ev">
    <el-button
      v-if="!readonly"
      link
      size="small"
      class="gt-alt-row-ev__clip"
      title="上传本行单据（可按单据类型识别后填入本行空白列）"
      aria-label="上传本行单据"
      data-testid="alt-row-upload"
      @click="openDialog"
    >📎</el-button>
    <RowEvidenceEye :wp-id="wpId" :project-id="projectId" :sheet-key="sheetKey" :cell-ref="cellRef" />
    <AlternativeDocOcrDialog
      v-if="mounted"
      v-model="dialogOpen"
      :target="target"
      :columns="columns"
      :row="row"
      @fill="(patch) => emit('fill', patch)"
    />
  </span>
</template>

<script setup lang="ts">
/**
 * 替代程序检查表的行内附件（spec attachment-confirmation-evidence-loop 需求 3.1，ADR-ACE-03）
 *
 * 编辑态「📎」打开单据识别弹窗；小眼睛任何状态下都显示本行附件（复核人只读也能看）。
 * 弹窗第一次打开才挂载（一个检查表几十行，不预建几十个弹窗）。
 */
import { computed, ref } from 'vue'
import RowEvidenceEye from '@/components/attachment/RowEvidenceEye.vue'
import { rowEvidenceCell, useRowEvidence } from '@/components/attachment/rowEvidence'
import AlternativeDocOcrDialog from './AlternativeDocOcrDialog.vue'
import type { AltColumn } from './alternativeDocMapping'
import type { AltRowTarget } from './alternativeDocOcr'

const props = withDefaults(
  defineProps<{
    wpId: string
    projectId?: string | null
    sheetKey: string
    rowId: string
    columns: AltColumn[]
    row: Record<string, unknown>
    readonly?: boolean
  }>(),
  { projectId: null, readonly: false },
)

const emit = defineEmits<{ (e: 'fill', patch: Record<string, string | number>): void }>()

const rowEv = useRowEvidence(() => props.wpId, () => props.projectId)
const cellRef = computed(() => rowEvidenceCell(props.rowId))
const target = computed<AltRowTarget>(() => ({
  projectId: rowEv.projectId(),
  wpId: props.wpId,
  sheetKey: props.sheetKey,
  rowId: props.rowId,
}))

const mounted = ref(false)
const dialogOpen = ref(false)

function openDialog() {
  mounted.value = true
  dialogOpen.value = true
}
</script>

<style scoped>
.gt-alt-row-ev {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.el-button.gt-alt-row-ev__clip {
  padding: 0 2px;
  min-height: auto;
}
</style>
