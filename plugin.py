###
# Copyright (c) 2014, sdmac
# All rights reserved.
###

import requests

import supybot.conf as conf
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks


class BeerMeHelper:
    @classmethod
    def _getBrewery(self, beer, color=None, num=1):
        if 'breweries' not in beer:
            return ""
        breweries = []
        for i in range(min(num, len(beer['breweries']))):
            brewery = beer['breweries'][i]
            name = ircutils.mircColor(brewery['name'], color)
            if 'established' in brewery:
                est = ircutils.mircColor(brewery['established'], color)
                breweries.append(u"{0}, est. {1}".format(name, est))
            else:
                breweries.append(u"{0}".format(name))
        return ' | '.join(breweries)

    @classmethod
    def _getSimpleField(self, beer, **kwargs):
        cur = beer
        for elem in kwargs['path']:
            if elem not in cur:
                return ""
            cur = cur[elem]
        color = kwargs['color'] if 'color' in kwargs else None
        if 'prefix' in kwargs:
            cur = kwargs['prefix'] + cur
        if 'postfix' in kwargs:
            cur = cur + kwargs['postfix']
        return u"{0}".format(ircutils.mircColor(cur, color))


class BeerMe(callbacks.Plugin):
    """
    Water and tea ain't got nothin' on me
    """
    baseUrl = 'http://api.brewerydb.com/v2'

    fieldDispatch = {
            'name': (BeerMeHelper._getSimpleField,
                {'color': 'orange',
                    'path': ['name'],
                    'bracketize': False}),
            'style': (BeerMeHelper._getSimpleField,
                {'color': 'brown',
                    'path': ['style', 'name']}),
            'abv': (BeerMeHelper._getSimpleField,
                {'color': 'dark grey',
                    'path': ['abv'],
                    'postfix': '% ABV'}),
            'glass': (BeerMeHelper._getSimpleField,
                {'color': 'purple',
                    'path': ['glass', 'name']}),
            'description': (BeerMeHelper._getSimpleField,
                {'color': 'light grey',
                    'path': ['description']}),
            'brewery': (BeerMeHelper._getBrewery,
                {'color': 'dark blue',
                    'num': 3})
            }

    def __init__(self, irc):
        self.__parent = super(BeerMe, self)
        self.__parent.__init__(irc)

    def listCommands(self):
        return self.__parent.listCommands(["random", "search"])

    def _printFields(self, beer, fields):
        outFields = []
        for field in fields:
            if field in self.fieldDispatch:
                (dispatch, kwargs) = self.fieldDispatch[field]
                out = dispatch(beer, **kwargs)
                if out:
                    if 'bracketize' in kwargs and kwargs['bracketize'] is False:
                        outFields.append(out)
                    else:
                        outFields.append(u"[{0}]".format(out))
        return ' '.join(outFields)

    def random(self, irc, msg, args, text):
        """[<field>,...]
        
        where <field> is one of
        { style, brewery, abv, glass, description, desc }
        and fields must be specified as a comma-separated list
        e.g. 'random style,desc,abv'
        """
        self.log.debug('Fetching random beer..')
        payload = {'key': self.registryValue('apiKey')}
        fields = ['name']
        if text:
            fields.extend(text.split(','))
            if 'brew' in fields or 'brewery' in fields:
                payload['withBreweries'] = 'Y'
        r = requests.get("%s/beer/random" % self.baseUrl, params=payload)
        jr = r.json()
        if 'data' in jr and jr['status'] == 'success':
            output = self._printFields(jr['data'], fields)
            irc.reply(output)
        else:
            irc.reply('The random beers only start after the first seven')
    random = wrap(random, [optional('text')])

    def _match(self, text, beer, search_type):
        match = False
        for term in text.split():
            if search_type == 'beer':
                if term.lower() in beer['name'].lower():
                    match = True
            elif search_type == 'brewery':
                for brewery in beer['breweries']:
                    if term.lower() in brewery['name'].lower():
                        match = True
        return match

    def search(self, irc, msg, args, text):
        """[beer | brewery] <query> [(<num_results>)]

        Search for beers matching <query>.
        Optionally specify 'beer' or 'brewery' first as search type.
        Optionally specify number of search results in parentheses.
        """
        maxNum = self.registryValue('search.limit')
        search_type = 'beer'
        terms = text.split()
        if terms[0] == 'beer' or terms[0] == 'beers':
            search_type = 'beer'
            terms = terms[1:]
        elif terms[0] == 'brewery' or terms[0] == 'breweries':
            search_type = 'brewery'
            terms = terms[1:]
        for term in terms:
            if term.startswith('(') and term.endswith(')'):
                try:
                    maxNum = int(term[1:-1])
                    if maxNum > 10:
                        maxNum = 10
                        irc.reply('Nice try. Hope you can live with 10,'
                                  ' Epicurus.')
                except ValueError:
                    irc.reply('Only integers in parentheses next time!')
                text = text.replace(term, '')
        self.log.debug('Searching beers for %s (%d hits)..' % (text, maxNum))
        payload = {'key': self.registryValue('apiKey'),
                   'type': 'beer',
                   'withBreweries': 'Y',
                   'q': text}
        r = requests.get("%s/search" % self.baseUrl, params=payload)
        self.log.debug('Search URL=[%s]' % r.url)
        jr = r.json()
        hits = []
        fields = self.registryValue('search.fields')
        if 'data' in jr and jr['status'] == 'success':
            for idx, beer in enumerate(jr['data'], start=1):
                if idx > maxNum:
                    break
                if self._match(text, beer, search_type):
                    hits.append(self._printFields(beer, fields))
            if len(hits) > 0:
                irc.replies(hits, prefixNick=False)
            else:
                irc.reply('Sorry bro, search results es no bueno')
        else:
            irc.reply('You\'re searchin\' for sumthin\' that ain\'t there')
    search = wrap(search, ['text'])

    def beerme(self, irc, msg, args):
        self.random(irc, msg, args)
    beerme = wrap(beerme)


Class = BeerMe

