#!/usr/bin/env python
#
# twig.py - TWitter Irc Gateways
# Greg Hewgill <greg@hewgill.com> http://hewgill.com
#
# LICENSE
#
# This software is provided 'as-is', without any express or implied
# warranty.  In no event will the author be held liable for any damages
# arising from the use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
#
# Copyright (c) 2010 Greg Hewgill

import base64
import codecs
import re
import select
import socket
import sys
import time
import urllib

try:
    import json
except ImportError:
    import simplejson as json

DEBUG = False

def load_json(uri):
    tries = 0
    while tries < 5:
        try:
            return json.load(urllib.urlopen(uri))
        except Exception, x:
            print "load_json:", x
        tries += 1
    print >>sys.stderr, "Fatal: could not load <%s>" % uri
    sys.exit(1)

Config = json.load(open("twig.config"))

class TwitterStream(object):
    def __init__(self, sender):
        self.sender = sender
        self.octets = 0
        self.data = ""
        self.connect()
    def connect(self):
        print "Connecting to stream.twitter.com"
        self.sock = socket.socket()
        while True:
            try:
                self.sock.connect(("stream.twitter.com", 80))
                break
            except Exception, e:
                print e
                time.sleep(5)
        #self.sock.send("GET /1/statuses/sample.json?delimited=length HTTP/1.0\r\n"+
        self.sock.send(("GET /1/statuses/filter.json?delimited=length&follow=%s HTTP/1.0\r\n"+
                        "Host: stream.twitter.com\r\n"+
                        "Authorization: Basic %s\r\n\r\n") % (
                        ",".join(map(str, ids)),
                        base64.b64encode(Config['name'] + ":" + Config['password']),
                    ))
        header = ""
        while True:
            s = self.sock.recv(1)
            if len(s) == 0:
                self.sock.close()
                self.sock = None
                break
            header += s
            if header.endswith("\r\n\r\n"):
                print header
                break
        self.lasttime = time.time()
        self.maxinterval = 30
    def socket(self):
        return self.sock
    def tick(self):
        if time.time() - self.lasttime > self.maxinterval * 2:
            self.sock.close()
            self.sock = None
            self.connect()
    def handle(self):
        if self.sock is None:
            self.connect()
            return
        data = self.sock.recv(2048)
        if len(data) == 0:
            print "Disconnected"
            self.sock.close()
            self.sock = None
            self.connect()
        self.maxinterval = max(self.maxinterval, time.time() - self.lasttime)
        self.lasttime = time.time()
        i = 0
        while i < len(data):
            if self.octets == 0:
                if data[i] in ("\r","\n"):
                    if len(self.data) > 0:
                        self.octets = int(self.data)
                        self.data = ""
                else:
                    self.data += data[i]
                i += 1
            else:
                use = min(len(data) - i, self.octets - len(self.data))
                self.data += data[i:i+use]
                i += use
                if len(self.data) == self.octets:
                    st = json.loads(self.data)
                    if 'user' in st:
                        if st['user']['id'] in ids:
                            self.sender(st['user']['screen_name'], st['text'])
                    self.octets = 0
                    self.data = ""

class IrcClient(object):
    def __init__(self, server, s):
        self.server = server
        self.sock = s
        self.data = ""
        self.nick = None
        self.user = None
        self.lastactivity = time.time()
        self.pingsent = False
    def socket(self):
        return self.sock
    def tick(self):
        silence = time.time() - self.lastactivity
        if silence > 300:
            self.sock.close()
            self.server.remove(self)
        elif silence > 150 and not self.pingsent:
            self.sock.send("PING :twig\r\n")
            self.pingsent = True
    def handle(self):
        self.lastactivity = time.time()
        try:
            data = self.sock.recv(1024)
        except socket.error:
            self.sock.close()
            self.server.remove(self)
            return
        if len(data) == 0:
            self.sock.close()
            self.server.remove(self)
            return
        for c in data:
            if c == "\r":
                continue
            if c == "\n":
                if DEBUG: print "<-", self.data
                if ' ' in self.data:
                    command, params = self.data.split(" ", 1)
                else:
                    command = self.data
                    params = ""
                handler = getattr(self, "handle_" + command.lower(), None)
                if handler is not None:
                    response = handler(params)
                    if response:
                        if DEBUG: print "->", response
                        self.sock.send(response + "\r\n")
                else:
                    print "unknown command:", self.data
                self.data = ""
            else:
                self.data += c
    def handle_nick(self, params):
        nick = params
        if not re.match(r"[a-zA-Z0-9\-\[\]'`^{}_]+$", nick):
            print "bad nick", nick
            sys.exit(1)
        self.nick = nick
        return ":%s %s %s :twig" % ("twig", "001", self.nick)
    def handle_user(self, params):
        self.user, mode, _, realname = params.split(" ", 3)
        return ":%s JOIN :%s" % (self.ident(), "#twig")
    def handle_ping(self, params):
        return ":%s PONG %s" % ("twig", params)
    def handle_pong(self, params):
        self.pingsent = False
    def handle_quit(self, params):
        self.sock.close()
        self.server.remove(self)
    def handle_who(self, params):
        for f in friends:
            self.sock.send(":twig 352 %s #twig %s twig twig %s H :1 %s\r\n" % (self.nick, f['screen_name'], f['screen_name'], f['name']))
        self.sock.send(":twig 315 %s :End of /WHO list" % self.nick)
    def handle_whois(self, params):
        userinfo = load_json("http://twitter.com/users/show/%s.json" % params)
        if 'error' in userinfo:
            return "User %s %s.\r\n" % (params, userinfo['error'])
        else:
            self.sock.send("%s [%s]\r\n" % (userinfo['screen_name'], userinfo['id']))
            for key, descr in (("name", "Real Name"),
                               ("verified", "Verified"),
                               ("location", "Location"),
                               ("time_zone", "Time Zone"),
                               ("description", "Description"),
                               ("url", "Home Page"),
                               ("followers_count", "Followers"),
                               ("friends_count", "Following"),
                               ("favourites_count", "Favourites")):
                if key in userinfo:
                    self.sock.send(" %-12s : %s\r\n" % (descr, userinfo[key]))
            if 'status' in userinfo and 'created_at' in userinfo['status']:
                self.sock.send(" %-12s : %s\r\n" % ("Idle Since",userinfo['status']['created_at']))
        return "End of WHOIS"
    def ident(self):
        return "%s!%s@%s" % (self.nick, self.user, "twig")
    def privmsg(self, user, channel, msg):
        self.sock.send(":%s PRIVMSG %s %s\r\n" % (user, channel, msg))

class IrcServer(object):
    def __init__(self):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", Config['port']))
        self.sock.listen(5)
        self.clients = []
    def socket(self):
        return self.sock
    def tick(self):
        pass
    def handle(self):
        t, a = self.sock.accept()
        print "Client connect", a
        self.clients.append(IrcClient(self, t))
    def privmsg(self, user, channel, msg):
        for x in self.clients:
            x.privmsg(user, channel, msg)
    def remove(self, client):
        self.clients.remove(client)

seen = set()
def sender(server, user, msg):
    key = user + msg
    if key not in seen and (not msg.startswith("@") or msg.startswith("@"+Config['name']+" ")):
        seen.add(key)
        server.privmsg("%s!%s@%s" % (str(user), str(user), "twig"), "#twig", codecs.utf_8_encode(msg)[0])
    else:
        print "dropped: %s <%s> %s" % (time.strftime("%H:%M"), str(user), repr(msg))

me = load_json("http://twitter.com/users/show/%s.json" % Config['name'])
friends = load_json("http://twitter.com/statuses/friends/%s.json" % Config['name'])
ids = [me['id']] + [x['id'] for x in friends]

server = IrcServer()
stream = TwitterStream(lambda user, msg: sender(server, user, msg))

while True:
    a = [stream, server] + server.clients
    r, w, e = select.select([x.socket() for x in a], [], [], 1)
    for x in r:
        for s in a:
            if x is s.socket():
                s.handle()
    for s in a:
        s.tick()
