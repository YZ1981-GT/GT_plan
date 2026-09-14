"""H1-9 监盘计划 Word 导出冒烟测试"""
from app.routers.wp_render_strategies._h1_stocktake_plan_export import build_plan_docx


def test_build_plan_docx_bytes():
    data = build_plan_docx(
        {
            "existenceRiskLevel": "中",
            "existenceRiskNote": "控制有效",
            "plannedDate": "2025-12-31",
            "plannedLead": "张三",
            "method": "抽样盘点",
            "categoryScopes": [
                {
                    "category": "机器设备",
                    "endingBalance": 1000,
                    "netBookValue": 800,
                    "planQty": 5,
                    "planAmount": 400,
                    "coverageRate": 50,
                }
            ],
            "planConclusion": "计划适当，可执行。",
        },
        entity_name="测试公司",
    )
    assert isinstance(data, (bytes, bytearray))
    assert len(data) > 1000
    # docx zip signature
    assert data[:2] == b"PK"
