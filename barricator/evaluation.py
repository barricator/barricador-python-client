"""Pure, synchronous targeting evaluator — a faithful port of the backend engine."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .context import UserContext
from .murmur import bucket_100k

REASON_OFF = "OFF"
REASON_RULE_MATCH = "RULE_MATCH"
REASON_FALLTHROUGH = "FALLTHROUGH"
REASON_FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
REASON_ERROR = "ERROR"

_DEFAULTED_REASONS = {REASON_FLAG_NOT_FOUND, REASON_ERROR}


@dataclass
class EvaluationResult:
    value: Any
    variation_id: Optional[str]
    reason: str

    @property
    def is_defaulted(self) -> bool:
        return self.reason in _DEFAULTED_REASONS


def evaluate(flag: Optional[Dict[str, Any]], ctx: UserContext, fallback: Any) -> EvaluationResult:
    """Evaluate a flag (raw dict from the ruleset) for a user. Never raises."""
    if flag is None:
        return EvaluationResult(fallback, None, REASON_FLAG_NOT_FOUND)
    try:
        if not flag.get("on", False):
            return _served(flag, flag.get("offVariationId"), REASON_OFF, fallback)

        for rule in flag.get("rules") or []:
            if _rule_matches(rule, ctx):
                if rule.get("rollout"):
                    variation_id = _bucket(flag["key"], rule["rollout"], ctx)
                else:
                    variation_id = rule.get("variationId")
                return _served(flag, variation_id, REASON_RULE_MATCH, fallback)

        fallthrough_rollout = flag.get("fallthroughRollout")
        if fallthrough_rollout:
            variation_id = _bucket(flag["key"], fallthrough_rollout, ctx)
            return _served(flag, variation_id, REASON_FALLTHROUGH, fallback)
        return _served(flag, flag.get("fallthroughVariationId"), REASON_FALLTHROUGH, fallback)
    except Exception:  # noqa: BLE001 - evaluation must never propagate
        return EvaluationResult(fallback, None, REASON_ERROR)


def _served(flag: Dict[str, Any], variation_id: Optional[str], reason: str, fallback: Any) -> EvaluationResult:
    value = _variation_value(flag, variation_id)
    if value is _MISSING:
        value = flag.get("defaultValue", fallback)
        if value is None:
            value = fallback
    return EvaluationResult(value, variation_id, reason)


_MISSING = object()


def _variation_value(flag: Dict[str, Any], variation_id: Optional[str]) -> Any:
    if variation_id is None:
        return _MISSING
    for variation in flag.get("variations") or []:
        if variation.get("id") == variation_id:
            return variation.get("value")
    return _MISSING


def _bucket(flag_key: str, rollout: Dict[str, Any], ctx: UserContext) -> Optional[str]:
    weighted: List[Dict[str, Any]] = rollout.get("variations") or []
    if not weighted:
        return None
    bucket_by = rollout.get("bucketBy") or "key"
    attr = ctx.attribute(bucket_by)
    bucket_by_value = str(attr) if attr is not None else ctx.key
    b = bucket_100k(flag_key, rollout.get("salt") or "", bucket_by_value)
    cumulative = 0
    for wv in weighted:
        cumulative += int(wv.get("weight", 0))
        if b < cumulative:
            return wv.get("variationId")
    return weighted[-1].get("variationId")


def _rule_matches(rule: Dict[str, Any], ctx: UserContext) -> bool:
    clauses = rule.get("clauses") or []
    if not clauses:
        return False
    return all(_clause_matches(c, ctx) for c in clauses)


def _clause_matches(clause: Dict[str, Any], ctx: UserContext) -> bool:
    attr = ctx.attribute(clause.get("attribute"))
    result = attr is not None and _apply_operator(clause.get("op"), attr, clause.get("values") or [])
    return clause.get("negate", False) != result


def _apply_operator(op: Optional[str], attr: Any, values: List[Any]) -> bool:
    if not op:
        return False
    s = lambda x: "" if x is None else str(x)  # noqa: E731
    if op == "IN":
        return any(_loose_eq(attr, v) for v in values)
    if op == "NOT_IN":
        return all(not _loose_eq(attr, v) for v in values)
    if op == "EQUALS":
        return bool(values) and _loose_eq(attr, values[0])
    if op == "NOT_EQUALS":
        return not values or not _loose_eq(attr, values[0])
    if op == "CONTAINS":
        return any(s(v) in s(attr) for v in values)
    if op == "NOT_CONTAINS":
        return all(s(v) not in s(attr) for v in values)
    if op == "STARTS_WITH":
        return any(s(attr).startswith(s(v)) for v in values)
    if op == "ENDS_WITH":
        return any(s(attr).endswith(s(v)) for v in values)
    if op == "MATCHES_REGEX":
        return any(_safe_regex(s(attr), s(v)) for v in values)
    if op in ("GREATER_THAN", "AFTER"):
        return _cmp_num(attr, values) > 0
    if op == "GREATER_THAN_OR_EQUAL":
        return _cmp_num(attr, values) >= 0
    if op in ("LESS_THAN", "BEFORE"):
        return _cmp_num(attr, values) < 0
    if op == "LESS_THAN_OR_EQUAL":
        return _cmp_num(attr, values) <= 0
    if op == "SEMVER_EQUAL":
        return _cmp_semver(attr, values) == 0
    if op == "SEMVER_GREATER_THAN":
        return _cmp_semver(attr, values) > 0
    if op == "SEMVER_LESS_THAN":
        return _cmp_semver(attr, values) < 0
    return False


def _loose_eq(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b or str(a) == str(b)


def _safe_regex(value: str, pattern: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


def _cmp_num(attr: Any, values: List[Any]) -> int:
    if not values:
        return 0
    try:
        a, b = float(attr), float(values[0])
        return (a > b) - (a < b)
    except (TypeError, ValueError):
        return 0


def _parse_semver(v: str) -> List[int]:
    core = re.split(r"[-+]", str(v))[0]
    parts = [0, 0, 0]
    for i, piece in enumerate(core.split(".")[:3]):
        try:
            parts[i] = int(piece.strip())
        except ValueError:
            parts[i] = 0
    return parts


def _cmp_semver(attr: Any, values: List[Any]) -> int:
    if not values:
        return 0
    a, b = _parse_semver(attr), _parse_semver(values[0])
    return (a > b) - (a < b)
