
-- ============================================================
-- PROJECT: E-commerce Data Warehouse
-- MIGRATION: 02
-- PURPOSE: Persist rejected source records during ETL validation
-- MYSQL: 8.0+
-- ============================================================

USE ecommerce_dw;

CREATE TABLE IF NOT EXISTS etl_rejected_records (
    rejection_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    etl_run_id BIGINT NOT NULL,

    source_table VARCHAR(100) NOT NULL,

    staging_record_id BIGINT NOT NULL,

    source_record_id VARCHAR(100) NULL,

    rejection_reasons JSON NOT NULL,

    raw_record JSON NOT NULL,

    rejected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_rejected_records_etl_run
        FOREIGN KEY (etl_run_id)
        REFERENCES etl_pipeline_runs(run_id),

    CONSTRAINT uq_rejected_record_per_run
        UNIQUE (
            etl_run_id,
            source_table,
            staging_record_id
        ),

    INDEX idx_rejected_records_run_id (etl_run_id),

    INDEX idx_rejected_records_source (
        source_table,
        source_record_id
    ),

    INDEX idx_rejected_records_rejected_at (rejected_at)

) ENGINE=InnoDB;

-- ============================================================
-- END OF MIGRATION
-- ============================================================
