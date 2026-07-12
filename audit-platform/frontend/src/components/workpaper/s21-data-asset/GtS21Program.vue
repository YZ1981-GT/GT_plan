<template>
  <div class="s21-program">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        执行数据资产审计程序，确认开发支出资本化的合规性、成本归集与分摊的合理性、摊销政策的适当性，以及相关会计政策披露的完整准确（CAS 6）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审计程序 S21 — 数据资产</span>
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
      <p>按照审计程序逐项执行，确认数据资产开发支出资本化的合规性与计算正确性。</p>
      <p>重点关注资本化5项条件的判断依据、成本归集的合理性以及摊销政策的适当性。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21Program.vue — 审计程序 S21（数据资产）
 *
 * 功能：
 * - 展示 S21 审计程序清单（checklist/procedure 格式）
 * - 支持执行人、结论填写
 * - GtIndexChip 跨底稿引用跳转
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 */
import { ref, defineAsyncComponent } from 'vue'
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
  { procedure: '获取数据资产基本情况表，了解企业数据资产的类型、取得方式、摊销方法等基本信息。', executor: '', conclusion: '', ref: 'S21-1' },
  { procedure: '获取开发支出资本化分析表，检查资本化时点判断是否满足5项条件（技术可行性/使用出售意图/市场需求/技术财力支持/单独核算可靠计量）。', executor: '', conclusion: '', ref: 'S21-2' },
  { procedure: '复核开发阶段各月各类目支出的归集金额，检查合计与占比计算是否正确。', executor: '', conclusion: '', ref: 'S21-2' },
  { procedure: '检查成本归集与分摊方法的适当性，评估分摊基础和分摊结果的合理性。', executor: '', conclusion: '', ref: 'S21-3' },
  { procedure: '检查摊销政策是否适当，包括摊销年限、残值率、摊销方法的选择依据。', executor: '', conclusion: '', ref: 'S21-4' },
  { procedure: '确认数据资产相关的会计政策披露是否完整、准确。', executor: '', conclusion: '', ref: '' },
])

// ─── 持久化接线（load + save） ────────────────────────────────────────────────

const ROWS_ID = 'S21-program-rows'
const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([{ itemId: ROWS_ID, ref: programSteps }])

function saveRows(): void {
  save(ROWS_ID, programSteps.value)
}
</script>

<style scoped>
.s21-program {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
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
