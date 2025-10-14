import os
import base64
import io
import asyncio
import logging
import threading
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque

import requests
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from flask import Flask, request, jsonify

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
BOT_USERNAME = os.getenv('BOT_USERNAME', 'WanVideoBot')

# Bot configuration
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
SUPPORTED_VIDEO_TYPES = ['video/mp4', 'video/webm']

# Rate limiting configuration
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
MAX_REQUESTS_PER_HOUR = 5
CONCURRENT_TASKS_PER_USER = 1

# Queue configuration
MAX_GLOBAL_QUEUE = 10

class RateLimiter:
    """Rate limiter for user requests"""
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)
    
    def is_allowed(self, user_id: int) -> tuple[bool, Optional[int]]:
        """Check if user is allowed to make request. Returns (allowed, seconds_until_reset)"""
        now = datetime.now()
        user_requests = self.requests[user_id]
        
        # Remove old requests outside the window
        while user_requests and (now - user_requests[0]).total_seconds() > self.window_seconds:
            user_requests.popleft()
        
        if len(user_requests) >= self.max_requests:
            oldest_request = user_requests[0]
            seconds_until_reset = int(self.window_seconds - (now - oldest_request).total_seconds())
            return False, seconds_until_reset
        
        return True, None
    
    def add_request(self, user_id: int):
        """Record a new request"""
        self.requests[user_id].append(datetime.now())
    
    def get_remaining_requests(self, user_id: int) -> int:
        """Get remaining requests for user"""
        now = datetime.now()
        user_requests = self.requests[user_id]
        
        # Remove old requests
        while user_requests and (now - user_requests[0]).total_seconds() > self.window_seconds:
            user_requests.popleft()
        
        return self.max_requests - len(user_requests)

class TaskQueue:
    """Queue manager for video generation tasks"""
    def __init__(self, max_global: int, max_per_user: int):
        self.max_global = max_global
        self.max_per_user = max_per_user
        self.global_queue = []
        self.user_tasks = defaultdict(int)
        self.lock = threading.Lock()
    
    def can_add_task(self, user_id: int) -> tuple[bool, Optional[str]]:
        """Check if task can be added. Returns (allowed, reason)"""
        with self.lock:
            if len(self.global_queue) >= self.max_global:
                return False, f"Server queue is full ({self.max_global} tasks). Please try again later."
            
            if self.user_tasks[user_id] >= self.max_per_user:
                return False, f"You have {self.max_per_user} task(s) in progress. Please wait for completion."
            
            return True, None
    
    def add_task(self, task_id: str, user_id: int):
        """Add task to queue"""
        with self.lock:
            self.global_queue.append(task_id)
            self.user_tasks[user_id] += 1
    
    def remove_task(self, task_id: str, user_id: int):
        """Remove task from queue"""
        with self.lock:
            if task_id in self.global_queue:
                self.global_queue.remove(task_id)
            if self.user_tasks[user_id] > 0:
                self.user_tasks[user_id] -= 1
    
    def get_queue_info(self, user_id: int) -> Dict[str, int]:
        """Get queue information"""
        with self.lock:
            return {
                'global_queue': len(self.global_queue),
                'max_global': self.max_global,
                'user_tasks': self.user_tasks[user_id],
                'max_per_user': self.max_per_user
            }

class WanVideoBot:
    def __init__(self):
        self.client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        self.user_states = {}
        self.user_data = {}
        self.task_to_user = {}
        self.WEBHOOK_URL = os.getenv('KINSTA_PUBLIC_URL', 'https://tes-brq7a.sevalla.app/').rstrip('/') + '/webhook'
        
        # Rate limiting and queue management
        self.rate_limiter = RateLimiter(MAX_REQUESTS_PER_HOUR, RATE_LIMIT_WINDOW)
        self.task_queue = TaskQueue(MAX_GLOBAL_QUEUE, CONCURRENT_TASKS_PER_USER)
        
        self.camera_motions = [
            "ZoomIn", "ZoomOut", "PanLeft", "PanRight", 
            "TiltUp", "TiltDown", "RollingClockwise", "RollingAnticlockwise"
        ]
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup all event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.show_main_menu_message(event)
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await self.show_help_message(event)
        
        @self.client.on(events.NewMessage(pattern='/skip'))
        async def skip_handler(event):
            await self.handle_skip(event)
        
        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            await self.show_stats(event)
        
        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            await self.handle_callback(event)
        
        @self.client.on(events.NewMessage(func=lambda e: not e.text.startswith('/')))
        async def message_handler(event):
            await self.handle_message(event)
    
    async def handle_callback(self, event):
        """Handle callback queries"""
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        try:
            if data == "main_menu":
                await self.show_main_menu(event)
            elif data == "t2v":
                await self.start_mode(event, 't2v')
            elif data == "i2v":
                await self.start_mode(event, 'i2v')
            elif data == "animate":
                await self.start_mode(event, 'animate')
            elif data == "camera":
                await self.start_camera_selection(event)
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
    
    async def handle_message(self, event):
        """Handle text and media messages"""
        user_id = event.sender_id
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        try:
            # Text handlers
            if state.endswith('_prompt'):
                await self.handle_prompt(event, state.replace('_prompt', ''))
            elif state.endswith('_negative'):
                await self.handle_negative_prompt(event, state.replace('_negative', ''))
            # Media handlers
            elif state.endswith('_image'):
                if event.media:
                    await self.handle_image(event, state.replace('_image', ''))
                else:
                    await event.respond("📷 Please send an image!")
            elif state == 'animate_video':
                if event.media:
                    await self.handle_video(event)
                else:
                    await event.respond("🎬 Please send a video!")
        except Exception as e:
            logger.error(f"Message handler error: {e}", exc_info=True)
            await event.respond("❌ An error occurred. Please try /start again.")
    
    async def show_main_menu_message(self, event):
        """Show main menu as new message"""
        user_id = event.sender_id
        self.user_states[user_id] = 'main_menu'
        
        await event.respond(
            f"🎬 **Welcome to {BOT_USERNAME}!**\n\n"
            "I can generate videos from text, images, or apply camera motions.\n\n"
            "Choose an option below:",
            buttons=self.get_main_menu_buttons()
        )
    
    async def show_main_menu(self, event):
        """Show main menu by editing message"""
        user_id = event.sender_id
        self.user_states[user_id] = 'main_menu'
        
        await event.edit(
            f"🎬 **{BOT_USERNAME} Main Menu**\n\n"
            "Choose what you want to create:",
            buttons=self.get_main_menu_buttons()
        )
    
    def get_main_menu_buttons(self):
        """Get main menu buttons"""
        return [
            [Button.inline("📝 Text to Video", "t2v")],
            [Button.inline("🖼️ Image to Video", "i2v")],
            [Button.inline("🎭 Animate Character", "animate")],
            [Button.inline("📹 Camera Motion", "camera")],
            [Button.inline("ℹ️ Help", "help")]
        ]
    
    async def start_mode(self, event, mode: str):
        """Start a generation mode"""
        user_id = event.sender_id
        
        # Initialize user data based on mode
        mode_configs = {
            't2v': {
                'type': 't2v',
                'state': 't2v_prompt',
                'title': '📝 **Text to Video**',
                'prompt_text': 'Send me a descriptive prompt for your video.\n\nExample: `A beautiful sunset over the ocean with waves gently crashing`',
                'data': {'width': 832, 'height': 480, 'num_frames': 121, 'steps': 30, 'cfg': 7.5, 'use_fast_mode': False}
            },
            'i2v': {
                'type': 'i2v',
                'state': 'i2v_image',
                'title': '🖼️ **Image to Video**',
                'prompt_text': 'Please send me an image that you want to animate.\n\nSupported: JPG, PNG, WebP\nMax size: 20MB',
                'data': {'width': 1280, 'height': 704, 'num_frames': 81, 'steps': 20, 'cfg': 3.5, 'use_fast_mode': True}
            },
            'animate': {
                'type': 'animate',
                'state': 'animate_ref_image',
                'title': '🎭 **Animate Character**',
                'prompt_text': 'This transfers motion from a video to your character.\n\n**Step 1:** Send me a reference image of your character\n\nSupported: JPG, PNG, WebP\nMax size: 20MB',
                'data': {'width': 640, 'height': 640, 'num_frames': 77, 'steps': 6, 'cfg': 1.0, 'use_fast_mode': True}
            }
        }
        
        config = mode_configs[mode]
        self.user_states[user_id] = config['state']
        self.user_data[user_id] = {
            'type': config['type'],
            'prompt': '',
            'negative_prompt': '',
            **config['data']
        }
        
        await event.edit(
            f"{config['title']}\n\n{config['prompt_text']}",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def start_camera_selection(self, event):
        """Show camera motion selection"""
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
        """Select camera motion and proceed"""
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
            "Supported: JPG, PNG, WebP\nMax size: 20MB",
            buttons=[
                [Button.inline("🔙 Back", "camera")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_prompt(self, event, mode: str):
        """Handle prompt input"""
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short! Please provide more detail.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = f'{mode}_negative'
        
        await event.respond(
            "✅ Prompt received!\n\n"
            "Send a negative prompt (what you DON'T want), or send /skip to continue.",
            buttons=[[Button.inline("Generate Now", "generate")]]
        )
    
    async def handle_negative_prompt(self, event, mode: str):
        """Handle negative prompt input"""
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        await self.show_generate_confirm(event)
    
    async def handle_image(self, event, mode: str):
        """Handle image upload"""
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
            
            # Store image based on mode
            if mode == 'animate_ref':
                self.user_data[user_id]['reference_image_base64'] = image_b64
                self.user_states[user_id] = 'animate_video'
                await event.respond(
                    "✅ Reference image received!\n\n"
                    "**Step 2:** Send a video with the motion to transfer.\n\n"
                    "Supported: MP4, WebM\nMax: 20MB"
                )
            else:
                self.user_data[user_id]['image_base64'] = image_b64
                self.user_states[user_id] = f'{mode}_prompt'
                await event.respond(
                    "✅ Image received!\n\n"
                    "Send a prompt describing how to animate it.\n\n"
                    "Example: `Camera slowly zooming in`"
                )
        except Exception as e:
            logger.error(f"Image processing error: {e}", exc_info=True)
            await event.respond("❌ Error processing image. Try again.")
    
    async def handle_video(self, event):
        """Handle video upload for animate mode"""
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
                await event.respond("⚠️ Video too large! Max 20MB.")
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
    
    async def handle_skip(self, event):
        """Handle skip command"""
        user_id = event.sender_id
        if user_id in self.user_states:
            state = self.user_states[user_id]
            if 'negative' in state:
                self.user_data[user_id]['negative_prompt'] = ''
                await self.show_generate_confirm(event)
    
    async def show_generate_confirm(self, event):
        """Show generation confirmation"""
        await event.respond(
            "✅ Ready to generate!\n\n"
            "Click below to start generation.",
            buttons=[[Button.inline("🎬 Generate Video", "generate")]]
        )
    
    async def generate_video(self, event):
        """Generate video with rate limiting and queue management"""
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ No data found, please /start again.", alert=True)
            return
        
        # Check rate limit
        allowed, wait_time = self.rate_limiter.is_allowed(user_id)
        if not allowed:
            remaining = self.rate_limiter.get_remaining_requests(user_id)
            await event.answer(
                f"⏳ Rate limit reached!\n\n"
                f"You can make {remaining} more request(s) in {wait_time} seconds.\n"
                f"Limit: {MAX_REQUESTS_PER_HOUR} requests per hour.",
                alert=True
            )
            return
        
        # Check queue
        can_add, reason = self.task_queue.can_add_task(user_id)
        if not can_add:
            await event.answer(f"⏳ {reason}", alert=True)
            return
        
        # Create task
        task_id = str(uuid.uuid4())
        self.task_to_user[task_id] = user_id
        
        # Add to queue and rate limiter
        self.task_queue.add_task(task_id, user_id)
        self.rate_limiter.add_request(user_id)
        
        data = self.user_data[user_id]
        
        # Build endpoint and payload
        endpoint_map = {
            't2v': f"{MODAL_API_URL}/api/generate/t2v",
            'i2v': f"{MODAL_API_URL}/api/generate/i2v",
            'animate': f"{MODAL_API_URL}/api/generate/animate",
            'camera': f"{MODAL_API_URL}/api/generate/camera-lora"
        }
        
        endpoint = endpoint_map.get(data['type'])
        if not endpoint:
            await event.respond("❌ Invalid request type")
            self.task_queue.remove_task(task_id, user_id)
            return
        
        payload = {k: v for k, v in data.items() if k != 'type'}
        payload['webhook_url'] = self.WEBHOOK_URL
        payload['task_id'] = task_id
        
        try:
            queue_info = self.task_queue.get_queue_info(user_id)
            remaining = self.rate_limiter.get_remaining_requests(user_id)
            
            processing_msg = await self.client.send_message(
                event.chat_id,
                "✅ **Task accepted!**\n\n"
                "Sending to processing server...\n\n"
                f"📊 Queue: {queue_info['global_queue']}/{queue_info['max_global']}\n"
                f"⏳ Your tasks: {queue_info['user_tasks']}/{queue_info['max_per_user']}\n"
                f"🔄 Remaining requests: {remaining}/{MAX_REQUESTS_PER_HOUR}"
            )
            
            response = requests.post(endpoint, json=payload, timeout=30)
            
            if response.status_code == 200:
                await processing_msg.edit(
                    "🚀 **Task successfully submitted!**\n\n"
                    "Video is being processed. I will send it to you when done (usually 1-3 minutes).\n\n"
                    f"📊 Queue position: {queue_info['global_queue']}/{queue_info['max_global']}\n"
                    f"⏳ Your active tasks: {queue_info['user_tasks']}/{queue_info['max_per_user']}\n\n"
                    "You can start a new task if you want."
                )
            else:
                error_msg = response.text[:500]
                await processing_msg.edit(
                    f"❌ **Failed to submit task**\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_msg}"
                )
                self.task_queue.remove_task(task_id, user_id)
                del self.task_to_user[task_id]
        
        except requests.Timeout:
            await processing_msg.edit("⏰ Server not responding. Failed to submit task. Try again later.")
            self.task_queue.remove_task(task_id, user_id)
            del self.task_to_user[task_id]
        except Exception as e:
            logger.error(f"Submission error: {e}", exc_info=True)
            await processing_msg.edit(f"❌ Error submitting: {str(e)[:200]}")
            self.task_queue.remove_task(task_id, user_id)
            del self.task_to_user[task_id]
        
        # Cleanup user data
        if user_id in self.user_data:
            del self.user_data[user_id]
        if user_id in self.user_states:
            del self.user_states[user_id]
    
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
        """Show help menu"""
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
            "**Limits:**\n"
            f"• Max {MAX_REQUESTS_PER_HOUR} videos per hour\n"
            f"• Max {CONCURRENT_TASKS_PER_USER} concurrent task\n"
            "• Max 20MB file size\n\n"
            "**Tips:**\n"
            "• Use descriptive prompts\n"
            "• Clear, well-lit images\n"
            "• 16:9 or 1:1 aspect ratios",
            buttons=[[Button.inline("🔙 Back", "main_menu")]]
        )
    
    async def show_help_message(self, event):
        """Show help as new message"""
        await event.respond(
            "🤖 **Bot Help**\n\n"
            "**Features:**\n"
            "• 📝 Text to Video\n"
            "• 🖼️ Image to Video\n"
            "• 🎭 Animate Character\n"
            "• 📹 Camera Motion\n\n"
            f"**Limits:**\n"
            f"• {MAX_REQUESTS_PER_HOUR} videos per hour\n"
            f"• {CONCURRENT_TASKS_PER_USER} concurrent task per user\n\n"
            "Use /start to begin!",
            buttons=[[Button.inline("🔙 Main Menu", "main_menu")]]
        )
    
    async def show_stats(self, event):
        """Show user statistics"""
        user_id = event.sender_id
        queue_info = self.task_queue.get_queue_info(user_id)
        remaining = self.rate_limiter.get_remaining_requests(user_id)
        
        await event.respond(
            "📊 **Your Statistics**\n\n"
            f"🔄 Remaining requests: {remaining}/{MAX_REQUESTS_PER_HOUR}\n"
            f"⏳ Your active tasks: {queue_info['user_tasks']}/{queue_info['max_per_user']}\n"
            f"📊 Global queue: {queue_info['global_queue']}/{queue_info['max_global']}\n\n"
            f"Rate limit resets every hour.",
            buttons=[[Button.inline("🔙 Main Menu", "main_menu")]]
        )
    
    def run(self):
        """Run the bot"""
        logger.info("Bot started!")
        self.client.run_until_disconnected()

# Flask webhook server
flask_app = Flask(__name__)
bot_instance = None

@flask_app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle webhook from Modal server"""
    global bot_instance
    if not bot_instance:
        return jsonify({"status": "error", "message": "Bot not initialized"}), 500
    
    data = request.json
    task_id = data.get('task_id')
    status = data.get('status')
    
    if not task_id or task_id not in bot_instance.task_to_user:
        logger.warning(f"Webhook received for unknown task_id: {task_id}")
        return jsonify({"status": "ignored", "reason": "unknown task_id"}), 200
    
    user_id = bot_instance.task_to_user.get(task_id)
    
    async def send_result():
        try:
            if status == 'success':
                video_b64 = data.get('video_base64')
                video_bytes = base64.b64decode(video_b64)
                video_file = io.BytesIO(video_bytes)
                video_file.name = f"video_{task_id[:8]}.mp4"
                
                queue_info = bot_instance.task_queue.get_queue_info(user_id)
                remaining = bot_instance.rate_limiter.get_remaining_requests(user_id)
                
                await bot_instance.client.send_file(
                    user_id,
                    video_file,
                    caption=(
                        "✅ **Your video is ready!**\n\n"
                        f"📊 Queue: {queue_info['global_queue']}/{queue_info['max_global']}\n"
                        f"🔄 Remaining requests: {remaining}/{MAX_REQUESTS_PER_HOUR}"
                    )
                )
            else:
                error_detail = data.get('detail', 'Unknown error')
                await bot_instance.client.send_message(
                    user_id,
                    f"❌ **Sorry, an error occurred while processing your video.**\n\n"
                    f"Detail: `{error_detail}`\n\n"
                    "Please try again or contact support if the problem persists."
                )
        except Exception as e:
            logger.error(f"Error sending result to user {user_id}: {e}")
        finally:
            # Remove task from queue
            bot_instance.task_queue.remove_task(task_id, user_id)
            if task_id in bot_instance.task_to_user:
                del bot_instance.task_to_user[task_id]
    
    # Run async function from Flask
    asyncio.run_coroutine_threadsafe(send_result(), bot_instance.client.loop)
    
    return jsonify({"status": "received"}), 200

@flask_app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    global bot_instance
    if not bot_instance:
        return jsonify({"status": "error", "message": "Bot not initialized"}), 500
    
    return jsonify({
        "status": "healthy",
        "bot_running": True,
        "webhook_url": bot_instance.WEBHOOK_URL
    }), 200

def run_flask():
    """Run Flask server"""
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == '__main__':
    bot_instance = WanVideoBot()
    
    # Run Flask in separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Bot and Webhook server started!")
    logger.info(f"Webhook URL: {bot_instance.WEBHOOK_URL}")
    logger.info(f"Rate limit: {MAX_REQUESTS_PER_HOUR} requests per hour")
    logger.info(f"Max concurrent tasks per user: {CONCURRENT_TASKS_PER_USER}")
    logger.info(f"Max global queue: {MAX_GLOBAL_QUEUE}")
    
    bot_instance.run()
