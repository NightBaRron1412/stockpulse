"""Post-Earnings Drift (PEAD) -- expert-specified surprise + tape confirmation."""

import logging
import math
from datetime import datetime, timedelta

from stockpulse.data.provider import get_price_history, get_current_quote
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def calc_pead_score(ticker: str) -> float:
    """Compute post-earnings drift score.

    Only active in the 1-20 trading days after an earnings report.
    Uses EPS surprise, revenue surprise, day-1 tape, and gap-hold.
    Returns 0 if no recent earnings or data unavailable.
    """
    cache_key = f"pead_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        import finnhub
        from stockpulse.config.settings import get_config
        cfg = get_config()
        client = finnhub.Client(api_key=cfg["finnhub_api_key"])

        # Look back 30 days for recent earnings
        today = datetime.now()
        past = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        data = client.earnings_calendar(_from=past, to=today_str, symbol=ticker)
        earnings = [e for e in data.get("earningsCalendar", [])
                    if e.get("symbol") == ticker
                    and e.get("epsActual") is not None
                    and e.get("epsEstimate") is not None]

        if not earnings:
            set_cached(cache_key, 0.0)
            return 0.0

        # Use most recent earnings
        latest = earnings[0]
        eps_actual = latest.get("epsActual", 0)
        eps_estimate = latest.get("epsEstimate", 0)
        rev_actual = latest.get("revenueActual", 0) or 0
        rev_estimate = latest.get("revenueEstimate", 0) or 0
        earnings_date = latest.get("date", "")

        if not earnings_date:
            set_cached(cache_key, 0.0)
            return 0.0

        # Check if within PEAD window (1-30 calendar days post-earnings)
        try:
            earn_dt = datetime.strptime(earnings_date, "%Y-%m-%d")
            days_since = (today - earn_dt).days
        except ValueError:
            set_cached(cache_key, 0.0)
            return 0.0

        if days_since < 1 or days_since > 30:
            set_cached(cache_key, 0.0)
            return 0.0

        # EPS surprise
        eps_surprise = (eps_actual - eps_estimate) / max(abs(eps_estimate), 0.10)

        # Revenue surprise
        rev_surprise = 0.0
        if rev_actual and rev_estimate:
            rev_surprise = (rev_actual - rev_estimate) / max(abs(rev_estimate), 1.0)

        # Normalize surprises (simple scaling -- typical surprise ~ 0.05-0.20)
        eps_z = eps_surprise / 0.15  # ~1 std at 15% surprise
        rev_z = rev_surprise / 0.03  # ~1 std at 3% revenue surprise

        # Tape confirmation: day-1 relative return and RVOL
        tape_z = 0.0
        gap_hold = 0.0
        try:
            df = get_price_history(ticker, period="3mo")
            spy_df = get_price_history("SPY", period="3mo")

            if not df.empty and not spy_df.empty and len(df) > 5:
                # Find the earnings date in the price data
                earn_date_ts = earn_dt.date()
                # Get indices after earnings date
                post_earn = df[df.index.date > earn_date_ts]

                if len(post_earn) >= 2:
                    # Day 1 after earnings
                    pre_earn_close = float(
                        df["Close"].iloc[-len(post_earn) - 1]
                    )
                    day1_ret = (
                        float(post_earn["Close"].iloc[0]) - pre_earn_close
                    ) / pre_earn_close

                    # SPY day 1
                    spy_post = spy_df[spy_df.index.date > earn_date_ts]
                    if len(spy_post) >= 1:
                        spy_pre_close = float(
                            spy_df["Close"].iloc[-len(spy_post) - 1]
                        )
                        spy_day1_ret = (
                            float(spy_post["Close"].iloc[0]) - spy_pre_close
                        ) / spy_pre_close
                        rel_ret = day1_ret - spy_day1_ret
                    else:
                        rel_ret = day1_ret

                    # RVOL on day 1
                    if len(df) > 30:
                        avg_vol = float(df["Volume"].iloc[-30:-1].mean())
                    else:
                        avg_vol = float(df["Volume"].mean())
                    day1_vol = float(post_earn["Volume"].iloc[0])
                    rvol = day1_vol / avg_vol if avg_vol > 0 else 1.0

                    tape_z = (
                        0.6 * (rel_ret / 0.02)
                        + 0.4 * (math.log(max(rvol, 0.1)) / 0.7)
                    )

                    # Gap hold flag
                    day1_close = float(post_earn["Close"].iloc[0])
                    day1_high = float(post_earn["High"].iloc[0])
                    day1_low = float(post_earn["Low"].iloc[0])
                    day1_range = day1_high - day1_low

                    close_in_top_35 = (
                        (day1_close - day1_low) / day1_range >= 0.65
                        if day1_range > 0
                        else False
                    )

                    if len(post_earn) >= 2:
                        day2_low = float(post_earn["Low"].iloc[1])
                        # within 0.5% of prior close
                        gap_holds = day2_low >= pre_earn_close * 0.995

                        if close_in_top_35 and gap_holds:
                            gap_hold = 1.0
        except Exception:
            logger.debug("PEAD tape analysis failed for %s", ticker)

        # Expert's PEAD formula
        pead_score = (
            0.45 * eps_z
            + 0.20 * rev_z
            + 0.25 * tape_z
            + 0.10 * gap_hold
        )

        # Scale to [-100, 100] (typical z-score range -3 to +3)
        scaled = pead_score * 30
        result = max(-100.0, min(100.0, scaled))

        # Decay over time (strongest in first 5 days, fades by day 20)
        decay = max(0.2, 1.0 - (days_since / 25.0))
        result *= decay

        set_cached(cache_key, result)
        return result
    except Exception:
        logger.debug("PEAD calculation failed for %s", ticker)
        return 0.0
