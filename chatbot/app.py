import os
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

# Files for storing conversation
CONVERSATION_LOG = "conversation_log.txt"
TRANSCRIPT_FILE = "latest_transcript.txt"

# OpenAI setup
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging function
def append_to_log(speaker, text):
    try:
        with open(CONVERSATION_LOG, "a") as f:
            f.write(f"{speaker}: {text}\n")
        print(f"[LOGGED] {speaker}: {text}")
    except Exception as e:
        print("[LOGGING ERROR]", e)

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
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speech_timeout="auto",
        barge_in=True
    )
    gather.say("Hi! This is AI4Bazaar. Are you interested in a custom website for your business?", voice="Polly.Joanna")
    return str(response)

@app.route("/process_recording", methods=["POST"])
def process_recording():
    user_text = request.form.get("SpeechResult", "").strip()
    print("[USER INPUT]:", user_text)

    if not user_text:
        ai_reply = "Sorry, I couldn't understand that. Could you repeat?"
        append_to_log("AI4Bazaar", ai_reply)
    else:
        append_to_log("User", user_text)
        try:
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are AI4Bazaar, a friendly AI that sells websites. Keep your answers short, clear, and conversational. Never more than 2 sentences."
                    },
                    {"role": "user", "content": user_text}
                ],
                max_tokens=100,
                temperature=0.7
            )
            ai_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT ERROR]", e)
            ai_reply = "Sorry, something went wrong on my end."

        append_to_log("AI4Bazaar", ai_reply)

    # Respond and ask for next input
    response = VoiceResponse()
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speech_timeout="auto",
        barge_in=True
    )
    gather.say(ai_reply, voice="Polly.Joanna")
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
