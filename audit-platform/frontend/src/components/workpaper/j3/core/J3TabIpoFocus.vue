<script setup lang="ts">
/**
 * J3TabIpoFocus — IPO 股份支付监管审计要点（整合页）
 *
 * 整合两份监管文件并以「逻辑主线 + 层次化条款」单页呈现：
 *  ① 北京注册会计师协会专家委员会提示[2016]第8号—IPO企业股权激励工具关注的审计重点
 *  ② 首发业务问答（二）问题1—股份支付
 * 供「IPO企业股权激励工具关注的审计重点」「首发业务解答二」两个 sheet 共用。
 */
import { ref, computed, onMounted, watch } from 'vue'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)
const KEY = { note: 'J3-IPO-note' }

// ── 逻辑主线（整合两份文件的审计逻辑） ───────────────────────────────────────
const LOGIC_STEPS = [
  { icon: '🔍', title: '识别适用情形', desc: '向职工/持股平台/客户/供应商新增或转让股份、低价增资等，判断是否构成 CAS 11 股份支付；报告期前对期初未分配利润影响重大的也应考虑。' },
  { icon: '💰', title: '确定公允价值', desc: 'IPO 股份未流通，按 CAS 22 三层次确定；管理层四维度相互印证；优先参考近期公允的 PE/战投入股价。' },
  { icon: '📊', title: '费用处置与摊销', desc: '无服务期限制→一次性计入授予日当期（非经常性损益）；有强制性服务期→服务期内分摊（经常性损益）。' },
  { icon: '⏱️', title: '上市规则：a/b 孰短', desc: '为满足"股权清晰"约定"上市即解锁"时，摊销期取服务期 a 与授予日至上市前报告期截止 b 孰短；每 6 个月更新对 b 的判断。' },
  { icon: '📝', title: '披露与核查', desc: '招股书/附注披露形成原因、公允价值及确认方法；保荐机构与申报会计师核查并对公允价值合理性、服务期判断、会计处理合规性发表明确意见。' },
]

// ── 关键规则速查（两份文件核心要点提炼） ─────────────────────────────────────
const KEY_RULES = [
  { tag: '重分类', text: '早于三年一期申报期的股份支付仍需关注：影响历史资产负债表权益项目期初分类，对留存收益与资本公积产生重分类影响。' },
  { tag: '公允价值', text: '三层次优先级：活跃市场相同资产报价 > 类似资产/可观察输入值 > 不可观察输入值；IPO 多依赖第二/第三层次。' },
  { tag: '四维度印证', text: '①近 6 个月外部机构/战投相对公允价格；②专业评估（首选现金流折现法）；③同类行业市盈率/市净率校对；④期权定价模型。' },
  { tag: '摊销期间', text: '仅禁售义务（非可行权条件）→ 全部计入授予日报告期损益；有强制服务期约束 → 分期摊销。' },
  { tag: 'a/b 孰短', text: '约定"上市即解锁"时，以服务期 a 与"授予日至上市前临近报告期截止 b"孰短作为摊销期限，并每 6 个月刷新 b。' },
  { tag: '实控人超比例', text: '实控人/老股东以低于公允价值增资，超过其原持股比例部分属股份支付（原比例按直接+穿透间接合并计算）。' },
]

// ── 文件①：北注协 2016-8 号 ───────────────────────────────────────────────────
interface DocNode { no?: string; title?: string; paras?: string[]; points?: string[]; subs?: DocNode[] }
const DOC1_INTRO = [
  '股权激励计划作为行之有效的激励工具被广泛采用。IPO 计划中已设定的股权激励工具对财务报表影响较重要，是 IPO 审计的重点和难点。',
  '本提示仅供参考，不能替代相关法律法规、执业准则及职业判断；审计时间、范围和程度需结合实际情况、风险导向原则及职业判断确定，不能照搬照抄。',
]
const DOC1: DocNode[] = [
  { no: '一', title: '关注 IPO 企业在以往期间的股权激励工具', subs: [
    { no: '（一）', title: '对历史财务报表以外信息的关注', paras: ['历史财务报表很可能未体现相应会计处理，仅凭历史报表无法辨别。应主动与管理层及股东讨论询问，辨认历史年度是否存在 CAS 11 所明确的股份支付情形。'] },
    { no: '（二）', title: '深入沟通股份支付的会计影响', paras: ['权益工具包括企业本身、母公司或同集团其他会计主体的权益工具（含专设股权激励平台/控股壳公司）。管理层认知可能与准则不一致，需深入沟通。通常以下属于股份支付会计影响事项：'], points: [
      '公司向董事、高管、核心员工、员工持股平台或其他人员发行新股价格明显低于公允价值（"其他人员"含个人或公司也可能落入范畴）；',
      '股东将其持有股份以较低价格转让给上述人士；',
      '股票发行价格低于每股净资产的，亦需格外关注（参见全国股转《挂牌公司股票发行常见问题解答（一）》）。',
    ] },
  ] },
  { no: '二', title: '关注 IPO 企业股权激励的初始计量', subs: [
    { no: '（一）', title: '确定公允价值的三个层次（CAS 22）', points: [
      '第一层次：计量日能获得相同资产/负债在活跃市场的报价，以该报价为依据；',
      '第二层次：活跃市场中类似资产报价、非活跃市场中相同/类似资产报价、除报价外的其他可观察输入值（利率与收益率曲线、隐含波动率、信用利差等）、市场验证的输入值；',
      '第三层次：相关资产/负债的不可观察输入值。IPO 企业通常需依靠第二或第三层次估计。',
    ] },
    { no: '（二）', title: '管理层确定公允价值的考虑（四维度相互印证）', points: [
      '以引入外部机构/战投相对公允的价格为参照（通常考虑 6 个月内股权交易，并关注近期业务重大变化；明显不公允的应排除）；',
      '引入专业资产评估机构评估（首选现金流折现法）；',
      '以相同/类似行业市盈率、市净率作为校对依据；',
      '使用期权定价模型。',
    ] },
  ] },
  { no: '三', title: '关注 IPO 企业对股权激励费用的处置', paras: ['CAS 11 第五条：授予后立即可行权的以权益结算的股份支付，应在授予日按公允价值计入相关成本或费用并增加资本公积。基于成本费用与获取服务相配比，费用通常应在服务期间内分期摊销；一次性还是分期，取决于授予的目的和条件。'], subs: [
    { no: '（一）', title: '非可行权条件 → 全部计入授予日报告期损益', paras: ['若股权锁定期仅要求履行原股东的一般禁售义务，不要求员工未来继续服务或达到业绩条件（服务期限不确定，限售期为非可行权条件），则不能作为分期摊销的充分条件，费用应全部计入授予日报告期损益。'] },
    { no: '（二）', title: '强制性服务期约束 → 分期摊销', paras: ['若股东与高管员工的合同条款对员工具有强制性服务期限约束（获取服务与服务期限确定），此类可行权条件下会计处理应分期摊销。'] },
  ] },
  { no: '四', title: '结合上市申请时间表，关注证监会上市规则', subs: [
    { no: '（一）', title: '证监会规定："股权清晰"与 a/b 孰短摊销', paras: [
      '《首次公开发行股票并上市管理办法》（2015 修订）第十三条要求"发行人股权清晰"。股权激励多含服务期限/业绩条件，可能被认定为"股权不清晰"而不满足上市要求（如摊销期内离职的股权归属、业绩条件能否实现等）。',
      '企业常在协议中约定"若达成 IPO 即提前解除服务锁定，以 IPO 达成之日为终止点"。此时摊销期取服务期 a 与"授予日至上市前临近报告期截止 b"孰短。例如 a=36 个月，管理层判断第 26 个月获批（b=26），则按 26 个月摊销。',
      '管理层应在每 6 个月追加申报更新时，刷新对上市获批最终时段 b 的判断，据此考量摊销期间是否需修改。',
    ] },
    { no: '（二）', title: '示例', paras: ['2015 年 1 月某 IPO 企业向非现有股东的主要管理层及核心员工定向增发股份激励，符合股份支付全部特征。承诺函约定自授予日起 3 年全职工作后方享收益（a=36 个月）；启动创业板 IPO 后管理层判断至上市前最近会计期间截止预计持续 24 个月（b=24），故约定"提前上市即解锁"，按 a 与 b 孰短即 24 个月摊销公允价值，并每 6 个月更新对 b 的估计。'] },
  ] },
]

// ── 文件②：首发业务问答（二）问题1—股份支付 ─────────────────────────────────
const DOC2_QUESTION = '基于企业发展考虑，部分首发企业上市前通过增资或转让股份等形式实现高管/核心技术人员/员工/主要业务伙伴持股。首发企业股份支付成因复杂、公允价值难以计量，与上市公司股权激励存在较大不同。对此，首发企业及中介机构需重点关注哪些方面？'
const DOC2_ANSWER = '发行人报告期内为获取职工和其他方提供服务而授予股份的交易，编制申报会计报表时应按 CAS 11 相关规定处理。'
const DOC2: DocNode[] = [
  { no: '（1）', title: '具体适用情形', points: [
    '报告期内向职工（含持股平台）、客户、供应商等新增股份，及主要股东及其关联方向上述对象转让股份，均应考虑是否适用 CAS 11；报告期前对期初未分配利润影响重大的也应考虑。',
    '解决股份代持、家族财产分割/继承/赠与等非交易行为、资产重组/业务并购/持股方式转换/向老股东同比例配售等导致的股权变动，在有充分证据支持与获取服务无关时，一般无需作为股份支付处理。',
    '为发行人提供服务的实控人/老股东以低于公允价值增资：超过其原持股比例获得的新增股份属于股份支付；原持股比例按直接持有与穿透控股平台后间接持有合并计算。',
  ] },
  { no: '（2）', title: '确定公允价值', paras: ['应按企业会计准则原则确定权益工具公允价值，可合理考虑：入股时间阶段、业绩基础与变动预期、市场环境变化、行业特点、同行业并购重组市盈率、当年市盈率与市净率等；也可优先参考公平原则下各方最近达成的入股价格/相似股权价格（如近期合理的 PE 入股价）；也可采用恰当估值技术，但要避免有争议、结果显失公平的方法（如明显增长预期下按成本法评估的每股净资产）。'] },
  { no: '（3）', title: '计量方式', points: [
    '立即授予/转让完成且无明确服务期等限制条件的，原则上一次性计入发生当期，作为偶发事项计入非经常性损益；',
    '设定服务期等限制条件的，可采用恰当方法在服务期内分摊，计入经常性损益。',
  ] },
  { no: '（4）', title: '披露与核查', paras: ['发行人应在招股说明书及报表附注披露股份支付的形成原因、权益工具公允价值及确认方法。保荐机构及申报会计师应核查报告期内股份变动是否适用 CAS 11，并对以下发表明确意见：公允价值计量方法及结果是否合理、与同期可比公司估值有无重大差异及原因；限制性条件是否真实可行、服务期判断是否准确、各年/期确认的服务成本或费用是否准确；相关会计处理是否符合企业会计准则。'] },
]

// ── 适用性与关注记录（可编辑 + AI + 持久化） ─────────────────────────────────
const activeDocs = ref<string[]>(['doc1', 'doc2'])
const applyNote = ref('')
const aiLoading = ref(false)
function load() { const v = props.allResponses?.get(KEY.note)?.remark; if (v) applyNote.value = v }
let timer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { props.saveImmediate?.([{ item_id: KEY.note, conclusion: null, remark: applyNote.value }]) }, 800)
}
async function aiGen() {
  if (isReadonly.value) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = { 科目: 'IPO 股份支付监管审计要点（北注协2016-8号 + 首发问答二）' }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section: 'j3-ipo-applicability', context, existingContent: applyNote.value })
    const d = (res as { data?: Record<string, any> })?.data
    const text = d?.data?.content || d?.content || d?.data?.text || d?.text || ''
    if (text) { applyNote.value = text; scheduleSave() }
  } catch { /* 静默 */ } finally { aiLoading.value = false }
}
onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j3-ipo-focus">
    <el-alert type="warning" :closable="false" show-icon class="intro">
      <template #title>IPO 股份支付监管审计要点（整合参考）</template>
      <template #default>
        本页整合两份监管指引，供拟 IPO 企业股份支付审计参考：①北京注册会计师协会专家委员会提示[2016]第8号；②中国证监会《首发业务若干问题解答（二）》问题1。属方法论参考，实务须结合项目实际、风险导向与职业判断。
      </template>
    </el-alert>

    <!-- 逻辑主线 -->
    <h4 class="sec-title">🧭 审计逻辑主线（两份文件整合）</h4>
    <div class="logic-flow">
      <template v-for="(s, i) in LOGIC_STEPS" :key="i">
        <div class="logic-step">
          <div class="logic-icon">{{ s.icon }}</div>
          <div class="logic-title">{{ s.title }}</div>
          <div class="logic-desc">{{ s.desc }}</div>
        </div>
        <div v-if="i < LOGIC_STEPS.length - 1" class="logic-arrow">→</div>
      </template>
    </div>

    <!-- 关键规则速查 -->
    <h4 class="sec-title">⭐ 关键规则速查</h4>
    <div class="rules-grid">
      <div v-for="(r, i) in KEY_RULES" :key="i" class="rule-card">
        <el-tag size="small" type="warning" effect="dark">{{ r.tag }}</el-tag>
        <span class="rule-text">{{ r.text }}</span>
      </div>
    </div>

    <!-- 两份文件详细条款 -->
    <el-collapse v-model="activeDocs" class="doc-collapse">
      <el-collapse-item name="doc1">
        <template #title><span class="doc-hd">📘 文件① 北注协专家委员会提示[2016]第8号 — IPO 企业股权激励工具关注的审计重点</span></template>
        <p v-for="(p, i) in DOC1_INTRO" :key="'d1i' + i" class="doc-intro">{{ p }}</p>
        <div v-for="(sec, si) in DOC1" :key="'d1' + si" class="doc-sec">
          <div class="sec-h1"><span class="sec-no">{{ sec.no }}</span>、{{ sec.title }}</div>
          <p v-for="(p, pi) in sec.paras || []" :key="'p' + pi" class="doc-para">{{ p }}</p>
          <ol v-if="sec.points" class="doc-points"><li v-for="(pt, pi) in sec.points" :key="'pt' + pi">{{ pt }}</li></ol>
          <div v-for="(sub, sbi) in sec.subs || []" :key="'sub' + sbi" class="doc-sub">
            <div class="sec-h2">{{ sub.no }} {{ sub.title }}</div>
            <p v-for="(p, pi) in sub.paras || []" :key="'sp' + pi" class="doc-para">{{ p }}</p>
            <ol v-if="sub.points" class="doc-points"><li v-for="(pt, pi) in sub.points" :key="'spt' + pi">{{ pt }}</li></ol>
          </div>
        </div>
      </el-collapse-item>

      <el-collapse-item name="doc2">
        <template #title><span class="doc-hd">📗 文件② 证监会《首发业务若干问题解答（二）》问题1 — 股份支付</span></template>
        <div class="qa-block"><span class="qa-tag">问</span><span>{{ DOC2_QUESTION }}</span></div>
        <div class="qa-block answer"><span class="qa-tag ans">答</span><span>{{ DOC2_ANSWER }}</span></div>
        <div v-for="(sec, si) in DOC2" :key="'d2' + si" class="doc-sub">
          <div class="sec-h2">{{ sec.no }} {{ sec.title }}</div>
          <p v-for="(p, pi) in sec.paras || []" :key="'d2p' + pi" class="doc-para">{{ p }}</p>
          <ol v-if="sec.points" class="doc-points"><li v-for="(pt, pi) in sec.points" :key="'d2pt' + pi">{{ pt }}</li></ol>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 本项目适用性与关注记录 -->
    <div class="note-wrap">
      <div class="note-hd">
        <span>本项目适用性与关注记录</span>
        <div class="note-actions">
          <GtIndexChip value="wp:J3-1" :context-project-id="projectId" />
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="aiGen">🤖 AI辅助</el-button>
        </div>
      </div>
      <el-input v-model="applyNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="结合上述监管要点，记录本项目是否存在 IPO 股份支付事项、适用情形判断、公允价值确定方法、摊销期间（a/b 孰短）判断、披露与核查结论等。" @change="scheduleSave" />
    </div>
  </div>
</template>

<style scoped>
.j3-ipo-focus { padding: 16px; }
.intro { margin-bottom: 16px; }
.intro :deep(.el-alert__description) { font-size: 12px; line-height: 1.6; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 18px 0 10px; }
.logic-flow { display: flex; align-items: stretch; gap: 4px; flex-wrap: wrap; }
.logic-step { flex: 1; min-width: 150px; background: linear-gradient(135deg, #fdf6ec 0%, #fef9f0 100%); border: 1px solid #f5dab1; border-radius: 8px; padding: 10px 12px; }
.logic-icon { font-size: 20px; }
.logic-title { font-size: 13px; font-weight: 600; color: #b88230; margin: 4px 0; }
.logic-desc { font-size: 12px; color: #8c6d1f; line-height: 1.6; }
.logic-arrow { display: flex; align-items: center; color: #e6a23c; font-weight: 700; font-size: 18px; }
.rules-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
.rule-card { display: flex; gap: 8px; align-items: flex-start; background: #fff; border: 1px solid #ebeef5; border-left: 3px solid #e6a23c; border-radius: 6px; padding: 8px 12px; }
.rule-text { font-size: 12px; color: #606266; line-height: 1.6; }
.doc-collapse { margin-top: 18px; }
.doc-hd { font-size: 14px; font-weight: 600; color: #303133; }
.doc-intro { font-size: 12px; color: #909399; line-height: 1.7; margin: 4px 0; padding: 6px 10px; background: #f5f7fa; border-radius: 4px; }
.doc-sec { margin: 12px 0; }
.sec-h1 { font-size: 14px; font-weight: 700; color: #409eff; margin: 12px 0 6px; padding-bottom: 4px; border-bottom: 1px solid #ecf5ff; }
.sec-no { display: inline-block; }
.sec-h2 { font-size: 13px; font-weight: 600; color: #303133; margin: 10px 0 4px; }
.doc-sub { padding-left: 12px; border-left: 2px solid #ebeef5; margin: 8px 0; }
.doc-para { font-size: 13px; color: #606266; line-height: 1.8; margin: 4px 0; text-align: justify; }
.doc-points { margin: 4px 0; padding-left: 22px; }
.doc-points li { font-size: 13px; color: #606266; line-height: 1.8; margin-bottom: 4px; text-align: justify; }
.qa-block { display: flex; gap: 8px; font-size: 13px; line-height: 1.8; margin: 6px 0; color: #606266; }
.qa-block.answer { color: #303133; }
.qa-tag { flex-shrink: 0; width: 22px; height: 22px; line-height: 22px; text-align: center; border-radius: 4px; background: #909399; color: #fff; font-size: 12px; font-weight: 600; }
.qa-tag.ans { background: #409eff; }
.note-wrap { margin-top: 18px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.note-actions { display: flex; gap: 8px; align-items: center; }
</style>
