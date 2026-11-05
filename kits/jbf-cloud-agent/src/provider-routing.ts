/** Free-first inference failover for the hosted JBF agent. */
export type FreeProvider<T> = {
  id: string;
  available: boolean;
  run: () => Promise<T>;
};

function statusCode(error: unknown): number | undefined {
  if (!error || typeof error !== "object") return undefined;
  const value = error as { statusCode?: unknown; status?: unknown };
  const code = Number(value.statusCode ?? value.status);
  return Number.isInteger(code) ? code : undefined;
}

export function isFreeCapacityError(error: unknown): boolean {
  return /(429|3036|3040|quota|capacity|rate.?limit|allocation|neurons|resource.?exhausted|free.?tier.*limit|limit.*reached)/i.test(String(error));
}

function isProviderFailure(error: unknown): boolean {
  const status = statusCode(error);
  return (status !== undefined && (status === 401 || status === 403 || status === 408 || status === 429 || status >= 500))
    || /(401|403|408|429|5\d\d|unauthori[sz]ed|invalid.*(api.?key|credential)|authentication|rate.?limit|quota|capacity|allocation|neurons|timeout|network|fetch failed)/i.test(String(error));
}

export async function runFreeProviders<T>(providers: FreeProvider<T>[]): Promise<{ provider: string; value: T }> {
  let lastError: unknown;
  for (const provider of providers) {
    if (!provider.available) continue;
    try {
      return { provider: provider.id, value: await provider.run() };
    } catch (error) {
      lastError = error;
      if (!isProviderFailure(error)) throw error;
    }
  }
  throw lastError ?? new Error("No configured free provider is available for this agent role.");
}

export async function runFreeFirst<T>(
  primary: () => Promise<T>,
  alternatives: FreeProvider<T>[],
): Promise<{ provider: string; value: T }> {
  try {
    return { provider: "cloudflare-ai", value: await primary() };
  } catch (primaryError) {
    if (!isFreeCapacityError(primaryError)) throw primaryError;
    let lastError: unknown = primaryError;
    for (const provider of alternatives) {
      if (!provider.available) continue;
      try {
        return { provider: provider.id, value: await provider.run() };
      } catch (error) {
        lastError = error;
        if (!isProviderFailure(error)) throw error;
      }
    }
    throw lastError;
  }
}
