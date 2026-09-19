<template>
  <div class="bc-flow">
    <!-- 顶部决策引导 -->
    <div class="bc-flow-guide">
      <div class="bc-flow-guide-icon">🔍</div>
      <div class="bc-flow-guide-text">
        <strong>如何判定业务类型？</strong>
        按客户性质和业务风险从高到低判定：先看是否属于 A 类 → 不是再看是否属于 B 类 → 都不是则为 C 类
      </div>
    </div>

    <!-- 三列流程卡片 -->
    <div class="bc-flow-columns">
      <!-- A 类 -->
      <div class="bc-col bc-col-a" :class="{ active: selectedCategory === 'A' }" @click="$emit('select', 'type_a')">
        <div class="bc-col-head">
          <div class="bc-col-badge">A</div>
          <div class="bc-col-title">
            <div class="bc-col-name">A 类 · 最高质控</div>
            <div class="bc-col-sub">重大公众利益实体</div>
          </div>
        </div>
        <div class="bc-col-body">
          <div class="bc-col-items">
            <div v-for="sub in aItems" :key="sub.code" class="bc-item">
              <el-tooltip :content="sub.description" placement="right" :show-after="300">
                <span class="bc-item-text"><b>{{ sub.code }}</b> {{ sub.name }}</span>
              </el-tooltip>
            </div>
          </div>
        </div>
        <div class="bc-col-qc">
          <div class="bc-qc-label">质量控制程序 ▼</div>
          <div class="bc-qc-items">
            <div class="bc-qc-item bc-qc-item-critical">
              <el-tooltip content="专委会审批（A26）：涉及重大判断事项须提交专委会" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A26')">🏛 专委会</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item bc-qc-item-critical">
              <el-tooltip content="项目质量复核合伙人（A24）：独立于项目组的合伙人复核" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A24')">👁 质量复核</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item bc-qc-item-critical">
              <el-tooltip content="EQCR（A25）：独立复核员全面审阅" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A25')">🔒 EQCR</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item">
              <el-tooltip content="IT审计专家（A27）：评估信息系统控制" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A27')">💻 IT审计</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item">
              <el-tooltip content="税务专家（A28）：复杂税务事项咨询" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A28')">📑 税务专家</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item">
              <el-tooltip content="独立性全员签署（A17-7/7A）" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A17')">✍ 独立性声明</span>
              </el-tooltip>
            </div>
          </div>
          <div class="bc-qc-note">+ 全套 A 类专属底稿（A17系列/A24~A28）</div>
        </div>
      </div>

      <!-- 箭头 -->
      <div class="bc-arrow">
        <span class="bc-arrow-text">不属于 A →</span>
      </div>

      <!-- B 类 -->
      <div class="bc-col bc-col-b" :class="{ active: selectedCategory === 'B' }" @click="$emit('select', 'type_b')">
        <div class="bc-col-head">
          <div class="bc-col-badge">B</div>
          <div class="bc-col-title">
            <div class="bc-col-name">B 类 · 中等质控</div>
            <div class="bc-col-sub">其他公众利益实体/特殊行业</div>
          </div>
        </div>
        <div class="bc-col-body">
          <div class="bc-col-items">
            <div v-for="sub in bItems" :key="sub.code" class="bc-item">
              <el-tooltip :content="sub.description" placement="right" :show-after="300">
                <span class="bc-item-text"><b>{{ sub.code }}</b> {{ sub.name }}</span>
              </el-tooltip>
            </div>
          </div>
        </div>
        <div class="bc-col-qc">
          <div class="bc-qc-label">质量控制程序 ▼</div>
          <div class="bc-qc-items">
            <div class="bc-qc-item bc-qc-item-critical">
              <el-tooltip content="EQCR 技术质控复核（视风险评估决定是否需要）" placement="top">
                <span class="bc-qc-chip" @click.stop="$emit('jump', 'A25')">🔒 EQCR技术质控复核（视风险）</span>
              </el-tooltip>
            </div>
            <div class="bc-qc-item">
              <span class="bc-qc-chip bc-qc-chip-normal">📋 三级复核（A21→A22→A23）</span>
            </div>
            <div class="bc-qc-item">
              <span class="bc-qc-chip bc-qc-chip-normal">✍ 独立性声明</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 箭头 -->
      <div class="bc-arrow">
        <span class="bc-arrow-text">不属于 B →</span>
      </div>

      <!-- C 类 -->
      <div class="bc-col bc-col-c" :class="{ active: selectedCategory === 'C' }" @click="$emit('select', 'type_c')">
        <div class="bc-col-head">
          <div class="bc-col-badge">C</div>
          <div class="bc-col-title">
            <div class="bc-col-name">C 类 · 标准质控</div>
            <div class="bc-col-sub">一般审计业务</div>
          </div>
        </div>
        <div class="bc-col-body">
          <div class="bc-col-items">
            <div class="bc-item"><span class="bc-item-text">不属于 A 类或 B 类的所有鉴证业务</span></div>
            <div class="bc-item"><span class="bc-item-text">一般企业年度审计</span></div>
            <div class="bc-item"><span class="bc-item-text">专项审计/验资/内控审计</span></div>
            <div class="bc-item"><span class="bc-item-text">小型企业审计</span></div>
          </div>
        </div>
        <div class="bc-col-qc">
          <div class="bc-qc-label">质量控制程序 ▼</div>
          <div class="bc-qc-items">
            <div class="bc-qc-item">
              <span class="bc-qc-chip bc-qc-chip-normal">📋 三级复核（A21→A22→A23）</span>
            </div>
            <div class="bc-qc-item">
              <span class="bc-qc-chip bc-qc-chip-normal">✍ 独立性声明</span>
            </div>
          </div>
          <div class="bc-qc-note">无需专委会/EQCR/IT审计专家</div>
        </div>
      </div>
    </div>

    <!-- 底部反洗钱提示 -->
    <div class="bc-flow-footer">
      <el-tooltip placement="top">
        <template #content>
          <div style="max-width: 360px; line-height: 1.6">
            <b>反洗钱合规要求（全部类型适用）</b><br/>
            • 首次承接/高风险客户须做反洗钱调查<br/>
            • 查询"中国反洗钱监测分析中心"是否命中<br/>
            • 涉及PEP（政治公众人物）须升级尽调<br/>
            • 保留客户身份识别资料≥5年
          </div>
        </template>
        <div class="bc-footer-badge">
          <span>⚠️ 反洗钱合规</span>
          <span class="bc-footer-note">全部类型适用 · 悬停查看详情</span>
        </div>
      </el-tooltip>

      <div class="bc-footer-source">
        分类依据：致同《鉴证业务分类及事务所层面质量控制程序一览表》2025年12月修订
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  selectedCategory?: string
}>()

defineEmits<{
  (e: 'select', value: string): void
  (e: 'jump', wpCode: string): void
}>()

const aItems = [
  { code: 'A1', name: '境内外上市公司', description: '境内、境外（含H股）上市公司审计' },
  { code: 'A2', name: '新三板/退市/股东超200人', description: '全国中小企业股份转让系统业务（挂牌、年审、融资、被收购；退市公司）；股东超过200人的公众公司' },
  { code: 'A3', name: '重大资产重组', description: '需经中国证监会核准或交易场所审核的重大资产重组业务，非本所上市公司客户涉及重大资产重组业绩承诺完成情况' },
  { code: 'A4', name: '超大型企业/央企', description: '营业收入超350亿元或资产总额超700亿元的审计业务；中央企业集团公司；其他受独立监管机构监管的企业' },
  { code: 'A5', name: '复杂金融业务', description: '复杂的金融业务（银行、保险公司）' },
  { code: 'A6', name: 'IPO（含境外）', description: 'IPO业务是指以最近年度终了为基准日申报或未来12个月内拟申报业务（含境外IPO）' },
  { code: 'A7', name: '信用类债券', description: '发行企业债券、公司债券以及非金融企业债务融资工具（面向公众投资者和专业投资者）' },
  { code: 'A8', name: '证券/期货/公募/REITs', description: '证券公司，证券交易所、期货交易所、公募基金管理公司及其管理的基金、REITs业务' },
]

const bItems = [
  { code: 'B1', name: '重要国际业务', description: '重要的国际业务；非本所境内上市公司客户重要子公司（含海外子公司）且其审计工作被集团审计师利用的财务报表审计' },
  { code: 'B2', name: '其他金融企业', description: '期货公司、黄金交易所、商品交易所等类似交易平台；其他金融企业（除A5，受国家金融监督管理总局监管）；互联网借贷信息中介机构' },
  { code: 'B3', name: '股东大会审议的并购', description: '按公司章程规定需经上市公司、新三板公司股东大会审议的资产重组或并购业务（不包括仅因关联交易的情形）' },
  { code: 'B4', name: '大型企业（收入超200亿）', description: '营业收入超200亿元或资产总额超350亿元的审计业务' },
  { code: 'B5', name: '资产证券化/资管/理财', description: '资产支持证券（发行、存续期、清算）；投资于公开证券市场的私募基金；资产管理计划；理财产品和集合信托' },
  { code: 'B6', name: '拟IPO改制/股交中心', description: '拟IPO、新三板挂牌的股份制改制审计业务；区域性股权交易市场（股交中心）业务（挂牌、年审、融资）' },
]
</script>

<style scoped>
.bc-flow { display: flex; flex-direction: column; gap: 16px; }

/* 顶部引导 */
.bc-flow-guide {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f0e9f9 0%, #faf8fd 100%);
  border: 1px solid var(--gt-purple-border, #e5d5f5);
  border-radius: 10px;
}
.bc-flow-guide-icon { font-size: 24px; }
.bc-flow-guide-text { font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; }

/* 三列布局 */
.bc-flow-columns {
  display: flex;
  align-items: stretch;
  gap: 0;
}

.bc-col {
  flex: 1;
  border: 2px solid var(--el-border-color-lighter);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s;
  cursor: pointer;
  display: flex;
  flex-direction: column;
}
.bc-col:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
.bc-col.active { border-color: var(--gt-purple, #4b2d77); box-shadow: 0 0 0 3px rgba(75,45,119,0.15); }

.bc-col-a .bc-col-head { background: linear-gradient(135deg, #fde8e8, #fdf2f2); }
.bc-col-b .bc-col-head { background: linear-gradient(135deg, #fef3e2, #fef9f0); }
.bc-col-c .bc-col-head { background: linear-gradient(135deg, #f0f2f5, #f8f9fa); }

.bc-col-head {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px;
}
.bc-col-badge {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 16px; color: #fff;
}
.bc-col-a .bc-col-badge { background: #dc3545; }
.bc-col-b .bc-col-badge { background: #f59e0b; }
.bc-col-c .bc-col-badge { background: #6b7280; }

.bc-col-name { font-weight: 700; font-size: 14px; color: var(--el-text-color-primary); }
.bc-col-sub { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 2px; }

.bc-col-body { padding: 12px 16px; flex: 1; }
.bc-col-items { display: flex; flex-direction: column; gap: 4px; }
.bc-item { font-size: 12px; padding: 3px 0; }
.bc-item-text { cursor: help; }
.bc-item-text b { color: var(--gt-purple, #4b2d77); margin-right: 4px; }

/* 质控程序区 */
.bc-col-qc {
  padding: 12px 16px;
  border-top: 1px dashed var(--el-border-color-lighter);
  background: #fafbfc;
}
.bc-qc-label { font-size: 11px; font-weight: 600; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.bc-qc-items { display: flex; flex-wrap: wrap; gap: 6px; }
.bc-qc-chip {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 3px 8px; border-radius: 4px;
  font-size: 11px; cursor: pointer;
  background: #fff; border: 1px solid var(--el-border-color);
  transition: all 0.15s;
}
.bc-qc-chip:hover { border-color: var(--gt-purple); color: var(--gt-purple); background: var(--gt-purple-light, #f4f0fa); }
.bc-qc-item-critical .bc-qc-chip { border-color: #dc3545; color: #dc3545; font-weight: 600; }
.bc-qc-item-critical .bc-qc-chip:hover { background: #fde8e8; }
.bc-qc-chip-normal { cursor: default; color: var(--el-text-color-secondary); }
.bc-qc-chip-normal:hover { border-color: var(--el-border-color); color: var(--el-text-color-secondary); background: #fff; }
.bc-qc-note { font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 8px; }

/* 箭头 */
.bc-arrow {
  display: flex; align-items: center; justify-content: center;
  width: 36px; flex-shrink: 0;
}
.bc-arrow-text {
  writing-mode: vertical-rl;
  font-size: 11px; color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

/* 底部 */
.bc-flow-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 8px; }
.bc-footer-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  background: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px;
  font-size: 13px; cursor: help;
}
.bc-footer-note { font-size: 11px; color: #d48806; }
.bc-footer-source { font-size: 11px; color: var(--el-text-color-placeholder); text-align: right; }
</style>
