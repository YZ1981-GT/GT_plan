<template>
  <div v-if="visible" class="k1-four-table-source">
    <div class="src-bar">
      <span class="src-title">四表库取数口径</span>
      <el-tag size="small" type="info">报表行 {{ src.row_code || 'BS-009' }}</el-tag>
      <el-tag size="small" :type="grossTagType">原值 {{ resolvedFromLabel(src.resolved_from) }}</el-tag>
      <el-tag size="small" :type="provTagType">
        坏账准备 {{ resolvedFromLabel(src.provision_resolved_from) }}
      </el-tag>
      <el-tag v-if="src.use_provision_name_filter" size="small" type="warning">
        已叠加「其他应收款」名称过滤
      </el-tag>
      <el-button size="small" link type="primary" @click="expanded = !expanded">
        {{ expanded ? '收起明细' : '展开明细' }}
      </el-button>
    </div>

    <el-collapse-transition>
      <div v-show="expanded" class="src-detail">
        <el-table :data="rows" size="small" :show-header="true" class="src-table">
          <el-table-column prop="role" label="口径" width="150" />
          <el-table-column prop="standard" label="标准科目码（试算平衡表）" min-width="200" />
          <el-table-column prop="original" label="客户原始科目码（余额表）" min-width="220" />
        </el-table>
        <p v-if="formulaText" class="src-formula">
          报表公式：<code>{{ src.formula }}</code>
          <span class="src-sign">（符号：{{ formulaText }}）</span>
        </p>
        <ul class="src-hint">
          <li>
            坏账准备只取「其他应收款」对应的备抵子科目 —— 科目表把各类应收款的坏账分别编在
            <code>1231.01</code>（应收票据）/<code>1231.02</code>（应收账款）/
            <code>1231.03</code>（其他应收款）等，取整个 <code>1231</code> 会把应收账款的坏账并进来。
          </li>
          <li>余额表按<strong>叶子科目</strong>汇总（无下级明细的最末级），叶子之和等于父科目期末余额。</li>
          <li>应收利息 / 应收股利不计入本表第一段，单独用于「与经审计的财务报表核对」区。</li>
        </ul>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup lang="ts">
/**
 * K1 四表库取数溯源面板
 *
 * 消费 render 下发的 `tb_source_codes`（R1.7：不得成为 dead output）：
 * 让审计师能看到「报表行 → 标准码 → 客户原始码」这条链路究竟落在哪些科目上，
 * 以及是走了报表规则映射还是兜底 —— 审计 UI 必须有逻辑追溯能力。
 */
import { computed, ref } from 'vue'
import {
  hasK1TbSourceCodes,
  k1CodeListText,
  k1ExtraEntries,
  k1ResolvedFromLabel,
  k1ResolvedFromTagType,
  k1SignedFormulaText,
  type K1TbSourceCodes,
} from '../../composables/k1TbSourceCodes'

const props = defineProps<{
  sourceCodes?: K1TbSourceCodes | null
}>()

const expanded = ref(false)

const src = computed<K1TbSourceCodes>(() => props.sourceCodes || {})
const visible = computed(() => hasK1TbSourceCodes(props.sourceCodes))

const grossTagType = computed(() => k1ResolvedFromTagType(src.value.resolved_from))
const provTagType = computed(() => k1ResolvedFromTagType(src.value.provision_resolved_from))
const formulaText = computed(() => k1SignedFormulaText(src.value))

const resolvedFromLabel = k1ResolvedFromLabel

interface SrcRow {
  role: string
  standard: string
  original: string
}

const rows = computed<SrcRow[]>(() => {
  const out: SrcRow[] = [
    {
      role: '其他应收款原值',
      standard: k1CodeListText(src.value.gross_standard),
      original: k1CodeListText(src.value.gross),
    },
    {
      role: '坏账准备',
      standard: k1CodeListText(src.value.provision_standard),
      original: k1CodeListText(src.value.provision),
    },
  ]
  for (const e of k1ExtraEntries(src.value)) {
    out.push({
      role: e.label,
      standard: e.standard,
      original: k1CodeListText(e.originals),
    })
  }
  return out
})
</script>

<style scoped>
.k1-four-table-source {
  margin: 8px 0;
  font-size: 13px;
}

.src-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 10px;
  background: #f5f7fa;
  border-left: 3px solid var(--el-color-primary);
  border-radius: 2px;
}

.src-title {
  font-weight: 600;
  color: #303133;
}

.src-detail {
  padding: 8px 10px 4px;
  background: #fafcff;
  border: 1px solid #ebeef5;
  border-top: none;
}

.src-table {
  font-size: 13px;
}

.src-formula {
  margin: 8px 0 4px;
  color: #606266;
}

.src-formula code {
  background: #f0f2f5;
  padding: 1px 4px;
  border-radius: 2px;
}

.src-sign {
  margin-left: 6px;
  color: #909399;
}

.src-hint {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #8a6d3b;
  background: #fffbe6;
  border-left: 3px solid #faad14;
  padding: 6px 6px 6px 22px;
  line-height: 1.7;
}

.src-hint code {
  background: #fff3cd;
  padding: 0 3px;
}
</style>
