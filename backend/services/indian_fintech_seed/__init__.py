"""Indian urban fintech-style transaction corpus (pool + persona assignment)."""

from __future__ import annotations

from services.indian_fintech_seed.assign import assign_corpus_to_user
from services.indian_fintech_seed.corpus_generator import corpus_validation_summary, generate_seed_corpus_rows

__all__ = [
    "assign_corpus_to_user",
    "corpus_validation_summary",
    "generate_seed_corpus_rows",
]
