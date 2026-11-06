import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1568277964762648657

STAFF_ROLES = [
    1568292371035193496,
    1568292367755116615,
    1568292377725247550,
    1568295300613939460,
]

MODERATOR_ROLES = [
    1568292371035193496,
    1568292367755116615,
]

SCAMMER_ROLE_ID = 1568292380862583045
RATTER_ROLE_ID  = 1568292391197085816

CATEGORY_MAP = {
    "Channel":      1568354090520674485,
    "Marketplace":  1568354130236280933,
    "Support":      1568354171281743922,
    "Scammers":     1568354189665632327,
    "Staff Apply":  1568354223354019860,
}

MAX_TICKETS = 2
PING_COOLDOWN_SECONDS = 86400

DATA_FILE = "bot_data.json"

BANNER_URL = "https://cdn.discordapp.com/attachments/1515618623425871994/1568334499778007081/pasters_heaven_banner.png?ex=6aef70d2&is=6aee1f52&hm=846e7c7da8f2e7f7c5d140d42870e9365bba263bd4761206d57867a3c90bd90f&"
EMBED_COLOR = 0x000000


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"tickets": {}, "ping_cooldowns": {}, "ticket_count": 0}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def has_staff_role():
    async def predicate(interaction: discord.Interaction):
        return any(role.id in STAFF_ROLES for role in interaction.user.roles)
    return app_commands.check(predicate)


def has_mod_role():
    async def predicate(interaction: discord.Interaction):
        return any(role.id in MODERATOR_ROLES for role in interaction.user.roles)
    return app_commands.check(predicate)


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


class TicketView(discord.ui.View):
    def __init__(self, ticket_owner_id: int, claimed_by_id: int = None):
        super().__init__(timeout=None)
        self.ticket_owner_id = ticket_owner_id
        self.claimed_by_id = claimed_by_id
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.clear_items()

        close_btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id=f"ticket_close_{self.ticket_owner_id}",
        )
        close_btn.callback = self.close_callback
        self.add_item(close_btn)

        if self.claimed_by_id is None:
            claim_btn = discord.ui.Button(
                label="Claim",
                style=discord.ButtonStyle.success,
                emoji="✋",
                custom_id=f"ticket_claim_{self.ticket_owner_id}",
            )
            claim_btn.callback = self.claim_callback
            self.add_item(claim_btn)

    async def close_callback(self, interaction: discord.Interaction):
        if not any(role.id in STAFF_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ Only staff can close tickets.", ephemeral=True)
            return

        data = load_data()
        ch_id = str(interaction.channel.id)
        if ch_id in data["tickets"]:
            del data["tickets"][ch_id]
            save_data(data)

        await interaction.response.send_message("🔒 Closing ticket in 3 seconds...")
        await discord.utils.sleep_until(discord.utils.utcnow().__class__.utcnow() if False else __import__("asyncio").sleep(3))
        import asyncio
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="Ticket closed")

    async def claim_callback(self, interaction: discord.Interaction):
        if not any(role.id in STAFF_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ Only staff can claim tickets.", ephemeral=True)
            return

        self.claimed_by_id = interaction.user.id
        self._refresh_buttons()

        data = load_data()
        ch_id = str(interaction.channel.id)
        if ch_id in data["tickets"]:
            data["tickets"][ch_id]["claimed_by"] = interaction.user.id
            save_data(data)

        # Update the original ticket embed to show claimed status
        claimed_embed = discord.Embed(
            title="🎫 Ticket Claimed",
            description=f"{interaction.user.mention} is now handling this ticket.",
            color=EMBED_COLOR,
        )
        claimed_embed.set_image(url=BANNER_URL)
        await interaction.response.send_message(embed=claimed_embed)

        # Edit the original message to update the status field
        async for msg in interaction.channel.history(oldest_first=True, limit=5):
            if msg.author == bot.user and msg.embeds:
                old = msg.embeds[0]
                new_embed = discord.Embed(
                    title=old.title,
                    description=old.description,
                    color=EMBED_COLOR,
                )
                new_embed.set_image(url=BANNER_URL)
                new_embed.add_field(name="Status", value=f"Claimed by {interaction.user.mention}", inline=False)
                await msg.edit(embed=new_embed, view=self)
                break


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Channel",     description="Request a personal channel",   emoji="🌐"),
            discord.SelectOption(label="Marketplace", description="Marketplace related support",   emoji="🛒"),
            discord.SelectOption(label="Support",     description="General support request",       emoji="❓"),
            discord.SelectOption(label="Scammers",    description="Report a scammer or ratter",    emoji="🚨"),
            discord.SelectOption(label="Staff Apply", description="Apply for a staff position",    emoji="📋"),
        ]
        super().__init__(
            placeholder="Pick a category to open a ticket...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        guild = interaction.guild
        user = interaction.user

        user_tickets = [
            ch_id for ch_id, info in data["tickets"].items()
            if info.get("user_id") == user.id
        ]

        if len(user_tickets) >= MAX_TICKETS:
            await interaction.response.send_message(
                f"❌ You already have {MAX_TICKETS} open tickets. Please wait for one to be closed.",
                ephemeral=True,
            )
            return

        chosen = self.values[0]
        category_id = CATEGORY_MAP.get(chosen)
        category = guild.get_channel(category_id)
        if category is None:
            await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role_id in STAFF_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        # Increment ticket count
        data["ticket_count"] = data.get("ticket_count", 0) + 1
        ticket_number = data["ticket_count"]
        ticket_num_str = str(ticket_number).zfill(4)

        slug_map = {
            "Channel":     "channel",
            "Marketplace": "marketplace",
            "Support":     "support",
            "Scammers":    "scammer",
            "Staff Apply": "staff-apply",
        }
        channel_name = f"{user.name}-{slug_map[chosen]}"

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
        )

        data["tickets"][str(channel.id)] = {
            "user_id": user.id,
            "channel_name": channel.name,
            "ticket_number": ticket_number,
            "claimed_by": None,
        }
        save_data(data)

        opened_ts = int(time.time())

        embed = discord.Embed(
            title=f"{chosen} Ticket",
            description=(
                f"Ticket `#{ticket_num_str}` · opened <t:{opened_ts}:R>\n\n"
                f"Thanks for reaching out, {user.mention}! A staff member will be with you shortly."
            ),
            color=EMBED_COLOR,
        )
        embed.set_image(url=BANNER_URL)
        embed.set_footer(text="Paster Heaven Support")

        view = TicketView(ticket_owner_id=user.id)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Your **{chosen}** ticket has been created: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


@tree.command(name="ticket-panel", description="Send the support ticket panel", guild=discord.Object(id=GUILD_ID))
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(color=EMBED_COLOR)
    embed.title = "Paster Heaven Support"
    embed.description = (
        "-# Top provider for multible Sources with undetected futures\n\n"
        "❓ **How can we help?**\n"
        "Pick the category that fits your request and the right team will pick it up.\n\n"
        "📌  **Before you open a ticket**\n"
        "<a:51047animatedarrowwhite:1568294336876257300> Read the terms in <#1568284830297358366> before you open a ticket.\n"
        "<a:51047animatedarrowwhite:1568294336876257300> Pick the category that matches your request."
    )
    embed.set_image(url=BANNER_URL)
    view = TicketPanelView()
    await interaction.response.send_message(embed=embed, view=view)


@tree.command(name="channel-create", description="Create a channel for a user", guild=discord.Object(id=GUILD_ID))
@has_staff_role()
@app_commands.describe(user="The user to create a channel for", name="Channel name")
async def channel_create(interaction: discord.Interaction, user: discord.Member, name: str):
    guild = interaction.guild
    category = guild.get_channel(CATEGORY_MAP["Channel"])

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for role_id in STAFF_ROLES:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    channel = await guild.create_text_channel(
        name=f"🌐┃{name}",
        category=category,
        overwrites=overwrites,
    )

    embed = discord.Embed(description=f"✅ Channel created for {user.mention}: {channel.mention}", color=EMBED_COLOR)
    embed.set_image(url=BANNER_URL)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="channel-ping", description="Ping @here in your channel (once per 24 hours)", guild=discord.Object(id=GUILD_ID))
async def channel_ping(interaction: discord.Interaction):
    data = load_data()
    user_id = str(interaction.user.id)
    now = time.time()

    last_ping = data["ping_cooldowns"].get(user_id, 0)
    elapsed = now - last_ping

    if elapsed < PING_COOLDOWN_SECONDS:
        reset_ts = int(last_ping + PING_COOLDOWN_SECONDS)
        await interaction.response.send_message(
            f"⏳ 24 Hours Haven't Gone — <t:{reset_ts}:R> left",
            ephemeral=True,
        )
        return

    data["ping_cooldowns"][user_id] = now
    save_data(data)

    await interaction.response.send_message(f"@here — pinged by {interaction.user.mention}")


@tree.command(name="scammer-alert", description="Report a scammer or ratter", guild=discord.Object(id=GUILD_ID))
@has_mod_role()
@app_commands.describe(user="The user to report", reason="Reason: Scamming or Ratting")
@app_commands.choices(reason=[
    app_commands.Choice(name="Scamming", value="scamming"),
    app_commands.Choice(name="Ratting",  value="ratting"),
])
async def scammer_alert(interaction: discord.Interaction, user: discord.Member, reason: app_commands.Choice[str]):
    guild = interaction.guild

    if reason.value == "scamming":
        role  = guild.get_role(SCAMMER_ROLE_ID)
        label = "Scammer"
    else:
        role  = guild.get_role(RATTER_ROLE_ID)
        label = "Ratter"

    if role is None:
        await interaction.response.send_message("❌ Role not found.", ephemeral=True)
        return

    await user.add_roles(role, reason=f"Reported by {interaction.user} for {reason.value}")

    embed = discord.Embed(
        title=f"🚨 Scammer Alert — {label}",
        description=f"{user.mention} has been flagged as a **{label}**.\n**Reported by:** {interaction.user.mention}",
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_image(url=BANNER_URL)
    await interaction.response.send_message(embed=embed)


@tree.command(name="ticket-purge", description="Delete all active tickets", guild=discord.Object(id=GUILD_ID))
@has_staff_role()
async def ticket_purge(interaction: discord.Interaction):
    data = load_data()
    guild = interaction.guild
    deleted = 0

    await interaction.response.defer(ephemeral=True)

    for ch_id in list(data["tickets"].keys()):
        channel = guild.get_channel(int(ch_id))
        if channel:
            await channel.delete(reason="Ticket purge")
            deleted += 1
        del data["tickets"][ch_id]

    save_data(data)

    embed = discord.Embed(description=f"✅ Purged {deleted} ticket(s).", color=EMBED_COLOR)
    embed.set_image(url=BANNER_URL)
    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="ticket-rename", description="Rename the current ticket channel", guild=discord.Object(id=GUILD_ID))
@has_staff_role()
@app_commands.describe(name="New name for this ticket")
async def ticket_rename(interaction: discord.Interaction, name: str):
    data = load_data()
    channel = interaction.channel

    if str(channel.id) not in data["tickets"]:
        await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
        return

    safe_name = name.lower().replace(" ", "-")[:100]
    await channel.edit(name=safe_name)

    data["tickets"][str(channel.id)]["channel_name"] = safe_name
    save_data(data)

    embed = discord.Embed(description=f"✅ Ticket renamed to `{safe_name}`.", color=EMBED_COLOR)
    embed.set_image(url=BANNER_URL)
    await interaction.response.send_message(embed=embed)


@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user} — commands synced.")


bot.run(TOKEN)
