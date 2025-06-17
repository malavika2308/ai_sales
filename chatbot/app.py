import os
import time
import threading
from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from openai import OpenAI
import smtplib
from email.message import EmailMessage

load_dotenv()
app = Flask(__name__)

# Twilio setup
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
twilio_number = os.getenv("TWILIO_NUMBER")
base_url = os.getenv("BASE_URL")

# OpenAI setup
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Files
LOG_PATH = "conversation_log.txt"
TRANSCRIPT_FILE = "latest_transcript.txt"

# Log conversation with timestamp
def append_to_log(speaker, text):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_PATH, "a") as f:
        f.write(f"[{timestamp}] {speaker}: {text}\n")

# Send email with formatted content
def send_email_with_conversation(judgment="Unknown", summary="No summary available."):
    try:
        with open(LOG_PATH, "r") as f:
            conversation_text = f.read()
    except FileNotFoundError:
        conversation_text = "No conversation found."

    msg = EmailMessage()
    msg["Subject"] = "AI4Bazaar Call Transcript & Judgment"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = os.getenv("EMAIL_RECEIVER")
    msg.set_content(f"""
Hello,

Here is the transcript and analysis of the recent AI sales call.

📅 Judgment: {judgment}

Summary:
{summary}

Please find the attached transcript for your review.

Regards,
AI4Bazaar Bot
""")
    msg.add_attachment(conversation_text, filename="conversation_log.txt")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
            smtp.send_message(msg)
    except Exception as e:
        print("[Email Error]", e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/make_call", methods=["POST"])
def make_call():
    data = request.get_json()
    target_number = data.get("target_number")

    if not target_number or not target_number.startswith("+"):
        return jsonify({"error": "Please enter a valid phone number with country code."}), 400

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
    append_to_log("System", f"📞 Call initiated to {target_number} at {time.ctime()}")
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
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are AI4Bazaar, a smart and friendly AI sales assistant. Your job is to sell websites to small business owners in a helpful, persuasive, and clear tone. Be confident but not pushy. Use everyday language, ask meaningful questions, and guide the user toward interest or booking a meeting."},
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
        speechTimeout="auto",
        bargeIn=True
    )
    gather.say(ai_reply, voice="Polly.Joanna")

    return str(response)

@app.route("/end_call", methods=["POST"])
def end_call():
    def handle_judgment_and_email():
        try:
            with open(LOG_PATH, "r") as f:
                convo = f.read()
        except FileNotFoundError:
            convo = ""

        try:
            judgment_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an assistant. Given this sales call transcript, respond only with 'Positive' or 'Negative' based on whether the user seemed interested."},
                    {"role": "user", "content": convo}
                ]
            )
            judgment = judgment_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT Judgment Error]", e)
            judgment = "Unknown"

        try:
            summary_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Summarize this sales call in 2-3 bullet points."},
                    {"role": "user", "content": convo}
                ]
            )
            summary = summary_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT Summary Error]", e)
            summary = "No summary available."

        send_email_with_conversation(judgment, summary)

    threading.Thread(target=handle_judgment_and_email).start()
    return jsonify({"status": "Conversation processing started"})

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
