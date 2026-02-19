import pytest

from bot.models.ta_signal import TASignal
from tests.conftest import make_signal


def test_side_up():
    sig = make_signal(signal="BUY UP")
    assert sig.side == "UP"


def test_side_down():
    sig = make_signal(signal="BUY DOWN")
    assert sig.side == "DOWN"


def test_side_no_trade():
    sig = make_signal(signal="NO TRADE")
    assert sig.side is None


def test_ta_score_up():
    sig = make_signal(signal="BUY UP", adjustedUp=0.72, adjustedDown=0.28)
    assert sig.ta_score == 0.72


def test_ta_score_down():
    sig = make_signal(signal="BUY DOWN", adjustedUp=0.28, adjustedDown=0.72)
    assert sig.ta_score == 0.72


def test_ta_score_no_trade():
    sig = make_signal(signal="NO TRADE")
    assert sig.ta_score == 0.0


def test_token_price_up():
    sig = make_signal(signal="BUY UP", marketUp=0.35, marketDown=0.65)
    assert sig.token_price == 35


def test_token_price_down():
    sig = make_signal(signal="BUY DOWN", marketUp=0.35, marketDown=0.65)
    assert sig.token_price == 65


def test_token_price_no_trade():
    sig = make_signal(signal="NO TRADE", marketUp=0.35, marketDown=0.65)
    assert sig.token_price == 0


def test_market_up_cents():
    sig = make_signal(marketUp=0.49)
    assert sig.market_up_cents == 49


def test_market_down_cents():
    sig = make_signal(marketDown=0.51)
    assert sig.market_down_cents == 51


def test_market_cents_rounding():
    sig = make_signal(marketUp=0.04, marketDown=0.95)
    assert sig.market_up_cents == 4
    assert sig.market_down_cents == 95
