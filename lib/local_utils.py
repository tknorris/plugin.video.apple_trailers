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
import struct
import xbmcvfs
import kodi
import log_utils
from trailer_scraper import BROWSER_UA
from trakt_api import Trakt_API, TransientTraktError, TraktAuthError
from trakt_api import SECTIONS

def __enum(**enums):
    return type('Enum', (), enums)

Q_ORDER = {'sd': 1, 'hd720': 2, 'hd1080': 3}
TRAKT_SORT = __enum(TITLE='title', ACTIVITY='activity', MOST_COMPLETED='most-completed', LEAST_COMPLETED='least-completed', RECENTLY_AIRED='recently-aired',
                    PREVIOUSLY_AIRED='previously-aired')
TRAKT_LIST_SORT = __enum(RANK='rank', RECENTLY_ADDED='added', TITLE='title', RELEASE_DATE='released', RUNTIME='runtime', POPULARITY='popularity',
                         PERCENTAGE='percentage', VOTES='votes')
TRAKT_SORT_DIR = __enum(ASCENDING='asc', DESCENDING='desc')
WATCHLIST_SLUG = 'watchlist_slug'
MAX_REDIR = 1024

def make_art(meta):
    art_dict = {'banner': '', 'fanart': '', 'thumb': '', 'poster': ''}
    if 'poster' in meta: art_dict['poster'] = meta['poster']
    if 'fanart' in meta: art_dict['fanart'] = meta['fanart']
    if 'thumb' in meta: art_dict['thumb'] = meta['thumb']
    return art_dict

def trailer_exists(path, file_name):
    for f in xbmcvfs.listdir(path)[1]:
        f = f.decode('utf-8')
        if f.startswith(file_name):
            return f

    return False

def get_best_stream(streams, method='stream'):
    setting = 'trailer_%s_quality' % (method)
    user_max = Q_ORDER.get(kodi.get_setting(setting), 3)
    best_quality = 0
    best_stream = ''
    for stream in streams:
        if Q_ORDER[stream] > best_quality and Q_ORDER[stream] <= user_max:
            best_quality = Q_ORDER[stream]
            best_stream = streams[stream]
    return best_stream

def make_list_dict():
    slug = kodi.get_setting('default_slug')
    token = kodi.get_setting('trakt_oauth_token')
    list_data = {}
    if token and slug:
        try:
            trakt_api = Trakt_API(token, kodi.get_setting('use_https') == 'true', timeout=int(kodi.get_setting('trakt_timeout')))
            if slug == WATCHLIST_SLUG:
                trakt_list = trakt_api.show_watchlist(SECTIONS.MOVIES)
            else:
                trakt_list = trakt_api.show_list(slug, SECTIONS.MOVIES)
        except (TransientTraktError, TraktAuthError) as e:
            log_utils.log(str(e), log_utils.LOGERROR)
            kodi.notify(msg=str(e), duration=5000)
            trakt_list = []
                
        for movie in trakt_list:
            key = movie['title'].upper()
            list_data[key] = list_data.get(key, set())
            if movie['year'] is not None:
                new_set = set([movie['year'] - 1, movie['year'], movie['year'] + 1])
                list_data[key].update(new_set)
    log_utils.log('List Dict: %s: %s' % (slug, list_data))
    return list_data

# manually handle quicktime redirects since Kodi doesn't
def resolve_trailer(trailer_url):
    req = urllib2.Request(trailer_url)
    req.add_header('User-Agent', BROWSER_UA)
    res = urllib2.urlopen(req)
    res_headers = dict(res.info().items())
    if res_headers.get('content-type') == 'video/quicktime' and int(res_headers.get('content-length', MAX_REDIR)) < MAX_REDIR:
        mov = res.read()
        r = re.search('moov.*?rmra.*?rdrf.*?url (....)(.*)', mov)
        if r:
            url_len = struct.unpack("!I", r.group(1))[0]
            trailer_url = r.group(2)[:url_len]
    return trailer_url
