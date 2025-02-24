# KerberosSDR Receiver

# Copyright (C) 2018-2019  Carl Laufer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

# -*- coding: utf-8 -*-

import numpy as np
import sys,os
import time
from struct import pack, unpack
from scipy import signal
from PyQt5 import QtCore

currentpath = os.path.dirname(os.path.realpath(__file__))

class ReceiverRTLSDR(QtCore.QObject):
    
    signal_spectrum_ready = QtCore.pyqtSignal()
    # GUI Signal definitions
   
    def __init__(self):
            #print("[ INFO ] Python rec: Starting Python RTL-SDR receiver")
            super().__init__()
            # Receiver control parameters            
            self.gc_fifo_name = currentpath + "/C/gate_control_fifo"
            self.sync_fifo_name = currentpath + "/C/sync_control_fifo"
            self.rec_control_fifo_name = currentpath + "/C/rec_control_fifo"
            
            self.gate_trigger_byte = pack('B',1)          
            self.gate_close_byte = pack('B',2)
            self.sync_close_byte = pack('B',2)
            self.rec_control_close_byte = pack('B',2) 
            self.sync_delay_byte = 'd'.encode('ascii')
            self.reconfig_tuner_byte = 'r'.encode('ascii')
            self.noise_source_on_byte = 'n'.encode('ascii')
            self.noise_source_off_byte = 'f'.encode('ascii')

            self.close_byte = 'c'.encode('ascii')
            self.open_byte = 'o'.encode('ascii')
            self.close_flag = False


            self.gc_fifo_descriptor = open(self.gc_fifo_name, 'w+b', buffering=0)
            self.sync_fifo_descriptor = open(self.sync_fifo_name, 'w+b', buffering=0)
            self.rec_control_fifo_descriptor = open(self.rec_control_fifo_name, 'w+b', buffering=0)
            
            self.receiver_gain = 0 # Gain in dB x 10 
            self.receiver_gain_2 = 0 # Gain in dB x 10 
            self.receiver_gain_3 = 0 # Gain in dB x 10 
            self.receiver_gain_4 = 0 # Gain in dB x 10 
            
            # Data acquisition parameters
            self.channel_number = 4
            self.block_size = 0; #128 * 1024 #256*1024
                        
            self.overdrive_detect_flag = False

            # IQ preprocessing parameters
            self.en_dc_compensation = False
            self.fs = 1.024 * 10**6  # Sampling frequency
            self.iq_corrections = np.array([1,1,1,1], dtype=np.complex64)  # Used for phase and amplitude correction
            self.fir_size = 0
            self.fir_bw = 1  # Normalized to sampling frequency
            self.fir_filter_coeffs = np.empty(0)
            self.decimation_ratio = 1
            
         
            
            
    def set_sample_offsets(self, sample_offsets):
        #print("[ INFO ] Python rec: Setting sample offset")
        delays = [0] + (sample_offsets.tolist())
        #print("Delays: ", delays)
        self.sync_fifo_descriptor.write(self.sync_delay_byte)
        self.sync_fifo_descriptor.write(pack("i"*4,*delays))

    
    def reconfigure_tuner(self, center_freq, sample_rate, gain):
       self.rec_control_fifo_descriptor.write(self.reconfig_tuner_byte)    
       self.rec_control_fifo_descriptor.write(pack("I", int(center_freq)))
       self.rec_control_fifo_descriptor.write(pack("I", int(sample_rate)))
       self.rec_control_fifo_descriptor.write(pack("i", int(gain[0])))
       self.rec_control_fifo_descriptor.write(pack("i", int(gain[1])))
       self.rec_control_fifo_descriptor.write(pack("i", int(gain[2])))
       self.rec_control_fifo_descriptor.write(pack("i", int(gain[3])))

    def switch_noise_source(self, state):
        if state:
            # print("[ INFO ] Python rec: Turning on noise source")
            self.rec_control_fifo_descriptor.write(self.noise_source_on_byte)
        else:
            # print("[ INFO ] Python rec: Turning off noise source")
            self.rec_control_fifo_descriptor.write(self.noise_source_off_byte)


            
    def set_fir_coeffs(self, fir_size, bw):
        """
            Set FIR filter coefficients
            
            TODO: Implement FIR in C and send coeffs there
        """
        
        # Data preprocessing parameters
        if fir_size >0 :
            cut_off = bw/(self.fs / self.decimation_ratio)
            self.fir_filter_coeffs = signal.firwin(fir_size, cut_off, window="hann")
        self.fir_size = fir_size
        
    def download_iq_samples(self):
            self.iq_samples = np.zeros((self.channel_number, self.block_size//2), dtype=np.complex64)
            # to show iq sample in spectrum
            self.spectrum_samples= None 
            self.gc_fifo_descriptor.write(self.gate_trigger_byte)
            #print("[ INFO ] Python rec: Trigger writen")
            # -*- coding: utf-8 -*-
            #time.sleep(0.5)
            read_size = self.block_size * self.channel_number           

            #byte_data=[]
            #format_string = "B"*read_size
            #while True:
            byte_array_read = sys.stdin.buffer.read(read_size)
            
            """                
                if not byte_array_read or len(byte_data) >= read_size:
                    print("EOF")
                    break
            """
            overdrive_margin = 0.95
            self.overdrive_detect_flag = False

            byte_data_np = np.frombuffer(byte_array_read, dtype='uint8', count=read_size)

            self.iq_samples.real = byte_data_np[0:self.channel_number*self.block_size:2].reshape(self.channel_number, self.block_size//2)
            self.iq_samples.imag = byte_data_np[1:self.channel_number*self.block_size:2].reshape(self.channel_number ,self.block_size//2)

            self.iq_samples /= (255 / 2)
            self.iq_samples -= (1 + 1j)
            
            self.spectrum_samples= self.iq_samples[0,]
            self.signal_spectrum_ready.emit()                      
            
            #np.save("hydra_raw.npy",self.iq_samples)
            self.iq_preprocessing()
            #print("[ DONE] IQ sample read ready")
            
            
            #return iq_samples    
       
    def iq_preprocessing(self):
                
        # Decimation
        if self.decimation_ratio > 1:
           iq_samples_dec = np.zeros((self.channel_number, round(self.block_size//2/self.decimation_ratio)), dtype=np.complex64)
           for m in range(self.channel_number):
               iq_samples_dec[m, :] = self.iq_samples[m, 0::self.decimation_ratio]
           self.iq_samples = iq_samples_dec

        # FIR filtering
        if self.fir_size > 0:
            for m in range(self.channel_number):
                self.iq_samples[m, :] = np.convolve(self.fir_filter_coeffs, self.iq_samples[m, :], mode="same")

        # Remove DC content (Force on for now)
        if self.en_dc_compensation or True:
            for m in np.arange(0, self.channel_number):
               self.iq_samples[m,:]-= np.average( self.iq_samples[m,:])
           
        # IQ correction
        for m in np.arange(0, self.channel_number):
            self.iq_samples[m, :] *= self.iq_corrections[m]
            #print(str(self.iq_corrections[m])+",")
        #print("\n")

    def close_device(self):
        if not self.close_flag:
            self.rec_control_fifo_descriptor.write(self.close_byte)
            self.close_flag = True

    def open_device(self):
        if self.close_flag:
            self.rec_control_fifo_descriptor.write(self.open_byte)
            self.close_flag = False

    def close(self):
        self.gc_fifo_descriptor.write(self.gate_close_byte)
        self.sync_fifo_descriptor.write(self.sync_close_byte)
        self.rec_control_fifo_descriptor.write(self.rec_control_close_byte)
        time.sleep(1)
        self.gc_fifo_descriptor.close()
        self.sync_fifo_descriptor.close()
        self.rec_control_fifo_descriptor.close()
        
        print("[ INFO ] Python rec: FIFOs are closed")






        
        


