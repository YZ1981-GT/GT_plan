<script setup lang="ts">
/**
 * GtChecklistSection — 核对表右侧主体（展示型子组件）
 *
 * 从 GtChecklistTable.vue 抽出（spec workpaper-frontend-large-component-split, Req 2）：
 * 右侧「章节标题 + 表头 + 条目列表(header/actionable/children) + 空态」整块展示 DOM 与样式。
 *
 * 铁律：行为零变更、markup/class 逐字不变。主组件公开 props/emit 契约不受影响；
 *       本子组件为内部展示组件，以「函数 props 下行（读取/回调）」透传主组件 composable 方法，
 *       保持模板表达式与原文逐字一致、响应式不破。activeCell 为纯 UI 编辑态，仅本块使用，下沉到子组件。
 */
import { ref } from 'vue'
import type { ChecklistSection, ChecklistItem, ResponseData, ReviewSignHint } from './checklistTypes'

const props = defineProps<{
  currentSection: ChecklistSection | null
  filteredCurrentItems: ChecklistItem[]
  sectionApplicable: boolean
  readonly: boolean
  getResponse: (itemId: string) => ResponseData
  getConclusionClass: (conclusion: string | null) => string
  signHintForItem: (item: ChecklistItem) => ReviewSignHint | null | undefined
  isExpanded: (itemId: string) => boolean
  toggleExpand: (itemId: string) => void
  updateConclusion: (itemId: string, value: string | null) => void
  updateRemark: (itemId: string, value: string) => void
  updateWpRef: (itemId: string, value: string) => void
  applySignHint: (itemId: string, hint: ReviewSignHint) => void
}>()

// ─── Active cell state (click-to-activate editing) ───
const activeCell = ref('')

function activateCell(itemId: string, field: string) {
  if (props.readonly) return
  activeCell.value = `${itemId}:${field}`
}
</script>

<template>
  <!-- 右侧核对表主体 -->
  <div class="gt-checklist-table__main">
    <template v-if="currentSection">
      <!-- 章节标题 -->
      <div class="gt-checklist-table__section-header">
        <span>§ {{ currentSection.title }}</span>
        <el-tag
          v-if="!sectionApplicable"
          type="info"
          size="small"
        >
          不适用
        </el-tag>
      </div>

      <!-- 表头 -->
      <div class="gt-checklist-table__table-header">
        <div class="col-ref">准则索引号</div>
        <div class="col-content">核对条目</div>
        <div class="col-conclusion">适用</div>
        <div class="col-remark">备注</div>
        <div class="col-wpref">底稿索引</div>
      </div>

      <!-- 条目列表 -->
      <div
        class="gt-checklist-table__items"
        :class="{ 'is-inapplicable-section': !sectionApplicable }"
      >
        <template v-for="item in filteredCurrentItems" :key="item.id">
          <!-- 小节标题 (header) -->
          <div v-if="item.type === 'header'" class="gt-checklist-table__header-row">
            <span class="header-row__text">{{ item.content }}</span>
          </div>

          <!-- 主条目 (actionable) -->
          <div
            v-else-if="item.type === 'actionable'"
            class="gt-checklist-table__item-row"
            :class="getConclusionClass(getResponse(item.id).conclusion)"
          >
            <div class="col-ref">
              <span class="item-ref__text">{{ item.standard_ref }}</span>
            </div>
            <div class="col-content">
              <div class="item-content__wrapper">
                <span
                  v-if="item.children && item.children.length > 0"
                  class="item-content__expand"
                  @click="toggleExpand(item.id)"
                >
                  {{ isExpanded(item.id) ? '▼' : '▶' }}
                </span>
                <span class="item-content__text">{{ item.content }}</span>
                <div
                  v-if="signHintForItem(item)?.reason"
                  class="item-sign-hint"
                >
                  <el-tag size="small" type="info">{{ signHintForItem(item)!.reason }}</el-tag>
                  <el-button
                    v-if="signHintForItem(item)?.suggested_conclusion && !readonly"
                    link
                    type="primary"
                    size="small"
                    @click="applySignHint(item.id, signHintForItem(item)!)"
                  >
                    应用建议 {{ signHintForItem(item)!.suggested_conclusion }}
                  </el-button>
                </div>
              </div>
            </div>
            <div class="col-conclusion" @click.stop="activateCell(item.id, 'conclusion')">
              <el-select
                v-if="activeCell === `${item.id}:conclusion`"
                :model-value="getResponse(item.id).conclusion || ''"
                placeholder="—"
                size="small"
                :disabled="readonly"
                automatic-dropdown
                @change="(val: string) => { updateConclusion(item.id, val || null); activeCell = '' }"
                @visible-change="(visible: boolean) => { if (!visible) activeCell = '' }"
              >
                <el-option label="Y" value="Y">
                  <el-tooltip content="适用并已在财务报表中披露" placement="left" :show-after="300">
                    <span>Y</span>
                  </el-tooltip>
                </el-option>
                <el-option label="X/I" value="X/I">
                  <el-tooltip content="适用但不重大，未在财务报表中披露" placement="left" :show-after="300">
                    <span>X/I</span>
                  </el-tooltip>
                </el-option>
                <el-option label="X/W" value="X/W">
                  <el-tooltip content="适用且重大，未在报表中披露，已在另附工作底稿说明原因" placement="left" :show-after="300">
                    <span>X/W</span>
                  </el-tooltip>
                </el-option>
                <el-option label="N/A" value="N/A">
                  <el-tooltip content="不适用于被审计单位财务报表" placement="left" :show-after="300">
                    <span>N/A</span>
                  </el-tooltip>
                </el-option>
              </el-select>
              <span v-else class="cell-display cell-conclusion" :class="{ 'cell-empty': !getResponse(item.id).conclusion }">
                {{ getResponse(item.id).conclusion || '—' }}
              </span>
            </div>
            <div class="col-remark" @click.stop="activateCell(item.id, 'remark')">
              <el-input
                v-if="activeCell === `${item.id}:remark`"
                :model-value="getResponse(item.id).remark || ''"
                size="small"
                placeholder="备注"
                :disabled="readonly"
                @change="(val: string) => updateRemark(item.id, val)"
                @blur="activeCell = ''"
              />
              <span v-else class="cell-display" :class="{ 'cell-empty': !getResponse(item.id).remark }">
                {{ getResponse(item.id).remark || '备注' }}
              </span>
            </div>
            <div class="col-wpref" @click.stop="activateCell(item.id, 'wpref')">
              <el-input
                v-if="activeCell === `${item.id}:wpref`"
                :model-value="getResponse(item.id).wp_ref || ''"
                size="small"
                placeholder="索引"
                :disabled="readonly"
                @change="(val: string) => updateWpRef(item.id, val)"
                @blur="activeCell = ''"
              />
              <span v-else class="cell-display" :class="{ 'cell-empty': !getResponse(item.id).wp_ref }">
                {{ getResponse(item.id).wp_ref || '索引' }}
              </span>
            </div>
          </div>

          <!-- 提示性子项 (children of actionable, collapsed by default) -->
          <div
            v-if="item.type === 'actionable' && item.children && item.children.length > 0 && isExpanded(item.id)"
            class="gt-checklist-table__children"
          >
            <div
              v-for="child in item.children"
              :key="child.id"
              class="gt-checklist-table__child-row"
            >
              <div class="col-ref child-ref">{{ child.standard_ref }}</div>
              <div class="col-content child-content">{{ child.content }}</div>
              <div class="col-conclusion" />
              <div class="col-remark" />
              <div class="col-wpref" />
            </div>
          </div>
        </template>
      </div>
    </template>

    <div v-else class="gt-checklist-table__empty">
      <p>请从左侧目录选择一个章节</p>
    </div>
  </div>
</template>

<style scoped>
/* ─── Main content area ─── */
.gt-checklist-table__main {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.gt-checklist-table__section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--gt-font-size-lg);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--gt-color-primary);
}

/* ─── Table header ─── */
.gt-checklist-table__table-header {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 2px solid var(--gt-color-border);
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  position: sticky;
  top: 0;
  background: var(--gt-color-bg-white);
  z-index: 1;
}

/* ─── Column widths ─── */
.col-ref { width: 100px; min-width: 100px; padding: 0 8px; }
.col-content { flex: 1; padding: 0 8px; }
.col-conclusion { width: 80px; min-width: 80px; padding: 0 4px; }
.col-remark { width: 140px; min-width: 140px; padding: 0 4px; }
.col-wpref { width: 90px; min-width: 90px; padding: 0 4px; }

/* ─── Items container ─── */
.gt-checklist-table__items {
  /* items styling */
}

.gt-checklist-table__items.is-inapplicable-section {
  opacity: 0.5;
  pointer-events: none;
}

/* ─── Header row (section subtitle) ─── */
.gt-checklist-table__header-row {
  padding: 10px 8px;
  font-weight: 700;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  border-bottom: 1px solid var(--gt-color-border-light);
  background: var(--gt-bg-subtle);
}

.header-row__text {
  padding-left: 108px; /* align with content column */
}

/* ─── Actionable item row ─── */
.gt-checklist-table__item-row {
  display: flex;
  align-items: flex-start;
  padding: 6px 0;
  border-bottom: 1px solid var(--gt-color-border-lighter);
  transition: background var(--gt-transition-fast);
}

.gt-checklist-table__item-row:hover {
  background: var(--gt-color-bg-purple-hover);
}

/* Color coding */
.gt-checklist-table__item-row.conclusion-yes {
  background: #e6f7e6;
}
.gt-checklist-table__item-row.conclusion-xi {
  background: #fff8e6;
}
.gt-checklist-table__item-row.conclusion-xw {
  background: #fde8e8;
}
.gt-checklist-table__item-row.conclusion-na {
  background: #f5f5f5;
}

.item-ref__text {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.4;
  word-break: break-all;
}

.item-content__wrapper {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.item-content__expand {
  cursor: pointer;
  color: var(--gt-color-primary);
  font-size: 11px;
  margin-top: 2px;
  user-select: none;
  flex-shrink: 0;
}

.item-content__text {
  font-size: var(--gt-font-size-sm);
  line-height: 1.5;
  color: var(--gt-color-text);
}

.item-sign-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}

/* ─── Children (guidance sub-items) ─── */
.gt-checklist-table__children {
  padding-left: 108px; /* align under content column */
  padding-bottom: 4px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
}

.gt-checklist-table__child-row {
  display: flex;
  align-items: flex-start;
  padding: 4px 8px;
  background: var(--gt-bg-subtle);
  border-left: 3px solid var(--gt-color-border-purple-light);
  margin: 2px 0;
  border-radius: 0 var(--gt-radius-xs) var(--gt-radius-xs) 0;
}

.child-ref {
  width: 80px;
  min-width: 80px;
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
}

.child-content {
  flex: 1;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.5;
}

/* ─── Empty state ─── */
.gt-checklist-table__empty {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  color: var(--gt-color-text-tertiary);
}

/* ─── Override Element Plus select width ─── */
.col-conclusion :deep(.el-select) {
  width: 100%;
}

.col-remark :deep(.el-input) {
  width: 100%;
}

.col-wpref :deep(.el-input) {
  width: 100%;
}

/* ─── Click-to-activate cell display ─── */
.cell-display {
  display: block;
  padding: 2px 6px;
  min-height: 22px;
  line-height: 20px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text);
  cursor: pointer;
  border: 1px dashed transparent;
  border-radius: var(--gt-radius-xs);
  transition: border-color var(--gt-transition-fast);
}

.cell-display:hover {
  border-color: var(--gt-color-border-purple-light);
}

.cell-display.cell-empty {
  color: var(--gt-color-text-tertiary);
}

.cell-conclusion {
  text-align: center;
  font-weight: 500;
}
</style>
