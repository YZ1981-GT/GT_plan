<!--
  K1TabWriteoffCheck.vue — K1-9 坏账准备转回（收回）、核销检查表

  忠实反映致同源模板 K1-9：审计目标（坏账准备计提充分性 + 转回/收回/转销恰当性）
  （一）本期重要的坏账准备转回检查（单位/转回原因/收回方式/原依据/收回或转回金额/
       收回或转回前累计已计提/合理性分析/索引号）
  （二）本期重要的核销检查（单位/性质/核销金额/核销原因/履行程序/是否关联方/合理性/索引号）
  + 审计说明 + 结论
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-9 坏账准备转回（收回）、核销检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">确定其他应收款坏账准备计提是否充分，坏账准备转回、收回、转销是否恰当；核销依据是否符合规定、会计处理是否正确；已核销坏账重新收回的会计处理是否正确。</p>
    </el-alert>

    <!-- (一) 转回检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、(一) 本期重要的坏账准备转回检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addRow('reversal'); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="tables.reversal" border size="small" :max-height="300" class="audit-table">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="单位名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" @change="persist" />
            <span v-else>{{ row.unit || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="persist" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回方式" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.method" size="small" @change="persist" />
            <span v-else>{{ row.method || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确定坏账准备的依据" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回或转回金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回/转回前累计已计提坏账准备" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumProvision" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accumProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.analysis" size="small" @change="persist" />
            <span v-else>{{ row.analysis || '-' }}</span>
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
            <el-button size="small" type="danger" link @click="removeRow('reversal', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　收回或转回金额：{{ fmtAmt(columnSum('reversal', 'amount')) }}</div>
        </template>
      </el-table>
    </el-card>

    <!-- (二) 核销检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、(二) 本期重要的核销检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addRow('writeoff'); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="tables.writeoff" border size="small" :max-height="300" class="audit-table">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="单位名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" @change="persist" />
            <span v-else>{{ row.unit || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他应收款的性质" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.nature" size="small" @change="persist" />
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="persist" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="履行的核销程序" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.procedure" size="small" @change="persist" />
            <span v-else>{{ row.procedure || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否关联方往来" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relatedParty" size="small" @change="persist">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.relatedParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.analysis" size="small" @change="persist" />
            <span v-else>{{ row.analysis || '-' }}</span>
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
            <el-button size="small" type="danger" link @click="removeRow('writeoff', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　核销金额：{{ fmtAmt(columnSum('writeoff', 'amount')) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="核销依据是否符合规定、会计处理是否正确；转回/收回合理性；已核销重新收回的处理" @change="persist" />
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
        <li>转回检查：关注原计提依据、收回方式与转回合理性</li>
        <li>核销检查：核销依据是否符合规定、核销程序是否履行、会计处理是否正确</li>
        <li>关联方往来的核销需重点关注合理性与合规性</li>
        <li>已确认并核销的坏账重新收回的，检查其会计处理是否正确</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabWriteoffCheck.vue — K1-9 坏账准备转回（收回）、核销检查表 */
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
const ITEM_ID = 'K1-9-writeoff'
const { tables, auditNote, conclusion, conclusionOption, load, addRow, removeRow, columnSum, serialize } =
  useK1AuditRows({ allResponses: allResponsesRef as any, itemId: ITEM_ID, tableKeys: ['reversal', 'writeoff'] })

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
function handleReview() { openReviewDialog('K1-9-writeoff') }
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
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
