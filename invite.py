from typing import Optional, Type

from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

import json
import datetime

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("admin_secret")
        helper.copy("legacy_mr")
        helper.copy("reg_url")
        helper.copy("reg_page")
        helper.copy("admins")
        helper.copy("expiration")
        helper.copy("message")
        helper.copy("admin_access_token")
        helper.copy("admin_api_url")

class Invite(Plugin):
    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def can_manage(self, evt: MessageEvent) -> bool:
        # check if access_token is defined
        if self.config["admin_access_token"]:
            # check if CAS SSO users are listed as admins
            if 'sso:cas' in self.config["admins"]:
                if await self.is_cas_user(evt):
                    return True

        # check if sender is specifically listed as an admin
        if evt.sender in self.config["admins"]:
            return True

        # sender cannot manage
        await evt.respond("You don't have permission to manage invitations for this server.")
        return False

    async def is_cas_user(self, evt: MessageEvent) -> bool:
        # retrieve user_profile information
        headers = {
            'Authorization': f"Bearer {self.config['admin_access_token']}",
            'Content-Type': 'application/json'
            }

        try:
            response = await self.http.get(f"{self.config['admin_api_url']}/_synapse/admin/v2/users/{evt.sender}", headers=headers)
            status = response.status
            resp_json = await response.json()
        except Exception as e:
            body = await response.text()
            await evt.respond(f"Uh oh! I got a {status} response from your admin endpoint:<br /> \
                        {body}<br /> \
                        which prompted me to produce this error:<br /> \
                        <code>{e.message}</code>", allow_html=True)
            return False

        try:
            external_ids = resp_json['external_ids']
            for i in external_ids:
                if i['auth_provider'] == 'cas':
                    return True
            return False
        except Exception as e:
            return False

    def set_api_endpoints(self) -> None:
        self.config["api_url"] = self.config["reg_url"] + "/api"

        if self.config["legacy_mr"] == True:
            self.config["api_url"] = self.config["reg_url"]

    @command.new(name="invite", help="Generate a unique invitation code to this matrix homeserver", \
            require_subcommand=True)
    async def invite(self, evt: MessageEvent) -> None:
        pass

    @invite.subcommand("generate", help="Generate a new invitation token.")
    async def generate(self, evt: MessageEvent) -> None:
        await evt.mark_read()

        if not await self.can_manage(evt):
            return

        self.set_api_endpoints()

        ex_date = datetime.datetime.strftime( \
                (datetime.date.today() + datetime.timedelta(days=self.config["expiration"])), \
                "%Y-%m-%d")
        # use re-ordered date if using legacy code
        if self.config["legacy_mr"] == True:
            ex_date = datetime.datetime.strftime( \
                    (datetime.date.today() + datetime.timedelta(days=self.config["expiration"])), \
                    "%m.%d.%Y")
        headers = {
            'Authorization': f"SharedSecret {self.config['admin_secret']}",
            'Content-Type': 'application/json'
            }

        try:
            response = await self.http.post(f"{self.config['api_url']}/token", headers=headers, \
                    json={"max_usage": 1, "one_time": True, "ex_date": ex_date, "expiration_date": ex_date})
            status = response.status
            resp_json = await response.json()
        except Exception as e:
            body = await response.text()
            await evt.respond(f"Uh oh! I got a {status} response from your registration endpoint:<br /> \
                        {body}<br /> \
                        which prompted me to produce this error:<br /> \
                        <code>{e.message}</code>", allow_html=True)
            return None
        try:
            token = resp_json['name']
        except Exception as e:
            await evt.respond(f"I got a bad response back, sorry, something is borked. \n\
                    {resp_json}")
            self.log.exception(e)
            return None

        msg = '<br />'.join(
            [
                f"Invitation token <b>{token}</b> created!",
                f"",
                f"Your unique url for registering is:",
                f"{self.config['reg_url']}{self.config['reg_page']}?token={token}",
                f"This invite token will expire in {self.config['expiration']} days.",
                f"If it expires before use, you must request a new token."
            ])

        if self.config['message']:
            msg = self.config["message"].format(token=token, reg_url=self.config['reg_url'],
                    reg_page=self.config['reg_page'], expiration=self.config['expiration'])

        await evt.respond(msg, allow_html=True)

    @invite.subcommand("status", help="Return the status of an invite token.")
    @command.argument("token", "Token", pass_raw=True, required=True)
    async def status(self, evt: MessageEvent, token: str) -> None:
        await evt.mark_read()

        if not await self.can_manage(evt):
            return

        self.set_api_endpoints()

        if not token:
            await evt.respond("you must supply a token to check")

        headers = {
            'Authorization': f"SharedSecret {self.config['admin_secret']}",
            'Content-Type': 'application/json'
            }

        try:
            response = await self.http.get(f"{self.config['api_url']}/token/{token}", headers=headers)
            resp_json = await response.json()
        except Exception as e:
            await evt.respond(f"request failed: {e.message}")
            return None

        # this isn't formatted nicely but i don't really care that much
        await evt.respond(f"Status of token {token}: \n<pre><code format=json>{json.dumps(resp_json, indent=4)}</code></pre>", allow_html=True)

    @invite.subcommand("revoke", help="Disable an existing invite token.")
    @command.argument("token", "Token", pass_raw=True, required=True)
    async def revoke(self, evt: MessageEvent, token: str) -> None:
        await evt.mark_read()

        if not await self.can_manage(evt):
            return

        self.set_api_endpoints()

        if not token:
            await evt.respond("you must supply a token to revoke")

        headers = {
            'Authorization': f"SharedSecret {self.config['admin_secret']}",
            'Content-Type': 'application/json'
            }

        # this is a really gross way of handling legacy installs and should be cleaned up
        # basically this command used to use PUT but now uses PATCH
        if self.config["legacy_mr"] == True:
            try:
                response = await self.http.put(f"{self.config['api_url']}/token/{token}", headers=headers, \
                        json={"disable": True})
                resp_json = await response.json()
            except Exception as e:
                await evt.respond(f"request failed: {e.message}")
                return None
        else:
            try:
                response = await self.http.patch(f"{self.config['api_url']}/token/{token}", headers=headers, \
                        json={"disabled": True})
                resp_json = await response.json()
            except Exception as e:
                await evt.respond(f"request failed: {e.message}")
                return None

        # this isn't formatted nicely but i don't really care that much
        await evt.respond(f"<pre><code format=json>{json.dumps(resp_json, indent=4)}</code></pre>", allow_html=True)

    @invite.subcommand("list", help="List all tokens that have been generated.")
    async def list(self, evt: MessageEvent) -> None:
        await evt.mark_read()

        if not await self.can_manage(evt):
            return

        self.set_api_endpoints()

        headers = {
            'Authorization': f"SharedSecret {self.config['admin_secret']}"
            }

        try:
            response = await self.http.get(f"{self.config['api_url']}/token", headers=headers)
            resp_json = await response.json()
        except Exception as e:
            await evt.respond(f"request failed: {e.message}")
            return None

        # this isn't formatted nicely but i don't really care that much
        await evt.respond(f"<pre><code format=json>{json.dumps(resp_json, indent=4)}</code></pre>", allow_html=True)
