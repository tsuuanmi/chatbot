"""Typed figure-description records."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FigureDescription:
    figure_id: str
    content_hash: str
    description: str
