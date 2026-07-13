<template>
  <div class="h7-tab-addition-cost">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：验证本期生产性生物资产增加（外购/自行栽培繁殖/在建工程转入）的真实性、完整性与计价准确性，成本归集符合 CAS 5《生物资产》。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-6" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-6 增加检查（成本模式）— {{ rows.length }}项 合计 {{ fmtAmt(totalAmount) }}
            <GtIndexChip value="wp:H7-2" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H7-6')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>符合确认条件：{{ qualifiedCount }} 项，金额 {{ fmtAmt(qualifiedAmount) }}</span>
        <span :class="{ 'text-warn': totalAmount > 0 && qualifiedAmount !== totalAmount }">
          与 H7-2 明细表本期增加合计应一致
        </span>
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="persistRows" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="资产类别" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" @change="persistRows">
              <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseType" label="增加方式" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.increaseType" size="small" @change="persistRows">
              <el-option v-for="t in INCREASE_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.increaseType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="入账原值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="acquireDate" label="增加日期" width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.acquireDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:120px" @change="persistRows" />
            <span v-else>{{ row.acquireDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="costBasis" label="成本构成/依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.costBasis" size="small" placeholder="买价+税费+运费/饲养费用归集" @change="persistRows" />
            <span v-else>{{ row.costBasis }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="qualified" label="符合确认条件" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.qualified" size="small" style="width:92px" @change="persistRows">
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
            </el-select>
            <el-tag v-else :type="row.qualified === '符合' ? 'success' : 'danger'" size="small">{{ row.qualified || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="检查结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="persistRows" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增增加项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录增加检查过程、抽凭结果与异常处理" @blur="persist('H7-6-cost-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-6-cost-conclusion', auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>成本模式下生产性生物资产按成本（买价+相关税费+运输费等）初始计量（CAS 5 第九条）。</li>
        <li>自行栽培/繁殖的生物资产成本为达到预定生产经营目的前发生的必要支出（种苗/饲料/人工/应分摊的间接费用）。</li>
        <li>在建工程（未成熟生产性生物资产）达到预定生产经营目的时转入生产性生物资产。</li>
        <li>本期增加合计应与 H7-2 明细表本期增加、H7-1 审定表借方发生额勾稽一致。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7AdditionCheck } from '../../composables/useH7AdditionCheck'
import { calcSubtotal } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const check = useH7AdditionCheck(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const CATEGORY_OPTIONS = ['经济林木', '产畜（种畜/役畜）', '产蛋/产奶禽畜', '水产养殖', '其他']
const INCREASE_TYPES = ['外购', '自行栽培/繁殖', '在建工程转入', '接受捐赠', '互转转入', '其他']

interface Row {
  rowId: string
  assetName: string
  category: string
  increaseType: string
  amount: number
  acquireDate: string
  costBasis: string
  voucherNo: string
  qualified: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

const totalAmount = computed(() => calcSubtotal(rows.value.map((r) => Number(r.amount) || 0)))
const qualifiedRows = computed(() => rows.value.filter((r) => r.qualified === '符合'))
const qualifiedCount = computed(() => qualifiedRows.value.length)
const qualifiedAmount = computed(() => calcSubtotal(qualifiedRows.value.map((r) => Number(r.amount) || 0)))

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    category: raw.category ?? '',
    increaseType: raw.increaseType ?? '',
    amount: Number(raw.amount) || 0,
    acquireDate: raw.acquireDate ?? '',
    costBasis: raw.costBasis ?? '',
    voucherNo: raw.voucherNo ?? '',
    qualified: raw.qualified ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = check.getString('H7-6-cost-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = check.getString('H7-6-cost-note')
  auditConclusion.value = check.getString('H7-6-cost-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-6-cost-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增增加项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) {
      rows.value.push(normalize({ assetName: value }))
      persistRows()
    }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-addition-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-warn { color: var(--el-color-warning); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
