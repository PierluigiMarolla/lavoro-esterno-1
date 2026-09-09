/** Contratti HTTP per pool ed endpoint proxy; le credenziali non vengono mai lette. */
import { apiRequest } from "./client";
import type { ProxyEndpoint, ProxyPool, ProxyScheme, ProxyTestResult } from "@/types";

export const fetchProxyPools = () => apiRequest<ProxyPool[]>("/admin/proxy-pools");
export const fetchProxies = () => apiRequest<ProxyEndpoint[]>("/admin/proxies");
export const createProxyPool = (input: { name: string; enabled: boolean; proxyIds: string[] }) =>
  apiRequest<ProxyPool>("/admin/proxy-pools", { method: "POST", body: input });
export const updateProxyPool = (
  id: string,
  input: { name?: string; enabled?: boolean; proxyIds?: string[] },
) => apiRequest<ProxyPool>(`/admin/proxy-pools/${id}`, { method: "PATCH", body: input });
export const deleteProxyPool = (id: string) =>
  apiRequest<void>(`/admin/proxy-pools/${id}`, { method: "DELETE" });

export interface ProxyEndpointInput {
  name: string;
  scheme: ProxyScheme;
  host: string;
  port: number;
  username?: string;
  password?: string;
  enabled: boolean;
}

export const createProxy = (input: ProxyEndpointInput) =>
  apiRequest<ProxyEndpoint>("/admin/proxies", { method: "POST", body: input });
export const updateProxy = (
  id: string,
  input: Partial<ProxyEndpointInput> & { clearCredential?: boolean },
) => apiRequest<ProxyEndpoint>(`/admin/proxies/${id}`, { method: "PATCH", body: input });
export const deleteProxy = (id: string) =>
  apiRequest<void>(`/admin/proxies/${id}`, { method: "DELETE" });
export const testProxy = (id: string, sourceId: string) =>
  apiRequest<ProxyTestResult>(`/admin/proxies/${id}/test`, {
    method: "POST",
    body: { sourceId },
  });
