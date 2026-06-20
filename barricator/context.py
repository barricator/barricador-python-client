"""User context passed to evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_BUILTINS = {"key", "name", "email", "country", "anonymous"}


@dataclass(frozen=True)
class UserContext:
    """The evaluation subject.

    ``key`` is the stable identity used for deterministic percentage rollouts and must be consistent
    across calls for a given subject. Custom attributes are addressable by targeting clauses.
    """

    key: str
    name: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    anonymous: bool = False
    custom: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("UserContext.key must be a non-empty string")

    def attribute(self, attribute: str) -> Any:
        """Resolve an attribute by clause name (built-ins take precedence over custom)."""
        if attribute == "key":
            return self.key
        if attribute == "name":
            return self.name
        if attribute == "email":
            return self.email
        if attribute == "country":
            return self.country
        if attribute == "anonymous":
            return self.anonymous
        return self.custom.get(attribute)

    def has_attribute(self, attribute: str) -> bool:
        if attribute in _BUILTINS:
            return self.attribute(attribute) is not None
        return attribute in self.custom
