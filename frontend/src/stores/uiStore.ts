/**
 * 0DTE GEX Frontend - Zustand Store for Client-side UI State
 *
 * RULE: Zustand is for CLIENT STATE only (UI settings, preferences).
 * Server state (API data) should use React Query, NOT Zustand.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * UI Settings State
 */
interface UIState {
  // Sidebar
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  // Alert Settings
  alertThreshold: number; // GEX threshold in billions
  setAlertThreshold: (threshold: number) => void;

  // Date Selection
  selectedDate: string | null;
  setSelectedDate: (date: string | null) => void;

  // Chart Settings
  showCallGex: boolean;
  showPutGex: boolean;
  showNetGex: boolean;
  toggleCallGex: () => void;
  togglePutGex: () => void;
  toggleNetGex: () => void;

  // Theme
  isDarkMode: boolean;
  toggleDarkMode: () => void;

  // Refresh Settings
  autoRefreshEnabled: boolean;
  refreshInterval: number; // in seconds
  setAutoRefresh: (enabled: boolean, interval?: number) => void;

  // Demo Mode
  demoModeEnabled: boolean;
  toggleDemoMode: () => void;
  setDemoMode: (enabled: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Sidebar - default open
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      setSidebarOpen: (open) => set({ isSidebarOpen: open }),

      // Alert threshold - default 1B (significant GEX)
      alertThreshold: 1.0,
      setAlertThreshold: (threshold) => set({ alertThreshold: threshold }),

      // Date - null means today/live
      selectedDate: null,
      setSelectedDate: (date) => set({ selectedDate: date }),

      // Chart toggles - all visible by default
      showCallGex: true,
      showPutGex: true,
      showNetGex: true,
      toggleCallGex: () => set((state) => ({ showCallGex: !state.showCallGex })),
      togglePutGex: () => set((state) => ({ showPutGex: !state.showPutGex })),
      toggleNetGex: () => set((state) => ({ showNetGex: !state.showNetGex })),

      // Theme - respect system preference
      isDarkMode: false,
      toggleDarkMode: () => set((state) => ({ isDarkMode: !state.isDarkMode })),

      // Auto refresh - enabled by default at 30s
      autoRefreshEnabled: true,
      refreshInterval: 30,
      setAutoRefresh: (enabled, interval) =>
        set({
          autoRefreshEnabled: enabled,
          refreshInterval: interval ?? 30,
        }),

      // Demo mode
      demoModeEnabled: false,
      toggleDemoMode: () => set((state) => ({ demoModeEnabled: !state.demoModeEnabled })),
      setDemoMode: (enabled) => set({ demoModeEnabled: enabled }),
    }),
    {
      name: 'odte-gex-ui-settings',
      partialize: (state) => ({
        // Only persist user preferences, not transient UI state
        alertThreshold: state.alertThreshold,
        showCallGex: state.showCallGex,
        showPutGex: state.showPutGex,
        showNetGex: state.showNetGex,
        isDarkMode: state.isDarkMode,
        autoRefreshEnabled: state.autoRefreshEnabled,
        refreshInterval: state.refreshInterval,
        demoModeEnabled: state.demoModeEnabled,
      }),
    }
  )
);
