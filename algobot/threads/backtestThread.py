import time
import traceback

from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot
from backtest import Backtester
from enums import BACKTEST


class BacktestSignals(QObject):
    finished = pyqtSignal(str)
    activity = pyqtSignal(dict)
    started = pyqtSignal(dict)
    error = pyqtSignal(int, str)


class BacktestThread(QRunnable):
    def __init__(self, gui):
        super(BacktestThread, self).__init__()
        self.gui = gui
        self.signals = BacktestSignals()

    def get_configuration_dictionary(self):
        backtester = self.gui.backtester
        return {
            'startingBalance': f'${backtester.startingBalance}',
            'interval': backtester.interval,
            'marginEnabled': f'{backtester.marginEnabled}',
            'stopLossPercentage': f'{backtester.lossPercentageDecimal * 100}%',
            'stopLossStrategy': f'{"Trailing Loss" if backtester.lossStrategy == 2 else "Stop Loss"}',
            'startPeriod': f'{backtester.data[backtester.startDateIndex]["date_utc"].strftime("%m/%d/%Y, %H:%M:%S")}',
            'endPeriod': f'{backtester.data[backtester.endDateIndex]["date_utc"].strftime("%m/%d/%Y, %H:%M:%S")}',
        }

    def get_activity_dictionary(self, period, index, length):
        backtester = self.gui.backtester
        profit = backtester.get_net() - backtester.startingBalance
        if profit < 0:
            profitPercentage = round(100 - backtester.get_net() / backtester.startingBalance * 100, 2)
        else:
            profitPercentage = round(backtester.get_net() / backtester.startingBalance * 100, 2)

        return {
            'net': backtester.get_net(),
            'netString': f'${round(backtester.get_net(), 2)}',
            'balance': f'${round(backtester.balance, 2)}',
            'commissionsPaid': f'${round(backtester.commissionsPaid, 2)}',
            'tradesMade': str(len(backtester.trades)),
            'profit': f'${abs(round(profit, 2))}',
            'profitPercentage': f'{profitPercentage}%',
            'currentPeriod': period['date_utc'].strftime("%m/%d/%Y, %H:%M:%S"),
            'utc': period['date_utc'].timestamp(),
            'percentage': int(index / length * 100)
        }

    def backtest(self):
        backtester = self.gui.backtester
        backtester.movingAverageTestStartTime = time.time()
        seenData = backtester.data[:backtester.minPeriod][::-1]  # Start from minimum previous period data.
        backtestPeriod = backtester.data[backtester.startDateIndex:backtester.endDateIndex]
        divisor = len(backtestPeriod) // 100
        testLength = len(backtestPeriod)
        if len(backtestPeriod) % 100 != 0:
            divisor += 1

        for index, period in enumerate(backtestPeriod):
            seenData.insert(0, period)
            backtester.currentPeriod = period
            backtester.currentPrice = period['open']
            backtester.main_logic()
            backtester.check_trend(seenData)
            division = index % divisor

            if division == 0:
                self.signals.activity.emit(self.get_activity_dictionary(period=period, index=index, length=testLength))

        if backtester.inShortPosition:
            backtester.exit_short('Exited short because of end of backtest.')
        elif backtester.inLongPosition:
            backtester.exit_long('Exiting long because of end of backtest.')

        self.signals.activity.emit(self.get_activity_dictionary(period=backtestPeriod[-1],
                                                                index=testLength,
                                                                length=testLength))
        backtester.movingAverageTestEndTime = time.time()

    def setup_bot(self):
        gui = self.gui
        startingBalance = gui.configuration.backtestStartingBalanceSpinBox.value()
        data = gui.configuration.data
        marginEnabled = gui.configuration.backtestMarginTradingCheckBox.isChecked()
        lossStrategy, lossPercentageDecimal = gui.get_loss_settings(BACKTEST)
        options = gui.get_trading_options(BACKTEST)
        startDate, endDate = gui.configuration.get_calendar_dates()
        if startDate == endDate:  # This means run everything by default.
            startDate = None
            endDate = None
        gui.backtester = Backtester(startingBalance=startingBalance,
                                    data=data,
                                    lossStrategy=lossStrategy,
                                    lossPercentage=lossPercentageDecimal * 100,
                                    options=options,
                                    marginEnabled=marginEnabled,
                                    startDate=startDate,
                                    endDate=endDate)
        self.signals.started.emit(self.get_configuration_dictionary())

    @pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """
        # Retrieve args/kwargs here; and fire processing using them
        try:
            self.setup_bot()
            self.backtest()
            path = self.gui.backtester.write_results()
            self.signals.finished.emit(path)
        except Exception as e:
            print(f'Error: {e}')
            traceback.print_exc()
            self.signals.error.emit(BACKTEST, str(e))
