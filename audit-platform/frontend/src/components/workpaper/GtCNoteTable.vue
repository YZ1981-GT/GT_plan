<!-- GtCNoteTable.vue — C 类附注披露嵌套表 shell -->

<template>
  <div class="gt-c-note-table" :class="{ 'gt-fullscreen': isFullscreen }">
    <!-- 空态：schema 未配置时显示提示 -->
    <el-empty
      v-if="!allSubTables.length && !contextFields.length"
      :image-size="80"
      description="附注披露表尚未配置，请等待模板初始化完成"
      class="gt-cnt__empty"
    />

    <template v-else>
    <!-- 工具栏：全屏/公式/导入/导出 -->
    <div class="gt-cnt__toolbar">
      <div class="gt-cnt__toolbar-title">附注披露</div>
      <div class="gt-cnt__toolbar-actions">
        <el-button size="small" @click="toggleFullscreen">
          {{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}
        </el-button>
        <el-button size="small" :disabled="readonly" @click="onOpenFormula">
          ƒx 公式
        </el-button>
        <el-button size="small" @click="onExportTemplate">
          📥 导出模板
        </el-button>
        <el-button size="small" @click="onExportData">
          📥 导出数据
        </el-button>
        <el-button size="small" :disabled="readonly" @click="triggerImport">
          📤 导入
        </el-button>
      </div>
    </div>

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

    <!-- 上下文字段 -->
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

    <!-- 隐藏子表恢复区 -->
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

    <!-- 子表卡片列表 -->
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

        <p v-if="st.description" class="gt-cnt__sub-desc">{{ st.description }}</p>

        <CNoteSubTableCard
          :sub-table="st"
          :rows="st.type === 'static_rows' ? getStaticRowsView(st) : dynamicRowsView(st)"
          :readonly="readonly"
          :visible-columns="visibleColumns(st)"
          :cell-computed-value="cellComputedValue"
          :footer-columns="footerTotalColumns(st)"
          :footer-value="(col) => footerTotalValue(st, col)"
          :reached-max="reachedMaxRows(st)"
          @cell-change="(row, col) => onCellChange(st, row, col)"
          @add-row="onAddDynamicRow(st)"
          @remove-row="(i) => onRemoveDynamicRow(st, i)"
        />

        <CNoteInheritanceBadge :statuses="ruleStatusForSubTable(st.id)" />
      </el-collapse-item>
    </el-collapse>

    <!-- 引用来源 -->
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

    <!-- 同步附注 -->
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

    <!-- 隐藏文件选择器（导入触发） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="onFileImport"
    />

    <!-- 导入预览弹窗 -->
    <el-dialog
      v-model="importVisible"
      title="导入附注披露数据"
      width="640px"
      append-to-body
    >
      <div v-if="importStats">
        <p>
          解析结果：匹配 <b>{{ importStats.matched }}</b> 行，跳过 <b>{{ importStats.skipped }}</b> 行
        </p>
        <el-table v-if="importPreviewRows.length" :data="importPreviewRows" border size="small" max-height="250">
          <el-table-column v-for="(val, key) in importPreviewRows[0]" :key="String(key)" :prop="String(key)" :label="String(key)" min-width="120" show-overflow-tooltip />
        </el-table>
      </div>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importStats?.matched" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>

    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef } from 'vue'
import { useRoute } from 'vue-router'
import {
  ElMessageBox,
  ElMessage,
} from 'element-plus'
import {
  Upload as UploadIcon,
  InfoFilled,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import CNoteSubTableCard from './cnote/CNoteSubTableCard.vue'
import CNoteInheritanceBadge from './cnote/CNoteInheritanceBadge.vue'
import { formatAmount } from '@/utils/formatAmount'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import type {
  SubClass,
  ColumnDefWithKey,
  SubTableSchema,
  ContextField,
  CrossRefDef,
  LinkageDownstreamRule,
  CNoteTableSchema,
  RowData,
  CNoteTableHtmlData,
  SyncPayload,
} from './GtCNoteTable.types'
import {
  deriveStandardFromSubClass,
  staticRowsView,
  buildEmptyRow,
  labelColumnField,
} from './cnote/cnoteHelpers'
import { useCNoteFormula } from './cnote/composables/useCNoteFormula'
import { useCNoteInheritance } from './cnote/composables/useCNoteInheritance'
import { useCNotePersist } from './cnote/composables/useCNotePersist'
import { useFullscreen } from '@/composables/useFullscreen'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'

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
  'open-formula': [payload: { sheetName: string }]
}>()

const subTableData = ref<Record<string, RowData[]>>({})
const hiddenSubtables = ref<string[]>([])
const contextData = ref<Record<string, any>>({})
const currentStandardSubClass = ref<SubClass>('listed')
const activeCollapse = ref<string[]>([])
const isSyncing = ref(false)
const route = useRoute()

const { cellComputedValue, footerTotalColumns, footerTotalValue } = useCNoteFormula(subTableData, currentStandardSubClass)
const { ruleStatuses, ruleStatusForSubTable } = useCNoteInheritance(toRef(props, 'schema'), subTableData, currentStandardSubClass)

const fixedCells = computed(() => props.schema?.fixed_cells ?? {})
const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(() => fixedCells.value?.I3 || fixedCells.value?.H3 || fixedCells.value?.J3 || '')
const contextFields = computed<ContextField[]>(() => Array.isArray(props.schema?.fields) ? props.schema.fields : [])

const sectionId = computed<string>(() => {
  const sec = contextData.value?.section_id
  if (sec) return String(sec)
  const def = contextFields.value.find(f => f.name === 'section_id')
  return def?.default ? String(def.default) : ''
})

const versionVariants = computed(() => props.schema?.version_variants ?? {})
const standardLabel = computed(() => versionVariants.value[currentStandardSubClass.value]?.label || '')
const standardTagType = computed<'success' | 'warning' | 'info'>(() =>
  currentStandardSubClass.value === 'listed' ? 'success' : currentStandardSubClass.value === 'soe' ? 'warning' : 'info')
const standardSwitchable = computed(() => !!(versionVariants.value.listed || versionVariants.value.soe))

const allSubTables = computed<SubTableSchema[]>(() => {
  const arr = props.schema?.sub_tables ?? []
  return Array.isArray(arr) ? [...arr].sort((a, b) => (a.order ?? 999) - (b.order ?? 999)) : []
})

const visibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st =>
    !(st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub))
    && !hiddenSubtables.value.includes(st.id))
})

const hiddenVisibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st =>
    !(st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub))
    && hiddenSubtables.value.includes(st.id))
})

const autoPullRefs = computed<CrossRefDef[]>(() => {
  const arr = props.schema?.cross_refs ?? []
  return Array.isArray(arr) ? arr.filter(r => r.auto_pull && r.direction === 'inbound') : []
})

const downstreamRules = computed<LinkageDownstreamRule[]>(() => {
  const arr = props.schema?.linkage?.downstream
  return Array.isArray(arr) ? arr : []
})
const hasSyncDownstream = computed(() => downstreamRules.value.some(r => r.target === 'disclosure_notes'))

function visibleColumns(st: SubTableSchema): ColumnDefWithKey[] {
  const sub = currentStandardSubClass.value
  return Object.entries(st.columns ?? {})
    .filter(([, col]) => !(col.applicable_to_sub_class && !col.applicable_to_sub_class.includes(sub)))
    .map(([cell, col]) => ({ ...col, _cellKey: cell }))
}

function subClassBadges(st: SubTableSchema): Array<{ value: string; label: string; type: 'success' | 'warning' | 'info' }> {
  const arr = st.applicable_to_sub_class
  if (!arr || arr.length !== 1) return []
  if (arr[0] === 'listed') return [{ value: 'listed', label: '上市专属', type: 'success' }]
  if (arr[0] === 'soe') return [{ value: 'soe', label: '国企专属', type: 'warning' }]
  return []
}

function subTableRowCount(stId: string): number { return subTableData.value[stId]?.length ?? 0 }
function reachedMaxRows(st: SubTableSchema): boolean { return (subTableData.value[st.id]?.length ?? 0) >= (st.max_rows ?? 100) }

function getStaticRowsView(st: SubTableSchema): RowData[] {
  return staticRowsView(st, subTableData.value[st.id] ?? [], visibleColumns(st))
}

function dynamicRowsView(st: SubTableSchema): RowData[] { return subTableData.value[st.id] ?? [] }

const { initData, buildSavePayload, debounceSave } = useCNotePersist({ props, subTableData, hiddenSubtables, currentStandardSubClass, contextData, activeCollapse, sectionId, allSubTables, contextFields, visibleSubTables, labelColumnField: (st: SubTableSchema) => labelColumnField(st, visibleColumns(st)), emit })

// ─── 工具栏：全屏 / 公式 / 导入导出 ─────────────────────────────────────
const { isFullscreen, toggleFullscreen } = useFullscreen()
const { exportTemplate: _exportTemplate, onFileSelected: _onFileSelected } = useExcelIO()
const fileInputRef = ref<HTMLInputElement | null>(null)
const importVisible = ref(false)
const importStats = ref<{ matched: number; skipped: number } | null>(null)
const importPreviewRows = ref<any[]>([])
const importParsedMap = ref<Map<string, { stId: string; rows: Record<string, any>[] }>>(new Map())

function onOpenFormula() {
  if (props.readonly) return
  emit('open-formula', { sheetName: props.sheetName })
}

/** 构建所有可见子表的导出行（含子表标题分隔） */
function _buildExportRows(includeData: boolean): { rows: any[][]; maxCols: number; columns: ExcelColumn[] } {
  let maxCols = 1
  const rows: any[][] = []
  // 先计算最大列数
  for (const st of visibleSubTables.value) {
    const cols = visibleColumns(st)
    if (cols.length > maxCols) maxCols = cols.length
  }
  for (const st of visibleSubTables.value) {
    const cols = visibleColumns(st)
    // 子表标题行（作为段落分隔，填满列避免样式越界）
    const titleRow: any[] = [`【${st.title}】`]
    while (titleRow.length < maxCols) titleRow.push('')
    rows.push(titleRow)
    // 子表说明（description 作为填写指引）
    if (st.description) {
      const descRow: any[] = [`说明：${st.description}`]
      while (descRow.length < maxCols) descRow.push('')
      rows.push(descRow)
    }
    // 列标题行（补齐到 maxCols）
    const headerRow = cols.map(c => c.label)
    while (headerRow.length < maxCols) headerRow.push('')
    rows.push(headerRow)
    if (includeData) {
      // 带数据导出：填入当前子表数据
      const data = st.type === 'static_rows' ? getStaticRowsView(st) : dynamicRowsView(st)
      for (const r of data) {
        const row = cols.map(c => r[c.field] ?? '')
        while (row.length < maxCols) row.push('')
        rows.push(row)
      }
    } else {
      // 空模板：静态行填行名，动态行留空占位 + 提示
      if (st.type === 'static_rows' && st.static_rows) {
        for (const sr of st.static_rows) {
          const row: any[] = [sr.label]
          while (row.length < maxCols) row.push('')
          rows.push(row)
        }
      } else {
        // 动态行：留 3 行空占位
        for (let i = 0; i < 3; i++) {
          const row: any[] = []
          while (row.length < maxCols) row.push('')
          rows.push(row)
        }
        const tipRow: any[] = [`（可按需增加行，列名请勿修改）`]
        while (tipRow.length < maxCols) tipRow.push('')
        rows.push(tipRow)
      }
    }
    // 空行分隔（补齐）
    const emptyRow: any[] = []
    while (emptyRow.length < maxCols) emptyRow.push('')
    rows.push(emptyRow)
  }
  // 构建 columns 定义（第一列宽，其余窄）
  const columns: ExcelColumn[] = Array.from({ length: maxCols }, (_, i) => ({
    key: String.fromCharCode(65 + (i % 26)) + (i >= 26 ? String(Math.floor(i / 26)) : ''),
    header: i === 0 ? '项目' : `列${i + 1}`,
    width: i === 0 ? 30 : 16,
  }))
  return { rows, maxCols, columns }
}

/**
 * 导出空模板：带子表说明 + 列标题 + 填写指引，供离线填写。
 * 静态行带行名预填（如"银行承兑汇票"/"合计"），动态行留空占位。
 */
async function onExportTemplate() {
  const { rows, columns } = _buildExportRows(false)
  await _exportTemplate({
    columns,
    sheetName: '附注披露模板',
    fileName: `附注披露模板_${props.sheetName || sectionId.value || '模板'}.xlsx`,
    existingData: rows,
    includeNoteRow: false,
    applyStyles: false,
    includeInstructions: true,
    instructionTitle: '附注披露 — 填写说明',
    instructionRows: [
      ['1. 每个【子表标题】下方是一张独立的披露表，按列标题填写金额'],
      ['2. 静态行（银行承兑汇票/商业承兑汇票/合计等）已预填行名，请勿修改行名，直接填数字'],
      ['3. 动态行（单项计提明细/核销明细等）可自由增删行，系统按列名匹配导入'],
      ['4. 金额列填数字（不带逗号/货币符号），百分比列填数字（如 5 表示 5%）'],
      ['5. 导入时系统按【子表标题】定位到对应子表，按行名或新增行匹配写回'],
    ],
  })
}

/**
 * 导出数据：带当前已填金额的完整披露表（含所有子表当前值）。
 */
async function onExportData() {
  const { rows, columns } = _buildExportRows(true)
  await _exportTemplate({
    columns,
    sheetName: '附注披露',
    fileName: `附注披露_${props.sheetName || sectionId.value || '导出'}.xlsx`,
    existingData: rows,
    includeNoteRow: false,
    applyStyles: false,
    includeInstructions: false,
  })
}

function triggerImport() {
  if (props.readonly) return
  fileInputRef.value?.click()
}

/**
 * 导入解析：按【子表标题】定位目标子表 → 按列名匹配 → 静态行按行名写回，动态行新增。
 * 支持一个 xlsx 同时含多张子表数据（子表标题行分隔）。
 */
async function onFileImport(e: Event) {
  if (props.readonly) return
  await _onFileSelected(
    e,
    (result) => {
      let matched = 0
      let skipped = 0
      const parsed = new Map<string, { stId: string; rows: Record<string, any>[] }>()

      // 解析策略：扫描行，遇到【子表标题】→ 切换目标子表 → 后续行按列名匹配
      let currentSt: SubTableSchema | null = null
      let currentCols: ColumnDefWithKey[] = []
      let headerRow: string[] = []
      let expectHeader = false

      for (const r of result.rows) {
        const firstCell = String(r[result.headers[0]] ?? '').trim()

        // 检测子表标题行（形如「【子表标题】」或以 ── 开头）
        if (firstCell.startsWith('【') && firstCell.endsWith('】')) {
          const title = firstCell.slice(1, -1)
          currentSt = visibleSubTables.value.find(st => st.title === title) || null
          if (currentSt) {
            currentCols = visibleColumns(currentSt)
            if (!parsed.has(currentSt.id)) {
              parsed.set(currentSt.id, { stId: currentSt.id, rows: [] })
            }
          }
          expectHeader = true
          continue
        }

        // 跳过说明行（"说明：..."）
        if (firstCell.startsWith('说明：') || firstCell.startsWith('（可按需')) {
          continue
        }

        // 列标题行（匹配后设为当前 header mapping）
        if (expectHeader && currentSt) {
          // 检测当前行是否像列标题（至少 2 个 header 标签命中）
          const rowVals = result.headers.map(h => String(r[h] ?? '').trim())
          const hitCount = rowVals.filter(v => currentCols.some(c => c.label === v)).length
          if (hitCount >= 2) {
            headerRow = rowVals
            expectHeader = false
            continue
          }
        }

        // 数据行：按列标题映射到字段
        if (currentSt && headerRow.length && currentCols.length) {
          const row: Record<string, any> = {}
          let hasData = false
          for (let i = 0; i < headerRow.length; i++) {
            const colLabel = headerRow[i]
            const col = currentCols.find(c => c.label === colLabel)
            if (!col) continue
            const val = r[result.headers[i]]
            if (val != null && val !== '') {
              row[col.field] = val
              hasData = true
            }
          }
          if (hasData) {
            parsed.get(currentSt.id)!.rows.push(row)
            matched++
          } else {
            skipped++
          }
        } else {
          skipped++
        }
      }

      importParsedMap.value = parsed
      importStats.value = { matched, skipped }
      // 预览：取前 10 行跨所有子表
      const preview: any[] = []
      for (const [stId, { rows: pRows }] of parsed) {
        const st = visibleSubTables.value.find(s => s.id === stId)
        for (const r of pRows.slice(0, 5)) {
          preview.push({ _子表: st?.title || stId, ...r })
        }
      }
      importPreviewRows.value = preview.slice(0, 10)
      importVisible.value = true
    },
    { sheetName: '附注披露模板', skipRows: 0 },
  )
}

/**
 * 确认导入：按子表 ID 写回数据。
 * - 静态行：按行名（labelColumnField）匹配已有行并覆盖数值列；
 * - 动态行：全部追加为新行（或按名称列去重覆盖）。
 */
function confirmImport() {
  if (props.readonly) return
  let totalImported = 0

  for (const [stId, { rows: importRows }] of importParsedMap.value) {
    const st = visibleSubTables.value.find(s => s.id === stId)
    if (!st) continue
    const cols = visibleColumns(st)
    const labelField = labelColumnField(st, cols)

    if (!subTableData.value[stId]) subTableData.value[stId] = []

    if (st.type === 'static_rows' && labelField) {
      // 静态行：按 label 匹配覆盖数值列
      for (const importRow of importRows) {
        const label = importRow[labelField]
        if (!label) continue
        const existing = subTableData.value[stId].find(r => r[labelField] === label)
        if (existing) {
          // 覆盖数值列（非 label/id/readonly）
          for (const col of cols) {
            if (col.field === labelField || col.readonly) continue
            if (importRow[col.field] != null && importRow[col.field] !== '') {
              existing[col.field] = importRow[col.field]
            }
          }
          totalImported++
        }
      }
    } else {
      // 动态行：追加
      for (const importRow of importRows) {
        const newRow = buildEmptyRow(st, cols, subTableData.value[stId].length)
        Object.assign(newRow, importRow)
        subTableData.value[stId].push(newRow)
        totalImported++
      }
    }
  }

  importVisible.value = false
  importStats.value = null
  importParsedMap.value = new Map()
  importPreviewRows.value = []
  debounceSave()
  ElMessage.success(`已导入 ${totalImported} 行数据到对应子表`)
}

function onCellChange(_st: SubTableSchema, _row: RowData, _col: ColumnDefWithKey) { debounceSave() }

function onAddDynamicRow(st: SubTableSchema) {
  if (reachedMaxRows(st)) return
  if (!subTableData.value[st.id]) subTableData.value[st.id] = []
  subTableData.value[st.id].push(buildEmptyRow(st, visibleColumns(st), subTableData.value[st.id].length))
  debounceSave()
}
function onRemoveDynamicRow(st: SubTableSchema, idx: number) {
  const rows = subTableData.value[st.id]
  if (!rows) return
  rows.splice(idx, 1)
  if (Object.values(st.columns ?? {}).some(c => c.field === 'seq'))
    rows.forEach((r, i) => { r.seq = i + 1 })
  debounceSave()
}
async function onHideSubTable(stId: string) {
  if (props.readonly) return
  try {
    await ElMessageBox.confirm('将此子表标记为「不适用」？标记后子表将折叠隐藏，但数据保留可恢复。', '标记不适用', { confirmButtonText: '确认标记', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  if (!hiddenSubtables.value.includes(stId)) hiddenSubtables.value.push(stId)
  activeCollapse.value = activeCollapse.value.filter(id => id !== stId)
  emit('subtable-toggle', stId)
  debounceSave()
}
function onRestoreSubTable(stId: string) {
  if (props.readonly) return
  hiddenSubtables.value = hiddenSubtables.value.filter(id => id !== stId)
  if (!activeCollapse.value.includes(stId)) activeCollapse.value.push(stId)
  emit('subtable-toggle', stId)
  debounceSave()
}
async function onStandardSwitch(newSub: string | number | boolean | undefined) {
  const target = String(newSub) as SubClass
  if (target !== 'listed' && target !== 'soe') return
  const requested = target
  const previous: SubClass = requested === 'listed' ? 'soe' : 'listed'
  const lostSubTables = allSubTables.value.filter(st => st.applicable_to_sub_class?.includes(previous) && !st.applicable_to_sub_class?.includes(requested))
  const gainedSubTables = allSubTables.value.filter(st => !st.applicable_to_sub_class?.includes(previous) && st.applicable_to_sub_class?.includes(requested))
  const messages: string[] = []
  if (lostSubTables.length) messages.push(`将隐藏 ${lostSubTables.length} 张${previous === 'listed' ? '上市' : '国企'}专属子表（数据保留）：${lostSubTables.map(s => s.title).join('、')}`)
  if (gainedSubTables.length) messages.push(`将显示 ${gainedSubTables.length} 张${requested === 'listed' ? '上市' : '国企'}专属子表：${gainedSubTables.map(s => s.title).join('、')}`)
  messages.push('共有字段值会保留，仅差异字段切换显示。')
  try {
    await ElMessageBox.confirm(messages.join('\n'), `切换到${requested === 'listed' ? '上市公司版' : '国企版'}`, { confirmButtonText: '确认切换', cancelButtonText: '取消', type: 'info' })
  } catch { currentStandardSubClass.value = previous; return }
  currentStandardSubClass.value = requested
  const newStandard = deriveStandardFromSubClass(requested, contextData.value._current_standard as string)
  contextData.value._current_standard = newStandard
  emit('standard-switch', newStandard)
  debounceSave()
}
function onJumpToReference(refCode: string) { if (refCode) emit('jump-to-reference', refCode) }
async function onSyncToDisclosureNotes() {
  if (!sectionId.value) { ElMessage.warning('未配置附注章节号（section_id），无法同步'); return }
  const payload: SyncPayload = { wp_id: props.wpId, sheet_name: props.sheetName, section_id: sectionId.value, sub_table_data: { ...subTableData.value }, current_standard: deriveStandardFromSubClass(currentStandardSubClass.value, contextData.value._current_standard as string) }
  emit('sync-to-disclosure-notes', payload)
  const projectId = route.params?.projectId as string | undefined
  if (!projectId) return
  if (isSyncing.value) return
  isSyncing.value = true
  try {
    const result: any = await api.post(`/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步 ${Number(result?.rows_synced ?? 0)} 行到附注模块「${sectionId.value}」`)
  } catch (err: any) {
    handleApiError(err, '同步附注')
  } finally { isSyncing.value = false }
}

function onContextChange(_name: string) { debounceSave() }

// ─── wp-locate-foundation Task 3.2: 暴露 scrollToRow 定位接口 ───
function scrollToRow(index: number) {
  const container = document.querySelector('.gt-c-note-table')
  if (!container) return
  const rows = container.querySelectorAll('.el-table__body .el-table__row')
  if (index >= 0 && index < rows.length) {
    rows[index].scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

defineExpose({ scrollToRow })

initData()
watch(() => props.htmlData, () => { initData() }, { deep: true })
watch(() => props.schema, () => { initData() }, { deep: true })
</script>


<style scoped>
.gt-c-note-table { display: flex; flex-direction: column; gap: 14px; padding: 16px; }
.gt-cnt__toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.gt-cnt__toolbar-title { font-size: var(--gt-font-size-base, 14px); font-weight: 600; color: var(--gt-color-primary); }
.gt-cnt__toolbar-actions { display: flex; align-items: center; gap: 8px; }
.gt-cnt__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 10px 14px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-cnt__header-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
.gt-cnt__entity { font-weight: 600; color: var(--el-text-color-primary); }
.gt-cnt__period, .gt-cnt__section, .gt-cnt__index { color: var(--el-text-color-regular); font-size: 12px; }
.gt-cnt__section strong, .gt-cnt__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-cnt__header-actions { display: flex; align-items: center; gap: 10px; }
.gt-cnt__context { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 14px; background: var(--gt-color-bg-white, #fff); }
.gt-cnt__context-input, .gt-cnt__context-select { width: 160px; }
.gt-cnt__hidden-summary { margin-top: 4px; }
.gt-cnt__hidden-list { display: flex; flex-direction: column; gap: 6px; }
.gt-cnt__hidden-label { font-weight: 600; color: var(--el-text-color-regular); }
.gt-cnt__hidden-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gt-cnt__collapse { border: none; background: transparent; }
.gt-cnt__sub-card { margin-bottom: 6px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--gt-color-bg-white, #fff); }
.gt-cnt__sub-card :deep(.el-collapse-item__header) { padding: 0 12px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px 6px 0 0; }
.gt-cnt__sub-card :deep(.el-collapse-item__content) { padding: 12px; }
.gt-cnt__sub-title { display: flex; flex: 1; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-cnt__sub-title-text { font-weight: 600; color: var(--el-text-color-primary); font-size: 14px; }
.gt-cnt__sub-badge { font-size: 11px; }
.gt-cnt__sub-toggle { margin-left: auto; margin-right: 8px; color: var(--el-color-warning); }
.gt-cnt__sub-desc { margin: 0 0 10px 0; padding: 6px 10px; background: var(--el-color-info-light-9); border-left: 3px solid var(--el-color-info-light-3); border-radius: 0 4px 4px 0; color: var(--el-text-color-regular); font-size: 12px; line-height: 1.5; }
.gt-cnt__refs { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 14px; background: var(--el-color-info-light-9); }
.gt-cnt__refs-title { margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }
.gt-cnt__refs-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.gt-cnt__ref-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--el-text-color-regular); }
.gt-cnt__ref-desc { flex: 1; }
.gt-cnt__footer-actions { display: flex; align-items: center; gap: 8px; padding-top: 8px; }
.gt-cnt__hint-icon { color: var(--el-color-info); font-size: 14px; }
</style>
