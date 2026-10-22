<!--
  GtRowNameAlignmentTag.vue — 行名对齐状态标识 + 溯源 + 直达入口
  spec: formula-row-name-alignment-confirmation Task 10；formula-governance-coverage-closure R4 接入对齐弹窗

  match_state 四态的文案 / 颜色只在这里定义一份（对齐弹窗的行列表也用它，不再各写一份）。
  - unmatched / ambiguous：可见 tag（禁止静默显示 0）；行内用法点击直达对齐弹窗并定位本行
  - user_confirmed：可溯源（hover 显示映射到哪些账套明细名、谁何时确认）+「重新确认」入口
  - auto_matched：轻量标识
  in-dialog：已经在对齐弹窗里 —— 不再发「打开弹窗」事件（会把弹窗里没确认的勾选清空），
  「重新确认」改为 emit select(row_key) 让弹窗激活这一行；其余点击由弹窗的行点击处理。
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
        <el-tag size="small" type="success" effect="light" class="gt-rnat__tag" data-state="user_confirmed">
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
        <el-button size="small" text type="primary" data-testid="rnat-reconfirm" @click="onReconfirm">重新确认</el-button>
      </div>
    </el-popover>

    <!-- 未匹配 / 待确认：可见 tag + 点击直达 -->
    <el-tag
      v-else-if="row.match_state === 'unmatched'"
      size="small"
      type="danger"
      effect="light"
      class="gt-rnat__tag"
      :class="{ 'gt-rnat__tag--click': !inDialog }"
      data-state="unmatched"
      :title="row.stale_reason || (inDialog ? '账套明细名没对上，在右侧勾选对应明细'
        : '此行取不到数是因为账套明细名没对上，点击确认对应关系')"
      @click="onTagClick"
    >
      {{ inDialog ? '未匹配' : '未匹配 · 去对齐' }}
    </el-tag>

    <el-tag
      v-else-if="row.match_state === 'ambiguous'"
      size="small"
      type="warning"
      effect="light"
      class="gt-rnat__tag"
      :class="{ 'gt-rnat__tag--click': !inDialog }"
      data-state="ambiguous"
      :title="inDialog ? '有多个候选账套明细，在右侧勾选确认' : '有多个候选账套明细，需人工确认'"
      @click="onTagClick"
    >
      {{ inDialog ? '待确认（多候选）' : '待确认 · 多候选' }}
    </el-tag>

    <!-- 自动匹配：轻量提示 -->
    <el-tag
      v-else-if="row.match_state === 'auto_matched'"
      size="small"
      type="info"
      effect="plain"
      class="gt-rnat__tag"
      data-state="auto_matched"
      title="按名称自动匹配"
    >
      自动匹配
    </el-tag>

    <!-- 后端新增了状态而这里没跟上：照实显示，不藏 -->
    <el-tag v-else-if="row.match_state" size="small" type="info" effect="plain" class="gt-rnat__tag">
      {{ row.match_state }}
    </el-tag>
  </span>
</template>

<script setup lang="ts">
import { eventBus, type RowNameAlignmentRowWire } from '@/utils/eventBus'

const props = withDefaults(defineProps<{
  row: RowNameAlignmentRowWire
  /** 在对齐弹窗里使用（见文件头） */
  inDialog?: boolean
  /** 行内用法：直达弹窗所需上下文（与刷新入口一致）；弹窗内不用 */
  wpId?: string
  projectId?: string
  year?: number
  wpCode?: string
  sheetCode?: string
  datasetId?: string | null
  /** 行内用法：同 sheet 的全部行 wire（点击直达时把整表带给弹窗，定位到本行） */
  allRows?: RowNameAlignmentRowWire[]
}>(), {
  inDialog: false, wpId: '', projectId: '', year: 0, wpCode: '', sheetCode: '', datasetId: null,
  allRows: () => [],
})

const emit = defineEmits<{ select: [rowKey: string] }>()

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

function onTagClick() {
  if (!props.inDialog) emitJump()
}

function onReconfirm() {
  if (props.inDialog) emit('select', props.row.row_key)
  else emitJump()
}

/** 行内用法：打开对齐弹窗（携带整表，弹窗默认激活本行）。缺上下文时不发（打开的弹窗会是空的）。 */
function emitJump() {
  if (!props.wpId || !props.sheetCode) return
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
