<template>
  <div class="g7-tab-accounting-policy">
    <div class="section-head">
      <h3 class="sheet-title">G7-6 被投资公司会计政策一致性检查</h3>
      <div class="head-actions">
        <el-dropdown v-if="!isReadonly" @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          size="small"
          type="primary"
          link
          :loading="aiLoading"
          :disabled="isReadonly"
          @click="handleAiConclusion"
        >🤖 AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-6-accounting-policy')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="一、审计目标：核实被投资单位会计政策与投资方是否一致；对不一致事项按投资方政策调整，为 G7-14 权益法测算提供口径一致的净利润基础（CAS 2）。"
    />

    <div class="methodology-context">
      <p>CAS 2 会计政策一致性要求：</p>
      <p>• 按投资方政策调整被投资方报表后再计算应享有份额；调整合计写入 G7-14「会计政策调整」列</p>
      <p>• 公允价值/可辨认净资产调整属 G7-13，勿混入本表</p>
      <p>• 被投资单位名单优先从 G7-4 合营/联营同步</p>
    </div>

    <el-card class="procedure-card" shadow="never">
      <template #header><span>二、审计过程</span></template>
      <ol class="procedure-list">
        <li>按被投资单位分别获取会计政策，并与投资方对照。</li>
        <li>识别对净利润有实质影响的差异；无关事项标「不适用」。</li>
        <li>测算不一致事项对报告期净利润的调整金额并填写说明。</li>
        <li>将各被投资方调整合计同步至 G7-14「会计政策调整」列。</li>
      </ol>
    </el-card>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">一致 {{ globalSummary.consistent }}</el-tag>
        <el-tag size="small" type="danger">不一致 {{ globalSummary.inconsistent }}</el-tag>
        <el-tag size="small" type="info">不适用 {{ globalSummary.na }}</el-tag>
        <el-tag v-if="globalSummary.empty > 0" size="small" type="warning">未判断 {{ globalSummary.empty }}</el-tag>
        <el-tag size="small" effect="plain">调整合计 {{ fmtAmount(globalSummary.totalAdj) }}</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">{{ groups.length }} 家被投资方</el-tag>
      </div>
    </div>

    <div class="table-section-label">三、会计政策对比（按被投资单位）</div>

    <div v-if="groups.length === 0" class="empty-state">
      <p>暂无被投资单位。请从 G7-4 同步合营/联营，或手动新增。</p>
      <el-button v-if="!isReadonly" type="primary" size="small" @click="syncGroupsFromG74">从 G7-4 同步</el-button>
      <el-button v-if="!isReadonly" size="small" @click="addGroupManual">手动新增</el-button>
    </div>

    <template v-for="group in groups" :key="group.investeeName">
      <div class="group-header" @click="toggleGroup(group.investeeName)">
        <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.investeeName] }">
          <ArrowDown />
        </el-icon>
        <span class="group-name">{{ group.investeeName }}</span>
        <el-tag size="small" type="danger" effect="plain">
          调整 {{ fmtAmount(groupSummary(group).totalAdj) }}
        </el-tag>
        <el-tag v-if="groupSummary(group).empty > 0" size="small" type="warning">
          未判断 {{ groupSummary(group).empty }}
        </el-tag>
        <div v-if="!isReadonly" class="group-actions" @click.stop>
          <el-button size="small" type="primary" link @click="syncGroupToG714(group)">同步至 G7-14</el-button>
          <el-button size="small" type="danger" link @click="removeGroup(group.investeeName)">删除分组</el-button>
        </div>
      </div>

      <div v-show="expandedMap[group.investeeName]" class="group-body">
        <div class="group-filter-bar">
          <el-radio-group v-model="groupFilters[group.investeeName]" size="small">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="empty">未判断</el-radio-button>
            <el-radio-button value="inconsistent">不一致</el-radio-button>
          </el-radio-group>
        </div>

        <el-table
          :data="filteredGroupRows(group)"
          border
          size="small"
          class="policy-table"
          :row-class-name="rowClassName"
          max-height="420"
        >
          <el-table-column label="#" width="45" align="center">
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>

          <el-table-column label="会计政策事项" min-width="150">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.policyItem"
                size="small"
                @change="persistAll()"
              />
              <span v-else>{{ row.policyItem }}</span>
            </template>
          </el-table-column>

          <el-table-column label="被投资方政策" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.investeePolicy"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                @change="onPolicyTextChange(row)"
              />
              <span v-else class="cell-text">{{ row.investeePolicy || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="投资方政策" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.investorPolicy"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                @change="onPolicyTextChange(row)"
              />
              <span v-else class="cell-text">{{ row.investorPolicy || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="是否一致" width="120" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.isConsistent"
                size="small"
                placeholder="请选择"
                :class="{ 'consistency-empty': !row.isConsistent }"
                @change="onConsistencyChange(row)"
              >
                <el-option label="一致" value="一致" />
                <el-option label="不一致" value="不一致" />
                <el-option label="不适用" value="不适用" />
              </el-select>
              <el-tag v-else size="small" :type="consistencyTagType(row.isConsistent)">
                {{ row.isConsistent || '—' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="调整金额" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                v-model="row.adjustmentAmount"
                size="small"
                :disabled="row.isConsistent !== '不一致'"
                style="width: 100%"
                @change="persistAll()"
              />
              <span v-else>{{ fmtAmount(row.adjustmentAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="调整说明" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.adjustmentNote"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                :disabled="row.isConsistent !== '不一致'"
                @change="persistAll()"
              />
              <span v-else class="cell-text">{{ row.adjustmentNote || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="deleteRow(group, row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!isReadonly" class="group-bottom-actions">
          <el-button size="small" @click="addRow(group)">+ 添加政策事项</el-button>
          <el-button
            size="small"
            :disabled="groupSummary(group).empty === 0"
            @click="markRemainingAsNa(group)"
          >未判断标为不适用</el-button>
        </div>
      </div>
    </template>

    <div v-if="!isReadonly" class="bottom-actions">
      <el-button type="primary" size="small" @click="syncGroupsFromG74">从 G7-4 同步合营/联营</el-button>
      <el-button size="small" @click="addGroupManual">+ 新增被投资单位</el-button>
      <el-button size="small" :disabled="groups.length === 0" @click="syncAllToG714">全部同步至 G7-14</el-button>
      <el-button size="small" @click="fillConclusionDraft">根据汇总生成结论草稿</el-button>
      <el-button size="small" type="success" @click="handleSave">💾 保存</el-button>
      <el-button size="small" type="primary" :disabled="groups.length === 0" @click="handleSaveAndSync">保存并同步 G7-14</el-button>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header><span>四、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="概述已执行程序、重大政策差异及调整理由；公允价值差异记入 G7-13。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header><span>五、审计结论</span></template>
      <el-input
        v-if="!isReadonly"
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="例如：除××公司××政策差异已调整××元外，其余重要会计政策与投资方一致。"
        @change="persistConclusion()"
      />
      <p v-else class="conclusion-text">{{ conclusion || '暂无结论' }}</p>
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 每个被投资单位单独核对；优先从 G7-4 同步合营/联营名单。</p>
        <p>2. 「是否一致」必填；双方政策文本相同将自动标「一致」。</p>
        <p>3. 「同步至 G7-14」会写入对应被投资方的「会计政策调整」并重算相关公式；合计为 0 时不覆盖 G7-14 已有金额。</p>
        <p>4. 投资成本/公允价值调整走 G7-13，勿与本表混淆。</p>
      </div>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx" class="hidden-input" @change="handleFileChange">
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G7TabAccountingPolicy — G7-6 被投资公司会计政策一致性检查
 * 按被投资单位分组；调整合计可同步至 G7-14 accountingPolicyAdj
 */
import { reactive, ref, computed, inject, onMounted, toRef } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { AccountingPolicyRow } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import {
  G7_4_ROWS_KEY,
  G7_6_ROWS_KEY,
  applyG76PolicyToG714Payload,
  applyPolicyAdjToG714Payload,
  buildG714DualWriteItems,
  loadEquityInvestees,
  makeG714ConclusionGetter,
  parseChecklistJson,
  resolveG714PayloadFromChecklist,
} from '../../composables/g7EquityMethodCrossSheet'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)

const CONCLUSION_KEY = 'G7-6-conclusion'
const AUDIT_NOTE_KEY = 'G7-6-audit-note'
const STORAGE_KEY_PREFIX = 'g7-accounting-policy-collapse-'

const DEFAULT_POLICY_ITEMS: string[] = [
  '会计年度',
  '记账本位币',
  '收入确认政策',
  '存货计价方法',
  '存货跌价准备计提',
  '固定资产折旧方法',
  '固定资产折旧年限',
  '固定资产残值率',
  '无形资产摊销方法',
  '无形资产摊销年限',
  '投资性房地产计量模式',
  '长期股权投资核算方法',
  '金融工具分类及计量',
  '金融资产减值模型',
  '应收款项坏账准备计提',
  '固定资产减值准备',
  '资产减值损失确认',
  '借款费用资本化',
  '研发支出资本化',
  '政府补助会计处理',
  '所得税会计处理',
  '租赁会计处理',
  '外币折算方法',
  '职工薪酬确认',
  '股份支付计量',
  '或有事项确认',
  '会计估计变更',
  '前期差错更正',
  '合并报表范围确定',
  '关联方交易定价',
  '资产负债表日后事项',
]

interface PolicyGroup {
  investeeName: string
  investeeId?: string
  rows: AccountingPolicyRow[]
}

type RowFilter = 'all' | 'empty' | 'inconsistent'

interface Summary {
  consistent: number
  inconsistent: number
  na: number
  empty: number
  totalAdj: number
}

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const { exportTemplate, exportData, importData } = useG7EquityMethodImportExport({
  wpId: toRef(props, 'wpId'),
})
const fileInputRef = ref<HTMLInputElement | null>(null)
const aiLoading = ref(false)

const groups = reactive<PolicyGroup[]>([])
const expandedMap = reactive<Record<string, boolean>>({})
const groupFilters = reactive<Record<string, RowFilter>>({})
const conclusion = ref('')
const auditNote = ref('')
const isReadonly = computed(() => !!props.readonly)

function emptySummary(): Summary {
  return { consistent: 0, inconsistent: 0, na: 0, empty: 0, totalAdj: 0 }
}

function summarize(rows: AccountingPolicyRow[]): Summary {
  const s = emptySummary()
  for (const row of rows) {
    if (row.isConsistent === '一致') s.consistent++
    else if (row.isConsistent === '不一致') {
      s.inconsistent++
      s.totalAdj += Number(row.adjustmentAmount) || 0
    } else if (row.isConsistent === '不适用') s.na++
    else s.empty++
  }
  return s
}

function groupSummary(group: PolicyGroup): Summary {
  return summarize(group.rows)
}

const globalSummary = computed(() => summarize(groups.flatMap(g => g.rows)))

function filteredGroupRows(group: PolicyGroup): AccountingPolicyRow[] {
  const filter = groupFilters[group.investeeName] || 'all'
  if (filter === 'empty') return group.rows.filter(r => !r.isConsistent)
  if (filter === 'inconsistent') return group.rows.filter(r => r.isConsistent === '不一致')
  return group.rows
}

function normalizePolicyText(text: string): string {
  return (text || '').replace(/\s+/g, '').trim()
}

function createEmptyRow(seq: number, policyItem = ''): AccountingPolicyRow {
  return {
    id: `ap-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    policyItem,
    investeePolicy: '',
    investorPolicy: '',
    isConsistent: '' as AccountingPolicyRow['isConsistent'],
    adjustmentAmount: 0,
    adjustmentNote: '',
  }
}

function createDefaultRows(): AccountingPolicyRow[] {
  return DEFAULT_POLICY_ITEMS.map((item, i) => createEmptyRow(i + 1, item))
}

function clearAdjustmentIfNotInconsistent(row: AccountingPolicyRow): void {
  if (row.isConsistent !== '不一致') {
    row.adjustmentAmount = 0
    row.adjustmentNote = ''
  }
}

function tryAutoConsistent(row: AccountingPolicyRow): void {
  const a = normalizePolicyText(row.investeePolicy)
  const b = normalizePolicyText(row.investorPolicy)
  if (a && b && a === b && row.isConsistent !== '不一致' && row.isConsistent !== '不适用') {
    row.isConsistent = '一致'
    clearAdjustmentIfNotInconsistent(row)
  }
}

function getCollapseKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getCollapseKey())
    if (raw) Object.assign(expandedMap, JSON.parse(raw))
  } catch { /* ignore */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getCollapseKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore */ }
}

function toggleGroup(name: string): void {
  expandedMap[name] = !expandedMap[name]
  saveCollapseState()
}

function ensureGroupMeta(name: string): void {
  if (expandedMap[name] === undefined) expandedMap[name] = true
  if (!groupFilters[name]) groupFilters[name] = 'all'
}

function pushGroup(name: string, rows?: AccountingPolicyRow[], investeeId = ''): void {
  groups.push({
    investeeName: name,
    investeeId: investeeId || undefined,
    rows: rows ?? createDefaultRows(),
  })
  ensureGroupMeta(name)
}

function persistRows(): void {
  if (isReadonly.value) return
  // debounce 路径：允许「未判断」草稿；「不一致」缺说明不可落库
  const missingNote: string[] = []
  for (const group of groups) {
    for (const row of group.rows) {
      if (row.isConsistent === '不一致' && !normalizePolicyText(row.adjustmentNote)) {
        missingNote.push(`${group.investeeName}#${row.seq}`)
      }
    }
  }
  if (missingNote.length > 0) {
    const shown = missingNote.length <= 3
      ? missingNote.join('、')
      : `${missingNote.slice(0, 3).join('、')}等${missingNote.length}处`
    ElMessage.error(`「不一致」须填写调整说明后方可保存：${shown}`)
    return
  }
  formData.debouncedSave(G7_6_ROWS_KEY, {
    conclusion: JSON.stringify({
      groups: groups.map(g => ({
        investeeName: g.investeeName,
        investeeId: g.investeeId,
        rows: g.rows,
      })),
      rows: groups.flatMap(g => g.rows.map(r => ({
        ...r,
        investeeName: g.investeeName,
        investeeId: g.investeeId,
      }))),
    }),
    remark: null,
  })
}

function persistConclusion(): void {
  if (isReadonly.value) return
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value })
}

function persistAll(): void {
  persistRows()
  persistConclusion()
}

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function onPolicyTextChange(row: AccountingPolicyRow): void {
  tryAutoConsistent(row)
  persistAll()
}

function onConsistencyChange(row: AccountingPolicyRow): void {
  clearAdjustmentIfNotInconsistent(row)
  persistAll()
}

function rowClassName({ row }: { row: AccountingPolicyRow }): string {
  if (row.isConsistent === '不一致') return 'row-inconsistent'
  if (!row.isConsistent) return 'row-empty-consistency'
  return ''
}

function resequence(group: PolicyGroup): void {
  group.rows.forEach((r, i) => { r.seq = i + 1 })
}

function addRow(group: PolicyGroup): void {
  group.rows.push(createEmptyRow(group.rows.length + 1))
  persistAll()
}

function deleteRow(group: PolicyGroup, id: string): void {
  const index = group.rows.findIndex(r => r.id === id)
  if (index < 0) return
  group.rows.splice(index, 1)
  resequence(group)
  persistAll()
}

function markRemainingAsNa(group: PolicyGroup): void {
  let n = 0
  for (const row of group.rows) {
    if (!row.isConsistent) {
      row.isConsistent = '不适用'
      clearAdjustmentIfNotInconsistent(row)
      n++
    }
  }
  if (n === 0) {
    ElMessage.info('没有未判断的事项')
    return
  }
  persistAll()
  ElMessage.success(`「${group.investeeName}」已将 ${n} 项标为不适用`)
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
    pushGroup(inv.name, undefined, inv.investeeId)
    added++
  }
  if (added === 0 && linked === 0) {
    ElMessage.info('合营/联营单位已全部同步')
    return
  }
  persistAll()
  saveCollapseState()
  ElMessage.success(
    added > 0
      ? `已从 G7-4 新增 ${added} 个被投资单位`
      : `已为 ${linked} 个现有分组回填被投资单位ID`,
  )
}

async function addGroupManual(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    const name = value.trim()
    if (groups.some(g => g.investeeName === name)) {
      ElMessage.warning(`「${name}」已存在`)
      return
    }
    pushGroup(name)
    persistAll()
    saveCollapseState()
  } catch { /* cancel */ }
}

function removeGroup(name: string): void {
  const idx = groups.findIndex(g => g.investeeName === name)
  if (idx < 0) return
  groups.splice(idx, 1)
  delete expandedMap[name]
  delete groupFilters[name]
  persistAll()
  saveCollapseState()
}

function loadG714Payload(): any | null {
  return resolveG714PayloadFromChecklist(
    makeG714ConclusionGetter(formData.data.value, props.htmlData?.responses_snapshot),
  )
}

function persistG714Payload(payload: Record<string, any>): void {
  void formData.saveBatch(buildG714DualWriteItems(payload))
}

function syncGroupToG714(group: PolicyGroup): void {
  const adj = groupSummary(group).totalAdj
  if (adj === 0) {
    ElMessage.warning(`「${group.investeeName}」无不一致调整金额，已跳过以免覆盖 G7-14 手工值`)
    return
  }
  const existing = loadG714Payload()
  const result = applyPolicyAdjToG714Payload(existing, group.investeeName, adj, group.investeeId)
  if (!result.ok || !result.payload) {
    ElMessage.error(result.message)
    return
  }
  persistG714Payload(result.payload)
  ElMessage.success(result.message)
}

function syncAllToG714(): void {
  if (groups.length === 0) {
    ElMessage.warning('暂无被投资单位可同步')
    return
  }
  const existing = loadG714Payload()
  const result = applyG76PolicyToG714Payload(existing, {
    groups: groups.map(g => ({
      investeeName: g.investeeName,
      investeeId: g.investeeId,
      rows: g.rows,
    })),
  })
  if (!result.ok || !result.payload) {
    ElMessage.warning(result.message)
    return
  }
  persistG714Payload(result.payload)
  ElMessage.success(result.message)
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void exportTemplate('G7-6')
  if (command === 'export') void exportData('G7-6')
  if (command === 'import') fileInputRef.value?.click()
}

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importData('G7-6', file)
  if (!result) return
  await formData.loadResponses()
  const raw = formData.data.value.get(G7_6_ROWS_KEY)?.conclusion
  const parsed = parseChecklistJson(raw) ?? raw
  if (!applyPayload(parsed)) {
    ElMessage.warning('导入成功但未能解析为会计政策分组，请检查模板')
    return
  }
  ElMessage.success(`已导入并刷新 G7-6（${groups.length} 家）`)
}

async function handleAiConclusion(): Promise<void> {
  if (isReadonly.value || aiLoading.value) return
  aiLoading.value = true
  try {
    const response = await http.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/accounting-policy-conclusion`,
      {
        existingContent: conclusion.value,
        relatedContext: {
          sheet: 'G7-6',
          summary: globalSummary.value,
          groups: groups.map(g => ({
            investeeName: g.investeeName,
            investeeId: g.investeeId,
            summary: groupSummary(g),
            inconsistentRows: g.rows
              .filter(r => r.isConsistent === '不一致')
              .map(r => ({
                policyItem: r.policyItem,
                adjustmentAmount: r.adjustmentAmount,
                adjustmentNote: r.adjustmentNote,
              })),
          })),
        },
      },
    )
    const data = response?.data?.data ?? response?.data ?? response
    const text = extractG7AiText(data)
    if (!text) {
      fillConclusionDraft()
      ElMessage.warning('AI未返回内容，已生成本地结论草稿')
      return
    }
    conclusion.value = String(text)
    persistConclusion()
    ElMessage.success('AI结论生成完成')
  } catch {
    fillConclusionDraft()
    ElMessage.warning('AI暂不可用，已生成本地结论草稿')
  } finally {
    aiLoading.value = false
  }
}

function validateBeforeSave(): boolean {
  const emptyRefs: string[] = []
  const missingNote: string[] = []

  for (const group of groups) {
    for (const row of group.rows) {
      if (!row.isConsistent) emptyRefs.push(`${group.investeeName}#${row.seq}`)
      if (row.isConsistent === '不一致' && !normalizePolicyText(row.adjustmentNote)) {
        missingNote.push(`${group.investeeName}#${row.seq}`)
      }
    }
  }

  if (emptyRefs.length > 0) {
    const shown = emptyRefs.length <= 5 ? emptyRefs.join('、') : `${emptyRefs.slice(0, 5).join('、')}等${emptyRefs.length}处`
    ElMessage.error(`以下位置「是否一致」未选择：${shown}`)
    return false
  }
  if (missingNote.length > 0) {
    const shown = missingNote.length <= 5 ? missingNote.join('、') : `${missingNote.slice(0, 5).join('、')}等${missingNote.length}处`
    ElMessage.error(`以下「不一致」行缺少调整说明：${shown}`)
    return false
  }
  return true
}

function fillConclusionDraft(): void {
  const s = globalSummary.value
  if (s.empty > 0) {
    ElMessage.warning(`仍有 ${s.empty} 处未判断一致性`)
  }
  const perInvestee = groups
    .map(g => {
      const gs = groupSummary(g)
      if (gs.inconsistent === 0) return null
      return `${g.investeeName}（调整 ${fmtAmount(gs.totalAdj)}）`
    })
    .filter(Boolean)
    .join('、')

  if (s.inconsistent === 0) {
    conclusion.value =
      `经核对 ${groups.length} 家合营/联营企业，重要会计政策与投资方一致` +
      `（一致 ${s.consistent} 项，不适用 ${s.na} 项），无需会计政策调整，可据以开展 G7-14 权益法测算。`
  } else {
    conclusion.value =
      `经核对，存在会计政策不一致：${perInvestee || `${s.inconsistent} 项`}，` +
      `调整合计 ${fmtAmount(s.totalAdj)} 元，应同步至 G7-14「会计政策调整」；` +
      `其余一致 ${s.consistent} 项、不适用 ${s.na} 项。除上述差异外，未发现其他重大政策差异。`
  }
  persistConclusion()
  ElMessage.success('已生成结论草稿')
}

function handleSave(): void {
  if (!validateBeforeSave()) return
  persistAll()
  void formData.saveImmediate(G7_6_ROWS_KEY, {
    conclusion: JSON.stringify({
      groups: groups.map(g => ({
        investeeName: g.investeeName,
        investeeId: g.investeeId,
        rows: g.rows,
      })),
      rows: groups.flatMap(g => g.rows.map(r => ({
        ...r,
        investeeName: g.investeeName,
        investeeId: g.investeeId,
      }))),
    }),
    remark: null,
  })
  void formData.saveImmediate(CONCLUSION_KEY, { conclusion: conclusion.value })
  ElMessage.success('会计政策一致性检查已保存')
}

function handleSaveAndSync(): void {
  if (!validateBeforeSave()) return
  handleSave()
  syncAllToG714()
}

function consistencyTagType(value: string): '' | 'success' | 'danger' | 'info' {
  switch (value) {
    case '一致': return 'success'
    case '不一致': return 'danger'
    case '不适用': return 'info'
    default: return ''
  }
}

function parseRow(r: any, idx: number): AccountingPolicyRow {
  const row: AccountingPolicyRow = {
    id: r.id ?? `ap-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    seq: r.seq ?? idx + 1,
    policyItem: r.policyItem ?? r.policy_item ?? '',
    investeePolicy: r.investeePolicy ?? r.investee_policy ?? '',
    investorPolicy: r.investorPolicy ?? r.investor_policy ?? '',
    isConsistent: r.isConsistent ?? r.is_consistent ?? '',
    adjustmentAmount: Number(r.adjustmentAmount ?? r.adjustment_amount ?? 0) || 0,
    adjustmentNote: r.adjustmentNote ?? r.adjustment_note ?? '',
  }
  tryAutoConsistent(row)
  return row
}

function applyPayload(payload: any): boolean {
  if (!payload) return false
  const rawGroups = payload.groups
  if (Array.isArray(rawGroups) && rawGroups.length > 0) {
    for (const g of rawGroups) {
      const name = String(g.investeeName ?? g.investee_name ?? '').trim() || '未命名'
      const investeeId = String(g.investeeId ?? g.investee_id ?? '').trim()
      const rows = (g.rows ?? []).map((r: any, idx: number) => parseRow(r, idx))
      groups.push({
        investeeName: name,
        investeeId: investeeId || undefined,
        rows: rows.length ? rows : createDefaultRows(),
      })
      ensureGroupMeta(name)
    }
    return true
  }
  const rawRows = payload.rows
  if (Array.isArray(rawRows) && rawRows.length > 0) {
    // 兼容旧版扁平结构：无 investeeName 时归入「未分组」
    const map = new Map<string, AccountingPolicyRow[]>()
    for (const r of rawRows) {
      const name = String(r.investeeName ?? r.investee_name ?? '未分组').trim() || '未分组'
      if (!map.has(name)) map.set(name, [])
      map.get(name)!.push(parseRow(r, map.get(name)!.length))
    }
    for (const [name, rows] of map.entries()) {
      const id = String(rows[0] && (rawRows.find((r: any) =>
        String(r.investeeName ?? r.investee_name ?? '未分组').trim() === name,
      )?.investeeId ?? rawRows.find((r: any) =>
        String(r.investeeName ?? r.investee_name ?? '未分组').trim() === name,
      )?.investee_id) || '').trim()
      groups.push({ investeeName: name, investeeId: id || undefined, rows })
      ensureGroupMeta(name)
    }
    return true
  }
  return false
}

onMounted(async () => {
  loadCollapseState()
  await formData.load()

  const saved = parseChecklistJson(formData.data.value.get(G7_6_ROWS_KEY)?.conclusion)
  const htmlPolicy = props.htmlData?.accountingPolicy ?? props.htmlData?.accounting_policy
  if (saved && applyPayload(saved)) {
    // restored
  } else if (htmlPolicy && applyPayload(htmlPolicy)) {
    // from html
  } else {
    // 自动从 G7-4 带出合营/联营（含 investeeId）
    const investees = loadEquityInvestees(formData.data.value.get(G7_4_ROWS_KEY)?.conclusion)
    for (const inv of investees) pushGroup(inv.name, undefined, inv.investeeId)
  }

  const savedConclusion = formData.data.value.get(CONCLUSION_KEY)?.conclusion
  if (savedConclusion) conclusion.value = savedConclusion
  else if (htmlPolicy?.conclusion) conclusion.value = htmlPolicy.conclusion

  auditNote.value = formData.data.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
})
</script>

<style scoped>
.g7-tab-accounting-policy {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left,
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }
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
.procedure-card { margin-bottom: 12px; }
.procedure-card :deep(.el-card__header) {
  padding: 10px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.procedure-list {
  margin: 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.7;
  font-size: 12px;
}
.table-section-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.empty-state {
  text-align: center;
  padding: 32px 16px;
  color: #909399;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  margin-bottom: 12px;
}
.empty-state .el-button { margin: 4px; }
.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  margin-top: 8px;
}
.group-name { font-weight: 600; color: #303133; }
.group-actions { margin-left: auto; display: flex; gap: 4px; }
.collapse-icon { transition: transform 0.2s; }
.collapse-icon.is-collapsed { transform: rotate(-90deg); }
.group-body {
  border: 1px solid #ebeef5;
  border-top: none;
  padding: 8px;
  margin-bottom: 4px;
}
.group-filter-bar { margin-bottom: 8px; }
.policy-table { margin-bottom: 8px; }
.cell-text { white-space: pre-wrap; word-break: break-word; }
:deep(.consistency-empty .el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
:deep(.row-inconsistent) { background: #fef0f0; }
:deep(.row-empty-consistency) { background: #fdf6ec; }
.group-bottom-actions,
.bottom-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 0;
}
.bottom-actions { margin-top: 12px; }
.conclusion-card { margin-top: 16px; }
.conclusion-card :deep(.el-card__header) {
  padding: 10px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.conclusion-text { margin: 0; color: #606266; white-space: pre-wrap; }
.hidden-input { display: none; }
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
</style>
