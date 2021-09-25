# About
This projects provides a dockerized smtp server that forwards incoming mails as signal messages.

# Quickstart
- Checkout this repository
- Create subdirectory data
- Start/Update services `$ docker-compose up --build --force-recreate -d --remove-orphans`
- Optionally: [Setup signal-cli](#setup-signal-cli) - register numbers, ...
- Get auto-created smtp credentials: `$ cat ./data/smtp2signal/smtp2signal.token`
- Done. The smtp server now listens at port 8025 (all interfaces). See [Signal Message Routing](#signal-message-routing) for howto send messages.

# Signal Message Routing
The smtp server evaulates the first mail recipient's address:
- The domain part (right side of @) must be valid but is ignored otherwise
- The local part (left side of @) is parsed as query string with the following exceptions:
  * `+` is treated literally and not replaced by space
  * `--` maybe used to substitute `=` if not supported by mail client
- If an argument is expected only once, but given multiple times, the last argument value takes precedence. The following arguments are supported:
  * `from`: required once - sender account number; must be registered for use with signal-cli, otherwise sending the signal message will be refused
  * `to`:  required at least once if not `to_group` is given - number(s) of recipient(s)
  * `to_group`: required once if not `to` is given - recipient group id in signal-cli format
  * `omit_subject`: optional boolean - mail subject will not be forwarded if `true`, defaults to `false`
  * `omit_body`: optional boolean - mail body will not be forwarded if `true`, defaults to `false`
  * `body_separator`: optional string - characters to insert between subject line and body, defaults to `\n\n`
  * `lines`: optional set of single line numbers, ranges of line numbers (`2-4` end inclusive), or the term `all` - for each argument, the referenced lines will be appended to the signal message, defaults to `all`

Examples:
 - `from--+49123456789&to--+49987654321&to--+49192837465@example.com` - message forwarded to +49987654321 and +49192837465 using +49123456789 as sender
 - `from--+49123456789&to_group--+xh18rfD4ewA0AikA+Yi5tfrSaikS5fCfnTt5VEJAaQ%3D&--omit_body=true@example.com` - message subject forwarded to given group using +49123456789 as sender

# Setup signal-cli
Numbers need to be register with signal-cli. The easiest way to to this is interact with the command line signal-cli client. This is only possible if the smtp2signal gateway is not running (more specifically the rest api container).

- Stop smtp2signal: `$ docker-compose stop`
- Run signal-cli container: `$ docker run -it --entrypoint sh -u signal-api -v "$PWD/data/signal-cli":"/home/.local/share/signal-cli" smtp2signal_signal-cli-rest-api`
- [Configure signal-cli](https://github.com/AsamK/signal-cli#usage): Register number, ...
- Restart smtp2signal `$ docker-compose up -d`

Note: Make sure the proper signal-cli data directory is bind-mounted for the signal-cli configuration data to be preserved.
