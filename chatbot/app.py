import os
from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
app = Flask(__name__)

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
twilio_number = os.getenv("TWILIO_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")
base_url = os.getenv("BASE_URL")

# File paths
CONVERSATION_LOG = "conversation_log.txt"
TRANSCRIPT_FILE = "latest_transcript.txt"
RESULT_FILE = "call_result.txt"

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
                    {"role": "system", "content": "You are AI4Bazaar, a friendly AI assistant that sells websites. Keep replies very short and clear, 1-2 sentences only."},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=100
            )
            ai_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("[GPT ERROR]", e)
            ai_reply = "Sorry, something went wrong."

        append_to_log("AI4Bazaar", ai_reply)

    response = VoiceResponse()
    gather = response.gather(
        input="speech",
        action="/process_recording",
        speechTimeout="5",  # Extended to 5 seconds pause
        bargeIn=True
    )
    gather.say(ai_reply, voice="Polly.Joanna")
    return str(response)

@app.route("/end_call", methods=["POST"])
def end_call():
    # Send full conversation to GPT and ask if it was a successful/positive call
    try:
        with open(CONVERSATION_LOG, "r") as f:
            conversation = f.read()

        result_prompt = (
            "Below is a sales conversation. Your job is to analyze if the customer showed a positive interest "
            "in the offer. Just reply with 'Positive' or 'Negative'.\n\n"
            f"{conversation}"
        )

        result = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an evaluator who judges customer interest in sales calls."},
                {"role": "user", "content": result_prompt}
            ],
            max_tokens=10
        )

        decision = result.choices[0].message.content.strip()
        with open(RESULT_FILE, "w") as f:
            f.write(f"Call result: {decision}")

        return jsonify({"result": decision})
    except Exception as e:
        print("[FINAL EVAL ERROR]", e)
        return jsonify({"result": "Error"}), 500

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
