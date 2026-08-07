"""Options strike selection prefers developing ATM–OTM setups."""

from app.providers.options.yahoo import _setup_priority, _strike_in_developing_band
from app.engine.models import CandidateOpportunity, SignalModule
from datetime import date, timedelta


def test_call_band_rejects_deep_itm_allows_modest_otm():
    spot = 100.0
    assert _strike_in_developing_band("call", 100.0, spot) is True  # ATM
    assert _strike_in_developing_band("call", 103.0, spot) is True  # ~3% OTM
    assert _strike_in_developing_band("call", 108.0, spot) is True  # ~8% OTM inside 10%
    assert _strike_in_developing_band("call", 99.0, spot) is True  # tiny ITM
    assert _strike_in_developing_band("call", 95.0, spot) is False  # deep ITM
    assert _strike_in_developing_band("call", 112.0, spot) is False  # too far OTM


def test_put_band_rejects_deep_itm_allows_modest_otm():
    spot = 100.0
    assert _strike_in_developing_band("put", 100.0, spot) is True
    assert _strike_in_developing_band("put", 97.0, spot) is True
    assert _strike_in_developing_band("put", 101.0, spot) is True  # tiny ITM
    assert _strike_in_developing_band("put", 105.0, spot) is False  # deep ITM
    assert _strike_in_developing_band("put", 88.0, spot) is False


def test_setup_priority_prefers_developing_otm():
    def cand(strike: float) -> CandidateOpportunity:
        return CandidateOpportunity(
            module=SignalModule.OPTIONS,
            symbol="TEST",
            option_type="call",
            strike=strike,
            expiration=date.today() + timedelta(days=10),
            premium=1.0,
            volume=100,
            open_interest=500,
            metadata={"stock_price": 100.0},
        )

    developing = _setup_priority(cand(103.0))
    itm = _setup_priority(cand(99.2))
    assert developing[0] > itm[0]
