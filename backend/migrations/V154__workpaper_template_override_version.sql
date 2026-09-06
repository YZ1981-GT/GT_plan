-- V154: Excel 模板覆盖层版本表
--
-- Spec: excel-template-override-layer-and-onlyoffice-template-editor / Wave 3 Task 10
-- Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
-- Design: §Data Models（版本表）
-- Properties: P16（每次保存产生接父版本的新版本）、P17（回滚取历史版本且不删行）、
--             P18（并发下当前版本恰一条）、P19（删除覆盖后回落到权威文件）
--
-- 迁移号实扫（实施前，2026-09-04）：backend/migrations 共 153 个 V*.sql，最大号 V153
-- （V153__workpaper_representation_candidate_attach_event.sql）⇒ 本迁移为 V154，无撞号。
-- R1xx__ 是配对回滚脚本，不占 V 号。配对回滚：R154__rollback_workpaper_template_override_version.sql
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 约定（沿用 V151 的四条）
-- ═══════════════════════════════════════════════════════════════════════════
-- 1. MigrationRunner 把整个文件放在**一个事务**里逐语句执行 ⇒ 不写 BEGIN/COMMIT，
--    不使用 PG enum（同事务内 `ALTER TYPE ADD VALUE` 后不可立即使用），一律 VARCHAR + CHECK。
-- 2. 幂等：CREATE TABLE/INDEX 用 IF NOT EXISTS；ADD CONSTRAINT 用 pg_constraint DO 守卫；
--    函数 CREATE OR REPLACE；触发器 CREATE OR REPLACE TRIGGER。
-- 3. additive-only：不 DROP 任何既有表/列，不改任何业务值。
--    **本迁移不碰 `wp_template` / `template_library` 已有列**（Requirement 7.5）。
-- 4. sha256 合法性复用 V151 建立的 `wpsync_is_digest()` 单一真源（非空 + 64 位小写 hex
--    + 非全零）。V151 < V154 ⇒ MigrationRunner 按序执行时该函数必已存在，不再抄一份正则。
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 为什么有 authoritative_stem 这一列
-- ═══════════════════════════════════════════════════════════════════════════
-- 一个 wp_code 可以对**多份**权威文件（如 D2 对 `D2-1至D2-4 …xlsx` 等）。
-- `find_template_file` 取其中的"主"文件，`find_all_template_files` 取全部。若覆盖只按
-- wp_code 标识，覆盖主文件后两个入口会返回**不同**的文件。故覆盖的粒度是
-- 「(wp_code, 权威文件 stem)」而不是 wp_code —— 与 `wp_template_override.override_dir_for()`
-- 的目录布局 `{scope_seg}/{wp_code}/{authoritative_stem}/current{ext}` 一一对应。

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. 版本表
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS workpaper_template_override_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wp_code TEXT NOT NULL,
    -- 被覆盖的权威文件名主干（不含扩展名），见上文说明
    authoritative_stem TEXT NOT NULL,
    -- 取值复用 template_library_models.TemplateLevel 三档（design Gate 2：
    -- 平台无独立事务所实体，但该枚举已定义这三档，不新造 OverrideScope）
    scope VARCHAR(20) NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE RESTRICT,
    group_id UUID,
    -- 相对 OVERRIDE_ROOT（= backend/storage/template_overrides/）的路径
    file_relpath TEXT NOT NULL,
    extension VARCHAR(10) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT false,
    parent_version_id UUID REFERENCES workpaper_template_override_version(id) ON DELETE RESTRICT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_wptov_scope CHECK (scope IN ('firm_default', 'group_custom', 'project')),

    -- 🔴 三值逻辑：必须显式写 IS NOT NULL / IS NULL 两侧。只写 `scope <> 'project' OR ...`
    --    时 NULL 会让整条 CHECK 求值为 NULL（= 视为满足），作用域缺 id 将被静默放行 ——
    --    与 V151 的 ck_wpsda_authority_model_type 同一条教训。
    CONSTRAINT ck_wptov_scope_ids CHECK (
        (scope = 'project'      AND project_id IS NOT NULL AND group_id IS NULL)
     OR (scope = 'group_custom' AND group_id   IS NOT NULL AND project_id IS NULL)
     OR (scope = 'firm_default' AND project_id IS NULL     AND group_id IS NULL)
    ),

    CONSTRAINT ck_wptov_sha256 CHECK (wpsync_is_digest(sha256)),
    CONSTRAINT ck_wptov_wp_code_non_empty CHECK (length(btrim(wp_code)) > 0),
    CONSTRAINT ck_wptov_stem_non_empty CHECK (length(btrim(authoritative_stem)) > 0),

    -- 扩展名门（Requirement 2.6）在 DB 层也留一道：小写、以点开头、且与 relpath 后缀一致。
    -- 应用层 `stage_override` 是第一道，这里是「有人绕过应用层直接写库」时的兜底。
    CONSTRAINT ck_wptov_extension_form CHECK (extension ~ '^\.[a-z0-9]+$'),
    CONSTRAINT ck_wptov_relpath_matches_extension CHECK (file_relpath LIKE '%' || extension),

    -- 越界门（Requirement 1.1）在 DB 层的兜底：相对路径不得穿越、不得是绝对路径、
    -- 不得含反斜杠（统一用 / 存储，避免同一份文件两种写法绕过 uq_wptov_file_relpath）。
    --
    -- 🔴 反斜杠这条**不能**写成 `NOT LIKE '%\%'`：PG 的 LIKE 默认以 `\` 为转义字符，
    --    `\%` 会被解释成「字面量 %」，于是模式变成「任意字符 + 一个 % 字符」——
    --    `a\b.xlsx` 不含 % ⇒ NOT LIKE 为真 ⇒ 反斜杠**原样放行**。
    --    干跑实测：34 项断言里只有这一条判 FAIL，正是被这个转义规则骗过去的。
    --    改用 position()，不涉及模式转义。
    CONSTRAINT ck_wptov_relpath_no_escape CHECK (
        file_relpath NOT LIKE '%..%'
        AND file_relpath NOT LIKE '/%'
        AND position('\' in file_relpath) = 0
        AND file_relpath !~ '^[A-Za-z]:'
        AND length(btrim(file_relpath)) > 0
    ),

    CONSTRAINT ck_wptov_no_self_parent CHECK (parent_version_id IS NULL OR parent_version_id <> id)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. is_current 唯一性 —— 部分唯一索引（Requirement 4.4）
-- ═══════════════════════════════════════════════════════════════════════════
--
-- 🔴 用**索引**而不是应用层检查：Requirement 4.4 要求在**并发**下成立，
--    "先 SELECT 再 UPDATE" 的应用层检查在并发下必失效（两个事务都读到 0 条当前版本）。
--
-- 三档作用域的 NULL 语义不同（project 用 project_id、group_custom 用 group_id、
-- firm_default 两者皆 NULL），而 Postgres 的唯一索引对 NULL **不去重** ⇒ 若直接把
-- project_id/group_id 放进索引列，firm_default 下可以插入任意多条 is_current=true。
-- 故按 design 的裁决用 COALESCE 归一到全零 UUID 后建**一条**索引（比三条部分索引更难漏，
-- 且 WHERE is_current 只写一次）。
CREATE UNIQUE INDEX IF NOT EXISTS uq_wptov_one_current_per_scope
    ON workpaper_template_override_version (
        wp_code,
        authoritative_stem,
        scope,
        COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(group_id,   '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_wptov_lookup
    ON workpaper_template_override_version (wp_code, authoritative_stem, scope);
CREATE INDEX IF NOT EXISTS idx_wptov_project ON workpaper_template_override_version (project_id);
CREATE INDEX IF NOT EXISTS idx_wptov_group ON workpaper_template_override_version (group_id);
CREATE INDEX IF NOT EXISTS idx_wptov_sha256 ON workpaper_template_override_version (sha256);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wptov_file_relpath
    ON workpaper_template_override_version (file_relpath);

COMMENT ON TABLE workpaper_template_override_version IS
    'V154 Excel 模板覆盖层版本台账：权威目录 backend/wp_templates/ 保持字节冻结，编辑产物落 '
    'backend/storage/template_overrides/ 并在此登记版本。覆盖粒度是 (wp_code, 权威文件 stem) '
    '而非 wp_code —— 一个 wp_code 可对多份权威文件。is_current 唯一性靠部分唯一索引而非应用层检查。';
COMMENT ON COLUMN workpaper_template_override_version.authoritative_stem IS
    '被覆盖的权威文件名主干（不含扩展名）。与 wp_template_override.override_dir_for() 的目录布局一一对应';
COMMENT ON COLUMN workpaper_template_override_version.is_current IS
    '参与解析的当前版本。回滚 = 把某历史版本置 true（不删行）；删除覆盖 = 该作用域下全部置 false';
COMMENT ON COLUMN workpaper_template_override_version.parent_version_id IS
    '保存前的当前版本（首版为 NULL）。Property 16 断言每次保存都接上它';

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. 不可变列 + 禁止物理删除（Requirement 4.3）
-- ═══════════════════════════════════════════════════════════════════════════
--
-- 版本记录是审计证据：只有 is_current 可变。改 sha256/relpath 等于把"某版本的内容"
-- 悄悄换掉，历史复核就失去意义。

CREATE OR REPLACE FUNCTION wptov_check_immutable() RETURNS trigger AS $fn$
BEGIN
    IF NEW.wp_code IS DISTINCT FROM OLD.wp_code
       OR NEW.authoritative_stem IS DISTINCT FROM OLD.authoritative_stem
       OR NEW.scope IS DISTINCT FROM OLD.scope
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.group_id IS DISTINCT FROM OLD.group_id
       OR NEW.file_relpath IS DISTINCT FROM OLD.file_relpath
       OR NEW.extension IS DISTINCT FROM OLD.extension
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.parent_version_id IS DISTINCT FROM OLD.parent_version_id
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION
            'workpaper_template_override_version 除 is_current 外全部列不可变（id=%）—— '
            '版本记录是审计证据，改内容身份等于抹掉历史', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wptov_immutable
    BEFORE UPDATE ON workpaper_template_override_version
    FOR EACH ROW EXECUTE FUNCTION wptov_check_immutable();

CREATE OR REPLACE FUNCTION wptov_forbid_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION
        'workpaper_template_override_version 禁止物理删除（id=%）—— Requirement 4.3：'
        '回滚只改 is_current，删除覆盖 = 该作用域下全部 is_current=false', OLD.id
        USING ERRCODE = 'restrict_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wptov_forbid_delete
    BEFORE DELETE ON workpaper_template_override_version
    FOR EACH ROW EXECUTE FUNCTION wptov_forbid_delete();

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. parent 必须同 (wp_code, stem, scope) —— 版本链不得跨作用域
-- ═══════════════════════════════════════════════════════════════════════════
--
-- 跨作用域接父版本会让「事务所级的历史」混进「项目级的链」，回滚时取到别的作用域的文件。

CREATE OR REPLACE FUNCTION wptov_check_parent_same_scope() RETURNS trigger AS $fn$
DECLARE
    v_code text;
    v_stem text;
    v_scope text;
    v_project uuid;
    v_group uuid;
BEGIN
    IF NEW.parent_version_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT wp_code, authoritative_stem, scope, project_id, group_id
      INTO v_code, v_stem, v_scope, v_project, v_group
      FROM workpaper_template_override_version WHERE id = NEW.parent_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'parent_version_id % 不存在', NEW.parent_version_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_code <> NEW.wp_code
       OR v_stem <> NEW.authoritative_stem
       OR v_scope <> NEW.scope
       OR v_project IS DISTINCT FROM NEW.project_id
       OR v_group IS DISTINCT FROM NEW.group_id THEN
        RAISE EXCEPTION
            '版本链不得跨作用域：新版本 (%/%/%) 的父版本落在 (%/%/%)',
            NEW.wp_code, NEW.authoritative_stem, NEW.scope, v_code, v_stem, v_scope
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_wptov_parent_same_scope
    BEFORE INSERT OR UPDATE ON workpaper_template_override_version
    FOR EACH ROW EXECUTE FUNCTION wptov_check_parent_same_scope();
