-- Publish every recipe stranded in draft.
--
-- persist() wrote status='draft' unconditionally, on the reasoning that a human
-- would confirm each import on a review screen. That screen was never built, so
-- draft became a state with no exit: the badge appeared on 100% of imports and
-- therefore distinguished nothing. The only accidental way out was opening the
-- edit form and saving, which is the one path that sets 'published'.
--
-- From here status is earned rather than assumed: schema.org imports and
-- high-confidence model extractions publish directly, and only a medium or low
-- confidence extraction is flagged. See handlers.status_for.
--
-- Existing rows cannot be re-judged, because the model's confidence was logged
-- and never stored. Publishing them is the honest default: they have been sitting
-- in the library being looked at, and leaving them flagged would carry forward
-- exactly the noise this removes. A genuinely bad import is still editable and
-- deletable.

UPDATE recipes SET status = 'published' WHERE status = 'draft';
