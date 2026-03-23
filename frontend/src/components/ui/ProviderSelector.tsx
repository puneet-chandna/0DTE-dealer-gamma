'use client';

import { cn } from '@/lib/utils';
import { useProviders } from '@/hooks/useProviders';
import { useUIStore } from '@/stores/uiStore';

export function ProviderSelector() {
  const { data, isLoading } = useProviders();
  const { selectedProvider, setSelectedProvider } = useUIStore();

  const providers = data?.providers ?? [];

  return (
    <label className="flex items-center gap-2 text-xs text-zinc-400">
      <span className="whitespace-nowrap text-zinc-500">Data Provider</span>
      <select
        aria-label="Data provider"
        value={selectedProvider}
        disabled={isLoading || providers.length === 0}
        onChange={(event) => {
          setSelectedProvider(event.target.value as typeof selectedProvider);
        }}
        className={cn(
          'min-w-[11rem] rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 outline-none transition-colors',
          'focus:border-violet-500 focus:ring-1 focus:ring-violet-500',
          'disabled:cursor-not-allowed disabled:opacity-60'
        )}
      >
        {providers.map((provider) => (
          <option
            key={provider.name}
            value={provider.name}
            disabled={!provider.is_available}
          >
            {provider.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}
