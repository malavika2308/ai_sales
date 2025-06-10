import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
app = Flask(__name__)

# Twilio setup
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
twilio_number = os.getenv("TWILIO_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")
base_url = os.getenv("BASE_URL")

# Files
TRANSCRIPT_FILE = "latest_transcript.txt"
JSON_LOG_FILE = "conversation_log.json"

# OpenAI
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Append to JSON log with timestamp
def append_to_log(speaker, text):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "speaker": speaker,
        "text": text
    }

    if not os.path.exists(JSON_LOG_FILE):
        with open(JSON_LOG_FILE, "w") as f:
            json.dump([], f)

    with open(JSON_LOG_FILE, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data.append(log_entry)
        f.seek(0)
        json.dump(data, f, indent=2)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/make_call", methods=["POST"])
def make_call():
    # Clear logs at start of each call
    open(TRANSCRIPT_FILE, "w").close()
    open(JSON_LOG_FILE, "w").write("[]")

    call = twilio_client.calls.create(
        to=target_number,
        from_=twilio_number,
        url=f"{base_url}/voice"
    )
    return jsonify({"status": "calling", "sid": call.sid})

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    response.pause(length=0.5)
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speechTimeout="auto",
        bargeIn=True
    )
    gather.say("Hi! This is AI4Bazaar. Are you interested in a custom website for your business?", voice="Polly.Joanna")
    return str(response)

@app.route("/transcription", methods=["POST"])
def transcription():
    transcript = request.form.get("TranscriptionText", "")
    print("[TRANSCRIPTION RECEIVED]:", transcript)
    append_to_log("User", transcript)
    with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(transcript)
    return "", 204

@app.route("/process_recording", methods=["POST"])
def process_recording():
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            user_text = f.read().strip()
    except FileNotFoundError:
        user_text = ""

    if not user_text:
        ai_reply = "Sorry, I couldn't understand that. Could you repeat?"
    else:
        append_to_log("User", user_text)
        try:
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are AI4Bazaar, a friendly AI sales assistant. Keep responses short and clear, under two sentences."},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=100
            )
            ai_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT ERROR]", e)
            ai_reply = "Something went wrong. Please try again later."

        append_to_log("AI4Bazaar", ai_reply)

    # Create Twilio response with interruption support
    response = VoiceResponse()
    response.pause(length=0.5)
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speechTimeout="auto",
        bargeIn=True
    )
    gather.say(ai_reply, voice="Polly.Joanna")

    return str(response)

@app.route("/conversation", methods=["GET"])
def conversation():
    try:
        with open(JSON_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    return render_template("conversation.html", lines=[f"{entry['speaker']}: {entry['text']}" for entry in data])

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
