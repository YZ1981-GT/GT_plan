<template>
  <div class="f5-adjudication">
    <div class="f5-adj-toolbar">
      <span class="f5-adj-title">F5-1 营业成本审定表（损益类·本期/上期对比）</span>
      <div class="f5-adj-actions">
        <el-button size="small" @click="openReview">💬 复核</el-button>
      </div>
    </div>

    <el-table :data="tableData" size="small" border stripe :row-class-name="rowClass" max-height="560">
      <el-table-column label="项目" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'group'">
            <span class="f5-adj-group">{{ row.label }}</span>
            <el-button v-if="!isReadonly && row.group" size="small" type="primary" link
              @click="promptAddRow(row.group)">+ 品种</el-button>
          </template>
          <template v-else-if="row.__type === 'data'">
            <el-input v-if="!row.isFixed && !isReadonly" v-model="row.label" size="small"
              @change="(v: string) => adj.updateCell(row.group, row.rowKey, 'label', v)" />
            <span v-else>{{ row.label }}</span>
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
          </template>
          <span v-else class="f5-adj-subtotal">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 本期 -->
      <el-table-column label="本期" align="center">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentUnadjusted" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentUnadjusted', v)" />
            <span v-else-if="row.currentUnadjusted != null">{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整(AJE)" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentAje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentAje', v)" />
            <span v-else-if="row.currentAje != null">{{ fmt(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类(RJE)" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.currentRje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'currentRje', v)" />
            <span v-else-if="row.currentRje != null">{{ fmt(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.currentAdjusted != null" class="f5-formula" title="审定 = 未审 + AJE + RJE">
              {{ fmt(row.currentAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 上期 -->
      <el-table-column label="上期" align="center">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorUnadjusted" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorUnadjusted', v)" />
            <span v-else-if="row.priorUnadjusted != null">{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="90" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorAje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorAje', v)" />
            <span v-else-if="row.priorAje != null">{{ fmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="90" align="right">
          <template #default="{ row }">
            <el-input v-if="row.__type === 'data' && !isReadonly" v-model.number="row.priorRje" size="small"
              @change="(v: any) => adj.updateCell(row.group, row.rowKey, 'priorRje', v)" />
            <span v-else-if="row.priorRje != null">{{ fmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.priorAdjusted != null" class="f5-formula" title="审定 = 未审 + AJE + RJE">
              {{ fmt(row.priorAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }">
          <span v-if="row.changeAmount != null" class="f5-formula" title="变动额 = 本期审定 - 上期审定">
            {{ fmt(row.changeAmount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm v-if="row.__type === 'data' && !row.isFixed" title="确认删除？"
            @confirm="adj.removeRow(row.group, row.rowKey)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 试算表 + 差异 -->
    <div class="f5-adj-tb">
      <span>试算表数（科目6401发生额）：</span>
      <el-input v-if="!isReadonly" v-model.number="tbInput" size="small" style="width: 160px"
        @change="onTbChange" />
      <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span class="f5-adj-variance" :class="{ 'is-error': Math.abs(adj.variance.value) > 0.01 }">
        差异（审定-试算）：{{ fmt(adj.variance.value) }}
      </span>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">
        发布审定数
      </el-button>
    </div>

    <el-card class="f5-adj-note" shadow="never">
      <template #header>
        <div class="f5-card-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="adj.auditNote.value" type="textarea" autosize :disabled="isReadonly"
        placeholder="营业成本审定说明..." />
    </el-card>
    <el-card class="f5-adj-note" shadow="never">
      <template #header>
        <div class="f5-card-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="adj.auditConclusion.value" type="textarea" autosize :disabled="isReadonly"
        placeholder="审计结论..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabAdjudication.vue — F5-1 审定表（损益类 6401 营业成本）
 * 主营品种行+小计 + 其他品种行+小计 + 总计+TB数+差异
 * 动态品种行增删(ElMessageBox.prompt) + GtIndexChip + EventBus发布
 */
import { ref, computed, inject, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useF5Adjudication } from '../composables/useF5Adjudication'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const adj = useF5Adjudication({
  wpId: props.wpId,
  projectId: props.projectId,
  allResponses: props.allResponses,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const tbInput = ref(adj.trialBalanceAmount.value)
watch(adj.trialBalanceAmount, (v) => { tbInput.value = v })

function onTbChange() {
  adj.updateTrialBalance(tbInput.value)
}

/** 组装表格行（分组标题 + 数据行 + 小计 + 总计） */
const tableData = computed(() => {
  const rows: any[] = []
  rows.push({ __type: 'group', label: '主营业务成本', group: 'main' })
  for (const r of adj.mainBusinessRows.value) rows.push({ __type: 'data', group: 'main', ...r })
  rows.push({ __type: 'subtotal', ...adj.mainSubtotal.value })
  rows.push({ __type: 'group', label: '其他业务成本', group: 'other' })
  for (const r of adj.otherBusinessRows.value) rows.push({ __type: 'data', group: 'other', ...r })
  rows.push({ __type: 'subtotal', ...adj.otherSubtotal.value })
  rows.push({ __type: 'subtotal', ...adj.grandTotal.value })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'group') return 'f5-row-group'
  if (row.__type === 'subtotal') return 'f5-row-subtotal'
  return ''
}

async function promptAddRow(group: 'main' | 'other') {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '品种名称不能为空',
    })
    if (value) adj.addRow(group, value.trim())
  } catch { /* 用户取消 */ }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function openReview() {
  openReviewDialog('F5-1-conclusion')
}
</script>

<style scoped>
.f5-adjudication { padding: 12px; font-size: 13px; }
.f5-adj-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.f5-adj-title { font-weight: 600; }
.f5-adj-group { font-weight: 600; color: #409eff; margin-right: 8px; }
.f5-adj-subtotal { font-weight: 700; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-adj-tb { display: flex; align-items: center; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.f5-adj-variance { font-weight: 600; }
.f5-adj-variance.is-error { color: #f56c6c; }
.f5-adj-note { margin-top: 12px; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.f5-row-group) { background: #ecf5ff; }
:deep(.f5-row-subtotal) { background: #f5f7fa; font-weight: 700; }
</style>
