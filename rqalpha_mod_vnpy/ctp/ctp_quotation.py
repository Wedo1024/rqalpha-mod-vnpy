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
from time import sleep
from rqalpha.utils.logger import system_log

from ..interface import AbstractQuotationProxy, TickDict, QuotationDict
from ..data_cache import DataCache
from ..vnpy import MdApi


class CTPTickDict(TickDict):
    def __init__(self, data):
        super(CTPTickDict, self).__init__()

        self.is_valid = False
        self.update_data(data)

    @property
    def quotation_dict(self):
        qd = QuotationDict()
        qd.price = self.last
        qd.limit_up = self.limit_up
        qd.limit_down = self.limit_down
        return qd

    def update_data(self, data):
        self.order_book_id = make_order_book_id(data['InstrumentID'])
        try:
            self.date = int(data['TradingDay'])
            self.time = int((data['UpdateTime'].replace(':', ''))) * 1000 + int(data['UpdateMillisec'])
            self.open = data['OpenPrice']
            self.last = data['LastPrice']
            self.low = data['LowestPrice']
            self.high = data['HighestPrice']
            self.prev_close = data['PreClosePrice']
            self.volume = data['Volume']
            self.total_turnover = data['Turnover']
            self.open_interest = data['OpenInterest']
            self.prev_settlement = data['SettlementPrice']

            self.b1 = data['BidPrice1']
            self.b2 = data['BidPrice2']
            self.b3 = data['BidPrice3']
            self.b4 = data['BidPrice4']
            self.b5 = data['BidPrice5']
            self.b1_v = data['BidVolume1']
            self.b2_v = data['BidVolume2']
            self.b3_v = data['BidVolume3']
            self.b4_v = data['BidVolume4']
            self.b5_v = data['BidVolume5']
            self.a1 = data['AskPrice1']
            self.a2 = data['AskPrice2']
            self.a3 = data['AskPrice3']
            self.a4 = data['AskPrice4']
            self.a5 = data['AskPrice5']
            self.a1_v = data['AskVolume1']
            self.a2_v = data['AskVolume2']
            self.a3_v = data['AskVolume3']
            self.a4_v = data['AskVolume4']
            self.a5_v = data['AskVolume5']

            self.limit_up = data['UpperLimitPrice']
            self.limit_down = data['LowerLimitPrice']
            self.is_valid = True
        except ValueError:
            self.is_valid = False


class CtpMdApi(MdApi):
    def __init__(self, ctp_quotation_proxy, temp_path, user_id, password, broker_id, address):
        super(CtpMdApi, self).__init__()

        self.proxy = ctp_quotation_proxy

        self.req_id = 0

        self.connected = False
        self.logged_in = False

        self.temp_path = temp_path
        self.user_id = user_id
        self.password = password
        self.broker_id = broker_id
        self.address = address

    def onFrontConnected(self):
        """服务器连接"""
        self.connected = True
        self.login()

    def onFrontDisconnected(self, n):
        """服务器断开"""
        self.connected = False
        self.logged_in = False

    def onHeartBeatWarning(self, n):
        """心跳报警"""
        pass

    def onRspError(self, error, n, last):
        """错误回报"""
        self.proxy.on_err(error)

    def onRspUserLogin(self, data, error, n, last):
        """登陆回报"""
        if error['ErrorID'] == 0:
            self.logged_in = True
        else:
            self.proxy.on_err(error)

    def onRspUserLogout(self, data, error, n, last):
        """登出回报"""
        if error['ErrorID'] == 0:
            self.logged_in = False
        else:
            self.proxy.on_err(error)

    def onRspSubMarketData(self, data, error, n, last):
        """订阅合约回报"""
        pass

    def onRspUnSubMarketData(self, data, error, n, last):
        """退订合约回报"""
        pass

    def onRtnDepthMarketData(self, data):
        """行情推送"""
        tick_dict = CTPTickDict(data)
        if tick_dict.is_valid:
            self.proxy.on_tick(tick_dict)

    def onRspSubForQuoteRsp(self, data, error, n, last):
        """订阅期权询价"""
        pass

    def onRspUnSubForQuoteRsp(self, data, error, n, last):
        """退订期权询价"""
        pass

    def onRtnForQuoteRsp(self, data):
        """期权询价推送"""
        pass

    def connect(self):
        """初始化连接"""
        if not self.connected:
            if not os.path.exists(self.temp_path):
                os.makedirs(self.temp_path)
            self.createFtdcMdApi(self.temp_path)
            self.registerFront(self.address)
            self.init()
        else:
            self.login()

    def subscribe(self, order_book_id):
        """订阅合约"""
        ins_dict = DataCache.available_ins.get(order_book_id)
        if ins_dict is None:
            return None
        ctp_instrument_id = ins_dict.ctp_instrument_id
        if instrument_id:
            self.subscribeMarketData(str(ctp_instrument_id))

    def login(self):
        """登录"""
        if not self.logged_in:
            req = {
                'UserID': self.user_id,
                'Password': self.password,
                'BrokerID': self.broker_id,
            }
            self.req_id += 1
            self.reqUserLogin(req, self.req_id)
        return self.req_id

    def stop(self):
        """关闭"""
        self.exit()


class CtpQuotationProxy(AbstractQuotation):
    def __init__(self, gateway, mod_config):
        super(CTPQuotation, self).__init__(gateway, mod_config)
        self.md_api = CtpMdApi(self, mod_config.temp_path, mod_config.CTP.userID, mod_config.CTP.password,
                               mod_config.CTP.brokerID, mod_config.CTP.mdAddress)
        self._subscribed = []
        self._quotation_cache = {}

    def start(self):
        for i in range(5):
            self.md_api.connect()
            sleep(1 * (i+1))
            if self.md_api.logged_in:
                self.on_log('CTP 行情服务器登录成功')
                break
        else:
            raise RuntimeError('CTP 行情服务器连接或登录超时')

        for order_book_id in DataCache.available_ins.keys():
            self.md_api.subscribe(order_book_id)

    def stop(self):
        self.md_api.stop()

    def update_universe(self, universe):
        self._subscribed = universe

    def on_tick(self, tick_dict):
        order_book_id = tick_dict.order_book_id
        self._quotation_cache[order_book_id] = tick_dict.quotation_dict
        if order_book_id in self._subscribed:
            self._on_tick(tick_dict)

    def get_last_quotation(self, order_book_id):
        return self._quotation_cache.get(order_book_id)

    @staticmethod
    def on_log(log):
        system_log.info(log)

    @staticmethod
    def on_err(error):
        system_log.error('CTP 错误，错误代码：%s，错误信息：%s' % (str(error['ErrorID']), error['ErrorMsg'].decode('GBK')))
