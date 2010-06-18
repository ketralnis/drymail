#!/usr/local/bin/python
from __future__ import with_statement

import sys

from utils import config, each_imap_message, Category

def main(imap_folder_name):
    "Mostly copy-pasted form drymail-train; probably need to be cleaned up"

    with config.IMAP_connection() as im:
        for msg_num, msg in each_imap_message(im,imap_folder_name):
            cat, prob = Category.classify(str(msg))

            print "%s(%f): %s" % (cat.name, prob,
                                  msg.get('Subject', '(none)').replace('\n',' '))

def usage():
    print "drymail-quickrun $imap_folder"

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.stderr.write("%s\n" % usage())
    else:
        main(sys.argv[1])
