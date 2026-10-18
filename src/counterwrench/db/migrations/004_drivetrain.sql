-- Drivetrain facts the compatibility engine needs for derailleurs and chains.
--
-- shift_family: cable pull (or electronic protocol) differs between families, so a
-- derailleur only works with shifters of a compatible family; it's not just Shimano vs SRAM
-- (e.g. Shimano road 10 vs Tiagra 4700/GRX 10, MTB Dyna-Sys vs road).
--
-- required_chain_type: shops fit a SRAM chain of the right speed to almost anything, so
-- this is set only for drivetrains that demand a specific chain (SRAM Flattop, T-Type).

ALTER TABLE bikes
    -- Temporary default so existing rows satisfy NOT NULL; dropped below. `make seed` always
    -- runs right after `migrate` and overwrites it with the real value.
    ADD COLUMN shift_family text NOT NULL DEFAULT 'unset',
    ADD COLUMN required_chain_type text
        CHECK (required_chain_type IN ('sram_flattop', 'sram_t_type'));

ALTER TABLE bikes ALTER COLUMN shift_family DROP DEFAULT;
