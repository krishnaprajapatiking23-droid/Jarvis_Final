"""
==========================================
JARVIS PRO
AGI safety boundaries
==========================================

Roadmap sections 62 (autonomous task pursuit), 63 (human collaboration),
66 (safe autonomy), 67 (human-in-the-loop) and 68 (AGI safety boundaries).

Everything here is enforced in code. The roadmap is explicit that safety must
not rest on prompt text, so this module never asks a model whether an action is
safe - it classifies the action, checks it against
:mod:`security.policy_engine`, and refuses or escalates.

Three layers, in order:

1. **Absolute boundaries.** Categories that autonomy never reaches regardless
   of permission state: secrets, credentials, financial systems, security
   configuration, privileged system operations. These return ``FORBIDDEN``.
2. **Policy check.** The existing engine decides risk and whether a human must
   confirm. The AGI does not get a softer ruling than a direct tool call would.
3. **Confidence gate.** Even an allowed action is escalated when the system is
   too unsure of what it is doing to act unsupervised (section 63).

A model can never confirm its own irreversible action - :func:`confirm` routes
to ``policy.confirm``, which only a human caller reaches.

    from agi.safety import guard

    verdict = guard.check("delete these files", action="file.delete",
                          confidence=0.9)
    verdict.allowed        # False
    verdict.needs_approval # True
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore
from security.policy_engine import policy

from .strategies import any_of

ALLOWED = "allowed"
NEEDS_APPROVAL = "needs_approval"
FORBIDDEN = "forbidden"

# Categories autonomy never enters on its own, whatever the policy mode says.
# Each entry is (label, pattern, why).
ABSOLUTE_BOUNDARIES: list[tuple[str, re.Pattern, str]] = [
    (
        # Inflections must match: an earlier version ended in \b directly after
        # the stem, so "api keys" slipped through and was ruled ALLOWED.
        #
        # "token" is deliberately absent as a bare word. It has a common
        # innocent meaning - LLM tokens, parser tokens - and including it
        # refused "explain how tokens work in an LLM". Only the qualified
        # forms below are unambiguously credentials.
        #
        # KNOWN GAP: a possessive ("my token") is caught, but a bare definite
        # reference ("read the token from the config") is not, because "the
        # tokens" also appears in ordinary requests such as "count the tokens
        # in this file". The narrower rule is the deliberate choice: an
        # over-block on everyday language is a real cost, and a credential
        # named this vaguely is rare. Anything naming a credential directly -
        # auth, access, bearer, refresh, session, api key - is still refused.
        "secrets",
        re.compile(
            "("
            + any_of("secret", "password", "credential", "keychain", "passphrase")
            + r"|\bapi[_ -]?keys?\b|\bprivate[_ -]?keys?\b|\bssh[_ -]?keys?\b"
            + r"|\b(?:auth|access|bearer|refresh|session)[_ -]?tokens?\b"
            + r"|\b(?:my|your) tokens?\b"
            + r"|\bwallet[_ -]?seeds?\b|\bseed[_ -]?phrases?\b"
            + r"|\bid_rsa\b|\.pem\b"
            + r"|(^|[\s\"'/\\])\.env\b"
            + ")",
            re.IGNORECASE,
        ),
        "reading or moving secrets is never an autonomous action",
    ),
    (
        "financial",
        re.compile(
            r"\b(transfer (money|funds)|wire|bank account|make a payment|"
            r"pay(ment)? (to|of)|purchase|checkout|credit card|upi pin)\b",
            re.IGNORECASE,
        ),
        "financial transactions always require the person",
    ),
    (
        "security_config",
        re.compile(
            r"\b(disable|turn off|bypass|uninstall) (the )?"
            r"(firewall|antivirus|defender|security|authentication|2fa|encryption)\b",
            re.IGNORECASE,
        ),
        "weakening security controls is refused",
    ),
    (
        "privilege",
        re.compile(
            r"\b(sudo|runas|administrator privileges|grant.*(root|admin)|"
            r"chmod 777|setuid|add.*to sudoers)\b",
            re.IGNORECASE,
        ),
        "privilege escalation is refused",
    ),
    (
        "mass_destruction",
        re.compile(
            r"(rm\s+-rf\s+/(?!\w)|format\s+[a-z]:|del\s+/[sq]\s+c:\\|"
            r"drop database|truncate table|\bwipe (the )?(disk|drive)\b)",
            re.IGNORECASE,
        ),
        "bulk irreversible destruction is refused",
    ),
    (
        "self_modification",
        re.compile(
            r"\b(rewrite|modify|patch|edit) (my own|jarvis'?s? own|the) "
            r"(source|core|safety|policy|guard)",
            re.IGNORECASE,
        ),
        "the AGI layer does not rewrite its own safety or core source",
    ),
]

# Request phrasing -> policy action name, so a natural request gets classified
# without needing an exact command match.
ACTION_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(delete|remove|erase|wipe|purge)\b", re.I), "file.delete"),
    (re.compile(r"\b(uninstall|format)\b", re.I), "system.restart"),
    (re.compile(r"\b(send|email|message|post|publish|share|reply)\b", re.I), "message.send"),
    (re.compile(r"\b(kill|terminate|stop) (the )?process\b", re.I), "process.kill"),
    (re.compile(r"\b(shutdown|restart|reboot)\b", re.I), "system.shutdown"),
    (re.compile(r"\b(change|modify|update) (the )?(setting|config)", re.I), "settings.change"),
    (re.compile(r"\b(run|execute|eval) (a )?(script|code|command|shell)\b", re.I), "code.execute"),
    (re.compile(r"\b(write|save|create|move|copy|rename)\b", re.I), "file.write"),
    (re.compile(r"\b(install)\b", re.I), "code.execute"),
    (re.compile(r"\b(open|launch|start)\b", re.I), "app.open"),
    (re.compile(r"\b(read|show|list|find|search|check|what|which|how)\b", re.I), "read"),
]

# Below this confidence, even a permitted action goes to the human (section 63).
AUTONOMY_CONFIDENCE_FLOOR = 0.45


@dataclass
class Verdict:
    """The outcome of a safety check, with the reasoning that produced it."""

    request: str
    action: str
    risk: str
    outcome: str
    reason: str
    boundary: str = ""
    token: str = ""
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    @property
    def allowed(self) -> bool:
        return self.outcome == ALLOWED

    @property
    def needs_approval(self) -> bool:
        return self.outcome == NEEDS_APPROVAL

    @property
    def forbidden(self) -> bool:
        return self.outcome == FORBIDDEN

    def report(self) -> dict[str, Any]:
        return {
            "request": self.request[:300],
            "action": self.action,
            "risk": self.risk,
            "outcome": self.outcome,
            "reason": self.reason,
            "boundary": self.boundary,
            "token": self.token,
            "confidence": self.confidence,
            "details": self.details,
            "at": self.at,
        }

    def question(self) -> str:
        """What to actually ask the person, when approval is needed."""

        if not self.needs_approval:
            return ""

        return (
            f"This would run '{self.action}' ({self.risk} risk): {self.request[:160]}. "
            f"{self.reason}. Approve?"
        )


def classify_action(request: str, explicit: str = "") -> str:
    """Map a natural request onto a policy action name."""

    if explicit:
        return explicit

    text = str(request or "")

    for pattern, action in ACTION_HINTS:
        if pattern.search(text):
            return action

    return "read"


class SafetyGuard:
    """The gate every autonomous AGI action passes through."""

    def __init__(self, path: str = "data/agi_safety_audit.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, [])
        self._recent: list[dict[str, Any]] = []

    # ------------------------------------------------------------ boundaries

    def boundary(self, request: str) -> tuple[str, str]:
        """Return (label, reason) if a request crosses an absolute boundary."""

        text = str(request or "")

        for label, pattern, why in ABSOLUTE_BOUNDARIES:
            if pattern.search(text):
                return label, why

        return "", ""

    # ------------------------------------------------------------ checking

    def check(
        self,
        request: str,
        action: str = "",
        confidence: float = 1.0,
        details: dict[str, Any] | None = None,
        autonomous: bool = True,
    ) -> Verdict:
        """Classify, check and rule on one proposed action."""

        details = dict(details or {})
        resolved = classify_action(request, action)

        # Layer 1: absolute boundaries.
        label, why = self.boundary(request)

        if label:
            verdict = Verdict(
                request=str(request),
                action=resolved,
                risk="critical",
                outcome=FORBIDDEN,
                reason=why,
                boundary=label,
                confidence=float(confidence),
                details=details,
            )
            self._audit(verdict)

            return verdict

        # Layer 2: the same policy engine the tool layer uses.
        decision = policy.check(resolved, details)

        if not decision.allowed and not decision.needs_confirmation:
            verdict = Verdict(
                request=str(request),
                action=resolved,
                risk=decision.risk,
                outcome=FORBIDDEN,
                reason=decision.reason,
                confidence=float(confidence),
                details=details,
            )
            self._audit(verdict)

            return verdict

        if decision.needs_confirmation:
            token = policy.request(decision)
            verdict = Verdict(
                request=str(request),
                action=resolved,
                risk=decision.risk,
                outcome=NEEDS_APPROVAL,
                reason=decision.reason,
                token=token,
                confidence=float(confidence),
                details=details,
            )
            self._audit(verdict)

            return verdict

        # Layer 3: confidence gate. Permitted, but is the system sure enough?
        if autonomous and float(confidence) < AUTONOMY_CONFIDENCE_FLOOR:
            decision_for_token = policy.check(resolved, details)
            token = policy.request(decision_for_token)
            verdict = Verdict(
                request=str(request),
                action=resolved,
                risk=decision.risk,
                outcome=NEEDS_APPROVAL,
                reason=(
                    f"confidence {float(confidence):.2f} is below the autonomy "
                    f"floor of {AUTONOMY_CONFIDENCE_FLOOR:.2f} - asking rather "
                    f"than guessing"
                ),
                token=token,
                confidence=float(confidence),
                details=details,
            )
            self._audit(verdict)

            return verdict

        verdict = Verdict(
            request=str(request),
            action=resolved,
            risk=decision.risk,
            outcome=ALLOWED,
            reason=decision.reason,
            confidence=float(confidence),
            details=details,
        )
        self._audit(verdict)

        return verdict

    # ------------------------------------------------------------ approval

    def confirm(self, token: str, approved: bool = True) -> bool:
        """Human approval. Routed to the policy engine, never self-granted."""

        return policy.confirm(token, approved)

    def approved(self, token: str) -> bool:
        return policy.is_confirmed(token)

    def pending(self) -> list[dict[str, Any]]:
        return policy.pending()

    def execute(
        self,
        verdict: Verdict,
        run: Any,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run an action only if its verdict permits it right now.

        Re-checks approval at execution time rather than trusting the verdict
        object, so a stale or unconfirmed token cannot let an action through.
        """

        if verdict.forbidden:
            return {
                "ok": False,
                "executed": False,
                "reason": verdict.reason,
                "outcome": FORBIDDEN,
            }

        if verdict.needs_approval and not self.approved(verdict.token):
            return {
                "ok": False,
                "executed": False,
                "reason": "waiting for human approval",
                "outcome": NEEDS_APPROVAL,
                "token": verdict.token,
                "question": verdict.question(),
            }

        try:
            result = run(*args, **kwargs)

        except Exception as exc:
            return {
                "ok": False,
                "executed": True,
                "error": f"{type(exc).__name__}: {exc}",
                "outcome": "error",
            }

        return {"ok": True, "executed": True, "result": result, "outcome": ALLOWED}

    # ------------------------------------------------------------ audit

    def _audit(self, verdict: Verdict) -> None:
        entry = verdict.report()

        with self._lock:
            self._recent.append(entry)
            del self._recent[:-200]

        if verdict.outcome != ALLOWED or verdict.risk in ("high", "critical"):
            try:
                def add(rows: list) -> list:
                    rows.append(entry)

                    return rows[-300:]

                self._store.update(add)

            except Exception:
                pass

    def audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent[-int(limit):])[::-1]

    def status(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._recent)

        counts: dict[str, int] = {}

        for row in rows:
            counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1

        return {
            "checks": len(rows),
            "by_outcome": counts,
            "boundaries_hit": sorted(
                {row["boundary"] for row in rows if row.get("boundary")}
            ),
            "pending_approvals": len(self.pending()),
            "policy_mode": policy.mode(),
        }


guard = SafetyGuard()
