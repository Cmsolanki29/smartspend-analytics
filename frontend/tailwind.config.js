/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        exiqo: {
          purple: "#7C3AED",
          "dark-purple": "#5B21B6",
          pink: "#EC4899",
          glow: "#A78BFA",
          navy: "#0A0E27",
          dark: "#1A1F3A",
        },
        // Per-feature signature accent palette (used ONLY on KPI glow, hero icon, chart primary, active states)
        feature: {
          cyan:     "#22D3EE",  // Transactions
          rose:     "#F43F5E",  // FraudShield
          violet:   "#A78BFA",  // Insights (AI)
          amber:    "#F59E0B",  // Subscriptions
          crimson:  "#DC2626",  // EMI Tracker
          emerald:  "#10B981",  // Analytics
          pink:     "#EC4899",  // Festivals
          sky:      "#38BDF8",  // Purchase Planner
        },
        // SmartSpend brand tokens (intro flow)
        ss: {
          "bg-deep": "#070418",
          "bg-rise": "#0F0A2E",
          violet: "#7C3AED",
          magenta: "#EC4899",
          cyan: "#22D3EE",
          ink: "#F5F3FF",
          mute: "#9CA3CF",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        heading: ['"Space Grotesk"', "Inter", "system-ui", "sans-serif"],
      },
      transitionTimingFunction: {
        brand: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      backgroundImage: {
        "ss-brand": "linear-gradient(135deg,#7C3AED 0%,#A855F7 40%,#EC4899 75%,#22D3EE 100%)",
      },
      animation: {
        "auth-mesh": "auth-mesh-shift 18s ease-in-out infinite",
        "auth-shimmer": "auth-shimmer 2.2s ease-in-out infinite",
        "auth-particle": "auth-particle 14s ease-in-out infinite",
        "auth-glow-pulse": "auth-glow-pulse 3s ease-in-out infinite",
        "ss-twinkle": "ss-twinkle 5.4s ease-in-out infinite",
        "ss-mesh": "ss-mesh 12s ease-in-out infinite alternate",
        "ss-spin-slow": "ss-spin 60s linear infinite",
        "ss-shimmer": "ss-shimmer 3.6s linear infinite",
      },
      keyframes: {
        "auth-mesh-shift": {
          "0%, 100%": { opacity: "0.45", transform: "scale(1) translate(0,0)" },
          "50%": { opacity: "0.65", transform: "scale(1.05) translate(2%, -2%)" },
        },
        "auth-shimmer": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "auth-particle": {
          "0%, 100%": { transform: "translateY(0) translateX(0)", opacity: "0.25" },
          "50%": { transform: "translateY(-28px) translateX(6px)", opacity: "0.65" },
        },
        "auth-glow-pulse": {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "0.55", transform: "scale(1.08)" },
        },
        "ss-twinkle": {
          "0%, 100%": { opacity: "0.25" },
          "50%": { opacity: "0.95" },
        },
        "ss-mesh": {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "100% 50%" },
        },
        "ss-spin": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "ss-shimmer": {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
      },
      boxShadow: {
        "auth-card": "0 25px 80px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.06), 0 0 60px rgba(139,92,246,0.12)",
        "auth-cta": "0 12px 40px rgba(139,92,246,0.35), 0 0 24px rgba(236,72,153,0.2)",
        "auth-cta-hover": "0 18px 50px rgba(139,92,246,0.45), 0 0 32px rgba(6,182,212,0.15)",
        "purple-glow": "0 0 40px rgba(124, 58, 237, 0.45)",
        "pink-glow": "0 0 40px rgba(236, 72, 153, 0.45)",
        "exiqo-card": "0 18px 48px rgba(0,0,0,0.35), 0 0 0 1px rgba(124,58,237,0.18), 0 0 36px rgba(124,58,237,0.15)",
        "ss-glass": "0 8px 40px rgba(124,58,237,0.15)",
        "ss-cta": "0 14px 44px rgba(124,58,237,0.40), 0 0 32px rgba(236,72,153,0.18)",
        "ss-cta-hover": "0 20px 56px rgba(124,58,237,0.55), 0 0 40px rgba(34,211,238,0.18)",
      },
    },
  },
  plugins: [],
};
