<!--
  J1TabIpoTips.vue — IPO企业薪酬审计提示（只读注意事项）

  内容源：北京注册会计师协会专家委员会专家提示第5号——IPO企业职工薪酬的审计。
  纯提示/注意事项，结构化只读展示（舞弊动机 + 7大风险提示 + 关注重点 + 股份支付要点/案例 + 社保公积金）。
-->
<template>
  <div class="j1-ipo-tips">
    <!-- 标题与免责说明 -->
    <el-alert type="warning" :closable="false" show-icon class="tips-head">
      <template #title><span class="th-title">北京注册会计师协会专家委员会专家提示第5号 — IPO企业职工薪酬的审计</span></template>
      <div class="th-body">
        <p>职工薪酬作为重要的成本费用项目及舞弊操纵易发领域，是注册会计师在 IPO 审计中需特别关注的重点之一。</p>
        <p class="th-disclaimer">本提示仅供事务所及相关业务人员执行专项核查时参考，不能替代法律法规、执业准则及注册会计师个人的职业判断，不能直接照搬照抄。</p>
      </div>
    </el-alert>

    <!-- 一、舞弊动机和方法 -->
    <div class="amber-context">
      <div class="amber-title">一、职工薪酬的相关舞弊动机和方法</div>
      <p>考虑到动机不同，企业利用职工薪酬的舞弊可分为<strong>盈利操纵</strong>和<strong>税收操纵</strong>。IPO 审计重点以防范盈利操纵为主，税收操纵涉及对企业规范运作要求。可能存在的舞弊情形主要有：</p>
      <ol class="motive-list">
        <li><b>以侵占财产为目标：</b>如虚增人数冒领工资侵占企业资产等；</li>
        <li><b>以少缴个人所得税为目标：</b>如将工资费用化或虚增人数"化整为零"少缴个税等；</li>
        <li><b>以少缴企业所得税为目标：</b>如虚增人数虚增薪酬总额、将资本化薪酬费用化、自产产品福利分配不确认收入成本等；</li>
        <li><b>以盈利操纵为目标：</b>如随意改变薪酬标准、延迟或提前确认薪酬费用、利用员工性质分类操纵或通过关联方承担薪酬改变费用金额等。</li>
      </ol>
      <p class="motive-note">发现相关舞弊情形，除按审计准则实施进一步程序外，还应考虑其对内部控制有效性及规范运作的影响；涉及税收风险的，需考虑是否构成重大违法。</p>
    </div>

    <!-- 二、7大风险提示 -->
    <div class="section-title-row">二、IPO 审计中具体事项的风险提示</div>
    <el-collapse v-model="activeRisks" class="risk-collapse">
      <el-collapse-item v-for="(risk, idx) in risks" :key="idx" :name="String(idx)">
        <template #title>
          <span class="risk-tag">风险提示{{ risk.no }}</span>
          <span class="risk-title">{{ risk.title }}</span>
        </template>
        <p class="risk-desc" v-html="risk.desc"></p>
        <template v-if="risk.focus && risk.focus.length">
          <div class="focus-label">关注重点</div>
          <ol class="focus-list">
            <li v-for="(f, i) in risk.focus" :key="i" v-html="f"></li>
          </ol>
        </template>
        <template v-if="risk.blocks">
          <div v-for="(b, bi) in risk.blocks" :key="bi" class="sub-block">
            <div class="sub-title">{{ b.title }}</div>
            <ul class="sub-list"><li v-for="(x, xi) in b.items" :key="xi" v-html="x"></li></ul>
          </div>
        </template>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
defineProps<{ wpId?: string; projectId?: string; htmlData?: Record<string, unknown> | null }>()

import { ref } from 'vue'

const activeRisks = ref<string[]>(['0'])

const risks = [
  {
    no: '一', title: '随意改变薪酬标准',
    desc: '合理的薪酬制度和标准是企业核心竞争力的关键。若发现企业随意改变职工薪酬标准导致员工薪酬水平变化较大（如经营好时提取额外奖金福利、业绩不及预期时阶段性降薪），应充分关注其合理性及粉饰业绩的可能性。',
    focus: [
      '改变薪酬标准是否符合企业规定的决策程序？国有性质企业是否经相关主管部门批准？',
      '薪酬制度和标准是否合理、符合税法规定、是否存在劳动纠纷隐患？',
      '改变薪酬标准的目的，是否与盈利目的相关？',
      '结合经营状况和动机，关注是否可能存在其他盈利操纵行为。',
    ],
  },
  {
    no: '二', title: '薪酬水平异常偏低',
    desc: '企业薪酬水平一般应与规模、经营状况、行业或区域地位匹配。若人均水平远低于同行业/同地区在岗职工平均水平、核心人员薪酬异常偏低等，应充分关注是否存在经营、舞弊操纵及其他审计风险。',
    focus: [
      '企业实际经营状况是否正常、是否与财务报表显示的状况相背离？',
      '是否存在人为操纵职工薪酬水平虚增业绩的行为？',
      '是否存在通过股份支付等其他途径承担核心人员和高管薪酬的情形？',
      '是否存在上市后大幅提高员工福利导致业绩变脸的可能？',
    ],
  },
  {
    no: '三', title: '职工人数异常下降',
    desc: '正常经营的企业在技术、工艺、产品、经营环境无较大改变时，职工人数不会异常变动。若人数异常下降，需关注是否经营下滑或存在关联方承担职工薪酬的舞弊可能。',
    focus: [
      '通过实地核对主要部门岗位用人信息、核对"五险一金"和个税缴纳信息，核实人数改变的真实性；',
      '通过对人数改变原因、生产效率和人均产能的审查，判断人数改变是否合理、是否存在盈利能力造假风险；',
      '关注关联企业及未合并企业的职工人数与产能匹配性及盈利真实性；',
      '关注存在辞退福利计划的可能。',
    ],
  },
  {
    no: '四', title: '利用员工分类进行盈利操纵',
    desc: '企业按员工岗位专业化特点分类管理考核，而某些会计核算及税收优惠政策往往与员工分类相关，依据岗位性质对员工分类存在一定操控空间。审计时应针对性分析员工分类及变化的合理性，必要时实地核对岗位人员信息与会计记录的一致性。',
    focus: [
      '<b>混淆资本性支出与收益性支出：</b>人为调整基建工程和无形资产研发人员人数以调整当期费用；调整研发人员人数还可能虚报研发费用加计扣除的违规风险；',
      '<b>混淆生产成本与当期费用：</b>人为将应费用化的员工薪酬计入生产成本虚增当期利润，反之虚增毛利率、虚减利润；',
      '<b>违规享受税收优惠：</b>福利性生产企业加计扣除、降低所得税率等优惠与员工性质有关，企业可能操纵"四残"性质人数违规享受优惠。',
    ],
  },
  {
    no: '五', title: '对辞退福利的确认',
    desc: '辞退福利、股份支付等特殊会计事项，会计准则规定了相应条件，计量金额较大程度依赖会计估计。除判断确认的合理性外，还要关注是否可能存在盈利操纵。',
    focus: [
      '会计准则对辞退福利确认规定了两个严格限定条件；IPO 审计中为防止虚增利润，应重点关注<b>应确认未确认</b>的情形，以及存在相关迹象时是否存在其他经营风险；',
      '为防范人为操纵，准则规定"企业不可单方面撤回解除劳动关系计划或裁减建议"，实质是只有符合"预计经济利益流出可能性超过 50%"才能确认预计负债；企业可单方面否定则操纵空间较大；',
      '为防范随意确认补偿金额，非强制性辞退计划补偿金额的确定应以企业与有选择权的员工签署离职协议为准。',
    ],
  },
  {
    no: '六', title: '对股份支付的考虑',
    desc: 'IPO 审计中考虑股份支付处理原则时主要关注两点：① 是否符合会计准则及监管部门强调的适用原则；② 是否存在人为操纵盈利的行为。实务中把握<strong>"认定从严、排除从宽"</strong>原则。',
    blocks: [
      { title: '换取服务的情形（属股份支付）', items: [
        '发行人向高管或员工、或高管持股公司低价发行股份，或大股东及关联股东向高管/员工低价转让股份（股权激励）；',
        '向特定供应商低价发行股份换取服务、对第三方低价发行股份取得共同专利独家所有权等；',
        '股份支付与约定服务期无必然联系，对以前服务的奖励也可作为股份支付。',
      ] },
      { title: '不属于股份支付范畴的情形', items: [
        '虚拟股权计划申报前落实、对股权清晰规范解决代持；取消境外上市转回股权；',
        '继承、分割、赠与、亲属间转让（即使亲属在公司任职）；资产重组/业务整合中的补偿或股份安排；',
        '对全体股东配股或调节股东间利益；小股东转让股份给高管。',
      ] },
      { title: '对价的确定（公允价值）', items: [
        '正常情况下高管取得股份公允价值介于同期每股净资产与同期入股 PE 价格之间，也可能低于每股净资产（如房地产）；PE 需有一定量，价格不必然等于公允价值，需合理依据；',
        '无 PE 价格可用估值模型，评估价值可作参考；报告期前两年可放宽估值方法但须超过每股净资产；',
        '高管间接持有股份不能直接变现，公允价值与直接持股不同，可用估值模型确定。',
      ] },
      { title: '会计处理', items: [
        '审核重点在最近一年一期，以前期间执行较宽；',
        '证监会不鼓励分期摊销；约定服务期的行权后可分期摊销，但离职须与股份相关利益流入企业，否则一次摊销；',
        '偶发性股份支付形成的费用可作非经常性损益处理。',
      ] },
      { title: '案例参考', items: [
        '<b>案例一（公允价值确定）：</b>无 PE 价格按净资产评估值确认；PE 入股邻近的按 PE 价格；以评估净资产为基础参照 PE 价格调整。处理时点多为申报期最近一年，也有前二年处理的案例；',
        '<b>案例二（按合同期限摊销）：</b>大股东以每股1元转让100万股给员工、7月以3.80元转让给非企业人员，确认股份支付费用387.60万元，按员工工作合同期5年摊销。',
      ] },
    ],
  },
  {
    no: '七', title: '对社会保险和公积金规范性影响的关注',
    desc: '为员工及时足额缴纳社保和住房公积金是企业的法定责任和社会责任。IPO 审计针对社保公积金规范性问题应予关注。',
    blocks: [
      { title: '实际存在的问题', items: [
        '<b>只为部分员工缴纳：</b>员工非当地/城镇户籍占多数、流动性高、认识不足不愿缴纳，外地员工转移手续不完整；',
        '<b>只缴纳部分险种：</b>未缴基本医疗（员工参加新农合）、未缴住房公积金（农村居民不愿交）；',
        '<b>缴纳基数低于法定标准：</b>部分企业人均社保基数、公积金基数仅为人均工资的 30% 和 50%。',
      ] },
      { title: '相关监管部门参考原则', items: [
        '<b>总体原则：</b>缴纳规定尚不完善、各地操作不一，上市前可能存在不合规问题；不涉太大问题一般允许上市，但上市后必须按规定缴纳；',
        '<b>历史欠缴要求：</b>①说明原因；②取得社保部门确认文件；③实际控制人或主要股东承诺承担因欠缴可能的支出或损失；',
        '<b>披露要求：</b>披露母子公司办理社保/公积金员工人数、未缴人数及原因、缴纳比例、起始日期、是否需补缴及金额与对业绩影响；保荐机构和律师核查并对是否构成重大违法出具意见。',
      ] },
      { title: '审计可参考的处理原则', items: [
        '根据相关法规完整计算应补缴金额；',
        '考虑追缴是否导致不能满足报告期盈利指标要求（成长性、连续盈利或盈利总额等）；',
        '取得下述支持文件后可考虑不进行审计调整：社保公积金管理部门守法证明、实控人和大股东承担相关支出损失的承诺、律师关于欠缴不构成重大违法及不对发行构成实际障碍的法律意见。',
      ] },
    ],
  },
]
</script>

<style scoped>
.j1-ipo-tips { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.tips-head { margin-bottom: 12px; }
.th-title { font-weight: 600; }
.th-body { margin-top: 4px; line-height: 1.6; font-size: 12px; }
.th-body p { margin: 3px 0; }
.th-disclaimer { color: #b45309; font-style: italic; }
.amber-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 4px; margin-bottom: 14px; color: #78350f; line-height: 1.7; }
.amber-context .amber-title { font-weight: 700; color: #92400e; margin-bottom: 6px; font-size: 14px; }
.amber-context p { margin: 4px 0; }
.motive-list { margin: 6px 0; padding-left: 20px; line-height: 1.7; }
.motive-note { font-size: 12px; color: #92400e; margin-top: 6px; }
.section-title-row { font-weight: 700; font-size: 14px; color: #303133; margin: 6px 0 10px; padding-left: 8px; border-left: 4px solid #409eff; }
.risk-collapse { border: none; }
.risk-collapse :deep(.el-collapse-item__header) { font-size: 14px; height: 44px; line-height: 44px; }
.risk-tag { display: inline-flex; align-items: center; background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4; border-radius: 4px; padding: 1px 8px; font-size: 12px; font-weight: 600; margin-right: 10px; flex-shrink: 0; }
.risk-title { font-weight: 600; color: #303133; }
.risk-desc { line-height: 1.7; color: #4b5563; margin: 4px 0 10px; }
.focus-label { font-weight: 600; color: #409eff; margin: 6px 0 4px; font-size: 13px; }
.focus-list { margin: 0; padding-left: 20px; line-height: 1.75; color: #303133; }
.focus-list li { margin-bottom: 4px; }
.sub-block { margin-top: 12px; background: #f8fafc; border: 1px solid #eef2f7; border-radius: 5px; padding: 8px 12px; }
.sub-title { font-weight: 600; color: #334155; margin-bottom: 6px; font-size: 13px; }
.sub-list { margin: 0; padding-left: 20px; line-height: 1.7; color: #475569; }
.sub-list li { margin-bottom: 3px; }
</style>
