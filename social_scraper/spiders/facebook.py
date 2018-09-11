# -*- coding: utf-8 -*-
import scrapy


class FacebookSpider(scrapy.Spider):
    name = 'facebook'
    allowed_domains = ['https://facebook.com']
    start_urls = ['http://https://facebook.com/']

    def parse(self, response):
        pass
