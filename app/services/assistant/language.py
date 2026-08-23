"""Which language to answer in.

Detection is deterministic and runs *before* the LLM, not as a field the model
fills in. Two reasons. First, the resolver has a fallback path — on a deadline
overrun or an exhausted cascade it returns a default QueryPlan — and a
model-supplied language field would silently revert a Hinglish conversation to
English exactly when things are already going wrong. Second, a rule you can read
is a rule you can test; ``detect_language`` is pure and has no I/O.

The output feeds one place only: the ``{language_rule}`` slot in the answer
prompt. Every structured field in the LLM contract stays English ASCII whatever
this returns.
"""

from __future__ import annotations

import re
from typing import Literal

Language = Literal["en", "hinglish"]

# Devanagari block. Present ⇒ unambiguously not plain English.
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Romanized Hindi function words and the verbs that actually show up in
# scheduling questions. Deliberately excludes bare 'to', 'me', 'is' and other
# sequences that collide with ordinary English.
HINGLISH_MARKERS = frozenset(
    {
        "aaj", "kal", "parso", "abhi", "phir", "dobara",
        "kya", "kaunsa", "kaun", "kitne", "kitna", "kaise", "kahan",
        "hafte", "hafta", "mahine", "mahina", "din",
        "mujhe", "mera", "meri", "mere", "tum", "aap", "apna", "apne",
        "dikha", "dikhao", "bata", "batao", "banao", "karna", "karo", "kar",
        "chahiye", "hai", "hain", "tha", "thi", "the", "hoga", "hogi",
        "nahi", "nahin", "haan", "acha", "theek",
        "wala", "wali", "wale", "bhi", "sirf", "bacha", "bache", "pending",
        "ka", "ki", "ke", "ko", "se", "mein", "pe", "par",
    }
)

# Below this many marker hits the signal is noise: 'ka'/'ke'/'se'/'hai' collide
# with English words and with romanized topic titles.
_MARKER_THRESHOLD = 2

# At or below this many tokens a turn carries no reliable language signal
# ('haan', 'ok', 'aur?', 'usko bhi') and must inherit rather than flip the
# conversation. Kept at 2, not 3: "what's on tomorrow?" is three tokens and is
# unambiguously English, and inheriting there answered an English question in
# Hinglish.
_SHORT_TURN_TOKENS = 2

# Words that only appear in an English question or command. One of these with
# zero Hinglish markers is a positive English signal strong enough to override
# both inheritance and the model's guess.
ENGLISH_MARKERS = frozenset(
    {
        "what", "whats", "what's", "when", "which", "who", "where", "why", "how",
        "show", "list", "give", "tell", "should", "need", "do", "does", "did",
        "is", "are", "was", "were", "my", "me", "the", "on", "for", "next",
        "this", "today", "tomorrow", "yesterday", "week", "pending", "review",
        "schedule", "post", "draft", "drafts",
    }
)

_WORD = re.compile(r"[a-z]+")


def _marker_hits(question: str) -> int:
    return sum(1 for w in _WORD.findall(question.lower()) if w in HINGLISH_MARKERS)


def _english_hits(question: str) -> int:
    return sum(1 for w in _WORD.findall(question.lower()) if w in ENGLISH_MARKERS)


def detect_language(
    question: str,
    previous: Language | None = None,
    model_guess: Language | None = None,
) -> Language:
    """Decide the answer language for one turn.

    Order:

    1. Any Devanagari ⇒ ``hinglish``, unconditionally.
    2. Two or more Hinglish markers ⇒ ``hinglish``.
    3. A very short turn inherits ``previous`` — an acknowledgement must not
       flip a Hinglish thread to English.
    4. Otherwise the resolver's guess, else English.

    Note the asymmetry in (2): a deterministic ``hinglish`` verdict overrides the
    model, but a deterministic *absence* of markers does not override a model
    that saw Hinglish. A false positive costs the user a Hinglish answer they can
    read anyway; a false negative is the actual complaint — "I asked in Hinglish
    and it replied in English".
    """
    text = (question or "").strip()
    if not text:
        return previous or model_guess or "en"

    if DEVANAGARI.search(text):
        return "hinglish"

    hinglish_hits = _marker_hits(text)
    if hinglish_hits >= _MARKER_THRESHOLD:
        return "hinglish"

    # A clear English signal with nothing Hinglish about it beats both the
    # inherited language and the model — this is what stops "what's on
    # tomorrow?" being answered in Hinglish just because the previous turn was.
    if hinglish_hits == 0 and _english_hits(text) >= 1:
        return "en"

    if len(text.split()) <= _SHORT_TURN_TOKENS and previous:
        return previous

    return model_guess or "en"


# Interpolated into the answer prompt. Written as two complete blocks rather
# than a generic "reply in the user's language" line, which Tier-3/Tier-4 models
# reliably ignore.
LANGUAGE_RULES: dict[str, str] = {
    "hinglish": (
        "LANGUAGE: Hinglish\n"
        "- Write `answer_markdown` in Hinglish — Hindi words in Latin script mixed with\n"
        "  English, the way the user typed. Example: \"Aaj 2 items scheduled hain: ek\n"
        "  YouTube video 09:00 pe, ek LinkedIn post 18:30 pe. Review queue mein 3 drafts\n"
        "  pending hain.\"\n"
        "- Use Latin script only. Do NOT use Devanagari. Do NOT write pure formal Hindi.\n"
        "- Keep topic titles, platform names and statuses verbatim in English — they are\n"
        "  data, not prose.\n"
        "- EVERY OTHER FIELD stays English ASCII: intent, verb, content_type, dates as\n"
        "  YYYY-MM-DD, ids as UUIDs. Only `answer_markdown` changes language."
    ),
    "en": (
        "LANGUAGE: English\n"
        "- Write `answer_markdown` in plain English.\n"
        "- Keep topic titles, platform names and statuses verbatim.\n"
        "- EVERY OTHER FIELD stays English ASCII: intent, verb, content_type, dates as\n"
        "  YYYY-MM-DD, ids as UUIDs."
    ),
}


def language_rule(language: str) -> str:
    return LANGUAGE_RULES.get(language, LANGUAGE_RULES["en"])
