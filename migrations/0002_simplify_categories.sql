-- Collapse thirteen recipe categories into six.
--
-- The filter row no longer fitted a phone screen, and the distinctions being
-- drawn were not ones anyone makes when deciding what to cook. Mapping is
-- lossy by intent; the pairs below are the ones judged not worth a filter of
-- their own at household scale.
--
-- The column's DEFAULT still reads 'main_course'. Changing it means rebuilding
-- a table that carries eight FTS5 sync triggers, which is a far larger risk
-- than the default itself poses: every insert path supplies a category
-- explicitly, so it never fires. recimin.db.categories.LEGACY_ALIASES resolves
-- the old key anyway, should it ever reach the application.

UPDATE recipes
SET category = CASE category
    WHEN 'main_course' THEN 'dinner'
    WHEN 'soup'        THEN 'dinner'
    WHEN 'side_dish'   THEN 'dinner'
    WHEN 'appetizer'   THEN 'dinner'
    WHEN 'sauce'       THEN 'dinner'
    -- No successor describes a drink. Mapped rather than dropped; there were
    -- no drink recipes when this ran.
    WHEN 'drink'       THEN 'dinner'
    WHEN 'bread'       THEN 'savoury_baking'
    WHEN 'dessert'     THEN 'sweet_baking'
    ELSE category
END
WHERE category IN (
    'main_course', 'soup', 'side_dish', 'appetizer', 'sauce',
    'drink', 'bread', 'dessert'
);
