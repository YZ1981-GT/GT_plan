<script setup lang="ts">
/**
 * D4TabCustomerChecklist — D4-28 客户核查清单
 *
 * 固定Y/N/NA清单项
 * Requirements: 14.8
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

const { customerChecklistRows } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d4-tab-customer-checklist">
    <div class="section-header mb-3">
      <h4>客户核查清单（固定事项）</h4>
      <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-28')">💬</el-button>
    </div>

    <el-table :data="customerChecklistRows" border stripe>
      <el-table-column type="index" label="#" width="50" />
      <el-table-column prop="item" label="检查事项" min-width="280" />
      <el-table-column label="结论" width="120" align="center">
        <template #default="{ row }">
          <el-radio-group v-model="row.answer" size="small" :disabled="isReadonly">
            <el-radio-button value="Y">Y</el-radio-button>
            <el-radio-button value="N">N</el-radio-button>
            <el-radio-button value="NA">NA</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.explanation" size="small" :disabled="isReadonly" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.d4-tab-customer-checklist { padding: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.section-header h4 { margin: 0; font-size: 15px; color: #303133; }
.mb-3 { margin-bottom: 12px; }
</style>
