# 双向回写 CPU 热点与事件循环阻塞 — Tasks

- [x] 1. 契约键索引（R2）
  - [x] 1.1 `SyncContract.template_candidate_indices`
  - [x] 1.2 `assert_matches_contract` / `ContractIndex.resolve` / `_resolve_stable_key` 改走候选
- [x] 2. 物化单格解析（R1）：`_cell_view` 字面前缀 + 预编译尾部正则
- [x] 3. 去重复提取（R3）：current 同 artifact 复用；published 形态不算 baseline、base 主 binding 填 baseline 缓存
- [x] 4. 事件循环（R4）：三方提取与合并移到工作线程
- [x] 5. 守卫与变异（R5.1）：`test_save_path_cpu_hotspots.py` 62 例；磁盘变异 11/11；179 个相关文件 HEAD 对比零新增失败（首轮 4 条新增均已修，见 D2 spec 勘误）；golden digest 242 不变；行数门过
- [x] 6. 实测（R5.2 / R5.3）：离线四个摘要不变，CPU 链 14.07 → 6.69 s；浏览器保存回表单 20.5 → 13.0 s、不改内容打开服务端 2.92 → 0.65 s；HTML 改过再打开只有离线前值（见 design §8）；测试编辑已还原（投影摘要回到 `4ba8628f…`）
- [x] 7. 收尾：本文件 / INDEX.md / memory.md，`git add`（不提交，INDEX / memory 只暂存本会话的行），清理探针与对照 worktree
