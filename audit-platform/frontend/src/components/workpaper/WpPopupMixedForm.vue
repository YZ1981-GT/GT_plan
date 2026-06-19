<script setup lang="ts">
/**
 * WpPopupMixedForm — A1-18 采用新金融工具准则衔接影响数核对
 *
 * el-tabs with 5 panels:
 * - Tab 1 "审计目标与过程": 审计目标(text) + 5步审计过程(checklist)
 * - Tab 2 "表一-权益调节": 7项 × 2列(留存收益/其他综合收益) number inputs
 * - Tab 3 "表二-分类调节": rows with 原分类→新分类 + 金额
 * - Tab 4 "表三-投资明细": dynamic rows (add/delete)
 * - Tab 5 "结论": 审计说明(textarea) + 审计结论(textarea)
 *
 * Data persistence:
 * - 程序步骤 → checklist_responses (A1-18-001~005)
 * - 调节表 → emit save with structured data (parent saves to parsed_data)
 * - 结论 → checklist_responses (A1-18-conclusion)
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
  projectInfo?: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const activeTab = ref('procedure')
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// ===== Tab 1: 审计目标与过程 =====
const AUDIT_OBJECTIVE = '核对采用新金融工具准则（CAS 22/23/24/37）后，金融资产重分类及相关衔接调整对财务报表的影响数，确认调整分录的准确性和完整性。'

const PROCEDURE_STEPS = [
  { id: 'A1-18-001', seq: 1, content: '获取管理层编制的新金融工具准则衔接影响数调节表' },
  { id: 'A1-18-002', seq: 2, content: '核实金融资产原分类与新分类的对应关系是否符合准则要求' },
  { id: 'A1-18-003', seq: 3, content: '验证重分类调整金额的计算准确性' },
  { id: 'A1-18-004', seq: 4, content: '检查权益影响数（留存收益/其他综合收益）的调整逻辑' },
  { id: 'A1-18-005', seq: 5, content: '确认调节表与财务报表相关项目的一致性' },
]

interface ProcedureState {
  applicable: string | null
  remark: string
}
const procedureStates = ref<Record<string, ProcedureState>>({})

// ===== Tab 2: 表一-权益调节 =====
const EQUITY_ITEMS = [
  { key: 'reclassify_afs', label: '可供出售金融资产重分类至FVOCI' },
  { key: 'reclassify_htm', label: '持有至到期投资重分类至摊余成本' },
  { key: 'reclassify_loan', label: '贷款和应收款项重分类' },
  { key: 'ecl_provision', label: '预期信用损失计提' },
  { key: 'fair_value_change', label: '公允价值变动重新计量' },
  { key: 'tax_effect', label: '所得税影响' },
  { key: 'other_adjustment', label: '其他调整' },
]

interface EquityRow {
  retainedEarnings: number | null
  otherComprehensive: number | null
}
const equityData = ref<Record<string, EquityRow>>({})

// ===== Tab 3: 表二-分类调节 =====
interface ReclassRow {
  originalClass: string
  newClass: string
  amount: number | null
  note: string
}
const reclassRows = ref<ReclassRow[]>([
  { originalClass: '', newClass: '', amount: null, note: '' },
])

// ===== Tab 4: 表三-投资明细 =====
interface InvestmentRow {
  name: string
  category: string
  bookValue: number | null
  fairValue: number | null
  note: string
}
const investmentRows = ref<InvestmentRow[]>([
  { name: '', category: '', bookValue: null, fairValue: null, note: '' },
])

// ===== Tab 5: 结论 =====
const auditExplanation = ref('')
const auditConclusion = ref('')

// ===== Data loading =====
function initStates() {
  for (const step of PROCEDURE_STEPS) {
    if (!procedureStates.value[step.id]) {
      procedureStates.value[step.id] = { applicable: null, remark: '' }
    }
  }
  for (const item of EQUITY_ITEMS) {
    if (!equityData.value[item.key]) {
      equityData.value[item.key] = { retainedEarnings: null, otherComprehensive: null }
    }
  }
}

async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    // Load checklist responses (procedure steps + conclusion)
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const responses = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of responses) {
      if (r.item_id?.startsWith('A1-18-') && r.item_id !== 'A1-18-conclusion') {
        if (procedureStates.value[r.item_id]) {
          procedureStates.value[r.item_id] = {
            applicable: r.conclusion || null,
            remark: r.remark || '',
          }
        }
      }
      if (r.item_id === 'A1-18-conclusion') {
        auditConclusion.value = r.conclusion || ''
        auditExplanation.value = r.remark || ''
      }
    }

    // Load parsed_data for adjustment tables
    try {
      const wpRes = await api.get(`/api/workpapers/${props.wpId}`)
      const wp = wpRes?.data ?? wpRes
      const parsedData = wp?.parsed_data?.a1_18_data
      if (parsedData) {
        if (parsedData.equity) {
          equityData.value = { ...equityData.value, ...parsedData.equity }
        }
        if (parsedData.reclass?.length) {
          reclassRows.value = parsedData.reclass
        }
        if (parsedData.investments?.length) {
          investmentRows.value = parsedData.investments
        }
      }
    } catch { /* working paper detail may not have parsed_data */ }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

// ===== Save logic =====
function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return

  // Save checklist_responses (procedure steps + conclusion)
  const items: any[] = PROCEDURE_STEPS.map(step => ({
    item_id: step.id,
    conclusion: procedureStates.value[step.id]?.applicable || null,
    remark: procedureStates.value[step.id]?.remark || null,
    wp_ref: null,
  }))
  items.push({
    item_id: 'A1-18-conclusion',
    conclusion: auditConclusion.value || null,
    remark: auditExplanation.value || null,
    wp_ref: null,
  })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
  } catch (err: any) {
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.error('程序步骤保存失败')
    }
  }

  // Save parsed_data (adjustment tables)
  try {
    await api.put(`/api/workpapers/${props.wpId}/parsed-data`, {
      a1_18_data: {
        equity: equityData.value,
        reclass: reclassRows.value,
        investments: investmentRows.value,
      },
    })
    emit('save')
    if (auditConclusion.value) emit('completed')
  } catch (err: any) {
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.error('调节表数据保存失败')
    }
  }
}

// ===== Tab handlers =====
function updateProcedure(id: string, field: 'applicable' | 'remark', val: string) {
  if (field === 'applicable') {
    procedureStates.value[id].applicable = val || null
  } else {
    procedureStates.value[id].remark = val
  }
  scheduleSave()
}

function updateEquity(key: string, field: 'retainedEarnings' | 'otherComprehensive', val: number | null) {
  equityData.value[key][field] = val
  scheduleSave()
}

function addReclassRow() {
  reclassRows.value.push({ originalClass: '', newClass: '', amount: null, note: '' })
}

function removeReclassRow(index: number) {
  if (reclassRows.value.length > 1) {
    reclassRows.value.splice(index, 1)
    scheduleSave()
  }
}

function addInvestmentRow() {
  investmentRows.value.push({ name: '', category: '', bookValue: null, fairValue: null, note: '' })
}

function removeInvestmentRow(index: number) {
  if (investmentRows.value.length > 1) {
    investmentRows.value.splice(index, 1)
    scheduleSave()
  }
}

function onReclassChange() {
  scheduleSave()
}

function onInvestmentChange() {
  scheduleSave()
}

function onConclusionInput() {
  scheduleSave()
}

onMounted(() => {
  initStates()
  loadData()
})

onBeforeUnmount(() => {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    doSave()
  }
})
</script>

<template>
  <div class="wp-popup-mixed-form" v-loading="loading">
    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab 1: 审计目标与过程 -->
      <el-tab-pane label="审计目标与过程" name="procedure">
        <div class="objective-section">
          <div class="section-subtitle">审计目标</div>
          <div class="objective-text">{{ AUDIT_OBJECTIVE }}</div>
        </div>
        <div class="procedure-section">
          <div class="section-subtitle">审计过程（5步）</div>
          <div
            v-for="step in PROCEDURE_STEPS"
            :key="step.id"
            class="procedure-step"
            :class="{ 'is-done': procedureStates[step.id]?.applicable }"
          >
            <div class="step-header">
              <span class="step-seq">{{ step.seq }}</span>
              <span class="step-content">{{ step.content }}</span>
              <span class="step-status" v-if="procedureStates[step.id]?.applicable">✓</span>
            </div>
            <div class="step-controls">
              <div class="step-field">
                <span class="step-label">是否适用：</span>
                <el-select
                  :model-value="procedureStates[step.id]?.applicable || ''"
                  size="small"
                  placeholder="请选择"
                  style="width: 100px"
                  @change="(val: string) => updateProcedure(step.id, 'applicable', val)"
                >
                  <el-option label="是" value="Y" />
                  <el-option label="否" value="N" />
                </el-select>
              </div>
              <div class="step-field step-field--remark">
                <span class="step-label">执行说明：</span>
                <el-input
                  :model-value="procedureStates[step.id]?.remark || ''"
                  size="small"
                  placeholder="填写执行说明"
                  style="flex: 1"
                  @input="(val: string) => updateProcedure(step.id, 'remark', val)"
                />
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 表一-权益调节 -->
      <el-tab-pane label="表一-权益调节" name="equity">
        <el-table :data="EQUITY_ITEMS" border size="small" class="equity-table">
          <el-table-column label="调整项目" min-width="220">
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column label="留存收益" width="160" align="center">
            <template #default="{ row }">
              <el-input-number
                :model-value="equityData[row.key]?.retainedEarnings"
                size="small"
                :controls="false"
                placeholder="金额"
                style="width: 130px"
                @update:model-value="(val: number | null) => updateEquity(row.key, 'retainedEarnings', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="其他综合收益" width="160" align="center">
            <template #default="{ row }">
              <el-input-number
                :model-value="equityData[row.key]?.otherComprehensive"
                size="small"
                :controls="false"
                placeholder="金额"
                style="width: 130px"
                @update:model-value="(val: number | null) => updateEquity(row.key, 'otherComprehensive', val)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 3: 表二-分类调节 -->
      <el-tab-pane label="表二-分类调节" name="reclass">
        <el-table :data="reclassRows" border size="small" class="reclass-table">
          <el-table-column label="序号" width="50" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="原分类" min-width="150">
            <template #default="{ row }">
              <el-input
                v-model="row.originalClass"
                size="small"
                placeholder="原分类"
                @input="onReclassChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="新分类" min-width="150">
            <template #default="{ row }">
              <el-input
                v-model="row.newClass"
                size="small"
                placeholder="新分类"
                @input="onReclassChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="140" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="row.amount"
                size="small"
                :controls="false"
                placeholder="金额"
                style="width: 110px"
                @change="onReclassChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                size="small"
                placeholder="备注"
                @input="onReclassChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button
                type="danger"
                size="small"
                link
                :disabled="reclassRows.length <= 1"
                @click="removeReclassRow($index)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button type="primary" size="small" plain class="add-row-btn" @click="addReclassRow">
          + 添加行
        </el-button>
      </el-tab-pane>

      <!-- Tab 4: 表三-投资明细 -->
      <el-tab-pane label="表三-投资明细" name="investments">
        <el-table :data="investmentRows" border size="small" class="investment-table">
          <el-table-column label="序号" width="50" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="投资名称" min-width="140">
            <template #default="{ row }">
              <el-input
                v-model="row.name"
                size="small"
                placeholder="投资名称"
                @input="onInvestmentChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="类别" width="120">
            <template #default="{ row }">
              <el-input
                v-model="row.category"
                size="small"
                placeholder="类别"
                @input="onInvestmentChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="130" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="row.bookValue"
                size="small"
                :controls="false"
                placeholder="金额"
                style="width: 100px"
                @change="onInvestmentChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="130" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="row.fairValue"
                size="small"
                :controls="false"
                placeholder="金额"
                style="width: 100px"
                @change="onInvestmentChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="100">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                size="small"
                placeholder="备注"
                @input="onInvestmentChange"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button
                type="danger"
                size="small"
                link
                :disabled="investmentRows.length <= 1"
                @click="removeInvestmentRow($index)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button type="primary" size="small" plain class="add-row-btn" @click="addInvestmentRow">
          + 添加行
        </el-button>
      </el-tab-pane>

      <!-- Tab 5: 结论 -->
      <el-tab-pane label="结论" name="conclusion">
        <div class="conclusion-section">
          <div class="section-subtitle">审计说明</div>
          <el-input
            v-model="auditExplanation"
            type="textarea"
            :rows="4"
            placeholder="填写审计说明..."
            @input="onConclusionInput"
          />
        </div>
        <div class="conclusion-section" style="margin-top: 16px">
          <div class="section-subtitle">审计结论</div>
          <el-input
            v-model="auditConclusion"
            type="textarea"
            :rows="4"
            placeholder="填写审计结论..."
            @input="onConclusionInput"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.wp-popup-mixed-form {
  padding: 0;
}

.objective-section {
  margin-bottom: 16px;
}

.objective-text {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
  padding: 10px 12px;
  background-color: #f4f0fa;
  border-radius: 4px;
  border-left: 3px solid #4b2d77;
}

.procedure-section {
  margin-top: 4px;
}

.section-subtitle {
  font-size: 14px;
  font-weight: 600;
  color: #4b2d77;
  margin-bottom: 8px;
}

.procedure-step {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 10px;
  transition: border-color 0.2s, background-color 0.2s;
}

.procedure-step:last-child {
  margin-bottom: 0;
}

.procedure-step.is-done {
  border-color: #d8b8ee;
  background-color: #f4f0fa;
}

.step-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.step-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: #4b2d77;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-content {
  font-size: 13px;
  line-height: 1.5;
  color: #303133;
  flex: 1;
}

.step-status {
  color: #4b2d77;
  font-weight: 700;
  font-size: 13px;
}

.step-controls {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.step-field {
  display: flex;
  align-items: center;
  gap: 4px;
}

.step-field--remark {
  flex: 1;
  min-width: 200px;
}

.step-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

.equity-table,
.reclass-table,
.investment-table {
  width: 100%;
}

.add-row-btn {
  margin-top: 10px;
}

.conclusion-section {
  margin-bottom: 0;
}
</style>
