import requests
import sqlite3 as lite
from time import sleep

TIMEOUT = 60
AUTH_TOKEN = '[[INSERT-AUTH-TOKEN]]'
BASE_URL = 'https://[[INSERT-COMPANY-NAME]].supportbee.com/'
HEADERS = {'Content-type': 'application/json', 'Accept': 'application/json'}
requests.packages.urllib3.disable_warnings()

class SupportBee():
    def __init__(self):
        self.base_url = BASE_URL
        self.auth_token = AUTH_TOKEN
        self.client = requests.session()
        self.client.headers.update(HEADERS)
        self.total_tickets = self.get_total_ticket_count()
        self.total_pages = self.total_tickets // 100 + 1
        self.con = lite.connect('supportbee.sqlite')
        self.clean_n_create_tables()
        self.start_page = int(input(f"[REQUIRED] WHICH PAGE WOULD YOU LIKE TO START FROM [1-{self.total_pages}]: "))
        print("--" * 20)

    def get_total_ticket_count(self):
        url = f"{BASE_URL}/tickets?auth_token={AUTH_TOKEN}&archived=any&per_page=1&page=1"
        response = self.client.get(url, verify=False, headers=HEADERS)
        if response.status_code == 200:
            page = response.json()
            total_tickets = page['total']
            print(f"[+] GOT TOTAL TICKETS COUNT: {total_tickets}")
            return total_tickets
        else:
            print(f"[!] GOT TOTAL TICKETS COUNT")
            return None

    def clean_n_create_tables(self):
        with self.con:
            cur = self.con.cursor()
            # print("[I] CLEANING DATABASE")
            # cur.execute("DROP TABLE IF EXISTS Tickets")
            # cur.execute("DROP TABLE IF EXISTS TicketAttachments")
            # cur.execute("DROP TABLE IF EXISTS Replies")
            # cur.execute("DROP TABLE IF EXISTS ReplyAttachments")
            # cur.execute("DROP TABLE IF EXISTS Comments")
            # cur.execute("DROP TABLE IF EXISTS CommentAttachments")
            # print("[+] DATABASE CLEANED")

            print("[I] CREATING TABLES")
            cur.execute("CREATE TABLE IF NOT EXISTS Tickets(Id INTEGER PRIMARY KEY, SupportbeeID TEXT, Subject TEXT, CreationDate TEXT, CreatedBy TEXT, AssignedTo TEXT, Content TEXT, Label TEXT, Status TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS TicketAttachments(Id INTEGER PRIMARY KEY, TicketID INT, SupportbeeID TEXT, FileName TEXT, CreationDate TEXT, ContentType TEXT, File BLOB)")
            cur.execute("CREATE TABLE IF NOT EXISTS Replies(Id INTEGER PRIMARY KEY, TicketID INT, SupportbeeID TEXT, Subject TEXT, CreationDate TEXT, Replier TEXT, Content TEXT, Label TEXT, Status TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS ReplyAttachments(Id INTEGER PRIMARY KEY, ReplyID INT, SupportbeeID TEXT, FileName TEXT, CreationDate TEXT, ContentType TEXT, File BLOB)")
            cur.execute("CREATE TABLE IF NOT EXISTS Comments(Id INTEGER PRIMARY KEY, SupportbeeID TEXT, CreationDate TEXT, CreatedBy TEXT, Content TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS CommentAttachments(Id INTEGER PRIMARY KEY, CommentId INT, FileName TEXT, CreationDate TEXT, ContentType TEXT, File BLOB)")
            print("[+] TABLES CREATED")


    def get_ticket_data(self, page_count):
        print(f"[I][{page_count}/{self.total_pages}] GETTING TICKET DATA FROM PAGE")
        url = f"{BASE_URL}/tickets?auth_token={AUTH_TOKEN}&archived=any&per_page=100&page={page_count}"
        resp = self.client.get(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            print(f"[+][{page_count}/{self.total_pages}] GOT TICKET DATA")
            json_data = resp.json()
            total_tickets = len(json_data['tickets'])
            ticket_count = 0
            for idx, ticket in enumerate(json_data['tickets'], start=1):
                ticket_id = ticket["id"]
                print(f"[I][{idx}/{total_tickets}] TICKET DATA: {ticket_id}")
                ticket_subject = ticket['subject']
                ticket_created_at = ticket['created_at']
                ticket_email = ticket['requester']['email']
                ticket_html = ticket['content']['html']

                ticket_assigned_to = ''
                if 'current_assignee' in ticket:
                    if 'user' in ticket['current_assignee']:
                        ticket_assigned_to = ticket['current_assignee']['user']['email']

                ticket_status = 'In Progress' if ticket['archived'] is False else 'Closed'
                ticket_label = 'imported,' + ','.join(l['name'] for l in ticket['labels'])
                with self.con:
                    cur = self.con.cursor()
                    cur.execute("INSERT INTO Tickets (SupportbeeID, Subject, CreationDate, CreatedBy, AssignedTo, Content, Label, Status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (int(ticket_id), ticket_subject, ticket_created_at, ticket_email, ticket_assigned_to, ticket_html, ticket_label, ticket_status))
                    ticket_count = cur.lastrowid
                    print(f"[+] ADDED TICKET DATA TO DATABASE: {ticket_count}")
                
                # Here we check if the ticket has any attachments. If it has attachments we need t add that to the database
                if 'attachments' in ticket['content']:
                    attachments = ticket['content']['attachments']
                    for attachment in attachments:
                        print(f"[I] ATTACHMENT FOUND FOR TICKET: {ticket_id}")
                        image_url = attachment['url']['original'] + f'?auth_token={self.auth_token}'
                        image_response = self.client.get(image_url, timeout=TIMEOUT, verify=False)
                        image = image_response.content
                        attachment_content = lite.Binary(image)
                        attachment_file_name = attachment['filename']
                        attachment_created_date = attachment['created_at']
                        attachment_content_type = attachment['content_type']
                        with self.con:
                            cur = self.con.cursor()
                            cur.execute("INSERT INTO TicketAttachments (TicketID, SupportbeeID, FileName, CreationDate, ContentType, File) VALUES (?, ?, ?, ?, ?, ?)",
                                        (ticket_count, ticket_id, attachment_file_name, attachment_created_date, attachment_content_type, attachment_content))
                            print("[+] ADDED ATTACHMENT")
                        sleep(0.5)
                

                # We need to get ticket replies if there are any and add them to the database
                sleep(0.5)
                print(f"[I] GETTING REPLIES FOR TICKET: {ticket_id}")
                replies_url = f"{self.base_url}/tickets/{ticket_id}/replies?auth_token={self.auth_token}"
                replies_response = self.client.get(replies_url, timeout=TIMEOUT)
                if replies_response.status_code == 200:
                    reply_count = 0
                    replies = replies_response.json()['replies']
                    if len(replies) != 0:
                        print(f"[+] GOT REPLIES FOR TICKET: {ticket_id}")
                        for reply in replies:
                            reply_created_date = reply['created_at']
                            reply_created_by = reply['replier']['email']
                            reply_html = ticket['content']['html']
                            with self.con:
                                cur = self.con.cursor()
                                cur.execute("INSERT INTO Replies (TicketID, SupportbeeID, Subject, CreationDate, Replier, Content, Label, Status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                            (ticket_count, ticket_id, ticket_subject, reply_created_date, reply_created_by, reply_html, ticket_label, ticket_status))
                                reply_count = cur.lastrowid
                                print(f"[+] ADDED REPLY TO THE DATABASE: {reply_count}")

                            if 'content' in reply:
                                content_attachments = reply['content']['attachments']
                                for attachment in content_attachments:
                                    print(f"[I] GETTING ATTACHMENT FOR REPLY")
                                    image_url = attachment['url']['original'] + f'?auth_token={self.auth_token}'
                                    image_response = self.client.get(image_url, timeout=TIMEOUT, verify=False)
                                    image = image_response.content
                                    reply_att_content = lite.Binary(image)
                                    reply_att_file_name = attachment['filename']
                                    reply_att_created_date = attachment['created_at']
                                    replyatt_content_type = attachment['content_type']
                                    with self.con:
                                        cur = self.con.cursor()
                                        cur.execute("INSERT INTO ReplyAttachments (ReplyID, SupportbeeID, FileName, CreationDate, ContentType, File) VALUES (?, ?, ?, ?, ?, ?)",
                                                    (reply_count, ticket_id, reply_att_file_name, reply_att_created_date, replyatt_content_type, reply_att_content))
                                        print(f"[+] ADDED ATTACHMENT FOR REPLY")
                                    sleep(0.5)
                    else:
                        print(f"[-] NO REPLIES ARE FOUND FOR TICKET: {ticket_id}")


                # We need to get ticket comments if there are any and add them to the database
                sleep(0.5)
                print(f"[I] GETTING COMMENTS FOR TICKET: {ticket_id}")
                comments_url = f"{self.base_url}/tickets/{ticket_id}/comments?auth_token={self.auth_token}"
                comments_response = self.client.get(comments_url, timeout=TIMEOUT)
                if comments_response.status_code == 200:
                    comments = comments_response.json()['comments']
                    if len(comments) != 0:
                        print("[+] GOT TICKET COMMENTS")
                        comment_id = 0
                        for comment in comments:
                            ticket_id = ticket["id"]
                            comment_created_date = comment['created_at']
                            comment_created_by = comment['commenter']['email']
                            comment_html = ticket['content']['html']
                            with self.con:
                                cur = self.con.cursor()
                                cur.execute("INSERT INTO Comments (SupportbeeID, CreationDate, CreatedBy, Content) VALUES (?, ?, ?, ?)",
                                        (ticket_id, comment_created_date, comment_created_by, comment_html))
                                comment_id = cur.lastrowid
                                print(f"[+] ADDED COMMENT TO THE DATABASE: {comment_id}")

                            c_attachments = comment['content']['attachments']
                            for attachment in c_attachments:
                                print("[I] GETTING COMMENT ATTACHMENT")
                                image_url = attachment['url']['original'] + f'?auth_token={self.auth_token}'
                                image_response = self.client.get(image_url, timeout=TIMEOUT, verify=False)
                                comment_att_content = lite.Binary(image_response.content)
                                comment_att_file_name = attachment['filename']
                                comment_att_created_date = attachment['created_at']
                                comment_att_content_type = attachment['content_type']
                                with self.con:
                                    cur = self.con.cursor()
                                    cur.execute("INSERT INTO CommentAttachments (CommentId, FileName, CreationDate, ContentType, File) VALUES (?, ?, ?, ?, ?)",
                                                (comment_id, comment_att_file_name, comment_att_created_date, comment_att_content_type, comment_att_content))
                                    print("[+] ADDED COMMENT ATTACHMENT TO THE DATABASE")
                                sleep(0.5)
                    else:
                        print("[-] NO COMMENTS ARE FOUND")
                self.con.commit()
                print("--" * 15)
        else:
            print(f"[!] COULD NOT GET TICKET DATA: STATUS CODE: {resp.status_code} | {resp.text}")
        
        sleep(2)


    def process_tickets_data(self):
        page_count = 1
        for page_count in range(self.start_page, self.total_pages+1):
            try:
                self.get_ticket_data(page_count)
            except Exception as e:
                print(f"[!] COULD NOT PROCESS PAGE: {page_count} | ERROR: {e}")

if __name__ == '__main__':
    supportbee = SupportBee()
    supportbee.process_tickets_data()
