<!--
  K1TabPolicyCheck.vue — K1-6 信用减值损失会计政策检查

  忠实反映致同源模板 K1-6：审计目标（计价分摊）
  （一）减值组合划分（组合名称/划分依据，动态行，预置押金保证金/关联公司/代垫/员工备用金）
  （二）前瞻性信息的来源及其影响
  （三）同行业公司的会计政策对比
  + 上市公司会计政策披露示例参考（6家，内嵌可一键套用）
  + 政策检查结论
-->
<template>
  <div class="k1-tab-policy-check">
    <div class="methodology-context">
      <p>K1-6检查企业信用减值损失会计政策是否符合 CAS 22 要求，并与前期及同行业对比，关注是否利用会计政策/估计变更操纵利润，是否存在管理层偏向迹象。</p>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">审计目标（认定）</span></template>
      <p class="ao-text">其他应收款、坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</p>
    </el-alert>

    <div class="section-head">
      <h3 class="sheet-title">K1-6 信用减值损失会计政策检查</h3>
      <div class="head-actions">
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- (一) 减值组合划分 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（一）减值组合划分</span>
          <el-button v-if="!isReadonly" size="small" @click="addCombo(); persist()">＋ 新增组合</el-button>
        </div>
      </template>
      <p class="hint-text">当单项其他应收款无法以合理成本评估预期信用损失信息时，依据信用风险特征划分为若干组合。共同信用风险特征包括：金融工具类型、信用风险评级、担保物类型、初始确认日期、剩余合同期限、债务人所处行业/地理位置、担保品价值等。</p>
      <el-table :data="combos" border size="small" class="policy-table">
        <el-table-column label="组合" width="120">
          <template #default="{ row, $index }">其他应收款组合{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="划分依据（款项性质）" min-width="360">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" placeholder="如：押金和保证金" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeCombo(row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (二)(三) 文本section -->
    <div v-for="section in textSections" :key="section.id" class="policy-section">
      <div class="policy-section-head">
        <h4 class="policy-section-title">{{ section.label }}</h4>
        <el-button size="small" type="primary" link @click="handleAiGenerate(section.id)">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
      </div>
      <p class="policy-section-desc">{{ section.description }}</p>
      <el-input v-if="!isReadonly" type="textarea" :autosize="{ minRows: 3 }"
        :model-value="sectionContents[section.id] || ''" :placeholder="section.placeholder"
        @change="(v: string) => handleSectionChange(section.id, v)" />
      <div v-else class="readonly-content">{{ sectionContents[section.id] || '（未填写）' }}</div>
    </div>

    <!-- 上市公司会计政策披露示例参考 -->
    <el-card shadow="never" class="ref-card">
      <template #header><span class="card-title">📚 上市公司会计政策披露示例参考</span></template>
      <p class="hint-text">以下为部分上市公司其他应收款减值组合披露示例，可点击"套用"填入"同行业公司的会计政策"作为对比参考。</p>
      <el-collapse>
        <el-collapse-item v-for="ex in listedExamples" :key="ex.company" :name="ex.company">
          <template #title>
            <span class="ex-company">{{ ex.company }}</span>
            <el-button size="small" type="primary" link class="ex-apply" @click.stop="applyExample(ex)">套用 →</el-button>
          </template>
          <p class="ex-text">{{ ex.text }}</p>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">政策检查结论</span></template>
      <el-input v-if="!isReadonly" type="textarea" :autosize="{ minRows: 2 }"
        v-model="conclusion" placeholder="请填写会计政策检查综合结论" @change="handleConclusionChange" />
      <div v-else class="readonly-content">{{ conclusion || '（未填写）' }}</div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 22）</summary>
      <ul>
        <li>减值组合划分依据：金融工具类型/信用风险评级/担保物类型/账龄/行业等共同信用风险特征</li>
        <li>常见组合：押金和保证金、应收关联公司款项、应收代垫款项、员工备用金</li>
        <li>前瞻性信息：宏观经济、行业趋势、债务人信用变化等纳入预期信用损失</li>
        <li>与前期及同行业对比，关注是否利用政策/估计变更操纵利润</li>
        <li>回顾上期估计值与当期结果，考虑是否存在管理层偏向迹象</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/** K1TabPolicyCheck.vue — K1-6 信用减值损失会计政策检查 */
import { ref, inject, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const textSections = [
  { id: 'K1-6-forward', label: '（二）前瞻性信息的来源及其影响', description: '检查是否考虑前瞻性信息对预期信用损失的影响（宏观经济、行业趋势等）。', placeholder: '说明前瞻性信息来源及其对ECL的影响...' },
  { id: 'K1-6-peer', label: '（三）同行业公司的会计政策', description: '与同行业其他公司会计政策对比，关注是否利用政策/估计变更操纵利润。', placeholder: '记录同行业公司会计政策对比情况...' },
]

interface Combo { id: string; basis: string }
const DEFAULT_COMBOS = ['押金和保证金', '应收关联公司款项', '应收代垫款项', '员工备用金']

const listedExamples = [
  { company: '中国中铁', text: '依据信用风险特征将其他应收款划分为若干组合：组合1 应收押金和保证金；组合2 应收代垫款；组合3 应收其他款项。参考历史信用损失经验，结合当前状况及未来经济预测，通过违约风险敞口和未来12个月内或整个存续期预期信用损失率计算预期信用损失。' },
  { company: '海螺水泥', text: '对单项测试未发生减值的其他应收款，包括在具有类似信用风险特征的组合中再进行减值测试。组合1 除政府代垫款及银行委托理财产品以外的其他应收款；组合2 政府代垫款；组合3 银行委托理财产品。' },
  { company: '北辰实业', text: '组合1 应收押金、保证金及备用金；组合2 应收关联公司款项；组合3 应收少数股东款项；组合4 应收代垫款项；组合5 应收其他款项。通过违约风险敞口和未来12个月内或整个存续期预期信用损失率计算预期信用损失。' },
  { company: '拉夏贝尔', text: '对较低信用风险金融工具假设信用风险自初始确认后未显著增加，按12个月内预期信用损失计量。组合：押金和保证金；员工备用金及其他；应收子公司款项；应收股利款；应收定期存款利息。' },
  { company: '上海医药', text: '组合一 账龄；组合二 关联方股利；组合三 利息及银行承兑汇票；组合四 保证金(含押金)及其他应收供应商款项；组合五 应收合并范围内公司款项。' },
  { company: '上海电气', text: '存在减值客观证据的单独进行减值测试计提单项减值准备。其余按组合：组合1 押金和保证金；组合2 员工备用金；组合3 其他。参考历史信用损失经验结合前瞻性预测计算预期信用损失。' },
]

const combos = ref<Combo[]>([])
const sectionContents = ref<Record<string, string>>({})
const conclusion = ref('')

onMounted(() => load())

function load() {
  const stored = props.allResponses.get('K1-6-combos')?.remark
  if (stored) {
    try { combos.value = JSON.parse(stored) } catch { seedCombos() }
  } else {
    seedCombos()
  }
  for (const s of textSections) sectionContents.value[s.id] = props.allResponses.get(s.id)?.remark || ''
  conclusion.value = props.allResponses.get('K1-6-conclusion')?.remark || ''
}
function seedCombos() {
  combos.value = DEFAULT_COMBOS.map((b, i) => ({ id: `combo-${i}`, basis: b }))
}
function addCombo() { combos.value.push({ id: `combo-${Date.now()}`, basis: '' }) }
function removeCombo(id: string) { combos.value = combos.value.filter(c => c.id !== id) }

function persist() {
  const raw = JSON.stringify(combos.value)
  props.allResponses.set('K1-6-combos', { item_id: 'K1-6-combos', conclusion: null, remark: raw })
  emit('save', 'K1-6-combos', { remark: raw })
}
function handleSectionChange(id: string, value: string) {
  sectionContents.value[id] = value
  props.allResponses.set(id, { item_id: id, conclusion: null, remark: value })
  emit('save', id, { remark: value })
}
function handleConclusionChange(value: string) {
  conclusion.value = value
  props.allResponses.set('K1-6-conclusion', { item_id: 'K1-6-conclusion', conclusion: value, remark: value })
  emit('save', 'K1-6-conclusion', { conclusion: value, remark: value })
}
function applyExample(ex: { company: string; text: string }) {
  const cur = sectionContents.value['K1-6-peer'] || ''
  const addition = `【${ex.company}】${ex.text}`
  sectionContents.value['K1-6-peer'] = cur ? `${cur}\n${addition}` : addition
  handleSectionChange('K1-6-peer', sectionContents.value['K1-6-peer'])
  ElMessage.success(`已套用 ${ex.company} 政策示例`)
}
function handleAiGenerate(section: string) { console.log('[K1-6] AI generate:', section) }
function handleReview() { openReviewDialog('K1-6-policy') }
</script>

<style scoped>
.k1-tab-policy-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 4px solid var(--el-color-warning); background: #fffbeb;
  padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6;
}
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; margin: 0 0 10px; }
.policy-table { font-size: var(--wp-font-size, 13px); }
.policy-section {
  margin-bottom: 12px; padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
}
.policy-section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.policy-section-title { font-size: 14px; font-weight: 600; margin: 0; }
.policy-section-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.readonly-content { padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; min-height: 40px; white-space: pre-wrap; line-height: 1.6; }
.ref-card { margin-bottom: 10px; }
.ref-card :deep(.el-card__header) { padding: 8px 14px; }
.ref-card :deep(.el-card__body) { padding: 12px 14px; }
.ex-company { font-weight: 600; }
.ex-apply { margin-left: 12px; }
.ex-text { font-size: 12px; line-height: 1.7; color: var(--el-text-color-regular); margin: 0; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
