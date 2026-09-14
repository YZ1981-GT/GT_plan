<template>
  <div class="pd-guidance">
    <el-collapse v-model="openNames">
      <el-collapse-item name="rating">
        <template #title>
          <span class="title">评级映射与基础边际 PD</span>
          <el-tag size="small" type="info" effect="plain">中证协指引参考</el-tag>
        </template>
        <div class="guide-block">
          <p>
            先取得债务人/债项外部评级，将国内评级审慎映射至国际评级，再从评级迁徙或违约率资料取得一年期边际
            PD。国内主体外部评级为 AA 时，映射等级原则上不应高于国际评级 BBB-，其他等级结合实际审慎调整。
          </p>
          <p>
            源模板引用 Moody's《Annual Default Study—Corporate Default 1920–2016》中
            “Average One-Year Alphanumeric Rating Migration Rates, 1983–2016”。因原始违约率不单调，
            可采用指数回归平滑，并设置 0.03% 下限；违约率应按年更新，并保留当期数据版本。
          </p>
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="评级映射、历史违约率与平滑方法均属于模型输入，不能只抄表；须记录评级日期、映射依据、数据版本及覆盖期间。"
          />
        </div>
      </el-collapse-item>

      <el-collapse-item name="forward">
        <template #title>
          <span class="title">前瞻性调整</span>
          <el-tag size="small" type="warning" effect="plain">宏观因子</el-tag>
        </template>
        <div class="guide-block">
          <div class="formula">Adjusted Marginal PD<sub>t</sub> = AdjFactor × Marginal PD<sub>t</sub></div>
          <p>
            根据对未来经济或信用环境的预测，对各资产负债表日未来年度边际违约概率进行前瞻性调整。
            调整因子可通过宏观变量与长期平均违约率关系、信用价差调整、违约概率校准法、蒙特卡洛等方法确定。
          </p>
          <p>
            也可建立对宏观经济预测的分布，或基于专家判断调整“评级—违约概率”映射。应说明采用的宏观变量、
            情景及权重、模型或专家判断依据，并验证调整后 PD 在 0～100% 范围内。
          </p>
        </div>
      </el-collapse-item>

      <el-collapse-item name="term">
        <template #title>
          <span class="title">期限调整与条件违约概率</span>
          <el-tag size="small" type="success" effect="plain">公式</el-tag>
        </template>
        <div class="guide-block">
          <p>剩余期限不足一年或最后一年不足整年时，可对边际 PD 做期限调整：</p>
          <div class="formula">
            调整后边际 PD<sub>t</sub> = 1 − (1 − 调整前边际 PD<sub>t</sub>)<sup>t</sup>
          </div>
          <p>其中 t 为剩余期限（年）。将边际 PD 转为第 i 年条件违约概率时：</p>
          <div class="formula">
            PD<sub>i</sub> = 调整后边际 PD<sub>i</sub> ×
            ∏<sub>j=1</sub><sup>i−1</sup>(1 − 调整后边际 PD<sub>j</sub>)
          </div>
          <p class="muted">
            注意：本项目现有“1−(1−一年期PD)^(月数/12)”是单一 PD 的期限近似；若采用多年逐期边际 PD，
            应按上式先做生存概率衔接，不能简单累加。
          </p>
        </div>
      </el-collapse-item>

      <el-collapse-item name="stage">
        <template #title>
          <span class="title">按三阶段和剩余期限取 PD</span>
          <el-tag size="small" type="danger" effect="plain">G4-9 → G4-11 → G4-10</el-tag>
        </template>
        <div class="guide-block">
          <ul>
            <li>
              <strong>Stage1：</strong>在外部评级映射 PD 基础上进行前瞻性调整；剩余期限不足一年按实际期限折算，
              超过一年只计未来 12 个月 PD。
            </li>
            <li>
              <strong>Stage2：</strong>取得前瞻性调整后的逐期边际 PD，再按整个剩余存续期计算；
              剩余期限不足一年按实际期限，超过一年按实际剩余期限逐期计算。
            </li>
            <li>
              <strong>Stage2 已到期但逾期不超过 90 天：</strong>可按逾期天数折算期次，
              t = 向上取整（逾期天数 ÷ 30），并采用相应短期/逐月 PD；须与企业模型口径一致。
            </li>
            <li><strong>Stage3：</strong>参考资料取 PD = 100%；实际 ECL 仍应结合 LGD、预计回收现金流及折现。</li>
          </ul>
        </div>
      </el-collapse-item>

      <el-collapse-item name="regulation">
        <template #title>
          <span class="title">法规边界：资本风险权重 ≠ 会计 PD</span>
          <el-tag size="small" type="danger" effect="dark">防误用</el-tag>
        </template>
        <div class="guide-block">
          <p>
            《商业银行资本管理办法》（2024年1月1日起实施）规定的公司风险暴露权重（例如一般公司 100%、
            符合条件中小企业 85%、投资级公司 75% 等）用于银行资本计量，并不是 CAS 22 下 ECL 模型的违约概率。
          </p>
          <el-alert
            type="error"
            :closable="false"
            show-icon
            title="风险权重只能作为外部监管背景或合理性佐证，不得直接填入“外部映射PD”“期限折算PD”或“信用损失率”。"
          />
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const openNames = ref<string[]>([])
</script>

<style scoped>
.pd-guidance {
  margin: 10px 0 12px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 0 12px;
  background: #fcfcfd;
}
.title {
  margin-right: 8px;
  font-weight: 600;
}
.guide-block {
  padding: 0 4px 12px;
  color: #606266;
  font-size: 12px;
  line-height: 1.75;
}
.guide-block p {
  margin: 6px 0;
}
.guide-block ul {
  margin: 4px 0;
  padding-left: 20px;
}
.guide-block li {
  margin-bottom: 6px;
}
.formula {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  color: #1d39c4;
  font-family: Cambria, "Times New Roman", serif;
  font-size: 13px;
}
.muted {
  color: #909399;
}
</style>
