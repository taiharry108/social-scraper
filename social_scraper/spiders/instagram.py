# -*- coding: utf-8 -*-
import scrapy
import json
from urllib.parse import urlencode
from scrapy.http.cookies import CookieJar 

class InstagramSpider(scrapy.Spider):
    name = 'instagram'
    allowed_domains = ['instagram.com']
    root_urls = ['https://instagram.com/']

    def __init__(self, username, password,
            user_id="", search="", explore="",
            search_tag=False ,**kwargs):
        self.user_id = user_id
        self.search_key = search
        self.explore_key = explore
        self.search_tag = search_tag == "True"
        self.username = username
        self.password = password
        self.cookie_jar = CookieJar()
        super().__init__(**kwargs)

    def start_requests(self):
        const_list = ["BASE_URL", "LOGIN_URL", "MEDIA_HASH", "QUERY_URL", "SEARCH_URL", "TAG_EXPLORE_HASH"]
        self.const_dict = {const:self.settings.attributes[const].value for const in const_list}
        self.log(self.explore_key)
        
        if self.user_id != "":
            yield scrapy.Request(self.const_dict["BASE_URL"], callback=self.go_to_first_page)
        elif self.search_key != "" and self.search_tag:
            yield scrapy.Request(self.const_dict["SEARCH_URL"] + "%23" + self.search_key, callback=self.tag_search)
        elif self.search_key != "" and not self.search_tag:
            yield scrapy.Request(self.const_dict["SEARCH_URL"] + self.search_key, callback=self.user_search)
        elif self.explore_key != "":
            yield scrapy.Request(self.const_dict["BASE_URL"], callback=self.go_to_first_page)
    
    def go_to_first_page(self, response):
        self.cookie_jar.extract_cookies(response, response.request)
        for cookie in self.cookie_jar:
            if cookie.name == "csrftoken":
                csrftoken = cookie.value
                self.log("csrftoken is set to " + csrftoken)
        
        req = scrapy.FormRequest(url=self.const_dict['LOGIN_URL']
            , method="POST"
            , formdata={
                "username":self.username,
                "password":self.password
            }, headers={
                'X-CSRFToken':csrftoken
            },
        callback=self.home_page)
        yield req
    def user_search(self, response):
        def get_user_data(user):
            user = user["user"]
            return {
                "username":user["username"],
                "full_name":user["full_name"],
                "is_private":user["is_private"],
                "follower_count":user["follower_count"]
            }
        jsonresponse = json.loads(response.body_as_unicode())
        users = jsonresponse["users"]
        results = [get_user_data(user) for user in users]
        return results

    def tag_search(self, response):
        def get_tag_data(tag):
            hashtag = tag["hashtag"]
            return {
                "name":hashtag["name"],
                "count":hashtag["media_count"],
            }
        jsonresponse = json.loads(response.body_as_unicode())
        tags = jsonresponse["hashtags"]
        results = [get_tag_data(tag) for tag in tags]
        return results
    
    @staticmethod
    def create_encoded_data(query_hash, query_data):
        formdata = {
            "query_hash": query_hash,
            "variables": json.dumps(query_data)
        }
        encoded_data = urlencode(formdata)
        encoded_data = encoded_data.replace('%3A+','%3A').replace('%2C+','%2C')
        return encoded_data

    @staticmethod
    def create_query_req(query_url, query_hash, query_data, callback, meta_dict={}):
        encoded_data = InstagramSpider.create_encoded_data(query_hash, query_data)
        req = scrapy.Request(query_url + "?" + encoded_data,
                callback=callback)
        req.meta.update(meta_dict)
        return req

    def create_tag_explore_req(self, tag_name):
        query_data = {
            "tag_name":tag_name,
            "include_reel":True,
            "include_logged_out":False
        }
        req = InstagramSpider.create_query_req(self.const_dict["QUERY_URL"],
                self.const_dict["TAG_EXPLORE_HASH"],
                query_data,
                callback=self.tag_explore_result)
        return req

    def create_page_req(self, result_data):
        const_dict = self.const_dict
        query_data = {
            "id":result_data["page_id"],
            "first":12,
            "after":result_data["end_cursor"]
        }
        req = InstagramSpider.create_query_req(const_dict["QUERY_URL"],
                const_dict["MEDIA_HASH"],
                query_data,
                callback=self.parse_next_page_data,
                meta_dict={"result_data":result_data})
        return req


    def home_page(self, response):
        if self.user_id != "":
            yield scrapy.Request(self.const_dict["BASE_URL"] + self.user_id, callback=self.user_page)
        elif self.explore_key != "":
            yield self.create_tag_explore_req(self.explore_key)
    def tag_explore_result(self, response):
        self.log(response.text)
    def get_post_data(self, edge):
        post_data = {}
        node = edge["node"]
        post_data["post_id"] = node["id"]
        post_data["comment_count"] = node["edge_media_to_comment"]["count"]
        post_data["timestamp"] = node["taken_at_timestamp"]
        post_data["like_count"] = node["edge_media_preview_like"]["count"]
        return post_data
    
    def crawl_data(self, data):
        profile_page = data["entry_data"]["ProfilePage"]
        user = profile_page[0]["graphql"]["user"]
        page_id = user["id"]
        follower_count = user["edge_followed_by"]["count"]
        page_name = user["full_name"]
        timeline_media = user["edge_owner_to_timeline_media"]
        media_count = timeline_media["count"]
        page_info = timeline_media["page_info"]
        has_next_page = page_info["has_next_page"]
        end_cursor = page_info["end_cursor"]
        edges = timeline_media["edges"]
        return {
            "page_id":page_id,
            "follower_count":follower_count,
            "page_name":page_name,
            "media_count":media_count,
            "has_next_page":has_next_page,
            "end_cursor":end_cursor,
            "post_data":[self.get_post_data(edge) for edge in edges]
        }
        
    def parse_next_page_data(self, response):
        data = json.loads(response.body_as_unicode())
        result_data = response.meta["result_data"]
        timeline_media = data["data"]["user"]["edge_owner_to_timeline_media"]
        edges = timeline_media["edges"]
        page_info = timeline_media["page_info"]
        has_next_page = page_info["has_next_page"]
        end_cursor = page_info["end_cursor"]
        result_data["post_data"].extend([self.get_post_data(edge) for edge in edges])
        result_data["has_next_page"] = timeline_media["page_info"]
        result_data["has_next_page"] = has_next_page
        result_data["end_cursor"] = end_cursor
        if result_data["has_next_page"]:
            yield self.create_page_req(result_data)
        else:
            yield result_data
    def user_page(self, response):
        for script in response.css("script::text"):
            text = script.extract()
            if text.startswith('window._sharedData'):
                data = json.loads(text[21:-1])
                result_data = self.crawl_data(data)
                if result_data["has_next_page"]:
                    yield self.create_page_req(result_data)
                else:
                    yield result_data