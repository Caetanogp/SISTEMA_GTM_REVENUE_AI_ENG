"""Organization: the multi-tenant boundary. Every other entity is scoped to exactly one."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class Organization:
    id: UUID
    name: str
    demo_mode: bool = True
