import logging
import textwrap
import time
import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bin.SSD1306 import SSD1306_128_32 as SSD1306

import smbus2
import RPi.GPIO as GPIO
from time import sleep
import i2cEncoderLibV2


def EncoderChange():
    encoder.writeLEDG(100)
    print ('Changed: %d' % (encoder.readCounter32()))
    encoder.writeLEDG(0)

def EncoderPush():
    encoder.writeLEDB(100)
    print ('Encoder Pushed!')
    encoder.writeLEDB(0)

def EncoderDoublePush():
    encoder.writeLEDB(100)
    encoder.writeLEDG(100)
    print ('Encoder Double Push!')
    encoder.writeLEDB(0)
    encoder.writeLEDG(0)

def EncoderMax():
    encoder.writeLEDR(100)
    print ('Encoder max!')
    encoder.writeLEDR(0)

def EncoderMin():
    encoder.writeLEDR(100)
    print ('Encoder min!')
    encoder.writeLEDR(0)

def Encoder_INT():
    encoder.updateStatus()

# RGB Encoder setup 
GPIO.setmode(GPIO.BCM)
bus = smbus2.SMBus(1)
INT_pin = 17
GPIO.setup(INT_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

encoder = i2cEncoderLibV2.i2cEncoderLibV2(bus, 0x45)

encconfig = (i2cEncoderLibV2.INT_DATA | i2cEncoderLibV2.WRAP_ENABLE | i2cEncoderLibV2.DIRE_RIGHT | i2cEncoderLibV2.IPUP_ENABLE | i2cEncoderLibV2.RMOD_X1 | i2cEncoderLibV2.RGB_ENCODER)
encoder.begin(encconfig)

encoder.writeCounter(0)
encoder.writeMax(35)
encoder.writeMin(-20)
encoder.writeStep(1)
encoder.writeAntibouncingPeriod(8)
encoder.writeDoublePushPeriod(50)
encoder.writeGammaRLED(i2cEncoderLibV2.GAMMA_2)
encoder.writeGammaGLED(i2cEncoderLibV2.GAMMA_2)
encoder.writeGammaBLED(i2cEncoderLibV2.GAMMA_2)

encoder.onChange = EncoderChange
encoder.onButtonPush = EncoderPush
encoder.onButtonDoublePush = EncoderDoublePush
encoder.onMax = EncoderMax
encoder.onMin = EncoderMin

encoder.autoconfigInterrupt()
print ('Board ID code: 0x%X' % (encoder.readIDCode()))
print ('Board Version: 0x%X' % (encoder.readVersion()))

encoder.writeRGBCode(0x640000)
sleep(0.3)
encoder.writeRGBCode(0x006400)
sleep(0.3)
encoder.writeRGBCode(0x000064)
sleep(0.3)
encoder.writeRGBCode(0x00)


class Display:
    DEFAULT_BUSNUM = 1
    SCREENSHOT_PATH = "./img/examples/"

    def __init__(self, busnum = None):
        self.logger = logging.getLogger('Display')

        if not isinstance(busnum, int):
            busnum = Display.DEFAULT_BUSNUM

        self.display = SSD1306(busnum)
        self.clear()
        self.width = self.display.width
        self.height = self.display.height
        
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def clear(self):
        self.display.begin()
        self.display.clear()
        self.display.display()

    def prepare(self):
        self.draw.rectangle((0, 0, self.width, self.height), outline = 0, fill = 0)
        
    def drawtext(self, text):
        font = ImageFont.truetype("Arial.ttf", 30)
        self.draw.text((2, 2), text, font=font, fill=255)
        

    def show(self):
        self.draw = ImageDraw.Draw(self.image)
        self.display.image(self.image)
        self.display.display()
        
# GPIO.add_event_detect(INT_pin, GPIO.FALLING, callback=Encoder_INT, bouncetime=10)

on = False
last_time =  int(time.time())
encoder_colour = 0x000000
top_sec = False
top_min = False
top_hour = False

disp = Display()

while True:
    if GPIO.input(INT_pin) == False: #
        Encoder_INT() #
        
    current_time = int(time.time())
    
    if current_time != last_time:
            if on:
                encoder_colour = 0x100000
                #encoder.writeRGBCode(0x160000)
            else:
                encoder_colour = 0x001000
                #encoder.writeRGBCode(0x001600)
            on = not on
            last_time = current_time
            # print(hex(encoder_colour))
            disp.prepare()
            time_str = datetime.datetime.fromtimestamp(last_time).strftime('%H:%M:%S')
            # time_str = time.strftime('%H:%M:%S',time.localtime())
            disp.drawtext(time_str)
            print(time_str)

    if time.strftime('%M') == '00':
        if not top_min:
            encoder_colour = encoder_colour | 0x484848 # encoder.writeRGBCode(0x006400)
            print('0 minute')
            top_min = True
            
    elif time.strftime('%M') == '15':
        if not top_min:
            encoder_colour = encoder_colour | 0x484800 
            print('15 minute')
            top_min = True
            
    elif time.strftime('%M') == '30':
        if not top_min:
            encoder_colour = encoder_colour | 0x480048 
            print('30 minute')
            top_min = True
            
    elif time.strftime('%M') == '45':
        if not top_min:
            encoder_colour = encoder_colour | 0x004848 
            print('45 minute')
            top_min = True
    else:
        if time.strftime('%S') == '00':
            if not top_sec:
                # encoder reset
                encoder_colour =  0x000048 # encoder.writeRGBCode(0x000064)
                top_sec = True
                print('00 second')
        else:
            top_sec = False
        top_min = False
        
        
    if time.strftime('%H') == '00':
        encoder_colour = encoder_colour | 0x480000 # encoder.writeRGBCode(0x640000)
        
    encoder.writeRGBCode(encoder_colour)
    disp.show()
        

        
    

