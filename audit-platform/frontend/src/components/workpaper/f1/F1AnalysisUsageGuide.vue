<script setup lang="ts">
/**
 * F1AnalysisUsageGuide — F1-4 实质性分析使用手册
 */
defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

function close(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-4 实质性分析 · 使用手册"
    width="720px"
    top="6vh"
    destroy-on-close
    append-to-body
    class="f1-usage-guide-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="guide-body">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        title="一句话：本表做分析性复核——总量同比 → 性质结构 → 经营比率 → 大额到户 → 说明结论。"
        class="mb12"
      />

      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li><b>余额分析</b>：按存货/费用/工程/其他填本期、上期；填存货余额；看占比是否异常。</li>
          <li><b>借方发生额</b>：分析新增预付结构，对照存货采购额看比率。</li>
          <li><b>贷方发生额</b>：看结转路径；大额「收回款项」须说明是否资金占用。</li>
          <li><b>大额供应商</b>：可「从 F1-2 取大额」；补账龄（与 F1-1 枚举一致）、原因、期后到货。</li>
          <li><b>分块说明 + 审计结论</b>：每表后写说明；结论可用 A/B/C 模板，支持 AI 草拟后二次编辑。</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>2. 公式与灰底列</h3>
        <ul>
          <li>变动金额 = 本期 − 上期；变动比例 = 变动额 / |上期|（上期为 0 时显示 N/A）。</li>
          <li>汇总行（预付账款余额/借贷发生额合计）= 各性质行自动相加，不可改。</li>
          <li>比率行自动计算；分母为 0 时显示 #DIV/0!。</li>
          <li>大额表：期末 = 期初 + 借方 − 贷方；账面价值 = 期末 − 坏账准备。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>3. 与其他底稿关系</h3>
        <table class="guide-table">
          <thead>
            <tr><th>关联</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr><td>F1-2 明细</td><td>大额供应商取数、户余额勾稽；集中度超 50% 会黄条提示。</td></tr>
            <tr><td>F1-1 审定</td><td>变动原因可由本表说明支撑；账龄枚举与审定表口径一致。</td></tr>
            <tr><td>F1-5 / F1-6</td><td>超期、关联疑点从本表大额分析进一步下沉检查。</td></tr>
            <tr><td>存货/采购</td><td>余额与借方分析的对照行，用于经营合理性锚点。</td></tr>
          </tbody>
        </table>
      </section>

      <section class="guide-section">
        <h3>4. 导入导出</h3>
        <ul>
          <li>导出模板 / 导出数据 / 导入数据：工作簿含「大额供应商」及余额/借贷结构表（如有）。</li>
          <li>导入以覆盖方式写入本表数据包，导入后请复核比率与说明。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>5. 小提示</h3>
        <ul>
          <li>字号固定 13，便于对所模板。</li>
          <li>AI 生成写入后仍可直接改字并保存。</li>
          <li>变动比例超 30% 的行会标红，便于扫视异常。</li>
        </ul>
      </section>
    </div>

    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.guide-body {
  max-height: min(68vh, 640px);
  overflow-y: auto;
  padding-right: 4px;
  font-size: 13px;
  color: #303133;
  line-height: 1.65;
}
.mb12 { margin-bottom: 12px; }
.guide-section { margin-bottom: 16px; }
.guide-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1d39c4;
  border-left: 3px solid #409eff;
  padding-left: 8px;
}
.guide-section ol,
.guide-section ul {
  margin: 0;
  padding-left: 1.35em;
}
.guide-section li { margin: 4px 0; }
.guide-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.guide-table th,
.guide-table td {
  border: 1px solid #ebeef5;
  padding: 6px 8px;
  vertical-align: top;
  text-align: left;
}
.guide-table th {
  background: #f5f7fa;
  font-weight: 600;
  width: 28%;
}
</style>
