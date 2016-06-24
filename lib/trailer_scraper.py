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
TRAILERS_URL = BASE_URL + '/feeds/data/%s.json'
XML_URL = BASE_URL + '/home/xml/current.xml'
USER_AGENT = 'iTunes'
BROWSER_UA = 'Mozilla/5.0 (compatible, MSIE 11, Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko'
XHR = {'X-Requested-With': 'XMLHttpRequest'}
SOURCES = ['srcAlt', 'src']

class Scraper(object):
    def __init__(self):
        self.extras = self.__get_extras()
        
    def get_all_movies(self, limit=0):
        return self.__get_movies('studios', limit)
    
    def get_most_popular_movies(self, limit=0):
        return self.__get_movies('most_pop', limit)
    
    def get_exclusive_movies(self, limit=0):
        return self.__get_movies('exclusive', limit)
    
    def get_most_recent_movies(self, limit=0):
        return self.__get_movies('just_added', limit)
        
    def __get_movie_id(self, url):
        headers = {'User-Agent': BROWSER_UA}
        html = self.__get_url(url, headers)
        match = re.search('''var\s+FilmId\s+=\s*['"]([^"']+)''', html)
        if match:
            return match.group(1)
    
    def __get_movies(self, source, limit):
        for i, movie in enumerate(self.__get_json(MOVIES_URL % (source))):
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
            meta['location'] = movie.get('location', '')
            
            extras = self.extras.get(meta['title'], {})
            meta['movie_id'] = extras.get('id', '')
            meta['plot'] = meta['plotoutline'] = extras.get('plot', '')
            if 'duration' in extras and extras['duration']: meta['duration'] = extras['duration']
            yield meta
            
    def get_trailers(self, location, movie_id):
        trailers = []
        if not movie_id.isdigit():
            page_url = urlparse.urljoin(BASE_URL, location)
            movie_id = self.__get_movie_id(page_url)
        
        if movie_id:
            headers = {'User-Agent': BROWSER_UA, 'Referer': page_url}
            headers.update(XHR)
            js_data = self.__get_json(TRAILERS_URL % (movie_id), headers)
            try: movie_title = js_data['page']['movie_title']
            except: movie_title = ''
            try: release_date = js_data['page']['release_date']
            except: release_date = ''
            try: mpaa_rating = js_data['page']['movie_rating'].upper()
            except: mpaa_rating = ''
            try: plot = js_data['details']['locale']['en']['synopsis']
            except: plot = ''
            try: directors = self.__get_cast(js_data['details']['locale']['en']['castcrew']['directors'])
            except: directors = []
            try: writers = self.__get_cast(js_data['details']['locale']['en']['castcrew']['writers'])
            except: writers = []
            try: cast = self.__get_cast(js_data['details']['locale']['en']['castcrew']['actors'])
            except: cast = []
            try: genre = self.__get_genre(js_data['details']['genres'])
            except: genre = []
            try: rating = js_data['reviews']['rating']
            except: rating = ''
            try: votes = js_data['reviews']['count']
            except: votes = ''
            if 'clips' in js_data:
                for clip in js_data['clips']:
                    meta = {}
                    if movie_title:
                        meta['title'] = '%s (%s)' % (movie_title, clip.get('title', 'Trailer'))
                    else:
                        meta['title'] = clip.get('title', 'Trailer')
                    meta['plot'] = plot
                    meta['director'] = ', '.join(directors)
                    meta['writer'] = ', '.join(writers)
                    meta['cast'] = cast
                    meta['genre'] = ', '.join(genre)
                    meta['premiered'] = clip.get('posted', release_date)
                    meta['year'] = meta['premiered'][:4]
                    meta['mpaa'] = mpaa_rating
                    meta['rating'] = rating
                    meta['votes'] = votes
                    meta['thumb'] = clip.get('screen', clip.get('thumb', ''))
                    if 'screen' in clip: meta['thumb'] = clip['screen']
                    if 'runtime' in clip: meta['duration'] = self.__get_duration(clip['runtime'], mult=1)
                    meta['studio'] = clip.get('artist', '')
                    meta['streams'] = self.__get_streams(clip)
                    trailers.append(meta)
        
        return trailers
    
    def __get_extras(self):
        xml = self.__get_url(XML_URL)
        xml = re.sub('[^\x00-\x7F]', '', xml)
        xml = re.sub('[\x01-\x08\x0B-\x0C\x0E-\x1F]', '', xml)
        root = ET.fromstring(xml)
        plots = {}
        for movie in root.findall('.//movieinfo'):
            info = movie.find('info')
            title = info.find('title').text
            if title:
                desc = info.find('description')
                desc = '' if desc is None else desc.text
                runtime = info.find('runtime')
                duration = '' if runtime is None else self.__get_duration(runtime.text)
                plots[title] = {'id': movie.get('id', ''), 'plot': desc, 'duration': duration}
        return plots
        
    def __get_streams(self, clip):
        streams = {}
        if 'versions' in clip and 'enus' in clip['versions'] and 'sizes' in clip['versions']['enus']:
            sizes = clip['versions']['enus']['sizes']
            for key in sizes:
                for source in SOURCES:
                    if source in sizes[key]:
                        streams[key] = sizes[key][source]
                        break
        return streams
        
    def __get_cast(self, cast):
        return [person.get('name', '') for person in cast]
    
    def __get_genre(self, genres):
        return [genre.get('name', '') for genre in genres]
    
    def __get_duration(self, runtime, mult=60):
        duration = 0
        for time in runtime.split(':')[::-1]:
            duration += int(time) * mult
            mult *= 60
        return duration
    
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
    
    def __get_json(self, url, headers=None):
        try:
            html = self.__get_url(url, headers)
            return json.loads(html)
        except ValueError:
            return {}

    @cache.cache_method(cache_limit=8)
    def __get_url(self, url, headers=None):
        if headers is None:
            headers = {'User-Agent': USER_AGENT}
        
        req = urllib2.Request(url, None, headers)
        html = urllib2.urlopen(req).read()
        return html
