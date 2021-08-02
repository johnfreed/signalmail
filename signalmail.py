#!/usr/bin/env python
# coding: UTF-8

#    signalmail is a Python script which can send Signal messages via Email.
#    It's relying on signal-cli (https://github.com/AsamK/signal-cli) to fetch the actual messages.
#    Configuration file $HOME/.local/share/signalmail/config.ini should be self explanatory.


##########################
version = "0.7.1"
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

data_dir = os.path.join("$HOME",".local","share","signalmail","")

# cli arg parser and help message:
parser=argparse.ArgumentParser(
    description='''signalmail is a Python script which can send Signal messages via Email.
    It's relying on signal-cli (https://github.com/AsamK/signal-cli) to fetch the actual messages.
    Configuration is done in config.ini in DATA_DIR and should be self explanatory.''')
parser.add_argument("--no-sendmail", dest="no_sendmail", action="store_true", help="override config and do not send mail")
parser.add_argument("--keep-attachments", dest="keep_attachments", action="store_true", help="override config and keep attachments")
parser.add_argument("--data-dir", dest="data_dir", help="set data directory (default: " + data_dir+ ")")
parser.add_argument("--debug", action="store_true", help="override config and switch on debug mode")
parser.add_argument("--no-autoreply", dest="no_autoreply", action="store_true", help="override config and do not send autoreply")

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

config.read(data_dir + 'config.ini')
#mandatory config variables
try:
    signalnumber = config['SIGNAL']['signalnumber']
    mailfrom = config['MAIL']['mailfrom']
    mailsubject = config['MAIL']['mailsubject']
    addr_list = config['MAIL']['addr_list']
    smtpserver = config['MAIL']['smtpserver']
    smtpuser = config['MAIL']['smtpuser']
    smtppassword = config['MAIL']['smtppassword']
except KeyError:
    print("Configuration error -- " + data_dir + "config.ini incomplete", file=sys.stderr)

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

signalgroupid = ""
try:
    signalgroupid = config['SIGNAL']['signalgroupid']
except KeyError: True

signal_cli_path = os.path.join('usr', 'local', 'bin', 'signal-cli', '')
try:
    signal_cli_path = config['SIGNAL']['signal_cli_path']
except KeyError: True

signalconfigpath = os.path.join('$HOME', '.local', 'share', 'signal-cli','')
try:
    signalconfigpath = config['SIGNAL']['signalconfigpath']
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

contacts = []
try:
    contacts = config.items("CONTACTS")
except KeyError: True
    
attachmentpath = os.path.join(os.path.expandvars(signalconfigpath), "attachments")


# override config if asked to do so:
if args.no_sendmail: sendmail = False
if args.debug: debug = True
if args.keep_attachments: deleteattachments = False
if args.no_autoreply: autoreply=""

# main program:
def main():
    if debug: print("DEBUG - main(): called")
    if debug: print("signalmail v" + version + ", Timestamp: " + str(datetime.datetime.now()), file=sys.stderr)
    if debug: print("Switch settings: debug = " + str(debug) +  ", sendmail = " + str(sendmail) + ", deleteattachments = " + str(deleteattachments))
    if debug:
        if autoreply: print("autoreply=" + autoreply)
    if debug:
        if autoattach: print("autoattach = " + autoattach)
    if debug: print("data_dir=",data_dir)


    loop = GLib.MainLoop()

    try:
        if debug: print("Trying session DBus")
        bus = SessionBus()
        signal_client = bus.get('org.asamk.Signal')
    except:
        if debug: print("Could not connect to DBus using /org/asamk/Signal, trying alternative")
        try:
            signal_client = bus.get('org.asamk.Signal._' + signalnumber[1:])
        except:
            if debug: print("Could not connect to DBus using /org/asamk/Signal/_" + signalnumber[1:])
            try:
                if debug: print("Trying system DBus")
                bus = SystemBus()
                signal_client = bus.get('org.asamk.Signal')

            except:
                print("Daemon error -- did you remember to specify --username to signal-cli and start it in daemon mode?", file=sys.stderr)
                raise SystemExit(1)

    signal_client.onMessageReceived = msgRcv
    signal_client.onReceiptReceived = rcptRcv
    signal_client.onSyncMessageReceived = syncRcv

    loop.run()


    print("\n#### Everything done. ####\n\n", file=sys.stderr)
    if debug: print("DEBUG - main(): finished")
# end main()

def msgRcv (timestamp, sender, groupId, message, attachmentlist):
    if debug: print("msgRcv called")
    if debug: print("timestamp: ", timestamp, " sender: ", sender, " groupId: ", groupId, " message: ", message, " attachmentlist: ", attachmentlist)

    if autoreply and sender:
        bus = SessionBus()
        signal_client = bus.get('org.asamk.Signal')
        if debug:
            print("DEBUG - msgRcv(): sending autoreply " + autoreply + " and attachment " + autoattach + " to sender " + sender)
        signal_client.sendMessage(autoreply, [autoattach], sender)
        
    sendername = "unknown"

    # contacts lookup:
    # check if number is known:
    if contacts:
        if debug: print("DEBUG - msgRcv() - checking contacts")
        for j, k in contacts:
            if j == sender: sendername = k
        if debug: print("DEBUG - msgRcv() - Message - sender name: " + sendername)

    else:
        if debug: print("DEBUG - msgRcv() - no contacts!")


    # timestamp includes milliseconds, we have to strip them:
    timestamp = datetime.datetime.utcfromtimestamp(float(str(timestamp)[0:-3]))

    mailtext = "New Signal message from " + str(sendername) + " (" +str(sender) + "), sent " + str(timestamp) + " ...\n" + message + "\n\n"
    print("## Message :", file=sys.stderr)
    print(mailtext, file=sys.stderr)
    print("## end of message", file=sys.stderr)

    # send mail if activated:
    if sendmail == True:
        print("\nsignalmail is sending emails", file=sys.stderr)
        sendemail(from_addr    = mailfrom,
              addr_list = addr_list,
              subject      = mailsubject,
              message      = mailtext,
              attachmentlist   = attachmentlist,
              timestamp    = timestamp,
              login        = smtpuser,
              password     = smtppassword,
              server       = smtpserver,
              port         = smtpport )
    else: print("\nsignalmail is not sending emails", file=sys.stderr)

    # deleting attachments if requested:
    if attachmentlist and deleteattachments:
        if debug: print("DEBUG - main(): removing attachments")
        for attachment in attachmentlist:
            if debug: print("DEBUG - main(): removing attachment " + attachment)
            os.remove(attachment) 

    return

def rcptRcv (timestamp, sender):
    if debug:
        print ("rcptRcv called")
        print (sender)
    return

def syncRcv (timestamp, sender, destination, groupId, message, attachmentlist):
    if debug:
        print ("syncRcv called")
        print (sender)
    return

# function handles sending of emails
def sendemail(from_addr, addr_list, subject, message, attachmentlist, timestamp, login, password, server, port):
    if debug: print("DEBUG - sendemail(): called, login=" + login + " password=" + password + " server=" + server + " port=" + port + "\nMessage=", message)
    if debug: print("DEBUG - sendemail(): attachmentlist=")
    if debug: print(attachmentlist)
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = addr_list
    msg["Subject"] = subject
    msg.set_content(message)

    for attachment in attachmentlist:
        # check for size limit before proceeding:
        attachmentsize = float(os.path.getsize(attachment)) / 1024.0 / 1024.0
        if attachmentsize <= float(max_attachmentsize):                      
            # .. try to find out MIME type and process it properly
            if debug: print("Guess MIME type of file '" + attachment + "'")
            fp = open(attachment, 'rb') #open in binary format
            raw_data = fp.read()
            fp.close()
            mime = magic.Magic(mime=True)
            ctype = mime.from_buffer(raw_data)
            
            if debug: print("ctype: ", ctype)
            if ctype is None:
                ctype = "application/octet-stream"

            maintype, subtype = ctype.split("/", 1)
            ext = mimetypes.guess_extension(ctype, strict=False)
             
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
#end sendemail(from_addr, addr_list, subject, message, attachmentlist, timestamp, login, password, server, port):


# this is a ugly workaround to convert timestamps in python < 3.2, see https://stackoverflow.com/questions/26165659/python-timezone-z-directive-for-datetime-strptime-not-available#26177579
def dt_parse(t):
    if debug: print("DEBUG - dt_parse(): called")
    ret = datetime.datetime.strptime(t[0:24],'%a, %d %b %Y %H:%M:%S') #e.g: Fri, 26 Jan 2018 12:36:52 +0100
    if t[26]=='+':
        ret-=datetime.timedelta(hours=int(t[27:29]),minutes=int(t[29:]))
    elif t[26]=='-':
        ret+=datetime.timedelta(hours=int(t[27:29]),minutes=int(t[29:]))
    if debug: print("DEBUG - dt_parse(): finished")
    return ret
#end dt_parse(t):

if __name__ == '__main__':
    main()
