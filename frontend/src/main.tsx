import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import './index.css';

const account = '00000000-0000-0000-0000-000000000001';
const api = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';
type Point = { bucket:string; billable_calls:number };
async function fetchJson(path:string) { const r=await fetch(api+path); if(!r.ok) throw new Error('Unable to load usage'); return r.json(); }
function App() {
  const [granularity,setGranularity] = React.useState(new URLSearchParams(location.search).get('g') ?? 'hour');
  const end = new Date(), start = new Date(Date.now()-24*60*60*1000);
  const range = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`;
  const usage = useQuery({queryKey:['usage',granularity],queryFn:()=>fetchJson(`/reports/usage/time-series?account_id=${account}&${range}&granularity=${granularity}`),refetchInterval:5000});
  const mtd = useQuery({queryKey:['mtd'],queryFn:()=>fetchJson(`/reports/usage/mtd?account_id=${account}`),refetchInterval:5000});
  const change=(g:string)=>{setGranularity(g); history.replaceState(null,'',`?g=${g}`)};
  const points:Point[] = usage.data?.data ?? []; const max=Math.max(1,...points.map(p=>p.billable_calls));
  return <main className="mx-auto max-w-5xl p-8"><header className="mb-8 flex items-center justify-between"><div><p className="text-sm text-cyan-400">Metered billing</p><h1 className="text-3xl font-bold">Demo account</h1></div><div className="rounded bg-slate-800 p-1"><button onClick={()=>change('hour')} className={granularity==='hour'?'rounded bg-cyan-500 px-3 py-1 text-slate-950':'px-3 py-1'}>Hourly</button><button onClick={()=>change('day')} className={granularity==='day'?'rounded bg-cyan-500 px-3 py-1 text-slate-950':'px-3 py-1'}>Daily</button></div></header>
  {mtd.isLoading ? <p>Loading account summary…</p> : mtd.isError ? <p className="text-rose-400">Could not load live billing data.</p> : <section className="mb-8 grid gap-4 md:grid-cols-3"><Card title="MTD calls" value={String(mtd.data.calls)}/><Card title="Allowance" value={String(mtd.data.included_calls)}/><Card title="Projected overage" value={`$${(mtd.data.projected_overage_cents/100).toFixed(2)}`}/></section>}
  <section className="rounded-xl bg-slate-900 p-6 shadow"><h2 className="mb-4 text-xl font-semibold">Billable calls</h2>{usage.isLoading?<p>Loading chart…</p>:usage.isError?<p className="text-rose-400">Could not load usage.</p>:points.length===0?<p className="text-slate-400">No usage in this range.</p>:<div className="flex h-52 items-end gap-px">{points.map(p=><div key={p.bucket} title={`${new Date(p.bucket).toLocaleString()}: ${p.billable_calls}`} className="min-w-1 flex-1 bg-cyan-500/80" style={{height:`${Math.max(2,p.billable_calls/max*100)}%`}}/>)}</div>}</section></main>;
}
function Card({title,value}:{title:string,value:string}) { return <div className="rounded-xl bg-slate-900 p-5"><p className="text-sm text-slate-400">{title}</p><p className="mt-2 text-2xl font-bold">{value}</p></div> }
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={new QueryClient()}><App/></QueryClientProvider></React.StrictMode>);
