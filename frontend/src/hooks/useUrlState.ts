import { useCallback, useEffect, useRef, useState } from 'react';
import { parseUrl, toSearch } from '../lib/url.ts';
import type { UrlState } from '../lib/url.ts';

/** URL-backed UI state. `push` adds a history entry (navigation); `replace` rewrites it (filters, typing). */
export function useUrlState(): [UrlState, (patch: Partial<UrlState>, mode?: 'push' | 'replace') => void] {
  const [state, setState] = useState<UrlState>(() => parseUrl(window.location.search));
  const latest = useRef(state);
  latest.current = state;

  useEffect(() => {
    const onPop = () => setState(parseUrl(window.location.search));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const update = useCallback((patch: Partial<UrlState>, mode: 'push' | 'replace' = 'replace') => {
    const next = { ...latest.current, ...patch };
    const search = toSearch(next);
    if (search !== window.location.search) {
      if (mode === 'push') window.history.pushState(null, '', window.location.pathname + search);
      else window.history.replaceState(null, '', window.location.pathname + search);
    }
    latest.current = next;
    setState(next);
  }, []);

  return [state, update];
}
