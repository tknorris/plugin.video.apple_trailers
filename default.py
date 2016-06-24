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
from lib.url_dispatcher import URL_Dispatcher
from lib import kodi
from lib import trailer_scraper
from lib import log_utils
from lib import utils

def __enum(**enums):
    return type('Enum', (), enums)

MODES = __enum(
    MAIN='main', TRAILERS='trailers'
)

url_dispatcher = URL_Dispatcher()

@url_dispatcher.register(MODES.MAIN)
def main_menu():
    scraper = trailer_scraper.Scraper()
    try: limit = int(kodi.get_setting('limit'))
    except: limit = 0
    for movie in scraper.get_all_movies(limit):
        label = movie['title']
        if 'year' in movie and movie['year']: label += ' (%s)' % (movie['year'])
        liz = utils.make_list_item(label, movie)
        liz.setInfo('video', movie)
        queries = {'mode': MODES.TRAILERS, 'movie_id': movie['movie_id'], 'location': movie['location']}
        liz_url = kodi.get_plugin_url(queries)
        xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=True)
    utils.set_view('movies')
    kodi.end_of_directory(cache_to_disc=False)

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
