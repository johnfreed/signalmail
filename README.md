# signalmail

signalmail is a Python script adapted from signalbot using DBus but with a more specific focus: forwarding Signal messages via Email. It's relying on signal-cli (https://github.com/AsamK/signal-cli) in daemon mode to fetch the actual messages. Configuration is done in by copying config_default.ini to $HOME/.local/share/signalmail/config.ini and modifying it.

## CLI arguments

You may pass the following arguments to signalbot.py to overwrite defaults set in config.ini:

- `--sendmail` override config and send mail
- `--notsendmail` override config and do not send mail
- `--debug` override config and switch on debug mode
- `--notdebug` override config and switch off debug mode
- `--deleteattachments` override config and delete attachments after processing
- `--notdeleteattachments` override config and keep attachments after processing

## Known issues

- users are untrusted if they reinstall Signal and therefore messages don't come through. As a workaround you can manually trust the new key using signal-cli: `signal-cli -u yourNumber trust -a untrustedNumber`

## ToDos

- add possibility to choose between multiple groups to be forwarded to different recipients

## Changelog

- 0.7.0   - first quick and dirty implementation (bumping version from signalbot to avoid conflict)

