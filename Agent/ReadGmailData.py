import logging
import re
from googleapiclient.discovery import build
import base64
from langchain_openai import ChatOpenAI
from bs4 import BeautifulSoup
import tiktoken
from GmailOAuth import GmailOAuth
from EmailDAO import EmailDAO
from EmailProcessing import EmailProcessing

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, openai_api_key="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")
tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")

# Step 2: Define search query based on keywords
keywords = 'funding OR "series" OR "pre-seed" OR "seed" OR "angel" OR "venture" OR "startup" OR "pitch" OR "investment" OR "deck" OR "fundraising" OR "strategic Investors"'
query = f"({keywords})"

class WorkOnGmailData:
    def __init__(self):
        pass

    # Function to truncate content to a specified token limit
    def truncate_to_token_limit(self,content, max_tokens=15000):
        tokens = tokenizer.encode(content)
        if len(tokens) > max_tokens:
            truncated_tokens = tokens[:max_tokens]
            truncated_content = tokenizer.decode(truncated_tokens)
            return truncated_content
        return content

    # Function to fetch and decode email body
    def get_email_body(self,payload):
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    body_data = part['body']['data']
                    body = base64.urlsafe_b64decode(body_data).decode("utf-8")
                    break
                elif part['mimeType'] == 'text/html':
                    body_data = part['body']['data']
                    html_content = base64.urlsafe_b64decode(body_data).decode("utf-8")
                    soup = BeautifulSoup(html_content, 'html.parser')
                    body = soup.get_text()
        else:
            body_data = payload.get('body', {}).get('data')
            if body_data:
                mime_type = payload.get('mimeType', '')
                decoded_content = base64.urlsafe_b64decode(body_data).decode("utf-8")
                if mime_type == 'text/html':
                    soup = BeautifulSoup(decoded_content, 'html.parser')
                    body = soup.get_text()
                else:
                    body = decoded_content
        cleaned_body = re.sub(r'\s+', ' ', body).strip()
        return cleaned_body


    def fetch_emails(self,api_resource, query, max_results=10000):
        results_list = []
        next_page_token = None

        while len(results_list) < max_results:
            response = api_resource.users().messages().list(
                userId='me', q=query, maxResults=50, pageToken=next_page_token
            ).execute()

            messages = response.get('messages', [])
            for msg in messages:
                message_data = api_resource.users().messages().get(userId='me', id=msg['id']).execute()
                payload = message_data.get("payload", {})

                # Extract key metadata
                subject = next((header["value"] for header in payload.get("headers", []) if header["name"] == "Subject"), "")
                sender = next((header["value"] for header in payload.get("headers", []) if header["name"] == "From"), "")
                to = next((header["value"] for header in payload.get("headers", []) if header["name"] == "To"), "")
                body = self.get_email_body(payload)

                # Store data in the list
                email_data = {
                    "threadId": msg['threadId'],
                    "messageId": msg['id'],
                    "subject": subject,
                    "from": sender,
                    "to": to,
                    "body": body,
                }
                results_list.append(email_data)

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        return results_list

    def filter_investment_related_emails(self,llm, email_data):
        email_body = self.truncate_to_token_limit(email_data['body'])
        prompt_template = """
        Evaluate the email content and determine if it involves any fundraising, investment opportunities, or attempts to secure funding. Consider the following indicators:
        - The sender is seeking investment or funding.
        - The email mentions investment terms such as "raising funds," "seed funding," "series funding," "pitch," "investors," or "financial support."
        - The email includes offers to discuss investment opportunities or pitches.
        
        Email Content:
        {email_body}
        
        Please answer "Yes" if the email is related to seeking or offering fundraising or investment opportunities. Answer "No" if it is not. 
        Also, briefly explain your reasoning.
        """

        prompt = prompt_template.format(email_body=email_body)
        response = llm.invoke(prompt).content.strip()
        return response.lower().startswith("yes")

    def filter_and_save_investment_emails(self,user_id):
        oauth = GmailOAuth()
        user_token =  oauth.get_user_token(user_id)
        logging.info("User Token - ", user_token)
        credentials = oauth.get_user_credentials(user_id)
        logging.info("credentials - ", credentials)
        api_resource = build("gmail", "v1", credentials=credentials)
        fetched_emails = self.fetch_emails(api_resource, query)
        logging.info("Fetched emails size - ", len(fetched_emails))
        investment_emails = []
        for email_data in fetched_emails:
            is_related = self.filter_investment_related_emails(llm, email_data)
            if is_related:
                investment_emails.append(email_data)
        logging.info("Investment emails size - ", len(investment_emails))
        email_dao =  EmailDAO()
        inserted_ids = email_dao.store_investment_emails_bulk(investment_emails, user_token.id)
        return inserted_ids


    def process_filtered_emails(self,user_id):
        oauth = GmailOAuth()
        user_token =  oauth.get_user_token(user_id)
        email_dao =  EmailDAO()
        investment_emails = email_dao.get_emails(user_token.id)
        email_processor = EmailProcessing()
        for email in investment_emails:
            extracted_response_text = email_processor.process_email(email)
        return "Summarized all Investment Emails"

    def categorise_score_emails(self,user_id):
        oauth = GmailOAuth()
        user_token =  oauth.get_user_token(user_id)
        email_dao =  EmailDAO()
        investment_emails = email_dao.get_emails(user_token.id)
        email_processor = EmailProcessing()
        for email in investment_emails:
            extracted_response_text = email_processor.categorise_and_score_emails(email)
        return "categorised and scored all Investment Emails"

"""


#  Processing Filtered Email in the database
email_dao =  EmailDAO()
email_processor = EmailProcessing()
investment_emails = email_dao.get_processed_emails(user_token_id)
for email in investment_emails:
    email_processor.process_email(email)

"""



