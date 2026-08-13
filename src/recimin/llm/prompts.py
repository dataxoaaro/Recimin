"""Extraction prompts, versioned as constants so a change is reviewable."""

from recimin.llm.schema import CATEGORY_KEYS, SUGGESTED_TAGS

_SHARED_RULES = f"""
Rules that apply to everything you return:

CATEGORY. Choose exactly one of: {", ".join(CATEGORY_KEYS)}.
TAGS. At most 6, chosen from: {", ".join(SUGGESTED_TAGS)}. Omit rather than invent.
LANGUAGE. "fi" if the recipe is in Finnish, otherwise "en". Do not translate.

INGREDIENTS. Keep the author's own wording in raw_text. Also fill qty, unit and
item where you can; leave them null where you cannot. Never drop a line you do
not understand — put it in raw_text and leave the parsed fields null.

ALTERNATIVES. A line ending in "TAI" or "or" introduces a choice, not a second
ingredient. Set alternative_of on the following line to the position of the one
it replaces, so a shopping list does not buy both.

UNITS. Convert to metric, and set original_text to the pre-conversion line
whenever you do.
  - Volumes of liquid: cups/tbsp/tsp to ml by exact arithmetic.
  - Dry bulk (flour, sugar, butter, rice): to grams, using the conventions of
    the recipe's OWN country. A US recipe's cup of flour is about 120 g.
  - Finnish units are already metric. Leave dl, rkl, tl, kpl, g, kg, ml and l
    exactly as written. Note tl is 5 ml and rkl is 15 ml, which is NOT the same
    as a US tsp or tbsp.

INSTRUCTIONS. Markdown, one numbered step per line. Preserve the method's
order. Do not invent steps that are not shown or described.

CONFIDENCE. "high" only when the ingredients and method were both stated
explicitly. "low" when you inferred substantially. Say low rather than guess
confidently — a human reviews this before it is saved.
""".strip()


WEB_FALLBACK = f"""
You are extracting a recipe from the readable text of a web page. The page had
no usable structured data, so this text is all there is.

Return only what the page actually says. If it is not a recipe, return an empty
ingredients list and a confidence of "low".

{_SHARED_RULES}
""".strip()


SOCIAL_EXTRACTION = f"""
You are extracting a recipe from a social media post: its caption, its audio,
and a series of frames sampled evenly through the video.

The caption often does not contain the recipe. Ingredient amounts are usually
either spoken aloud or shown as on-screen text. Read the frames carefully for
ingredient cards and quantity overlays — that is normally where the real
information is.

Combine all three sources. Where they disagree, prefer on-screen text for
quantities and the audio for method.

{_SHARED_RULES}
""".strip()


def user_message(caption: str, transcript: str, page_text: str) -> str:
    """Assemble the text part of the request."""
    parts = []
    if caption:
        parts.append(f"CAPTION:\n{caption}")
    if transcript:
        parts.append(f"TRANSCRIPT:\n{transcript}")
    if page_text:
        parts.append(f"PAGE TEXT:\n{page_text}")
    return "\n\n".join(parts) if parts else "(no text available; use the frames)"
