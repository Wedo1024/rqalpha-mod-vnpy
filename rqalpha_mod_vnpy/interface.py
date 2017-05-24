# -*- coding: utf-8 -*-
#
# Copyright 2017 Ricequant, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import abc
from .utils import DataDict


class TickDict(DataDict):
    def __init__(self):
        super(TickDict, self).__init__()
        self.order_book_id = None
        self.date = None
        self.time = None
        self.open = None
        self.last = None
        self.low = None
        self.high = None
        self.prev_close = None
        self.volume = None
        self.total_turnover = None
        self.open_interest = None
        self.prev_settlement = None

        self.b1 = None
        self.b2 = None
        self.b3 = None
        self.b4 = None
        self.b5 = None

        self.b1_v = None
        self.b2_v = None
        self.b3_v = None
        self.b4_v = None
        self.b5_v = None

        self.a1 = None
        self.a2 = None
        self.a3 = None
        self.a4 = None
        self.a5 = None

        self.a1_v = None
        self.a2_v = None
        self.a3_v = None
        self.a4_v = None
        self.a5_v = None

        self.limit_down = None
        self.limit_up = None


class QuotationDict(DataDict):
    def __init__(self):
        super(QuotationDict, self).__init__()
        self.price = None
        self.limit_up = None
        self.limit_down = None


class OrderDict(DataDict):
    def __init__(self):
        super(OrderDict, self).__init__()
        self.order_id = None
        self.order_book_id = None
        self.calendar_dt = None
        self.trading_dt = None
        self.quantity = None
        self.side = None
        self.style = None
        self.position_effect = None
        self.status = None


class PositionDict(DataDict):
    def __init__(self):
        super(PositionDict, self).__init__()
        self.order_book_id = None

        self.buy_old_quantity = None
        self.buy_quantity = None
        self.buy_today_quantity = None
        self.buy_transaction_cost = None
        self.buy_realized_pnl = None
        self.buy_open_cost = None

        self.sell_old_quantity = None
        self.sell_quantity = None
        self.sell_today_quantity = None
        self.sell_transaction_cost = None
        self.sell_realized_pnl = None
        self.sell_open_cost = None

        self.prev_settle_price = None


class TradeDict(DataDict):
    def __init__(self):
        super(TradeDict, self).__init__()
        self.order_id = None
        self.trade_id = None
        self.calendar_dt = None
        self.trading_dt = None
        self.order_book_id = None
        self.side = None
        self.position_effect = None
        self.amount = None
        self.style = None
        self.price = None


class InstrumentDict(DataDict):
    def __init__(self):
        super(InstrumentDict, self).__init__()
        self.order_book_id = None
        self.underlying_symbol = None
        self.exchange_id = None
        self.contract_multiplier = None

        self.margin_type = None
        self.long_margin_ratio = None
        self.short_margin_ratio = None

        self.close_commission_ratio = None
        self.open_commission_ratio = None
        self.close_today_commission_ratio = None
        self.commission_type = None


class AbstractQuotationProxy(object):
    """
    实时行情类，该类用于获取实时行情数据并将之推送到 gateway，除此之外，该类还应可以获取到所有合约的最新价格。
    """

    def __init__(self, gateway, mod_config):
        self.gateway = gateway
        self.mod_config = mod_config

    @abc.abstractmethod
    def start(self):
        """
        QuotationProxy 应在调用该函数后开始发送 TickDict 对象，也应在调用该函数后可以取到 last_quotation。
        该函数会在每个交易日盘前被调用。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """
        QuotationProxy 应在调用该函数后停止发送 TickDict 对象，同时终止子线程。
        该函数会在每个交易日盘后被调用。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def update_universe(self, universe):
        """
        通过调用该函数更新合约订阅池，QuotationProxy 应仅发送订阅了的合约的 TickDict 对象。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_last_quotation(self, order_book_id):
        """
        获取最新行情数据，包括价格和涨跌停价，返回字典
        :return: QuotationDict 对象
        """
        raise NotImplementedError

    def _on_tick(self, tick_dict):
        """
        QuotationProxy 应调用该函数发出 TickDict 对象
        """
        self.gateway.on_tick(tick_dict)


class AbstractTradingProxy(object):
    def __init__(self, gateway, mod_config):
        self.gateway = gateway
        self.mod_config = mod_config

    @abc.abstractmethod
    def start(self):
        """
        TradingProxy 的各项功能应在该函数被调用后起作用
        该函数会在每个交易日盘前被调用。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """
        子线程应在该函数后终止。
        该函数会在每个交易日盘后被调用。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_available_instrument(self, order_book_id=None):
        """
        返回指定合约的 InsDcit 对象，若 order_book_id 为 None，则返回所有合约的对象字典。
        :return: ins_dict or dict of ins_dict
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_portfolio(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_earlier_orders(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_earlier_trades(self):
        raise NotImplementedError

    @abc.abstractmethod
    def submit_order(self, order):
        raise NotImplementedError

    @abc.abstractmethod
    def cancel_order(self, order):
        raise NotImplementedError

    def _on_order(self, order_dict):
        self.gateway.on_order(order_dict)

    def _on_trade(self, trade_dict):
        self.gateway.on_trade(trade_dict)