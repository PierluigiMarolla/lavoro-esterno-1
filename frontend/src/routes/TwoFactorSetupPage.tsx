import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";
import Icon from "@/components/ui/Icon";

// Mandatory 2FA enrollment screen: shown whenever an Admin/Operator account
// hasn't activated TOTP yet (ProtectedRoute redirects here for any other
// route, mirroring the backend's own enforcement in
// app/security/deps.py:get_current_user). No mockup exists for this screen
// (it's a new, previously-missing flow) — styled consistently with
// LoginPage.tsx using the same Tailwind design tokens, not a pixel-perfect
// replica of anything in desing/.
export default function TwoFactorSetupPage() {
  const { completeTwoFactorSetup, logout } = useAuth();
  const navigate = useNavigate();

  const [loadingSetup, setLoadingSetup] = useState(true);
  const [qrCodeBase64, setQrCodeBase64] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [savedCodesAck, setSavedCodesAck] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authApi
      .setupTwoFactor()
      .then((setup) => {
        if (cancelled) return;
        setQrCodeBase64(setup.qrCodeBase64);
        setSecret(setup.secret);
        setBackupCodes(setup.backupCodes);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Unable to start 2FA setup."))
      .finally(() => setLoadingSetup(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const handleVerify = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await completeTwoFactorSetup(code);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invalid verification code.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-background text-on-background min-h-screen flex items-center justify-center p-margin-page">
      <div className="w-full max-w-[480px] bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col">
        <div className="p-8 pb-6 text-center border-b border-border bg-surface-bright">
          <Icon name="verified_user" className="text-primary mb-2" size={28} />
          <h1 className="text-headline-lg text-primary tracking-tight mb-2">Two-Factor Setup Required</h1>
          <p className="text-body-md text-on-surface-variant">
            Your role requires two-factor authentication before you can continue.
          </p>
        </div>

        <div className="p-8 pt-6 flex-1 flex flex-col justify-center gap-5">
          {error && (
            <div className="px-3 py-2 rounded bg-error-container/40 text-error text-body-md">{error}</div>
          )}

          {loadingSetup ? (
            <p className="text-center text-body-md text-on-surface-variant">Preparing setup…</p>
          ) : !savedCodesAck ? (
            <>
              <div className="flex flex-col items-center gap-3">
                {qrCodeBase64 && (
                  <img
                    src={`data:image/png;base64,${qrCodeBase64}`}
                    alt="TOTP QR code"
                    className="w-40 h-40 border border-outline-variant rounded"
                  />
                )}
                <p className="text-label-sm text-on-surface-variant text-center">
                  Scan with Google Authenticator / Microsoft Authenticator, or enter this key manually:
                </p>
                <code className="font-mono text-mono-data text-on-surface bg-surface px-2 py-1 rounded border border-outline-variant">
                  {secret}
                </code>
              </div>

              <div className="space-y-2">
                <p className="text-label-sm text-on-surface">
                  Save these backup codes now — each can be used once if you lose access to your
                  authenticator app, and they will not be shown again:
                </p>
                <div className="grid grid-cols-2 gap-2 font-mono text-mono-data bg-surface border border-outline-variant rounded p-3">
                  {backupCodes.map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSavedCodesAck(true)}
                className="w-full py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container transition-colors"
              >
                I&apos;ve saved my secret and backup codes
              </button>
            </>
          ) : (
            <form className="space-y-5" onSubmit={handleVerify}>
              <div className="space-y-1.5">
                <label className="block text-label-sm text-on-surface" htmlFor="totp-code">
                  Enter the 6-digit code from your authenticator app
                </label>
                <input
                  id="totp-code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  pattern="\d{6}"
                  maxLength={6}
                  required
                  autoFocus
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000000"
                  className="block w-full text-center tracking-[0.5em] py-2 px-3 border border-outline-variant rounded bg-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container font-mono text-headline-sm text-on-surface placeholder-outline-variant transition-colors outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={submitting || code.length !== 6}
                className="w-full py-2.5 px-4 rounded shadow-sm text-label-sm text-on-primary bg-primary hover:bg-primary-container transition-colors disabled:opacity-60"
              >
                {submitting ? "Verifying…" : "Activate 2FA"}
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => logout()}
            className="text-center text-label-sm text-on-surface-variant hover:text-primary transition-colors"
          >
            Sign out instead
          </button>
        </div>
      </div>
    </div>
  );
}
