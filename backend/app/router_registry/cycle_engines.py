"""审计循环计算引擎路由注册

覆盖原 router_registry.py 中以下分组：
  §64 D 销售循环：客户访谈 LLM 摘要
  §65 D 销售循环：D2 业务模式分析
  §66 F 采购存货循环：存货监盘 LLM 差异分析
  §67 F 采购存货循环：F-F11 计价测试自动抽样
  §68 F 采购存货循环：F-F12 跌价准备 ECL 模型辅助
  §69 H 固定资产循环：H-F11 折旧自动测算引擎
  §70 H 固定资产循环：H-F12 减值 DCF 模型辅助
  §71 I 无形资产循环：I-F4 商誉减值 DCF 模型辅助
  §72 I 无形资产循环：I-F5 开发支出资本化时点判断
  §73 I 无形资产循环：I-F2 摊销自动测算引擎
  §74 G 投资循环：G-F4 公允价值测试
  §75 G 投资循环：G-F5 ECL 三阶段模型
  §76 G 投资循环：G-F11 金融资产分类辅助
  §77 J 职工薪酬循环：J-F7 薪酬计提引擎
  §78 J 职工薪酬循环：J-F8 股份支付 Black-Scholes
  §79 K 管理循环：K-F7 销售/管理费用分析引擎
  §80 K 管理循环：K-F8 K11 资产减值损失跨循环汇总
  §81 L 筹资循环：L-F7 利息自动测算引擎
  §82 L 筹资循环：L-F8 应付债券摊余成本引擎
  §83 M 权益循环：M-F7 权益变动表引擎
  §84 N 税金循环：N-F7 所得税费用测算引擎
"""
from fastapi import FastAPI


def register_cycle_engine_routers(app: FastAPI) -> None:
    """注册各审计循环计算引擎路由"""

    # ═══ §64. D 销售循环：客户访谈 LLM 摘要 ═══
    from app.routers.wp_ai_interview import router as wp_ai_interview_router
    app.include_router(wp_ai_interview_router, tags=["wp-ai-interview"])

    # ═══ §65. D 销售循环：D2 业务模式分析 ═══
    from app.routers.wp_business_pattern import router as wp_business_pattern_router
    app.include_router(wp_business_pattern_router, tags=["wp-business-pattern"])

    # ═══ §66. F 采购存货循环：存货监盘 LLM 差异分析 ═══
    from app.routers.wp_ai_stocktake import router as wp_ai_stocktake_router
    app.include_router(wp_ai_stocktake_router, tags=["wp-ai-stocktake"])

    # ═══ §67. F 采购存货循环：F-F11 计价测试自动抽样 ═══
    from app.routers.wp_f2_valuation import router as wp_f2_valuation_router
    app.include_router(wp_f2_valuation_router, tags=["wp-f2-valuation"])

    # ═══ §68. F 采购存货循环：F-F12 跌价准备 ECL 模型辅助 ═══
    from app.routers.wp_f2_impairment import router as wp_f2_impairment_router
    app.include_router(wp_f2_impairment_router, tags=["wp-f2-impairment"])

    # ═══ §69. H 固定资产循环：H-F11 折旧自动测算引擎 ═══
    from app.routers.wp_h_depreciation import router as wp_h_depreciation_router
    app.include_router(wp_h_depreciation_router, tags=["wp-h-depreciation"])

    # ═══ §70. H 固定资产循环：H-F12 减值 DCF 模型辅助 ═══
    from app.routers.wp_h_impairment import router as wp_h_impairment_router
    app.include_router(wp_h_impairment_router, tags=["wp-h-impairment"])

    # ═══ §71. I 无形资产循环：I-F4 商誉减值 DCF 模型辅助 ═══
    from app.routers.wp_i_goodwill import router as wp_i_goodwill_router
    app.include_router(wp_i_goodwill_router, tags=["wp-i-goodwill"])

    # ═══ §72. I 无形资产循环：I-F5 开发支出资本化时点判断 ═══
    from app.routers.wp_i_capitalization import router as wp_i_capitalization_router
    app.include_router(wp_i_capitalization_router, tags=["wp-i-capitalization"])

    # ═══ §73. I 无形资产循环：I-F2 摊销自动测算引擎 ═══
    from app.routers.wp_i_amortization import (
        router_i1 as wp_i_amortization_i1_router,
        router_i4 as wp_i_amortization_i4_router,
    )
    app.include_router(wp_i_amortization_i1_router, tags=["wp-i-amortization"])
    app.include_router(wp_i_amortization_i4_router, tags=["wp-i-amortization"])

    # ═══ §74. G 投资循环：G-F4 公允价值测试 ═══
    from app.routers.wp_g_fair_value import router as wp_g_fair_value_router
    app.include_router(wp_g_fair_value_router, tags=["wp-g-fair-value"])

    # ═══ §75. G 投资循环：G-F5 ECL 三阶段模型 ═══
    from app.routers.wp_g_ecl import router as wp_g_ecl_router
    app.include_router(wp_g_ecl_router, tags=["wp-g-ecl"])

    # ═══ §76. G 投资循环：G-F11 金融资产分类辅助 ═══
    from app.routers.wp_g_classification import router as wp_g_classification_router
    app.include_router(wp_g_classification_router, tags=["wp-g-classification"])

    # ═══ §77. J 职工薪酬循环：J-F7 薪酬计提引擎 ═══
    from app.routers.wp_j_payroll_calc import router as wp_j_payroll_calc_router
    app.include_router(wp_j_payroll_calc_router, tags=["wp-j-payroll"])

    # ═══ §78. J 职工薪酬循环：J-F8 股份支付 Black-Scholes ═══
    from app.routers.wp_j_share_payment import router as wp_j_share_payment_router
    app.include_router(wp_j_share_payment_router, tags=["wp-j-share-payment"])

    # ═══ §79. K 管理循环：K-F7 销售/管理费用分析引擎 ═══
    from app.routers.wp_k_expense_analysis import router as wp_k_expense_analysis_router
    app.include_router(wp_k_expense_analysis_router, tags=["wp-k-expense-analysis"])

    # ═══ §80. K 管理循环：K-F8 K11 资产减值损失跨循环汇总 ═══
    from app.routers.wp_k_impairment_summary import router as wp_k_impairment_summary_router
    app.include_router(wp_k_impairment_summary_router, tags=["wp-k-impairment-summary"])

    # ═══ §81. L 筹资循环：L-F7 利息自动测算引擎 ═══
    from app.routers.wp_l_interest_calc import router as wp_l_interest_calc_router
    app.include_router(wp_l_interest_calc_router, tags=["wp-l-interest"])

    # ═══ §82. L 筹资循环：L-F8 应付债券摊余成本引擎 ═══
    from app.routers.wp_l_bond_amortization import router as wp_l_bond_amortization_router
    app.include_router(wp_l_bond_amortization_router, tags=["wp-l-bond-amortization"])

    # ═══ §83. M 权益循环：M-F7 权益变动表引擎 ═══
    from app.routers.wp_m_equity_movement import router as wp_m_equity_movement_router
    app.include_router(wp_m_equity_movement_router, tags=["wp-m-equity-movement"])

    # ═══ §84. N 税金循环：N-F7 所得税费用测算引擎 ═══
    from app.routers.wp_n_income_tax_calc import router as wp_n_income_tax_calc_router
    app.include_router(wp_n_income_tax_calc_router, tags=["wp-n-income-tax"])
