<template>
  <div class="s15-program">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        执行每股收益与净资产收益率的审计程序，确认计算表数据来源与审定财务报表一致，复核基本/稀释每股收益及全面摊薄/加权平均净资产收益率计算的正确性和完整性。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审计程序 S15</span>
        </div>
      </template>

      <el-table
        :data="programSteps"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="procedure" label="审计程序" min-width="300" />
        <el-table-column prop="executor" label="执行人" width="100" align="center">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.executor"
              size="small"
              placeholder="—"
              @change="saveRows"
            />
            <span v-else>{{ row.executor || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="执行结论" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.conclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写执行结论"
              @change="saveRows"
            />
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ref" :value="row.ref" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>按照审计程序逐项执行，确认每股收益与净资产收益率计算的正确性和完整性。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15Program.vue — 审计程序 S15
 *
 * 功能：
 * - 展示 S15 审计程序清单（checklist/procedure 格式）
 * - 支持执行人、结论填写
 * - GtIndexChip 跨底稿引用跳转
 */
import { ref } from 'vue'
import { defineAsyncComponent } from 'vue'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// 审计程序步骤（骨架数据，seed 时从 responses 覆盖）
const programSteps = ref([
  { procedure: '获取本期每股收益和净资产收益率计算表，检查计算表数据来源是否与审定的财务报表数据一致。', executor: '', conclusion: '', ref: 'S15-2' },
  { procedure: '复核基本每股收益的计算是否正确，特别关注加权平均股本数的计算。', executor: '', conclusion: '', ref: 'S15-2' },
  { procedure: '复核稀释每股收益的计算是否正确，检查稀释性潜在普通股的影响。', executor: '', conclusion: '', ref: 'S15-3' },
  { procedure: '复核净资产收益率（全面摊薄和加权平均）的计算是否正确。', executor: '', conclusion: '', ref: 'S15-4' },
])

// ─── 持久化接线（load + save） ────────────────────────────────────────────────

const ROWS_ID = 'S15-program-rows'
const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([{ itemId: ROWS_ID, ref: programSteps }])

function saveRows(): void {
  save(ROWS_ID, programSteps.value)
}
</script>

<style scoped>
.s15-program {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
