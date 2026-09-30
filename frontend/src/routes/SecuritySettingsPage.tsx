import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useSecuritySettings, useUpdateSecuritySettings } from "@/hooks/useIntegrations";
import SettingsTabs from "@/components/settings/SettingsTabs";
import ErrorState from "@/components/ui/ErrorState";
import Button from "@/components/ui/Button";
import { describeError } from "@/lib/errors";

export default function SecuritySettingsPage() {
  const { user, refreshUser } = useAuth();
  const query = useSecuritySettings();
  const update = useUpdateSecuritySettings();
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (query.data) setEnabled(query.data.mfaRequired);
  }, [query.data]);

  if (user?.role !== "admin") return <ErrorState error={new Error("Accesso riservato agli Admin.")} />;
  if (query.isError || !query.data) {
    return query.isLoading ? <div className="h-40 animate-pulse rounded bg-surface-container-low" /> : <ErrorState error={query.error} />;
  }

  const save = async () => {
    await update.mutateAsync({ mfaRequired: enabled, expectedRevision: query.data.revision });
    await refreshUser();
  };

  return <div className="space-y-6"><div><h2 className="text-headline-md">Impostazioni</h2><SettingsTabs /></div>
    <section className="max-w-3xl space-y-4 rounded-lg border border-border bg-surface-container-lowest p-5">
      <div><h3 className="text-headline-sm">Autenticazione OTP globale</h3><p className="mt-2 text-body-sm text-on-surface-variant">Di base l&apos;OTP è disattivato. Se lo abiliti, verrà richiesto a tutti gli utenti dal prossimo accesso; le sessioni già aperte non saranno interrotte.</p></div>
      <label className="flex items-start gap-3 rounded border border-border p-4"><input type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /><span><strong>Richiedi OTP a tutti gli utenti</strong><span className="mt-1 block text-body-sm text-on-surface-variant">Chi lo ha già configurato inserirà il codice; gli altri completeranno il setup al login successivo.</span></span></label>
      <Button disabled={update.isPending || enabled === query.data.mfaRequired} onClick={() => void save().catch(() => undefined)}>{update.isPending ? "Salvataggio…" : "Salva impostazione"}</Button>
      {update.isSuccess && <p className="text-body-sm text-success">Impostazione salvata. La modifica vale dai prossimi accessi.</p>}
      {update.isError && <p className="text-body-sm text-error">{describeError(update.error).description}</p>}
    </section>
  </div>;
}
