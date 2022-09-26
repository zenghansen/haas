#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

'''
基于HaaS Python框架的本地语音播报温湿度系统
'''

from aliyunIoT import Device
import netmgr as nm
import utime
import ujson
from speech_utils import (
    Speaker,
    AUDIO_HEADER
)
import time
from cht8305 import CHT8305 
from driver import I2C
import sh1106              # SH1106 OLED驱动库
from driver import SPI     # 引入SPI总线库
from driver import GPIO    # 引入GPIO库
import framebuf            # framebuf基类，用于设置字体库

from driver import ADC
import noise
import _thread


# 语音播放相关的音频资源文件定义
resDir = "/data/pyamp/resource/"
tonepathConnected = AUDIO_HEADER + resDir + "connected.wav"
tonepathPowerOn = AUDIO_HEADER + resDir + "poweron.wav"

# 三元组信息
productKey = "a1gUTjU8p84"
deviceName = "myth"
deviceSecret = "6041ff67571bcd434850a044be56eacb"

# 空调和加湿器状态变量
airconditioner = 0
humidifier = 0
airconditioner_value = 0
humidifier_value = 0


# Wi-Fi SSID和Password设置
wifi_ssid = "huawei"
wifi_password = "12345678"

# 回调函数状态
on_request = False
on_play = False
iot_connected = False


# 等待Wi-Fi成功连接到路由器
def get_wifi_status():
    nm.init()
    wifi_connected = nm.getStatus()
    nm.disconnect()
    print("start to connect " , wifi_ssid)
    # 连接到指定的路由器（路由器名称为wifi_ssid, 密码为：wifi_password）
    nm.connect(wifi_ssid, wifi_password)

    while True :
        if wifi_connected == 5:               # nm.getStatus()返回5代表连线成功
            break
        else:
            wifi_connected = nm.getStatus() # 获取Wi-Fi连接路由器的状态信息
            utime.sleep(0.5)
            print("wifi_connectedaa:", wifi_connected)
    # utime.sleep(5)
    print("Wi-Fi connected")
    print('DeviceIP:' + nm.getInfo()['ip'])  # 打印Wi-Fi的IP地址信息

# 物联网平台连接成功的回调函数
def on_connect(data):
    global iot_connected
    iot_connected = True

def post_data_to_cloud(device, temphumidity):
    # 上报温湿度到云平台
    prop = ujson.dumps({
        "CurrentTemperature": temphumidity[0],
        "CurrentHumidity": temphumidity[1],
    })
    

    

    upload_data = {"params": prop}
    ret = device.postProps(upload_data)
    
    if(ret == -516):
        global iot_connected
        iot_connected = False
        get_wifi_status()


def play_display_temperature_humidity(cht8305Dev):
    play_data = {"format":0, "speechs":[]}
    temphumidity = cht8305Dev.getTempHumidity()
    print("当前温度:", temphumidity[0], "当前湿度:", temphumidity[1])

    if (temphumidity[0] < 0):
        temperature = "{$%.2f}" % -temphumidity[0]
        humidity = "{$%.2f}" % temphumidity[1]
        play_data["speechs"] = ["temperature", "negative", temperature, "centigrade", "humidity", humidity]
    else:
        temperature = "{$%.2f}" % temphumidity[0]
        humidity = "{$%.2f}" % temphumidity[1]
        play_data["speechs"] = ["temperature", temperature, "centigrade", "humidity", humidity]

    temp_str = "T:%.2f" % temphumidity[0]
    humi_str = "H:%.2f%%" % temphumidity[1]
    print("temp_str",temp_str)
    print("humi_str",humi_str)
    oledShowText(temp_str, 3, 1, 1, True, 12)
    oledShowText(humi_str, 13, 26, 1, False, 16)

    #speaker.play_voice(play_data,resDir)
    return temphumidity

# OLED初始化
def oledInit():
    global oled

    # 字库文件存放于项目目录 font, 注意若用到了中英文字库则都需要放置
    framebuf.set_font_path(framebuf.FONT_ASC12_8, '/data/font/ASC12_8')
    framebuf.set_font_path(framebuf.FONT_ASC16_8, '/data/font/ASC16_8')
    framebuf.set_font_path(framebuf.FONT_ASC24_12, '/data/font/ASC24_12')
    framebuf.set_font_path(framebuf.FONT_ASC32_16, '/data/font/ASC32_16')

    oled_spi = SPI()
    oled_spi.open("oled_spi")

    oled_res = GPIO()
    oled_res.open("oled_res")

    oled_dc = GPIO()
    oled_dc.open("oled_dc")

    #oled像素132*64
    oled = sh1106.SH1106_SPI(132, 64, oled_spi, oled_dc, oled_res)

# OLED显示
# text:显示的文本
# x:水平坐标 y:垂直坐标
# color:颜色
# clear: True-清屏显示 False-不清屏显示
# sz:字体大小
def oledShowText(text, x, y, color, clear, sz):
    global oled
    if clear:
        oled.fill(0) # 清屏
    oled.text(text, x, y, color, size = sz)
    oled.show()

# 连接物联网平台
def do_connect_lk(productKey, deviceName, deviceSecret):
    global device, iot_connected, on_request, on_play, oled
    key_info = {
        'region' : 'cn-shanghai' ,      #实例的区域
        'productKey': productKey ,      #物联网平台的PK
        'deviceName': deviceName ,      #物联网平台的DeviceName
        'deviceSecret': deviceSecret ,  #物联网平台的deviceSecret
        'keepaliveSec': 60
    }
    # 将三元组信息设置到iot组件中
    device = Device()

    # 设定连接到物联网平台的回调函数，如果连接物联网平台成功，则调用on_connect函数
    device.on(Device.ON_CONNECT, on_connect)

    # 配置收到云端属性控制指令的回调函数，如果收到物联网平台发送的属性控制消息，则调用on_props函数
    device.on(Device.ON_PROPS, on_props)

    print ("开始连接物联网平台")

    # 启动连接阿里云物联网平台过程
    device.connect(key_info)
    # 等待设备成功连接到物联网平台
    while True:
        if iot_connected:
            print("物联网平台连接成功")
            #speaker.play(tonepathConnected)
            break
        else:
            print("sleep for 1 s")
            time.sleep(1)

    # 打开CHT8305温湿度传感器
    i2cDev = I2C()
    
    i2cDev.open("cht8305")
    cht8305Dev = CHT8305(i2cDev)


    oledInit()

    # # 检测温湿度语音播报并上报云端
    while True:
        temphumidity = play_display_temperature_humidity(cht8305Dev)
        post_data_to_cloud(device, temphumidity)
        time.sleep(10)
        print("sleep for 10 s")
        

    oled.spi.close()
    oled.res.close()
    oled.dc.close()
    i2cDev.close()
    # 断开连接
    device.end()

# 设置props 事件接收函数（当云平台向设备下发属性时）
def on_props(request):
    global airconditioner, humidifier, airconditioner_value, humidifier_value

    # {"airconditioner":1} or {"humidifier":1} or {"airconditioner":1, "humidifier":1}
    payload = ujson.loads(request['params'])
    print ("接收云回调数据",payload)
    # 获取dict状态字段 注意要验证键存在 否则会抛出异常
    if "airconditioner" in payload.keys():
        airconditioner_value = payload["airconditioner"]
        if (airconditioner_value):
            print("打开空调")
        else:
            print("关闭空调")

    if "humidifier" in payload.keys():
        humidifier_value = payload["humidifier"]
        if (humidifier_value):
            print("打开加湿器")
        else:
            print("关闭加湿器")

    # print(airconditioner_value, humidifier_value)

    airconditioner.write(airconditioner_value) # 控制空调开关
    humidifier.write(humidifier_value)         # 控制加湿器开关

    # 要将更改后的状态同步上报到云平台
    prop = ujson.dumps({
        'airconditioner': airconditioner_value,
        'humidifier': humidifier_value,
    })

    upload_data = {'params': prop}
    # 上报空调和加湿器属性到云端
    device.postProps(upload_data)

if __name__ == '__main__':
    print("local speaker demo version")
    #speaker = Speaker(resDir)                                       # 初始化speaker
    #speaker.play(tonepathPowerOn)                                   # 播放开机启动提示音


    airconditioner = GPIO()
    humidifier = GPIO()
    red = GPIO()

    humidifier.open('led_g')     # 加湿器使用board.json中led_g节点定义的GPIO，对应HaaS EDU K1上的绿灯
    airconditioner.open('led_b') # 空调使用board.json中led_b节点定义的GPIO，对应HaaS EDU K1上的蓝灯

    red.open('led_r')  

    red.write(1)

    airconditioner.write(1)
    humidifier.write(1)

    get_wifi_status()

    adcObj = ADC()
    # 按照 board.json 中名为 "noise_adc" 的设备节点的配置参数，初始化 ADC 类型设备对象
    ret = adcObj.open('noise_adc')
    if ret != 0:
        raise Exception('open device failed %s' % ret)

    # 初始化 Noise 传感器
    drv = noise.Noise(adcObj)

    print('watch, doing...')

    _thread.start_new_thread(do_connect_lk,[productKey, deviceName, deviceSecret])

    while True:      # 无限循环
        voltage = drv.getVoltage()  # 获取当前噪音值 mV

        #print("voltage is", voltage, "mV")

        changed = drv.checkNoise(voltage, 100)  # 检查噪音值是否有变化，阈值为400mV（默认）
        if changed:
            print('got change %s' % voltage)


        utime.sleep_ms(30)

    adcObj.close()  # 关闭 ADC 设备

                     
    #do_connect_lk(productKey, deviceName, deviceSecret)     # 启动千里传音服务
