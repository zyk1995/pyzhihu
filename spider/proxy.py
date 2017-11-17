#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Description
- 获取IP代理。
Info
- author : "zyk"
- github : "1251134350@qq.com"
- date   : "2017.11.15"
"""
__author__ = "zyk"

from bs4 import  BeautifulSoup
import  requests
import  random

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


url = 'http://www.xdaili.cn/freeproxy'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36'
}


# 代理服务器
proxyHost = "http-dyn.abuyun.com"
proxyPort = "9020"

# 代理隧道验证信息
proxyUser = ""
proxyPass = ""

proxyMeta = "http://%(host)s:%(port)s" % {
    "host": proxyHost,
    "port": proxyPort,
}

proxies = {
    "http": proxyMeta,
    "https": proxyMeta,
}
'''
def get_ip_list(url, headers):
    web_data = requests.get(url, headers=headers)
    soup = BeautifulSoup(web_data.text, 'html.parser')
    ips = soup.find_all('tr')
    ip_list = []
    for i in range(1, len(ips)):
        ip_info = ips[i]
        print(ips[i])
        tds = ip_info.find_all('td')
        ip_list.append(tds[1].text + ':' + tds[2].text)
    return ip_list
'''

def get_ip_list(url):
    driver = webdriver.Chrome()
    driver.implicitly_wait(10)  # seconds
    driver.get("http://www.xdaili.cn/freeproxy")
    try:
        ips = WebDriverWait(driver, 1000).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#el-table_1_column_8 is-center"))
        )
        ports = WebDriverWait(driver, 1000).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#el-table_1_column_9 is-center"))
        )

        ip_list = []
        for i in range(1, len(ips)):
            ip_list.append(ips[i] + ':' + ports[i])
    finally:
        pass
def get_random_ip(ip_list):
    proxy_list = []
    for ip in ip_list:
        proxy_list.append('http://' + ip)
    proxy_ip = random.choice(proxy_list)
    proxies['http'] = proxy_ip
    proxies['https'] = proxy_ip
    return proxies

def getproxies():
    #ip_list = get_ip_list(url, headers=headers)
    ip_list = get_ip_list(url)
    proxies = get_random_ip(ip_list)
    return proxies

if __name__ == '__main__':
    list = get_ip_list(url)
    for i in list:
        print(i)
    #print(getproxies())



