<template>
  <div class="h3-disc-soe">

    <!-- ① 顶部信息栏 -->
    <div class="header-bar">
      <div class="header-main">
        <span class="header-title">致同会计师事务所 — 附注披露信息（国有企业）</span>
        <span class="header-note">投资性房地产（国资委口径）</span>
      </div>
      <div class="mode-badge" :class="measurementModel === 'cost' ? 'mode-cost' : 'mode-fair'">
        {{ measurementModel === 'cost' ? '成本模式' : '公允价值模式' }}
      </div>
      <div class="header-actions" style="display:flex;gap:8px;margin-left:auto">
        <el-button size="small" type="success" :loading="syncLoading" :disabled="isReadonly" @click="syncToDisclosureNotes">
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain @click="jumpToNote">
          ↩ 跳转回附注（{{ H3_NOTE_SECTION.soe }}）
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="obj-alert"
      title="审计目标：核实投资性房地产附注披露（国有企业格式）的完整与准确；成本模式与公允价值模式互斥，不适用的表格自动省略（不需要生成）。"
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
        ? '成本法 — 生成：账面原值 / 折旧摊销 / 账面净值三表；公允价值相关表格自动省略。'
        : '公允价值法 — 生成：公允价值变动表 / 公允价值变动损益表；成本法三张表自动省略。' }}</span>
    </div>

    <!-- ④ 主体：按计量模式渲染对应披露块 -->

    <!-- === 成本模式 === -->
    <template v-if="measurementModel === 'cost'">

      <!-- 账面原值 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（1）以成本计量的投资性房地产 — 账面原值</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-cost')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-cost')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-item">项 目</th>
              <th rowspan="2" class="col-num">期初余额</th>
              <th colspan="2" class="group-th">本期增加</th>
              <th colspan="2" class="group-th">本期减少</th>
              <th rowspan="2" class="col-num formula-th">期末余额</th>
              <th rowspan="2" class="col-usage">用 途</th>
              <th v-if="!isReadonly" rowspan="2" class="col-op"></th>
            </tr>
            <tr>
              <th class="col-num">购置或计提</th>
              <th class="col-num">自用房地产或存货转入</th>
              <th class="col-num">处 置</th>
              <th class="col-num">转为自用房地产</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('soe-cost')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-cost', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-cost', row)" /></td>
              <td><el-input v-model.number="row.buyOrProvision" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost', row)" /></td>
              <td><el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost', row)" /></td>
              <td><el-input v-model.number="row.disposal" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost', row)" /></td>
              <td><el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost', row)" /></td>
              <td class="formula-cell">{{ fmtNum((Number(row.beginBalance) || 0) + rowIncrease(row) - rowDecrease(row)) }}</td>
              <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="出租/自用/增值" @change="onRowChange('soe-cost', row)" /></td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-cost', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('soe-cost', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost', 'buyOrProvision')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost', 'transferIn')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost', 'disposal')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost', 'transferOut')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost', 'beginBalance') + sumCol('soe-cost', 'increase') - sumCol('soe-cost', 'decrease')) }}</td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-cost']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明本期增加/减少主要原因（外购、自用房地产或存货转入、转出、处置等）" :disabled="isReadonly"
            @change="onTextChange('soe-cost')" />
        </div>
      </div>

      <!-- 累计折旧和摊销 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（2）累计折旧和累计摊销</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-cost-dep')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-cost-dep')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-item">项 目</th>
              <th rowspan="2" class="col-num">期初余额</th>
              <th colspan="2" class="group-th">本期增加</th>
              <th colspan="2" class="group-th">本期减少</th>
              <th rowspan="2" class="col-num formula-th">期末余额</th>
              <th rowspan="2" class="col-usage">用 途</th>
              <th v-if="!isReadonly" rowspan="2" class="col-op"></th>
            </tr>
            <tr>
              <th class="col-num">购置或计提</th>
              <th class="col-num">自用房地产或存货转入</th>
              <th class="col-num">处 置</th>
              <th class="col-num">转为自用房地产</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('soe-cost-dep')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-cost-dep', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-cost-dep', row)" /></td>
              <td><el-input v-model.number="row.buyOrProvision" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost-dep', row)" /></td>
              <td><el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost-dep', row)" /></td>
              <td><el-input v-model.number="row.disposal" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost-dep', row)" /></td>
              <td><el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-cost-dep', row)" /></td>
              <td class="formula-cell">{{ fmtNum((Number(row.beginBalance) || 0) + rowIncrease(row) - rowDecrease(row)) }}</td>
              <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="出租/自用" @change="onRowChange('soe-cost-dep', row)" /></td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-cost-dep', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('soe-cost-dep', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost-dep', 'buyOrProvision')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost-dep', 'transferIn')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost-dep', 'disposal')) }}</td>
              <td>{{ fmtNum(sumCol('soe-cost-dep', 'transferOut')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost-dep', 'beginBalance') + sumCol('soe-cost-dep', 'increase') - sumCol('soe-cost-dep', 'decrease')) }}</td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-cost-dep']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明折旧方法、使用年限、残值率等计量政策。" :disabled="isReadonly"
            @change="onTextChange('soe-cost-dep')" />
        </div>
      </div>

      <!-- 账面净值（自动汇总） -->
      <div class="disc-block summary-block">
        <div class="block-header">
          <span class="block-title">（3）投资性房地产账面净值</span>
          <span class="auto-badge">自动计算</span>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th class="col-item">项 目</th>
              <th class="col-num">期初账面净值</th>
              <th class="col-num">期末账面净值</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>账面原值</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost', 'beginBalance')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost', 'beginBalance') + sumCol('soe-cost', 'increase') - sumCol('soe-cost', 'decrease')) }}</td>
            </tr>
            <tr>
              <td>减：累计折旧和摊销</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost-dep', 'beginBalance')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost-dep', 'beginBalance') + sumCol('soe-cost-dep', 'increase') - sumCol('soe-cost-dep', 'decrease')) }}</td>
            </tr>
            <tr class="total-row">
              <td>账面净值</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-cost', 'beginBalance') - sumCol('soe-cost-dep', 'beginBalance')) }}</td>
              <td class="formula-cell" :class="{ 'diff-warn': netValueDiff !== 0 }">
                {{ fmtNum(computedNetValue) }}
                <span v-if="netValueDiff !== 0" class="diff-tip">（与 H3-1 差异：{{ fmtNum(netValueDiff) }}）</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 减值准备（国企格式单独列示） -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（4）减值准备</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-impair')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-impair')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-item">项 目</th>
              <th rowspan="2" class="col-num">期初余额</th>
              <th colspan="2" class="group-th">本期增加</th>
              <th colspan="2" class="group-th">本期减少</th>
              <th rowspan="2" class="col-num formula-th">期末余额</th>
              <th v-if="!isReadonly" rowspan="2" class="col-op"></th>
            </tr>
            <tr>
              <th class="col-num">购置或计提</th>
              <th class="col-num">自用房地产或存货转入</th>
              <th class="col-num">处 置</th>
              <th class="col-num">转为自用房地产</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('soe-impair')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-impair', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-impair', row)" /></td>
              <td><el-input v-model.number="row.buyOrProvision" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-impair', row)" /></td>
              <td><el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-impair', row)" /></td>
              <td><el-input v-model.number="row.disposal" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-impair', row)" /></td>
              <td><el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-impair', row)" /></td>
              <td class="formula-cell">{{ fmtNum((Number(row.beginBalance) || 0) + rowIncrease(row) - rowDecrease(row)) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-impair', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('soe-impair', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('soe-impair', 'buyOrProvision')) }}</td>
              <td>{{ fmtNum(sumCol('soe-impair', 'transferIn')) }}</td>
              <td>{{ fmtNum(sumCol('soe-impair', 'disposal')) }}</td>
              <td>{{ fmtNum(sumCol('soe-impair', 'transferOut')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-impair', 'beginBalance') + sumCol('soe-impair', 'increase') - sumCol('soe-impair', 'decrease')) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-impair']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明本期减值迹象、测试情况及结论；如无减值，请注明。" :disabled="isReadonly"
            @change="onTextChange('soe-impair')" />
        </div>
      </div>

    </template>

    <!-- === 公允价值模式 === -->
    <template v-else>

      <!-- 公允价值变动表 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（1）采用公允价值计量的投资性房地产</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-fair-value')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-fair-value')">AI</el-button>
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
              <th class="col-usage">用 途</th>
              <th v-if="!isReadonly" class="col-op"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('soe-fair-value')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-fair-value', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-fair-value', row)" /></td>
              <td><el-input v-model.number="row.increase" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-fair-value', row)" /></td>
              <td><el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-fair-value', row)" /></td>
              <td><el-input v-model.number="(row as any).fairChange" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-fair-value', row)" /></td>
              <td class="formula-cell">{{ fmtNum(row.beginBalance + row.increase - row.decrease + ((row as any).fairChange || 0)) }}</td>
              <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="出租/增值" @change="onRowChange('soe-fair-value', row)" /></td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-fair-value', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('soe-fair-value', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-value', 'increase')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-value', 'decrease')) }}</td>
              <td>{{ fmtNum(sumFairChange('soe-fair-value')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-fair-value', 'beginBalance') + sumCol('soe-fair-value', 'increase') - sumCol('soe-fair-value', 'decrease') + sumFairChange('soe-fair-value')) }}</td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-fair-value']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明公允价值确定依据、评估机构、评估方法及关键假设。" :disabled="isReadonly"
            @change="onTextChange('soe-fair-value')" />
        </div>
      </div>

      <!-- 公允价值变动损益 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（2）公允价值变动损益</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-fair-change')">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-fair-change')">AI</el-button>
          </div>
        </div>
        <table class="disc-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-item">项 目</th>
              <th rowspan="2" class="col-num">期初公允价值</th>
              <th colspan="3" class="group-th">本期增加</th>
              <th colspan="2" class="group-th">本期减少</th>
              <th rowspan="2" class="col-num formula-th">期末公允价值</th>
              <th v-if="!isReadonly" rowspan="2" class="col-op"></th>
            </tr>
            <tr>
              <th class="col-num">购置</th>
              <th class="col-num">自用房地产或存货转入</th>
              <th class="col-num">公允价值变动损益</th>
              <th class="col-num">处 置</th>
              <th class="col-num">转为自用房地产</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in getSectionRows('soe-fair-change')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.buyOrProvision" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.fairChange" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.disposal" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-fair-change', row)" /></td>
              <td><el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" class="num-input" @change="onSubChange('soe-fair-change', row)" /></td>
              <td class="formula-cell">{{ fmtNum((Number(row.beginBalance) || 0) + rowIncrease(row) - rowDecrease(row) + (Number(row.fairChange) || 0)) }}</td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-fair-change', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'beginBalance')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'buyOrProvision')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'transferIn')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'fairChange')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'disposal')) }}</td>
              <td>{{ fmtNum(sumCol('soe-fair-change', 'transferOut')) }}</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-fair-change', 'beginBalance') + sumCol('soe-fair-change', 'increase') - sumCol('soe-fair-change', 'decrease') + sumCol('soe-fair-change', 'fairChange')) }}</td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-fair-change']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明公允价值变动与 H3-8 复核表及审定表勾稽情况。" :disabled="isReadonly"
            @change="onTextChange('soe-fair-change')" />
        </div>
      </div>

      <!-- 公允价值层次披露（CAS39） -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（3）公允价值层次、估值技术及关键输入值（CAS39）</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="onImportFvFromH38">从 H3-8 带入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addFvHierarchyRow()">＋ 插行</el-button>
            <el-button size="small" plain @click="generateAI('soe-fair-hierarchy')">AI</el-button>
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
              <td>第一层次合计</td><td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level1) }}</td>
              <td colspan="3"></td><td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>第二层次合计</td><td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level2) }}</td>
              <td colspan="3"></td><td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>第三层次合计</td><td></td>
              <td class="formula-cell">{{ fmtNum(fvHierarchyTotalsByLevel.level3) }}</td>
              <td colspan="3"></td><td v-if="!isReadonly"></td>
            </tr>
            <tr class="total-row">
              <td>合 计</td><td></td>
              <td class="formula-cell" :class="{ 'diff-warn': fvHierarchyDiff !== 0 }">
                {{ fmtNum(fvHierarchyTotalsByLevel.total) }}
                <span v-if="fvHierarchyDiff !== 0" class="diff-tip">（与公允价值表期末差异：{{ fmtNum(fvHierarchyDiff) }}）</span>
              </td>
              <td colspan="3"></td><td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
        <div class="block-note">
          <el-input v-model="sectionTexts['soe-fair-hierarchy']" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="披露公允价值层次确定依据；第三层次采用的估值技术及关键不可观察输入值（市场租金/折现率/资本化率）；层次间转换情况。" :disabled="isReadonly"
            @change="onTextChange('soe-fair-hierarchy')" />
        </div>
      </div>

      <!-- 未办妥产权证书 -->
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（3）未办妥产权证书情况</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-unlicensed')">＋ 插行</el-button>
          </div>
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
            <tr v-for="row in getSectionRows('soe-unlicensed')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="请填写原因" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-unlicensed', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-unlicensed', 'beginBalance')) }}</td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
      </div>

    </template>

    <!-- ⑤ 共用：未办妥产权证书（成本模式同样展示） -->
    <template v-if="measurementModel === 'cost'">
      <div class="disc-block">
        <div class="block-header">
          <span class="block-title">（5）未办妥产权证书情况</span>
          <div class="block-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRow('soe-unlicensed')">＋ 插行</el-button>
          </div>
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
            <tr v-for="row in getSectionRows('soe-unlicensed')" :key="row.rowId" class="data-row">
              <td><el-input v-model="row.category" size="small" :disabled="isReadonly" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td><el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" class="num-input" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td><el-input v-model="row.usage" size="small" :disabled="isReadonly" placeholder="请填写原因" @change="onRowChange('soe-unlicensed', row)" /></td>
              <td v-if="!isReadonly"><el-button text type="danger" size="small" @click="removeRow('soe-unlicensed', row.rowId)">删除</el-button></td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>合 计</td>
              <td class="formula-cell">{{ fmtNum(sumCol('soe-unlicensed', 'beginBalance')) }}</td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>

    <!-- ⑥ 共用块：补充说明 / 产权受限 / 租赁经营 -->
    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">补充说明</span>
        <el-button size="small" plain @click="generateAI('soe-policy')">AI</el-button>
      </div>
      <el-input v-model="sectionTexts['soe-policy']" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :placeholder="measurementModel === 'cost'
          ? '描述成本模式后续计量政策、折旧方法、残值率、使用年限，以及本期折旧摊销合计金额及投资性房地产减值准备本期计提合计金额。'
          : '描述公允价值模式选择原因、公允价值确定依据（评估机构/方法/关键假设）及本期公允价值变动损益计入情况。'"
        :disabled="isReadonly"
        @change="onTextChange('soe-policy')" />
    </div>

    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">产权及受限情况</span>
        <el-button size="small" plain @click="generateAI('soe-restriction')">AI</el-button>
      </div>
      <el-input v-model="sectionTexts['soe-restriction']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="说明产权归属、抵押担保（抵押投资性房地产账面价值）、查封情况及其他使用限制。"
        :disabled="isReadonly"
        @change="onTextChange('soe-restriction')" />
    </div>

    <div class="disc-block">
      <div class="block-header">
        <span class="block-title">租赁及经营情况</span>
        <el-button size="small" plain @click="generateAI('soe-rental')">AI</el-button>
      </div>
      <el-input v-model="sectionTexts['soe-rental']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="说明主要租赁安排（租期/租金/租户）、本期租金收入合计、空置率及即将到期合同续签情况。"
        :disabled="isReadonly"
        @change="onTextChange('soe-rental')" />
    </div>

    <!-- ⑦ 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示 / 检查清单</summary>
      <ul>
        <li>国有企业投资性房地产附注格式按国资委要求披露；计量模式互斥，不适用表格自动省略。</li>
        <li>成本模式：账面原值、累计折旧/摊销、账面净值、减值准备四表须完整；用途列应填写"出租""增值持有"等。</li>
        <li>公允价值模式：公允价值变动表及变动损益表须完整；需披露评估机构、方法及关键假设。</li>
        <li>未办妥产权证书情况在两种计量模式下均需单独列示，合计金额与受限情况说明要一致。</li>
        <li>账面净值差异警告（与 H3-1 对比）自动显示；各表"期末余额"自动计算，无需手填。</li>
        <li>本期折旧摊销额及减值准备计提额须在补充说明中以 XXX 元量化表述。</li>
      </ul>
    </details>

  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDisclosureSoe.vue — 附注披露（国有企业版）
 * 模板化表格块 + 计量模式二选一 + 无限插行/删行 + 用途列 + 产权专项表 + 勾稽差异高亮
 */
import { ref, computed, inject, toRef, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useH3Disclosure } from '../../composables/useH3Disclosure'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3CrossSheet } from '../../composables/useH3CrossSheet'
import { eventBus } from '@/utils/eventBus'
import { H3_FALLBACK_CODES } from '../../composables/h3AccountScope'
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
  variant: ref('soe') as any,
  disclosureAutoFill: crossSheet.disclosureAutoFill,
})

function onImportFvFromH38() {
  const r = importFvHierarchyFromH38()
  ElMessage[r.added ? 'success' : 'info'](r.message)
}

const fvHierarchyDiff = computed(() => {
  if (props.measurementModel !== 'fair_value') return 0
  const fairEnd = sumCol('soe-fair-value', 'beginBalance') + sumCol('soe-fair-value', 'increase') - sumCol('soe-fair-value', 'decrease') + sumFairChange('soe-fair-value')
  const hierarchyTotal = fvHierarchyTotalsByLevel.value.total
  if (fairEnd === 0 && hierarchyTotal === 0) return 0
  return Math.abs(hierarchyTotal - fairEnd) > 0.005 ? hierarchyTotal - fairEnd : 0
})

function publishNoteTextUpdated(key: string) {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'H3',
    section: key,
    // 🔴 改造前写死 1503 = 可供出售金融资产（G6 域）；投资性房地产是 1521 族
    accountCode: H3_FALLBACK_CODES.gross,
    projectId: props.projectId,
    sectionIds: ['投资性房地产', H3_NOTE_SECTION.listed, H3_NOTE_SECTION.soe],
    timestamp: Date.now(),
  })
}

// ─── 同步到附注 + 跳转回附注 ────────────────────────────────────────────────
const router = useRouter()
const syncLoading = ref(false)

async function syncToDisclosureNotes() {
  syncLoading.value = true
  try {
    const payload = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: props.measurementModel,
      costOriginalRows: getSectionRows('soe-cost'),
      costDepRows: getSectionRows('soe-cost-dep'),
      // 🔴 原写 'cost-impair'（那是**上市**组件的 section key）→ 国企减值行永远取空、
      // 减值层与账面价值层恒为 0。国企自身 key 是 'soe-impair'。
      costImpairRows: getSectionRows('soe-impair'),
      fairChangeRows: getSectionRows('soe-fair-change'),
      titleRows: getSectionRows('soe-unlicensed'),
      sectionTexts: { ...sectionTexts },
      projectId: props.projectId,
      wpId: props.wpId,
    })
    await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      { ...payload, year: auditYear.value },
    )
    ElMessage.success(`已同步到附注（国企 ${H3_NOTE_SECTION.soe}）`)
    publishNoteTextUpdated('sync-soe')
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.response?.data?.message || e?.message || '未知错误'))
  } finally {
    syncLoading.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'H3', 'soe')
  if (route) router.push(route)
  else ElMessage.info('无法定位附注章节')
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => getSectionRows('soe-cost'),
    () => getSectionRows('soe-cost-dep'),
    // 与 buildH3SyncPayload 入参一致（原写 'cost-impair' 是上市 key → 国企减值改动不触发同步）
    () => getSectionRows('soe-impair'),
    () => getSectionRows('soe-fair-change'),
    () => getSectionRows('soe-unlicensed'),
    () => sectionTexts,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => { autoSync.cancelPending() })

function onRowChange(key: string, row: any) { updateRow(key, row) }
function onTextChange(key: string) {
  updateText(key, sectionTexts[key])
  publishNoteTextUpdated(key)
}
function addRow(key: string) { addSectionRow(key, { category: '', usage: '' }) }
function removeRow(key: string, rowId: string) { removeSectionRow(key, rowId) }

function sumCol(key: string, field: string): number {
  return getSectionRows(key).reduce((s, r) => s + (Number((r as any)[field]) || 0), 0)
}

/**
 * 源模板两级子列（本期增加{购置或计提, 自用房地产或存货转入} /
 * 本期减少{处 置, 转为自用房地产}）录入后，把聚合 `increase`/`decrease` 回写为子列之和。
 *
 * 这样期末余额、合计行、`buildH3SyncPayload` 的期末派生三处口径一致；
 * 载荷侧 `toMovement` 会优先采用细分子列值（不再走「聚合额归入主渠道」的退化映射）。
 */
function onSubChange(key: string, row: any) {
  const n = (v: unknown) => Number(v) || 0
  row.increase = n(row.buyOrProvision) + n(row.transferIn)
  row.decrease = n(row.disposal) + n(row.transferOut)
  updateRow(key, row)
}

/** 该行本期增加 / 减少（由子列派生，供表格展示与合计） */
function rowIncrease(row: any): number {
  return (Number(row.buyOrProvision) || 0) + (Number(row.transferIn) || 0)
}
function rowDecrease(row: any): number {
  return (Number(row.disposal) || 0) + (Number(row.transferOut) || 0)
}
function sumFairChange(key: string): number {
  return getSectionRows(key).reduce((s, r) => s + (Number((r as any).fairChange) || 0), 0)
}

// 成本模式：净值 = 原值期末 - 折旧期末
const computedNetValue = computed(() => {
  const origEnd = sumCol('soe-cost', 'beginBalance') + sumCol('soe-cost', 'increase') - sumCol('soe-cost', 'decrease')
  const depEnd  = sumCol('soe-cost-dep', 'beginBalance') + sumCol('soe-cost-dep', 'increase') - sumCol('soe-cost-dep', 'decrease')
  return origEnd - depEnd
})

const h3NetValue = computed(() => crossSheet.detailTotals.value?.netValue ?? 0)
const netValueDiff = computed(() => {
  if (props.measurementModel !== 'cost') return 0
  return computedNetValue.value - h3NetValue.value
})

const crossCheckWarnings = computed((): string[] => {
  const ws: string[] = []
  if (props.measurementModel === 'cost' && Math.abs(netValueDiff.value) > 0.005) {
    ws.push(`账面净值与 H3-2/H3-1 审定数差异 ${fmtNum(netValueDiff.value)}，请检查明细表数据。`)
  }
  const af = crossSheet.disclosureAutoFill.value
  if (props.measurementModel === 'fair_value' && af) {
    const autoEnd = af['disc_asset_end'] ?? 0
    const discEnd = sumCol('soe-fair-value', 'beginBalance') + sumCol('soe-fair-value', 'increase') - sumCol('soe-fair-value', 'decrease') + sumFairChange('soe-fair-value')
    if (autoEnd !== 0 && Math.abs(discEnd - autoEnd) > 0.005) {
      ws.push(`公允价值期末 ${fmtNum(discEnd)} 与 H3-2 明细合计 ${fmtNum(autoEnd)} 不一致，请核实。`)
    }
    const autoChange = af['disc_fair_value_change_total'] ?? 0
    const discChange = sumFairChange('soe-fair-value')
    if (autoChange !== 0 && Math.abs(discChange - autoChange) > 0.005) {
      ws.push(`公允价值变动 ${fmtNum(discChange)} 与 H3-8 复核合计 ${fmtNum(autoChange)} 不一致。`)
    }
  }
  return ws
})

function fmtNum(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
</script>

<style scoped>
.h3-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }

.header-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid var(--el-border-color); }
.header-main { display: flex; flex-direction: column; gap: 2px; }
.header-title { font-size: 14px; font-weight: 600; }
.header-note { font-size: 12px; color: var(--el-text-color-secondary); }
.mode-badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.mode-cost { background: #e6f4ff; color: #1677ff; }
.mode-fair { background: #f0f9eb; color: #52c41a; }

.obj-alert { margin-bottom: 10px; }
.cross-warn { margin-bottom: 10px; }
.warn-list { margin: 0; padding-left: 16px; }
.warn-list li { margin-bottom: 2px; }
.mode-bar { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 16px; }
.mode-label { font-weight: 600; margin-right: 4px; }

.disc-block { margin-bottom: 20px; border: 1px solid var(--el-border-color-light); border-radius: 6px; overflow: hidden; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--el-fill-color-light); border-bottom: 1px solid var(--el-border-color-light); }
.block-title { font-weight: 600; font-size: 13px; }
.block-actions { display: flex; gap: 6px; }
.auto-badge { font-size: 11px; color: var(--el-color-success); background: #f0f9eb; padding: 2px 8px; border-radius: 10px; }

.disc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.disc-table th, .disc-table td { border: 1px solid var(--el-border-color-light); padding: 5px 8px; }
.disc-table thead tr { background: #f5f7fa; }
.disc-table th { font-weight: 500; white-space: nowrap; }
.col-item { min-width: 160px; text-align: left; }
.col-num { width: 120px; text-align: right; }
.col-usage { width: 100px; }
.col-op { width: 72px; text-align: center; }
.col-lvl { width: 110px; text-align: center; }
.col-tech { min-width: 130px; text-align: left; }
.col-obs { width: 96px; text-align: center; }
.empty-tip { text-align: center; color: var(--el-text-color-secondary); font-size: 12px; padding: 10px; }
.formula-th { background: #f0f7ff; }
/* 两级表头父分组（源模板 本期增加 / 本期减少 跨列表头） */
.group-th { text-align: center; background: #eef1f6; font-weight: 600; }
.formula-cell { background: #f0f7ff; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.data-row:hover { background: var(--el-fill-color-lighter); }
.total-row td { background: var(--el-fill-color); font-weight: 600; }
.num-input { width: 100%; }
:deep(.num-input .el-input__inner) { text-align: right; }

.diff-warn { color: var(--el-color-warning); }
.diff-tip { font-size: 11px; color: var(--el-color-warning); margin-left: 6px; }

.summary-block .block-header { background: #f0f9eb; }

.block-note { padding: 8px 12px; border-top: 1px solid var(--el-border-color-light); background: #fafafa; }

.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
