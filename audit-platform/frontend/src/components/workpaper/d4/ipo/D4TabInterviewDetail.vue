<script setup lang="ts">
/**
 * D4TabInterviewDetail — D4-31 客户访谈记录
 *
 * 结构化访谈问卷：4大章节 + 多选/单选/条件展开
 * 元信息 → 受访人介绍 → 客户基本情况 → 业务情况(7问) → 关联关系(3问)
 * + 附件清单 + 签字区 + 承诺声明 + CAS18提示
 * AI辅助生成访谈问卷内容 + 双模式OO
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 问卷数据模型 ─────────────────────────────────────────────────────
interface InterviewData {
  // 元信息
  target: string; timePlace: string; interviewee: string; interviewer: string
  // 一、受访人介绍
  introduction: string
  // 二、客户基本情况
  companyName: string; regCapital: string; establishDate: string; bizNature: string
  legalRep: string; equityStructure: string
  // 三、业务情况
  q1_relation: string[]  // 多选
  q2a_payment: string    // 客户采购结算
  q2b_collection: string // 客户销售结算
  q3a_hasContract: string // 是/否
  q3b_quality: string
  q3c_returnClause: string // 是/否
  q3d_returnAmount: string
  q3e_acceptance: string
  q3f_hasRebate: string  // 是/否
  q3f_rebateMethod: string
  q3f_rebateAmount: string
  q3g_finalSold: string  // 是/否
  q4_otherFunds: string  // 是/否
  q5_otherMatters: string
  // 四、关联关系
  q6_hasShares: string   // 是/否
  q6_hasPosition: string // 是/否
  q6_hasTransaction: string // 是/否
  // 签字
  signInterviewee: string; signAuditor: string; signOther: string; signDate: string
}

const defaultData = (): InterviewData => ({
  target: '', timePlace: '', interviewee: '', interviewer: '',
  introduction: '',
  companyName: '', regCapital: '', establishDate: '', bizNature: '', legalRep: '', equityStructure: '',
  q1_relation: [], q2a_payment: '', q2b_collection: '',
  q3a_hasContract: '', q3b_quality: '', q3c_returnClause: '', q3d_returnAmount: '',
  q3e_acceptance: '', q3f_hasRebate: '', q3f_rebateMethod: '', q3f_rebateAmount: '',
  q3g_finalSold: '', q4_otherFunds: '', q5_otherMatters: '',
  q6_hasShares: '', q6_hasPosition: '', q6_hasTransaction: '',
  signInterviewee: '', signAuditor: '', signOther: '', signDate: '',
})

const formData = ref<InterviewData>(defaultData())
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function loadData() {
  const r = props.allResponses.get('D4-31-interview')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p && typeof p === 'object') { formData.value = { ...defaultData(), ...p }; return } } catch {} }
  formData.value = defaultData()
}
watch(() => props.allResponses.get('D4-31-interview')?.remark, loadData, { immediate: true })

function persistAll() {
  props.allResponses.set('D4-31-interview', { item_id: 'D4-31-interview', conclusion: null, remark: JSON.stringify(formData.value) })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: [props.allResponses.get('D4-31-interview')].filter(Boolean) } })) }, 2000)
}
function update(field: keyof InterviewData, value: any) { if (props.isReadonly) return; (formData.value as any)[field] = value; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: [props.allResponses.get('D4-31-interview')].filter(Boolean) } })) } })

const editorMode = ref<string>('问卷视图'); const modeOptions = ['问卷视图', '在线编辑']
const activeSection = ref('meta')
const showExample = ref(false)

// AI
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiLoading = ref(false)

async function aiGenerateIntro() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'interview-questions',
      existingContent: formData.value.introduction || '',
      relatedContext: { task: '根据客户基本情况生成访谈人介绍模板文字', companyName: formData.value.companyName, target: formData.value.target },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (t) { await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); update('introduction', t) }
    else ElMessage.warning('AI 未生成内容')
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = false }
}

// 选项定义
const RELATION_OPTIONS = ['客户是终端客户', '客户是经销商(客户)', '客户是供应商', '客户既是客户又是供应商', '客户是ABC的关联方']
const PAYMENT_OPTIONS = ['预付款方式', '货到付款方式', '赊销方式', '预付款方式和赊销方式兼有']
const COLLECTION_OPTIONS = ['预收款方式', '货到收款方式', '赊销方式', '预收款方式和赊销方式兼有']
const QUALITY_OPTIONS = ['良好', '一般', '产品质量不稳定', '产品质量差']
const RETURN_AMOUNT_OPTIONS = ['无', '20万元以下', '20-50万元', '50-100万元', '100万元以上']
const ACCEPTANCE_OPTIONS = ['检验合格后计量入库签收确认收到货物', '直接计量入库签收确认收到货物', '其他方式请描述']
const REBATE_METHOD_OPTIONS = ['现金', '其他方式']
const REBATE_AMOUNT_OPTIONS = ['10万元以下', '10-50万元', '50-100万元', '100万元以上']

// 案例中交易核对表数据
const exampleTradeItems = [
  { seq: 1, item: '交易模式', info: '包销', source: '与合同条款一致' },
  { seq: 2, item: '交易标的', info: 'AAA材料', source: '与合同条款一致' },
  { seq: 3, item: '交易规模', info: '500-800吨（含税金额约5000-8000万）', source: '与合同条款一致' },
  { seq: 4, item: '付款方式', info: '银行承兑汇票或银行转账', source: '与合同条款一致' },
  { seq: 5, item: '账期时间', info: '与合同条款一致', source: '与合同条款一致' },
  { seq: 6, item: '付款期限', info: '十个月以内，基本在月之内发货（一般每月发一次货）', source: '合同条款为十个工之内' },
  { seq: 7, item: '账金返利', info: '结存差额高于若超过27000万，按全年期初差额余额当月，按年归还每年进行合同金额', source: '与合同条款一致' },
  { seq: 8, item: '账金水平', info: '略高于同行业销售水平，行业平均为4.8-5%', source: '与合同条款一致' },
  { seq: 9, item: '运输方式及费用承担', info: '火车运输为主，少量汽运/叉车运输；发运时自提，运费由买方XXX负担', source: '与合同条款一致' },
  { seq: 10, item: '交付方式', info: 'XYZ收到货，签字确认即可/交付完毕', source: '与合同条款一致' },
  { seq: 11, item: '质量保证', info: '收货验收后十个月', source: '与合同条款一致' },
  { seq: 12, item: '验收或检验', info: '出具收据即可到账认收入次/月', source: '与凭证检查结论一致' },
  { seq: 13, item: '退货、换货条件', info: '合同5年来，从未发生过一次重大质量问题损，换货/赔偿', source: '与关于/入境条款行信息一致' },
  { seq: 14, item: '是否涉及委托加工', info: '否', source: '' },
  { seq: 15, item: '是否存在来料加工', info: '否', source: '' },
  { seq: 16, item: '资金交易情况', info: '无', source: '' },
  { seq: 17, item: '第三方收款/付款', info: '无', source: '' },
  { seq: 18, item: '代收款、代付款', info: '无', source: '' },
  { seq: 19, item: '其他资金往来', info: '无', source: '' },
  { seq: 20, item: '是否涉知', info: '否', source: '' },
]
</script>

<template>
<div class="d4-interview-detail">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-button size="small" type="warning" plain @click="showExample = true">📖 查看访谈案例</el-button>
      <GtIndexChip value="wp:D4-30" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-31-detail')">💬 复核</el-button>
    </div>
  </div>

  <template v-if="editorMode === '问卷视图'">
    <!-- 左侧导航 + 右侧内容 -->
    <div class="questionnaire-layout">
      <nav class="section-nav">
        <div :class="['nav-item', { active: activeSection === 'meta' }]" @click="activeSection='meta'">元信息</div>
        <div :class="['nav-item', { active: activeSection === 'ch1' }]" @click="activeSection='ch1'">一、受访人介绍</div>
        <div :class="['nav-item', { active: activeSection === 'ch2' }]" @click="activeSection='ch2'">二、客户基本情况</div>
        <div :class="['nav-item', { active: activeSection === 'ch3' }]" @click="activeSection='ch3'">三、业务情况</div>
        <div :class="['nav-item', { active: activeSection === 'ch4' }]" @click="activeSection='ch4'">四、关联关系</div>
        <div :class="['nav-item', { active: activeSection === 'sign' }]" @click="activeSection='sign'">签字与承诺</div>
      </nav>

      <div class="section-content">
        <!-- 元信息 -->
        <div v-show="activeSection==='meta'" class="form-section">
          <h4>访谈基本信息</h4>
          <div class="form-grid">
            <div class="form-item"><label>访谈对象</label><el-input :model-value="formData.target" :disabled="isReadonly" @input="(v:string)=>update('target',v)" /></div>
            <div class="form-item"><label>访谈时间及地点</label><el-input :model-value="formData.timePlace" :disabled="isReadonly" @input="(v:string)=>update('timePlace',v)" /></div>
            <div class="form-item"><label>接受访谈人员及职务</label><el-input :model-value="formData.interviewee" :disabled="isReadonly" @input="(v:string)=>update('interviewee',v)" /></div>
            <div class="form-item"><label>访谈人</label><el-input :model-value="formData.interviewer" :disabled="isReadonly" @input="(v:string)=>update('interviewer',v)" /></div>
          </div>
          <div class="form-hint">💡 访谈内容应根据被审计单位实际情况、关注的客户主要风险情况修改。</div>
        </div>

        <!-- 一、受访人介绍 -->
        <div v-show="activeSection==='ch1'" class="form-section">
          <div class="section-title-row"><h4>一、接受访谈人介绍</h4><el-button v-if="aiAvailable" size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="aiGenerateIntro">🤖 AI生成模板</el-button></div>
          <p class="field-hint">包括姓名、任职的公司、职务、具体负责的工作等</p>
          <el-input type="textarea" :autosize="{minRows:3,maxRows:10}" :model-value="formData.introduction" :disabled="isReadonly" placeholder="请记录受访人基本介绍信息" @input="(v:string)=>update('introduction',v)" />
        </div>

        <!-- 二、客户基本情况 -->
        <div v-show="activeSection==='ch2'" class="form-section">
          <h4>二、客户的基本情况</h4>
          <p class="field-hint">附有关部门盖章确认的工商登记证明文件、主体纳税证明等</p>
          <div class="form-grid">
            <div class="form-item"><label>公司名称</label><el-input :model-value="formData.companyName" :disabled="isReadonly" @input="(v:string)=>update('companyName',v)" /></div>
            <div class="form-item"><label>注册资本</label><el-input :model-value="formData.regCapital" :disabled="isReadonly" @input="(v:string)=>update('regCapital',v)" /></div>
            <div class="form-item"><label>成立日期</label><el-input :model-value="formData.establishDate" :disabled="isReadonly" @input="(v:string)=>update('establishDate',v)" /></div>
            <div class="form-item"><label>经济性质</label><el-input :model-value="formData.bizNature" :disabled="isReadonly" @input="(v:string)=>update('bizNature',v)" /></div>
            <div class="form-item"><label>法定代表人</label><el-input :model-value="formData.legalRep" :disabled="isReadonly" @input="(v:string)=>update('legalRep',v)" /></div>
            <div class="form-item"><label>股权结构</label><el-input :model-value="formData.equityStructure" :disabled="isReadonly" @input="(v:string)=>update('equityStructure',v)" /></div>
          </div>
        </div>

        <!-- 三、业务情况 -->
        <div v-show="activeSection==='ch3'" class="form-section">
          <h4>三、与客户业务情况</h4>
          <!-- Q1 业务关系 -->
          <div class="question-card">
            <div class="q-label">1. 客户与发行人的业务关系为</div>
            <el-checkbox-group :model-value="formData.q1_relation" :disabled="isReadonly" @change="(v:string[])=>update('q1_relation',v)">
              <el-checkbox v-for="opt in RELATION_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </div>
          <!-- Q2 结算方式 -->
          <div class="question-card">
            <div class="q-label">2. 客户与发行人的结算方式</div>
            <div class="sub-question"><span class="sub-label">(1) 客户向发行人的采购</span>
              <el-radio-group :model-value="formData.q2a_payment" :disabled="isReadonly" @change="(v:string)=>update('q2a_payment',v)"><el-radio v-for="opt in PAYMENT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group>
            </div>
            <div class="sub-question"><span class="sub-label">(2) 客户向发行人的销售</span>
              <el-radio-group :model-value="formData.q2b_collection" :disabled="isReadonly" @change="(v:string)=>update('q2b_collection',v)"><el-radio v-for="opt in COLLECTION_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group>
            </div>
          </div>
          <!-- Q3 交易情况 -->
          <div class="question-card">
            <div class="q-label">3. 20XX年度至今客户与发行人交易情况</div>
            <div class="sub-question"><span class="sub-label">(1) 所有交易行为是否签订合同</span><el-radio-group :model-value="formData.q3a_hasContract" :disabled="isReadonly" @change="(v:string)=>update('q3a_hasContract',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(2) 产品质量情况（适用客户）</span><el-radio-group :model-value="formData.q3b_quality" :disabled="isReadonly" @change="(v:string)=>update('q3b_quality',v)"><el-radio v-for="opt in QUALITY_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(3) 是否约定退换货条款</span><el-radio-group :model-value="formData.q3c_returnClause" :disabled="isReadonly" @change="(v:string)=>update('q3c_returnClause',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
            <div v-if="formData.q3c_returnClause==='是'" class="sub-question condition-expand"><span class="sub-label">(4) 退换货金额</span><el-radio-group :model-value="formData.q3d_returnAmount" :disabled="isReadonly" @change="(v:string)=>update('q3d_returnAmount',v)"><el-radio v-for="opt in RETURN_AMOUNT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(5) 产品验收入库情况</span><el-radio-group :model-value="formData.q3e_acceptance" :disabled="isReadonly" @change="(v:string)=>update('q3e_acceptance',v)"><el-radio v-for="opt in ACCEPTANCE_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(6) 是否存在返利约定</span><el-radio-group :model-value="formData.q3f_hasRebate" :disabled="isReadonly" @change="(v:string)=>update('q3f_hasRebate',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
            <template v-if="formData.q3f_hasRebate==='是'">
              <div class="sub-question condition-expand"><span class="sub-label">A. 返利支付方式</span><el-radio-group :model-value="formData.q3f_rebateMethod" :disabled="isReadonly" @change="(v:string)=>update('q3f_rebateMethod',v)"><el-radio v-for="opt in REBATE_METHOD_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
              <div class="sub-question condition-expand"><span class="sub-label">B. 返利金额</span><el-radio-group :model-value="formData.q3f_rebateAmount" :disabled="isReadonly" @change="(v:string)=>update('q3f_rebateAmount',v)"><el-radio v-for="opt in REBATE_AMOUNT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            </template>
            <div class="sub-question"><span class="sub-label">(7) 经销商购买的货物是否已最终销售</span><el-radio-group :model-value="formData.q3g_finalSold" :disabled="isReadonly" @change="(v:string)=>update('q3g_finalSold',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio><el-radio value="不适用">不适用</el-radio></el-radio-group></div>
          </div>
          <!-- Q4 其他资金 -->
          <div class="question-card">
            <div class="q-label">4. 除采购外是否还存在其他资金往来？</div>
            <el-radio-group :model-value="formData.q4_otherFunds" :disabled="isReadonly" @change="(v:string)=>update('q4_otherFunds',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group>
          </div>
          <!-- Q5 其他 -->
          <div class="question-card">
            <div class="q-label">5. 其他重要事项</div>
            <el-input type="textarea" :autosize="{minRows:2,maxRows:6}" :model-value="formData.q5_otherMatters" :disabled="isReadonly" placeholder="记录其他需关注的重要事项" @input="(v:string)=>update('q5_otherMatters',v)" />
          </div>
        </div>

        <!-- 四、关联关系 -->
        <div v-show="activeSection==='ch4'" class="form-section">
          <h4>四、关联关系情况</h4>
          <p class="field-hint">发行人的实际控制人、自然人股东、董事、监事或高管人员及主要关联方是否在客户持有股份</p>
          <div class="question-card"><div class="q-label">是否持有股份</div><el-radio-group :model-value="formData.q6_hasShares" :disabled="isReadonly" @change="(v:string)=>update('q6_hasShares',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
          <div class="question-card"><div class="q-label">是否担任职务</div><el-radio-group :model-value="formData.q6_hasPosition" :disabled="isReadonly" @change="(v:string)=>update('q6_hasPosition',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
          <div class="question-card"><div class="q-label">是否和客户有交易</div><el-radio-group :model-value="formData.q6_hasTransaction" :disabled="isReadonly" @change="(v:string)=>update('q6_hasTransaction',v)"><el-radio value="是">是</el-radio><el-radio value="否">否</el-radio></el-radio-group></div>
        </div>

        <!-- 签字与承诺 -->
        <div v-show="activeSection==='sign'" class="form-section">
          <h4>附件清单</h4>
          <div class="attachment-list">
            <div class="attachment-item">
              <span class="att-label">1. 供应商盖章确认的工商登记证明文件</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">📎 上传 ▾</el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('附件上传功能开发中')"><span>上传文件</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('文件夹上传功能开发中')"><span>上传文件夹</span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">2. 跟函回函</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">📎 上传 ▾</el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('附件上传功能开发中')"><span>上传文件</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('文件夹上传功能开发中')"><span>上传文件夹</span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">3. XX产品销售明细账、XX产品库存商品明细账</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">📎 上传 ▾</el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('附件上传功能开发中')"><span>上传文件</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('文件夹上传功能开发中')"><span>上传文件夹</span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">4. XXX账户资金流水</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">📎 上传 ▾</el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('附件上传功能开发中')"><span>上传文件</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('文件夹上传功能开发中')"><span>上传文件夹</span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
          </div>

          <h4 style="margin-top:20px;">参与访谈的各方人员签字</h4>
          <div class="form-grid">
            <div class="form-item"><label>接受访谈人员</label><el-input :model-value="formData.signInterviewee" :disabled="isReadonly" @input="(v:string)=>update('signInterviewee',v)" /></div>
            <div class="form-item"><label>审计人员</label><el-input :model-value="formData.signAuditor" :disabled="isReadonly" @input="(v:string)=>update('signAuditor',v)" /></div>
            <div class="form-item"><label>其他人员</label><el-input :model-value="formData.signOther" :disabled="isReadonly" @input="(v:string)=>update('signOther',v)" /></div>
            <div class="form-item"><label>日期</label><el-input :model-value="formData.signDate" :disabled="isReadonly" placeholder="YYYY-MM-DD" @input="(v:string)=>update('signDate',v)" /></div>
          </div>
          <!-- 承诺声明 -->
          <div class="commitment-box">
            <p class="commitment-text">"本公司向XX会计师事务所提供的信息和资料真实、完整，如存在虚假信息或重大遗漏，本公司愿意承担一切法律责任"。</p>
            <p class="commitment-hint">如识别出客户存在第三方配合实施财务舞弊的风险，应要求客户就其提供的资料进行承诺并加盖公章。</p>
          </div>
          <!-- CAS18提示 -->
          <details class="tips-collapse"><summary class="tips-summary">⚠️ CAS18号实地走访提示</summary><ol class="tips-list">
            <li>选择多名或不同层级人员访谈相同问题，进行相互印证。</li>
            <li>核实被询问人员是否与被审计单位存在特殊关系。</li>
            <li>对客户的产品实施观察、检查等程序，关注存货的存放和领用是否为真实需要。</li>
            <li>对经销商客户关注库存量是否明显不合理，考虑检查经销商进销存记录。</li>
            <li>针对识别出的风险，考虑采用跟函方式进行函证，观察函证处理过程。</li>
          </ol></details>
        </div>
      </div>
    </div>
  </template>

  <template v-if="editorMode === '在线编辑'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="客户访谈记录 D4-31" :readonly="isReadonly" /></div>
  </template>

  <!-- 访谈案例弹窗 -->
  <el-dialog v-model="showExample" title="📖 访谈记录与核对示例" width="800px" destroy-on-close top="5vh">
    <div class="example-content">
      <div class="example-section">
        <h4 class="example-title">一、走访的公司基本信息</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>【XYZ公司的基本情况，包括：XYZ公司法定代表人、注册地、注册资本、设立及变更历史、经营范围、实缴资本情况及在册股东出资比例等。公司营业执照、企业信用信息公示报告等】</p>
          <p>工商信息查询结果、天眼查等查询结果。</p>
          <p>百度地图等查询走访地址的结果。</p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">二、交易基本信息</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>【询问及XYZ公司与发行人的合作情况（交易模式、交易金额、交易方式、付款方式、退换条款、结算条件等），并关注实物流与合同条款及账面记录的一致性；需核对的问题如下，将核对情况记录在下表：】</p>
        </div>
        <el-table :data="exampleTradeItems" border size="small" class="example-table">
          <el-table-column prop="seq" label="Q#" width="40" align="center" />
          <el-table-column prop="item" label="项目" width="100" />
          <el-table-column prop="info" label="询问所获信息" min-width="200" />
          <el-table-column prop="source" label="来自发行人合同条款" min-width="150" />
        </el-table>
      </div>

      <div class="example-section">
        <h4 class="example-title">三、与发行人的交易与合同条款核对</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>【询问及取得有关证明文件核对XYZ公司与发行人合作协议的情况。包括合同条款约定、销售金额比对、第三方收款/付款情况、资金交易情况等。】</p>
          <p>与发行人合作始于2008年签订合作协议【与发行人XXX产品销售AAAHH材料】，报告三年合同金额分别为XXX。</p>
          <p>期间交易金额、与前述发票及台账核对一致，无异议。交易金额比对正常。</p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">四、走访经营情况</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>【走访XYZ的生产经营情况（若适用），关注其生产经营现状与访谈内容和凭证扫描】</p>
          <p>XYZ公司位于XXX工业园区，园区面积1300亩，主要生产XXXXX，主要原材料AAA，年产能XXXX吨。</p>
          <p>XYZ公司目前拥有3个生产车间，整体成品存"生产许可证"，开工率约为90%。</p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">五、凭证核对</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>【对XYZ公司进行现场函证（此部分内容包括但不限于：截至目的日的货权/服务合同、或是全期的全部交易及往来余额）；无联方关系确认函。】</p>
          <p>现场收取的XYZ公司对函证信息进行一次（差异为XXXX元，250万），XYZ公司确认无任何第2月前实际的质检的原材料按照应收账款余额，并按要求对其进行盖章签字。</p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">六、关联方关系</h4>
        <p class="example-hint">【建议采写】</p>
        <div class="example-text">
          <p>走访公司的股权结构、实际控制人。</p>
          <p>走访公司的董监高、关键经办人员（如正名、销售员/门店店人、出纳等）。</p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">七、其他</h4>
        <p class="example-hint">【建议采写】</p>
      </div>

      <div class="example-section">
        <h4 class="example-title">走访结论</h4>
        <div class="example-text">
          <p>（由审计人员根据走访情况总结得出结论）</p>
        </div>
      </div>
    </div>
  </el-dialog>
</div>
</template>

<style scoped>
.d4-interview-detail { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }

.questionnaire-layout { display: flex; gap: 20px; min-height: 500px; }
.section-nav { width: 140px; flex-shrink: 0; position: sticky; top: 80px; align-self: flex-start; }
.nav-item { padding: 8px 12px; margin-bottom: 4px; border-radius: 6px; font-size: 12px; color: #606266; cursor: pointer; transition: all 0.2s; }
.nav-item:hover { background: #f0f5ff; color: #409eff; }
.nav-item.active { background: #ecf5ff; color: #409eff; font-weight: 600; border-left: 3px solid #409eff; }

.section-content { flex: 1; min-width: 0; }
.form-section { padding: 16px; border: 1px solid #ebeef5; border-radius: 8px; background: #fafbfc; }
.form-section h4 { margin: 0 0 12px; font-size: 14px; color: #303133; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title-row h4 { margin: 0; }

.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 20px; }
.form-item { display: flex; flex-direction: column; gap: 4px; }
.form-item label { font-size: 12px; color: #909399; }
.form-hint { margin-top: 12px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-size: 12px; color: #67c23a; }
.field-hint { font-size: 12px; color: #909399; margin-bottom: 10px; }

.question-card { margin-bottom: 14px; padding: 12px 16px; border: 1px solid #ebeef5; border-radius: 6px; background: #fff; }
.q-label { font-size: 13px; font-weight: 500; color: #303133; margin-bottom: 8px; }
.sub-question { margin: 8px 0 8px 16px; }
.sub-label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; }
.condition-expand { margin-left: 32px; padding: 8px 12px; background: #fdf6ec; border-radius: 4px; border-left: 2px solid #e6a23c; }

.commitment-box { margin-top: 16px; padding: 14px 16px; border: 1px solid #e1f3d8; border-radius: 6px; background: #f0f9eb; }
.commitment-text { font-size: 13px; color: #303133; font-style: italic; margin-bottom: 8px; }
.commitment-hint { font-size: 12px; color: #e6a23c; }

.attachment-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.attachment-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border: 1px solid #ebeef5; border-radius: 6px; background: #fff; }
.att-label { font-size: 12px; color: #606266; }

.tips-collapse { margin-top: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; background: #fef0f0; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }

/* 案例弹窗 */
.example-content { max-height: 70vh; overflow-y: auto; padding: 0 8px; }
.example-section { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #f0f0f0; }
.example-section:last-child { border-bottom: none; }
.example-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 4px; }
.example-hint { font-size: 12px; color: #e6a23c; margin-bottom: 8px; font-style: italic; }
.example-text { font-size: 13px; color: #606266; line-height: 1.8; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; border-left: 3px solid #409eff; }
.example-text p { margin: 4px 0; }
.example-table { margin-top: 8px; font-size: 13px; }
.example-table :deep(.el-table__cell) { padding: 6px 8px; font-size: 13px; }
</style>
