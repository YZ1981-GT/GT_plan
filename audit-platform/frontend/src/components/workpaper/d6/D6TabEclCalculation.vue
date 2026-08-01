<template>
<div class="d6-tab-ecl-calculation">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表依 CAS22 预期信用损失（ECL）模型测算合同资产（科目1141）应计提的坏账准备，分单项计提与账龄组合计提两部分。</p>
      <p>2. 灰色底纹列为自动计算列：应计提 = 审定余额 × 损失率；差异 = 应计提 − 账面余额，差异≥0.01 时高亮提示。</p>
      <p>3. 损失率应结合历史损失经验、当前状况及前瞻性信息确定，并与 D6-7 政策检查评价一致。</p>
      <p>4. 合计应计提与账面的总差异应查明原因，测算结果回填 D6-3 减值准备明细，为审定表坏账准备提供依据。</p>
      <p>5. CAS22第63条：对于不含重大融资成分的应收账款和合同资产，企业应当始终按照整个存续期的预期信用损失计量其损失准备。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <span class="ao-title">审计目标</span>
    </template>
    <template #default>
      <div class="ao-text">合同资产以恰当的金额包括在财务报表中，与之相关的计价调整已恰当记录。</div>
    </template>
  </el-alert>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left"></div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-7" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ browseRowCount }} 行</el-tag>
    </div>
  </div>

  <!-- 勾稽校验：ECL损失率 ↔ D6-7政策评价 -->
  <el-alert
    v-if="eclPolicyCheck"
    :type="eclPolicyCheck.type"
    :title="eclPolicyCheck.message"
    :closable="false"
    show-icon
    style="margin-bottom: 8px"
  />

  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    fixed
    class="virtual-table"
  />

  <template v-if="!useVirtualScroll || !browseMode">
  <!-- (一) 单项计提 -->
  <div class="ecl-block">
    <div class="block-header">
      <h4 class="block-title">(一) 单项计提坏账准备</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addSingleRow">添加债务人</el-button>
    </div>
    <el-table :data="singleRows" size="small" border stripe style="width:100%">
      <el-table-column label="债务人名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'debtorName', v)" />
          <span v-else>{{ row.debtorName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定余额①" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'auditedBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="损失率②" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'lossRate', v ?? 0)" />
          <span v-else>{{ fmtPct(row.lossRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
      </el-table-column>
      <el-table-column label="账面余额④" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'bookBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="['auto-calc', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="计提依据" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.basis" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'basis', v)" />
          <span v-else>{{ row.basis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSingleRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="subtotal-line">
      单项小计 — 应计提：{{ fmtAmt(singleTotal.provision) }}，账面：{{ fmtAmt(singleTotal.book) }}，差异：{{ fmtAmt(singleTotal.diff) }}
    </div>
  </div>

  <!-- (二) 账龄组合 -->
  <div class="ecl-block">
    <div class="block-header">
      <h4 class="block-title">(二) 账龄组合计提坏账准备</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addAgingGroup">添加组合</el-button>
    </div>

    <div v-for="(group, gIdx) in agingGroups" :key="group.groupId" class="aging-group">
      <div class="group-header">
        <el-input
          v-if="!isReadonly"
          :model-value="group.groupName"
          size="small"
          placeholder="组合名称"
          style="width:200px"
          @change="(v: string) => updateGroupName(group.groupId, v)"
        />
        <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
        <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeAgingGroup(group.groupId)">删除组合</el-button>
      </div>
      <el-table :data="group.rows" size="small" border stripe>
        <el-table-column prop="agingBand" label="账龄" width="100">
          <template #default="{ row }">
            <span :class="{ 'aging-overdue': isOverdueAging(row.agingBand) }">{{ row.agingBand }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定余额①" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'lossRate', v ?? 0)" />
            <span v-else>{{ fmtPct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="账面余额④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'bookBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="['auto-calc', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-line">
        组合小计 — 应计提：{{ fmtAmt(agingGroupTotals[gIdx]?.provision) }}，账面：{{ fmtAmt(agingGroupTotals[gIdx]?.book) }}，差异：{{ fmtAmt(agingGroupTotals[gIdx]?.diff) }}
      </div>
    </div>
  </div>

  <!-- 合计 -->
  <div class="grand-total">
    <span>合计应计提：<strong>{{ fmtAmt(grandTotal.expectedProvision) }}</strong></span>
    <span>合计账面：<strong>{{ fmtAmt(grandTotal.bookBalance) }}</strong></span>
    <span>总差异：<strong :class="{ 'diff-warn': Math.abs(grandTotal.totalDiff) >= 0.01 }">{{ fmtAmt(grandTotal.totalDiff) }}</strong></span>
    <GtIndexChip value="wp:D6-7" :context-project-id="projectId" style="margin-left:8px" />
    <GtIndexChip value="wp:D6-3" :context-project-id="projectId" style="margin-left:4px" />
  </div>

  <el-alert v-if="diffAlert" type="warning" :closable="false" show-icon style="margin-top:12px">
    {{ diffAlert }}
  </el-alert>

  <!-- 源模板底部方法论提示（琥珀块） -->
  <div class="amber-context" style="margin-top:14px">
    <span class="amber-icon">📌</span>
    <div class="amber-text">
      <p><strong>提示：</strong>预期信用损失以客户的违约风险为基础，同一客户的违约风险相同，上市公司对于同一客户的合同资产与应收账款，采用不同计提比例计量预期信用损失时，应充分分析两者存在不同违约风险损失的原因及合理性。由于现金流缺口要基于预期能收到的现金流量进行计算，因此在计量合同资产的预期信用损失时考虑的期限应截止于预期收取现金流量之日，即需要考虑合同资产转为应收款项后可能发生的信用违约事件造成的损失。</p>
      <p><strong>提示2：</strong>预期信用损失计量测试可参考应收账款预期信用损失计量示例。</p>
    </div>
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-7" :context-project-id="projectId" />
          <GtIndexChip value="wp:D6-3" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">三、审计说明</span>
        <div class="opinion-actions">
          <el-button size="small" type="primary" plain @click="aiGenerateNote('explanation')">🤖 AI辅助</el-button>
          <el-button size="small" @click="openReview('D6-8-note-explanation')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :disabled="isReadonly" placeholder="ECL模型参数及损失率选取依据、单项计提判断理由、与D6-7政策检查的一致性分析..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">四、审计结论</span>
        <div class="opinion-actions">
          <el-select
            v-model="selectedConclusionTemplate"
            placeholder="快速选择结论模板"
            size="small"
            clearable
            style="width: 200px; margin-right: 8px"
            @change="onConclusionTemplateSelect"
          >
            <el-option v-for="t in ECL_CONCLUSION_TEMPLATES" :key="t.label" :label="t.label" :value="t.value" />
          </el-select>
          <el-button size="small" type="primary" plain @click="aiGenerateNote('conclusion')">🤖 AI辅助</el-button>
          <el-button size="small" @click="openReview('D6-8-note-conclusion')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }" :disabled="isReadonly" placeholder="减值准备计提充分性结论..." />
    </div>
  </el-card>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabEclCalculation.vue — 减值准备测算 D6-8
 */
import { computed, inject, toRef, ref, type Ref } from 'vue'
import { useD6EclCalculation } from '../composables/useD6EclCalculation'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'
import http from '@/utils/http'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-8',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  singleRows, singleTotal, addSingleRow, removeSingleRow, updateSingleCell,
  agingGroups, agingGroupTotals, addAgingGroup, removeAgingGroup, updateGroupName, updateAgingCell,
  grandTotal, diffAlert, auditNotes,
} = useD6EclCalculation({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

/** 勾稽校验：ECL组合损失率 ↔ D6-7政策检查评价损失率 */
const eclPolicyCheck = computed<{ type: 'info' | 'success' | 'warning'; message: string } | null>(() => {
  const responses = allResponsesRef.value
  if (!responses || responses.size === 0) return null

  // 查找 D6-7 相关数据
  const d67Keys = [...responses.keys()].filter(k => k.startsWith('D6-7'))
  if (d67Keys.length === 0) {
    return { type: 'info', message: '勾稽校验：D6-7 政策检查尚未填写损失率评价数据' }
  }

  // 尝试从 D6-7-eval-loss-rate-{groupId} 或 D6-7-evaluations 读取政策评价损失率
  const policyRates = new Map<string, number>()

  for (const key of d67Keys) {
    if (key.startsWith('D6-7-eval-loss-rate')) {
      const resp = responses.get(key)
      const remark = resp?.remark
      if (remark != null) {
        const rate = typeof remark === 'string' ? parseFloat(remark) : Number(remark)
        if (!isNaN(rate)) {
          // groupId 从 key 末段提取
          const groupId = key.replace('D6-7-eval-loss-rate-', '').replace('D6-7-eval-loss-rate', '')
          policyRates.set(groupId || key, rate)
        }
      }
    }
  }

  // 尝试从 D6-7-evaluations 的 remark JSON 解析
  const evalResp = responses.get('D6-7-evaluations')
  if (evalResp?.remark) {
    try {
      const parsed = typeof evalResp.remark === 'string' ? JSON.parse(evalResp.remark) : evalResp.remark
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          if (item.groupId && item.lossRate != null) {
            policyRates.set(String(item.groupId), Number(item.lossRate))
          }
        }
      } else if (parsed && typeof parsed === 'object') {
        for (const [gId, rate] of Object.entries(parsed)) {
          if (rate != null) policyRates.set(gId, Number(rate))
        }
      }
    } catch { /* JSON解析失败忽略 */ }
  }

  // 如无可比对的政策损失率数据，显示 info
  if (policyRates.size === 0) {
    return { type: 'info', message: '勾稽校验：D6-7 政策检查尚未填写损失率评价数据' }
  }

  // 比对每个 agingGroup 的 lossRate 与政策评价率
  const diffs: string[] = []
  const groups = agingGroups.value
  for (const group of groups) {
    const policyRate = policyRates.get(group.groupId) ?? policyRates.get(group.groupName)
    if (policyRate == null) continue
    for (const row of group.rows) {
      const eclRate = row.lossRate ?? 0
      const diff = Math.abs(eclRate - policyRate)
      if (diff > 0.01) {
        diffs.push(`${group.groupName}-${row.agingBand}(ECL ${fmtPct(eclRate)} vs 政策 ${fmtPct(policyRate)})`)
      }
    }
  }

  if (diffs.length === 0) {
    return { type: 'success', message: '勾稽校验通过：ECL 组合损失率与政策检查评价一致' }
  }

  return {
    type: 'warning',
    message: `勾稽校验：以下组合损失率与D6-7政策评价差异超过1%：${diffs.join('、')}`,
  }
})

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => {
  const flat: Array<{ label: string; auditedBalance: number; expectedProvision: number; difference: number }> = []
  for (const r of singleRows.value) {
    flat.push({
      label: `[单项] ${r.debtorName || '-'}`,
      auditedBalance: r.auditedBalance,
      expectedProvision: r.expectedProvision,
      difference: r.difference,
    })
  }
  for (const g of agingGroups.value) {
    for (const r of g.rows) {
      flat.push({
        label: `[${g.groupName}] ${r.agingBand}`,
        auditedBalance: r.auditedBalance,
        expectedProvision: r.expectedProvision,
        difference: r.difference,
      })
    }
  }
  return flat
})

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('label', '项目', 220),
  virtualNumCol('auditedBalance', '审定余额', 110, fmtAmt),
  virtualNumCol('expectedProvision', '应计提', 110, fmtAmt),
  virtualNumCol('difference', '差异', 100, fmtAmt),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 900,
})

function fmtPct(rate: number): string {
  if (!rate) return '-'
  return `${(rate * 100).toFixed(2)}%`
}

// ─── 结论模板 ─────────────────────────────────────────────────────────────────
const ECL_CONCLUSION_TEMPLATES = [
  {
    label: 'A-计提充分',
    value: '经独立测算，被审计单位合同资产预期信用损失的计量方法符合CAS22要求，损失率选取与历史经验及前瞻性信息一致，单项计提判断合理，账龄组合计提金额与独立测算结果无重大差异，坏账准备计提充分。',
  },
  {
    label: 'B-基本充分需关注',
    value: '经独立测算，被审计单位合同资产坏账准备整体计提基本充分，但存在以下需关注事项：（1）______组合损失率与测算值差异____万元。经分析，该差异原因为______，在可接受范围内/已建议调整。',
  },
  {
    label: 'C-计提不足需调整',
    value: '经独立测算，被审计单位合同资产坏账准备存在计提不足____万元，主要原因：（1）______。已提请管理层补提坏账准备（详见审计调整分录D6-4）。',
  },
]

const selectedConclusionTemplate = ref('')
function onConclusionTemplateSelect(val: string) {
  if (val) {
    auditNotes.value = { ...auditNotes.value, conclusion: val }
    selectedConclusionTemplate.value = ''
  }
}

// ─── 账龄风险标识（3年+标红） ──────────────────────────────────────────────────
function isOverdueAging(band: string): boolean {
  if (!band) return false
  return /[3-9]年|[4-9]年|5年以上|[三四五六七八九十]年/.test(band)
}

// ─── AI辅助生成 ──────────────────────────────────────────────────────────────
async function aiGenerateNote(section: 'explanation' | 'conclusion') {
  try {
    const context: Record<string, string> = {
      '底稿编号': 'D6-8',
      '单项计提行数': String(singleRows.value.length),
      '单项合计应计提': fmtAmt(singleTotal.value.provision),
      '单项合计差异': fmtAmt(singleTotal.value.diff),
      '账龄组合数': String(agingGroups.value.length),
      '合计应计提': fmtAmt(grandTotal.value.expectedProvision),
      '合计账面': fmtAmt(grandTotal.value.bookBalance),
      '总差异': fmtAmt(grandTotal.value.totalDiff),
    }
    if (section === 'conclusion' && auditNotes.value.explanation) {
      context['审计说明'] = auditNotes.value.explanation
    }
    const promptMap = {
      explanation: '根据合同资产减值准备测算数据（单项计提+账龄组合），生成审计说明，包括：ECL模型参数选取依据、损失率与D6-7政策检查的一致性分析、差异原因说明。',
      conclusion: '根据测算结果和审计说明，生成审计结论，明确判断坏账准备计提是否充分、损失率是否合理、是否需要调整。',
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `d6-8-${section}`,
      prompt: promptMap[section],
      context,
      existingContent: section === 'explanation' ? auditNotes.value.explanation : auditNotes.value.conclusion,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (section === 'explanation') {
        auditNotes.value = { ...auditNotes.value, explanation: text }
      } else {
        auditNotes.value = { ...auditNotes.value, conclusion: text }
      }
    }
  } catch {
    // silent - vLLM可能不可用
  }
}
</script>

<style scoped>
.d6-tab-ecl-calculation { padding: 16px; }
.d6-tab-ecl-calculation :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-ecl-calculation :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.ecl-block { margin-bottom: 20px; }
.block-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.block-title { font-size: 14px; font-weight: 600; margin: 0; color: #303133; }
.aging-group { margin-bottom: 16px; padding: 12px; border: 1px solid #ebeef5; border-radius: 6px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.subtotal-line { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.grand-total {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.diff-warn { color: #e6a23c; font-weight: 600; }

/* 账龄风险标红（3年+） */
.aging-overdue { color: #f56c6c; font-weight: 500; }

/* 方法论琥珀块 */
.amber-context {
  padding: 10px 14px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #8a6d3b;
  display: flex;
  gap: 8px;
}
.amber-context .amber-icon { flex-shrink: 0; }
.amber-context .amber-text { flex: 1; }
.amber-context .amber-text p { margin: 4px 0; }

/* 审计目标 */
.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { font-size: 12px; line-height: 1.5; margin-top: 2px; }

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
