import discord
from discord.ext import commands
import os
import datetime
import pytz 
import asyncio
import discord.http 
import json
import urllib.request
import urllib.parse 
import aiohttp 
import subprocess 
import time
import io
import math
import yt_dlp
import traceback
import wave 
import edge_tts 
import random 
import logging

# Enable discord voice logging only (gateway is too verbose)
logging.basicConfig(level=logging.WARNING)
logging.getLogger('discord.voice_client').setLevel(logging.DEBUG)

# ==========================================
# ☢️ THE "NUCLEAR" PATCH v96 (+Trim Feature Added)
# ==========================================

# 1. Login Patch (RESTORED TO SCRIPT 1 - SIMPLE UA)
async def patched_login(self, token):
    self.token = token.strip().strip('"')
    self._token_type = ""
    
    if not hasattr(self, '_HTTPClient__session') or getattr(self, '_HTTPClient__session').__class__.__name__ == '_MissingSentinel':
        self._HTTPClient__session = aiohttp.ClientSession()

    req = urllib.request.Request("https://discord.com/api/v9/users/@me")
    req.add_header("Authorization", self.token)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise discord.LoginFailure("Invalid User Token.")
        raise

# 2. DIRECT SEND (RESTORED TO SCRIPT 1 - STABLE UPLOAD)
async def direct_send(self, content=None, **kwargs):
    if hasattr(self, 'channel'):
        channel_id = self.channel.id 
    elif hasattr(self, 'id'):
        channel_id = self.id 
    else:
        return

    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    
    global bot
    session = bot.http._HTTPClient__session
    
    headers = {
        "Authorization": bot.http.token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    files_to_send = []
    if kwargs.get('files'):
        files_to_send.extend(kwargs['files'])
    if kwargs.get('file'):
        files_to_send.append(kwargs['file'])

    if files_to_send:
        data = aiohttp.FormData()
        payload = {'content': str(content) if content else ""}
        data.add_field('payload_json', json.dumps(payload))
        
        for i, file in enumerate(files_to_send):
            file.fp.seek(0)
            data.add_field(
                f'files[{i}]', 
                file.fp, 
                filename=file.filename,
                content_type='application/octet-stream' 
            )
        
        headers.pop("Content-Type", None) 
        
        try:
            async with session.post(url, data=data, headers=headers) as resp:
                if resp.status not in [200, 201]:
                    print(f"❌ Upload Failed: {resp.status}")
                return await resp.json()
        except Exception as e:
            print(f"❌ Upload Error: {e}")
            return None
    else:
        headers["Content-Type"] = "application/json"
        payload = {}
        if content:
            payload['content'] = str(content)
            
        async with session.post(url, json=payload, headers=headers) as resp:
            return await resp.json()

# 3. Request Patch
original_request = discord.http.HTTPClient.request
async def patched_request(self, route, **kwargs):
    headers = kwargs.get('headers', {})
    headers['Authorization'] = self.token
    headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    kwargs['headers'] = headers
    
    try:
        return await original_request(self, route, **kwargs)
    except discord.HTTPException as e:
        if e.status == 401:
            return []
        raise e

# 4. Helper: DIRECT NAME FETCH
def fetch_real_name_sync(user_id, token):
    url = f"https://discord.com/api/v9/users/{user_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", token)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get('global_name') or data.get('username')
    except:
        return f"User_{user_id}"

# Apply Patches
discord.http.HTTPClient.static_login = patched_login
discord.http.HTTPClient.request = patched_request
discord.abc.Messageable.send = direct_send

# 5.5 Voice-Only UA Patch: Swap User-Agent to browser ONLY for voice WS connections.
#     Setting user_agent globally breaks GET /gateway (403 error 40333).
#     This patch temporarily swaps UA during DiscordVoiceWebSocket.from_client only.
import discord.gateway

# --- DAVE PROTOCOL FIX ---
# Close code 4017 = "DAVE (E2EE) protocol required". Since March 2026, ALL Discord
# voice connections MUST include max_dave_protocol_version in the IDENTIFY payload.
# py-cord doesn't do this for self_bot accounts, so Discord rejects with 4017.
# Fix: Patch the voice IDENTIFY to include max_dave_protocol_version: 1

_orig_voice_identify = discord.gateway.DiscordVoiceWebSocket.identify

async def _patched_voice_identify(self):
    """Include max_dave_protocol_version in voice IDENTIFY for DAVE compliance."""
    state = self._connection
    payload = {
        'op': self.IDENTIFY,
        'd': {
            'server_id': str(state.guild.id),
            'user_id': str(state.user.id),
            'session_id': state.session_id,
            'token': state.token,
            'max_dave_protocol_version': 1,
        }
    }
    print(f"[DAVE] Sending voice IDENTIFY with max_dave_protocol_version: 1")
    await self.send_as_json(payload)

discord.gateway.DiscordVoiceWebSocket.identify = _patched_voice_identify

# Also patch the voice poll_event to handle DAVE-specific opcodes (21-30)
# that py-cord doesn't know about. Without this, unknown opcodes cause crashes.
_orig_voice_poll_event = discord.gateway.DiscordVoiceWebSocket.poll_event

async def _patched_voice_poll_event(self):
    """Handle DAVE-specific opcodes gracefully."""
    try:
        await _orig_voice_poll_event(self)
    except KeyError as e:
        # py-cord hits KeyError on unknown opcodes (DAVE ops 21-30)
        print(f"[DAVE] Ignoring unknown voice opcode: {e}")
    except Exception as e:
        if 'dave' in str(e).lower() or 'unknown op' in str(e).lower():
            print(f"[DAVE] Handled DAVE-related error: {e}")
        else:
            raise

discord.gateway.DiscordVoiceWebSocket.poll_event = _patched_voice_poll_event

# UA swap for voice connections
_orig_voice_from_client = discord.gateway.DiscordVoiceWebSocket.from_client

@classmethod
async def _patched_voice_from_client(cls, client, *, resume=False):
    """Swap UA to browser-like for voice WS connection only."""
    http = client._state.http
    orig_ua = http.user_agent
    http.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    try:
        return await _orig_voice_from_client(client, resume=resume)
    finally:
        http.user_agent = orig_ua

discord.gateway.DiscordVoiceWebSocket.from_client = _patched_voice_from_client

# 6. Voice Client Patch: Prevent poll_voice_ws crash from auto-disconnecting
#    In self_bot mode, vc.ws is '_MissingSentinel' so poll_voice_ws crashes.
#    The crash triggers py-cord's internal cleanup which disconnects the VC.
#    This patch catches the crash and sleeps silently instead.
_original_poll_voice_ws = discord.VoiceClient.poll_voice_ws

async def _safe_poll_voice_ws(self, reconnect=True):
    """Self-bot safe voice WS poller - prevents disconnect on missing WS"""
    while True:
        try:
            if not hasattr(self.ws, 'poll_event'):
                # WS is _MissingSentinel - just sleep, don't crash
                await asyncio.sleep(30)
                continue
            await self.ws.poll_event()
        except AttributeError:
            # _MissingSentinel has no poll_event
            await asyncio.sleep(30)
        except Exception as exc:
            if not reconnect:
                raise
            await asyncio.sleep(5)

discord.VoiceClient.poll_voice_ws = _safe_poll_voice_ws

# ==========================================
# 🎵 CUSTOM AUDIO ENGINE (ANTI-STUTTER + SYNC)
# ==========================================
BOT_PCM_BUFFER = io.BytesIO()
IS_RECORDING_BOT = False

class RecordableFFmpegPCMAudio(discord.FFmpegPCMAudio):
    def read(self):
        data = super().read()
        
        if IS_RECORDING_BOT and SESSION_START_TIME and data:
            try:
                # 1. Calculate bytes needed
                elapsed = datetime.datetime.now() - SESSION_START_TIME
                expected_bytes = int(elapsed.total_seconds() * 192000) 
                expected_bytes -= (expected_bytes % 4) 
                
                # 2. Check current buffer
                current_bytes = BOT_PCM_BUFFER.tell()
                padding_needed = expected_bytes - current_bytes
                
                # 3. Anti-Stutter Logic (Threshold = 15000 bytes / ~75ms)
                if padding_needed > 15000:
                    if padding_needed < 100000000: 
                        BOT_PCM_BUFFER.write(b'\x00' * padding_needed)
                
                # 4. Write audio
                BOT_PCM_BUFFER.write(data)
            except:
                pass 
                
        return data

# ==========================================
# 🧠 SYNC SINK (ANTI-STUTTER)
# ==========================================
class SyncWaveSink(discord.sinks.WaveSink):
    def __init__(self):
        super().__init__()
        self.start_time = None
        self.bytes_per_second = 192000

    def write(self, data, user_id):
        if self.start_time is None:
            self.start_time = time.time()

        if user_id not in self.audio_data:
            self.audio_data[user_id] = discord.sinks.core.AudioData(io.BytesIO())

        file = self.audio_data[user_id].file
        
        elapsed_seconds = time.time() - self.start_time
        expected_bytes = int(elapsed_seconds * self.bytes_per_second)
        expected_bytes = expected_bytes - (expected_bytes % 4) 
        
        current_bytes = file.tell()
        padding_needed = expected_bytes - current_bytes
        
        # Anti-Stutter Logic (Threshold = 15000 bytes)
        if padding_needed > 15000: 
            padding_needed = padding_needed - (padding_needed % 4)
            chunk_size = min(padding_needed, 1920000) 
            file.write(b'\x00' * chunk_size)
            
        file.write(data)

# ==========================================
# 🎵 SAFE MERGE & SPLIT (RECORDER STABLE)
# ==========================================
async def split_audio_if_large(filepath, limit_mb=9):
    if not os.path.exists(filepath): return []
    
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb <= limit_mb:
        return [filepath]

    chunk_duration = 500 
    
    base_name = filepath.rsplit('.', 1)[0]
    ext = filepath.rsplit('.', 1)[1]
    output_pattern = f"{base_name}_part%03d.{ext}"
    
    cmd = [
        'ffmpeg', '-y', '-i', filepath,
        '-f', 'segment', 
        '-segment_time', str(chunk_duration), 
        '-c', 'copy', 
        output_pattern
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    
    parts = []
    i = 0
    while True:
        part_name = f"{base_name}_part{i:03d}.{ext}"
        if os.path.exists(part_name):
            parts.append(part_name)
            i += 1
        else:
            break
            
    return parts

# === NEW: SMART VIDEO SPLITTER & COMPRESSOR FOR +UPLOAD ===
async def get_media_duration(filename):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filename]
    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = await process.communicate()
        return float(out.decode().strip())
    except:
        return None

async def compress_video(filepath, target_height):
    base, ext = os.path.splitext(filepath)
    output_path = f"{base}_compressed_{target_height}p{ext}"
    
    # FFmpeg scale command: Scale height, maintain aspect ratio, CRF 28 (compressed)
    cmd = [
        'ffmpeg', '-y', 
        '-i', filepath,
        '-vf', f'scale=-2:{target_height}', 
        '-c:v', 'libx264', 
        '-crf', '28', 
        '-preset', 'fast', 
        '-c:a', 'copy', 
        output_path
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path
    return filepath # Return original if fail

async def split_media_smart(filepath, limit_mb=8.5): # 8.5MB to be safe for 9MB limit
    if not os.path.exists(filepath): return []
    size = os.path.getsize(filepath) / (1024 * 1024)
    if size <= limit_mb: return [filepath]
    
    duration = await get_media_duration(filepath)
    if not duration: return [filepath] 
    
    segment_time = (limit_mb / size) * duration
    
    base, ext = os.path.splitext(filepath)
    output_pattern = f"{base}_part%03d{ext}"
    
    cmd = [
        'ffmpeg', '-y', '-i', filepath,
        '-c', 'copy',
        '-f', 'segment',
        '-segment_time', str(segment_time),
        '-reset_timestamps', '1',
        output_pattern
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    
    parts = []
    i = 0
    while True:
        part = f"{base}_part{i:03d}{ext}"
        if os.path.exists(part):
            parts.append(part)
            i += 1
        else:
            break
    return parts

async def convert_and_merge(file_list, output_filename, duration):
    if not file_list: return None
    
    cmd = ['ffmpeg', '-y']
    for f in file_list:
        cmd.extend(['-i', f])
    
    if len(file_list) == 1:
         cmd.extend([
            '-af', 'apad', 
            '-t', str(duration),
            '-b:a', '128k', 
            output_filename
        ])
    else:
        cmd.extend([
            '-filter_complex', 
            f'amix=inputs={len(file_list)}:duration=longest:dropout_transition=0:normalize=0,apad', 
            '-t', str(duration),
            '-b:a', '128k', 
            output_filename
        ])
        
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return output_filename

async def convert_wav_to_mp3_padded(wav_filename, mp3_filename, duration):
    cmd = [
        'ffmpeg', '-y', 
        '-i', wav_filename, 
        '-af', 'apad', 
        '-t', str(duration),
        '-b:a', '128k', 
        mp3_filename
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()
    return mp3_filename

# --- Helper for Time Parsing ---
def parse_time_str(t_str):
    try:
        parts = list(map(int, t_str.split(':')))
        if len(parts) == 1: return parts[0] # seconds only
        if len(parts) == 2: return parts[0] * 60 + parts[1] # MM:SS
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2] # HH:MM:SS
    except:
        return None
    return None

# ==========================================

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
SECRET_KEY = os.getenv('KEY')
if SECRET_KEY:
    SECRET_KEY = SECRET_KEY.strip()

AUTHORIZED_USERS = set() 
MERGE_MODE = False
SESSION_START_TIME = None 
AUTO_REC_MODE = None 

# MEMORY FOR STABLE FOLLOW
CURRENT_RECORDING_CONFIG = {"merge": False, "bot_audio": False}

# AUDIO FX GLOBALS
VOLUME_LEVEL = 1.0 
BASS_ACTIVE = False
FOLLOW_MODE = False
GLOBAL_MUTE = False
GLOBAL_DEAF = False

# TTS SETTINGS (FIXED ARAB VOICES)
TTS_VOICE = "en-IN-NeerjaNeural" # Default
VOICE_MAP = {
    "default": "en-IN-NeerjaNeural",
    "india_male": "en-IN-PrabhatNeural",
    "us_female": "en-US-JennyNeural",
    "us_male": "en-US-GuyNeural",
    "uk_female": "en-GB-SoniaNeural",
    "uk_male": "en-GB-RyanNeural",
    "arab_female": "ar-EG-SalmaNeural", 
    "arab_male": "ar-EG-ShakirNeural"   
}

# --- SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True 
intents.voice_states = True 

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

# --- 🔒 THE GATEKEEPER ---
@bot.check
async def global_login_check(ctx):
    if ctx.command.name == 'login': return True
    if ctx.author.id in AUTHORIZED_USERS: return True
    await ctx.send("❌ **Access Denied.** Please use `+login <key>` first.")
    return False

# --- 😊 FRIENDLY ERROR HANDLER ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure): return
    if isinstance(error, commands.CommandNotFound): return
    
    if isinstance(error, commands.CommandInvokeError):
        original = error.original
        if isinstance(original, discord.Forbidden):
            return await ctx.send("❌ I don't have permission to join/speak in that channel.")
        if isinstance(original, discord.ClientException):
            return await ctx.send(f"⚠️ {str(original)}")
    
    print(f"⚠️ UNHANDLED ERROR: {error}")
    await ctx.send("❌ An error occurred while executing the command.")

# --- 🔍 VOICE STATE DEBUG LOGGER ---
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.user.id:
        return  # Only track the bot's own voice state
    
    before_ch = before.channel.name if before.channel else "None"
    after_ch = after.channel.name if after.channel else "None"
    
    if before.channel and not after.channel:
        print(f"⚠️ [VOICE DEBUG] Bot DISCONNECTED from '{before_ch}'")
        print(f"   voice_clients count: {len(bot.voice_clients)}")
        traceback.print_stack()
    elif not before.channel and after.channel:
        print(f"✅ [VOICE DEBUG] Bot CONNECTED to '{after_ch}'")
    elif before.channel != after.channel:
        print(f"🔄 [VOICE DEBUG] Bot MOVED: '{before_ch}' → '{after_ch}'")

# --- HELPER FUNCTIONS ---
async def finished_callback(sink, dest_channel, *args):
    global SESSION_START_TIME, IS_RECORDING_BOT, BOT_PCM_BUFFER
    
    IS_RECORDING_BOT = False
    
    if SESSION_START_TIME:
        total_duration = (datetime.datetime.now() - SESSION_START_TIME).total_seconds()
    else:
        total_duration = 10 
        
    try:
        await dest_channel.send(f"✅ **Recording finished.** Duration: {int(total_duration)}s. Processing...")
    except Exception as e:
        print(f"Recording callback send error (non-critical): {e}")
    
    temp_wavs = [] 
    real_names = [] 
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    time_str = now.strftime("%I-%M-%p")

    i = 0
    for user_id, audio in sink.audio_data.items():
        username = None
        try:
            if hasattr(dest_channel, 'guild'):
                member = dest_channel.guild.get_member(user_id)
                if member: username = member.display_name
        except: pass
        if not username:
            user = bot.get_user(user_id)
            if user: username = user.display_name or user.name
        if not username:
            username = await asyncio.to_thread(fetch_real_name_sync, user_id, bot.http.token)

        safe_username = "".join(x for x in username if x.isalnum() or x in "._- ")
        real_name = f"{safe_username}_{time_str}.mp3"
        real_names.append(real_name)

        temp_name = f"input_{i}.wav"
        with open(temp_name, "wb") as f:
            f.write(audio.file.getbuffer())
        temp_wavs.append(temp_name)
        i += 1
    
    # SAVE BOT AUDIO
    if BOT_PCM_BUFFER.getbuffer().nbytes > 0:
        bot_wav_name = f"bot_track_{time_str}.wav"
        try:
            with wave.open(bot_wav_name, 'wb') as wf:
                wf.setnchannels(2) 
                wf.setsampwidth(2) 
                wf.setframerate(48000) 
                wf.writeframes(BOT_PCM_BUFFER.getvalue())
            temp_wavs.append(bot_wav_name)
            await dest_channel.send("🎹 **Bot Audio Captured & Synced.**")
        except Exception as e:
            print(f"Bot Save Error: {e}")
            
    BOT_PCM_BUFFER.seek(0)
    BOT_PCM_BUFFER.truncate(0)
    
    global MERGE_MODE
    
    if MERGE_MODE and temp_wavs:
        # STEALTH: Fake Typing during merge
        async with dest_channel.typing():
            await dest_channel.send("🔄 **Merging & Checking Size...**")
            merged_output = "merged_temp.mp3" 
            final_nice_name = f"Conversation_{time_str}.mp3" 
            
            result = await convert_and_merge(temp_wavs, merged_output, total_duration)
            
            if result and os.path.exists(result) and os.path.getsize(result) > 0:
                chunks = await split_audio_if_large(result)
                if len(chunks) > 1:
                    await dest_channel.send(f"📦 File > 9MB. Sending {len(chunks)} parts:")
                    for idx, chunk in enumerate(chunks):
                        chunk_nice_name = f"Conversation_{time_str}_Part{idx+1}.mp3"
                        await dest_channel.send(f"**Part {idx+1}:**", file=discord.File(chunk, filename=chunk_nice_name))
                        await asyncio.sleep(3) # STEALTH: Wait 3s between upload parts
                        os.remove(chunk)
                    os.remove(result)
                else:
                    await dest_channel.send("Here is the full conversation:", 
                                          file=discord.File(result, filename=final_nice_name))
                    await asyncio.sleep(3) # STEALTH: Wait 3s
                    os.remove(result)
            else:
                await dest_channel.send("❌ Merge failed. Sending separate files.")
                MERGE_MODE = False 

    if not MERGE_MODE:
        if temp_wavs:
            await dest_channel.send("Here are the synced recordings:")

        for idx, wav in enumerate(temp_wavs):
            mp3_name = real_names[idx] if idx < len(real_names) else f"Track_{idx}.mp3"
            await convert_wav_to_mp3_padded(wav, mp3_name, total_duration)
            
            if os.path.exists(mp3_name):
                chunks = await split_audio_if_large(mp3_name)
                
                if len(chunks) > 1:
                     for c_idx, chunk in enumerate(chunks):
                        await dest_channel.send(
                            f"**{mp3_name[:-4]} (Part {c_idx+1}):**",
                            file=discord.File(chunk, filename=f"{mp3_name[:-4]}_Part{c_idx+1}.mp3")
                        )
                        await asyncio.sleep(3) # STEALTH: Wait 3s between upload parts
                        os.remove(chunk)
                else:
                    await dest_channel.send(file=discord.File(mp3_name))
                    await asyncio.sleep(3) # STEALTH: Wait 3s
                
                if os.path.exists(mp3_name): os.remove(mp3_name)

    for f in temp_wavs:
        if os.path.exists(f): os.remove(f)

# --- REUSABLE RECORDING FUNCTION ---
async def start_recording_logic(ctx, merge_flag, capture_bot=False):
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ I am not in a VC.")
    
    vc = bot.voice_clients[0]
    if vc.recording:
        return await ctx.send("⚠️ Already recording.")

    global MERGE_MODE, SESSION_START_TIME, IS_RECORDING_BOT, BOT_PCM_BUFFER, CURRENT_RECORDING_CONFIG
    
    # SAVE CONFIG FOR STABLE FOLLOW
    CURRENT_RECORDING_CONFIG["merge"] = merge_flag
    CURRENT_RECORDING_CONFIG["bot_audio"] = capture_bot

    MERGE_MODE = merge_flag
    IS_RECORDING_BOT = capture_bot
    SESSION_START_TIME = datetime.datetime.now() 
    
    # Reset Bot Buffer
    BOT_PCM_BUFFER.seek(0)
    BOT_PCM_BUFFER.truncate(0)

    vc.start_recording(
        SyncWaveSink(), 
        finished_callback, 
        ctx.channel 
    )
    
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.datetime.now(ist).strftime("%I:%M %p")
    
    if capture_bot:
        mode_str = "STUDIO MODE (Users + Bot)"
    else:
        mode_str = "Merged" if merge_flag else "Synced"
    
    if hasattr(ctx, 'send'):
        await ctx.send(f"🔴 **Recording Started [{mode_str}] at {start_time} IST!**")

# ==========================================
# 🐕 STABLE FOLLOW MODE (CRASH FIX)
# ==========================================
@bot.event
async def on_voice_state_update(member, before, after):
    if not FOLLOW_MODE: return
    if member.id not in AUTHORIZED_USERS: return
    if after.channel is not None and after.channel != before.channel:
        try:
            vc = member.guild.voice_client
            
            # Helper for Restarting
            class FakeCtx:
                def __init__(self, ch, g): self.channel = ch; self.guild = g
                async def send(self, msg): print(msg)

            if not vc:
                await asyncio.sleep(random.uniform(1.5, 3.0))
                await after.channel.connect()
                print(f"🐕 Followed to {after.channel.name}")
                if AUTO_REC_MODE:
                    await asyncio.sleep(2)
                    is_merge = (AUTO_REC_MODE == 'merged')
                    await start_recording_logic(FakeCtx(after.channel, member.guild), is_merge, False)

            elif vc.channel.id != after.channel.id:
                print("🐕 Moving...")
                
                # CRITICAL STABILITY FIX: STOP before Move
                was_recording = vc.recording
                if was_recording:
                    vc.stop_recording()
                    await asyncio.sleep(4) # Wait for upload
                
                await vc.move_to(after.channel)
                print(f"🐕 Moved to {after.channel.name}")
                
                # RESTART with saved config
                if was_recording:
                    await asyncio.sleep(2)
                    restore_merge = CURRENT_RECORDING_CONFIG.get("merge", False)
                    restore_bot = CURRENT_RECORDING_CONFIG.get("bot_audio", False)
                    await start_recording_logic(FakeCtx(after.channel, member.guild), restore_merge, restore_bot)

        except Exception as e:
            print(f"Follow Error: {e}")

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as "{bot.user.name}"')
    if SECRET_KEY:
        print("✅ Secret Key Loaded.")
    else:
        print("⚠️ Warning: No 'KEY' secret found.")
    print("✅ Nuclear Patch v96 (Quality Compressor + Splitter + Trim + URL Support) Active.")

@bot.command()
async def login(ctx, *, key: str):
    try: await ctx.message.delete()
    except: pass
    
    if ctx.author.id in AUTHORIZED_USERS:
        return await ctx.send("✅ You are already logged in.")

    if not SECRET_KEY:
        return await ctx.send("⚠️ **System Error:** KEY Secret is missing.")

    if key.strip() == SECRET_KEY:
        AUTHORIZED_USERS.add(ctx.author.id)
        await ctx.send(f"✅ **Access Granted.** Welcome, {ctx.author.display_name}.")
    else:
        await ctx.send("❌ **Wrong Key.** Access Denied.")

@bot.command()
async def help(ctx):
    msg = (
        "**🎙️ User Recorder**\n"
        "`+login <key>` - Unlock the bot\n"
        "`+join` - Find you and join VC\n"
        "`+joinid <id>` - Join specific Channel ID\n"
        "`+autorec on/off` - Auto Record when joining\n"
        "`+record` - Synced Separate Files (Voices Only)\n"
        "`+recordall` - Synced & Merged File (Voices Only)\n"
        "`+recordme` - **STUDIO MODE** (Voices + Music Synced)\n"
        "`+stop` - Stop & Upload\n"
        "`+dc` - Stop & Disconnect\n"
        "`+m` - Toggle Mute\n"
        "`+deaf` - Toggle Deafen\n"
        "`+follow` - Toggle Auto-Follow Mode\n"
        "\n**🎵 Universal Player**\n"
        "`+play [Song/URL]` - Play/Queue\n"
        "`+upload [URL] [Quality]` - e.g. `+upload http://... 480p`\n"
        "`+trim <start> <end> [URL]` - Trim audio/video (Reply, Attach or URL)\n"
        "`+ss [URL] [time]` - Screenshot (Smart Wait)\n"
        "`+tts [Text]` - Indian TTS\n"
        "`+settingtts [voice]` - Change TTS Voice\n"
        "`+skip` - Skip song\n"
        "`+pause` - Pause playback\n"
        "`+resume` - Resume playback\n"
        "`+vol <0-500>` - Set Volume\n"
        "`+bass` - Toggle Deep Bass Mode\n"
        "`+queue` - View Queue\n"
        "`+pstop` - Stop Player"
    )
    await ctx.send(msg)

@bot.command()
async def autorec(ctx, option: str = None, mode: str = None):
    global AUTO_REC_MODE
    
    if option is None:
        current = "OFF" if AUTO_REC_MODE is None else f"ON ({AUTO_REC_MODE})"
        return await ctx.send(f"ℹ️ AutoRec is currently: **{current}**")
    
    option = option.lower()
    
    if option == "off":
        AUTO_REC_MODE = None
        await ctx.send("✅ Auto-Record disabled.")
        return

    if option == "on":
        if mode:
            option = mode.lower() 
        else:
            return await ctx.send("⚠️ Please specify mode: `+autorec separate` or `+autorec merged`")

    if option in ["separate", "normal"]:
        AUTO_REC_MODE = 'separate'
        await ctx.send("✅ Auto-Record set to: **Separate Files**")
    elif option in ["merged", "all"]:
        AUTO_REC_MODE = 'merged'
        await ctx.send("✅ Auto-Record set to: **Merged File**")
    else:
        await ctx.send("❌ Invalid mode. Use `separate`, `merged`, or `off`.")

# --- MUTE/DEAF (Robust v31 Logic + STEALTH) ---
@bot.command()
async def m(ctx):
    # STEALTH: Human Jitter (0.5s - 1.5s)
    await asyncio.sleep(random.uniform(0.5, 1.5))
    
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ Not in a VC.")
    vc = bot.voice_clients[0]
    
    try:
        current_mute = vc.guild.me.voice.self_mute
        current_deaf = vc.guild.me.voice.self_deaf
        new_mute = not current_mute
    except:
        new_mute = True
        current_deaf = False
    
    payload = {
        "op": 4,
        "d": {
            "guild_id": vc.channel.guild.id, 
            "channel_id": vc.channel.id,
            "self_mute": new_mute,
            "self_deaf": current_deaf
        }
    }
    await bot.ws.send_as_json(payload)
    status = "🔇 **Muted**" if new_mute else "🎙️ **Unmuted**"
    await ctx.send(f"✅ Mic is now {status}.")

@bot.command()
async def deaf(ctx):
    # STEALTH: Human Jitter (0.5s - 1.5s)
    await asyncio.sleep(random.uniform(0.5, 1.5))
    
    if len(bot.voice_clients) == 0:
        return await ctx.send("❌ Not in a VC.")
    vc = bot.voice_clients[0]
    
    try:
        current_mute = vc.guild.me.voice.self_mute
        current_deaf = vc.guild.me.voice.self_deaf
        new_deaf = not current_deaf
    except:
        new_deaf = True
        current_mute = False
    
    payload = {
        "op": 4,
        "d": {
            "guild_id": vc.channel.guild.id,
            "channel_id": vc.channel.id,
            "self_mute": current_mute,
            "self_deaf": new_deaf
        }
    }
    await bot.ws.send_as_json(payload)
    status = "🔕 **Deafened**" if new_deaf else "🔔 **Undeafened**"
    await ctx.send(f"✅ Headset is now {status}.")

# -------------------------------------------------------

@bot.command()
async def join(ctx):
    # STEALTH: Join Delay (1.0s - 2.0s)
    await ctx.send("🔍 Scanning servers...")
    await asyncio.sleep(random.uniform(1.0, 2.0))
    
    found = False
    for guild in bot.guilds:
        member = guild.get_member(ctx.author.id)
        if member and member.voice:
            await member.voice.channel.connect() 
            await ctx.send(f"👍 Joined **{member.voice.channel.name}** in **{guild.name}**!")
            found = True
            
            if AUTO_REC_MODE:
                await asyncio.sleep(1) 
                is_merge = (AUTO_REC_MODE == 'merged')
                await start_recording_logic(ctx, is_merge)
            break
            
    if not found:
        await ctx.send("❌ I couldn't find you in any Voice Channel.")

@bot.command()
async def joinid(ctx, channel_id: str):
    # STEALTH: Join Delay (1.0s - 2.0s)
    await asyncio.sleep(random.uniform(1.0, 2.0))
    
    channel = bot.get_channel(int(channel_id))
    if isinstance(channel, discord.VoiceChannel):
        await channel.connect()
        await ctx.send(f"👍 Joined **{channel.name}**")
        
        if AUTO_REC_MODE:
            await asyncio.sleep(1)
            is_merge = (AUTO_REC_MODE == 'merged')
            await start_recording_logic(ctx, is_merge)
    else:
        await ctx.send("❌ Not a voice channel.")

@bot.command()
async def record(ctx):
    await start_recording_logic(ctx, False, False)

@bot.command()
async def recordall(ctx):
    await start_recording_logic(ctx, True, False)

@bot.command()
async def recordme(ctx):
    # This is the new command for Studio Mode
    await start_recording_logic(ctx, True, True)

@bot.command()
async def stop(ctx):
    # STEALTH: Random Delay
    await asyncio.sleep(random.uniform(0.5, 1.0))
    
    if len(bot.voice_clients) == 0:
        return await ctx.send("Not connected.")
    vc = bot.voice_clients[0]
    
    if vc.recording:
        vc.stop_recording()
        await ctx.send("💾 **Saving & Uploading... (Bot will stay in VC)**")
    else:
        await ctx.send("❓ Not recording.")

@bot.command()
async def dc(ctx):
    if len(bot.voice_clients) == 0:
        return await ctx.send("Not connected.")
    vc = bot.voice_clients[0]
    
    if vc.recording:
        vc.stop_recording()
        await ctx.send("💾 **Saving & Uploading before Disconnect...**")
    
    # STEALTH: Safe Disconnect Logic
    if vc.is_playing():
        vc.stop()
    await asyncio.sleep(1) # Wait for stop to register
    await vc.disconnect()
    await ctx.send("👋 **Disconnected.**")

# ==========================================
# 🎵 PLAYER (FX ENABLED & RECORDABLE)
# ==========================================

queues = {}

def get_queue_id(ctx):
    if ctx.guild and hasattr(ctx.guild, 'id'): return ctx.guild.id
    if hasattr(ctx, 'author') and hasattr(ctx.author, 'id'): return ctx.author.id
    return 0  # Fallback for DummyContext with no guild

def play_next_in_queue(ctx):
    q_id = get_queue_id(ctx)
    if q_id in queues and queues[q_id]:
        track = queues[q_id].pop(0)
        coro = ctx.send(f"▶️ **Now Playing:** {track['title']}")
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
        play_audio_core(ctx, track['url'], track['title'])

def play_audio_core(ctx, url, title):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    
    # --- AUDIO FX FILTER BUILDER ---
    filters = []
    if VOLUME_LEVEL != 1.0:
        filters.append(f"volume={VOLUME_LEVEL}")
    if BASS_ACTIVE:
        filters.append("bass=g=20")
        
    # Pre-calculate filter string to avoid f-string SyntaxError (FIXED v69)
    filter_str = ""
    if filters:
        filter_str = f' -filter:a "{",".join(filters)}"'
    
    # ----------------------------------------------------
    # NUCLEAR FIX v69: Detect if Local File or Web Stream
    # ----------------------------------------------------
    if url.startswith("http") or url.startswith("www"):
        # Web Stream Options (Reconnect allowed)
        opts = {'before_options': '-reconnect 1 -reconnect_streamed 1', 'options': f'-vn{filter_str}'}
    else:
        # Local File Options (NO Reconnect - Fixes TTS silence)
        opts = {'options': f'-vn{filter_str}'}
    # ----------------------------------------------------

    def on_finish(e):
        # Cleanup TTS file if it exists
        if os.path.exists(url) and "tts_" in url:
            try: os.remove(url)
            except: pass
        if queues.get(get_queue_id(ctx)):
            t = queues[get_queue_id(ctx)].pop(0)
            play_audio_core(ctx, t['url'], t['title'])
    
    try:
        # Use our Custom Recordable Audio Class instead of the standard one
        source = RecordableFFmpegPCMAudio(url, **opts)
        vc.play(source, after=on_finish)
    except Exception as e:
        print(f"Play Core Error: {e}")

@bot.command()
async def tts(ctx, *, text: str):
    if len(bot.voice_clients) == 0: return await ctx.send("❌ **Not in a VC.** Please use `+join` first.")
    
    # Generate unique filename
    output_file = f"tts_{int(time.time())}.mp3"
    
    try:
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        await communicate.save(output_file)
        
        q_id = get_queue_id(ctx)
        if q_id not in queues: queues[q_id] = []
        
        if bot.voice_clients[0].is_playing():
            queues[q_id].append({'url': output_file, 'title': f"🗣️ {text[:20]}..."})
            await ctx.send(f"📝 **TTS Queued:** {text}")
        else:
            play_audio_core(ctx, output_file, f"🗣️ {text}")
            
    except Exception as e:
        await ctx.send(f"❌ TTS Error: {e}")

@bot.command()
async def settingtts(ctx, voice: str = None):
    global TTS_VOICE
    if not voice:
        # List options
        msg = "**🗣️ Available Voices:**\n"
        for k in VOICE_MAP.keys():
            msg += f"`{k}`\n"
        msg += f"\n**Current:** `{next((k for k, v in VOICE_MAP.items() if v == TTS_VOICE), 'Custom')}`"
        return await ctx.send(msg)
    
    if voice.lower() in VOICE_MAP:
        TTS_VOICE = VOICE_MAP[voice.lower()]
        await ctx.send(f"✅ TTS Voice set to: **{voice.lower()}**")
    else:
        await ctx.send("❌ Invalid voice. Type `+settingtts` to see list.")

# ==========================================
# 📸 SCREENSHOT COMMAND (Smart Engine + Windows 11 Size)
# ==========================================
@bot.command()
async def ss(ctx, url: str, wait_arg: str = "5s"):
    if not url.startswith("http"): url = "https://" + url
    
    # Parse seconds (Min 5, Max 50) - Retained per user request
    seconds = 5
    try:
        val = int("".join(filter(str.isdigit, wait_arg)))
        seconds = max(5, min(50, val))
    except:
        seconds = 5
    
    await ctx.send(f"📸 **Capturing:** {url} (Smart Wait Active, ~{seconds}s max)...")
    
    # Using WordPress mShots with FORCED DESKTOP DIMENSIONS (1920x1080)
    encoded_url = urllib.parse.quote(url)
    api_url = f"https://s0.wp.com/mshots/v1/{encoded_url}?w=1920&h=1080"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    file = discord.File(io.BytesIO(data), filename="screenshot.jpg")
                    await ctx.send(file=file)
                else:
                    await ctx.send("❌ Screenshot API failed.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 📥 NEW COMMAND: +UPLOAD (With Quality Selector)
# ==========================================
@bot.command()
async def upload(ctx, url: str, quality: str = None):
    if not url.startswith("http"):
        return await ctx.send("❌ Invalid URL.")

    # STEALTH: Fake Typing
    async with ctx.typing():
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await ctx.send("📥 **Downloading File...**")

        try:
            filename = f"downloaded_{int(time.time())}.mp4" 
            
            # 1. Download File
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        ctype = resp.headers.get('Content-Type', '')
                        if 'image' in ctype: filename = filename.replace('.mp4', '.png')
                        elif 'audio' in ctype: filename = filename.replace('.mp4', '.mp3')
                        
                        with open(filename, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024):
                                f.write(chunk)
                    else:
                        return await ctx.send(f"❌ Failed to download: {resp.status}")

            # 2. Quality Compression (If requested)
            if quality and 'mp4' in filename:
                target_height = None
                if '720' in quality: target_height = 720
                elif '480' in quality: target_height = 480
                elif '360' in quality: target_height = 360
                elif '240' in quality: target_height = 240
                
                if target_height:
                    await ctx.send(f"📉 **Compressing to {target_height}p...** (This reduces file size)")
                    compressed_name = await compress_video(filename, target_height)
                    if compressed_name != filename:
                        os.remove(filename) # Remove big original
                        filename = compressed_name

            # 3. Check Size & Split if needed
            if os.path.getsize(filename) > 0:
                chunks = await split_media_smart(filename, limit_mb=8.5) 
                
                if len(chunks) > 1:
                    await ctx.send(f"📦 File is large (>9MB). Sending {len(chunks)} parts:")
                    for idx, chunk in enumerate(chunks):
                        await ctx.send(f"**Part {idx+1}:**", file=discord.File(chunk))
                        await asyncio.sleep(3) # STEALTH: Wait 3s between parts
                        os.remove(chunk)
                else:
                    await ctx.send("✅ **Upload Complete:**", file=discord.File(filename))
                    await asyncio.sleep(3)
                
                if os.path.exists(filename): os.remove(filename)
            else:
                await ctx.send("❌ Downloaded file is empty.")
                
        except Exception as e:
            await ctx.send(f"❌ Upload Error: {e}")
            if os.path.exists(filename): os.remove(filename)

# ==========================================
# ✂️ NEW COMMAND: +TRIM (Added to Stable v96)
# ==========================================
@bot.command()
async def trim(ctx, start_time: str, end_time: str, *, url: str = None):
    # Verify Times
    s_sec = parse_time_str(start_time)
    e_sec = parse_time_str(end_time)

    if s_sec is None or e_sec is None:
        return await ctx.send("❌ Invalid time format. Use `MM:SS` (e.g. `1:30`)")
    if s_sec >= e_sec:
        return await ctx.send("❌ Start time must be before end time.")

    # Find Target
    target_url = None
    filename = "media_to_trim"
    
    if ctx.message.attachments:
        target_url = ctx.message.attachments[0].url
        filename = ctx.message.attachments[0].filename
    elif ctx.message.reference:
        try:
            ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if ref.attachments:
                target_url = ref.attachments[0].url
                filename = ref.attachments[0].filename
        except: pass
    elif url:
        target_url = url.strip()
        # Basic guess for temp filename extension
        if ".mp3" in target_url: filename = "download.mp3"
        elif ".wav" in target_url: filename = "download.wav"
        else: filename = "download.mp4"
    
    if not target_url:
        return await ctx.send("❌ Please attach a file, reply to one, or provide a URL.")

    async with ctx.typing():
        # Download
        try:
            if 'mp4' in filename.lower(): ext = '.mp4'
            elif 'mp3' in filename.lower(): ext = '.mp3'
            elif 'wav' in filename.lower(): ext = '.wav'
            elif 'm4a' in filename.lower(): ext = '.m4a'
            else: ext = os.path.splitext(filename)[1]
            
            input_path = f"temp_trim_in_{int(time.time())}{ext}"
            output_path = f"trimmed_{int(time.time())}{ext}"

            async with aiohttp.ClientSession() as session:
                async with session.get(target_url) as resp:
                    if resp.status == 200:
                        with open(input_path, 'wb') as f:
                            f.write(await resp.read())
                    else:
                        return await ctx.send("❌ Download failed.")
            
            # Trim Command (Uses COPY to keep quality and speed)
            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-ss', str(s_sec),
                '-to', str(e_sec),
                '-c', 'copy', 
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await process.communicate()

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                # Reuse the smart splitter just in case the trim is still huge
                chunks = await split_media_smart(output_path, limit_mb=8.5)
                if len(chunks) == 1:
                    await ctx.send(f"✂️ **Trimmed ({start_time} - {end_time}):**", file=discord.File(chunks[0]))
                else:
                    await ctx.send(f"📦 Trimmed file > 9MB. Sending {len(chunks)} parts:")
                    for idx, c in enumerate(chunks):
                        await ctx.send(f"Part {idx+1}:", file=discord.File(c))
                        await asyncio.sleep(2)
                        os.remove(c)
                
                if os.path.exists(output_path): os.remove(output_path)
            else:
                await ctx.send("❌ Trim failed (Output empty). Check your timestamps.")

            if os.path.exists(input_path): os.remove(input_path)

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
            if os.path.exists(input_path): os.remove(input_path)

@bot.command()
async def play(ctx, *, query: str = None):
    # STEALTH: Fake "Typing..." + Random Delay for ALL play requests
    async with ctx.typing():
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        try:
            if len(bot.voice_clients) == 0:
                 return await ctx.send("❌ **Not in a VC.** Please use `+join` first.")
            vc = bot.voice_clients[0]

            target_url = None
            title = "Unknown Track"
            is_search = False

            if ctx.message.attachments:
                target_url = ctx.message.attachments[0].url
                title = ctx.message.attachments[0].filename
                await ctx.send("📂 **Processing attached file...**")

            elif ctx.message.reference:
                ref = ctx.message.reference
                if ref.cached_message and ref.cached_message.attachments:
                    target_url = ref.cached_message.attachments[0].url
                    title = ref.cached_message.attachments[0].filename
                if not target_url:
                    try:
                        ref_msg = await ctx.channel.fetch_message(ref.message_id)
                        if ref_msg.attachments:
                            target_url = ref_msg.attachments[0].url
                            title = ref_msg.attachments[0].filename
                    except: pass
                if target_url: await ctx.send("↩️ **Queuing Replied Audio...**")

            elif query:
                # ------------------------------------------------
                # YT FIX: BLOCK YOUTUBE EXPLICITLY TO STOP CRASHES
                # ------------------------------------------------
                if "youtube.com" in query or "youtu.be" in query:
                    return await ctx.send("❌ **YouTube is disabled.** Use SoundCloud or direct links.")
                    
                # Direct Link Check
                if query.startswith("http") or query.startswith("www"):
                    target_url = query.strip()
                    title = "Direct Link"
                    await ctx.send("🔗 **Processing Direct Link...**")
                else:
                    is_search = True
                    await ctx.send(f"☁️ **Searching SoundCloud for:** `{query}`...")
            
            else:
                return await ctx.send("❌ **No audio found.** Provide a URL, name, or file.")

            if is_search:
                ydl_opts = {
                    'format': 'bestaudio/best', 'noplaylist': True, 
                    'quiet': True, 'no_warnings': True, 
                    'source_address': '0.0.0.0', 'nocheckcertificate': True
                }
                loop = asyncio.get_event_loop()
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"scsearch1:{query}", download=False))
                    if 'entries' in info and info['entries']:
                        target_url = info['entries'][0]['url']
                        title = info['entries'][0].get('title', 'Unknown Track')
                    else:
                        return await ctx.send("❌ No results found.")

            q_id = get_queue_id(ctx)
            if q_id not in queues: queues[q_id] = []

            if vc.is_playing() or vc.is_paused():
                queues[q_id].append({'url': target_url, 'title': title})
                await ctx.send(f"📝 **Added to Queue:** {title}")
            else:
                await ctx.send(f"▶️ **Now Playing:** {title}")
                play_audio_core(ctx, target_url, title)

        except Exception as e:
            await ctx.send(f"❌ **Error:** {e}")

# --- NEW COMMANDS (Volume, Bass, Follow) ---

@bot.command()
async def vol(ctx, volume: int):
    global VOLUME_LEVEL
    if volume < 0: return await ctx.send("❌ Volume cannot be negative.")
    
    # 100 = 1.0, 200 = 2.0
    VOLUME_LEVEL = volume / 100
    await ctx.send(f"🔊 **Volume set to {volume}%.** (Applies to next song)")

@bot.command()
async def bass(ctx):
    global BASS_ACTIVE
    BASS_ACTIVE = not BASS_ACTIVE
    state = "ON 🔥" if BASS_ACTIVE else "OFF"
    await ctx.send(f"🎸 **Bass Boost is {state}.** (Applies to next song)")

@bot.command()
async def follow(ctx):
    global FOLLOW_MODE
    FOLLOW_MODE = not FOLLOW_MODE
    state = "ENABLED 🐕" if FOLLOW_MODE else "DISABLED"
    await ctx.send(f"👣 **Auto-Follow Mode is {state}.**")

@bot.command()
async def skip(ctx):
    if len(bot.voice_clients) == 0: return await ctx.send("❌ Not in VC.")
    vc = bot.voice_clients[0]
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏭️ **Skipped.**")
    else:
        await ctx.send("❓ Nothing to skip.")

@bot.command()
async def pause(ctx):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    if vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ **Paused.**")

@bot.command()
async def resume(ctx):
    if len(bot.voice_clients) == 0: return
    vc = bot.voice_clients[0]
    if vc.is_paused():
        vc.resume()
        await ctx.send("▶️ **Resumed.**")

@bot.command()
async def queue(ctx):
    q_id = get_queue_id(ctx)
    if q_id not in queues or not queues[q_id]:
        return await ctx.send("📭 **Queue is empty.**")
    msg = "**🎵 Up Next:**\n"
    for i, track in enumerate(queues[q_id]):
        msg += f"`{i+1}.` {track['title']}\n"
    await ctx.send(msg)

@bot.command()
async def pstop(ctx):
    if len(bot.voice_clients) == 0: return await ctx.send("❌ Not in VC.")
    vc = bot.voice_clients[0]
    q_id = get_queue_id(ctx)
    if q_id in queues: queues[q_id].clear()
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏹️ **Stopped & Queue Cleared.**")
    else:
        await ctx.send("❓ Nothing playing.")

# ==========================================
# 🌐 WEB DASHBOARD & CLOUDFLARE INTEGRATION
# ==========================================
from aiohttp import web
import platform
import shutil

# Dynamic Token Status
NEEDS_TOKEN = False
IS_LOGGED_IN = False
CLOUDFLARE_URL = None

async def download_cloudflared():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        cf_bin = "cloudflared.exe"
        if "amd64" in machine or "x86_64" in machine:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        else:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-386.exe"
    elif system == "linux":
        cf_bin = "cloudflared"
        if "aarch64" in machine or "arm64" in machine:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        elif "arm" in machine:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
        else:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    else:
        print(f"Unsupported OS for auto Cloudflare: {system}")
        return None

    if not os.path.exists(cf_bin) or (os.path.exists(cf_bin) and os.path.getsize(cf_bin) < 1000):
        print(f"Downloading Cloudflared from {url}...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(cf_bin, 'wb') as f:
                            f.write(await resp.read())
                        if system == "linux":
                            os.chmod(cf_bin, 0o755)
                        print("✅ Cloudflared Downloaded!")
                    else:
                        print(f"HTTP Error: {resp.status}")
        except Exception as e:
            print(f"❌ Failed to download Cloudflared via aiohttp: {e}")
            if system == "linux":
                print("Trying wget fallback...")
                os.system(f"wget -qO {cf_bin} {url} && chmod +x {cf_bin}")
                
    if os.path.exists(cf_bin):
        if system == "linux":
            os.chmod(cf_bin, 0o755)
            return f"./{cf_bin}"
        return cf_bin
    else:
        return "cloudflared"

async def run_cloudflare_tunnel(port):
    global CLOUDFLARE_URL
    cf_bin = await download_cloudflared()
    if not cf_bin: return

    print("🚀 Starting Cloudflare Tunnel...")
    process = await asyncio.create_subprocess_exec(
        cf_bin, "tunnel", "--url", f"http://localhost:{port}",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    async def read_cf_stderr():
        global CLOUDFLARE_URL
        while True:
            line = await process.stderr.readline()
            if not line: break
            decoded = line.decode('utf-8', errors='ignore')
            if "trycloudflare.com" in decoded:
                for part in decoded.split():
                    if "trycloudflare.com" in part:
                        import sys
                        CLOUDFLARE_URL = part.strip()
                        print(f"\n=====================================")
                        print(f"🌍 WEB UI LINK: {CLOUDFLARE_URL}")
                        print(f"=====================================")
                        sys.stdout.flush()

    asyncio.create_task(read_cf_stderr())

# --- API Endpoints ---
async def api_status(request):
    safe_name = bot.user.name if bot.user else "RecorderBot"
    safe_display = bot.user.display_name if bot.user else "RecorderBot"
    username = f"@{safe_name}"
    
    vc_name = "None"
    if hasattr(bot, 'voice_clients') and len(bot.voice_clients) > 0:
        vc = bot.voice_clients[0]
        if hasattr(vc, 'channel') and vc.channel and hasattr(vc.channel, 'name'):
            vc_name = vc.channel.name
            
    global FOLLOW_MODE, AUTHORIZED_USERS
    follow_name = "None"
    if FOLLOW_MODE and len(AUTHORIZED_USERS) > 0:
        follow_name = "Active"
    
    return web.json_response({
        "needs_token": NEEDS_TOKEN,
        "logged_in": IS_LOGGED_IN,
        "bot_display": safe_display,
        "bot_username": username,
        "vc_name": vc_name,
        "follow_name": follow_name,
        "global_mute": GLOBAL_MUTE,
        "global_deaf": GLOBAL_DEAF
    })

async def api_auth(request):
    try:
        data = await request.json()
        key = data.get('key', '')
        if key.strip() == SECRET_KEY:
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "Invalid Secret Key"})
    except:
        return web.json_response({"success": False, "error": "Invalid JSON"})

async def api_set_token(request):
    global TOKEN, NEEDS_TOKEN
    try:
        data = await request.json()
        new_token = data.get('token', '').strip()
        if not new_token: return web.json_response({"success": False, "error": "Empty Token"})
        
        # Save to environment tentatively
        os.environ['DISCORD_TOKEN'] = new_token
        TOKEN = new_token
        NEEDS_TOKEN = False
        
        print("🔄 Dynamic Token Update Received. Waiting for main loop to pick up...")
        return web.json_response({"success": True})
    except:
        return web.json_response({"success": False, "error": "Invalid JSON"})

class DummyContext:
    def __init__(self):
        self.message = type('obj', (object,), {'attachments': [], 'reference': None})()
        # Channel needs async send method for callbacks
        async def _dummy_send(*args, **kwargs): pass
        self.channel = type('obj', (object,), {'id': 0, 'fetch_message': lambda x: None, 'send': _dummy_send})()
        if hasattr(bot, 'guilds') and len(bot.guilds)>0:
            self.guild = bot.guilds[0]
            if len(self.guild.members) > 0:
                 self.author = self.guild.members[0] # Pick any author for context
            else:
                 self.author = type('obj', (object,), {'id': 0})()
        else:
            self.guild = None
            self.author = type('obj', (object,), {'id': 0})()
            
    async def send(self, *args, **kwargs): pass
    def typing(self):
         class TypingMgr:
              async def __aenter__(self): return self
              async def __aexit__(self,a,b,c): pass
         return TypingMgr()

    async def invoke(self, command, *args, **kwargs):
        try:
            return await command.callback(self, *args, **kwargs)
        except Exception as e:
            print(f"DummyContext Invoke Error: {e}")

async def api_command(request):
    try:
        data = await request.json()
        cmd_str = data.get('cmd', '')
        parts = cmd_str.split(' ')
        base = parts[0].replace('+', '')
        
        # --- DIRECT LOGIC OVERRIDES ---
        if base == 'dc':
            if len(bot.voice_clients) > 0:
                vc = bot.voice_clients[0]
                try:
                    if vc.recording: vc.stop_recording()
                    if vc.is_playing(): vc.stop()
                except: pass
                await vc.disconnect(force=True)
            return web.json_response({"success": True})
            
        elif base == 'm':
            global GLOBAL_MUTE, GLOBAL_DEAF
            if len(bot.voice_clients) > 0:
                vc = bot.voice_clients[0]
                GLOBAL_MUTE = not GLOBAL_MUTE
                try:
                    await vc.guild.me.edit(mute=GLOBAL_MUTE)
                except Exception as e:
                    print(f"Mute Error: {e}")
                return web.json_response({"success": True})
            return web.json_response({"success": False, "error": "Not in VC"})
            
        elif base == 'deaf':
            if len(bot.voice_clients) > 0:
                vc = bot.voice_clients[0]
                GLOBAL_DEAF = not GLOBAL_DEAF
                try:
                    await vc.guild.me.edit(deafen=GLOBAL_DEAF)
                except Exception as e:
                    print(f"Deaf Error: {e}")
                return web.json_response({"success": True})
            return web.json_response({"success": False, "error": "Not in VC"})

        # --- DIRECT JOIN BY CHANNEL ID ---
        elif base == 'joinid' and len(parts) > 1:
            channel_id = parts[1]
            try:
                # Force disconnect any existing voice client
                if len(bot.voice_clients) > 0:
                    try: await bot.voice_clients[0].disconnect(force=True)
                    except: pass
                    await asyncio.sleep(0.5)
                
                channel = bot.get_channel(int(channel_id))
                if channel is None:
                    return web.json_response({"success": False, "error": f"Channel ID {channel_id} not found in cache. Is the bot in that server?"})
                if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    return web.json_response({"success": False, "error": f"Channel '{channel.name}' is a {type(channel).__name__}, not a voice channel."})
                
                vc = await channel.connect(timeout=10)
                # Give voice gateway a moment to settle
                await asyncio.sleep(1)
                print(f"✅ Joined VC: {channel.name}")
                return web.json_response({"success": True})
            except Exception as e:
                print(f"Join Error: {e}")
                return web.json_response({"success": False, "error": str(e)})

        # --- DIRECT JOIN BY USER NAME/ID ---
        elif base == 'join_target' and len(parts) > 1:
            uid = parts[1]
            
            # Safety: reject channel IDs
            if uid.isdigit():
                try:
                    check_vc = bot.get_channel(int(uid))
                    if isinstance(check_vc, discord.VoiceChannel):
                        return web.json_response({"success": False, "error": "That's a Channel ID! Use 'Join ID' instead."})
                except: pass

            found = False
            for g in bot.guilds:
                for v in g.voice_channels:
                    for m in v.members:
                        if uid.lower() in m.name.lower() or uid.lower() in m.display_name.lower() or str(m.id) == uid:
                            # Force disconnect first
                            if len(bot.voice_clients) > 0:
                                try: await bot.voice_clients[0].disconnect(force=True)
                                except: pass
                                await asyncio.sleep(0.5)
                            
                            vc = await v.connect(timeout=10)
                            await asyncio.sleep(1)
                            found = True
                            print(f"✅ Joined VC: {v.name} (following {m.display_name})")
                            return web.json_response({"success": True})
            if not found:
                return web.json_response({"success": False, "error": f"Could not find user '{uid}' in any Voice Channel!"})

        # --- DIRECT TTS ---
        elif base == 'tts' and len(parts) > 1:
            tts_text = " ".join(parts[1:])
            if len(bot.voice_clients) == 0:
                return web.json_response({"success": False, "error": "Not connected to a Voice Channel. Join first!"})
            
            try:
                output_file = f"tts_{int(time.time())}.mp3"
                communicate = edge_tts.Communicate(tts_text, TTS_VOICE)
                await communicate.save(output_file)
                
                vc = bot.voice_clients[0]
                if vc.is_playing():
                    q_id = bot.guilds[0].id if bot.guilds else 0
                    if q_id not in queues: queues[q_id] = []
                    queues[q_id].append({'url': output_file, 'title': f"🗣️ {tts_text[:20]}..."})
                else:
                    play_audio_core(None, output_file, f"🗣️ {tts_text}")
                    
                return web.json_response({"success": True})
            except Exception as e:
                print(f"TTS Direct Error: {e}")
                return web.json_response({"success": False, "error": str(e)})
        
        # --- FOLLOW (direct) ---
        elif base == 'follow' and len(parts) > 1:
            uid = parts[1]
            global AUTHORIZED_USERS
            for g in bot.guilds:
                for m in g.members:
                    if uid.lower() in m.name.lower() or uid.lower() in m.display_name.lower() or str(m.id) == uid:
                        AUTHORIZED_USERS.add(m.id)
            ctx = DummyContext()
            cmd = bot.get_command('follow')
            if cmd:
                await ctx.invoke(cmd)
            return web.json_response({"success": True})
        
        # --- EVERYTHING ELSE through DummyContext ---
        ctx = DummyContext()
        cmd = bot.get_command(base)
        if cmd:
            args = parts[1:]
            if base == 'play':
                 await ctx.invoke(cmd, query=" ".join(args))
            elif base in ['trim'] and len(args)>=2:
                 url = " ".join(args[2:]) if len(args)>2 else None
                 await ctx.invoke(cmd, start_time=args[0], end_time=args[1], url=url)
            elif base in ['upload'] and len(args)>=1:
                 q = args[1] if len(args)>1 else None
                 await ctx.invoke(cmd, url=args[0], quality=q)
            elif base in ['vol'] and len(args)>0:
                 await ctx.invoke(cmd, volume=int(args[0]))
            else:
                 await ctx.invoke(cmd)
                  
        return web.json_response({"success": True})
        
    except Exception as e:
        print(f"API Command Error: {e}")
        return web.json_response({"success": False, "error": str(e)})

async def api_gh_command(request):
    try:
        data = await request.json()
        cmd = data.get('cmd', '')
        
        # Security: In real production, executing arbitrary bash on GH actions is high risk.
        # But this is requested directly by user for workflow admin.
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode('utf-8') if stdout else ""
        err_out = stderr.decode('utf-8') if stderr else ""
        
        res_text = out + "\n" + err_out
        if not res_text.strip(): res_text = "Success (No Output)"
        
        return web.json_response({"success": True, "output": res_text})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

# Start Web Server
async def web_server():
    app = web.Application()
    
    # Setup static routes and API
    app.router.add_static('/ui/', path='web_ui', name='ui')
    app.router.add_get('/', lambda r: web.HTTPFound('/ui/index.html'))
    
    app.router.add_get('/api/status', api_status)
    app.router.add_post('/api/auth', api_auth)
    app.router.add_post('/api/set_token', api_set_token)
    app.router.add_post('/api/command', api_command)
    app.router.add_post('/api/gh_command', api_gh_command)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("✅ Local Web Server Started on Port 8000")
    
    # Auto Cloudflare
    await run_cloudflare_tunnel(8000)

async def run_bot_dynamically():
    global NEEDS_TOKEN, IS_LOGGED_IN, TOKEN
    
    while True:
        if not TOKEN or NEEDS_TOKEN:
            NEEDS_TOKEN = True
            IS_LOGGED_IN = False
            print("⚠️ Waiting for Valid Discord Token via Web UI...")
            await asyncio.sleep(5)
            continue
            
        try:
            NEEDS_TOKEN = False
            print(f"🔄 Attempting Login with Token: {TOKEN[:10]}...")
            await bot.login(TOKEN)
            IS_LOGGED_IN = True
            print("✅ Discord Login Subsystem Initialized!")
            await bot.connect(reconnect=True)
            
        except discord.LoginFailure:
            print("❌ Invalid Discord Token Detected!")
            NEEDS_TOKEN = True
            IS_LOGGED_IN = False
        except Exception as e:
            print(f"⚠️ Bot connection error: {e}")
            await asyncio.sleep(5)

async def main():
    if not SECRET_KEY:
         print("⚠️ WARNING: No SECRET_KEY found in environment variables. Web Auth will fail!")
         
    # Start web server task
    asyncio.create_task(web_server())
    
    # Start Discord connection loop
    await run_bot_dynamically()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Shutdown.")
