import type { ReactNode } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { ApiError } from '../api/client';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : 'Something went wrong.';
}

export function Panel({ title, subtitle, actions, children, className }: {
  title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cx('rounded-xl border border-slate-800 bg-slate-900 p-5 print:border-0 print:bg-white print:p-0', className)}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 print:text-black">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 print:hidden">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

/** Loading: pulsing placeholder shaped like the content. Announced politely to screen readers. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx('animate-pulse rounded bg-slate-800', className)} />;
}

export function LoadingBlock({ label = 'Loading', height = 'h-40' }: { label?: string; height?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}…</span>
      <Skeleton className={cx('w-full', height)} />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

/** Empty: nothing went wrong, there is simply nothing here. Dashed outline, muted, with a way forward. */
export function EmptyState({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-700 px-6 py-10 text-center">
      <div aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-lg text-slate-500">∅</div>
      <p className="font-medium text-slate-200">{title}</p>
      {hint && <p className="max-w-md text-sm text-slate-400">{hint}</p>}
      {action}
    </div>
  );
}

/** Error: something failed. Red, says what happened, and offers a retry. */
export function ErrorState({ error, onRetry, title = 'Could not load this data' }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-lg border border-rose-900 bg-rose-950/40 p-4">
      <p className="font-medium text-rose-200">{title}</p>
      <p className="text-sm text-rose-300/90">{errorMessage(error)}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="rounded bg-rose-800 px-3 py-1 text-sm text-rose-50 hover:bg-rose-700 focus:outline-none focus:ring-2 focus:ring-rose-400">
          Try again
        </button>
      )}
    </div>
  );
}

export function Button({ children, onClick, variant = 'primary', disabled, type = 'button', title }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'danger'; disabled?: boolean; type?: 'button' | 'submit'; title?: string;
}) {
  const styles = {
    primary: 'bg-cyan-500 text-slate-950 hover:bg-cyan-400',
    secondary: 'bg-slate-800 text-slate-100 hover:bg-slate-700',
    danger: 'bg-rose-700 text-rose-50 hover:bg-rose-600',
  }[variant];
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={cx('rounded-md px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-300 disabled:cursor-not-allowed disabled:opacity-50', styles)}>
      {children}
    </button>
  );
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'good' | 'warn' | 'bad'; children: ReactNode }) {
  const styles = {
    neutral: 'bg-slate-800 text-slate-300',
    good: 'bg-emerald-950 text-emerald-300',
    warn: 'bg-amber-950 text-amber-300',
    bad: 'bg-rose-950 text-rose-300',
  }[tone];
  return <span className={cx('inline-block rounded-full px-2 py-0.5 text-xs font-medium', styles)}>{children}</span>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'warn' | 'bad' }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className={cx('mt-1 text-2xl font-semibold tabular-nums', tone === 'bad' ? 'text-rose-300' : tone === 'warn' ? 'text-amber-300' : 'text-slate-50')}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

/** A small "live" pulse: green while data is fresh, spinner-ish while refetching, red when refresh is failing. */
export function LiveIndicator({ fetching, failing }: { fetching: boolean; failing: boolean }) {
  const label = failing ? 'Refresh failing' : fetching ? 'Updating' : 'Live';
  const dot = failing ? 'bg-rose-400' : fetching ? 'bg-amber-300 animate-pulse' : 'bg-emerald-400';
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400" role="status">
      <span aria-hidden="true" className={cx('h-2 w-2 rounded-full', dot)} />
      {label}
    </span>
  );
}

/**
 * Renders the right state for a query: skeleton while first loading, error (with retry) when there is nothing
 * to show, an "empty" view for empty results, and — crucially — keeps showing the last good data (with a slim
 * warning) if a background refresh fails, so a blip never blanks the screen.
 */
export function Async<T>({ query, loading, isEmpty, empty, children }: {
  query: UseQueryResult<T, Error>;
  loading?: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  const data = query.data;
  if (query.isPending) return <>{loading ?? <LoadingBlock />}</>;
  if (data === undefined) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <>
      {query.isError && (
        <p role="alert" className="mb-3 rounded border border-amber-900 bg-amber-950/40 px-3 py-1.5 text-xs text-amber-200">
          Showing the last successful data — refreshing failed: {errorMessage(query.error)}
        </p>
      )}
      {isEmpty?.(data) ? empty ?? <EmptyState title="Nothing to show yet" /> : children(data)}
    </>
  );
}
