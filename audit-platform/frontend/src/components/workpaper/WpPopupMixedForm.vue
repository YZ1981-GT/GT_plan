<script setup lang="ts">
/**
 * WpPopupMixedForm — A1-18 采用新金融工具准则衔接影响数核对
 *
 * Tab 式多面板：
 * - 审计目标 + 审计过程（5步程序）
 * - 表一：新金融工具准则首次施行日权益调节表
 * - 表二：金融工具分类调节表
 * - 表三：权益工具投资明细表
 * - 审计说明 + 审计结论
 *
 * 程序步骤保存到 checklist_responses（A1-18-001~005）
 * 审计结论保存到 checklist_responses（A1-18-conclusion）
 * 调节表数据保存到 checklist_responses（A1-18-table-{n} 的 remark 字段存 JSON）
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───
const activeTab = ref('procedure')
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// 审计目标
const auditObjective = '确定首次执行新金融工具准则的期初未分配利润影响数的计算、其他综合收益的调整金额和比较数据的列报是否符合新旧衔接的要求。'

// 审计过程（5步）
const STEPS = [
  { id: 'A1-18-001', seq: 1, content: '了解被审计单位与新金融工具准则相关的会计政策和会计估计变更。' },
  { id: 'A1-18-002', seq: 2, content: '了解被审计单位财务报表体系的更新。' },
  { id: 'A1-18-003', seq: 3, content: '走访各相关部门和第三方服务机构，了解与新金融工具准则实施和衔接相关的内控流程及信息系统的建立和变更情况。' },
  { id: 'A1-18-004', seq: 4, content: '执行抽样检查，对首次执行日的金融资产和金融负债的分类变化做出实质性判断，复核历史存续金融工具在首次执行日的财务报表列报是否体现了新金融工具准则的分类要求，并且与历史数据和近期的财务预算、经营计划相吻合。' },
  { id: 'A1-18-005', seq: 5, content: '结合金融资产减值、公允价值计量等计价准确性认定相关的审计程序，对期初未分配利润和其他综合收益的影响数进行重新计算。' },
]

interface StepState { applicable: string | null; remark: string }
const stepStates = ref<Record<string, StepState>>({})

// 调节表数据（简化为 JSON 文本编辑）
const table1Data = ref('')  // 表一：权益调节表
const table2Data = ref('')  // 表二：分类调节表
const table3Data = ref('')  // 表三：投资明细表

// 审计说明 + 结论
const auditExplanation = ref('')
const auditConclusion = ref('')

// ─── Init ───
function initStates() {
  for (const step of STEPS) {
    if (!stepStates.value[step.id]) {
      stepStates.value[step.id] = { applicable: null, remark: '' }
    }
  }
}

// ─── Load ───
async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of list) {
      if (r.item_id?.startsWith('A1-18-00')) {
        stepStates.value[r.item_id] = { applicable: r.conclusion, remark: r.remark || '' }
      }
      if (r.item_id === 'A1-18-conclusion') {
        auditConclusion.value = r.remark || ''
      }
      if (r.item_id === 'A1-18-explanation') {
        auditExplanation.value = r.remark || ''
      }
      if (r.item_id === 'A1-18-table-1') table1Data.value = r.remark || ''
      if (r.item_id === 'A1-18-table-2') table2Data.value = r.remark || ''
      if (r.item_id === 'A1-18-table-3') table3Data.value = r.remark || ''
    }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

// ─── Save ───
function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return
  const items: Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = []

  // 程序步骤
  for (const step of STEPS) {
    items.push({
      item_id: step.id,
      conclusion: stepStates.value[step.id]?.applicable || null,
      remark: stepStates.value[step.id]?.remark || null,
      wp_ref: null,
    })
  }

  // 审计说明+结论
  items.push({ item_id: 'A1-18-explanation', conclusion: null, remark: auditExplanation.value || null, wp_ref: null })
  items.push({ item_id: 'A1-18-conclusion', conclusion: auditConclusion.value ? 'Y' : null, remark: auditConclusion.value || null, wp_ref: null })

  // 调节表（JSON 存 remark）
  items.push({ item_id: 'A1-18-table-1', conclusion: null, remark: table1Data.value || null, wp_ref: null })
  items.push({ item_id: 'A1-18-table-2', conclusion: null, remark: table2Data.value || null, wp_ref: null })
  items.push({ item_id: 'A1-18-table-3', conclusion: null, remark: table3Data.value || null, wp_ref: null })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId, items })
    emit('save')
    if (auditConclusion.value) emit('completed')
  } catch (err: any) {
    if (err?.message !== 'canceled' && err?.code !== 'ERR_CANCELED') ElMessage.error('保存失败')
  }
}

function updateStep(id: string, field: 'applicable' | 'remark', val: string) {
  stepStates.value[id][field] = val || null as any
  scheduleSave()
}

function onTextChange() { scheduleSave() }

onMounted(() => { initStates(); loadData() })
onBeforeUnmount(() => { if (saveTimer.value) { clearTimeout(saveTimer.value); doSave() } })
</script>

<template>
  <div class="wp-popup-mixed" v-loading="loading">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="审计目标与过程" name="procedure">
        <!-- 审计目标 -->
        <div class="mixed-section">
          <div class="mixed-section__title">一、审计目标</div>
          <p class="mixed-objective">{{ auditObjective }}</p>
        </div>
        <!-- 审计过程 -->
        <div class="mixed-section">
          <div class="mixed-section__title">二、审计过程</div>
          <div v-for="step in STEPS" :key="step.id" class="mixed-step" :class="{ 'is-done': stepStates[step.id]?.applicable }">
            <div class="step-header">
              <span class="step-seq">{{ step.seq }}</span>
              <span v-if="stepStates[step.id]?.applicable" class="step-check">✓</span>
            </div>
            <div class="step-content">{{ step.content }}</div>
            <div class="step-controls">
              <el-select :model-value="stepStates[step.id]?.applicable || ''" size="small" placeholder="—" style="width:80px" @change="(v: string) => updateStep(step.id, 'applicable', v)">
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-input :model-value="stepStates[step.id]?.remark || ''" size="small" placeholder="执行说明" style="flex:1;margin-left:8px" @input="(v: string) => updateStep(step.id, 'remark', v)" />
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="表一：权益调节" name="table1">
        <div class="mixed-section__title">表一：新金融工具准则首次施行日权益调节表</div>
        <p class="mixed-hint">金融工具调节事项 × 留存收益调整金额 / 其他综合收益调整金额</p>
        <el-input type="textarea" :rows="10" v-model="table1Data" placeholder="在此填写权益调节表数据（格式：每行一个项目，用逗号分隔列）" @input="onTextChange" />
      </el-tab-pane>

      <el-tab-pane label="表二：分类调节" name="table2">
        <div class="mixed-section__title">表二：首次施行日金融工具分类调节表</div>
        <p class="mixed-hint">原金融工具准则分类 → 新金融工具准则分类 × 按原/新准则列报的金额</p>
        <el-input type="textarea" :rows="10" v-model="table2Data" placeholder="在此填写分类调节表数据" @input="onTextChange" />
      </el-tab-pane>

      <el-tab-pane label="表三：投资明细" name="table3">
        <div class="mixed-section__title">表三：权益工具投资明细表</div>
        <p class="mixed-hint">首次施行日指定为以公允价值计量且其变动计入其他综合收益的金融资产</p>
        <el-input type="textarea" :rows="10" v-model="table3Data" placeholder="在此填写权益工具投资明细数据" @input="onTextChange" />
      </el-tab-pane>

      <el-tab-pane label="审计说明与结论" name="conclusion">
        <div class="mixed-section">
          <div class="mixed-section__title">一、审计说明</div>
          <el-input type="textarea" :rows="4" v-model="auditExplanation" placeholder="填写审计说明..." @input="onTextChange" />
        </div>
        <div class="mixed-section" style="margin-top:16px">
          <div class="mixed-section__title">二、审计结论</div>
          <el-input type="textarea" :rows="4" v-model="auditConclusion" placeholder="填写审计结论..." @input="onTextChange" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.wp-popup-mixed { padding: 0; }
.mixed-section { margin-bottom: 16px; }
.mixed-section__title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.mixed-objective { font-size: 13px; line-height: 1.6; color: #606266; padding: 8px 12px; background: #f4f0fa; border-radius: 4px; border-left: 3px solid #4b2d77; }
.mixed-hint { font-size: 12px; color: #909399; margin-bottom: 8px; }

.mixed-step { border: 1px solid #e4e7ed; border-radius: 6px; padding: 12px 14px; margin-bottom: 10px; transition: border-color 0.2s, background 0.2s; }
.mixed-step.is-done { border-color: #d8b8ee; background: #f4f0fa; }
.step-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.step-seq { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: #4b2d77; color: #fff; font-size: 11px; font-weight: 600; }
.step-check { color: #4b2d77; font-weight: 700; }
.step-content { font-size: 13px; line-height: 1.6; color: #303133; margin-bottom: 8px; }
.step-controls { display: flex; align-items: center; }
</style>
