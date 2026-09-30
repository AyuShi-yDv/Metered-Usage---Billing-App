import { useState } from 'react';
import { useApiKeys, useCreateApiKey, useRevokeApiKey, useRotateApiKey } from '../api/hooks';
import { Async, Badge, Button, EmptyState, Panel } from './ui';
import { errorMessage } from './ui';

function dateTime(value: string | null): string { return value ? new Date(value).toLocaleString() : '—'; }

export function ApiKeys({ account }: { account: string }) {
  const query = useApiKeys(account);
  const create = useCreateApiKey(account);
  const revoke = useRevokeApiKey(account);
  const rotate = useRotateApiKey(account);
  const [secret, setSecret] = useState<{ prefix: string; value: string } | null>(null);
  const [error, setError] = useState('');

  const createNew = async () => { setError(''); try { const key = await create.mutateAsync(); setSecret({ prefix: key.prefix, value: key.secret }); } catch (e) { setError(errorMessage(e)); } };
  const rotateKey = async (id: string) => { setError(''); try { const key = await rotate.mutateAsync({ keyId: id, overlapSeconds: 300 }); setSecret({ prefix: key.prefix, value: key.secret }); } catch (e) { setError(errorMessage(e)); } };
  const revokeKey = async (id: string) => { if (!window.confirm('Revoke this API key? In-flight traffic using it will stop immediately unless it is inside a rotation overlap window.')) return; setError(''); try { await revoke.mutateAsync(id); } catch (e) { setError(errorMessage(e)); } };

  return <Panel title="API keys" subtitle="Secrets are displayed once when created or rotated and are never returned by the list endpoint."
    actions={<Button onClick={createNew} disabled={create.isPending}>{create.isPending ? 'Creating…' : 'Create API key'}</Button>}>
    {secret && <div role="alertdialog" aria-label="New API secret" className="mb-5 rounded-lg border border-cyan-800 bg-cyan-950/40 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold text-cyan-200">Save this secret now</p><p className="mt-1 text-sm text-cyan-300/80">It will not be shown again. Prefix: {secret.prefix}</p></div><Button variant="secondary" onClick={() => setSecret(null)}>I saved it</Button></div><code className="mt-3 block overflow-x-auto rounded bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100">{secret.value}</code></div>}
    {error && <p role="alert" className="mb-4 rounded border border-rose-900 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">{error}</p>}
    <Async query={query} isEmpty={(rows) => rows.length === 0} empty={<EmptyState title="No API keys" hint="Create a key for this account to start sending usage events." />}>
      {(rows) => <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">API keys</caption><thead className="text-xs uppercase tracking-wide text-slate-400"><tr><th className="py-2 pr-4">Prefix</th><th className="py-2 pr-4">Created</th><th className="py-2 pr-4">Status</th><th className="py-2 pr-4">Rotation overlap</th><th className="py-2 text-right">Actions</th></tr></thead><tbody className="divide-y divide-slate-800">{rows.map((key) => { const active = !key.revoked_at; return <tr key={key.id}><td className="py-3 pr-4 font-mono text-slate-200">{key.prefix}••••</td><td className="py-3 pr-4 text-slate-300">{dateTime(key.created_at)}</td><td className="py-3 pr-4"><Badge tone={active ? 'good' : 'bad'}>{active ? 'Active' : 'Revoked'}</Badge></td><td className="py-3 pr-4 text-slate-300">{key.overlap_expires_at ? `until ${dateTime(key.overlap_expires_at)}` : '—'}</td><td className="py-3 text-right"><div className="flex justify-end gap-2">{active && <><Button variant="secondary" disabled={rotate.isPending} onClick={() => void rotateKey(key.id)}>Rotate</Button><Button variant="danger" disabled={revoke.isPending} onClick={() => void revokeKey(key.id)}>Revoke</Button></>}</div></td></tr>; })}</tbody></table></div>}
    </Async>
    <p className="mt-4 text-xs text-slate-500">Rotation creates a new secret and keeps the old secret valid for 5 minutes, preventing in-flight events from being dropped.</p>
  </Panel>;
}
