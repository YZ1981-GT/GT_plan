<!--
  K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表

  忠实反映致同源模板 K1-5：审计目标（存在/计价分摊）+ 审计过程（选前10名，函证、核对
  支持性证据、识别未识别关联方）+ 前10名查验汇总表（序号/债务人/期初/借贷发生/期末未审/
  坏账准备/账面价值/账龄/经济业务/关联方/协议索引/期后收款）+ 审计说明 + 结论
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-5 大额其他应收款情况分析表</h3>
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

    <el-alert type="warning" :closable="false" class="process-hint">
      <template #title>
        <span>二、审计过程：选择前 10 名大额其他应收款余额，通过函证、与高管及相关人员核对，检查支持性证据，确定其存在性，识别是否存在未识别的关联方。</span>
      </template>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">前 10 名查验汇总表（不含合并范围内关联方）</span></template>
      <el-table :data="tables.rows" border size="small" :max-height="400" class="audit-table">
        <el-table-column label="序号" type="index" width="52" align="center" />
        <el-table-column label="债务人名称" min-width="150" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审余额" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endUnaudited" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.endUnaudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减:坏账准备" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.provision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="账面价值=期末未审余额-坏账准备">{{ fmtAmt((Number(row.endUnaudited)||0) - (Number(row.provision)||0)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发生时间及账龄" min-width="130">
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
        <el-table-column label="关联方" width="80" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" v-model="row.isRelated" @change="persist" />
            <span v-else>{{ row.isRelated ? '√' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="协议/合同索引" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractIndex" size="small" @change="persist" />
            <span v-else>{{ row.contractIndex || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后收款" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.postCollection" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.postCollection) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('rows', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　期末未审余额：{{ fmtAmt(columnSum('rows', 'endUnaudited')) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="针对期后收款的凭证检查详见 K1-12；说明大额款项的核查情况与识别的未识别关联方" @change="persist" />
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
        <li>选取前 10 名大额其他应收款（不含合并范围内关联方）</li>
        <li>通过函证、与高管/相关人员核对、检查支持性证据确认存在性</li>
        <li>关注是否存在未识别的关联方（结合 B19）</li>
        <li>账面价值 = 期末未审余额 - 坏账准备（自动计算）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表 */
import { computed, inject, onMounted } from 'vue'
import { useK1AuditRows, K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const ITEM_ID = 'K1-5-large-amount'
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
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function handleReview() { openReviewDialog('K1-5-large-amount') }
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.process-hint { margin-bottom: 10px; }
.process-hint :deep(.el-alert__title) { font-size: 12px; line-height: 1.55; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
