# twig - Twitter Irc Gateway

Twig is an IRC server that reads from the Twitter Streaming API and forwards
new tweets to an IRC channel. It is designed to be used by a single user only.

## Requirements

Twig is written in Python and has no external dependencies other than a JSON
library.  In Python 2.6 and later, a JSON library already available, but for
Python 2.4 or 2.5 you may have to install
[simplejson](http://code.google.com/p/simplejson/).

## Configuration

A `twig.config.sample` sample configuration file is provided. Copy this to
`twig.config` and edit as needed. The "port" value is the local IRC server
listening port.

## Running

Start `twig.py` and wait for it to connect to Twitter and print an HTTP server
response message.  Then, connect to the local IRC server using your IRC client,
for example in irssi:

    /connect localhost 6969

You will be force-joined to the `#twig` channel (the only channel on the
server) and will start receiving tweets from the people you follow.

## Bugs

- Doesn't echo your own tweets to the channel.
- Twitter stream server disconnections may not be handled gracefully.
- Client disconnections are probably equally ungraceful.
- Error handling is terse and often fatal.
