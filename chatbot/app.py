import os
import requests
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

# OpenAI setup
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Conversation log file
CONVERSATION_LOG = "conversation_log.txt"

def append_to_log(speaker, text):
    with open(CONVERSATION_LOG, "a") as f:
        f.write(f"{speaker}: {text}\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/make_call", methods=["POST"])
def make_call():
    # Clear previous conversation
    open(CONVERSATION_LOG, "w").close()

    call = twilio_client.calls.create(
        to=target_number,
        from_=twilio_number,
        url=f"{base_url}/voice"
    )
    return jsonify({"status": "calling", "sid": call.sid})

@app.route("/voice", methods=["GET", "POST"])
def voice():
    if request.method == "GET":
        return "This route expects a POST from Twilio.", 405

    response = VoiceResponse()
    response.say("Hi! This is AI4Bazaar. Are you interested in a custom website for your business?", voice="Polly.Joanna")
    response.record(
        action="/handle_recording",
        max_length=10,
        play_beep=True
    )
    return str(response)

@app.route("/handle_recording", methods=["POST"])
def handle_recording():
    recording_url = request.form.get("RecordingUrl")
    if not recording_url:
        return "No recording URL received.", 400

    audio_url = f"{recording_url}.wav"
    audio_file_path = "user_input.wav"

    # Download the user's voice recording
    try:
        audio_data = requests.get(audio_url).content
        with open(audio_file_path, "wb") as f:
            f.write(audio_data)
    except Exception as e:
        return f"Error downloading audio: {str(e)}", 500

    # Transcribe with Whisper
    try:
        with open(audio_file_path, "rb") as audio_file:
            transcript_response = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        user_text = transcript_response.text.strip()
        append_to_log("User", user_text)
        print("User said:", user_text)
    except Exception as e:
        return f"Transcription error: {str(e)}", 500

    # Generate GPT-4 reply
    try:
        gpt_response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are AI4Bazaar, an AI that sells custom websites."},
                {"role": "user", "content": user_text}
            ]
        )
        ai_reply = gpt_response.choices[0].message.content.strip()
        append_to_log("AI4Bazaar", ai_reply)
        print("AI reply:", ai_reply)
    except Exception as e:
        return f"GPT-4 error: {str(e)}", 500

    # Respond with AI voice
    response = VoiceResponse()
    response.say(ai_reply, voice="Polly.Joanna")

    # Loop back for next input
    response.record(
        action="/handle_recording",
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
