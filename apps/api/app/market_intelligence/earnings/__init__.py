"""Earnings Intelligence package — paper-only setups inside Market Intelligence."""

from app.market_intelligence.earnings.engine import evaluate_earnings_setup
from app.market_intelligence.earnings.service_api import build_earnings_desk

__all__ = ["evaluate_earnings_setup", "build_earnings_desk"]
