#!/usr/bin/env python
# coding: UTF-8

#    signalmail is a Python script which can send Signal messages via Email.
#    It's relying on signal-cli (https://github.com/AsamK/signal-cli) to fetch the actual messages.
#    Configuration file $HOME/.local/share/signalmail/config.ini should be self explanatory.


##########################
version = "0.7.2"
##########################


import sys
import os
import argparse # argument parser
import json # for json handling
import configparser # for config file
import datetime # for decoding timestamps
import time # for timestamp formatting / modification
import smtplib # for sending mails
import mimetypes # for guessing extension of attachment filenames, because Signal does not use them
from email.message import EmailMessage # for sending mails

import base64  # because DBus processor strips contentType
import magic   # because DBus processor strips contentType

from pydbus import SessionBus   # for DBus processing
from pydbus import SystemBus   # for DBus processing
from gi.repository import GLib  # for DBus processing

from functools import reduce, singledispatch

#default data_dir is ${HOME}/.local/share/signalmail/
data_dir = os.path.join("$HOME",".local","share","signalmail","")

# cli arg parser and help message:
parser=argparse.ArgumentParser(
    description='''signalmail is a Python script which can send Signal messages via Email.
    It relies on signal-cli (https://github.com/AsamK/signal-cli) to fetch the actual messages.
    Configuration is done in config.ini in DATA_DIR and should be self explanatory.''')
parser.add_argument("--no-sendmail", dest="no_sendmail", action="store_true", help="override config and do not send mail")
parser.add_argument("--keep-attachments", dest="keep_attachments", action="store_true", help="override config and keep attachments")
parser.add_argument("--data-dir", dest="data_dir", help="set data directory (default: " + data_dir + ")")
parser.add_argument("--config-file", dest="config_file", help="set config file, either an absolute path or relative to the data-directory (default: " + os.path.join(data_dir, "config.ini") + ")")
parser.add_argument("--signal-account", dest="signalnumber", help="override config and use this number as Signal-account")
parser.add_argument("--debug", action="store_true", help="override config and switch on debug mode")
parser.add_argument("--no-autoreply", dest="no_autoreply", action="store_true", help="override config and do not send autoreply")
parser.add_argument("--system", dest="system", action="store_true", help="override config and use system DBus")
parser.add_argument("--useAPIV2", dest="useAPIV2", action="store_true", help="override config and use API V2")

args=parser.parse_args()

if args.data_dir:
    data_dir = args.data_dir
    data_dir = os.path.join(data_dir, '')

data_dir = os.path.expandvars(data_dir)

if not os.path.exists(data_dir):
    try:
        os.makedirs(data_dir)
    except OSError as error:
        print(error, file=sys.stderr)
        print("Configuration error -- failed to create directory " + data_dir, file=sys.stderr)
        raise SystemExit(1)
    try:
        f = open(data_dir + 'config.ini', 'w')
        f.close()
        print("Configuration error -- " + data_dir + "config.ini is empty", file=sys.stderr)
        raise SystemExit(1)
    except OSError as error:
        print(error, file=sys.stderr)
        print("Configuration error -- " + data_dir + " must have read/write access", file=sys.stderr)
        raise SystemExit(1)

config = configparser.ConfigParser()
config.optionxform = lambda option: option # otherwise it's lowercase only

config_file = os.path.join(data_dir, 'config.ini')
if args.config_file:
    if os.path.isabs(args.config_file):
        config_File = argts.config_file
    else:
        config_file = os.path.join(data_dir, args.config_file)

config.read(data_dir + 'config.ini')
#mandatory config variables
try:
    signalnumber = config['SIGNAL']['signalnumber']
    signalname = config['SIGNAL']['signalname']
    mailfrom = config['MAIL']['mailfrom']
    mailsubject = config['MAIL']['mailsubject']
    mailsignature = config['MAIL']['mailsignature']
    bodyHeading = config['MAIL']['bodyheading']
    addr_list = config['MAIL']['addr_list']
    smtpserver = config['MAIL']['smtpserver']
    smtpuser = config['MAIL']['smtpuser']
    smtppassword = config['MAIL']['smtppassword']
except KeyError as key:
    print(key)
    print("Configuration error -- " + data_dir + "config.ini incomplete, missing key " + str(key) + ".", file=sys.stderr)
    raise SystemExit(1)

#optional config variables, with defaults
debug = False
try:
    debug = config['SWITCHES'].getboolean('debug')
except KeyError: True

sendmail = True
try:
    sendmail = config['SWITCHES'].getboolean('sendmail')
except KeyError: True

deleteattachments = True
try:
    deleteattachments = config['SWITCHES'].getboolean('deleteattachments')
except KeyError: True

sessiondbus = True
try:
    sessiondbus = config['SWITCHES'].getboolean('sessiondbus')
except KeyError: True

#global flag to prevent double-calling if we are using V2 of the API
APIV2 = False
try:
    APIV2 = config['SWITCHES'].getboolean('APIV2')
except KeyError: True

signalgroupid = ""
try:
    signalgroupid = config['SIGNAL']['signalgroupid']
except KeyError: True

signal_cli_path = os.path.join('usr', 'local', 'bin', 'signal-cli', '')
try:
    signal_cli_path = config['SIGNAL']['signal_cli_path']
except KeyError: True

signalsettingspath = os.path.join('$HOME', '.local', 'share', 'signal-cli','')
try:
    signalsettingspath = config['SIGNAL']['signalsettingspath']
except KeyError: True

smtpport = 587
try:
    smtpport = config['MAIL']['smtpport']
except KeyError: True

max_attachmentsize = 5
try:
    max_attachmentsize = config['MAIL']['max_attachmentsize']
except KeyError: True

autoreply = ""
try:
    autoreply = config['OTHER']['autoreply']
except KeyError: True

autoattach = ""
try:
    autoattach = config['OTHER']['autoattach']
except KeyError: True

timeformat = "%Y-%m-%d %H:%M:%S %Z"
try:
    timeformat = config['OTHER']['timeformat']
except KeyError: True

contacts = []
try:
    contacts = config.items("CONTACTS")
except KeyError: True

exclude = []
try:
    exclude = config.items("EXCLUDE")
except KeyError: True

headers = []
try:
    headers = config.items("HEADERS")
except KeyError: True

attachmentpath = os.path.join(os.path.expandvars(signalsettingspath), "attachments", "")

# override config if asked to do so:
if args.no_sendmail: sendmail = False
if args.debug: debug = True
if args.keep_attachments: deleteattachments = False
if args.no_autoreply: autoreply=""
if args.system: sessiondbus = False
if args.useAPIV2: APIV2 = True
if args.signalnumber: signalnumber = args.signalnumber

if debug: print("startup: APIV2 is", APIV2)

# main program:
def main():
    if debug: print("DEBUG - main(): called")
    if debug: print("signalmail v" + version + ", Timestamp: " + str(datetime.datetime.now()))
    if debug: print("Switch settings: debug = " + str(debug) +  ", sendmail = " + str(sendmail) + ", deleteattachments = " + str(deleteattachments) + ", sessiondbus = " + str(sessiondbus) + ", APIV2 = " + str(APIV2) + ", autoreply = " + str(autoreply))
    if debug:
        if autoreply: print("autoreply=" + autoreply)
    if debug:
        if autoattach: print("autoattach = " + autoattach)
    if debug: print("data_dir=",data_dir)


    loop = GLib.MainLoop()

    global signal_client
    signal_client = connectToDBus()

    # contacts lookup:
    # check if number is known:
    if contacts:
        if debug: print("DEBUG - configuring contacts")
        for contactNumber, contactName in contacts:
            dbusName = signal_client.getContactName(contactNumber)
            if not contactName == dbusName:
                try:
                    signal_client.setContactName(contactNumber, contactName)
                    if debug: print("DEBUG - set contact name for " + contactNumber + " to " + contactName)
                except:
                    if debug: print("DEBUG - unable to set contact name for " + contactNumber + " to configured value " + contactName)
            else:
                if debug: print("DEBUG - contact name " + contactName + " for " + contactNumber + " is already configured")
    else:
        if debug: print("DEBUG - no contacts!")

    # finally add the own number if not already there
    if signalname:
        selfName = signal_client.getContactName(signalnumber)
        if not selfName:
            signal_client.setContactName(signalnumber, signalname)
            if debug: print("DEBUG - set own display name to '" + signalname + "'.")
        else:
            if debug: print("DEBUG - own display name already configured as '" + signalname + "'.")

    signal_client.onMessageReceivedV2 = msgRcvV2
    signal_client.onMessageReceived = msgRcv
    signal_client.onReceiptReceived = rcptRcv
    signal_client.onReceiptReceivedV2 = rcptRcvV2
    signal_client.onSyncMessageReceived = syncRcv
    signal_client.onSyncMessageReceivedV2 = syncRcvV2

    loop.run()

    if debug: print("DEBUG - main(): finished")
# end main()

def msgRcv (timestamp, sender, groupId, message, attachmentList):
    global APIV2
    if APIV2: return
    if debug: print("msgRcv called")
    if debug: print("timestamp: ", timestamp, " sender: ", sender, " groupId: ", groupId, " message: ", message, " attachmentList: ", attachmentList)
    msgRcvV2 (timestamp, sender, groupId, message, {"attachments":  attachmentList})

def msgRcvV2 (timestamp, sender, groupId, message, extras):
    global headers
    global signal_client
    global APIV2
    APIV2 = True
    if debug: print("msgRcvV2 called")

    if sender in config["EXCLUDE"]:
        if debug: print('DEBUG - excluding ' + sender)
        return

    # de- and encode some of the given arguments to more convenient formats
    mentionList = extras.get("mentions", [])
    attachmentList = extras.get("attachments", [])
    groupIdEncoded = base64.b64encode(bytes(groupId)).decode("utf-8")

    if debug: print("timestamp: ", timestamp, " sender: ", sender, " groupId: ", groupId, " message: ", message, " attachmentList: ", attachmentList)
    if debug: print("mentionList: ", mentionList)
    if debug: print("extras: ", extras)
    if debug: print("groupId: ", groupIdEncoded)

    if groupId:
        groupName = signal_client.getGroupName(groupId)
    else:
        groupName = ""

    if autoreply and sender:
        if debug:
            print("DEBUG - msgRcvV2(): sending autoreply '" + autoreply + "' and attachment '" + autoattach + "' to sender '" + sender + "'")
        try:
            signal_client.sendMessage(autoreply, [autoattach], sender)
        except Exception as e:
            print("Unexpected error:", sys.exc_info()[0])
            print("Cannot send autoreply", file=sys.stderr)
            print(e, " ", type(e), file=sys.stderr)
            print("signal-desktop might be running")

    try:
        sendername = signal_client.getContactName(sender)
    except:
        sendername = "unknown"
    if debug: print("DEBUG - msgRcvV2() - Message - sender name: " + sendername)

    #expand mentions
    #objectReplacementCharacter is Unicode U+FFFC
    #  or \xEF\xBF\xBC in UTF-8
    #objectReplacementCharacter = b'\xEF\xBF\xBC'.decode("utf-8")
    if mentionList:
        lastindex = 0
        newmessage = ""
        for mention in mentionList:
            if isinstance(mention, dict):
                number = mention["recipient"]
                position = mention["start"]
                length = mention["length"]
            else:
                number = mention[0]
                position = mention[1]
                length = mention[2]
            messagepart = message[lastindex:position]
            name = signal_client.getContactName(number)
            newmessage += messagepart + "@" + number
            if name:
                newmessage += " (" + name + ")"
            lastindex = position + length
            if debug: print("DEBUG - msgRcvV2() building message:", newmessage)
        if (lastindex <= len(message)):
            newmessage += message[lastindex:]
        message = newmessage
        if debug: print("DEBUG - msgRcvV2() final message is:", message)

    # timestamp includes milliseconds, we have to strip them:
    timestamp = datetime.datetime.fromtimestamp(float(str(timestamp)[0:-3]), getLocalTimezone())

    replacements = {
        "{senderId}": sender,
        "{senderName}": sendername,
        "{groupId}": groupIdEncoded,
        "{groupName}": groupName,
        "{timestamp}": timestamp.strftime(timeformat),
    }
    mailtext = replacePlaceholders(bodyHeading, replacements) + "\n" \
        + message \
        + "\n\n-- \n" + replacePlaceholders(mailsignature, replacements)
    if debug: print("## Message :")
    if debug: print(mailtext)
    if debug: print("## end of message")

    extraHeaders = {}
    for header, headerValue in headers:
        headerValue = replacePlaceholders(headerValue, replacements)
        if headerValue:
            extraHeaders[header] = headerValue
    
    # send mail if activated:
    if sendmail == True:
        if debug: print("\nsignalmail is sending emails")
        sendemail(from_addr    = replacePlaceholders(mailfrom, replacements),
              addr_list = addr_list,
              subject      = replacePlaceholders(mailsubject, replacements),
              headers      = extraHeaders,
              message      = mailtext,
              attachmentList   = attachmentList,
              login        = smtpuser,
              password     = smtppassword,
              server       = smtpserver,
              port         = smtpport )
    else:
        if debug: print("\nsignalmail is not sending emails")

    # deleting attachments if requested:
    if attachmentList and deleteattachments:
        if debug: print("DEBUG - main(): removing attachments")
        for rawAttachment in attachmentList:
            attachment = get_attachmentFile(rawAttachment)
            if debug: print("DEBUG - main(): removing attachment " + attachment)
            os.remove(attachment)
    return
#end msgRcvV2

def rcptRcv (timestamp, sender):
    global APIV2
    if APIV2: return
    if debug:
        print ("rcptRcv called")
        print (sender)
    return

#
# type parameter
# - read
# - viewed
# - delivery
# - unknown
#
def rcptRcvV2 (timestamp, sender, type, extras):
    global APIV2
    APIV2 = True
    if debug:
        print ("rcptRcvV2 called")
        print("timestamp: ", timestamp, ", sender: ", sender, ", type: ", type, ", extras: ", extras)
    return

def syncRcv (timestamp, sender, destination, groupId, message, attachmentList):
    global APIV2
    if APIV2: return
    if debug:
        print ("syncRcv called")
        print (sender)
    return

def syncRcvV2 (timestamp, sender, destination, groupId, message, extras):
    global APIV2
    APIV2 = True
    if debug:
        print ("syncRcvV2 called")
        print (sender)
    return

# function handles sending of emails
def sendemail(from_addr, addr_list, subject, headers, message, attachmentList, login, password, server, port):
    if debug: print("DEBUG - sendemail(): called, login=" + login + " password=" + password + " server=" + server + " port=" + port + "\nMessage=", message)
    if debug: print("DEBUG - sendemail(): attachmentList=")
    if debug: print(attachmentList)
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = addr_list
    msg["Subject"] = subject
    # add sender and group as custom headers
    for header, headerValue in headers.items():
        msg[header] = headerValue
    msg.set_content(message)

    for rawAttachment in attachmentList:
        attachment = get_attachmentFile(rawAttachment)
        # check for size limit before proceeding:
        attachmentsize =  get_attachmentFileSize(rawAttachment) / 1024.0 / 1024.0
        if debug: print("DEBUG - sendemail(): attachmentsize=",attachmentsize,"MB")
        if attachmentsize <= float(max_attachmentsize):
            ctype, raw_data = get_attachmentContentType(rawAttachment)
            if debug: print("DEBUG - sendemail(): ctype=",ctype)
            maintype, subtype = ctype.split("/", 1)
            ext = mimetypes.guess_extension(ctype, strict=False)
            filename = get_attachmentRemoteName(rawAttachment)
            if filename == "":
                filename = os.path.basename(attachment) + ext
            msg.add_attachment(raw_data, maintype=maintype, subtype=subtype, filename=filename)
        else:
            if debug: print("DEBUG - messagehandler(): Attachment size of ", attachmentsize, " bigger than maximum size of ", max_attachmentsize, "MB, skipping!", sep='')

    # send the email to SMTP server:
    server = smtplib.SMTP(server, port, timeout=10)
    if debug: server.set_debuglevel(1)
    server.starttls()
    server.login(login,password)
    server.sendmail(from_addr, addr_list.split(','), msg.as_string())
    server.quit()
    if debug: print("DEBUG - sendemail(): finished")
#end sendemail(from_addr, addr_list, subject, message, attachmentList, login, password, server, port):

# Replace multiple placeholders according to the keys of repalcements dict
def replacePlaceholders(inputString, replacements):
    if debug: print("DEBUG - replacements", replacements)
    return reduce(lambda a, kv: a.replace(*kv), replacements.items(), inputString)

# Why is Python so great?
def getLocalTimezone():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo

def connectToDBus():
    if sessiondbus:
        bus = SessionBus()
        try:
            signal_client = bus.get('org.asamk.Signal', '_' + signalnumber[1:])
            if debug: print("Using session DBus for /org/asamk/Signal/_" + signalnumber[1:])
        except:
            if debug: print("Could not connect to DBus using /org/asamk/Signal/_" + signalnumber[1:] + ", trying alternative")
            try:
                signal_client = bus.get('org.asamk.Signal')
                if (signalnumber != signal_client.getSelfNumber()):
                    raise SystemExit(1)
                if debug: print("Using session DBus on /org/asamk/Signal")
            except:
                if debug: print("Could not connect to DBus using /org/asamk/Signal")
                print("Daemon error -- did you remember to specify --username to signal-cli and start it in daemon mode?", file=sys.stderr)
                raise SystemExit(1)
    else:
        try:
            bus = SystemBus()
            signal_client = bus.get('org.asamk.Signal', '_' + signalnumber[1:])
            if debug: print("Using system DBus for /org/asamk/Signal/_" + signalnumber[1:])
        except:
            if debug: print("Could not connect to system DBus")
            print("Daemon error -- did you remember to specify --system to signal-cli and start it in daemon mode?", file=sys.stderr)
            raise SystemExit(1)
    return signal_client
#end connectToDBus():

@singledispatch
def get_attachmentFile(rawAttachment):
    print("Attachment type unknown", type(rawAttachment), file=sys.stderr)
    raise SystemExit(1)
    return
@get_attachmentFile.register
def _(arg: dict, verbose=False):
    attachmentFile = arg["file"]
    return attachmentFile
@get_attachmentFile.register
def _(arg: tuple, verbose=False):
    attachmentFile = attachmentpath + arg[2]
    return attachmentFile
@get_attachmentFile.register
def _(arg: str, verbose=False):
    attachmentFile = arg
    return attachmentFile
#end get_attachmentFile(rawAttachment):

@singledispatch
def get_attachmentContentType(rawAttachment):
    return attachmentContentType, raw_data
@get_attachmentContentType.register
def _(arg: dict, verbose=False):
    attachmentContentType = arg["contentType"]
    if debug: print("Content-type: " + attachmentContentType)
    fp = open(get_attachmentFile(arg), 'rb') #open in binary format
    raw_data = fp.read()
    fp.close()
    return attachmentContentType, raw_data
@get_attachmentContentType.register
def _(arg: tuple, verbose=False):
    attachmentContentType = arg[0]
    if debug: print("Content-type: " + attachmentContentType)
    fp = open(get_attachmentFile(arg), 'rb') #open in binary format
    raw_data = fp.read()
    fp.close()
    return attachmentContentType, raw_data
@get_attachmentContentType.register
def _(arg: str, verbose=False):
    fp = open(get_attachmentFile(arg), 'rb') #open in binary format
    raw_data = fp.read()
    fp.close()
    # .. try to find out MIME type and process it properly
    if debug: print("Guess MIME type of file '" + get_attachmentFile(arg) + "'")
    mime = magic.Magic(mime=True)
    ctype = mime.from_buffer(raw_data)
    if debug: print("ctype: ", ctype)
    if ctype is None:
        ctype = "application/octet-stream"
    return ctype, raw_data
#end get_attachmentContentType(rawAttachment):

@singledispatch
def get_attachmentFileSize(rawAttachment):
    return
@get_attachmentFileSize.register
def _(arg: dict, verbose=False):
    attachmentFileSize = float(arg["size"])
    return attachmentFileSize
@get_attachmentFileSize.register
def _(arg: tuple, verbose=False):
    attachmentFileSize = float(arg[3])
    return attachmentFileSize
@get_attachmentFileSize.register
def _(arg: str, verbose=False):
    attachmentFileSize = float(os.path.getsize(arg))
    return attachmentFileSize
#end get_attachmentFileSize(rawAttachment):

@singledispatch
def get_attachmentRemoteName(rawAttachment):
    return
@get_attachmentRemoteName.register
def _(arg: dict, verbose=False):
    attachmentRemoteName = arg["fileName"]
    return attachmentRemoteName
@get_attachmentRemoteName.register
def _(arg: tuple, verbose=False):
    attachmentRemoteName = arg[1]
    return attachmentRemoteName
@get_attachmentRemoteName.register
def _(arg: str, verbose=False):
    attachmentRemoteName = ""
    return attachmentRemoteName
#end get_attachmentRemoteName(rawAttachment):

if __name__ == '__main__':
    main()
