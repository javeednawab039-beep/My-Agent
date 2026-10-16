# Jarvis WhatsApp Bridge

This Chromium extension connects the local Jarvis page to WhatsApp Web. It only works while `start-local-voice.bat` is running and WhatsApp Web is open and logged in.

## Install

1. Start `start-local-voice.bat` and leave its window open.
2. In Chrome or Edge, open the extensions page (`chrome://extensions` or `edge://extensions`).
3. Turn on **Developer mode**, choose **Load unpacked**, and select this `whatsapp-extension` folder.
4. Refresh or open `https://web.whatsapp.com/`, then sign in if prompted.
5. Return to Jarvis at `http://127.0.0.1:8000/`.

## Voice workflow

- Choose English or Urdu before starting the microphone.
- Say “Jarvis, open WhatsApp” or use the **Open WhatsApp Web** button.
- Say “Jarvis, message to Ali saying I will arrive at five” or “Jarvis, علی کو پیغام بھیجو: میں پانچ بجے آؤں گا”.
- Jarvis searches for an exact chat/contact name and puts the message in the draft box. If more than one result has that name, it stops rather than choosing a recipient. It does not send at this stage.
- Jarvis reads the recipient and complete message aloud. Only the spoken “yes, send it” / “ہاں” confirmation sends it. Say “no, cancel” / “نہیں” to discard it.

Voice audio is processed by the local Whisper model on this computer. The extension can read and operate WhatsApp Web because its content script interacts with the open page; use it only in your own signed-in browser.
