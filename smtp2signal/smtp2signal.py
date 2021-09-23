#!/usr/bin/python3

import aiohttp
import aiosmtpd.controller
import aiosmtpd.smtp
import asyncio
import base64
import email
import email.policy
import html2text
import json
import logging
import os
import secrets
import signal
import sys
from os.path import exists
from urllib.parse import parse_qs

from pprint import pprint

SIGNAL_SMTP_PORT = os.getenv("SIGNAL_SMTP_PORT", "8025")
SIGNAL_SMTP_HOST = os.getenv("SIGNAL_SMTP_HOST", "localhost")
SIGNAL_SMTP_TOKEN_FILE = os.getenv("SIGNAL_SMTP_TOKEN_FILE", None)
SIGNAL_SMTP_TOKEN_LEN = 16
SIGNAL_CLI_BASE_URL = os.getenv("SIGNAL_CLI_BASE_URL", "http://127.0.0.1:8080")
SIGNAL_CLI_SEND_API = SIGNAL_CLI_BASE_URL.rstrip("/") + "/v2/send"
SMTP_POLICY = email.policy.SMTPUTF8.clone(raise_on_defect=True)
SHUTDOWN_TIMEOUT_SEC = 5

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_main(loop))
    try:
        # _main installs signal handler to stop loop
        loop.run_forever()
    finally:
        loop.close()

async def _main(loop):
    rest_client = aiohttp.ClientSession()
    smtp_controller = CooperativeSmtpController(Smtp2SignalHandler(rest_client), authenticator=TokenAuthenticator(), auth_required=True, auth_require_tls=False,
            hostname=SIGNAL_SMTP_HOST, port=SIGNAL_SMTP_PORT)

    async def _shutdown(signal):
        logging.warning(f"Received signal {signal.name}. Going to shutdown. Waiting up to {SHUTDOWN_TIMEOUT_SEC}s for tasks to finish.")
        smtp_controller.end()
        await rest_client.close()
        
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if (tasks):
            logging.warning(f"Waiting up to {SHUTDOWN_TIMEOUT_SEC}s for tasks to finish.")
            await asyncio.wait(tasks, timeout=SHUTDOWN_TIMEOUT_SEC)
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            
            logging.warning("Some tasks did not finish in time. Forcing cancellation.")
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)

        logging.warning("Have a nice day!")
        loop.stop()
    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(_shutdown(s)))

    logging.warning(f"Going to listen on {smtp_controller.hostname}:{smtp_controller.port}")
    await smtp_controller.async_begin()

class CooperativeSmtpController(aiosmtpd.controller.UnthreadedController):
    async def async_begin(self):
        self.loop = asyncio.get_running_loop()
        self.server_coro = self._create_server()
        self.server = await self.server_coro

class TokenAuthenticator:
    def __init__(self):
        if (not SIGNAL_SMTP_TOKEN_FILE or not exists(SIGNAL_SMTP_TOKEN_FILE)):
            self.token = secrets.token_urlsafe(2 * SIGNAL_SMTP_TOKEN_LEN)[0:SIGNAL_SMTP_TOKEN_LEN]
            logging.warning("New auth token created. Will be cached if SIGNAL_SMTP_TOKEN_FILE is defined.")
            logging.warning(f"Use theses credentials: user=(any), password={self.token}")
        else:
            with open(SIGNAL_SMTP_TOKEN_FILE, "r") as f: self.token = f.readlines()[0]
            logging.warning("Loaded auth token from file")
            return

        if (SIGNAL_SMTP_TOKEN_FILE):
            with open(SIGNAL_SMTP_TOKEN_FILE, "w+") as f: f.write(self.token)

    def __call__(self, server, session, envelope, mechanism, auth_data):
        fail_nothandled = aiosmtpd.smtp.AuthResult(success=False, handled=False)
        if mechanism not in ("LOGIN", "PLAIN"):
            logging.warning("unsupported auth mechanism attempted")
            return fail_nothandled

        username = auth_data.login.decode('utf-8')
        password = auth_data.password.decode('utf-8')

        if (password == self.token):
            return aiosmtpd.smtp.AuthResult(success=True)

        logging.warning(f"peer {session.peer} failed to authenticate")
        return fail_nothandled

class Smtp2SignalHandler:
    def __init__(self, rest_client):
        self.rest_client = rest_client
        self.html2text = html2text.HTML2Text(bodywidth=0)
        self.html2text.ignore_tables = True
    
    async def handle_DATA(self, server, session, envelope):
        try:
            peer = session.peer
            mailfrom = envelope.mail_from
            rcpttos = envelope.rcpt_tos

            mail_message = email.message_from_bytes(envelope.content, policy=SMTP_POLICY)

            self.send_signal_as_task(**self.build_signal(rcpttos, mail_message))
        except Exception as exc:
            logging.warning(f"Failed to handle smtp data: {exc}", exc_info=exc)
            return f"451 {exc}"

        return '250 OK'

    def build_signal(self, rcpttos, mail_message):
        def ensure_list(v):
            if (isinstance(v, list)):
                return v
            return [v]

        def str2bool(v):
              return str(ensure_list(v)[-1]).lower() in ("yes", "true", "t", "1")


        mail_subject = mail_message['subject']
        mail_body = mail_message.get_body(preferencelist=('plain'))
        mail_text = mail_body.get_content() if mail_body else None
        if (not mail_body):
            mail_body = mail_message.get_body(preferencelist=('html'))
            mail_text = self.html2text.handle(mail_body.get_content()) if mail_body else None
        if (not mail_body):
            mail_body = mail_message
            mail_text = mail_message.get_content()
        
        first_attachment = next((a.get_content() for a in mail_message.iter_attachments()), None)

        addr_parts = rcpttos[0].strip("<> ").split('@', 1)
        # ignore domain part

        # local part of RCPT TO (as per RFC5321) ist treated as url query string
        # with the following exceptions:
        # 1. "+" is treated literally and not replaced by space
        # 2. (unencoded) literal "--" is replaced by "="
        options = parse_qs(addr_parts[0].replace("+","%2B").replace("--","="))

        logging.warning(f"building signal with options {options}")
        if (not options.get("to")):
            raise RuntimeError(f"rcpttos[0] is missing to-argument: {rcpttos[0]}")
        if (not options.get("from")):
            raise RuntimeError(f"rcpttos[0] is missing from-argument: {rcpttos[0]}")

        text = ""
        if (not str2bool(options.get("omit_subject"))):
            text += mail_subject
        if (not str2bool(options.get("omit_body"))):
            if (not str2bool(options.get("omit_subject"))):
                text += options.get("body_separator", "\n\n")
            line_selectors = "/".join(ensure_list(options.get("lines", "all"))).split("/")
            for selector in line_selectors:
                if (selector.lower() == "all"):
                    text += mail_text
                else:
                    mail_text_lines = mail_text.splitlines(True)
                    start_stop = selector.split("-", 1)
                    start_idx = int(start_stop[0])
                    stop = ((start_stop[1:] + [start_idx+1])[0])
                    stop_idx = None if stop.lower() == "end" else int(stop)+1
                    
                    to_append = mail_text_lines[start_idx:stop_idx]
                    text += "".join(to_append)

                text += "\n"

        signal = {
            "from_number": ensure_list(options["from"])[-1],
            "to": options["to"],
            "text": text.strip(),
            "binary_attachment": first_attachment
        }
        return signal


    async def send_signal(self, from_number, to, text, binary_attachment=None):
        recipients = to if isinstance(to, list) else [to]

        data = {
                "message": text,
                "number": from_number,
                "recipients": recipients,
                "base64_attachments": [ str(base64.b64encode(binary_attachment), encoding="utf-8") ] if binary_attachment is not None else []
        }

        async with self.rest_client.request("post", SIGNAL_CLI_SEND_API, json=data) as response:
            if (not response.ok):
                details = "n/a"
                try:
                    details = await response.text()
                except:
                    logging.warning("failed to retrieve api error details.")
                    pass
                raise aiohttp.ClientError(f"signal api failed: {response.status} - {response.reason} - {details}")
    
    def send_signal_as_task(self, from_number, to, text, binary_attachment=None):
        t = asyncio.create_task(self.send_signal(from_number, to, text, binary_attachment))
        t.add_done_callback(self.signal_task_done_callback)

    def signal_task_done_callback(self,task):
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logging.warning(f"Signal api failed: {exc}")

if __name__ == "__main__":
    main()
