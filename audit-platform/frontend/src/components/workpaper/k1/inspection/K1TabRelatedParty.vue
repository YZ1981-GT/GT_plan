<!--
  K1TabRelatedParty.vue — K1-11 关联方及交易检查表

  忠实反映致同源模板 K1-11：关注关联方其他应收款真实性/合理性/合法性/会计处理，
  考虑未识别关联方。明细表（关联方/关联关系/期初/借贷发生/期末/坏账准备/账面价值/
  账龄/款项性质/期后收款/索引号/备注）+ 审计说明 + 结论。关联关系分类参考。
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-11 关联方及交易检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
        <el-button v-if="!isReadonly" size="small" @click="addRow('rows'); persist()">＋ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">关注对关联方的其他应收款的真实性、合理性、合法性、会计处理是否正确，考虑是否存在未识别的关联方，检查关联交易和余额披露是否正确。</p>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、关联方及交易明细</span></template>
      <el-table :data="tables.rows" border size="small" :max-height="400" class="audit-table">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="关联方名称" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persist" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联关系" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relation" size="small" filterable allow-create @change="persist">
              <el-option v-for="opt in relationOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.relation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方发生" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方发生" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endBalance" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
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
            <span class="formula-cell" title="账面价值=期末余额-坏账准备">{{ fmtAmt((Number(row.endBalance)||0) - (Number(row.provision)||0)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.aging" size="small" @change="persist" />
            <span v-else>{{ row.aging || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="款项性质" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.nature" size="small" @change="persist" />
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后收款" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.postCollection" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.postCollection) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
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
          <div class="table-total">小计　期末余额：{{ fmtAmt(columnSum('rows', 'endBalance')) }}</div>
        </template>
      </el-table>
      <div class="relation-ref">
        <span class="rr-label">关联关系分类参考：</span>
        <el-tag v-for="opt in relationOptions" :key="opt" size="small" effect="plain" class="rr-tag">{{ opt }}</el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="针对期后收款的凭证检查详见 K1-12；关注是否存在未识别关联方，关联交易及余额披露是否正确" @change="persist" />
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
        <li>核对关联方其他应收款的真实性、合理性、合法性及会计处理正确性</li>
        <li>考虑是否存在未识别的关联方（结合 B19 识别关联方程序）</li>
        <li>账面价值 = 期末余额 - 坏账准备（自动计算）</li>
        <li>关联关系分类：实际控制人/控股股东/附属企业/5%以上股东/联营/合营/关键管理人员/其他</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabRelatedParty.vue — K1-11 关联方及交易检查表 */
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

const relationOptions = [
  '实际控制人', '控股股东', '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织', '联营企业', '合营企业',
  '董高监等关键管理人员', '其他关联方',
]

const allResponsesRef = computed(() => props.allResponses)
const ITEM_ID = 'K1-11-related-party'
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
function handleReview() { openReviewDialog('K1-11-related-party') }
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.relation-ref { margin-top: 10px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.rr-label { font-size: 12px; color: var(--el-text-color-secondary); }
.rr-tag { margin: 0; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
