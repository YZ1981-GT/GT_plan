# Design — D4-4/8/12 gap closure

1. C0模板/identity：仅核定D4-4/8/12真实sheet、区域、wp_id稳定身份，并反向去重owner。
2. C1sync：为已核定表接入共享服务、三方冲突和applied确认。
3. C2formula：实现真实表内/表间DAG、custom/preset版本和fail-closed状态。
4. C3linkage：保留已有A13/调整、产品计算、合同OCR/AI，仅补真实联动接收端。
5. C4逐表验收：roundtrip、权限、Playwright、缺失/损坏公式及变异；只门控本spec相关产物。

## Correctness Properties
### Property 1
缺失owner的表才进入gap spec，已有owner表不会重复出现。
**Validates: Requirements 1.1, 1.2**
### Property 2
所有提交经共享服务，冲突保留三值与durable ack且不采用最后写胜出。
**Validates: Requirements 2.1**
### Property 3
公式按effective preset/custom与真实DAG执行，普通override不能充当公式库。
**Validates: Requirements 2.2**
### Property 4
每个已核定wp_code都有逐表roundtrip、权限和Playwright状态；UNVERIFIABLE不计通过。
**Validates: Requirements 3.1**
