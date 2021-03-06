import sys, os
import math
import datetime
import code
import logging
import traceback
import atexit
import trader.AlgoGUI as Alg
import trader.ManagerGUI as Man
from trader.Setup import *
from trader.Util import *
from trader.Algorithm import *

debuglogger = logging.getLogger("debuglogger")
debuglogger.setLevel(logging.DEBUG)
fh = logging.FileHandler('debug.log')
fmt = logging.Formatter('%(levelname)-7s: %(asctime)-s | %(message)s')
fh.setFormatter(fmt)
fh.setLevel(logging.DEBUG)
debuglogger.addHandler(fh)

class Manager:
	def __init__(self):

		# Variables that the user can change
		self.running = False
		self.algo_alloc = {}
		# Private variables
		self.graphing = False
		self.portfolio = portfoliodata()
		# Variables that change automatically
		self.value = self.portfolio["value"]
		self.cash = self.portfolio["cash"]
		self.chartminute = []
		self.chartminutetimes = []
		self.chartday = []
		self.chartdaytimes = []
		self.stocks = {}
		self.updatemin()
		debuglogger.debug('Starting AlgoManager')
		atexit.register(debuglogger.debug, 'Stopping AlgoManager')
		atexit.register(self.stop)


	# Adds an algorithm to the manager.
	# Allocation is the decimal proportion of the total portfolio to use for the algorithm.
	def add(self, algorithm, allocation=1):
		self.algo_alloc[algorithm] = allocation
	# Removes an algorithm from the manager
	def remove(self, algorithm):
		del self.algo_alloc[algorithm]


	# Starts running the algorithms
	# To stop, set self.running = False
	# Always move stocks into algos and call rebalance() before calling start()
	def start(self):
		self.running = True
		tradingthread = threading.Thread(target=self.run)
		tradingthread.start()


	def stop(self):
		self.running = False

	# Redistributes the capital among the algorithms according to the
	# specified allocations in self.algo_alloc.
	# Funds become unbalanced when some algorithms outperform others
	# or algo_alloc is manually edited.
	def rebalance(self):
		total_allocation = 0
		for algo, alloc in self.algo_alloc.items():
			if not algo.running:
				total_allocation += alloc
		if total_allocation > 1:
			logging.warning("You are attempting to allocate more than 100%% of your portfolio")
			return
		newcash = {}
		for algo in self.algo_alloc:
			startingcapital = math.floor(self.value * self.algo_alloc[algo])
			cash = startingcapital - (algo.value - algo.cash)
			if cash < 0:
				logging.warning("You are trying to allocate less than %s already has in stocks. \
								 Either remove those stocks from the algo with assignstocks({\"SPY\":0},algo) \
								 or increase your allocation", algo.__class__.__name__)
				return
			if cash > self.cash and not algo.running:
				logging.warning("You are trying to allocate more cash than you have to %s. \
								Either sell those other stocks, transfer them into the algorithm with \
								assignstocks(stocks,algo), or lower your allocation.", algo.__class__.__name__)
				return
			newcash[algo] = (startingcapital, cash)
		for algo, (startingcapital, cash) in newcash.items():
			algo.startingcapital = startingcapital
			algo.cash = cash
			algo.updatetick()


	# Moves stocks that you already hold into an algorithm
	# It will prevent you from trying to assign more of a stock than you actually own
	# stocks: Can be a list of symbols (moves all shares of each given stock),
	#       a dict of {symbol: shares to have in algo}, 'all' (which allocates everything),
	#       'none' (which removes everything), or a string of the symbol (allocates all shares)
	# algo: The algorithm you are moving the stocks to
	def assignstocks(self, stocks, algo):
		# Assign stocks to the algo
		if stocks == 'all':
			for stock, amount in self.stocks.items():
				algo.stocks[stock] = (amount - self.numstockinalgos(stock, algo))
		elif stocks == 'none':
			algo.stocks = {}
		elif type(stocks) == list:
			for stock in stocks:
				algo.stocks[stock] = (self.stocks[stock] - self.numstockinalgos(stock, algo))
		elif type(stocks) == dict:
			for (stock, amount) in stocks.items():
				algo.stocks[stock] = min(amount, self.stocks[stock]-self.numstockinalgos(stock, algo))
		else:
			algo.stocks[stocks] = (self.stocks[stocks] - self.numstockinalgos(stocks, algo))
		# Update the algo's value
		value = 0
		for stock, amount in algo.stocks.items():
			value += price(stock) * amount
		algo.value = value + algo.cash
	# Helper function for assignstocks.
	# Gets the total number of a given stock in all algos (except given algo, if given)
	def numstockinalgos(self, stock, algo=None):
		numstock = 0
		for algorithm in list(self.algo_alloc.keys()):
			numstock += (algorithm.stocks[stock] if (stock in algorithm.stocks) else 0)
		if algo != None:
			numstock -= (algo.stocks[stock] if (stock in algo.stocks) else 0)
		return numstock


	# Keep algorithm manager running and enter interactive mode
	# Allows you to view and change class attributes from the command line
	def interactive(self,vars={}):
		try:
			code.interact(local={**locals(),**vars})
		except SystemExit:
			pass


	# Opens GUI of all algorithms in the manager
	def gui(self,thread=True):
		desktoptrader = Man.Gui(self)
		if thread:
			guithread = threading.Thread(target=desktoptrader.mainloop)
			guithread.start()
		else:
			desktoptrader.mainloop()


	# Opens the GUI to visualize the Algorithm's performance (also works with Backtests)
	@staticmethod
	def algogui(algo,thread=False):
		desktoptrader = Alg.Gui(algo)
		if thread:
			guithread = threading.Thread(target=desktoptrader.mainloop)
			guithread.start()
		else:
			desktoptrader.mainloop()


	# Graphs portfolio performance
	# Press 'q' to exit
	# timeframe = 'daily', '1min' (plotting resolution)
	def graph(self, timeframe='day'):
		import matplotlib.pyplot as plt
		plt.ion()
		plt.xkcd()
		plt.gcf().canvas.mpl_connect('key_press_event', self.quit_figure)
		self.graphing = True
		while self.graphing:
			if timeframe == '1min':
				plt.plot(self.chartminute, 'b')
			else:
				plt.plot(self.chartday, 'b')
			plt.title(('Portfolio: $%0.2f    Day Change: %0.2f%%' % (self.value, self.portfolio["day change"])))
			plt.pause(0.05)


	# Private Method
	# Graph callback helper
	def quitfigure(self, event):
		import matplotlib.pyplot as plt
		if event.key == 'q':
			plt.close(event.canvas.figure)
			self.graphing = False



	def __str__(self):
		varsdict = self.__dict__.copy()
		del varsdict["chartminutetimes"]
		del varsdict["chartminute"]
		del varsdict["graphing"]
		del varsdict["running"]
		return dict2string(varsdict)


	# Private Method
	# Called every tick
	# Updates the data in the Manager
	# Allows you to track how the portfolio is doing in real time
	def updatetick(self):
		portfolio = portfoliodata()
		self.value = portfolio["value"]
		self.cash = portfolio["cash"]


	# Private Method
	# Called every minute
	# Updates the data in the Manager
	def updatemin(self):
		portfolio = portfoliodata()
		self.value = portfolio["value"]
		self.cash = portfolio["cash"]
		self.chartminute.append(self.value)
		self.chartminutetimes.append(getdatetime())
		for name, amount in positions().items():
			if amount == 0:
				self.stocks.pop(name, None)
			else:
				self.stocks[name] = amount


	# Private Method
	# Called at the start of every day
	def updateday(self):
		self.chartminute = []
		self.chartminutetimes = []
		self.chartday.append(self.value)
		self.chartdaytimes.append(getdatetime())


	# Private Method
	# Updates the data in each algorithm continuously
	# Runs each algorithm at the right time of day
	def run(self):
		lasttime = None
		lastday = None
		# function that returns a boolean for if the given day is a trading day
		tradingday = lambda currentday: datetimeequals(tradingdays(start=currentday,end=currentday+datetime.timedelta(days=1))[0].date(), currentday)
		# boolean trading day flag
		istradingday = tradingday(getdatetime().date())
		# Main Loop
		while self.running:
			time.sleep(15)
			try:
				# Get time and day
				currenttime = getdatetime().time().replace(second=0, microsecond=0)
				currentday = getdatetime().date()
				debuglogger.debug('time: %s, day: %s', currenttime, currentday)
				if currentday != lastday:
					istradingday = tradingday(currentday)
					lastday = currentday
				# If trading is open
				debuglogger.debug('istradingday: %s, newtime: %s, lateenough: %s, earlyenough: %s', istradingday, not datetimeequals(currenttime, lasttime), currenttime >= datetime.time(9,30), currenttime <= datetime.time(16,0))
				if (istradingday) and (not datetimeequals(currenttime, lasttime)) and (currenttime >= datetime.time(9,30)) and (currenttime <= datetime.time(16,0)):
					lasttime = currenttime
					# Update minute
					for algo in self.algo_alloc:
						algo.updatemin()
					self.updatemin()
					# Update day
					if currentday != lastday:
						self.updateday()
						for algo in self.algo_alloc:
							algo.updateday()
						logging.debug('New day. Variables: %s', self)
					# Run algorithms
					for algo in self.algo_alloc:
						currdatetime = datetime.datetime.combine(currentday,currenttime)
						debuglogger.debug('algo %s: nextruntime=%s, currenttime=%s, (running=%s)', algo.__class__.__name__, algo.nextruntime(currdatetime), currdatetime, datetimeequals(algo.nextruntime(currdatetime), currdatetime))
						if datetimeequals(algo.nextruntime(currdatetime), currdatetime):
							algothread = threading.Thread(target=algo.runalgo)
							algothread.start()
							debuglogger.debug('Running algo %s. Variables: %s', algo.__class__.__name__, algo)
			except Exception as err:
				exc_type, exc_obj, exc_tb = sys.exc_info()
				fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
				stacktrace = traceback.format_tb(exc_tb)
				logging.error('%s %s in file %s:\n'.join(stacktrace), exc_type.__name__, err, fname)

