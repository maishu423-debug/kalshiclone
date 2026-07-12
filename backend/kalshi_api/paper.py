import json
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.db import transaction

from .models import PaperAccount, PaperPosition, PaperTrade


STARTING_CASH_CENTS = 100_000
ACCOUNT_NAME = "default"


class PaperTradeError(Exception):
    pass


def get_account():
    return PaperAccount.objects.get_or_create(
        name=ACCOUNT_NAME,
        defaults={"cash_cents": STARTING_CASH_CENTS},
    )[0]


def decimal_to_float(value):
    return float(value.quantize(Decimal("0.0001")))


def money_to_cents(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def serialize_position(position):
    return {
        "market_ticker": position.market_ticker,
        "market_label": position.market_label,
        "side": position.side,
        "contracts": decimal_to_float(position.contracts),
        "avg_price_cents": float(position.avg_price_cents),
        "cost_basis_cents": money_to_cents(position.contracts * position.avg_price_cents),
    }


def serialize_trade(trade):
    return {
        "id": trade.id,
        "market_ticker": trade.market_ticker,
        "market_label": trade.market_label,
        "action": trade.action,
        "side": trade.side,
        "price_cents": trade.price_cents,
        "contracts": decimal_to_float(trade.contracts),
        "cash_delta_cents": trade.cash_delta_cents,
        "realized_pl_cents": trade.realized_pl_cents,
        "created_at": trade.created_at.isoformat(),
    }


def get_state():
    account = get_account()
    positions = PaperPosition.objects.filter(account=account, contracts__gt=0).order_by(
        "market_ticker",
        "side",
    )
    trades = PaperTrade.objects.filter(account=account).order_by("-created_at")[:20]

    # Aggregate realized P&L across ALL sell trades (not just last 20)
    all_sells = PaperTrade.objects.filter(
        account=account, action="sell", realized_pl_cents__isnull=False
    ).values_list("realized_pl_cents", flat=True)

    total_profit_cents = sum(v for v in all_sells if v > 0)
    total_loss_cents   = sum(v for v in all_sells if v < 0)

    return {
        "account": {
            "cash_cents": account.cash_cents,
            "starting_cash_cents": STARTING_CASH_CENTS,
            "total_profit_cents": total_profit_cents,
            "total_loss_cents":   total_loss_cents,
        },
        "positions": [serialize_position(position) for position in positions],
        "trades": [serialize_trade(trade) for trade in trades],
    }


def parse_order(raw_body):
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PaperTradeError("Invalid JSON body.") from exc

    action = payload.get("action")
    side = payload.get("side")
    market_ticker = payload.get("market_ticker")
    market_label = payload.get("market_label", "")
    price_cents = payload.get("price_cents")
    dollars_cents = payload.get("dollars_cents")

    if action not in {"buy", "sell"}:
        raise PaperTradeError("Action must be buy or sell.")
    if side not in {"yes", "no"}:
        raise PaperTradeError("Side must be yes or no.")
    if not market_ticker:
        raise PaperTradeError("Missing market ticker.")

    try:
        price_cents = int(price_cents)
        dollars_cents = int(dollars_cents)
    except (TypeError, ValueError) as exc:
        raise PaperTradeError("Price and dollars must be numbers.") from exc

    if price_cents <= 0 or price_cents >= 100:
        raise PaperTradeError("Price must be between 1 and 99 cents.")
    if dollars_cents <= 0:
        raise PaperTradeError("Enter a trade amount greater than $0.")

    return {
        "action": action,
        "side": side,
        "market_ticker": market_ticker,
        "market_label": market_label,
        "price_cents": price_cents,
        "dollars_cents": dollars_cents,
    }


@transaction.atomic
def place_order(order):
    account = PaperAccount.objects.select_for_update().get(pk=get_account().pk)
    price = Decimal(order["price_cents"])
    requested_cash = order["dollars_cents"]
    contracts = (Decimal(requested_cash) / price).quantize(
        Decimal("0.0001"),
        rounding=ROUND_DOWN,
    )

    if contracts <= 0:
        raise PaperTradeError("Trade amount is too small for this price.")

    cash_amount = money_to_cents(contracts * price)
    position, _created = PaperPosition.objects.select_for_update().get_or_create(
        account=account,
        market_ticker=order["market_ticker"],
        side=order["side"],
        defaults={
            "market_label": order["market_label"],
            "contracts": Decimal("0"),
            "avg_price_cents": Decimal("0"),
        },
    )
    position.market_label = order["market_label"]

    realized_pl = None

    if order["action"] == "buy":
        if cash_amount > account.cash_cents:
            raise PaperTradeError("Insufficient paper cash.")

        old_value = position.contracts * position.avg_price_cents
        new_value = contracts * price
        new_contracts = position.contracts + contracts
        position.avg_price_cents = (old_value + new_value) / new_contracts
        position.contracts = new_contracts
        account.cash_cents -= cash_amount
        cash_delta = -cash_amount
    else:
        if position.contracts <= 0:
            raise PaperTradeError("No position to sell.")
        if contracts > position.contracts:
            contracts = position.contracts
            cash_amount = money_to_cents(contracts * price)

        realized_pl = money_to_cents((price - position.avg_price_cents) * contracts)
        position.contracts -= contracts
        if position.contracts <= 0:
            position.avg_price_cents = Decimal("0")
        account.cash_cents += cash_amount
        cash_delta = cash_amount

    account.save(update_fields=["cash_cents", "updated_at"])
    position.save(update_fields=["market_label", "contracts", "avg_price_cents", "updated_at"])

    trade = PaperTrade.objects.create(
        account=account,
        market_ticker=order["market_ticker"],
        market_label=order["market_label"],
        action=order["action"],
        side=order["side"],
        price_cents=order["price_cents"],
        contracts=contracts,
        cash_delta_cents=cash_delta,
        realized_pl_cents=realized_pl if order["action"] == "sell" else None,
    )

    return {"trade": serialize_trade(trade), "state": get_state()}


@transaction.atomic
def reset_account():
    account = get_account()
    PaperPosition.objects.filter(account=account).delete()
    PaperTrade.objects.filter(account=account).delete()
    account.cash_cents = STARTING_CASH_CENTS
    account.save(update_fields=["cash_cents", "updated_at"])
    return get_state()
