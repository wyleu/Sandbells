import smbus2
import RPi.GPIO as GPIO
from time import sleep
import i2cEncoderLibV2

import ADS1x15

import VL53L0X

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

def map_range(x, in_min, in_max, out_min, out_max):
  return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

GPIO.setmode(GPIO.BCM)
bus = smbus2.SMBus(1)

#Encoder set up

INT_pin = 17
GPIO.setup(INT_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

encoder = i2cEncoderLibV2.i2cEncoderLibV2(bus, 0x47)

encconfig = (
    i2cEncoderLibV2.INT_DATA |
    i2cEncoderLibV2.WRAP_ENABLE |
    i2cEncoderLibV2.DIRE_RIGHT |
    i2cEncoderLibV2.IPUP_ENABLE |
    i2cEncoderLibV2.RMOD_X1 |
    i2cEncoderLibV2.RGB_ENCODER)

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

encoder.writeGP1conf(i2cEncoderLibV2.GP_PWM | i2cEncoderLibV2.GP_PULL_DI | i2cEncoderLibV2.GP_INT_DI)
encoder.writeGP2conf(i2cEncoderLibV2.GP_PWM| i2cEncoderLibV2.GP_PULL_DI | i2cEncoderLibV2.GP_INT_DI)

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


# Output Laser
encoder.writeGP1(255) # Laser on
encoder.writeGP2(255) # Lasers on

print('Laser1', encoder.readGP1())
print('Laser2', encoder.readGP2())

print('Laser1 conf', encoder.readGP1conf())
print('Laser2 conf', encoder.readGP2conf())

# Set up the AtoD board.
ADS = ADS1x15.ADS1115(1)
print("ADS:-", ADS)

# Set up the distance sensor 

tof = VL53L0X.VL53L0X(i2c_bus=1,i2c_address=0x29)
tof.open()
# Start ranging
tof.start_ranging(VL53L0X.Vl53l0xAccuracyMode.BETTER)

timing = tof.get_timing()

if timing < 20000:
    timing = 20000
print("Timing %d ms" % (timing/1000))


# activity toggle blue lED

activity = True
activity_count = 0
activity_threshold =  20 

# GPIO.add_event_detect(INT_pin, GPIO.FALLING, callback=Encoder_INT, bouncetime=10)

encoder.writeRGBCode(0x006400)
distance = 0
distance_max = 0   # 1280 ++ 
distance_min = 0   # 4 ++

while True:
    if GPIO.input(INT_pin) == False: #
        Encoder_INT() #
        encoder.writeLEDG(int(map_range(distance, 0, 1290, 0, 100)))

    value = tof.get_distance()
    if value != 8190 and value != 0:
        distance = value

    a0 = ADS.readADC(0)
    a1 = ADS.readADC(1)
    a2 = ADS.readADC(2)
    a3 = ADS.readADC(3)

    average = ( a0 + a1 + a2 + a3 ) / 4
    print(a0,'      ', a1,'    ', a2,'    ', a3, '      ', distance , map_range(distance, 0, 1290, 0, 64))

    encoder.writeLEDG(int(map_range(distance, 0, 1290, 0, 100)))
    encoder.writeLEDR(int(map_range(average, 0, 32768, 0, 100)))     #32768


    # Toggle actiity LED
    if activity_count == activity_threshold:
        activity_count = 0
        encoder.writeLEDB(100)
    else:
        encoder.writeLEDB(0)
    activity = not activity
    activity_count = activity_count + 1 


sleep(0.3)
encoder.writeRGBCode(0x00)
print('Shutdown cleanly...')
