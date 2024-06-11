import mailbox
import openai
import time
import string
import re
import html
import tkinter as tk
from tkinter import filedialog, messagebox
from tqdm import tqdm

# Global Variables
RATE_LIMIT_RPM = 3  # 3 requests per minute
RATE_LIMIT_TPM = 40_000  # 40,000 tokens per minute
DAILY_REQUEST_LIMIT = 200  # 200 requests per day
DAILY_TOKEN_LIMIT = 200_000  # 200,000 tokens per day

requests_made = 0
tokens_used = 0
daily_requests = 0
daily_tokens = 0
last_checked = time.time()

# Initialize OpenAI API
openai.api_key = ''  # Replace with your OpenAI API key

# Helper Functions
def reset_limits():
    global requests_made, tokens_used, last_checked
    requests_made = 0
    tokens_used = 0
    last_checked = time.time()

def check_and_wait():
    global last_checked, requests_made, tokens_used, daily_requests, daily_tokens
    elapsed_time = time.time() - last_checked
    if elapsed_time < 60:
        wait_time = 60 - elapsed_time
        print(f"Rate limit reached. Waiting for {wait_time:.2f} seconds...")
        time.sleep(wait_time)
    reset_limits()

def log_api_usage():
    print(f"Requests Made: {requests_made}/{RATE_LIMIT_RPM}, Tokens Used: {tokens_used}/{RATE_LIMIT_TPM}")
    print(f"Daily Requests Made: {daily_requests}/{DAILY_REQUEST_LIMIT}, Daily Tokens Used: {daily_tokens}/{DAILY_TOKEN_LIMIT}")

def strip_html(text):
    if text is None:
        return None
    return re.sub('<[^<]+?>', '', html.unescape(text))

def sanitize_string(s):
    return ''.join(filter(lambda x: x in string.printable, s)) if s else None

def end_at_sent_from(text):
    return text.split("Sent from")[0].strip() if text else None

def map_gpt_sentiment(sentiment_text):
    sentiment_text = sentiment_text.lower()
    return "negative" if "negative" in sentiment_text else "positive" if "positive" in sentiment_text else "neutral"

def analyze_sentiment_with_chatgpt(text):
    global requests_made, tokens_used, daily_requests, daily_tokens
    MAX_TOKENS = 1900  
    text = text[:MAX_TOKENS]

    if time.time() - last_checked > 60:
        reset_limits()

    if requests_made + 1 > RATE_LIMIT_RPM or tokens_used + len(text.split()) > RATE_LIMIT_TPM or daily_requests + 1 > DAILY_REQUEST_LIMIT or daily_tokens + len(text.split()) > DAILY_TOKEN_LIMIT:
        check_and_wait()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"Please provide a detailed sentiment analysis for the statement: \"{text}\""}
    ]
    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, max_tokens=150)
    except openai.error.RateLimitError:
        print("Rate limit exceeded. Waiting and retrying...")
        check_and_wait()
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, max_tokens=150)
    except openai.error.InsufficientQuotaError:
        print("Insufficient quota. Please check your plan and billing details.")
        return "quota_exceeded"

    requests_made += 1
    tokens_used += len(text.split())
    daily_requests += 1
    daily_tokens += len(text.split())
    log_api_usage()

    raw_sentiment = response['choices'][0]['message']['content'].strip()
    return map_gpt_sentiment(raw_sentiment)

def analyze_messages_and_export_to_txt(inbox_path, txt_file_path):
    mbox = mailbox.mbox(inbox_path)
    total_emails = len(mbox)

    with open(txt_file_path, 'w') as f:
        for idx, message in tqdm(enumerate(mbox), total=total_emails, desc="Processing emails"):
            try:
                if message.is_multipart():
                    email_content_parts = [
                        sanitize_string(part.get_payload(decode=True).decode(errors="replace"))
                        for part in message.get_payload() if part.get_payload(decode=True)
                    ]
                    email_content = ' '.join(filter(None, email_content_parts))
                else:
                    payload = message.get_payload(decode=True)
                    if payload:
                        email_content = sanitize_string(payload.decode(errors="replace"))
                    else:
                        email_content = None

                email_content = end_at_sent_from(email_content)
                email_content = strip_html(email_content)

                if email_content and not email_content.isspace():
                    sentiment = analyze_sentiment_with_chatgpt(email_content)
                    if sentiment == "quota_exceeded":
                        print("Quota exceeded, stopping analysis.")
                        break

                    sender = message['From']
                    sender_email = sender.split()[-1].strip('<>')
                    sender_name = sender.replace(sender_email, '').strip()

                    f.write(f"Subject: {message['subject']}\n")
                    f.write(f"Sender Name: {sender_name}\n")
                    f.write(f"Sender Email: {sender_email}\n")
                    f.write(f"Sentiment: {sentiment}\n")
                    f.write("Email Content:\n")
                    f.write(email_content + "\n")
                    f.write('-'*100 + "\n")

                print(f"Processed {idx + 1} emails...")
            except Exception as e:
                print(f"\nError processing email {idx + 1}: {str(e)}")

# GUI Functions
def analyze_inbox_file():
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    inbox_path = filedialog.askopenfilename(title="Select the file")

    root.destroy()  # Close the root window

    if not inbox_path:
        return  # User cancelled the file dialog

    txt_file_path = "sentiment_results_gpt3.txt"
    try:
        analyze_messages_and_export_to_txt(inbox_path, txt_file_path)
        print("Analysis completed successfully!")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

def main_gui():
    root = tk.Tk()
    root.title("Sentiment Analysis")

    # Create a frame for some padding
    frame = tk.Frame(root, padx=20, pady=20)
    frame.pack(padx=10, pady=10)

    # Add a button to select and analyze the INBOX file
    btn_select_file = tk.Button(frame, text="Select INBOX file and analyze", command=analyze_inbox_file)
    btn_select_file.pack()

    root.mainloop()

if __name__ == "__main__":
    main_gui()
