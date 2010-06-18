from __future__ import with_statement

import os, sys, getpass, random, StringIO, email, re

import imaplib

def chunker(seq, size):
    return (seq[pos:pos + size] for pos in xrange(0, len(seq), size))

class IMAP_connection(object):
    """Used like:

       with config.IMAP_connection() as im:
           do_stuff(im)
    """
    def __init__(self, server, port, user, passw, ssl):
        self.server = server
        self.port   = port
        self.user   = user
        self.passw  = passw
        self.ssl    = ssl

    def __enter__(self):
        if self.ssl:
            im = imaplib.IMAP4_SSL(self.server, self.port)
        else:
            im = imaplib.IMAP4(self.server, self.port)

        im.login(self.user, self.passw)

        self.im = im

        return im
        
    def __exit__(self, type, value, traceback):
        self.im.logout()

def im_resp(x):
    typ, resp = x
    if typ != 'OK':
        sys.stderr.write("%s is not OK\n" % typ)
        
        assert typ == 'OK'
    return resp

def each_imap_message(im, imap_folder_name, flags = None):
    "a simple way to iterate over all imap_message"
    with config.IMAP_connection() as im:
        im_resp(im.select(imap_folder_name, readonly = True))

        msg_nums = im_resp(im.search(None, flags or 'ALL'))
        msg_nums = msg_nums[0].split()

        for nums in chunker(msg_nums, 100):
            nums_str = ','.join(nums)
            msgs = im_resp(im.fetch(nums_str, '(RFC822)'))

            for x in range(0,len(msgs),2):
                envstart = msgs[x][0]
                text     = msgs[x][1]
                envend   = msgs[x+1]
                
                msg_num = envstart.split(' ')[0]

                msg = email.message_from_string(text)

                yield msg_num, msg

class ConfigException(Exception): pass

class ConfigOption(object):
    def __init__(self, default, required=False):
        self.default = default
        self.required = required
    def valid(self, val):
        return True
    def conv(self, val):
        return val
    def validate(self, val):
        try:
            val = self.conv(val)
        except ValueError:
            raise ConfigException, "%s: %s is not valid" % (self.__class__.__name__, val)
        if not self.valid(val):
            raise ConfigException, "%s: %s is not valid" % (self.__class__.__name__, val)
        return val

class StringConfigOption(ConfigOption):
    def __init__(self, default, regex = '.*', **kw):
        self.regex = re.compile(regex)
        ConfigOption.__init__(self, default, **kw)
    def valid(self, val):
        return self.regex.match(val)

class IntConfigOption(ConfigOption):
    def __init__(self, default, min = None, max = None, **kw):
        self.min = min
        self.max = max
        ConfigOption.__init__(self, default, **kw)
    def conv(self, val):
        return int(val)
    def valid(self, val):
        if self.min is not None and val < self.min:
            return False
        if self.max is not None and val > self.max:
            return False
        return True

class BooleanConfigOption(ConfigOption):
    def conv(self, val):
        return val.lower() == 'true'

class Config(object):
    _options = dict(
        imap_server   = StringConfigOption(None, '^[a-zA-Z0-9.-]+$',required=True),
        imap_port     = IntConfigOption(143, min = 1, max = 65535,required=True),
        imap_user     = StringConfigOption(None,required=True),
        imap_password = StringConfigOption(None,required=True),
        imap_ssl      = BooleanConfigOption(None)
        )

    def parse(self, text):
        lines = [ line for line in text.split('\n')
                  if not line.startswith('#') ]
        for line in lines:
            if line.strip():
                line = line.split('=')
                assert len(line) == 2
                opt = line[0].strip()
                val = ''.join(line[1:]).strip()

                if opt in self._options:
                    setattr(self, opt, self._options[opt].validate(val))
                else:
                    sys.stderr.write("ignoring unknown option %s"
                                     % opt)

        for name, opt in self._options.iteritems():
            if not hasattr(self, name):
                if opt.required:
                    raise "Need to set %s" % name
                else:
                    setattr(self,name,opt.default)

    def __init__(self, **kw):
        for key,val in kw.iteritems():
            setattr(self, key, val)

    def __repr__(self):
        opts = ', '.join(('%s = %r'
                          % (key, getattr(self, key))
                          for key in self._defaults.keys()
                          if key != 'imap_password'))
        return ("%s(%s)" % (self.__class__.__name__, opts))

    def get_password(self):
        if self.imap_password:
            return self.imap_password

        self.imap_password = getpass.getpass()
        return self.imap_password        

    def IMAP_connection(self):
        return IMAP_connection(self.imap_server, self.imap_port,
                               self.imap_user, self.get_password(),
                               self.imap_ssl)

drymaildir  = "%s/.drymail" % os.environ['HOME']
drymailrc   = "%s/config" % drymaildir
dbs_dir     = "%s/dbs" % drymaildir
actions_dir = "%s/actions" % drymaildir

# create required default directories
for dir in drymaildir, dbs_dir, actions_dir:
    if not os.path.isdir(dir):
        print "Creating %s" % dir
        os.mkdir(dir)

config = Config()
try:
    with open(drymailrc) as f:
        config.parse(f.read())
except IOError,e:
    sys.stderr.write("Couldn't read config %s\n" % e)
    config = Config()


class Category(object):
    @classmethod
    def all(cls):
        return [ Category('.'.join(os.path.basename(x).split('.')[:-1]))
                 for x in os.listdir(dbs_dir) ]

    @classmethod
    def create(cls, name):
        Crm114.create(name)
        return cls(name = name)

    @staticmethod
    def exists(name):
        fname = '%s/%s.css' % (dbs_dir, name)
        return (os.path.exists(fname)
                and os.path.isfile(fname))

    @classmethod
    def get(cls, name):
        if not cls.exists(name):
            return cls.create(name)

        return cls(name = name)

    @classmethod
    def classify(cls, data, dbs = None):
        if dbs is None:
            dbs = cls.all()

        db, prob = Crm114.classify([ d.name for d in dbs ], data)
        return cls(name = db), prob

    @staticmethod
    def delete(name):
        os.unlink("%s/%s.css" % (dbs_dir, name))

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "%s(name = %r)" % (self.__class__.__name__, self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return self.name.hash

    def train(self, data):
        return Crm114.train(self.name, data)
    
    def untrain(self, data):
        return Crm114.untrain(self.name, data)

    def action(self):
        fname = '%s/%s' % (actions_dir, self.name)
        return Action(fname)

class Action(object):
    def __init__(self, fname):
        self.fname = fname

    def __repr__(self):
        return "%s(fname = %r)" % (self.__class__.__name__, self.fname)

    def execute(self, msg):
        # msg =:= email.Message()

        # make sure that the child script will have access to our
        # modules
        mydir = os.path.dirname(__file__)
        if 'PYTHONPATH' not in os.environ:
            os.environ['PYTHONPATH'] = mydir
        elif mydir not in os.environ['PYTHONPATH']:
            os.environ['PYTHONPATH'] += ":" + mydir

        stdin, stdout = os.popen2(self.fname)

        stdin.write(str(msg))
        stdin.close()

        print stdout.read()

    def exists(self):
        return os.path.exists(self.fname) and os.path.isfile(self.fname)

class Crm114(object):
    classifier = "osb microgroom"
    tokeniser  = "[[:graph:]]+"

    @classmethod
    def classify(cls, dbs, data):
        s = """isolate (:stats:) /init/;
               classify <%s> ( %s ) (:stats:) /%s/;
               match (:: :match: :prob:) [:stats:] /Best match to file #[0-9]+ \\((.*?).css\\) prob: ([.0-9]+)/;
               output /:*:match: :*:prob:\\n/;
            """ % (cls.classifier,
                   ' '.join( ('%s.css' % c) for 
                             c in dbs),
                   cls.tokeniser)

        outp = cls._program(s, data)
        outp_db, outp_prob = [ x.strip() for x in outp.split(' ') ]
        return outp_db, float(outp_prob)

    @classmethod
    def _train(cls, db, data, learner_extra = ''):
        # create it if it doesn't exist
        s = """learn <%s %s> (%s.css) /%s/;
               output /OK\\n/;
            """ % (cls.classifier, learner_extra, db, cls.tokeniser)

        resp = cls._program(s, data)
        if resp != 'OK\n':
            sys.stderr.write("%s is not OK\n" % resp)
            assert 'OK\n' == cls._program(s, data)

    @classmethod
    def create(cls, db):
        assert db is not None and db != ''
        os.system("cssutil -r -q  %s/%s.css"
                  % (dbs_dir, db))
    
    @classmethod
    def train(cls, db, data):
        return cls._train(db, data)

    @classmethod
    def untrain(cls, db, data):
        return cls._train(db, data, learner_extra = 'refute')

    @classmethod
    def _program(cls, prog, input):
        stdin, stdout = os.popen2("crm -u '%s' '-{ %s }' "
                                  % (dbs_dir, prog))

        stdin.write(input)
        stdin.close()

        output = stdout.read()

        stdout.close()

        return output

