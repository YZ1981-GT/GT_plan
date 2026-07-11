<template>
  <div class="j1-tab-allocation">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证应付职工薪酬按受益对象在管理费用、销售费用、生产成本、制造费用、研发费用、在建工程等科目间分配的合理性与完整性，确保分配合计与贷方增加额闭合。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">分配情况检查表（J1-7）</span>
          <el-tag v-if="hasImbalance" type="danger" size="small">分配不平衡</el-tag>
          <el-tag v-else type="success" size="small">分配闭合✓</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        </div>
      </template>

      <el-table :data="rows" border size="small" style="font-size: 13px" max-height="500">
        <el-table-column prop="category" label="薪酬项目" min-width="120" fixed />
        <el-table-column prop="adminExpense" label="管理费用(→K9)" width="110" align="right" />
        <el-table-column prop="sellingExpense" label="销售费用(→K8)" width="110" align="right" />
        <el-table-column prop="productionCost" label="生产成本" width="100" align="right" />
        <el-table-column prop="manufacturing" label="制造费用" width="100" align="right" />
        <el-table-column prop="researchExpense" label="研发费用" width="100" align="right" />
        <el-table-column prop="construction" label="在建工程" width="100" align="right" />
        <el-table-column prop="otherExpense" label="其他" width="90" align="right" />
        <el-table-column label="行合计" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="行合计=Σ各科目">{{ row.rowTotal?.toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditIncrease" label="贷方增加" width="110" align="right" />
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': !row.isBalanced }">{{ row.difference?.toFixed(2) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- K8/K9联动摘要 -->
      <div class="linkage-summary">
        <el-tag effect="plain">→ K9管理费用薪酬: {{ totalAdmin?.toLocaleString() }}</el-tag>
        <el-tag effect="plain" type="warning">→ K8销售费用薪酬: {{ totalSelling?.toLocaleString() }}</el-tag>
        <el-tag effect="plain" type="info">研发费用薪酬: {{ totalResearch?.toLocaleString() }}</el-tag>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，应付职工薪酬应按受益对象分配计入相关资产成本或当期损益。</p>
        <p>2. 灰色底纹"行合计"列为自动计算列（Σ各科目分配额），不可手动编辑。</p>
        <p>3. 各行"行合计"应等于对应"贷方增加"额，差额非零标红提示分配不平衡。</p>
        <p>4. 管理费用薪酬联动 K9、销售费用薪酬联动 K8，须与费用类底稿勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1AllocationCheck } from '@/composables/workpaper/j1/useJ1AllocationCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, totalAdmin, totalSelling, totalResearch, hasImbalance, initFromHtmlData } = useJ1AllocationCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-allocation { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.text-danger { color: #f56c6c; font-weight: 600; }
.linkage-summary { margin-top: 12px; display: flex; gap: 12px; flex-wrap: wrap; }
</style>
