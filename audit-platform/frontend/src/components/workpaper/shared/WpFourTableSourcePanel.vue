<template>
  <div v-if="visible" class="wp-four-table-source">
    <div class="src-bar">
      <span class="src-title">四表库取数口径</span>
      <el-tag size="small" type="info">报表行 {{ src.row_code || fallbackRowCode }}</el-tag>
      <el-tag size="small" :type="grossTagType">
        {{ grossLabel }} {{ resolvedFromLabel(src.resolved_from) }}
      </el-tag>
      <el-tag v-if="showProvision" size="small" :type="provTagType">
        {{ provisionLabel }} {{ resolvedFromLabel(src.provision_resolved_from) }}
      </el-tag>
      <el-tag v-if="showProvision && src.use_provision_name_filter" size="small" type="warning">
        已叠加「{{ provisionFilterLabel }}」名称过滤
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
        <ul v-if="hints.length" class="src-hint">
          <!-- eslint-disable-next-line vue/no-v-html -- 提示文案来自各循环的编译期常量（无用户输入） -->
          <li v-for="(h, i) in hints" :key="i" v-html="h" />
        </ul>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup lang="ts">
/**
 * WpFourTableSourcePanel — 四表库取数溯源面板（跨循环共用）
 *
 * 消费各循环 render 下发的 `tb_source_codes`（不得成为 dead output）：
 * 让审计师看到「报表行 → 标准码 → 客户原始码」这条链路究竟落在哪些科目上，
 * 以及是走了报表规则映射还是兜底 —— 审计 UI 必须有逻辑追溯能力。
 *
 * 循环差异全部由 props 声明（原值/备抵中文名、附加科目名、提示文案、兜底报表行），
 * 组件内**不含任何循环专属常量**。首个消费者 = K1（`K1FourTableSourcePanel` 薄壳）、
 * K2（`K2FourTableSourcePanel` 薄壳）。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 2.1
 */
import { computed, ref } from 'vue'
import {
  hasTbSourceCodes,
  tbCodeListText,
  tbExtraEntries,
  tbResolvedFromLabel,
  tbResolvedFromTagType,
  tbSignedFormulaText,
  type TbSourceCodes,
} from '../composables/shared/tbSourceCodes'

const props = withDefaults(
  defineProps<{
    sourceCodes?: TbSourceCodes | null
    /** 原值口径中文名（如「其他应收款原值」/「其他流动资产原值」） */
    grossLabel: string
    /** 备抵口径中文名；不传（或该循环无备抵科目）则不显示备抵行与 tag */
    provisionLabel?: string
    /** 名称过滤 tag 里的科目名（默认取 `grossLabel`） */
    provisionFilterLabel?: string
    /** 附加科目标准码 → 中文名 */
    extraLabels?: Readonly<Record<string, string>>
    /** 口径说明（允许内嵌 `<code>`/`<strong>`，均为编译期常量） */
    hints?: readonly string[]
    /** 溯源未下发 row_code 时的展示兜底 */
    fallbackRowCode?: string
  }>(),
  {
    sourceCodes: null,
    provisionLabel: '',
    provisionFilterLabel: '',
    extraLabels: () => ({}),
    hints: () => [],
    fallbackRowCode: '',
  },
)

const expanded = ref(false)

const src = computed<TbSourceCodes>(() => props.sourceCodes || {})
const visible = computed(() => hasTbSourceCodes(props.sourceCodes))

/** 无备抵科目的循环（如 K2 其他流动资产）不显示备抵行 */
const showProvision = computed(() => !!props.provisionLabel)
const provisionFilterLabel = computed(() => props.provisionFilterLabel || props.grossLabel)

const grossTagType = computed(() => tbResolvedFromTagType(src.value.resolved_from))
const provTagType = computed(() => tbResolvedFromTagType(src.value.provision_resolved_from))
const formulaText = computed(() => tbSignedFormulaText(src.value))
const hints = computed(() => props.hints || [])

const resolvedFromLabel = tbResolvedFromLabel

interface SrcRow {
  role: string
  standard: string
  original: string
}

const rows = computed<SrcRow[]>(() => {
  const out: SrcRow[] = [
    {
      role: props.grossLabel,
      standard: tbCodeListText(src.value.gross_standard),
      original: tbCodeListText(src.value.gross),
    },
  ]
  if (showProvision.value) {
    out.push({
      role: props.provisionLabel,
      standard: tbCodeListText(src.value.provision_standard),
      original: tbCodeListText(src.value.provision),
    })
  }
  for (const e of tbExtraEntries(src.value, props.extraLabels)) {
    out.push({
      role: e.label,
      standard: e.standard,
      original: tbCodeListText(e.originals),
    })
  }
  return out
})
</script>

<style scoped>
.wp-four-table-source {
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

.src-hint :deep(code) {
  background: #fff3cd;
  padding: 0 3px;
}
</style>
