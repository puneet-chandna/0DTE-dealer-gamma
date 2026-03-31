"""0DTE GEX Backend - Technical Indicators via pandas-ta.

Computes ATR, RSI, and Bollinger Bands to overlay with GEX analysis.
Feature idea: "GEX vs ATR" — if spot moves > ATR while GEX is low,
volatility could explode.
"""

import logging

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Supported indicator names
SUPPORTED_INDICATORS = {"ATR", "RSI", "BBANDS"}


class TechnicalIndicatorEngine:
    """Calculate technical indicators for price data using pandas-ta.

    Supports:
    - ATR (Average True Range) — volatility measure
    - RSI (Relative Strength Index) — momentum oscillator
    - BBANDS (Bollinger Bands) — volatility bands
    """

    @staticmethod
    def compute_indicators(
        price_df: pd.DataFrame,
        indicators: list[str] | None = None,
        atr_length: int = 14,
        rsi_length: int = 14,
        bb_length: int = 20,
        bb_std: float = 2.0,
    ) -> pd.DataFrame:
        """Compute technical indicators and append them to the price DataFrame.

        Args:
            price_df: DataFrame with columns: open, high, low, close, volume.
                     Must have a DatetimeIndex or a 'date' column.
            indicators: List of indicator names to compute.
                       Defaults to all supported indicators.
            atr_length: ATR lookback period (default 14).
            rsi_length: RSI lookback period (default 14).
            bb_length: Bollinger Bands lookback period (default 20).
            bb_std: Bollinger Bands standard deviation multiplier (default 2.0).

        Returns:
            DataFrame with indicator columns appended.

        Raises:
            ValueError: If price_df is missing required columns or is too short.
        """
        if indicators is None:
            indicators = list(SUPPORTED_INDICATORS)

        # Normalize indicator names
        indicators = [i.upper() for i in indicators]

        # Validate requested indicators
        unsupported = set(indicators) - SUPPORTED_INDICATORS
        if unsupported:
            raise ValueError(
                f"Unsupported indicators: {unsupported}. "
                f"Supported: {SUPPORTED_INDICATORS}"
            )

        # Validate required columns
        required_cols = {"close"}
        if "ATR" in indicators or "BBANDS" in indicators:
            required_cols |= {"high", "low"}

        # Normalize column names to lowercase
        df = price_df.copy()
        df.columns = [c.lower() for c in df.columns]

        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            raise ValueError(
                f"Missing required columns: {missing_cols}. "
                f"Available: {set(df.columns)}"
            )

        if len(df) < 5:
            raise ValueError(
                f"Need at least 5 data points, got {len(df)}"
            )

        # Compute each indicator
        if "ATR" in indicators:
            atr = ta.atr(df["high"], df["low"], df["close"], length=atr_length)
            if atr is not None:
                df["atr"] = atr
            else:
                logger.warning("ATR computation returned None (not enough data?)")
                df["atr"] = float("nan")

        if "RSI" in indicators:
            rsi = ta.rsi(df["close"], length=rsi_length)
            if rsi is not None:
                df["rsi"] = rsi
            else:
                logger.warning("RSI computation returned None")
                df["rsi"] = float("nan")

        if "BBANDS" in indicators:
            bbands = ta.bbands(df["close"], length=bb_length, std=bb_std)
            if bbands is not None:
                # pandas-ta returns columns like BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
                cols = bbands.columns.tolist()
                df["bb_lower"] = bbands[cols[0]].values
                df["bb_mid"] = bbands[cols[1]].values
                df["bb_upper"] = bbands[cols[2]].values
                # Bandwidth and %B if available
                if len(cols) > 3:
                    df["bb_bandwidth"] = bbands[cols[3]].values
                if len(cols) > 4:
                    df["bb_pctb"] = bbands[cols[4]].values
            else:
                logger.warning("Bollinger Bands computation returned None")
                df["bb_lower"] = float("nan")
                df["bb_mid"] = float("nan")
                df["bb_upper"] = float("nan")

        return df

    @staticmethod
    def compute_gex_vs_atr(
        price_df: pd.DataFrame,
        gex_series: pd.Series,
        atr_length: int = 14,
    ) -> pd.DataFrame:
        """Compute GEX vs ATR metric for volatility explosion detection.

        When spot moves > ATR while GEX is low (short gamma),
        this signals potential for a volatility explosion.

        Args:
            price_df: DataFrame with high, low, close columns.
            gex_series: Series of net GEX values, indexed by timestamp.
            atr_length: ATR lookback period.

        Returns:
            DataFrame with columns: close, atr, net_gex, spot_move,
            move_exceeds_atr (bool), gex_is_short (bool), explosion_signal (bool).
        """
        df = price_df.copy()
        df.columns = [c.lower() for c in df.columns]

        # Compute ATR
        atr = ta.atr(df["high"], df["low"], df["close"], length=atr_length)
        if atr is None:
            raise ValueError("Could not compute ATR (insufficient data?)")

        df["atr"] = atr

        # Compute spot move (absolute change)
        df["spot_move"] = df["close"].diff().abs()

        # Align GEX data (forward-fill to match price timestamps)
        df["net_gex"] = gex_series.reindex(df.index, method="ffill")

        # Signal detection
        df["move_exceeds_atr"] = df["spot_move"] > df["atr"]
        df["gex_is_short"] = df["net_gex"] < 0
        df["explosion_signal"] = df["move_exceeds_atr"] & df["gex_is_short"]

        return df.dropna(subset=["atr"])
