<script setup lang="ts">
/**
 * D4TabThirdParty — D4-24 第三方回款
 *
 * 代付协议 + 资金流向 + 资金回流模式识别
 * Requirements: 14.4
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Ipo } from '../../composables/useD4Ipo'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { thirdPartyRows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="d4-tab-third-party">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">第三方代付/回款记录（关注资金回流风险）</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-24')">
        + 添加记录
      </el-button>
    </div>

    <el-table :data="thirdPartyRows" border stripe max-height="450">
      <el-table-column prop="payer" label="付款方" min-width="120" />
      <el-table-column prop="payee" label="收款方" min-width="120" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="110" />
      <el-table-column prop="relation" label="关系说明" min-width="140" />
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-24', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-24-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入第三方回款检查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-third-party { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
