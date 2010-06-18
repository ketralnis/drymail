import email, sys, os, StringIO

def open_mailapp_template(templ):
    def esc(s):
        return s.replace('\\',"\\\\").replace('"','\\"')

    msg = email.message_from_string(sys.stdin.read())
    to_addr = msg.get('reply-to', msg.get('from'))
    old_subject = msg.get('subject', "(no subject)")
    new_subject = "re: %s" % old_subject

    strio = StringIO.StringIO()
    email.generator.DecodedGenerator(strio).flatten(msg)
    oldbody = strio.getvalue()

    body = \
"""%s

-----------
Subject: %s
From: %s

%s""" % (templ, to_addr, old_subject, old_body)

    ascript ="""
tell application "Mail"
	set theMessage to make new outgoing message with properties {visible:true, subject:"%s", content:"%s"}
	tell theMessage
		make new to recipient at end of to recipients with properties {address:"%s"}
	end tell
	
	activate
end tell""" % (esc(new_subject), esc(body), esc(to_addr))

    stdin = os.popen("osascript", 'w')

    stdin.write(ascript)
    stdin.close()

