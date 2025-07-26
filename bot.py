import os
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import io
from typing import Optional
from replit import db
import ast
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuration constants
MONTHS = [
    "Martius", "Aprilis", "Maius", "Junius", "Quintilis", "Sextilis",
    "September", "October", "November", "December"
]
DAYS_OF_WEEK = [
    "Solinday", "Lunaday", "Terraday", "Aquaday", "Aerinday", "Liberae",
    "Morticaday"
]
DAYS_PER_MONTH = len(DAYS_OF_WEEK) * 4  # 28 days per month
CHANNEL_NAME = "calendar"
GUILD_ID = 1398618799023853729


# Persistent state using Replit DB
def load_state():
    raw = db.get("calendar_state", "{}")
    try:
        return ast.literal_eval(raw)
    except:
        return {}


def save_state():
    db["calendar_state"] = str(state)


state = load_state()

# Compute offset so that 11 Aprilis 1784 is Aerinday
OFFSET_BASE = (4 - ((11 - 1) % len(DAYS_OF_WEEK))) % len(DAYS_OF_WEEK)


# Function to draw calendar image
async def draw_calendar(year: int, month: int, day: int,
                        events: dict) -> io.BytesIO:
    width, height = 800, 600
    cell_w = width // len(DAYS_OF_WEEK)
    header_h = 50
    img = Image.new("RGB", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    font_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "Tangerine-Regular.ttf")
    if not os.path.isfile(font_path):
        raise FileNotFoundError(f"Font file not found at: {font_path}")
    font_large = ImageFont.truetype(font_path, size=18)
    font_small = ImageFont.truetype(font_path, size=24)

    for idx, name in enumerate(DAYS_OF_WEEK):
        bbox = draw.textbbox((0, 0), name, font=font_large)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = idx * cell_w + (cell_w - text_w) / 2
        y = (header_h - text_h) / 2
        draw.text((x, y), name, font=font_large, fill=(255, 255, 255))

    marker_idx = ((day - 1) + OFFSET_BASE) % len(DAYS_OF_WEEK)
    draw.rectangle(
        [marker_idx * cell_w, 0, (marker_idx + 1) * cell_w, header_h],
        outline=(255, 0, 0),
        width=3)

    ev_list = events.get((year, month, day), [])
    event_y = height - 180
    for ev in ev_list[:5]:
        bbox = draw.textbbox((0, 0), ev, font=font_small)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) / 2
        draw.text((x, event_y),
                  f"• {ev}",
                  font=font_small,
                  fill=(200, 200, 100))
        event_y += 30

    month_name = MONTHS[month - 1]
    title = f"Jaar: {year} | Maand: {month_name} ({month}) | Dag: {day}"
    bbox = draw.textbbox((0, 0), title, font=font_large)
    title_w, title_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    title_x = (width - title_w) / 2
    title_y = height - title_h - 10
    draw.text((title_x, title_y), title, font=font_large, fill=(200, 200, 200))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


app = Flask('')


@app.route('/')
def home():
    return "Bot draait nog!"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


class CalendarBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        try:
            # Clear any existing guild commands
            guild = discord.Object(id=GUILD_ID)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            print("Cleared existing guild commands")
            
            # Only sync globally (this takes longer but is more reliable)
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} global commands")
            print("Note: Global commands may take up to 1 hour to appear")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"Ingelogd als {self.user}")
        for guild in self.guilds:
            await self._ensure_state(guild)

    async def _ensure_state(self,
                            guild: discord.Guild,
                            force_redraw: bool = False):
        if guild.id not in state:
            state[guild.id] = {
                "year": 1784,
                "month": 2,
                "day": 11,
                "message_id": None,
                "events": {}
            }
            save_state()
        elif not force_redraw:
            return
        data = state[guild.id]
        buf = await draw_calendar(data["year"], data["month"], data["day"],
                                  data["events"])
        channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
        if channel is None:
            channel = await guild.create_text_channel(CHANNEL_NAME)
        if data["message_id"]:
            try:
                old = await channel.fetch_message(data["message_id"])
                await old.delete()
            except:
                pass
        msg = await channel.send(
            file=discord.File(buf, filename="calendar.png"))
        data["message_id"] = msg.id
        save_state()


bot = CalendarBot()


@bot.tree.command(name="set_date",
                  description="Set the in-game calendar date.")
@app_commands.describe(year="Year to set",
                       month="Month number (1-10)",
                       day="Day number (1-28)")
async def set_date(interaction: discord.Interaction, year: int, month: int,
                   day: int):
    if not (1 <= month <= len(MONTHS)) or not (1 <= day <= DAYS_PER_MONTH):
        await interaction.response.send_message("Ongeldige datum.",
                                                ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    state[interaction.guild.id].update({
        "year": year,
        "month": month,
        "day": day
    })
    save_state()
    await bot._ensure_state(interaction.guild)
    await interaction.followup.send("✅ Datum aangepast.", ephemeral=True)
    await interaction.channel.send(
        f"📆 **Datum aangepast:**\n🗓️ {day} {MONTHS[month - 1]} {year}")


@bot.tree.command(name="add_event",
                  description="Add an event to the current or a specific day.")
@app_commands.describe(
    event="Event description text",
    day="(Optional) Day number (1-28) [requires month]",
    month="(Optional) Month number (1-10) [required if day is set]",
    year="(Optional) Year of the event")
async def add_event(interaction: discord.Interaction,
                    event: str,
                    day: Optional[int] = None,
                    month: Optional[int] = None,
                    year: Optional[int] = None):
    await interaction.response.defer(ephemeral=True)
    data = state[interaction.guild.id]

    if (day is not None and month is None):
        return await interaction.followup.send(
            "Als je een dag opgeeft, moet je ook een maand opgeven.",
            ephemeral=True)

    d = day if day is not None else data["day"]
    m = month if month is not None else data["month"]
    y = year if year is not None else data["year"]

    if not (1 <= m <= len(MONTHS)) or not (1 <= d <= DAYS_PER_MONTH):
        return await interaction.followup.send("Ongeldige datum.",
                                               ephemeral=True)

    key = (y, m, d)
    data["events"].setdefault(key, []).append(event)
    save_state()
    await bot._ensure_state(interaction.guild)

    await interaction.followup.send(f"✅ Event toegevoegd op {d}/{m}/{y}.",
                                    ephemeral=True)
    await interaction.channel.send(
        f"📅 **Nieuw event toegevoegd!**\n🗓️ {d} {MONTHS[m - 1]} {y}\n📌 *{event}*"
    )


@bot.tree.command(name="remove_event",
                  description="Verwijder een bestaand event uit de kalender.")
async def remove_event(interaction: discord.Interaction):
    data = state.get(interaction.guild.id, {}).get("events", {})
    all_options = []

    for (y, m, d), evs in data.items():
        for idx, ev in enumerate(evs):
            label = f"{d} {MONTHS[m - 1]} {y}: {ev}"
            value = f"{y}|{m}|{d}|{idx}"
            all_options.append(
                discord.SelectOption(label=label[:100], value=value))

    if not all_options:
        await interaction.response.send_message(
            "Er zijn momenteel geen events om te verwijderen.", ephemeral=True)
        return

    class RemoveEventView(discord.ui.View):

        @discord.ui.select(placeholder="Kies een event om te verwijderen",
                           options=all_options)
        async def select_callback(self,
                                  interaction_select: discord.Interaction,
                                  select: discord.ui.Select):
            selected = select.values[0]
            y, m, d, idx = map(int, selected.split("|"))
            key = (y, m, d)
            removed_event = state[interaction.guild.id]["events"][key].pop(idx)
            if not state[interaction.guild.id]["events"][key]:
                del state[interaction.guild.id]["events"][key]
            save_state()
            await bot._ensure_state(interaction.guild)
            await interaction_select.response.send_message(
                "✅ Event verwijderd.", ephemeral=True)
            await interaction.channel.send(
                f"🗑️ **Event verwijderd:**\n🗓️ {d} {MONTHS[m - 1]} {y}\n❌ *{removed_event}*"
            )

    await interaction.response.send_message(
        "Selecteer een event om te verwijderen:",
        view=RemoveEventView(),
        ephemeral=True)


@bot.tree.command(name="show_calendar",
                  description="Show the current in-game calendar.")
async def show_calendar(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
        await bot._ensure_state(interaction.guild, force_redraw=True)
        await interaction.followup.send("✅ Kalender bijgewerkt.", ephemeral=True)
    except discord.NotFound:
        # Interaction has expired, but we can still update the calendar
        await bot._ensure_state(interaction.guild, force_redraw=True)
        print("Interaction expired, but calendar was updated successfully.")
    except Exception as e:
        print(f"Error in show_calendar: {e}")
        try:
            await interaction.followup.send("❌ Er is een fout opgetreden bij het bijwerken van de kalender.", ephemeral=True)
        except:
            pass


@bot.tree.command(name="list_events",
                  description="Choose how you want to list planned events.")
async def list_events(interaction: discord.Interaction):

    class EventListView(discord.ui.View):

        @discord.ui.select(
            placeholder="Kies een weergaveoptie",
            options=[
                discord.SelectOption(label="Alles",
                                     value="all",
                                     description="Toon alle geplande events."),
                discord.SelectOption(
                    label="Deze maand",
                    value="current",
                    description="Toon events van deze maand."),
                discord.SelectOption(
                    label="Volgende maand",
                    value="next",
                    description="Toon events van volgende maand."),
                discord.SelectOption(label="Selecteer maand",
                                     value="select",
                                     description="Voer zelf maand en jaar in.")
            ])
        async def select_callback(self,
                                  interaction_select: discord.Interaction,
                                  select: discord.ui.Select):
            value = select.values[0]
            data = state[interaction.guild.id]
            current_year = data["year"]
            current_month = data["month"]

            if value == "all":
                all_events = data["events"]
                if not all_events:
                    await interaction.channel.send("📭 Geen geplande events.")
                    await interaction_select.response.send_message(
                        "📬 Geen events gevonden.", ephemeral=True)
                    return
                grouped = {}
                for (y, m, d), evs in all_events.items():
                    grouped.setdefault((y, m), []).append((d, evs))
                message = "📅 Alle geplande events:\n"
                for (y, m), days in sorted(grouped.items()):
                    message += f"\n{MONTHS[m - 1]} {y}:\n"
                    for d, evs in sorted(days):
                        evs_txt = "\n".join(f"• {e}" for e in evs)
                        message += f"  {d} {MONTHS[m - 1]}:\n{evs_txt}\n"
                await interaction.channel.send(message)
                await interaction_select.response.send_message(
                    "📬 Events weergegeven in dit kanaal.", ephemeral=True)

            elif value in ["current", "next"]:
                year = current_year
                month = current_month + 1 if value == "next" else current_month
                if month > len(MONTHS):
                    month = 1
                    year += 1
                message = f"📆 Events in {MONTHS[month - 1]} {year}:\n"
                found = False
                for d in range(1, DAYS_PER_MONTH + 1):
                    key = (year, month, d)
                    ev_list = data["events"].get(key, [])
                    if ev_list:
                        found = True
                        evs = "\n".join(f"  • {e}" for e in ev_list)
                        message += f"{d} {MONTHS[month - 1]}:\n{evs}\n"
                if not found:
                    message += "Geen geplande events."
                await interaction.channel.send(message)
                await interaction_select.response.send_message(
                    "📬 Events weergegeven in dit kanaal.", ephemeral=True)

            elif value == "select":
                await interaction_select.response.send_message(
                    "Gebruik `/list_events_maand year:1784 month:4` om een specifieke maand op te vragen.",
                    ephemeral=True)

    await interaction.response.send_message(
        "Hoe wil je geplande events bekijken?",
        view=EventListView(),
        ephemeral=True)


@bot.tree.command(name="next_day", description="Advance to the next day.")
async def next_day(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = state[interaction.guild.id]
    data["day"] = data["day"] % DAYS_PER_MONTH + 1
    if data["day"] == 1:
        data["month"] = data["month"] % len(MONTHS) + 1
        if data["month"] == 1:
            data["year"] += 1
    save_state()
    await bot._ensure_state(interaction.guild)
    await interaction.followup.send("Volgende dag.")


@bot.tree.command(name="prev_day", description="Move back one day.")
async def prev_day(interaction: discord.Interaction):
    data = state[interaction.guild.id]
    data["day"] -= 1
    if data["day"] < 1:
        data["month"] -= 1
        if data["month"] < 1:
            data["month"] = len(MONTHS)
            data["year"] -= 1
        data["day"] = DAYS_PER_MONTH
    save_state()
    await bot._ensure_state(interaction.guild)
    await interaction.response.send_message("Vorige dag.", ephemeral=True)


if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
