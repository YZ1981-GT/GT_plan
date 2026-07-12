<!--
  K1TabBadDebtCalc.vue — K1-8 坏账准备测算

  忠实反映致同源模板 K1-8：审计目标（计价分摊）
  （一）单项计提坏账准备（债务人/审定账面余额①/预期信用损失率②/期末应计提③=①×②/
       期末坏账准备账面余额④/差异⑤=③-④/计提依据/索引号）
  （二）押金保证金组合（信用期分档）
  （三）其他组合（账龄分档）
  差异合计=0 勾稽校验 + 审计说明 + 结论
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-8 坏账准备测算</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">其他应收款、坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</p>
    </el-alert>

    <!-- 勾稽状态 -->
    <el-alert :type="totalDiff === 0 ? 'success' : 'warning'" :closable="false" show-icon class="recon-bar">
      <template #title>
        测算合计差异（应计提 - 账面）：{{ fmtAmt(totalDiff) }}
        <span v-if="totalDiff === 0">　✓ 已计提充分</span>
        <span v-else>　⚠ 存在差异，需分析计提是否充分</span>
      </template>
    </el-alert>

    <!-- (一) 单项计提 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（一）单项计提坏账准备</span>
          <el-button v-if="!isReadonly" size="small" @click="addRow('single'); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="tables.single" border size="small" :max-height="260" class="audit-table">
        <el-table-column label="债务人名称" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persist" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定账面余额①" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.balance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预期信用损失率②" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt" @change="persist" />
            <span v-else>{{ pct(row.rate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="③=①×②">{{ fmtAmt(calc(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookProvision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤=③-④" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(diff(row)) > 0.01 }" title="⑤=③-④">{{ fmtAmt(diff(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据及文件" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('single', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">小计　应计提③：{{ fmtAmt(sumCalc('single')) }}　账面④：{{ fmtAmt(columnSum('single', 'bookProvision')) }}</div>
        </template>
      </el-table>
    </el-card>

    <!-- (二) 押金保证金组合 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">（二）押金/保证金组合计提坏账准备（按信用期）</span></template>
      <el-table :data="tables.deposit" border size="small" class="audit-table">
        <el-table-column label="信用期" min-width="140" prop="name" />
        <el-table-column label="审定账面余额①" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.balance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预期信用损失率②" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt" @change="persist" />
            <span v-else>{{ pct(row.rate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
          <template #default="{ row }"><span class="formula-cell" title="③=①×②">{{ fmtAmt(calc(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookProvision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤=③-④" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" :class="{ 'diff-warn': Math.abs(diff(row)) > 0.01 }">{{ fmtAmt(diff(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="计提依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (三) 其他组合（账龄） -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">（三）其他组合计提坏账准备（按账龄）</span></template>
      <el-table :data="tables.aging" border size="small" class="audit-table">
        <el-table-column label="账龄" min-width="160" prop="name" />
        <el-table-column label="审定账面余额①" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.balance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预期信用损失率②" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt" @change="persist" />
            <span v-else>{{ pct(row.rate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
          <template #default="{ row }"><span class="formula-cell" title="③=①×②">{{ fmtAmt(calc(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookProvision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤=③-④" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" :class="{ 'diff-warn': Math.abs(diff(row)) > 0.01 }">{{ fmtAmt(diff(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="计提依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">总计　应计提③：{{ fmtAmt(grandCalc) }}　账面④：{{ fmtAmt(grandBook) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="选取金额大于X且逾期超过Y天账户，与授信部门了解并复核往来函件；预期信用损失率计量参考 D2应收账款示例" @change="persist" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select"
        placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="形成审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期末应计提③ = 审定账面余额① × 预期信用损失率②（自动计算）</li>
        <li>差异⑤ = 应计提③ - 账面④；合计差异应为 0，否则需分析计提充分性</li>
        <li>预期信用损失率参考 D2 应收账款-预期信用损失计提示例</li>
        <li>共同信用风险特征：金融工具类型、信用风险评级、担保物类型、账龄、行业等</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabBadDebtCalc.vue — K1-8 坏账准备测算 */
import { computed, inject, onMounted } from 'vue'
import { useK1AuditRows, K1_CONCLUSION_TEMPLATES, type AuditRow } from '../../composables/useK1AuditRows'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const ITEM_ID = 'K1-8-bad-debt-calc'
const { tables, auditNote, conclusion, conclusionOption, load, addRow, removeRow, columnSum, serialize } =
  useK1AuditRows({ allResponses: allResponsesRef as any, itemId: ITEM_ID, tableKeys: ['single', 'deposit', 'aging'] })

const DEPOSIT_ROWS = ['合同期内', '逾期30天以内', '逾期30-90天', '逾期90天以上']
const AGING_ROWS = ['1年以内/未逾期', '1年-2年/逾期30天以内', '2年-3年/逾期30-90天', '3年-4年/逾期90天-1年', '4年-5年/逾期1年-2年', '5年以上/逾期2年以上']

onMounted(() => {
  load()
  // 预置固定分档行（首次进入）
  if (tables.value.deposit.length === 0) {
    DEPOSIT_ROWS.forEach(name => tables.value.deposit.push(mkFixed(name)))
  }
  if (tables.value.aging.length === 0) {
    AGING_ROWS.forEach(name => tables.value.aging.push(mkFixed(name)))
  }
})

function mkFixed(name: string): AuditRow {
  return { id: `fx-${name}`, name, balance: 0, rate: 0, bookProvision: 0, basis: '', indexNo: '' }
}

// ─── 公式 ────────────────────────────────────────────────────────────────────
function calc(row: AuditRow): number { return (Number(row.balance) || 0) * (Number(row.rate) || 0) }
function diff(row: AuditRow): number { return calc(row) - (Number(row.bookProvision) || 0) }
function sumCalc(key: string): number { return (tables.value[key] ?? []).reduce((s, r) => s + calc(r), 0) }

const grandCalc = computed(() => sumCalc('single') + sumCalc('deposit') + sumCalc('aging'))
const grandBook = computed(() =>
  columnSum('single', 'bookProvision') + columnSum('deposit', 'bookProvision') + columnSum('aging', 'bookProvision')
)
const totalDiff = computed(() => Math.round((grandCalc.value - grandBook.value) * 100) / 100)

function persist() {
  const data = serialize()
  props.allResponses.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: data })
  emit('save', ITEM_ID, { remark: data })
}
function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function pct(v: number | null | undefined): string {
  if (v == null) return '-'
  return (Number(v) * 100).toFixed(2) + '%'
}
function handleReview() { openReviewDialog('K1-8-bad-debt-calc') }
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.recon-bar { margin-bottom: 10px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.diff-warn { color: var(--el-color-danger); font-weight: 600; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
