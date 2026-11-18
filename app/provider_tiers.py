"""The ordered LLM provider chain, declared as data rather than control flow.

Why this module exists
----------------------
The chain used to live as a run of ``fallback_chain.append(...)`` calls inside
``app.llm.build_fallback_cascade``. Two things went wrong with that:

* The order was an accident of the code's shape. Local ``qwen2.5:latest`` sat at
  tier 2, ahead of both the cloud Gemma and the hosted models, because that was
  the branch that happened to be unconditional. A prospect audit that lost its
  Gemini quota therefore landed on the *weakest* model in the building.
* Nothing recorded which tier answered, so an audit written by a 7B local model
  was indistinguishable — in the database, the API and the PDF — from one written
  by Gemini.

Declaring the chain as a tuple of :class:`ProviderTier` fixes both: the order is
reviewable in one place, and every tier carries the ``grade`` that decides
whether its output may reach a client.

Grades
------
``client_grade`` output may be exported, printed and shared. ``internal_only``
output is for the operator's eyes: it is still a real audit and still worth
reading, but it has not met the bar for something that goes out under the
company's name. The gate is enforced server-side in
``app.routers.youtube_prospects``; the grade travels with the tier so that
enforcement never has to guess from a model string.

A tier is *configured* when its API key field is set (or it needs no key). An
unconfigured tier is skipped with a warning and keeps its index, so "tier 3" in
a log line always means the same provider regardless of what is switched on.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Grades ───────────────────────────────────────────────────────────────────
CLIENT_GRADE = "client_grade"
INTERNAL_ONLY = "internal_only"

#: Grade assumed for any audit whose provenance is unknown — legacy rows written
#: before tier tracking existed, or a result that arrived with no tier stamp.
#: Unknown must never mean exportable.
UNKNOWN_GRADE = INTERNAL_ONLY


@dataclass(frozen=True)
class ProviderTier:
    """One rung of the cascade.

    ``model_field`` / ``api_key_field`` / ``timeout_field`` name attributes on
    :class:`app.config.Settings` rather than holding values, so that changing a
    model or key in ``.env`` needs no code change and the chain never carries a
    stale copy of a secret.
    """

    index: int
    key: str
    name: str
    builder: str
    model_field: str
    api_key_field: str | None
    grade: str
    timeout_field: str

    @property
    def is_client_grade(self) -> bool:
        return self.grade == CLIENT_GRADE

    def model(self, settings) -> str:
        return getattr(settings, self.model_field, "") or ""

    def api_key(self, settings) -> str | None:
        if self.api_key_field is None:
            return None
        return getattr(settings, self.api_key_field, None)

    def timeout(self, settings) -> int:
        return int(getattr(settings, self.timeout_field, 0) or 60)

    def is_configured(self, settings) -> bool:
        """True when this tier has everything it needs to be attempted.

        A tier with no ``api_key_field`` (the Ollama tiers, which authenticate to
        a local daemon by not authenticating at all) counts as configured as long
        as it has a model string.
        """
        if not self.model(settings):
            return False
        if self.api_key_field is None:
            return True
        return bool(self.api_key(settings))


# ── The chain ────────────────────────────────────────────────────────────────
# Order is significant and is the whole point of the file. Tiers 1 and 2 are the
# same model on two different keys: the free Gemini quota is per project, so a
# second key is a second daily allowance and a genuine retry, not a downgrade.
# Everything below them is a real drop in quality, which is why the grade flips.
# ── Default Chain (Remaining Pages: Uses Free API Key) ───────────────────────
DEFAULT_PROVIDER_CHAIN: tuple[ProviderTier, ...] = (
    ProviderTier(
        index=1,
        key="gemini_free",
        name="Tier 1: Gemini (free key)",
        builder="gemini",
        model_field="analysis_model",
        api_key_field="gemini_api_key",
        grade=CLIENT_GRADE,
        timeout_field="gemini_tier_timeout",
    ),
    ProviderTier(
        index=2,
        key="gemini_free_backup",
        name="Tier 2: Gemini (backup free key)",
        builder="gemini",
        model_field="analysis_model",
        api_key_field="gemini_backup_api_key",
        grade=CLIENT_GRADE,
        timeout_field="gemini_tier_timeout",
    ),
    ProviderTier(
        index=3,
        key="ollama_cloud",
        name="Tier 3: Ollama Cloud (Gemma 4 31B)",
        builder="ollama_cloud",
        model_field="ollama_cloud_model",
        api_key_field=None,
        grade=INTERNAL_ONLY,
        timeout_field="ollama_cloud_tier_timeout",
    ),
)

# ── Channel Audit Chain (Uses Paid Gemini 3.8 with Fallback Gemma) ────────────
AUDIT_PROVIDER_CHAIN: tuple[ProviderTier, ...] = (
    ProviderTier(
        index=1,
        key="gemini_38_paid",
        name="Tier 1: Gemini 3.8 Flash (paid)",
        builder="gemini",
        model_field="audit_model",
        api_key_field="gemini_paid_api_key",
        grade=CLIENT_GRADE,
        timeout_field="gemini_tier_timeout",
    ),
    ProviderTier(
        index=2,
        key="gemini_37_paid_backup",
        name="Tier 2: Gemini 3.7 Flash (paid backup)",
        builder="gemini",
        model_field="analysis_model",
        api_key_field="gemini_paid_api_key",
        grade=CLIENT_GRADE,
        timeout_field="gemini_tier_timeout",
    ),
    ProviderTier(
        index=3,
        key="ollama_cloud",
        name="Tier 3: Ollama Cloud (Gemma 4 31B)",
        builder="ollama_cloud",
        model_field="ollama_cloud_model",
        api_key_field=None,
        grade=CLIENT_GRADE,
        timeout_field="ollama_cloud_tier_timeout",
    ),
)

_BY_KEY = {tier.key: tier for tier in DEFAULT_PROVIDER_CHAIN}
_AUDIT_BY_KEY = {tier.key: tier for tier in AUDIT_PROVIDER_CHAIN}


def resolve_chain(order: str = "") -> tuple[ProviderTier, ...]:
    """The default chain for general/remaining pages."""
    if not order.strip():
        return DEFAULT_PROVIDER_CHAIN
    picked = [_BY_KEY[k] for key in order.split(",") if (k := key.strip()) in _BY_KEY]
    if not picked:
        return DEFAULT_PROVIDER_CHAIN
    from dataclasses import replace

    return tuple(replace(tier, index=i) for i, tier in enumerate(picked, start=1))


def resolve_audit_chain(order: str = "") -> tuple[ProviderTier, ...]:
    """The dedicated chain for Channel Audit page."""
    return AUDIT_PROVIDER_CHAIN
