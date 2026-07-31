<template>
  <div class="h3-disc-listed">

    <!-- ① 顶部信息栏 -->
    <div class="header-bar">
      <div class="header-main">
        <span class="header-title">致同会计师事务所 — 附注披露信息（上市公司）</span>
        <span class="header-note">投资性房地产（CAS33）</span>
      </div>
      <div class="mode-badge" :class="measurementModel === 'cost' ? 'mode-cost' : 'mode-fair'">
        {{ measurementModel === 'cost' ? '成本模式' : '公允价值模式' }}
      </div>
      <div class="header-actions" style="display:flex;gap:8px;margin-left:auto">
        <el-button size="small" type="success" :loading="syncLoading" :disabled="isReadonly" @click="syncToDisclosureNotes">
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain @click="jumpToNote">
          ↩ 跳转回附注（五、21）
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="obj-alert"
      title="审计目标：核实投资性房地产附注披露（CAS33）的完整与准确；成本模式与公允价值模式互斥，不适用的表格自动省略（不需要生成）。"
    />

    <!-- ② 勾稽差异警告 -->
    <el-alert
      v-if="crossCheckWarnings.length"
      type="warning"
      :closable="false"
      class="cross-warn"
    >
      <ul class="warn-list">
        <li v-for="w in crossCheckWarnings" :key="w">{{ w }}</li>
      </ul>
    </el-alert>

    <!-- ③ 模式说明条 -->
    <div class="mode-bar">
      <span class="mode-label">当前编制模式：</span>
      <span>{{ measurementModel === 'cost'
        ? '成本法 — 生成：账面原值变动表 / 累计折旧摊销表 / 减值准备表；公允价值相关表格自动省略。'
        : '公允价值法 — 生成：公允价值变动表；成本法三张表自动省略。' }}</span>
    </div>

    <!-- ④ 主体：按计量模式渲染对应披露块 -->

    <!-- === 成本模式 === -->
    <template v-if="measurementModel === 'cost'">

      <!-- 账面原值 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（1）账面原值</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('cost-original')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('cost-original')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期初余额</th>
              <th class="col-num">本期增加金额</th>
              <th class="col-num">本期减少金额</th>
              <th class="col-num formula-th">期末余额</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('cost-original')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('cost-original', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-original', row)" /></td>
              <td><el-input v-model.number="row.increase" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-original', row)" /></td>
              <td><el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-original', row)" /></td>
              <td class="formula-cell">{{ fmtNum(row.beginBalance + row.increase - row.decrease) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('cost-original', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('cost-original', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('cost-original', 'increase')) }}</td>
              <td>{{ fmtNum(sumCol('cost-original', 'decrease')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-original', 'beginBalance') + sumCol('cost-original', 'increase') - sumCol('cost-original', 'decrease')) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['cost-original']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明本期增加/减少的主要原因（如外购、自用转入、在建工程转入、处置等）" :disabled="isReadonly"
            @change="onTextChange('cost-original')" />
        </div>
      </div>

      <!-- 累计折旧和累计摊销 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（2）累计折旧和累计摊销</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('cost-dep')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('cost-dep')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期初余额</th>
              <th class="col-num">本期增加</th>
              <th class="col-num">本期减少</th>
              <th class="col-num formula-th">期末余额</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('cost-dep')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('cost-dep', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-dep', row)" /></td>
              <td><el-input v-model.number="row.increase" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-dep', row)" /></td>
              <td><el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-dep', row)" /></td>
              <td class="formula-cell">{{ fmtNum(row.beginBalance + row.increase - row.decrease) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('cost-dep', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('cost-dep', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('cost-dep', 'increase')) }}</td>
              <td>{{ fmtNum(sumCol('cost-dep', 'decrease')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-dep', 'beginBalance') + sumCol('cost-dep', 'increase') - sumCol('cost-dep', 'decrease')) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['cost-dep']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明本期折旧/摊销政策、折旧方法、使用年限等" :disabled="isReadonly"
            @change="onTextChange('cost-dep')" />
        </div>
      </div>

      <!-- 减值准备 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（3）减值准备</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('cost-impair')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('cost-impair')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期初余额</th>
              <th class="col-num">本期计提</th>
              <th class="col-num">本期转回/转出</th>
              <th class="col-num formula-th">期末余额</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('cost-impair')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('cost-impair', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-impair', row)" /></td>
              <td><el-input v-model.number="row.increase" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-impair', row)" /></td>
              <td><el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('cost-impair', row)" /></td>
              <td class="formula-cell">{{ fmtNum(row.beginBalance + row.increase - row.decrease) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('cost-impair', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('cost-impair', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('cost-impair', 'increase')) }}</td>
              <td>{{ fmtNum(sumCol('cost-impair', 'decrease')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-impair', 'beginBalance') + sumCol('cost-impair', 'increase') - sumCol('cost-impair', 'decrease')) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['cost-impair']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明本期减值测试情况；如无减值，请在文字框注明。" :disabled="isReadonly"
            @change="onTextChange('cost-impair')" />
        </div>
      </div>

      <!-- 账面价值 = 原值 - 折旧 - 减值（自动汇总展示） -->
      <div class="disc-block summary-block">
        <div class="block-header">
          <span class="block-title">（4）账面价值汇总</span>
          <span class="auto-badge">自动计算</span>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期末账面价值</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>账面原值</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-original', 'beginBalance') + sumCol('cost-original', 'increase') - sumCol('cost-original', 'decrease')) }}</td>
            </tr>
            <tr>
              <td>减：累计折旧和摊销</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-dep', 'beginBalance') + sumCol('cost-dep', 'increase') - sumCol('cost-dep', 'decrease')) }}</td>
            </tr>
            <tr>
              <td>减：减值准备</td>
              <td class="formula-cell">{{ fmtNum(sumCol('cost-impair', 'beginBalance') + sumCol('cost-impair', 'increase') - sumCol('cost-impair', 'decrease')) }}</td>
            </tr>
            <tr class="total-row">
              <td>账面净值</td>
              <td class="formula-cell" :class="{ 'diff-warn': netValueDiff !== 0 }">
                {{ fmtNum(computedNetValue) }}
                <span v-if="netValueDiff !== 0" class="diff-tip">（与 H3-1 差异：{{ fmtNum(netValueDiff) }}）</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

    </template>

    <!-- === 公允价值模式 === -->
    <template v-else>

      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（1）采用公允价值计量的投资性房地产</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('fair-change')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('fair-change')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期初公允价值</th>
              <th class="col-num">本期增加</th>
              <th class="col-num">本期减少</th>
              <th class="col-num">公允价值变动</th>
              <th class="col-num formula-th">期末公允价值</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('fair-change')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('fair-change', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('fair-change', row)" /></td>
              <td><el-input v-model.number="row.increase" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('fair-change', row)" /></td>
              <td><el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('fair-change', row)" /></td>
              <td><el-input v-model.number="(row as any).fairChange" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('fair-change', row)" /></td>
              <td class="formula-cell">{{ fmtNum(row.beginBalance + row.increase - row.decrease + ((row as any).fairChange || 0)) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('fair-change', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('fair-change', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('fair-change', 'increase')) }}</td>
              <td>{{ fmtNum(sumCol('fair-change', 'decrease')) }}</td>
              <td>{{ fmtNum(sumFairChange()) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('fair-change', 'beginBalance') + sumCol('fair-change', 'increase') - sumCol('fair-change', 'decrease') + sumFairChange()) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['fair-change']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明公允价值确定依据、评估机构、评估方法及关键假设。" :disabled="isReadonly"
            @change="onTextChange('fair-change')" />
        </div>
      </div>

      <!-- （2）公允价值层次披露（CAS39） -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（2）公允价值层次、估值技术及关键输入值（CAS39）</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="onImportFvFromH38">从 H3-8 带入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addFvHierarchyRow()">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('fair-hierarchy')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-lvl">公允价值层次</th>
              <th class="col-num">期末公允价值</th>
              <th class="col-tech">估值技术</th>
              <th class="col-tech">关键输入值</th>
              <th class="col-obs">输入值可观察</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in fvHierarchyRows" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateFvHierarchyRow(idx)" /></td>
              <td>
                <el-select v-model="row.level" size="small" :disabled="isReadonly" @change="updateFvHierarchyRow(idx)">
                  <el-option label="第一层次" value="1" />
                  <el-option label="第二层次" value="2" />
                  <el-option label="第三层次" value="3" />
                </el-select>
              </td>
              <td><el-input v-model.number="row.fairValue" size="small" :disabled="isReadonly" class="num-input" @change="updateFvHierarchyRow(idx)" /></td>
              <td>
                <el-select v-model="row.valuationTechnique" size="small" filterable allow-create default-first-option :disabled="isReadonly" @change="updateFvHierarchyRow(idx)">
                  <el-option label="市场法" value="市场法" />
                  <el-option label="收益法" value="收益法" />
                  <el-option label="成本法" value="成本法" />
                </el-select>
              </td>
              <td><el-input v-model="row.keyInputs" size="small" :disabled="isReadonly" placeholder="如市场租金/折现率/资本化率" @change="updateFvHierarchyRow(idx)" /></td>
              <td>
                <el-select v-model="row.isObservable" size="small" :disabled="isReadonly" @change="updateFvHierarchyRow(idx)">
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
              </td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeFvHierarchyRow(row.rowId)">删除</el-button></td>
            </tr>
            <tr v-if="!fvHierarchyRows.length" class="data-row">
              <td colspan="7" class="empty-tip">暂无公允价值层次数据，可「从 H3-8 带入」或「＋ 插行」。第三层次（不可观察输入）须披露估值技术与关键输入值。</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>第一层次合计</td>
              <td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level1) }}</td>
              <td colspan="3"></td>
              <td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>第二层次合计</td>
              <td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level2) }}</td>
              <td colspan="3"></td>
              <td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>第三层次合计</td>
              <td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level3) }}</td>
              <td colspan="3"></td>
              <td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>合 计</td>
              <td></td>
              <td class="formula-cell" :class="{ 'diff-warn': fvHierarchyDiff !== 0 }">
                {{ fmtNum(fvHierarchyTotalsByLevel.total) }}
                <span v-if="fvHierarchyDiff !== 0" class="diff-tip">（与公允价值变动表期末差异：{{ fmtNum(fvHierarchyDiff) }}）</span>
              </td>
              <td colspan="3"></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['fair-hierarchy']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="披露：公允价值层次的确定依据；第三层次采用的估值技术及关键不可观察输入值（如市场租金、折现率、资本化率）；层次间转换情况及原因。" :disabled="isReadonly"
            @change="onTextChange('fair-hierarchy')" />
        </div>
      </div>

    </template>

    <!-- （3）未办妥产权证书的情况（源模板 A65~A68；此前底稿无行录入位置 → 该附注表永远无法推送） -->
    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">（3）未办妥产权证书的情况</span>
        <div class="block-actions">
          <el-button v-if="!isReadonly" size="small" @click="addRow('title-cert')">＋ 插行</el-button>
        </div>
      </div>
      <div class="src-hint">
        <p>（披露未办妥产权证书的投资性房地产账面价值及原因。）行可无限量添加。</p>
      </div>
      <table class="disc-table">
        <thead>
          <tr>
            <th class="col-item">项 目</th>
            <th class="col-num">账面价值</th>
            <th style="min-width:200px">未办妥产权证书原因</th>
            <th v-if="!isReadonly" class="col-op"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in getSectionRows('title-cert')" :key="row.rowId" class="data-row">
            <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('title-cert', row)" /></td>
            <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('title-cert', row)" /></td>
            <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="请填写原因" @change="onRowChange('title-cert', row)" /></td>
            <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('title-cert', row.rowId)">删除</el-button></td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="total-row">
            <td>合 计</td>
            <td class="formula-cell">{{ fmtNum(sumCol('title-cert', 'beginBalance')) }}</td>
            <td></td>
            <td v-if="!isReadonly"></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- ⑤ 共用块：补充说明 / 受限及担保 -->
    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">补充说明</span>
        <el-button size="small" plain @click="generateAI('measurement-basis')">AI</el-button>
      </div>
      <el-input v-model="sectionTexts['measurement-basis']" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :placeholder="measurementModel === 'cost'
          ? '描述成本模式后续计量政策、折旧方法、残值率、使用年限，以及报告期内是否发生计量模式转换。'
          : '描述公允价值模式选择原因、确定依据（评估机构/方法/关键假设），以及报告期内是否发生计量模式转换。'"
        :disabled="isReadonly"
        @change="onTextChange('measurement-basis')" />
    </div>

    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">受限及担保情况</span>
        <el-button size="small" plain @click="generateAI('restriction')">AI</el-button>
      </div>
      <el-input v-model="sectionTexts['restriction']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="说明抵押给金融机构的投资性房地产账面价值、未办妥产权证书情况及原因，以及其他使用限制。"
        :disabled="isReadonly"
        @change="onTextChange('restriction')" />
    </div>

    <!-- （4）房地产转换情况及改变计量模式的情况（源模板 A71~A74，此前底稿无录入位置） -->
    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">（4）房地产转换情况及改变计量模式的情况</span>
        <el-button size="small" plain :loading="_h3AiLoading" :disabled="isReadonly"
          @click="generateAI('conversion')">🤖 AI</el-button>
      </div>
      <div class="src-hint">
        <p>（说明报告期内房地产转换或改变计量模式的情况、理由，以及对损益或所有者权益的影响。</p>
        <p>对于转换为投资性房地产并采用公允价值计量模式的，应披露转换的理由、审批程序，以及对损益、其他综合收益的影响。（15号文第十九条（十二））</p>
        <p>房地产开发企业列示出租开发产品时，应披露出租开发产品的成本、租赁合同主要条款等内容。对重要的出租房产应单项披露，非重要或零星的出租房产可采用合并披露。）</p>
      </div>
      <el-input v-model="sectionTexts['conversion']" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="按源模板口径说明：①报告期内房地产转换或改变计量模式的情况、理由及对损益/所有者权益的影响；②转换为投资性房地产并采用公允价值计量模式的，披露理由、审批程序及对损益、其他综合收益的影响；③房地产开发企业出租开发产品的成本、租赁合同主要条款。"
        :disabled="isReadonly"
        @change="onTextChange('conversion')" />
    </div>

    <!-- ⑥ 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示 / 检查清单</summary>
      <ul>
        <li>上市公司附注按 CAS33 格式披露；计量模式互斥，已采用模式对应表格自动生成，另一模式自动省略。</li>
        <li>成本模式：账面原值变动、累计折旧/摊销、减值准备三表均须完整。可按房屋建筑物、土地使用权及实际项目继续插行。</li>
        <li>公允价值模式：仅生成公允价值变动表；需披露公允价值确定依据、评估机构及方法。</li>
        <li>各表"期末余额"自动计算（期初＋增加−减少），无需手填；账面净值差异警告（与 H3-1 审定数对比）自动显示。</li>
        <li>长期资产本期进行减值测试的，应披露可收回金额确定方法、关键参数及其确定依据。</li>
      </ul>
    </details>

  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDisclosureListed.vue — 附注披露（上市公司版）
 * 模板化表格块 + 计量模式二选一 + 无限插行/删行 + 勾稽差异高亮
 */
import { ref, computed, inject, toRef, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useH3Disclosure } from '../../composables/useH3Disclosure'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3CrossSheet } from '../../composables/useH3CrossSheet'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { buildH3SyncPayload, H3_NOTE_SECTION } from '../../composables/h3NoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'
import { useAuditContext } from '@/composables/useAuditContext'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const { year: auditYear } = useAuditContext()

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: toRef(props, 'measurementModel') as any,
})

const crossSheet = useH3CrossSheet(
  computed(() => props.allResponses) as any,
  toRef(props, 'measurementModel') as any,
)

const {
  sectionTexts, updateText, getSectionRows, addSectionRow, removeSectionRow, updateRow,
  fvHierarchyRows, fvHierarchyTotalsByLevel,
  addFvHierarchyRow, removeFvHierarchyRow, updateFvHierarchyRow, importFvHierarchyFromH38,
} = useH3Disclosure({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
  measurementModel: toRef(props, 'measurementModel') as any,
  variant: ref('listed') as any,
  disclosureAutoFill: crossSheet.disclosureAutoFill,
})

function onImportFvFromH38() {
  const r = importFvHierarchyFromH38()
  ElMessage[r.added ? 'success' : 'info'](r.message)
}

// ─── 发布文本更新事件 ─────────────────────────────────────────────────────────
function publishNoteTextUpdated(key: string) {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'H3',
    section: key,
    accountCode: '1503',
    projectId: props.projectId,
    sectionIds: ['投资性房地产', '五、21', '八、22'],
    timestamp: Date.now(),
  })
}

// ─── 行级操作 ────────────────────────────────────────────────────────────────
function onRowChange(key: string, row: any) { updateRow(key, row) }
function onTextChange(key: string) {
  updateText(key, sectionTexts[key])
  publishNoteTextUpdated(key)
}
function addRow(key: string) { addSectionRow(key, { category: '' }) }
function removeRow(key: string, rowId: string) { removeSectionRow(key, rowId) }

// ─── 数值计算 ────────────────────────────────────────────────────────────────
function sumCol(key: string, field: 'beginBalance' | 'increase' | 'decrease'): number {
  return getSectionRows(key).reduce((s, r) => s + (Number(r[field]) || 0), 0)
}
function sumFairChange(): number {
  return getSectionRows('fair-change').reduce((s, r) => s + (Number((r as any).fairChange) || 0), 0)
}

// 公允价值层次合计 vs 公允价值变动表期末合计 勾稽
const fvHierarchyDiff = computed(() => {
  if (props.measurementModel !== 'fair_value') return 0
  const fairEnd = sumCol('fair-change', 'beginBalance') + sumCol('fair-change', 'increase') - sumCol('fair-change', 'decrease') + sumFairChange()
  const hierarchyTotal = fvHierarchyTotalsByLevel.value.total
  if (fairEnd === 0 && hierarchyTotal === 0) return 0
  return Math.abs(hierarchyTotal - fairEnd) > 0.005 ? hierarchyTotal - fairEnd : 0
})

// 账面净值 = 原值期末 - 折旧期末 - 减值期末
const computedNetValue = computed(() => {
  const origEnd = sumCol('cost-original', 'beginBalance') + sumCol('cost-original', 'increase') - sumCol('cost-original', 'decrease')
  const depEnd  = sumCol('cost-dep', 'beginBalance')      + sumCol('cost-dep', 'increase')      - sumCol('cost-dep', 'decrease')
  const impEnd  = sumCol('cost-impair', 'beginBalance')   + sumCol('cost-impair', 'increase')   - sumCol('cost-impair', 'decrease')
  return origEnd - depEnd - impEnd
})

// 与 H3 跨表净值比对
const h3NetValue = computed(() => {
  const t = crossSheet.detailTotals.value
  return t ? t.netValue : 0
})
const netValueDiff = computed(() => {
  if (props.measurementModel !== 'cost') return 0
  return computedNetValue.value - h3NetValue.value
})

// 勾稽差异警告
const crossCheckWarnings = computed((): string[] => {
  const ws: string[] = []
  if (props.measurementModel === 'cost' && Math.abs(netValueDiff.value) > 0.005) {
    ws.push(`账面净值与 H3-2/H3-1 审定数差异 ${fmtNum(netValueDiff.value)}，请检查各明细表数据是否一致。`)
  }
  const fairAutoFill = crossSheet.disclosureAutoFill.value
  if (props.measurementModel === 'fair_value' && fairAutoFill) {
    const autoFairEnd = fairAutoFill['disc_asset_end'] ?? 0
    const discFairEnd = sumCol('fair-change', 'beginBalance') + sumCol('fair-change', 'increase') - sumCol('fair-change', 'decrease') + sumFairChange()
    if (autoFairEnd !== 0 && Math.abs(discFairEnd - autoFairEnd) > 0.005) {
      ws.push(`公允价值期末合计 ${fmtNum(discFairEnd)} 与 H3-2 明细合计 ${fmtNum(autoFairEnd)} 不一致，请核实。`)
    }
  }
  return ws
})

function fmtNum(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 同步到附注 + 跳转回附注 ────────────────────────────────────────────────
const router = useRouter()
const syncLoading = ref(false)

async function syncToDisclosureNotes() {
  syncLoading.value = true
  try {
    const payload = buildH3SyncPayload({
      variant: 'listed',
      measurementModel: props.measurementModel,
      costOriginalRows: getSectionRows('cost-original'),
      costDepRows: getSectionRows('cost-dep'),
      costImpairRows: getSectionRows('cost-impair'),
      fairChangeRows: getSectionRows('fair-change'),
      titleRows: getSectionRows('title-cert'),
      sectionTexts: { ...sectionTexts },
      projectId: props.projectId,
      wpId: props.wpId,
    })
    await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      { ...payload, year: auditYear.value },
    )
    ElMessage.success('已同步到附注（上市 五、21）')
    publishNoteTextUpdated('sync-listed')
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.response?.data?.message || e?.message || '未知错误'))
  } finally {
    syncLoading.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'H3', 'listed')
  if (route) router.push(route)
  else ElMessage.info('无法定位附注章节')
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => getSectionRows('cost-original'),
    () => getSectionRows('cost-dep'),
    () => getSectionRows('cost-impair'),
    () => getSectionRows('fair-change'),
    () => getSectionRows('title-cert'),
    () => sectionTexts,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => { autoSync.cancelPending() })

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
</script>

<style scoped>
.h3-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 顶部栏 */
.header-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid var(--el-border-color); }
.header-main { display: flex; flex-direction: column; gap: 2px; }
.header-title { font-size: 14px; font-weight: 600; }
.header-note { font-size: 12px; color: var(--el-text-color-secondary); }
.mode-badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.mode-cost { background: #e6f4ff; color: #1677ff; }
.mode-fair { background: #f0f9eb; color: #52c41a; }

/* 提示栏 */
.obj-alert { margin-bottom: 10px; }
.cross-warn { margin-bottom: 10px; }
.warn-list { margin: 0; padding-left: 16px; }
.warn-list li { margin-bottom: 2px; }
.mode-bar { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 16px; }
.mode-label { font-weight: 600; margin-right: 4px; }

/* 披露块 */
.disc-block { margin-bottom: 20px; border: 1px solid var(--el-border-color-light); border-radius: 6px; overflow: hidden; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--el-fill-color-light); border-bottom: 1px solid var(--el-border-color-light); }
.block-title { font-weight: 600; font-size: 13px; }
.block-actions { display: flex; gap: 6px; }
.auto-badge { font-size: 11px; color: var(--el-color-success); background: #f0f9eb; padding: 2px 8px; border-radius: 10px; }

/* 表格 */
.disc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.disc-table th, .disc-table td { border: 1px solid var(--el-border-color-light); padding: 5px 8px; }
.disc-table thead tr { background: #f5f7fa; }
.disc-table th { font-weight: 500; white-space: nowrap; }
.col-item { min-width: 160px; text-align: left; }
.col-num { width: 120px; text-align: right; }
.col-op { width: 72px; text-align: center; }
.col-lvl { width: 110px; text-align: center; }
.col-tech { min-width: 130px; text-align: left; }
.col-obs { width: 96px; text-align: center; }
.empty-tip { text-align: center; color: var(--el-text-color-secondary); font-size: 12px; padding: 10px; }
.formula-th { background: #f0f7ff; }
.formula-cell { background: #f0f7ff; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.data-row:hover { background: var(--el-fill-color-lighter); }
.total-row td { background: var(--el-fill-color); font-weight: 600; }
.num-input { width: 100%; }
:deep(.num-input .el-input__inner) { text-align: right; }

/* 差异警告 */
.diff-warn { color: var(--el-color-warning); }
.diff-tip { font-size: 11px; color: var(--el-color-warning); margin-left: 6px; }

/* 汇总块 */
.summary-block .block-header { background: #f0f9eb; }

/* 源模板红字方法论上下文（琥珀色左边线 + 浅黄背景，平台统一约定） */
.src-hint {
  margin: 8px 12px 0;
  padding: 8px 10px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  line-height: 1.7;
  color: #7a5b1c;
}
.src-hint p { margin: 0 0 4px; }
.src-hint p:last-child { margin-bottom: 0; }

/* 备注文本 */
.block-note { padding: 8px 12px; border-top: 1px solid var(--el-border-color-light); background: #fafafa; }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
