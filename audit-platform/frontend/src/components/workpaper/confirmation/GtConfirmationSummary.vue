<template>
  <div class="gt-confirmation-summary">
    <!-- 旧格式降级：检测 htmlData 无 _format 时显示只读 GtGridSheet -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-summary__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <!-- Fallback: 使用 GtGridSheet 只读渲染 -->
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：完整 confirmation-v1 组件 -->
    <template v-else>
      <!-- 无数据空态：仅首次打开（从未操作过）显示 onboarding -->
      <div v-if="data.rows.value.length === 0 && !hasInteracted" class="gt-confirmation-summary__onboarding">
        <div class="gt-confirmation-summary__onboarding-card">
          <div class="gt-confirmation-summary__onboarding-icon">✉️</div>
          <h3 class="gt-confirmation-summary__onboarding-title">开始编制函证底稿</h3>
          <div class="gt-confirmation-summary__onboarding-steps">
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">1</span>
              <span>新增函证对象或从 Excel 导入清单</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">2</span>
              <span>填写发函信息（科目、金额、方式）并寄出</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">3</span>
              <span>登记回函结果，处理差异或执行替代程序</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">4</span>
              <span>确认覆盖率达标后填写审计结论</span>
            </div>
          </div>
          <div class="gt-confirmation-summary__onboarding-actions">
            <el-button v-if="!readonly" type="primary" @click="handleAdd">+ 新增函证对象</el-button>
            <el-button v-if="!readonly" @click="handleDownloadImportTemplate">下载导入模板</el-button>
            <el-button v-if="!readonly" @click="handleImportClick">从 Excel 导入</el-button>
            <el-button
              v-if="!readonly"
              :loading="syncing"
              title="将已发函/已回函的行同步到项目函证中心台账（供工作包摘要/覆盖率消费）"
              @click="handleSyncHub"
            >同步到函证中心</el-button>
          </div>
        </div>
      </div>

      <!-- 有数据时：紧凑布局 -->
      <template v-else>
        <!-- 看板区（数据充分时默认展开，数据少时默认折叠减少干扰） -->
        <el-collapse v-model="expandedSections">
          <el-collapse-item :title="dashboardTitle" name="dashboard">
            <ConfirmationDashboard :metrics="data.dashboardMetrics.value" :coverage="data.coverageMetrics.value" />
          </el-collapse-item>
        </el-collapse>

        <!-- 科目 Tab + 视图切换 -->
        <div class="gt-confirmation-summary__toolbar">
          <ConfirmationTabs :tabs="data.accountTabs.value" :active-tab="data.activeTab.value" @update:active-tab="data.activeTab.value = $event" />
          <div class="gt-confirmation-summary__toolbar-right">
            <el-tag
              v-if="syncStatusSummary.total > 0"
              size="small"
              :type="syncStatusSummary.unsynced === 0 ? 'success' : 'info'"
              title="已同步=已回写函证中心台账标识的行；待同步=已进入函证程序但尚未同步的行"
            >已同步 {{ syncStatusSummary.synced }} · 待同步 {{ syncStatusSummary.unsynced }}</el-tag>
            <el-button
              v-if="!readonly && isE0"
              size="small"
              :loading="importingLists"
              title="从 E0-3~E0-6 发函清单筛「是否函证=是」的账户带入本汇总表"
              @click="handleImportE0Lists"
            >从发函清单带入</el-button>
            <el-button
              v-if="!readonly"
              size="small"
              :loading="syncing"
              title="将已发函/已回函的行同步到项目函证中心台账（供工作包摘要/覆盖率消费）"
              @click="handleSyncHub"
            >同步到函证中心</el-button>
            <el-radio-group v-model="viewMode.viewMode.value" size="small">
              <el-radio-button value="list">列表视图</el-radio-button>
              <el-radio-button value="grid">完整表格</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <!-- 列表视图 -->
        <template v-if="viewMode.viewMode.value === 'list'">
          <ConfirmationMaster
            :rows="data.filteredRows.value"
            :readonly="readonly"
            :selected-ids="selectedIds"
            @update:selected-ids="selectedIds = $event"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @download-template="handleDownloadImportTemplate"
            @import-data="handleImportClick"
            @show-formula="showFormulaDialog = true"
            @row-click="handleRowClick"
          />
          <ConfirmationDetail
            :row="currentRow"
            :readonly="readonly"
            :dict-data="dictData"
            @update="handleFieldUpdate"
          />
        </template>

        <!-- 完整表格视图 -->
        <template v-else>
          <ConfirmationFullGrid
            :rows="data.filteredRows.value"
            :readonly="readonly"
            :cycle="confirmCycle"
            @update="handleGridUpdate"
          />
        </template>

        <!-- 辅助区（默认折叠） -->
        <el-collapse v-model="expandedSections">
          <el-collapse-item title="样本选择" name="sampling">
            <ConfirmationSampling
              :data="data.sampling.value"
              :readonly="readonly"
              :dict-data="dictData"
              :total-count="data.rows.value.length"
              :total-amount="data.rows.value.reduce((sum, r) => sum + (r.amount || 0), 0)"
              :sample-count="data.rows.value.length"
              :sample-amount="data.rows.value.reduce((sum, r) => sum + (r.amount || 0), 0)"
              @update="handleSamplingUpdate"
            />
          </el-collapse-item>

          <el-collapse-item title="审计说明" name="notes">
            <ConfirmationNotes
              :data="data.notes.value"
              :readonly="readonly"
              :wp-id="wpId"
              :project-id="projectId"
              :wp-code="wpCode"
              :stats="notesAiStats"
              @update="handleNotesUpdate"
            />
          </el-collapse-item>

          <el-collapse-item title="审计结论" name="conclusion">
            <ConfirmationConclusion :data="data.conclusion.value" :readonly="readonly" @update="handleConclusionUpdate" />
          </el-collapse-item>
        </el-collapse>
      </template>
    </template>

    <!-- 隐藏文件选择器（导入用，放在组件根层级确保始终可访问） -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- 右键菜单 -->
    <ConfirmationContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :readonly="readonly"
      @update:visible="contextMenu.visible = $event"
      @action="handleContextAction"
    />

    <!-- 公式管理弹窗 -->
    <el-dialog v-model="showFormulaDialog" title="公式管理 — 函证结果汇总表" width="640px" append-to-body>
      <div class="gt-formula-dialog">
        <h4>表内自动计算规则</h4>
        <el-table :data="formulaRules" border size="small" style="width:100%">
          <el-table-column prop="field" label="字段" width="120" />
          <el-table-column prop="formula" label="计算规则" min-width="300" />
          <el-table-column prop="source" label="来源" width="100" />
        </el-table>

        <h4 style="margin-top:20px">跨表校对关系</h4>
        <el-table :data="crossRefRules" border size="small" style="width:100%">
          <el-table-column prop="field" label="本表字段" width="120" />
          <el-table-column prop="target" label="关联底稿" width="120" />
          <el-table-column prop="rule" label="校对规则" min-width="260" />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useConfirmationData } from './composables/useConfirmationData'
import { useViewMode } from './composables/useViewMode'
import { syncHubFromSummary, hubStatusToRowPatch, accountTypeToHubType, rowToHubStatus } from './coordination/syncHubFromSummary'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { emitConfirmationCompletedFromSummary, isConfirmationInFlight } from './coordination/emitConfirmationCompleted'
import { importE0ListsToSummary } from './coordination/importE0ListsToSummary'
import type { ConfirmationRow } from './confirmationTypes'

import ConfirmationDashboard from './ConfirmationDashboard.vue'
import ConfirmationTabs from './ConfirmationTabs.vue'
import ConfirmationMaster from './ConfirmationMaster.vue'
import ConfirmationDetail from './ConfirmationDetail.vue'
import ConfirmationFullGrid from './ConfirmationFullGrid.vue'
import ConfirmationSampling from './ConfirmationSampling.vue'
import ConfirmationNotes from './ConfirmationNotes.vue'
import ConfirmationConclusion from './ConfirmationConclusion.vue'
import ConfirmationContextMenu from './ConfirmationContextMenu.vue'

// GtGridSheet for legacy fallback
const GtGridSheet = defineAsyncComponent(() => import('../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'confirmation-v1')

// 枢纽标识（Cycle_Variant_Column 列集合选取，confirmation-shared-model-extension 决策 2）
// 由 wpCode（D0-1/E0-1/…/L0-1）派生：取前缀字母+0 组，回退 D0。
const confirmCycle = computed<import('./confirmationColumnSpec').ConfirmCycle>(() => {
  const m = String(props.wpCode || '').match(/^([A-Z])0/)
  const c = m ? (`${m[1]}0` as import('./confirmationColumnSpec').ConfirmCycle) : 'D0'
  const valid: import('./confirmationColumnSpec').ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0']
  return valid.includes(c) ? c : 'D0'
})

// E0（货币资金/借款）循环：提供「从发函清单（E0-3~E0-6）带入」入口
const isE0 = computed(() => confirmCycle.value === 'E0')
const importingLists = ref(false)

// ─── 数据核心 ────────────────────────────────────────────────────────────────

// 科目审定总额(TB population)：后端 render 注入 project_context.population_amount（前端只读）
// 作为函证/确认覆盖率分母；缺失时覆盖率显示为「不可用」(Skip-on-missing)
const populationAmount = computed<number | null>(() => {
  const p = props.htmlData?.project_context?.population_amount
  return typeof p === 'number' && p > 0 ? p : null
})

const data = useConfirmationData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
  population: () => populationAmount.value,
})

const viewMode = useViewMode()

// P1-1: 保存后自动同步到函证中心台账（防抖/非阻塞/失败静默/只读gate）
const autoSync = useDisclosureAutoSync({
  isReadonly: () => props.readonly,
  debounceMs: 2000,
})

// 同步状态可见（Task 4.2 / Property 20）：已同步=已回写 hubId 的行；
// 待同步=已进入函证程序（已发函/已回函）但尚未持久化 hubId 的行。数据源为行上持久化的 _hub_confirmation_id。
const syncStatusSummary = computed(() => {
  const inFlight = data.rows.value.filter((r) => r.entity_name?.trim() && isConfirmationInFlight(r))
  const synced = inFlight.filter((r) => !!r._hub_confirmation_id).length
  return { total: inFlight.length, synced, unsynced: inFlight.length - synced }
})

// ─── UI 状态 ──────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const currentRow = ref<ConfirmationRow | null>(null)
const contextMenu = ref({ visible: false, x: 0, y: 0 })
// 同步到函证中心（P0-2：编制真源 confirmation-v1 → 后端 Confirmation 台账/工作包摘要真源）
const syncing = ref(false)
// 用户是否已操作过（新增/删除），用于区分首次空态 vs 删光后空态
const hasInteracted = ref(false)

// #3: 订阅 Hub 状态变更→反向刷新编制真源行（Hub 手动推进后同步回来）
function _onConfirmationReceived(payload: { confirmationId?: string; accountCode?: string }) {
  // Hub 推进到终态后触发——同会话即时刷新（加速）；持久化以 _backflowFromHub 为准。
  if (!payload?.confirmationId) return
  const row = data.rows.value.find(r => r._hub_confirmation_id === payload.confirmationId)
  if (row) {
    // 已有 hubId 映射的行：标记 is_replied（终态必定已回函）
    const patch = hubStatusToRowPatch('returned')
    Object.assign(row, patch)
  }
  // 触发一次持久化拉取（拿到回函金额/终态，手工优先）
  _backflowFromHub(true)
}

/**
 * Reply_Backflow（R4.1/R4.5）：从后端台账拉取回函结果刷新本表行，不依赖同会话事件。
 * - 匹配优先级：行的 _hub_confirmation_id > 对方名称（counterparty）
 * - 手工优先（P8）：行已有审计师手工回函金额（reply_amount）时不覆盖，仅补状态标记
 * - 持久化读取（P9）：跨会话打开也能读到台账最新回函
 */
let _backflowRan = false
async function _backflowFromHub(force = false) {
  if (!props.projectId) return
  if (_backflowRan && !force) { /* onMounted 只跑一次；事件驱动 force=true */ }
  try {
    const res = await http.get<any>(
      `/api/projects/${props.projectId}/confirmations`,
      { _silent: true } as any,
    )
    const items: any[] = res?.items ?? res?.data?.items ?? []
    if (!items.length) return
    // 建索引：按 id 与按对方名称
    const byId = new Map<string, any>()
    const byName = new Map<string, any>()
    for (const it of items) {
      if (it.id) byId.set(String(it.id), it)
      const name = String(it.counterparty || '').trim()
      if (name && !byName.has(name)) byName.set(name, it)
    }
    let anyPatched = false
    for (const row of data.rows.value) {
      const hit = (row._hub_confirmation_id && byId.get(row._hub_confirmation_id))
        || byName.get(String(row.entity_name || '').trim())
      if (!hit) continue
      const status = String(hit.status || '')
      if (!['returned', 'matched', 'discrepancy'].includes(status)) continue
      // 手工优先：行已有回函金额（审计师手填）则不覆盖金额，仅补状态标记
      const hasManualReply = row.reply_amount != null && row.reply_amount !== '' && Number(row.reply_amount) !== 0
      const patch = hubStatusToRowPatch(
        status,
        hasManualReply ? undefined : {
          confirmed_amount: hit.confirmed_amount,
          diff_amount: hit.diff_amount,
        },
      )
      // 首次回填 hubId 映射（供后续幂等 + 状态显示）
      if (!row._hub_confirmation_id && hit.id) row._hub_confirmation_id = String(hit.id)
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined) continue
        if ((row as any)[k] !== v) { (row as any)[k] = v; anyPatched = true }
      }
    }
    if (anyPatched) {
      // 持久化刷新结果（不触发二次同步，供跨会话可读 P9）
      emit('save', data.buildPayload())
    }
  } catch {
    // 台账不可读时静默（不打扰用户）
  } finally {
    _backflowRan = true
  }
}
onMounted(() => {
  eventBus.on('confirmation:received', _onConfirmationReceived)
  // 打开时按持久化台账刷新回函结果（不依赖同会话事件）
  if (data.rows.value.length > 0) _backflowFromHub()
})
onUnmounted(() => {
  eventBus.off('confirmation:received', _onConfirmationReceived)
})

// 清除待触发的自动同步定时器
onBeforeUnmount(() => {
  autoSync.cancelPending()
})

// 公式管理弹窗
const showFormulaDialog = ref(false)
const formulaRules = [
  { field: '可确认金额', formula: '相符→函证金额；不符→回函金额；消极式未回函→函证金额；积极式未回函→替代确认金额', source: '自动计算' },
  { field: '差异金额', formula: '= 函证金额 - 回函金额（相符时强制为0）', source: '自动计算' },
  { field: '确认覆盖率', formula: '= (回函确认 + 替代确认) / 函证发出总额 × 100%', source: '看板汇总' },
  { field: '回函率', formula: '= 已回函笔数 / 已发函笔数 × 100%', source: '看板汇总' },
  { field: '函证覆盖率（科目总体）', formula: '= 函证发出总额 / 科目审定总额 × 100%（需接入试算表审定总额，暂未计算）', source: '待接入 TB' },
]
const crossRefRules = [
  { field: '函证金额', target: 'TB 试算表', rule: '应与科目审定余额(audited_amount)核对一致' },
  { field: '差异金额', target: 'D0-4 差异调节', rule: '不符项跳转到 D0-4 差异调节表编制' },
  { field: '替代确认', target: 'D0-5/D0-6', rule: '未回函项跳转到替代程序底稿确认' },
  { field: '回函可靠性', target: 'D0-7', rule: '电子回函需跳转 D0-7 验证可靠性' },
  { field: '舞弊风险', target: 'D0-8/B50', rule: '异常迹象需记录到 D0-8 并汇总至 B50 风险评估' },
]

/** 默认展开：数据充分(≥3条)时展开看板，数据少时折叠（减少视觉干扰） */
const expandedSections = ref<string[]>(data.rows.value.length >= 3 ? ['dashboard'] : [])

/** 为审计说明 AI 预填充提供的统计数据 */
const notesAiStats = computed(() => {
  const rows = data.rows.value
  const totalCount = rows.length
  const totalAmount = rows.reduce((s, r) => s + (r.amount || 0), 0)
  const repliedCount = rows.filter(r => r.is_replied).length
  const matchedCount = rows.filter(r => r.match_status === '相符').length
  const unrepliedCount = totalCount - repliedCount
  const coveragePct = totalAmount > 0
    ? (rows.filter(r => r.is_replied).reduce((s, r) => s + (r.amount || 0), 0) / totalAmount) * 100
    : 0
  const accountTypes = [...new Set(rows.map(r => r.account_type).filter(Boolean))] as string[]
  return { totalCount, totalAmount, repliedCount, matchedCount, unrepliedCount, coveragePct, accountTypes }
})

/** 看板标题：少量数据时提示尚不完整 */
const dashboardTitle = computed(() => {
  const count = data.rows.value.length
  if (count === 0) return '函证情况统计'
  if (count < 3) return `函证情况统计（已录入 ${count} 条，录入更多后指标更有参考价值）`
  return `函证情况统计（${count} 条函证）`
})

// TODO: dictData 从 useDictStore 获取（暂用内置默认值，用户可自定义输入扩展）
const dictData = ref<Record<string, any[]>>({
  confirmation_account_type: ['应收账款', '应付账款', '银行存款', '合同负债', '其他应收款', '预付账款', '长期应收款'],
  confirmation_method: ['积极式', '消极式'],
  confirmation_reply_method: ['邮寄', '传真', '电子邮件', '第三方平台', '当面递交'],
  confirmation_match: ['相符', '不符', '未回函', '部分相符'],
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)

function handleAdd() {
  hasInteracted.value = true
  try {
    data.addRow()
  } catch (e: any) {
    console.warn('[GtConfirmationSummary] handleAdd error:', e?.message)
  }
}

function handleImportClick() {
  importFileInput.value?.click()
}

async function handleDownloadImportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 数据模板（固定列头，用户在此填写）
    const headers = ['序号', '索引号', '被询证单位', '地址', '联系人', '联系电话', '科目', '函证金额', '币种', '函证方式', '发函日期']
    const exampleRow = [1, 'D0-001', '示例公司（请删除此行）', '北京市XX区XX路XX号', '张三', '010-12345678', '应收账款', 100000, 'CNY', '积极式', '2025-12-31']
    const dataSheet = utils.aoa_to_sheet([headers, exampleRow])
    // 设置列宽
    dataSheet['!cols'] = [
      { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 30 }, { wch: 10 }, { wch: 14 },
      { wch: 12 }, { wch: 14 }, { wch: 6 }, { wch: 10 }, { wch: 12 },
    ]
    utils.book_append_sheet(wb, dataSheet, '函证清单')

    // Sheet 2: 填写说明
    const instructions = [
      ['函证清单导入模板 - 填写说明'],
      [''],
      ['【必填列】'],
      ['  被询证单位：函证对象公司全称（必填）'],
      ['  科目：函证涉及的会计科目（如：应收账款、应付账款、银行存款、合同负债）'],
      ['  函证金额：账面金额（数字，单位：元）'],
      [''],
      ['【选填列】'],
      ['  序号：自动递增编号（留空则自动生成）'],
      ['  索引号：函证编号（如 D0-001），留空则自动生成'],
      ['  地址：邮寄发函地址'],
      ['  联系人：被询证单位联系人姓名'],
      ['  联系电话：被询证单位联系电话'],
      ['  币种：默认 CNY，外币函证填写对应币种'],
      ['  函证方式：积极式 / 消极式（默认积极式）'],
      ['  发函日期：格式 YYYY-MM-DD'],
      [''],
      ['【注意事项】'],
      ['  1. 请在「函证清单」sheet 中填写数据，本说明 sheet 无需修改'],
      ['  2. 第一行为表头，请勿修改列名（系统按列名识别）'],
      ['  3. 示例行（第2行）请删除后再填写实际数据'],
      ['  4. 金额列请填纯数字，不要带"元"或千分位逗号'],
      ['  5. 填写完成后保存，回到系统点击「↑导入」上传此文件'],
      ['  6. 导入后可在系统中继续补充回函结果和相符情况'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 70 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, '函证清单导入模板.xlsx')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const { read, utils } = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = read(buf, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rawRows: Record<string, any>[] = utils.sheet_to_json(ws)
    if (rawRows.length === 0) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    // 列名映射（支持多种常见写法，与导入模板列头对齐）
    const colMap: Record<string, string[]> = {
      entity_name: ['被询证单位', '单位名称', '被函证单位', '客户名称', '对方单位'],
      account_type: ['科目', '科目类型', '账户类型', '函证科目'],
      amount: ['函证金额', '金额', '账面金额', '余额', '发函金额'],
      confirmation_method: ['函证方式', '方式', '发函方式'],
      entity_address: ['地址', '邮寄地址', '联系地址'],
      contact_person: ['联系人', '联系人姓名'],
      contact_phone: ['联系电话', '电话', '手机'],
      currency: ['币种', '货币'],
      send_date: ['发函日期', '寄出日期'],
      confirm_index: ['索引号', '函证索引号', '编号'],
    }
    let importCount = 0
    for (const raw of rawRows) {
      // 跳过完全空行
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row = data.addRow()
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            const val = field === 'amount' ? (parseFloat(String(raw[alias])) || null) : String(raw[alias]).trim()
            ;(row as any)[field] = val
            break
          }
        }
      }
      importCount++
    }
    if (importCount > 0) {
      ElMessage.success(`成功导入 ${importCount} 条函证记录`)
    } else {
      ElMessage.warning('未识别到有效数据行，请检查 Excel 列头是否包含：被询证单位、科目、函证金额')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

function handleDelete() {
  hasInteracted.value = true
  data.deleteRows(selectedIds.value)
  selectedIds.value = []
}

/**
 * 同步到函证中心：把本汇总表「已进入函证程序」的行 upsert 到后端 Confirmation 台账，
 * 并按状态机推进（终态触发 CONFIRMATION_RECEIVED → 下游 D2/F2/G7… stale）。
 * 这是 confirmation-v1 编制真源 → 后端摘要真源的桥（此前 syncHubFromSummary 为死代码未接线）。
 */
async function handleSyncHub() {
  if (!props.projectId) { ElMessage.warning('缺少项目上下文，无法同步'); return }
  syncing.value = true
  try {
    const cycleCode = (props.wpCode || '').split('-')[0] || undefined
    const res = await syncHubFromSummary({
      projectId: props.projectId,
      wpId: props.wpId,
      sourceWpCode: props.wpCode,
      wpCode: cycleCode,
      year: props.year ? Number(props.year) : undefined,
      rows: data.rows.value,
    })
    const summary = `新增 ${res.created} · 更新 ${res.updated} · 状态推进 ${res.transitioned}`
    if (res.errors.length) {
      ElMessage.warning(`同步完成（部分失败）：${summary}；${res.errors[0]}`)
    } else if (res.created + res.updated + res.transitioned === 0) {
      ElMessage.info('暂无「已发函/已回函」的行需要同步')
    } else {
      ElMessage.success(`已同步到函证中心：${summary}`)
    }
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.message || '未知错误'))
  } finally {
    syncing.value = false
  }
}

/**
 * E0 清单 → E0-1 带入（Task 3.3 / Property 14）：
 * 从 E0-3~E0-6 发函清单筛「是否函证=是」的账户，按品种置 account_type，去重后建行。
 * 复用既有 addRow + updateField 写入路径（不新造 confirmation-v1 写入实现）。
 */
async function handleImportE0Lists() {
  if (!props.projectId) { ElMessage.warning('缺少项目上下文，无法带入'); return }
  importingLists.value = true
  try {
    const res = await importE0ListsToSummary(props.projectId, data.rows.value)
    if (!res.ok) {
      ElMessage.warning('从发函清单带入失败：' + (res.message || '未知错误'))
      return
    }
    if (res.candidates.length === 0) {
      ElMessage.info(res.emptyReason || '无可带入项目')
      return
    }
    hasInteracted.value = true
    for (const c of res.candidates) {
      const row = data.addRow()
      if (c.entity_name) data.updateField(row._row_id!, 'entity_name', c.entity_name)
      if (c.confirm_index) data.updateField(row._row_id!, 'confirm_index', c.confirm_index)
      if (c.account_type) data.updateField(row._row_id!, 'account_type', c.account_type)
      // 账号/理财产品名称：源模板 E0-1 E 列，是 F 列 SUMIF 的匹配键，必须带过来
      if (c.account_no) data.updateField(row._row_id!, 'account_no', c.account_no)
      if (c.currency) data.updateField(row._row_id!, 'currency', c.currency)
      if (c.amount != null) data.updateField(row._row_id!, 'amount', c.amount)
      ;(row as any)._source = 'auto'
    }
    handleSave()
    ElMessage.success(`已从发函记录表带入 ${res.candidates.length} 条`)
    // 品种靠兜底值推出（源模板「所属科目」「借款类型」两列都缺）→ 明示提示，不静默归类
    if (res.typeFallbackLists?.length) {
      ElMessage.warning(
        `${res.typeFallbackLists.join('、')} 缺「所属科目」列，品种已按默认值填入，请复核（长期借款需手工改正）`,
      )
    }
  } catch (e: any) {
    ElMessage.warning('从发函清单带入失败：' + (e?.message || '未知错误'))
  } finally {
    importingLists.value = false
  }
}

/**
 * #1+#2+#4: 保存后自动同步 Hub（批量端点，单次 HTTP 替代 N+1）。
 * 使用 useDisclosureAutoSync 统一封装：防抖 2s/非阻塞/失败静默/只读gate。
 * 同步成功后 hubId 写回 row._hub_confirmation_id → re-save 持久化映射。
 */
function _triggerAutoSyncHub() {
  if (!props.projectId) return
  autoSync.scheduleAutoSync(async () => {
    if (syncing.value) return // 正在手动同步，跳过
    const candidates = data.rows.value.filter(
      (r) => r.entity_name?.trim() && isConfirmationInFlight(r),
    )
    if (!candidates.length) return

    const cycleCode = (props.wpCode || '').split('-')[0] || undefined
    const items = candidates.map((r) => ({
      confirm_type: accountTypeToHubType(r.account_type),
      counterparty: (r.entity_name || '').trim(),
      wp_id: props.wpId || undefined,
      account_code: r.confirm_index || undefined,
      book_amount: Number(r.amount) || null,
      confirmed_amount: Number(r.reply_amount) || null,
      diff_amount: r.difference != null ? Number(r.difference) : null,
      diff_note: r.remark || undefined,
      target_status: rowToHubStatus(r),
      hub_confirmation_id: r._hub_confirmation_id || undefined,
    }))

    const res = await http.post<any>(
      `/api/projects/${props.projectId}/confirmations/batch-sync`,
      {
        items,
        wp_id: props.wpId,
        wp_code: cycleCode,
        year: props.year ? Number(props.year) : undefined,
      },
      { _silent: true } as any,
    )
    // #2: 写回 hubId 到各行
    const hubIds: Record<string, string> = res?.hub_ids || {}
    let anyMapped = false
    for (const row of candidates) {
      const name = (row.entity_name || '').trim()
      if (hubIds[name] && row._hub_confirmation_id !== hubIds[name]) {
        row._hub_confirmation_id = hubIds[name]
        anyMapped = true
      }
    }
    // re-save 持久化 hubId 映射（不触发二次同步）
    if (anyMapped) {
      const payload = data.buildPayload()
      emit('save', payload)
    }
  })
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  // 通知兄弟函证 sheet 刷新（confirmation:updated EventBus 联动）
  if (props.projectId && props.wpCode) {
    eventBus.emit('confirmation:updated', {
      projectId: props.projectId,
      wpCode: props.wpCode,
      wpId: props.wpId,
      timestamp: Date.now(),
    })
  }
  // #6: 批量回写科目明细 isConfirmed='Y'（此前为死代码，现接线）
  emitConfirmationCompletedFromSummary({
    projectId: props.projectId,
    sourceWpCode: props.wpCode,
    rows: data.rows.value,
  })
  // #1+#2: 保存后自动同步到函证中心（非阻塞，hubId 回写后自动 re-save 持久化）
  if (props.projectId) {
    _triggerAutoSyncHub()
  }
}

function handleRowClick(row: ConfirmationRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  data.updateField(currentRow.value._row_id, field, value)
}

function handleGridUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

function handleSamplingUpdate(field: string, value: any) {
  ;(data.sampling.value as any)[field] = value
}

function handleNotesUpdate(field: string, value: any) {
  ;(data.notes.value as any)[field] = value
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
}

function handleContextAction(action: string) {
  // Context menu actions - to be wired with row context
  console.log('[GtConfirmationSummary] context action:', action)
}

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleDownloadImportTemplate,
  handleImportClick,
  handleExportData: handleSave, // 导出数据 = 保存当前数据
})
</script>

<style scoped>
.gt-confirmation-summary {
  padding: 8px 0;
}

.gt-confirmation-summary__legacy-notice {
  margin-bottom: 12px;
}

/* Onboarding card - 空态首屏引导 */
.gt-confirmation-summary__onboarding {
  display: flex;
  justify-content: center;
  padding: 40px 20px;
}
.gt-confirmation-summary__onboarding-card {
  max-width: 480px;
  text-align: center;
  padding: 32px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}
.gt-confirmation-summary__onboarding-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.gt-confirmation-summary__onboarding-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 20px;
}
.gt-confirmation-summary__onboarding-steps {
  text-align: left;
  margin-bottom: 24px;
}
.gt-confirmation-summary__step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: #606266;
  line-height: 1.5;
}
.gt-confirmation-summary__step-no {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #7b61ff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-confirmation-summary__onboarding-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

/* 有数据时的工具栏 */
.gt-confirmation-summary__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-confirmation-summary__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-summary__view-switch {
  display: flex;
  justify-content: flex-end;
  margin: 8px 0;
}
</style>
