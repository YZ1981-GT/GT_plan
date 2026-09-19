<script setup lang="ts">
/**
 * F1DetailUsageGuide — F1-2 明细表使用手册弹窗
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
    title="F1-2 预付账款明细表 · 使用手册"
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
        title="一句话：Excel 模板是归档形态；本页按「阶段」编制，健康度找问题，全表留给复核。"
        class="mb12"
      />

      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li><b>①取数勾稽</b>：从余额表导入或手工录入债权人；填期初审定、借贷发生；先看「合计−TB」是否一致。</li>
          <li><b>②账龄风险</b>：填期末审定账龄；点健康度「&gt;1年待说明 / &gt;3年」筛出行，在备注写清原因与期后是否结清。</li>
          <li><b>③调整审定</b>：录入客户重分类、账项调整(AJE)、重分类调整(RJE)；核对期末审定。</li>
          <li><b>④证据落实</b>：标记发函、填期后结转；与 F1-7 勾稽（有缺口会黄条提示）。</li>
          <li><b>全表</b>：复核、对事务所 Excel 模板、或需要通览全部列时使用。</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>2. 界面控件说明</h3>
        <table class="guide-table">
          <thead>
            <tr><th>控件</th><th>作用</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>阶段切换（①～④ / 全表）</td>
              <td>只显示当前阶段常用列，减少横滑；切换不改动已填数据。</td>
            </tr>
            <tr>
              <td>⚙ 列设置</td>
              <td>在当前阶段内勾选显隐；偏好保存在本机浏览器，可「重置默认」。</td>
            </tr>
            <tr>
              <td>健康度标签</td>
              <td>一览勾稽与风险户数；点击标签会自动切换「风险筛选」。</td>
            </tr>
            <tr>
              <td>风险筛选 / 搜索</td>
              <td>按账龄异常、关联方、疑似重分类、期后缺口等缩小行范围。</td>
            </tr>
            <tr>
              <td>行内「风险」列</td>
              <td>当前行的快捷标签（账龄不符、&gt;3年、关联方等）。</td>
            </tr>
            <tr>
              <td>导入导出 ▾</td>
              <td>导出模板 / 导出数据 / 导入数据。始终为<strong>全量列</strong>，与当前阶段无关。</td>
            </tr>
            <tr>
              <td>从余额表导入</td>
              <td>批量生成明细行，再人工补账龄、调整与备注。</td>
            </tr>
            <tr>
              <td>灰色底纹列</td>
              <td>自动计算（H 期初审定、O 期末余额、Q 期末未审、T 期末审定），不可手工改。</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="guide-section">
        <h3>3. 健康度含义</h3>
        <ul>
          <li><b>合计−TB</b>：明细合计与试算平衡钩稽；不一致须先查漏户或漏数。</li>
          <li><b>账龄校验异常</b>：期末审定账龄各档之和 ≠ 期末审定数（允许极小尾差）。</li>
          <li><b>&gt;1年待说明</b>：审定账龄已超 1 年，但备注为空。</li>
          <li><b>&gt;3年</b>：存在 3 年以上审定账龄，须专项说明。</li>
          <li><b>疑似应重分类</b>：款项性质含工程/设备/固定资产/土地等，评估是否应列非流动资产。</li>
          <li><b>期后划转缺口</b>：F1-7 有期后贷方，但本表 Z 列为空。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>4. 审计说明与结论</h3>
        <ul>
          <li>说明区分变动分析、合同履约、超期未结转；可与 F1-1 / F1-5 / F1-6 交叉索引。</li>
          <li>结论可用模板：<b>A</b> 未见异常 · <b>B</b> 拟调整后未见异常 · <b>C</b> 无法确认。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>5. 小提示</h3>
        <ul>
          <li>阶段视图只影响「看见哪些列」，不会删数据；导出永远完整。</li>
          <li>复核同事若看不全列，切到「全表」或让其自行改列设置。</li>
          <li>关联方行淡黄底，账龄/风险行淡红底，便于扫视。</li>
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
