<template>
  <div class="s21-cost-allocation">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        检查数据资产开发支出的成本归集范围是否合理（仅限开发阶段直接相关支出）、分摊方法是否适当、分摊结果是否与实际受益程度匹配，防止研究阶段支出或期间费用被误计入资本化成本。
      </div>
    </el-alert>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>成本归集检查应关注：① 归集范围是否合理（仅开发阶段直接相关支出）；② 分摊方法是否适当（工时/直接成本比例等）；③ 分摊结果是否与实际受益程度匹配。</p>
    </div>

    <!-- ─── 成本归集检查 ─── -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>成本归集与分摊检查表 S21-3</span>
        </div>
      </template>

      <el-table
        :data="allocationRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="costItem" label="成本项目" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.costItem"
              size="small"
              placeholder="成本项目名称"
            />
            <span v-else>{{ row.costItem || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额(元)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.amount"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
            />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocationMethod" label="分摊方法" width="150" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.allocationMethod"
              size="small"
              placeholder="选择分摊方法"
            >
              <el-option label="直接归集" value="直接归集" />
              <el-option label="工时比例" value="工时比例" />
              <el-option label="直接成本比例" value="直接成本比例" />
              <el-option label="人工成本比例" value="人工成本比例" />
              <el-option label="工作量比例" value="工作量比例" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.allocationMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocationBasis" label="分摊依据/基础" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.allocationBasis"
              size="small"
              placeholder="说明分摊依据"
            />
            <span v-else>{{ row.allocationBasis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="appropriateness" label="适当性评价" width="140" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.appropriateness"
              size="small"
              placeholder="评价"
            >
              <el-option label="适当" value="适当" />
              <el-option label="基本适当" value="基本适当" />
              <el-option label="不适当" value="不适当" />
            </el-select>
            <el-tag
              v-else
              :type="row.appropriateness === '适当' ? 'success' : row.appropriateness === '不适当' ? 'danger' : 'warning'"
              size="small"
            >
              {{ row.appropriateness || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注说明"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 动态行操作 -->
      <div v-if="!isReadonly" class="row-actions">
        <el-button size="small" type="primary" plain @click="addRow">
          + 新增成本项目
        </el-button>
      </div>
    </el-card>

    <!-- ─── 审计结论 ─── -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写成本归集与分摊检查的审计结论（如：经检查，管理层采用的成本归集与分摊方法适当，分摊结果合理）"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>① 逐项列示归集的成本项目及金额。</p>
      <p>② 对非直接归集的项目，记录其分摊方法和分摊依据。</p>
      <p>③ 评价分摊方法的适当性：是否与实际受益程度相匹配、是否前后一致、是否经过审批。</p>
      <p>④ 关注是否存在研究阶段支出误入开发阶段、或管理费用/销售费用错归入开发支出的情况。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21CostAllocation.vue — 成本归集与分摊检查表 S21-3
 *
 * 功能（Req 5.5）：
 * - 成本归集检查：列示各成本项目及其归集金额
 * - 分摊方法评价：分摊方法 + 分摊依据 + 适当性评价
 * - 动态行增减
 * - 审计结论
 *
 * Requirements: 5.5
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 */
import { ref, watch, onMounted, nextTick } from 'vue'
import { ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import { useSExpertPersist, parseResponseValue } from '../composables/useSExpertPersist'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

interface AllocationRow {
  costItem: string
  amount: number
  allocationMethod: string
  allocationBasis: string
  appropriateness: string
  remark: string
}

const allocationRows = ref<AllocationRow[]>([
  { costItem: '采购成本', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '人工成本', amount: 0, allocationMethod: '工时比例', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '脱敏清洗标注整合分析支出', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '数据权属鉴证费', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '质量评估费', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '登记结算费', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
  { costItem: '安全管理费', amount: 0, allocationMethod: '直接归集', allocationBasis: '', appropriateness: '', remark: '' },
])

const auditConclusion = ref('')

// ─── 持久化接线（load seed + save；hydrating 防回写） ─────────────────────────

const ROWS_ID = 'S21-3-rows'
const CONCLUSION_ID = 'S21-3-conclusion'
const { save } = useSExpertPersist(() => props.allResponses)

let hydrating = false

onMounted(async () => {
  hydrating = true
  const rows = parseResponseValue(props.allResponses, ROWS_ID)
  if (Array.isArray(rows) && rows.length) allocationRows.value = rows
  const conc = parseResponseValue(props.allResponses, CONCLUSION_ID)
  if (typeof conc === 'string') auditConclusion.value = conc
  await nextTick()
  hydrating = false
})

watch(allocationRows, () => { if (!hydrating) save(ROWS_ID, allocationRows.value) }, { deep: true })
watch(auditConclusion, () => { if (!hydrating) save(CONCLUSION_ID, auditConclusion.value) })

async function addRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入成本项目名称', '新增成本项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '成本项目名称',
    })
    if (value) {
      allocationRows.value.push({
        costItem: value,
        amount: 0,
        allocationMethod: '',
        allocationBasis: '',
        appropriateness: '',
        remark: '',
      })
    }
  } catch {
    // 取消
  }
}

function removeRow(index: number) {
  allocationRows.value.splice(index, 1)
}
</script>

<style scoped>
.s21-cost-allocation {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

/* 方法论上下文 */
.methodology-context {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.audit-section {
  margin-bottom: 16px;
}
.row-actions {
  margin-top: 12px;
}
.audit-conclusion-card {
  margin-top: 16px;
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
