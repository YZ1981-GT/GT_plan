# J1 发布后语义与证据闭环 — 需求

## 目标

J1 已接真双向，但合并前必须消除复盘发现的语义偏差、假绿输入与不可复验状态，并诚实收口 J2/J3 剩余任务。

## Requirements

1. **金额语义**：HTML `diff` SHALL 与模板 `I=G-H=estimated-actual` 同号，`estimated` SHALL 按 Excel `ROUND(,2)`。
2. **标签权威**：`计提情况检查表J1-6!A17:A35` SHALL 是固定模板元数据；HTML 持久化/OO 写入使用模板原字节，不得用半角标点/去缩进/去换行版本覆盖。
3. **身份严格性**：19 条固定骨架第 i 行身份 SHALL 精确等于 `GTROW-J16S-{17+i:04d}`；错 namespace、错行号、错序均须换绑，异形行数 fail-safe 不猜。
4. **真实 E2E**：脚本 SHALL 强制显式 project_id + wp_id（或唯一选择），核 wp_code/current generation/current bundle 四 digest/净化模板/OO 版本，并输出机器可读 evidence JSON；使用真实前端骨架载荷而非模板自造标签。
5. **翻转门**：`published_representation_verified` SHALL 可追溯到与当前 commit、active bundle 一致的 evidence；缺失或过期 fail closed。
6. **净化门**：权威模板和 active frozen template 均无 externalLinks/External relationship；sanitizer 对已净化输入字节幂等。
7. **证据诚实**：旧 blocked evidence 保留但明确 superseded；tasks 不得同时写“完成/待裁决/未完成”；人工审核与自动 approved bundle 分开表述。
8. **J2/J3**：状态 SHALL 现算为 16/18；Task 14 拆登记完成/治理未完成；barrel 后孤儿、披露 owner、J3 幽灵读取/直写旁路逐项登记或修复，不误删 `useJ3ImportExport`。
9. **架构收敛**：J1 provider SHALL 委托公共 HC store/publish/registration 能力；重构前后 contract/instrumentation/projection golden digest 不变。
10. **安全与原子性**：补项目越权负例、首版发布中途失败回滚、重跑幂等/并发 CAS 证据；无证据不得宣称已验。