-- R218：撤销 V218（粗裁确认当前态投影）。
-- 只删派生投影；已消费的 trim 预览凭证是不可变真源，原样保留。
-- 回滚须与旧代码一起部署：旧读法按预览凭证扫描确认状态，结果与投影一致（V218 回填自检保证）。

DROP TABLE IF EXISTS procedure_trim_cycle_confirmations;
