<template>
  <div class="fraud-risk-checklist">
    <!-- 顶部编制说明 -->
    <div class="fraud-risk-checklist__top-note">
      <el-alert type="info" :closable="false" show-icon>
        {{ GUIDANCE_NOTES_D08.top_note }}
      </el-alert>
    </div>

    <!-- 工具栏 -->
    <div class="fraud-risk-checklist__toolbar">
      <div class="fraud-risk-checklist__toolbar-left">
        <el-button v-if="!readonly" size="small" type="primary" @click="handleAddItem">
          <el-icon><Plus /></el-icon> 新增自定义条目
        </el-button>
        <el-button v-if="!readonly" size="small" type="warning" plain @click="$emit('auto-fill')">
          <el-icon><MagicStick /></el-icon> 上游联动填充
        </el-button>
      </div>
      <div class="fraud-risk-checklist__toolbar-right">
        <el-button size="small" @click="$emit('import')">导入</el-button>
        <el-button size="small" @click="$emit('export')">导出</el-button>
      </div>
    </div>

    <!-- 分组折叠面板 -->
    <el-collapse v-model="activeGroups" class="fraud-risk-checklist__groups">
      <el-collapse-item
        v-for="group in groupedItems"
        :key="group.key"
        :name="group.key"
      >
        <template #title>
          <div class="fraud-risk-checklist__group-title">
            <span class="fraud-risk-checklist__group-icon">{{ group.icon }}</span>
            <span class="fraud-risk-checklist__group-name">{{ group.label }}</span>
            <el-badge
              v-if="getGroupExistCount(group.key) > 0"
              :value="getGroupExistCount(group.key)"
              type="danger"
              class="fraud-risk-checklist__group-badge"
            />
            <span class="fraud-risk-checklist__group-count">{{ group.items.length }} 条</span>
          </div>
        </template>

        <div class="fraud-risk-checklist__group-items">
          <div
            v-for="item in group.items"
            :key="item._row_id"
            class="fraud-risk-checklist__item"
            :class="{
              'fraud-risk-checklist__item--exist': item.is_exist === '是',
              'fraud-risk-checklist__item--auto': item._auto_filled,
              'fraud-risk-checklist__item--warning': isHighlighted(item) && needsCountermeasure(item),
            }"
          >
            <!-- 行1：序号 + 描述 + badge -->
            <div class="fraud-risk-checklist__item-header">
              <span class="fraud-risk-checklist__item-seq">{{ item.seq }}</span>
              <span v-if="readonly || item._preset" class="fraud-risk-checklist__item-desc">
                {{ item.description }}
              </span>
              <el-input
                v-else
                v-model="item.description"
                size="small"
                placeholder="请输入自定义风险迹象描述"
                @change="handleUpdate(item._row_id!, 'description', item.description)"
              />
              <!-- 上游联动标记 -->
              <el-tag v-if="item._auto_filled" size="small" type="warning" effect="plain" class="fraud-risk-checklist__auto-tag">
                上游联动
              </el-tag>
              <!-- tooltip -->
              <el-tooltip
                v-if="item.tooltip_key && ITEM_TOOLTIPS_D08[item.tooltip_key]"
                :content="ITEM_TOOLTIPS_D08[item.tooltip_key]"
                placement="right"
                :raw-content="true"
                effect="light"
                :popper-style="{ whiteSpace: 'pre-line', maxWidth: '420px' }"
              >
                <el-icon class="fraud-risk-checklist__info-icon"><InfoFilled /></el-icon>
              </el-tooltip>
              <!-- 删除 -->
              <el-button
                v-if="!readonly && !item._preset"
                size="small"
                type="danger"
                text
                @click="handleDelete(item._row_id!)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>

            <!-- 行2：三字段 -->
            <div class="fraud-risk-checklist__item-fields">
              <div class="fraud-risk-checklist__field">
                <span class="fraud-risk-checklist__field-label">是否存在</span>
                <el-select
                  v-if="!readonly"
                  :model-value="item.is_exist"
                  size="small"
                  placeholder="—"
                  style="width: 85px"
                  @change="(val: string) => handleUpdate(item._row_id!, 'is_exist', val)"
                >
                  <el-option v-for="opt in FRAUD_RISK_EXIST_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
                </el-select>
                <span v-else :class="['fraud-risk-checklist__exist-val', item.is_exist === '是' ? 'is-yes' : '']">
                  {{ item.is_exist || '—' }}
                </span>
              </div>
              <div class="fraud-risk-checklist__field">
                <span class="fraud-risk-checklist__field-label fraud-risk-checklist__field-label--tip">相关索引</span>
                <el-input
                  v-if="!readonly"
                  :model-value="item.source_ref"
                  size="small"
                  placeholder="D0-"
                  style="width: 110px"
                  @change="(val: string) => handleUpdate(item._row_id!, 'source_ref', val)"
                />
                <span v-else class="fraud-risk-checklist__ref-link" @click="item.source_ref && $emit('jump-ref', item.source_ref)">
                  {{ item.source_ref || '—' }}
                </span>
              </div>
              <div class="fraud-risk-checklist__field fraud-risk-checklist__field--wide">
                <span class="fraud-risk-checklist__field-label">应对措施</span>
                <el-input
                  v-if="!readonly"
                  :model-value="item.countermeasure"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  size="small"
                  :placeholder="GUIDANCE_NOTES_D08.countermeasure_placeholder"
                  @change="(val: string) => handleUpdate(item._row_id!, 'countermeasure', val)"
                />
                <span v-else class="fraud-risk-checklist__field-value">{{ item.countermeasure || '—' }}</span>
                <el-button
                  v-if="!readonly && !item.countermeasure && getCountermeasurePreset(item.seq)"
                  size="small"
                  type="warning"
                  text
                  class="fraud-risk-checklist__preset-btn"
                  @click="handleFillPreset(item)"
                >
                  推荐
                </el-button>
                <el-icon v-if="isHighlighted(item) && needsCountermeasure(item)" class="fraud-risk-checklist__warn-icon"><Warning /></el-icon>
              </div>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Plus, Delete, InfoFilled, Warning, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FraudRiskRow } from './fraudRiskTypes'
import { ITEM_TOOLTIPS_D08, GUIDANCE_NOTES_D08 } from './fraudRiskPresets'
import { FRAUD_RISK_EXIST_OPTIONS } from './fraudRiskEnums'
import { getCountermeasurePreset } from './countermeasurePresets'

const props = defineProps<{
  items: FraudRiskRow[]
  readonly: boolean
  isHighlighted: (row: FraudRiskRow) => boolean
  needsCountermeasure: (row: FraudRiskRow) => boolean
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', rowId: string): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import'): void
  (e: 'export'): void
  (e: 'jump-ref', ref: string): void
  (e: 'auto-fill'): void
}>()

// ─── 分组定义 ────────────────────────────────────────────────────────────────

interface ItemGroup {
  key: string
  icon: string
  label: string
  seqRange: [number, number] // inclusive
  items: FraudRiskRow[]
}

const RISK_GROUPS = [
  { key: 'control', icon: '🔒', label: '内部控制与管理层', seqRange: [1, 4] as [number, number] },
  { key: 'counterparty', icon: '🏢', label: '被询证方特征', seqRange: [5, 6] as [number, number] },
  { key: 'reply', icon: '📬', label: '回函可靠性与差异', seqRange: [7, 9] as [number, number] },
  { key: 'entity', icon: '🔍', label: '被函证单位异常', seqRange: [10, 11] as [number, number] },
  { key: 'transaction', icon: '💰', label: '交易与收入异常', seqRange: [12, 13] as [number, number] },
  { key: 'statistics', icon: '📊', label: '统计异常与回函率', seqRange: [14, 15] as [number, number] },
  { key: 'other', icon: '⚠️', label: '其他风险因素', seqRange: [16, 19] as [number, number] },
]

const groupedItems = computed<ItemGroup[]>(() => {
  const result: ItemGroup[] = []
  for (const g of RISK_GROUPS) {
    const groupItems = props.items.filter(item => {
      const seq = item.seq ?? 0
      return seq >= g.seqRange[0] && seq <= g.seqRange[1]
    })
    if (groupItems.length > 0) {
      result.push({ ...g, items: groupItems })
    }
  }
  // 自定义条目（seq > 19）归入"其他"
  const customItems = props.items.filter(item => (item.seq ?? 0) > 19)
  if (customItems.length > 0) {
    const otherGroup = result.find(g => g.key === 'other')
    if (otherGroup) {
      otherGroup.items.push(...customItems)
    } else {
      result.push({ key: 'other', icon: '⚠️', label: '其他风险因素', seqRange: [16, 99], items: customItems })
    }
  }
  return result
})

// 默认折叠策略：只展开有"是"标记的组 + "其他"组
const activeGroups = ref<string[]>(computeDefaultActiveGroups())

function computeDefaultActiveGroups(): string[] {
  // 初始全部展开（首次加载无数据时展示完整），后续由 watch 动态调整
  return RISK_GROUPS.map(g => g.key)
}

// 数据加载后自动收起无风险组（仅在有数据时生效）
watch(
  () => props.items.length,
  (len) => {
    if (len === 0) return
    const groupsWithRisk = new Set<string>()
    for (const item of props.items) {
      if (item.is_exist === '是' || item.is_exist === '待核实') {
        const seq = item.seq ?? 0
        for (const g of RISK_GROUPS) {
          if (seq >= g.seqRange[0] && seq <= g.seqRange[1]) {
            groupsWithRisk.add(g.key)
            break
          }
        }
      }
    }
    // 始终展开"其他"组（自定义条目 + 通用风险）
    groupsWithRisk.add('other')
    // 如果没有任何风险标记，全部展开（空态）
    if (groupsWithRisk.size <= 1) return
    activeGroups.value = [...groupsWithRisk]
  },
  { immediate: true }
)

function getGroupExistCount(groupKey: string): number {
  const group = groupedItems.value.find(g => g.key === groupKey)
  if (!group) return 0
  return group.items.filter(item => item.is_exist === '是').length
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAddItem() {
  emit('add')
}

function handleDelete(rowId: string) {
  emit('delete', rowId)
}

function handleUpdate(rowId: string, field: string, value: any) {
  emit('update', rowId, field, value)
}

function handleFillPreset(item: FraudRiskRow) {
  const preset = getCountermeasurePreset(item.seq)
  if (preset && item._row_id) {
    emit('update', item._row_id, 'countermeasure', preset)
    ElMessage.success(`已填入第 ${item.seq} 条推荐应对措施（可修改）`)
  }
}
</script>

<style scoped>
.fraud-risk-checklist__top-note {
  margin-bottom: 12px;
}

.fraud-risk-checklist__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.fraud-risk-checklist__toolbar-left,
.fraud-risk-checklist__toolbar-right {
  display: flex;
  gap: 8px;
}

/* ─── 分组折叠 ───────────────────────────────────────────────────────────── */

.fraud-risk-checklist__groups :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  padding: 0 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.fraud-risk-checklist__group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.fraud-risk-checklist__group-icon {
  font-size: 16px;
}

.fraud-risk-checklist__group-name {
  font-weight: 600;
  font-size: 13px;
}

.fraud-risk-checklist__group-badge {
  margin-left: 4px;
}

.fraud-risk-checklist__group-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
}

/* ─── 检查项 ─────────────────────────────────────────────────────────────── */

.fraud-risk-checklist__group-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
}

.fraud-risk-checklist__item {
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 8px 12px;
  transition: all 0.2s;
}

.fraud-risk-checklist__item--exist {
  border-color: var(--el-color-danger-light-5);
  background: #fef0f0;
}

.fraud-risk-checklist__item--auto {
  border-left: 3px solid var(--el-color-warning);
}

.fraud-risk-checklist__item--warning {
  border-color: var(--el-color-warning);
  background: #fdf6ec;
}

.fraud-risk-checklist__item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.fraud-risk-checklist__item-seq {
  font-weight: 700;
  font-size: 13px;
  min-width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.fraud-risk-checklist__item--exist .fraud-risk-checklist__item-seq {
  background: var(--el-color-danger);
  color: #fff;
}

.fraud-risk-checklist__item-desc {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
}

.fraud-risk-checklist__auto-tag {
  flex-shrink: 0;
}

.fraud-risk-checklist__info-icon {
  color: var(--el-color-primary);
  cursor: help;
  font-size: 15px;
  flex-shrink: 0;
}

/* ─── 字段行 ─────────────────────────────────────────────────────────────── */

.fraud-risk-checklist__item-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-start;
  padding-left: 30px;
}

.fraud-risk-checklist__field {
  display: flex;
  align-items: center;
  gap: 6px;
}

.fraud-risk-checklist__field--wide {
  flex: 1;
  min-width: 180px;
}

.fraud-risk-checklist__field-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.fraud-risk-checklist__field-label--tip {
  text-decoration: underline dotted;
  cursor: help;
}

.fraud-risk-checklist__field-value {
  font-size: 12px;
}

.fraud-risk-checklist__exist-val {
  font-size: 12px;
}

.fraud-risk-checklist__exist-val.is-yes {
  color: var(--el-color-danger);
  font-weight: 600;
}

.fraud-risk-checklist__ref-link {
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.fraud-risk-checklist__warn-icon {
  color: var(--el-color-warning);
  font-size: 15px;
  margin-left: 4px;
}

.fraud-risk-checklist__preset-btn {
  flex-shrink: 0;
  font-size: 11px;
}
</style>
