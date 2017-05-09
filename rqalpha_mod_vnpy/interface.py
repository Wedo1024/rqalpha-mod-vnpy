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
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """
        QuotationProxy 应在调用该函数后停止发送 TickDict 对象，同时终止子线程。
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



