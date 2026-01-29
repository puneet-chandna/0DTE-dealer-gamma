/**
 * Chart Components Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChartErrorBoundary } from './ChartErrorBoundary';
import { RegimeIndicator } from './RegimeIndicator';
import { ZeroGammaLine, zeroGammaReferenceLineConfig } from './ZeroGammaLine';

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

describe('ChartErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ChartErrorBoundary>
        <div>Chart Content</div>
      </ChartErrorBoundary>
    );
    expect(screen.getByText('Chart Content')).toBeInTheDocument();
  });

  it('renders fallback when provided and error occurs', () => {
    const ThrowError = () => {
      throw new Error('Test error');
    };
    
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    render(
      <ChartErrorBoundary fallback={<div>Custom Fallback</div>}>
        <ThrowError />
      </ChartErrorBoundary>
    );
    
    expect(screen.getByText('Custom Fallback')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('renders default error UI with chart name', () => {
    const ThrowError = () => {
      throw new Error('Test error');
    };
    
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    render(
      <ChartErrorBoundary chartName="GEX Bar Chart">
        <ThrowError />
      </ChartErrorBoundary>
    );
    
    expect(screen.getByText('GEX Bar Chart Error')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });
});

describe('RegimeIndicator', () => {
  it('renders short_gamma regime correctly', () => {
    render(<RegimeIndicator regime="short_gamma" />);
    expect(screen.getByText('Short Gamma')).toBeInTheDocument();
    expect(screen.getByText('Volatility amplification expected')).toBeInTheDocument();
  });

  it('renders long_gamma regime correctly', () => {
    render(<RegimeIndicator regime="long_gamma" />);
    expect(screen.getByText('Long Gamma')).toBeInTheDocument();
    expect(screen.getByText('Volatility dampening expected')).toBeInTheDocument();
  });

  it('renders neutral regime correctly', () => {
    render(<RegimeIndicator regime="neutral" />);
    expect(screen.getByText('Neutral')).toBeInTheDocument();
    expect(screen.getByText('Normal volatility expected')).toBeInTheDocument();
  });

  it('renders compact mode', () => {
    const { container } = render(<RegimeIndicator regime="short_gamma" compact />);
    // Compact mode should have smaller indicator (h-3 w-3)
    expect(container.querySelector('.h-3.w-3')).toBeInTheDocument();
  });

  it('displays net GEX billions value', () => {
    render(<RegimeIndicator regime="short_gamma" netGexBillions={-1.5} />);
    expect(screen.getByText('(-1.50B)')).toBeInTheDocument();
  });

  it('displays custom description', () => {
    render(
      <RegimeIndicator
        regime="short_gamma"
        description="Custom description text"
      />
    );
    expect(screen.getByText('Custom description text')).toBeInTheDocument();
  });
});

describe('ZeroGammaLine', () => {
  it('renders zero gamma value', () => {
    render(<ZeroGammaLine value={5925} />);
    expect(screen.getByText('Zero Γ')).toBeInTheDocument();
    expect(screen.getByText('$5,925')).toBeInTheDocument();
  });

  it('shows distance from spot price', () => {
    // Zero gamma 5925 < spot 5950 means spot is ABOVE zero gamma
    render(<ZeroGammaLine value={5925} spotPrice={5950} />);
    // The component shows "Above spot by $X (Y%)"
    expect(screen.getByText(/Above/i)).toBeInTheDocument();
  });

  it('shows below spot when zero gamma is higher', () => {
    // Zero gamma 5975 > spot 5950 means spot is BELOW zero gamma
    render(<ZeroGammaLine value={5975} spotPrice={5950} />);
    // The component shows "Below spot by $X (Y%)"
    expect(screen.getByText(/Below/i)).toBeInTheDocument();
  });
});

describe('zeroGammaReferenceLineConfig', () => {
  it('returns correct configuration object', () => {
    const config = zeroGammaReferenceLineConfig(5925);
    
    expect(config.x).toBe(5925);
    expect(config.stroke).toBe('#a78bfa');
    expect(config.strokeWidth).toBe(2);
    expect(config.strokeDasharray).toBe('8 4');
    expect(config.label.value).toBe('0Γ: $5,925');
    expect(config.label.position).toBe('top');
    expect(config.label.fill).toBe('#a78bfa');
  });
});
