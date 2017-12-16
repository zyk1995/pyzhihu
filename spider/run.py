#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Description
- 实现多线程，主线程和若干工作线程。
- 主线程：维护一个已爬取用户的set，用于去重；从响应队列中取出关注用户的列表，去重后放入任务队列。
- 工作线程：从任务队列获取url token，爬取用户信息后，存入csv文件；并生成响应信息放入响应队列。
Info
- author : "zyk"
- github : "1251134350@qq.com"
- date   : "2017.11.24"
"""
import time
import os
import json
from threading import Thread
from queue import Queue
from crawl import Crawl
from datafile import DataFile

__author__ = 'zyk'