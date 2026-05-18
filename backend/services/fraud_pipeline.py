"""Unified FraudShield pipeline — wires phases 1–12 on upload and check-transaction.

Sync paths (psycopg2 routes) use ``score_transaction_sync``.
Async enrichment (orchestrator, events) uses ``_run_async`` helpers.
Each phase is wrapped in try/except so one failure never blocks others.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Full scoring outcome for one transaction."""

    risk_score: int = 0
    risk_level: str = "LOW"
    rule_score: int = 0
    ml_score: Optional[int] = None
    graph_score: Optional[int] = None
    gnn_score: Optional[int] = None
    dnn_score: Optional[int] = None
    sup_score: Optional[int] = None
    final_action: str = "allow"
    decision_action: str = "allow"
    risk_factors: list[str] = field(default_factory=list)
    pattern_matched: Optional[str] = None
    feature_scores: list[dict[str, Any]] = field(default_factory=list)
    models_used: dict[str, Any] = field(default_factory=dict)
    orchestrator: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    signals: dict[str, Any] = field(default_factory=dict)
    flagged_by: list[str] = field(default_factory=list)
    hybrid_explanation_detail: Optional[dict[str, Any]] = None

    def to_check_transaction_response(
        self,
        *,
        warning_message: str,
        security_advice: str,
        recommendation: str,
        should_proceed: bool,
    ) -> dict[str, Any]:
        """Shape for POST /fraud-shield/{user_id}/check-transaction."""
        models_agree = sum(
            1
            for k, v in self.models_used.items()
            if isinstance(v, (int, float)) and int(v) >= 60
        )
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "should_proceed": should_proceed,
            "warning_message": warning_message,
            "ai_security_message": security_advice,
            "hinglish_warning": security_advice,
            "risk_factors": self.risk_factors,
            "feature_scores": self.feature_scores,
            "pattern_matched": self.pattern_matched,
            "recommendation": recommendation,
            "alert_id": None,
            "cybercrime_url": "https://cybercrime.gov.in",
            "helpline": "1930",
            "rule_score": self.rule_score,
            "ml_score": self.ml_score,
            "graph_score": self.graph_score,
            "gnn_score": self.gnn_score,
            "dnn_score": self.dnn_score,
            "models_used": self.models_used,
            "flagged_by": self.flagged_by,
            "models_agreed": models_agree,
            "decision": {
                "action": self.decision_action,
                "final_action": self.final_action,
            },
            "explanation": self.explanation,
            "model_comparison": {
                "rules": {
                    "decision": "FLAG" if self.rule_score >= 60 else "ALLOW",
                    "score": round(self.rule_score / 100, 3),
                    "reason": "Eight-factor rule engine",
                },
                "isolation_forest": {
                    "decision": "FLAG" if (self.ml_score or 0) >= 60 else "ALLOW",
                    "score": round((self.ml_score or 0) / 100, 3),
                    "reason": "Unsupervised IsolationForest",
                },
                "graph": {
                    "decision": "FLAG" if (self.graph_score or 0) >= 55 else "ALLOW",
                    "score": round((self.graph_score or 0) / 100, 3),
                    "reason": "Shared-merchant graph signals",
                },
                "gnn": {
                    "decision": "FLAG" if (self.gnn_score or 0) >= 55 else "ALLOW",
                    "score": round((self.gnn_score or 0) / 100, 3),
                    "reason": "GNN embedding distance",
                },
                "dnn": {
                    "decision": "FLAG" if (self.dnn_score or 0) >= 55 else "ALLOW",
                    "score": round((self.dnn_score or 0) / 100, 3),
                    "reason": "DNN shadow lane",
                },
                "orchestrator": self.orchestrator,
            },
        }


def _run_async(coro: Any) -> Any:
    """Run async coroutine from sync FastAPI routes."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=45)


def assemble_features_sync(txn: dict[str, Any], user_history: dict[str, Any]) -> dict[str, Any]:
    """Phase 2 — derive features from ledger history (no Redis required)."""
    amount = float(txn.get("amount") or 0)
    hour = int(txn.get("hour") or txn.get("hour_of_day") or 12)
    avg_debit = float(user_history.get("avg_debit_last_30d") or 0) or 500.0
    amt_ratio = amount / max(avg_debit, 1.0)
    prev_count = int(user_history.get("payee_previous_debit_count") or 0)
    debits_30 = int(user_history.get("debits_last_30_min") or 0)
    debits_10 = int(user_history.get("debits_last_10_min") or 0)
    small_prev = int(user_history.get("small_debits_to_payee_30d") or 0)

    is_weekend = 1.0 if datetime.now().weekday() >= 5 else 0.0
    is_round = 1.0 if amount >= 500 and (amount % 1000 == 0 or amount % 500 == 0) else 0.0

    features: dict[str, Any] = {
        "amount": amount,
        "hour_of_day": hour,
        "amt_ratio_30d": round(amt_ratio, 4),
        "amount_vs_user_avg_30d": round(amt_ratio, 4),
        "hours_since_prev": 24.0 if debits_30 == 0 else max(0.5, 30.0 / max(debits_30, 1)),
        "velocity_inr_per_hour": round(amount * max(debits_10, 1) * 2, 2),
        "merchant_changed": 1.0 if prev_count == 0 else 0.0,
        "merchant_is_new": prev_count == 0,
        "merchant_first_seen": prev_count == 0,
        "txn_count_last_7d": int(user_history.get("txn_count_last_7d") or debits_30 + 1),
        "amount_percentile": min(99, int(amt_ratio * 20)),
        "amount_is_round": is_round,
        "is_weekend": is_weekend,
        "user_avg_amount_30d": avg_debit,
    }
    return features


def compute_graph_features_sync(cur, user_id: int, merchant: str) -> dict[str, Any]:
    """Phase 6 — SQL-backed graph metrics (no NetworkX required)."""
    out: dict[str, Any] = {}
    if cur is None or not merchant:
        return out
    try:
        cur.execute(
            """
            SELECT COUNT(DISTINCT t.user_id)::int
            FROM transactions t
            WHERE LOWER(COALESCE(t.merchant, t.description, '')) = LOWER(%s)
              AND t.user_id <> %s
              AND UPPER(t.type) = 'DEBIT'
              AND t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
            """,
            (merchant.strip(), user_id),
        )
        row = cur.fetchone()
        shared = int(row[0] if row else 0)
        out["graph_shared_merchant_count"] = shared
        ring_risk = min(100, shared * 12 + (15 if shared >= 3 else 0))
        out["graph_ring_risk"] = ring_risk
        out["graph_score"] = ring_risk
    except Exception as exc:  # noqa: BLE001
        logger.debug("graph_features_sync skipped: %s", exc)
    return out


def build_feature_explanations(
    features: dict[str, Any],
    user_history: dict[str, Any],
    merchant: str,
    risk_factors: list[str],
) -> list[dict[str, Any]]:
    """Phase 7 — feature-vs-baseline explanations (no fake weight table)."""
    explanations: list[dict[str, Any]] = []
    avg = float(features.get("user_avg_amount_30d") or user_history.get("avg_debit_last_30d") or 500)
    amount = float(features.get("amount") or 0)
    if avg > 0 and amount > avg * 1.5:
        ratio = amount / avg
        explanations.append(
            {
                "feature": "Amount",
                "score": round(min(0.4, ratio * 0.08), 2),
                "contribution": min(40, int(ratio * 10)),
                "impact": "high" if ratio > 3 else "medium",
                "detail": f"₹{amount:,.0f} is {ratio:.1f}× your avg",
            }
        )
    if features.get("merchant_is_new"):
        explanations.append(
            {
                "feature": "New merchant",
                "score": 0.25,
                "contribution": 25,
                "impact": "high",
                "detail": f"First time with {merchant or 'this payee'}",
            }
        )
    hour = int(features.get("hour_of_day") or 12)
    if hour >= 23 or hour < 5:
        explanations.append(
            {
                "feature": "Night transaction",
                "score": 0.2,
                "contribution": 20,
                "impact": "high",
                "detail": f"Payment at {hour}:00 — unusual hour",
            }
        )
    if float(features.get("is_weekend") or 0) >= 1:
        explanations.append(
            {
                "feature": "Weekend",
                "score": 0.08,
                "contribution": 8,
                "impact": "low",
                "detail": "Weekend spend pattern",
            }
        )
    vel = float(features.get("velocity_inr_per_hour") or 0)
    if vel > 50000:
        explanations.append(
            {
                "feature": "Velocity",
                "score": 0.15,
                "contribution": 15,
                "impact": "medium",
                "detail": "Burst of outgoing payments",
            }
        )
    g_ring = int(features.get("graph_ring_risk") or 0)
    if g_ring >= 40:
        explanations.append(
            {
                "feature": "Graph cluster",
                "score": round(g_ring / 100, 2),
                "contribution": min(30, g_ring // 3),
                "impact": "high" if g_ring >= 60 else "medium",
                "detail": "Shared merchant with other high-risk users",
            }
        )
    if not explanations and risk_factors:
        for i, rf in enumerate(risk_factors[:5]):
            explanations.append(
                {
                    "feature": f"Rule {i + 1}",
                    "score": round(0.12 - i * 0.02, 2),
                    "contribution": max(5, 20 - i * 3),
                    "impact": "medium" if i < 2 else "low",
                    "detail": rf,
                }
            )
    return explanations


def _compute_gnn_score(user_id: int, merchant: str, features: dict[str, Any]) -> Optional[int]:
    settings = get_settings()
    if not getattr(settings, "PHASE_10_GNN_ENABLED", False):
        return None
    try:
        emb = _run_async(_fetch_gnn_embedding(user_id))
        if not emb:
            return None
        # Centroid distance proxy: L2 norm of embedding (higher = more atypical)
        norm = float(math.sqrt(sum(x * x for x in emb)))
        baseline = 1.0
        distance = abs(norm - baseline)
        score = int(min(100, max(0, distance * 35)))
        features["gnn_embedding_norm"] = round(norm, 4)
        return score
    except Exception as exc:  # noqa: BLE001
        logger.debug("gnn_score skipped: %s", exc)
        return None


async def _fetch_gnn_embedding(user_id: int) -> list[float] | None:
    from services.phase_10_gnn.inference import get_user_embedding

    return await get_user_embedding(int(user_id))


def _compute_dnn_score(features: dict[str, Any]) -> Optional[int]:
    settings = get_settings()
    if not getattr(settings, "PHASE_11_DNN_ENABLED", False):
        return None
    try:
        from services.phase_11_dnn import inference as dnn_inf

        if not dnn_inf.is_enabled():
            return None
        prob = dnn_inf.predict_proba(features)
        if prob is None:
            return None
        return int(round(min(100, max(0, float(prob) * 100))))
    except Exception as exc:  # noqa: BLE001
        logger.debug("dnn_score skipped: %s", exc)
        return None


def _blend_final_score(
    rule_score: int,
    ml_score: Optional[int],
    graph_score: Optional[int],
    gnn_score: Optional[int],
    dnn_score: Optional[int],
    hybrid_score: int,
) -> int:
    """Phase 12 lite — weighted blend when full async orchestrator unavailable."""
    settings = get_settings()
    if getattr(settings, "PHASE_12_ORCHESTRATOR_ENABLED", False):
        return hybrid_score

    parts: list[tuple[int, float]] = [(rule_score, 0.35)]
    if ml_score is not None:
        parts.append((ml_score, 0.30))
    if graph_score is not None:
        parts.append((graph_score, 0.15))
    if gnn_score is not None:
        parts.append((gnn_score, 0.10))
    if dnn_score is not None and getattr(settings, "PHASE_11_DNN_PROMOTED", False):
        parts.append((dnn_score, 0.10))
    total_w = sum(w for _, w in parts)
    if total_w <= 0:
        return rule_score
    blended = sum(s * w for s, w in parts) / total_w
    return int(min(100, max(0, round(blended))))


def _risk_level(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _sync_decide(score: int, txn: dict[str, Any]) -> str:
    """Phase 4 sync fallback when asyncpg pool unavailable."""
    if score >= 95:
        return "block"
    if score >= 80:
        return "challenge"
    if score >= 60:
        return "review"
    amt = float(txn.get("amount") or 0)
    if amt >= 50000 and score >= 45:
        return "review"
    return "allow"


def score_transaction_sync(
    user_id: int,
    txn: dict[str, Any],
    user_history: dict[str, Any],
    *,
    conn=None,
    txn_id: Optional[int] = None,
) -> PipelineResult:
    """Score one transaction through rules + ML + graph + orchestrator."""
    from routes.fraud_shield import calculate_fraud_risk_score
    from services.hybrid_scorer import hybrid_scorer
    from services.ml_model import ml_detector

    out = PipelineResult()
    features = assemble_features_sync(txn, user_history)
    graph_feats = compute_graph_features_sync(conn, user_id, (txn.get("payee") or txn.get("merchant") or ""))
    features.update(graph_feats)

    # Phase 3–4: rules
    rule_res = calculate_fraud_risk_score(txn, user_history)
    out.rule_score = int(rule_res.get("risk_score") or 0)
    out.risk_factors = list(rule_res.get("risk_factors") or [])
    out.pattern_matched = rule_res.get("pattern_matched")

    # Ensure IF trained
    if user_id not in ml_detector.models:
        try:
            ml_detector.warm_start(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("IF warm_start skipped uid=%s: %s", user_id, exc)

    score_txn = {
        **txn,
        "user_id": user_id,
        "category": txn.get("category") or "Others",
        "hour_of_day": txn.get("hour") or txn.get("hour_of_day") or 12,
        "day_of_week": txn.get("day_of_week", datetime.now().weekday()),
        "type": txn.get("type", "DEBIT"),
        "balance_after": txn.get("balance_after", 100000),
    }

    # Phase 3: hybrid (IF + optional XGB)
    try:
        hybrid = hybrid_scorer.score_sync(user_id, score_txn, features)
        out.ml_score = int(round((hybrid.unsup_score or 0) * 100))
        if hybrid.sup_score is not None:
            out.sup_score = int(round(hybrid.sup_score * 100))
        out.signals = dict(hybrid.signals or {})
        out.hybrid_explanation_detail = hybrid.explanation_detail
        if hybrid.explanation:
            out.explanation = hybrid.explanation
        hybrid_risk = int(hybrid.risk_score)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hybrid_scorer failed uid=%s: %s", user_id, exc)
        try:
            if_res = ml_detector.score_single(user_id, score_txn, features)
            out.ml_score = int(if_res.risk_score)
            hybrid_risk = out.ml_score
        except Exception as exc2:  # noqa: BLE001
            logger.warning("score_single failed uid=%s: %s", user_id, exc2)
            hybrid_risk = out.rule_score

    out.graph_score = int(graph_feats.get("graph_score") or 0) or None
    out.gnn_score = _compute_gnn_score(user_id, str(txn.get("merchant") or ""), features)
    out.dnn_score = _compute_dnn_score(features)

    out.risk_score = _blend_final_score(
        out.rule_score, out.ml_score, out.graph_score, out.gnn_score, out.dnn_score, hybrid_risk
    )
    out.risk_level = _risk_level(out.risk_score)

    out.models_used = {
        "rules": out.rule_score,
        "isolation_forest": out.ml_score,
        "graph": out.graph_score,
        "gnn": out.gnn_score,
        "dnn_shadow": out.dnn_score,
        "xgboost": out.sup_score,
        "hybrid": hybrid_risk,
    }
    out.flagged_by = [
        name
        for name, val in (
            ("Rules", out.rule_score),
            ("IsolationForest", out.ml_score),
            ("Graph", out.graph_score),
            ("GNN", out.gnn_score),
            ("DNN", out.dnn_score),
        )
        if val is not None and int(val) >= 60
    ]

    out.feature_scores = build_feature_explanations(
        features, user_history, str(txn.get("payee") or txn.get("merchant") or ""), out.risk_factors
    )

    # Phase 4 decision engine (async) with sync fallback
    user_dict = {"id": user_id}
    if txn_id is not None:
        score_txn["id"] = txn_id
    try:
        from schemas.score import ScoreResult
        from services.decision_engine import decision_engine

        sr = ScoreResult(
            risk_score=out.risk_score,
            risk_level=out.risk_level,
            unsup_score=(out.ml_score or 0) / 100.0,
            sup_score=(out.sup_score / 100.0) if out.sup_score is not None else None,
            signals=out.signals,
            explanation=out.explanation or "",
            detector_version="fraud_pipeline",
            latency_ms=0,
        )

        async def _decide():
            return await decision_engine.decide(sr, score_txn, user_dict, features)

        decision = _run_async(_decide())
        out.decision_action = str(decision.action)
        out.final_action = out.decision_action
    except Exception as exc:  # noqa: BLE001
        logger.debug("decision_engine sync fallback: %s", exc)
        out.decision_action = _sync_decide(out.risk_score, txn)
        out.final_action = out.decision_action

    # Phase 12 orchestrator
    settings = get_settings()
    try:
        from services.phase_12_orchestrator.routing_policy import RoutingPolicy, route, tier_to_human

        policy = RoutingPolicy.from_settings(settings)
        routing = route(
            risk_score=out.risk_score,
            signals=out.signals,
            rule_overrides=[],
            policy=policy,
        )
        tier_label = tier_to_human(routing.tier)
        out.orchestrator = {
            **routing.to_dict(),
            "decision": out.final_action.upper(),
            "conflict": len(out.flagged_by) >= 2 and out.rule_score >= 60
            and (out.ml_score or 0) < 50,
            "models_used": out.models_used,
        }
        if policy.enabled:
            async def _orch():
                from services.phase_12_orchestrator.orchestrator import decide as orch_decide

                return await orch_decide(
                    user_id=user_id,
                    txn=score_txn,
                    user=user_dict,
                    features=features,
                    triggered_by="check_transaction",
                )

            orch_out = _run_async(_orch())
            if orch_out:
                out.final_action = str(orch_out.final_action)
                out.orchestrator = {**out.orchestrator, **orch_out.to_dict()}
                out.risk_score = int(orch_out.baseline_score or out.risk_score)
                out.risk_level = _risk_level(out.risk_score)
    except Exception as exc:  # noqa: BLE001
        logger.debug("orchestrator skipped: %s", exc)
        if not out.orchestrator:
            out.orchestrator = {
                "tier_label": "Tier 1 — Rules + IF",
                "decision": out.final_action.upper(),
                "models_used": out.models_used,
            }

    return out


async def publish_transaction_scored(
    user_id: int,
    txn_id: Optional[int],
    result: PipelineResult,
    *,
    reason: str = "",
) -> None:
    """Phase 1 — emit TRANSACTIONS_SCORED for alert consumer."""
    try:
        from services.event_bus.publisher import TOPIC_TRANSACTIONS_SCORED, event_publisher

        await event_publisher.publish(
            TOPIC_TRANSACTIONS_SCORED,
            {
                "txn_id": txn_id,
                "user_id": user_id,
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "reason": reason or (result.risk_factors[0] if result.risk_factors else ""),
                "action": result.final_action,
                "detector_version": "fraud_pipeline",
                "models_used": result.models_used,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("publish_transaction_scored skipped: %s", exc)


async def publish_batch_scored(user_id: int, count: int) -> None:
    try:
        from services.event_bus.publisher import TOPIC_TRANSACTIONS_SCORED, event_publisher

        await event_publisher.publish(
            TOPIC_TRANSACTIONS_SCORED,
            {
                "user_id": user_id,
                "count": count,
                "event": "transactions_scored",
                "risk_level": "MEDIUM",
                "risk_score": 0,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("publish_batch_scored skipped: %s", exc)


def run_post_upload_pipeline(user_id: int, conn) -> dict[str, Any]:
    """After statement import: train IF, score scoped txns, register model, emit events."""
    from services.fraud_from_transactions import score_scoped_transactions
    from services.ml_model import ml_detector

    summary: dict[str, Any] = {"trained": False, "scored": 0, "high_risk": 0}
    try:
        summary["trained"] = bool(ml_detector.train(user_id))
        det = ml_detector.detect_and_update(user_id, process_all=False)
        summary["ml_processed"] = det.get("processed", 0)
        summary["high_risk"] = det.get("high_risk", 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("post_upload ML train failed uid=%s: %s", user_id, exc)

    try:
        from services.ml_registry.registry import model_registry

        if user_id in ml_detector.models:
            model_registry.register_model(
                ml_detector.models[user_id],
                name=f"if_user_{user_id}",
                metrics={"samples": summary.get("ml_processed", 0)},
                hyperparams={"type": "IsolationForest"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("model registry register skipped: %s", exc)

    cur = conn.cursor()
    try:
        alerts = score_scoped_transactions(cur, user_id, limit=200, min_risk=50)
        summary["scored"] = len(alerts)
        for a in alerts[:25]:
            tid = a.get("transaction_id")
            if tid is None:
                continue
            pr = PipelineResult(
                risk_score=int(a.get("risk_score") or 0),
                risk_level=_risk_level(int(a.get("risk_score") or 0)),
                pattern_matched=a.get("pattern_matched"),
            )
            try:
                _run_async(
                    publish_transaction_scored(
                        user_id, int(tid), pr, reason=str(a.get("warning_message") or "")
                    )
                )
            except Exception:
                pass
    finally:
        cur.close()

    try:
        _run_async(publish_batch_scored(user_id, summary["scored"]))
    except Exception:
        pass

    # Phase 2: on-demand feature materialize (async) + sync fallback
    try:
        from workers.feature_materializer import feature_materializer

        _run_async(feature_materializer.materialize_now("user", str(user_id)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("materialize_now skipped: %s", exc)
    try:
        from services.feature_store.sync_materializer import materialize_user_sync

        materialize_user_sync(conn, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("sync_materialize_user skipped: %s", exc)

    return summary


def record_alert_feedback(user_id: int, transaction_id: int, action: str) -> None:
    """Phase 8 — map alert action to FeedbackService + optional retrain."""
    act = action.upper()
    if act not in {"BLOCKED", "ALLOWED", "REPORTED"}:
        return
    label_fraud = act in {"BLOCKED", "REPORTED"}

    async def _record():
        from services.feedback.feedback_service import feedback_service

        # record_user_report → event_publisher → local_bus when Redis is down
        await feedback_service.record_user_report(
            user_id,
            int(transaction_id),
            label=label_fraud,
            notes=f"fraud_shield_alert:{act.lower()}",
        )

    try:
        _run_async(_record())
    except Exception as exc:  # noqa: BLE001
        logger.debug("feedback record skipped: %s", exc)
        try:
            from services.ml_model import ml_detector

            if int(transaction_id) % 5 == 0:
                ml_detector.retrain(user_id, include_labels=True)
        except Exception:
            pass
