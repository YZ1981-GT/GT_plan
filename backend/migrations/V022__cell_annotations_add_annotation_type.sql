-- V022: Add annotation_type column to cell_annotations
-- Required by wp_review_status.py which filters on annotation_type = 'review_mark'

ALTER TABLE cell_annotations ADD COLUMN IF NOT EXISTS annotation_type VARCHAR(50) NOT NULL DEFAULT 'comment';

-- Index for the review_status query (JOIN + FILTER on annotation_type)
CREATE INDEX IF NOT EXISTS idx_cell_annotations_type_object
    ON cell_annotations(object_id, annotation_type)
    WHERE is_deleted = false;
