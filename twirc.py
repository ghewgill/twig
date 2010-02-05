import base64
import codecs
import simplejson as json
import re
import select
import socket
import urllib

Config = json.load(open("twirc.config"))

class TwitterStream(object):
    def __init__(self, sender):
        self.sender = sender
        self.octets = 0
        self.data = ""
        friends = json.load(urllib.urlopen("http://twitter.com/statuses/friends/ghewgill.json"))
        ids = [x['id'] for x in friends]
        self.sock = socket.socket()
        self.sock.connect(("stream.twitter.com", 80))
        #self.sock.send("GET /1/statuses/sample.json?delimited=length HTTP/1.0\r\n"+
        self.sock.send(("GET /1/statuses/filter.json?delimited=length&follow=%s HTTP/1.0\r\n"+
                        "Host: stream.twitter.com\r\n"+
                        "Authorization: Basic %s\r\n\r\n") % (
                        ",".join(map(str, ids)),
                        base64.b64encode(Config['name'] + ":" + Config['password']),
                    ))
        s = ""
        while True:
            s += self.sock.recv(1)
            if s.endswith("\r\n\r\n"):
                print s
                break
    def socket(self):
        return self.sock
    def handle(self):
        data = self.sock.recv(2048)
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
                        nick = str(st['user']['screen_name'])
                        self.sender("%s!%s@%s" % (nick, nick, "twirc"), codecs.utf_8_encode(st['text'])[0])
                    self.octets = 0
                    self.data = ""

class IrcClient(object):
    def __init__(self, server, s):
        self.server = server
        self.sock = s
        self.data = ""
        self.nick = None
        self.user = None
    def socket(self):
        return self.sock
    def handle(self):
        data = self.sock.recv(1024)
        for c in data:
            if c == "\r":
                continue
            if c == "\n":
                if ' ' in self.data:
                    command, params = self.data.split(" ", 1)
                else:
                    command = self.data
                    params = ""
                handler = getattr(self, "handle_" + command.lower(), None)
                if handler is not None:
                    response = handler(params)
                    if response:
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
        return ":%s %s %s :twirc" % ("twirc", "001", self.nick)
    def handle_user(self, params):
        self.user, mode, _, realname = params.split(" ", 3)
        return ":%s JOIN :%s" % (self.ident(), "#twirc")
    def handle_ping(self, params):
        return ":%s PONG :%s" % ("twirc", "twirc")
    def ident(self):
        return "%s!%s@%s" % (self.nick, self.user, "twirc")
    def privmsg(self, user, channel, msg):
        self.sock.send(":%s PRIVMSG %s %s\r\n" % (user, channel, msg))

class IrcServer(object):
    def __init__(self):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 6969))
        self.sock.listen(5)
        self.clients = []
    def socket(self):
        return self.sock
    def handle(self):
        t, a = self.sock.accept()
        print "Client connect", a
        self.clients.append(IrcClient(self, t))
    def privmsg(self, user, channel, msg):
        for x in self.clients:
            x.privmsg(user, channel, msg)

server = IrcServer()
stream = TwitterStream(lambda user, msg: server.privmsg(user, "#twirc", msg))

while True:
    a = [stream, server] + server.clients
    r, w, e = select.select([x.socket() for x in a], [], [])
    for x in r:
        for s in a:
            if x is s.socket():
                s.handle()
