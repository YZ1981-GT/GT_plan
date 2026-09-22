# 任务：OO 物化单趟写入 + participant 主动离开

**spec**：`oo-single-pass-materialize-and-room-leave`　**创建**：2026-09-22
**状态**：0/11（未开工；本 spec 由 2026-09-22 会话按用户指派创建，实施另起）

> 顺序有意义：阶段 1 是**调查 + 基线判据**，没有它后面的提速无法与「少写了东西」区分开。

## 阶段 1：基线与依赖调查

- [ ] 1. 把「39 趟」钉成测试判据
  - 在真库 D4 entry 上对 `openpyxl.load_workbook` / `Workbook.save` 打桩计数，落一条
    **当前行为**的基线测试（先断言 `== 39`，单趟化落地后改为 `== 1`）
  - 同时记录单次物化的墙钟耗时与内存峰值到 `docs/operations/evidence/`
  - _Requirements: 1.1, 1.5_

- [ ] 2. binding 顺序依赖调查（**结论进 design.md 附录，不写代码**）
  - 逐 binding 检查是否存在「读取前一 binding 写入结果」的情形（公式落格、跨 sheet 引用、
    命名区域）
  - 输出：有依赖的 binding 清单 + 是否可拓扑排序；无依赖则显式记录「实证无依赖」
  - _Requirements: 1.2_

## 阶段 2：单趟写入

- [ ] 3. 实现单趟写入路径（一次 load → 全部 binding → 一次 save）
  - 保留旧链式实现于**同一个**函数内不可达分支是禁止的：切换后直接删旧路径（删前 grep
    零调用方 + 独立 commit）
  - _Requirements: 1.1, 1.2_

- [ ] 4. 新旧产物等值判据（P2）
  - 同一份 projection 分别走旧链式（git 检出的历史实现或等价模拟）与新单趟，`extract`
    结果逐字段比对
  - _Requirements: 1.2_

- [ ] 5. 失败原子性（P3）
  - 在第 k 个 binding 注入异常，断言：无 staged artifact、临时目录扫描为空、DB 无半条记录
  - _Requirements: 1.3_

- [ ] 6. 句柄释放（Windows）
  - 单趟写入结束后 `release_scoped_workbooks(path)`，断言临时文件可被 `unlink`
  - _Requirements: 1.4_

- [ ] 7. 真库前后对照计时证据
  - 同一 wp / 同一 projection，改动前后各跑一次，登记证据文件；目标 ≤10s
  - _Requirements: 1.5_

## 阶段 3：解析复用

- [ ] 8. materialize / extract / verify 共用一个 `workbook_read_scope()`（P4）
  - 断言全流程对同一份字节的解析次数为 1；`data_only` 两种形态不得互相冒充
  - _Requirements: 2.1, 2.2_

- [ ] 9. verify 判据不放宽（P5）
  - 变异反证：产物少一个字段 ⇒ verify 必红
  - _Requirements: 2.3_

## 阶段 4：复用可观测

- [ ] 10. 复用命中/未命中进 metrics + 「连续两次必命中」守卫（P6）
  - 未命中原因至少三类可区分；digest 口径不一致这一类在 CI 判红
  - _Requirements: 3.1, 3.2, 3.3_

## 阶段 5：participant 主动离开

- [ ] 11. leave 路径（repository + service + 端点 + 前端接线）
  - `active/closing → left`，不建 request、不推 barrier、不旋转 generation（P7）
  - 幂等显式分支（P9）、dirty 拒绝（P8）、authorization-first 同 404 oracle
  - 前端 `leaveWithoutSaving()` 改为调用它，并把「零请求」判据更新为「恰一次 leave、
    零次 forcesave、零次 close-intent」
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
