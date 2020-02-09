import os
import re
import requests
import pprint
import json
from pathlib import Path
import urllib.request
from urllib.parse import quote
import sys
import aiohttp
import asyncio
import errno
from unidecode import unidecode

# Queries
MAX = 500
BASE_URL = 'https://dragalialost.gamepedia.com/api.php?action=cargoquery&format=json&limit={}'.format(
    MAX
)

# regex stuff
alphafy_re = re.compile('[^a-zA-Z_]')

# static
pattern = {
    'adventurer': r'\d{6}_\d{2,3}_r0[345].png',
    'dragon': r'\d{6}_01.png',
    'weapon': r'\d{6}_01_\d{5}.png',
    'wyrmprint': r'\d{6}_0[12].png'
}

start = {
    'adventurer': '100001_01_r04.png',
    'dragon': '200010_01.png',
    'weapon': '301001_01_19901.png',
    'wyrmprint': '400001_01.png'
}

end = {
    'adventurer': '2',
    'dragon': '3',
    'weapon': '4',
    'wyrmprint': 'A'
}

save_dir = {
    'adventurer': 'character',
    'dragon': 'dragon',
    'weapon': 'weapon',
    'wyrmprint': 'amulet'
}

def snakey(name):
    return re.sub(r'[^0-9a-zA-Z ]', '', unidecode(name)).replace(' ', '_').replace('_amp', '_and')

def get_api_request(offset, **kwargs):
    q = '{}&offset={}'.format(BASE_URL, offset)
    for key, value in kwargs.items():
        q += '&{}={}'.format(key, quote(value))
    return q


def get_data(**kwargs):
    offset = 0
    data = []
    while offset % MAX == 0:
        url = get_api_request(offset, **kwargs)
        r = requests.get(url).json()
        try:
            if len(r['cargoquery']) == 0:
                break
            data += r['cargoquery']
            offset += len(r['cargoquery'])
        except:
            raise Exception(url)
    return data

def check_target_path(target):
    if not os.path.exists(os.path.dirname(target)):
        try:
            os.makedirs(os.path.dirname(target))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

@asyncio.coroutine
async def download(session, tbl, save_dir, k, v):
    try:
        fn = snakey(tbl[k]) + '.png'
        path = Path(__file__).resolve().parent / 'img/{}/{}'.format(save_dir, fn)
    except KeyError:
        if save_dir == 'amulet':
            try:
                fn = snakey(tbl[k.replace('_01', '_02')]) + '.png'
                path = Path(__file__).resolve().parent / 'img/{}/{}'.format(save_dir, fn)
            except KeyError:
                return
        else:
            return
    async with session.get(v) as resp:
        if resp.status == 200:
            check_target_path(path)
            with open(path, 'wb') as f:
                f.write(await resp.read())
                print('download image: {}'.format(fn))

def image_list(file_name):
    tbl = None
    if file_name == 'adventurer':
        tbl = {
            '{}_0{}_r0{}.png'.format(
                d['title']['Id'], int(d['title']['VariationId']), int(d['title']['Rarity'])
            ): d['title']['FullName']
            for d in get_data(tables='Adventurers', fields='Id,VariationId,FullName,Rarity')
        }
    elif file_name == 'dragon':
        welfare_Dragons = ['Story', 'High Dragon', 'Event Welfare', 'Void', 'Event Welfare, Zodiac']
        welfare_cond = 'NOT (' + ' OR '.join(['Availability="{}"'.format(w) for w in welfare_Dragons]) + ')'
        tbl = {
            '{}_{:02d}.png'.format(d['title']['BaseId'], int(d['title']['VariationId'])): d[
                'title'
            ]['FullName']
            for d in get_data(tables='Dragons', fields='BaseId,VariationId,FullName', where='Rarity>=5 AND '+welfare_cond)
        }
    elif file_name == 'wyrmprint':
        tbl = {
            '{}_02.png'.format(d['title']['BaseId']): d['title']['Name']
            for d in get_data(tables='Wyrmprints', fields='BaseId,Name')
        }
    elif file_name == 'weapon':
        availability_dict = {
            'High Dragon': 'HDT2',
            'Agito': 'Agito'
        }
        tbl = {
            '{}_01_{}.png'.format(d['title']['BaseId'], d['title']['FormId']): '{} {} {}'.format(
                availability_dict[d['title']['Availability']],
                d['title']['ElementalType'].lower(),
                d['title']['Type'].lower()
            )
            for d in get_data(tables='Weapons', fields='BaseId,FormId,Availability,ElementalType,Type', where='(Availability=\'High Dragon\' AND CraftNodeId >= 200) OR Availability=\'Agito\'')
        }

    download = {}
    aifrom = start[file_name]
    keep = True
    while keep:
        url = 'https://dragalialost.gamepedia.com/api.php?action=query&format=json&list=allimages&aifrom={}&ailimit=max'.format(
            aifrom
        )

        response = requests.get(url).json()
        try:
            data = response['query']['allimages']

            for i in data:
                name = i['name']
                if name[0] == end[file_name]:
                    keep = False
                    break
                r = re.search(pattern[file_name], name)
                if r:
                    download[name] = i['url']

            con = response.get('continue', None)
            if con and con.get('aicontinue', None):
                aifrom = con['aicontinue']
            else:
                keep = False
                break
        except:
            raise Exception
    return tbl, download

async def download_images(file_name):
    tbl, dl = image_list(file_name)
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[
            download(session, tbl, save_dir[file_name], k, v)
            for k, v in dl.items()
        ])

if __name__ == '__main__':
    if len(sys.argv) > 1:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(download_images(sys.argv[1]))
    else:
        for file_name in ('adventurer', 'dragon', 'weapon', 'wyrmprint'):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(download_images(file_name))
