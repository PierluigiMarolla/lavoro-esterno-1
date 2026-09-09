/** Console Admin per pool, endpoint, credenziali write-only e test dei proxy. */
import { useState, type FormEvent } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useSources } from "@/hooks/useSources";
import {
  useCreateProxy,
  useCreateProxyPool,
  useDeleteProxy,
  useDeleteProxyPool,
  useProxyEndpoints,
  useProxyPools,
  useTestProxy,
  useUpdateProxy,
  useUpdateProxyPool,
} from "@/hooks/useProxies";
import type { ProxyScheme } from "@/types";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import ErrorState from "@/components/ui/ErrorState";
import { describeError } from "@/lib/errors";

export default function ProxySettingsPage() {
  const { user } = useAuth();
  const proxies = useProxyEndpoints();
  const pools = useProxyPools();
  const sources = useSources();
  const createProxy = useCreateProxy();
  const updateProxy = useUpdateProxy();
  const deleteProxy = useDeleteProxy();
  const createPool = useCreateProxyPool();
  const updatePool = useUpdateProxyPool();
  const deletePool = useDeleteProxyPool();
  const testProxy = useTestProxy();
  const [endpoint, setEndpoint] = useState({
    name: "", scheme: "http" as ProxyScheme, host: "", port: 8080, username: "", password: "",
  });
  const [poolName, setPoolName] = useState("");
  const [poolMembers, setPoolMembers] = useState<string[]>([]);
  const [testSourceId, setTestSourceId] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  if (user?.role !== "admin") return <ErrorState error={new Error("Accesso riservato agli Admin.")} />;
  if (proxies.isLoading || pools.isLoading) return <div className="h-64 animate-pulse bg-surface-container-low rounded-lg" />;
  if (proxies.isError || pools.isError) return <ErrorState error={proxies.error ?? pools.error} />;

  async function addEndpoint(event: FormEvent) {
    event.preventDefault(); setMessage(null);
    try {
      await createProxy.mutateAsync({
        name: endpoint.name, scheme: endpoint.scheme, host: endpoint.host,
        port: endpoint.port, enabled: true,
        ...(endpoint.username ? { username: endpoint.username, password: endpoint.password } : {}),
      });
      setEndpoint({ name: "", scheme: "http", host: "", port: 8080, username: "", password: "" });
    } catch (error) { setMessage(describeError(error).description); }
  }

  async function addPool(event: FormEvent) {
    event.preventDefault(); setMessage(null);
    try {
      await createPool.mutateAsync({ name: poolName, enabled: true, proxyIds: poolMembers });
      setPoolName(""); setPoolMembers([]);
    } catch (error) { setMessage(describeError(error).description); }
  }

  async function runMutation(action: () => Promise<unknown>) {
    setMessage(null);
    try {
      await action();
    } catch (error) {
      setMessage(describeError(error).description);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-headline-md">Impostazioni</h2>
        <div className="flex gap-4 mt-3 border-b border-border">
          <NavLink to="/settings/ai" className="pb-2 text-on-surface-variant">AI</NavLink>
          <NavLink to="/settings/proxies" className="pb-2 border-b-2 border-primary text-primary">Rotazione proxy</NavLink>
        </div>
        <p className="text-body-md text-on-surface-variant mt-4">
          Pool globali con selezione least-recently-used. Una fonte assegnata non usa mai la connessione diretta se il pool è esaurito.
        </p>
      </div>
      {message && <div role="alert" className="p-3 rounded border border-error/30 text-error">{message}</div>}

      <section className="bg-surface-container-lowest border border-border rounded-lg p-5">
        <h3 className="text-headline-sm mb-4">Nuovo proxy</h3>
        <form onSubmit={addEndpoint} className="grid md:grid-cols-4 gap-3">
          <Input required placeholder="Nome" value={endpoint.name} onChange={(e) => setEndpoint({ ...endpoint, name: e.target.value })} />
          <select className="border border-outline-variant rounded px-3 bg-surface" value={endpoint.scheme} onChange={(e) => setEndpoint({ ...endpoint, scheme: e.target.value as ProxyScheme })}>
            {(["http", "https", "socks4", "socks5"] as const).map((value) => <option key={value}>{value}</option>)}
          </select>
          <Input required placeholder="proxy.example.com" value={endpoint.host} onChange={(e) => setEndpoint({ ...endpoint, host: e.target.value })} />
          <Input required type="number" min={1} max={65535} value={endpoint.port} onChange={(e) => setEndpoint({ ...endpoint, port: Number(e.target.value) })} />
          <Input placeholder="Nome utente (opzionale)" value={endpoint.username} onChange={(e) => setEndpoint({ ...endpoint, username: e.target.value })} />
          <Input type="password" placeholder="Password" value={endpoint.password} onChange={(e) => setEndpoint({ ...endpoint, password: e.target.value })} />
          <Button type="submit" disabled={createProxy.isPending}>Aggiungi proxy</Button>
        </form>
      </section>

      <section className="bg-surface-container-lowest border border-border rounded-lg p-5">
        <div className="flex items-center justify-between mb-4"><h3 className="text-headline-sm">Endpoint</h3>
          <select className="border border-outline-variant rounded px-2 py-1 bg-surface" value={testSourceId} onChange={(e) => setTestSourceId(e.target.value)}>
            <option value="">Fonte per il test…</option>{sources.data?.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
          </select>
        </div>
        <div className="space-y-2">{proxies.data?.map((proxy) => (
          <div key={proxy.id} className="flex flex-wrap items-center gap-3 border border-border rounded p-3">
            <div className="flex-1 min-w-60"><div className="font-medium">{proxy.name}</div><div className="text-label-sm text-on-surface-variant">{proxy.scheme}://{proxy.host}:{proxy.port} · {proxy.health} · credenziali {proxy.credentialConfigured ? "configurate" : "assenti"}</div></div>
            <Button size="sm" variant="secondary" disabled={!testSourceId || testProxy.isPending} onClick={async () => { try { const result = await testProxy.mutateAsync({ id: proxy.id, sourceId: testSourceId }); setMessage(`${proxy.name}: ${result.message} (${result.latencyMs} ms)`); } catch (error) { setMessage(describeError(error).description); } }}>Test</Button>
            <Button size="sm" variant="secondary" onClick={() => runMutation(() => updateProxy.mutateAsync({ id: proxy.id, input: { enabled: !proxy.enabled } }))}>{proxy.enabled ? "Disabilita" : "Abilita"}</Button>
            <Button size="sm" variant="danger" onClick={() => { if (window.confirm(`Eliminare il proxy ${proxy.name}?`)) void runMutation(() => deleteProxy.mutateAsync(proxy.id)); }}>Elimina</Button>
          </div>
        ))}</div>
      </section>

      <section className="bg-surface-container-lowest border border-border rounded-lg p-5">
        <h3 className="text-headline-sm mb-4">Nuovo pool</h3>
        <form onSubmit={addPool} className="space-y-3">
          <Input required placeholder="Nome pool" value={poolName} onChange={(e) => setPoolName(e.target.value)} />
          <div className="flex flex-wrap gap-3">{proxies.data?.map((proxy) => <label key={proxy.id} className="flex gap-2 items-center"><input type="checkbox" checked={poolMembers.includes(proxy.id)} onChange={() => setPoolMembers((items) => items.includes(proxy.id) ? items.filter((id) => id !== proxy.id) : [...items, proxy.id])} />{proxy.name}</label>)}</div>
          <Button type="submit" disabled={createPool.isPending}>Crea pool</Button>
        </form>
        <div className="space-y-2 mt-6">{pools.data?.map((pool) => (
          <div key={pool.id} className="border border-border rounded p-3 space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex-1"><div className="font-medium">{pool.name}</div><div className="text-label-sm text-on-surface-variant">{pool.healthyCount}/{pool.totalCount} proxy disponibili</div></div>
              <Button size="sm" variant="secondary" onClick={() => runMutation(() => updatePool.mutateAsync({ id: pool.id, input: { enabled: !pool.enabled } }))}>{pool.enabled ? "Disabilita" : "Abilita"}</Button>
              <Button size="sm" variant="danger" onClick={() => { if (window.confirm(`Eliminare il pool ${pool.name}?`)) void runMutation(() => deletePool.mutateAsync(pool.id)); }}>Elimina</Button>
            </div>
            <div className="flex flex-wrap gap-3">
              {proxies.data?.map((proxy) => (
                <label key={proxy.id} className="flex gap-2 items-center text-label-sm">
                  <input
                    type="checkbox"
                    checked={pool.proxyIds.includes(proxy.id)}
                    onChange={() => void runMutation(() => updatePool.mutateAsync({
                      id: pool.id,
                      input: { proxyIds: pool.proxyIds.includes(proxy.id) ? pool.proxyIds.filter((id) => id !== proxy.id) : [...pool.proxyIds, proxy.id] },
                    }))}
                  />
                  {proxy.name}
                </label>
              ))}
            </div>
          </div>
        ))}</div>
      </section>
    </div>
  );
}
