#!/usr/local/bin/python
from __future__ import with_statement

import sys

from utils import config, each_imap_message, Category

def main(category_name, imap_folder_name):
    cat = Category.get(category_name)

    with config.IMAP_connection() as im:
        for msg_num, msg in each_imap_message(im, imap_folder_name):
            print ('Training "%s"'
                   % msg.get('Subject', '(none)').replace('\n',' '))
            cat.train(str(msg))

    return 'not implemented'

def usage():
    return "drymail-train $category $imap_folder"

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.stderr.write("%s\n" % usage())
    else:
        main(sys.argv[1], sys.argv[2])
