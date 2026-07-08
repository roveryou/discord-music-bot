import discord
from discord import app_commands
from discord.ext import commands
import wavelink
from config import *
import datetime

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ─────────────────────────────────────────────
#  BOT READY / LAVALINK SETUP
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[✓] Bot eingeloggt als {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"[✓] {len(synced)} Slash-Commands synced")
    except Exception as e:
        print(f"[✗] Sync-Fehler: {e}")

    # Lavalink Node verbinden
    node = wavelink.Node(
        uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
        password=LAVALINK_PASSWORD,
    )
    await wavelink.Pool.connect(client=bot, nodes=[node])
    print("[✓] Lavalink verbunden")


# ─────────────────────────────────────────────
#  MUSIK VIEW (Buttons + Embed)
# ─────────────────────────────────────────────
class MusicView(discord.ui.View):
    def __init__(self, player, track):
        super().__init__(timeout=None)
        self.player = player
        self.track = track
        self.is_paused = False

    @discord.ui.button(emoji=EMOJI_KICK, style=discord.ButtonStyle.danger, custom_id="kick")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bot verlässt den Channel"""
        player = self.player
        if interaction.user.voice and interaction.user.voice.channel == player.channel:
            await player.disconnect()
            await interaction.response.edit_message(
                content="👋 Bot hat den Channel verlassen.",
                embed=None,
                view=None
            )
        else:
            await interaction.response.send_message("Du bist nicht in meinem Voice-Channel!", ephemeral=True)

    @discord.ui.button(emoji=EMOJI_PAUSE, style=discord.ButtonStyle.secondary, custom_id="pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Play / Pause"""
        player = self.player
        if interaction.user.voice and interaction.user.voice.channel == player.channel:
            if player.paused:
                await player.resume()
                self.is_paused = False
                button.style = discord.ButtonStyle.secondary
                await interaction.response.edit_message(view=self)
            else:
                await player.pause()
                self.is_paused = True
                button.style = discord.ButtonStyle.success
                await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("Du bist nicht in meinem Voice-Channel!", ephemeral=True)

    @discord.ui.button(emoji=EMOJI_REPEAT, style=discord.ButtonStyle.primary, custom_id="repeat")
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Wiederholen des aktuellen Tracks"""
        player = self.player
        if interaction.user.voice and interaction.user.voice.channel == player.channel:
            current = player.current
            if current:
                await player.play(current)
                await interaction.response.send_message("🔁 Track wird wiederholt!", ephemeral=True)
            else:
                await interaction.response.send_message("Kein Track zum Wiederholen.", ephemeral=True)
        else:
            await interaction.response.send_message("Du bist nicht in meinem Voice-Channel!", ephemeral=True)


# ─────────────────────────────────────────────
#  EMBED BAUEN (mit Album-Art, Fortschritt, etc.)
# ─────────────────────────────────────────────
def build_music_embed(track):
    duration = datetime.timedelta(milliseconds=track.length) if track.length else "🔴 Live"
    if isinstance(duration, datetime.timedelta):
        duration_str = str(duration).split(".")[0]
    else:
        duration_str = duration

    embed = discord.Embed(
        title="🎵 **Jetzt läuft**",
        description=f"**{track.title}**",
        color=discord.Color.from_rgb(30, 215, 96),  # Spotify Grün
    )
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)
    if track.author:
        embed.add_field(name="👤 Künstler", value=track.author, inline=True)
    embed.add_field(name="⏱ Dauer", value=duration_str, inline=True)
    if track.uri:
        embed.add_field(name="🔗 Link", value=f"[Öffnen]({track.uri})", inline=False)
    embed.set_footer(text=f"Angefordert von ...", icon_url=bot.user.display_avatar.url)
    return embed


# ─────────────────────────────────────────────
#  EVENT: TRACK START (Buttons + Embed senden)
# ─────────────────────────────────────────────
@bot.listen()
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player = payload.player
    track = payload.track

    if not player or not track:
        return

    embed = build_music_embed(track)
    view = MusicView(player, track)

    if hasattr(player, "message") and player.message:
        try:
            await player.message.edit(embed=embed, view=view)
        except:
            player.message = await player.channel.send(embed=embed, view=view)
    else:
        player.message = await player.channel.send(embed=embed, view=view)


# ─────────────────────────────────────────────
#  SLASH-COMMAND: /play
# ─────────────────────────────────────────────
@bot.tree.command(name="play", description="Spiele einen Song ab (Name oder URL)")
@app_commands.describe(suche="Songname oder YouTube/Spotify URL")
async def slash_play(interaction: discord.Interaction, suche: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send("Du bist in keinem Voice-Channel!", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    player = await channel.connect(cls=wavelink.Player)
    player.channel = channel

    tracks = await wavelink.Playable.search(suche)
    if not tracks:
        await interaction.followup.send("❌ Keine Ergebnisse gefunden.", ephemeral=True)
        return

    track = tracks[0]
    await player.play(track)

    embed = build_music_embed(track)
    view = MusicView(player, track)

    await interaction.followup.send(embed=embed, view=view)
    player.message = await interaction.original_response()


# ─────────────────────────────────────────────
#  PREFIX-COMMAND: !play
# ─────────────────────────────────────────────
@bot.command(name="play")
async def prefix_play(ctx: commands.Context, *, suche: str):
    if not ctx.author.voice:
        await ctx.send("Du bist in keinem Voice-Channel!", delete_after=10)
        return

    channel = ctx.author.voice.channel
    player = await channel.connect(cls=wavelink.Player)
    player.channel = channel

    tracks = await wavelink.Playable.search(suche)
    if not tracks:
        await ctx.send("❌ Keine Ergebnisse gefunden.", delete_after=10)
        return

    track = tracks[0]
    await player.play(track)

    embed = build_music_embed(track)
    view = MusicView(player, track)

    # Lösche die Command-Nachricht des Users für Sauberkeit
    try:
        await ctx.message.delete()
    except:
        pass

    msg = await ctx.send(embed=embed, view=view)
    player.message = msg


# ─────────────────────────────────────────────
#  !help / /help
# ─────────────────────────────────────────────
@bot.command(name="help")
async def prefix_help(ctx: commands.Context):
    embed = discord.Embed(
        title="🎵 Musik Bot Hilfe",
        description="Hier sind alle Befehle:",
        color=discord.Color.green()
    )
    embed.add_field(name="**Slash-Commands**", value="""
`/play <Name/URL>` - Spiele Musik ab
`/help` - Zeigt diese Hilfe
""", inline=False)
    embed.add_field(name="**Prefix-Commands**", value="""
`!play <Name/URL>` - Spiele Musik ab
`!help` - Zeigt diese Hilfe
""", inline=False)
    embed.add_field(name="**Buttons**", value=f"""
{EMOJI_KICK} = Bot verlässt Channel
{EMOJI_PAUSE} = Play / Pause
{EMOJI_REPEAT} = Track wiederholen
""", inline=False)
    embed.set_footer(text="Erstellt mit ❤️ | HackerAI")
    await ctx.send(embed=embed)


@bot.tree.command(name="help", description="Zeigt die Hilfe an")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Musik Bot Hilfe",
        description="Hier sind alle Befehle:",
        color=discord.Color.green()
    )
    embed.add_field(name="**Slash-Commands**", value="""
`/play <Name/URL>` - Spiele Musik ab
`/help` - Zeigt diese Hilfe
""", inline=False)
    embed.add_field(name="**Prefix-Commands**", value="""
`!play <Name/URL>` - Spiele Musik ab
`!help` - Zeigt diese Hilfe
""", inline=False)
    embed.add_field(name="**Buttons**", value=f"""
{EMOJI_KICK} = Bot verlässt Channel
{EMOJI_PAUSE} = Play / Pause
{EMOJI_REPEAT} = Track wiederholen
""", inline=False)
    embed.set_footer(text="Erstellt mit ❤️ | HackerAI")
    await interaction.response.send_message(embed=embed)


# ─────────────────────────────────────────────
#  BOT START
# ─────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN)
