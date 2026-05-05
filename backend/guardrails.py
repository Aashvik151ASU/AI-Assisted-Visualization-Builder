"""
Input and output guardrails for the AI layer.

Input guardrails  – validate user prompts before they reach Claude.
Output guardrails – sanitize Claude responses before they reach the user.

Raises GuardrailViolation (a ValueError subclass) on any breach so callers
can convert it to an appropriate HTTP 422 response without importing FastAPI.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_PROMPT_CHARS = 2_000
MAX_INSIGHT_CHARS = 1_500
MAX_TITLE_CHARS = 200


# ── Exceptions ─────────────────────────────────────────────────────────────────

class GuardrailViolation(ValueError):
    """Raised when input or output fails a guardrail check."""

    def __init__(self, message: str, *, category: str) -> None:
        super().__init__(message)
        self.category = category


class _CheckResult(NamedTuple):
    passed: bool
    violation: str | None   # None when passed


# ── Compiled patterns ──────────────────────────────────────────────────────────

# Prompt injection: attempts to override the system prompt
_INJECTION = [
    re.compile(
        r"\bignore\b.{0,50}\b(previous|prior|above|all)\b.{0,50}\b"
        r"(instruction|rule|prompt|directive)s?\b",
        re.I | re.S,
    ),
    re.compile(r"\bforget\b.{0,50}\b(instruction|rule|prompt|directive)s?\b", re.I | re.S),
    re.compile(r"\bdisregard\b.{0,50}\b(instruction|rule|prompt|directive)s?\b", re.I | re.S),
    re.compile(r"\boverride\b.{0,50}\b(instruction|rule|prompt|directive|system)s?\b", re.I | re.S),
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\bnew\s+(role|persona|instructions?)\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bDAN\s+mode\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"\bno\s+(restrictions?|limits?|filters?|guardrails?)\b", re.I),
    # Attempts to read back the system prompt
    re.compile(r"\b(print|output|repeat|show|reveal|return)\b.{0,30}\bsystem\s+prompt\b", re.I | re.S),
    re.compile(r"\bwhat\s+(are|were)\s+(your|the)\s+(instructions?|rules?|prompts?)\b", re.I),
]

# Secret / credential extraction
_SECRET_EXTRACTION = [
    re.compile(r"\bapi[\s_\-]?key\b", re.I),
    re.compile(r"\bsecret[\s_\-]?key\b", re.I),
    re.compile(r"\baccess[\s_\-]?key\b", re.I),
    re.compile(r"\banthrop(ic)?\b.{0,30}\b(key|token|secret)\b", re.I | re.S),
    re.compile(r"\bpassword\b", re.I),
    re.compile(r"\bpassphrase\b", re.I),
    re.compile(r"\bcredentials?\b", re.I),
    re.compile(r"\bprivate[\s_\-]?key\b", re.I),
    re.compile(r"\benv(ironment)?\s+variables?\b", re.I),
    re.compile(r"(?<!\w)\.env\b"),
    re.compile(r"\bexfiltrat\w*\b", re.I),
    re.compile(r"\bANTHROPIC_API_KEY\b"),
    re.compile(r"\b(database|db)[\s_\-]?(password|secret|credential|url)\b", re.I),
    # Requests to print/reveal something sensitive
    re.compile(r"\b(print|reveal|show|output|return|leak|exfiltrat\w*)\b.{0,40}"
               r"\b(key|token|secret|password|credential)\b", re.I | re.S),
]

# Social engineering / role-play bypass
_SOCIAL_ENGINEERING = [
    re.compile(r"\bpretend\s+(you\s+are|to\s+be)\b", re.I),
    re.compile(r"\bact\s+as\s+(if|though)\b", re.I),
    re.compile(r"\brole[\s\-]?play(ing)?\b", re.I),
    re.compile(
        r"\bfor\s+(educational|research|testing|academic)\s+purpose[s]?\b.{0,50}"
        r"\b(show|tell|reveal|print|give|provide)\b",
        re.I | re.S,
    ),
    re.compile(r"\bhypothetically\b.{0,30}\b(what|how|tell|give)\b", re.I | re.S),
    re.compile(r"\bin\s+a\s+(fictional|hypothetical|imaginary|simulated)\s+(scenario|world|context)\b", re.I),
    re.compile(r"\bwithout\s+(restrictions?|limits?|filters?|safety|guardrails?)\b", re.I),
    re.compile(r"\bcompletely\s+(unrestricted|unfiltered|honest)\b", re.I),
    # Prompt-in-prompt / indirect injection via dataset label tricks
    re.compile(r"<\s*(system|assistant|user)\s*>", re.I),
    re.compile(r"\[INST\]|\[/INST\]"),   # LLaMA instruction markers
]

# Patterns that indicate potential secrets in AI *output*
_OUTPUT_SECRETS = [
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),                    # Anthropic key
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),                           # OpenAI-style key
    re.compile(r"\b[A-Za-z0-9+/]{40,}={1,2}\b"),                     # Base64 token with padding
    re.compile(r"(postgres|mysql|mongodb|redis|sqlite)://\S+", re.I), # DB URLs
    re.compile(r"\bANTHROPIC_API_KEY\b"),
    re.compile(r"\bDATABASE_URL\b"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """NFKC-normalize to neutralise homoglyph / encoding obfuscation."""
    return unicodedata.normalize("NFKC", text)


def _strip_control_chars(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", text)


# ── Input checks ───────────────────────────────────────────────────────────────

def _check_length(prompt: str) -> _CheckResult:
    if len(prompt) > MAX_PROMPT_CHARS:
        return _CheckResult(
            False,
            f"Prompt is too long ({len(prompt)} characters). "
            f"Maximum allowed is {MAX_PROMPT_CHARS} characters.",
        )
    return _CheckResult(True, None)


def _check_injection(prompt: str) -> _CheckResult:
    normalized = _normalize(prompt)
    for pattern in _INJECTION:
        if pattern.search(normalized):
            return _CheckResult(
                False,
                "Your prompt contains instructions that attempt to override the AI's "
                "behaviour. Please rephrase your visualization request.",
            )
    return _CheckResult(True, None)


def _check_secret_extraction(prompt: str) -> _CheckResult:
    normalized = _normalize(prompt)
    for pattern in _SECRET_EXTRACTION:
        if pattern.search(normalized):
            return _CheckResult(
                False,
                "Your prompt appears to request sensitive system information. "
                "Only visualization-related requests are supported.",
            )
    return _CheckResult(True, None)


def _check_social_engineering(prompt: str) -> _CheckResult:
    normalized = _normalize(prompt)
    for pattern in _SOCIAL_ENGINEERING:
        if pattern.search(normalized):
            return _CheckResult(
                False,
                "Your prompt uses techniques that attempt to bypass AI safety guidelines. "
                "Please describe what you'd like to visualize instead.",
            )
    return _CheckResult(True, None)


def validate_input(prompt: str) -> None:
    """
    Run all input guardrail checks in priority order.
    Raises GuardrailViolation with a user-safe message on the first failure.
    """
    for category, check_fn in (
        ("length",           _check_length),
        ("injection",        _check_injection),
        ("secret_extraction", _check_secret_extraction),
        ("social_engineering", _check_social_engineering),
    ):
        result = check_fn(prompt)
        if not result.passed:
            raise GuardrailViolation(result.violation, category=category)  # type: ignore[arg-type]


# ── Output checks ──────────────────────────────────────────────────────────────

def _redact_secrets(text: str) -> tuple[str, list[str]]:
    """Replace potential secrets with [REDACTED]. Returns (clean_text, warnings)."""
    warnings: list[str] = []
    for pattern in _OUTPUT_SECRETS:
        if pattern.search(text):
            warnings.append(
                f"AI response contained a potential secret matching "
                f"pattern '{pattern.pattern[:50]}'; it has been redacted."
            )
            text = pattern.sub("[REDACTED]", text)
    return text, warnings


def sanitize_insight(insight: str) -> tuple[str, list[str]]:
    """
    Sanitize a Claude-generated insight string.

    Returns (safe_text, list_of_warnings). Warnings are non-empty only when
    something suspicious was found and redacted; callers may log them.
    """
    text = _strip_control_chars(insight)
    text, warnings = _redact_secrets(text)
    if len(text) > MAX_INSIGHT_CHARS:
        text = text[:MAX_INSIGHT_CHARS] + "…"
    return text, warnings


def sanitize_title(title: str) -> str:
    """Return a control-char-stripped, length-capped chart title."""
    title = _normalize(title)
    title = _strip_control_chars(title)
    return title[:MAX_TITLE_CHARS]


def validate_viz_spec_output(raw: dict) -> list[str]:
    """
    Scan a parsed VizSpec dict for suspicious content in its text fields.

    Returns a list of warning strings (empty list = clean). Does not raise;
    the caller decides whether to surface or just log the warnings.
    """
    warnings: list[str] = []
    text_fields = ("title", "interpreted_intent", "x_axis", "y_axis")
    for field_name in text_fields:
        _, issues = _redact_secrets(str(raw.get(field_name, "")))
        warnings.extend(issues)
    for item in raw.get("alignment_issues", []):
        _, issues = _redact_secrets(str(item))
        warnings.extend(issues)
    return warnings
