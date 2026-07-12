<template>
  <div class="g5-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G5-4 调整分录汇总</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G5-4" />
        <el-tag size="small" type="info">共 {{ adj.entries.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-4-adjustment" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      汇总长期应收款相关审计调整分录（AJE）与重分类分录（RJE），校验借贷平衡，回写 G5-1 审定表调整列。
    </el-alert>

    <!-- 借贷平衡提示 -->
    <div v-if="!adj.isBalanced.value" class="balance-alert">
      <el-alert type="error" :closable="false">
        借贷不平衡！差额：{{ fmt(adj.balanceDiff.value) }}
      </el-alert>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" plain @click="adj.addEntry()" :disabled="props.readonly">
        + 新增分录
      </el-button>
      <span class="totals">
        借方合计: {{ fmt(adj.debitTotal.value) }} | 贷方合计: {{ fmt(adj.creditTotal.value) }}
      </span>
    </div>

    <el-table :data="adj.entries.value" border stripe style="width: 100%; font-size: 13px" :height="420">
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="entryType" label="类型" width="70">
        <template #default="{ row }">
          <el-select v-model="row.entryType" size="small" :disabled="props.readonly">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目代码" width="80" />
      <el-table-column prop="accountName" label="科目名称" min-width="100" />
      <el-table-column prop="debitAmount" label="借方金额" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="props.readonly" />
        </template>
      </el-table-column>
      <el-table-column prop="preparedBy" label="编制人" width="80" />
      <el-table-column prop="remark" label="备注" min-width="80" />
      <el-table-column label="操作" width="60" v-if="!props.readonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="adj.removeEntry(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>每条分录须借贷平衡；表底借方合计应等于贷方合计，否则顶部红色告警</li>
        <li>AJE（审计调整）影响审定数；RJE（重分类）不改变损益仅调整列报</li>
        <li>摘要应清晰说明调整事由，科目代码/名称与会计科目表一致</li>
        <li>调整分录经复核后回写 G5-1 审定表对应项目的 AJE/RJE 列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { useG5Adjustment } from '../../composables/useG5Adjustment'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const adj = useG5Adjustment()

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.balance-alert { margin-bottom: 8px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.totals { font-size: 12px; color: #606266; margin-left: auto; }
</style>
