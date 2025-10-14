import os
import base64
import io
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

import requests
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.tl.custom import Button

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv('API_ID', '10446785'))
API_HASH = os.getenv('API_HASH', '4261b62d60200eb99a38dcd8b71c8634')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8222362928:AAG85K4WRPmf2yBPb_6j3uJiMHDYgscgolc')
MODAL_API_URL = os.getenv('MODAL_API_URL', 'https://oktetod--comfyui-wan2-2-complete-production-fastapi-app.modal.run')
ADMIN_ID = int(os.getenv('ADMIN_ID', '8484686373'))

# Bot configuration
BOT_USERNAME = os.getenv('BOT_USERNAME', 'WanVideoBot')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
SUPPORTED_VIDEO_TYPES = ['video/mp4', 'video/webm']

class WanVideoBot:
    def __init__(self):
        self.client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        self.user_states = {}
        self.user_data = {}
        self.camera_motions = [
            "ZoomIn", "ZoomOut", "PanLeft", "PanRight", 
            "TiltUp", "TiltDown", "RollingClockwise", "RollingAnticlockwise"
        ]
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup all event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = event.sender_id
            self.user_states[user_id] = 'main_menu'
            
            await event.respond(
                f"🎬 **Welcome to {BOT_USERNAME}!**\n\n"
                "I can generate videos from text, images, or apply camera motions.\n\n"
                "Choose an option below:",
                buttons=[
                    [Button.inline("📝 Text to Video", "t2v")],
                    [Button.inline("🖼️ Image to Video", "i2v")],
                    [Button.inline("🎭 Animate Character", "animate")],
                    [Button.inline("📹 Camera Motion", "camera")],
                    [Button.inline("ℹ️ Help", "help")]
                ]
            )
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await self.show_help_message(event)
        
        @self.client.on(events.NewMessage(pattern='/skip'))
        async def skip_handler(event):
            await self.handle_skip(event)
        
        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            user_id = event.sender_id
            data = event.data.decode('utf-8')
            
            try:
                if data == "main_menu":
                    await self.show_main_menu(event)
                elif data == "t2v":
                    await self.start_t2v(event)
                elif data == "i2v":
                    await self.start_i2v(event)
                elif data == "animate":
                    await self.start_animate(event)
                elif data == "camera":
                    await self.start_camera(event)
                elif data == "help":
                    await self.show_help(event)
                elif data.startswith("camera_"):
                    motion = data.replace("camera_", "")
                    await self.select_camera_motion(event, motion)
                elif data == "cancel":
                    await self.cancel_operation(event)
                elif data == "generate":
                    await self.generate_video(event)
            except Exception as e:
                logger.error(f"Callback error: {e}", exc_info=True)
                try:
                    await event.answer("❌ Error occurred", alert=True)
                except:
                    pass
        
        @self.client.on(events.NewMessage(func=lambda e: not e.text.startswith('/')))
        async def message_handler(event):
            user_id = event.sender_id
            
            if user_id not in self.user_states:
                return
            
            state = self.user_states[user_id]
            
            try:
                if state == "t2v_prompt":
                    await self.handle_t2v_prompt(event)
                elif state == "t2v_negative":
                    await self.handle_t2v_negative(event)
                elif state == "i2v_image":
                    if event.media:
                        await self.handle_i2v_image(event)
                    else:
                        await event.respond("📷 Please send an image!")
                elif state == "i2v_prompt":
                    await self.handle_i2v_prompt(event)
                elif state == "i2v_negative":
                    await self.handle_i2v_negative(event)
                elif state == "animate_ref_image":
                    if event.media:
                        await self.handle_animate_ref_image(event)
                    else:
                        await event.respond("📷 Please send a reference image!")
                elif state == "animate_video":
                    if event.media:
                        await self.handle_animate_video(event)
                    else:
                        await event.respond("🎬 Please send a video!")
                elif state == "animate_prompt":
                    await self.handle_animate_prompt(event)
                elif state == "animate_negative":
                    await self.handle_animate_negative(event)
                elif state == "camera_image":
                    if event.media:
                        await self.handle_camera_image(event)
                    else:
                        await event.respond("📷 Please send an image!")
                elif state == "camera_prompt":
                    await self.handle_camera_prompt(event)
                elif state == "camera_negative":
                    await self.handle_camera_negative(event)
            except Exception as e:
                logger.error(f"Message handler error: {e}", exc_info=True)
                await event.respond("❌ An error occurred. Please try again or /start")
    
    async def show_main_menu(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'main_menu'
        
        await event.edit(
            f"🎬 **{BOT_USERNAME} Main Menu**\n\n"
            "Choose what you want to create:",
            buttons=[
                [Button.inline("📝 Text to Video", "t2v")],
                [Button.inline("🖼️ Image to Video", "i2v")],
                [Button.inline("🎭 Animate Character", "animate")],
                [Button.inline("📹 Camera Motion", "camera")],
                [Button.inline("ℹ️ Help", "help")]
            ]
        )
    
    async def start_t2v(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 't2v_prompt'
        self.user_data[user_id] = {
            'type': 't2v',
            'prompt': '',
            'negative_prompt': '',
            'width': 832,
            'height': 480,
            'num_frames': 121,
            'steps': 30,
            'cfg': 7.5,
            'use_fast_mode': False
        }
        
        await event.edit(
            "📝 **Text to Video**\n\n"
            "Send me a descriptive prompt for your video.\n\n"
            "Example: `A beautiful sunset over the ocean with waves gently crashing`",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_i2v(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'i2v_image'
        self.user_data[user_id] = {
            'type': 'i2v',
            'image_base64': '',
            'prompt': '',
            'negative_prompt': '',
            'width': 1280,
            'height': 704,
            'num_frames': 81,
            'steps': 20,
            'cfg': 3.5,
            'use_fast_mode': False
        }
        
        await event.edit(
            "🖼️ **Image to Video**\n\n"
            "Please send me an image that you want to animate.\n\n"
            "Supported: JPG, PNG, WebP\n"
            "Max size: 20MB",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_animate(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'animate_ref_image'
        self.user_data[user_id] = {
            'type': 'animate',
            'reference_image_base64': '',
            'video_base64': '',
            'prompt': '',
            'negative_prompt': '',
            'width': 640,
            'height': 640,
            'num_frames': 77,
            'steps': 6,
            'cfg': 1.0,
            'use_fast_mode': True
        }
        
        await event.edit(
            "🎭 **Animate Character**\n\n"
            "This transfers motion from a video to your character.\n\n"
            "**Step 1:** Send me a reference image of your character\n\n"
            "Supported: JPG, PNG, WebP\n"
            "Max size: 20MB",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_camera(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'camera_motion'
        
        buttons = []
        for i in range(0, len(self.camera_motions), 2):
            row = []
            if i < len(self.camera_motions):
                row.append(Button.inline(f"📹 {self.camera_motions[i]}", f"camera_{self.camera_motions[i]}"))
            if i + 1 < len(self.camera_motions):
                row.append(Button.inline(f"📹 {self.camera_motions[i+1]}", f"camera_{self.camera_motions[i+1]}"))
            if row:
                buttons.append(row)
        
        buttons.append([Button.inline("🔙 Back", "main_menu")])
        
        await event.edit(
            "📹 **Camera Motion**\n\n"
            "Select a camera motion to apply:",
            buttons=buttons
        )
    
    async def select_camera_motion(self, event, motion):
        user_id = event.sender_id
        self.user_states[user_id] = 'camera_image'
        self.user_data[user_id] = {
            'type': 'camera',
            'camera_motion': motion,
            'lora_strength': 1.0,
            'image_base64': '',
            'prompt': '',
            'negative_prompt': '',
            'width': 1280,
            'height': 704,
            'num_frames': 81,
            'steps': 20,
            'cfg': 3.5
        }
        
        await event.edit(
            f"📹 **Camera Motion: {motion}**\n\n"
            "Now send me an image to apply this motion.\n\n"
            "Supported: JPG, PNG, WebP\n"
            "Max size: 20MB",
            buttons=[
                [Button.inline("🔙 Back", "camera")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_t2v_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 10:
            await event.respond("⚠️ Prompt too short! Please provide more detail.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 't2v_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Send a negative prompt (what you DON'T want).\n"
            "Or send /skip to continue.",
            buttons=[[Button.inline("Generate Now", "generate")]]
        )
    
    async def handle_t2v_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        await self.show_generate_confirm(event, user_id)
    
    async def handle_i2v_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image!")
                return
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large! Max 20MB.")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['image_base64'] = image_b64
            self.user_states[user_id] = 'i2v_prompt'
            
            await event.respond(
                "✅ Image received!\n\n"
                "Send a prompt describing how to animate it.\n\n"
                "Example: `Camera slowly zooming in`"
            )
        except Exception as e:
            logger.error(f"Image processing error: {e}", exc_info=True)
            await event.respond("❌ Error processing image. Try again.")
    
    async def handle_i2v_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short!")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'i2v_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Send negative prompt or /skip",
            buttons=[[Button.inline("Generate Now", "generate")]]
        )
    
    async def handle_i2v_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        await self.show_generate_confirm(event, user_id)
    
    async def handle_animate_ref_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image!")
                return
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large!")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['reference_image_base64'] = image_b64
            self.user_states[user_id] = 'animate_video'
            
            await event.respond(
                "✅ Reference image received!\n\n"
                "**Step 2:** Send a video with the motion to transfer.\n\n"
                "Supported: MP4, WebM\n"
                "Max: 20MB"
            )
        except Exception as e:
            logger.error(f"Image error: {e}", exc_info=True)
            await event.respond("❌ Error processing image.")
    
    async def handle_animate_video(self, event):
        user_id = event.sender_id
        
        try:
            if event.video:
                video = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_VIDEO_TYPES:
                video = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid video!")
                return
            
            if len(video) > MAX_FILE_SIZE:
                await event.respond("⚠️ Video too large!")
                return
            
            video_b64 = base64.b64encode(video).decode('utf-8')
            self.user_data[user_id]['video_base64'] = video_b64
            self.user_states[user_id] = 'animate_prompt'
            
            await event.respond(
                "✅ Video received!\n\n"
                "Send a prompt describing the animation.\n\n"
                "Example: `Character dancing happily`"
            )
        except Exception as e:
            logger.error(f"Video error: {e}", exc_info=True)
            await event.respond("❌ Error processing video.")
    
    async def handle_animate_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short!")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'animate_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Send negative prompt or /skip",
            buttons=[[Button.inline("Generate Now", "generate")]]
        )
    
    async def handle_animate_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        await self.show_generate_confirm(event, user_id)
    
    async def handle_camera_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image!")
                return
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large!")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['image_base64'] = image_b64
            self.user_states[user_id] = 'camera_prompt'
            
            await event.respond(
                "✅ Image received!\n\n"
                "Send a prompt describing the scene.\n\n"
                "Example: `Beautiful landscape with mountains`"
            )
        except Exception as e:
            logger.error(f"Image error: {e}", exc_info=True)
            await event.respond("❌ Error processing image.")
    
    async def handle_camera_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short!")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'camera_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Send negative prompt or /skip",
            buttons=[[Button.inline("Generate Now", "generate")]]
        )
    
    async def handle_camera_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        await self.show_generate_confirm(event, user_id)
    
    async def handle_skip(self, event):
        user_id = event.sender_id
        if user_id in self.user_states:
            state = self.user_states[user_id]
            if 'negative' in state:
                self.user_data[user_id]['negative_prompt'] = ''
                await self.show_generate_confirm(event, user_id)
    
    async def show_generate_confirm(self, event, user_id):
        await event.respond(
            "✅ Ready to generate!\n\n"
            "Click below to start generation.",
            buttons=[[Button.inline("🎬 Generate Video", "generate")]]
        )
    
    async def generate_video(self, event):
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ No data found", alert=True)
            return
        
        data = self.user_data[user_id]
        
        processing_msg = await self.client.send_message(
            event.chat_id,
            "⏳ **Processing...**\n\n"
            "This may take 1-3 minutes.\n"
            "Please wait...\n\n"
            "🎬 Generating video..."
        )
        
        try:
            if data['type'] == 't2v':
                endpoint = f"{MODAL_API_URL}/api/generate/t2v"
                payload = {
                    'prompt': data['prompt'],
                    'negative_prompt': data.get('negative_prompt', ''),
                    'width': data['width'],
                    'height': data['height'],
                    'num_frames': data['num_frames'],
                    'steps': data['steps'],
                    'cfg': data['cfg'],
                    'use_fast_mode': data['use_fast_mode']
                }
            elif data['type'] == 'i2v':
                endpoint = f"{MODAL_API_URL}/api/generate/i2v"
                payload = {
                    'image_base64': data['image_base64'],
                    'prompt': data['prompt'],
                    'negative_prompt': data.get('negative_prompt', ''),
                    'width': data['width'],
                    'height': data['height'],
                    'num_frames': data['num_frames'],
                    'steps': data['steps'],
                    'cfg': data['cfg'],
                    'use_fast_mode': data['use_fast_mode']
                }
            elif data['type'] == 'animate':
                endpoint = f"{MODAL_API_URL}/api/generate/animate"
                payload = {
                    'reference_image_base64': data['reference_image_base64'],
                    'video_base64': data['video_base64'],
                    'prompt': data['prompt'],
                    'negative_prompt': data.get('negative_prompt', ''),
                    'width': data['width'],
                    'height': data['height'],
                    'num_frames': data['num_frames'],
                    'steps': data['steps'],
                    'cfg': data['cfg'],
                    'use_fast_mode': data['use_fast_mode']
                }
            elif data['type'] == 'camera':
                endpoint = f"{MODAL_API_URL}/api/generate/camera-lora"
                payload = {
                    'image_base64': data['image_base64'],
                    'prompt': data['prompt'],
                    'camera_motion': data['camera_motion'],
                    'lora_strength': data['lora_strength'],
                    'negative_prompt': data.get('negative_prompt', ''),
                    'width': data['width'],
                    'height': data['height'],
                    'num_frames': data['num_frames'],
                    'steps': data['steps'],
                    'cfg': data['cfg']
                }
            else:
                await processing_msg.edit("❌ Invalid request type")
                return
            
            response = requests.post(endpoint, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                video_b64 = result.get('video_base64')
                
                if video_b64:
                    video_bytes = base64.b64decode(video_b64)
                    video_file = io.BytesIO(video_bytes)
                    video_file.name = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                    
                    await self.client.send_file(
                        event.chat_id,
                        video_file,
                        caption="✅ **Video generated successfully!**"
                    )
                    
                    await processing_msg.delete()
                    
                    if user_id in self.user_data:
                        del self.user_data[user_id]
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                else:
                    await processing_msg.edit("❌ No video in response")
            else:
                error_msg = response.text[:500]
                await processing_msg.edit(
                    f"❌ **Error generating video**\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_msg}"
                )
        except requests.Timeout:
            await processing_msg.edit("⏰ Request timeout. Please try again.")
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
    
    async def cancel_operation(self, event):
        user_id = event.sender_id
        
        if user_id in self.user_data:
            del self.user_data[user_id]
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await event.edit(
            "❌ **Operation cancelled**\n\n"
            "Returning to main menu...",
            buttons=[[Button.inline("🔙 Main Menu", "main_menu")]]
        )
    
    async def show_help(self, event):
        await event.edit(
            "🤖 **Bot Help**\n\n"
            "**Features:**\n"
            "• 📝 Text to Video\n"
            "• 🖼️ Image to Video\n"
            "• 🎭 Animate Character\n"
            "• 📹 Camera Motion\n\n"
            "**How to use:**\n"
            "1. Select a feature\n"
            "2. Follow instructions\n"
            "3. Wait 1-3 minutes\n"
            "4. Download video!\n\n"
            "**Tips:**\n"
            "• Use descriptive prompts\n"
            "• Clear, well-lit images\n"
            "• 16:9 or 1:1 aspect ratios",
            buttons=[[Button.inline("🔙 Back", "main_menu")]]
        )
    
    async def show_help_message(self, event):
        await event.respond(
            "🤖 **Bot Help**\n\n"
            "**Features:**\n"
            "• 📝 Text to Video\n"
            "• 🖼️ Image to Video\n"
            "• 🎭 Animate Character\n"
            "• 📹 Camera Motion\n\n"
            "Use /start to begin!",
            buttons=[[Button.inline("🔙 Main Menu", "main_menu")]]
        )
    
    def run(self):
        logger.info("Bot started!")
        self.client.run_until_disconnected()

if __name__ == '__main__':
    bot = WanVideoBot()
    bot.run()
