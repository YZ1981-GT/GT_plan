-- R161: 回滚 checklist_responses.content_version 乐观锁版本列
--
-- 删除 V161 增加的列。删除后并发导入回退为 last-write-wins（旧行为），无数据丢失
-- （content_version 仅为并发控制元数据，不承载业务内容）。

ALTER TABLE checklist_responses
    DROP COLUMN IF EXISTS content_version;
