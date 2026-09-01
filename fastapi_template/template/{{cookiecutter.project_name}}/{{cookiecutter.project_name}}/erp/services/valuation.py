"""Stock valuation — NK port of erpnext/stock/valuation.py (FIFO/LIFO)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import NewType

StockBin = NewType("StockBin", list[float])
QTY = 0
RATE = 1


def _flt(value: float, precision: int = 7) -> float:
    if abs(0.0 - float(value)) < (1.0 / (10**precision)):
        return 0.0
    return float(value)


def round_off_if_near_zero(number: float, precision: int = 7) -> float:
    return _flt(number, precision)


class BinWiseValuation(ABC):
    @abstractmethod
    def add_stock(self, qty: float, rate: float) -> None: ...

    @abstractmethod
    def remove_stock(
        self,
        qty: float,
        outgoing_rate: float = 0.0,
        rate_generator: Callable[[], float] | None = None,
        is_return_purchase_entry: bool = False,
    ) -> list[StockBin]: ...

    @property
    @abstractmethod
    def state(self) -> list[StockBin]: ...

    def get_total_stock_and_value(self) -> tuple[float, float]:
        total_qty = 0.0
        total_value = 0.0
        for qty, rate in self.state:
            total_qty += _flt(qty)
            total_value += _flt(qty) * _flt(rate)
        return round_off_if_near_zero(total_qty), round_off_if_near_zero(total_value)


class FIFOValuation(BinWiseValuation):
    __slots__ = ("queue",)

    def __init__(self, state: list[StockBin] | None = None) -> None:
        self.queue: list[StockBin] = state if state is not None else []

    @property
    def state(self) -> list[StockBin]:
        return self.queue

    def add_stock(self, qty: float, rate: float) -> None:
        if not self.queue:
            self.queue.append([0.0, 0.0])
        if self.queue[-1][RATE] == rate:
            self.queue[-1][QTY] += qty
        elif self.queue[-1][QTY] > 0:
            self.queue.append([qty, rate])
        else:
            merged = self.queue[-1][QTY] + qty
            if merged > 0:
                self.queue[-1] = [merged, rate]
            else:
                self.queue[-1][QTY] = merged

    def remove_stock(
        self,
        qty: float,
        outgoing_rate: float = 0.0,
        rate_generator: Callable[[], float] | None = None,
        is_return_purchase_entry: bool = False,
    ) -> list[StockBin]:
        if rate_generator is None:
            rate_generator = lambda: 0.0
        consumed: list[StockBin] = []
        while qty:
            if not self.queue:
                self.queue.append([0.0, rate_generator()])
            index = 0
            if outgoing_rate > 0 or is_return_purchase_entry:
                for idx, fifo_bin in enumerate(self.queue):
                    if fifo_bin[RATE] == outgoing_rate:
                        index = idx
                        break
            fifo_bin = self.queue[index]
            if qty >= fifo_bin[QTY]:
                qty = round_off_if_near_zero(qty - fifo_bin[QTY])
                consumed.append(list(self.queue.pop(index)))
                if not self.queue and qty:
                    self.queue.append([-qty, outgoing_rate or fifo_bin[RATE]])
                    consumed.append([qty, outgoing_rate or fifo_bin[RATE]])
                    break
            else:
                fifo_bin[QTY] = round_off_if_near_zero(fifo_bin[QTY] - qty)
                consumed.append([qty, fifo_bin[RATE]])
                qty = 0
        return consumed


class LIFOValuation(BinWiseValuation):
    __slots__ = ("stack",)

    def __init__(self, state: list[StockBin] | None = None) -> None:
        self.stack: list[StockBin] = state if state is not None else []

    @property
    def state(self) -> list[StockBin]:
        return self.stack

    def add_stock(self, qty: float, rate: float) -> None:
        if not self.stack:
            self.stack.append([0.0, 0.0])
        if self.stack[-1][RATE] == rate:
            self.stack[-1][QTY] += qty
        elif self.stack[-1][QTY] > 0:
            self.stack.append([qty, rate])
        else:
            merged = self.stack[-1][QTY] + qty
            if merged > 0:
                self.stack[-1] = [merged, rate]
            else:
                self.stack[-1][QTY] = merged

    def remove_stock(
        self,
        qty: float,
        outgoing_rate: float = 0.0,
        rate_generator: Callable[[], float] | None = None,
        is_return_purchase_entry: bool = False,
    ) -> list[StockBin]:
        if rate_generator is None:
            rate_generator = lambda: 0.0
        consumed: list[StockBin] = []
        while qty:
            if not self.stack:
                self.stack.append([0.0, rate_generator()])
            stock_bin = self.stack[-1]
            if qty >= stock_bin[QTY]:
                qty = round_off_if_near_zero(qty - stock_bin[QTY])
                consumed.append(list(self.stack.pop()))
                if not self.stack and qty:
                    self.stack.append([-qty, outgoing_rate or stock_bin[RATE]])
                    consumed.append([qty, outgoing_rate or stock_bin[RATE]])
                    break
            else:
                stock_bin[QTY] = round_off_if_near_zero(stock_bin[QTY] - qty)
                consumed.append([qty, stock_bin[RATE]])
                qty = 0
        return consumed
