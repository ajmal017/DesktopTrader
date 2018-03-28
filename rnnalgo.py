import os, sys
sys.path.append(os.path.dirname(os.path.realpath("")))
from AlgoManager import *
from keras.models import Sequential
from keras.layers import *
from keras.callbacks import *
from keras.regularizers import l1
import keras.backend as K
import tensorflow as tf
import matplotlib.pyplot as plt

class RNN(Algorithm):

	def initialize(self):
		self.securities = ['SPY','MSFT','CSCO','NFLX','DIS']
		self.sec = 'SPY'
		self.benchmark = self.sec
		self.lookback = 3
		self.weights_path = 'rnn_weights.h5'
		# original: LSTM32, Dense128, Dense1
		self.model = Sequential()
		self.model.add(LSTM(32,input_shape=(self.lookback,4),return_sequences=False,dropout=0.2,recurrent_dropout=0.2,kernel_regularizer=l1(0.001),recurrent_regularizer=l1(0.001)))
		self.model.add(Dropout(0.2))
		self.model.add(Dense(128,kernel_regularizer=l1(0.001),activation='relu'))
		#self.model.add(LSTM(32,dropout=0.2,recurrent_dropout=0.2,kernel_regularizer=l1(0.001),recurrent_regularizer=l1(0.001)))
		self.model.add(Dropout(0.2))
		self.model.add(Dense(1,kernel_regularizer=l1(0.001)))
		try:
			self.model.load_weights(self.weights_path)
		except OSError as err:
			print(err)
		self.model.compile(loss='mean_squared_error',optimizer='adam',metrics=[accuracy])
		self.graph = tf.get_default_graph()
		# percent change * 100
		# (bollinger upper - bollinger lower) / bollinger middle
		# macd hist
		# d/dt (14-day rsi) / 100
		# ((2-day rsi) - 50) / 100


	def run(self):
		signals = []
		for security in self.securities:
			signals.append(self.indicator(security))
		maxsig = max(signals)
		maxsigstock = self.securities[signals.index(maxsig)]
		if maxsig > 0.2:
			if maxsigstock not in self.stocks:
				self.sellall(verbose=True)
			self.orderpercent(maxsigstock,1,verbose=True)
		elif maxsig < 0.2:
			self.sellall(verbose=True)


	def indicator(self,stock,length=1,skip=-1):
		dataX, _ = self.getdata(stock,length,skip)
		with self.graph.as_default():
			return self.model.predict(dataX)


	def train(self):
		callbacks = []
		callbacks.append(ModelCheckpoint(self.weights_path, monitor='val_loss', verbose=1, save_best_only=False, save_weights_only=True))
		dataX, dataY = self.getdata("SPY",datapoints=3200,skip=1200)
		dataXval, dataYval = self.getdata("SPY",datapoints=800,skip=400)
		self.model.fit(dataX,dataY,validation_data=(dataXval,dataYval),callbacks=callbacks,epochs=100)
		self.model.save_weights(self.weights_path)


	def test(self):
		length = 400
		predicted = self.indicator(stock="SPY",length=length,skip=0)
		actual = self.percentchange(stock="SPY",length=length) * 100
		plt.hold(True)
		t = np.linspace(1,length,length)
		plt.plot(t,predicted,'go')
		plt.plot(t,actual,'r.')
		plt.plot(np.array([0,length]),np.array([0,0]))
		plt.show()


	def getdata(self,stock,datapoints=1,skip=-1):
		# returns tuple (inputs, resulting next day price change)
		# datapoints: number of time steps
		# skip: number of most recent datapoints to skip 
		# (if -1, then the last element in dataX is the most recent data for the stock and dataY is NaN)
		percchange = self.percentchange(stock,length=skip+datapoints+self.lookback)
		bollinger = self.bollinger(stock,length=skip+datapoints+self.lookback)
		macd = self.macd(stock,length=skip+datapoints+self.lookback)
		rsi2 = self.rsi(stock,mawindow=2,length=skip+datapoints+self.lookback)
		rsi14 = self.rsi(stock,mawindow=14,length=skip+datapoints+self.lookback)
		dataX = []
		dataY = []
		for i in range(datapoints):
			dataX.append(self.formatdata(percchange[i:i+self.lookback],
										 bollinger[i:i+self.lookback],
										 macd[i:i+self.lookback],
										 rsi2[i:i+self.lookback],
										 rsi14[i:i+self.lookback]))
			if i+self.lookback < len(percchange):
				dataY.append(percchange[i+self.lookback] * 100)
			else:
				dataY.append(np.nan)
		dataX = np.array(dataX)
		dataY = np.array(dataY)
		return (dataX, dataY)


	def formatdata(self,percchange,bollinger,macd,rsi2,rsi14):
		percchange = percchange * 100
		volatility = (bollinger['Real Upper Band'] - bollinger['Real Lower Band']) / bollinger['Real Middle Band']
		rsi2 /= 100
		ddtrsi14 = rsi14.diff() / 100
		ddtrsi14[0] = 0
		data = np.concatenate((np.expand_dims(percchange,axis=1),
							   np.expand_dims(volatility,axis=1),
							   np.expand_dims(macd,axis=1),
							   np.expand_dims(rsi2,axis=1)),axis=1)
							   # np.expand_dims(ddtrsi14,axis=1)
		return data


def accuracy(y_true,y_pred):
	return K.sum(tf.to_float(K.equal(K.sign(y_true),K.sign(y_pred)))) / tf.to_float(tf.shape(y_true)[0])

def train():
	algo = RNN()
	algo.train()

def test():
	algo = RNN()
	algo.test()

def debug():
	algo = RNN()
	import pdb; pdb.set_trace()
	algo.test()

def backtest():
	algo = backtester(RNN())
	algo.start(startdate=(1,1,2017))
	algo.gui()
	import code; code.interact(local=locals())

if __name__ == '__main__':
	backtest()
		