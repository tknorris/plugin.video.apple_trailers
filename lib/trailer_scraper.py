"""
     Apple Trailers Kodi Addon
    Copyright (C) 2016 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import re
import urllib2
import urlparse
import json
import log_utils
import cache
from email.utils import parsedate_tz
import xml.etree.ElementTree as ET

BASE_URL = 'http://trailers.apple.com/trailers'
COVER_BASE_URL = 'http://trailers.apple.com'
MOVIES_URL = BASE_URL + '/home/feeds/%s.json'
XML_URL = BASE_URL + '/home/xml/current.xml'
USER_AGENT = 'iTunes'

class Scraper(object):
    def __init__(self):
        self.plots = self.__get_plots()
        
    def get_all_movies(self, limit=0):
        return self.__get_movies('studios', limit)
    
    def get_most_popular_movies(self, limit=0):
        return self.__get_movies('most_pop', limit)
    
    def get_exclusive_movies(self, limit=0):
        return self.__get_movies('exclusive', limit)
    
    def get_most_recent_movies(self, limit=0):
        return self.__get_movies('just_added', limit)
        
    def __get_movies(self, source, limit):
        for i, movie in enumerate(self.__get_movies_json(source)):
            log_utils.log(movie)
            if limit and i >= limit: break
            meta = {}
            meta['mediatype'] = 'movie'
            meta['title'] = movie['title']
            meta['premiered'] = meta['aired'] = self.__parse_date(movie.get('releasedate'))
            meta['year'] = meta['premiered'][:4]
            meta['poster'] = self.__make_poster(movie['poster'])
            meta['fanart'] = self.__make_background(movie['poster'])
            meta['studio'] = movie.get('studio', '')
            meta['mpaa'] = movie.get('rating', '')
            meta['director'] = movie.get('directors', '')
            meta['genre'] = ', '.join(movie.get('genre', []))
            meta['cast'] = movie.get('actors', [])
            plot = self.plots.get(meta['title'], {})
            meta['movie_id'] = plot.get('id', '')
            meta['plot'] = meta['plotoutline'] = plot.get('plot', '')
            meta['location'] = movie.get('location', '')
            yield meta
            
    def __get_plots(self):
        xml = self.__get_url(XML_URL)
        xml = re.sub('[^\x00-\x7F]', '', xml)
        xml = re.sub('[\x01-\x08\x0B-\x0C\x0E-\x1F]', '', xml)
        root = ET.fromstring(xml)
        plots = {}
        for movie in root.findall('.//movieinfo'):
            info = movie.find('info')
            title = info.find('title').text
            if title:
                plots[title] = {'id': movie.get('id'), 'plot': info.find('description').text}
        return plots
        
    def __parse_date(self, date_str):
        if date_str:
            d = parsedate_tz(date_str)
            return '%04d-%02d-%02d' % (d[0], d[1], d[2])
        else:
            return ''
    
    def __make_poster(self, url):
        if not url.startswith('http'):
            url = urlparse.urljoin(COVER_BASE_URL, url)
        return url.replace('poster', 'poster-xlarge')
            
    def __make_background(self, url):
        if not url.startswith('http'):
            url = urlparse.urljoin(COVER_BASE_URL, url)
        return url.replace('poster', 'background')
    
    def __get_movies_json(self, source):
        try:
            html = self.__get_url(MOVIES_URL % (source))
            return json.loads(html)
        except ValueError:
            return {}

    @cache.cache_method(cache_limit=8)
    def __get_url(self, url):
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        html = urllib2.urlopen(req).read()
        return html
