import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ProviderSelector } from './ProviderSelector';

const mockSetSelectedProvider = vi.fn();

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => ({
    selectedProvider: 'yfinance',
    setSelectedProvider: mockSetSelectedProvider,
  }),
}));

vi.mock('@/hooks/useProviders', () => ({
  useProviders: () => ({
    data: {
      active_default: 'yfinance',
      providers: [
        {
          name: 'yfinance',
          display_name: 'Yahoo Finance',
          provides_greeks: false,
          supports_spx_directly: false,
          rate_limit: 10,
          requires_api_key: false,
          is_available: true,
          unavailable_reason: null,
          features: ['spot_price', 'options_chain'],
        },
        {
          name: 'tradier',
          display_name: 'Tradier',
          provides_greeks: true,
          supports_spx_directly: true,
          rate_limit: 120,
          requires_api_key: true,
          is_available: false,
          unavailable_reason: 'Missing API key',
          features: ['spot_price', 'options_chain', 'greeks', 'spx_direct'],
        },
      ],
    },
    isLoading: false,
  }),
}));

describe('ProviderSelector', () => {
  beforeEach(() => {
    mockSetSelectedProvider.mockReset();
  });

  it('renders the current provider and disables unavailable options', () => {
    render(<ProviderSelector />);

    const select = screen.getByLabelText(/data provider/i);
    expect(select).toHaveValue('yfinance');
    expect(screen.getByRole('option', { name: /yahoo finance/i })).toBeEnabled();
    expect(screen.getByRole('option', { name: /tradier/i })).toBeDisabled();
  });

  it('updates provider selection when the user chooses an available provider', () => {
    render(<ProviderSelector />);

    fireEvent.change(screen.getByLabelText(/data provider/i), {
      target: { value: 'yfinance' },
    });

    expect(mockSetSelectedProvider).toHaveBeenCalledWith('yfinance');
  });
});
