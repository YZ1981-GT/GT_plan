<script setup lang="ts">
/**
 * J3PlanDialog — 股份支付方案「新增/编辑」引导式弹窗
 *
 * 把 J3-1 明细宽表（14 列）的录入拆成分组卡片，每组内嵌对应的方法论要点（CAS 11），
 * 尽量用下拉/单选/allow-create「点点点」方式录入，并在填写时实时给出分析提示，
 * 辅助审计师理解要点、边录入边分析，最终完成底稿。
 */
import { reactive, computed, watch } from 'vue'

export interface SbpPlan {
  id: number
  name: string; type: string; grantDate: string; approvalDept: string; exerciseDate: string
  instrumentQty: number; vestingPeriod: string; fvMethod: string; agreementChange: string
  bsUpdate: string; remainingPeriod: string; agreementIndex: string; calcTableIndex: string; conclusion: string
}

const props = defineProps<{
  modelValue: boolean
  plan: SbpPlan | null
  isReadonly?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  save: [plan: SbpPlan]
}>()

const TYPE_OPTIONS = [
  { value: '以权益工具结算', desc: '按授予日权益工具公允价值计量，后续不重新计量，贷记资本公积（M4）' },
  { value: '以现金结算', desc: '按每个资产负债表日重新计量的公允价值计量，贷记应付职工薪酬（J1）' },
  { value: '以权益与现金结合结算', desc: '含权益与现金两部分，分别按对应方法核算' },
]
const FV_METHOD_OPTIONS = ['Black-Scholes 期权定价模型', '二叉树期权定价模型', 'Monte Carlo 模拟', '活跃市场价格', '最近融资/交易价格', '独立第三方评估', '其他']
const AGREEMENT_CHANGE_OPTIONS = ['无变更', '协议已变更（修改条款）', '协议已取消', '部分取消/失效']
const BS_UPDATE_OPTIONS = ['按最佳估计更新可行权数量', '权益结算：授予日计量后不重新计量', '现金结算：按资产负债表日公允价值重新计量', '无变化']
const CONCLUSION_OPTIONS = [
  '条款与工具一致，会计处理恰当，未见异常',
  '分类恰当（权益/现金结算），费用分摊正确，未见异常',
  '公允价值假设合理，未见异常',
  '存在差异，已作调整',
  '需进一步关注',
]

function emptyPlan(): SbpPlan {
  return { id: 0, name: '', type: '以权益工具结算', grantDate: '', approvalDept: '', exerciseDate: '', instrumentQty: 0, vestingPeriod: '', fvMethod: '', agreementChange: '', bsUpdate: '', remainingPeriod: '', agreementIndex: '', calcTableIndex: '', conclusion: '' }
}
const local = reactive<SbpPlan>(emptyPlan())
const isEdit = computed(() => !!props.plan && props.plan.id > 0)

watch(() => props.modelValue, (v) => {
  if (v) Object.assign(local, props.plan ? { ...props.plan } : emptyPlan())
})

const typeDesc = computed(() => TYPE_OPTIONS.find(o => o.value === local.type)?.desc || '')

// ── 实时分析提示 ──────────────────────────────────────────────────────────────
function parseDate(s: string): Date | null { if (!s) return null; const d = new Date(s.replace(/\./g, '-')); return isNaN(d.getTime()) ? null : d }
const grantExerciseMonths = computed(() => {
  const g = parseDate(local.grantDate), e = parseDate(local.exerciseDate)
  if (!g || !e) return null
  return (e.getFullYear() - g.getFullYear()) * 12 + (e.getMonth() - g.getMonth())
})

interface Hint { type: 'success' | 'warning' | 'info'; text: string }
const analysis = computed<Hint[]>(() => {
  const out: Hint[] = []
  if (local.type.includes('现金')) out.push({ type: 'warning', text: '现金结算：须在每个资产负债表日按公允价值重新计量（要点2），请如实填写"资产负债表日估计更新情况"。' })
  if (local.type.includes('权益')) out.push({ type: 'info', text: '权益结算：按授予日公允价值一次性确定，等待期内分摊、后续不重新计量（贷记资本公积 M4）。' })
  if (grantExerciseMonths.value !== null) {
    const m = grantExerciseMonths.value
    if (m < 0) out.push({ type: 'warning', text: '行权日早于授予日，请核对日期是否录入有误。' })
    else if (m > 60) out.push({ type: 'warning', text: `授予日至行权日间隔约 ${m} 个月（较长），关注是否存在重大时间间隔或日期倒签风险（要点1、8）。` })
    else out.push({ type: 'success', text: `授予日至行权日间隔约 ${m} 个月。` })
  }
  if (!local.fvMethod) out.push({ type: 'warning', text: '未填写公允价值确定方法：请评价估值假设合理性，必要时利用估值专家（要点6、7，S12/S12A）。' })
  if (!local.calcTableIndex) out.push({ type: 'info', text: '建议填写"股份支付计算表索引号"，以支持等待期费用分摊金额的追溯（分配至管理费用/销售费用 K8/K9）。' })
  if (!local.agreementIndex) out.push({ type: 'info', text: '建议填写"协议索引号"，关联董事会决议/授权文件等支持性文件（要点1、4、5）。' })
  return out
})

const canSave = computed(() => !!local.name.trim())

function onSave() {
  if (props.isReadonly || !canSave.value) return
  emit('save', { ...local })
  emit('update:modelValue', false)
}
function onClose() { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog :model-value="modelValue" :title="isEdit ? '编辑股份支付方案' : '新增股份支付方案'" width="860px"
    top="6vh" append-to-body @update:model-value="onClose">
    <div class="plan-dialog-body">
      <!-- 方案基本信息 + 分类判断 -->
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>① 方案基本信息与分类</span><span class="grp-tip">要点2：依条款判断分类（权益/现金/结合），并确认会计处理是否恰当反映分类</span></div></template>
        <el-form label-width="132px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="股份支付项目名称" required>
                <el-input v-model="local.name" :disabled="isReadonly" placeholder="如：2024年限制性股票激励计划" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="批准部门">
                <el-select v-model="local.approvalDept" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择或输入" style="width:100%">
                  <el-option label="董事会" value="董事会" />
                  <el-option label="股东大会" value="股东大会" />
                  <el-option label="董事会 + 股东大会" value="董事会 + 股东大会" />
                  <el-option label="薪酬与考核委员会" value="薪酬与考核委员会" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="类型">
            <el-radio-group v-model="local.type" :disabled="isReadonly">
              <el-radio v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value" border>{{ o.value }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <div v-if="typeDesc" class="type-desc">💡 {{ typeDesc }}</div>
        </el-form>
      </el-card>

      <!-- 关键日期与条款 -->
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>② 关键日期与条款</span><span class="grp-tip">要点1：核对主要条款（授予日、价格、股数、行权日等），关注授权日与行权日的时间间隔</span></div></template>
        <el-form label-width="132px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="授予日"><el-date-picker v-model="local.grantDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%" placeholder="选择授予日" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="行权日"><el-date-picker v-model="local.exerciseDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%" placeholder="选择行权日" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="权益工具数量"><el-input-number v-model="local.instrumentQty" :controls="false" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="等待期"><el-input v-model="local.vestingPeriod" :disabled="isReadonly" placeholder="如 3 年" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="剩余等待期限"><el-input v-model="local.remainingPeriod" :disabled="isReadonly" placeholder="如 2 年" /></el-form-item></el-col>
          </el-row>
        </el-form>
      </el-card>

      <!-- 公允价值确定 -->
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>③ 公允价值的确定及数据来源</span><span class="grp-tip">要点6、7：了解估值假设并评价其合理性；必要时利用估值专家（S12/S12A）</span></div></template>
        <el-form label-width="132px" label-position="right" size="small">
          <el-form-item label="确定方法和数据来源">
            <el-select v-model="local.fvMethod" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择常用方法或输入" style="width:100%">
              <el-option v-for="m in FV_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 协议变更与资产负债表日更新 -->
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>④ 协议变更与资产负债表日更新</span><span class="grp-tip">要点4：分析新增/修改的股份支付，确认修改是否已适当确认</span></div></template>
        <el-form label-width="132px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="协议变更/取消情况">
                <el-select v-model="local.agreementChange" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择或输入" style="width:100%">
                  <el-option v-for="o in AGREEMENT_CHANGE_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="资产负债表日估计更新">
                <el-select v-model="local.bsUpdate" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择或输入" style="width:100%">
                  <el-option v-for="o in BS_UPDATE_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-card>

      <!-- 索引与结论 -->
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>⑤ 支持性文件索引与结论</span><span class="grp-tip">要点5：取得合同及支持性文件，确认条款与工具一致</span></div></template>
        <el-form label-width="132px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="12"><el-form-item label="协议索引号"><el-input v-model="local.agreementIndex" :disabled="isReadonly" placeholder="如 S12 / 附件索引" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="计算表索引号"><el-input v-model="local.calcTableIndex" :disabled="isReadonly" placeholder="如 J3-2" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="结论">
            <el-select v-model="local.conclusion" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择常用结论或输入" style="width:100%">
              <el-option v-for="c in CONCLUSION_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 实时分析提示 -->
      <div class="analysis-panel">
        <div class="analysis-hd">🔎 边录入边分析（基于 CAS 11 关注要点）</div>
        <el-alert v-for="(h, i) in analysis" :key="i" :type="h.type" :title="h.text" :closable="false" show-icon class="analysis-item" />
        <div v-if="analysis.length === 0" class="analysis-empty">填写方案信息后，将在此显示分类、日期间隔、公允价值假设等分析提示。</div>
      </div>
    </div>

    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" :disabled="isReadonly || !canSave" @click="onSave">{{ isEdit ? '保存修改' : '添加方案' }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.plan-dialog-body { max-height: 68vh; overflow-y: auto; padding-right: 4px; }
.grp-card { margin-bottom: 12px; }
.grp-card :deep(.el-card__header) { padding: 8px 14px; background: #fafafa; }
.grp-card :deep(.el-card__body) { padding: 12px 14px; }
.grp-hd { display: flex; flex-direction: column; gap: 2px; }
.grp-hd > span:first-child { font-size: 13px; font-weight: 600; color: #303133; }
.grp-tip { font-size: 12px; color: #b88230; }
.type-desc { font-size: 12px; color: #409eff; background: #ecf5ff; border-radius: 4px; padding: 6px 10px; margin-top: 4px; }
.analysis-panel { border: 1px dashed #e6a23c; border-radius: 6px; padding: 10px 12px; background: #fffdf8; }
.analysis-hd { font-size: 13px; font-weight: 600; color: #b88230; margin-bottom: 8px; }
.analysis-item { margin-bottom: 6px; }
.analysis-item:last-child { margin-bottom: 0; }
.analysis-empty { font-size: 12px; color: #909399; }
</style>
