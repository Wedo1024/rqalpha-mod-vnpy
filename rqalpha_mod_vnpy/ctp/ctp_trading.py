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
from functools import wraps
import os
import numpy as np
from six import iteritems
from rqalpha.const import ORDER_TYPE, SIDE, POSITION_EFFECT

from .data_dict import DataDict

from ..vnpy import TdApi
from ..utils import make_order_book_id, make_underlying_symbol, is_future, make_trading_dt
from ..interface import AbstractTradingProxy, OrderDict, PositionDict, TradeDict, InstrumentDict


class CtpOrderDict(OrderDict):
    def __init__(self, data, rejected=False):
        super(CtpOrderDict, self).__init__()

        self.is_valid = False
        self.update_dasta(data, rejected)

    def update_dasta(self, data, rejected=False):
        if not data['InstrumentID']:
            return
        self.order_book_id = make_order_book_id(data['InstrumentID'])
        try:
            self.order_id = int(data['OrderRef'])
        except ValueError:
            self.order_id = np.nan

        if 'InsertTime' in data:
            self.calendar_dt = parse(data['InsertTime'])
            self.trading_dt = make_trading_dt(self.calendar_dt)

        self.quantity = data['VolumeTotalOriginal']
        self.side = SIDE_REVERSE.get(data['Direction'], SIDE.BUY)

        if self.exchange_id == 'SHFE':
            if data['CombOffsetFlag'] == defineDict['THOST_FTDC_OF_Open']:
                self.position_effect = POSITION_EFFECT.OPEN
            elif data['CombOffsetFlag'] == defineDict['THOST_FTDC_OF_CloseToday']:
                self.position_effect = POSITION_EFFECT.CLOSE_TODAY
            else:
                self.position_effect = POSITION_EFFECT.CLOSE
        else:
            if data['CombOffsetFlag'] == defineDict['THOST_FTDC_OF_Open']:
                self.position_effect = POSITION_EFFECT.OPEN
            else:
                self.position_effect = POSITION_EFFECT.CLOSE

        if rejected:
            self.status = ORDER_STATUS.REJECTED
        else:
            if 'OrderStatus' in data:
                if data['OrderStatus'] in [defineDict["THOST_FTDC_OST_PartTradedQueueing"], defineDict["THOST_FTDC_OST_NoTradeQueueing"]]:
                    self.status = ORDER_STATUS.ACTIVE
                elif data['OrderStatus'] == defineDict["THOST_FTDC_OST_AllTraded"]:
                    self.status = ORDER_STATUS.FILLED
                elif data['OrderStatus'] == defineDict["THOST_FTDC_OST_Canceled"]:
                    self.status = ORDER_STATUS.CANCELLED
                else:
                    return

        self.style = LimitOrder(data['LimitPrice'])
        self.is_valid = True


class CtpPositionDict(PositionDict):
    def __init__(self, data):
        super(CtpPositionDict, self).__init__()
        self.buy_old_quantity = 0
        self.buy_quantity = 0
        self.buy_today_quantity = 0
        self.buy_transaction_cost = 0.
        self.buy_realized_pnl = 0.

        self.sell_old_quantity = 0
        self.sell_quantity = 0
        self.sell_today_quantity = 0
        self.sell_transaction_cost = 0.
        self.sell_realized_pnl = 0.

        self.prev_settle_price = 0.

        self.buy_open_cost = 0.
        self.sell_open_cost = 0.

        self.update_data(data)

    def update_data(self, data):
        elf.order_book_id = make_order_book_id(data['InstrumentID'])

        if data['PosiDirection'] in [defineDict["THOST_FTDC_PD_Net"], defineDict["THOST_FTDC_PD_Long"]]:
            if data['YdPosition']:
                self.buy_old_quantity = data['YdPosition']
            if data['TodayPosition']:
                self.buy_today_quantity = data['TodayPosition']
            self.buy_quantity += data['Position']
            self.buy_transaction_cost += data['Commission']
            self.buy_realized_pnl += data['CloseProfit']
            self.buy_open_cost += data['OpenCost']

        elif data['PosiDirection'] == defineDict["THOST_FTDC_PD_Short"]:
            if data['YdPosition']:
                self.sell_old_quantity = data['YdPosition']
            if data['TodayPosition']:
                self.sell_today_quantity = data['TodayPosition']
            self.sell_quantity += data['Position']
            self.sell_transaction_cost += data['Commission']
            self.sell_realized_pnl += data['CloseProfit']
            self.sell_open_cost += data['OpenCost']

        if data['PreSettlementPrice']:
            self.prev_settle_price = data['PreSettlementPrice']


class CtpTradeDict(TradeDict):
    def __init__(self, data):
        super(CtpTradeDict, self).__init__()
        self.update_data(data)

    def update_data(self, data):
        self.order_id = int(data['OrderRef'])
        self.trade_id = data['TradeID']
        self.calendar_dt = parse(data['TradeTime'])
        self.trading_dt = make_trading_dt(self.calendar_dt)
        self.order_book_id = make_order_book_id(data['InstrumentID'])

        self.side = SIDE_REVERSE.get(data['Direction'], SIDE.BUY)

        if data['ExchangeID'] == 'SHFE':
            if data['OffsetFlag'] == defineDict['THOST_FTDC_OF_Open']:
                self.position_effect = POSITION_EFFECT.OPEN
            elif data['OffsetFlag'] == defineDict['THOST_FTDC_OF_CloseToday']:
                self.position_effect = POSITION_EFFECT.CLOSE_TODAY
            else:
                self.position_effect = POSITION_EFFECT.CLOSE
        else:
            if data['OffsetFlag'] == defineDict['THOST_FTDC_OF_Open']:
                self.position_effect = POSITION_EFFECT.OPEN
            else:
                self.position_effect = POSITION_EFFECT.CLOSE

        self.amount = data['Volume']
        self.price = data['Price']
        self.style = LimitOrder(self.price)


class CtpInstrumentDict(InstrumentDict):
    def __init__(self, data):
        super(CtpInstrumentDict, self).__init__()
        self.ctp_instrument_id = None
        self.is_valid = False
        self.commission_valid = False
        self.update_data(data)

    def update_data(self, data):
        if is_future(data['InstrumentID']):
            self.order_book_id = make_order_book_id(data['InstrumentID'])
            self.underlying_symbol = make_underlying_symbol(data['InstrumentID'])
            self.exchange_id = data['ExchangeID']
            self.contract_multiplier = data['VolumeMultiple']
            self.long_margin_ratio = data['LongMarginRatio']
            self.short_margin_ratio = data['ShortMarginRatio']
            self.margin_type = MARGIN_TYPE.BY_MONEY
            self.ctp_instrument_id = data['InstrumentID']
            self.is_valid = True

    def update_commission(self, commission_dict):
        self.close_commission_ratio = commission_dict.close_ratio
        self.open_commission_ratio = commission_dict.open_ratio
        self.close_today_commission_ratio = commission.close_today_ratio
        self.commission_valid = True


class CtpCommissionDict(DataDict):
    def __init__(self, data):
        super(CommissionDict, self).__init__()
        self.underlying_symbol = None
        self.close_ratio = None
        self.open_ratio = None
        self.close_today_ratio = None
        self.commission_type = None

        self.is_valid = False
        self.update_data(data)

    def update_data(self, data):
        self.underlying_symbol = make_underlying_symbol(data['InstrumentID'])
        if data['OpenRatioByMoney'] == 0 and data['CloseRatioByMoney']:
            self.open_ratio = data['OpenRatioByVolume']
            self.close_ratio = data['CloseRatioByVolume']
            self.close_today_ratio = data['CloseTodayRatioByVolume']
            if data['OpenRatioByVolume'] != 0 or data['CloseRatioByVolume'] != 0:
                self.commission_type = COMMISSION_TYPE.BY_VOLUME
            else:
                self.commission_type = None
        else:
            self.open_ratio = data['OpenRatioByMoney']
            self.close_ratio = data['CloseRatioByMoney']
            self.close_today_ratio = data['CloseTodayRatioByMoney']
            if data['OpenRatioByVolume'] == 0 and data['CloseRatioByVolume'] == 0:
                self.commission_type = COMMISSION_TYPE.BY_MONEY
            else:
                self.commission_type = None
        self.is_valid = True


def query_in_sync(func):
    @wraps(func)
    def wrapper(api, data, error, n, last):
        api.req_id = max(api.req_id, n)
        result = func(api, data, last)
        if last:
            api.proxy.query_returns[n] = result
    return wrapper


class CtpTdApi(TdApi):
    def __init__(self, trading_proxy, temp_path, user_id, password, broker_id, address, auth_code, user_production_info):
        super(CtpTdApi, self).__init__()

        self.proxy = trading_proxy
        self.temp_path = temp_path
        self.req_id = 0

        self.connected = False
        self.logged_in = False
        self.authenticated = False

        self.user_id = user_id
        self.password = password
        self.broker_id = broker_id
        self.address = address
        self.auth_code = auth_code
        self.user_production_info = user_production_info

        self.front_id = 0
        self.session_id = 0

        self.require_authentication = False

        self.pos_cache = {}
        self.ins_cache = {}
        self.order_cache = {}

    def onFrontConnected(self):
        """服务器连接"""
        self.connected = True
        if self.require_authentication:
            self.authenticate()
        else:
            self.login()

    def onFrontDisconnected(self, n):
        """服务器断开"""
        self.connected = False
        self.logged_in = False

    def onHeartBeatWarning(self, n):
        """心跳报警"""
        pass

    def onRspAuthenticate(self, data, error, n, last):
        """验证客户端回报"""
        if error['ErrorID'] == 0:
            self.authenticated = True
            self.login()
        else:
            self.proxy.on_err(error)

    def onRspUserLogin(self, data, error, n, last):
        """登陆回报"""
        if error['ErrorID'] == 0:
            self.front_id = str(data['FrontID'])
            self.session_id = str(data['SessionID'])
            self.logged_in = True
            self.qrySettlementInfoConfirm()
        else:
            self.proxy.on_err(error)

    def onRspUserLogout(self, data, error, n, last):
        """登出回报"""
        if error['ErrorID'] == 0:
            self.logged_in = False
        else:
            self.proxy.on_err(error)

    def onRspUserPasswordUpdate(self, data, error, n, last):
        """"""
        pass

    def onRspTradingAccountPasswordUpdate(self, data, error, n, last):
        """"""
        pass

    def onRspOrderInsert(self, data, error, n, last):
        """发单错误（柜台）"""
        order_dict = OrderDict(data, rejected=True)
        if order_dict.is_valid:
            self.proxy.on_order(order_dict)

    def onRspParkedOrderInsert(self, data, error, n, last):
        """"""
        pass

    def onRspParkedOrderAction(self, data, error, n, last):
        """"""
        pass

    def onRspOrderAction(self, data, error, n, last):
        """撤单错误（柜台）"""
        self.proxy.on_err(error)

    def onRspQueryMaxOrderVolume(self, data, error, n, last):
        """"""
        pass

    def onRspSettlementInfoConfirm(self, data, error, n, last):
        """确认结算信息回报"""
        pass

    def onRspRemoveParkedOrder(self, data, error, n, last):
        """"""
        pass

    def onRspRemoveParkedOrderAction(self, data, error, n, last):
        """"""
        pass

    def onRspExecOrderInsert(self, data, error, n, last):
        """"""
        pass

    def onRspExecOrderAction(self, data, error, n, last):
        """"""
        pass

    def onRspForQuoteInsert(self, data, error, n, last):
        """"""
        pass

    def onRspQuoteInsert(self, data, error, n, last):
        """"""
        pass

    def onRspQuoteAction(self, data, error, n, last):
        """"""
        pass

    def onRspLockInsert(self, data, error, n, last):
        """"""
        pass

    def onRspCombActionInsert(self, data, error, n, last):
        """"""
        pass

    @query_in_sync
    def onRspQryOrder(self, data, last):
        """报单回报"""
        order_dict = CtpOrderDict(data)
        if order_dict.is_valid:
            self.order_cache[order_dict.order_id] = order_dict
        if last:
            return self.order_cache

    def onRspQryTrade(self, data, error, n, last):
        """"""
        pass

    @query_in_sync
    def onRspQryInvestorPosition(self, data, last):
        """持仓查询回报"""

        if data['InstrumentID']:
            order_book_id = make_order_book_id(data['InstrumentID'])
            if order_book_id not in self.pos_cache:
                self.pos_cache[order_book_id] = CtpPositionDict(data)
            else:
                self.pos_cache[order_book_id].update_data(data)

        if last:
            return self.pos_cache

    @query_in_sync
    def onRspQryTradingAccount(self, data, last):
        """资金账户查询回报"""
        return AccountDict(data)

    def onRspQryInvestor(self, data, error, n, last):
        """"""
        pass

    def onRspQryTradingCode(self, data, error, n, last):
        """"""
        pass

    def onRspQryInstrumentMarginRate(self, data, error, n, last):
        """"""
        pass

    @query_in_sync
    def onRspQryInstrumentCommissionRate(self, data, last):
        """请求查询合约手续费率响应"""
        return CtpCommissionDict(data)

    def onRspQryExchange(self, data, error, n, last):
        """"""
        pass

    def onRspQryProduct(self, data, error, n, last):
        """"""
        pass

    @query_in_sync
    def onRspQryInstrument(self, data, last):
        """合约查询回报"""
        ins_dict = CtpInstrumentDict(data)
        if ins_dict.is_valid:
            self.ins_cache[ins_dict.order_book_id] = ins_dict
        if last:
            return self.ins_cache

    def onRspQryDepthMarketData(self, data, error, n, last):
        """"""
        pass

    def onRspQrySettlementInfo(self, data, error, n, last):
        """"""
        pass

    def onRspQryTransferBank(self, data, error, n, last):
        """"""
        pass

    def onRspQryInvestorPositionDetail(self, data, error, n, last):
        """"""
        pass

    def onRspQryNotice(self, data, error, n, last):
        """"""
        pass

    def onRspQrySettlementInfoConfirm(self, data, error, n, last):
        """"""
        pass

    def onRspQryInvestorPositionCombineDetail(self, data, error, n, last):
        """"""
        pass

    def onRspQryCFMMCTradingAccountKey(self, data, error, n, last):
        """"""
        pass

    def onRspQryEWarrantOffset(self, data, error, n, last):
        """"""
        pass

    def onRspQryInvestorProductGroupMargin(self, data, error, n, last):
        """"""
        pass

    def onRspQryExchangeMarginRate(self, data, error, n, last):
        """"""
        pass

    def onRspQryExchangeMarginRateAdjust(self, data, error, n, last):
        """"""
        pass

    def onRspQryExchangeRate(self, data, error, n, last):
        """"""
        pass

    def onRspQrySecAgentACIDMap(self, data, error, n, last):
        """"""
        pass

    def onRspQryProductExchRate(self, data, error, n, last):
        """"""
        pass

    def onRspQryProductGroup(self, data, error, n, last):
        """"""
        pass

    def onRspQryOptionInstrTradeCost(self, data, error, n, last):
        """"""
        pass

    def onRspQryOptionInstrCommRate(self, data, error, n, last):
        """"""
        pass

    def onRspQryExecOrder(self, data, error, n, last):
        """"""
        pass

    def onRspQryForQuote(self, data, error, n, last):
        """"""
        pass

    def onRspQryQuote(self, data, error, n, last):
        """"""
        pass

    def onRspQryLock(self, data, error, n, last):
        """"""
        pass

    def onRspQryLockPosition(self, data, error, n, last):
        """"""
        pass

    def onRspQryInvestorLevel(self, data, error, n, last):
        """"""
        pass

    def onRspQryExecFreeze(self, data, error, n, last):
        """"""
        pass

    def onRspQryCombInstrumentGuard(self, data, error, n, last):
        """"""
        pass

    def onRspQryCombAction(self, data, error, n, last):
        """"""
        pass

    def onRspQryTransferSerial(self, data, error, n, last):
        """"""
        pass

    def onRspQryAccountregister(self, data, error, n, last):
        """"""
        pass

    def onRspError(self, error, n, last):
        """错误回报"""
        self.proxy.on_err(error)

    def onRtnOrder(self, data):
        """报单回报"""
        order_dict = OrderDict(data)
        if order_dict.is_valid:
            self.proxy.on_order(order_dict)

    def onRtnTrade(self, data):
        """成交回报"""
        trade_dict = CtpTradeDict(data)
        self.proxy.on_trade(trade_dict)

    def onErrRtnOrderInsert(self, data, error):
        """发单错误回报（交易所）"""

        self.proxy.on_err(error)
        order_dict = CtpOrderDict(data, rejected=True)
        if order_dict.is_valid:
            self.proxy.on_order(order_dict)

    def onErrRtnOrderAction(self, data, error):
        """撤单错误回报（交易所）"""
        self.proxy.on_err(error)

    def onRtnInstrumentStatus(self, data):
        """"""
        pass

    def onRtnTradingNotice(self, data):
        """"""
        pass

    def onRtnErrorConditionalOrder(self, data):
        """"""
        pass

    def onRtnExecOrder(self, data):
        """"""
        pass

    def onErrRtnExecOrderInsert(self, data, error):
        """"""
        pass

    def onErrRtnExecOrderAction(self, data, error):
        """"""
        pass

    def onErrRtnForQuoteInsert(self, data, error):
        """"""
        pass

    def onRtnQuote(self, data):
        """"""
        pass

    def onErrRtnQuoteInsert(self, data, error):
        """"""
        pass

    def onErrRtnQuoteAction(self, data, error):
        """"""
        pass

    def onRtnForQuoteRsp(self, data):
        """"""
        pass

    def onRtnCFMMCTradingAccountToken(self, data):
        """"""
        pass

    def onRtnLock(self, data):
        """"""
        pass

    def onErrRtnLockInsert(self, data, error):
        """"""
        pass

    def onRtnCombAction(self, data):
        """"""
        pass

    def onErrRtnCombActionInsert(self, data, error):
        """"""
        pass

    def onRspQryContractBank(self, data, error, n, last):
        """"""
        pass

    def onRspQryParkedOrder(self, data, error, n, last):
        """"""
        pass

    def onRspQryParkedOrderAction(self, data, error, n, last):
        """"""
        pass

    def onRspQryTradingNotice(self, data, error, n, last):
        """"""
        pass

    def onRspQryBrokerTradingParams(self, data, error, n, last):
        """"""
        pass

    def onRspQryBrokerTradingAlgos(self, data, error, n, last):
        """"""
        pass

    def onRspQueryCFMMCTradingAccountToken(self, data, error, n, last):
        """"""
        pass

    def onRtnFromBankToFutureByBank(self, data):
        """"""
        pass

    def onRtnFromFutureToBankByBank(self, data):
        """"""
        pass

    def onRtnRepealFromBankToFutureByBank(self, data):
        """"""
        pass

    def onRtnRepealFromFutureToBankByBank(self, data):
        """"""
        pass

    def onRtnFromBankToFutureByFuture(self, data):
        """"""
        pass

    def onRtnFromFutureToBankByFuture(self, data):
        """"""
        pass

    def onRtnRepealFromBankToFutureByFutureManual(self, data):
        """"""
        pass

    def onRtnRepealFromFutureToBankByFutureManual(self, data):
        """"""
        pass

    def onRtnQueryBankBalanceByFuture(self, data):
        """"""
        pass

    def onErrRtnBankToFutureByFuture(self, data, error):
        """"""
        pass

    def onErrRtnFutureToBankByFuture(self, data, error):
        """"""
        pass

    def onErrRtnRepealBankToFutureByFutureManual(self, data, error):
        """"""
        pass

    def onErrRtnRepealFutureToBankByFutureManual(self, data, error):
        """"""
        pass

    def onErrRtnQueryBankBalanceByFuture(self, data, error):
        """"""
        pass

    def onRtnRepealFromBankToFutureByFuture(self, data):
        """"""
        pass

    def onRtnRepealFromFutureToBankByFuture(self, data):
        """"""
        pass

    def onRspFromBankToFutureByFuture(self, data, error, n, last):
        """"""
        pass

    def onRspFromFutureToBankByFuture(self, data, error, n, last):
        """"""
        pass

    def onRspQueryBankAccountMoneyByFuture(self, data, error, n, last):
        """"""
        pass

    def onRtnOpenAccountByBank(self, data):
        """"""
        pass

    def onRtnCancelAccountByBank(self, data):
        """"""
        pass

    def onRtnChangeAccountByBank(self, data):
        """"""
        pass

    def connect(self):
        """初始化连接"""
        if not self.connected:
            if not os.path.exists(self.temp_path):
                os.makedirs(self.temp_path)
            self.createFtdcTraderApi(self.temp_path)
            self.subscribePrivateTopic(0)
            self.subscribePublicTopic(0)
            self.registerFront(self.address)
            self.init()
        else:
            if self.require_authentication:
                self.authenticate()
            else:
                self.login()

    def login(self):
        """连接服务器"""
        if not self.logged_in:
            req = {
                'UserID': self.user_id,
                'Password': self.password,
                'BrokerID': self.broker_id,
            }
            self.req_id += 1
            self.reqUserLogin(req, self.req_id)
        return self.req_id

    def authenticate(self):
        """申请验证"""
        if self.authenticated:
            req = {
                'UserID': self.user_id,
                'BrokerID': self.broker_id,
                'AuthCode': self.auth_code,
                'UserProductInfo': self.user_production_info,
            }
            self.req_id += 1
            self.reqAuthenticate(req, self.req_id)
        else:
            self.login()
        return self.req_id

    def qrySettlementInfoConfirm(self):
        req = {
            'BrokerID': self.broker_id,
            'InvestorID': self.user_id,
        }
        self.req_id += 1
        self.reqSettlementInfoConfirm(req, self.req_id)
        return self.req_id

    def qryInstrument(self):
        self.ins_cache = {}
        self.req_id += 1
        self.reqQryInstrument({}, self.req_id)
        return self.req_id

    def qryCommission(self, order_book_id):
        self.req_id += 1
        ins_dict = DataCache.available_ins.get(order_book_id)
        if ins_dict is None:
            return None
        req = {
            'InstrumentID': ins_dict.instrument_id,
            'InvestorID': self.user_id,
            'BrokerID': self.broker_id,
            'ExchangeID': ins_dict.exchange_id,
        }
        self.reqQryInstrumentCommissionRate(req, self.req_id)
        return self.req_id

    def qryAccount(self):
        """查询账户"""
        self.req_id += 1
        self.reqQryTradingAccount({}, self.req_id)
        return self.req_id

    def qryPosition(self):
        """查询持仓"""
        self.pos_cache = {}
        self.req_id += 1
        req = {
            'BrokerID': self.broker_id,
            'InvestorID': self.user_id,
        }
        self.reqQryInvestorPosition(req, self.req_id)
        return self.req_id

    def qryOrder(self):
        """订单查询"""
        self.order_cache = {}
        self.req_id += 1
        req = {
            'BrokerID': self.broker_id,
            'InvestorID': self.user_id,
        }
        self.reqQryOrder(req, self.req_id)
        return self.req_id

    def sendOrder(self, order):
        """发单"""

        ins_dict = DataCache.available_ins.get(order_book_id)
        if ins_dict is None:
            return None

        req = {
            'InstrumentID': ins_dict.instrument_id,
            'LimitPrice': order.price,
            'VolumeTotalOriginal': order.quantity,
            'OrderPriceType': ORDER_TYPE_MAPPING.get(order.type, ''),
            'Direction': SIDE_MAPPING.get(order.side, ''),
            'CombOffsetFlag': POSITION_EFFECT_MAPPING.get(order.position_effect, ''),

            'OrderRef': str(order.order_id),
            'InvestorID': self.user_id,
            'UserID': self.user_id,
            'BrokerID': self.broker_id,

            'CombHedgeFlag': defineDict['THOST_FTDC_HF_Speculation'],  # 投机单
            'ContingentCondition': defineDict['THOST_FTDC_CC_Immediately'],  # 立即发单
            'ForceCloseReason': defineDict['THOST_FTDC_FCC_NotForceClose'],  # 非强平
            'IsAutoSuspend': 0,  # 非自动挂起
            'TimeCondition': defineDict['THOST_FTDC_TC_GFD'],  # 今日有效
            'VolumeCondition': defineDict['THOST_FTDC_VC_AV'],  # 任意成交量
            'MinVolume': 1,  # 最小成交量为1
        }

        self.req_id += 1
        self.reqOrderInsert(req, self.req_id)
        return self.req_id

    def cancelOrder(self, order):
        """撤单"""
        ins_dict = DataCache.available_ins.get(order_book_id)
        if ins_dict is None:
            return None

        self.req_id += 1
        req = {
            'InstrumentID': ins_dict.instrument_id,
            'ExchangeID': ins_dict.exchange_id,
            'OrderRef': str(order.order_id),
            'FrontID': int(self.front_id),
            'SessionID': int(self.session_id),

            'ActionFlag': defineDict['THOST_FTDC_AF_Delete'],
            'BrokerID': self.broker_id,
            'InvestorID': self.user_id,
        }

        self.reqOrderAction(req, self.req_id)
        return self.req_id

    def stop(self):
        """关闭"""
        self.exit()


class CTPTradingProxy(AbstractTradingProxy):
    def __init__(self, gateway, mod_config):
        super(CTPTradingProxy, self).__init__(gateway, mod_config)
        self.td_api = CtpTdApi(self, mod_config.temp_path, mod_config.CTP.userID, mod_config.CTP.password,
                               mod_config.CTP.brokerID, mod_config.CTP.tdAddress, None, None)

        self.query_returns = {}

        self.available_ins_cache = None

    def start(self):
        for i in range(5):
            self.td_api.connect()
            sleep(1 * (i + 1))
            if self.td_api.logged_in:
                self.on_log('CTP 交易服务器登录成功')
                break
        else:
            raise RuntimeError('CTP 交易服务器连接或登录超时')

        self.query_returns.clear()
        self.available_ins_cache = None
        self.get_available_instrument()

    def stop(self):
        self.td_api.stop()

    def get_available_instrument(self, order_book_id=None):
        if self.available_ins_cache is None:
            for i in range(5):
                req_id = self.td_api.qryInstrument()
                sleep(1 * (i + 1))
                if req_id in self.query_returns:
                    self.available_ins_cache = self.query_returns[req_id].copy()
                    self.on_debug('%d 条合约数据返回。' % len(ins_cache))
                    break
            else:
                raise RuntimeError('请求合约数据超时')

            for order_book_id, ins_dict in iteritems(self.available_ins_cache):
                if ins_dict.commission_valid:
                    continue
                for i in range(5):
                    req_id = self.td_api.qryCommission(ins_dict.order_book_id)
                    sleep(1 * (i + 1))
                    if req_id in self.query_returns:
                        commission_dict = self.query_returns[req_id].copy()
                        for ins_dict in self.available_ins_cache.values():
                            ins_dict.update_commission(commission_dict)

        if order_book_id is None:
            return self.available_ins_cache
        else:
            return self.available_ins_cache.get(order_book_id)

    @staticmethod
    def on_err(error):
        system_log.error('CTP 错误，错误代码：%s，错误信息：%s' % (str(error['ErrorID']), error['ErrorMsg'].decode('GBK')))

    @staticmethod
    def on_log(log):
        system_log.info(log)


