"""The centralized assistant: chat over the user's own planner data.

Answering a question runs three stages, in this order and no other:

1. ``resolver``  — one LLM call turns "aaj kya post karna hai?" into a
   structured QueryPlan (intent, IST date range, platform/status filters).
2. ``context``   — deterministic, index-backed SQL builds a bounded pack of the
   user's real rows for that range. No LLM touches this stage.
3. ``answerer``  — one LLM call writes prose over the pack, and may *propose*
   actions naming ids that appear in it.

The split exists so retrieval is never improvised: the model chooses *what to
look up*, never *what the data says*. It is also what makes writes safe — every
proposed action is validated by set membership against the pack before it is
persisted, so an id the model invented cannot be acted on.
"""
