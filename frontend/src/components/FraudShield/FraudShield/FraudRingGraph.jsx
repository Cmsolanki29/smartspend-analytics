/**
 * FraudRingGraph — D3 force-directed graph showing GNN-derived fraud rings.
 * Each ring is a cluster of users, merchants, and devices linked by shared
 * activity. Node colour: red (score > 0.7), amber (0.4-0.7), green (< 0.4).
 */

import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { getApiBaseUrl } from "../../../services/apiBaseUrl";

const API_BASE = getApiBaseUrl();

function nodeColor(score) {
  if (score >= 0.7) return "#ef4444";
  if (score >= 0.4) return "#f59e0b";
  return "#22c55e";
}


function RiskBadge({ level }) {
  const map = { HIGH: "#ef4444", MEDIUM: "#f59e0b", LOW: "#22c55e" };
  const color = map[level] || "#9ca3af";
  return (
    <span
      style={{
        background: `${color}20`,
        color,
        border: `1px solid ${color}60`,
        borderRadius: 6,
        fontSize: 10,
        fontWeight: 700,
        padding: "2px 8px",
        letterSpacing: "0.05em",
      }}
    >
      {level}
    </span>
  );
}

function RingGraph({ ring }) {
  const svgRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    if (!ring || !ring.nodes || !ring.edges) return;
    const width = 340, height = 240;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    const nodes = ring.nodes.map((n) => ({ ...n }));
    const links = ring.edges.map((e) => ({
      source: e.from,
      target: e.to,
      weight: e.weight ?? 0.5,
      label: e.label,
    }));

    // Index nodes by id for d3 link resolution
    const nodeById = {};
    nodes.forEach((n) => (nodeById[n.id] = n));

    const simulation = d3.forceSimulation(nodes)
      .force("link",   d3.forceLink(links).id((n) => n.id).distance(70))
      .force("charge", d3.forceManyBody().strength(-160))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide(28));

    // Draw edges
    const link = g.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.18)")
      .attr("stroke-width", (d) => Math.max(1, d.weight * 4));

    // Draw nodes
    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .call(
        d3.drag()
          .on("start", (ev, d) => {
            if (!ev.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on("end",  (ev, d) => {
            if (!ev.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      )
      .on("mouseover", (ev, d) => {
        setTooltip({
          x: ev.offsetX,
          y: ev.offsetY,
          text: `${d.label} (${d.type}) · score: ${d.fraud_score}`,
        });
      })
      .on("mousemove", (ev) => {
        setTooltip((t) => t ? { ...t, x: ev.offsetX, y: ev.offsetY } : t);
      })
      .on("mouseout", () => setTooltip(null));

    // Circles for users
    node.filter((d) => d.type === "user")
      .append("circle")
      .attr("r", 14)
      .attr("fill", (d) => nodeColor(d.fraud_score))
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
      .style("filter", (d) => d.fraud_score >= 0.7 ? "drop-shadow(0 0 6px rgba(239,68,68,0.7))" : "none");

    // Rectangles for merchants
    node.filter((d) => d.type === "merchant")
      .append("rect")
      .attr("x", -14).attr("y", -14)
      .attr("width", 28).attr("height", 28)
      .attr("rx", 4)
      .attr("fill", (d) => nodeColor(d.fraud_score))
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5);

    // Diamond for devices
    node.filter((d) => d.type === "device")
      .append("polygon")
      .attr("points", "0,-16 16,0 0,16 -16,0")
      .attr("fill", (d) => nodeColor(d.fraud_score))
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5);

    // Labels
    node.append("text")
      .attr("y", 26)
      .attr("text-anchor", "middle")
      .attr("font-size", 9)
      .attr("fill", "rgba(255,255,255,0.7)")
      .text((d) => d.label.length > 12 ? d.label.slice(0, 12) + "…" : d.label);

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [ring]);

  return (
    <div style={{ position: "relative" }}>
      <svg
        ref={svgRef}
        width="100%"
        viewBox="0 0 340 240"
        style={{ background: "rgba(255,255,255,0.02)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)" }}
      />
      {tooltip && (
        <div
          style={{
            position: "absolute",
            left: tooltip.x + 8,
            top: tooltip.y - 28,
            background: "rgba(10,10,20,0.9)",
            color: "white",
            fontSize: 11,
            padding: "4px 8px",
            borderRadius: 6,
            border: "1px solid rgba(255,255,255,0.15)",
            pointerEvents: "none",
            whiteSpace: "nowrap",
          }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}

const FraudRingGraph = () => {
  const [rings, setRings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/fraud-shield/rings`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("smartspend_access_token") || ""}`,
      },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setRings(data.rings || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message || "Failed to load fraud rings");
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="glass-card" style={{ textAlign: "center", padding: 24 }}>
        <p className="muted">Loading GNN fraud ring data…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card" style={{ padding: 16 }}>
        <p className="muted small" style={{ color: "#ef4444" }}>⚠ {error}</p>
      </div>
    );
  }

  if (!rings || rings.length === 0) {
    return (
      <div className="glass-card" style={{ textAlign: "center", padding: 24 }}>
        <p className="muted">No fraud rings detected — system is clean ✅</p>
      </div>
    );
  }

  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>🕸 GNN Fraud Ring Detection</h3>
        <span className="muted small">Phase 10 · {rings.length} ring{rings.length !== 1 ? "s" : ""} found</span>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
        {[
          { shape: "●", color: "#ef4444", label: "High risk (>0.7)" },
          { shape: "●", color: "#f59e0b", label: "Medium (0.4-0.7)" },
          { shape: "●", color: "#22c55e", label: "Low (<0.4)" },
          { shape: "■", color: "#aaa",    label: "Merchant" },
          { shape: "◆", color: "#aaa",    label: "Device" },
        ].map(({ shape, color, label }) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ color, fontSize: 12 }}>{shape}</span> {label}
          </span>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {rings.map((ring) => (
          <div key={ring.ring_id} style={{ space: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.6)" }}>
                {ring.ring_id}
              </span>
              <RiskBadge level={ring.risk_level} />
              <span className="muted small">
                {ring.nodes?.length || 0} nodes · {ring.edges?.length || 0} edges
              </span>
            </div>
            <RingGraph ring={ring} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default FraudRingGraph;
