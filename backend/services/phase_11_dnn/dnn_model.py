"""Multi-branch DNN — Stripe Radar / ResNeXt-style ``Network-in-Neuron``.

Architecture rationale (CTO-honest):

* Pure DNNs lose to gradient-boosted trees on small tabular data because
  trees memorise interactions cheaply.  Stripe's blog ("How we built it:
  Stripe Radar") fixes this by stacking *several* parallel MLP branches
  whose outputs are summed.  Each branch can latch onto a different
  cross-feature pattern, mimicking GBDT's ensemble behaviour while
  remaining differentiable.

* We keep every branch identical in shape but initialised independently.
  4 branches × 128 hidden is enough capacity to overfit our 5k synthetic
  rows; we lean on dropout + weight decay to control variance.

* The forward pass returns a *logit* (no sigmoid) so we can plug it into
  ``BCEWithLogitsLoss`` (numerically stabler) and only sigmoid at
  inference time.

This module has zero PostgreSQL / Redis / FastAPI imports — it is pure
PyTorch and trivially unit-testable on a CPU.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn


@dataclass(frozen=True)
class DNNConfig:
    """Architecture settings for ``MultiBranchDNN``."""

    feature_dim: int
    branches: int = 4
    hidden_dim: int = 128
    dropout: float = 0.15

    def to_dict(self) -> dict:
        return {
            "feature_dim": int(self.feature_dim),
            "branches": int(self.branches),
            "hidden_dim": int(self.hidden_dim),
            "dropout": float(self.dropout),
        }


class _Branch(nn.Module):
    """Single MLP branch: 3 layers, ReLU + Dropout."""

    def __init__(self, feature_dim: int, hidden_dim: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class MultiBranchDNN(nn.Module):
    """ResNeXt-inspired tabular DNN — sum of independent MLP branches.

    Forward returns *logits* of shape ``(batch_size,)``.  Use
    :meth:`predict_proba` for sigmoid-activated probabilities.
    """

    def __init__(self, cfg: DNNConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.branches = nn.ModuleList(
            [
                _Branch(cfg.feature_dim, cfg.hidden_dim, cfg.dropout)
                for _ in range(cfg.branches)
            ]
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Stack branch outputs and sum (Network-in-Neuron pattern).
        # Shape: (B, branches, 1) → (B,)
        stacked = torch.stack([b(x) for b in self.branches], dim=1)
        logits = stacked.sum(dim=1).squeeze(-1)
        return logits

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Sigmoid-activated probabilities; useful for inference."""
        self.eval()
        return torch.sigmoid(self.forward(x))


def build_model(
    feature_dim: int,
    *,
    branches: int = 4,
    hidden_dim: int = 128,
    dropout: float = 0.15,
) -> MultiBranchDNN:
    """Convenience factory that mirrors the settings dataclass."""
    return MultiBranchDNN(
        DNNConfig(
            feature_dim=feature_dim,
            branches=branches,
            hidden_dim=hidden_dim,
            dropout=dropout,
        )
    )
