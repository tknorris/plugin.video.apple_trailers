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
import xbmcgui
import xbmc
import xbmcplugin
import xbmcvfs
import kodi
import log_utils
from kodi import i18n
from trailer_scraper import BROWSER_UA

def __enum(**enums):
    return type('Enum', (), enums)

Q_ORDER = {'sd': 1, 'hd720': 2, 'hd1080': 3}
PROGRESS = __enum(OFF=0, WINDOW=1, BACKGROUND=2)
CHUNK_SIZE = 512 * 1024
DEFAULT_EXT = '.mpg'

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

def set_view(content, set_sort=False):
    # set content type so library shows more views and info
    if content:
        kodi.set_content(content)

    view = kodi.get_setting('%s_view' % (content))
    if view and view != '0':
        log_utils.log('Setting View to %s (%s)' % (view, content), log_utils.LOGDEBUG)
        xbmc.executebuiltin('Container.SetViewMode(%s)' % (view))

    # set sort methods - probably we don't need all of them
    if set_sort:
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_GENRE)

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
    
            file_name = re.sub('.m4v$', get_extension(url, response), file_name)
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
    ext = os.path.splitext(filename)[1]
    if not ext: ext = DEFAULT_EXT
    return ext

def create_legal_filename(title, year):
    if year: title = '%s (%s)' % (title, year)
    filename = '%s.m4v' % title
    filename = re.sub(r'(?!%s)[^\w\-_\.]', '.', filename)
    filename = re.sub('\.+', '.', filename)
    xbmc.makeLegalFilename(filename)
    return filename


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
