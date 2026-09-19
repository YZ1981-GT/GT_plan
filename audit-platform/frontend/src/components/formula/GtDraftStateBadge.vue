<template>
  <el-tooltip :content="tip" placement="top" :show-after="120" :disabled="!tip">
    <el-tag
      :type="tagType"
      :effect="isDraft ? 'plain' : 'light'"
      size="small"
      class="gt-draft-state-badge"
      :class="{ 'gt-draft-state-badge--draft': isDraft }"
      round
    >
      <el-icon class="gt-draft-state-badge__icon"><component :is="iconComp" /></el-icon>
      <span class="gt-draft-state-badge__label">{{ label }}</span>
    </el-tag>
  </el-tooltip>
</template>

<script setup lang="ts">
/**
 * GtDraftStateBadge — 初稿 / 已审定 状态徽标（Req 3.5）
 *
 * 前端按 `draft_marker.state` 区分展示：
 * - `draft`        → "初稿"（草稿态徽标：橙色 + 虚线描边），由一键刷新自动生成、尚未经人工复核。
 * - `human_edited` → "已审定"（正式徽标：绿色），已被人工编辑/复核介入。
 * - `audited`      → "已审定"（正式徽标：绿色）显式审定态。
 * - null/空        → 无 draft 标记，视为人工维护的已审定数据（正式徽标）。
 *
 * 遵循底稿 UI 规范：初稿=草稿态徽标，已审定=正式徽标。
 *
 * 依赖说明：draft 状态查询数据源迁移协调 acnr-consumer-wiring Req 14；本组件按 `state` 数据驱动，
 * 上游查询到的 state 直接传入即可。
 *
 * Requirements: 3.5
 */
import { computed } from 'vue'
import { EditPen, CircleCheck } from '@element-plus/icons-vue'
import { DRAFT_MARKER_STATE, type DraftMarkerState } from '@/constants/statusEnum'

export type DraftState = DraftMarkerState | null | undefined

const props = withDefaults(
  defineProps<{
    /** draft_marker.state；空表示无标记（按已审定展示） */
    state?: DraftState
    /** 覆盖默认"初稿"文案 */
    draftLabel?: string
    /** 覆盖默认"已审定"文案 */
    auditedLabel?: string
  }>(),
  {
    state: null,
    draftLabel: '初稿',
    auditedLabel: '已审定',
  },
)

const isDraft = computed(() => props.state === DRAFT_MARKER_STATE.DRAFT)

const label = computed(() => (isDraft.value ? props.draftLabel : props.auditedLabel))

const tagType = computed<'warning' | 'success'>(() => (isDraft.value ? 'warning' : 'success'))

const iconComp = computed(() => (isDraft.value ? EditPen : CircleCheck))

const tip = computed(() => {
  if (isDraft.value) return '由一键刷新自动生成，尚未经人工复核'
  if (props.state === DRAFT_MARKER_STATE.HUMAN_EDITED) return '已被人工编辑介入'
  if (props.state === DRAFT_MARKER_STATE.AUDITED) return '已审定数据'
  return ''
})
</script>

<style scoped>
.gt-draft-state-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  line-height: 1;
  vertical-align: middle;
}
.gt-draft-state-badge--draft {
  border-style: dashed;
}
.gt-draft-state-badge__icon {
  font-size: 12px;
}
.gt-draft-state-badge__label {
  line-height: 1;
}
</style>
