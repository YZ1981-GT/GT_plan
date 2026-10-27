# D2 模板骨架槽位复用 + 双向回写提速 — Requirements

## 背景

- 重药安徽 D2-2 切「在线编辑」后，OO 里第 13~24 行是 12 行空白，业务数据从第 25 行开始。
  根因在平台引擎：`excel_materialize.plan_managed_writes` 把 store 里没有物理行的身份一律交给
  `_plan_row_shift` 追加在**最后一个有身份的行之后**（`insert_at = max(row_identity_by_row) + 1`），
  而模板骨架行（`GTROW-D22-0013..0024`）永不收敛 ⇒ 业务行全部排在 12 行骨架之后。
  该缺陷已登记为未修（`_archive/42-d2-online-edit-platform-closure/design.md` §7.5 第 3 条）。
- 旧 `d2-sync` 直写路径已坏（只重冻裸 `GT_FOOTER_ROW`，冻结键已改为 `GT_FOOTER_ROW_D22`），
  且 openpyxl 重写会丢 x14 数据验证、绕开 revision / room / 历史 ⇒ 不走「D2 专用脚本」，修通用引擎。
- OO→HTML 保存方向实测 15.4~22s（三次整册 extract 各约 4s），`_archive/44` 的 P4「去重复提取」延后未做。

## R1 骨架槽位复用（按表声明启用）

1. provider 声明启用的受管表，store 行在 substrate 上没有物理行时，**先**落进「空闲骨架槽位」，剩余的才结构性插行。
2. 空闲槽位 = 同时满足：骨架身份（`contracts.is_template_skeleton_identity`）∧ 本次 projection 未声明该身份
   ∧ 位于「最后一个已有物理行的 projection 声明行」**之后** ∧ 可编辑格与模板原值一致（`SkeletonBaseline.carries_user_content` 为假）。
3. 槽位按行号升序、store 行按声明序一一对应；剩余 store 行照旧插在最后一个有身份的行之后。
4. 被复用的行：隐藏 UUID 列改写为 store 行身份；每个非受保护字段写 projection 值，projection 没有该字段时整格清空
   （不得残留模板示例文字）；受保护格（公式 / auto_source / cross_sheet）不动。
5. 未声明启用的表：计划与产物逐字节不变。

## R2 完整性不降级

1. 身份保留门只豁免**本次计划写盘前声明**退役的骨架身份；非骨架身份即使被声明也不豁免。
2. 退役清单随 `MaterializeResult` 流到同一次提交的 roundtrip extract；Word adapter 与未退役路径的调用形态不变。
3. roundtrip 等值、未管理区域、footer 两门、单趟 / 逐趟两条物化路径的判据一律不改。

## R3 存量底稿刷新

1. 新增按底稿定位的重发布工具：从权威模板重新 instrument + 当前 store 走 `publish_first_generation`，
   产出新 revision / 新代际，业务内容不变；`--check` 只读预览，`--apply` 才写库。
2. 先只对重药安徽 D2 执行；和平药房两份底稿需用户确认后再执行。

## R4 OO→HTML 回写可见

1. 在 OO 里改一格后点「结构化视图」，表单必须显示新值；若会话有过编辑却只发了 leave、没有 forcesave，按缺陷修复。

2. 回调必须能落地：文档服务回调下载地址解析到不可达的 IPv6 时改用已校验的其他地址；
   落盘前被拒的回调要把对应 forcesave 请求结算掉（文档服务不会重发，留着会让 leave 永远 409）。

## R6 重开在线编辑必须打开最新版

1. 同一用户的 lease 未过期（关标签页 / 刷新 / leave 失败后再点在线编辑）时，确认最新基线必须成功：
   回传的 descriptor 等于 room 已认可的 client-confirmed 快照、且内容版本严格更新 ⇒ 旧确认作废、新确认生效。
2. 其余换基线仍拒绝：旧基线重放、room 未认可的基线、快照被拉回旧版本时的版本倒退。

## R5 提速（OO→HTML 方向）

1. 三方提取里 base 与 current 是同一 artifact 时只提取一次；提取结果按「adapter 提取口径 + artifact sha」缓存。
2. 缓存命中与冷提取结果逐字段相同（守卫）。
3. 改动前后用 `report_sync_switch_timings.py` 记录真实耗时。

## 验收

- Playwright 实测重药安徽 D2-2：OO 第一条业务数据在第 13 行，上方无空行；OO 改 C13 → 切回结构化视图看到新值 → 改回原值。
- 相关后端套件 + golden digest + 行数门通过。
