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
import sys
import os
import urllib2
import urllib
import urlparse
import datetime
import time
import json
import xbmcgui
import xbmc
import xbmcplugin
import xbmcvfs
import kodi
import log_utils
from trakt_api import Trakt_API, TransientTraktError, TraktAuthError
from kodi import i18n
from trailer_scraper import BROWSER_UA
from trakt_api import SECTIONS

def __enum(**enums):
    return type('Enum', (), enums)

INTERVALS = 5
Q_ORDER = {'sd': 1, 'hd720': 2, 'hd1080': 3}
PROGRESS = __enum(OFF=0, WINDOW=1, BACKGROUND=2)
CHUNK_SIZE = 512 * 1024
DEFAULT_EXT = 'mpg'
TRAKT_SORT = __enum(TITLE='title', ACTIVITY='activity', MOST_COMPLETED='most-completed', LEAST_COMPLETED='least-completed', RECENTLY_AIRED='recently-aired',
                    PREVIOUSLY_AIRED='previously-aired')
TRAKT_LIST_SORT = __enum(RANK='rank', RECENTLY_ADDED='added', TITLE='title', RELEASE_DATE='released', RUNTIME='runtime', POPULARITY='popularity',
                         PERCENTAGE='percentage', VOTES='votes')
TRAKT_SORT_DIR = __enum(ASCENDING='asc', DESCENDING='desc')
WATCHLIST_SLUG = 'watchlist_slug'


def make_list_item(label, meta):
    art = make_art(meta)
    listitem = xbmcgui.ListItem(label, iconImage=art['thumb'], thumbnailImage=art['thumb'])
    listitem.setProperty('fanart_image', art['fanart'])
    listitem.addStreamInfo('video', {})
    try: listitem.setArt(art)
    except: pass
    return listitem

def make_art(meta):
    art_dict = {'banner': '', 'fanart': '', 'thumb': '', 'poster': ''}
    if 'poster' in meta: art_dict['poster'] = meta['poster']
    if 'fanart' in meta: art_dict['fanart'] = meta['fanart']
    if 'thumb' in meta: art_dict['thumb'] = meta['thumb']
    return art_dict

def download_media(url, path, file_name):
    try:
        progress = int(kodi.get_setting('down_progress'))
        active = not progress == PROGRESS.OFF
        background = progress == PROGRESS.BACKGROUND
        with kodi.ProgressDialog(kodi.get_name(), i18n('downloading') % (file_name), background=background, active=active) as pd:
            try:
                headers = dict([item.split('=') for item in (url.split('|')[1]).split('&')])
                for key in headers: headers[key] = urllib.unquote(headers[key])
            except:
                headers = {}
            if 'User-Agent' not in headers: headers['User-Agent'] = BROWSER_UA
            request = urllib2.Request(url.split('|')[0], headers=headers)
            response = urllib2.urlopen(request)
            if 'Content-Length' in response.info():
                content_length = int(response.info()['Content-Length'])
            else:
                content_length = 0
    
            file_name += '.' + get_extension(url, response)
            full_path = os.path.join(path, file_name)
            log_utils.log('Downloading: %s -> %s' % (url, full_path), log_utils.LOGDEBUG)
    
            path = xbmc.makeLegalFilename(path)
            try:
                try: xbmcvfs.mkdirs(path)
                except: os.makedirs(path)
            except Exception as e:
                log_utils.log('Path Create Failed: %s (%s)' % (e, path), log_utils.LOGDEBUG)
    
            if not path.endswith(os.sep): path += os.sep
            if not xbmcvfs.exists(path):
                raise Exception(i18n('failed_create_dir'))
            
            file_desc = xbmcvfs.File(full_path, 'w')
            total_len = 0
            cancel = False
            while True:
                data = response.read(CHUNK_SIZE)
                if not data:
                    break
    
                if pd.is_canceled():
                    cancel = True
                    break
    
                total_len += len(data)
                if not file_desc.write(data):
                    raise Exception(i18n('failed_write_file'))
    
                percent_progress = (total_len) * 100 / content_length if content_length > 0 else 0
                log_utils.log('Position : %s / %s = %s%%' % (total_len, content_length, percent_progress), log_utils.LOGDEBUG)
                pd.update(percent_progress)
            
            file_desc.close()

        if not cancel:
            kodi.notify(msg=i18n('download_complete') % (file_name), duration=5000)
            log_utils.log('Download Complete: %s -> %s' % (url, full_path), log_utils.LOGDEBUG)

    except Exception as e:
        log_utils.log('Error (%s) during download: %s -> %s' % (str(e), url, file_name), log_utils.LOGERROR)
        kodi.notify(msg=i18n('download_error') % (str(e), file_name), duration=5000)

def get_extension(url, response):
    filename = url2name(url)
    if 'Content-Disposition' in response.info():
        cd_list = response.info()['Content-Disposition'].split('filename=')
        if len(cd_list) > 1:
            filename = cd_list[-1]
            if filename[0] == '"' or filename[0] == "'":
                filename = filename[1:-1]
    elif response.url != url:
        filename = url2name(response.url)
    ext = os.path.splitext(filename)[1][1:]
    if not ext: ext = DEFAULT_EXT
    return ext

def create_legal_filename(title, year):
    filename = title
    if year: filename += ' %s' % (year)
    filename = re.sub(r'(?!%s)[^\w\-_\.]', '.', filename)
    filename = re.sub('\.+', '.', filename)
    xbmc.makeLegalFilename(filename)
    return filename

def trailer_exists(path, file_name):
    for f in xbmcvfs.listdir(path)[1]:
        if f.startswith(file_name):
            return f

    return False

def url2name(url):
    return os.path.basename(urllib.unquote(urlparse.urlsplit(url)[2]))

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

def to_slug(username):
    username = username.strip()
    username = username.lower()
    username = re.sub('[^a-z0-9_]', '-', username)
    username = re.sub('--+', '-', username)
    return username

def iso_2_utc(iso_ts):
    if not iso_ts or iso_ts is None: return 0
    delim = -1
    if not iso_ts.endswith('Z'):
        delim = iso_ts.rfind('+')
        if delim == -1: delim = iso_ts.rfind('-')

    if delim > -1:
        ts = iso_ts[:delim]
        sign = iso_ts[delim]
        tz = iso_ts[delim + 1:]
    else:
        ts = iso_ts
        tz = None

    if ts.find('.') > -1:
        ts = ts[:ts.find('.')]

    try: d = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
    except TypeError: d = datetime.datetime(*(time.strptime(ts, '%Y-%m-%dT%H:%M:%S')[0:6]))

    dif = datetime.timedelta()
    if tz:
        hours, minutes = tz.split(':')
        hours = int(hours)
        minutes = int(minutes)
        if sign == '-':
            hours = -hours
            minutes = -minutes
        dif = datetime.timedelta(minutes=minutes, hours=hours)
    utc_dt = d - dif
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = utc_dt - epoch
    try: seconds = delta.total_seconds()  # works only on 2.7
    except: seconds = delta.seconds + delta.days * 24 * 3600  # close enough
    return seconds

def json_load_as_str(file_handle):
    return _byteify(json.load(file_handle, object_hook=_byteify), ignore_dicts=True)

def json_loads_as_str(json_text):
    return _byteify(json.loads(json_text, object_hook=_byteify), ignore_dicts=True)

def _byteify(data, ignore_dicts=False):
    if isinstance(data, unicode):
        return data.encode('utf-8')
    if isinstance(data, list):
        return [_byteify(item, ignore_dicts=True) for item in data]
    if isinstance(data, dict) and not ignore_dicts:
        return dict([(_byteify(key, ignore_dicts=True), _byteify(value, ignore_dicts=True)) for key, value in data.iteritems()])
    return data

def auth_trakt():
    start = time.time()
    use_https = kodi.get_setting('use_https') == 'true'
    trakt_timeout = int(kodi.get_setting('trakt_timeout'))
    trakt_api = Trakt_API(use_https=use_https, timeout=trakt_timeout)
    result = trakt_api.get_code()
    code, expires, interval = result['device_code'], result['expires_in'], result['interval']
    time_left = expires - int(time.time() - start)
    line1 = i18n('verification_url') % (result['verification_url'])
    line2 = i18n('prompt_code') % (result['user_code'])
    line3 = i18n('code_expires') % (time_left)
    with kodi.ProgressDialog(i18n('trakt_acct_auth'), line1=line1, line2=line2, line3=line3) as pd:
        pd.update(100)
        while time_left:
            for _ in range(INTERVALS):
                kodi.sleep(interval * 1000 / INTERVALS)
                if pd.is_canceled(): return

            try:
                result = trakt_api.get_device_token(code)
                break
            except urllib2.URLError as e:
                # authorization is pending; too fast
                if e.code in [400, 429]:
                    pass
                elif e.code == 418:
                    kodi.notify(msg=i18n('user_reject_auth'), duration=3000)
                    return
                elif e.code == 410:
                    break
                else:
                    raise
                
            time_left = expires - int(time.time() - start)
            progress = time_left * 100 / expires
            pd.update(progress, line3=i18n('code_expires') % (time_left))
        
    try:
        kodi.set_setting('trakt_oauth_token', result['access_token'])
        kodi.set_setting('trakt_refresh_token', result['refresh_token'])
        trakt_api = Trakt_API(result['access_token'], use_https=use_https, timeout=trakt_timeout)
        profile = trakt_api.get_user_profile(cached=False)
        kodi.set_setting('trakt_user', '%s (%s)' % (profile['username'], profile['name']))
        kodi.notify(msg=i18n('trakt_auth_complete'), duration=3000)
    except Exception as e:
        log_utils.log('Trakt Authorization Failed: %s' % (e), log_utils.LOGDEBUG)

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

def choose_list(username=None):
    trakt_api = Trakt_API(kodi.get_setting('trakt_oauth_token'), kodi.get_setting('use_https') == 'true', timeout=int(kodi.get_setting('trakt_timeout')))
    lists = trakt_api.get_lists(username)
    if username is None: lists.insert(0, {'name': 'watchlist', 'ids': {'slug': WATCHLIST_SLUG}})
    if lists:
        dialog = xbmcgui.Dialog()
        index = dialog.select(i18n('pick_a_list'), [list_data['name'] for list_data in lists])
        if index > -1:
            return (lists[index]['ids']['slug'], lists[index]['name'])
    else:
        kodi.notify(msg=i18n('no_lists_for_user') % (username), duration=5000)
