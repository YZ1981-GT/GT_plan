# 需求：46 个预存失败用例逐一收口

2026-10-20 现跑（`backend` 下 12 个测试文件）：46 failed。来源分三类：生产代码偏离了正确行为、测试没跟上后来有意的改动、测试环境不封闭（真调外部服务 / 依赖库里数据）。本 spec 逐例定根因、修根因；判据不放宽。

## 范围

| 组 | 文件 | 例数 |
|----|------|------|
| G1 | `tests/test_wopi_working_paper_qc_review.py` | 15 |
| G2 | `tests/test_index_source.py` | 7 |
| G3 | `tests/test_ai_content_structured.py` | 4 |
| G4 | `tests/dsh_agent_panel/test_task4_run_contract.py` | 3 |
| G5 | `tests/test_g7_sub_integration.py` | 3 |
| G6 | `tests/test_qc_rule_definitions_loader.py` | 3 |
| G7 | `tests/test_a16_sign_status_check_auto.py` | 2 |
| G8 | `tests/test_archive_deprecated.py` | 2 |
| G9 | `tests/test_g1_classification.py` | 2 |
| G10 | `tests/test_ocr_service.py` | 2 |
| G11 | `tests/test_startup_registry.py` | 2 |
| G12 | `tests/test_review_prompt_integration.py` | 1 |

（另 3 例 `test_dsh_discovery_task27.py` 已在 `dsh-kb-ocr-local-first-routing` Task 2 修复：vendor 根目录改为 pin 检出。）

## Requirement 1：每例先定根因再动手

1.1 每组在 design 里写明：现象（失败信息原文）、根因（代码位置 + 证据）、判定（生产缺陷 / 测试过时 / 测试不封闭）、修法。

1.2 判定为生产缺陷的，修生产代码，并补一条能单独抓住该缺陷的测试；判定为测试过时的，按现行设计改成**精确**断言（集合相等、具体值），并写明是哪次改动让它过时；禁止改成 `>=`、`in`、跳过或 xfail 来过关。

1.3 测试不得真调外部服务（LLM / OCR / 网络）或依赖开发库里恰好存在的数据；需要的数据由夹具建立。

## Requirement 2：修复不扩大影响

2.1 生产代码改动只动根因所在处；触及的同类写法全仓 grep 后一并处理，或登记为不在本轮范围（写明数量与原因）。

2.2 新增 / 改动的守卫逐条做变异证明（磁盘注入，逐字节恢复）。

2.3 跑完 12 个文件全绿；跑相邻测试（同模块的其它测试文件）确认无新增失败。

## Requirement 3：需要裁决的事项如实标出

3.1 修法涉及口径变化（覆盖率怎么算、字段清单以哪个为准）的，在 design 里列出选项与依据，按现行代码与 spec 的原意实施，并在最终汇报里提请确认。
