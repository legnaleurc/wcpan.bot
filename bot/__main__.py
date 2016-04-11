import sys
import functools
import re
import inspect
import random
import functools
import json

from tornado import ioloop, gen, options, web, log, httpserver, httpclient
from telezombie import api

from . import settings, db


class KelThuzad(api.TeleLich):

    def __init__(self, api_token):
        super(KelThuzad, self).__init__(api_token)

        self._text_handlers = []

    def add_text_handlers(self, handlers):
        self._text_handlers.extend(handlers)

    @property
    def text_handlers(self):
        return self._text_handlers


def command_filter(pattern):
    def real_decorator(fn):
        @functools.wraps(fn)
        def callee(*args, **kwargs):
            spec = inspect.getfullargspec(fn)
            if 'self' in spec.args:
                self = args[0]
                message = args[1]
            else:
                self = None
                message = args[0]

            m = re.match(pattern, message.text.strip())
            if not m:
                return None
            args = m.groups()

            if self:
                return fn(self, message, *args)
            else:
                return fn(message, *args)
        return callee
    return real_decorator


class UpdateHandler(api.TeleHookHandler):

    @gen.coroutine
    def on_text(self, message):
        id_ = message.message_id
        chat = message.chat
        text = message.text
        lich = self.settings['lich']
        for handler in lich.text_handlers:
            result = handler(message)
            if result:
                yield lich.send_message(chat.id_, result, reply_to_message_id=id_)
                break
        else:
            print(message.text)


class NOPHandler(web.RequestHandler):

    def get(self):
        print('??')

    def post(self):
        print(self.request.body)


class YPCHandler(object):

    def __init__(self):
        pass

    @command_filter(r'^/ypc(@\S+)?$')
    def ypc(self, message, *args, **kwargs):
        with db.Session() as session:
            murmur = session.query(db.Murmur).all()
            if not murmur:
                return None
            mm = random.choice(murmur)
            return mm.sentence

    @command_filter(r'^/ypc(@\S+)?\s+add\s+(.+)$')
    def ypc_add(self, message, *args, **kwargs):
        with db.Session() as session:
            mm = db.Murmur(sentence=args[1])
            session.add(mm)
            session.commit()
            return str(mm.id)

    @command_filter(r'^/ypc(@\S+)?\s+remove\s+(\d+)$')
    def ypc_remove(self, message, *args, **kwargs):
        try:
            with db.Session() as session:
                mm = session.query(db.Murmur).filter_by(id=int(args[1]))
                for m in mm:
                    session.delete(m)
                return args[1]
        except Exception:
            return None

    @command_filter(r'^/ypc(@\S+)?\s+list$')
    def ypc_list(self, message, *args, **kwargs):
        o = ['']
        with db.Session() as session:
            murmur = session.query(db.Murmur)
            for mm in murmur:
                o.append('{0}: {1}'.format(mm.id, mm.sentence))
        return '\n'.join(o)

    @command_filter(r'^/ypc(@\S+)?\s+help$')
    def ypc_help(self, message, *args, **kwargs):
        return '\n'.join((
            '',
            '/ypc',
            '/ypc add <sentence>',
            '/ypc remove <id>',
            '/ypc list',
            '/ypc help',
        ))



class MemeHandler(object):

    def __init__(self):
        pass

    @command_filter(r'^/meme(@\S+)?\s+(\S+)$')
    def get(self, message, *args, **kwargs):
        with db.Session() as session:
            mm = session.query(db.Meme).filter_by(name=args[1]).first()
            if not mm:
                return None
            return mm.url

    @command_filter(r'^/meme(@\S+)?\s+add\s+(\S+)\s+(\S+)$')
    def set_(self, message, *args, **kwargs):
        with db.Session() as session:
            mm = db.Meme(name=args[1], url=args[2])
            session.add(mm)
            session.commit()
            return mm.url

    @command_filter(r'^/meme(@\S+)?\s+remove\s+(\S+)$')
    def unset(self, message, *args, **kwargs):
        try:
            with db.Session() as session:
                mm = session.query(db.Meme).filter_by(name=args[1])
                for m in mm:
                    session.delete(m)
                return args[1]
        except Exception:
            return None

    @command_filter(r'^/meme(@\S+)?\s+list$')
    def list_(self, message, *args, **kwargs):
        o = ['']
        with db.Session() as session:
            meme = session.query(db.Meme)
            for mm in meme:
                o.append(mm.name)
        return '\n'.join(o)

    @command_filter(r'^/meme(@\S+)?\s+help$')
    def help(self, message, *args, **kwargs):
        return '\n'.join((
            '',
            '/meme <name>',
            '/meme add <name> <url>',
            '/meme remove <name>',
            '/meme list',
            '/meme help',
        ))


class TwitchPuller(object):

    def __init__(self, kel_thuzad, channel_name):
        self._kel_thuzad = kel_thuzad
        self._channel_name = channel_name
        self._is_online = False
        url = 'https://api.twitch.tv/kraken/streams/{0}'.format(self._channel_name)
        self._curl = httpclient.AsyncHTTPClient()
        self._request = httpclient.HTTPRequest(url, headers={
            'Accept': 'application/vnd.twitchtv.v3+json',
        })
        self._chat_id = -16028742
        self._line = (
            '我廢，我宅，我實況',
            '唔哦！好實況，不看嗎？',
            '牛魔王，跟上帝出來看娘子！',
            '玩遊戲就是要實況啊，不然要幹麻？',
            '你知道你媽在這裡開實況嗎？',
        )

    @gen.coroutine
    def __call__(self):
        try:
            data = yield self._curl.fetch(self._request)
            data = data.body.decode('utf-8')
            data = json.loads(data)
        except Exception as e:
            print(e)
            return

        if self._is_online:
            if data['stream'] is None:
                self._is_online = False
        else:
            if data['stream'] is not None:
                self._is_online = True
                line = random.choice(self._line)
                yield self._kel_thuzad.send_message(self._chat_id, '{0}\nhttp://www.twitch.tv/{1}'.format(line, self._channel_name))


@command_filter(r'^/help(@\S+)?$')
def help(message, *args, **kwargs):
    return '\n'.join((
        '',
        '/ypc',
        '/ypc add <sentence>',
        '/ypc remove <id>',
        '/ypc list',
        '/ypc help',
        '/meme <name>',
        '/meme add <name> <url>',
        '/meme remove <name>',
        '/meme list',
        '/meme help',
    ))


@gen.coroutine
def forever():
    api_token = options.options.api_token

    kel_thuzad = KelThuzad(api_token)
    ypc = YPCHandler()
    meme = MemeHandler()

    kel_thuzad.add_text_handlers([
        help,
        ypc.ypc,
        ypc.ypc_add,
        ypc.ypc_remove,
        ypc.ypc_list,
        ypc.ypc_help,
        meme.set_,
        meme.unset,
        meme.list_,
        meme.get,
        meme.help,
    ])

    yield kel_thuzad.poll()


@gen.coroutine
def setup():
    api_token = options.options.api_token
    dsn = options.options.database
    db.prepare(dsn)

    kel_thuzad = KelThuzad(api_token)
    ypc = YPCHandler()
    meme = MemeHandler()

    kel_thuzad.add_text_handlers([
        help,
        ypc.ypc,
        ypc.ypc_add,
        ypc.ypc_remove,
        ypc.ypc_list,
        meme.set_,
        meme.unset,
        meme.list_,
        meme.get,
    ])

    application = web.Application([
        (r'^/{0}$'.format(api_token), UpdateHandler),
        (r'.*', NOPHandler),
    ], lich=kel_thuzad)
    application.listen(8443)

    twitch_users = (
        'inker610566',
        'legnaleurc',
        'markseinn',
        'vaporting',
        'wonwon0102',
    )
    twitch_daemons = (TwitchPuller(kel_thuzad, _) for _ in twitch_users)
    twitch_daemons = (ioloop.PeriodicCallback(_, 5 * 60 * 1000) for _ in twitch_daemons)
    for daemon in twitch_daemons:
        daemon.start()

    yield kel_thuzad.listen('https://www.wcpan.me/bot/{0}'.format(api_token))


def parse_config(path):
    data = settings.load(path)
    options.options.api_token = data['api_token']
    options.options.database = data['database']


def main(args=None):
    if args is None:
        args = sys.argv

    log.enable_pretty_logging()
    options.define('config', default=None, type=str, help='config file path', metavar='telezombie.yaml', callback=parse_config)
    options.define('api_token', default=None, type=str, help='API token', metavar='<token>')
    options.define('database', default=None, type=str, help='database URI', metavar='<uri>')
    remains = options.parse_command_line(args)

    main_loop = ioloop.IOLoop.instance()

    main_loop.add_callback(setup)

    main_loop.start()
    main_loop.close()

    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
