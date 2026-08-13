/**
 * Derive cook-mode steps from the instructions markdown.
 *
 * Steps are never persisted. Instructions are stored as one markdown blob
 * because that is what a human can edit comfortably, and the stepper is
 * computed at render time — so gaining step tracking never needed a migration,
 * and losing it never would either.
 *
 * A blob with no list structure yields a single step. That is correct
 * behaviour, not a bug: some recipes really are one paragraph.
 */

const NUMBERED = /^\s*\d+[.)]\s+/;
const BULLET = /^\s*[-*•]\s+/;
const HEADING = /^\s*#{1,6}\s+/;

export function deriveSteps(markdown: string): string[] {
  const lines = markdown.split("\n");

  const listItems = lines
    .filter((line) => NUMBERED.test(line) || BULLET.test(line))
    .map((line) => line.replace(NUMBERED, "").replace(BULLET, "").trim())
    .filter(Boolean);

  if (listItems.length > 0) return listItems;

  // No list markers. Fall back to non-empty, non-heading paragraphs.
  const paragraphs = markdown
    .split(/\n\s*\n/)
    .map((block) => block.replace(HEADING, "").trim())
    .filter(Boolean);

  return paragraphs.length > 0 ? paragraphs : [];
}

/**
 * Scale a quantity for a new serving count.
 *
 * Rounds to something a person can actually measure. Nobody weighs 1.3333
 * eggs, and a recipe that displays that has made itself less useful than the
 * one it came from.
 */
export function scaleQuantity(qty: number, from: number, to: number): number {
  if (from <= 0 || to <= 0) return qty;
  const scaled = (qty * to) / from;

  if (scaled >= 100) return Math.round(scaled / 5) * 5;
  if (scaled >= 10) return Math.round(scaled);
  if (scaled >= 1) return Math.round(scaled * 4) / 4;
  return Math.round(scaled * 8) / 8;
}

/** Format a scaled quantity without trailing zeroes. */
export function formatQuantity(qty: number): string {
  return Number.isInteger(qty) ? String(qty) : String(Number(qty.toFixed(2)));
}

/**
 * Rewrite an ingredient line for a new serving count.
 *
 * Only lines with a parsed quantity scale. A raw-only line ("a pinch of salt")
 * is returned untouched — inventing a number for it would be worse than
 * leaving it alone.
 */
export function scaleLine(
  raw: string,
  qty: number | null,
  from: number | null,
  to: number,
): string {
  if (qty === null || from === null || from === to) return raw;

  const scaled = scaleQuantity(qty, from, to);
  const formatted = formatQuantity(scaled);

  // Replace only the first numeric run, which is the quantity. A number later
  // in the line ("400 g tin") belongs to the product, not the amount.
  const original = formatQuantity(qty);
  const pattern = new RegExp(`(^\\s*)${original.replace(".", "[.,]")}\\b`);
  if (pattern.test(raw)) return raw.replace(pattern, `$1${formatted}`);

  return `${formatted} × ${raw}`;
}
