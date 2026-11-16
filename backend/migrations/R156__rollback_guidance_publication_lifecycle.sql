-- R156: 回滚 V156（guidance publication lifecycle）。
DO $$
BEGIN
    IF (to_regclass('public.guidance_publication') IS NOT NULL AND EXISTS (SELECT 1 FROM guidance_publication LIMIT 1))
       OR (to_regclass('public.guidance_publication_event') IS NOT NULL AND EXISTS (SELECT 1 FROM guidance_publication_event LIMIT 1))
       OR (to_regclass('public.project_guidance_supplement') IS NOT NULL AND EXISTS (SELECT 1 FROM project_guidance_supplement LIMIT 1))
       OR (to_regclass('public.guidance_exemption_record') IS NOT NULL AND EXISTS (SELECT 1 FROM guidance_exemption_record LIMIT 1)) THEN
        RAISE EXCEPTION 'R156 拒绝回滚：guidance 发布/事件/项目补充/豁免数据存在';
    END IF;
END $$;
DROP TABLE IF EXISTS project_guidance_supplement;
DROP TABLE IF EXISTS guidance_exemption_record;
DROP TABLE IF EXISTS guidance_publication_event;
DROP TABLE IF EXISTS guidance_publication;
