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
import sys
import xbmcplugin
import xbmcgui
from lib import kodi
from lib.kodi import i18n
from lib import trailer_scraper
from lib import log_utils
from lib import utils
from lib.url_dispatcher import URL_Dispatcher
from lib.trailer_scraper import BROWSER_UA

def __enum(**enums):
    return type('Enum', (), enums)

MODES = __enum(
    MAIN='main', TRAILERS='trailers', PLAY_TRAILER='play_trailer', DOWNLOAD_TRAILER='download_trailer', AUTH_TRAKT='auth_trakt'
)

url_dispatcher = URL_Dispatcher()
scraper = trailer_scraper.Scraper()
trailer_sources = [scraper.get_all_movies, scraper.get_exclusive_movies, scraper.get_most_popular_movies, scraper.get_most_recent_movies]

CP_ADD_URL = 'plugin://plugin.video.couchpotato_manager/movies/add?title=%s'
TRAKT_ADD_URL = 'plugin://plugin.video.trakt_list_manager/movies/add?title=%s'

@url_dispatcher.register(MODES.MAIN)
def main_menu():
    try: limit = int(kodi.get_setting('limit'))
    except: limit = 0
    try: source = int(kodi.get_setting('source'))
    except: source = 0
    for movie in trailer_sources[source](limit):
        label = movie['title']
        liz = utils.make_list_item(label, movie)
        liz.setInfo('video', movie)
        
        menu_items = []
        runstring = 'RunPlugin(%s)' % (CP_ADD_URL % (movie['title']))
        menu_items.append((i18n('add_to_cp'), runstring),)
        runstring = 'RunPlugin(%s)' % (TRAKT_ADD_URL % (movie['title']))
        menu_items.append((i18n('add_to_trakt'), runstring),)
        liz.addContextMenuItems(menu_items, replaceItems=True)
        
        queries = {'mode': MODES.TRAILERS, 'movie_id': movie['movie_id'], 'location': movie['location'], 'poster': movie.get('poster', ''), 'fanart': movie.get('fanart', '')}
        liz_url = kodi.get_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=True)
    utils.set_view('movies', set_sort=True)
    kodi.end_of_directory(cache_to_disc=False)

@url_dispatcher.register(MODES.TRAILERS, ['location'], ['movie_id', 'poster', 'fanart'])
def show_trailers(location, movie_id='', poster='', fanart=''):
    for trailer in scraper.get_trailers(location, movie_id):
        trailer['fanart'] = fanart
        trailer['poster'] = poster
        stream_url = utils.get_best_stream(trailer['streams'], 'stream')
        download_url = utils.get_best_stream(trailer['streams'], 'download')
        label = trailer['title']
        liz = utils.make_list_item(label, trailer)
        liz.setProperty('isPlayable', 'true')
        del trailer['streams']
        liz.setInfo('video', trailer)

        menu_items = []
        queries = {'mode': MODES.DOWNLOAD_TRAILER, 'trailer_url': download_url, 'title': trailer['title'], 'year': trailer.get('year', '')}
        runstring = 'RunPlugin(%s)' % kodi.get_plugin_url(queries)
        menu_items.append(('Download Trailer', runstring),)
        liz.addContextMenuItems(menu_items, replaceItems=True)
        
        queries = {'mode': MODES.PLAY_TRAILER, 'trailer_url': stream_url, 'thumb': trailer.get('thumb', '')}
        liz_url = kodi.get_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)
    utils.set_view('movies', set_view=True)
    kodi.end_of_directory()

@url_dispatcher.register(MODES.PLAY_TRAILER, ['trailer_url'], ['thumb'])
def play_trailer(trailer_url, thumb=''):
    trailer_url += '|User-Agent=%s' % (BROWSER_UA)
    listitem = xbmcgui.ListItem(path=trailer_url, iconImage=thumb, thumbnailImage=thumb)
    try: listitem.setArt({'thumb': thumb})
    except: pass
    listitem.setPath(trailer_url)
    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)
    
@url_dispatcher.register(MODES.DOWNLOAD_TRAILER, ['trailer_url', 'title'], ['year'])
def download_trailer(trailer_url, title, year=''):
    path = kodi.get_setting('download_path')
    while not path:
        ret = xbmcgui.Dialog().yesno(kodi.get_name(), i18n('no_download_path'), nolabel=i18n('cancel'), yeslabel=i18n('set_it_now'))
        if not ret:
            return

        kodi.show_settings()
        path = kodi.get_setting('download_path')
        
    file_name = utils.create_legal_filename(title, year)
    utils.download_media(trailer_url, path, file_name)

@url_dispatcher.register(MODES.AUTH_TRAKT)
def auth_trakt():
    utils.auth_trakt()
 
def main(argv=None):
    if sys.argv: argv = sys.argv
    queries = kodi.parse_query(sys.argv[2])
    log_utils.log('Version: |%s| Queries: |%s|' % (kodi.get_version(), queries), log_utils.LOGNOTICE)
    log_utils.log('Args: |%s|' % (argv), log_utils.LOGNOTICE)

    # don't process params that don't match our url exactly. (e.g. plugin://plugin.video.1channel/extrafanart)
    plugin_url = 'plugin://%s/' % (kodi.get_id())
    if argv[0] != plugin_url:
        return

    mode = queries.get('mode', None)
    url_dispatcher.dispatch(mode, queries)

if __name__ == '__main__':
    sys.exit(main())
