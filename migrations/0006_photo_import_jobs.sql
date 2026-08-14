-- Photo imports: a job whose input is uploaded images rather than a URL.
-- The images are stored by the api as orphan media rows before the job is
-- queued; this column carries their ids to the worker as a JSON array.
-- NULL for every URL import.
ALTER TABLE jobs ADD COLUMN media_ids TEXT;
