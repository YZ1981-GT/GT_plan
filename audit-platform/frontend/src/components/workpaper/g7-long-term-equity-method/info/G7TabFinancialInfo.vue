<template>
  <div class="g7-tab-financial-info">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-5 被投资单位财务信息（合营、联营）</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G7-5-financial-info')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p>被投资单位财务信息核实要点：</p>
      <p>• 核对被投资方报表关键指标（资产/负债/净资产/收入/利润），确认与被投资方提供的财务报表一致</p>
      <p>• 变动额 = 本年金额 - 上年金额；变动率 = 变动额 / 上年金额（上年为0时不计算）</p>
      <p>• 关注异常变动，作为权益法测算(G7-14)净利润调整的基础数据来源</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实被投资单位财务信息（资产/负债/净资产/收入/利润）的完整性与准确性，为权益法测算(G7-14)提供可靠的基础数据。"
      class="objective-alert"
    />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <!-- 57行分组虚拟滚动容器 -->
    <div class="financial-scroll-container">
      <template v-for="group in groups" :key="group.investeeName">
        <!-- 分组标题 -->
        <div class="group-header" @click="toggleGroup(group.investeeName)">
          <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.investeeName] }">
            <ArrowDown />
          </el-icon>
          <span class="group-name">{{ group.investeeName }}</span>
          <span class="group-count">({{ group.rows.length }}行)</span>
          <div class="group-actions" v-if="!isReadonly" @click.stop>
            <el-button size="small" type="primary" link @click="addRowToGroup(group.investeeName)">
              + 添加行
            </el-button>
          </div>
        </div>

        <!-- 分组表格 -->
        <div v-show="expandedMap[group.investeeName]" class="group-body">
          <el-table
            :data="group.rows"
            border
            size="small"
            class="financial-table"
            :max-height="400"
          >
            <!-- 序号 -->
            <el-table-column type="index" label="#" width="45" align="center" />

            <!-- 报表项目 -->
            <el-table-column label="报表项目" width="140" prop="reportItem">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.reportItem"
                  size="small"
                  placeholder="如：总资产"
                  @change="handleCellChange(group.investeeName, row)"
                />
                <span v-else>{{ row.reportItem }}</span>
              </template>
            </el-table-column>

            <!-- 上年金额 -->
            <el-table-column label="上年金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorAmount"
                  size="small"
                  :controls="false"
                  style="width: 100%"
                  @update:model-value="(v: number) => updateAmount(group.investeeName, row, 'priorAmount', v)"
                />
                <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
              </template>
            </el-table-column>

            <!-- 本年金额 -->
            <el-table-column label="本年金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.currentAmount"
                  size="small"
                  :controls="false"
                  style="width: 100%"
                  @update:model-value="(v: number) => updateAmount(group.investeeName, row, 'currentAmount', v)"
                />
                <span v-else>{{ fmtAmount(row.currentAmount) }}</span>
              </template>
            </el-table-column>

            <!-- 变动额（公式列） -->
            <el-table-column label="变动额" width="120" align="right">
              <template #default="{ row }">
                <span
                  class="formula-cell"
                  :title="'变动额 = 本年金额 - 上年金额'"
                >{{ fmtAmount(row.changeAmount) }}</span>
              </template>
            </el-table-column>

            <!-- 变动率（公式列） -->
            <el-table-column label="变动率" width="100" align="right">
              <template #default="{ row }">
                <span
                  class="formula-cell"
                  :class="{ 'rate-warning': isRateWarning(row.changeRate) }"
                  :title="'变动率 = 变动额 / 上年金额（上年为0时不计算）'"
                >{{ fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>

            <!-- 分析说明 -->
            <el-table-column label="分析说明" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.analysisNote"
                  size="small"
                  placeholder="变动原因分析"
                  @change="handleCellChange(group.investeeName, row)"
                />
                <span v-else>{{ row.analysisNote }}</span>
              </template>
            </el-table-column>

            <!-- 数据来源 -->
            <el-table-column label="数据来源" width="120">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.dataSource"
                  size="small"
                  placeholder="如：年报"
                  @change="handleCellChange(group.investeeName, row)"
                />
                <span v-else>{{ row.dataSource }}</span>
              </template>
            </el-table-column>

            <!-- 审计状态（下拉） -->
            <el-table-column label="审计状态" width="100" align="center">
              <template #default="{ row }">
                <el-select
                  v-if="!isReadonly"
                  v-model="row.auditStatus"
                  size="small"
                  placeholder="状态"
                  @change="handleCellChange(group.investeeName, row)"
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

            <!-- 备注 -->
            <el-table-column label="备注" width="120">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.remark"
                  size="small"
                  placeholder="备注"
                  @change="handleCellChange(group.investeeName, row)"
                />
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>

            <!-- 操作列 -->
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
              <template #default="{ row, $index }">
                <el-button
                  size="small"
                  type="danger"
                  link
                  @click="deleteRow(group.investeeName, $index)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="groups.length === 0" class="empty-state">
        <p>暂无被投资单位财务信息数据</p>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="addNewGroup">
          + 新增被投资单位
        </el-button>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div v-if="!isReadonly" class="bottom-actions">
      <el-button type="primary" size="small" @click="addNewGroup">+ 新增被投资单位分组</el-button>
      <el-button size="small" @click="syncGroupsFromG74">从 G7-4 同步合营/联营</el-button>
      <el-button v-if="groups.length > 0" size="small" type="success" @click="handleSave">💾 保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <span>审计说明</span>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、核对情况及结果，异常变动分析及数据来源核实情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除已调整事项外未见异常。C、存在重大未调整事项或审计范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 按被投资单位分组录入财务数据，每组包含资产/负债/净资产/收入/利润等关键指标</p>
        <p>2. 变动额 = 本年金额 - 上年金额（自动计算，公式列显示虚线下划线）</p>
        <p>3. 变动率 = 变动额 / 上年金额（上年为0时显示"—"不计算，避免除零错误）</p>
        <p>4. |变动率| > 50% 橙色高亮，需在"分析说明"列补充变动原因</p>
        <p>5. 数据来源建议注明：年报/审计报告/管理层提供/公开信息等</p>
        <p>6. 本表数据为 G7-14 权益法测算的基础输入</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabFinancialInfo — G7-5 被投资单位财务信息（合营、联营）
 *
 * 57行×10列，按被投资单位分组 + 虚拟滚动(max-height 57行阈值)
 *
 * 10列：被投资单位(分组)|报表项目|上年金额|本年金额|变动额(公式)|变动率(公式)|分析说明|数据来源|审计状态|备注
 *
 * 功能：
 * - 按被投资单位折叠分组（localStorage持久化）
 * - 虚拟滚动（57行阈值，max-height 容器）
 * - 动态行增删（组内添加/删除）
 * - 公式自动计算：变动额=本年-上年；变动率=变动额/上年(上年=0→null)
 * - |变动率|>50% 橙色高亮
 * - 公式列虚线下划线+cursor:help+tooltip来源
 * - section标题栏右侧复核按钮(inject openReviewDialog)
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Requirements: 3.1, 3.3, 7.5
 */
import { reactive, ref, computed, inject, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { FinancialInfoRow } from '../../composables/useG7EquityMethodFormData'
import { G7_4_ROWS_KEY, loadEquityInvestees } from '../../composables/g7EquityMethodCrossSheet'

// ═══ Props ═══════════════════════════════════════════════════════════════════

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ═══ Injections ═══════════════════════════════════════════════════════════════

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ Constants ═══════════════════════════════════════════════════════════════

const ROWS_KEY = 'G7-5-rows'
const STORAGE_KEY_PREFIX = 'g7-financial-info-collapse-'

// ═══ 默认报表项目模板 ═══════════════════════════════════════════════════════

const DEFAULT_REPORT_ITEMS = [
  '总资产', '流动资产', '非流动资产',
  '总负债', '流动负债', '非流动负债',
  '所有者权益（净资产）',
  '营业收入', '营业成本', '净利润',
]

// ═══ Types ═══════════════════════════════════════════════════════════════════

interface FinancialGroup {
  investeeName: string
  investeeId?: string
  rows: FinancialInfoRow[]
}

// ═══ State ═══════════════════════════════════════════════════════════════════

const groups = reactive<FinancialGroup[]>([])
const expandedMap = reactive<Record<string, boolean>>({})
const isReadonly = computed(() => !!props.readonly)
const rowCount = computed(() => groups.reduce((n, g) => n + g.rows.length, 0))

// ═══ 持久化（checklist_responses） ═══════════════════════════════════════════

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const AUDIT_NOTE_KEY = 'G7-5-audit-note'
const AUDIT_CONCLUSION_KEY = 'G7-5-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

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

// ═══ 折叠状态持久化 ═══════════════════════════════════════════════════════

function getStorageKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw) {
      const saved = JSON.parse(raw) as Record<string, boolean>
      Object.assign(expandedMap, saved)
    }
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

// ═══ 公式计算 ═══════════════════════════════════════════════════════════════

/**
 * 计算变动额：本年金额 - 上年金额
 */
function calcChangeAmount(currentAmount: number, priorAmount: number): number {
  return Math.round((parseNum(currentAmount) - parseNum(priorAmount)) * 100) / 100
}

/**
 * 计算变动率：变动额 / 上年金额
 * 上年金额为0时返回null（避免除零）
 */
function calcChangeRate(changeAmount: number, priorAmount: number): number | null {
  const prior = parseNum(priorAmount)
  if (prior === 0) return null
  return Math.round((parseNum(changeAmount) / prior) * 10000) / 10000
}

/**
 * 重新计算行的公式列
 */
function recalcRow(row: FinancialInfoRow): void {
  row.changeAmount = calcChangeAmount(row.currentAmount, row.priorAmount)
  row.changeRate = calcChangeRate(row.changeAmount, row.priorAmount)
}

// ═══ 单元格更新 ═══════════════════════════════════════════════════════════════

function updateAmount(groupName: string, row: FinancialInfoRow, field: 'priorAmount' | 'currentAmount', value: number): void {
  ;(row as any)[field] = value
  recalcRow(row)
  persistRows()
}

function handleCellChange(_groupName: string, _row: FinancialInfoRow): void {
  persistRows()
}

// ═══ 动态行增删 ═══════════════════════════════════════════════════════════════

function addRowToGroup(groupName: string): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return

  const newRow: FinancialInfoRow = {
    id: `fi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq: group.rows.length + 1,
    investeeName: groupName,
    reportItem: '',
    priorAmount: 0,
    currentAmount: 0,
    changeAmount: 0,
    changeRate: null,
    analysisNote: '',
    dataSource: '',
    auditStatus: '未审',
    remark: '',
  }
  group.rows.push(newRow)
  persistRows()
}

function deleteRow(groupName: string, index: number): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return
  group.rows.splice(index, 1)
  // 重排序号
  group.rows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

async function addNewGroup(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增被投资单位',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      },
    )
    const name = value.trim()

    // 唯一性校验
    if (groups.some(g => g.investeeName === name)) {
      ElMessage.warning(`被投资单位"${name}"已存在`)
      return
    }

    pushDefaultGroup(name)
    persistRows()
  } catch {
    // 用户取消
  }
}

function pushDefaultGroup(name: string, investeeId = ''): void {
  const newRows: FinancialInfoRow[] = DEFAULT_REPORT_ITEMS.map((item, idx) => ({
    id: `fi-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    seq: idx + 1,
    investeeName: name,
    reportItem: item,
    priorAmount: 0,
    currentAmount: 0,
    changeAmount: 0,
    changeRate: null,
    analysisNote: '',
    dataSource: '',
    auditStatus: '未审' as const,
    remark: '',
  }))
  groups.push({
    investeeName: name,
    investeeId: investeeId || undefined,
    rows: newRows,
  })
  expandedMap[name] = true
  saveCollapseState()
}

/** 从 G7-4 同步合营/联营单位（已存在的分组不覆盖；回填 investeeId） */
function syncGroupsFromG74(): void {
  const investees = loadEquityInvestees(formData.data.value.get(G7_4_ROWS_KEY)?.conclusion)
  if (investees.length === 0) {
    ElMessage.warning('G7-4 中暂无合营/联营企业，请先维护基本信息')
    return
  }
  let added = 0
  let linked = 0
  for (const inv of investees) {
    const existing = groups.find((g) =>
      (inv.investeeId && g.investeeId === inv.investeeId)
      || g.investeeName === inv.name,
    )
    if (existing) {
      if (inv.investeeId && !existing.investeeId) {
        existing.investeeId = inv.investeeId
        linked++
      }
      continue
    }
    pushDefaultGroup(inv.name, inv.investeeId)
    added++
  }
  if (added === 0 && linked === 0) {
    ElMessage.info('合营/联营单位已全部同步，无需新增')
    return
  }
  persistRows()
  ElMessage.success(
    added > 0
      ? `已从 G7-4 新增 ${added} 个被投资单位分组`
      : `已为 ${linked} 个现有分组回填被投资单位ID`,
  )
}

// ═══ 保存 ═══════════════════════════════════════════════════════════════════

function persistRows(): void {
  if (isReadonly.value) return
  const allRows = groups.flatMap(g => g.rows)
  formData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify({
      rows: allRows,
      groups: groups.map(g => ({
        investeeName: g.investeeName,
        investeeId: g.investeeId,
        rows: g.rows,
      })),
    }),
    remark: null,
  })
}

function handleSave(): void {
  persistRows()
  void formData.saveImmediate(ROWS_KEY, {
    conclusion: JSON.stringify({
      rows: groups.flatMap(g => g.rows),
      groups: groups.map(g => ({
        investeeName: g.investeeName,
        investeeId: g.investeeId,
        rows: g.rows,
      })),
    }),
    remark: null,
  })
  ElMessage.success('财务信息已保存')
}

function mapRawRow(r: any, name: string, idx: number): FinancialInfoRow {
  const row: FinancialInfoRow = {
    id: r.id ?? `fi-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    seq: r.seq ?? idx + 1,
    investeeName: name,
    reportItem: r.reportItem ?? r.report_item ?? '',
    priorAmount: parseNum(r.priorAmount ?? r.prior_amount),
    currentAmount: parseNum(r.currentAmount ?? r.current_amount),
    changeAmount: 0,
    changeRate: null,
    analysisNote: r.analysisNote ?? r.analysis_note ?? '',
    dataSource: r.dataSource ?? r.data_source ?? '',
    auditStatus: r.auditStatus ?? r.audit_status ?? '未审',
    remark: r.remark ?? '',
  }
  recalcRow(row)
  return row
}

function applyGroupsFromPayload(payload: any): boolean {
  const rawGroups = payload?.groups ?? []
  if (Array.isArray(rawGroups) && rawGroups.length > 0) {
    for (const g of rawGroups) {
      const name = g.investeeName ?? g.investee_name ?? g.name ?? '未命名'
      const investeeId = String(g.investeeId ?? g.investee_id ?? '').trim()
      const rows = (g.rows ?? []).map((r: any, idx: number) => mapRawRow(r, name, idx))
      groups.push({ investeeName: name, investeeId: investeeId || undefined, rows })
      if (expandedMap[name] === undefined) expandedMap[name] = true
    }
    return true
  }
  const rawRows = payload?.rows ?? []
  if (Array.isArray(rawRows) && rawRows.length > 0) {
    const groupMap = new Map<string, FinancialInfoRow[]>()
    for (const r of rawRows) {
      const name = r.investeeName ?? r.investee_name ?? '未分组'
      if (!groupMap.has(name)) groupMap.set(name, [])
      groupMap.get(name)!.push(mapRawRow(r, name, groupMap.get(name)!.length))
    }
    for (const [name, rows] of groupMap.entries()) {
      groups.push({ investeeName: name, rows })
      if (expandedMap[name] === undefined) expandedMap[name] = true
    }
    return true
  }
  return false
}

// ═══ 数据水合 ═══════════════════════════════════════════════════════════════

function hydrateData(): void {
  const data = props.htmlData
  const financialInfo = data?.financialInfo ?? data?.financial_info ?? data
  applyGroupsFromPayload(financialInfo)
}

function parseStoredPayload(value: unknown): any | null {
  if (!value) return null
  if (typeof value === 'string') {
    try { return JSON.parse(value) } catch { return null }
  }
  return value
}

// ═══ 辅助函数 ═══════════════════════════════════════════════════════════════

function isRateWarning(rate: number | null): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.5
}

function fmtRate(v: number | null): string {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

function auditStatusType(status: string): '' | 'success' | 'warning' | 'info' {
  switch (status) {
    case '已审': return 'success'
    case '未审': return 'info'
    case '待确认': return 'warning'
    default: return ''
  }
}

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════

onMounted(async () => {
  loadCollapseState()
  await formData.load()

  const saved = parseStoredPayload(formData.data.value.get(ROWS_KEY)?.conclusion)
  if (saved && applyGroupsFromPayload(saved)) {
    // 已从 checklist 恢复
  } else {
    hydrateData()
  }

  auditNote.value = formData.data.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
  auditConclusion.value = formData.data.value.get(AUDIT_CONCLUSION_KEY)?.remark ?? ''
})
</script>

<style scoped>
.g7-tab-financial-info {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.conclusion-card {
  margin-top: 16px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* Section 标题栏 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.head-actions {
  display: flex;
  gap: 8px;
}

/* 方法论上下文区域 */
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
.methodology-context p {
  margin: 2px 0;
}

/* 虚拟滚动容器（57行阈值） */
.financial-scroll-container {
  max-height: calc(57 * 34px + 120px);
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 4px;
}

/* 分组标题 */
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
  transition: background 0.2s;
}
.group-header:first-child {
  margin-top: 0;
}
.group-header:hover {
  background: #d9ecff;
}
.group-name {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.group-count {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.group-actions {
  margin-left: auto;
}
.collapse-icon {
  transition: transform 0.2s;
  font-size: 14px;
}
.collapse-icon.is-collapsed {
  transform: rotate(-90deg);
}

/* 分组内容 */
.group-body {
  margin-bottom: 4px;
}

/* 表格 */
.financial-table {
  margin-top: 4px;
}

/* 公式列样式（虚线下划线+cursor:help） */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

/* 变动率橙色高亮 */
.rate-warning {
  color: #e6a23c;
  font-weight: 600;
}

/* 底部操作栏 */
.bottom-actions {
  margin-top: 12px;
  padding: 8px 0;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
}
.empty-state p {
  margin-bottom: 12px;
}

/* 编制提示 */
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-content p {
  margin: 4px 0;
}
</style>
