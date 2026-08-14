-- Listing indexes, matched to the queries the app actually runs.

-- GET /api/imports is polled every 3 seconds by the Imports screen and runs
-- ORDER BY created_at DESC, id DESC LIMIT 50 with no filter. The only index
-- was (status, created_at), which cannot serve an unfiltered sort, so every
-- poll scanned the whole table into a temp B-tree — and nothing ever deleted
-- jobs, so the table only grew. The worker now prunes old terminal jobs too;
-- this index makes the poll an index walk either way.
CREATE INDEX idx_jobs_created ON jobs(created_at DESC, id DESC);

-- The library lists with the same two-key ORDER BY; the old single-column
-- index left the id tie-break to a temp B-tree on every page load.
DROP INDEX idx_recipes_created;
CREATE INDEX idx_recipes_created ON recipes(created_at DESC, id DESC);

-- A status-filtered listing (the review view) matched on the old
-- single-column index and then sorted every match in a temp B-tree. Most
-- recipes share one status, so that was nearly the whole table. The composite
-- serves the filter and the sort together.
DROP INDEX idx_recipes_status;
CREATE INDEX idx_recipes_status ON recipes(status, created_at DESC);
