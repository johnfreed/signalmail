# signalmail

signalmail is a Python script to forward Signal messages via email. It 
relies on signal-cli (`https://github.com/AsamK/signal-cli`) running in 
daemon mode to fetch the actual messages. Configuration is done in by 
copying config_default.ini to $HOME/.local/share/signalmail/config.ini and 
modifying it.

Please note that messages are NOT END-TO-END ENCRYPTED. Signalmail is an 
UNOFFICIAL program that does not connect directly to the Signal servers. 
Messages and attachments are sent "in the clear" via DBus on the local 
computer, so signalmail relies on DBus security to protect your message. 
Further, signal-cli is an UNOFFICIAL client that does connect directly to 
the Signal servers. It is signal-cli that encrypts and decrypts the 
messages.

Finally, forwarding the message via email is inherently insecure, using 
the SMTP protocol. 

## CLI arguments

You may pass the following arguments to `signalbot.py`:

- `--no-sendmail` override config and do not send mail
- `--debug` override config and switch on debug mode
- `--keepattachments` override config and keep attachments after processing
- `--autoreply` text of a reply to each incoming Signal message
- `--autoattach` path to file to send as attachment with autoreply
- `--system` override config and use system DBus

## Known issues

- users are untrusted if they reinstall Signal and therefore messages 
  don't come through. See https://github.com/AsamK/signal-cli/wiki/Manage-trusted-keys 

  As a workaround using signal-cli:
	- If you don't care about security, you can manually trust the new key   
   `signal-cli -u yourNumber trust -a untrustedNumber`
	- Better is to verify it with the remote number's SAFETY_NUMBER  
   `signal-cli -u yourNumber trust -v SAFETY_NUMBER -a untrustedNumber`


## ToDos

- add possibility to choose between multiple groups to be forwarded to different recipients

