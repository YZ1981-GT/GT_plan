<template>
  <div class="g7-tab-financial-info">
    <div class="section-head">
      <h3 class="sheet-title">G7-5 被投资单位财务信息（合营、联营）</h3>
      <div class="head-actions">
        <el-dropdown trigger="click" :disabled="importExport.importing.value" @command="handleImportExportCommand">
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-5-financial-info')">💬复核</el-button>
        <GtIndexChip value="wp:G7-5" :context-project-id="projectId" />
      </div>
    </div>

    <div class="methodology-context">
      <p>被投资单位财务信息核实要点：</p>
      <p>• 核对被投资方报表关键指标（资产/负债/净资产/收入/利润），确认与被投资方提供的财务报表一致</p>
      <p>• 变动额 = 本年金额 - 上年金额；变动率 = 变动额 / 上年金额（上年为0时不计算）</p>
      <p>• 关注异常变动，作为权益法测算(G7-14)净利润调整的基础数据来源</p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实被投资单位财务信息（资产/负债/净资产/收入/利润）的完整性与准确性，为权益法测算(G7-14)提供可靠的基础数据。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="info">共 {{ rowCount }} 行 / {{ groups.length }} 家</el-tag>
        <el-tag v-if="warningCount" size="small" type="warning">{{ warningCount }} 项待补充</el-tag>
        <el-tag v-if="useGroupVirtual" size="small" type="success">虚拟滚动</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" size="small" @click="syncGroupsFromG74">从 G7-4 同步合营/联营</el-button>
        <el-button v-if="!isReadonly && groups.length" size="small" @click="handleRollForward">上年金额滚存</el-button>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="addNewGroup">+ 新增被投资单位</el-button>
      </div>
    </div>

    <el-alert
      v-if="unauditedStats.total > 0"
      type="warning"
      :closable="false"
      show-icon
      class="unaudited-alert"
      :title="unauditedBannerTitle"
    >
      未审/待确认数据默认不会带入 G7-14；请核实后改为「已审」，或在 G7-14 带入时勾选包含未审。
    </el-alert>

    <el-alert
      v-if="validationIssues.length"
      type="warning"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <div v-for="(issue, index) in validationIssues.slice(0, 8)" :key="`${issue.rowId}-${index}`">
        {{ issue.message }}
      </div>
      <div v-if="validationIssues.length > 8">……另有 {{ validationIssues.length - 8 }} 项</div>
    </el-alert>

    <div
      ref="scrollContainerRef"
      class="financial-scroll-container"
      @scroll.passive="onScrollContainer"
    >
      <div
        class="virtual-spacer"
        :style="useGroupVirtual ? { height: `${virtualWindow.totalHeight}px`, position: 'relative' } : undefined"
      >
        <div
          class="virtual-window"
          :style="useGroupVirtual ? { transform: `translateY(${virtualWindow.offsetY}px)` } : undefined"
        >
          <template v-for="group in renderedGroups" :key="group.investeeName">
            <div class="group-header" @click="toggleGroup(group.investeeName)">
              <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.investeeName] }">
                <ArrowDown />
              </el-icon>
              <span class="group-name">{{ group.investeeName }}</span>
              <span class="group-count">({{ group.rows.length }}行)</span>
              <div v-if="!isReadonly" class="group-actions" @click.stop>
                <el-button size="small" type="primary" link @click="addRowToGroup(group.investeeName)">
                  + 添加行
                </el-button>
              </div>
            </div>

            <div v-show="expandedMap[group.investeeName]" class="group-body">
              <el-table
                :data="group.rows"
                border
                size="small"
                class="financial-table"
                :max-height="400"
              >
                <el-table-column type="index" label="#" width="45" align="center" />
                <el-table-column label="报表项目" width="140" prop="reportItem">
                  <template #default="{ row }">
                    <el-input
                      v-if="!isReadonly"
                      v-model="row.reportItem"
                      size="small"
                      placeholder="如：总资产"
                      @change="persistRows"
                    />
                    <span v-else>{{ row.reportItem }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="上年金额" width="130" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!isReadonly"
                      :model-value="row.priorAmount"
                      size="small"
                      :controls="false"
                      style="width: 100%"
                      @update:model-value="(v: number) => updateAmount(row, 'priorAmount', v)"
                    />
                    <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="本年金额" width="130" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!isReadonly"
                      :model-value="row.currentAmount"
                      size="small"
                      :controls="false"
                      style="width: 100%"
                      @update:model-value="(v: number) => updateAmount(row, 'currentAmount', v)"
                    />
                    <span v-else>{{ fmtAmount(row.currentAmount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="变动额" width="120" align="right">
                  <template #default="{ row }">
                    <span class="formula-cell" title="变动额 = 本年金额 - 上年金额">{{ fmtAmount(row.changeAmount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="变动率" width="100" align="right">
                  <template #default="{ row }">
                    <span
                      class="formula-cell"
                      :class="{ 'rate-warning': isFinancialRateWarning(row.changeRate) }"
                      title="变动率 = 变动额 / 上年金额（上年为0时不计算）"
                    >{{ fmtRate(row.changeRate) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="分析说明" min-width="140">
                  <template #default="{ row }">
                    <el-input
                      v-if="!isReadonly"
                      v-model="row.analysisNote"
                      size="small"
                      :class="{ 'required-input': isFinancialRateWarning(row.changeRate) && !row.analysisNote }"
                      placeholder="变动原因分析"
                      @change="persistRows"
                    />
                    <span v-else>{{ row.analysisNote }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="数据来源" width="120">
                  <template #default="{ row }">
                    <el-input
                      v-if="!isReadonly"
                      v-model="row.dataSource"
                      size="small"
                      placeholder="如：年报"
                      @change="persistRows"
                    />
                    <span v-else>{{ row.dataSource }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="审计状态" width="100" align="center">
                  <template #default="{ row }">
                    <el-select
                      v-if="!isReadonly"
                      v-model="row.auditStatus"
                      size="small"
                      placeholder="状态"
                      @change="persistRows"
                    >
                      <el-option label="已审" value="已审" />
                      <el-option label="未审" value="未审" />
                      <el-option label="待确认" value="待确认" />
                    </el-select>
                    <el-tag v-else size="small" :type="auditStatusType(row.auditStatus)">
                      {{ row.auditStatus }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="备注" width="120">
                  <template #default="{ row }">
                    <el-input
                      v-if="!isReadonly"
                      v-model="row.remark"
                      size="small"
                      placeholder="备注"
                      @change="persistRows"
                    />
                    <span v-else>{{ row.remark }}</span>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
                  <template #default="{ $index }">
                    <el-button size="small" type="danger" link @click="deleteRow(group.investeeName, $index)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </div>
      </div>

      <div v-if="groups.length === 0" class="empty-state">
        <p>暂无被投资单位财务信息数据</p>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="addNewGroup">
          + 新增被投资单位
        </el-button>
        <el-button v-if="!isReadonly" size="small" @click="syncGroupsFromG74">从 G7-4 同步</el-button>
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、核对情况及结果，异常变动分析及数据来源核实情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除已调整事项外未见异常。C、存在重大未调整事项或审计范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 按被投资单位分组录入财务数据，每组包含资产/负债/净资产/收入/利润等关键指标</p>
        <p>2. 变动额 = 本年金额 - 上年金额（自动计算，公式列显示虚线下划线）</p>
        <p>3. 变动率 = 变动额 / 上年金额（上年为0时显示"—"不计算，避免除零错误）</p>
        <p>4. |变动率| > 50% 橙色高亮，须在"分析说明"列补充变动原因</p>
        <p>5. 数据来源建议注明：年报/审计报告/管理层提供/公开信息等</p>
        <p>6. 本表数据为 G7-14 权益法测算的基础输入；导入导出变动率按百分数填写</p>
      </div>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx" class="hidden-input" @change="handleFileChange">
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabFinancialInfo — G7-5 被投资单位财务信息（合营、联营）
 * 分组录入 + 变动额/率公式 + 校验 + IE + 版本链。
 */
import { reactive, ref, computed, inject, onMounted, nextTick, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import { G7_4_ROWS_KEY, loadEquityInvestees } from '../../composables/g7EquityMethodCrossSheet'
import {
  computeFinancialGroupVirtualWindow,
  countUnauditedFinancialRows,
  createDefaultFinancialGroup,
  createFinancialInfoRow,
  estimateFinancialGroupHeight,
  isFinancialRateWarning,
  parseFinancialInfoGroups,
  recalcFinancialInfoRow,
  rollForwardFinancialPriorAmounts,
  serializeFinancialInfoPayload,
  shouldUseFinancialGroupVirtual,
  validateFinancialInfoGroups,
  type G7FinancialInfoGroup,
  type G7FinancialInfoRow,
} from './g7FinancialInfoModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => !!props.readonly)
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const importExport = useG7EquityMethodImportExport({ wpId: computed(() => props.wpId) })

const ROWS_KEY = 'G7-5-rows'
const AUDIT_NOTE_KEY = 'G7-5-audit-note'
const AUDIT_CONCLUSION_KEY = 'G7-5-audit-conclusion'
const STORAGE_KEY_PREFIX = 'g7-financial-info-collapse-'

const groups = reactive<G7FinancialInfoGroup[]>([])
const expandedMap = reactive<Record<string, boolean>>({})
const auditNote = ref('')
const auditConclusion = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const scrollContainerRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewportHeight = ref(640)

const rowCount = computed(() => groups.reduce((n, g) => n + g.rows.length, 0))
const validationIssues = computed(() => validateFinancialInfoGroups(groups))
const warningCount = computed(() => validationIssues.value.length)
const unauditedStats = computed(() => countUnauditedFinancialRows(groups))
const unauditedBannerTitle = computed(() => {
  const { unaudited, pending, total } = unauditedStats.value
  const parts: string[] = []
  if (unaudited) parts.push(`未审 ${unaudited} 行`)
  if (pending) parts.push(`待确认 ${pending} 行`)
  return `尚有 ${total} 项未审数据（${parts.join('，')}）`
})
const useGroupVirtual = computed(() =>
  shouldUseFinancialGroupVirtual(groups.length, rowCount.value),
)
const groupHeights = computed(() =>
  groups.map(g => estimateFinancialGroupHeight(g, expandedMap[g.investeeName] !== false)),
)
const virtualWindow = computed(() =>
  computeFinancialGroupVirtualWindow(groupHeights.value, scrollTop.value, viewportHeight.value),
)
const renderedGroups = computed(() => {
  if (!useGroupVirtual.value) return groups
  return groups.slice(virtualWindow.value.start, virtualWindow.value.end)
})

function onScrollContainer(event: Event): void {
  const el = event.target as HTMLElement
  scrollTop.value = el.scrollTop
  viewportHeight.value = el.clientHeight || 640
}

function getStorageKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw) Object.assign(expandedMap, JSON.parse(raw) as Record<string, boolean>)
  } catch { /* ignore */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore */ }
}

function toggleGroup(name: string): void {
  expandedMap[name] = !expandedMap[name]
  saveCollapseState()
}

function persistRows(): void {
  if (isReadonly.value) return
  formData.debouncedSave(ROWS_KEY, {
    conclusion: serializeFinancialInfoPayload(groups),
    remark: null,
  })
}

function updateAmount(row: G7FinancialInfoRow, field: 'priorAmount' | 'currentAmount', value: number): void {
  row[field] = value ?? 0
  recalcFinancialInfoRow(row)
  persistRows()
}

function addRowToGroup(groupName: string): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return
  group.rows.push(createFinancialInfoRow(groupName, group.rows.length + 1))
  persistRows()
}

function deleteRow(groupName: string, index: number): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return
  group.rows.splice(index, 1)
  group.rows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

async function addNewGroup(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    const name = value.trim()
    if (groups.some(g => g.investeeName === name)) {
      ElMessage.warning(`被投资单位"${name}"已存在`)
      return
    }
    const group = createDefaultFinancialGroup(name)
    groups.push(group)
    expandedMap[name] = true
    saveCollapseState()
    persistRows()
  } catch { /* cancel */ }
}

async function handleRollForward(): Promise<void> {
  if (isReadonly.value || !groups.length) return
  try {
    await ElMessageBox.confirm(
      '将各行「本年金额」写入「上年金额」。是否同时清空本年金额（适合新年度开账）？',
      '上年金额滚存',
      {
        distinguishCancelAndClose: true,
        confirmButtonText: '滚存并清空本年',
        cancelButtonText: '仅滚存保留本年',
        type: 'info',
      },
    )
    const n = rollForwardFinancialPriorAmounts(groups, { clearCurrent: true })
    persistRows()
    ElMessage.success(`已滚存 ${n} 行（本年已清空）`)
  } catch (action) {
    if (action === 'cancel') {
      const n = rollForwardFinancialPriorAmounts(groups, { clearCurrent: false })
      persistRows()
      ElMessage.success(`已滚存 ${n} 行（本年金额保留）`)
    }
  }
}

function syncGroupsFromG74(): void {
  const investees = loadEquityInvestees(formData.data.value.get(G7_4_ROWS_KEY)?.conclusion)
  if (investees.length === 0) {
    ElMessage.warning('G7-4 中暂无合营/联营企业，请先维护基本信息')
    return
  }
  let added = 0
  let linked = 0
  for (const inv of investees) {
    const existing = groups.find(g =>
      (inv.investeeId && g.investeeId === inv.investeeId) || g.investeeName === inv.name,
    )
    if (existing) {
      if (inv.investeeId && !existing.investeeId) {
        existing.investeeId = inv.investeeId
        linked++
      }
      continue
    }
    const group = createDefaultFinancialGroup(inv.name, inv.investeeId)
    groups.push(group)
    expandedMap[inv.name] = true
    added++
  }
  if (added === 0 && linked === 0) {
    ElMessage.info('合营/联营单位已全部同步，无需新增')
    return
  }
  saveCollapseState()
  persistRows()
  ElMessage.success(
    added > 0
      ? `已从 G7-4 新增 ${added} 个被投资单位分组`
      : `已为 ${linked} 个现有分组回填被投资单位ID`,
  )
}

function hydrateGroups(parsed: G7FinancialInfoGroup[]): void {
  groups.splice(0, groups.length, ...parsed)
  for (const g of groups) {
    if (expandedMap[g.investeeName] === undefined) expandedMap[g.investeeName] = true
  }
}

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (isReadonly.value) return
  auditConclusion.value = val
  formData.debouncedSave(AUDIT_CONCLUSION_KEY, { remark: val, conclusion: null })
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void importExport.exportTemplate('G7-5')
  if (command === 'export') void importExport.exportData('G7-5')
  if (command === 'import') fileInputRef.value?.click()
}

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-5', file)
  if (!result) return
  await formData.loadResponses()
  hydrateGroups(parseFinancialInfoGroups(formData.data.value.get(ROWS_KEY)?.conclusion))
}

function fmtRate(v: number | null): string {
  if (v == null) return '—'
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- percentage display
  return `${(v * 100).toFixed(2)}%`
}

function auditStatusType(status: string): '' | 'success' | 'warning' | 'info' {
  switch (status) {
    case '已审': return 'success'
    case '未审': return 'info'
    case '待确认': return 'warning'
    default: return ''
  }
}

watch([() => groups.length, rowCount], async () => {
  await nextTick()
  if (scrollContainerRef.value) {
    viewportHeight.value = scrollContainerRef.value.clientHeight || 640
  }
})

onMounted(async () => {
  loadCollapseState()
  await formData.load()
  const saved = parseFinancialInfoGroups(formData.data.value.get(ROWS_KEY)?.conclusion)
  if (saved.length) {
    hydrateGroups(saved)
  } else {
    const data = props.htmlData
    const financialInfo = data?.financialInfo ?? data?.financial_info ?? data
    hydrateGroups(parseFinancialInfoGroups(financialInfo))
  }
  auditNote.value = formData.data.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
  auditConclusion.value = formData.data.value.get(AUDIT_CONCLUSION_KEY)?.remark ?? ''
  await nextTick()
  if (scrollContainerRef.value) {
    viewportHeight.value = scrollContainerRef.value.clientHeight || 640
  }
})
</script>

<style scoped>
.g7-tab-financial-info { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert, .validation-alert, .unaudited-alert { margin-bottom: 12px; }
.conclusion-card { margin-top: 16px; }
.section-head, .tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions, .toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p { margin: 2px 0; }
.virtual-spacer { min-height: 0; }
.virtual-window { will-change: transform; }
.financial-scroll-container {
  max-height: calc(57 * 34px + 120px);
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 4px;
}
.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  margin-top: 8px;
  cursor: pointer;
  user-select: none;
}
.group-header:first-child { margin-top: 0; }
.group-header:hover { background: #d9ecff; }
.group-name { font-weight: 600; color: #303133; }
.group-count { font-size: 12px; color: #909399; }
.group-actions { margin-left: auto; }
.collapse-icon { transition: transform 0.2s; font-size: 14px; }
.collapse-icon.is-collapsed { transform: rotate(-90deg); }
.group-body { margin-bottom: 4px; }
.financial-table { margin-top: 4px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warning { color: #e6a23c; font-weight: 600; }
.required-input :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.empty-state { text-align: center; padding: 40px 20px; color: #909399; }
.empty-state p { margin-bottom: 12px; }
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-content p { margin: 4px 0; }
.hidden-input { display: none; }
</style>
