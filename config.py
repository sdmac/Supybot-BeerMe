###
# Copyright (c) 2014, Sean Mac
# All rights reserved.
###

import supybot.conf as conf
import supybot.registry as registry

def configure(advanced):
    # This will be called by supybot to configure this module.  advanced is
    # a bool that specifies whether the user identified himself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('BeerMe', True)


BeerMe = conf.registerPlugin('BeerMe')
conf.registerGlobalValue(BeerMe, 'apiKey',
    registry.String('a2cac2b9b32c8724e39964d6f84ba644',
    """The BreweryDB API Key."""))
conf.registerGroup(BeerMe, 'search')
conf.registerGlobalValue(BeerMe.search, 'limit',
    registry.PositiveInteger(5, """Maximum number of search results to
    display."""))
conf.registerGlobalValue(BeerMe.search, 'fields',
    registry.CommaSeparatedListOfStrings(['name', 'style', 'brewery', 'abv'],
    """Which fields to display for each search result hit."""))

