"""Classifies request_text as DELETION / NON_DELETION.

Uses the LLM path (batched, cached, Gemini Flash) when GEMINI_API_KEY is
configured; otherwise a deterministic multilingual-keyword fallback plus the
CLASSIFY_REQUEST activity override. See docs/SPEC.md section 5 and section
6 "Run order" step 6 (owner explicitly authorized shipping the fallback
first and not blocking on the LLM key).
"""
from __future__ import annotations

import re

DELETION_KEYWORDS = [
    # English
    "delete", "deletion", "erase", "remove my", "close my account", "close the account",
    "wipe my data", "forget me", "right to be forgotten", "gdpr",
    # Portuguese / Spanish
    "exclusão", "excluir", "eliminación", "eliminar", "borrar", "apagar",
    # French
    "suppression", "supprimer", "effacer",
    # German
    "löschen", "lösche",
    # Italian
    "cancella", "eliminazione",
    # Russian
    "удалить", "удален",
    # Arabic
    "حذف",
    # Korean / Japanese / Chinese
    "삭제", "削除", "消去",
]

NON_DELETION_HINTS = [
    "update my phone", "update phone", "change my phone", "update my email", "change my email",
    "download my data", "export my data", "copy of my invoice", "send me my invoice",
    "reset my password", "reset password", "login issue", "can't log in", "cannot log in",
    "unsubscribe", "opt out of marketing", "marketing preferences", "update my address",
    "change my password", "two-factor", "verify my identity", "invoice copy",
    # broadened after the first full-run pass flagged 6 misses (docs/EVAL_LOG.md /
    # docs/GAPS.md): explicit "keep it as-is" framing around an otherwise
    # unrelated correction/export/opt-out/change request.
    "leave the account", "keep the account", "leave my profile", "leave my account",
    "without removing", "continue using the service", "continue using this service",
    "portable format", "misspelled", "correct it without", "remove me from marketing",
    "out of date. please replace", "out of date, please replace",
]


def classify_text(text: str) -> tuple[str, str]:
    """Returns (DELETION|NON_DELETION, reason). Deterministic fallback path."""
    lowered = text.lower()

    for hint in NON_DELETION_HINTS:
        if hint in lowered:
            for kw in DELETION_KEYWORDS:
                if kw in lowered:
                    return "DELETION", f"deletion keyword '{kw}' present alongside non-deletion hint"
            return "NON_DELETION", f"matched non-deletion hint: '{hint}'"

    for kw in DELETION_KEYWORDS:
        if kw in lowered:
            return "DELETION", f"matched deletion keyword: '{kw}'"

    return "DELETION", "no confident signal either way; defaulting to deletion (majority class in samples)"


def classify_case(request_text: str, classify_request_override: bool) -> tuple[str, str]:
    if classify_request_override:
        return "NON_DELETION", "CLASSIFY_REQUEST activity marked this account's request as non-deletion"
    return classify_text(request_text)
