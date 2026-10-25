# B 类共享基类载体通道 — 任务

> 判据一律引用 `b-cycle-sync-foundation-and-first-canary` 的 BC 编号，本文件不重复裁决。
> 推进顺序：先 b22 三条，后 b50（b50 宿主 2772 行且缺陷最多，依赖前三条经验）。

## 阶段 1：共享基类兼容改线

- [x] 1. 冻结 `useWorkpaperEntryDualMode.ts` 边归属基线
  - 断言全域 **26** 条生产边，B 域占 **5**（本组 4 + canary 1），其余 **21** 条属其他循环
  - 断言 4 条挂点行号 `#L29` / `#L32` / `#L24` / `#L30`
  - 断言 `becomes_orphan_after_rewire` 为**假**（与 `useWpDualMode` 相反）
  - _判据：BC-2、BC-58_

- [x] 2. 新增可选参数 + 缺省退回旧路径
  - 未传新参数时走改线前逻辑，传入时走权威源解析
  - 断言其余 21 条生产边行为不变（快照测试）
  - _判据：BC-2_

- [x] 3. 按 entry 粒度回滚能力
  - 4 条 entry 的 `capability` 可独立置 `bidirectional` / 退回 `null`
  - 断言单条回滚不影响其余 3 条与 canary
  - _判据：BC-2、BC-58_

## 阶段 2：`B22B` 一码双 entry 消歧

- [x] 4. componentType 作归属主键
  - 断言 `xlsx/gt-b22-b-control-matrix` 与 `xlsx/gt-b22-b-deficiency-evaluation` 共用 pattern `B22B` 但 componentType 不同、宿主文件不同
  - 断言 `gt-b22-b-deficiency-evaluation` 的 `wp_code_count_via_component_type` 为 **0**
  - 断言这是 A 域 BP-11 的对偶形态
  - _判据：BC-45、BC-15_

- [x] 5. 显式册映射替代 fallback
  - 不走 `props.wpCode || 'B22B'`，改用 componentType → 显式册映射
  - 为 override 零命中的 deficiency 侧补显式映射项
  - 断言映射结果不依赖 finder 内部排序
  - _判据：BC-50、BC-51、BC-52_

- [x] 6. `item_id` 命名空间分离确认
  - 断言真库 `B22B` 13 行全为 `B22B-row-0-{12 字段}` + `B22B-row-count`，属控制矩阵形态
  - 确认并登记 deficiency 侧的 `item_id` 命名轴（真库分母为 0，须实测代码而非查库）
  - 断言两侧命名空间不重叠
  - _判据：BC-15、BC-19、BC-60_

## 阶段 3：行键与 `count` 键迁移

- [x] 7. 违规形态逐条冻结
  - 断言 `B22B-row-{n}`（0-based，12 字段/行）与 `B22C-env-def-{n}`（1-based，4 字段）两种基准并存
  - 断言 `idx` 形参出现在 3 个宿主（deficiency / b22c / b50）
  - 断言 label 作 key **4** 处全在 `GtB50RiskAssessment.vue`（`#L1475` `row.name` / `#L1499` `` `${row.name}-${a}` `` / `#L1577` `grp.label` / `#L1792` `row.name`）
  - _判据：BC-53、BC-56、BC-48_

- [x] 8. 行键改稳定 id（参照 B60 pilot 的 `rowUuid` 形态）
  - 新行生成携带稳定 id，不复用数组下标
  - `:key` 改绑稳定 id，`row.name` / `grp.label` 仅作显示
  - _判据：BC-53、BC-6_

- [x] 9. 存量数据迁移脚本（两种基准分别处理）
  - `B22B-row-{n}` 按 0-based、`B22C-env-def-{n}` 按 1-based 分别映射
  - 🔴 禁止统一假设编号基准
  - 迁移前后断言行数与内容逐值一致
  - _判据：BC-56、BC-54_

- [x] 10. `count` 键降级为校验值
  - 读取时断言 `count` == 实际行键数量，不一致报错而非静默取小值
  - 断言真库三种 count 键中本组两种：`B22B-row-count` / `B22C-env-def-count`
  - 断言前端 `count` 持久化 13 处中本组占 b22c 与 b50 两个宿主
  - _判据：BC-54_

- [x] 11. 熵键替换（`gt-b22-b-deficiency-evaluation` 单点）
  - 定位该宿主 **1** 处熵键并确认用途
  - 替换为稳定 id（渲染 key 用熵键会致 DOM 每次重建；持久化键用熵键会致数据无法二次定位）
  - _判据：BC-53_

## 阶段 4：门控与持久化通道

- [x] 12. 门控假阴修正（`gt-b50-risk-assessment`）
  - 用 foundation 的祖先链 × 递归 v-else 回溯口径断言 b50 的 OO 挂点被 mode 门控
  - 断言仅自身口径会漏判该条（本组唯一假阴）
  - _判据：BC-13、BC-11_

- [x] 13. 持久化通道深度登记
  - 断言 D0 两条（`gt-b22-b-deficiency-evaluation` / `gt-b22-c-design-effectiveness` 宿主内直调 `/checklist-responses`）
  - 断言 D1 两条（`gt-b22-b-control-matrix` → `useB22BControlMatrix.ts`；`gt-b50-risk-assessment` → `useB50FormData.ts`）
  - 断言 `gt-b50-risk-assessment` 的 localStorage 在 **D1**（`useB50DetailColumnPrefs.ts`），为全 B 域最浅
  - _判据：BC-42、BC-3_

- [x] 14. `GRP-05` 通道实测（不可推演）
  - 断言 `gt-b50-risk-assessment` 为 `GRP-05`，其余 3 条 `GRP-04`
  - 断言 `field-overrides` 在前端闭包深度 3 内命中 **0**
  - 实测确认该通道走后端或已废弃，并登记结论
  - _判据：BC-43、BC-42_

- [x] 15. mode 值体系断言
  - 断言本组 4 条全用 `'onlyoffice'`，其中 b50 出现 **2** 次
  - 断言 4 条均**未**在宿主内声明 `modeOptions`（定义在共享载体内）
  - _判据：BC-41_

## 阶段 5：零分母 entry 验证

- [x] 16. 零分母声明与人造数据集
  - `gt-b50-risk-assessment` 真库 **0** 行、`gt-b22-b-deficiency-evaluation` 真库可归属载荷 **0** 行
  - 各造至少 **2** 行人工数据以暴露行键错位
  - 测试中显式声明「本 entry 真库分母为 0，验证基于人造数据」
  - 🔴 不得因分母为 0 跳过验证
  - _判据：BC-20、BC-60_

- [x] 17. 非零分母 entry 真实数据验证
  - `gt-b22-c-design-effectiveness`：断言真库 23 行 / remark 非空 7 / conclusion 非空 **1**（全 B 域唯一 conclusion 非空）
  - `gt-b22-b-control-matrix`：断言 `B22B` 13 行
  - 断言 remark 强 / conclusion 弱（BC-34 反转）在本组同样成立
  - _判据：BC-34、BC-60_

- [x] 18. 一码多册与 `wp_index` 一码多行制约
  - 断言 `wp_index` 中 `B22B` 3 行 / `B22C` 3 行 / `B50` **4** 行
  - 改线须显式确定使用哪一行并断言
  - 断言模板层 `B22B` / `B22C` / `B50` 各自的候选册数
  - _判据：BC-55、BC-50、BC-44_

- [x] 19. xlsm 与幽灵行制约核查
  - 断言 `B22B 了解企业层面控制 - 控制矩阵.xlsx` 报数据验证扩展警告（16 本受影响之一）
  - 遍历上界取 `last_value_row` 而非 `max_row`
  - _判据：BC-49、BC-35_

## 外部依赖（本轮不可标 completed）

- [ ]* 20. BP-1 ~ BP-5 五项全 slice 共有阻塞 —— 见 foundation tasks 26 ~ 30
- [ ]* 21. `gt-b50-risk-assessment` 与 `gt-b22-b-deficiency-evaluation` 的真实数据 UAT —— 待真库出现该 entry 载荷
