import { EmptyState, Panel } from './ui';

// Stage-1 placeholder: replaced by the real view in the final package.
export function ComingSoon({ title }: { title: string }) {
  return (
    <Panel title={title}>
      <EmptyState title="Not built in this snapshot yet" hint="This view lands in the final (100%) package." />
    </Panel>
  );
}
