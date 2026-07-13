<template>
  <div class="g1-contract-cf">
    <div class="section-head">
      <h3 class="sheet-title">G1-10 合同现金流量特征（SPPI 逐项分析）</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">新增投资项目</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-9" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-10-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：逐项测试金融资产合同现金流量特征（SPPI），确认现金流量是否仅为对本金和未偿付本金金额利息的支付，为分类适当性（G1-9）提供依据。"
      class="objective-alert"
    />

    <div class="methodology">
      合同现金流量特征测试（SPPI）：逐项检查合同条款，判断现金流量是否仅为对本金和未偿付本金金额的利息的支付。
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ rows.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <!-- 虚拟滚动速览（只读） -->
    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="rows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="44"
      :header-height="42"
      fixed
      class="virtual-table"
    />

    <!-- 编辑表格 -->
    <el-table v-else :data="rows" border size="small" max-height="560">
      <el-table-column label="序号" width="60" fixed="left">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="投资项目" width="160" fixed="left">
        <template #default="{ row }">
          <el-input v-model="row.investItem" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { investItem: row.investItem })" />
        </template>
      </el-table-column>
      <el-table-column
        v-for="col in narrativeCols"
        :key="col.prop"
        :label="col.label"
        :min-width="col.minWidth"
      >
        <template #default="{ row }">
          <el-input v-model="row[col.prop]" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }"
            size="small" :disabled="isReadonly" @change="updateRow(row.id, { [col.prop]: row[col.prop] })" />
        </template>
      </el-table-column>
      <el-table-column label="SPPI结论" width="130">
        <template #default="{ row }">
          <el-select v-model="row.sppiConclusion" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { sppiConclusion: row.sppiConclusion })">
            <el-option value="pass" label="通过" />
            <el-option value="fail" label="不通过" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.auditEval" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }"
            size="small" :disabled="isReadonly" @change="updateRow(row.id, { auditEval: row.auditEval })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）执行的合同现金流量特征（SPPI）测试程序及结果；（2）逐项条款分析的关键判断及例外情形。" />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对合同现金流量特征分析的整体复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐项检查是否含本金、利息构成、修改的货币时间价值、提前还款/展期条款、非追索权特征。</li>
        <li>任一条款导致现金流量不符合 SPPI，则结论为「不通过」，应分类为 FVTPL。</li>
        <li>行数超过 30 行时启用虚拟滚动速览，双击或切换按钮进入编辑模式。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject, h } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'
import { virtualTextCol } from '../../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const DATA_KEY = 'G1-10-rows'
const CONCLUSION_KEY = 'G1-10-conclusion'

interface ContractCashflowRow {
  id: string
  investItem: string
  contractTermDesc: string
  hasPrincipal: string
  interestComposition: string
  timeValueModification: string
  prepaymentExtension: string
  nonRecourseFeature: string
  sppiConclusion: string
  auditEval: string
}

const narrativeCols = [
  { prop: 'contractTermDesc' as const, label: '合同条款描述', minWidth: 180 },
  { prop: 'hasPrincipal' as const, label: '是否含本金', minWidth: 130 },
  { prop: 'interestComposition' as const, label: '利息构成分析', minWidth: 160 },
  { prop: 'timeValueModification' as const, label: '修改的货币时间价值', minWidth: 170 },
  { prop: 'prepaymentExtension' as const, label: '提前还款/展期条款', minWidth: 170 },
  { prop: 'nonRecourseFeature' as const, label: '非追索权特征', minWidth: 150 },
]

function emptyRow(id: string): ContractCashflowRow {
  return {
    id,
    investItem: '',
    contractTermDesc: '',
    hasPrincipal: '',
    interestComposition: '',
    timeValueModification: '',
    prepaymentExtension: '',
    nonRecourseFeature: '',
    sppiConclusion: '',
    auditEval: '',
  }
}

function loadRows(): ContractCashflowRow[] {
  const raw = props.allResponses.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow('1')]
  try {
    const parsed = JSON.parse(raw) as ContractCashflowRow[]
    return Array.isArray(parsed) && parsed.length ? parsed : [emptyRow('1')]
  } catch {
    return [emptyRow('1')]
  }
}

const rows = ref<ContractCashflowRow[]>(loadRows())
const conclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '')

const AUDIT_NOTE_KEY = 'G1-10-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const SPPI_LABEL: Record<string, string> = { pass: '通过', fail: '不通过' }

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('investItem', '投资项目', 180),
  virtualTextCol('contractTermDesc', '合同条款描述', 220),
  virtualTextCol('interestComposition', '利息构成分析', 200),
  virtualTextCol('prepaymentExtension', '提前还款/展期条款', 200),
  {
    key: 'sppiConclusion',
    dataKey: 'sppiConclusion',
    title: 'SPPI结论',
    width: 120,
    cellRenderer: ({ cellData }) =>
      h('span', {}, SPPI_LABEL[String(cellData)] ?? '-'),
  },
])

const { browseMode, useVirtualScroll, tableWidth, tableHeight, toggleBrowseMode } = useWorkpaperBrowseMode({
  rows,
  virtualColumns,
  tableWidth: 1120,
})

function persist() {
  if (props.isReadonly) return
  props.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
}

function updateRow(id: string, patch: Partial<ContractCashflowRow>) {
  if (props.isReadonly) return
  rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
  persist()
}

async function addRow() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '投资项目名称不能为空',
    })
    rows.value = [...rows.value, { ...emptyRow(`row-${Date.now()}`), investItem: value }]
    persist()
  } catch {
    /* cancelled */
  }
}

function removeRow(id: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  rows.value = rows.value.filter((r) => r.id !== id)
  persist()
}

watch(conclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: v })
})
</script>

<style scoped>
.g1-contract-cf { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-contract-cf :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-contract-cf :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.methodology { margin-bottom: 12px; padding: 8px 12px; background: #fdf6ec; border-left: 3px solid #e6a23c; font-size: 12px; color: #8a6d3b; border-radius: 2px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; border: 1px solid #ebeef5; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
