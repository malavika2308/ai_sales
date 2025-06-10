import os
import time
from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Pause
from dotenv import load_dotenv
from openai import OpenAI
import smtplib
from email.message import EmailMessage

load_dotenv()
app = Flask(__name__)

# Twilio setup
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
twilio_number = os.getenv("TWILIO_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")
base_url = os.getenv("BASE_URL")

# Conversation log
LOG_PATH = "conversation_log.txt"
TRANSCRIPT_FILE = "latest_transcript.txt"

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def append_to_log(speaker, text):
    with open(LOG_PATH, "a") as f:
        f.write(f"{speaker}: {text}\n")

def send_email_with_conversation(judgment="Unknown"):
    try:
        with open(LOG_PATH, "r") as f:
            conversation_text = f.read()
    except FileNotFoundError:
        conversation_text = "No conversation found."

    msg = EmailMessage()
    msg["Subject"] = "AI4Bazaar Call Transcript & Judgment"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = os.getenv("EMAIL_RECEIVER")
    msg.set_content(f"Call Judgment: {judgment}\n\nTranscript attached.")
    msg.add_attachment(conversation_text, filename="conversation_log.txt")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        smtp.send_message(msg)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/make_call", methods=["POST"])
def make_call():
    open(LOG_PATH, "w").close()
    open(TRANSCRIPT_FILE, "w").close()
    call = twilio_client.calls.create(
        to=target_number,
        from_=twilio_number,
        url=f"{base_url}/voice",
        status_callback=f"{base_url}/end_call",
        status_callback_event=["completed"],
        status_callback_method="POST"
    )
    return jsonify({"status": "calling", "sid": call.sid})

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speechTimeout="auto",
        bargeIn=True
    )
    gather.say("Hi! This is AI4Bazaar. Are you interested in a custom website for your business?", voice="Polly.Joanna")
    return str(response)

@app.route("/process_recording", methods=["POST"])
def process_recording():
    user_text = request.form.get("SpeechResult", "").strip()

    if not user_text:
        ai_reply = "Sorry, I couldn't understand that. Could you repeat?"
        append_to_log("AI4Bazaar", ai_reply)
    else:
        append_to_log("User", user_text)
        try:
            gpt_response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are AI4Bazaar, a witty AI sales assistant. Your goal is to sell websites to small business owners. Use humor, make the value clear, and sound like a clever friend. Keep replies short and persuasive."},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=100
            )
            ai_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT ERROR]", e)
            ai_reply = "Oops! Something glitched. Mind saying that again?"

        append_to_log("AI4Bazaar", ai_reply)

    response = VoiceResponse()
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speechTimeout="5",
        bargeIn=True
    )
    gather.say(ai_reply, voice="Polly.Joanna")

    # Add polite goodbye if no response within 30 seconds
    response.pause(length=30)
    response.say("Looks like you're busy. Feel free to call us anytime. Goodbye!", voice="Polly.Joanna")
    response.hangup()
    return str(response)

@app.route("/end_call", methods=["POST"])
def end_call():
    try:
        with open(LOG_PATH, "r") as f:
            convo = f.read()
    except FileNotFoundError:
        convo = ""

    try:
        result = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an assistant. Given this sales call transcript, respond only with 'Positive' or 'Negative' based on whether the user seemed interested."},
                {"role": "user", "content": convo}
            ]
        )
        judgment = result.choices[0].message.content.strip()
    except Exception as e:
        print("[GPT Judgment Error]", e)
        judgment = "Unknown"

    send_email_with_conversation(judgment)
    return jsonify({"status": "Conversation emailed", "outcome": judgment})

@app.route("/conversation", methods=["GET"])
def conversation():
    try:
        with open(LOG_PATH, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = ["No conversation yet."]
    return render_template("conversation.html", lines=lines)

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
