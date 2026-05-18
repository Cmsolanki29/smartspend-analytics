
      {postponeGoal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.target === e.currentTarget && setPostponeGoal(null)}
        >
          <div className="modal-card glass-card purchase-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Postpone — {postponeGoal.item_name}</h3>
            <p className="muted small">
              Shifts your target date and lowers monthly savings pace. EMI Tracker and planners will update.
            </p>
            <label className="fraud-field">
              Postpone by (months)
              <input
                type="number"
                min={1}
                max={60}
                value={postponeMonths}
                onChange={(e) => setPostponeMonths(e.target.value)}
              />
            </label>
            <div className="fest-card-actions" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="btn-outline" onClick={() => setPostponeGoal(null)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={postponing} onClick={handlePostpone}>
                {postponing ? "Updating…" : "Confirm postpone"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default PurchasePlanner;
