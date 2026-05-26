<!--
  GtCNoteTable.vue — C 类附注披露嵌套表组件

  按 design §3.5 实现：
  - 子表（4-7 张）独立渲染为可折叠卡片 + "不适用"软标记（hidden_subtables）
  - 上市/国企版本切换（standard switcher）：保留共有字段值，差异字段 ElMessageBox 提示
  - 子表合计 ↔ 主表行实时联动（inheritance_rules 校验，badge 显示 ✓ / ✗ + 差异）
  - applicable_to_sub_class 过滤子表/列（仅显示匹配当前 standard 的）
  - static_rows / dynamic_rows 两种子表类型
  - render hints：amount / amount_formula / percent / percent_formula / checkmark / tag / index_chip
  - footer_total 自动 SUM
  - cross_refs auto_pull 显示数据来源 + 点击跳转
  - Debounced auto-save (1.5s)

  锚定 spec workpaper-html-renderer Task 10.2
  Validates: Requirements 3.4（C 类 166 sheet）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
  附注双源同步走 `/api/projects/{pid}/disclosure-notes/sync-from-workpaper`
  单向推送（Task 10.3，C → disclosure_notes 模块）。
-->

<template>
  <div class="gt-c-note-table">
    <!-- ─── 顶部头部信息 + standard switcher ─── -->
    <header class="gt-cnt__header">
      <div class="gt-cnt__header-meta">
        <span v-if="entityName" class="gt-cnt__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-cnt__period">{{ periodEnd }}</span>
        <span v-if="sectionId" class="gt-cnt__section">附注章节：<strong>{{ sectionId }}</strong></span>
        <span v-if="indexNo" class="gt-cnt__index">索引号：<strong>{{ indexNo }}</strong></span>
      </div>
      <div class="gt-cnt__header-actions">
        <el-tag v-if="standardLabel" :type="standardTagType" size="small" effect="dark">
          {{ standardLabel }}
        </el-tag>
        <el-radio-group
          v-if="standardSwitchable && !readonly"
          v-model="currentStandardSubClass"
          size="small"
          @change="onStandardSwitch"
        >
          <el-radio-button value="listed">上市</el-radio-button>
          <el-radio-button value="soe">国企</el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <!-- ─── 上下文字段（金额单位/币种等） ─── -->
    <section v-if="contextFields.length" class="gt-cnt__context">
      <el-form
        :model="contextData"
        label-position="left"
        label-width="100px"
        inline
        :disabled="readonly"
        size="small"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
        >
          <el-select
            v-if="field.type === 'enum'"
            v-model="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            clearable
            class="gt-cnt__context-select"
            @change="onContextChange(field.name)"
          >
            <el-option
              v-for="opt in field.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
          <el-input
            v-else
            v-model="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            class="gt-cnt__context-input"
            @change="onContextChange(field.name)"
          />
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 隐藏子表恢复区（compact 单行展示） ─── -->
    <section
      v-if="hiddenVisibleSubTables.length"
      class="gt-cnt__hidden-summary"
    >
      <el-alert type="info" :closable="false" show-icon>
        <template #default>
          <div class="gt-cnt__hidden-list">
            <span class="gt-cnt__hidden-label">已标记不适用：</span>
            <div class="gt-cnt__hidden-tags">
              <el-tag
                v-for="st in hiddenVisibleSubTables"
                :key="st.id"
                closable
                size="small"
                type="info"
                effect="plain"
                @close="onRestoreSubTable(st.id)"
              >
                {{ st.title }}
              </el-tag>
            </div>
          </div>
        </template>
      </el-alert>
    </section>

    <!-- ─── 子表卡片列表（按 order 排序） ─── -->
    <el-collapse
      v-model="activeCollapse"
      class="gt-cnt__collapse"
    >
      <el-collapse-item
        v-for="st in visibleSubTables"
        :key="st.id"
        :name="st.id"
        class="gt-cnt__sub-card"
      >
        <template #title>
          <div class="gt-cnt__sub-title">
            <span class="gt-cnt__sub-title-text">{{ st.title }}</span>
            <el-tag
              v-for="badge in subClassBadges(st)"
              :key="badge.value"
              :type="badge.type"
              size="small"
              effect="plain"
              class="gt-cnt__sub-badge"
            >
              {{ badge.label }}
            </el-tag>
            <el-tag
              v-if="st.type === 'dynamic_rows'"
              size="small"
              effect="plain"
              class="gt-cnt__sub-badge"
            >
              {{ subTableRowCount(st.id) }} / {{ st.max_rows ?? 100 }} 行
            </el-tag>
            <el-button
              v-if="!readonly"
              link
              size="small"
              class="gt-cnt__sub-toggle"
              @click.stop="onHideSubTable(st.id)"
            >
              不适用
            </el-button>
          </div>
        </template>

        <!-- 子表说明 -->
        <p v-if="st.description" class="gt-cnt__sub-desc">{{ st.description }}</p>

        <!-- ── static_rows 渲染 ── -->
        <div v-if="st.type === 'static_rows'" class="gt-cnt__sub-body">
          <el-table
            :data="staticRowsView(st)"
            border
            size="small"
            :row-class-name="staticRowClass"
            class="gt-cnt__sub-table"
          >
            <el-table-column
              v-for="col in visibleColumns(st)"
              :key="col._cellKey"
              :label="col.label"
              :min-width="col.width || 130"
              :align="isLabelField(col.field) ? 'left' : 'right'"
              resizable
            >
              <template #default="{ row }">
                <CNoteCell
                  :row="row"
                  :col="col"
                  :readonly="readonly"
                  :computed-value="cellComputedValue(st, row, col)"
                  @change="onCellChange(st, row, col)"
                />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- ── dynamic_rows 渲染 ── -->
        <div v-else-if="st.type === 'dynamic_rows'" class="gt-cnt__sub-body">
          <div v-if="!readonly" class="gt-cnt__sub-toolbar">
            <el-button
              size="small"
              :icon="PlusIcon"
              :disabled="reachedMaxRows(st)"
              @click="onAddDynamicRow(st)"
            >
              新增行
            </el-button>
          </div>

          <el-table
            :data="dynamicRowsView(st)"
            border
            size="small"
            class="gt-cnt__sub-table"
            empty-text="暂无数据，点击「新增行」开始填写"
          >
            <el-table-column
              v-for="col in visibleColumns(st)"
              :key="col._cellKey"
              :label="col.label"
              :min-width="col.width || 130"
              resizable
            >
              <template #default="{ row }">
                <CNoteCell
                  :row="row"
                  :col="col"
                  :readonly="readonly"
                  :computed-value="cellComputedValue(st, row, col)"
                  @change="onCellChange(st, row, col)"
                />
              </template>
            </el-table-column>

            <el-table-column
              v-if="!readonly"
              label="操作"
              width="70"
              fixed="right"
            >
              <template #default="{ $index }">
                <el-button
                  link
                  type="danger"
                  size="small"
                  @click="onRemoveDynamicRow(st, $index)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 子表底部合计行 -->
          <div
            v-if="st.footer_total?.enabled"
            class="gt-cnt__sub-footer"
          >
            <span class="gt-cnt__footer-label">{{ st.footer_total.label || '合计' }}：</span>
            <span
              v-for="col in footerTotalColumns(st)"
              :key="col.field"
              class="gt-cnt__footer-cell"
            >
              <span class="gt-cnt__footer-col-label">{{ col.label }}</span>
              <span class="gt-amt">{{ formatAmount(footerTotalValue(st, col)) }}</span>
            </span>
          </div>
        </div>

        <!-- ── inheritance_rules 校验徽标（每张子表底部） ── -->
        <div
          v-if="ruleStatusForSubTable(st.id).length"
          class="gt-cnt__rule-status"
        >
          <el-tooltip
            v-for="rs in ruleStatusForSubTable(st.id)"
            :key="rs.ruleId"
            :content="rs.tooltip"
            placement="top"
          >
            <el-tag
              size="small"
              :type="ruleStatusTagType(rs)"
              effect="light"
              class="gt-cnt__rule-tag"
            >
              <el-icon><component :is="ruleStatusIcon(rs)" /></el-icon>
              <span>{{ rs.label }}</span>
            </el-tag>
          </el-tooltip>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- ─── 引用来源（cross_refs auto_pull 展示） ─── -->
    <section v-if="autoPullRefs.length" class="gt-cnt__refs">
      <h4 class="gt-cnt__refs-title">数据来源</h4>
      <ul class="gt-cnt__refs-list">
        <li
          v-for="refItem in autoPullRefs"
          :key="refItem.ref_id"
          class="gt-cnt__ref-item"
        >
          <GtIndexChip
            v-if="refItem.target_wp"
            :value="refItem.target_wp"
            :validate="true"
            @click="onJumpToReference(refItem.target_wp || '')"
          />
          <span class="gt-cnt__ref-desc">{{ refItem.description }}</span>
        </li>
      </ul>
    </section>

    <!-- ─── 底部工具栏：手动同步附注 ─── -->
    <footer v-if="!readonly && hasSyncDownstream" class="gt-cnt__footer-actions">
      <el-button
        size="small"
        type="primary"
        plain
        :icon="UploadIcon"
        :loading="isSyncing"
        :disabled="isSyncing"
        @click="onSyncToDisclosureNotes"
      >
        同步到附注模块
      </el-button>
      <el-tooltip
        content="C 类附注 sheet 是编辑入口，保存时自动同步到 disclosure_notes 模块对应章节。点击此按钮可手动触发同步。"
        placement="top"
      >
        <el-icon class="gt-cnt__hint-icon"><InfoFilled /></el-icon>
      </el-tooltip>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, defineComponent, h } from 'vue'
import { useRoute } from 'vue-router'
import {
  ElInput,
  ElInputNumber,
  ElSelect,
  ElOption,
  ElCheckbox,
  ElDatePicker,
  ElIcon,
  ElMessageBox,
  ElMessage,
} from 'element-plus'
import {
  Plus as PlusIcon,
  Upload as UploadIcon,
  InfoFilled,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { formatAmount } from '@/utils/formatAmount'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

type SubTableType = 'static_rows' | 'dynamic_rows'
type ColumnType = 'text' | 'textarea' | 'number' | 'enum' | 'multi_enum' | 'date' | 'boolean'
type RenderHint =
  | 'amount'
  | 'amount_formula'
  | 'percent'
  | 'percent_formula'
  | 'checkmark'
  | 'tag'
  | 'index_chip'
  | string
type SubClass = 'listed' | 'soe'

interface ColumnDef {
  field: string
  label: string
  type?: ColumnType
  enum?: string[]
  render?: RenderHint
  width?: number
  min?: number
  max?: number
  max_length?: number
  required?: boolean
  readonly?: boolean
  formula?: string
  default?: any
  applicable_to_sub_class?: SubClass[]
  hint?: string
  format?: string
}

interface ColumnDefWithKey extends ColumnDef {
  _cellKey: string
}

interface StaticRowDef {
  id: string
  label: string
  is_grand_total?: boolean
  is_subtotal?: boolean
  indent?: number
}

interface FooterTotalDef {
  enabled?: boolean
  label?: string
  sum_columns?: string[]
  formula_columns?: Record<string, string>
}

interface SubTableSchema {
  id: string
  title: string
  type: SubTableType
  applicable_to_sub_class?: SubClass[]
  order?: number
  columns?: Record<string, ColumnDef>
  static_rows?: StaticRowDef[]
  max_rows?: number
  add_row_button?: boolean
  description?: string
  footer_total?: FooterTotalDef
}

interface InheritanceRuleSourceTarget {
  sub_table?: string
  row?: string
  column?: string
  sum_field?: string
  exclude_rows?: string[]
  group_by?: string
  filter?: string
  formula?: string
  external?: string
  query?: Record<string, any>
}

interface InheritanceRule {
  id: string
  source: InheritanceRuleSourceTarget
  target: InheritanceRuleSourceTarget
  formula?: 'SUM' | string
  validation: 'equal' | 'less_than_or_equal' | string
  on_mismatch: 'error' | 'warning' | 'info' | string
  description?: string
  applicable_when?: { standard?: SubClass | string }
}

interface VersionVariant {
  label?: string
  extra_subtables?: string[]
  extra_columns_in?: Record<string, string[]>
}

interface ContextField {
  name: string
  label: string
  type?: ColumnType
  cell?: string
  default?: any
  enum?: string[]
  readonly?: boolean
  hint?: string
}

interface CrossRefDef {
  ref_id: string
  source?: any
  source_cell?: string
  target_wp?: string
  target_sheet?: string
  target_section?: string
  target_field?: string
  description?: string
  severity?: 'required' | 'optional' | string
  direction?: 'inbound' | 'outbound' | string
  auto_pull?: boolean
  sync_strategy?: string
}

interface LinkageDownstreamRule {
  target?: string
  condition?: string
  action?: string
  description?: string
}

interface LinkageDef {
  upstream?: any[]
  downstream?: LinkageDownstreamRule[]
}

interface CNoteTableSchema {
  component_type?: string
  applicable_standard?: string
  applicable_standards?: string[]
  fixed_cells?: Record<string, string>
  fields?: ContextField[]
  sub_tables?: SubTableSchema[]
  inheritance_rules?: InheritanceRule[]
  version_variants?: Partial<Record<SubClass, VersionVariant>>
  hidden_subtables?: { semantics?: string; default?: string[] }
  cross_refs?: CrossRefDef[]
  linkage?: LinkageDef
  [key: string]: any
}

type RowData = Record<string, any> & { _row_id?: string }

interface CNoteTableHtmlData {
  sub_table_data?: Record<string, RowData[]>
  hidden_subtables?: string[]
  current_standard?: string
  context?: Record<string, any>
  [key: string]: any
}

interface SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  sub_table_data: Record<string, RowData[]>
  current_standard: string
}

interface RuleStatus {
  ruleId: string
  subTableId: string
  status: 'ok' | 'mismatch' | 'warning' | 'na'
  label: string
  tooltip: string
  diff?: number
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: CNoteTableSchema
  htmlData: CNoteTableHtmlData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'subtable-toggle': [subTableId: string]
  'standard-switch': [standard: string]
  'sync-to-disclosure-notes': [payload: SyncPayload]
  'jump-to-reference': [refCode: string]
  'save': [data: CNoteTableHtmlData]
}>()

// ─── Refs（按 setup const 顺序铁律：先定义被 computed 引用的 ref） ────────────

const subTableData = ref<Record<string, RowData[]>>({})
const hiddenSubtables = ref<string[]>([])
const contextData = ref<Record<string, any>>({})
const currentStandardSubClass = ref<SubClass>('listed')
const activeCollapse = ref<string[]>([])
// 手动同步附注按钮 loading 状态（design §12.1：底稿 → 模块单向同步）
const isSyncing = ref(false)
const route = useRoute()

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Inline cell renderer (kept as functional component to keep template clean) ──

const CNoteCell = defineComponent({
  name: 'CNoteCell',
  props: {
    row: { type: Object, required: true },
    col: { type: Object, required: true },
    readonly: { type: Boolean, default: false },
    computedValue: { type: [Number, String, Object] as any, default: null },
  },
  emits: ['change'],
  setup(p, { emit: emitInner }) {
    const onUpdate = (v: any) => {
      p.row[p.col.field] = v
      emitInner('change', v)
    }

    return () => {
      const col = p.col as ColumnDefWithKey
      const row = p.row as RowData

      // Read-only label / readonly columns (e.g. category_label)
      if (col.readonly || isLabelField(col.field)) {
        const indent = (row._indent ?? 0) as number
        const text = String(row[col.field] ?? row._label ?? '')
        return h(
          'span',
          {
            class: ['gt-cnt__cell-readonly', indent > 0 ? `gt-cnt__indent-${indent}` : ''].filter(Boolean).join(' '),
          },
          text,
        )
      }

      // amount_formula / percent_formula → readonly computed display
      if (col.render === 'amount_formula') {
        return h(
          'span',
          { class: 'gt-cnt__cell-readonly gt-amt' },
          formatAmount(p.computedValue as number | null),
        )
      }
      if (col.render === 'percent_formula') {
        return h(
          'span',
          { class: 'gt-cnt__cell-readonly' },
          formatPercent(p.computedValue as number | null),
        )
      }

      // checkmark display when boolean readonly
      if (col.type === 'boolean') {
        return h(ElCheckbox, {
          modelValue: !!row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
        })
      }

      if (col.type === 'number') {
        const isAmount = col.render === 'amount' || col.render === 'amount_formula'
        return h(ElInputNumber, {
          modelValue: (row[col.field] ?? null) as number | null,
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          precision: isAmount ? 2 : undefined,
          controlsPosition: 'right',
          size: 'small',
          class: isAmount ? 'gt-amt gt-cnt__amount-input' : undefined,
          min: col.min,
          max: col.max,
        })
      }

      if (col.type === 'enum') {
        return h(
          ElSelect,
          {
            modelValue: row[col.field],
            'onUpdate:modelValue': onUpdate,
            disabled: p.readonly,
            size: 'small',
            clearable: true,
            placeholder: col.label,
          },
          {
            default: () =>
              (col.enum || []).map(opt =>
                h(ElOption, { key: opt, label: opt, value: opt }),
              ),
          },
        )
      }

      if (col.type === 'multi_enum') {
        return h(
          ElSelect,
          {
            modelValue: row[col.field] ?? [],
            'onUpdate:modelValue': onUpdate,
            disabled: p.readonly,
            size: 'small',
            multiple: true,
            collapseTags: true,
            collapseTagsTooltip: true,
            placeholder: col.label,
          },
          {
            default: () =>
              (col.enum || []).map(opt =>
                h(ElOption, { key: opt, label: opt, value: opt }),
              ),
          },
        )
      }

      if (col.type === 'date') {
        return h(ElDatePicker, {
          modelValue: row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          size: 'small',
          type: 'date',
          format: 'YYYY-MM-DD',
          valueFormat: 'YYYY-MM-DD',
          placeholder: col.label,
        })
      }

      if (col.type === 'textarea') {
        return h(ElInput, {
          modelValue: row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          size: 'small',
          type: 'textarea',
          rows: 2,
          maxlength: col.max_length,
          showWordLimit: !!col.max_length,
          placeholder: col.label,
        })
      }

      // Default: text
      return h(ElInput, {
        modelValue: row[col.field],
        'onUpdate:modelValue': onUpdate,
        disabled: p.readonly,
        size: 'small',
        maxlength: col.max_length,
        placeholder: col.label,
      })
    }
  },
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function deriveSubClassFromStandard(std: string | undefined): SubClass {
  if (!std) return 'listed'
  return std.startsWith('soe') ? 'soe' : 'listed'
}

function deriveStandardFromSubClass(
  sub: SubClass,
  prevStandard: string | undefined,
): string {
  // Preserve scope (standalone / consolidated)
  const scope = (prevStandard && prevStandard.includes('consolidated'))
    ? 'consolidated'
    : 'standalone'
  return `${sub}_${scope}`
}

function isLabelField(field: string): boolean {
  return (
    field === 'category_label' ||
    field === 'aging_label' ||
    field === 'movement_label' ||
    field === 'maturity_label' ||
    field === 'guarantee_label' ||
    field === 'ecl_stage' ||
    field.endsWith('_label')
  )
}

function escapeNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return isNaN(n) ? null : n
}

function formatPercent(value: number | string | null | undefined): string {
  if (value == null || value === '') return ''
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (typeof num !== 'number' || isNaN(num)) return ''
  return `${num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

// ─── Computed: schema 派生 ───────────────────────────────────────────────────

const fixedCells = computed(() => props.schema?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.I3 || fixedCells.value?.H3 || fixedCells.value?.J3 || '',
)

const contextFields = computed<ContextField[]>(() => {
  const arr = props.schema?.fields
  return Array.isArray(arr) ? arr : []
})

const sectionId = computed<string>(() => {
  const sec = contextData.value?.section_id
  if (sec) return String(sec)
  const def = contextFields.value.find(f => f.name === 'section_id')
  return def?.default ? String(def.default) : ''
})

const versionVariants = computed(() => props.schema?.version_variants ?? {})

const standardLabel = computed(() => {
  const variant = versionVariants.value[currentStandardSubClass.value]
  return variant?.label || ''
})

const standardTagType = computed<'success' | 'warning' | 'info'>(() => {
  if (currentStandardSubClass.value === 'listed') return 'success'
  if (currentStandardSubClass.value === 'soe') return 'warning'
  return 'info'
})

const standardSwitchable = computed(() => {
  // 仅当 schema 配置了 listed 或 soe 变体时才允许切换
  const v = versionVariants.value
  return !!(v.listed || v.soe)
})

const allSubTables = computed<SubTableSchema[]>(() => {
  const arr = props.schema?.sub_tables ?? []
  if (!Array.isArray(arr)) return []
  return [...arr].sort((a, b) => (a.order ?? 999) - (b.order ?? 999))
})

const visibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st => {
    if (st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub)) {
      return false
    }
    if (hiddenSubtables.value.includes(st.id)) return false
    return true
  })
})

const hiddenVisibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st => {
    if (st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub)) {
      return false
    }
    return hiddenSubtables.value.includes(st.id)
  })
})

const inheritanceRules = computed<InheritanceRule[]>(() => {
  const arr = props.schema?.inheritance_rules ?? []
  if (!Array.isArray(arr)) return []
  return arr.filter(rule => {
    if (rule.applicable_when?.standard) {
      return rule.applicable_when.standard === currentStandardSubClass.value
    }
    return true
  })
})

const autoPullRefs = computed<CrossRefDef[]>(() => {
  const arr = props.schema?.cross_refs ?? []
  if (!Array.isArray(arr)) return []
  return arr.filter(r => r.auto_pull && r.direction === 'inbound')
})

const downstreamRules = computed<LinkageDownstreamRule[]>(() => {
  const arr = props.schema?.linkage?.downstream
  return Array.isArray(arr) ? arr : []
})

const hasSyncDownstream = computed(() =>
  downstreamRules.value.some(r => r.target === 'disclosure_notes'),
)

// ─── Helpers: 列过滤 + 子表展示 ─────────────────────────────────────────────

function visibleColumns(st: SubTableSchema): ColumnDefWithKey[] {
  const cols = st.columns ?? {}
  const sub = currentStandardSubClass.value
  return Object.entries(cols)
    .filter(([_cell, col]) => {
      if (col.applicable_to_sub_class && !col.applicable_to_sub_class.includes(sub)) {
        return false
      }
      return true
    })
    .map(([cell, col]) => ({ ...col, _cellKey: cell }))
}

function subClassBadges(
  st: SubTableSchema,
): Array<{ value: string; label: string; type: 'success' | 'warning' | 'info' }> {
  const arr = st.applicable_to_sub_class
  if (!arr || arr.length === 0) return []
  if (arr.length === 1) {
    if (arr[0] === 'listed') return [{ value: 'listed', label: '上市专属', type: 'success' }]
    if (arr[0] === 'soe') return [{ value: 'soe', label: '国企专属', type: 'warning' }]
  }
  return []
}

function subTableRowCount(stId: string): number {
  return subTableData.value[stId]?.length ?? 0
}

function reachedMaxRows(st: SubTableSchema): boolean {
  const max = st.max_rows ?? 100
  return (subTableData.value[st.id]?.length ?? 0) >= max
}

// ─── Static rows view (returns reactive rows merged with definitions) ───────

function staticRowsView(st: SubTableSchema): RowData[] {
  const defs = st.static_rows ?? []
  const stored = subTableData.value[st.id] ?? []
  const storedMap = new Map<string, RowData>()
  for (const r of stored) {
    if (r.id) storedMap.set(String(r.id), r)
  }
  const labelField = labelColumnField(st)
  return defs.map(def => {
    const existing = storedMap.get(def.id)
    if (existing) {
      // Make sure label is always synced
      if (labelField && !existing[labelField]) existing[labelField] = def.label
      existing._label = def.label
      existing._is_grand_total = def.is_grand_total
      existing._is_subtotal = def.is_subtotal
      existing._indent = def.indent ?? 0
      return existing
    }
    // Should never happen if initData was called, but defensive
    const fresh: RowData = {
      id: def.id,
      _label: def.label,
      _is_grand_total: def.is_grand_total,
      _is_subtotal: def.is_subtotal,
      _indent: def.indent ?? 0,
    }
    if (labelField) fresh[labelField] = def.label
    return fresh
  })
}

function labelColumnField(st: SubTableSchema): string | null {
  const cols = visibleColumns(st)
  const first = cols[0]
  if (first && (first.readonly || isLabelField(first.field))) return first.field
  return null
}

function staticRowClass({ row }: { row: RowData }): string {
  if (row._is_grand_total) return 'gt-cnt-row-grand-total'
  if (row._is_subtotal) return 'gt-cnt-row-subtotal'
  return ''
}

function dynamicRowsView(st: SubTableSchema): RowData[] {
  return subTableData.value[st.id] ?? []
}

function buildEmptyRow(st: SubTableSchema): RowData {
  const row: RowData = { _row_id: genRowId() }
  for (const col of visibleColumns(st)) {
    if (col.field === 'seq') {
      row[col.field] = (subTableData.value[st.id]?.length ?? 0) + 1
      continue
    }
    if (col.type === 'multi_enum') row[col.field] = []
    else if (col.type === 'number') row[col.field] = null
    else if (col.type === 'boolean') row[col.field] = false
    else row[col.field] = col.default ?? ''
  }
  return row
}

// ─── Formula computation ─────────────────────────────────────────────────────

function cellComputedValue(
  st: SubTableSchema,
  row: RowData,
  col: ColumnDefWithKey,
): number | null {
  if (col.render !== 'amount_formula' && col.render !== 'percent_formula') return null
  const formula = col.formula
  if (!formula) return null
  const cols = st.columns ?? {}
  const cellMap = new Map<string, ColumnDef>()
  for (const [cell, c] of Object.entries(cols)) {
    cellMap.set(cell, c)
  }
  const expr = formula
    .replace(/^=/, '')
    .replace(/[A-Z][a-zA-Z_]*/g, (token) => {
      // Try direct cell-letter substitution first (e.g. "B-D")
      const colDef = cellMap.get(token)
      if (colDef) {
        const v = row[colDef.field]
        const n = escapeNumber(v)
        return n == null ? '0' : String(n)
      }
      return '0'
    })
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function(`return (${expr})`)
    const result = fn()
    if (typeof result === 'number' && isFinite(result)) return result
    return null
  } catch {
    return null
  }
}

function footerTotalColumns(st: SubTableSchema): ColumnDef[] {
  const cellList = st.footer_total?.sum_columns ?? []
  const colMap = st.columns ?? {}
  const sub = currentStandardSubClass.value
  const result: ColumnDef[] = []
  for (const cell of cellList) {
    const c = colMap[cell]
    if (!c) continue
    if (c.applicable_to_sub_class && !c.applicable_to_sub_class.includes(sub)) continue
    result.push(c)
  }
  return result
}

function footerTotalValue(st: SubTableSchema, col: ColumnDef): number {
  const rows = subTableData.value[st.id] ?? []
  let sum = 0
  for (const row of rows) {
    const n = escapeNumber(row[col.field])
    if (n != null) sum += n
  }
  return sum
}

// ─── Inheritance rule status ─────────────────────────────────────────────────

const ruleStatuses = computed<RuleStatus[]>(() => {
  const out: RuleStatus[] = []
  for (const rule of inheritanceRules.value) {
    const status = evaluateRule(rule)
    if (status) out.push(status)
  }
  return out
})

function findSubTable(id: string | undefined): SubTableSchema | undefined {
  if (!id) return undefined
  return (props.schema?.sub_tables ?? []).find(s => s.id === id)
}

function evaluateRule(rule: InheritanceRule): RuleStatus | null {
  const src = rule.source
  const tgt = rule.target

  // 仅同 sheet 内 sub_table → sub_table 规则可前端实时评估
  if (!src.sub_table || !tgt.sub_table) {
    return {
      ruleId: rule.id,
      subTableId: src.sub_table || tgt.sub_table || '',
      status: 'na',
      label: '外部勾稽',
      tooltip: rule.description || '此规则关联外部数据源（试算表/其它底稿），需保存后服务端校验',
    }
  }

  const sourceValue = computeRuleSource(rule)
  const targetValue = computeRuleTarget(rule)

  if (sourceValue === null || targetValue === null) {
    return null
  }

  const diff = sourceValue - targetValue
  const tolerance = 0.01

  if (rule.validation === 'equal') {
    if (Math.abs(diff) <= tolerance) {
      return {
        ruleId: rule.id,
        subTableId: src.sub_table,
        status: 'ok',
        label: '勾稽一致',
        tooltip: rule.description || `${src.sub_table} → ${tgt.sub_table} 勾稽一致`,
        diff: 0,
      }
    }
    return {
      ruleId: rule.id,
      subTableId: src.sub_table,
      status: rule.on_mismatch === 'error' ? 'mismatch' : 'warning',
      label: `差异 ${formatAmount(diff)}`,
      tooltip: `${rule.description || src.sub_table + ' → ' + tgt.sub_table}\n源值: ${formatAmount(sourceValue)}\n目标值: ${formatAmount(targetValue)}`,
      diff,
    }
  }

  if (rule.validation === 'less_than_or_equal') {
    if (sourceValue <= targetValue + tolerance) {
      return {
        ruleId: rule.id,
        subTableId: src.sub_table,
        status: 'ok',
        label: '上限通过',
        tooltip: rule.description || `${src.sub_table} ≤ ${tgt.sub_table}`,
        diff: 0,
      }
    }
    return {
      ruleId: rule.id,
      subTableId: src.sub_table,
      status: rule.on_mismatch === 'error' ? 'mismatch' : 'warning',
      label: `超限 ${formatAmount(sourceValue - targetValue)}`,
      tooltip: `${rule.description || ''}\n源值 ${formatAmount(sourceValue)} > 目标值 ${formatAmount(targetValue)}`,
      diff: sourceValue - targetValue,
    }
  }

  return null
}

function computeRuleSource(rule: InheritanceRule): number | null {
  const src = rule.source
  if (!src.sub_table) return null
  const rows = subTableData.value[src.sub_table] ?? []

  if (src.sum_field) {
    const filtered = filterRows(rows, src)
    let sum = 0
    for (const r of filtered) {
      const n = escapeNumber(r[src.sum_field])
      if (n != null) sum += n
    }
    return sum
  }

  if (src.row && src.column) {
    const st = findSubTable(src.sub_table)
    const col = st?.columns?.[src.column]
    if (!col) return null
    const stored = rows.find(r => r.id === src.row)
    if (!stored) return null
    return escapeNumber(stored[col.field])
  }

  return null
}

function computeRuleTarget(rule: InheritanceRule): number | null {
  const tgt = rule.target
  if (!tgt.sub_table || !tgt.row || !tgt.column) return null
  const st = findSubTable(tgt.sub_table)
  const col = st?.columns?.[tgt.column]
  if (!col) return null
  const rows = subTableData.value[tgt.sub_table] ?? []
  const stored = rows.find(r => r.id === tgt.row)
  if (!stored) return null
  return escapeNumber(stored[col.field])
}

function filterRows(rows: RowData[], src: InheritanceRuleSourceTarget): RowData[] {
  let result = rows
  if (Array.isArray(src.exclude_rows) && src.exclude_rows.length) {
    const set = new Set(src.exclude_rows)
    result = result.filter(r => !r.id || !set.has(String(r.id)))
  }
  if (src.group_by) {
    const [field, value] = src.group_by.split('=')
    if (field && value !== undefined) {
      result = result.filter(r => String(r[field.trim()] ?? '') === value.trim())
    }
  }
  if (src.filter) {
    const [field, raw] = src.filter.split('=')
    if (field && raw !== undefined) {
      const want = raw.trim()
      result = result.filter(r => {
        const v = r[field.trim()]
        if (want === 'true') return v === true || v === 'true' || v === 1
        if (want === 'false') return v === false || v === 'false' || v === 0 || v == null
        return String(v ?? '') === want
      })
    }
  }
  return result
}

function ruleStatusForSubTable(stId: string): RuleStatus[] {
  return ruleStatuses.value.filter(r => r.subTableId === stId)
}

function ruleStatusTagType(rs: RuleStatus): 'success' | 'warning' | 'danger' | 'info' {
  if (rs.status === 'ok') return 'success'
  if (rs.status === 'mismatch') return 'danger'
  if (rs.status === 'warning') return 'warning'
  return 'info'
}

function ruleStatusIcon(rs: RuleStatus) {
  if (rs.status === 'ok') return CircleCheckFilled
  if (rs.status === 'mismatch') return CircleCloseFilled
  if (rs.status === 'warning') return WarningFilled
  return InfoFilled
}

// ─── Cell change handlers ───────────────────────────────────────────────────

function onCellChange(_st: SubTableSchema, _row: RowData, _col: ColumnDefWithKey) {
  debounceSave()
}

function onAddDynamicRow(st: SubTableSchema) {
  if (reachedMaxRows(st)) return
  if (!subTableData.value[st.id]) subTableData.value[st.id] = []
  subTableData.value[st.id].push(buildEmptyRow(st))
  debounceSave()
}

function onRemoveDynamicRow(st: SubTableSchema, idx: number) {
  const rows = subTableData.value[st.id]
  if (!rows) return
  rows.splice(idx, 1)
  // 重排 seq（若列存在）
  if (Object.values(st.columns ?? {}).some(c => c.field === 'seq')) {
    rows.forEach((r, i) => {
      r.seq = i + 1
    })
  }
  debounceSave()
}

// ─── Hide/restore subtable（"不适用"软标记） ─────────────────────────────────

async function onHideSubTable(stId: string) {
  if (props.readonly) return
  try {
    await ElMessageBox.confirm(
      '将此子表标记为「不适用」？标记后子表将折叠隐藏，但数据保留可恢复，导出 xlsx 时该子表区域将留空并加批注。',
      '标记不适用',
      {
        confirmButtonText: '确认标记',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  if (!hiddenSubtables.value.includes(stId)) {
    hiddenSubtables.value.push(stId)
  }
  activeCollapse.value = activeCollapse.value.filter(id => id !== stId)
  emit('subtable-toggle', stId)
  debounceSave()
}

function onRestoreSubTable(stId: string) {
  if (props.readonly) return
  hiddenSubtables.value = hiddenSubtables.value.filter(id => id !== stId)
  if (!activeCollapse.value.includes(stId)) {
    activeCollapse.value.push(stId)
  }
  emit('subtable-toggle', stId)
  debounceSave()
}

// ─── Standard switch（上市↔国企） ────────────────────────────────────────────

async function onStandardSwitch(newSub: string | number | boolean | undefined) {
  const target = String(newSub) as SubClass
  if (target !== 'listed' && target !== 'soe') return

  // currentStandardSubClass 已经被 v-model 同步更新，需要先回退再确认
  const requested = target
  const previous: SubClass = requested === 'listed' ? 'soe' : 'listed'

  const lostSubTables = allSubTables.value.filter(st => {
    if (!st.applicable_to_sub_class) return false
    return st.applicable_to_sub_class.includes(previous) && !st.applicable_to_sub_class.includes(requested)
  })
  const gainedSubTables = allSubTables.value.filter(st => {
    if (!st.applicable_to_sub_class) return false
    return !st.applicable_to_sub_class.includes(previous) && st.applicable_to_sub_class.includes(requested)
  })

  const messages: string[] = []
  if (lostSubTables.length) {
    const titles = lostSubTables.map(s => s.title).join('、')
    messages.push(`将隐藏 ${lostSubTables.length} 张${previous === 'listed' ? '上市' : '国企'}专属子表（数据保留）：${titles}`)
  }
  if (gainedSubTables.length) {
    const titles = gainedSubTables.map(s => s.title).join('、')
    messages.push(`将显示 ${gainedSubTables.length} 张${requested === 'listed' ? '上市' : '国企'}专属子表：${titles}`)
  }
  messages.push('共有字段值会保留，仅差异字段切换显示。')

  try {
    await ElMessageBox.confirm(
      messages.join('\n'),
      `切换到${requested === 'listed' ? '上市公司版' : '国企版'}`,
      {
        confirmButtonText: '确认切换',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
  } catch {
    // Revert the radio button selection
    currentStandardSubClass.value = previous
    return
  }

  // Confirmed; ensure ref reflects target
  currentStandardSubClass.value = requested
  const newStandard = deriveStandardFromSubClass(
    requested,
    contextData.value._current_standard as string,
  )
  contextData.value._current_standard = newStandard
  emit('standard-switch', newStandard)
  debounceSave()
}

// ─── Cross-ref jump ──────────────────────────────────────────────────────────

function onJumpToReference(refCode: string) {
  if (refCode) emit('jump-to-reference', refCode)
}

// ─── Manual sync to disclosure_notes ────────────────────────────────────────

async function onSyncToDisclosureNotes() {
  if (!sectionId.value) {
    ElMessage.warning('未配置附注章节号（section_id），无法同步')
    return
  }
  const payload: SyncPayload = {
    wp_id: props.wpId,
    sheet_name: props.sheetName,
    section_id: sectionId.value,
    sub_table_data: { ...subTableData.value },
    current_standard: deriveStandardFromSubClass(
      currentStandardSubClass.value,
      contextData.value._current_standard as string,
    ),
  }
  // 始终先 emit 让父组件感知
  emit('sync-to-disclosure-notes', payload)

  // 直接调用同步端点（design §12.1 推荐选项 A：底稿 → 模块单向同步）
  const projectId = route.params?.projectId as string | undefined
  if (!projectId) {
    // 父组件未在 router 路径中提供 projectId，则不主动 push（仅 emit 让上层处理）
    return
  }

  if (isSyncing.value) return
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const rows = Number(result?.rows_synced ?? 0)
    ElMessage.success(`已同步 ${rows} 行到附注模块「${sectionId.value}」`)
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    ElMessage.error(`同步附注失败：${detail}`)
  } finally {
    isSyncing.value = false
  }
}

function onContextChange(_name: string) {
  debounceSave()
}

// ─── Init / Sync ─────────────────────────────────────────────────────────────

function initData() {
  const data = props.htmlData ?? {}

  // sub_table_data
  const stIn = data.sub_table_data && typeof data.sub_table_data === 'object'
    ? data.sub_table_data
    : {}
  const result: Record<string, RowData[]> = {}
  for (const st of allSubTables.value) {
    const rows = (stIn as Record<string, any>)[st.id]
    if (Array.isArray(rows)) {
      result[st.id] = rows.map(r => {
        const cleaned: RowData = { ...r }
        if (!cleaned._row_id && st.type === 'dynamic_rows') {
          cleaned._row_id = genRowId()
        }
        return cleaned
      })
    } else {
      // 静态行预填充：把 static_rows[] 转成 row（首次加载）
      const initRows: RowData[] = []
      if (st.type === 'static_rows' && Array.isArray(st.static_rows)) {
        const labelField = labelColumnField(st)
        for (const def of st.static_rows) {
          const row: RowData = { id: def.id }
          if (labelField) row[labelField] = def.label
          initRows.push(row)
        }
      }
      result[st.id] = initRows
    }
  }
  subTableData.value = result

  // hidden_subtables（合并 schema 默认值 + 数据持久化值）
  const hidden = Array.isArray(data.hidden_subtables) ? data.hidden_subtables : []
  const defHidden = props.schema?.hidden_subtables?.default ?? []
  hiddenSubtables.value = Array.from(new Set([...defHidden, ...hidden]))

  // current_standard
  const std = (data.current_standard as string) || (props.schema?.applicable_standard as string) || ''
  currentStandardSubClass.value = deriveSubClassFromStandard(std)

  // context（金额单位等）
  const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
  const ctxOut: Record<string, any> = { _current_standard: std }
  for (const f of contextFields.value) {
    ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? f.default ?? ''
  }
  contextData.value = ctxOut

  // 默认展开所有可见子表
  activeCollapse.value = visibleSubTables.value.map(st => st.id)
}

initData()

watch(
  () => props.htmlData,
  () => {
    initData()
  },
  { deep: true },
)

watch(
  () => props.schema,
  () => {
    initData()
  },
  { deep: true },
)

// ─── Save payload + debounce ────────────────────────────────────────────────

function buildSavePayload(): CNoteTableHtmlData {
  const ctx: Record<string, any> = {}
  for (const k of Object.keys(contextData.value)) {
    if (k.startsWith('_')) continue
    ctx[k] = contextData.value[k]
  }
  const currentStandard = deriveStandardFromSubClass(
    currentStandardSubClass.value,
    contextData.value._current_standard as string,
  )
  // Strip internal markers from rows before persist
  const cleanedSubTables: Record<string, RowData[]> = {}
  for (const [id, rows] of Object.entries(subTableData.value)) {
    cleanedSubTables[id] = rows.map(r => {
      const out: RowData = {}
      for (const [k, v] of Object.entries(r)) {
        if (k === '_label' || k === '_is_grand_total' || k === '_is_subtotal' || k === '_indent') {
          continue
        }
        out[k] = v
      }
      return out
    })
  }
  return {
    ...(props.htmlData || {}),
    sub_table_data: cleanedSubTables,
    hidden_subtables: [...hiddenSubtables.value],
    current_standard: currentStandard,
    context: ctx,
  }
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', buildSavePayload())
  }, 1500)
}

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})

// Keep ElIcon used reference (template referenced above)
void ElIcon
</script>


<style scoped>
.gt-c-note-table {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

/* ── Header ── */
.gt-cnt__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}

.gt-cnt__header-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}

.gt-cnt__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-cnt__period,
.gt-cnt__section,
.gt-cnt__index {
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.gt-cnt__section strong,
.gt-cnt__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

.gt-cnt__header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── Context ── */
.gt-cnt__context {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 10px 14px;
  background: var(--gt-color-bg-white, #fff);
}

.gt-cnt__context-input,
.gt-cnt__context-select {
  width: 160px;
}

/* ── Hidden summary ── */
.gt-cnt__hidden-summary {
  margin-top: 4px;
}

.gt-cnt__hidden-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-cnt__hidden-label {
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.gt-cnt__hidden-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ── Collapse / sub cards ── */
.gt-cnt__collapse {
  border: none;
  background: transparent;
}

.gt-cnt__sub-card {
  margin-bottom: 6px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
}

.gt-cnt__sub-card :deep(.el-collapse-item__header) {
  padding: 0 12px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px 6px 0 0;
}

.gt-cnt__sub-card :deep(.el-collapse-item__content) {
  padding: 12px;
}

.gt-cnt__sub-title {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-cnt__sub-title-text {
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.gt-cnt__sub-badge {
  font-size: 11px;
}

.gt-cnt__sub-toggle {
  margin-left: auto;
  margin-right: 8px;
  color: var(--el-color-warning);
}

.gt-cnt__sub-desc {
  margin: 0 0 10px 0;
  padding: 6px 10px;
  background: var(--el-color-info-light-9);
  border-left: 3px solid var(--el-color-info-light-3);
  border-radius: 0 4px 4px 0;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.5;
}

/* ── Sub body ── */
.gt-cnt__sub-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-cnt__sub-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.gt-cnt__sub-table {
  width: 100%;
}

/* Static row styles */
.gt-cnt__sub-table :deep(.gt-cnt-row-grand-total) {
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}

.gt-cnt__sub-table :deep(.gt-cnt-row-subtotal) {
  background: var(--el-color-info-light-9);
  font-weight: 500;
}

.gt-cnt__cell-readonly {
  display: inline-block;
  width: 100%;
  padding: 0 4px;
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
}

.gt-cnt__indent-1 {
  padding-left: 16px;
}

.gt-cnt__indent-2 {
  padding-left: 32px;
}

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.gt-cnt__amount-input :deep(.el-input__inner) {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* ── Footer total ── */
.gt-cnt__sub-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  font-size: 13px;
}

.gt-cnt__footer-label {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-cnt__footer-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.gt-cnt__footer-col-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

/* ── Rule status ── */
.gt-cnt__rule-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
}

.gt-cnt__rule-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* ── Refs ── */
.gt-cnt__refs {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 10px 14px;
  background: var(--el-color-info-light-9);
}

.gt-cnt__refs-title {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.gt-cnt__refs-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-cnt__ref-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.gt-cnt__ref-desc {
  flex: 1;
}

/* ── Footer actions ── */
.gt-cnt__footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
}

.gt-cnt__hint-icon {
  color: var(--el-color-info);
  font-size: 14px;
}
</style>
