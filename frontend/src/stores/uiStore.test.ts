/**
 * 0DTE GEX Frontend - Zustand UI Store Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from './uiStore';

describe('useUIStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useUIStore.setState({
      isSidebarOpen: true,
      alertThreshold: 1.0,
      selectedDate: null,
      selectedProvider: 'yfinance',
      availableProviders: [],
      activeDefaultProvider: 'yfinance',
      showCallGex: true,
      showPutGex: true,
      showNetGex: true,
      isDarkMode: false,
      autoRefreshEnabled: true,
      refreshInterval: 30,
      demoModeEnabled: false,
    });
  });

  describe('sidebar state', () => {
    it('has sidebar open by default', () => {
      const state = useUIStore.getState();
      expect(state.isSidebarOpen).toBe(true);
    });

    it('toggles sidebar correctly', () => {
      const { toggleSidebar } = useUIStore.getState();

      toggleSidebar();
      expect(useUIStore.getState().isSidebarOpen).toBe(false);

      toggleSidebar();
      expect(useUIStore.getState().isSidebarOpen).toBe(true);
    });

    it('sets sidebar state directly', () => {
      const { setSidebarOpen } = useUIStore.getState();

      setSidebarOpen(false);
      expect(useUIStore.getState().isSidebarOpen).toBe(false);

      setSidebarOpen(true);
      expect(useUIStore.getState().isSidebarOpen).toBe(true);
    });
  });

  describe('alert threshold', () => {
    it('has default threshold of 1.0', () => {
      expect(useUIStore.getState().alertThreshold).toBe(1.0);
    });

    it('updates threshold correctly', () => {
      const { setAlertThreshold } = useUIStore.getState();

      setAlertThreshold(2.5);
      expect(useUIStore.getState().alertThreshold).toBe(2.5);

      setAlertThreshold(-1.0);
      expect(useUIStore.getState().alertThreshold).toBe(-1.0);
    });
  });

  describe('date selection', () => {
    it('has null date by default (today/live)', () => {
      expect(useUIStore.getState().selectedDate).toBeNull();
    });

    it('sets and clears date correctly', () => {
      const { setSelectedDate } = useUIStore.getState();

      setSelectedDate('2026-01-29');
      expect(useUIStore.getState().selectedDate).toBe('2026-01-29');

      setSelectedDate(null);
      expect(useUIStore.getState().selectedDate).toBeNull();
    });
  });

  describe('chart visibility toggles', () => {
    it('has all chart types visible by default', () => {
      const state = useUIStore.getState();
      expect(state.showCallGex).toBe(true);
      expect(state.showPutGex).toBe(true);
      expect(state.showNetGex).toBe(true);
    });

    it('toggles call GEX visibility', () => {
      const { toggleCallGex } = useUIStore.getState();

      toggleCallGex();
      expect(useUIStore.getState().showCallGex).toBe(false);

      toggleCallGex();
      expect(useUIStore.getState().showCallGex).toBe(true);
    });

    it('toggles put GEX visibility', () => {
      const { togglePutGex } = useUIStore.getState();

      togglePutGex();
      expect(useUIStore.getState().showPutGex).toBe(false);

      togglePutGex();
      expect(useUIStore.getState().showPutGex).toBe(true);
    });

    it('toggles net GEX visibility', () => {
      const { toggleNetGex } = useUIStore.getState();

      toggleNetGex();
      expect(useUIStore.getState().showNetGex).toBe(false);

      toggleNetGex();
      expect(useUIStore.getState().showNetGex).toBe(true);
    });
  });

  describe('dark mode', () => {
    it('is disabled by default', () => {
      expect(useUIStore.getState().isDarkMode).toBe(false);
    });

    it('toggles dark mode correctly', () => {
      const { toggleDarkMode } = useUIStore.getState();

      toggleDarkMode();
      expect(useUIStore.getState().isDarkMode).toBe(true);

      toggleDarkMode();
      expect(useUIStore.getState().isDarkMode).toBe(false);
    });
  });

  describe('auto refresh settings', () => {
    it('has auto refresh enabled with 30s interval by default', () => {
      const state = useUIStore.getState();
      expect(state.autoRefreshEnabled).toBe(true);
      expect(state.refreshInterval).toBe(30);
    });

    it('disables auto refresh', () => {
      const { setAutoRefresh } = useUIStore.getState();

      setAutoRefresh(false);
      expect(useUIStore.getState().autoRefreshEnabled).toBe(false);
    });

    it('enables auto refresh with custom interval', () => {
      const { setAutoRefresh } = useUIStore.getState();

      setAutoRefresh(true, 10);
      expect(useUIStore.getState().autoRefreshEnabled).toBe(true);
      expect(useUIStore.getState().refreshInterval).toBe(10);
    });

    it('uses default interval when not specified', () => {
      const { setAutoRefresh } = useUIStore.getState();

      // First set custom interval
      setAutoRefresh(true, 60);
      expect(useUIStore.getState().refreshInterval).toBe(60);

      // Then reset without specifying interval
      setAutoRefresh(true);
      expect(useUIStore.getState().refreshInterval).toBe(30);
    });
  });

  describe('provider selection', () => {
    it('defaults to yfinance provider', () => {
      const state = useUIStore.getState();
      expect(state.selectedProvider).toBe('yfinance');
      expect(state.activeDefaultProvider).toBe('yfinance');
      expect(state.availableProviders).toEqual([]);
    });

    it('updates selected provider directly', () => {
      const { setSelectedProvider } = useUIStore.getState();

      setSelectedProvider('tradier');
      expect(useUIStore.getState().selectedProvider).toBe('tradier');
    });

    it('syncs unavailable persisted provider back to the active default', () => {
      useUIStore.setState({
        selectedProvider: 'tradier',
      });

      const { setAvailableProviders, syncSelectedProvider } = useUIStore.getState();

      setAvailableProviders(
        [
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
        'yfinance'
      );
      syncSelectedProvider();

      expect(useUIStore.getState().selectedProvider).toBe('yfinance');
    });
  });
});
