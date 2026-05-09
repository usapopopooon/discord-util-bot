"""Ticket feature package smoke tests."""

from src.features.ticket import TicketCog, api_router


def test_ticket_feature_facade_exports() -> None:
    assert TicketCog.__name__ == "TicketCog"
    assert api_router is not None
