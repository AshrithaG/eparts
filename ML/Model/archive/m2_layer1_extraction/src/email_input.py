"""Email request extraction for Layer 1.

Implements V1_Engineering_Spec §4.1 "Parse emails with Python's email module.
Strip signatures and reply chains via curated regex heuristics."

The heuristics start small and conservative; expand them as real customer
samples land. Spec §2.3 flags that 1A descriptions are *not* email-shaped,
so we cannot validate this path against the training corpus.
"""

from __future__ import annotations

import email
import re
from email import policy
from email.message import EmailMessage

from ..config import UnitAliasMap
from ..contracts import ExtractedInput, SourceType
from .units import find_value_unit_pairs

# Signature delimiters seen in the wild. Anything *after* a match (including
# the line containing the marker) is dropped before downstream encoding.
_SIGNATURE_PATTERNS = [
    re.compile(r"(?im)^\s*--\s*$"),              # RFC 3676 sig delimiter
    re.compile(r"(?im)^\s*sent from my .+$"),    # mobile-mail auto sig
    re.compile(r"(?im)^\s*regards,?\s*$"),       # generic sign-off
    re.compile(r"(?im)^\s*best,?\s*$"),
    re.compile(r"(?im)^\s*thanks,?\s*$"),
]

# Reply-chain header. Everything *from* this point on is a quoted prior
# message and should not influence the encoded text.
_REPLY_HEADER_PATTERN = re.compile(
    r"(?im)^\s*on\s.+wrote:\s*$",
)

# Leading-character quote marker (e.g. "> previous message ...").
_QUOTED_LINE_PATTERN = re.compile(r"^\s*>")


def _strip_quoted_and_signature(body: str) -> str:
    """Best-effort removal of reply chains and signatures from an email body."""
    if not body:
        return ""

    # Drop everything from the reply-chain header onward.
    reply_match = _REPLY_HEADER_PATTERN.search(body)
    if reply_match:
        body = body[: reply_match.start()]

    # Drop everything from the first signature delimiter onward.
    earliest = len(body)
    for pat in _SIGNATURE_PATTERNS:
        m = pat.search(body)
        if m and m.start() < earliest:
            earliest = m.start()
    body = body[:earliest]

    # Drop quoted lines line-by-line.
    kept_lines = [
        line for line in body.splitlines() if not _QUOTED_LINE_PATTERN.match(line)
    ]
    return "\n".join(kept_lines).strip()


def _coerce_message(payload: bytes | str | EmailMessage) -> EmailMessage:
    """Accept raw bytes/str RFC-822 payloads or an already-parsed message."""
    if isinstance(payload, EmailMessage):
        return payload
    if isinstance(payload, str):
        return email.message_from_string(payload, policy=policy.default)  # type: ignore[return-value]
    return email.message_from_bytes(payload, policy=policy.default)  # type: ignore[return-value]


def _extract_plain_body(msg: EmailMessage) -> str:
    """Return the message's plain-text body (preferring ``text/plain`` parts)."""
    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is None:
        return ""
    content = body_part.get_content()
    return str(content) if content is not None else ""


def extract_from_email(
    payload: bytes | str | EmailMessage,
    aliases: UnitAliasMap,
    source_ref: str | None = None,
) -> ExtractedInput:
    """Parse a raw email into an :class:`ExtractedInput`.

    Subject + cleaned body are concatenated into ``text``. The ``From``
    header lands in ``structured_fields["sender"]`` for audit purposes only —
    Layer 2 must not match on it as a manufacturer.
    """
    msg = _coerce_message(payload)

    subject = (msg.get("Subject") or "").strip()
    sender = (msg.get("From") or "").strip()
    cleaned_body = _strip_quoted_and_signature(_extract_plain_body(msg))

    text = "\n".join(part for part in (subject, cleaned_body) if part)

    structured = {"sender": sender} if sender else {}
    normalized_units: dict[str, tuple[str, str]] = {}
    for i, pair in enumerate(find_value_unit_pairs(text, aliases)):
        normalized_units[f"value_unit_{i}"] = (pair.value, pair.unit)

    return ExtractedInput(
        source_type=SourceType.EMAIL,
        text=text,
        structured_fields=structured,
        normalized_units=normalized_units,
        source_ref=source_ref,
    )
