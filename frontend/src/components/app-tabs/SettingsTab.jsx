import React, { useState } from "react";
import { ArrowLeft, Lock, Settings } from "lucide-react";
import { GlassCard } from "../intro/GlassCard";
import UploadStatement from "../Upload/UploadStatement";
import ConnectedAccountsSettings from "../Settings/ConnectedAccountsSettings";

export default function SettingsTab({ onOpenAdmin, userId, onLeave }) {
  const [panel, setPanel] = useState("accounts"); // accounts | upload
  const [uploadSourceType, setUploadSourceType] = useState("credit_card");

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-10">
      {typeof onLeave === "function" ? (
        <div className="flex items-center gap-2 border-b border-white/10 pb-3 md:hidden">
          <button
            type="button"
            onClick={() => onLeave()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-3 py-2 text-sm font-semibold text-white/90 hover:bg-white/[0.1]"
          >
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden />
            Back to dashboard
          </button>
        </div>
      ) : null}

      <div className="flex max-md:flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-1">
        <button
          type="button"
          onClick={() => setPanel("accounts")}
          className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition ${
            panel === "accounts" ? "bg-violet-600 text-white" : "text-white/50 hover:text-white/80"
          }`}
        >
          Connected accounts
        </button>
        <button
          type="button"
          onClick={() => setPanel("upload")}
          className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition ${
            panel === "upload" ? "bg-violet-600 text-white" : "text-white/50 hover:text-white/80"
          }`}
        >
          Uploads &amp; history
        </button>
      </div>

      {userId ? (
        panel === "accounts" ? (
          <ConnectedAccountsSettings
            userId={userId}
            onGoUpload={(kind) => {
              setUploadSourceType(kind || "credit_card");
              setPanel("upload");
            }}
          />
        ) : (
          <UploadStatement userId={userId} initialSourceType={uploadSourceType} />
        )
      ) : (
        <GlassCard padding="lg" className="border-dashed border-white/15">
          <p className="text-sm text-white/50">Select a user to manage connected accounts.</p>
        </GlassCard>
      )}

      {typeof onOpenAdmin === "function" ? (
        <GlassCard padding="lg" className="border-dashed border-white/15">
          <div className="flex items-start gap-3">
            <Settings className="mt-0.5 h-6 w-6 text-exiqo-glow shrink-0" aria-hidden />
            <div className="min-w-0 flex-1">
              <h2 className="font-heading text-lg font-semibold text-white">Engine diagnostics</h2>
              <p className="mt-2 text-sm text-exiqo-glow/70">
                ML ops consoles are not listed in the workspace sidebar. Unlock with your admin passphrase.
              </p>
              <button
                type="button"
                onClick={() => onOpenAdmin()}
                className="mt-3 inline-flex items-center gap-2 rounded-xl border border-violet-500/40 bg-violet-500/15 px-4 py-2.5 text-sm font-semibold text-violet-100 transition hover:bg-violet-500/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40"
              >
                <Lock className="h-4 w-4 shrink-0" aria-hidden />
                Unlock engine diagnostics
              </button>
            </div>
          </div>
        </GlassCard>
      ) : null}
    </div>
  );
}
