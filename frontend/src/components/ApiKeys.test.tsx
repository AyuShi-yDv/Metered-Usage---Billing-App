import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { ApiKeys } from './ApiKeys';

// The component reaches the network only through these hooks, so we replace them
// with stand-ins and test how the component responds to their results.
const createMutateAsync = vi.fn();

vi.mock('../api/hooks', () => ({
  useApiKeys: () => ({
    data: [
      { id: 'k1', prefix: 'abc123', created_at: '2026-01-01T00:00:00Z', revoked_at: null, overlap_expires_at: null },
    ],
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCreateApiKey: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useRevokeApiKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRotateApiKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

beforeEach(() => {
  createMutateAsync.mockReset();
});

// Remove rendered components after each test so tests don't see each other's DOM.
afterEach(() => {
  cleanup();
});

describe('ApiKeys secret display', () => {
  it('shows the new secret once and hides it after the user confirms', async () => {
    createMutateAsync.mockResolvedValue({ id: 'k2', prefix: 'newpfx', secret: 'newpfx-SECRET-VALUE' });
    render(<ApiKeys account="acct-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Create API key' }));

    const dialog = await screen.findByRole('alertdialog', { name: 'New API secret' });
    expect(dialog).toHaveTextContent('newpfx-SECRET-VALUE');

    fireEvent.click(screen.getByRole('button', { name: 'I saved it' }));

    await waitFor(() => {
      expect(screen.queryByRole('alertdialog', { name: 'New API secret' })).toBeNull();
    });
    expect(screen.queryByText('newpfx-SECRET-VALUE')).toBeNull();
  });

  it('never displays a full secret for keys in the list', () => {
    render(<ApiKeys account="acct-1" />);
    expect(screen.getByText('abc123••••')).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});