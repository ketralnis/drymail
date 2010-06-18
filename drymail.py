#!/usr/local/bin/python
from __future__ import with_statement

from utils import config, Category, each_imap_message, im_resp

import sys, re, os, stat, StringIO
import email, email.generator
from distutils.util import split_quoted
from cmd import Cmd
import readline

def category_name(fn):
    def ret(self, cat, *a, **kw):
        if not cat and self.current_category:
            cat = self.current_category
            return fn(self, cat, *a, **kw)
        elif cat and Category.exists(cat):
            cat = Category.get(cat)
            return fn(self, cat, *a, **kw)            
        elif cat and not Category.exists(cat):
            print "category %s not found. try 'categories'?" % cat
        else:
            print "must specify a category. try 'categories'?"
    ret.__doc__ = fn.__doc__
    return ret

def folder_name(fn):
    def ret(self, folder, *a, **kw):
        if not folder:
            print "must specify a folder. try 'lsub'"
        elif folder not in self._lsub():
            print "can't find folder \"%s\". try 'lsub'" % folder
        else:
            return fn(self, folder, *a, **kw)
    ret.__doc__ = fn.__doc__
    return ret


def current_message(fn):
    def ret(self, *a, **kw):
        if not self.current_message:
            print "there is no current message. try 'reload'?"
        else:
            return fn(self, *a, **kw)
    ret.__doc__ = fn.__doc__
    return ret

class DrymailProcessor(Cmd):
    def __init__(self, imap_connection, imap_folder):
        self.im                    = imap_connection
        self.imap_folder           = imap_folder

        # self.messages =:= [ (msg_num, email.Message()) ]
        self.messages              = []
        self.current_message       = None
        self.current_message_index = None
        self.current_category      = None
        self.current_probability   = None

        self.colours = True

        self._reload()

        if self.messages:
            print
            self.do_messages(None)
            self.do_show(None)
            self._classify()

        return Cmd.__init__(self, completekey='tab')

    def emptyline(self):
        return

    @property
    def prompt(self):
        ret = []

        ret.append('drymail')
        if self.current_message is not None:
            ret.append("#%s" % self.messages[self.current_message_index][0])

            subj = self.current_message.get('subject', '(no subject)')
            subj_cutoff = 30
            ret.append('"'
                       + subj[:subj_cutoff]
                       + ('...' if len(subj) > subj_cutoff else '')
                       + '"')
        if self.current_category is not None:
            ret.append("{%s}" % self.current_category.name)
        if self.current_probability is not None:
            ret.append("%.2f%%" % (self.current_probability*100))

        if self.colours:
            ret.insert(0, bcolours.OKBLUE)
            ret.append(bcolours.ENDC)

        return "<%s> " % ' '.join(ret)

    def _complete_categories(self, text, line, begidx, endidx):
        return [ x.name for x in Category.all()
                 if x.name.startswith(text) ]
    def _complete_folders(self, text, line, bedidx, endidx):
        return [ x for x in self._lsub()
                 if x.startswith(text) ]

    def do_messages(self, noargs):
        """print the messages that we currently know about"""
        if not self.messages:
            print "No messages"
            return

        for i, (msg_num, msg) in enumerate(self.messages):
            print ("%s %s: <%s> -- %s "
                   % ('*' if i == self.current_message_index else ' ',
                      msg_num,
                      msg.get("from", "(no from)"),
                      msg.get("subject", "(no subject)")))

    def do_select(self, msg_num):
        """select a given message from the message list by number"""
        self._select_num(msg_num)
        self.do_show(None)

    numbery = re.compile('^[0-9]+$')
    def do_reload(self, noargs):
        "reload from imap"
        self._reload()

        if self.messages:
            self.do_messages(None)
                          
    @current_message
    def do_show(self, noargs):
        """print the current message in a friendly format"""
        for h in ['from', 'to', 'date', 'subject']:
            if h in self.current_message:
                print '%s: %s' % (h, self.current_message[h])
        print
        strio = StringIO.StringIO()
        email.generator.DecodedGenerator(strio).flatten(self.current_message)
        print strio.getvalue()

    @current_message
    def do_showcomplete(self, noargs):
        """print the entire mail messages, headers and all"""
        print str(self.current_message)

    @current_message
    def do_next(self, noargs):
        "skip the current message, leaving it as unread"
        if self.current_message_index == len(self.messages) - 1:
            self._select_idx(0)
        else:
            self._select_idx(self.current_message_index + 1)
        self.do_show(None)
            
    @current_message
    def do_prev(self, noargs):
        "go to the previous message, leaving the current one unread"
        if self.current_message_index == 0:
            self._select_idx(len(self.messages)-1)
        else:
            self._select_idx(self.current_message_index - 1)
        self.do_show(None)

    @category_name
    def do_editaction(self, cat):
        """create a new action, opening a text editor in $EDITOR or
        vi"""
        fname = cat.action().fname # this may not yet exist

        if 'VISUAL' in os.environ:
            editor = os.environ['VISUAL']
        elif 'EDITOR' in os.environ:
            editor = os.environ['EDITOR']
        else:
            editor = 'vi'

        os.system("%s %s" % (editor, fname))

        if os.path.isfile(fname):
            mode = os.stat(fname)[0]
            os.chmod(fname, mode | stat.S_IXUSR)
        else:
            print 'no action created'
    complete_editaction = _complete_categories

    @current_message
    def do_markread(self, noargs):
        "mark the current message as 'read' and move on to the next message"
        self._markread()

    @current_message
    @folder_name
    def do_move(self,new_folder):
        return self._copymove(new_folder,True)
    complete_move = _complete_folders

    @current_message
    @folder_name
    def do_copy(self,new_folder):
        return self._copymove(new_folder,False)
    complete_copy = _complete_folders

    def do_lsub(self,noargs):
        for x in self._lsub():
            print x

    validfolder_expr = '^[a-z0-9-]+$'
    validfolder = re.compile(validcat_expr)
    def do_newfolder(self, folder_name):
        if not self.valid_folder.match(folder_name):
            print ("I'm not very adventurous, I'll only let you create folders named \"%s\""
                   % validfolder_expr)
            return

        im_resp(self.im.create(folder_name))
        im_resp(self.im.subscribe(folder_name))
        self._lsub_cache = None

    def do_subscribefolder(self, folder_name):
        if folder_name in self.lsub():
            print "already subscribed. maybe 'reload' and/or 'lsub'?"
            return

        im_resp(self.im.subscribe(folder_name))
        if self.im.select(folder_name,readonly=True)[0] != 'OK':
            print "I subscribed, but I can't select it. You might want to unsubscribe"

    @folder_name
    def do_unsubscribefolder(self, folder):
        if folder_name not in self.lsub():
            print "not subscribed. maybe 'reload' and/or 'lsub'?"
            return

        im_resp(self.im.unsubscribe(folder))
        self._lsub_cache = None
        
    complete_unsubscribefolder = _complete_folders

    @current_message
    @category_name
    def do_action(self, cat):
        """execute the action for this message as it was categorised,
        mark it as read, and move on to the next message"""
        if not cat.action().exists():
            print ("there's no defined action for \"%s\". try 'editaction %s'"
                   % (cat.name,cat.name))
            return

        action = cat.action()
        action.execute(self.current_message)

        self._markread()
    complete_action = _complete_categories

    def do_actions(self, noargs):
        if not Category.all():
            print "no categories"
            return

        count = 0
        for x in Category.all():
            if x.action().exists():
                count += 1
                print x.name

        if not count:
            print 'no actions defined'
            
    validcat_expr = '^[a-z0-9-]+$'
    validcat = re.compile(validcat_expr)
    def do_newcategory(self, cat):
        "create a new category"
        if not self.validcat.match(cat):
            print "invalid category name. must match %s" % validcat_expr
            return

        newcat = Category.create(cat)
        print (('Created "%s". Note that this new category is empty,'
                +'and will need to be trained')
               % newcat.name)

    def do_categories(self, noargs):
        """just return the list of currently known categories"""
        for x in Category.all():
            print x.name

    @current_message
    @category_name
    def do_train(self, cat):
        """indicate that the current message was mis-classified, so
        retrain it with the given category"""
        cat.train(str(self.current_message))
        self.current_category = cat
        self.current_probability = None
    complete_train = _complete_categories

    @current_message
    @category_name
    def do_untrain(self, cat):
        """this message has previously been trained for some category
        (defaulting to the current one), and needs to be untrained"""
        cat.untrain(str(self.current_message))

        self._classify()

    @current_message
    @category_name
    def do_supertrain(self, cat):
        """train the current message on the given category until the
        classifier says that's what it is"""
        train_count = 0
        while True:
            train_count += 1

            (newcat, prob) = Category.classify(str(self.current_message))
            if newcat == cat:
                break

            print "Training %d... (%s %.2f%%)" % (train_count, newcat.name, prob*100)
            cat.train(str(self.current_message))
        self._classify()
    complete_supertrain = _complete_categories

    @current_message
    def do_reclassify(self, noargs):
        """throw away what we currently know about the current message
        and try to classify it again"""
        self._classify()

    def do_EOF(self, args):
        print
        print "G'bye now"
        sys.exit(0)

    def _classify(self):
        self.current_category = self.current_probability = None

        if not Category.all():
            print "Can't classify because I have no categories"
            return

        if not self.current_message:
            return

        cat, prob = Category.classify(str(self.current_message))

        self.current_category = cat
        self.current_probability = prob

        return self.current_category

    def _select_num(self, num):
        return self._select_idx(self._index_of(num))
                           
    def _select_idx(self, idx):
        if idx < 0 or idx > len(self.messages) - 1:
            print "I don't know that number. try 'messages'?"
            return

        self.current_message_index = idx
        self.current_message = self.messages[idx][1]

        self._classify()

    def _index_of(self, msg_num):
        for i, (num, msg) in enumerate(self.messages):
            if msg_num == num:
                return i
        print "I couln't find #%s" % msg_num
        

    def _reload(self):
        numbery = re.compile('^[0-9]+$')
        self.current_message_index = None
        self.current_message = None
        self.current_probability = None
        self.current_category = None

        def msgs_cmp(a,b):
            if isinstance(a[0], str) and self.numbery.match(a[0]):
                a = int(a[0]), a[1]
            if isinstance(b[0], str) and self.numbery.match(b[0]):
                b = int(b[0]), b[1]
            return cmp(a,b)

        self.messages = []
        for msg_num, msg in sorted(each_imap_message(self.im, self.imap_folder, flags = '(UNSEEN)'),
                                   cmp = msgs_cmp):
            self.messages.append((msg_num, msg))

        if self.messages:
            self._select_idx(0)

        self._lsub_cache = None

    def _markread(self):
        """
        mark the current messages as 'read', and try to move on to the
        logically next message
        """
        # if we can, try to gracefully move on to the next message
        # after we're done
        next_msg_num = self._find_next_msg_num()

        self._set_flag('\\Seen')
        self._reload()

        # if we were able to find what would normally be the next
        # message number, let's now try to load it up
        if next_msg_num:
            self._try_select_msg_num(next_msg_num)
        if self.messages:
            self.do_messages(None)
            self.do_show(None)

    def _set_flag(self, flag):
        im_resp(im.select(self.imap_folder, readonly = False))
        im_resp(im.store(self.messages[self.current_message_index][0], "+FLAGS", flag))
        # go back to readonly mode
        im_resp(im.select(self.imap_folder, readonly = True))

    def _find_next_msg_num(self):
        next_msg_num = None
        if len(self.messages) > 1:
            if self.current_message_index == len(self.messages) - 1:
                next_msg_num = self.messages[0][0]
            else:
                next_msg_num = self.messages[self.current_message_index+1][0]
        return next_msg_num

    def _try_select_msg_num(self, msg_num):
        after_next_msg_idx = self._index_of(msg_num)
        if after_next_msg_idx:
            self._select_idx(after_next_msg_idx)

    mailbox_list_re = re.compile(r'\((?P<attributes>.*?)\) ' +
                                 r'(?P<hierarchy_delimiter>"."|NIL) ' +
                                 r'"(?P<name>.*?)"')
    def _lsub(self):
        if self._lsub_cache is not None:
            return self._lsub_cache

        # im.lsub() returns a relatively raw response like
        # ['(\Nochildren \Seen \Bacon) "/" "INBOX"',
        #  '() "/" "lists/reddit-dev_googlegroups_com"',
        #  '() "/" "lists/commits.couchdb.apache.org"' ]
        folders_descr = im_resp(im.lsub())
        folders = []
        for x in folders_descr:
            
        folders_descr = [ split_quoted(x)
                          for x in folders_descr ]
        # we're going to force the use of / as a separator, even if
        # the server disagrees
        folders = [ '/'.join(x[2].split(x[1]))
                    for x in folders_descr ]

        self._lsub_cache = folders
        return self._lsub_cache

    def _copymove(self, new_folder, delete):
        if new_folder not in self._lsub():
            print "I can't find \"%s\" on the remote side" % newfolder
            return

        next_msg_num = self._find_next_msg_num()

        im_resp.copy(self.messages[self.current_message_index][0], new_folder)

        if delete:
            self._set_flag('\\Deleted')
            self._reload()
            self._try_select_msg_num(next_msg_num)

            if self.messages:
                self.do_messages(None)
                self.do_show(None)

class bcolours:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def usage():
    return "drymail [ $imap_folder ]"

if __name__ == '__main__':
    if len(sys.argv) in (1,2):
        folder = (sys.argv[1]
                  if len(sys.argv) == 2
                  else 'INBOX')
        with config.IMAP_connection() as im:
            DrymailProcessor(im, folder).cmdloop()
    else:
        print usage()


