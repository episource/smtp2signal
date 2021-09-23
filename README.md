# About
This projects provides a dockerized smtp server that forwards incoming mails as signal messages.

# Quickstart
1. Checkout this repository
2. Create subdirectory data
3. Start services `$ docker-compose up --build --force-recreate -d --remove-orphans`
4. Setup signal-cli:
  a. `$ docker exec -it -u signal-api smtp2signal_signal-cli-rest-api_1 sh`
  b. [Configure signal-cli](https://github.com/AsamK/signal-cli#usage): Register number, ...
5. Get auto-created smtp credentials: `$ cat ./data/smtp2signal/smtp2signal.token`
6. Done. The smtp server now listens at port 8025 (all interfaces). See [Signal Message Routing](#signal-message-routing) for howto send messages.

# Signal Message Routing
The smtp server evaulates the first mail recipient's address:
1. The domain part (right side of @) must be valid but is ignored otherwise
2. The local part (left side of @) is parsed as query string with the following exceptions:
  a. `+` is treated literally and not replaced by space
  b. `--` maybe used to substitute `=` if not supported by mail client
3. If an argument is expected only once, but given multiple times, the last argument value takes precedence. The following arguments are supported:
  a. `from`: required once - sender account number; must be registered for use with signal-cli, otherwise sending the signal message will be refused
  b. `to`:  required at least once if not `to_group` is given - number(s) of recipient(s)
  c. `to_group`: required once if not `to` is given - recipient group id in signal-cli format
  d. `omit_subject`: optional boolean - mail subject will not be forwarded if `true`, defaults to `false`
  e. `omit_body`: optional boolean - mail body will not be forwarded if `true`, defaults to `false`
  f. `body_separator`: optional string - characters to insert between subject line and body, defaults to `\n\n`
  g. `lines`: optional set of single line numbers, ranges of line numbers (`2-4` end inclusive), or the term `all` - for each argument, the referenced lines will be appended to the signal message, defaults to `all`

Examples:
 - `from--+49123456789&to--+49987654321&to--+49192837465@example.com` - message forwarded to +49987654321 and +49192837465 using +49123456789 as sender
 - `from--+49123456789&to_group--+xh18rfD4ewA0AikA+Yi5tfrSaikS5fCfnTt5VEJAaQ%3D&--omit_body=true@example.com` - message subject forwarded to given group using +49123456789 as sender
