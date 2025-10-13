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
from telethon.tl.types import (
    InputMediaPhoto, InputMediaDocument, 
    InputMediaVideo, InputMediaAnimation
)
from telethon.errors import FloodWait, MessageNotModified
from telethon.tl.custom import Button

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MODAL_API_URL = os.getenv('MODAL_API_URL', 'https://your-app.modal.run')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Bot configuration
BOT_USERNAME = os.getenv('BOT_USERNAME', 'WanVideoBot')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
SUPPORTED_VIDEO_TYPES = ['video/mp4', 'video/webm']

class WanVideoBot:
    def __init__(self):
        self.client = TelegramClient(
            'bot_session',
            API_ID,
            API_HASH
        ).start(bot_token=BOT_TOKEN)
        
        self.user_states = {}  # Store user states
        self.user_data = {}   # Store user data (images, videos, etc.)
        
        # Camera motions list
        self.camera_motions = [
            "ZoomIn", "ZoomOut", "PanLeft", "PanRight", 
            "TiltUp", "TiltDown", "RollingClockwise", "RollingAnticlockwise"
        ]
        
        # Setup handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup all event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            """Handle /start command"""
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
                    [Button.inline("ℹ️ Help", "help")],
                    [Button.inline("⚙️ Settings", "settings")]
                ],
                file='https://telegra.ph/file/4a3c8b5c5d5d5d5d5d5d5.jpg'  # Replace with your image
            )
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            """Handle /help command"""
            help_text = (
                "🤖 **Bot Help**\n\n"
                "**Features:**\n"
                "• 📝 Text to Video - Generate video from text prompt\n"
                "• 🖼️ Image to Video - Animate static image\n"
                "• 🎭 Animate - Character pose transfer\n"
                "• 📹 Camera Motion - Apply camera movements\n\n"
                "**How to use:**\n"
                "1. Select a feature from the menu\n"
                "2. Follow the instructions\n"
                "3. Wait for processing (1-3 minutes)\n"
                "4. Download your video!\n\n"
                "**Tips:**\n"
                "• Use descriptive prompts\n"
                "• Images should be clear and well-lit\n"
                "• For best results, use 16:9 or 1:1 aspect ratios\n\n"
                "**Support:** @admin"
            )
            
            await event.respond(
                help_text,
                buttons=[[Button.inline("🔙 Back to Menu", "main_menu")]]
            )
        
        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            """Handle button callbacks"""
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
                
                elif data == "settings":
                    await self.show_settings(event)
                
                elif data.startswith("camera_"):
                    motion = data.replace("camera_", "")
                    await self.select_camera_motion(event, motion)
                
                elif data.startswith("quality_"):
                    quality = data.replace("quality_", "")
                    await self.select_quality(event, quality)
                
                elif data.startswith("fast_mode_"):
                    fast_mode = data.replace("fast_mode_", "")
                    await self.toggle_fast_mode(event, fast_mode == "on")
                
                elif data == "cancel":
                    await self.cancel_operation(event)
                
                elif data == "generate":
                    await self.generate_video(event)
                
            except Exception as e:
                logger.error(f"Callback error: {e}")
                await event.answer("❌ Error occurred", alert=True)
        
        @self.client.on(events.NewMessage())
        async def message_handler(event):
            """Handle text and media messages"""
            user_id = event.sender_id
            
            # Skip if user is not in a state
            if user_id not in self.user_states:
                return
            
            state = self.user_states[user_id]
            
            # Handle different states
            if state == "t2v_prompt":
                await self.handle_t2v_prompt(event)
            
            elif state == "i2v_image":
                if event.media:
                    await self.handle_i2v_image(event)
                else:
                    await event.respond("📷 Please send an image first!")
            
            elif state == "i2v_prompt":
                await self.handle_i2v_prompt(event)
            
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
            
            elif state == "camera_image":
                if event.media:
                    await self.handle_camera_image(event)
                else:
                    await event.respond("📷 Please send an image!")
            
            elif state == "camera_prompt":
                await self.handle_camera_prompt(event)
    
    async def show_main_menu(self, event):
        """Show main menu"""
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
                [Button.inline("ℹ️ Help", "help")],
                [Button.inline("⚙️ Settings", "settings")]
            ]
        )
    
    async def start_t2v(self, event):
        """Start Text to Video process"""
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
            "Example: `A beautiful sunset over the ocean with waves gently crashing`\n\n"
            "⚙️ **Current Settings:**\n"
            f"• Resolution: {self.user_data[user_id]['width']}x{self.user_data[user_id]['height']}\n"
            f"• Frames: {self.user_data[user_id]['num_frames']}\n"
            f"• Steps: {self.user_data[user_id]['steps']}\n"
            f"• Fast Mode: {'ON' if self.user_data[user_id]['use_fast_mode'] else 'OFF'}\n\n"
            "Buttons:",
            buttons=[
                [Button.inline("⚙️ Change Settings", "t2v_settings")],
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_i2v(self, event):
        """Start Image to Video process"""
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
            "Supported formats: JPG, PNG, WebP\n"
            "Max size: 20MB\n\n"
            "⚙️ **Current Settings:**\n"
            f"• Resolution: {self.user_data[user_id]['width']}x{self.user_data[user_id]['height']}\n"
            f"• Frames: {self.user_data[user_id]['num_frames']}\n"
            f"• Steps: {self.user_data[user_id]['steps']}\n"
            f"• Fast Mode: {'ON' if self.user_data[user_id]['use_fast_mode'] else 'OFF'}\n\n"
            "Buttons:",
            buttons=[
                [Button.inline("⚙️ Change Settings", "i2v_settings")],
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_animate(self, event):
        """Start Animate process"""
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
            "This feature transfers motion from a video to your character.\n\n"
            "**Step 1:** Send me a reference image of your character\n\n"
            "Supported formats: JPG, PNG, WebP\n"
            "Max size: 20MB\n\n"
            "Buttons:",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_camera(self, event):
        """Start Camera Motion process"""
        user_id = event.sender_id
        self.user_states[user_id] = 'camera_motion'
        
        # Create camera motion buttons
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
            "Select a camera motion to apply to your image:\n\n"
            "Available motions:",
            buttons=buttons
        )
    
    async def select_camera_motion(self, event, motion):
        """Handle camera motion selection"""
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
            "Now send me an image to apply this motion to.\n\n"
            "Supported formats: JPG, PNG, WebP\n"
            "Max size: 20MB\n\n"
            f"⚙️ **Current Settings:**\n"
            f"• Motion: {motion}\n"
            f"• Strength: {self.user_data[user_id]['lora_strength']}\n"
            f"• Resolution: {self.user_data[user_id]['width']}x{self.user_data[user_id]['height']}\n"
            f"• Frames: {self.user_data[user_id]['num_frames']}\n\n"
            "Buttons:",
            buttons=[
                [Button.inline("⚙️ Change Settings", "camera_settings")],
                [Button.inline("🔙 Back", "camera")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_t2v_prompt(self, event):
        """Handle T2V prompt input"""
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 10:
            await event.respond("⚠️ Prompt too short! Please provide a more detailed description.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 't2v_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Now send a negative prompt (optional).\n"
            "Describe what you DON'T want in the video.\n\n"
            "Or send /skip to continue without negative prompt.",
            buttons=[[Button.inline("🔙 Back", "t2v")]]
        )
    
    async def handle_i2v_image(self, event):
        """Handle I2V image input"""
        user_id = event.sender_id
        
        # Check if it's an image
        if not event.photo and not event.document:
            await event.respond("⚠️ Please send a valid image!")
            return
        
        # Download and process image
        try:
            # Get image bytes
            if event.photo:
                photo = await event.download_media(file=bytes)
            else:
                # Check if document is image
                if event.document.mime_type not in SUPPORTED_IMAGE_TYPES:
                    await event.respond("⚠️ Unsupported image format!")
                    return
                photo = await event.download_media(file=bytes)
            
            # Check file size
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large! Max size is 20MB.")
                return
            
            # Convert to base64
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['image_base64'] = image_b64
            self.user_states[user_id] = 'i2v_prompt'
            
            await event.respond(
                "✅ Image received!\n\n"
                "Now send me a prompt describing how you want to animate this image.\n\n"
                "Example: `Camera slowly zooming in, gentle movement`\n\n"
                "Buttons:",
                buttons=[[Button.inline("🔙 Back", "i2v")]]
            )
            
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            await event.respond("❌ Error processing image. Please try again.")
    
    async def handle_i2v_prompt(self, event):
        """Handle I2V prompt input"""
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short! Please provide a description.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'i2v_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Now send a negative prompt (optional).\n"
            "Describe what you DON'T want in the video.\n\n"
            "Or send /skip to continue without negative prompt.",
            buttons=[[Button.inline("🔙 Back", "i2v")]]
        )
    
    async def handle_animate_ref_image(self, event):
        """Handle animate reference image input"""
        user_id = event.sender_id
        
        # Check if it's an image
        if not event.photo and not event.document:
            await event.respond("⚠️ Please send a valid image!")
            return
        
        try:
            # Get image bytes
            if event.photo:
                photo = await event.download_media(file=bytes)
            else:
                if event.document.mime_type not in SUPPORTED_IMAGE_TYPES:
                    await event.respond("⚠️ Unsupported image format!")
                    return
                photo = await event.download_media(file=bytes)
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large! Max size is 20MB.")
                return
            
            # Convert to base64
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['reference_image_base64'] = image_b64
            self.user_states[user_id] = 'animate_video'
            
            await event.respond(
                "✅ Reference image received!\n\n"
                "**Step 2:** Now send me a video with the motion you want to transfer.\n\n"
                "Supported formats: MP4, WebM\n"
                "Max size: 20MB\n\n"
                "This video will provide the pose/motion for your character.",
                buttons=[[Button.inline("🔙 Back", "animate")]]
            )
            
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            await event.respond("❌ Error processing image. Please try again.")
    
    async def handle_animate_video(self, event):
        """Handle animate video input"""
        user_id = event.sender_id
        
        # Check if it's a video
        if not event.video and not event.document:
            await event.respond("⚠️ Please send a valid video!")
            return
        
        try:
            # Get video bytes
            if event.video:
                video = await event.download_media(file=bytes)
            else:
                if event.document.mime_type not in SUPPORTED_VIDEO_TYPES:
                    await event.respond("⚠️ Unsupported video format!")
                    return
                video = await event.download_media(file=bytes)
            
            if len(video) > MAX_FILE_SIZE:
                await event.respond("⚠️ Video too large! Max size is 20MB.")
                return
            
            # Convert to base64
            video_b64 = base64.b64encode(video).decode('utf-8')
            self.user_data[user_id]['video_base64'] = video_b64
            self.user_states[user_id] = 'animate_prompt'
            
            await event.respond(
                "✅ Video received!\n\n"
                "Now send me a prompt describing the animation.\n\n"
                "Example: `The character is dancing happily`\n\n"
                "Buttons:",
                buttons=[[Button.inline("🔙 Back", "animate")]]
            )
            
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            await event.respond("❌ Error processing video. Please try again.")
    
    async def handle_animate_prompt(self, event):
        """Handle animate prompt input"""
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short! Please provide a description.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'animate_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Now send a negative prompt (optional).\n"
            "Describe what you DON'T want in the video.\n\n"
            "Or send /skip to continue without negative prompt.",
            buttons=[[Button.inline("🔙 Back", "animate")]]
        )
    
    async def handle_camera_image(self, event):
        """Handle camera image input"""
        user_id = event.sender_id
        
        # Check if it's an image
        if not event.photo and not event.document:
            await event.respond("⚠️ Please send a valid image!")
            return
        
        try:
            # Get image bytes
            if event.photo:
                photo = await event.download_media(file=bytes)
            else:
                if event.document.mime_type not in SUPPORTED_IMAGE_TYPES:
                    await event.respond("⚠️ Unsupported image format!")
                    return
                photo = await event.download_media(file=bytes)
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large! Max size is 20MB.")
                return
            
            # Convert to base64
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['image_base64'] = image_b64
            self.user_states[user_id] = 'camera_prompt'
            
            await event.respond(
                "✅ Image received!\n\n"
                "Now send me a prompt describing the scene.\n\n"
                "Example: `A beautiful landscape with mountains`\n\n"
                "Buttons:",
                buttons=[[Button.inline("🔙 Back", "camera")]]
            )
            
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            await event.respond("❌ Error processing image. Please try again.")
    
    async def handle_camera_prompt(self, event):
        """Handle camera prompt input"""
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short! Please provide a description.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'camera_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Now send a negative prompt (optional).\n"
            "Describe what you DON'T want in the video.\n\n"
            "Or send /skip to continue without negative prompt.",
            buttons=[[Button.inline("🔙 Back", "camera")]]
        )
    
    async def generate_video(self, event):
        """Generate video using Modal API"""
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ No data found", alert=True)
            return
        
        data = self.user_data[user_id]
        
        # Show processing message
        processing_msg = await event.respond(
            "⏳ **Processing your request...**\n\n"
            "This may take 1-3 minutes depending on the complexity.\n"
            "Please wait patiently.\n\n"
            "🎬 Generating video..."
        )
        
        try:
            # Prepare API endpoint based on type
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
            
            # Make API request
            response = requests.post(endpoint, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                video_b64 = result.get('video_base64')
                
                if video_b64:
                    # Decode video
                    video_bytes = base64.b64decode(video_b64)
                    
                    # Send video to user
                    video_file = io.BytesIO(video_bytes)
                    video_file.name = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                    
                    await processing_msg.edit(
                        "✅ **Video generated successfully!**\n\n"
                        "Here's your video:",
                        file=video_file
                    )
                    
                    # Clean up user data
                    if user_id in self.user_data:
                        del self.user_data[user_id]
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    
                else:
                    await processing_msg.edit("❌ No video in response")
            
            else:
                error_msg = response.text
                await processing_msg.edit(
                    f"❌ **Error generating video**\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_msg[:500]}"
                )
        
        except requests.Timeout:
            await processing_msg.edit(
                "⏰ **Request timeout**\n\n"
                "The server took too long to respond. Please try again."
            )
        
        except Exception as e:
            logger.error(f"Generation error: {e}")
            await processing_msg.edit(
                f"❌ **Error occurred**\n\n"
                f"Error: {str(e)[:200]}"
            )
    
    async def cancel_operation(self, event):
        """Cancel current operation"""
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
        """Show help message"""
        help_text = (
            "🤖 **Bot Help**\n\n"
            "**Features:**\n"
            "• 📝 Text to Video - Generate video from text prompt\n"
            "• 🖼️ Image to Video - Animate static image\n"
            "• 🎭 Animate - Character pose transfer\n"
            "• 📹 Camera Motion - Apply camera movements\n\n"
            "**How to use:**\n"
            "1. Select a feature from the menu\n"
            "2. Follow the instructions\n"
            "3. Wait for processing (1-3 minutes)\n"
            "4. Download your video!\n\n"
            "**Tips:**\n"
            "• Use descriptive prompts\n"
            "• Images should be clear and well-lit\n"
            "• For best results, use 16:9 or 1:1 aspect ratios\n\n"
            "**Support:** @admin"
        )
        
        await event.edit(
            help_text,
            buttons=[[Button.inline("🔙 Back to Menu", "main_menu")]]
        )
    
    async def show_settings(self, event):
        """Show settings menu"""
        user_id = event.sender_id
        
        # Get current settings or defaults
        settings = self.user_data.get(user_id, {})
        
        await event.edit(
            "⚙️ **Settings**\n\n"
            "Global settings for all generations:\n\n"
            "Buttons:",
            buttons=[
                [Button.inline("🎨 Quality Presets", "quality_menu")],
                [Button.inline("⚡ Fast Mode", "fast_mode_menu")],
                [Button.inline("📊 Statistics", "stats")],
                [Button.inline("🔙 Back", "main_menu")]
            ]
        )
    
    def run(self):
        """Run the bot"""
        logger.info("Bot started!")
        self.client.run_until_disconnected()

# Main execution
if __name__ == '__main__':
    bot = WanVideoBot()
    bot.run()