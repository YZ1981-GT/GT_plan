<template>
  <div class="h3-tab-detail-fair">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（公允价值模式）</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产明细表（公允价值模式），分「基本信息 / 公允变动」两区段，行数据跨区段同步。</p>
        <p>2. 期末公允 = 期初 + 本期增加 − 本期减少 + 转入 − 转出 + 公允价值变动；公允价值模式下不计提折旧与减值（CAS3第10条）。</p>
        <p>3. 必须填写公允价值来源（活跃市场报价/评估机构报告等）；涉及评估的须填写评估依据（市场法/收益法/成本法）。</p>
        <p>4. 公允价值变动损益将自动汇总至 G13 公允价值变动损益科目，关注与 H3-8 公允价值复核表的勾稽。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：逐项核实投资性房地产（公允价值模式）的期初/期末公允价值及公允价值变动的真实、准确与计量恰当，支持 H3-1 审定表及 G13 损益核查。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag size="small" :type="crossValidationDiff === 0 ? 'success' : 'danger'">
        {{ crossValidationDiff === 0 ? '已与H3-1勾稽' : `与H3-1差异 ${fmtNum(crossValidationDiff)}` }}
      </el-tag>
      <el-tag
        v-if="unmatchedCategory.unmatchedCount > 0"
        size="small"
        type="warning"
      >
        非标准类别 {{ unmatchedCategory.unmatchedCount }} 行 / {{ fmtNum(unmatchedCategory.unmatchedEnd) }}
      </el-tag>
    </div>

    <!-- 汇总看板 -->
    <div class="summary-strip">
      <div class="summary-card begin">
        <div class="sc-label">期初公允合计</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.fairValueBegin) }}</div>
      </div>
      <div class="summary-card inc">
        <div class="sc-label">本期增加</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.fairIncrease) }}</div>
      </div>
      <div class="summary-card dec">
        <div class="sc-label">本期减少</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.fairDecrease) }}</div>
      </div>
      <div class="summary-card change" :class="subtotalRow.fairValueChange >= 0 ? 'positive' : 'negative'">
        <div class="sc-label">公允价值变动</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.fairValueChange) }}</div>
      </div>
      <div class="summary-card end">
        <div class="sc-label">期末公允合计</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.fairValueEnd) }}</div>
      </div>
      <div class="summary-card restrict">
        <div class="sc-label">权属受限</div>
        <div class="sc-value">{{ restrictedCount }} 项</div>
      </div>
      <div class="summary-card mortgage">
        <div class="sc-label">抵押/质押</div>
        <div class="sc-value">{{ mortgagedCount }} 项</div>
      </div>
    </div>

    <el-table
      v-if="categorySubtotals.length"
      :data="categorySubtotals"
      border
      size="small"
      class="category-table"
    >
      <el-table-column prop="category" label="资产类别小计" min-width="140" />
      <el-table-column prop="count" label="项数" width="70" align="center" />
      <el-table-column label="期末公允" min-width="130" align="right">
        <template #default="{ row }">{{ fmtNum(row.fairValueEnd) }}</template>
      </el-table-column>
      <el-table-column label="公允变动" min-width="130" align="right">
        <template #default="{ row }">{{ fmtNum(row.fairValueChange) }}</template>
      </el-table-column>
    </el-table>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddAsset">
        + 添加资产行
      </el-button>
      <el-dropdown size="small" class="export-dropdown" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="doExportTemplate">导出空白模板</el-dropdown-item>
            <el-dropdown-item @click="doExportData">导出当前数据</el-dropdown-item>
            <el-dropdown-item :divided="true" @click="doImportData">从Excel导入</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileSelected" />
    </div>

    <!-- ───────────── 区段1：基本信息 ───────────── -->
    <template v-if="activeSegment === '基本信息'">
      <div class="segment-header basic-header">一、基本信息</div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryBasic">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
          <template #default="{ row }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="assetType" label="类别" min-width="120">
          <template #default="{ row }">
            <el-select v-model="row.assetType" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option v-for="t in ASSET_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="位置/地址" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.location" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="area" label="面积(㎡)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.area" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="acquireDate" label="取得日期" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.acquireDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueBegin" label="期初公允" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValueBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末公允" min-width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少+转入-转出+公允变动（在公允变动区段录入）">{{ fmtNum(row.fairValueEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairValueSource" label="公允价值来源" min-width="150">
          <template #default="{ row }">
            <el-select v-model="row.fairValueSource" size="small" :disabled="isReadonly" style="width:100%" allow-create filterable @change="onCellChange(row)">
              <el-option v-for="s in FAIR_VALUE_SOURCE_OPTIONS" :key="s" :label="s" :value="s" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="appraisalBasis" label="评估依据" min-width="110">
          <template #default="{ row }">
            <el-select v-model="row.appraisalBasis" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option v-for="b in APPRAISAL_BASIS_OPTIONS" :key="b" :label="b || '（无）'" :value="b" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="ownershipRestricted" label="权属受限" min-width="90" align="center">
          <template #default="{ row }">
            <el-select v-model="row.ownershipRestricted" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="—" value="" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="mortgaged" label="抵押/质押" min-width="90" align="center">
          <template #default="{ row }">
            <el-select v-model="row.mortgaged" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="—" value="" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text :disabled="isReadonly" @click="handleRemoveRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ───────────── 区段2：公允变动 ───────────── -->
    <template v-if="activeSegment === '公允变动'">
      <div class="segment-header fair-header">二、公允价值变动明细</div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryFair">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
        <el-table-column prop="assetType" label="类别" min-width="100" fixed />
        <el-table-column prop="changeDate" label="增减日期" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.changeDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="changeType" label="增减方式" min-width="130">
          <template #default="{ row }">
            <el-select v-model="row.changeType" size="small" :disabled="isReadonly" style="width:100%" allow-create filterable @change="onCellChange(row)">
              <el-option v-for="t in FAIR_CHANGE_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="counterAccount" label="对方科目" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairIncrease" label="本期增加" min-width="110" align="right" class-name="inc-col">
          <template #default="{ row }">
            <el-input v-model.number="row.fairIncrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairDecrease" label="本期减少" min-width="110" align="right" class-name="dec-col">
          <template #default="{ row }">
            <el-input v-model.number="row.fairDecrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入" min-width="100" align="right" class-name="inc-col">
          <template #default="{ row }">
            <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出" min-width="100" align="right" class-name="dec-col">
          <template #default="{ row }">
            <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueChange" label="公允价值变动" min-width="120" align="right" class-name="change-col">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueBegin" label="期初公允" min-width="110" align="right" />
        <el-table-column label="期末公允" min-width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少+转入-转出+变动">{{ fmtNum(row.fairValueEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text :disabled="isReadonly" @click="handleRemoveRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ───────────── 区段3：审定调整 ───────────── -->
    <template v-if="activeSegment === '审定调整'">
      <div class="segment-header audit-header">三、审定调整（未审 / AJE / RJE / 审定）</div>
      <div class="toolbar-inline">
        <el-button size="small" :disabled="isReadonly" @click="handleSeedUnadj">从账面期末带入未审数</el-button>
        <span class="hint-text">审定数 = 未审 + AJE + RJE；公允变动审定同步勾稽 H3-1 / G13</span>
      </div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryAudit">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="130" fixed />
        <el-table-column label="期末公允" align="center">
          <el-table-column prop="fairUnadj" label="未审" min-width="110" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fairUnadj" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="fairAje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fairAje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="fairRje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fairRje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="审定" min-width="110" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.fairAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="公允价值变动" align="center">
          <el-table-column prop="fvChangeUnadj" label="未审" min-width="110" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fvChangeUnadj" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="fvChangeAje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fvChangeAje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="fvChangeRje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.fvChangeRje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="审定" min-width="110" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtNum(row.fvChangeAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </template>

    <!-- 交叉验证差异提示 -->
    <div v-if="crossValidationDiff !== 0" class="cross-validation-warn">
      <el-alert type="error" :closable="false" show-icon
        :title="`明细期末公允合计与 H3-1 审定数差异：${fmtNum(crossValidationDiff)}，请核对。`"
      />
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-fair')">AI生成</el-button>
            <el-button size="small" circle @click="openReview('H3-2-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：明细逐项核对情况、公允价值来源与评估报告复核、增减变动核查过程（关注凭证/合同）、公允价值变动合理性分析、与 H3-1 及 H3-8 勾稽差异及原因。"
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="A、未见异常。B、除上述事项外未见异常。C、存在重大未调整事项，不可确认。"
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDetailFair.vue — H3-2 明细表（公允价值模式）
 * 2区段Tab + 序号 + 增减日期/方式/凭证号/对方科目 + 公允来源/评估依据 + 行删除 + 导入导出
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH3DetailFair,
  FAIR_VALUE_SOURCE_OPTIONS,
  APPRAISAL_BASIS_OPTIONS,
  FAIR_CHANGE_TYPE_OPTIONS,
} from '../../composables/useH3DetailFair'
import { ASSET_TYPE_OPTIONS } from '../../composables/useH3DetailCost'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport } from '../../composables/useH3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('fair_value'),
})

const {
  rows, subtotal: subtotalRow, categorySubtotals, unmatchedCategory, restrictedCount, mortgagedCount,
  crossValidationDiff, addRow, removeRow, updateCell, seedUnadjFromBook, loadRows,
} = useH3DetailFair({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const { exportTemplate, exportData, importData } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref<'cost' | 'fair_value'>('fair_value'),
  onImported: () => loadRows(),
})

const activeSegment = ref('基本信息')
const segmentOptions = ['基本信息', '公允变动', '审定调整']
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────────────
const NOTE_KEY = 'H3-2-fair-audit-note'
const CONCLUSION_KEY = 'H3-2-fair-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

// ─── Row 操作 ─────────────────────────────────────────────────────────────────
async function handleAddAsset() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '添加资产行', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  if (value) addRow(value)
}

async function handleRemoveRow(rowId: string) {
  await ElMessageBox.confirm('确认删除该资产行？删除后不可恢复。', '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  removeRow(rowId)
}

async function handleSeedUnadj() {
  await ElMessageBox.confirm('将用账面期末公允/公允变动覆盖各行「未审数」，是否继续？', '带入未审数', {
    confirmButtonText: '确认带入',
    cancelButtonText: '取消',
    type: 'info',
  })
  seedUnadjFromBook()
  ElMessage.success('已从账面期末带入未审数')
}

function onCellChange(row: any) { updateCell(row.rowId) }

// ─── 格式化 ───────────────────────────────────────────────────────────────────
function fmtNum(v: number): string {
  if (!v || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtNumRaw(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────
function _buildSummary(propMap: Record<string, () => number>) {
  return ({ columns }: { columns: any[] }): string[] =>
    columns.map((col, idx) => {
      if (idx === 0) return '合计'
      const fn = propMap[col.property as string]
      if (fn) return fmtNumRaw(fn())
      const lmap: Record<string, () => number> = {
        '期末公允': () => subtotalRow.value.fairValueEnd,
        '审定': () => subtotalRow.value.fairAudited,
      }
      const lfn = lmap[col.label as string]
      if (lfn && col.label !== '审定') return fmtNumRaw(lfn())
      if (col.label === '审定') {
        // 两套嵌套「审定」列：期末公允 / 公允变动 — 无法区分时返回空，由 prop 合计覆盖
        return ''
      }
      return ''
    })
}

const getSummaryBasic = _buildSummary({
  area: () => subtotalRow.value.area,
  fairValueBegin: () => subtotalRow.value.fairValueBegin,
})

const getSummaryFair = _buildSummary({
  fairValueBegin: () => subtotalRow.value.fairValueBegin,
  fairIncrease: () => subtotalRow.value.fairIncrease,
  fairDecrease: () => subtotalRow.value.fairDecrease,
  transferIn: () => subtotalRow.value.transferIn,
  transferOut: () => subtotalRow.value.transferOut,
  fairValueChange: () => subtotalRow.value.fairValueChange,
})

const getSummaryAudit = _buildSummary({
  fairUnadj: () => subtotalRow.value.fairUnadj,
  fairAje: () => subtotalRow.value.fairAje,
  fairRje: () => subtotalRow.value.fairRje,
  fvChangeUnadj: () => subtotalRow.value.fvChangeUnadj,
  fvChangeAje: () => subtotalRow.value.fvChangeAje,
  fvChangeRje: () => subtotalRow.value.fvChangeRje,
})

// ─── 导入导出 ─────────────────────────────────────────────────────────────────
async function doExportTemplate() { await exportTemplate('H3-2') }
async function doExportData() { await exportData('H3-2') }
function doImportData() { fileInputRef.value?.click() }

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await importData('H3-2', file)
  if (result?.success) ElMessage.success(`H3-2（公允）已导入 ${result.rowCount} 行`)
  input.value = ''
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}

function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-detail-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #722ed1; background: #f9f0ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #722ed1; user-select: none; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; }
.guidance-content p { margin: 3px 0; }

/* 工具栏 */
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 汇总看板 */
.summary-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.summary-card { display: flex; flex-direction: column; min-width: 130px; padding: 8px 14px; border-radius: 6px; border: 1px solid var(--el-border-color-lighter); }
.sc-label { font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.sc-value { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.summary-card.begin  { background: #e6f4ff; border-color: #91d5ff; }
.summary-card.inc    { background: #f6ffed; border-color: #95de64; }
.summary-card.dec    { background: #fff2f0; border-color: #ffccc7; }
.summary-card.change { background: #fff7e6; border-color: #ffd591; }
.summary-card.change.positive .sc-value { color: #389e0d; }
.summary-card.change.negative .sc-value { color: #cf1322; }
.summary-card.end    { background: #f9f0ff; border-color: #d3adf7; }
.summary-card.restrict { background: #fffbe6; border-color: #ffe58f; }
.summary-card.mortgage { background: #fff1f0; border-color: #ffa39e; }
.category-table { margin-bottom: 14px; }

/* 区段标题 */
.segment-header { padding: 6px 10px; font-weight: 600; font-size: 13px; border-radius: 4px; margin-bottom: 8px; }
.basic-header { background: #e6f4ff; color: #0958d9; border-left: 3px solid #1677ff; }
.fair-header  { background: #f9f0ff; color: #531dab; border-left: 3px solid #722ed1; }
.audit-header { background: #f6ffed; color: #237804; border-left: 3px solid #52c41a; }
.toolbar-inline { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); }

/* 操作栏 */
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.export-dropdown { margin-left: auto; }

/* 表格 */
.audit-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.inc-col .cell)    { background: rgba(82, 196, 26, 0.06); }
.audit-table :deep(.dec-col .cell)    { background: rgba(255, 77, 79, 0.06); }
.audit-table :deep(.change-col .cell) { background: rgba(250, 173, 20, 0.08); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-weight: 500; }
.seq-cell { color: var(--el-text-color-secondary); font-size: 12px; }

/* 交叉验证 */
.cross-validation-warn { margin: 12px 0; }

/* 审计说明 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
</style>
