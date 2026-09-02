"""Text normalisation shared by the pattern-based detectors.

Real model output is *typographic*, not ASCII. A chat model writing a card number in a markdown list emits
narrow no-break spaces (U+202F) between the digit groups; writing "27-year-old" it emits a non-breaking
hyphen (U+2011). Patterns written with a plain ``" "`` or ``"-"`` silently miss both -- which is the worst
kind of detector bug, because it fails open: the leak or the biased phrasing sails through and the receipt
records a confident "no PII patterns matched".

Folding is strictly 1 character -> 1 character, so match offsets computed on the folded text index the
original text correctly and a redactor can still cut exactly the right span.
"""

from __future__ import annotations

_FOLD = {
    # Unicode space separators -> ASCII space (U+202F NARROW NO-BREAK SPACE is the one models really emit).
    **{ord(c): " " for c in "\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
                            "\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"},
    # Typographic hyphens / dashes / minus -> ASCII hyphen.
    **{ord(c): "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"},
    # Curly quotes -> ASCII, so "isn't" and "isn\u2019t" match the same pattern.
    **{ord(c): "'" for c in "\u2018\u2019\u02bc"},
    **{ord(c): chr(34) for c in "\u201c\u201d"},
}


def fold_typography(text: str) -> str:
    """Fold typographic spaces, dashes, and quotes to ASCII, preserving character offsets."""
    return text.translate(_FOLD)
