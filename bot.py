import os
import base64
import io
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import requests
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.tl.custom import Button

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

API_ID = int(os.getenv('API_ID', '10446785'))
API_HASH = os.getenv('API_HASH', '4261b62d60200eb99a38dcd8b71c8634')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8222362928:AAG85K4WRPmf2yBPb_6j3uJiMHDYgscgolc')
MODAL_API_URL = os.getenv('MODAL_API_URL', 'https://oktetod--comfyui-wan2-2-complete-production-fastapi-app.modal.run')
ADMIN_ID = int(os.getenv('ADMIN_ID', '8484686373'))

BOT_USERNAME = os.getenv('BOT_USERNAME', 'WanVideoBot')
MAX_FILE_SIZE = 20 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
SUPPORTED_VIDEO_TYPES = ['video/mp4', 'video/webm']

LORA_CATEGORIES = {
    "style_loras": "🎨 Style",
    "character_loras": "👤 Character",
    "lighting_loras": "💡 Lighting",
    "environment_loras": "🌍 Environment",
    "effect_loras": "✨ Effect"
}

CONTROLNET_TYPES = {
    "canny": "🖊️ Canny (Edge)",
    "depth": "📏 Depth Map",
    "openpose": "🤸 OpenPose",
    "scribble": "✏️ Scribble"
}

class WanVideoBot:
    def __init__(self):
        self.client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        self.user_states = {}
        self.user_data = {}
        self.lora_registry = {}
        self.controlnet_list = list(CONTROLNET_TYPES.keys())
        self.setup_handlers()
    
    async def load_available_loras(self):
        try:
            response = requests.get(f"{MODAL_API_URL}/api/loras", timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.lora_registry = data.get('loras_by_category', {})
                logger.info(f"Loaded {data.get('total_loras', 0)} LoRAs")
        except Exception as e:
            logger.error(f"Failed to load LoRAs: {e}")
    
    def setup_handlers(self):
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = event.sender_id
            self.user_states[user_id] = 'main_menu'
            
            await event.respond(
                f"🎬 **Welcome to {BOT_USERNAME}!**\n\n"
                "✨ **New Features:**\n"
                "• 50 LoRAs across 5 categories\n"
                "• 4 ControlNet types\n"
                "• Enhanced video generation\n\n"
                "Choose an option below:",
                buttons=[
                    [Button.inline("📝 Text to Video", "t2v")],
                    [Button.inline("🖼️ Image to Video", "i2v")],
                    [Button.inline("🎭 Animate Character", "animate")],
                    [Button.inline("🎨 Browse LoRAs", "browse_loras")],
                    [Button.inline("🎯 ControlNet Preview", "controlnet_preview")],
                    [Button.inline("ℹ️ Help", "help")]
                ]
            )
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await self.show_help_message(event)
        
        @self.client.on(events.NewMessage(pattern='/skip'))
        async def skip_handler(event):
            await self.handle_skip(event)
        
        @self.client.on(events.NewMessage(pattern='/cancel'))
        async def cancel_handler(event):
            await self.cancel_operation_message(event)
        
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
                elif data == "browse_loras":
                    await self.show_lora_categories(event)
                elif data.startswith("lora_cat_"):
                    category = data.replace("lora_cat_", "")
                    await self.show_loras_in_category(event, category)
                elif data.startswith("lora_info_"):
                    lora_name = data.replace("lora_info_", "")
                    await self.show_lora_info(event, lora_name)
                elif data.startswith("add_lora_"):
                    lora_name = data.replace("add_lora_", "")
                    await self.add_lora_to_generation(event, lora_name)
                elif data == "show_selected_loras":
                    await self.show_selected_loras(event)
                elif data.startswith("remove_lora_"):
                    index = int(data.replace("remove_lora_", ""))
                    await self.remove_lora_from_generation(event, index)
                elif data == "controlnet_preview":
                    await self.start_controlnet_preview(event)
                elif data.startswith("cn_type_"):
                    cn_type = data.replace("cn_type_", "")
                    await self.select_controlnet_type(event, cn_type)
                elif data == "add_controlnet":
                    await self.start_add_controlnet(event)
                elif data.startswith("add_cn_"):
                    cn_type = data.replace("add_cn_", "")
                    await self.add_controlnet_to_generation(event, cn_type)
                elif data == "skip_controlnet":
                    await self.skip_controlnet(event)
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
                elif state == "controlnet_preview_image":
                    if event.media:
                        await self.handle_controlnet_preview_image(event)
                    else:
                        await event.respond("📷 Please send an image!")
                elif state == "controlnet_image":
                    if event.media:
                        await self.handle_controlnet_image(event)
                    else:
                        await event.respond("📷 Please send an image!")
            except Exception as e:
                logger.error(f"Message handler error: {e}", exc_info=True)
                await event.respond("❌ An error occurred. Please try /start")
    
    async def show_main_menu(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'main_menu'
        
        await event.edit(
            f"🎬 **{BOT_USERNAME} Main Menu**\n\n"
            "🚀 **Available Features:**\n"
            "• 50+ LoRAs for style enhancement\n"
            "• 4 ControlNet types\n"
            "• Multiple generation modes\n\n"
            "Choose what you want to create:",
            buttons=[
                [Button.inline("📝 Text to Video", "t2v")],
                [Button.inline("🖼️ Image to Video", "i2v")],
                [Button.inline("🎭 Animate Character", "animate")],
                [Button.inline("🎨 Browse LoRAs", "browse_loras")],
                [Button.inline("🎯 ControlNet Preview", "controlnet_preview")],
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
            'use_fast_mode': True,
            'loras': [],
            'controlnet_image': None,
            'controlnet_type': None,
            'controlnet_scale': 1.0
        }
        
        await event.edit(
            "📝 **Text to Video**\n\n"
            "Send me a descriptive prompt for your video.\n\n"
            "💡 **Example:**\n"
            "`A beautiful sunset over the ocean with waves gently crashing on the shore`\n\n"
            "🎨 You can add LoRAs after this step!",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_t2v_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 10:
            await event.respond("⚠️ Prompt too short! Please provide more detail (min 10 characters).")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 't2v_options'
        
        await event.respond(
            "✅ **Prompt received!**\n\n"
            "🎨 **Optional Enhancements:**\n"
            "• Add LoRAs for style\n"
            "• Add ControlNet for control\n"
            "• Add negative prompt\n\n"
            "Or generate directly!",
            buttons=[
                [Button.inline("🎨 Add LoRAs", "browse_loras")],
                [Button.inline("🎯 Add ControlNet", "add_controlnet")],
                [Button.inline("🚫 Negative Prompt", "add_negative_t2v")],
                [Button.inline("🎬 Generate Now", "generate")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_t2v_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        self.user_states[user_id] = 't2v_options'
        await event.respond(
            "✅ Negative prompt saved!",
            buttons=[[Button.inline("🎬 Generate Now", "generate")]]
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
            'use_fast_mode': True,
            'loras': [],
            'controlnet_image': None,
            'controlnet_type': None,
            'controlnet_scale': 1.0
        }
        
        await event.edit(
            "🖼️ **Image to Video**\n\n"
            "Please send me an image to animate.\n\n"
            "📋 **Requirements:**\n"
            "• Format: JPG, PNG, WebP\n"
            "• Max size: 20MB\n"
            "• Clear, well-lit images work best",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_i2v_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image (JPG, PNG, WebP)!")
                return
            
            if len(photo) > MAX_FILE_SIZE:
                await event.respond("⚠️ Image too large! Maximum 20MB allowed.")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['image_base64'] = image_b64
            self.user_states[user_id] = 'i2v_prompt'
            
            await event.respond(
                "✅ **Image received!**\n\n"
                "Now send a prompt describing how to animate it.\n\n"
                "💡 **Example:**\n"
                "`Camera slowly zooming in, dramatic lighting`"
            )
        except Exception as e:
            logger.error(f"Image processing error: {e}", exc_info=True)
            await event.respond("❌ Error processing image. Please try again.")
    
    async def handle_i2v_prompt(self, event):
        user_id = event.sender_id
        prompt = event.text.strip()
        
        if len(prompt) < 5:
            await event.respond("⚠️ Prompt too short! Minimum 5 characters.")
            return
        
        self.user_data[user_id]['prompt'] = prompt
        self.user_states[user_id] = 'i2v_options'
        
        await event.respond(
            "✅ **Prompt received!**\n\n"
            "🎨 **Optional Enhancements:**",
            buttons=[
                [Button.inline("🎨 Add LoRAs", "browse_loras")],
                [Button.inline("🎯 Add ControlNet", "add_controlnet")],
                [Button.inline("🚫 Negative Prompt", "add_negative_i2v")],
                [Button.inline("🎬 Generate Now", "generate")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_i2v_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        self.user_states[user_id] = 'i2v_options'
        await event.respond(
            "✅ Negative prompt saved!",
            buttons=[[Button.inline("🎬 Generate Now", "generate")]]
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
            'use_fast_mode': True,
            'loras': []
        }
        
        await event.edit(
            "🎭 **Animate Character**\n\n"
            "This feature transfers motion from a video to your character.\n\n"
            "**Step 1/3:** Send a reference image of your character\n\n"
            "📋 **Requirements:**\n"
            "• Format: JPG, PNG, WebP\n"
            "• Max size: 20MB",
            buttons=[
                [Button.inline("🔙 Back", "main_menu")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
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
                "✅ **Reference image received!**\n\n"
                "**Step 2/3:** Send a video with the motion to transfer\n\n"
                "📋 **Requirements:**\n"
                "• Format: MP4, WebM\n"
                "• Max size: 20MB\n"
                "• Clear motion works best"
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
                "✅ **Video received!**\n\n"
                "**Step 3/3:** Send a prompt describing the animation\n\n"
                "💡 **Example:**\n"
                "`Character dancing happily with energetic movements`"
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
        self.user_states[user_id] = 'animate_options'
        
        await event.respond(
            "✅ **All data received!**\n\n"
            "🎨 **Optional:**",
            buttons=[
                [Button.inline("🎨 Add LoRAs", "browse_loras")],
                [Button.inline("🚫 Negative Prompt", "add_negative_animate")],
                [Button.inline("🎬 Generate Now", "generate")],
                [Button.inline("❌ Cancel", "cancel")]
            ]
        )
    
    async def handle_animate_negative(self, event):
        user_id = event.sender_id
        self.user_data[user_id]['negative_prompt'] = event.text.strip()
        self.user_states[user_id] = 'animate_options'
        await event.respond(
            "✅ Negative prompt saved!",
            buttons=[[Button.inline("🎬 Generate Now", "generate")]]
        )
    
    async def show_lora_categories(self, event):
        buttons = []
        for cat_key, cat_name in LORA_CATEGORIES.items():
            buttons.append([Button.inline(cat_name, f"lora_cat_{cat_key}")])
        
        buttons.append([Button.inline("📋 Show Selected", "show_selected_loras")])
        buttons.append([Button.inline("🔙 Back", "main_menu")])
        
        await event.edit(
            "🎨 **Browse LoRAs**\n\n"
            "Select a category to explore:\n\n"
            f"📦 **Total:** 50 LoRAs across 5 categories",
            buttons=buttons
        )
    
    async def show_loras_in_category(self, event, category):
        user_id = event.sender_id
        
        if category not in self.lora_registry:
            await event.answer("⏳ Loading LoRAs...", alert=True)
            await self.load_available_loras()
        
        loras = self.lora_registry.get(category, [])
        
        if not loras:
            await event.answer("❌ No LoRAs found in this category", alert=True)
            return
        
        buttons = []
        for lora_name in loras[:10]:
            emoji = "✅" if any(l['name'] == lora_name for l in self.user_data.get(user_id, {}).get('loras', [])) else "➕"
            buttons.append([Button.inline(f"{emoji} {lora_name}", f"add_lora_{lora_name}")])
        
        buttons.append([Button.inline("🔙 Categories", "browse_loras")])
        
        cat_display = LORA_CATEGORIES.get(category, category)
        await event.edit(
            f"🎨 **{cat_display}**\n\n"
            f"Found {len(loras)} LoRAs\n"
            "Tap to add/remove:",
            buttons=buttons
        )
    
    async def add_lora_to_generation(self, event, lora_name):
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ Start a generation first!", alert=True)
            return
        
        loras = self.user_data[user_id].get('loras', [])
        
        existing = next((i for i, l in enumerate(loras) if l['name'] == lora_name), None)
        if existing is not None:
            loras.pop(existing)
            await event.answer(f"➖ Removed: {lora_name}", alert=False)
        else:
            if len(loras) >= 5:
                await event.answer("⚠️ Maximum 5 LoRAs allowed!", alert=True)
                return
            loras.append({"name": lora_name, "strength": 1.0})
            await event.answer(f"✅ Added: {lora_name}", alert=False)
        
        self.user_data[user_id]['loras'] = loras
    
    async def show_selected_loras(self, event):
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ Start a generation first!", alert=True)
            return
        
        loras = self.user_data[user_id].get('loras', [])
        
        if not loras:
            await event.answer("No LoRAs selected yet", alert=True)
            return
        
        text = "✅ **Selected LoRAs:**\n\n"
        for i, lora in enumerate(loras, 1):
            text += f"{i}. {lora['name']} (strength: {lora['strength']})\n"
        
        buttons = []
        for i in range(len(loras)):
            buttons.append([Button.inline(f"➖ Remove #{i+1}", f"remove_lora_{i}")])
        
        buttons.append([Button.inline("🔙 Back", "browse_loras")])
        
        await event.edit(text, buttons=buttons)
    
    async def remove_lora_from_generation(self, event, index):
        user_id = event.sender_id
        loras = self.user_data[user_id].get('loras', [])
        
        if 0 <= index < len(loras):
            removed = loras.pop(index)
            await event.answer(f"➖ Removed: {removed['name']}", alert=False)
            self.user_data[user_id]['loras'] = loras
            await self.show_selected_loras(event)
        else:
            await event.answer("❌ Invalid index", alert=True)
    
    async def start_controlnet_preview(self, event):
        user_id = event.sender_id
        self.user_states[user_id] = 'controlnet_preview_select'
        
        buttons = []
        for cn_key, cn_name in CONTROLNET_TYPES.items():
            buttons.append([Button.inline(cn_name, f"cn_type_{cn_key}")])
        
        buttons.append([Button.inline("🔙 Back", "main_menu")])
        
        await event.edit(
            "🎯 **ControlNet Preview**\n\n"
            "Select a ControlNet type to preview processing:\n\n"
            "This will show you how your image will be processed.",
            buttons=buttons
        )
    
    async def select_controlnet_type(self, event, cn_type):
        user_id = event.sender_id
        self.user_states[user_id] = 'controlnet_preview_image'
        self.user_data[user_id] = {'preview_cn_type': cn_type}
        
        await event.edit(
            f"🎯 **ControlNet: {CONTROLNET_TYPES[cn_type]}**\n\n"
            "Send an image to see the processed result:",
            buttons=[[Button.inline("🔙 Back", "controlnet_preview")]]
        )
    
    async def handle_controlnet_preview_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image!")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            cn_type = self.user_data[user_id].get('preview_cn_type')
            
            processing_msg = await event.respond("⏳ Processing with ControlNet...")
            
            response = requests.post(
                f"{MODAL_API_URL}/api/controlnet/preview",
                json={
                    'image_base64': image_b64,
                    'controlnet_type': cn_type
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                processed_b64 = result.get('processed_image_base64')
                
                if processed_b64:
                    processed_bytes = base64.b64decode(processed_b64)
                    processed_file = io.BytesIO(processed_bytes)
                    processed_file.name = f"controlnet_{cn_type}.png"
                    
                    await self.client.send_file(
                        event.chat_id,
                        processed_file,
                        caption=f"✅ **ControlNet Preview**\n\nType: {CONTROLNET_TYPES[cn_type]}"
                    )
                    await processing_msg.delete()
                else:
                    await processing_msg.edit("❌ No processed image in response")
            else:
                await processing_msg.edit(f"❌ Error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"ControlNet preview error: {e}", exc_info=True)
            await event.respond("❌ Error processing image")
    
    async def start_add_controlnet(self, event):
        user_id = event.sender_id
        
        buttons = []
        for cn_key, cn_name in CONTROLNET_TYPES.items():
            buttons.append([Button.inline(cn_name, f"add_cn_{cn_key}")])
        
        buttons.append([Button.inline("⏭️ Skip ControlNet", "skip_controlnet")])
        buttons.append([Button.inline("🔙 Back", "main_menu")])
        
        await event.edit(
            "🎯 **Add ControlNet**\n\n"
            "Select a ControlNet type for better control:",
            buttons=buttons
        )
    
    async def add_controlnet_to_generation(self, event, cn_type):
        user_id = event.sender_id
        self.user_states[user_id] = 'controlnet_image'
        self.user_data[user_id]['controlnet_type'] = cn_type
        
        await event.edit(
            f"🎯 **ControlNet: {CONTROLNET_TYPES[cn_type]}**\n\n"
            "Send an image for ControlNet guidance:",
            buttons=[[Button.inline("❌ Cancel", "cancel")]]
        )
    
    async def handle_controlnet_image(self, event):
        user_id = event.sender_id
        
        try:
            if event.photo:
                photo = await event.download_media(file=bytes)
            elif event.document and event.document.mime_type in SUPPORTED_IMAGE_TYPES:
                photo = await event.download_media(file=bytes)
            else:
                await event.respond("⚠️ Please send a valid image!")
                return
            
            image_b64 = base64.b64encode(photo).decode('utf-8')
            self.user_data[user_id]['controlnet_image'] = image_b64
            
            gen_type = self.user_data[user_id].get('type')
            self.user_states[user_id] = f'{gen_type}_options'
            
            await event.respond(
                "✅ **ControlNet image saved!**\n\n"
                "Ready to generate!",
                buttons=[[Button.inline("🎬 Generate Now", "generate")]]
            )
        except Exception as e:
            logger.error(f"ControlNet image error: {e}", exc_info=True)
            await event.respond("❌ Error processing image")
    
    async def skip_controlnet(self, event):
        user_id = event.sender_id
        gen_type = self.user_data[user_id].get('type')
        self.user_states[user_id] = f'{gen_type}_options'
        
        await event.edit(
            "⏭️ **ControlNet skipped**\n\n"
            "Ready to generate!",
            buttons=[[Button.inline("🎬 Generate Now", "generate")]]
        )
    
    async def handle_skip(self, event):
        user_id = event.sender_id
        if user_id in self.user_states:
            state = self.user_states[user_id]
            if 'negative' in state:
                self.user_data[user_id]['negative_prompt'] = ''
                gen_type = self.user_data[user_id].get('type')
                self.user_states[user_id] = f'{gen_type}_options'
                await event.respond(
                    "✅ Negative prompt skipped!",
                    buttons=[[Button.inline("🎬 Generate Now", "generate")]]
                )
    
    async def generate_video(self, event):
        user_id = event.sender_id
        
        if user_id not in self.user_data:
            await event.answer("❌ No data found. Please start over with /start", alert=True)
            return
        
        data = self.user_data[user_id]
        gen_type = data.get('type')
        
        loras_count = len(data.get('loras', []))
        has_controlnet = data.get('controlnet_image') is not None
        
        status_text = (
            f"⏳ **Generating {gen_type.upper()} Video...**\n\n"
            f"📊 **Configuration:**\n"
            f"• Frames: {data.get('num_frames', 0)}\n"
            f"• Steps: {data.get('steps', 0)}\n"
            f"• LoRAs: {loras_count}\n"
            f"• ControlNet: {'Yes' if has_controlnet else 'No'}\n\n"
            f"⏱️ **Estimated time:** 2-5 minutes\n"
            f"Please wait..."
        )
        
        processing_msg = await self.client.send_message(event.chat_id, status_text)
        
        try:
            if gen_type == 't2v':
                endpoint = f"{MODAL_API_URL}/api/generate/t2v"
                payload = {
                    'prompt': data['prompt'],
                    'negative_prompt': data.get('negative_prompt', ''),
                    'width': data['width'],
                    'height': data['height'],
                    'num_frames': data['num_frames'],
                    'steps': data['steps'],
                    'cfg': data['cfg'],
                    'use_fast_mode': data.get('use_fast_mode', True),
                    'loras': data.get('loras', []),
                    'controlnet_image': data.get('controlnet_image'),
                    'controlnet_type': data.get('controlnet_type'),
                    'controlnet_scale': data.get('controlnet_scale', 1.0)
                }
            elif gen_type == 'i2v':
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
                    'use_fast_mode': data.get('use_fast_mode', True),
                    'loras': data.get('loras', []),
                    'controlnet_image': data.get('controlnet_image'),
                    'controlnet_type': data.get('controlnet_type'),
                    'controlnet_scale': data.get('controlnet_scale', 1.0)
                }
            elif gen_type == 'animate':
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
                    'use_fast_mode': data.get('use_fast_mode', True),
                    'loras': data.get('loras', [])
                }
            else:
                await processing_msg.edit("❌ Invalid generation type")
                return
            
            logger.info(f"Sending request to {endpoint}")
            logger.info(f"Payload: {gen_type} with {loras_count} LoRAs")
            
            response = requests.post(endpoint, json=payload, timeout=600)
            
            if response.status_code == 200:
                result = response.json()
                video_b64 = result.get('video_base64')
                metadata = result.get('metadata', {})
                
                if video_b64:
                    video_bytes = base64.b64decode(video_b64)
                    video_file = io.BytesIO(video_bytes)
                    video_file.name = f"wanvideo_{gen_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                    
                    caption = (
                        f"✅ **Video Generated Successfully!**\n\n"
                        f"📊 **Details:**\n"
                        f"• Type: {gen_type.upper()}\n"
                        f"• Resolution: {metadata.get('width', 0)}x{metadata.get('height', 0)}\n"
                        f"• Frames: {metadata.get('num_frames', 0)}\n"
                        f"• LoRAs: {metadata.get('loras_applied', 0)}\n\n"
                        f"🎬 Enjoy your video!"
                    )
                    
                    await self.client.send_file(
                        event.chat_id,
                        video_file,
                        caption=caption,
                        supports_streaming=True
                    )
                    
                    await processing_msg.delete()
                    
                    if user_id in self.user_data:
                        del self.user_data[user_id]
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    
                    await self.client.send_message(
                        event.chat_id,
                        "🎉 **Generation complete!**\n\nUse /start for a new video",
                        buttons=[[Button.inline("🔄 Generate Another", "main_menu")]]
                    )
                else:
                    await processing_msg.edit("❌ No video in response. Please try again.")
            else:
                error_text = response.text[:500]
                logger.error(f"API Error {response.status_code}: {error_text}")
                await processing_msg.edit(
                    f"❌ **Generation Failed**\n\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {error_text}\n\n"
                    f"Please try again with /start"
                )
        except requests.Timeout:
            await processing_msg.edit(
                "⏰ **Request Timeout**\n\n"
                "The generation took too long. This might be due to:\n"
                "• High server load\n"
                "• Complex generation settings\n\n"
                "Please try again with:\n"
                "• Fewer frames\n"
                "• Fewer LoRAs\n"
                "• Simpler prompt"
            )
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            await processing_msg.edit(
                f"❌ **Unexpected Error**\n\n"
                f"Error: {str(e)[:200]}\n\n"
                f"Please try again with /start"
            )
    
    async def cancel_operation(self, event):
        user_id = event.sender_id
        
        if user_id in self.user_data:
            del self.user_data[user_id]
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await event.edit(
            "❌ **Operation Cancelled**\n\n"
            "All data has been cleared.\n"
            "Use /start to begin again.",
            buttons=[[Button.inline("🔄 Start Over", "main_menu")]]
        )
    
    async def cancel_operation_message(self, event):
        user_id = event.sender_id
        
        if user_id in self.user_data:
            del self.user_data[user_id]
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await event.respond(
            "❌ **Operation Cancelled**\n\n"
            "Use /start to begin again.",
            buttons=[[Button.inline("🔄 Start Over", "main_menu")]]
        )
    
    async def show_help(self, event):
        await event.edit(
            "🤖 **WanVideo Bot Help**\n\n"
            "**🎬 Features:**\n"
            "• 📝 Text to Video - Generate from text\n"
            "• 🖼️ Image to Video - Animate images\n"
            "• 🎭 Animate Character - Motion transfer\n"
            "• 🎨 50+ LoRAs - Style enhancements\n"
            "• 🎯 4 ControlNets - Precise control\n\n"
            "**📋 How to Use:**\n"
            "1. Choose a generation mode\n"
            "2. Follow the step-by-step prompts\n"
            "3. (Optional) Add LoRAs for style\n"
            "4. (Optional) Add ControlNet for control\n"
            "5. Wait 2-5 minutes\n"
            "6. Download your video!\n\n"
            "**💡 Tips:**\n"
            "• Use detailed, descriptive prompts\n"
            "• Clear, well-lit images work best\n"
            "• Experiment with different LoRAs\n"
            "• ControlNet helps with composition\n"
            "• Keep videos under 20MB\n\n"
            "**🎨 LoRA Categories:**\n"
            "• Style: anime, realistic, cyberpunk...\n"
            "• Character: disney, ghibli, manga...\n"
            "• Lighting: neon, dramatic, golden hour...\n"
            "• Environment: urban, nature, space...\n"
            "• Effect: motion blur, film grain...\n\n"
            "**🎯 ControlNet Types:**\n"
            "• Canny: Edge detection\n"
            "• Depth: Depth map control\n"
            "• OpenPose: Pose guidance\n"
            "• Scribble: Sketch-based\n\n"
            "**⚙️ Commands:**\n"
            "/start - Main menu\n"
            "/help - Show this help\n"
            "/skip - Skip optional step\n"
            "/cancel - Cancel operation\n\n"
            "**📊 Limits:**\n"
            "• Max file size: 20MB\n"
            "• Max LoRAs: 5 per generation\n"
            "• Max frames: 240\n"
            "• Generation time: 2-5 minutes\n\n"
            "Need more help? Contact admin.",
            buttons=[[Button.inline("🔙 Back to Menu", "main_menu")]]
        )
    
    async def show_help_message(self, event):
        await event.respond(
            "🤖 **WanVideo Bot Help**\n\n"
            "**Features:**\n"
            "• Text to Video (with 50+ LoRAs)\n"
            "• Image to Video (with ControlNet)\n"
            "• Character Animation\n"
            "• ControlNet preview\n\n"
            "Use /start to begin generating videos!\n\n"
            "For detailed help, use the Help button in the main menu.",
            buttons=[[Button.inline("📖 Full Help", "help"), Button.inline("🚀 Start", "main_menu")]]
        )
    
    # Di dalam class WanVideoBot:
    def run(self):
    # TAMBAHKAN BLOK INI
        logger.info("Initializing bot and loading available LoRAs...")
        try:
            self.client.loop.run_until_complete(self.load_available_loras())
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to load LoRAs on startup. Bot cannot function properly. Error: {e}")
            return # Hentikan bot jika LoRA gagal dimuat

        logger.info(f"Bot started! Username: {BOT_USERNAME}")
        logger.info(f"API URL: {MODAL_API_URL}")
        logger.info("Features: 50 LoRAs, 4 ControlNets, 3 Generation Modes")
        self.client.run_until_disconnected()

if __name__ == '__main__':
    bot = WanVideoBot()
    bot.run()
