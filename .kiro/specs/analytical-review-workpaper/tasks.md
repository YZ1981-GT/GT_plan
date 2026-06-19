# Implementation Plan

## P0: 核心取数+渲染

- [x] 1. 后端: componentType 路由注册
  - `_WP_CODE_OVERRIDE` 加 `"A1-13": "analytical-review"` 和 `"A1-14": "analytical-review"`
  - `VALID_COMPONENT_TYPES` 加 `"analytical-review"`
  - 新增测试确认路由正确
  - _Requirements: 7.1, 7.2_

- [x] 2. 后端: analytical_review_service.py
  - 从 trial_balance 按 row_code 取本年/上年审定数
  - 计算变动额/变动%/变动状况(显著/关注/正常)
  - BS 横向/纵向 + IS 横向/纵向 四个维度数据组装
  - 重要性水平从 projects.overall_materiality 取
  - 阈值判定：变动%>20% 或 变动额>重要性 → significant
  - 预留变动原因引用接口（当前返回 None）
  - 单测：mock 数据验证计算逻辑
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 3. 后端: 比率分析计算引擎
  - 46 个比率公式定义（RATIO_FORMULAS dict）
  - 6 大类分组（盈利/短期偿债/长期偿债/资产管理/资本管理/现金流量）
  - 从 trial_balance 取分子/分母数据计算指标值
  - 年化处理(annualized)逻辑
  - 平均数按年末年初算术平均
  - 增减方向标记
  - 单测：验证公式正确性
  - _Requirements: 3.1~3.9_

- [x] 4. 后端: render-config 集成
  - `wp_render_config.py` 加 `analytical-review` 分支
  - 调用 analytical_review_service 返回数据
  - scope 判定（standalone vs consolidated）
  - in-process httpx 验证
  - _Requirements: 1.1, 7.4_

- [x] 5. 前端: htmlRendererRegistry 注册
  - `HtmlComponentType` union 加 `'analytical-review'`
  - REGISTRY_LIST 加 entry
  - 创建 GtAnalyticalReview.vue stub
  - vitest 更新
  - _Requirements: 6.4_

- [x] 6. 前端: GtAnalyticalReview.vue 组件
  - Tab 导航：BS横向/BS纵向/IS横向/IS纵向/比率分析（+同行业/EPS 条件显示）
  - 表格渲染：科目行 + 金额列 + 变动列 + 状况标记 + 原因列
  - 颜色编码：显著=红底、关注=黄底
  - 比率表：公式列 + 分子/分母数值 + 指标值 + 增减箭头
  - 变动原因列可编辑（debounce 2s 自动保存）
  - 科目行点击跳转对应循环底稿（预留，当前 console.log）
  - _Requirements: 6.1~6.4_

- [x] 7. 集成验证
  - getDiagnostics 无报错
  - 后端测试全绿
  - 前端 vitest 全绿
  - Playwright: 打开 A1-13 → 看到 Tab 导航 + BS 横向数据
  - 回归: A1-15 核对表仍正常
  - _Requirements: 7.1~7.4_

## P1: 上市公司专用 sheet

- [x] 8. 同行业对比分析 A1-14-6
  - 可比公司录入（5家 × 证券简称/代码）
  - 主要财务数据表 + 对比分析表（3年 × 多指标）
  - 数据来源标注
  - 按 project.is_listed 条件显示
  - _Requirements: 4.1~4.5_
  - **现状（2026-06-17 实证）**：仅有空结构骨架（`build_industry_comparison` 返回全 null 网格），前端只读展示、无可编辑/保存/持久化；未接 `project.is_listed`（误用 `template_type=='listed'`）；5 家可比公司 A~E 列未实现

- [x] 9. EPS-ROE 计算表
  - 净资产收益率（全面摊薄/加权平均）
  - 基本/稀释每股收益
  - 股本变动明细（期初 S0 + 增减 × 时间权重）
  - 公式内置，用户填参数自动计算
  - 按 project.is_listed 条件显示
  - _Requirements: 5.1~5.6_
  - **现状（2026-06-17 实证）**：仅从报表预填 4 个字段 + 后端一次性算 4 个结果；无用户编辑、无股本变动明细 S1~Sk、无 CAS34 加权公式、无保存端点

## P2: 联动增强（预留）

- [ ]* 10. 变动原因自动引用
  - 从各科目审定表 audit_explanation 读取
  - 按 row_code → account_codes → wp_code 映射
  - 待各科目底稿修订完成后实现
  - _Requirements: 2.1, 2.2_
  - **现状**：`get_audit_explanation_for_row` 仍硬返回 None，行数据 reason 恒为 null
