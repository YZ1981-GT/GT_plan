-- R153: 回滚 V153（底稿 representation candidate attach event）。
DO $$
BEGIN
    IF to_regclass('public.working_paper_representation_candidate_event') IS NOT NULL
       AND EXISTS (SELECT 1 FROM working_paper_representation_candidate_event LIMIT 1) THEN
        RAISE EXCEPTION 'R153 拒绝回滚：candidate attach/refused 审计事件存在';
    END IF;
END $$;
DROP TRIGGER IF EXISTS trg_wprce_append_only ON working_paper_representation_candidate_event;
DROP TABLE IF EXISTS working_paper_representation_candidate_event;
