/**
 * UI Components Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Card, CardHeader, CardContent, CardTitle, CardFooter } from './Card';
import { Badge } from './Badge';
import { Skeleton, SkeletonText, SkeletonValue, SkeletonCard } from './Skeleton';
import { MetricCard } from './MetricCard';
import { AlertBanner, regimeDescriptions } from './AlertBanner';

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, className, ...props }: { children: React.ReactNode; className?: string }) => (
      <div className={className} {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe('Card Components', () => {
  it('renders Card with children', () => {
    render(<Card data-testid="card">Card Content</Card>);
    expect(screen.getByText('Card Content')).toBeInTheDocument();
  });

  it('renders CardHeader correctly', () => {
    render(<CardHeader>Header</CardHeader>);
    expect(screen.getByText('Header')).toBeInTheDocument();
  });

  it('renders CardContent correctly', () => {
    render(<CardContent>Content</CardContent>);
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('renders CardTitle correctly', () => {
    render(<CardTitle>Title</CardTitle>);
    expect(screen.getByText('Title')).toBeInTheDocument();
  });

  it('renders CardFooter correctly', () => {
    render(<CardFooter>Footer</CardFooter>);
    expect(screen.getByText('Footer')).toBeInTheDocument();
  });

  it('applies custom className to Card', () => {
    const { container } = render(<Card className="custom-class">Content</Card>);
    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('uses responsive padding classes for card sections', () => {
    const { container: headerContainer } = render(<CardHeader>Header</CardHeader>);
    const { container: contentContainer } = render(<CardContent>Content</CardContent>);
    const { container: footerContainer } = render(<CardFooter>Footer</CardFooter>);

    expect(headerContainer.firstChild).toHaveClass('px-4', 'py-3', 'sm:px-5', 'sm:py-4');
    expect(contentContainer.firstChild).toHaveClass('px-4', 'py-3', 'sm:px-5', 'sm:py-4');
    expect(footerContainer.firstChild).toHaveClass('px-4', 'py-3', 'sm:px-5');
  });
});

describe('Badge', () => {
  it('renders Badge with children', () => {
    render(<Badge>Status</Badge>);
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('applies variant styles', () => {
    const { container } = render(<Badge variant="success">Success</Badge>);
    expect(container.firstChild).toHaveClass('text-emerald-400');
  });

  it('renders danger variant correctly', () => {
    const { container } = render(<Badge variant="danger">Danger</Badge>);
    expect(container.firstChild).toHaveClass('text-rose-400');
  });

  it('renders warning variant correctly', () => {
    const { container } = render(<Badge variant="warning">Warning</Badge>);
    expect(container.firstChild).toHaveClass('text-amber-400');
  });

  it('renders with pulse indicator', () => {
    const { container } = render(<Badge variant="success" pulse>Live</Badge>);
    expect(container.querySelector('.animate-ping')).toBeInTheDocument();
  });
});

describe('Skeleton', () => {
  it('renders base Skeleton', () => {
    const { container } = render(<Skeleton className="h-4 w-20" />);
    expect(container.firstChild).toHaveClass('animate-pulse');
    expect(container.firstChild).toHaveClass('h-4');
    expect(container.firstChild).toHaveClass('w-20');
  });

  it('renders SkeletonText', () => {
    const { container } = render(<SkeletonText />);
    expect(container.firstChild).toHaveClass('h-4');
    expect(container.firstChild).toHaveClass('w-full');
  });

  it('renders SkeletonValue', () => {
    const { container } = render(<SkeletonValue />);
    expect(container.firstChild).toHaveClass('h-8');
    expect(container.firstChild).toHaveClass('w-32');
  });

  it('renders SkeletonCard with header', () => {
    render(<SkeletonCard showHeader={true} />);
    // Should have two skeleton elements (title + value)
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThanOrEqual(2);
  });

  it('renders SkeletonCard without header', () => {
    const { container } = render(<SkeletonCard showHeader={false} />);
    // Should not have border-b class for header
    expect(container.querySelector('.border-b')).toBeNull();
  });
});

describe('MetricCard', () => {
  it('renders with label and value', () => {
    render(<MetricCard label="Test Label" value="$100" />);
    expect(screen.getByText('Test Label')).toBeInTheDocument();
    expect(screen.getByText('$100')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    const { container } = render(<MetricCard label="Loading" value="" isLoading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('applies negative color when isNegative', () => {
    render(<MetricCard label="Negative" value="-$100" isNegative />);
    const value = screen.getByText('-$100');
    expect(value).toHaveClass('text-rose-400');
  });

  it('applies positive color when isPositive', () => {
    render(<MetricCard label="Positive" value="+$100" isPositive />);
    const value = screen.getByText('+$100');
    expect(value).toHaveClass('text-emerald-400');
  });

  it('renders with subtext', () => {
    render(
      <MetricCard
        label="With Subtext"
        value="$100"
        subtext="Additional info"
      />
    );
    expect(screen.getByText('Additional info')).toBeInTheDocument();
  });

  it('renders with trend indicator', () => {
    render(
      <MetricCard
        label="With Trend"
        value="$100"
        trend="up"
        trendValue="+5%"
      />
    );
    expect(screen.getByText('+5%')).toBeInTheDocument();
  });
});

describe('AlertBanner', () => {
  it('renders short_gamma regime correctly', () => {
    render(<AlertBanner regime="short_gamma" />);
    expect(screen.getByText('Short Gamma')).toBeInTheDocument();
  });

  it('renders long_gamma regime correctly', () => {
    render(<AlertBanner regime="long_gamma" />);
    expect(screen.getByText('Long Gamma')).toBeInTheDocument();
  });

  it('renders neutral regime correctly', () => {
    render(<AlertBanner regime="neutral" />);
    expect(screen.getByText('Neutral')).toBeInTheDocument();
  });

  it('displays net GEX billions value', () => {
    render(<AlertBanner regime="short_gamma" netGexBillions={-1.5} />);
    expect(screen.getByText('(-1.50B)')).toBeInTheDocument();
  });

  it('displays positive GEX with + sign', () => {
    render(<AlertBanner regime="long_gamma" netGexBillions={2.0} />);
    expect(screen.getByText('(+2.00B)')).toBeInTheDocument();
  });

  it('displays description when provided', () => {
    render(
      <AlertBanner
        regime="short_gamma"
        description="Market volatility expected"
      />
    );
    expect(screen.getByText('Market volatility expected')).toBeInTheDocument();
  });

  it('does not render when isVisible is false', () => {
    render(<AlertBanner regime="short_gamma" isVisible={false} />);
    expect(screen.queryByText('Short Gamma')).not.toBeInTheDocument();
  });

  it('renders dismiss button when onDismiss is provided', () => {
    const onDismiss = vi.fn();
    render(<AlertBanner regime="neutral" onDismiss={onDismiss} />);
    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    expect(dismissButton).toBeInTheDocument();
  });

  it('calls onDismiss when dismiss button is clicked', () => {
    const onDismiss = vi.fn();
    render(<AlertBanner regime="neutral" onDismiss={onDismiss} />);
    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissButton);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('applies correct styling for short_gamma (danger)', () => {
    const { container } = render(<AlertBanner regime="short_gamma" />);
    const banner = container.firstChild as HTMLElement;
    expect(banner).toHaveClass('bg-rose-500/10');
    expect(banner).toHaveClass('border-rose-500/30');
  });

  it('applies correct styling for long_gamma (success)', () => {
    const { container } = render(<AlertBanner regime="long_gamma" />);
    const banner = container.firstChild as HTMLElement;
    expect(banner).toHaveClass('bg-emerald-500/10');
    expect(banner).toHaveClass('border-emerald-500/30');
  });

  it('applies correct styling for neutral (warning)', () => {
    const { container } = render(<AlertBanner regime="neutral" />);
    const banner = container.firstChild as HTMLElement;
    expect(banner).toHaveClass('bg-amber-500/10');
    expect(banner).toHaveClass('border-amber-500/30');
  });
});

describe('regimeDescriptions', () => {
  it('has description for short_gamma', () => {
    expect(regimeDescriptions.short_gamma).toBe(
      'Dealers are short gamma. Volatility amplification expected.'
    );
  });

  it('has description for long_gamma', () => {
    expect(regimeDescriptions.long_gamma).toBe(
      'Dealers are long gamma. Volatility dampening expected.'
    );
  });

  it('has description for neutral', () => {
    expect(regimeDescriptions.neutral).toBe(
      'Near neutral gamma positioning. Normal volatility expected.'
    );
  });
});
