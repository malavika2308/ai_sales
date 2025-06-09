import os
from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Twilio setup
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
twilio_number = os.getenv("TWILIO_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")
base_url = os.getenv("BASE_URL")

# Conversation log
CONVERSATION_LOG = "conversation_log.txt"
TRANSCRIPT_FILE = "latest_transcript.txt"

def append_to_log(speaker, text):
    with open(CONVERSATION_LOG, "a") as f:
        f.write(f"{speaker}: {text}\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/make_call", methods=["POST"])
def make_call():
    open(CONVERSATION_LOG, "w").close()
    open(TRANSCRIPT_FILE, "w").close()
    call = twilio_client.calls.create(
        to=target_number,
        from_=twilio_number,
        url=f"{base_url}/voice"
    )
    return jsonify({"status": "calling", "sid": call.sid})

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    response.say("Hi! This is AI4Bazaar. Are you interested in a custom website for your business?", voice="Polly.Joanna")
    response.record(
        action="/process_recording",
        transcribe=True,
        transcribe_callback="/transcription",
        max_length=10,
        play_beep=True
    )
    return str(response)

@app.route("/transcription", methods=["POST"])
def transcription():
    transcript = request.form.get("TranscriptionText", "")
    print("[TRANSCRIPTION RECEIVED]:", transcript)
    append_to_log("User", transcript)
    with open(TRANSCRIPT_FILE, "w") as f:
        f.write(transcript)
    return "", 204

@app.route("/process_recording", methods=["POST"])
def process_recording():
    try:
        with open(TRANSCRIPT_FILE, "r") as f:
            user_text = f.read().strip()
    except FileNotFoundError:
        user_text = ""

    if not user_text:
        ai_reply = "Sorry, I couldn't understand that. Could you repeat?"
    else:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        try:
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are AI4Bazaar, an AI that sells custom websites."},
                    {"role": "user", "content": user_text}
                ]
            )
            ai_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT ERROR]", e)
            ai_reply = "Sorry, something went wrong on my end."

    append_to_log("AI4Bazaar", ai_reply)
    response = VoiceResponse()
    response.say(ai_reply, voice="Polly.Joanna")
    response.record(
        action="/process_recording",
        transcribe=True,
        transcribe_callback="/transcription",
        max_length=10,
        play_beep=True
    )
    return str(response)

@app.route("/conversation", methods=["GET"])
def conversation():
    try:
        with open(CONVERSATION_LOG, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = ["No conversation yet."]
    return render_template("conversation.html", lines=lines)

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
