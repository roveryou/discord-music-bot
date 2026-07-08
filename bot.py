import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import re
import urllib.parse
import urllib.request

# Bot Konfiguration
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Musik-Queue für jeden Server
queues = {}

class MusicPlayer:
    def __init__(self):
        self.queue = []
        self.now_playing = None
        self.loop = False
        self.paused = False

def get_audio_url(query):
    """Sucht Musik auf YouTube und gibt die Audio-URL zurück"""
    query_string = urllib.parse.urlencode({"search_query": query})
    html_content = urllib.request.urlopen(
        "http://www.youtube.com/results?" + query_string
    )
    search_results = re.findall(r'/watch\?v=(.{11})', html_content.read().decode())
    
    if not search_results:
        return None, None
    
    video_id = search_results[0]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url'], info

async def play_next(ctx):
    """Spielt den nächsten Song in der Queue"""
    guild_id = ctx.guild.id
    
    if guild_id not in queues:
        return
    
    player = queues[guild_id]
    
    if player.loop and player.now_playing:
        # Wiederhole den aktuellen Song
        audio_url, info = player.now_playing
        player.queue.insert(0, (audio_url, info))
    
    if player.queue:
        audio_url, info = player.queue.pop(0)
        player.now_playing = (audio_url, info)
        
        voice_client = ctx.voice_client
        if voice_client:
            ffmpeg_options = {
                'options': '-vn',
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            }
            
            voice_client.play(
                discord.FFmpegPCMAudio(audio_url, **ffmpeg_options),
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(ctx), bot.loop
                )
            )
            
            # Sende die Musik-Info mit Buttons
            await send_music_info(ctx, info)
    else:
        player.now_playing = None

async def send_music_info(ctx, info):
    """Sendet die Musik-Info mit den 3 Buttons"""
    title = info.get('title', 'Unbekannter Titel')
    duration = info.get('duration', 0)
    minutes = duration // 60
    seconds = duration % 60
    thumbnail = info.get('thumbnail', '')
    
    # Buttons erstellen
    kick_button = discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        custom_id="kick",
        emoji="<:kick:1524557831200575608>"
    )
    
    play_pause_button = discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        custom_id="play_pause",
        emoji="<:kick:1524557831200575608>"
    )
    
    loop_button = discord.ui.Button(
        style=discord.ButtonStyle.secondary,
        custom_id="loop",
        emoji="<:widerholen:1524557584051474533>"
    )
    
    view = discord.ui.View()
    view.add_item(kick_button)
    view.add_item(play_pause_button)
    view.add_item(loop_button)
    
    embed = discord.Embed(
        title="🎵 Jetzt spielt:",
        description=f"**{title}**\n\n⏱️ Dauer: {minutes}:{seconds:02d}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=thumbnail)
    
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_ready():
    print(f"{bot.user} ist online!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Handle Button-Interaktionen"""
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        guild_id = interaction.guild_id
        
        if custom_id == "kick":
            # Bot aus dem Voice-Channel kicken
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.disconnect()
                await interaction.response.send_message(
                    "👋 Bot wurde aus dem Voice-Channel entfernt!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Bot ist in keinem Voice-Channel!",
                    ephemeral=True
                )
        
        elif custom_id == "play_pause":
            # Play/Pause umschalten
            if guild_id in queues:
                player = queues[guild_id]
                voice_client = interaction.guild.voice_client
                
                if voice_client and voice_client.is_playing():
                    voice_client.pause()
                    player.paused = True
                    await interaction.response.send_message(
                        "⏸️ Pausiert!",
                        ephemeral=True
                    )
                elif voice_client and voice_client.is_paused():
                    voice_client.resume()
                    player.paused = False
                    await interaction.response.send_message(
                        "▶️ Weiter!",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Es spielt gerade nichts!",
                        ephemeral=True
                    )
        
        elif custom_id == "loop":
            # Loop umschalten
            if guild_id in queues:
                player = queues[guild_id]
                player.loop = not player.loop
                
                status = "🔁 Wiederholung AN" if player.loop else "➡️ Wiederholung AUS"
                await interaction.response.send_message(
                    status,
                    ephemeral=True
                )

# Slash-Commands (/)
@bot.tree.command(name="play", description="Spiele einen Song ab")
@app_commands.describe(song="Name oder URL des Songs")
async def slash_play(interaction: discord.Interaction, song: str):
    await play_command(interaction, song)

@bot.tree.command(name="skip", description="Überspringe den aktuellen Song")
async def slash_skip(interaction: discord.Interaction):
    await skip_command(interaction)

@bot.tree.command(name="stop", description="Stoppe die Musik und leere die Queue")
async def slash_stop(interaction: discord.Interaction):
    await stop_command(interaction)

@bot.tree.command(name="queue", description="Zeige die aktuelle Warteschlange")
async def slash_queue(interaction: discord.Interaction):
    await queue_command(interaction)

@bot.tree.command(name="loop", description="Schalte Wiederholung ein/aus")
async def slash_loop(interaction: discord.Interaction):
    await loop_command(interaction)

# Prefix-Commands (!)
@bot.command(name="play")
async def prefix_play(ctx, *, song: str):
    await play_command(ctx, song)

@bot.command(name="skip")
async def prefix_skip(ctx):
    await skip_command(ctx)

@bot.command(name="stop")
async def prefix_stop(ctx):
    await stop_command(ctx)

@bot.command(name="queue")
async def prefix_queue(ctx):
    await queue_command(ctx)

@bot.command(name="loop")
async def prefix_loop(ctx):
    await loop_command(ctx)

@bot.command(name="help")
async def prefix_help(ctx):
    embed = discord.Embed(
        title="🤖 Musik Bot Hilfe",
        description="**Slash-Commands (/):**\n"
                    "`/play <Song>` - Spielt einen Song ab\n"
                    "`/skip` - Überspringt den Song\n"
                    "`/stop` - Stoppt die Musik\n"
                    "`/queue` - Zeigt die Warteschlange\n"
                    "`/loop` - Schaltet Wiederholung um\n\n"
                    "**Prefix-Commands (!):**\n"
                    "`!play <Song>` - Spielt einen Song ab\n"
                    "`!skip` - Überspringt den Song\n"
                    "`!stop` - Stoppt die Musik\n"
                    "`!queue` - Zeigt die Warteschlange\n"
                    "`!loop` - Schaltet Wiederholung um\n\n"
                    "**Buttons während der Wiedergabe:**\n"
                    "<:kick:1524557831200575608> - Bot aus Channel kicken\n"
                    "<:kick:1524557831200575608> - Play/Pause\n"
                    "<:widerholen:1524557584051474533> - Wiederholung",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

async def play_command(ctx, song: str):
    """Spielt einen Song ab (wird von Slash und Prefix verwendet)"""
    if not ctx.author.voice:
        await ctx.send("❌ Du musst in einem Voice-Channel sein!")
        return
    
    channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    
    # Voice-Client verbinden
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)
    
    # Queue initialisieren
    if guild_id not in queues:
        queues[guild_id] = MusicPlayer()
    
    # Song suchen
    await ctx.send(f"🔍 Suche nach `{song}`...")
    
    audio_url, info = get_audio_url(song)
    
    if audio_url is None:
        await ctx.send("❌ Konnte keinen Song finden!")
        return
    
    player = queues[guild_id]
    
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        player.queue.append((audio_url, info))
        await ctx.send(f"✅ `{info['title']}` wurde zur Queue hinzugefügt!")
    else:
        player.queue.append((audio_url, info))
        await play_next(ctx)

async def skip_command(ctx):
    """Überspringt den aktuellen Song"""
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("⏭️ Song übersprungen!")
    else:
        await ctx.send("❌ Es spielt gerade nichts!")

async def stop_command(ctx):
    """Stoppt die Musik und leert die Queue"""
    guild_id = ctx.guild.id
    
    if guild_id in queues:
        queues[guild_id].queue.clear()
        queues[guild_id].now_playing = None
    
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Musik gestoppt und Bot disconnected!")
    else:
        await ctx.send("❌ Bot ist in keinem Voice-Channel!")

async def queue_command(ctx):
    """Zeigt die Warteschlange"""
    guild_id = ctx.guild.id
    
    if guild_id not in queues or not queues[guild_id].queue:
        if queues.get(guild_id, None) and queues[guild_id].now_playing:
            await ctx.send(f"🎵 Aktuell spielt: **{queues[guild_id].now_playing[1]['title']}**\n📭 Keine weiteren Songs in der Queue.")
        else:
            await ctx.send("📭 Die Queue ist leer!")
        return
    
    player = queues[guild_id]
    queue_list = []
    
    for i, (_, info) in enumerate(player.queue[:10], 1):
        queue_list.append(f"`{i}.` {info['title']}")
    
    now_playing = f"🎵 **Jetzt spielt:** {player.now_playing[1]['title']}\n\n" if player.now_playing else ""
    
    embed = discord.Embed(
        title="📋 Warteschlange",
        description=now_playing + "\n".join(queue_list),
        color=discord.Color.blue()
    )
    
    if len(player.queue) > 10:
        embed.set_footer(text=f"Und {len(player.queue) - 10} weitere Songs...")
    
    await ctx.send(embed=embed)

async def loop_command(ctx):
    """Schaltet Loop um"""
    guild_id = ctx.guild.id
    
    if guild_id in queues:
        player = queues[guild_id]
        player.loop = not player.loop
        status = "🔁 Wiederholung AN" if player.loop else "➡️ Wiederholung AUS"
        await ctx.send(status)
    else:
        await ctx.send("❌ Es läuft keine Musik!")

# Bot starten
bot.run("DEIN_BOT_TOKEN_HIER")
