"""Tests for the Hawkes Process Engine."""

import time
import numpy as np
import pandas as pd
import pytest

from app.core.hawkes_engine import HawkesEngine, HawkesState


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
