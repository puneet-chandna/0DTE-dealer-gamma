import { beforeEach, describe, expect, it, vi } from 'vitest';

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('useUIStore theme initialization', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it('uses the system dark preference as the initial theme when no preference is saved', async () => {
    mockMatchMedia(true);

    const { useUIStore } = await import('./uiStore');

    expect(useUIStore.getState().isDarkMode).toBe(true);
  });

  it('defaults to light mode when the system preference is not dark', async () => {
    mockMatchMedia(false);

    const { useUIStore } = await import('./uiStore');

    expect(useUIStore.getState().isDarkMode).toBe(false);
  });
});
