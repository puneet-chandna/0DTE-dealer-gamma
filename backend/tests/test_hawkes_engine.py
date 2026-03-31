"""Tests for the Hawkes Process Engine."""

import pandas as pd
import pytest

from app.core.hawkes_engine import HawkesEngine


class TestHawkesEngine:
    """Tests for the snapshot-based Hawkes process."""

    def test_initial_state_is_zero(self):
        """Initial state should have zero intensities."""
        engine = HawkesEngine()
        state = engine.get_state()

        assert state.call_intensity == 0.0
        assert state.put_intensity == 0.0
        assert state.net_toxicity == 0.0
        assert state.squeeze_probability == 0.0

    def test_first_update_no_prior(self):
        """First update has no prior volumes, so no delta → zero intensity."""
        engine = HawkesEngine()
        df = pd.DataFrame({
            "strike": [5800.0, 5800.0],
            "type": ["call", "put"],
            "volume": [100, 200],
        })

        state = engine.update(df, timestamp=1000.0)

        # First update: no prior volumes to compare, so intensities stay at 0
        assert state.call_intensity == 0.0
        assert state.put_intensity == 0.0

    def test_volume_increase_fires_event(self):
        """Increased volume between snapshots should raise intensity."""
        engine = HawkesEngine(alpha=0.1, volume_threshold=10)

        # First snapshot: set baseline volumes
        df1 = pd.DataFrame({
            "strike": [5800.0, 5800.0],
            "type": ["call", "put"],
            "volume": [100, 100],
        })
        engine.update(df1, timestamp=1000.0)

        # Second snapshot: call volume jumped by 100
        df2 = pd.DataFrame({
            "strike": [5800.0, 5800.0],
            "type": ["call", "put"],
            "volume": [200, 100],
        })
        state = engine.update(df2, timestamp=1005.0)

        assert state.call_intensity > 0
        assert state.put_intensity == pytest.approx(0.0, abs=1e-6)
        assert state.net_toxicity > 0

    def test_decay_reduces_intensity(self):
        """Without new events, intensity should decay exponentially."""
        engine = HawkesEngine(alpha=0.1, beta=0.5, volume_threshold=10)

        # Create an event
        df1 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [100],
        })
        engine.update(df1, timestamp=1000.0)

        df2 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [200],
        })
        state_after_event = engine.update(df2, timestamp=1005.0)

        # Now pass time with no volume change
        df3 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [200],  # Same volume, no new events
        })
        state_after_decay = engine.update(df3, timestamp=1010.0)

        # Intensity should have decayed
        assert state_after_decay.call_intensity < state_after_event.call_intensity

    def test_squeeze_probability_bounded(self):
        """Squeeze probability should always be between 0 and 1."""
        engine = HawkesEngine()

        # Create a large event
        df1 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [0],
        })
        engine.update(df1, timestamp=1000.0)

        df2 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [10000],  # Massive volume spike
        })
        state = engine.update(df2, timestamp=1005.0)

        assert 0.0 <= state.squeeze_probability <= 1.0

    def test_reset(self):
        """Reset should clear all state."""
        engine = HawkesEngine()

        # Create some state
        df1 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [100],
        })
        engine.update(df1, timestamp=1000.0)

        df2 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [200],
        })
        engine.update(df2, timestamp=1005.0)

        # Reset
        engine.reset()
        state = engine.get_state()

        assert state.call_intensity == 0.0
        assert state.put_intensity == 0.0

    def test_missing_volume_column(self):
        """DataFrame without 'volume' column should not crash."""
        engine = HawkesEngine()
        df = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "open_interest": [100],
        })

        state = engine.update(df)
        assert state.call_intensity == 0.0

    def test_empty_dataframe(self):
        """Empty DataFrame should not crash."""
        engine = HawkesEngine()
        state = engine.update(pd.DataFrame())
        assert state.call_intensity == 0.0

    def test_restore_state_rejects_missing_required_keys_without_mutating_state(self):
        """Invalid restore payloads should fail before mutating engine state."""
        engine = HawkesEngine()
        original_state = engine.snapshot_state()

        with pytest.raises(ValueError, match="missing required keys"):
            engine.restore_state({
                "call_intensity": 99.0,
                "put_intensity": 77.0,
            })

        assert engine.snapshot_state() == original_state

    def test_new_contracts_are_baselined_before_scoring_and_metadata_is_exposed(self):
        """Only contracts seen in consecutive snapshots should contribute events."""
        engine = HawkesEngine(alpha=1.0, beta=0.0, volume_threshold=1)

        df1 = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "volume": [100],
            "open_interest": [250],
            "bid": [10.0],
            "ask": [10.4],
            "mid": [10.2],
            "implied_vol": [0.18],
            "delta": [0.52],
            "gamma": [0.012],
            "expiration": ["2099-01-15T16:00:00-05:00"],
        })
        engine.update(
            df1,
            timestamp=1000.0,
            spot_price=5805.0,
            provider_mode="tradier_rich",
        )

        df2 = pd.DataFrame({
            "strike": [5800.0, 5820.0],
            "type": ["call", "call"],
            "volume": [140, 500],
            "open_interest": [265, 900],
            "bid": [10.1, 4.5],
            "ask": [10.5, 5.0],
            "mid": [10.3, 4.75],
            "implied_vol": [0.18, 0.22],
            "delta": [0.53, 0.21],
            "gamma": [0.012, 0.008],
            "expiration": ["2099-01-15T16:00:00-05:00", "2099-01-15T16:00:00-05:00"],
        })
        state = engine.update(
            df2,
            timestamp=1005.0,
            spot_price=5805.0,
            provider_mode="tradier_rich",
        )

        assert state.call_intensity > 0
        assert state.event_count == 1
        assert state.baseline_ready is True
        assert state.provider_mode == "tradier_rich"
        assert state.confidence_score > 0.8

    def test_yfinance_proxy_mode_computes_missing_greeks_and_reports_lower_confidence(self):
        """yfinance snapshots without provider Greeks should still yield a lower-confidence signal."""
        engine = HawkesEngine(alpha=1.0, beta=0.0, volume_threshold=1)

        df1 = pd.DataFrame({
            "strike": [6000.0],
            "type": ["call"],
            "volume": [75],
            "open_interest": [180],
            "bid": [9.8],
            "ask": [10.2],
            "mid": [10.0],
            "implied_vol": [0.21],
            "delta": [None],
            "gamma": [None],
            "expiration": ["2099-01-15T16:00:00-05:00"],
        })
        engine.update(
            df1,
            timestamp=1000.0,
            spot_price=6030.0,
            provider_mode="yfinance_proxy",
        )

        df2 = pd.DataFrame({
            "strike": [6000.0],
            "type": ["call"],
            "volume": [110],
            "open_interest": [205],
            "bid": [10.0],
            "ask": [10.5],
            "mid": [10.25],
            "implied_vol": [0.22],
            "delta": [None],
            "gamma": [None],
            "expiration": ["2099-01-15T16:00:00-05:00"],
        })
        state = engine.update(
            df2,
            timestamp=1005.0,
            spot_price=6030.0,
            provider_mode="yfinance_proxy",
        )

        assert state.call_intensity > 0
        assert state.baseline_ready is True
        assert state.provider_mode == "yfinance_proxy"
        assert 0.0 < state.confidence_score < 0.8
        assert state.event_count == 1
