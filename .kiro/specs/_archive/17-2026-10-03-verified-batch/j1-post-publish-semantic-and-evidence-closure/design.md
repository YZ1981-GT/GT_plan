# J1 发布后语义与证据闭环 — 设计

## 裁决

- 模板 A17:A35 是固定业务字典，**模板原字节为权威**；前端默认行从同一 TS 常量输出，Python E2E 读取前端生成的 JSON，不再从 xlsx 反向自证。
- 固定骨架身份按 index 映射是模板坐标绑定，不是用户动态行位置身份；19 行以外不迁移。
- E2E 必须显式定位项目/底稿，并验证 active representation → bundle → 4 child digests → 净化后模板；JSON evidence 内容寻址并记录 source commit、DB fingerprint、OO version。
- capability evidence 门由独立检查器消费 evidence；普通无 PG/OO CI 跑静态门，真实环境 job 生成/校验 evidence。
- J1 provider 迁到 `phase5_h_cycle_common` 已有公共 facade；J 专属事实只保留 identity/spec/review。
- J2/J3 本轮只做可确定的工程清理；披露会计口径不擅自改值，但 owner/死读/旁路可修。

## 验证

1. Vitest：正负/零差异、模板原字节、错 namespace/错序身份、legacy 19 行迁移、18 行不猜。
2. 后端：contract/source、instrumentation identity、sanitizer 幂等、active artifact 无外链、evidence schema/commit/digest fail-closed。
3. 真栈：两轮 OO roundtrip + legacy-ID 变异；指定 project/wp；JSON evidence。
4. 安全：跨项目 403/404 不泄露；publication fault injection 回滚；重复运行不增行。
5. J2/J3：AST 可达性守卫、直写旁路清零、J3 dead-read 清零、状态/证据一致。

## 风险

- active bundle 更新涉及真库：先只读预演，再 apply，前后查数据。
- overlay/manifest 为多会话热点：独立 worktree 生成并检查 mount diff。
- 历史 artifact 不删；只标 active/historical/unreachable。