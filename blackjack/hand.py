"""Blackjack hand values. Cards are the detector's labels: rank then suit, e.g. '10H', 'AS', 'KD'."""


def rank(card: str) -> str:
    return card[:-1]


def value(card: str) -> int:
    r = rank(card)
    if r == 'A':
        return 1
    if r in ('J', 'Q', 'K'):
        return 10
    return int(r)


def total(cards: list[str]) -> tuple[int, bool]:
    """Best total and whether it is soft (an ace counted as 11)."""
    hard = sum(value(c) for c in cards)
    if any(rank(c) == 'A' for c in cards) and hard + 10 <= 21:
        return hard + 10, True
    return hard, False


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and total(cards)[0] == 21


def is_bust(cards: list[str]) -> bool:
    return total(cards)[0] > 21


def dealer_hits(cards: list[str]) -> bool:
    """Dealer draws below 17 and stands on every 17, soft ones included."""
    return total(cards)[0] < 17


def outcome(player: list[str], dealer: list[str]) -> str:
    """'player', 'dealer' or 'push'."""
    if is_bust(player):
        return 'dealer'
    if is_blackjack(player) and not is_blackjack(dealer):
        return 'player'
    if is_blackjack(dealer) and not is_blackjack(player):
        return 'dealer'
    if is_bust(dealer):
        return 'player'
    p, d = total(player)[0], total(dealer)[0]
    return 'player' if p > d else 'dealer' if d > p else 'push'
