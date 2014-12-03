###
# Copyright (c) 2014, sdmac
# All rights reserved.
###

import time
import requests

import supybot.dbi as dbi
import supybot.cdb as cdb
import supybot.conf as conf
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
from supybot.ircutils import mircColor as mircColor
import supybot.callbacks as callbacks


class BeerReviewDB(plugins.DbiChannelDB):
    class DB(dbi.DB):
        Mapping = 'cdb'
        class Record(dbi.Record):
            __fields__ = [
                    'beer_id',
                    'name',
                    'brewery',
                    'nick',
                    'date_added',
                    'votes',
                    'reviews',
                    ]

        def __init__(self, filename):
            self.db = cdb.open(filename + '.reviews', 'c')

        def _new_record(self, serialized):
            record = self.Record()
            record.deserialize(serialized)
            return record

        def update(self, beer_id, name, brewery, date, nick, review):
            if beer_id in self.db:
                existing_record = self._new_record(self.db[beer_id])
                existing_record.reviews.append(review)
                self.db[beer_id] = existing_record.serialize()
            else:
                new_record = self.Record(beer_id=beer_id, name=name,
                                         brewery=brewery, date_added=date,
                                         nick=nick, reviews=[review],
                                         votes=0)
                self.db[beer_id] = new_record.serialize()

        def update_votes(self, beer_id, votes):
            if beer_id in self.db:
                existing_record = self._new_record(self.db[beer_id])
                existing_record.votes = votes
                self.db[beer_id] = existing_record.serialize()
            else:
                raise KeyError, beer_id

        def get(self, beer_id):
            return self._new_record(self.db[beer_id])

        def get_all(self):
            records = {}
            for (beer_id, serialized_record) in self.db.iteritems():
                records[beer_id] = self._new_record(serialized_record)
            return records

        def flush(self):
            self.db.flush()

        def close(self):
            self.db.close()

class BeerTrackerDB(plugins.DbiChannelDB):
    class DB(dbi.DB):
        Mapping = 'cdb'
        class Record(dbi.Record):
            __fields__ = [
                    'beer_id',
                    'name',
                    'brewery',
                    'refs',
                    ]

        def __init__(self, filename):
            self.db = cdb.open(filename + '.tracker', 'c')

        def _new_record(self, serialized):
            record = self.Record()
            record.deserialize(serialized)
            return record

        def update(self, beer_id, name, brewery, nick, date):
            if beer_id in self.db:
                existing_record = self._new_record(self.db[beer_id])
                existing_record.refs.append((nick, date))
                self.db[beer_id] = existing_record.serialize()
            else:
                new_record = self.Record(beer_id=beer_id, name=name,
                                         brewery=brewery, refs=[(nick, date)])
                self.db[beer_id] = new_record.serialize()

        def get(self, beer_id):
            return self._new_record(self.db[beer_id])

        def get_all(self):
            records = {}
            for (beer_id, serialized_record) in self.db.iteritems():
                records[beer_id] = self._new_record(serialized_record)
            return records

        def flush(self):
            self.db.flush()

        def close(self):
            self.db.close()


class BeerMeHelper:
    @classmethod
    def _getBrewery(self, beer, color=None, num=1):
        if 'breweries' not in beer:
            return ""
        breweries = []
        for i in range(min(num, len(beer['breweries']))):
            brewery = beer['breweries'][i]
            name = mircColor(brewery['name'], color)
            if 'established' in brewery:
                est = mircColor(brewery['established'], color)
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
        return u"{0}".format(mircColor(cur, color))


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
            'category': (BeerMeHelper._getSimpleField,
                {'color': 'brown',
                    'path': ['style', 'category', 'name']}),
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
            'desc': (BeerMeHelper._getSimpleField,
                {'color': 'light grey',
                    'path': ['description']}),
            'brewery': (BeerMeHelper._getBrewery,
                {'color': 'dark blue',
                    'num': 3})
            }

    def __init__(self, irc):
        self.__parent = super(BeerMe, self)
        self.__parent.__init__(irc)
        self.review_db = plugins.DB('BeerMe', {'cdb': BeerReviewDB})()
        self.tracker_db = plugins.DB('BeerMe', {'cdb': BeerTrackerDB})()

    def listCommands(self):
        return self.__parent.listCommands(["random",
                                           "search",
                                           "describe",
                                           "review",
                                           "reviews",
                                           "top",
                                           "upvote",
                                           "downvote",
                                           "tracker"])

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

    def _track(self, channel, beer, nick):
        self.tracker_db.update(channel,
                               beer['id'],
                               beer['name'],
                               (beer['breweries'][0]['name']
                                   if ('breweries' in beer
                                           and 'name' in beer['breweries'][0])
                                   else ''),
                               nick,
                               time.strftime('%B %d, %Y %H:%M',
                                             time.localtime()))

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

    def _internal_search(self, text, maxNum, search_type):
        self.log.debug('Searching beers for %s (%d hits)..' % (text, maxNum))
        payload = {'key': self.registryValue('apiKey'),
                   'type': 'beer',
                   'withBreweries': 'Y',
                   'q': text}
        r = requests.get("%s/search" % self.baseUrl, params=payload)
        self.log.debug('Search URL=[%s]' % r.url)
        jr = r.json()
        hits = []
        reason = ''
        if 'data' in jr and jr['status'] == 'success':
            for beer in jr['data']:
                if (len(hits) + 1) > maxNum:
                    break
                if self._match(text, beer, search_type):
                    hits.append(beer)
            if len(hits) == 0:
                reason = 'Sorry bro, search results es no bueno'
        else:
            reason = 'You\'re searchin\' for sumthin\' that ain\'t there'
        return (hits, reason)

    def search(self, irc, msg, args, channel, text):
        """[beer | brewery] <query> [(<num_results>)]

        Search for beers matching <query>.
        Optionally specify 'beer' or 'brewery' first as search type.
        Optionally specify number of search results in parentheses.
        """
        maxNum = self.registryValue('search.limit')
        fields = self.registryValue('search.fields')
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
        (hits, no_hits_reason) = self._internal_search(text, maxNum, search_type)
        if len(hits) > 0:
            pretty_hits = [self._printFields(hit, fields) for hit in hits]
            self._track(channel, hits[0], msg.nick)
            irc.replies(pretty_hits, prefixNick=False)
        else:
            irc.reply(no_hits_reason)
    search = wrap(search, ['channel', 'text'])

    def describe(self, irc, msg, args, channel, text):
        """<beer_name> [(<field>,...)]

        Describe the beer in full.
        Optionally specify the output fields where each <field> is one of: 
        { brewery, style, category, abv, glass, description, desc }
        and fields must be specified as a comma-separated list in parens 
        e.g. 'Ruination IPA (style,abv,desc)'
        """
        (hits, no_hits_reason) = self._internal_search(text, 1, 'beer')
        if len(hits) > 0:
            fields = ['name', 'style', 'brewery', 'abv', 'glass', 'desc']
            for term in text.split():
                if term.startswith('(') and term.endswith(')'):
                    fields = ['name'] + term[1:-1].split(',')
            pretty_hits = [self._printFields(hit, fields) for hit in hits]
            self._track(channel, hits[0], msg.nick)
            irc.replies(pretty_hits, prefixNick=False)
        else:
            irc.reply(no_hits_reason)
    describe = wrap(describe, ['channel', 'text'])

    def tracker(self, irc, msg, args, channel):
        output = []
        freq_calculated = []
        records = self.tracker_db.get_all(channel)
        for (_, r) in records.iteritems():
            freq = len(r.refs)
            mentioners = set([ref[0] for ref in r.refs])
            freq_calculated.append((freq, mentioners, r))
        ranked_by_freq = sorted(freq_calculated, reverse=True)[0:10]
        for i, (freq, ments, r) in enumerate(ranked_by_freq, start=1):
            nicks = ', '.join([mircColor(m, 'blue') for m in ments])
            output.append((u" [{rank}] {name} ({brewery}) [{ms} {freq}] "
                            "[{mrs} {nicks}]"
                            .format(rank=mircColor(i, 'blue'),
                                    name=mircColor(r.name, 'orange'),
                                    brewery=mircColor(r.brewery, 'dark blue'),
                                    freq=mircColor(freq, 'green'),
                                    ms=mircColor('Mentions:', 'dark grey'),
                                    mrs=mircColor('Mentioners:', 'dark grey'),
                                    nicks=nicks)))
        irc.replies(output, prefixNick=False)
    tracker = wrap(tracker, ['channel'])

    def _show_review(self, irc, channel, beer_id=None, beer_name=None):
        try:
            if not beer_id:
                (beers, reason) = self._internal_search(beer_name, 1, 'beer')
                if len(beers) != 1:
                    irc.reply('Cannot find this one: %s' % reason)
                    return
                beer_id = beers[0]['id']
            entry = self.review_db.get(channel, beer_id)
            rating_sum = float(0)
            for review in entry.reviews:
                rating_sum = rating_sum + float(review['rating'])
            num_reviews = len(entry.reviews)
            rating_avg = rating_sum / num_reviews
            out = [(u"{0} ({1}) [Avg. {2}] [{3} vote{4}]"
                    .format(mircColor(entry.name, 'orange'),
                            mircColor(entry.brewery, 'dark blue'),
                            mircColor(rating_avg, 'green'),
                            mircColor(entry.votes, 'dark grey'),
                            's' if int(entry.votes) != 1 else ''))]
            for review in entry.reviews:
                r = (u" [{0}][{1}][{2}][{3}]"
                        .format(mircColor(review['date'], 'dark grey'),
                                mircColor(review['nick'], 'blue'),
                                mircColor(('{0:0.1f}'
                                           .format(float(review['rating']))),
                                           'green'),
                                mircColor(review['description'], 'light grey')))
                out.append(r)
            irc.replies(out, prefixNick=False)
        except KeyError:
            irc.reply('Cannot find a review for \'%s\'' % beer_name)

    def review(self, irc, msg, args, channel, text):
        components = text.split(';')
        if len(components) == 3:
            date = time.strftime('%B %d, %Y %H:%M', time.localtime())
            (beer_name, rating, desc) = tuple(components)
            (beers, reason) = self._internal_search(beer_name, 1, 'beer')
            if len(beers) == 1:
                beer = beers[0]
                review = {'rating': rating.strip(),
                          'description': desc.strip(),
                          'nick': msg.nick,
                          'date': date}
                brewery = ''
                if 'breweries' in beer and 'name' in beer['breweries'][0]:
                    brewery = beer['breweries'][0]['name']
                self.review_db.update(channel,
                                      beer['id'], beer['name'], brewery,
                                      date, msg.nick, review)
                self._show_review(irc, channel, beer_id=beer['id'])
            else:
                irc.reply('Cannot find this one: %s' % reason)
        else:
            irc.reply('Try again. And this time, think a little harder first.')
    review = wrap(review, ['channel', 'text'])

    def reviews(self, irc, msg, args, channel, text):
        self._show_review(irc, channel, beer_name=text)
    reviews = wrap(reviews, ['channel', 'text'])

    def top(self, irc, msg, args, channel):
        rating_calculated = []
        all_beers = self.review_db.get_all(channel)
        if len(all_beers) == 0:
            irc.reply('No reviewed beers!')
            return
        for (beer_id, record) in all_beers.iteritems():
            rating_sum = float(0)
            for review in record.reviews:
                rating_sum = rating_sum + float(review['rating'])
            num_reviews = len(record.reviews)
            rating_avg = rating_sum / num_reviews
            rating_calculated.append((rating_avg, num_reviews, record))
        output = []
        ranked_by_rating = sorted(rating_calculated, reverse=True)[0:10]
        l = [(len(r.name) + len(r.brewery)) for (_, _, r) in ranked_by_rating]
        max_len = sorted(l, reverse=True)[0] + 11
        for i, (avg, num, record) in enumerate(ranked_by_rating, start=1):
            beer_brewery = (u"{0} ({1})"
                            .format(mircColor(record.name, 'orange'),
                                    mircColor(record.brewery, 'dark blue')))
            output.append((u" [{rank}] {beer:{beer_width}} [{avg_str} {avg} "
                            "({num_reviews} review{rev_plural})] "
                            "[{num_votes} vote{vote_plural}]"
                            .format(rank=mircColor(i, 'blue'),
                                    beer=beer_brewery, beer_width=int(max_len),
                                    avg_str=mircColor('Avg.', 'dark grey'),
                                    avg=mircColor('{0:0.1f}'.format(avg),
                                                  'green'),
                                    num_reviews=mircColor(num, 'light grey'),
                                    rev_plural=('s' if num > 1 else ' '),
                                    num_votes=mircColor(record.votes,
                                                        'dark grey'),
                                    vote_plural=('s' if int(record.votes) != 1
                                                     else ''))))
        irc.replies(output, prefixNick=False)
    top = wrap(top, ['channel'])

    def _vote(self, irc, msg, args, channel, text, up_vote=True):
        try:
            (beers, reason) = self._internal_search(text, 1, 'beer')
            if len(beers) == 1:
                beer_id = beers[0]['id']
                entry = self.review_db.get(channel, beer_id)
                num_votes = ((entry.votes + 1) if up_vote
                             else ((entry.votes - 1) if entry.votes > 0 else 0))
                self.review_db.update_votes(channel, beer_id, num_votes)
                self._show_review(irc, channel, beer_id=beer_id)
            else:
                irc.reply('Cannot find this one: %s' % reason)
        except KeyError:
            irc.reply('There must be at least one review before voting')

    def upvote(self, irc, msg, args, channel, text):
        self._vote(irc, msg, args, channel, text, True)
    upvote = wrap(upvote, ['channel', 'text'])

    def downvote(self, irc, msg, args, channel, text):
        self._vote(irc, msg, args, channel, text, False)
    downvote = wrap(downvote, ['channel', 'text'])

    def beerme(self, irc, msg, args):
        self.random(irc, msg, args)
    beerme = wrap(beerme)


Class = BeerMe

