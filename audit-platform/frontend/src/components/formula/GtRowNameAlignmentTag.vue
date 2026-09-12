<!--
  GtRowNameAlignmentTag.vue — 行内名称对齐状态标识 + 溯源 + 直达入口
  spec: formula-row-name-alignment-confirmation Task 10

  可复用行内组件：底稿子组件在「按行名取数」的行上放它显示 match_state。
  - unmatched / ambiguous：可见 tag（中文文案）+ 点击直达弹窗对应行（禁止静默显示 0）
  - user_confirmed：可溯源（hover 显示映射到哪些账套明细名、谁何时确认）+「重新确认」入口
  - auto_matched：轻量成功标识
-->
<template>
  <span class="gt-rnat">
    <!-- 已确认：溯源 popover + 重新确认 -->
    <el-popover
      v-if="row.match_state === 'user_confirmed'"
      placement="top"
      :width="320"
      trigger="hover"
    >
      <template #reference>
        <el-tag size="small" type="success" effect="light" class="gt-rnat__tag">
          已确认
        </el-tag>
      </template>
      <div class="gt-rnat__trace">
        <div class="gt-rnat__trace-title">映射到账套明细：</div>
        <ul class="gt-rnat__trace-list">
          <li v-for="t in row.target_identity" :key="t.dimension_key">
            {{ t.aux_name }}
            <span v-if="t.aux_type" class="gt-rnat__dim">（{{ t.aux_type }}）</span>
          </li>
        </ul>
        <div class="gt-rnat__trace-meta">
          <span v-if="row.confirmed_by">确认人：{{ row.confirmed_by }}</span>
          <span v-if="row.confirmed_at">· {{ formatTime(row.confirmed_at) }}</span>
          <span v-if="row.mapping_version"> · v{{ row.mapping_version }}</span>
        </div>
        <el-button size="small" text type="primary" @click="emitJump">重新确认</el-button>
      </div>
    </el-popover>

    <!-- 未匹配 / 待确认：可见 tag + 点击直达 -->
    <el-tag
      v-else-if="row.match_state === 'unmatched'"
      size="small"
      type="danger"
      effect="light"
      class="gt-rnat__tag gt-rnat__tag--click"
      :title="row.stale_reason || '此行取不到数是因为账套明细名没对上，点击确认对应关系'"
      @click="emitJump"
    >
      未匹配 · 去对齐
    </el-tag>

    <el-tag
      v-else-if="row.match_state === 'ambiguous'"
      size="small"
      type="warning"
      effect="light"
      class="gt-rnat__tag gt-rnat__tag--click"
      title="有多个候选账套明细，需人工确认"
      @click="emitJump"
    >
      待确认 · 多候选
    </el-tag>

    <!-- 自动匹配：轻量提示 -->
    <el-tag
      v-else-if="row.match_state === 'auto_matched'"
      size="small"
      type="info"
      effect="plain"
      class="gt-rnat__tag"
      title="按名称自动匹配"
    >
      自动匹配
    </el-tag>
  </span>
</template>

<script setup lang="ts">
import { eventBus, type RowNameAlignmentRowWire } from '@/utils/eventBus'

const props = defineProps<{
  row: RowNameAlignmentRowWire
  /** 直达弹窗所需上下文（与刷新入口一致）。 */
  wpId: string
  projectId: string
  year: number
  wpCode: string
  sheetCode: string
  datasetId?: string | null
  /** 同 sheet 的全部行 wire（点击直达时把整表带给弹窗，定位到本行）。 */
  allRows: RowNameAlignmentRowWire[]
}>()

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

/** 点击 → 打开对齐弹窗（携带整表，弹窗默认激活本行）。 */
function emitJump() {
  eventBus.emit('open-row-name-alignment', {
    wpId: props.wpId,
    projectId: props.projectId,
    year: props.year,
    wpCode: props.wpCode,
    sheetCode: props.sheetCode,
    datasetId: props.datasetId ?? null,
    rows: props.allRows,
  })
}
</script>

<style scoped>
.gt-rnat {
  display: inline-flex;
  align-items: center;
}
.gt-rnat__tag--click {
  cursor: pointer;
}
.gt-rnat__trace-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}
.gt-rnat__trace-list {
  margin: 0 0 6px 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
}
.gt-rnat__dim {
  color: var(--gt-color-text-secondary, #909399);
}
.gt-rnat__trace-meta {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
  margin-bottom: 6px;
}
</style>
