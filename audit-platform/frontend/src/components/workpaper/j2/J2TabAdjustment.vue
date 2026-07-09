<template>
  <div class="j2-tab-adjustment">
    <h3 class="section-title">长期应付职工薪酬调整分录汇总表</h3>

    <el-table :data="entries" border stripe style="width: 100%; font-size: 13px">
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column prop="description" label="调整事项说明" min-width="200">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.description" size="small" />
          <span v-else>{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="140">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.category" size="small" placeholder="选择">
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="reportItem" label="报表项目" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.reportItem" size="small" />
          <span v-else>{{ row.reportItem }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountName" size="small" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="indexRef" label="索引" width="80" align="center" />
      <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeEntry($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <div class="balance-check" :class="{ balanced: isBalanced, unbalanced: !isBalanced }">
      <span>借方合计：{{ fmt(totalDebit) }}</span>
      <span>贷方合计：{{ fmt(totalCredit) }}</span>
      <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
        {{ isBalanced ? '借贷平衡 ✓' : '借贷不平衡 ✗' }}
      </el-tag>
    </div>

    <el-button v-if="!isReadonly" type="primary" plain size="small" @click="addEntry" style="margin-top: 12px">
      + 新增调整分录
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface AdjEntry {
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
}

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const entries = ref<AdjEntry[]>([])

const totalDebit = computed(() => entries.value.reduce((s, e) => s + (e.debitAmount || 0), 0))
const totalCredit = computed(() => entries.value.reduce((s, e) => s + (e.creditAmount || 0), 0))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)

function addEntry() {
  entries.value.push({
    description: '',
    category: '账项调整',
    reportItem: '长期应付职工薪酬',
    accountName: '',
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: '',
  })
}

function removeEntry(idx: number) {
  entries.value.splice(idx, 1)
}

function fmt(val: number): string {
  if (!val) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => {
  if (props.htmlData?.adjustments && Array.isArray(props.htmlData.adjustments)) {
    entries.value = props.htmlData.adjustments as AdjEntry[]
  }
})
</script>

<style scoped>
.j2-tab-adjustment { padding: 16px; }
.section-title { font-size: 15px; font-weight: 600; text-align: center; margin-bottom: 12px; }
.balance-check { display: flex; gap: 16px; align-items: center; margin-top: 12px; font-size: 13px; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; }
</style>
