"""Thread-safe monetary admission. Quotes remain in memory; snapshots contain no rates."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal,ROUND_CEILING
import threading
from uuid import uuid4

from mira.pricing import PriceBook,PricingError

UNIT=Decimal('.000001')


class SpendingError(RuntimeError):
    """A safe refusal before another paid request, or an unexpected usage overrun."""


def _amount(value) -> Decimal:
    try:amount=value if isinstance(value,Decimal) else Decimal(str(value))
    except Exception:raise SpendingError('Invalid monetary amount') from None
    if not amount.is_finite() or amount<0:raise SpendingError('Invalid monetary amount')
    return amount


def _money(value) -> Decimal:
    return _amount(value).quantize(UNIT,rounding=ROUND_CEILING)


@dataclass(frozen=True)
class SpendTicket:
    id: str
    kind: str
    role: str
    provider: str
    model: str
    reserved_usd: Decimal


class SpendingLedger:
    def __init__(self,max_usd: Decimal,price_book: PriceBook,*,known_usd: Decimal=Decimal(0),
                 unknown_usd: Decimal=Decimal(0)):
        self.max_usd=_amount(max_usd)
        if not Decimal(0)<self.max_usd<=Decimal(1000):raise SpendingError('USD allowance must be positive and at most 1000')
        self.price_book=price_book
        self.known=_money(known_usd);self.unknown=_money(unknown_usd);self.pending=Decimal(0)
        self._pending: dict[str,SpendTicket]={};self._lock=threading.RLock()

    def _reserve(self,kind,role,provider,model,cost):
        cost=_money(cost)
        protected=Decimal(0) if role=='writer' else self.max_usd/Decimal(5)
        with self._lock:
            if self.known+self.unknown+self.pending+cost+protected>self.max_usd:
                raise SpendingError('API cost allowance or downstream reserve reached')
            ticket=SpendTicket(uuid4().hex,kind,role,provider,model,cost)
            self._pending[ticket.id]=ticket;self.pending+=cost
            return ticket

    def reserve_model(self,role: str,provider: str,model: str,input_upper: int,max_output: int) -> SpendTicket:
        try:cost=self.price_book.token_rate(provider,model).cost(input_upper,max_output)
        except PricingError:raise SpendingError('No validated price for this provider/model') from None
        return self._reserve('model',role,provider,model,cost)

    def reserve_embedding(self,provider: str,model: str,input_upper: int) -> SpendTicket:
        try:cost=self.price_book.token_rate(provider,model).cost(input_upper,0)
        except PricingError:raise SpendingError('No validated embedding price') from None
        return self._reserve('embedding','experimental_hybrid',provider,model,cost)

    def reserve_search(self,result_limit: int) -> SpendTicket:
        try:cost=self.price_book.search_cost(result_limit)
        except PricingError:raise SpendingError('No validated Exa search price') from None
        return self._reserve('search','regulatory_scout','exa','auto',cost)

    def settle(self,ticket: SpendTicket,*,tokens_in: int | None=None,tokens_out: int | None=None,
               request_sent: bool | None=True):
        with self._lock:
            if self._pending.get(ticket.id) is not ticket:raise SpendingError('Cost reservation already settled or unknown')
            if request_sent is False and not (tokens_in or tokens_out):known=unknown=Decimal(0)
            elif tokens_in is None or tokens_out is None:known=Decimal(0);unknown=ticket.reserved_usd
            elif ticket.kind=='search':known=ticket.reserved_usd;unknown=Decimal(0)
            else:
                try:known=_money(self.price_book.token_rate(ticket.provider,ticket.model).cost(tokens_in,tokens_out))
                except (PricingError,ValueError):raise SpendingError('Measured usage could not be priced') from None
                unknown=Decimal(0)
            self.pending-=ticket.reserved_usd;del self._pending[ticket.id]
            self.known+=known;self.unknown+=unknown
            if known>ticket.reserved_usd or self.known+self.unknown+self.pending>self.max_usd:
                raise SpendingError('Provider usage exceeded its reserved estimate; further requests stopped')

    def snapshot(self) -> dict:
        with self._lock:
            return {'max_usd':str(self.max_usd),'known_estimated_usd':str(self.known),
                'unknown_reserved_usd':str(self.unknown),'pending_usd':str(_money(self.pending)),
                'allowance_used_usd':str(_money(self.known+self.unknown+self.pending)),
                'pricing':self.price_book.metadata()}
