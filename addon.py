# Builtins
import os
import sys
import time
import pickle
import urllib
from datetime import datetime
from urlparse import urlparse, parse_qs, parse_qsl

# Third party
import dateutil.parser
from dateutil import tz
import requests
import json
import m3u8
from PIL import Image

# XBMC
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon


__url__ = sys.argv[0]
__handle__ = int(sys.argv[1])
__args__ = parse_qs(sys.argv[2][1:])

# Load plugin settings
settings = xbmcaddon.Addon(id='plugin.video.rugbypass.nrl')
PROXY_REQUESTS = settings.getSetting('proxy')

PLUGIN_LOCATION = os.path.dirname(os.path.realpath(__file__))
COOKIE_FILE_LOCATION = os.path.join(PLUGIN_LOCATION, 'cookies.dat')
IMAGE_LOCATION = os.path.join(PLUGIN_LOCATION, 'resources', 'img')

DEFAULT_USER_AGENT = 'Safari/537.36 Mozilla/5.0 AppleWebKit/537.36 Chrome/31.0.1650.57'
ANDROID_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 6.0.1; ONE A2003 Build/MMB29M)'

BASE_URL = 'https://watch.rugbypass.com/'
CONTENT_LOC = 'http://smb.cdnllnwnl.neulion.com/u/mt1/csmrugby/thumbs'

PROXY_URL = 'http://proxy.bernex.net'

# Create session
s = requests.Session()


def show_notification(msg, ms=5000):
    """Displays a popup notification message using Kodi's builtin Notification function

    :param msg: Message to display
    :param ms: Time to display message in milliseconds
    """
    xbmc.executebuiltin('Notification(%s, %s, %d)' % ('Rugbypass', msg, ms))


def proxy_request(url, session=None, headers={}, data=None):
    if data:
        url += '?' + urllib.urlencode(data)

    if not session:
        session = requests

    r = session.post(PROXY_URL + '/index.php',
                      headers=headers,
                      data={'q': url,
                            'hl[include_form]': 'on',
                            'hl[remove_scripts]': 'on',
                            'hl[accept_cookies]': 'on',
                            'hl[show_images]': 'on',
                            'hl[show_referer]': 'on',
                            'hl[base64_encode]': 'on',
                            'hl[strip_meta]': 'on',
                            'hl[session_cookies]': 'on',
                            })
    return r


def authenticate(email, password):
    # Authenticate with server
    # Android login
    '''
        devicetypes:
        '6': 'iphone',
        '7': 'ipad',
        '8': 'android_phone',
        '13': 'android_pad',
        '14':'kindle',
        '138':'google_tv',
        '139':'apple_tv',
        '142':'fire_tv'
    '''
    request_headers = {'User-Agent': ANDROID_USER_AGENT,
                       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    form_data = {'password': password,
                 'username': email,
                 'deviceid': 'b27cb67d',
                 'devicetype': '8',
                 'format': 'json'}
    r = proxy_request(BASE_URL + '/secure/authenticate', session=s, headers=request_headers, data=form_data)
    js = json.loads(r.text)
    if js['code'] == 'loginsuccess':
        return True

    return False


def fetch_games(lid):
    request_headers = {'User-Agent': ANDROID_USER_AGENT,
                       'X-Requested-With': 'XMLHttpRequest'}
    form_data = {'format': 'json',
                 'lid': lid,
                 '_': int(time.time())}
    r = proxy_request(BASE_URL + '/scoreboard', session=s, headers=request_headers, data=form_data)
    js = json.loads(r.text)
    return js['games']


def generate_thumbnail(filepath, home_code, away_code):
    img1 = Image.open(os.path.join(IMAGE_LOCATION, '{0}_el.png'.format(home_code)))
    img2 = Image.open(os.path.join(IMAGE_LOCATION, '{0}_el.png'.format(away_code)))
    thumb = Image.new('RGB', (img1.size[0] * 2, img1.size[1]), (255, 255, 255))
    thumb.paste(img1, (0, 0))
    thumb.paste(img2, (img1.size[0], 0))
    thumb.save(filepath, 'png', optimize=True)


def get_thumbnail(home_code, away_code):
    thumb_path = os.path.join(IMAGE_LOCATION, 'generated', '{0}v{1}.png'.format(home_code, away_code))
    if not os.path.exists(thumb_path):
        try:
            generate_thumbnail(thumb_path, home_code, away_code)
        except IOError:
            return None

    return thumb_path


def list_event_categories():
    listing = []

    # List any games that are currently live
    nrl_games = fetch_games('nrl')
    stateoforigin_games = fetch_games('stateoforigin')
    games = nrl_games + stateoforigin_games
    for game in games:
        if game['gameState'] == 1:
            item_name = '[LIVE] {0} vs {1}'.format(game['homeTeam']['name'], game['awayTeam']['name'])
            list_item = xbmcgui.ListItem(item_name)
            list_item.setProperty('IsPlayable', 'true')
            list_item.setProperty('IsFolder', 'false')

            thumb_path = get_thumbnail(game['homeTeam']['code'], game['awayTeam']['code'])
            list_item.setArt({'thumb': thumb_path})

            url = '{0}?action=play&game_id={1}&game_state={2}'.format(__url__, game['id'], game['gameState'])
            listing.append((url, list_item, False))

    # Create menu option for upcoming events
    list_item = xbmcgui.ListItem('Upcoming Events')
    list_item.setInfo('video', {'title': 'Upcoming Events'})
    list_item.setProperty('IsFolder', 'true')
    url = '{0}?action=list_games&future=1'.format(__url__)
    listing.append((url, list_item, True))

    # Create menu option for past events
    list_item = xbmcgui.ListItem('Past Events')
    list_item.setInfo('video', {'title': 'Past Events'})
    list_item.setProperty('IsFolder', 'true')
    url = '{0}?action=list_games&future=0'.format(__url__)
    listing.append((url, list_item, True))

    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    xbmcplugin.endOfDirectory(__handle__)


def list_games(future=False):
    nrl_games = fetch_games('nrl')
    stateoforigin_games = fetch_games('stateoforigin')
    games = nrl_games + stateoforigin_games

    listing = []
    if future:
        # Upcoming games
        games = [g for g in games if g['gameState'] == 0]
        games = sorted(games, key=lambda k: k['date'])

        for game in games:
            item_name = '{0} vs {1} [{2}]'.format(game['homeTeam']['name'],
                                                  game['awayTeam']['name'],
                                                  format_date(game['dateTimeGMT']))
            list_item = xbmcgui.ListItem(item_name)
            list_item.setProperty('IsPlayable', 'false')

            thumb_path = get_thumbnail(game['homeTeam']['code'], game['awayTeam']['code'])
            list_item.setArt({'thumb': thumb_path})

            url = '{0}?action=notify_start&start_time={1}'.format(__url__, game['dateTimeGMT'])
            listing.append((url, list_item, False))
    else:
        # Past games
        games = [g for g in games if g['gameState'] == 3]
        games = sorted(games, key=lambda k: k['date'], reverse=True)

        for game in games:
            item_name = '{0} vs {1} [{2}]'.format(game['homeTeam']['name'],
                                                  game['awayTeam']['name'],
                                                  format_date(game['dateTimeGMT']))
            list_item = xbmcgui.ListItem(item_name)
            list_item.setProperty('IsPlayable', 'true')

            thumb_path = get_thumbnail(game['homeTeam']['code'], game['awayTeam']['code'])
            list_item.setArt({'thumb': thumb_path})

            url = '{0}?action=play&game_id={1}&game_state={2}'.format(__url__, game['id'], game['gameState'])
            listing.append((url, list_item, False))

    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    xbmcplugin.endOfDirectory(__handle__)


def play_stream(game_id, game_state):
    # Get game link
    form_data = {'gt': '1',
                 'type': 'game',
                 'id': game_id,
                 'nt': '1',
                 'format': 'json',
                 'gs': game_state}
    request_headers = {'User-Agent': ANDROID_USER_AGENT,
                       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    r = proxy_request(BASE_URL + '/service/publishpoint', session=s, data=form_data, headers=request_headers)

    # Check if request failed due to expired session
    if r.status_code == 400:
        # Delete expired session cookie
        os.remove(COOKIE_FILE_LOCATION)

        # Try and log in again
        email = settings.getSetting('email')
        password = settings.getSetting('password')
        authenticated = authenticate(email, password)

        if not authenticated:
            show_notification('Problem logging in. Check email/password in plugin settings')
            return

        # Make request again
        r = proxy_request(BASE_URL + '/service/publishpoint', session=s, data=form_data, headers=request_headers)

    js = json.loads(r.text)
    link = js['path']

    # Get "best" stream
    request_headers = {'User-Agent': DEFAULT_USER_AGENT}
    r = s.get(link, headers=request_headers)
    m3u8_obj = m3u8.loads(r.text)
    stream_path = max(m3u8_obj.playlists, key=lambda p: p.stream_info.bandwidth)
    o = urlparse(link)
    stream_url = o.scheme + '://' + o.netloc + os.path.split(o.path)[0] + '/' + stream_path.uri

    # Upgrade to 720p stream >:)
    stream_url = stream_url.replace('3000', '4500')

    # Add cookie data to stream url
    cookies = s.cookies.get_dict()
    cookie_str = ''.join(['%s=%s; ' % (k, v) for k, v in cookies.iteritems()])[:-2]
    kodi_params = {'User-Agent': DEFAULT_USER_AGENT,
                   'Cookie': cookie_str}
    stream_url += '|' + urllib.urlencode(kodi_params)

    item = xbmcgui.ListItem(path=stream_url)
    xbmcplugin.setResolvedUrl(__handle__, True, listitem=item)


def notify_start(start_time):
    game_time = dateutil.parser.parse(start_time)
    game_time = game_time.replace(tzinfo=tz.tzutc())
    dt = game_time - datetime.utcnow()

    days = dt.days
    hours, remainder = divmod(dt.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    show_notification('Game starts in\n%d days %d hours %d minutes' % (days, hours, minutes))


def format_date(date_str):
    game_time = dateutil.parser.parse(date_str)
    game_time = game_time.replace(tzinfo=tz.tzutc())
    game_time = game_time.astimezone(tz.tzlocal())
    return game_time.strftime('%I:%M%p, %d %B %Y')


def main(paramstring):
    """Routing function for plugin navigation

    :param paramstring: Parameter string in the form of a URL query
    """
    params = dict(parse_qsl(paramstring[1:]))

    # Load existing session or authenticate
    try:
        with open(COOKIE_FILE_LOCATION) as f:
            cookies = pickle.load(f)
            s.cookies = cookies
    except IOError:
        email = settings.getSetting('email')
        password = settings.getSetting('password')
        authenticated = authenticate(email, password)

        if not authenticated:
            show_notification('Problem logging in. Check email/password in plugin settings')
            return

    if params:
        action = params.pop('action')

        if action == 'play':
            play_stream(params['game_id'], params['game_state'])
        elif action == 'notify_start':
            notify_start(params['start_time'])
        elif action == 'list_games':
            list_games(bool(int(params['future'])))
    else:
        list_event_categories()

    # Write session cookies out to file
    with open(COOKIE_FILE_LOCATION, 'w') as f:
        pickle.dump(s.cookies, f)


if __name__ == '__main__':
    main(sys.argv[2])


