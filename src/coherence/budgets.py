"""Shared-budget ledger with atomic reserve / commit / release.

A reservation holds funds (or calls, or tokens) while an agent works.
Nothing is spent until the harness commits the proposal, and a rejected
proposal releases every reservation it made, so two agents that each
check "enough remains" locally can never jointly overspend a cap the
harness enforces at commit time.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .units import Quantity


class BudgetExceeded(ValueError):
    """Raised when a reservation would exceed the remaining budget."""


@dataclass
class Reservation:
    id: int
    budget: str
    amount: Quantity
    owner: str
    state: str = "held"  # held -> committed | released


@dataclass
class Budget:
    name: str
    cap: Quantity
    _spent: float = 0.0  # canonical units
    _reserved: float = 0.0

    @property
    def spent(self) -> Quantity:
        return Quantity(self._spent, self.cap.canonical().unit).to(self.cap.unit)

    @property
    def reserved(self) -> Quantity:
        return Quantity(self._reserved, self.cap.canonical().unit).to(self.cap.unit)

    @property
    def remaining(self) -> Quantity:
        return Quantity(
            self.cap.canonical().value - self._spent - self._reserved,
            self.cap.canonical().unit,
        ).to(self.cap.unit)

    def can_reserve(self, amount: Quantity) -> bool:
        return amount.canonical().value <= self.remaining.canonical().value + 1e-9


@dataclass
class Ledger:
    budgets: dict = field(default_factory=dict)
    _reservations: dict = field(default_factory=dict)
    _counter: itertools.count = field(default_factory=itertools.count, repr=False)
    events: list = field(default_factory=list)

    def add_budget(self, budget: Budget):
        self.budgets[budget.name] = budget
        return budget

    def reserve(self, budget_name, amount: Quantity, owner: str, force: bool = False) -> Reservation:
        budget = self.budgets[budget_name]
        if not force and not budget.can_reserve(amount):
            raise BudgetExceeded(
                f"budget {budget_name!r}: reserving {amount} would exceed "
                f"remaining {budget.remaining}"
            )
        rid = next(self._counter) + 1
        reservation = Reservation(id=rid, budget=budget_name, amount=amount, owner=owner)
        canonical = amount.canonical().value
        budget._reserved += canonical
        self._reservations[rid] = reservation
        self.events.append({"event": "reserve", "id": rid, "budget": budget_name,
                            "amount": canonical, "owner": owner})
        return reservation

    def reserve_all(self, requests, owner: str):
        """Reserve several budgets atomically: all succeed or none do."""
        amounts = []
        for budget_name, amount in requests:
            budget = self.budgets[budget_name]
            if not budget.can_reserve(amount):
                raise BudgetExceeded(
                    f"budget {budget_name!r}: reserving {amount} would exceed "
                    f"remaining {budget.remaining}"
                )
            amounts.append((budget, amount))
        reservations = []
        for budget, amount in amounts:
            reservations.append(self.reserve(budget.name, amount, owner))
        return reservations

    def commit(self, reservation: Reservation):
        if reservation.state != "held":
            raise ValueError(f"reservation {reservation.id} is {reservation.state}, not held")
        budget = self.budgets[reservation.budget]
        canonical = reservation.amount.canonical().value
        budget._reserved -= canonical
        budget._spent += canonical
        reservation.state = "committed"
        self.events.append({"event": "commit", "id": reservation.id,
                            "budget": reservation.budget, "amount": canonical})
        return reservation

    def release(self, reservation: Reservation):
        if reservation.state != "held":
            return reservation
        budget = self.budgets[reservation.budget]
        budget._reserved -= reservation.amount.canonical().value
        reservation.state = "released"
        self.events.append({"event": "release", "id": reservation.id,
                            "budget": reservation.budget})
        return reservation

    def release_all(self, reservations):
        for reservation in reservations:
            self.release(reservation)

    def total_spent(self, budget_name) -> Quantity:
        return self.budgets[budget_name].spent

    def is_over_cap(self, budget_name) -> bool:
        budget = self.budgets[budget_name]
        return budget.spent.canonical().value > budget.cap.canonical().value + 1e-9
