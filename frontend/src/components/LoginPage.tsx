/**
 * Login Page — "Clean Split"
 *
 * Layout : Two-panel flex row (left brand, right form)
 * Fonts  : DM Sans (body) + DM Serif Display (headings)
 * CSS    : Scoped lp- prefix, self-contained <style> tag, no UI library
 * Anim   : Single `mounted` boolean drives all entrance transitions
 */

import { useState, useEffect, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

const PILLS = ['Q&A Extraction', 'Speaker Analysis', 'On-Premise'];

export function LoginPage() {
  const { login } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [mounted, setMounted]   = useState(false);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string }>({
    open: false, message: '',
  });

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 40);
    return () => clearTimeout(t);
  }, []);

  // Auto-dismiss snackbar
  useEffect(() => {
    if (!snackbar.open) return;
    const t = setTimeout(() => setSnackbar(s => ({ ...s, open: false })), 4000);
    return () => clearTimeout(t);
  }, [snackbar.open]);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ username, password });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed. Please check your credentials.';
      setError(msg);
      setSnackbar({ open: true, message: msg });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display&display=swap');

        /* ─── Global reset ───────────────────────────────────────── */
        body { margin: 0; padding: 0; }
        .lp-root *, .lp-root *::before, .lp-root *::after { box-sizing: border-box; }

        /* ─── Root container ─────────────────────────────────────── */
        .lp-root {
          display: flex;
          min-height: 100vh;
          background: #eaf1f8;
          font-family: 'DM Sans', sans-serif;
        }

        /* ═══════════════════════════════════════════════════════════
           LEFT PANEL
        ═══════════════════════════════════════════════════════════ */
        .lp-panel {
          display: none;
          flex: 1;
          flex-direction: column;
          justify-content: space-between;
          padding: 52px 56px;
          background: #b3d1eb;
          position: relative;
          overflow: hidden;

          /* Entrance: hidden → visible */
          opacity: 0;
          transform: translateX(-28px);
          transition: opacity 0.65s cubic-bezier(0.22,1,0.36,1),
                      transform 0.65s cubic-bezier(0.22,1,0.36,1);
        }
        @media (min-width: 960px) { .lp-panel { display: flex; } }
        .lp-panel.visible { opacity: 1; transform: translateX(0); }

        /* Decoration ::before — subtle grid texture */
        .lp-panel::before {
          content: '';
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(14,41,128,0.07) 1px, transparent 1px),
            linear-gradient(90deg, rgba(14,41,128,0.07) 1px, transparent 1px);
          background-size: 48px 48px;
          pointer-events: none;
        }

        /* Decoration ::after — large transparent circle (ring only) */
        .lp-panel::after {
          content: '';
          position: absolute;
          bottom: -130px;
          right: -130px;
          width: 500px;
          height: 500px;
          border-radius: 50%;
          border: 72px solid rgba(14,41,128,0.07);
          background: transparent;
          pointer-events: none;
        }

        /* All content sits above pseudo-elements */
        .lp-panel-logo,
        .lp-panel-body,
        .lp-panel-footer {
          position: relative;
          z-index: 1;
        }

        /* ── Logo ── */
        .lp-panel-logo {
          opacity: 0;
          transform: translateY(8px);
          transition: opacity 0.45s ease, transform 0.45s ease;
          transition-delay: 0.3s;
        }
        .lp-panel.visible .lp-panel-logo { opacity: 1; transform: translateY(0); }

        .lp-panel-logo img {
          height: 44px;
          width: auto;
          object-fit: contain;
        }

        /* ── Body: headline, subtitle, pills ── */
        .lp-panel-body {
          display: flex;
          flex-direction: column;
          gap: 0;
        }

        .lp-headline {
          font-family: 'DM Serif Display', serif;
          font-size: clamp(2.5rem, 3.8vw, 3.4rem);
          font-weight: 400;
          line-height: 1.08;
          color: #0e2980;
          margin: 0 0 18px 0;
          letter-spacing: -0.01em;

          opacity: 0;
          transform: translateY(14px);
          transition: opacity 0.5s ease, transform 0.5s ease;
          transition-delay: 0.35s;
        }
        .lp-panel.visible .lp-headline { opacity: 1; transform: translateY(0); }

        .lp-panel-sub {
          font-size: 0.9rem;
          font-weight: 300;
          color: rgba(14,41,128,0.7);
          line-height: 1.65;
          max-width: 320px;
          margin: 0 0 36px 0;

          opacity: 0;
          transform: translateY(10px);
          transition: opacity 0.45s ease, transform 0.45s ease;
          transition-delay: 0.45s;
        }
        .lp-panel.visible .lp-panel-sub { opacity: 1; transform: translateY(0); }

        /* Pill tags row */
        .lp-pills {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .lp-pill {
          display: inline-flex;
          align-items: center;
          padding: 5px 13px;
          border-radius: 100px;
          background: rgba(14,41,128,0.10);
          border: 1px solid rgba(14,41,128,0.18);
          font-size: 0.72rem;
          font-weight: 500;
          color: #0e2980;
          letter-spacing: 0.02em;

          opacity: 0;
          transform: translateY(6px);
          transition: opacity 0.4s ease, transform 0.4s ease;
        }
        .lp-pill:nth-child(1) { transition-delay: 0.50s; }
        .lp-pill:nth-child(2) { transition-delay: 0.56s; }
        .lp-pill:nth-child(3) { transition-delay: 0.62s; }
        .lp-panel.visible .lp-pill { opacity: 1; transform: translateY(0); }

        /* ── Footer ── */
        .lp-panel-footer {
          font-size: 0.67rem;
          letter-spacing: 0.06em;
          color: rgba(14,41,128,0.38);

          opacity: 0;
          transition: opacity 0.45s ease;
          transition-delay: 0.7s;
        }
        .lp-panel.visible .lp-panel-footer { opacity: 1; }

        /* ═══════════════════════════════════════════════════════════
           RIGHT FORM PANEL
        ═══════════════════════════════════════════════════════════ */
        .lp-form-wrap {
          width: 100%;
          max-width: 480px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          padding: 52px 44px;
          background: #ffffff;

          opacity: 0;
          transform: translateY(20px);
          transition: opacity 0.6s cubic-bezier(0.22,1,0.36,1),
                      transform 0.6s cubic-bezier(0.22,1,0.36,1);
          transition-delay: 0.15s;
        }
        .lp-form-wrap.visible { opacity: 1; transform: translateY(0); }

        @media (max-width: 959px) {
          .lp-form-wrap {
            max-width: 100%;
            align-items: center;
            padding: 48px 28px;
          }
          .lp-form-inner { width: 100%; max-width: 400px; }
        }

        .lp-form-inner { width: 100%; }

        /* Mobile logo */
        .lp-mobile-logo {
          display: none;
          justify-content: center;
          margin-bottom: 36px;
        }
        .lp-mobile-logo img { height: 28px; object-fit: contain; }
        @media (max-width: 959px) { .lp-mobile-logo { display: flex; } }

        /* Eyebrow */
        .lp-eyebrow {
          font-size: 0.68rem;
          font-weight: 600;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: #0e2980;
          margin-bottom: 10px;
        }

        /* Title */
        .lp-title {
          font-family: 'DM Serif Display', serif;
          font-size: 2.1rem;
          font-weight: 400;
          color: #0e2980;
          margin: 0 0 6px 0;
          line-height: 1.1;
          letter-spacing: -0.01em;
        }

        /* Subtitle */
        .lp-subtitle {
          font-size: 0.875rem;
          font-weight: 300;
          color: #555;
          margin: 0 0 28px 0;
          line-height: 1.55;
        }

        /* ── Error bar ── */
        .lp-error {
          background: #fff0f0;
          border: 1px solid #f5c6c6;
          border-radius: 8px;
          padding: 10px 14px;
          font-size: 0.8rem;
          color: #c0392b;
          margin-bottom: 20px;
          animation: lp-shake 0.35s ease;
        }
        @keyframes lp-shake {
          0%   { transform: translateX(0);   }
          20%  { transform: translateX(-2px); }
          40%  { transform: translateX(3px);  }
          60%  { transform: translateX(-4px); }
          80%  { transform: translateX(4px);  }
          100% { transform: translateX(0);   }
        }

        /* ── Field group ── */
        .lp-field-group {
          display: flex;
          flex-direction: column;
          gap: 18px;
          margin-bottom: 24px;
        }

        .lp-field {
          transition: transform 0.15s ease;
        }
        .lp-field:focus-within { transform: scale(1.01); }

        .lp-label {
          display: block;
          font-size: 0.72rem;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #222;
          margin-bottom: 7px;
          transition: color 0.18s ease;
        }
        .lp-field:focus-within .lp-label { color: #0e2980; }

        .lp-input {
          display: block;
          width: 100%;
          padding: 11px 14px;
          font-size: 0.875rem;
          font-family: 'DM Sans', sans-serif;
          color: #111;
          background: #fafcff;
          border: 1.5px solid #dde4ed;
          border-radius: 8px;
          outline: none;
          transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
        }
        .lp-input::placeholder { color: #a0aab8; }
        .lp-input:focus {
          border-color: #0e2980;
          background: #ffffff;
          box-shadow: 0 0 0 3px rgba(14,41,128,0.12);
        }

        /* ── Submit button ── */
        .lp-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 9px;
          width: 100%;
          padding: 13px 0;
          font-size: 0.875rem;
          font-weight: 600;
          font-family: 'DM Sans', sans-serif;
          letter-spacing: 0.02em;
          color: #fff;
          background: #0e2980;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
          margin-bottom: 20px;
        }
        .lp-btn:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(14,41,128,0.28);
        }
        .lp-btn:active:not(:disabled) {
          transform: translateY(0);
          box-shadow: none;
        }
        .lp-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .lp-btn.lp-loading { animation: lp-btn-pulse 1.4s ease-in-out infinite; }
        @keyframes lp-btn-pulse {
          0%,100% { background: #0e2980; }
          50%      { background: #0c2270; }
        }

        /* CSS spinner (replaces MUI CircularProgress) */
        .lp-spinner {
          width: 15px; height: 15px;
          border: 2px solid rgba(255,255,255,0.30);
          border-top-color: #fff;
          border-radius: 50%;
          animation: lp-spin 0.65s linear infinite;
          flex-shrink: 0;
        }
        @keyframes lp-spin { to { transform: rotate(360deg); } }

        /* ── Divider ── */
        .lp-divider {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 14px;
        }
        .lp-divider::before, .lp-divider::after {
          content: '';
          flex: 1;
          height: 1px;
          background: #edf0f4;
        }
        .lp-divider-label {
          font-size: 0.67rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: #c8cfd8;
        }

        /* ── Footer text ── */
        .lp-footer-text {
          font-size: 0.68rem;
          color: #bdc5cf;
          text-align: center;
          letter-spacing: 0.04em;
        }

        /* ═══════════════════════════════════════════════════════════
           SNACKBAR TOAST
        ═══════════════════════════════════════════════════════════ */
        .lp-snackbar {
          position: fixed;
          bottom: 28px;
          left: 50%;
          transform: translateX(-50%) translateY(16px);
          background: #2d1a1a;
          color: #fff;
          padding: 11px 20px;
          border-radius: 8px;
          font-size: 0.82rem;
          font-family: 'DM Sans', sans-serif;
          box-shadow: 0 4px 20px rgba(0,0,0,0.22);
          border-left: 3px solid #c0392b;
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.25s ease, transform 0.25s ease;
          white-space: nowrap;
          z-index: 9999;
        }
        .lp-snackbar.open {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
          pointer-events: auto;
        }
      `}</style>

      <div className="lp-root">

        {/* ── Left branding panel ── */}
        <div className={`lp-panel${mounted ? ' visible' : ''}`}>

          <div className="lp-panel-logo">
            <img src="/futuraiq-logo.svg" alt="FuturAIQ" />
          </div>

          <div className="lp-panel-body">
            <h1 className="lp-headline">
              Transcript<br />Intelligence
            </h1>
            <p className="lp-panel-sub">
              Transform earnings call PDFs into structured intelligence —
              speaker registries, Q&amp;A chains, and strategic signals.
            </p>
            <div className="lp-pills">
              {PILLS.map(pill => (
                <span key={pill} className="lp-pill">{pill}</span>
              ))}
            </div>
          </div>

          <div className="lp-panel-footer">
            Internal Tool &middot; FuturAIQ &middot; All rights reserved
          </div>
        </div>

        {/* ── Right form panel ── */}
        <div className={`lp-form-wrap${mounted ? ' visible' : ''}`}>
          <div className="lp-form-inner">

            <div className="lp-mobile-logo">
              <img src="/futuraiq-logo.svg" alt="FuturAIQ" />
            </div>

            <div className="lp-eyebrow">Secure Access</div>
            <h2 className="lp-title">Welcome back</h2>
            <p className="lp-subtitle">Sign in to your FuturAIQ analytics account</p>

            {error && (
              <div className="lp-error" key={error}>{error}</div>
            )}

            <form onSubmit={handleLogin}>
              <div className="lp-field-group">
                <div className="lp-field">
                  <label className="lp-label" htmlFor="lp-username">Username</label>
                  <input
                    id="lp-username"
                    className="lp-input"
                    type="text"
                    placeholder="your.username"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    required
                    autoFocus
                    autoComplete="username"
                    disabled={loading}
                  />
                </div>
                <div className="lp-field">
                  <label className="lp-label" htmlFor="lp-password">Password</label>
                  <input
                    id="lp-password"
                    className="lp-input"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    disabled={loading}
                  />
                </div>
              </div>

              <button
                type="submit"
                className={`lp-btn${loading ? ' lp-loading' : ''}`}
                disabled={loading}
              >
                {loading && <span className="lp-spinner" />}
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <div className="lp-divider">
              <span className="lp-divider-label">FuturAIQ</span>
            </div>
            <div className="lp-footer-text">
              &copy; {new Date().getFullYear()} FuturAIQ &middot; All rights reserved
            </div>
          </div>
        </div>

      </div>

      {/* Snackbar toast */}
      <div className={`lp-snackbar${snackbar.open ? ' open' : ''}`}>
        {snackbar.message}
      </div>
    </>
  );
}
