import asyncio
import base64
from collections import deque
import difflib
import json
import os
import re
import time
import uuid
import webbrowser
import cv2
import numpy as np
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit

import websockets
from pywhispercpp.model import Model as WhisperModel

import phone_camera_companion as phone_companion


HOST = "127.0.0.1"
PORT = 8765
HTTP_PORT = 8000
SAMPLE_RATE = 16000
WHISPER_MODEL_NAME = "tiny"
WHISPER_MODEL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "pywhispercpp" / "pywhispercpp" / "models"
FACE_CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
MAX_FACE_FRAME_BYTES = 48_000
SPEECH_RMS_THRESHOLD = 350
SPEECH_END_SILENCE_SECONDS = 0.85
MAX_SPEECH_SECONDS = 25


COMMANDS = [
    ("time", "what time is it", "time"),
    ("date", "what is today's date", "date"),
    ("weekday", "what day is it today", "weekday"),
    ("year", "what year is it", "year"),
    ("day-of-year", "what number day of the year is it", "day-of-year"),
    ("math-2-plus-2", "what is two plus two", "Two plus two is four."),
    ("math-10-minus-3", "what is ten minus three", "Ten minus three is seven."),
    ("math-6-times-7", "what is six times seven", "Six times seven is forty-two."),
    ("math-20-divided-by-4", "what is twenty divided by four", "Twenty divided by four is five."),
    ("math-square-9", "what is nine squared", "Nine squared is eighty-one."),
    ("math-half-50", "what is half of fifty", "Half of fifty is twenty-five."),
    ("math-100-plus-25", "what is one hundred plus twenty-five", "One hundred plus twenty-five is one hundred twenty-five."),
    ("math-12-times-12", "what is twelve times twelve", "Twelve times twelve is one hundred forty-four."),
    ("math-100-minus-45", "what is one hundred minus forty-five", "One hundred minus forty-five is fifty-five."),
    ("math-square-root-81", "what is the square root of eighty-one", "The square root of eighty-one is nine."),
    ("identity", "who are you", "I am Jarvis, your offline voice assistant."),
    ("name", "what is your name", "My name is Jarvis."),
    ("creator", "who made you", "I was created as your personal character assistant."),
    ("capabilities", "what can you do", "I can answer these one hundred offline questions, tell the time and date, and keep you company."),
    ("help", "show me the commands", "Open the one hundred commands list in the camera panel to see what you can ask."),
    ("listening", "are you listening", "Yes, Javeed. I am listening while offline voice mode is on."),
    ("hello", "say hello", "Hello, Javeed. It is nice to see you."),
    ("good-morning", "say good morning", "Good morning, Javeed. I hope your day starts well."),
    ("good-afternoon", "say good afternoon", "Good afternoon, Javeed. I hope your day is going smoothly."),
    ("good-evening", "say good evening", "Good evening, Javeed. I hope you have had a good day."),
    ("thanks", "say you are welcome", "You are welcome, Javeed."),
    ("how-are-you", "how are you", "I am doing well and ready to help, Javeed."),
    ("introduce", "introduce yourself", "Hello, I am Jarvis. I listen for your questions and answer using the offline command list."),
    ("my-name", "what is my name", "Your name is Javeed."),
    ("wake-up", "wake up", "I am awake and listening, Javeed."),
    ("sleep", "go to sleep", "Okay, I will wait for you to say Jarvis again."),
    ("explain-ai", "what is artificial intelligence", "Artificial intelligence is software designed to perform tasks that usually need human reasoning, such as recognizing speech or finding patterns."),
    ("explain-computer", "what is a computer", "A computer is an electronic machine that processes information according to instructions."),
    ("explain-internet", "what is the internet", "The internet is a worldwide network that lets connected devices exchange information."),
    ("explain-browser", "what is a web browser", "A web browser is an app used to open and view websites."),
    ("explain-html", "what is html", "HTML is the markup language used to structure content on web pages."),
    ("explain-css", "what is css", "CSS is the language used to style and lay out web pages."),
    ("explain-javascript", "what is javascript", "JavaScript is a programming language commonly used to make web pages interactive."),
    ("explain-python", "what is python", "Python is a popular programming language known for clear and readable syntax."),
    ("explain-algorithm", "what is an algorithm", "An algorithm is a clear sequence of steps for solving a problem."),
    ("explain-data", "what is data", "Data is information that can be stored, processed, and used."),
    ("explain-password", "what makes a strong password", "A strong password is long, unique, and hard to guess. Use a password manager rather than reusing passwords."),
    ("explain-cloud", "what is cloud computing", "Cloud computing means using computing services over a network instead of relying only on your own device."),
    ("explain-robot", "what is a robot", "A robot is a machine that can carry out actions automatically, often using sensors and programmed instructions."),
    ("explain-moon", "what is the moon", "The Moon is Earth's natural satellite and the brightest object in our night sky."),
    ("explain-earth", "what planet do we live on", "We live on Earth, the third planet from the Sun."),
    ("explain-water", "what is water made of", "A water molecule contains two hydrogen atoms and one oxygen atom."),
    ("explain-gravity", "what is gravity", "Gravity is the attraction between objects that have mass."),
    ("explain-light", "does light travel faster than sound", "Yes. Light travels much faster than sound, which is why lightning is seen before thunder is heard."),
    ("explain-rainbow", "how does a rainbow form", "A rainbow forms when sunlight is refracted, reflected, and spread into colors by water droplets."),
    ("explain-plant", "what do plants need to grow", "Most plants need light, water, air, nutrients, and suitable temperatures to grow."),
    ("explain-photosynthesis", "what is photosynthesis", "Photosynthesis is how plants use light energy to turn water and carbon dioxide into sugars and oxygen."),
    ("explain-heart", "what does the heart do", "The heart pumps blood around the body."),
    ("explain-brain", "what does the brain do", "The brain processes information and helps control thought, movement, senses, and many body functions."),
    ("explain-sleep", "why is sleep important", "Sleep helps the body and brain recover and supports memory, mood, and concentration."),
    ("explain-exercise", "why is exercise helpful", "Regular movement supports general fitness, strength, and well-being. Choose activity that is suitable for you."),
    ("explain-science", "what is science", "Science is a way of learning about the world through observation, evidence, and testing ideas."),
    ("explain-math", "what is mathematics", "Mathematics studies patterns, quantities, shapes, and the relationships between them."),
    ("explain-energy", "what is energy", "Energy is the capacity to cause change or do work."),
    ("explain-electricity", "what is electricity", "Electricity involves the presence or movement of electric charge."),
    ("explain-recycling", "why is recycling useful", "Recycling can turn used materials into new products and reduce the amount sent to landfill."),
    ("explain-weather", "what is weather", "Weather describes short-term conditions in the atmosphere, such as temperature, wind, and rain."),
    ("explain-climate", "what is climate", "Climate describes the typical weather patterns of a place over a long period."),
    ("explain-language", "what is a language", "A language is a shared system of words and rules people use to communicate."),
    ("explain-practice", "why should i practice", "Practice helps you build skill through repetition, feedback, and patience."),
    ("advice-start", "give me a study tip", "Try studying in short focused sessions, take brief breaks, and review what you learned."),
    ("advice-focus", "help me focus", "Choose one small task, silence distractions, and work on it for ten minutes before deciding what is next."),
    ("advice-stress", "give me a calming tip", "Pause for a moment, relax your shoulders, and take a few slow comfortable breaths."),
    ("advice-goal", "help me set a goal", "Make your goal specific and realistic, then choose one small action you can take today."),
    ("advice-motivation", "motivate me", "You do not have to finish everything at once. Start with one small step, Javeed."),
    ("advice-kindness", "tell me something kind", "You deserve patience while you learn and grow, Javeed."),
    ("advice-break", "remind me to take a break", "This is your reminder to stand up, rest your eyes, and take a short break."),
    ("advice-water", "remind me to drink water", "Here is your reminder to have some water if you are thirsty."),
    ("advice-organize", "how can i organize my day", "Write down your main tasks, choose the most important one, and give it a realistic time slot."),
    ("advice-mistake", "what should i do after a mistake", "Notice what happened, learn what you can, and choose one helpful next step."),
    ("advice-new-skill", "how do i learn a new skill", "Break it into small parts, practice regularly, and use feedback to improve."),
    ("advice-memory", "how can i remember something", "Try explaining it in your own words and reviewing it again after a short interval."),
    ("advice-confidence", "give me a confidence tip", "Prepare what you can, take one manageable step, and remember that confidence grows with practice."),
    ("advice-patience", "why is patience important", "Patience gives you time to understand a challenge and respond thoughtfully."),
    ("advice-creativity", "give me a creative idea", "Pick an ordinary object nearby and invent three new uses for it."),
    ("joke-pencil", "tell me a joke", "Why was the pencil so confident? It had a good point."),
    ("joke-computer", "tell me a computer joke", "Why did the computer go to the doctor? It caught a virus."),
    ("joke-calendar", "tell me a calendar joke", "Why was the calendar popular? It had a lot of dates."),
    ("joke-book", "tell me a book joke", "Why did the book visit the doctor? It needed a new cover."),
    ("joke-clock", "tell me a clock joke", "What did the clock do when it was hungry? It went back four seconds."),
    ("joke-math", "tell me a maths joke", "Why was the equal sign so humble? It knew it was not less than or greater than anyone."),
    ("joke-science", "tell me a science joke", "I told a chemistry joke, but there was no reaction."),
    ("joke-space", "tell me a space joke", "How do astronauts organize a party? They planet."),
    ("joke-music", "tell me a music joke", "Why did the music teacher need a ladder? To reach the high notes."),
    ("joke-short", "make me laugh", "I tried to write a joke about paper, but it was tearable."),
    ("compliment", "give me a compliment", "You are curious and thoughtful for exploring what I can do."),
    ("fun-fact", "tell me a fun fact", "Octopuses have three hearts."),
    ("favorite-color", "what is your favorite color", "I like cyan. It matches the glow around me."),
    ("favorite-food", "what is your favorite food", "I do not eat, but I can help you choose something you enjoy."),
    ("favorite-book", "what is your favorite book", "I do not have personal favorites, but there are wonderful books for every interest."),
    ("favorite-music", "what music do you like", "I cannot listen for pleasure, but I can talk about many styles of music."),
    ("weather-limit", "what is the weather today", "I do not have an internet weather service in offline mode. Please check a local weather app."),
    ("news-limit", "what is the latest news", "I am offline, so I cannot fetch live news. Please check a trusted news source."),
    ("web-limit", "search the internet", "I cannot browse the internet in offline mode, but I can answer the questions in my command list."),
    ("goodbye", "say goodbye", "Goodbye for now, Javeed. Say Jarvis whenever you want to talk again."),
]

COMMANDS_BY_ID = {command_id: (question, response) for command_id, question, response in COMMANDS}
PHRASE_TO_ID = {question: command_id for command_id, question, _ in COMMANDS}
URDU_RESPONSES = {
    "hello": ("السلام علیکم جاوید، آپ سے بات کر کے خوشی ہوئی۔", "ur-PK"),
    "how-are-you": ("میں ٹھیک ہوں اور آپ کی مدد کے لیے تیار ہوں۔", "ur-PK"),
    "thanks": ("آپ کا خیر مقدم ہے، جاوید۔", "ur-PK"),
    "identity": ("میں جارویس ہوں، آپ کا مقامی وائس اسسٹنٹ۔", "ur-PK"),
    "goodbye": ("اللہ حافظ جاوید۔ جب بات کرنی ہو تو جارویس کہیں۔", "ur-PK"),
}

whisper_model: WhisperModel | None = None
whisper_model_lock = Lock()
transcription_lock = Lock()
voice_clients: set = set()
whatsapp_clients: set = set()
pending_whatsapp: dict[str, dict] = {}


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", text.casefold(), flags=re.UNICODE)).strip()


def identify_command(text: str) -> str | None:
    normalized = normalize(text)
    if normalized.startswith("jarvise "):
        normalized = normalized[len("jarvise "):]
    elif normalized.startswith("jarvis "):
        normalized = normalized[len("jarvis "):]

    if normalized in PHRASE_TO_ID:
        return PHRASE_TO_ID[normalized]

    matches = difflib.get_close_matches(normalized, PHRASE_TO_ID, n=1, cutoff=0.78)
    return PHRASE_TO_ID[matches[0]] if matches else None


def response_for(command_id: str) -> str:
    _, response = COMMANDS_BY_ID[command_id]
    now = datetime.now()
    dynamic_responses = {
        "time": f"It is {now.strftime('%I:%M %p').lstrip('0')}.",
        "date": f"Today is {now.strftime('%B')} {now.day}, {now.year}.",
        "weekday": f"Today is {now.strftime('%A')}.",
        "year": f"It is {now.year}.",
        "day-of-year": f"Today is day {now.timetuple().tm_yday} of the year.",
    }
    return dynamic_responses.get(command_id, response)


def load_whisper_model() -> WhisperModel:
    global whisper_model
    with whisper_model_lock:
        if whisper_model is None:
            print(f"Loading the one-time offline multilingual speech model: {WHISPER_MODEL_NAME}")
            WHISPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            whisper_model = WhisperModel(
                WHISPER_MODEL_NAME,
                models_dir=str(WHISPER_MODEL_DIR),
                n_threads=2,
                print_progress=False,
                print_realtime=False,
                redirect_whispercpp_logs_to=None,
                context_params={"use_gpu": False, "flash_attn": False},
            )
            print("Offline multilingual speech model is ready.")
    return whisper_model


def transcribe_audio(audio_data: bytes, language: str) -> str:
    samples = np.frombuffer(audio_data, dtype="<i2").astype(np.float32) / 32768.0
    if len(samples) < SAMPLE_RATE // 4:
        return ""
    model = load_whisper_model()
    with transcription_lock:
        segments = model.transcribe(
            samples,
            language=language,
            n_threads=2,
            print_progress=False,
            print_realtime=False,
            no_context=True,
        )
    return " ".join(segment.text.strip() for segment in segments).strip()


def strip_wake_word(transcript: str) -> tuple[str, bool]:
    text = transcript.strip()
    normalized = normalize(text)
    wake_words = ("jarvis", "jarvise", "جارویس", "جاویس", "جاروِس")
    for wake_word in wake_words:
        if normalized == wake_word:
            return "", True
        if normalized.startswith(f"{wake_word} "):
            return text[len(wake_word):].lstrip(" ،,:،-"), True
    return text, False


def parse_whatsapp_request(transcript: str) -> tuple[str, str] | None:
    text, _ = strip_wake_word(transcript)
    patterns = (
        r"(?:send|write|message)\s+(?:a\s+)?(?:message\s+)?to\s+(.+?)\s+(?:saying|that\s+says)\s+(.+)",
        r"message\s+to\s+(.+?)\s+(?:saying|that\s+says)\s+(.+)",
        r"(.+?)\s+کو\s+(?:پیغام|میسج)\s*(?:بھیجو|بھیجیں|کر\s*دو|کرو)?\s*(?:[:،-]\s*|\s+)(.+)",
        r"(?:پیغام|میسج)\s+(.+?)\s+کو\s*(?:بھیجو|بھیجیں|کر\s*دو|کرو)?\s*(?:[:،-]\s*|\s+)(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            recipient, body = (part.strip(" ،,:،-") for part in match.groups())
            if recipient and body:
                return recipient, body
    return None


def confirmation_intent(transcript: str) -> str | None:
    normalized = normalize(transcript)
    affirmative = (
        "yes", "yes send", "yes send it", "confirm", "haan", "han", "ji haan",
        "ہاں", "جی ہاں", "ہاں بھیج دو", "جی بھیج دیں",
    )
    negative = ("no", "no cancel", "cancel", "nahin", "nahi", "نہیں", "نہ بھیجو", "منسوخ")
    if any(normalized == phrase or normalized.startswith(f"{phrase} ") for phrase in affirmative):
        return "yes"
    if any(normalized == phrase or normalized.startswith(f"{phrase} ") for phrase in negative):
        return "no"
    return None


def message_for_transcript(transcript: str, language: str) -> dict[str, str] | None:
    text, wake = strip_wake_word(transcript)
    normalized = normalize(text)
    if not normalized and wake:
        return {"type": "wake"}
    if not normalized:
        return None

    if re.search(
        r"\b(open|launch)\s+(?:my\s+)?(?:whats?app|whatsapp)\b"
        r"|(?:واٹس ?ایپ|واٹس ایپ)\s+کھول(?:و|یں| دو)"
        r"|whats?app\s+khol(?:o|do)",
        text,
        re.IGNORECASE,
    ):
        return {"type": "open_whatsapp", "wake": str(wake).lower()}

    message = parse_whatsapp_request(transcript)
    if message:
        return {
            "type": "whatsapp_request",
            "contact": message[0],
            "text": message[1],
            "wake": str(wake).lower(),
        }

    if language == "ur":
        urdu_phrases = {
            "وقت کیا ہوا ہے": "time",
            "آج کون سا دن ہے": "weekday",
            "آج کی تاریخ کیا ہے": "date",
            "آپ کیسے ہیں": "how-are-you",
            "شکریہ": "thanks",
            "سلام": "hello",
            "آپ کون ہیں": "identity",
            "خدا حافظ": "goodbye",
        }
        for phrase, command_id in urdu_phrases.items():
            if phrase in normalized:
                now = datetime.now()
                answers = {
                    "time": f"ابھی {now.strftime('%I:%M')} بجے ہیں۔",
                    "weekday": f"آج {now.strftime('%A')} ہے۔",
                    "date": f"آج {now.day} {now.strftime('%B')} {now.year} ہے۔",
                }
                answer, reply_language = URDU_RESPONSES.get(
                    command_id, (answers.get(command_id, response_for(command_id)), "ur-PK")
                )
                return {
                    "type": "command",
                    "id": command_id,
                    "answer": answer,
                    "replyLanguage": reply_language,
                    "wake": str(wake).lower(),
                }

    command_id = identify_command(text)
    if command_id:
        answer, reply_language = URDU_RESPONSES.get(command_id, (response_for(command_id), "en-US"))
        return {
            "type": "command",
            "id": command_id,
            "answer": answer,
            "replyLanguage": reply_language if language == "ur" else "en-US",
            "wake": str(wake).lower(),
        }
    if wake:
        return {"type": "wake"}
    return {"type": "unrecognized"}


async def send_to_voice_client(websocket, message: dict) -> None:
    if websocket in voice_clients:
        await websocket.send(json.dumps(message, ensure_ascii=False))


async def broadcast_to_whatsapp(message: dict) -> bool:
    delivered = False
    for client in tuple(whatsapp_clients):
        try:
            await client.send(json.dumps(message, ensure_ascii=False))
            delivered = True
        except websockets.exceptions.ConnectionClosed:
            whatsapp_clients.discard(client)
    return delivered


async def handle_whatsapp_result(message: dict) -> None:
    request_id = message.get("requestId")
    if not isinstance(request_id, str):
        return
    request = pending_whatsapp.get(request_id)
    if not request:
        return
    voice = request["voice"]
    if message.get("type") == "whatsapp_prepared":
        if message.get("ok"):
            request["stage"] = "awaiting_confirmation"
            await send_to_voice_client(voice, {
                "type": "whatsapp_confirmation",
                "requestId": request_id,
                "contact": request["contact"],
                "text": request["text"],
            })
        else:
            pending_whatsapp.pop(request_id, None)
            await send_to_voice_client(voice, {
                "type": "whatsapp_error",
                "message": message.get("message", "I could not find that exact WhatsApp contact."),
            })
    elif message.get("type") == "whatsapp_sent":
        pending_whatsapp.pop(request_id, None)
        await send_to_voice_client(voice, {
            "type": "whatsapp_sent",
            "contact": request["contact"],
            "message": message.get("message", ""),
        })
    elif message.get("type") == "whatsapp_error":
        pending_whatsapp.pop(request_id, None)
        await send_to_voice_client(voice, {
            "type": "whatsapp_error",
            "message": message.get("message", "WhatsApp could not complete that action."),
        })


class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path not in ("/", "/index.html"):
            self.send_error(404)
            return

        page_path = Path(__file__).resolve().parent / "Realistic CSS Human Head.html"
        try:
            page = phone_companion.substitute_phone_origin(page_path.read_bytes())
        except OSError as error:
            self.send_error(500, f"Could not read the character page: {error}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, format: str, *args: object) -> None:
        print(f"Web page: {format % args}")


async def handle_client(websocket) -> None:
    language: str | None = None
    audio_parts: list[bytes] = []
    pre_roll: deque[bytes] = deque(maxlen=4)
    speech_started = False
    silence_seconds = 0.0
    awake_until = 0.0
    try:
        await websocket.send(json.dumps({
            "type": "ready",
            "languages": ["en", "ur"],
            "commands": [{"id": command_id, "question": question} for command_id, question, _ in COMMANDS],
        }, ensure_ascii=False))

        async for audio_chunk in websocket:
            if not isinstance(audio_chunk, bytes):
                try:
                    request = json.loads(audio_chunk)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON request."}))
                    continue

                request_type = request.get("type")
                if request_type == "register_whatsapp":
                    whatsapp_clients.add(websocket)
                    await websocket.send(json.dumps({"type": "whatsapp_extension_ready"}))
                    continue
                if request_type in ("whatsapp_prepared", "whatsapp_sent", "whatsapp_error"):
                    if websocket in whatsapp_clients:
                        await handle_whatsapp_result(request)
                    continue
                if request_type == "open_whatsapp":
                    if not await broadcast_to_whatsapp({"type": "open_whatsapp"}):
                        await websocket.send(json.dumps({
                            "type": "whatsapp_error",
                            "message": "Install and enable the Jarvis WhatsApp extension, then try again.",
                        }))
                    else:
                        await websocket.send(json.dumps({"type": "whatsapp_opening"}))
                    continue
                if request_type == "confirm_whatsapp":
                    request_id = request.get("requestId")
                    pending = pending_whatsapp.get(request_id)
                    if pending and pending["voice"] is websocket and pending["stage"] == "awaiting_confirmation":
                        pending["stage"] = "sending"
                        delivered = await broadcast_to_whatsapp({
                            "type": "confirm_whatsapp",
                            "requestId": request_id,
                            "contact": pending["contact"],
                        })
                        if not delivered:
                            pending_whatsapp.pop(request_id, None)
                            await websocket.send(json.dumps({
                                "type": "whatsapp_error",
                                "message": "The WhatsApp extension disconnected; the message was not sent.",
                            }))
                    continue
                if request_type == "cancel_whatsapp":
                    request_id = request.get("requestId")
                    pending = pending_whatsapp.get(request_id)
                    if pending and pending["voice"] is websocket:
                        pending_whatsapp.pop(request_id, None)
                        await broadcast_to_whatsapp({"type": "cancel_whatsapp", "requestId": request_id})
                    continue
                if request_type == "configure":
                    selected_language = request.get("language")
                    if selected_language not in ("en", "ur"):
                        await websocket.send(json.dumps({"type": "error", "message": "Choose English or Urdu."}))
                        continue
                    await websocket.send(json.dumps({"type": "model_loading", "language": selected_language}))
                    try:
                        await asyncio.to_thread(load_whisper_model)
                    except Exception as error:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": f"Could not load the offline speech model: {error}",
                        }))
                        continue
                    language = selected_language
                    voice_clients.add(websocket)
                    audio_parts.clear()
                    pre_roll.clear()
                    speech_started = False
                    silence_seconds = 0.0
                    await websocket.send(json.dumps({"type": "language_ready", "language": language}))
                    continue
                if request_type == "open_whatsapp":
                    if await broadcast_to_whatsapp({"type": "open_whatsapp"}):
                        await websocket.send(json.dumps({"type": "whatsapp_opening"}))
                    else:
                        await websocket.send(json.dumps({
                            "type": "whatsapp_error",
                            "message": "Install and enable the Jarvis WhatsApp extension, then try again.",
                        }))
                    continue
                if request_type == "face_frame":
                    try:
                        frame_data = base64.b64decode(request.get("image", ""), validate=True)
                        if not frame_data or len(frame_data) > MAX_FACE_FRAME_BYTES:
                            raise ValueError("Camera frame is empty or too large.")
                        frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                        if frame is None:
                            raise ValueError("Camera frame is not a valid image.")
                        faces = face_detector.detectMultiScale(
                            cv2.equalizeHist(frame),
                            scaleFactor=1.1,
                            minNeighbors=5,
                            minSize=(35, 35),
                        )
                        if len(faces):
                            x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
                            result = {
                                "type": "face_presence",
                                "detected": True,
                                "x": (x + width / 2) / frame.shape[1],
                                "y": (y + height / 2) / frame.shape[0],
                            }
                        else:
                            result = {"type": "face_presence", "detected": False}
                        await websocket.send(json.dumps(result))
                    except (ValueError, cv2.error) as error:
                        await websocket.send(json.dumps({"type": "error", "message": f"Face detection failed: {error}"}))
                    continue
                await websocket.send(json.dumps({"type": "error", "message": "Unsupported request type."}))
                continue

            if language is None:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Select a recognition language before sending audio.",
                }))
                continue

            samples = np.frombuffer(audio_chunk, dtype="<i2").astype(np.float32)
            if not len(samples):
                continue
            duration = len(samples) / SAMPLE_RATE
            rms = float(np.sqrt(np.mean(np.square(samples))))
            if not speech_started:
                pre_roll.append(audio_chunk)
                if rms >= SPEECH_RMS_THRESHOLD:
                    audio_parts = list(pre_roll)
                    speech_started = True
                    silence_seconds = 0.0
                continue

            audio_parts.append(audio_chunk)
            silence_seconds = silence_seconds + duration if rms < SPEECH_RMS_THRESHOLD else 0.0
            buffered_seconds = sum(len(part) for part in audio_parts) / (SAMPLE_RATE * 2)
            if silence_seconds < SPEECH_END_SILENCE_SECONDS and buffered_seconds < MAX_SPEECH_SECONDS:
                continue

            captured_audio = b"".join(audio_parts)
            audio_parts.clear()
            pre_roll.clear()
            speech_started = False
            silence_seconds = 0.0
            try:
                transcript = await asyncio.to_thread(transcribe_audio, captured_audio, language)
            except Exception as error:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Offline speech recognition failed: {error}",
                }))
                continue
            if not transcript:
                continue

            message = message_for_transcript(transcript, language)
            if not message:
                continue
            pending = next(
                (request for request in pending_whatsapp.values() if request["voice"] is websocket),
                None,
            )
            if pending:
                if pending["stage"] == "awaiting_confirmation":
                    intent = confirmation_intent(transcript)
                    request_id = next(
                        request_id for request_id, request in pending_whatsapp.items() if request is pending
                    )
                    if intent == "yes":
                        pending["stage"] = "sending"
                        delivered = await broadcast_to_whatsapp({
                            "type": "confirm_whatsapp",
                            "requestId": request_id,
                            "contact": pending["contact"],
                        })
                        if delivered:
                            await websocket.send(json.dumps({"type": "whatsapp_sending"}))
                        else:
                            pending_whatsapp.pop(request_id, None)
                            await websocket.send(json.dumps({
                                "type": "whatsapp_error",
                                "message": "The WhatsApp extension disconnected; the message was not sent.",
                            }))
                    elif intent == "no":
                        pending_whatsapp.pop(request_id, None)
                        await broadcast_to_whatsapp({"type": "cancel_whatsapp", "requestId": request_id})
                        await websocket.send(json.dumps({"type": "whatsapp_cancelled"}))
                    else:
                        await websocket.send(json.dumps({"type": "whatsapp_repeat_confirmation"}))
                continue

            if message["type"] == "whatsapp_request":
                if message.get("wake") != "true" and time.monotonic() >= awake_until:
                    continue
                request_id = uuid.uuid4().hex
                pending_whatsapp[request_id] = {
                    "voice": websocket,
                    "contact": message["contact"],
                    "text": message["text"],
                    "stage": "preparing",
                }
                delivered = await broadcast_to_whatsapp({
                    "type": "prepare_whatsapp",
                    "requestId": request_id,
                    "contact": message["contact"],
                    "text": message["text"],
                })
                if not delivered:
                    pending_whatsapp.pop(request_id, None)
                    await websocket.send(json.dumps({
                        "type": "whatsapp_error",
                        "message": "Install and enable the Jarvis WhatsApp extension, then try again.",
                    }))
                else:
                    await websocket.send(json.dumps({"type": "whatsapp_preparing", "contact": message["contact"]}))
            elif message["type"] == "open_whatsapp":
                if message.get("wake") != "true" and time.monotonic() >= awake_until:
                    continue
                if await broadcast_to_whatsapp({"type": "open_whatsapp"}):
                    await websocket.send(json.dumps({"type": "whatsapp_opening"}))
                else:
                    await websocket.send(json.dumps({
                        "type": "whatsapp_error",
                        "message": "Install and enable the Jarvis WhatsApp extension, then try again.",
                    }))
            elif message["type"] == "command":
                if message["id"] == "sleep":
                    awake_until = 0.0
                elif message.get("wake") == "true" or message["id"] == "wake-up" or time.monotonic() < awake_until:
                    awake_until = time.monotonic() + 15
                await websocket.send(json.dumps(message, ensure_ascii=False))
            elif message["type"] == "wake":
                awake_until = time.monotonic() + 15
                await websocket.send(json.dumps(message, ensure_ascii=False))
            elif message["type"] == "unrecognized":
                await websocket.send(json.dumps(message, ensure_ascii=False))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        voice_clients.discard(websocket)
        whatsapp_clients.discard(websocket)
        for request_id, request in tuple(pending_whatsapp.items()):
            if request["voice"] is websocket:
                pending_whatsapp.pop(request_id, None)


async def main() -> None:
    global face_detector
    face_detector = cv2.CascadeClassifier(str(FACE_CASCADE_PATH))
    if face_detector.empty():
        raise RuntimeError(f"Could not load the local face detector: {FACE_CASCADE_PATH}")
    async with websockets.serve(
        handle_client,
        HOST,
        PORT,
        origins=[re.compile(rf"(?:http://{re.escape(HOST)}:{HTTP_PORT}|chrome-extension://[a-p]{{32}})")],
        max_size=65536,
        ping_timeout=180,
    ):
        page_server = ThreadingHTTPServer((HOST, HTTP_PORT), PageHandler)
        page_thread = Thread(target=page_server.serve_forever, daemon=True)
        page_thread.start()
        phone_server = None
        phone_thread = None
        companion_server = None
        lan_ip = None
        try:
            lan_ip = phone_companion.select_lan_ipv4()
            tls_context = phone_companion.make_companion_tls_context(lan_ip)
            phone_server = ThreadingHTTPServer(
                (lan_ip, phone_companion.HTTPS_PORT),
                phone_companion.PhonePageHandler,
            )
            phone_server.socket = tls_context.wrap_socket(phone_server.socket, server_side=True)
            phone_thread = Thread(target=phone_server.serve_forever, daemon=True)
            phone_thread.start()
            companion_server = await websockets.serve(
                phone_companion.PairingBroker().handle,
                lan_ip,
                phone_companion.WSS_PORT,
                origins=[
                    re.compile(rf"^{re.escape(origin)}$")
                    for origin in (
                        f"http://127.0.0.1:{HTTP_PORT}",
                        f"http://localhost:{HTTP_PORT}",
                        phone_companion.PHONE_ORIGIN,
                    )
                ],
                ssl=tls_context,
                max_size=phone_companion.MAX_SIGNAL_BYTES,
                max_queue=16,
                ping_timeout=30,
                close_timeout=5,
            )
        except (OSError, RuntimeError, ValueError) as error:
            if phone_server is not None:
                phone_server.shutdown()
                phone_server.server_close()
            if phone_thread is not None:
                phone_thread.join(timeout=2)
            phone_server = None
            phone_companion.PHONE_ORIGIN = ""
            print(f"Phone camera companion unavailable: {error}")

        print(f"Local offline voice server ready at ws://{HOST}:{PORT}")
        print(f"Character page is available at http://{HOST}:{HTTP_PORT}/")
        if lan_ip and companion_server:
            print(f"Phone camera page: https://{lan_ip}:{phone_companion.HTTPS_PORT}/phone")
            print(f"Install this local CA on the phone: {phone_companion.CA_CERT_PATH}")
            print("Phone setup and private-network firewall instructions: PHONE-CAMERA-SETUP.md")
        if os.environ.get("JARVIS_NO_BROWSER") != "1":
            webbrowser.open(f"http://{HOST}:{HTTP_PORT}/")
        try:
            await asyncio.Future()
        finally:
            if companion_server is not None:
                companion_server.close()
                await companion_server.wait_closed()
            page_server.shutdown()
            page_server.server_close()
            if phone_server is not None:
                phone_server.shutdown()
                phone_server.server_close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLocal offline voice server stopped.")
