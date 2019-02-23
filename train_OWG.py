## train_OWG.py 
## A script to train optical wave height gauges for 4 models and 4 batch sizes
## Written by Daniel Buscombe,
## Northern Arizona University
## daniel.buscombe.nau.edu

## GPU with 10GB memory recommended

import numpy as np 
import pandas as pd 

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

import os
import json
import time, datetime
from glob import glob
from keras.applications.mobilenet import MobileNet
from keras.applications.mobilenet_v2 import MobileNetV2
from keras.applications.inception_v3 import InceptionV3
from keras.applications.inception_resnet_v2 import InceptionResNetV2

from keras.layers import GlobalAveragePooling2D, Dense, Dropout, Flatten, BatchNormalization
from keras.models import Sequential
from keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
from sklearn.model_selection import train_test_split
from keras.preprocessing.image import ImageDataGenerator

from utils import *

from keras.metrics import mean_absolute_error

def mae_metric(in_gt, in_pred):
    return mean_absolute_error(div*in_gt, div*in_pred)


#==============================================================	
## script starts here
if __name__ == '__main__':

	# start time
	print ("start time - {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
	start = time.time()
	
	# load the user configs
	with open(os.getcwd()+os.sep+'conf'+os.sep+'config.json') as f:    
		config = json.load(f)

	print(config)
	# config variables
	imsize    = int(config["img_size"])
	num_epochs = int(config["num_epochs"]) ##100
	test_size = float(config["test_size"])
	batch_size = int(config["batch_size"])
	height_shift_range = float(config["height_shift_range"])
	width_shift_range = float(config["width_shift_range"])
	rotation_range = float(config["rotation_range"])
	samplewise_std_normalization = config["samplewise_std_normalization"]
	horizontal_flip = config["horizontal_flip"]
	vertical_flip = config["vertical_flip"]
	samplewise_center = config["samplewise_center"]
	shear_range = float(config["shear_range"])
	zoom_range = float(config["zoom_range"])
	steps_per_epoch = int(config["steps_per_epoch"])
	dropout_rate = float(config["dropout_rate"])
	epsilon = float(config["epsilon"])
	min_lr = float(config["min_lr"])
	factor = float(config["factor"])
	input_image_format = config["input_image_format"]
	input_csv_file = config["input_csv_file"]
	category = config["category"] ##'H'
	fill_mode = config["fill_mode"]
	
	IMG_SIZE = (imsize, imsize) ##(128, 128) 
	
	base_dir = os.path.normpath(os.getcwd()+os.sep+'train') 

	for batch_size in [16,32,64,128]: 
		print ("[INFO] Batch size = "+str(batch_size))
		
		archs = {'1':MobileNet, '2':MobileNetV2, '3':InceptionV3, '4':InceptionResNetV2}

		counter =1

		for arch in archs:
			print(arch)

			df = pd.read_csv(os.path.join(base_dir, input_csv_file)) ##'training-dataset.csv'))
																																									 
			df['path'] = df['id'].map(lambda x: os.path.join(base_dir,
															     'images',  
															     '{}.png'.format(x)))	
																 
			df['exists'] = df['path'].map(os.path.exists)
			print(df['exists'].sum(), 'images found of', df.shape[0], 'total')

			if category == 'H':
				mean = df['H'].mean() 
				div = 2*df['H'].std() 
				df['zscore'] = df['H'].map(lambda x: (x-mean)/div)
			elif category == 'T':
				mean = df['T'].mean() 
				div = 2*df['T'].std() 
				df['zscore'] = df['T'].map(lambda x: (x-mean)/div)			
			else:
				print("Unknown category: "+str(category))
				print("Fix config file, exiting now ...")
				import sys
				sys.exit()
			
			df.dropna(inplace = True)
			
			if category == 'H':
				df['category'] = pd.cut(df['H'], 10)
			else:
				df['category'] = pd.cut(df['T'], 8)

			new_df = df.groupby(['category']).apply(lambda x: x.sample(2000, replace = True) 
																  ).reset_index(drop = True)
			print('New Data Size:', new_df.shape[0], 'Old Size:', df.shape[0])

			train_df, valid_df = train_test_split(new_df, 
											   test_size = test_size, #0.33, 
											   random_state = 2018,
											   stratify = new_df['category'])
			print('train', train_df.shape[0], 'validation', valid_df.shape[0])


			im_gen = ImageDataGenerator(samplewise_center=samplewise_center, ##True, 
										  samplewise_std_normalization=samplewise_std_normalization, ##True, 
										  horizontal_flip = horizontal_flip, ##False, 
										  vertical_flip = vertical_flip, ##False, 
										  height_shift_range = height_shift_range, ##0.1, 
										  width_shift_range = width_shift_range, ##0.1, 
										  rotation_range = rotation_range, ##10, 
										  shear_range = shear_range, ##0.05,
										  fill_mode = fill_mode, ##'reflect', #'nearest',
										  zoom_range= zoom_range) ##0.2)

			train_gen = gen_from_df(im_gen, train_df, 
										 path_col = 'path',
										y_col = 'zscore', 
										target_size = IMG_SIZE,
										 color_mode = 'grayscale',
										batch_size = batch_size) ##64)

			valid_gen = gen_from_df(im_gen, valid_df, 
										 path_col = 'path',
										y_col = 'zscore', 
										target_size = IMG_SIZE,
										 color_mode = 'grayscale',
										batch_size = batch_size) ##64) 
									
			test_X, test_Y = next(gen_from_df(im_gen, 
										   valid_df, 
										 path_col = 'path',
										y_col = 'zscore', 
										target_size = IMG_SIZE,
										 color_mode = 'grayscale',
										batch_size = len(df))) ##1000 


			t_x, t_y = next(train_gen)
		   
			train_gen.batch_size = batch_size

			if category == 'H':			
				weights_path="im"+str(IMG_SIZE[0])+"_waveheight_weights_model"+str(counter)+"_"+str(num_epochs)+"epoch_"+str(train_gen.batch_size)+"batch.best.hdf5" 
			else:
				weights_path="im"+str(IMG_SIZE[0])+"_waveperiod_weights_model"+str(counter)+"_"+str(num_epochs)+"epoch_"+str(train_gen.batch_size)+"batch.best.hdf5" 			

			model_checkpoint = ModelCheckpoint(weights_path, monitor='val_loss', verbose=1, 
									 save_best_only=True, mode='min', save_weights_only = True)


			reduceloss_plat = ReduceLROnPlateau(monitor='val_loss', factor=factor, patience=10, verbose=1, mode='auto', epsilon=epsilon, cooldown=5, min_lr=min_lr) ##0.0001, 0.8
			earlystop = EarlyStopping(monitor="val_loss", mode="min", patience=15) 
			callbacks_list = [model_checkpoint, earlystop, reduceloss_plat]	

			base_model = archs[arch](input_shape =  t_x.shape[1:], include_top = False, weights = None)

			print ("[INFO] Training optical wave gauge")
			
			OWG = Sequential()
			OWG.add(BatchNormalization(input_shape = t_x.shape[1:]))
			OWG.add(base_model)
			OWG.add(BatchNormalization())
			OWG.add(GlobalAveragePooling2D())
			OWG.add(Dropout(dropout_rate)) ##0.5
			OWG.add(Dense(1, activation = 'linear' )) 

			OWG.compile(optimizer = 'adam', loss = 'mse',
								   metrics = [mae_metric])

			OWG.summary()
			
			# train the model
			OWG.fit_generator(train_gen, validation_data = (test_X, test_Y), 
										  epochs = num_epochs, steps_per_epoch= steps_per_epoch, ##100, 
										  callbacks = callbacks_list)

			# load the new model weights							  
			OWG.load_weights(weights_path)

			print ("[INFO] Testing optical wave gauge")
			
			# the model predicts zscores - recover value using pop. mean and standard dev.			
			pred_Y = div*OWG.predict(test_X, batch_size = train_gen.batch_size, verbose = True)+mean
			test_Y = div*test_Y+mean

			print ("[INFO] Creating plots ")
			
			fig, ax1 = plt.subplots(1,1, figsize = (6,6))
			ax1.plot(test_Y, pred_Y, 'k.', label = 'predictions')
			ax1.plot(test_Y, test_Y, 'r-', label = 'actual')
			ax1.legend()
			if category == 'H':			
				ax1.set_xlabel('Actual H (m)')
				ax1.set_ylabel('Predicted H (m)')
				plt.savefig('im'+str(IMG_SIZE[0])+'_waveheight_model'+str(counter)+'_'+str(num_epochs)+'epoch'+str(train_gen.batch_size)+'batch.png', dpi=300, bbox_inches='tight')
			else:
				ax1.set_xlabel('Actual T (s)')
				ax1.set_ylabel('Predicted T (s)')
				plt.savefig('im'+str(IMG_SIZE[0])+'_waveperiod_model'+str(counter)+'_'+str(num_epochs)+'epoch'+str(train_gen.batch_size)+'batch.png', dpi=300, bbox_inches='tight')
			
			plt.close('all')

			rand_idx = np.random.choice(range(test_X.shape[0]), 9)
			fig, m_axs = plt.subplots(3, 3, figsize = (16, 32))
			for (idx, c_ax) in zip(rand_idx, m_axs.flatten()):
			  c_ax.imshow(test_X[idx, :,:,0], cmap = 'gray')
			  if category == 'H':
			     c_ax.set_title('H: %0.3f\nPredicted H: %0.3f' % (test_Y[idx], pred_Y[idx]))
			  else:
			     c_ax.set_title('T: %0.3f\nPredicted T: %0.3f' % (test_Y[idx], pred_Y[idx]))
			  
			  c_ax.axis('off')

			if category == 'H':			  
				fig.savefig('im'+str(IMG_SIZE[0])+'_waveheight_predictions_model'+str(counter)+'_'+str(num_epochs)+'epoch'+str(train_gen.batch_size)+'batch.png', dpi=300, bbox_inches='tight')
			else:
				fig.savefig('im'+str(IMG_SIZE[0])+'_waveperiod_predictions_model'+str(counter)+'_'+str(num_epochs)+'epoch'+str(train_gen.batch_size)+'batch.png', dpi=300, bbox_inches='tight')			

			counter += 1

   
	# end time
	end = time.time()
	print ("end time - {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

	
