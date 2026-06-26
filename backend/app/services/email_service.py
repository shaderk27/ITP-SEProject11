import os

#todo after setup the email

# SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
# SENDER_EMAIL = os.getenv("SENDER_EMAIL")

class EmailService:
    def send_temp_password(self, email: str, name: str, temp_password: str) -> None:
        message = Mail(
            from_email=SENDER_EMAIL,
            to_emails=email,
            subject="Your Temporary Password",
            plain_text_content=(
                f"Hi {name},\n\n"
                f"Your temporary password is: {temp_password}\n\n"
                f"It expires in 1 hour. Please log in and change your password immediately.\n\n"
                f"If you did not request this, please contact your administrator."
            )
        )
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(message)