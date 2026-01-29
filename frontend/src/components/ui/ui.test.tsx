/**
 * UI Components Tests
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Card, CardHeader, CardContent, CardTitle, CardFooter } from './Card';
import { Badge } from './Badge';
import { Skeleton, SkeletonText, SkeletonValue, SkeletonCard } from './Skeleton';
import { MetricCard } from './MetricCard';

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
