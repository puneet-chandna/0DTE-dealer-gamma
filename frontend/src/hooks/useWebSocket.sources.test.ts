import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWebSocket } from './useWebSocket';

class Socket {
  static OPEN = 1;
  static CONNECTING = 0;
  static instances: Socket[] = [];
  readyState = Socket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  send = vi.fn();

  constructor(public url: string) { Socket.instances.push(this); }
  close() { this.readyState = 3; }
  open() { this.readyState = Socket.OPEN; this.onopen?.(); }
  message(source: string) {
    this.onmessage?.({ data: JSON.stringify({ type: 'gex_update', data: { source } }) });
  }
}

describe('WebSocket source changes', () => {
  beforeEach(() => {
    Socket.instances = [];
    vi.stubGlobal('WebSocket', Socket);
    vi.useFakeTimers();
    vi.setSystemTime(1000);
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('hides the previous source on the first render and resets its timestamp', () => {
    const renders: { source: string | undefined; time: number | null; connected: boolean }[] = [];
    const { result, rerender } = renderHook(({ endpoint }) => {
      const stream = useWebSocket<{ source: string }>(endpoint);
      renders.push({ source: stream.data?.source, time: stream.lastUpdateTime, connected: stream.isConnected });
      return stream;
    }, { initialProps: { endpoint: '/gex-stream?provider=yfinance' } });
    act(() => { Socket.instances[0].open(); Socket.instances[0].message('yfinance'); });
    expect(result.current.data).toEqual({ source: 'yfinance' });
    const previousRenderCount = renders.length;

    rerender({ endpoint: '/gex-stream?provider=tradier' });
    expect(renders[previousRenderCount]).toEqual({ source: undefined, time: null, connected: false });
    expect(result.current.data).toBeNull();
    expect(result.current.lastUpdateTime).toBeNull();
    expect(result.current.connectionState).toBe('connecting');
  });

  it('ignores all late callbacks from a replaced socket', () => {
    const { result, rerender } = renderHook(({ endpoint }) => useWebSocket<{ source: string }>(endpoint),
      { initialProps: { endpoint: '/gex-stream?provider=yfinance' } });
    const obsolete = Socket.instances[0];
    act(() => { obsolete.open(); obsolete.message('yfinance'); });
    rerender({ endpoint: '/gex-stream?provider=tradier' });
    const current = Socket.instances[1];

    act(() => obsolete.open());
    expect(result.current.isConnected).toBe(false);
    act(() => { current.open(); current.message('tradier'); });
    vi.setSystemTime(2000);
    act(() => {
      obsolete.message('yfinance');
      obsolete.onerror?.();
      obsolete.onclose?.({ code: 1006 });
    });
    expect(result.current.data).toEqual({ source: 'tradier' });
    expect(result.current.lastUpdateTime).toBe(1000);
    expect(result.current.isConnected).toBe(true);
    expect(result.current.error).toBeNull();
    act(() => vi.advanceTimersByTime(30000));
    expect(current.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }));
    expect(Socket.instances).toHaveLength(2);
  });

  it('shows the server error message instead of its object representation', () => {
    const { result } = renderHook(() => useWebSocket('/gex-stream'));
    act(() => Socket.instances[0].onmessage?.({ data: JSON.stringify({
      type: 'error', data: { message: 'No eligible captured history for yfinance/SPX' },
    }) }));
    expect(result.current.error).toBe('No eligible captured history for yfinance/SPX');
  });
});
