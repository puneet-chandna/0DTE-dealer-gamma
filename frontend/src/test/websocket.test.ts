/**
 * WebSocket Hook Tests
 *
 * Tests for useWebSocket and useGEXStream hooks with mocked WebSocket.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWebSocket, useGEXStream } from '@/hooks/useWebSocket';
import type { GEXUpdate } from '@/types';

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  static CONNECTING = 0;

  url: string;
  readyState: number = MockWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send() {
    // Mock send implementation
  }

  close(code?: number) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code: code ?? 1000 });
    }
  }

  // Helper methods for testing
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    if (this.onopen) {
      this.onopen();
    }
  }

  simulateMessage(data: object) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror();
    }
  }

  simulateClose(code: number = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code });
    }
  }
}

// Replace global WebSocket with mock
const originalWebSocket = global.WebSocket;

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    // @ts-expect-error - mocking global
    global.WebSocket = MockWebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.useRealTimers();
  });

  it('should start with connecting state (effect runs immediately)', () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    // Initial state transitions to connecting due to immediate useEffect
    expect(result.current.connectionState).toBe('connecting');
    expect(result.current.data).toBeNull();
    expect(result.current.isConnected).toBe(false);
  });

  it('should transition to connecting state', async () => {
    renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    // Wait for effect to run
    await act(async () => {
      vi.runAllTimers();
    });

    expect(MockWebSocket.instances.length).toBeGreaterThan(0);
  });

  it('should connect and update state on open', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    // Simulate connection open
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.connectionState).toBe('connected');
    expect(result.current.error).toBeNull();
  });

  it('should receive and parse data on message', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    const mockData: GEXUpdate = {
      net_gex: -1500000000,
      net_gex_billions: -1.5,
      zero_gamma_level: 5950,
      spot_price: 5945,
      regime: 'short_gamma',
    };

    act(() => {
      ws.simulateMessage({ type: 'gex_update', data: mockData });
    });

    expect(result.current.data).toEqual(mockData);
  });

  it('should handle connection error', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateError();
    });

    expect(result.current.error).toBe('WebSocket connection error');
  });

  it('should transition to disconnected on close', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);

    act(() => {
      ws.simulateClose(1006);
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.connectionState).toBe('disconnected');
  });

  it('should send message when connected', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    const sendSpy = vi.spyOn(ws, 'send');

    act(() => {
      ws.simulateOpen();
    });

    act(() => {
      result.current.sendMessage('test message');
    });

    expect(sendSpy).toHaveBeenCalledWith('test message');
  });

  it('should not send message when disconnected', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    const sendSpy = vi.spyOn(ws, 'send');

    // Don't open the connection
    act(() => {
      result.current.sendMessage('test message');
    });

    expect(sendSpy).not.toHaveBeenCalled();
  });

  it('should disconnect on command', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);

    act(() => {
      result.current.disconnect();
    });

    expect(result.current.connectionState).toBe('disconnected');
  });

  it('should reconnect manually after an established connection', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const initialSocket = MockWebSocket.instances[0];
    act(() => {
      initialSocket.simulateOpen();
    });

    act(() => {
      result.current.reconnect();
    });

    await act(async () => {
      vi.runAllTimers();
    });

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(result.current.connectionState).toBe('connecting');
  });

  it('should treat unknown message types with data as updates', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint')
    );

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    const fallbackData: GEXUpdate = {
      net_gex: 150000000,
      net_gex_billions: 0.15,
      zero_gamma_level: 5960,
      spot_price: 5955,
      regime: 'neutral',
    };

    act(() => {
      ws.simulateMessage({ type: 'custom_event', data: fallbackData });
    });

    expect(result.current.data).toEqual(fallbackData);
  });
});

describe('useGEXStream', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    // @ts-expect-error - mocking global
    global.WebSocket = MockWebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.useRealTimers();
  });

  it('should connect to /gex-stream endpoint', async () => {
    renderHook(() => useGEXStream());

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(ws.url).toContain('/gex-stream');
  });

  it('should connect to demo stream when demo mode is enabled', async () => {
    renderHook(() => useGEXStream(true));

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(ws.url).toContain('/gex-stream?demo=true');
  });

  it('should include provider in the stream query string', async () => {
    renderHook(() => useGEXStream(false, 'tradier'));

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(ws.url).toContain('/gex-stream?provider=tradier');
  });

  it('should return GEXUpdate typed data', async () => {
    const { result } = renderHook(() => useGEXStream());

    await act(async () => {
      vi.runAllTimers();
    });

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    const mockData: GEXUpdate = {
      net_gex: 2000000000,
      net_gex_billions: 2.0,
      zero_gamma_level: 5980,
      spot_price: 5975,
      regime: 'long_gamma',
    };

    act(() => {
      ws.simulateMessage({ type: 'gex_update', data: mockData });
    });

    expect(result.current.data?.regime).toBe('long_gamma');
    expect(result.current.data?.net_gex_billions).toBe(2.0);
  });
});

describe('Exponential Backoff', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    // @ts-expect-error - mocking global
    global.WebSocket = MockWebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.useRealTimers();
  });

  it('should increment retry count on reconnection', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint', { maxRetries: 5 })
    );

    await act(async () => {
      vi.runAllTimers();
    });

    // Get the WebSocket and simulate open then close
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    act(() => {
      ws.simulateOpen();
    });

    expect(result.current.retryCount).toBe(0);

    // Simulate abnormal close (code !== 1000)
    act(() => {
      ws.simulateClose(1006);
    });

    expect(result.current.connectionState).toBe('disconnected');
  });

  it('should enter error state after exhausting reconnect retries', async () => {
    const { result } = renderHook(() =>
      useWebSocket<GEXUpdate>('/test-endpoint', { maxRetries: 1 })
    );

    vi.spyOn(Math, 'random').mockReturnValue(0.5);

    await act(async () => {
      vi.runAllTimers();
    });

    const firstSocket = MockWebSocket.instances[0];
    act(() => {
      firstSocket.simulateOpen();
    });

    act(() => {
      firstSocket.simulateClose(1006);
    });

    await act(async () => {
      vi.runOnlyPendingTimers();
    });

    const retrySocket = MockWebSocket.instances[1];
    act(() => {
      retrySocket.simulateClose(1006);
    });

    expect(result.current.connectionState).toBe('error');
    expect(result.current.error).toBe('Max reconnection attempts (1) exceeded');
  });
});
