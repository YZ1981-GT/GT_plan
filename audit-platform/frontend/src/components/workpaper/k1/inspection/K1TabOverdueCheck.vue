<!--
  K1TabOverdueCheck.vue — K1-10 长期未收回款项检查表

  忠实反映致同源模板 K1-10：审计目标（存在/计价分摊）+ 长期未收回明细表
  （债务人/期初/借贷发生/期末/账龄/经济业务/未收回原因/是否诉讼/是否无法收回/
   处理计划/坏账准备/审定余额/期后收款/备注）+ 审计说明 + 结论
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-10 长期未收回款项检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
        <el-button v-if="!isReadonly" size="small" @click="addRow('rows'); persist()">＋ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应收款、坏账准备是存在的，且已记录于恰当的账户；</li>
        <li><b>计价和分摊：</b>其他应收款、坏账准备以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录，披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、长期未收回款项明细</span></template>
      <el-table :data="tables.rows" border size="small" :max-height="420" class="audit-table"
        :row-class-name="riskRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="债务人名称" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.aging" size="small" @change="persist" />
            <span v-else>{{ row.aging || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="经济业务说明" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessDesc" size="small" @change="persist" />
            <span v-else>{{ row.businessDesc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未收回原因" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="persist" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否诉讼" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.litigation" size="small" @change="persist">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.litigation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否无法收回" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.unrecoverable" size="small" @change="persist">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.unrecoverable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处理计划" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.plan" size="small" @change="persist" />
            <span v-else>{{ row.plan || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="坏账准备" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.provision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.auditedBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后收款" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.postCollection" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.postCollection) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('rows', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　期末余额：{{ fmtAmt(columnSum('rows', 'endBalance')) }}　坏账准备：{{ fmtAmt(columnSum('rows', 'provision')) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="针对期后收款的凭证检查详见 K1-12；分析账龄较长原因（纠纷/付款能力等），评估坏账准备计提是否充分" @change="persist" />
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
      <summary>编制提示（CSRC 551-9）</summary>
      <ul>
        <li>账龄较长的其他应收款，判断是否长期挂账推迟正常开支或无需支付，检查原始凭证，必要时函证</li>
        <li>实施上述程序未见异常后，分析账龄长原因（纠纷/对方付款能力），评估坏账准备计提充分性</li>
        <li>标红行：判定为"无法收回"或"涉诉"，重点关注减值充分性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabOverdueCheck.vue — K1-10 长期未收回款项检查表 | Req 8.x */
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
const ITEM_ID = 'K1-10-overdue'
const { tables, auditNote, conclusion, conclusionOption, load, addRow, removeRow, columnSum, serialize } =
  useK1AuditRows({ allResponses: allResponsesRef as any, itemId: ITEM_ID, tableKeys: ['rows'] })

onMounted(() => load())

function persist() {
  const data = serialize()
  props.allResponses.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: data })
  emit('save', ITEM_ID, { remark: data })
}
function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}
function riskRowClass({ row }: { row: AuditRow }): string {
  return row.unrecoverable === '是' || row.litigation === '是' ? 'risk-row' : ''
}
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function handleReview() { openReviewDialog('K1-10-overdue') }
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.audit-table :deep(.risk-row td) { background-color: #fff7ed !important; }
.conclusion-card { margin-bottom: 10px; }
.section-card + .conclusion-card :deep(.el-card__header),
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
