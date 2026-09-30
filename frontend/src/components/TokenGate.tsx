import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button } from './ui';

export function TokenGate({ message, onSubmit }: { message?: string; onSubmit: (token: string) => void }) {
  const [value, setValue] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (value.trim()) onSubmit(value.trim());
  };
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <p className="text-sm font-medium text-cyan-400">Metered billing</p>
      <h1 className="mt-1 text-3xl font-bold">Sign in to the dashboard</h1>
      <p className="mt-2 text-sm text-slate-400">Enter a dashboard token. The finance token can see every account; a customer token sees only its own account. It is kept for this browser tab only.</p>
      <form onSubmit={submit} className="mt-6 space-y-3">
        <label className="block text-sm text-slate-300">
          Dashboard token
          <input type="password" autoComplete="off" autoFocus value={value} onChange={(e) => setValue(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-300" />
        </label>
        {message && <p role="alert" className="text-sm text-rose-300">{message}</p>}
        <Button type="submit" disabled={!value.trim()}>Connect</Button>
      </form>
      <p className="mt-6 text-xs text-slate-500">Local demo default: <code className="rounded bg-slate-800 px-1">demo-dashboard-token</code> (see <code>.env.example</code>).</p>
    </main>
  );
}
