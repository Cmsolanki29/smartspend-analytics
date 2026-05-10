"""Phase 11 — Multi-branch DNN (Stripe Radar-style migration path).

Shadow-deployed via the existing Phase 5 ``shadow_logger``.  Promotion is
gated by ``PHASE_11_DNN_PROMOTED`` and a 24h pass on the segment
regression check.  See ``backend/models/cards/fraud_dnn_v1.md``.
"""
