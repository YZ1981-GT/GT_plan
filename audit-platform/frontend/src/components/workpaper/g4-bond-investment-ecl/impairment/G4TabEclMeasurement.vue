<template>
  <div class="g4-tab-ecl-measurement">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认企业预期信用损失(ECL)计量方法、组合划分依据及信用损失率(PD/LGD/EAD)参数的选取与计算合理、可靠。"
      style="margin-bottom: 12px"
    />
    <!-- 方法论上下文（琥珀色左边线+浅黄背景）: ECL三种方法简介 -->
    <div class="methodology-context">
      <p><strong>预期信用损失(ECL)计量的三种方法：</strong></p>
      <ul>
        <li><strong>个别评估</strong>：对单笔金额重大的金融资产逐项评估预期信用损失，适用于具有独特信用风险特征的大额债权投资</li>
        <li><strong>组合评估</strong>：将具有类似信用风险特征的金融资产分组，以组合为基础评估预期信用损失（PD×LGD×EAD模型）</li>
        <li><strong>简化方法</strong>：对不含重大融资成分的应收款项和合同资产，始终按整个存续期ECL计提（本底稿一般不适用）</li>
      </ul>
    </div>

    <!-- ═══ Section(一) ECL计量方法评价 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(一) ECL计量方法评价</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('section1')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-ecl-method-eval')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="methodEvaluation" border size="small" class="ecl-table">
        <el-table-column label="检查项目" prop="checkItem" min-width="120" />
        <el-table-column label="检查内容" prop="checkContent" min-width="180">
          <template #default="{ row }">
            <span class="check-content-text">{{ row.checkContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业采用方法" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.companyMethod"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="企业ECL计量方法..."
              @update:model-value="(v: string) => updateMethodEval(row.id, 'companyMethod', v)"
            />
            <span v-else>{{ row.companyMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => updateMethodEval(row.id, 'auditEvaluation', v)"
            >
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="补充说明..."
              @update:model-value="(v: string) => updateMethodEval(row.id, 'note', v)"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(二) 组合划分依据 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(二) 组合划分依据</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAddGroup">+ 新增组合</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleAi('section2')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-group-basis')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="groupBasis.length === 0" description="暂无组合，点击"新增组合"添加" :image-size="60" />
      <el-table v-else :data="groupBasis" border size="small" class="ecl-table">
        <el-table-column label="组合名称" min-width="120">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.groupName }}</span>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="handleRemoveGroup(row.id, row.groupName)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="划分依据" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.basis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="划分依据..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'basis', v)"
            />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="信用风险特征" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.riskCharacteristic"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="风险特征描述..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'riskCharacteristic', v)"
            />
            <span v-else>{{ row.riskCharacteristic || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="样本量" width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.sampleSize"
              size="small"
              :min="0"
              :controls="false"
              style="width: 80px"
              @update:model-value="(v: number | undefined) => updateGroupBasis(row.id, 'sampleSize', v ?? 0)"
            />
            <span v-else>{{ row.sampleSize }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => updateGroupBasis(row.id, 'auditEvaluation', v)"
            >
              <el-option value="合理" label="合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="补充说明..."
              @update:model-value="(v: string) => updateGroupBasis(row.id, 'note', v)"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(三) 信用损失率确定 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) 信用损失率的确定</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAddParameter">+ 新增参数</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleAi('section3')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-parameter-eval')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="parameterEvaluation.length === 0" description="暂无参数，点击"新增参数"添加" :image-size="60" />
      <el-table v-else :data="parameterEvaluation" border size="small" class="ecl-table">
        <el-table-column label="参数名称" min-width="100">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.paramName }}</span>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="handleRemoveParameter(row.id, row.paramName)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.dataSource"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="数据来源..."
              @update:model-value="(v: string) => updateParameterEval(row.id, 'dataSource', v)"
            />
            <span v-else>{{ row.dataSource || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计算方法" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.calcMethod"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="计算方法..."
              @update:model-value="(v: string) => updateParameterEval(row.id, 'calcMethod', v)"
            />
            <span v-else>{{ row.calcMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计验证结果" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.verificationResult"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="验证结果..."
              @update:model-value="(v: string) => updateParameterEval(row.id, 'verificationResult', v)"
            />
            <span v-else>{{ row.verificationResult || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditEvaluation"
              size="small"
              style="width: 100%"
              @change="(v: string) => updateParameterEval(row.id, 'auditEvaluation', v)"
            >
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.auditEvaluation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="补充说明..."
              @update:model-value="(v: string) => updateParameterEval(row.id, 'note', v)"
            />
            <span v-else>{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(四) 审计结论 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(四) 审计结论</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('conclusion')">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G4-11-conclusion')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="综合评价企业ECL计量方法、组合划分依据、信用损失率确定方法的合理性..."
        @input="handleConclusionChange"
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="g4-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g4-guide-content">
        <p>1. ECL计量方法评价：检查企业是否根据CAS22合理选择个别评估或组合评估方法</p>
        <p>2. 组合划分依据：评价企业组合划分是否具有共同信用风险特征，样本量是否充分</p>
        <p>3. 信用损失率确定：验证PD(违约概率)、LGD(违约损失率)、EAD(违约风险敞口)参数来源是否可靠、计算方法是否合理</p>
        <p>4. PD来源：外部评级机构历史违约率、内部信用评级模型、中证协减值指引附表等</p>
        <p>5. LGD确定：考虑担保物价值、回收率、清偿时间等因素</p>
        <p>6. EAD确定：一般等于信用风险敞口余额(含表外承诺需考虑信用转换因子CCF)</p>
        <p>7. 需结合参考材料"中证协金融工具减值指引"和"剩余期限折算PD"进行验证</p>
        <p>8. 对于组合评估，关注企业是否定期回测模型准确性并更新参数</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabEclMeasurement.vue — G4-11 预期信用损失计量测试
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Task 8.1
 * Requirements: 4.1~4.9, 11.1, 11.5
 *
 * 四section布局：
 * (一) ECL计量方法评价 — 静态检查行，textarea + select
 * (二) 组合划分依据 — 动态行增删
 * (三) 信用损失率确定 — 动态行增删(PD/LGD/EAD)
 * (四) 审计结论 — textarea + AI按钮
 *
 * 顶部方法论上下文（琥珀色：ECL三种方法简介）
 * 底部编制提示details折叠
 * inject('openReviewDialog') for 复核按钮
 */
import { ref, inject, computed, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import type {
  MethodEvalRow,
  GroupBasisRow,
  ParameterEvalRow,
} from '../../composables/useG4EclFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Section(一) 预定义检查项目（静态行） ───
const DEFAULT_METHOD_EVAL_ROWS: MethodEvalRow[] = [
  {
    id: 'me-1',
    checkItem: 'ECL计量方法选择',
    checkContent: '企业是否根据金融资产特征选择了合适的ECL计量方法（个别评估/组合评估）',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-2',
    checkItem: '前瞻性信息运用',
    checkContent: '企业是否在ECL计量中合理考虑了前瞻性宏观经济信息（GDP增速、失业率等）',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-3',
    checkItem: '概率加权场景',
    checkContent: '企业是否设置了多情景概率加权（乐观/基准/悲观），各情景概率分配是否合理',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-4',
    checkItem: '模型验证',
    checkContent: '企业是否定期对ECL模型进行回测验证，验证结果是否在可接受范围内',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
  {
    id: 'me-5',
    checkItem: '数据质量',
    checkContent: '企业ECL计量所使用的基础数据（历史违约数据、回收率数据等）是否完整、准确',
    companyMethod: '',
    auditEvaluation: '合理',
    note: '',
  },
]

// ─── 响应式数据 ───
const methodEvaluation = ref<MethodEvalRow[]>([...DEFAULT_METHOD_EVAL_ROWS])
const groupBasis = ref<GroupBasisRow[]>([])
const parameterEvaluation = ref<ParameterEvalRow[]>([])
const conclusion = ref('')

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

function initFromData(): void {
  const content = formData.parseContent()
  const ecl = content.eclMeasurement
  if (!ecl) return

  if (ecl.methodEvaluation?.length) {
    methodEvaluation.value = ecl.methodEvaluation
  }
  if (ecl.groupBasis?.length) {
    groupBasis.value = ecl.groupBasis
  }
  if (ecl.parameterEvaluation?.length) {
    parameterEvaluation.value = ecl.parameterEvaluation
  }
  if (ecl.conclusion) {
    conclusion.value = ecl.conclusion
  }
}

// ─── 保存逻辑 ───
function saveAll(): void {
  formData.debouncedSave('G4-11-ecl-measurement', {
    conclusion: JSON.stringify({
      methodEvaluation: methodEvaluation.value,
      groupBasis: groupBasis.value,
      parameterEvaluation: parameterEvaluation.value,
      conclusion: conclusion.value,
    }),
  })
}

// ─── Section(一) 更新 ───
function updateMethodEval(rowId: string, field: keyof MethodEvalRow, value: any): void {
  const row = methodEvaluation.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  saveAll()
}

// ─── Section(二) 组合划分 CRUD ───
function updateGroupBasis(rowId: string, field: keyof GroupBasisRow, value: any): void {
  const row = groupBasis.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  saveAll()
}

async function handleAddGroup(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入组合名称',
      '新增组合',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '组合名称不能为空',
        inputPlaceholder: '例如：同一外部评级组合',
      },
    )
    if (value?.trim()) {
      const newRow: GroupBasisRow = {
        id: `gb-${Date.now()}`,
        groupName: value.trim(),
        basis: '',
        riskCharacteristic: '',
        sampleSize: 0,
        auditEvaluation: '合理',
        note: '',
      }
      groupBasis.value.push(newRow)
      saveAll()
      ElMessage.success(`已新增组合"${value.trim()}"`)
    }
  } catch {
    // 用户取消
  }
}

async function handleRemoveGroup(rowId: string, groupName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除组合"${groupName}"？`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
    groupBasis.value = groupBasis.value.filter((r) => r.id !== rowId)
    saveAll()
    ElMessage.success(`已删除"${groupName}"`)
  } catch {
    // 用户取消
  }
}

// ─── Section(三) 参数评价 CRUD ───
function updateParameterEval(rowId: string, field: keyof ParameterEvalRow, value: any): void {
  const row = parameterEvaluation.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  saveAll()
}

async function handleAddParameter(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入参数名称（如PD、LGD、EAD、CCF等）',
      '新增参数',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '参数名称不能为空',
        inputPlaceholder: '例如：PD(违约概率)',
      },
    )
    if (value?.trim()) {
      const newRow: ParameterEvalRow = {
        id: `pe-${Date.now()}`,
        paramName: value.trim(),
        dataSource: '',
        calcMethod: '',
        verificationResult: '',
        auditEvaluation: '合理',
        note: '',
      }
      parameterEvaluation.value.push(newRow)
      saveAll()
      ElMessage.success(`已新增参数"${value.trim()}"`)
    }
  } catch {
    // 用户取消
  }
}

async function handleRemoveParameter(rowId: string, paramName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除参数"${paramName}"？`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
    parameterEvaluation.value = parameterEvaluation.value.filter((r) => r.id !== rowId)
    saveAll()
    ElMessage.success(`已删除"${paramName}"`)
  } catch {
    // 用户取消
  }
}

// ─── Section(四) 审计结论更新 ───
function handleConclusionChange(): void {
  saveAll()
}

// ─── AI辅助 ───
function handleAi(section: string): void {
  ElMessage.info(`AI辅助(${section})功能将在AI模块完成后启用`)
}

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    methodEvaluation: methodEvaluation.value,
    groupBasis: groupBasis.value,
    parameterEvaluation: parameterEvaluation.value,
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-tab-ecl-measurement {
  padding: 12px;
  font-size: 13px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 4px;
}

.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}

.methodology-context li {
  margin-bottom: 2px;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.ecl-table {
  font-size: 13px;
}

.check-content-text {
  color: #606266;
  font-size: 12px;
}

/* ─── 名称单元格（含删除按钮） ─── */
.name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ─── 编制提示 ─── */
.g4-guide-details {
  margin-top: 16px;
}

.g4-guide-details summary {
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  font-weight: 600;
}

.g4-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g4-guide-content p {
  margin: 0;
}
</style>
